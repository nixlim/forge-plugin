from __future__ import annotations

import copy
import errno
import fcntl
import os
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TypedDict, cast

from . import batch, journal

CLOSE_LAW_CONTROLS = frozenset(
    {"read-only-chain-lock", "read-only-receipt-check"}
)
RUN_CLOSE_LEGIBILITY_CONTROLS = frozenset(
    {"first-issue", "blocked-close-projection"}
)
CHAIN_LOCK_WAIT_SECONDS = 10.0

ChainLock = Callable[..., AbstractContextManager[None]]
ReceiptVerifier = Callable[
    [
        Path,
        str,
        dict[str, object],
        dict[str, object],
        tuple[dict[str, object], ...],
        dict[str, object],
    ],
    None,
]


class CloseProjection(TypedDict, total=False):
    issues: list[str]
    warnings: list[str]
    non_passing_verifications: list[dict[str, object]]
    profile: str
    ok: bool


_REPORT_MODE: ContextVar[tuple[str | None, batch.BatchLock] | None] = ContextVar(
    "close_law_report_mode", default=None
)
_BLOCKED_CLOSE_PASSED_ISSUES: ContextVar[tuple[str, ...]] = ContextVar(
    "blocked_close_passed_issues", default=()
)


def project_close(
    run_dir: Path,
    records: Sequence[dict[str, object]],
    judgment: str,
) -> dict[str, object]:
    """Project the gate-profile half of one run-close build in memory."""

    _BLOCKED_CLOSE_PASSED_ISSUES.set(())
    validation = cast(
        CloseProjection, journal.validate_run(run_dir, gates=False)
    )
    passed_validation = (
        copy.deepcopy(validation)
        if judgment == "blocked"
        and "blocked-close-projection" in RUN_CLOSE_LEGIBILITY_CONTROLS
        else None
    )
    _apply_gate_projection(validation, records, judgment)
    if passed_validation is not None:
        _apply_gate_projection(passed_validation, records, "passed")
        _BLOCKED_CLOSE_PASSED_ISSUES.set(
            tuple(cast(list[str], passed_validation["issues"]))
        )
    return cast(dict[str, object], validation)


def _apply_gate_projection(
    validation: CloseProjection,
    records: Sequence[dict[str, object]],
    judgment: str,
) -> None:
    issues = validation["issues"]
    _apply_projected_task_updates(records, issues)
    warnings = validation["warnings"]
    projected = [
        {**record, "_line": line}
        for line, record in enumerate(records, start=1)
    ]
    projected.append(
        {
            "type": "run_closed",
            "judgment": judgment,
            "_line": len(projected) + 1,
        }
    )
    declaration = journal._legacy_compatibility_declaration(projected)
    line_value = declaration.get("_line") if declaration is not None else None
    declaration_line = line_value if isinstance(line_value, int) else None
    journal.check_gate_profile(projected, issues, warnings, declaration_line)
    validation["profile"] = "gates"
    validation["ok"] = not issues


def refusal_text(base: str, issues: Sequence[str]) -> str:
    """Make a passed-close refusal name its first existing validation issue."""

    if "first-issue" not in RUN_CLOSE_LEGIBILITY_CONTROLS or not issues:
        return base
    suffix = ""
    if len(issues) > 1:
        suffix = (
            f" (+{len(issues) - 1} more; run journal close-preflight)"
        )
    return f"{base}: {issues[0]}{suffix}"


def blocked_close_passed_issues() -> tuple[str, ...]:
    """Return passed-close issues projected by the latest blocked close build."""

    return _BLOCKED_CLOSE_PASSED_ISSUES.get()


def _apply_projected_task_updates(
    records: Sequence[dict[str, object]], issues: list[str]
) -> None:
    """Remove the on-disk active-task issue replaced by a projected terminal task."""

    latest_statuses = {
        str(record["id"]): record.get("status")
        for record in records
        if record.get("type") == "task"
        and isinstance(record.get("id"), str)
    }
    terminal_tasks = {
        task_id
        for task_id, status in latest_statuses.items()
        if status in journal.TERMINAL_TASK_STATUSES
    }
    prefixes = tuple(
        f"task {task_id} is not terminal; latest status is "
        for task_id in terminal_tasks
    )
    if prefixes:
        issues[:] = [issue for issue in issues if not issue.startswith(prefixes)]


