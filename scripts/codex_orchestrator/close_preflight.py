from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from . import batch, builders, close_law, journal

_OUTPUT_SCHEMA = "forge-close-preflight/1"
_OUTPUT_LIMIT = 65_536
_LOCK_POLL_SECONDS = 0.1
_RUN_NOT_OPEN = "forge: close preflight — run is not open"
_INVALID_CHAIN = "forge: close preflight — invalid chain id"
_NO_BOUND_GATES = (
    "forge: close preflight — projected chain has no bound gate records: "
)


def _take_shared_lock(descriptor: int) -> None:
    deadline = time.monotonic() + close_law.CHAIN_LOCK_WAIT_SECONDS
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return
        except (BlockingIOError, InterruptedError):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise journal.CoordinationRefusal(
                    journal.JOURNAL_READ_TRANSACTION_REFUSAL
                ) from None
            time.sleep(min(_LOCK_POLL_SECONDS, remaining))


def _open_shared_batch_lock(run_dir: Path) -> batch.BatchLock:
    run_descriptor: int | None = None
    lock_descriptor: int | None = None
    try:
        run_descriptor, _ = journal._open_bound_directory(run_dir)
        _, lock_observation = batch._validate_named_file(
            run_descriptor, journal.BATCH_LOCK_NAME
        )
        lock_descriptor = os.open(
            journal.BATCH_LOCK_NAME,
            batch._safe_open_flags(os.O_RDONLY, nonblocking=True),
            dir_fd=run_descriptor,
        )
        if not batch._same(os.fstat(lock_descriptor), lock_observation):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        _take_shared_lock(lock_descriptor)
        locked = batch.BatchLock(
            run_dir, run_descriptor, lock_descriptor, lock_observation
        )
        batch._validate_batch_lock(locked)
        return locked
    except (OSError, journal.CoordinationRefusal) as exc:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if run_descriptor is not None:
            os.close(run_descriptor)
        raise journal.CoordinationRefusal(
            journal.JOURNAL_READ_TRANSACTION_REFUSAL
        ) from exc


