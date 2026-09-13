"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import json
from typing import Any, Mapping, Callable, Sequence
from forge_cli.chain_core._controls import _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS, _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS
from forge_cli.chain_core._state import COMMON_LOCK_POLL_SECONDS, CHAIN_ID_RE, SHA256_RE
from pathlib import Path
from forge_cli import runtime
import datetime as dt
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode
import copy
import dataclasses
import re
import os
import errno
from forge_cli.policy import sha256_bytes


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _chain_storage_root(repository: Path) -> Path:
    """Resolve the shared Git-common DM-012/DM-014 authority root."""

    runtime._coordination_modules()
    from codex_orchestrator.chain_paths import chain_storage_root

    return chain_storage_root(repository)


def _validated_commitment_path(
    label: str,
    value: str,
    *,
    repository: Path,
    run_dir: Path | None = None,
    direct_parent: Path | None = None,
    require_file: bool = False,
) -> object | None:
    """Project one CLI path decision through the shared FR-017 inventory."""

    runtime._coordination_modules()
    from commitment_paths import commitment_surface, validate_surface_path

    try:
        surface = commitment_surface(label)
    except KeyError:
        return None
    return validate_surface_path(
        surface,
        value,
        repository=repository,
        run_dir=run_dir,
        direct_parent=direct_parent,
        require_file=require_file,
    )


def _parsed_run_captured_path(value: str, run_id: str) -> object | None:
    """Apply the shared grammar for run-relative ingest captures."""

    runtime._coordination_modules()
    from commitment_paths import parse_run_captured_path

    return parse_run_captured_path(value, run_id=run_id)


