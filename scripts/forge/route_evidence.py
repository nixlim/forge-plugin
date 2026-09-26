"""Route snapshots, launch comparison, and orchestrator-model evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import NoReturn

import route_config
import route_vocab

ROUTE_FIELDS = ("provider", "model", "effort", "route_source", "route_sha256")
ROUTE_SOURCES = frozenset(("local", "committed-default", "plugin-default"))
EXECUTION_ROUTE_SOURCES = ROUTE_SOURCES | {"unrecorded"}
EXECUTION_ROUTE_TRIO = ("sandbox", "route_source", "route_sha256")
ORCHESTRATOR_REASONS = frozenset(("var-unset", "transcript-absent", "unreadable"))
TRANSCRIPT_TAIL_BYTES = 1024 * 1024
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
EXECUTION_ROUTE_FIELDS_TO_COMPARE = (
    "provider",
    "model",
    "effort",
    "route_source",
    "route_sha256",
)


def route_digest(role: str, route: dict[str, object]) -> str:
    """Return the DM-018 digest for one route entry."""

    preimage = {
        "schema": "forge-route/1",
        "role": role,
        **{field: route[field] for field in ROUTE_FIELDS[:-1]},
    }
    canonical = json.dumps(
        preimage, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def resolve_snapshot(
    repo: Path, head: str, *, refusal: type[Exception] = RuntimeError
) -> dict[str, dict[str, str]]:
    """Resolve all launched roles at one Git head, preserving route diagnostics."""

    try:
        resolution = route_config.load(repo, head=head)
        return {
            role: {
                field: getattr(resolution.for_role(role), field)
                for field in ROUTE_FIELDS
            }
            for role in route_config.ROLES
        }
    except route_config.RouteRefusal as exc:
        raise refusal(str(exc)) from None


def _project_slug(repo: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(repo.resolve()))


def _as_transcript_record(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None


def _last_transcript_model(path: Path) -> str | None:
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        end = stream.tell()
        start = max(0, end - TRANSCRIPT_TAIL_BYTES)
        stream.seek(start)
        payload = stream.read(TRANSCRIPT_TAIL_BYTES)
    lines = payload.splitlines()
    if start and lines:
        lines = lines[1:]
    for raw in reversed(lines):
        try:
            record = _as_transcript_record(json.loads(raw))
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
            continue
        if record is None:
            continue
        message = record.get("message")
        model = message.get("model") if isinstance(message, dict) else None
        if record.get("type") == "assistant" and isinstance(model, str) and model:
            return model
    return None


def _valid_transcript_model(value: object) -> bool:
    return isinstance(value, str) and route_config.MODEL_RE.fullmatch(value) is not None


def orchestrator_model(repo: Path) -> dict[str, object]:
    """Read bounded best-effort model evidence from the current Claude transcript."""

    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session_id:
        return {"observed": None, "reason": "var-unset"}
    if Path(session_id).name != session_id:
        return {"observed": None, "reason": "unreadable"}
    try:
        transcript = (
            Path.home()
            / ".claude"
            / "projects"
            / _project_slug(repo)
            / f"{session_id}.jsonl"
        )
        observed = _last_transcript_model(transcript)
    except FileNotFoundError:
        return {"observed": None, "reason": "transcript-absent"}
    except (OSError, RuntimeError, UnicodeError, ValueError):
        return {"observed": None, "reason": "unreadable"}
    if _valid_transcript_model(observed):
        return {"observed": observed}
    return {"observed": None, "reason": "unreadable"}


def opening_fields(
    repo: Path, head: str, *, refusal: type[Exception] = RuntimeError
) -> dict[str, object]:
    """Build the two known-optional DM-018 run-opening fields."""

    return {
        "route": resolve_snapshot(repo, head, refusal=refusal),
        "orchestrator_model": orchestrator_model(repo),
    }


def _refuse(detail: str, refusal: type[Exception]) -> NoReturn:
    raise refusal(
        "forge: journal append refused — invalid journal record: " + detail
    )


def _valid_route_entry(role: str, entry: object) -> str | None:
    if not isinstance(entry, dict) or set(entry) != set(ROUTE_FIELDS):
        return f"run_started.route.{role} must contain exactly {', '.join(ROUTE_FIELDS)}"
    provider = entry.get("provider")
    model = entry.get("model")
    effort = entry.get("effort")
    source = entry.get("route_source")
    digest = entry.get("route_sha256")
    detail = None
    if not isinstance(provider, str) or provider not in route_config.PROVIDERS:
        detail = f"run_started.route.{role}.provider must be one of claude, codex"
    elif not isinstance(model, str) or route_config.MODEL_RE.fullmatch(model) is None:
        detail = f"run_started.route.{role}.model must be a valid model id"
    elif not isinstance(effort, str) or effort not in route_config.EFFORTS[provider]:
        detail = f"run_started.route.{role}.effort is invalid for provider {provider}"
    elif not isinstance(source, str) or source not in ROUTE_SOURCES:
        detail = (
            f"run_started.route.{role}.route_source must be one of local, "
            "committed-default, plugin-default"
        )
    elif not isinstance(digest, str) or HEX_SHA256.fullmatch(digest) is None:
        detail = f"run_started.route.{role}.route_sha256 must be 64 lowercase hex"
    elif digest != route_digest(role, entry):
        detail = (
            f"run_started.route.{role}.route_sha256 must match the DM-018 route digest"
        )
    return detail


def _valid_orchestrator_model(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) == {"observed"}:
        observed = value.get("observed")
        return (
            isinstance(observed, str)
            and route_config.MODEL_RE.fullmatch(observed) is not None
        )
    reason = value.get("reason")
    return (
        set(value) == {"observed", "reason"}
        and value.get("observed") is None
        and isinstance(reason, str)
        and reason in ORCHESTRATOR_REASONS
    )


def validate_run_started(
    record: dict[str, object],
    *,
    historical: bool,
    refusal: type[Exception] = RuntimeError,
) -> None:
    """Validate the known-optional DM-018 opening fields on a new write."""

    if historical:
        return
    if "route" in record:
        route = record.get("route")
        if not isinstance(route, dict) or set(route) != set(route_config.ROLES):
            _refuse(
                "run_started.route must contain exactly "
                + ", ".join(route_config.ROLES),
                refusal,
            )
        for role in route_config.ROLES:
            detail = _valid_route_entry(role, route[role])
            if detail is not None:
                _refuse(detail, refusal)
    if "orchestrator_model" in record and not _valid_orchestrator_model(
        record.get("orchestrator_model")
    ):
        _refuse(
            "run_started.orchestrator_model must be exactly {observed: <model>} "
            "or {observed: null, reason: var-unset | transcript-absent | unreadable}",
            refusal,
        )


def _opening_snapshot(
    prior_records: tuple[dict[str, object], ...],
) -> dict[str, object] | None:
    for record in prior_records:
        route = record.get("route")
        if record.get("type") == "run_started" and isinstance(route, dict):
            return route
    return None


def _execution_route_shape(
    record: dict[str, object], refusal: type[Exception]
) -> bool:
    present = [field in record for field in EXECUTION_ROUTE_TRIO]
    if any(present) and not all(present):
        _refuse(
            "execution route fields must be given together "
            "(sandbox, route_source, route_sha256)",
            refusal,
        )
    if not all(present):
        return False
    sandbox = record.get("sandbox")
    source = record.get("route_source")
    digest = record.get("route_sha256")
    if not isinstance(sandbox, str) or not sandbox:
        _refuse("execution.sandbox must be a nonempty string", refusal)
    if sandbox not in route_vocab.SANDBOX_IDS:
        _refuse(
            "execution.sandbox must be one of " + ", ".join(route_vocab.SANDBOX_IDS),
            refusal,
        )
    if not isinstance(source, str) or source not in EXECUTION_ROUTE_SOURCES:
        _refuse(
            "execution.route_source must be one of local, committed-default, "
            "plugin-default, unrecorded",
            refusal,
        )
    if not isinstance(digest, str) or HEX_SHA256.fullmatch(digest) is None:
        _refuse("execution.route_sha256 must be 64 lowercase hex", refusal)
    return True


def _refuse_divergence(
    role: str, field: str, refusal: type[Exception]
) -> NoReturn:
    raise refusal(
        f"forge: execution refused — route diverges from run snapshot for {role}: {field}"
    )


def _snapshot_route(
    snapshot: dict[str, object], role: str, refusal: type[Exception]
) -> dict[str, object]:
    if role not in snapshot:
        raise refusal(
            f"forge: execution refused — role {role} has no frozen route "
            "in the run snapshot"
        )
    expected = snapshot.get(role)
    if not isinstance(expected, dict):
        _refuse_divergence(role, "provider", refusal)
    return expected


def validate_execution(
    record: dict[str, object],
    prior_records: tuple[dict[str, object], ...],
    *,
    historical: bool,
    refusal: type[Exception] = RuntimeError,
) -> None:
    """Validate the execution route trio and compare it with the run snapshot."""

    if historical:
        if "sandbox" in record and (
            not isinstance(record.get("sandbox"), str) or not record.get("sandbox")
        ):
            _refuse("execution.sandbox must be a nonempty string", refusal)
        return
    try:
        route_vocab.validate_new_write(
            role=str(record["role"]),
            provider=str(record["provider"]),
            mode=str(record["mode"]),
            event_source=str(record["event_source"]),
        )
    except route_vocab.NewWriteRefusal as exc:
        _refuse(str(exc), refusal)
    if not _execution_route_shape(record, refusal):
        return
    snapshot = _opening_snapshot(prior_records)
    if snapshot is None:
        return
    provider = str(record["provider"])
    role = route_vocab.canonical_role(str(record["role"]), provider)
    assert role is not None
    expected = _snapshot_route(snapshot, role, refusal)
    for field in EXECUTION_ROUTE_FIELDS_TO_COMPARE:
        if record.get(field) != expected.get(field):
            _refuse_divergence(role, field, refusal)
    if record.get("sandbox") != route_config.profile_sandbox(provider, role):
        _refuse_divergence(role, "sandbox", refusal)


def projected_route_source(record: dict[str, object]) -> str:
    """Project pre-route execution records through the durable compatibility value."""

    source = record.get("route_source")
    if isinstance(source, str) and source in EXECUTION_ROUTE_SOURCES:
        return source
    return "unrecorded"
