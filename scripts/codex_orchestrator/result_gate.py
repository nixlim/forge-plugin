"""Pending-execution checks for run-bound commit-chain gates."""

from __future__ import annotations

import json
import shlex
from collections.abc import Collection, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from . import close_law, close_preflight, journal

RESULT_GATE_CONTROLS = frozenset(
    {"result-before-gate", "close-projection-warning"}
)

_WARNING_PREFIX = (
    "forge: journal warning — this append makes a passed close impossible "
    "as recorded: "
)
_WARNING_LIMIT = 20


@dataclass(frozen=True)
class Pending:
    """One mutating execution that has no authoritative terminal result."""

    execution: str
    task: str
    agent: str
    launched: bool


def _numbered_records(
    records: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    """Return authoritative one-based positions without trusting journal data."""

    return [
        {**record, "_line": line}
        for line, record in enumerate(records, start=1)
    ]


def _legacy_declaration_line(
    records: list[dict[str, object]],
) -> int | None:
    declaration = journal._legacy_compatibility_declaration(records)
    line = declaration.get("_line") if declaration is not None else None
    return line if isinstance(line, int) else None


def _latest_task_files(
    records: Sequence[dict[str, object]],
) -> dict[str, tuple[str, ...]]:
    latest: dict[str, tuple[str, ...]] = {}
    for record in records:
        task = record.get("id")
        if record.get("type") == "task" and isinstance(task, str) and task:
            latest[task] = journal._task_files(record)
    return latest


def _tasks_overlap(
    chain_paths: Sequence[str], task_files: Sequence[str]
) -> bool:
    return any(
        journal.pathspecs_overlap(chain_path, task_path)
        for chain_path in chain_paths
        for task_path in task_files
    )


def _result_is_terminal(result: dict[str, object]) -> bool:
    """Match the close law: every non-string status is non-terminal."""

    status = result.get("status")
    return (
        isinstance(status, str)
        and status in journal.TERMINAL_EXECUTION_STATUSES
    )


def pending_mutations(
    records: Sequence[dict[str, object]],
    *,
    chain_task: str,
    chain_paths: Sequence[str],
    exempt_paths: Collection[str],
) -> tuple[list[Pending], list[Pending]]:
    """Partition pending mutating executions into blocking and advisory sets."""

    if "result-before-gate" not in RESULT_GATE_CONTROLS:
        return [], []
    record_list = _numbered_records(records)
    if not journal._writer_contract_active(record_list):
        return [], []

    authoritative = journal._authoritative_execution_results(record_list)
    declaration_line = _legacy_declaration_line(record_list)
    task_files = _latest_task_files(record_list)
    exempt = frozenset(exempt_paths)
    effective_paths = tuple(path for path in chain_paths if path not in exempt)
    blocking: list[Pending] = []
    advisory: list[Pending] = []
    for record in record_list:
        if record.get("type") != "execution":
            continue
        role = record.get("role")
        if isinstance(role, str) and journal.route_vocab.is_non_mutating(role):
            continue
        key = journal.execution_key(record)
        task = record.get("task")
        if key is None or not isinstance(task, str) or not task:
            continue
        result = authoritative.get(key)
        if result is not None and _result_is_terminal(result):
            continue
        if journal._legacy_allows(
            "missing-execution-result", declaration_line, record
        ):
            continue
        pending = Pending(
            execution=key[1],
            task=task,
            agent=key[0],
            launched=isinstance(record.get("launch_marker"), str),
        )
        target = (
            blocking
            if task == chain_task
            or _tasks_overlap(effective_paths, task_files.get(task, ()))
            else advisory
        )
        target.append(pending)
    return blocking, advisory


def remediation(pending: Pending, run_id: str) -> str:
    """Return the pinned result-recording command for one pending execution."""

    quoted_run = shlex.quote(run_id)
    quoted_execution = shlex.quote(pending.execution)
    if pending.launched:
        return (
            "forge launch collect --repo <repo> "
            f"--run-id {quoted_run} --execution {quoted_execution}"
        )
    quoted_task = shlex.quote(pending.task)
    return (
        'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" '
        "journal execution-result "
        f"--repo <repo> --run-id {quoted_run} --idempotency-key <64-hex> "
        f"--execution {quoted_execution} --agent <agent> --task {quoted_task} "
        "--status <complete|blocked|failed> --summary <text>"
    )


def _diagnostic_word(value: str) -> str:
    """Return a quoted, single-line display spelling for an identifier."""

    escaped = json.dumps(value, ensure_ascii=True)[1:-1]
    return shlex.quote(escaped)


def refusal_message(verb: str, pending: Pending) -> str:
    """Return the pinned refusal diagnostic for one command."""

    return (
        f"forge: {verb} refused — execution {_diagnostic_word(pending.execution)} "
        f"(task {_diagnostic_word(pending.task)}) has no terminal execution_result; "
        "journal it before gating this candidate"
    )


def warning_message(pending: Pending) -> str:
    """Return the advisory diagnostic for a non-overlapping execution."""

    return (
        f"forge: warning — execution {_diagnostic_word(pending.execution)} "
        f"(task {_diagnostic_word(pending.task)}) "
        "has no terminal execution_result; its result will move the run-level "
        "gate boundary past this chain's gates"
    )


def _run_dir(repo: Path, run_id: str) -> Path:
    _, state_root = journal._resolve_repository(repo, "journal append")
    validated_run_id = journal._operation_run_id("journal append", run_id)
    return state_root / ".codex-orchestrator" / "runs" / validated_run_id


def _projected_issues(
    run_dir: Path, records: Sequence[dict[str, object]]
) -> list[str]:
    projection = close_law.project_close(run_dir, records, "passed")
    value = projection.get("issues")
    if not isinstance(value, list):
        raise ValueError
    issues: list[str] = []
    for issue in value:
        if not isinstance(issue, str):
            raise ValueError
        issues.append(issue)
    return issues


@contextmanager
def _projection_snapshot(run_dir: Path) -> Iterator[bytes]:
    """Hold one immutable shared-lock generation through both projections."""

    with close_preflight._shared_batch_lock(run_dir):
        yield journal._stable_journal_read(run_dir / "journal.jsonl")


def _warning_lines(issues: Sequence[str]) -> list[str]:
    lines = [f"{_WARNING_PREFIX}{issue}" for issue in issues[:_WARNING_LIMIT]]
    omitted = len(issues) - _WARNING_LIMIT
    if omitted > 0:
        lines.append(
            f"{_WARNING_PREFIX}(+{omitted} more; run journal close-preflight)"
        )
    return lines


def _new_issue_warnings(
    run_dir: Path,
    before: Sequence[dict[str, object]],
    after: Sequence[dict[str, object]],
) -> list[str]:
    baseline_before = set(_unterminated_execution_issues(before))
    baseline_new = [
        issue
        for issue in _unterminated_execution_issues(after)
        if issue not in baseline_before
    ]
    before_issues = _projected_issues(run_dir, before)
    projected_new = [
        issue
        for issue in _projected_issues(run_dir, after)
        if issue not in before_issues
    ]
    new_issues = [
        *baseline_new,
        *(issue for issue in projected_new if issue not in baseline_new),
    ]
    return _warning_lines(new_issues)


def _unterminated_execution_issues(
    records: Sequence[dict[str, object]],
) -> list[str]:
    """Return the structural issues an appended execution can introduce."""

    record_list = _numbered_records(records)
    authoritative = journal._authoritative_execution_results(record_list)
    declaration_line = _legacy_declaration_line(record_list)
    issues: list[str] = []
    for record in record_list:
        if record.get("type") != "execution":
            continue
        key = journal.execution_key(record)
        if key is None or key in authoritative:
            continue
        if journal._legacy_allows(
            "missing-execution-result", declaration_line, record
        ):
            continue
        issues.append(
            f"execution {journal.display_execution(key)} has no terminal "
            "execution_result"
        )
    return issues


def _receipt_snapshots(
    raw: bytes, receipt: dict[str, object]
) -> tuple[list[dict[str, object]], list[dict[str, object]]] | None:
    base_size = receipt.get("base_size")
    journal_size = receipt.get("journal_size")
    expected_sha256 = receipt.get("journal_sha256")
    if (
        type(base_size) is not int
        or type(journal_size) is not int
        or not isinstance(expected_sha256, str)
        or not 0 <= base_size <= journal_size
    ):
        return None
    if (
        len(raw) < journal_size
        or journal._sha256(raw[:journal_size]) != expected_sha256
    ):
        return None
    before, before_issues = journal._decode_journal_snapshot(
        raw[:base_size], allow_partial_final_line=False
    )
    after, after_issues = journal._decode_journal_snapshot(
        raw[:journal_size], allow_partial_final_line=False
    )
    if before_issues or after_issues:
        return None
    return before, after


def append_warnings(
    repo: Path, run_id: str, receipt: dict[str, object]
) -> list[str]:
    """Return close-projection warnings for one receipted journal append."""

    if "close-projection-warning" not in RESULT_GATE_CONTROLS:
        return []
    try:
        run_dir = _run_dir(repo, run_id)
        with _projection_snapshot(run_dir) as raw:
            snapshots = _receipt_snapshots(raw, receipt)
            if snapshots is None:
                return []
            before, after = snapshots
            return _new_issue_warnings(run_dir, before, after)
    except Exception:
        return []


def record_warnings(
    repo: Path, run_id: str, record: dict[str, object]
) -> list[str]:
    """Return close-projection warnings for one typed-launch record."""

    if "close-projection-warning" not in RESULT_GATE_CONTROLS:
        return []
    try:
        record_type = record.get("type")
        target_key = journal.execution_key(record)
        if record_type not in {"execution", "execution_result"} or target_key is None:
            return []
        run_dir = _run_dir(repo, run_id)
        with _projection_snapshot(run_dir) as raw:
            records, issues = journal._decode_journal_snapshot(
                raw, allow_partial_final_line=False
            )
            if issues:
                return []
            matches = [
                index
                for index, candidate in enumerate(records)
                if candidate.get("type") == record_type
                and journal.execution_key(candidate) == target_key
            ]
            if len(matches) != 1:
                return []
            index = matches[0]
            return _new_issue_warnings(
                run_dir, records[:index], records[: index + 1]
            )
    except Exception:
        return []


def print_record_warnings(
    repo: Path,
    run_id: str,
    record: dict[str, object],
    *,
    stream: TextIO,
) -> None:
    """Print typed-launch warnings without changing the owning command."""

    if "close-projection-warning" not in RESULT_GATE_CONTROLS:
        return
    try:
        for warning in record_warnings(repo, run_id, record):
            print(warning, file=stream)
    except Exception:
        return