def _require_ingest_proof(
    name: str, completed: list[str] | None = None
) -> None:
    """Fail closed when a named proof is disabled or reached out of order."""

    _batch, builders, journal = runtime._coordination_modules()
    if (
        name not in _REQUIRED_INGEST_PROOF_CONTROLS
        or name not in INGEST_PROOF_CONTROLS
        or (
            completed is not None
            and (
                len(completed) >= len(INGEST_PROOF_ORDER)
                or INGEST_PROOF_ORDER[len(completed)] != name
            )
        )
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    if completed is not None:
        completed.append(name)


def iso_z(value: dt.datetime | None = None) -> str:
    current = value or runtime.utc_now()
    current = current.astimezone(dt.timezone.utc).replace(microsecond=0)
    return current.isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp is not UTC Z form")
    parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return parsed.astimezone(dt.timezone.utc)


def _require_merge_store_control(name: str) -> None:
    if (
        name not in _REQUIRED_MERGE_STORE_CONTROLS
        or name not in MERGE_STORE_CONTROLS
    ):
        raise FrozenError(
            f"merge storage control is unavailable: {name}",
            schema=REVISION9_OUTPUT_SCHEMA,
        )


def _require_merge_adapter_control(name: str) -> None:
    if (
        name not in _REQUIRED_MERGE_ADAPTER_CONTROLS
        or name not in MERGE_ADAPTER_CONTROLS
    ):
        raise FrozenError(
            f"merge adapter control is unavailable: {name}",
            schema=REVISION9_OUTPUT_SCHEMA,
        )


def _require_merge_integration_control(name: str) -> None:
    if (
        name not in _REQUIRED_MERGE_INTEGRATION_CONTROLS
        or name not in MERGE_INTEGRATION_CONTROLS
    ):
        raise FrozenError(
            f"merge integration control is unavailable: {name}",
            schema=REVISION9_OUTPUT_SCHEMA,
        )


def _require_common_lock_control(name: str) -> None:
    if name not in _REQUIRED_COMMON_LOCK_CONTROLS:
        raise ValueError(f"unknown common-lock control: {name}")
    if name not in COMMON_LOCK_CONTROLS:
        raise FrozenError(
            f"FR-235/FR-236 common-lock control is unavailable: {name}",
            observed=name,
            schema=REVISION9_OUTPUT_SCHEMA,
        )


class CommonLockBoundaryCrash(BaseException):
    """Test/embedding seam that models a process disappearing at a boundary.

    The lock implementation deliberately does not catch this ``BaseException``.
    A caller using it must do so only in an expendable process, because the
    canonical artifacts and any child are intentionally abandoned exactly as
    they would be after a crash.
    """


@dataclasses.dataclass(frozen=True)
class PublishedLockRecord:
    path: str
    device: int
    inode: int
    digest: str
    record: dict[str, Any]
    mode: int
    links: int

    def evidence(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "device": self.device,
            "inode": self.inode,
            "digest": self.digest,
            "record": copy.deepcopy(self.record),
        }


@dataclasses.dataclass(frozen=True)
class CommonLockInspection:
    topology: str
    outer: PublishedLockRecord | None = None
    inner: PublishedLockRecord | None = None
    detail: str | None = None
    artifacts: dict[str, Any] | None = None

    @property
    def recoverable(self) -> bool:
        return self.topology in {
            "complete",
            "outer-only",
            "outer-empty-directory",
        }

    def evidence(self, common_dir: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "common_dir": str(common_dir),
            "topology": self.topology,
            "detail": self.detail,
        }
        if self.outer is not None:
            result["owner"] = self.outer.evidence()
        if self.inner is not None:
            result["inner"] = self.inner.evidence()
        if self.artifacts is not None:
            result["artifacts"] = copy.deepcopy(self.artifacts)
        return result


class CommonLockUnavailable(Refusal):
    """The exact envelope-only FR-235 acquisition refusal."""

    def __init__(self, evidence: Mapping[str, Any]) -> None:
        rendered = canonical_bytes(dict(evidence)).decode("utf-8")
        super().__init__(
            V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
            "forge: common rebase lock unavailable",
            expected=(
                "complete mandatory portable ownership and any secondary flock "
                "within the shared 300-second deadline"
            ),
            observed=rendered,
            remediation=(
                "inspect the reported immutable owner, reservation, and fence; "
                "do not remove or replace them automatically"
            ),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
        self.evidence = copy.deepcopy(dict(evidence))


class CommonLockReleaseFailure(Refusal):
    """Release-only failure after the caller's primary truth is durable."""

    def __init__(self, evidence: Mapping[str, Any]) -> None:
        rendered = canonical_bytes(dict(evidence)).decode("utf-8")
        super().__init__(
            V2ReasonCode.LOCK_RELEASE_FAILED,
            "forge: common rebase lock release failed",
            expected="reverse-order release of the exact acquired lock identity",
            observed=rendered,
            remediation="retry only release recovery for the recorded lock identity",
            schema=REVISION9_OUTPUT_SCHEMA,
        )
        self.evidence = copy.deepcopy(dict(evidence))


class ChainLeaseUnavailable(Refusal):
    """Fail-closed per-chain serialization refusal."""

    def __init__(self, chain_id: str, evidence: Mapping[str, Any]) -> None:
        rendered = canonical_bytes(dict(evidence)).decode("utf-8")
        super().__init__(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: merge chain lease unavailable",
            expected=f"exclusive current lease for {chain_id}",
            observed=rendered,
            remediation=f"forge status --chain-id {chain_id}",
            next_required_step=f"forge status --chain-id {chain_id}",
            chain={"chain_id": chain_id, "state": "unknown"},
            schema=REVISION9_OUTPUT_SCHEMA,
        )
        self.evidence = copy.deepcopy(dict(evidence))


class FencedChildSurvived(RuntimeError):
    """A fenced process group remains live or cannot be proved gone."""

    def __init__(self, result: "FencedProcessResult") -> None:
        super().__init__("fenced process group survived termination")
        self.result = result


def _valid_utc_second(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return iso_z(parse_time(value)) == value
    except (TypeError, ValueError):
        return False


def _valid_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_host(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value.encode("utf-8")) <= 255
        and "\x00" not in value
    )


def _valid_nonce(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _valid_nullable_chain(kind: Any, chain_id: Any, *, allow_phase5: bool) -> bool:
    if kind == "merge":
        return isinstance(chain_id, str) and CHAIN_ID_RE.fullmatch(chain_id) is not None
    allowed = {"push", "phase5"} if allow_phase5 else {"push"}
    return kind in allowed and chain_id is None


def _write_all(descriptor: int, value: bytes) -> None:
    position = 0
    while position < len(value):
        written = os.write(descriptor, value[position:])
        if written <= 0:
            raise OSError("short write")
        position += written


class _PublicationCleanupFailure(OSError):
    """A failed publication left an attempt-owned name unproved or undurable."""


def _process_probe(pid: int) -> str:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        return "unprovable"
    except OSError as exc:
        return "dead" if exc.errno == errno.ESRCH else "unprovable"
    return "live"


def _group_probe(pgid: int) -> str:
    try:
        os.kill(-pgid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        return "unprovable"
    except OSError as exc:
        return "dead" if exc.errno == errno.ESRCH else "unprovable"
    return "live"


def _sleep_with_deadline(
    deadline: float,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> bool:
    remaining = deadline - clock()
    if remaining <= 0:
        return False
    sleeper(min(COMMON_LOCK_POLL_SECONDS, remaining))
    return clock() < deadline


def _require_deadline_open(
    deadline: float, clock: Callable[[], float], operation: str
) -> None:
    _require_common_lock_control("single-deadline")
    if clock() >= deadline:
        raise TimeoutError(f"{operation} exhausted the shared common-lock deadline")


@dataclasses.dataclass(frozen=True)
class FencedProcessResult:
    argv: list[str]
    returncode: int | None
    duration_seconds: float
    output: bytes
    output_digest: str
    timed_out: bool
    output_limit: bool
    launch_failed: bool
    group_survived: bool
    authorized: bool
    fence_digest: str
    fence_inode: int
    metadata: Mapping[str, Any] | None = None

    def evidence(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "output_digest": self.output_digest,
            "timed_out": self.timed_out,
            "output_limit": self.output_limit,
            "launch_failed": self.launch_failed,
            "group_survived": self.group_survived,
            "authorized": self.authorized,
            "fence_digest": self.fence_digest,
            "fence_inode": self.fence_inode,
        }


def merge_gate_intent_digest(
    *,
    chain_id: str,
    epoch_intent_digest: str,
    seal_event_digest: str,
    generation_digest: str,
    policy_digest: str,
    suite_digest: str,
    cursor: int,
    kind: str,
    gate_id: str,
    authorizing_event_digest: str,
) -> str:
    """Return Revision-10's exact cursor-selected gate-intent digest."""

    _require_common_lock_control("fence-intent-revalidation")
    if not CHAIN_ID_RE.fullmatch(chain_id):
        raise ValueError("gate intent chain identifier is invalid")
    digests = (
        epoch_intent_digest,
        seal_event_digest,
        generation_digest,
        policy_digest,
        suite_digest,
        authorizing_event_digest,
    )
    if any(SHA256_RE.fullmatch(value) is None for value in digests):
        raise ValueError("gate intent contains a malformed digest")
    if not _valid_nonnegative_int(cursor):
        raise ValueError("gate intent cursor is invalid")
    if kind not in {"gate", "scoped-mutation"}:
        raise ValueError("gate intent kind is invalid")
    if not isinstance(gate_id, str) or not gate_id:
        raise ValueError("gate intent id is invalid")
    if kind == "scoped-mutation" and gate_id != "scoped-mutation":
        raise ValueError("scoped-mutation gate intent id is invalid")
    if cursor == 0 and authorizing_event_digest != seal_event_digest:
        raise ValueError("cursor-zero gate intent is not authorized by its seal")
    preimage = {
        "schema": "forge-merge-gate-intent/1",
        "chain_id": chain_id,
        "epoch_intent_digest": epoch_intent_digest,
        "seal_event_digest": seal_event_digest,
        "generation_digest": generation_digest,
        "policy_digest": policy_digest,
        "suite_digest": suite_digest,
        "cursor": cursor,
        "kind": kind,
        "id": gate_id,
        "authorizing_event_digest": authorizing_event_digest,
    }
    return sha256_bytes(canonical_bytes(preimage))


def _forge_command(state: Mapping[str, Any] | None, verb: str) -> str:
    suffix = f" --chain-id {state['chain_id']}" if state else ""
    return f"forge {verb}{suffix}"


@dataclasses.dataclass(frozen=True)
class MergeRunTaskSnapshot:
    """Immutable journal values captured before a run-bound merge fetch."""

    binding: dict[str, str]
    task_files: tuple[str, ...]
    admitted_scope: tuple[str, ...]


def _merge_refusal(
    reason: V2ReasonCode,
    message: str,
    *,
    expected: str | None = None,
    observed: str | None = None,
    remediation: str | None = None,
    chain: Mapping[str, Any] | None = None,
    evidence_refs: Sequence[str] = (),
) -> Refusal:
    return Refusal(
        reason,
        message,
        expected=expected,
        observed=observed,
        remediation=remediation,
        chain=chain,
        evidence_refs=evidence_refs,
        schema=REVISION9_OUTPUT_SCHEMA,
    )


def _valid_sorted_unique_strings(value: object) -> bool:
    return bool(
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and value
        == sorted(set(value), key=lambda item: item.encode("utf-8"))
    )