@contextmanager
def _shared_batch_lock(run_dir: Path) -> Iterator[batch.BatchLock]:
    locked = _open_shared_batch_lock(run_dir)
    marked = False
    try:
        try:
            journal._mark_batch_lock(run_dir, held=True)
        except journal.CoordinationRefusal as exc:
            raise journal.CoordinationRefusal(
                journal.JOURNAL_READ_TRANSACTION_REFUSAL
            ) from exc
        marked = True
        yield locked
        try:
            batch._validate_batch_lock(locked)
        except journal.CoordinationRefusal as exc:
            raise journal.CoordinationRefusal(
                journal.JOURNAL_READ_TRANSACTION_REFUSAL
            ) from exc
    finally:
        if marked:
            journal._mark_batch_lock(run_dir, held=False)
        try:
            fcntl.flock(locked.lock_descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(locked.lock_descriptor)
        os.close(locked.run_descriptor)


def _bound_chain_record(record: dict[str, object], chain_id: str) -> bool:
    bound = journal._binding_chain_and_candidate(record)
    return bool(
        record.get("type") == "verification"
        and bound is not None
        and bound[0] == chain_id
    )


def _reported_chain(chain_id: str | None) -> str | None:
    """Return only a syntactically validated identifier for report output."""

    return chain_id if chain_id and journal.CHAIN_ID_PATTERN.fullmatch(chain_id) else None


def _chain_state(repository: Path, chain_id: str) -> dict[str, object]:
    descriptor: int | None = None
    try:
        descriptor, _ = journal._open_bound_directory(
            builders.chain_storage_root(repository)
        )
        value = builders._read_json_at(descriptor, f"{chain_id}.json")
        if not isinstance(value, dict):
            raise ValueError("chain state is not an object")
        return value
    except (OSError, ValueError, journal.CoordinationRefusal) as exc:
        raise journal.CoordinationRefusal(builders.TERMINAL_CHAIN_INVALID) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _project_records(
    repository: Path,
    records: Sequence[dict[str, object]],
    chain_id: str | None,
) -> tuple[list[dict[str, object]], str | None]:
    if chain_id is None:
        return list(records), None
    if journal.CHAIN_ID_PATTERN.fullmatch(chain_id) is None:
        return list(records), _INVALID_CHAIN
    if not any(_bound_chain_record(record, chain_id) for record in records):
        return list(records), f"{_NO_BOUND_GATES}{chain_id}"
    state = _chain_state(repository, chain_id)
    return close_law.projected_chain_records(records, chain_id, state), None


def _projected_issues(
    repository: Path,
    run_id: str,
    run_dir: Path,
    records: list[dict[str, object]],
    chain_id: str | None,
    shared_lock: batch.BatchLock,
) -> list[str]:
    projection_input = tuple(
        {name: value for name, value in record.items() if name != "_line"}
        for record in records
    )
    validation = close_law.project_close(run_dir, projection_input, "passed")
    issues_value = validation.get("issues")
    issues = list(issues_value) if isinstance(issues_value, list) else []
    try:
        with close_law.report_mode(chain_id, shared_lock):
            builders._terminal_chain_guard(
                repository, run_id, records, task_id=None
            )
    except journal.CoordinationRefusal as exc:
        issues.append(str(exc))
    try:
        journal.route_provenance.enforce_run_close(
            records, "passed", refusal=RuntimeError
        )
    except RuntimeError as exc:
        issues.extend(line for line in str(exc).splitlines() if line)
    return issues


def _json_bytes(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )


def _bounded_payload(
    run_id: str,
    journal_lines: int,
    chain_id: str | None,
    issues: Sequence[str],
) -> dict[str, object]:
    all_issues = list(issues)
    payload: dict[str, object] = {
        "schema": _OUTPUT_SCHEMA,
        "run_id": run_id,
        "journal_lines": journal_lines,
        "projected_chain": chain_id,
        "would_close_passed": not issues,
        "issues": all_issues,
    }
    if len(_json_bytes(payload)) <= _OUTPUT_LIMIT or not all_issues:
        return payload
    low, high = 0, len(all_issues)
    while low < high:
        retained = (low + high + 1) // 2
        payload["issues"] = all_issues[:retained]
        payload["issues_omitted"] = len(all_issues) - retained
        if len(_json_bytes(payload)) <= _OUTPUT_LIMIT:
            low = retained
        else:
            high = retained - 1
    payload["issues"] = all_issues[:low]
    payload["issues_omitted"] = len(all_issues) - low
    return payload


def _preflight_under_lock(
    repository: Path,
    run_id: str,
    run_dir: Path,
    chain: str | None,
    shared_lock: batch.BatchLock,
) -> dict[str, object]:
    reported_chain = _reported_chain(chain)
    records, read_issues = journal.read_journal(run_dir / "journal.jsonl")
    if read_issues:
        return _bounded_payload(run_id, len(records), reported_chain, read_issues)
    if any(record.get("type") == "run_closed" for record in records):
        return _bounded_payload(run_id, len(records), reported_chain, [_RUN_NOT_OPEN])
    try:
        projected, projection_issue = _project_records(repository, records, chain)
    except journal.CoordinationRefusal as exc:
        return _bounded_payload(run_id, len(records), reported_chain, [str(exc)])
    if projection_issue is not None:
        return _bounded_payload(
            run_id, len(records), reported_chain, [projection_issue]
        )
    issues = _projected_issues(
        repository, run_id, run_dir, projected, chain, shared_lock
    )
    return _bounded_payload(run_id, len(records), reported_chain, issues)


def preflight(repo: Path, run_id: str, *, chain: str | None = None) -> dict:
    repository, state_root = journal._resolve_repository(
        repo, "journal close-preflight"
    )
    validated_run_id = journal._operation_run_id(
        "journal close-preflight", run_id
    )
    run_dir = (
        state_root / ".codex-orchestrator" / "runs" / validated_run_id
    )
    try:
        with _shared_batch_lock(run_dir) as shared_lock:
            return _preflight_under_lock(
                repository, validated_run_id, run_dir, chain, shared_lock
            )
    except journal.CoordinationRefusal as exc:
        if str(exc) != journal.JOURNAL_READ_TRANSACTION_REFUSAL:
            raise
        return _bounded_payload(
            validated_run_id,
            0,
            _reported_chain(chain),
            [journal.JOURNAL_READ_TRANSACTION_REFUSAL],
        )


def main(repo: Path, run_id: str, *, chain: str | None = None) -> int:
    payload = preflight(repo, run_id, chain=chain)
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if payload["would_close_passed"] else 1
