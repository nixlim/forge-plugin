from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
import signal
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from forge_cli.engine._review_attempt_proc import (
    group_members as _group_members,
)
from forge_cli.engine._review_attempt_proc import (
    process_probe as _process_probe,
)
from forge_cli.engine._review_attempt_proc import (
    send_group_signal as _send_group_signal,
)
from forge_cli.engine._review_attempt_proc import (
    wait_group_empty as _wait_group_empty,
)
from forge_cli.engine._review_wrapper import IDENTITY_SCHEMA, exclusive_publish, open_owner_regular
from forge_cli.engine._review_wrapper import (
    attempt_publication_lock as attempt_publication_lock,
)
from forge_cli.engine._review_wrapper_io import COMPLETION_SCHEMA
from forge_cli.envelope import Outcome, Refusal

IDENTITY_NAME, COMPLETION_NAME, STALE_NAME = "identity.json", "completion.json", "stale.json"
NEWER_SHAPE_LITERAL = (
    "forge: review request shape newer than this plugin — finish or abort the chain "
    "on the requesting version"
)
_IDENTITY_KEYS = set(
    "schema attempt wrapper_pid pgid wrapper_birth reviewer_pid reviewer_birth started_at".split()
)
COMPLETION_KEYS = set(
    "argv_digest attempt completed_at environment_names error events_bytes observed_model "
    "omitted_short pgid prompt_digest provider returncode reviewer_pid route_sha256 "
    "route_source sandbox schema started_at timed_out verdict_digest verdict_size "
    "wrapper_pid".split()
)
COMPLETION_ERRORS = frozenset(
    "events cap|stderr cap|not-logged-in|claude result error|verdict missing|verdict empty|"
    "verdict cap|verdict invalid|wrapper failure|abandoned|wrapper-lost|"
    "cancelled".split("|")
)
_COMPLETION_KEYS = COMPLETION_KEYS
_COMPLETION_ERRORS = COMPLETION_ERRORS
_HEX = frozenset("0123456789abcdef")


def launch_failure(exc: Exception) -> str:
    code = getattr(exc, "errno", None)
    return f"launch-failed: errno {code}" if type(code) is int else "launch-failed: spawn error"


class AttemptRecordError(ValueError):
    pass


