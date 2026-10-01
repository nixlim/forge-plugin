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
_SUMMARY_ISSUE_LIMIT_BYTES = 4_096
_SUMMARY_TRUNCATION = "..."
_SUMMARY_ESCAPES = {
    "\b": r"\b",
    "\t": r"\t",
    "\n": r"\n",
    "\v": r"\v",
    "\f": r"\f",
    "\r": r"\r",
}
_RUN_NOT_OPEN = "forge: close preflight — run is not open"
_INVALID_CHAIN = "forge: close preflight — invalid chain id"
_NO_BOUND_GATES = (
    "forge: close preflight — projected chain has no bound gate records: "
)
CLOSE_PREFLIGHT_CONTROLS = frozenset({"close-preflight-line"})


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


def _open_shared_batch_lock(run_dir: Path) -> batch.BatchLock | None:
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
    except FileNotFoundError:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if run_descriptor is not None:
            os.close(run_descriptor)
        return None
    except (OSError, journal.CoordinationRefusal) as exc:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if run_descriptor is not None:
            os.close(run_descriptor)
        raise journal.CoordinationRefusal(
            journal.JOURNAL_READ_TRANSACTION_REFUSAL
        ) from exc


def _batch_sidecars_absent_at(descriptor: int) -> bool:
    return not any(
        journal._name_exists_at(descriptor, name)
        for name in (
            journal.BATCH_LOCK_NAME,
            journal.BATCH_INTENT_NAME,
            journal.BATCH_RECEIPTS_NAME,
        )
    )


