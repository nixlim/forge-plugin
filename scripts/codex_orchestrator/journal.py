"""Append-only run records and a structural, legacy-tolerant reader."""

# forge: modified from upstream — append plain facts and preserve legacy records as data.

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

INVALID_ENVELOPE = (
    "forge: journal append refused: record must be a JSON object with kind and run_id"
)
APPEND_IO_ERROR = "forge: journal append failed: I/O error"
TERMINAL_EXECUTION_STATUSES = frozenset({"complete", "blocked", "failed"})


class CoordinationRefusal(Exception):
    """A journal operation refused its envelope or encountered I/O."""


def _valid_run_id(run_id: object) -> bool:
    if not isinstance(run_id, str) or not run_id or run_id.startswith("."):
        return False
    if any(char in run_id for char in ("/", "\\")):
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in run_id):
        return False
    try:
        run_id.encode("utf-8")
    except UnicodeError:
        return False
    return True


def require_run_id(operation: str, run_id: object) -> str:
    if not _valid_run_id(run_id):
        raise CoordinationRefusal(f"forge: {operation} refused — invalid run id")
    assert isinstance(run_id, str)
    return run_id


def run_directory(repo: Path, run_id: str) -> Path:
    return repo / ".codex-orchestrator" / "runs" / run_id


def _record_line(record: object) -> bytes:
    if not isinstance(record, dict) or "kind" not in record or "run_id" not in record:
        raise CoordinationRefusal(INVALID_ENVELOPE)
    require_run_id("journal append", record["run_id"])
    try:
        encoded = json.dumps(
            record, sort_keys=True, allow_nan=False, separators=(",", ":")
        )
        return (encoded + "\n").encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as exc:
        raise CoordinationRefusal(INVALID_ENVELOPE) from exc


def _open_journal(repo: Path, run_id: str) -> int:
    require_run_id("journal append", run_id)
    try:
        directory = run_directory(repo, run_id)
        directory.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            pass
        parent = os.open(
            directory,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            return os.open(
                "journal.jsonl",
                os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent,
            )
        finally:
            os.close(parent)
    except OSError as exc:
        raise CoordinationRefusal(APPEND_IO_ERROR) from exc


def open_append_lock(repo: Path, run_id: str) -> int:
    """Open and lock the single append descriptor; caller closes it."""
    descriptor = _open_journal(repo, run_id)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except OSError as exc:
        os.close(descriptor)
        raise CoordinationRefusal(APPEND_IO_ERROR) from exc
    return descriptor


def _prepare_boundary(descriptor: int, path: Path) -> None:
    try:
        reader = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(reader)
            locked = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (locked.st_dev, locked.st_ino):
                raise OSError("journal file changed")
            size = opened.st_size
            if size and os.pread(reader, 1, size - 1) != b"\n":
                if os.write(descriptor, b"\n") != 1:
                    raise OSError("short journal boundary write")
        finally:
            os.close(reader)
    except OSError as exc:
        raise CoordinationRefusal(APPEND_IO_ERROR) from exc


def _write_line(descriptor: int, line: bytes) -> None:
    try:
        remaining = memoryview(line)
        while remaining:
            written = os.write(descriptor, remaining)
            if written == 0:
                raise OSError("zero-byte journal write")
            remaining = remaining[written:]
    except OSError as exc:
        raise CoordinationRefusal(APPEND_IO_ERROR) from exc


def append_locked_record(descriptor: int, path: Path, record: object) -> None:
    """Write one line using a descriptor already held under the append lock."""
    line = _record_line(record)
    _prepare_boundary(descriptor, path)
    _write_line(descriptor, line)


def append_run_record(
    repo: Path, run_id: str, record: object, *, operation: str = "journal append"
) -> Path:
    require_run_id(operation, run_id)
    _record_line(record)
    path = run_directory(repo, run_id) / "journal.jsonl"
    descriptor = open_append_lock(repo, run_id)
    try:
        append_locked_record(descriptor, path, record)
    finally:
        os.close(descriptor)
    return path


def _reject_constant(_value: str) -> None:
    raise ValueError("non-JSON constant")


def _decode(
    raw: bytes, *, allow_partial_final_line: bool = False
) -> tuple[list[dict[str, object]], list[str]]:
    records: list[dict[str, object]] = []
    issues: list[str] = []
    terminated = raw.endswith(b"\n")
    lines = raw.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    for number, line in enumerate(lines, 1):
        if allow_partial_final_line and number == len(lines) and not terminated:
            try:
                json.loads(line, parse_constant=_reject_constant)
            except (ValueError, UnicodeError, RecursionError):
                continue
        try:
            value = json.loads(line, parse_constant=_reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            issues.append(f"forge: journal validate failed: malformed JSON object at line {number}")
            continue
        if not isinstance(value, dict) or not (
            ("kind" in value and "run_id" in value and _valid_run_id(value["run_id"]))
            or "type" in value
        ):
            issues.append(f"forge: journal validate failed: malformed JSON object at line {number}")
            continue
        records.append(value)
    return records, issues


def read_journal(
    path: Path, *, allow_partial_final_line: bool = False
) -> tuple[list[dict[str, object]], list[str]]:
    try:
        return _decode(path.read_bytes(), allow_partial_final_line=allow_partial_final_line)
    except OSError:
        return [], ["journal.jsonl: I/O error"]


def validate_run(run_dir: Path) -> dict[str, object]:
    _, issues = read_journal(run_dir / "journal.jsonl")
    return {"ok": not issues, "issues": issues}


def execution_key(record: dict[str, object]) -> tuple[str, str] | None:
    agent = record.get("agent", record.get("role"))
    execution = record.get("execution_id", record.get("execution"))
    if isinstance(agent, str) and agent and isinstance(execution, str) and execution:
        return agent, execution
    return None


def resolve_run_path(run_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (run_dir / path).resolve()