class AttemptShapeNewer(AttemptRecordError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AttemptRecordError(message)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value = dict(pairs)
    _require(len(value) == len(pairs), "attempt record has duplicate JSON keys")
    return value


@dataclass(frozen=True)
class AttemptObservation:
    outcome: str
    reason: str | None = None
    identity: dict[str, Any] | None = None
    completion: dict[str, Any] | None = None
    members: tuple[int, ...] = ()


@dataclass(frozen=True)
class GroupProof:
    outcome: str
    pgid: int | None
    members: tuple[int, ...] = ()


GroupTermination = GroupProof


def cancel_identity_unproven_message(proof: GroupProof) -> str:
    return (
        "forge: review cancel refused — identity-unproven; "
        f"member PIDs {list(proof.members)}; recorded PGID {proof.pgid}; "
        "nothing was signalled"
    )


def _read_json_at(directory: int, name: str, *, limit: int = 65_536) -> dict[str, Any] | None:
    try:
        descriptor = open_owner_regular(directory, name, os.O_RDONLY)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AttemptRecordError(f"{name} is unavailable or unsafe: {exc}") from exc
    try:
        with os.fdopen(descriptor, "rb") as handle:
            data = handle.read(limit + 1)
    except OSError as exc:
        raise AttemptRecordError(f"{name} is unavailable or unsafe: {exc}") from exc
    if len(data) > limit:
        raise AttemptRecordError(f"{name} exceeds {limit} bytes")
    try:
        value = json.loads(data, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttemptRecordError(f"{name} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise AttemptRecordError(f"{name} is not a JSON object")
    return value


def _valid_birth(value: object) -> bool:
    if isinstance(value, Mapping) and value.get("kind") == "linux-proc":
        return set(value) == {"kind", "boot_id", "starttime"} and (
            isinstance(value.get("boot_id"), str) and bool(value["boot_id"])
            and type(value.get("starttime")) is int and value["starttime"] >= 0
        )
    return isinstance(value, Mapping) and value.get("kind") == "macos-starttime" and set(value) == {
        "kind", "seconds", "microseconds"
    } and all(type(value.get(name)) is int for name in ("seconds", "microseconds")) \
        and 0 <= value["microseconds"] < 1_000_000


def _valid_pid(value: object) -> bool:
    return type(value) is int and int(value) > 0


def _valid_attempt(value: object) -> bool:
    return isinstance(value, str) and len(value) == 24 and value.startswith("attempt-") \
        and set(value[8:]) <= _HEX


def _validate_live_identity(value: Mapping[str, Any]) -> None:
    wrapper_pid = value.get("wrapper_pid")
    pgid = value.get("pgid")
    wrapper_birth = value.get("wrapper_birth")
    _require(_valid_pid(wrapper_pid) and _valid_pid(pgid), "invalid wrapper identity")
    _require(
        wrapper_pid == pgid and (wrapper_birth is None or _valid_birth(wrapper_birth)),
        "identity.json does not identify its group leader",
    )
    child = (value.get("reviewer_pid"), value.get("reviewer_birth"))
    _require(
        wrapper_birth is not None or child == (None, None),
        "unproven wrapper identity has child identity",
    )
    _require(
        child == (None, None) or _valid_pid(child[0]) and (
            child[1] is None or _valid_birth(child[1])
        ),
        "identity.json has invalid reviewer identity",
    )


def _validate_identity(value: dict[str, Any], expected_attempt: str | None) -> None:
    if value.get("schema") != IDENTITY_SCHEMA:
        raise AttemptShapeNewer(NEWER_SHAPE_LITERAL)
    _require(set(value) == _IDENTITY_KEYS, "identity.json has an invalid key set")
    attempt = value.get("attempt")
    _require(_valid_attempt(attempt), "identity.json has an invalid attempt")
    _require(
        expected_attempt is None or attempt == expected_attempt,
        "identity.json is bound to a different attempt",
    )
    _require(isinstance(value.get("started_at"), str) and bool(value["started_at"]),
             "invalid identity timestamp")
    process_fields = (value.get("wrapper_pid"), value.get("pgid"), value.get("wrapper_birth"))
    if process_fields == (None, None, None):
        if value.get("reviewer_pid") is not None or value.get("reviewer_birth") is not None:
            raise AttemptRecordError("identity.json abandonment claim has child identity")
        return
    _validate_live_identity(value)


def read_identity(directory: int, expected_attempt: str | None = None) -> dict[str, Any] | None:
    value = _read_json_at(directory, IDENTITY_NAME, limit=16_384)
    if value is not None:
        _validate_identity(value, expected_attempt)
    return value


def _valid_sorted_names(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value) \
        and value == sorted(set(value))


def _valid_optional_digest(value: object) -> bool:
    return value is None or isinstance(value, str) and len(value) == 64 and set(value) <= _HEX


def _validate_completion_values(value: Mapping[str, Any]) -> None:
    returncode = value.get("returncode")
    error = value.get("error")
    dynamic = isinstance(error, str) and (
        error.removeprefix("bad line ").isdigit()
        or error.removeprefix("provider exit ").removeprefix("-").isdigit()
        or error.startswith(("redaction damaged ", "launch-failed: "))
    )
    counts = (value.get("events_bytes"), value.get("verdict_size"))
    _require(all(type(item) is int and item >= 0 for item in counts), "invalid byte counts")
    names = (value.get("environment_names"), value.get("omitted_short"))
    _require(all(_valid_sorted_names(item) for item in names), "invalid environment names")
    digests = (value.get("argv_digest"), value.get("prompt_digest"), value.get("verdict_digest"))
    _require(all(_valid_optional_digest(item) for item in digests), "invalid digests")
    _require(value.get("verdict_digest") is not None or value.get("verdict_size") == 0,
             "invalid verdict size")
    pids = (value.get("wrapper_pid"), value.get("pgid"), value.get("reviewer_pid"))
    _require(all(pid is None or _valid_pid(pid) for pid in pids), "invalid process identity")
    _require(returncode is None or type(returncode) is int, "invalid returncode")
    _require(error is None or error in _COMPLETION_ERRORS or dynamic, "invalid error")
    _require(returncode is not None or value.get("timed_out") or error is not None,
             "null returncode")
    _require(type(value.get("timed_out")) is bool, "invalid timed_out")


def _validate_completion(value: dict[str, Any], expected_attempt: str | None) -> None:
    if value.get("schema") != COMPLETION_SCHEMA:
        raise AttemptShapeNewer(NEWER_SHAPE_LITERAL)
    attempt = value.get("attempt")
    _require(set(value) == _COMPLETION_KEYS, "completion.json has invalid key set")
    _require(_valid_attempt(attempt), "completion.json has invalid attempt")
    _require(expected_attempt is None or attempt == expected_attempt, "attempt binding differs")
    strings = (value.get(name) for name in ("completed_at", "provider", "route_source",
                                             "route_sha256", "sandbox"))
    _require(all(isinstance(item, str) and item for item in strings), "invalid string fields")
    _require(value.get("provider") in {"codex", "claude"}, "invalid provider")
    _require(_valid_optional_digest(value.get("route_sha256")), "invalid route_sha256")
    _require(value.get("started_at") is None or isinstance(value["started_at"], str),
             "invalid started_at")
    _require(value.get("observed_model") is None or isinstance(value["observed_model"], str),
             "invalid observed_model")
    _validate_completion_values(value)


def read_completion(directory: int, expected_attempt: str | None = None) -> dict[str, Any] | None:
    value = _read_json_at(directory, COMPLETION_NAME)
    if value is not None:
        _validate_completion(value, expected_attempt)
    return value


def _request_value(request: Mapping[str, Any], field: str) -> object:
    route = request.get("route")
    return route.get(field) if field in {"provider", "route_source", "route_sha256"} \
        and isinstance(route, Mapping) else request.get(field)


def validate_completion_binding(
    completion: Mapping[str, Any],
    request: Mapping[str, Any],
    identity: Mapping[str, Any] | None,
) -> None:
    for field in ("provider", "route_source", "route_sha256", "sandbox", "attempt"):
        if completion.get(field) != _request_value(request, field):
            raise AttemptRecordError(f"completion.json {field} differs from the request")
    for field in ("argv_digest", "prompt_digest"):
        expected = request.get(field) or request.get(f"launcher_{field}")
        if expected is not None and completion.get(field) != expected:
            raise AttemptRecordError(f"completion.json {field} differs from the request")
    if identity is None:
        _require(
            isinstance(completion.get("error"), str)
            and str(completion["error"]).startswith("launch-failed: "),
            "completion.json without identity.json is not launch-failed",
        )
        _require(
            not any(
                completion.get(field) is not None
                for field in ("wrapper_pid", "pgid", "reviewer_pid")
            ),
            "completion.json has process identity without identity.json",
        )
        return
    if identity.get("wrapper_pid") is None:
        _require(
            completion.get("error") == "abandoned",
            "completion.json with an abandonment claim is not abandoned",
        )
        _require(
            not any(
                completion.get(field) is not None
                for field in ("wrapper_pid", "pgid", "reviewer_pid")
            ),
            "abandoned completion has process identity",
        )
        return
    for field in ("wrapper_pid", "pgid", "reviewer_pid"):
        if completion.get(field) != identity.get(field):
            raise AttemptRecordError(f"completion.json {field} differs from identity.json")


def _iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def make_terminal_completion(
    request: Mapping[str, Any],
    error: str,
    *,
    identity: Mapping[str, Any] | None = None,
    completed_at: str | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    route_value = request.get("route")
    route: Mapping[str, Any] = route_value if isinstance(route_value, Mapping) else {}
    identity = identity or {}
    record: dict[str, Any] = {
        "argv_digest": request.get("argv_digest") or request.get("launcher_argv_digest"),
        "attempt": request.get("attempt"),
        "completed_at": completed_at or _iso_now(),
        "environment_names": list(request.get("environment_names") or ()),
        "error": error,
        "events_bytes": 0,
        "observed_model": None,
        "omitted_short": list(request.get("omitted_short") or ()),
        "pgid": identity.get("pgid"),
        "prompt_digest": request.get("prompt_digest"),
        "provider": request.get("provider") or route.get("provider"),
        "returncode": None,
        "reviewer_pid": identity.get("reviewer_pid"),
        "route_sha256": _request_value(request, "route_sha256"),
        "route_source": _request_value(request, "route_source"),
        "sandbox": request.get("sandbox"),
        "schema": COMPLETION_SCHEMA,
        "started_at": identity.get("started_at") if identity.get("wrapper_pid") else None,
        "timed_out": False,
        "verdict_digest": None,
        "verdict_size": 0,
        "wrapper_pid": identity.get("wrapper_pid"),
    }
    if overrides:
        unknown = set(overrides) - _COMPLETION_KEYS
        if unknown:
            raise AttemptRecordError(f"completion override has unknown keys: {sorted(unknown)}")
        record.update(overrides)
    _validate_completion(record, str(request.get("attempt") or ""))
    return record


def publish_terminal_completion(directory: int, record: Mapping[str, Any]) -> bool:
    value = dict(record)
    _validate_completion(value, str(value.get("attempt") or ""))
    return exclusive_publish(directory, COMPLETION_NAME, value)


def claim_abandoned(
    directory: int, request: Mapping[str, Any], now: str | None = None
) -> tuple[bool, dict[str, Any]]:
    claim = {
        "schema": IDENTITY_SCHEMA,
        "attempt": request.get("attempt"),
        "wrapper_pid": None,
        "pgid": None,
        "wrapper_birth": None,
        "reviewer_pid": None,
        "reviewer_birth": None,
        "started_at": now or _iso_now(),
    }
    _validate_identity(claim, str(request.get("attempt") or ""))
    completion = make_terminal_completion(request, "abandoned", completed_at=now)
    won = exclusive_publish(directory, IDENTITY_NAME, claim)
    existing_identity = read_identity(directory, str(request.get("attempt") or "")) if not won \
        else claim
    if existing_identity is None or existing_identity.get("wrapper_pid") is not None:
        return False, completion
    existing = read_completion(directory, str(request.get("attempt") or ""))
    if existing is not None:
        validate_completion_binding(existing, request, existing_identity)
        return existing.get("error") == "abandoned", existing
    if not publish_terminal_completion(directory, completion):
        existing = read_completion(directory, str(request.get("attempt") or ""))
        if existing is None:
            raise AttemptRecordError("abandoned completion raced but is unreadable")
        validate_completion_binding(existing, request, existing_identity)
        return existing.get("error") == "abandoned", existing
    return True, completion


def record_stale(directory: int, attempt: str, completion: Mapping[str, Any]) -> bool:
    _validate_completion(dict(completion), attempt)
    canonical = json.dumps(
        dict(completion), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    record: dict[str, object] = {
        "schema": "forge-review-stale/1",
        "attempt": attempt,
        "completion_sha256": hashlib.sha256(canonical).hexdigest(),
        "recorded_at": _iso_now(),
    }
    return exclusive_publish(directory, STALE_NAME, record)


def mark_stale_attempts(
    store: Any, chain_id: str, current_relative: str
) -> tuple[str, ...]:
    root = store.artifact_dir(chain_id)
    current = root / current_relative
    references: list[str] = []
    for attempt_dir in (root / "review").glob("iteration-*/attempt-*"):
        if attempt_dir == current or not attempt_dir.is_dir():
            continue
        relative = (attempt_dir.relative_to(root) / COMPLETION_NAME).as_posix()
        try:
            with store.artifact_parent_descriptor(
                chain_id, relative, create=False
            ) as (directory, _name):
                completion = read_completion(directory, attempt_dir.name)
                if completion is not None:
                    record_stale(directory, attempt_dir.name, completion)
                    references.append(
                        (attempt_dir.relative_to(store.common_root) / STALE_NAME).as_posix()
                    )
        except (OSError, Refusal, ValueError):
            continue
    return tuple(references)


def with_stale_evidence(outcome: Any, references: tuple[str, ...]) -> Any:
    if not references:
        return outcome
    if isinstance(outcome, Refusal):
        outcome.evidence_refs += references
        return outcome
    if not isinstance(outcome, Outcome):
        return outcome
    return dataclasses.replace(
        outcome, evidence_refs=outcome.evidence_refs + references
    )


def _unowned_proof(
    probes: list[tuple[str, int]], scan: tuple[tuple[int, ...], bool], pgid: int
) -> GroupProof:
    members, complete = scan
    outcomes = {outcome for outcome, _pid in probes}
    if probes[0][0] == "identity-unproven":
        outcome = "wrapper-identity-unproven"
    elif any(result == "identity-unproven" for result, _pid in probes[1:]):
        outcome = "recorded-identity-unproven"
    elif "boot-id-changed" in outcomes:
        outcome = "boot-id-changed"
    elif "identity-mismatch" in outcomes:
        outcome = "identity-mismatch"
    elif members or not complete or "identity-unproven" in outcomes:
        outcome = "identity-unproven"
    else:
        outcome = "group-empty"
    return GroupProof(outcome, pgid, members)


def prove_group_ownership(identity: Mapping[str, Any]) -> GroupProof:
    value = dict(identity)
    _validate_identity(value, str(value.get("attempt") or ""))
    pgid_value = value.get("pgid")
    if not _valid_pid(pgid_value):
        return GroupProof("group-empty", None)
    pgid = cast(int, pgid_value)
    wrapper_pid = cast(int, value.get("wrapper_pid"))
    scan = _group_members(pgid)
    members, _complete = scan
    if value.get("wrapper_birth") is None:
        outcome = "wrapper-identity-unproven" if members or not _complete else "group-empty"
        return GroupProof(outcome, pgid, members)
    probes = [_process_probe(wrapper_pid, value["wrapper_birth"], pgid)]
    reviewer_pid = value.get("reviewer_pid")
    if _valid_pid(reviewer_pid):
        probes.append(
            _process_probe(cast(int, reviewer_pid), value["reviewer_birth"], pgid)
        )
    if probes[0][0] == "match":
        return GroupProof("wrapper-alive", pgid, members)
    if len(probes) > 1 and probes[1][0] == "match":
        return GroupProof("reviewer-alive", pgid, members)
    return _unowned_proof(probes, scan, pgid)


def _observe_processes(identity: dict[str, Any]) -> AttemptObservation:
    proof = prove_group_ownership(identity)
    if proof.outcome == "wrapper-alive":
        reviewer_pid = identity.get("reviewer_pid")
        if _valid_pid(reviewer_pid):
            child = _process_probe(
                cast(int, reviewer_pid),
                identity.get("reviewer_birth"),
                cast(int, identity["pgid"]),
            )
            if child[0] != "match":
                return AttemptObservation(
                    "wrapper-alive / child-dead", child[0], identity, members=proof.members
                )
        return AttemptObservation("running", identity=identity, members=proof.members)
    if proof.outcome == "reviewer-alive":
        return AttemptObservation(
            "wrapper-dead / child-alive", identity=identity, members=proof.members
        )
    outcome = proof.outcome if proof.outcome.endswith("identity-unproven") else "wrapper-lost"
    return AttemptObservation(outcome, proof.outcome, identity, members=proof.members)


def observe_attempt(
    directory: int,
    expected_attempt: str,
    identity_deadline: dt.datetime,
    now: dt.datetime | None = None,
) -> AttemptObservation:
    completion = read_completion(directory, expected_attempt)
    identity = read_identity(directory, expected_attempt)
    if completion is not None:
        return AttemptObservation("completed", identity=identity, completion=completion)
    if identity is None:
        current = now or dt.datetime.now(dt.timezone.utc)
        outcome = "launching" if current < identity_deadline else "abandonable"
        return AttemptObservation(outcome, reason="identity deadline")
    if identity.get("wrapper_pid") is None:
        return AttemptObservation("abandoned-claimed", identity=identity)
    return _observe_processes(identity)


def terminate_owned_group(
    identity: Mapping[str, Any],
    grace_seconds: float = 5.0,
    post_kill_seconds: float = 5.0,
) -> GroupProof:
    proof = prove_group_ownership(identity)
    if proof.outcome not in {"wrapper-alive", "reviewer-alive"} or proof.pgid is None:
        return GroupProof(proof.outcome, proof.pgid, proof.members)
    term = _send_group_signal(proof.pgid, signal.SIGTERM)
    if term != "sent":
        outcome = "group-empty" if term == "gone" else "kill-unconfirmed"
        return GroupProof(outcome, proof.pgid, () if term == "gone" else proof.members)
    remaining, empty = _wait_group_empty(proof.pgid, grace_seconds)
    if empty:
        return GroupProof("cancelled", proof.pgid)
    killed = _send_group_signal(proof.pgid, signal.SIGKILL)
    if killed != "sent":
        outcome = "cancelled" if killed == "gone" else "kill-unconfirmed"
        return GroupProof(outcome, proof.pgid, remaining)
    remaining, empty = _wait_group_empty(proof.pgid, post_kill_seconds)
    outcome = "cancelled" if empty else "kill-unconfirmed"
    return GroupProof(outcome, proof.pgid, remaining)
