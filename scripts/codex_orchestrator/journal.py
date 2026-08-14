from __future__ import annotations

import datetime as dt
import errno
import fcntl
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

FORGE_SCRIPTS = Path(__file__).resolve().parents[1] / "forge"
if str(FORGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FORGE_SCRIPTS))

from commitment_paths import path_tokens  # noqa: E402

JOURNAL_ENTRY_TYPES = {
    "run_started",
    "task",
    "execution",
    "execution_result",
    "verification",
    "decision",
    "run_closed",
}

TERMINAL_TASK_STATUSES = {"complete", "blocked", "failed"}
TERMINAL_EXECUTION_STATUSES = {"complete", "blocked", "failed"}
VERIFICATION_RESULTS = {"passed", "failed", "inconclusive", "skipped"}

# forge: modified from upstream — recognize gate records without changing journal enums
GATE_VERIFICATION_PREFIXES = ("gate-1: ", "gate-2: ", "gate-3: ")
GATE_3_CRITERION = "gate-3: review-final verdict"


# forge: modified from upstream — enforce D13 journal ownership and run-scope admission
REGISTRY_UNAVAILABLE = "forge: new run refused — run registry unavailable"
REGISTRY_SCHEMA_VERSION = 1
RETIREMENT_RESOLUTION = "run-retired: non-mutating"
READMISSION_RESOLUTION = "scope-readmission: locked"
OWNER_PATTERN = re.compile(
    rb"pid: ([1-9][0-9]*)\nhost: ([^\n]+)\nstarted_at: ([^\n]+)\n"
)
UTC_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z")
MAGIC_CHARS = "*?["
TRANSIENT_SCOPE_ROOTS = (".forge", ".codex-orchestrator", ".worktrees")
CITATION_CORRECTION_TOKEN = "citation-correction:"
CITATION_DECISION_CORRECTION = re.compile(
    r"^(?P<id>\S+) basis\[(?P<index>[0-9]+)\]: (?P<path>.+)$"
)
CITATION_VERIFICATION_CORRECTION = re.compile(
    r"^(?P<id>\S+) observation: (?P<cited>.+?) -> (?P<path>.+)$"
)


class CoordinationRefusal(RuntimeError):
    """A fail-closed D13 coordination refusal whose text is operator-facing."""


class JournalAppendRefusal(CoordinationRefusal):
    """An exact FR-191 ownership refusal."""


@dataclass(frozen=True)
class Owner:
    pid: int
    host: str
    started_at: str


@dataclass(frozen=True)
class RunState:
    run_id: str
    run_dir: Path
    disposition: str
    scope: tuple[str, ...]
    successor_of: str | None = None


def _byte_key(value: str) -> bytes:
    return value.encode("utf-8")


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _valid_utc(value: str) -> bool:
    if not UTC_PATTERN.fullmatch(value):
        return False
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.utcoffset() == dt.timedelta(0)


def _session_owner() -> Owner:
    raw_pid = os.environ.get("FORGE_SESSION_PID", "")
    if not re.fullmatch(r"[1-9][0-9]*", raw_pid):
        raise CoordinationRefusal(
            "forge: FORGE_SESSION_PID must be exported as a positive base-10 integer"
        )
    host = socket.gethostname()
    if not host or "\n" in host or "\r" in host:
        raise CoordinationRefusal("forge: current journal owner host is unavailable")
    return Owner(pid=int(raw_pid), host=host, started_at=_utc_now())


def _owner_bytes(owner: Owner) -> bytes:
    return (
        f"pid: {owner.pid}\nhost: {owner.host}\nstarted_at: {owner.started_at}\n"
    ).encode("utf-8")


def _parse_owner(path: Path) -> Owner | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    match = OWNER_PATTERN.fullmatch(raw)
    if match is None:
        return None
    try:
        host = match.group(2).decode("utf-8")
        started_at = match.group(3).decode("ascii")
        owner = Owner(pid=int(match.group(1)), host=host, started_at=started_at)
    except (UnicodeError, ValueError):
        return None
    if not owner.host or not _valid_utc(owner.started_at):
        return None
    return owner


def _pid_is_live(pid: int) -> bool | None:
    try:
        os.kill(pid, 0)
    except OverflowError:
        # A syntactically valid but OS-unrepresentable PID cannot be proven
        # dead, so DM-010 classifies it as unverifiable foreign ownership.
        return None
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno == errno.EPERM:
            return None
        return None
    return True


def _citation_correction_lines(record: dict[str, object]) -> tuple[str, ...] | None:
    """Return a strict FR-191 correction block, or ``None`` for ordinary decisions."""

    if record.get("type") != "decision":
        return None
    resolution = record.get("resolution")
    if not isinstance(resolution, str) or not resolution.startswith(CITATION_CORRECTION_TOKEN):
        return None
    suffix = resolution[len(CITATION_CORRECTION_TOKEN) :]
    if not suffix.startswith("\n"):
        raise CoordinationRefusal(
            "forge: journal append refused — invalid citation correction"
        )
    lines = tuple(suffix[1:].splitlines())
    if not lines or any(
        not line
        or (
            CITATION_DECISION_CORRECTION.fullmatch(line) is None
            and CITATION_VERIFICATION_CORRECTION.fullmatch(line) is None
        )
        for line in lines
    ):
        raise CoordinationRefusal(
            "forge: journal append refused — invalid citation correction"
        )
    return lines