@contextmanager
def report_mode(
    skip_chain: str | None, shared_lock: batch.BatchLock
) -> Iterator[None]:
    """Select read-only terminal-chain behavior for a preflight report."""

    reset = _REPORT_MODE.set((skip_chain, shared_lock))
    try:
        yield
    finally:
        _REPORT_MODE.reset(reset)


def chain_lock(default: ChainLock) -> ChainLock:
    """Return the chain lock appropriate for the current execution mode."""

    if (
        _REPORT_MODE.get() is not None
        and "read-only-chain-lock" in CLOSE_LAW_CONTROLS
    ):
        return read_only_chain_lock
    return default


def guard_chain_ids(chain_ids: Sequence[str]) -> Sequence[str]:
    """Exclude the in-memory projected chain from terminal artifact checks."""

    report = _REPORT_MODE.get()
    if report is None or report[0] is None:
        return chain_ids
    return [chain_id for chain_id in chain_ids if chain_id != report[0]]


def receipt_verifier() -> ReceiptVerifier | None:
    """Return a verifier that reuses the preflight's shared batch hold."""

    report = _REPORT_MODE.get()
    if report is None or "read-only-receipt-check" not in CLOSE_LAW_CONTROLS:
        return None
    _skip_chain, shared_lock = report

    def verify(
        repository: Path,
        chain_id: str,
        state: dict[str, object],
        pending: dict[str, object],
        carried_records: tuple[dict[str, object], ...],
        acknowledgement: dict[str, object],
    ) -> None:
        from . import builders

        run_binding = state.get("run_binding")
        if (
            not isinstance(run_binding, dict)
            or run_binding.get("run_id") != shared_lock.run_dir.name
        ):
            raise builders._binding_replay_refusal()
        builders._verify_receipted_batch_locked(
            shared_lock,
            repository,
            chain_id,
            state,
            pending,
            carried_records,
            acknowledgement,
        )

    return verify


@contextmanager
def read_only_chain_lock(
    chains_root: Path,
    chain_id: str,
    *,
    root_descriptor: int | None = None,
    root_observation: journal.FileObservation | None = None,
) -> Iterator[None]:
    """Share an existing chain lock without creating or synchronizing it."""

    owned_root_descriptor: int | None = None
    lock_descriptor: int | None = None
    name = f".{chain_id}.events.lock"
    try:
        root_descriptor, root_observation, owned_root_descriptor = _chain_lock_root(
            chains_root, root_descriptor, root_observation
        )
        opened = _open_read_only_chain_lock(root_descriptor, name)
        if opened is None:
            yield
            return
        lock_descriptor, observation = opened
        _take_shared_chain_lock(lock_descriptor, chain_id)
        _validate_chain_lock_observations(
            chains_root, root_descriptor, root_observation, name, observation
        )
        yield
        rebound = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
        if journal._file_observation(rebound) != observation:
            raise journal.CoordinationRefusal(_terminal_chain_invalid())
    except journal.CoordinationRefusal:
        raise
    except OSError as exc:
        raise journal.CoordinationRefusal(_terminal_chain_invalid()) from exc
    finally:
        if lock_descriptor is not None:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(lock_descriptor)
        if owned_root_descriptor is not None:
            os.close(owned_root_descriptor)


def _terminal_chain_invalid() -> str:
    from . import builders

    return builders.TERMINAL_CHAIN_INVALID


def _chain_lock_root(
    chains_root: Path,
    root_descriptor: int | None,
    root_observation: journal.FileObservation | None,
) -> tuple[int, journal.FileObservation, int | None]:
    if root_descriptor is None:
        owned, observed = journal._open_bound_directory(chains_root)
        return owned, observed, owned
    if root_observation is None:
        raise journal.CoordinationRefusal(_terminal_chain_invalid())
    return root_descriptor, root_observation, None