def _batch_sidecars_absent(run_dir: Path) -> bool:
    descriptor: int | None = None
    try:
        descriptor, _ = journal._open_strict_batch_directory(
            run_dir, refusal=journal.JOURNAL_READ_TRANSACTION_REFUSAL
        )
        return _batch_sidecars_absent_at(descriptor)
    except FileNotFoundError:
        return True
    except (OSError, journal.CoordinationRefusal) as exc:
        raise journal.CoordinationRefusal(
            journal.JOURNAL_READ_TRANSACTION_REFUSAL
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _lockless_journal_snapshot(path: Path) -> bytes:
    descriptor: int | None = None
    try:
        descriptor, _ = journal._open_strict_batch_directory(
            path.parent, refusal=journal.JOURNAL_READ_TRANSACTION_REFUSAL
        )
        if not _batch_sidecars_absent_at(descriptor):
            raise journal.CoordinationRefusal(
                journal.JOURNAL_READ_TRANSACTION_REFUSAL
            )
        raw = journal._read_journal_descriptor_snapshot(descriptor, path.name)
        if (
            not _batch_sidecars_absent_at(descriptor)
            or journal._snapshot_activates_writer(raw)
        ):
            raise journal.CoordinationRefusal(
                journal.JOURNAL_READ_TRANSACTION_REFUSAL
            )
        return raw
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_preflight_journal(
    path: Path, shared_lock: batch.BatchLock | None
) -> tuple[list[dict[str, object]], list[str]]:
    if shared_lock is not None:
        return journal.read_journal(path)
    try:
        raw = _lockless_journal_snapshot(path)
        return journal._decode_journal_snapshot(
            raw, allow_partial_final_line=False
        )
    except journal.CoordinationRefusal as exc:
        if str(exc) == journal.JOURNAL_READ_TRANSACTION_REFUSAL:
            return [], [journal.JOURNAL_READ_TRANSACTION_REFUSAL]
        return [], [f"could not read journal: {exc}"]
    except FileNotFoundError:
        return [], [f"missing journal: {path}"]
    except (OSError, RuntimeError, ValueError) as exc:
        return [], [f"could not read journal: {exc}"]


@contextmanager
def _shared_batch_lock(run_dir: Path) -> Iterator[batch.BatchLock | None]:
    locked = _open_shared_batch_lock(run_dir)
    if locked is None:
        yield None
        if not _batch_sidecars_absent(run_dir):
            raise journal.CoordinationRefusal(
                journal.JOURNAL_READ_TRANSACTION_REFUSAL
            )
        return
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
    run_dir: Path,
    base_validation: dict[str, object],
    records: list[dict[str, object]],
    chain_id: str | None,
    shared_lock: batch.BatchLock | None,
) -> list[str]:
    projection_input = tuple(
        {name: value for name, value in record.items() if name != "_line"}
        for record in records
    )
    validation = close_law.project_close(
        run_dir,
        projection_input,
        "passed",
        base_validation=base_validation,
    )
    issues_value = validation.get("issues")
    issues = list(issues_value) if isinstance(issues_value, list) else []
    try:
        with close_law.report_mode(chain_id, shared_lock):
            builders._terminal_chain_guard(
                repository, run_dir.name, records, task_id=None
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


def _summary_prefix(projecting_chain: str | None) -> str:
    suffix = f", projecting {projecting_chain}" if projecting_chain else ""
    return f"close preflight (journal-only{suffix})"


def _summary_issue_fragment(character: str) -> str:
    escaped = _SUMMARY_ESCAPES.get(character)
    if escaped is not None:
        return escaped
    if character.isprintable():
        return character
    value = ord(character)
    if value <= 0xFF:
        return f"\\x{value:02x}"
    if value <= 0xFFFF:
        return f"\\u{value:04x}"
    return f"\\U{value:08x}"


def _summary_issue(issue: str) -> str:
    """Escape one untrusted issue and cap its human rendering."""

    fragments = [_summary_issue_fragment(character) for character in issue]
    if sum(len(fragment.encode("utf-8")) for fragment in fragments) <= (
        _SUMMARY_ISSUE_LIMIT_BYTES
    ):
        return "".join(fragments)
    budget = _SUMMARY_ISSUE_LIMIT_BYTES - len(_SUMMARY_TRUNCATION)
    retained: list[str] = []
    used = 0
    for fragment in fragments:
        size = len(fragment.encode("utf-8"))
        if used + size > budget:
            break
        retained.append(fragment)
        used += size
    return "".join(retained) + _SUMMARY_TRUNCATION


def _summary_records(run_dir: Path) -> list[dict[str, object]]:
    records, read_issues = journal.read_journal(run_dir / "journal.jsonl")
    if read_issues:
        raise ValueError("journal snapshot is unavailable")
    return records


def summary_line(
    run_dir: Path,
    projecting_chain: str | None,
    chain_state: dict[str, object] | None,
) -> str:
    """Summarize only journal law; omit terminal-chain artifact checks."""

    if "close-preflight-line" not in CLOSE_PREFLIGHT_CONTROLS:
        return ""
    prefix = _summary_prefix(None)
    try:
        valid_chain = (
            projecting_chain is None
            or journal.CHAIN_ID_PATTERN.fullmatch(projecting_chain) is not None
        )
        reported_chain = projecting_chain if valid_chain else None
        prefix = _summary_prefix(reported_chain)
        if not valid_chain:
            raise ValueError("projected chain identifier is malformed")
        records = _summary_records(run_dir)
        if any(record.get("type") == "run_closed" for record in records):
            return f"{prefix}: 1 issue(s), first: {_RUN_NOT_OPEN}"
        projected = list(records)
        if projecting_chain is not None:
            if not isinstance(chain_state, dict) or not any(
                _bound_chain_record(record, projecting_chain) for record in records
            ):
                raise ValueError("projected chain state is unavailable")
            projected = close_law.projected_chain_records(
                records, projecting_chain, chain_state
            )
        projection_input = tuple(
            {name: value for name, value in record.items() if name != "_line"}
            for record in projected
        )
        validation = close_law.project_close(run_dir, projection_input, "passed")
        raw_issues = validation.get("issues")
        if not isinstance(raw_issues, list) or not all(
            isinstance(issue, str) for issue in raw_issues
        ):
            raise ValueError("close projection issues are malformed")
        issues = list(raw_issues)
        try:
            journal.route_provenance.enforce_run_close(
                projected, "passed", refusal=RuntimeError
            )
        except RuntimeError as exc:
            issues.extend(line for line in str(exc).splitlines() if line)
        if not issues:
            return f"{prefix}: no issue found; terminal chain guard not run"
        return (
            f"{prefix}: {len(issues)} issue(s), first: "
            f"{_summary_issue(issues[0])}"
        )
    except Exception:
        return f"{prefix}: unavailable"


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
    shared_lock: batch.BatchLock | None,
) -> dict[str, object]:
    reported_chain = _reported_chain(chain)
    records, read_issues = _read_preflight_journal(
        run_dir / "journal.jsonl", shared_lock
    )
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
    base_validation = journal.validate_run(
        run_dir,
        gates=False,
        snapshot_records=records,
    )
    issues = _projected_issues(
        repository,
        run_dir,
        base_validation,
        projected,
        chain,
        shared_lock,
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