def _validate_citation_correction(record: dict[str, object]) -> None:
    _citation_correction_lines(record)


def _citation_targets(records: list[dict[str, object]]) -> set[tuple[object, ...]]:
    targets: set[tuple[object, ...]] = set()
    for record in records:
        kind = record.get("type")
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            continue
        if kind == "decision" and isinstance(record.get("basis"), list):
            for index, value in enumerate(record["basis"]):  # type: ignore[union-attr]
                if isinstance(value, str) and path_tokens(value, context="basis"):
                    targets.add(("decision", record_id, index))
        elif kind == "verification" and isinstance(record.get("observation"), str):
            targets.update(
                ("verification", record_id, token)
                for token in path_tokens(record["observation"], context="observation")
            )
    return targets


def _validate_citation_targets(
    record: dict[str, object], prior_records: list[dict[str, object]]
) -> None:
    lines = _citation_correction_lines(record)
    if lines is None:
        return
    available = _citation_targets(prior_records)
    for line in lines:
        decision_match = CITATION_DECISION_CORRECTION.fullmatch(line)
        verification_match = CITATION_VERIFICATION_CORRECTION.fullmatch(line)
        if decision_match is not None:
            target: tuple[object, ...] = (
                "decision",
                decision_match.group("id"),
                int(decision_match.group("index")),
            )
        else:
            assert verification_match is not None
            target = (
                "verification",
                verification_match.group("id"),
                verification_match.group("cited"),
            )
        if target not in available:
            raise CoordinationRefusal(
                "forge: journal append refused — citation correction target does not exist"
            )


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _journal_line(record: dict[str, object]) -> bytes:
    return (
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _resolve_state_root(repo: Path) -> Path:
    try:
        repository = repo.expanduser().resolve(strict=True)
        common: Path | None = None
        for arguments, require_absolute in (
            (("--path-format=absolute", "--git-common-dir"), True),
            (("--git-common-dir",), False),
        ):
            completed = subprocess.run(
                ["git", "-C", str(repository), "rev-parse", *arguments],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            rendered = completed.stdout.rstrip("\n")
            if completed.returncode != 0 or not rendered or "\n" in rendered or "\r" in rendered:
                continue
            candidate = Path(rendered)
            if require_absolute and not candidate.is_absolute():
                continue
            if not candidate.is_absolute():
                candidate = repository / candidate
            try:
                common = candidate.resolve(strict=True)
            except OSError:
                continue
            break
        if common is None or not common.is_dir():
            raise ValueError
        return common.parent
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc


@contextmanager
def _registry_lock(state_root: Path) -> Iterator[None]:
    lock_path = state_root / ".forge/tmp/run-registry.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except CoordinationRefusal:
        raise
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc


def _valid_run_id(run_id: object) -> bool:
    if (
        not isinstance(run_id, str)
        or not run_id
        or run_id.startswith(".")
        or run_id in {".", ".."}
    ):
        return False
    if any(character in run_id for character in ("/", "\\", "\x00", "\n", "\r")):
        return False
    try:
        run_id.encode("utf-8")
    except UnicodeError:
        return False
    return True


def _valid_scope_item(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if value.startswith(("/", "!", "^", "-", ":", "./")) or "\\" in value or "\x00" in value:
        return False
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    first = parts[0]
    # A magical top-level segment can select transient coordination state, so
    # it cannot prove the FR-192 exclusion and must fail conservatively.
    if first in TRANSIENT_SCOPE_ROOTS or any(character in first for character in MAGIC_CHARS):
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return True


def canonical_scope(values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    if not all(_valid_scope_item(value) for value in values):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    return tuple(sorted(set(values), key=_byte_key))


def _scope_from_record(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    try:
        canonical = canonical_scope(value)
    except CoordinationRefusal:
        return None
    return canonical if list(canonical) == value else None


def _segment_may_overlap(left: str, right: str) -> bool:
    left_magic = any(character in left for character in MAGIC_CHARS)
    right_magic = any(character in right for character in MAGIC_CHARS)
    if not left_magic and not right_magic:
        return left == right
    # Git wildmatch/pathspec magic can span more of the candidate than a
    # segment-local fnmatch probe suggests.  Once either segment contains
    # magic, no disjointness proof is safe without asking Git about a finite
    # repository tree, so admission fails conservatively.
    return True


def pathspecs_overlap(left: str, right: str) -> bool:
    """Conservatively prove disjointness for positive repository pathspecs."""

    left_parts = left.split("/")
    right_parts = right.split("/")
    limit = min(len(left_parts), len(right_parts))
    for index in range(limit):
        left_part = left_parts[index]
        right_part = right_parts[index]
        if left_part == "**" or right_part == "**":
            return True
        if not _segment_may_overlap(left_part, right_part):
            return False
    if len(left_parts) == len(right_parts):
        return True
    # A shorter positive pathspec can select descendants, and Git wildcard
    # semantics may consume path separators.  Matching prefixes therefore
    # cannot prove disjointness merely because component counts differ.
    return True


def scopes_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return any(pathspecs_overlap(a, b) for a in left for b in right)


def _literal_prefix(pattern: str) -> str:
    segments: list[str] = []
    for segment in pattern.split("/"):
        if segment == "**" or any(character in segment for character in MAGIC_CHARS):
            break
        segments.append(segment)
    return "/".join(segments)


def pathspec_contained(candidate: str, container: str) -> bool:
    if candidate == container:
        return True
    container_magic = any(character in container for character in MAGIC_CHARS)
    candidate_magic = any(character in candidate for character in MAGIC_CHARS)
    if not container_magic:
        return candidate == container or candidate.startswith(container.rstrip("/") + "/")
    if container.endswith("/**") and not any(
        character in container[:-3] for character in MAGIC_CHARS
    ):
        prefix = container[:-3].rstrip("/")
        return candidate == prefix or candidate.startswith(prefix + "/")
    if not candidate_magic:
        import fnmatch

        return fnmatch.fnmatchcase(candidate, container)
    candidate_prefix = _literal_prefix(candidate)
    return bool(candidate_prefix) and candidate_prefix == container.rstrip("/")


def _task_files_contained(record: dict[str, object], scope: tuple[str, ...]) -> bool:
    if record.get("type") != "task":
        return True
    files = record.get("files")
    if not isinstance(files, list) or not files:
        return record.get("status") != "active"
    for item in files:
        if not _valid_scope_item(item) or not any(
            pathspec_contained(item, admitted) for admitted in scope
        ):
            return False
    return True


def _task_files(record: dict[str, object]) -> tuple[str, ...]:
    if record.get("type") != "task":
        return ()
    files = record.get("files")
    if not isinstance(files, list):
        return ()
    return tuple(item for item in files if isinstance(item, str))


def _all_task_files_contained(
    records: list[dict[str, object]], scope: tuple[str, ...]
) -> bool:
    return all(
        all(any(pathspec_contained(item, admitted) for admitted in scope) for item in _task_files(record))
        for record in records
    )


def _read_raw_records(journal: Path) -> list[dict[str, object]]:
    try:
        raw = journal.read_bytes()
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    if not raw or not raw.endswith(b"\n"):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    records: list[dict[str, object]] = []
    try:
        for line in raw.splitlines():
            value = json.loads(line.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError
            records.append(value)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    return records


def _scan_run(run_dir: Path) -> RunState:
    run_id = run_dir.name
    if not _valid_run_id(run_id):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    records = _read_raw_records(run_dir / "journal.jsonl")
    starts = [record for record in records if record.get("type") == "run_started"]
    closures = [record for record in records if record.get("type") == "run_closed"]
    if len(starts) != 1 or records[0] is not starts[0] or starts[0].get("run_id") != run_id:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    if len(closures) > 1 or (closures and records[-1] is not closures[0]):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    scope = _scope_from_record(starts[0].get("scope"))
    successor_of = starts[0].get("successor_of")
    if successor_of is not None and not _valid_run_id(successor_of):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    for record in records[1:]:
        if record.get("type") == "decision" and record.get("resolution") == READMISSION_RESOLUTION:
            updated = _scope_from_record(record.get("scope"))
            if updated is None:
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            scope = updated
    retired = bool(
        records
        and records[-1].get("type") == "decision"
        and records[-1].get("id") == "forge-run-retired"
        and records[-1].get("resolution") == RETIREMENT_RESOLUTION
    )
    disposition = "closed" if closures else "retired" if retired else "open"
    if disposition != "closed" and scope is None:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    return RunState(
        run_id=run_id,
        run_dir=run_dir,
        disposition=disposition,
        scope=scope or (),
        successor_of=successor_of if isinstance(successor_of, str) else None,
    )


def _scan_runs(state_root: Path) -> dict[str, RunState]:
    runs_root = state_root / ".codex-orchestrator/runs"
    if not runs_root.exists():
        return {}
    try:
        entries = list(runs_root.iterdir())
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    # An atomic-open temporary can survive a process crash after ownership and
    # run_started were written but before rename/registry replacement. Its
    # scope is therefore ambiguous open-run state and must never be skipped.
    if any(entry.name.startswith(".") for entry in entries):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    if any(not entry.is_dir() for entry in entries):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    directories = entries
    states: dict[str, RunState] = {}
    for run_dir in sorted(directories, key=lambda path: _byte_key(path.name)):
        state = _scan_run(run_dir)
        if state.run_id in states:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        states[state.run_id] = state
    return states


def _registry_payload(open_runs: dict[str, tuple[str, ...]]) -> bytes:
    payload = {
        "open_runs": [
            {"run_id": run_id, "scope": list(open_runs[run_id])}
            for run_id in sorted(open_runs, key=_byte_key)
        ],
        "schema_version": REGISTRY_SCHEMA_VERSION,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load_registry(state_root: Path, states: dict[str, RunState]) -> dict[str, tuple[str, ...]]:
    registry_path = state_root / ".forge/tmp/run-registry.json"
    if not registry_path.exists():
        if any(state.disposition == "open" for state in states.values()):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        return {}
    try:
        raw = registry_path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    if not isinstance(value, dict) or set(value) != {"open_runs", "schema_version"}:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    if value.get("schema_version") != REGISTRY_SCHEMA_VERSION or not isinstance(value.get("open_runs"), list):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    loaded: dict[str, tuple[str, ...]] = {}
    for item in value["open_runs"]:
        if not isinstance(item, dict) or set(item) != {"run_id", "scope"}:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        run_id = item.get("run_id")
        scope = _scope_from_record(item.get("scope"))
        if not _valid_run_id(run_id) or scope is None or run_id in loaded:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        loaded[run_id] = scope
    if raw != _registry_payload(loaded):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    reconciled: dict[str, tuple[str, ...]] = {}
    for run_id, scope in loaded.items():
        state = states.get(run_id)
        if state is None:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        if state.disposition == "open":
            if state.scope != scope:
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            reconciled[run_id] = scope
    for run_id, state in states.items():
        if state.disposition == "open" and run_id not in loaded:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    if reconciled != loaded:
        _atomic_replace(registry_path, _registry_payload(reconciled))
    return reconciled


def _write_registry(state_root: Path, open_runs: dict[str, tuple[str, ...]]) -> None:
    _atomic_replace(
        state_root / ".forge/tmp/run-registry.json", _registry_payload(open_runs)
    )


def _owner_refusal(run_id: str, owner: Owner) -> JournalAppendRefusal:
    return JournalAppendRefusal(
        f"forge: journal append refused — run {run_id} has live owner {owner.pid}@{owner.host}"
    )


def _ensure_owner(run_dir: Path, run_id: str, current: Owner) -> bool:
    owner_path = run_dir / "owner"
    owner = _parse_owner(owner_path)
    if owner is None:
        raise JournalAppendRefusal(
            f"forge: journal append refused — owner record missing or malformed for run {run_id}"
        )
    if owner.host == current.host and owner.pid == current.pid:
        return False
    if owner.host != current.host:
        raise _owner_refusal(run_id, owner)
    live = _pid_is_live(owner.pid)
    if live is not False:
        raise _owner_refusal(run_id, owner)
    _atomic_replace(owner_path, _owner_bytes(current))
    return True


def _append_with_locked_stream(
    stream: object,
    run_dir: Path,
    run_id: str,
    record: dict[str, object],
    *,
    allow_lifecycle: bool = False,
) -> int:
    current = _session_owner()
    _ensure_owner(run_dir, run_id, current)
    if not isinstance(record, dict) or record.get("type") not in JOURNAL_ENTRY_TYPES:
        raise CoordinationRefusal("forge: journal append refused — invalid journal record")
    if not allow_lifecycle and record.get("type") in {"run_started", "run_closed"}:
        raise CoordinationRefusal("forge: journal append refused — lifecycle command required")
    if "run_id" in record and record.get("run_id") != run_id:
        raise CoordinationRefusal("forge: journal append refused — run identity mismatch")
    # CONTROL citation-correction-grammar BEGIN
    stream_path = Path(stream.name)  # type: ignore[attr-defined]
    _validate_citation_targets(record, _read_raw_records(stream_path))
    # CONTROL citation-correction-grammar END
    payload = _journal_line(record)
    try:
        descriptor = stream.fileno()  # type: ignore[attr-defined]
        offset = os.lseek(descriptor, 0, os.SEEK_END)
        remaining = memoryview(payload)
        while remaining:
            count = os.write(descriptor, remaining)
            if count <= 0:
                raise OSError(errno.EIO, "short journal write")
            remaining = remaining[count:]
        os.fsync(descriptor)
        return offset
    except (AttributeError, OSError) as exc:
        try:
            os.ftruncate(descriptor, offset)  # type: ignore[possibly-undefined]
            os.fsync(descriptor)  # type: ignore[possibly-undefined]
        except (AttributeError, OSError, UnboundLocalError):
            pass
        raise CoordinationRefusal("forge: journal append refused — journal write failed") from exc


def _rollback_append(stream: object, offset: int) -> None:
    try:
        descriptor = stream.fileno()  # type: ignore[attr-defined]
        os.ftruncate(descriptor, offset)
        os.lseek(descriptor, offset, os.SEEK_SET)
        os.fsync(descriptor)
    except (AttributeError, OSError) as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc


@contextmanager
def _locked_journal(run_dir: Path) -> Iterator[object]:
    journal = run_dir / "journal.jsonl"
    try:
        with journal.open("a+b", buffering=0) as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield stream
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except CoordinationRefusal:
        raise
    except OSError as exc:
        raise CoordinationRefusal("forge: journal append refused — journal write failed") from exc


def append_owned_record(journal: Path, record: dict[str, object]) -> None:
    """Append one record only after the current session proves DM-010 ownership."""

    run_dir = journal.expanduser().resolve().parent
    run_id = run_dir.name
    if not _valid_run_id(run_id):
        raise CoordinationRefusal("forge: journal append refused — invalid run identity")
    state_root = _resolve_state_root(run_dir)
    with _registry_lock(state_root):
        states = _scan_runs(state_root)
        open_runs = _load_registry(state_root, states)
        state = states.get(run_id)
        expected = state_root / ".codex-orchestrator/runs" / run_id / "journal.jsonl"
        if (
            state is None
            or state.disposition != "open"
            or run_id not in open_runs
            or journal.expanduser().resolve() != expected.resolve()
        ):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        with _locked_journal(state.run_dir) as stream:
            _append_with_locked_stream(stream, state.run_dir, run_id, record)


def open_run(
    repo: Path,
    run_id: str,
    scope_values: list[str],
    record: dict[str, object],
    *,
    successor_of: str | None = None,
) -> Path:
    if not _valid_run_id(run_id) or (successor_of is not None and not _valid_run_id(successor_of)):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    scope = canonical_scope(scope_values)
    current = _session_owner()
    state_root = _resolve_state_root(repo)
    with _registry_lock(state_root):
        states = _scan_runs(state_root)
        open_runs = _load_registry(state_root, states)
        if run_id in states:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        if successor_of is not None:
            predecessor = states.get(successor_of)
            if predecessor is None or predecessor.disposition != "retired":
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            if not scopes_overlap(scope, predecessor.scope):
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            with _locked_journal(predecessor.run_dir):
                _ensure_owner(predecessor.run_dir, predecessor.run_id, current)
        conflicts = [
            other_id
            for other_id, other_scope in open_runs.items()
            if scopes_overlap(scope, other_scope)
        ]
        if conflicts:
            lines = [
                f"forge: new run refused — scope overlap between {run_id} and open run {other_id}"
                for other_id in sorted(conflicts, key=_byte_key)
            ]
            raise CoordinationRefusal("\n".join(lines))
        for predecessor in states.values():
            if predecessor.disposition != "retired" or not scopes_overlap(scope, predecessor.scope):
                continue
            if predecessor.run_id != successor_of:
                raise CoordinationRefusal(
                    f"forge: new run refused — scope overlap between {run_id} and open run {predecessor.run_id}"
                )
        if not isinstance(record, dict) or record.get("type") != "run_started":
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        if record.get("run_id") != run_id:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        opening = dict(record)
        opening["scope"] = list(scope)
        if successor_of is not None:
            opening["successor_of"] = successor_of
        elif "successor_of" in opening:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        runs_root = state_root / ".codex-orchestrator/runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        target = runs_root / run_id
        temporary = Path(tempfile.mkdtemp(prefix=f".{run_id}.open.", dir=runs_root))
        installed = False
        try:
            (temporary / "owner").write_bytes(_owner_bytes(current))
            (temporary / "journal.jsonl").write_bytes(_journal_line(opening))
            os.replace(temporary, target)
            installed = True
            updated = dict(open_runs)
            updated[run_id] = scope
            _write_registry(state_root, updated)
        except BaseException:
            cleanup = target if installed else temporary
            for name in ("owner", "journal.jsonl"):
                try:
                    (cleanup / name).unlink()
                except OSError:
                    pass
            try:
                cleanup.rmdir()
            except OSError:
                pass
            raise
        return target


def append_run_record(repo: Path, run_id: str, record: dict[str, object]) -> None:
    if not _valid_run_id(run_id):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    state_root = _resolve_state_root(repo)
    with _registry_lock(state_root):
        states = _scan_runs(state_root)
        open_runs = _load_registry(state_root, states)
        state = states.get(run_id)
        if state is None or state.disposition != "open" or run_id not in open_runs:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        with _locked_journal(state.run_dir) as stream:
            if not _task_files_contained(record, open_runs[run_id]):
                raise CoordinationRefusal(
                    f"forge: journal append refused — task files exceed admitted scope for run {run_id}"
                )
            _append_with_locked_stream(stream, state.run_dir, run_id, record)


def readmit_run(repo: Path, run_id: str, scope_values: list[str]) -> None:
    if not _valid_run_id(run_id):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    scope = canonical_scope(scope_values)
    state_root = _resolve_state_root(repo)
    with _registry_lock(state_root):
        states = _scan_runs(state_root)
        open_runs = _load_registry(state_root, states)
        state = states.get(run_id)
        if state is None or state.disposition != "open" or run_id not in open_runs:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        conflicts = [
            other_id
            for other_id, other_scope in open_runs.items()
            if other_id != run_id and scopes_overlap(scope, other_scope)
        ]
        if conflicts:
            raise CoordinationRefusal(
                "\n".join(
                    f"forge: new run refused — scope overlap between {run_id} and open run {other_id}"
                    for other_id in sorted(conflicts, key=_byte_key)
                )
            )
        for other in states.values():
            if other.disposition != "retired" or other.run_id == state.successor_of:
                continue
            if scopes_overlap(scope, other.scope):
                raise CoordinationRefusal(
                    f"forge: new run refused — scope overlap between {run_id} and open run {other.run_id}"
                )
        record = {
            "type": "decision",
            "id": f"forge-scope-readmission-{uuid.uuid4().hex}",
            "resolution": READMISSION_RESOLUTION,
            "scope": list(scope),
            "recorded_at": _utc_now(),
        }
        with _locked_journal(state.run_dir) as stream:
            _ensure_owner(state.run_dir, run_id, _session_owner())
            if not _all_task_files_contained(
                _read_raw_records(state.run_dir / "journal.jsonl"), scope
            ):
                raise CoordinationRefusal(
                    f"forge: journal append refused — task files exceed admitted scope for run {run_id}"
                )
            offset = _append_with_locked_stream(stream, state.run_dir, run_id, record)
            try:
                updated = dict(open_runs)
                updated[run_id] = scope
                _write_registry(state_root, updated)
            except BaseException:
                _rollback_append(stream, offset)
                raise


def close_run(repo: Path, run_id: str, record: dict[str, object]) -> None:
    if not _valid_run_id(run_id) or not isinstance(record, dict) or record.get("type") != "run_closed":
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    state_root = _resolve_state_root(repo)
    with _registry_lock(state_root):
        states = _scan_runs(state_root)
        open_runs = _load_registry(state_root, states)
        state = states.get(run_id)
        if state is None or state.disposition != "open" or run_id not in open_runs:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        with _locked_journal(state.run_dir) as stream:
            offset = _append_with_locked_stream(
                stream, state.run_dir, run_id, record, allow_lifecycle=True
            )
            try:
                updated = dict(open_runs)
                updated.pop(run_id, None)
                _write_registry(state_root, updated)
            except BaseException:
                _rollback_append(stream, offset)
                raise


def retire_run(repo: Path, run_id: str) -> None:
    if not _valid_run_id(run_id):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    state_root = _resolve_state_root(repo)
    with _registry_lock(state_root):
        states = _scan_runs(state_root)
        open_runs = _load_registry(state_root, states)
        state = states.get(run_id)
        if state is None or state.disposition != "open" or run_id not in open_runs:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        record = {
            "type": "decision",
            "id": "forge-run-retired",
            "resolution": RETIREMENT_RESOLUTION,
            "recorded_at": _utc_now(),
        }
        with _locked_journal(state.run_dir) as stream:
            offset = _append_with_locked_stream(stream, state.run_dir, run_id, record)
            try:
                updated = dict(open_runs)
                updated.pop(run_id, None)
                _write_registry(state_root, updated)
            except BaseException:
                _rollback_append(stream, offset)
                raise


def read_journal(
    path: Path, *, allow_partial_final_line: bool = False
) -> tuple[list[dict[str, object]], list[str]]:
    records: list[dict[str, object]] = []
    issues: list[str] = []
    try:
        if not path.exists():
            return records, [f"missing journal: {path}"]
        with path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                terminated = raw_line.endswith(b"\n")
                try:
                    line = raw_line.decode("utf-8")
                except UnicodeDecodeError as exc:
                    if allow_partial_final_line and not terminated:
                        break
                    issues.append(f"could not read journal: {exc}")
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    value = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    if allow_partial_final_line and not terminated:
                        break
                    issues.append(f"line {line_number}: invalid JSON: {exc.msg}")
                    continue
                if not isinstance(value, dict):
                    issues.append(f"line {line_number}: journal entry must be an object")
                    continue
                value["_line"] = line_number
                records.append(value)
    except (OSError, RuntimeError, ValueError) as exc:
        issues.append(f"could not read journal: {exc}")
    return records, issues


def record_line(record: dict[str, object]) -> str:
    line = record.get("_line")
    return f"line {line}" if isinstance(line, int) else "journal"


def execution_key(record: dict[str, object]) -> tuple[str, str] | None:
    agent = record.get("agent")
    execution = record.get("execution")
    if isinstance(agent, str) and agent and isinstance(execution, str) and execution:
        return agent, execution
    return None


def display_execution(key: tuple[str, str]) -> str:
    return f"{key[0]}/{key[1]}"


def resolve_run_path(run_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (run_dir / path).resolve()


def declared_file_exists(run_dir: Path, value: object, *, nonempty: bool = False) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        path = resolve_run_path(run_dir, value)
        return path.is_file() and (not nonempty or path.stat().st_size > 0)
    except (OSError, RuntimeError, ValueError):
        return False


def check_declared_file(
    run_dir: Path, record: dict[str, object], field: str, issues: list[str]
) -> None:
    if field not in record:
        return
    value = record.get(field)
    if not isinstance(value, str) or not value:
        issues.append(f"{record_line(record)}: {field} must name a file")
        return
    if not declared_file_exists(run_dir, value):
        issues.append(f"{record_line(record)}: referenced {field} file does not exist: {value}")


# forge: modified from upstream — add opt-in checks over the existing journal schema
def check_gate_profile(records: list[dict[str, object]], issues: list[str]) -> None:
    verifications = [record for record in records if record.get("type") == "verification"]
    passed_close = any(
        record.get("type") == "run_closed" and record.get("judgment") == "passed"
        for record in records
    )
    mutating_executions = [
        record
        for record in records
        if record.get("type") == "execution" and record.get("role") != "review"
    ]

    if passed_close and mutating_executions:
        mutating_keys = {
            key
            for record in mutating_executions
            if (key := execution_key(record)) is not None
        }
        terminal_results = [
            record
            for record in records
            if record.get("type") == "execution_result"
            and record.get("status") in TERMINAL_EXECUTION_STATUSES
            and execution_key(record) in mutating_keys
        ]
        terminal_result_keys = {execution_key(record) for record in terminal_results}
        has_unterminated_mutation = any(
            execution_key(record) not in terminal_result_keys
            for record in mutating_executions
        )
        terminal_result_lines = [
            int(record.get("_line", 0)) for record in terminal_results
        ]
        last_mutating_result_line = max(terminal_result_lines, default=0)
        required_gates = (
            (
                "gate-1",
                lambda criterion: criterion.startswith("gate-1: "),
            ),
            (
                "gate-2",
                lambda criterion: criterion.startswith("gate-2: "),
            ),
            (
                GATE_3_CRITERION,
                lambda criterion: criterion == GATE_3_CRITERION,
            ),
        )
        for gate_name, criterion_matches in required_gates:
            has_passing_gate = not has_unterminated_mutation and any(
                verification.get("result") == "passed"
                and isinstance((criterion := verification.get("criterion")), str)
                and criterion_matches(criterion)
                and int(verification.get("_line", 0)) > last_mutating_result_line
                for verification in verifications
            )
            if not has_passing_gate:
                issues.append(
                    "run closed as passed without a passing "
                    f"'{gate_name}' verification after the last mutating execution"
                )

    for index, verification in enumerate(verifications):
        criterion = verification.get("criterion")
        if not isinstance(criterion, str):
            continue
        known_gate = criterion.startswith(GATE_VERIFICATION_PREFIXES)
        if criterion.startswith("gate-") and not known_gate:
            issues.append(f"unknown gate criterion: {criterion}")
        if verification.get("result") != "failed" or not known_gate:
            continue
        has_passing_recheck = any(
            later.get("criterion") == criterion and later.get("result") == "passed"
            for later in verifications[index + 1 :]
        )
        if not has_passing_recheck:
            issues.append(
                f"failed gate verification '{verification.get('id')}' "
                "has no subsequent passing recheck"
            )


# forge: modified from upstream — accept the opt-in Level B gate profile
def validate_run(run_dir: Path, *, gates: bool = False) -> dict[str, object]:
    warnings: list[str] = []
    non_passing: list[dict[str, object]] = []
    try:
        run_dir = run_dir.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        payload: dict[str, object] = {
            "ok": False,
            "issues": [f"invalid run directory: {exc}"],
            "warnings": warnings,
            "non_passing_verifications": non_passing,
        }
        # forge: modified from upstream — identify gated validation on early failures
        if gates:
            payload["profile"] = "gates"
        return payload
    records, issues = read_journal(run_dir / "journal.jsonl")

    known_records: list[dict[str, object]] = []
    for index, record in enumerate(records):
        kind = record.get("type")
        if not isinstance(kind, str) or kind not in JOURNAL_ENTRY_TYPES:
            issues.append(f"{record_line(record)}: unknown journal entry type: {kind!r}")
        else:
            known_records.append(record)
            try:
                _validate_citation_targets(record, records[:index])
            except CoordinationRefusal as exc:
                issues.append(f"{record_line(record)}: {exc}")

    starts = [record for record in known_records if record.get("type") == "run_started"]
    closures = [record for record in known_records if record.get("type") == "run_closed"]
    if len(starts) != 1:
        issues.append(f"journal must contain exactly one run_started entry; found {len(starts)}")
    elif records and records[0] is not starts[0]:
        issues.append("run_started must be the first journal entry")
    if len(closures) > 1:
        issues.append(f"journal may contain at most one run_closed entry; found {len(closures)}")
    if closures and records and records[-1] is not closures[-1]:
        issues.append("run_closed must be the final journal entry")
    for closure in closures:
        judgment = closure.get("judgment")
        if not isinstance(judgment, str) or judgment not in {"passed", "blocked"}:
            issues.append(f"{record_line(closure)}: run_closed judgment must be passed or blocked")

    tasks: dict[str, dict[str, object]] = {}
    executions: dict[tuple[str, str], dict[str, object]] = {}
    execution_results: dict[tuple[str, str], dict[str, object]] = {}
    seen_ids: dict[str, set[str]] = {"verification": set(), "decision": set()}

    for record in known_records:
        kind = record.get("type")
        if kind in seen_ids:
            record_id = record.get("id")
            if isinstance(record_id, str) and record_id:
                if record_id in seen_ids[kind]:
                    issues.append(f"{record_line(record)}: duplicate {kind} id {record_id}")
                seen_ids[kind].add(record_id)
        if kind == "task":
            task_id = record.get("id")
            if isinstance(task_id, str) and task_id:
                tasks[task_id] = record
            else:
                issues.append(f"{record_line(record)}: task must have a non-empty id")
        elif kind == "execution":
            key = execution_key(record)
            if key is None:
                issues.append(f"{record_line(record)}: execution must identify agent and execution")
            elif key in executions:
                issues.append(
                    f"{record_line(record)}: duplicate execution {display_execution(key)}"
                )
            else:
                executions[key] = record
            check_declared_file(run_dir, record, "prompt", issues)
            check_declared_file(run_dir, record, "events", issues)
        elif kind == "execution_result":
            status = record.get("status")
            if not isinstance(status, str) or status not in TERMINAL_EXECUTION_STATUSES:
                issues.append(
                    f"{record_line(record)}: execution_result status is not terminal: {status}"
                )
            key = execution_key(record)
            if key is None:
                issues.append(
                    f"{record_line(record)}: execution_result must identify agent and execution"
                )
            elif key in execution_results:
                issues.append(
                    f"{record_line(record)}: duplicate execution_result for "
                    f"{display_execution(key)}"
                )
            else:
                execution_results[key] = record
        elif kind == "verification":
            result = record.get("result")
            if not isinstance(result, str) or result not in VERIFICATION_RESULTS:
                issues.append(
                    f"{record_line(record)}: verification result is not recognized: {result}"
                )
            elif result != "passed":
                non_passing.append(
                    {
                        key: record[key]
                        for key in (
                            "id",
                            "task",
                            "criterion",
                            "result",
                            "check",
                            "observation",
                        )
                        if key in record
                    }
                )
            evidence = record.get("evidence", [])
            if not isinstance(evidence, list):
                issues.append(f"{record_line(record)}: evidence must be a list of file paths")
            else:
                for index, value in enumerate(evidence):
                    if not isinstance(value, str) or not value:
                        issues.append(
                            f"{record_line(record)}: evidence[{index}] must name a file: {value!r}"
                        )
                    elif not declared_file_exists(run_dir, value):
                        issues.append(
                            f"{record_line(record)}: referenced evidence[{index}] "
                            f"file does not exist: {value}"
                        )

    for task_id, task in tasks.items():
        status = task.get("status")
        if not isinstance(status, str) or status not in TERMINAL_TASK_STATUSES:
            issues.append(f"task {task_id} is not terminal; latest status is {status!r}")

    for record in known_records:
        kind = record.get("type")
        task_id = record.get("task")
        if kind in {"execution", "execution_result", "verification", "decision"}:
            if "task" in record and (not isinstance(task_id, str) or not task_id):
                issues.append(f"{record_line(record)}: {kind} task reference must be a string")
            elif isinstance(task_id, str) and task_id not in tasks:
                issues.append(f"{record_line(record)}: {kind} references unknown task {task_id}")

    for key, execution in executions.items():
        result = execution_results.get(key)
        if result is None:
            issues.append(f"execution {display_execution(key)} has no terminal execution_result")
            continue
        task_id = execution.get("task")
        result_task = result.get("task")
        if isinstance(task_id, str) and isinstance(result_task, str) and result_task != task_id:
            issues.append(
                f"{record_line(result)}: execution_result task {result_task!r} "
                f"does not match execution task {task_id!r}"
            )
        if int(execution.get("_line", 0)) >= int(result.get("_line", 0)):
            issues.append(
                f"{record_line(result)}: execution {display_execution(key)} "
                "must be recorded before execution_result"
            )
        handoff_values = [
            source.get("handoff") for source in (execution, result) if "handoff" in source
        ]
        handoff_ok = bool(handoff_values) and all(
            declared_file_exists(run_dir, value, nonempty=True) for value in handoff_values
        )
        if not handoff_ok:
            message = f"execution {display_execution(key)} handoff is missing or empty"
            (issues if result.get("status") == "complete" else warnings).append(message)

    for key, result in execution_results.items():
        if key not in executions:
            issues.append(
                f"{record_line(result)}: execution_result references unknown execution "
                f"{display_execution(key)}"
            )

    # forge: modified from upstream — layer gate issues after all baseline checks
    if gates:
        check_gate_profile(known_records, issues)

    payload = {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "non_passing_verifications": non_passing,
    }
    # forge: modified from upstream — expose the active profile only for --gates
    if gates:
        payload["profile"] = "gates"
    return payload