def _open_read_only_chain_lock(
    root_descriptor: int, name: str
) -> tuple[int, journal.FileObservation] | None:
    try:
        observed = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not journal._batch_regular_stat_valid(observed):
        raise journal.CoordinationRefusal(_terminal_chain_invalid())
    descriptor = os.open(
        name,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=root_descriptor,
    )
    try:
        observation = journal._file_observation(observed)
        if journal._file_observation(os.fstat(descriptor)) != observation:
            raise journal.CoordinationRefusal(_terminal_chain_invalid())
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, observation


def _take_shared_chain_lock(descriptor: int, chain_id: str) -> None:
    deadline = time.monotonic() + CHAIN_LOCK_WAIT_SECONDS
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise journal.CoordinationRefusal(
                    f"forge: close preflight — chain lock busy: {chain_id}"
                ) from exc
            time.sleep(min(0.1, remaining))


def _validate_chain_lock_observations(
    chains_root: Path,
    root_descriptor: int,
    root_observation: journal.FileObservation,
    name: str,
    observation: journal.FileObservation,
) -> None:
    rebound = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
    if (
        journal._file_observation(rebound) != observation
        or journal._file_observation(os.fstat(root_descriptor)) != root_observation
        or journal._file_observation(os.lstat(chains_root)) != root_observation
    ):
        raise journal.CoordinationRefusal(_terminal_chain_invalid())


def projected_chain_records(
    records: Sequence[dict[str, object]],
    chain_id: str,
    chain_state: dict[str, object],
) -> list[dict[str, object]]:
    """Project a chain landing, any required approval, and task completion."""

    projected = list(records)
    verification: dict[str, object] | None = None
    for record in reversed(records):
        bound = journal._binding_chain_and_candidate(record)
        if record.get("type") == "verification" and bound is not None:
            if bound[0] == chain_id and isinstance(record.get("task"), str):
                verification = record
                break
    if verification is None:
        return projected
    source_binding = verification["binding"]
    assert isinstance(source_binding, dict)
    candidate = copy.deepcopy(source_binding["candidate"])
    task = str(verification["task"])
    preimage = {
        "schema": journal.BINDING_SCHEMA,
        "source_record": {"chain_id": chain_id, "event_digest": "0" * 64},
        "candidate": candidate,
        "review": None,
    }
    binding = {
        **preimage,
        "binding_id": journal._sha256(journal._canonical_json_bytes(preimage)),
    }
    next_line = (
        max(
            (
                line
                for record in projected
                if type(line := record.get("_line")) is int
            ),
            default=0,
        )
        + 1
    )
    projected.append(
        {
            "type": "decision",
            "id": "decision-projected",
            "outcome": "chain-landing",
            "task": task,
            "basis": [],
            "binding": binding,
            "_line": next_line,
        }
    )
    tier = chain_state.get("tier")
    review = chain_state.get("review")
    approval_required = bool(
        (isinstance(tier, dict) and tier.get("control"))
        or (
            isinstance(review, dict)
            and review.get("operator_cosign_required")
        )
    )
    candidate_bytes = journal._canonical_json_bytes(candidate)
    has_approval = any(
        record.get("type") == "decision"
        and record.get("outcome") == "chain-approval"
        and (bound := journal._binding_chain_and_candidate(record)) is not None
        and bound[0] == chain_id
        and bound[1] == candidate_bytes
        for record in records
    )
    if approval_required and not has_approval:
        next_line += 1
        projected.append(
            {
                "type": "decision",
                "id": "decision-projected-approval",
                "outcome": "chain-approval",
                "task": task,
                "basis": [],
                "binding": copy.deepcopy(binding),
                "_line": next_line,
            }
        )
    next_line += 1
    projected.append(
        {
            "type": "task",
            "id": task,
            "status": "complete",
            "_line": next_line,
        }
    )
    return projected
