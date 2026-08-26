from __future__ import annotations

import ctypes
import datetime as dt
import errno
import fcntl
import json
import os
import re
import socket
import stat
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

# forge: modified from upstream — support declared pre-cutover journal dialect compatibility
LEGACY_COMPATIBILITY_DECLARATION_ID = "journal-dialect-compat"
LEGACY_COMPATIBILITY_RESOLUTION_PREFIX = "legacy-dialect-compat: "
LEGACY_COMPATIBILITY_LEGS = frozenset(
    {
        "observation",
        "verification-pass",
        "string-evidence",
        "execution-result-status",
        "execution-task-mismatch",
        "missing-execution-file",
        "duplicate-verification-id",
        "missing-execution-result",
        "empty-events",
        "failed-gate-recheck",
    }
)
LEGACY_EXECUTION_STATUS_MAP = {
    "handoff-ready": "complete",
    "pass": "complete",
    "block": "blocked",
}


# forge: modified from upstream — refuse out-of-root citations before journal writes
CITATION_ROOT_ENFORCEMENT_LEGS = frozenset({"append-time"})
CITATION_ROOT_DIRECT_FIELDS = {
    "execution": ("prompt", "events", "handoff"),
    "execution_result": ("handoff",),
}


# forge: modified from upstream — FR-018 operator-directed closed-run dispensation
CLOSED_RUN_DISPENSATION_LEGS = frozenset({"closed-legacy-compat"})
CLOSED_LEGACY_COMPAT_REFUSAL = (
    "forge: closed-legacy-compat refused — journal has no run_closed entry"
)


# forge: modified from upstream — enforce D13 journal ownership and run-scope admission
REGISTRY_UNAVAILABLE = "forge: new run refused — run registry unavailable"
REGISTRY_LOCK_UNAVAILABLE = (
    "forge: run coordination refused — run registry lock unavailable"
)
REGISTRY_UPDATE_FAILED = "forge: run coordination refused — run registry update failed"
JOURNAL_ROLLBACK_FAILED = (
    "forge: run coordination refused — journal rollback failed after run registry "
    "update failure"
)
INVALID_JOURNAL_RECORD = "forge: journal append refused — invalid journal record"
SESSION_PID_INVALID = (
    "forge: FORGE_SESSION_PID must be exported as a positive base-10 integer"
)
SESSION_PID_NOT_LIVE = (
    "forge: FORGE_SESSION_PID does not name a live same-host session owner"
)
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
EXECUTION_ID_PATTERN = re.compile(r"execution-[0-9]{2}")
GIT_OBJECT_ID_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
READMISSION_ID_PATTERN = re.compile(r"forge-scope-readmission-[0-9a-f]{32}")

# forge: modified from upstream — independently disableable revision-8 controls
NEW_WRITE_VALIDATION_CONTROLS = frozenset({"schema"})
ORPHAN_CLASSIFICATION_CONTROLS = frozenset({"classify"})
SUCCESSOR_DAG_CONTROLS = frozenset({"transfer", "release"})
_MISSING = object()


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
class FileObservation:
    device: int
    inode: int
    mode: int


@dataclass(frozen=True)
class ExactFile:
    payload: bytes
    observation: FileObservation


@dataclass(frozen=True)
class NamespaceMutationOutcome:
    phase: str
    failure: BaseException | None


@dataclass(frozen=True)
class RunState:
    run_id: str
    run_dir: Path
    disposition: str
    scope: tuple[str, ...]
    opening_scope: tuple[str, ...]
    successor_of: str | None = None
    pre_coordination: bool = False
    records: tuple[dict[str, object], ...] = ()
    was_retired: bool = False
    close_judgment: str | None = None
    legacy: bool = False
    directory_observation: FileObservation | None = None
    journal_observation: FileObservation | None = None


@dataclass(frozen=True)
class OwnerClassification:
    disposition: str
    observed: bytes | None
    owner: Owner | None = None
    device: int | None = None
    inode: int | None = None
    mode: int | None = None


@dataclass(frozen=True)
class OwnerObservation:
    observed: bytes
    device: int
    inode: int
    mode: int


@dataclass(frozen=True)
class OwnerTakeover:
    prior: OwnerClassification
    candidate_observation: FileObservation | None
    candidate_payload: bytes | None
    backup_name: str | None


@dataclass(frozen=True)
class PlaceholderObservation:
    path: Path
    device: int
    inode: int
    mode: int


@dataclass(frozen=True)
class RegistrySnapshot:
    exists: bool
    raw: bytes | None
    open_runs: dict[str, tuple[str, ...]]
    observation: FileObservation | None = None


@dataclass(frozen=True)
class RegistryLock:
    directory: Path
    directory_descriptor: int
    directory_observation: FileObservation
    lock_descriptor: int
    lock_observation: FileObservation


@dataclass(frozen=True)
class NewRunClaim:
    run_id: str
    runs_root_observation: FileObservation
    directory_observation: FileObservation
    files: tuple[tuple[str, FileObservation, bytes], ...]


@dataclass(frozen=True)
class RegistryPublication:
    prior: RegistrySnapshot
    candidate_observation: FileObservation
    candidate_payload: bytes
    backup_name: str | None


class RegistryRestorationRefusal(CoordinationRefusal):
    """Registry publication could not be restored; journal rollback is unsafe."""


class OwnerRestorationRefusal(CoordinationRefusal):
    """Owner takeover could not be restored without overwriting foreign state."""


class NamespaceMutationAmbiguity(RuntimeError):
    """An atomic namespace syscall left neither its exact pre nor post state."""


@dataclass(frozen=True)
class ScopeReservation:
    run_id: str
    disposition: str
    scope: tuple[str, ...]
    lineage: frozenset[str]


@dataclass(frozen=True)
class CoordinationView:
    registry: RegistrySnapshot
    states: dict[str, RunState]
    open_runs: dict[str, tuple[str, ...]]
    reservations: dict[str, ScopeReservation]
    placeholders: dict[str, PlaceholderObservation]
    owners: dict[str, OwnerObservation]
    runs_root_observation: FileObservation | None


@dataclass(frozen=True)
class LockedJournal:
    stream: object
    run_descriptor: int
    state: RunState

    def fileno(self) -> int:
        return self.stream.fileno()  # type: ignore[attr-defined,no-any-return]


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
        raise CoordinationRefusal(SESSION_PID_INVALID)
    try:
        pid = int(raw_pid)
    except (OverflowError, ValueError) as exc:
        raise CoordinationRefusal(SESSION_PID_NOT_LIVE) from exc
    if _pid_is_live(pid) is not True:
        raise CoordinationRefusal(SESSION_PID_NOT_LIVE)
    try:
        host = socket.gethostname()
    except OSError as exc:
        raise CoordinationRefusal(SESSION_PID_NOT_LIVE) from exc
    if not _safe_diagnostic_text(host):
        raise CoordinationRefusal(SESSION_PID_NOT_LIVE)
    return Owner(pid=pid, host=host, started_at=_utc_now())


def _owner_bytes(owner: Owner) -> bytes:
    return (
        f"pid: {owner.pid}\nhost: {owner.host}\nstarted_at: {owner.started_at}\n"
    ).encode("utf-8")


def _parse_owner_bytes(raw: bytes) -> Owner | None:
    match = OWNER_PATTERN.fullmatch(raw)
    if match is None:
        return None
    try:
        host = match.group(2).decode("utf-8")
        started_at = match.group(3).decode("ascii")
        owner = Owner(pid=int(match.group(1)), host=host, started_at=started_at)
    except (UnicodeError, ValueError):
        return None
    if not _safe_diagnostic_text(owner.host) or not _valid_utc(owner.started_at):
        return None
    return owner


def _parse_owner(path: Path) -> Owner | None:
    try:
        return _parse_owner_bytes(path.read_bytes())
    except OSError:
        return None


def _safe_diagnostic_text(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return True


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
    # FR-191: the directive block ends at the first line that is not a directive;
    # that line and everything after it is free prose and is ignored. A strict
    # whole-block grammar would make one badly-shaped appended entry permanently
    # fatal over an append-only record, which is the fail-always condition the
    # FR-173 audit rejects. This parse matches audit-commitments.py exactly, so a
    # correction accepted at append time is the same one the audit applies.
    directives: list[str] = []
    for line in suffix[1:].splitlines():
        if (
            CITATION_DECISION_CORRECTION.fullmatch(line) is None
            and CITATION_VERIFICATION_CORRECTION.fullmatch(line) is None
        ):
            break
        directives.append(line)
    if not directives:
        raise CoordinationRefusal(
            "forge: journal append refused — invalid citation correction"
        )
    return tuple(directives)


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


def _record_citations(record: dict[str, object]) -> Iterator[tuple[str, str]]:
    """Yield the exact FR-017 citation inventory and operator-facing field names."""

    kind = record.get("type")
    for field in CITATION_ROOT_DIRECT_FIELDS.get(str(kind), ()):
        value = record.get(field)
        if isinstance(value, str) and value:
            yield f"{kind}.{field}", value
    if kind == "verification":
        evidence = record.get("evidence")
        if isinstance(evidence, list):
            for index, value in enumerate(evidence):
                if isinstance(value, str) and value:
                    yield f"verification.evidence[{index}]", value
        observation = record.get("observation")
        if isinstance(observation, str):
            for token in path_tokens(observation, context="observation"):
                yield f"verification.observation token {token}", token
    elif kind == "decision":
        basis = record.get("basis")
        if isinstance(basis, list):
            for index, value in enumerate(basis):
                if not isinstance(value, str):
                    continue
                for token in path_tokens(value, context="basis"):
                    yield f"decision.basis[{index}]", token


def _path_uses_symlink(root: Path, relative: Path) -> bool:
    """Return whether an existing component below ``root`` is a symlink."""

    candidate = root
    for part in relative.parts:
        if part in {"", "."}:
            continue
        candidate = candidate.parent if part == ".." else candidate / part
        try:
            if candidate.is_symlink():
                return True
        except OSError:
            return False
    return False


def _citation_is_contained(repo_root: Path, run_dir: Path, citation: str) -> bool:
    """Apply ordered resolve-then-contain semantics without requiring existence."""

    try:
        relative = Path(citation)
        if relative.is_absolute():
            return False
        repository = repo_root.expanduser().resolve(strict=True)
        run = run_dir.expanduser().resolve(strict=False)
        roots = (run, repository) if run != repository else (run,)
        fallback = False
        anchored = False
        for root in roots:
            candidate = root / relative
            resolved = candidate.resolve(strict=False)
            try:
                resolved.relative_to(root)
                contained = True
            except ValueError:
                contained = False

            # Append time proves containment only. Existence remains the later
            # validator/audit concern: a missing in-root target is accepted.
            # Existing targets or symlink components only select the same
            # root-specific resolution that the audit will inspect later.
            rooted = candidate.exists() or candidate.is_symlink()
            symlinked = _path_uses_symlink(root, relative)
            if rooted or symlinked:
                anchored = True
                if contained:
                    return True
            fallback = fallback or contained
        return fallback if not anchored else False
    except (OSError, RuntimeError, ValueError):
        return False


def _validate_append_citations(
    repo_root: Path | None,
    run_dir: Path,
    record: object,
    *,
    state_root: Path | None = None,
) -> None:
    """Refuse FR-017 citation escapes before any coordination artifact is written."""

    if "append-time" not in CITATION_ROOT_ENFORCEMENT_LEGS or not isinstance(record, dict):
        return
    citations = tuple(_record_citations(record))
    if not citations:
        return
    if repo_root is None:
        if state_root is None:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        repo_root = _recorded_repository_root(run_dir, state_root)
    for field, citation in citations:
        if not _safe_diagnostic_text(citation):
            raise CoordinationRefusal(INVALID_JOURNAL_RECORD)
        if not _citation_is_contained(repo_root, run_dir, citation):
            raise CoordinationRefusal(
                "forge: journal append refused — record cites path outside run or "
                f"repository: {field}: {citation}"
            )


def _recorded_repository_root(
    run_dir: Path,
    state_root: Path,
    *,
    records: tuple[dict[str, object], ...] | None = None,
) -> Path:
    """Resolve a run's repository without letting journal data widen its authority."""

    if records is None:
        records = tuple(_read_raw_records(run_dir / "journal.jsonl"))
    if not records or records[0].get("type") != "run_started":
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    opening = records[0]
    recorded = opening.get("repo")
    if recorded is None:
        # Pre-coordination journals did not consistently record their worktree.
        # Their common Git root is the only repository authority still provable.
        if "scope" not in opening:
            return state_root
        raise CoordinationRefusal(
            f"forge: journal append refused — recorded repository unavailable for run "
            f"{run_dir.name}"
        )
    refusal = CoordinationRefusal(
        f"forge: journal append refused — recorded repository unavailable for run "
        f"{run_dir.name}"
    )
    if not isinstance(recorded, str) or not recorded or not Path(recorded).is_absolute():
        raise refusal
    try:
        repository, recorded_state_root = _resolve_repository(
            Path(recorded), "journal append"
        )
    except CoordinationRefusal as exc:
        raise refusal from exc
    if recorded_state_root != state_root:
        raise refusal
    return repository


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
        json.dumps(
            record,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _journal_payload(record: dict[str, object]) -> bytes:
    """Serialize a candidate before any owner or coordination byte is mutated."""

    try:
        return _journal_line(record)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CoordinationRefusal(INVALID_JOURNAL_RECORD) from exc


def _resolve_repository(repo: Path, operation: str) -> tuple[Path, Path]:
    try:
        repository = repo.expanduser().resolve(strict=True)
        if not repository.is_dir():
            raise ValueError
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
        return repository, common.parent
    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise CoordinationRefusal(
            f"forge: {operation} refused — repository unavailable"
        ) from exc


def _resolve_state_root(repo: Path, operation: str = "new run") -> Path:
    return _resolve_repository(repo, operation)[1]


def _validate_registry_lock(state_root: Path, locked: RegistryLock) -> None:
    try:
        directory_path = state_root / ".forge/tmp"
        directory_path_stat = os.lstat(directory_path)
        directory_open_stat = os.fstat(locked.directory_descriptor)
        lock_path_stat = os.stat(
            "run-registry.lock",
            dir_fd=locked.directory_descriptor,
            follow_symlinks=False,
        )
        lock_open_stat = os.fstat(locked.lock_descriptor)
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_LOCK_UNAVAILABLE) from exc
    if (
        directory_path != locked.directory
        or not _matches_observation(
            directory_path_stat, locked.directory_observation
        )
        or not _matches_observation(
            directory_open_stat, locked.directory_observation
        )
        or not _matches_observation(lock_path_stat, locked.lock_observation)
        or not _matches_observation(lock_open_stat, locked.lock_observation)
        or not stat.S_ISDIR(directory_open_stat.st_mode)
        or not stat.S_ISREG(lock_open_stat.st_mode)
        or stat.S_ISLNK(lock_path_stat.st_mode)
    ):
        raise CoordinationRefusal(REGISTRY_LOCK_UNAVAILABLE)


@contextmanager
def _registry_lock(state_root: Path) -> Iterator[RegistryLock]:
    lock_path = state_root / ".forge/tmp/run-registry.lock"
    directory_descriptor: int | None = None
    lock_descriptor: int | None = None
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        directory_descriptor, directory_observation = _open_bound_directory(
            lock_path.parent
        )
        try:
            before = os.stat(
                lock_path.name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            before = None
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        lock_descriptor = os.open(
            lock_path.name, flags, 0o600, dir_fd=directory_descriptor
        )
        opened = os.fstat(lock_descriptor)
        rebound = os.stat(
            lock_path.name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        lock_observation = _file_observation(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(rebound.st_mode)
            or not _matches_observation(rebound, lock_observation)
            or (
                before is not None
                and not _matches_observation(before, lock_observation)
            )
        ):
            raise OSError(errno.EAGAIN, "registry lock identity changed")
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        locked = RegistryLock(
            lock_path.parent,
            directory_descriptor,
            directory_observation,
            lock_descriptor,
            lock_observation,
        )
        _validate_registry_lock(state_root, locked)
    except CoordinationRefusal:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)
        raise
    except OSError as exc:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)
        raise CoordinationRefusal(REGISTRY_LOCK_UNAVAILABLE) from exc
    try:
        yield locked
    finally:
        assert lock_descriptor is not None
        assert directory_descriptor is not None
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(lock_descriptor)
            os.close(directory_descriptor)


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
    if any(ord(character) < 32 or ord(character) == 127 for character in run_id):
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


# In-memory sentinel for a pre-coordination run's repository-wide scope.
# canonical_scope refuses "**" for admitted runs, so the sentinel can never
# collide with a real scope — and it is not a validatable pathspec, so it
# must never reach the persisted registry.
PRE_COORDINATION_SCOPE = ("**",)


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


# forge: modified from upstream — FR-019 validates proposed writes, never history
def _invalid_record_field(kind: str, field: str, requirement: str) -> None:
    raise CoordinationRefusal(
        f"{INVALID_JOURNAL_RECORD}: {kind}.{field} {requirement}"
    )


def _validate_record_envelope(record: object) -> dict[str, object]:
    if (
        not isinstance(record, dict)
        or not isinstance(record.get("type"), str)
        or record.get("type") not in JOURNAL_ENTRY_TYPES
    ):
        raise CoordinationRefusal(INVALID_JOURNAL_RECORD)
    return record


def _required_string(
    record: dict[str, object], kind: str, field: str, *, nonempty: bool = True
) -> str:
    if field not in record:
        _invalid_record_field(kind, field, "is required")
    value = record.get(field)
    if not isinstance(value, str):
        _invalid_record_field(kind, field, "must be a string")
    assert isinstance(value, str)
    if nonempty and not value:
        _invalid_record_field(kind, field, "must be nonempty")
    return value


def _string_array(
    record: dict[str, object],
    kind: str,
    field: str,
    *,
    required: bool = True,
    nonempty: bool = False,
) -> list[str] | None:
    if field not in record:
        if required:
            _invalid_record_field(kind, field, "is required")
        return None
    value = record.get(field)
    if not isinstance(value, list):
        _invalid_record_field(kind, field, "must be an array")
    assert isinstance(value, list)
    if nonempty and not value:
        _invalid_record_field(kind, field, "must be nonempty")
    for index, member in enumerate(value):
        if not isinstance(member, str) or not member:
            _invalid_record_field(
                kind, f"{field}[{index}]", "must be a nonempty string"
            )
    return value  # type: ignore[return-value]


def _task_inherited_field(
    record: dict[str, object],
    prior_records: tuple[dict[str, object], ...],
    field: str,
) -> object:
    if field in record:
        return record[field]
    if record.get("status") not in TERMINAL_TASK_STATUSES:
        return _MISSING
    task_id = record.get("id")
    for prior in reversed(prior_records):
        if prior.get("type") == "task" and prior.get("id") == task_id:
            return prior[field] if field in prior else _MISSING
    return _MISSING


def _validate_proposed_record(
    record: object,
    *,
    run_id: str,
    repo_root: Path,
    scope: tuple[str, ...],
    prior_records: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    """Validate one FR-019 new-write candidate without mutating coordination state."""

    candidate = _validate_record_envelope(record)
    if "schema" not in NEW_WRITE_VALIDATION_CONTROLS:
        return candidate

    kind = str(candidate["type"])
    if "recorded_at" not in candidate:
        _invalid_record_field(kind, "recorded_at", "is required")
    recorded_at = candidate.get("recorded_at")
    if not isinstance(recorded_at, str) or not _valid_utc(recorded_at):
        _invalid_record_field(
            kind,
            "recorded_at",
            "must be a valid UTC RFC-3339 timestamp ending in Z",
        )
    if "run_id" in candidate:
        candidate_run_id = candidate.get("run_id")
        if not _valid_run_id(candidate_run_id):
            _invalid_record_field(kind, "run_id", "must be a valid run ID")
        if candidate_run_id != run_id:
            _invalid_record_field(kind, "run_id", "must match target run")

    if kind == "run_started":
        if "run_id" not in candidate:
            _invalid_record_field(kind, "run_id", "is required")
        _required_string(candidate, kind, "goal")
        repository = _required_string(candidate, kind, "repo", nonempty=False)
        repository_path = Path(repository)
        if not repository_path.is_absolute():
            _invalid_record_field(kind, "repo", "must be an absolute path")
        try:
            matches_repository = repository_path.resolve(strict=True) == repo_root
        except (OSError, RuntimeError, UnicodeError, ValueError):
            matches_repository = False
        if not matches_repository:
            _invalid_record_field(kind, "repo", "must match target repository")
        head = _required_string(candidate, kind, "repo_head", nonempty=False)
        if GIT_OBJECT_ID_PATTERN.fullmatch(head) is None:
            _invalid_record_field(kind, "repo_head", "must be a full Git object ID")
        _string_array(candidate, kind, "repo_status")
        _required_string(candidate, kind, "plugin_ref")
        opening_scope = _string_array(candidate, kind, "scope", nonempty=True)
        assert opening_scope is not None
        if _scope_from_record(opening_scope) is None:
            _invalid_record_field(
                kind, "scope", "must be a canonical nonempty admitted scope"
            )
        if "successor_of" in candidate:
            successor_of = candidate.get("successor_of")
            if not _valid_run_id(successor_of):
                _invalid_record_field(kind, "successor_of", "must be a valid run ID")
        return candidate

    if kind == "task":
        _required_string(candidate, kind, "id")
        status = _required_string(candidate, kind, "status", nonempty=False)
        if status not in {"active", "complete", "blocked", "failed"}:
            _invalid_record_field(
                kind, "status", "must be one of active, complete, blocked, failed"
            )
        effective_goal = _task_inherited_field(candidate, prior_records, "goal")
        if effective_goal is _MISSING:
            _invalid_record_field(kind, "goal", "is required")
        if not isinstance(effective_goal, str):
            _invalid_record_field(kind, "goal", "must be a string")
        if not effective_goal:
            _invalid_record_field(kind, "goal", "must be nonempty")
        for field in ("acceptance", "files"):
            effective = _task_inherited_field(candidate, prior_records, field)
            if effective is _MISSING:
                _invalid_record_field(kind, field, "is required")
            if not isinstance(effective, list):
                _invalid_record_field(kind, field, "must be an array")
            if not effective:
                _invalid_record_field(kind, field, "must be nonempty")
            for index, member in enumerate(effective):
                if not isinstance(member, str) or not member:
                    _invalid_record_field(
                        kind, f"{field}[{index}]", "must be a nonempty string"
                    )
                if field == "files":
                    if not _valid_scope_item(member):
                        _invalid_record_field(
                            kind,
                            f"files[{index}]",
                            "must be a positive repository-relative Git pathspec",
                        )
                    if not any(pathspec_contained(member, admitted) for admitted in scope):
                        _invalid_record_field(
                            kind, f"files[{index}]", "must be contained by admitted scope"
                        )
        return candidate

    if kind == "execution":
        for field in ("agent", "task", "provider", "role", "mode", "model", "effort"):
            _required_string(candidate, kind, field)
        execution = _required_string(candidate, kind, "execution", nonempty=False)
        if EXECUTION_ID_PATTERN.fullmatch(execution) is None:
            _invalid_record_field(kind, "execution", "must match execution-NN")
        worktree = _required_string(candidate, kind, "worktree", nonempty=False)
        if not Path(worktree).is_absolute():
            _invalid_record_field(kind, "worktree", "must be an absolute path")
        head = _required_string(candidate, kind, "head", nonempty=False)
        if GIT_OBJECT_ID_PATTERN.fullmatch(head) is None:
            _invalid_record_field(kind, "head", "must be a full Git object ID")
        for field in ("prompt", "handoff", "event_source"):
            _required_string(candidate, kind, field)
        if "events" in candidate:
            events = candidate.get("events")
            if not isinstance(events, str):
                _invalid_record_field(kind, "events", "must be a string")
            if candidate.get("event_source") == "exec" and not events:
                _invalid_record_field(kind, "events", "must be nonempty")
        elif candidate.get("event_source") == "exec":
            _invalid_record_field(kind, "events", "is required")
        return candidate

    if kind == "execution_result":
        for field in ("agent", "task", "summary"):
            _required_string(candidate, kind, field)
        execution = _required_string(candidate, kind, "execution", nonempty=False)
        if EXECUTION_ID_PATTERN.fullmatch(execution) is None:
            _invalid_record_field(kind, "execution", "must match execution-NN")
        status = _required_string(candidate, kind, "status", nonempty=False)
        if status not in {"complete", "blocked", "failed"}:
            _invalid_record_field(
                kind, "status", "must be one of complete, blocked, failed"
            )
        _string_array(candidate, kind, "files_changed")
        _string_array(candidate, kind, "caveats")
        if "handoff" in candidate:
            handoff = candidate.get("handoff")
            if not isinstance(handoff, str):
                _invalid_record_field(kind, "handoff", "must be a string")
            if status == "complete" and not handoff:
                _invalid_record_field(kind, "handoff", "must be nonempty")
        elif status == "complete":
            _invalid_record_field(kind, "handoff", "is required")
        return candidate

    if kind == "verification":
        for field in ("id", "task", "criterion", "method", "check", "observation"):
            _required_string(candidate, kind, field)
        result = _required_string(candidate, kind, "result", nonempty=False)
        if result not in {"passed", "failed", "inconclusive", "skipped"}:
            _invalid_record_field(
                kind,
                "result",
                "must be one of passed, failed, inconclusive, skipped",
            )
        _string_array(candidate, kind, "evidence", required=False)
        return candidate

    if kind == "decision":
        decision_id = _required_string(candidate, kind, "id")
        resolution = _required_string(candidate, kind, "resolution")
        for field in ("task", "finding", "outcome", "risk"):
            if field in candidate and not isinstance(candidate.get(field), str):
                _invalid_record_field(kind, field, "must be a string")
        _string_array(candidate, kind, "basis", required=False)
        if decision_id == "forge-run-retired" or resolution == RETIREMENT_RESOLUTION:
            if decision_id != "forge-run-retired":
                _invalid_record_field(kind, "id", "must be forge-run-retired")
            if resolution != RETIREMENT_RESOLUTION:
                _invalid_record_field(
                    kind, "resolution", f"must be {RETIREMENT_RESOLUTION}"
                )
        if resolution == READMISSION_RESOLUTION or decision_id.startswith(
            "forge-scope-readmission-"
        ):
            if READMISSION_ID_PATTERN.fullmatch(decision_id) is None:
                _invalid_record_field(
                    kind, "id", "must match forge-scope-readmission-<uuid-hex>"
                )
            if resolution != READMISSION_RESOLUTION:
                _invalid_record_field(
                    kind, "resolution", f"must be {READMISSION_RESOLUTION}"
                )
            admitted = _string_array(candidate, kind, "scope", nonempty=True)
            assert admitted is not None
            if _scope_from_record(admitted) is None:
                _invalid_record_field(
                    kind, "scope", "must be a canonical nonempty admitted scope"
                )
        if decision_id == LEGACY_COMPATIBILITY_DECLARATION_ID:
            if (
                not resolution.startswith(LEGACY_COMPATIBILITY_RESOLUTION_PREFIX)
                or "\n" in resolution
                or "\r" in resolution
                or not resolution[len(LEGACY_COMPATIBILITY_RESOLUTION_PREFIX) :].strip()
            ):
                _invalid_record_field(
                    kind, "resolution", "must match legacy-dialect-compat grammar"
                )
        return candidate

    assert kind == "run_closed"
    judgment = _required_string(candidate, kind, "judgment", nonempty=False)
    if judgment not in {"passed", "blocked"}:
        _invalid_record_field(kind, "judgment", "must be one of passed, blocked")
    _required_string(candidate, kind, "summary")
    if "validation" not in candidate:
        _invalid_record_field(kind, "validation", "is required")
    validation = candidate.get("validation")
    if not isinstance(validation, dict):
        _invalid_record_field(kind, "validation", "must be an object")
    assert isinstance(validation, dict)
    if "ok" not in validation:
        _invalid_record_field(kind, "validation.ok", "is required")
    if not isinstance(validation.get("ok"), bool):
        _invalid_record_field(kind, "validation.ok", "must be Boolean")
    for field in ("issues", "warnings", "non_passing_verifications"):
        path = f"validation.{field}"
        if field not in validation:
            _invalid_record_field(kind, path, "is required")
        values = validation.get(field)
        if not isinstance(values, list):
            _invalid_record_field(kind, path, "must be an array")
        if field == "non_passing_verifications":
            continue
        for index, member in enumerate(values):
            if not isinstance(member, str) or not member:
                _invalid_record_field(
                    kind, f"{path}[{index}]", "must be a nonempty string"
                )
    if "profile" not in validation:
        _invalid_record_field(kind, "validation.profile", "is required")
    if validation.get("profile") != "gates":
        _invalid_record_field(kind, "validation.profile", "must be exactly gates")
    _string_array(candidate, kind, "risks")
    _string_array(candidate, kind, "follow_ups")
    return candidate


def _reserved_lifecycle_decision(record: dict[str, object]) -> bool:
    if record.get("type") != "decision":
        return False
    decision_id = record.get("id")
    resolution = record.get("resolution")
    return bool(
        decision_id == "forge-run-retired"
        or resolution == RETIREMENT_RESOLUTION
        or (
            isinstance(decision_id, str)
            and decision_id.startswith("forge-scope-readmission-")
        )
        or resolution == READMISSION_RESOLUTION
    )


def _ordinary_append_requires_lifecycle_command(record: dict[str, object]) -> bool:
    return record.get("type") in {"run_started", "run_closed"} or _reserved_lifecycle_decision(
        record
    )


def _file_observation(value: os.stat_result) -> FileObservation:
    return FileObservation(value.st_dev, value.st_ino, value.st_mode)


def _matches_observation(
    value: os.stat_result, observation: FileObservation
) -> bool:
    return _file_observation(value) == observation


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )


def _regular_open_flags(*, writable: bool = False) -> int:
    flags = os.O_RDWR | os.O_APPEND if writable else os.O_RDONLY
    return flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


def _read_descriptor(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _parse_raw_records(raw: bytes) -> list[dict[str, object]]:
    if not raw or not raw.endswith(b"\n"):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    records: list[dict[str, object]] = []
    try:
        for line in raw.splitlines():
            value = json.loads(line.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError
            records.append(value)
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    return records


def _open_bound_directory(path: Path) -> tuple[int, FileObservation]:
    before = os.lstat(path)
    if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise OSError(errno.EINVAL, "not a real directory")
    descriptor = os.open(path, _directory_open_flags())
    try:
        opened = os.fstat(descriptor)
        rebound = os.lstat(path)
        observation = _file_observation(before)
        if (
            not _matches_observation(opened, observation)
            or not _matches_observation(rebound, observation)
            or not stat.S_ISDIR(opened.st_mode)
            or stat.S_ISLNK(opened.st_mode)
        ):
            raise OSError(errno.EAGAIN, "directory identity changed")
        return descriptor, observation
    except BaseException:
        os.close(descriptor)
        raise


def _open_bound_child_directory(
    parent_descriptor: int,
    name: str,
    before: os.stat_result,
) -> tuple[int, FileObservation]:
    observation = _file_observation(before)
    if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise OSError(errno.EINVAL, "not a real directory")
    descriptor = os.open(name, _directory_open_flags(), dir_fd=parent_descriptor)
    try:
        opened = os.fstat(descriptor)
        rebound = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            not _matches_observation(opened, observation)
            or not _matches_observation(rebound, observation)
            or not stat.S_ISDIR(opened.st_mode)
            or stat.S_ISLNK(opened.st_mode)
        ):
            raise OSError(errno.EAGAIN, "directory identity changed")
        return descriptor, observation
    except BaseException:
        os.close(descriptor)
        raise


def _read_bound_regular(
    directory_descriptor: int,
    name: str,
    *,
    require_nonempty: bool = False,
) -> tuple[bytes, FileObservation]:
    before = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    observation = _file_observation(before)
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or not _readable_mode(before.st_mode)
        or (require_nonempty and before.st_size <= 0)
    ):
        raise OSError(errno.EINVAL, "not a readable regular file")
    descriptor = os.open(
        name, _regular_open_flags(), dir_fd=directory_descriptor
    )
    try:
        opened = os.fstat(descriptor)
        if not _matches_observation(opened, observation):
            raise OSError(errno.EAGAIN, "file identity changed")
        raw = _read_descriptor(descriptor)
        after = os.fstat(descriptor)
        rebound = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
        if (
            not _matches_observation(after, observation)
            or not _matches_observation(rebound, observation)
            or (require_nonempty and not raw)
        ):
            raise OSError(errno.EAGAIN, "file identity changed")
        return raw, observation
    finally:
        os.close(descriptor)


def _read_raw_records(journal: Path) -> list[dict[str, object]]:
    try:
        run_descriptor, directory_observation = _open_bound_directory(journal.parent)
        try:
            raw, _ = _read_bound_regular(
                run_descriptor, journal.name, require_nonempty=True
            )
            rebound = os.lstat(journal.parent)
            if not _matches_observation(rebound, directory_observation):
                raise OSError(errno.EAGAIN, "journal directory identity changed")
        finally:
            os.close(run_descriptor)
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    return _parse_raw_records(raw)


def _scan_run(
    run_dir: Path,
    *,
    raw: bytes | None = None,
    directory_observation: FileObservation | None = None,
    journal_observation: FileObservation | None = None,
) -> RunState:
    """Read historical lifecycle state without applying the FR-019 write schema."""

    run_id = run_dir.name
    if not _valid_run_id(run_id):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    if raw is None:
        run_descriptor: int | None = None
        try:
            run_descriptor, directory_observation = _open_bound_directory(run_dir)
            raw, journal_observation = _read_bound_regular(
                run_descriptor, "journal.jsonl", require_nonempty=True
            )
            rebound = os.lstat(run_dir)
            assert directory_observation is not None
            if not _matches_observation(rebound, directory_observation):
                raise OSError(errno.EAGAIN, "run directory identity changed")
        except OSError as exc:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
        finally:
            if run_descriptor is not None:
                os.close(run_descriptor)
    assert raw is not None
    records = _parse_raw_records(raw)
    starts = [record for record in records if record.get("type") == "run_started"]
    closures = [record for record in records if record.get("type") == "run_closed"]
    if len(starts) != 1 or records[0] is not starts[0]:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    legacy = "run_id" not in starts[0]
    identity = starts[0].get("id") if legacy else starts[0].get("run_id")
    if identity != run_id or len(closures) > 1:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    close_position: int | None = None
    if closures:
        close_position = next(
            position for position, record in enumerate(records) if record is closures[0]
        )
        if records[-1] is not closures[0]:
            trailing = records[close_position + 1 :]
            if not legacy or any(
                record.get("type") not in {"decision", "verification"}
                for record in trailing
            ):
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)

    opening_scope = _scope_from_record(starts[0].get("scope"))
    scope = opening_scope
    successor_of = starts[0].get("successor_of")
    if successor_of is not None and not _valid_run_id(successor_of):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    retirement_positions: list[int] = []
    for position, record in enumerate(records[1:], start=1):
        if record.get("type") != "decision":
            continue
        decision_id = record.get("id")
        resolution = record.get("resolution")
        readmission_id = (
            isinstance(decision_id, str)
            and decision_id.startswith("forge-scope-readmission-")
        )
        if readmission_id or resolution == READMISSION_RESOLUTION:
            if (
                not isinstance(decision_id, str)
                or READMISSION_ID_PATTERN.fullmatch(decision_id) is None
                or resolution != READMISSION_RESOLUTION
            ):
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            updated = _scope_from_record(record.get("scope"))
            if updated is None:
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            scope = updated
        retirement_id = decision_id == "forge-run-retired"
        if retirement_id or resolution == RETIREMENT_RESOLUTION:
            if not retirement_id or resolution != RETIREMENT_RESOLUTION:
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            retirement_positions.append(position)
    if len(retirement_positions) > 1:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    if retirement_positions:
        expected_position = (
            close_position - 1 if close_position is not None else len(records) - 1
        )
        if retirement_positions[0] != expected_position:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    was_retired = bool(retirement_positions)
    disposition = "closed" if closures else "retired" if was_retired else "open"
    close_judgment = closures[0].get("judgment") if closures else None
    if closures and not legacy and close_judgment not in {"passed", "blocked"}:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)

    pre_coordination = disposition == "open" and scope is None and "scope" not in starts[0]
    if pre_coordination:
        scope = PRE_COORDINATION_SCOPE
    if disposition != "closed" and scope is None:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    return RunState(
        run_id=run_id,
        run_dir=run_dir,
        disposition=disposition,
        scope=scope or (),
        opening_scope=opening_scope or (),
        successor_of=successor_of if isinstance(successor_of, str) else None,
        pre_coordination=pre_coordination,
        records=tuple(records),
        was_retired=was_retired,
        close_judgment=close_judgment if isinstance(close_judgment, str) else None,
        legacy=legacy,
        directory_observation=directory_observation,
        journal_observation=journal_observation,
    )


def _decode_registry_snapshot(
    raw: bytes, observation: FileObservation
) -> RegistrySnapshot:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    if not isinstance(value, dict) or set(value) != {"open_runs", "schema_version"}:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    if value.get("schema_version") != REGISTRY_SCHEMA_VERSION or not isinstance(
        value.get("open_runs"), list
    ):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    loaded: dict[str, tuple[str, ...]] = {}
    for item in value["open_runs"]:
        if not isinstance(item, dict) or set(item) != {"run_id", "scope"}:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        run_id = item.get("run_id")
        scope = _scope_from_record(item.get("scope"))
        if not _valid_run_id(run_id) or scope is None or run_id in loaded:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        loaded[str(run_id)] = scope
    if raw != _registry_payload(loaded):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    return RegistrySnapshot(True, raw, loaded, observation)


def _read_registry_snapshot(
    state_root: Path, *, locked: RegistryLock | None = None
) -> RegistrySnapshot:
    registry_path = state_root / ".forge/tmp/run-registry.json"
    if locked is not None:
        _validate_registry_lock(state_root, locked)
        try:
            raw, observation = _read_bound_regular(
                locked.directory_descriptor, registry_path.name
            )
        except FileNotFoundError:
            _validate_registry_lock(state_root, locked)
            return RegistrySnapshot(False, None, {})
        except OSError as exc:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
        _validate_registry_lock(state_root, locked)
        return _decode_registry_snapshot(raw, observation)

    directory_descriptor: int | None = None
    try:
        directory_descriptor, directory_observation = _open_bound_directory(
            registry_path.parent
        )
    except FileNotFoundError:
        return RegistrySnapshot(False, None, {})
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    try:
        raw, registry_observation = _read_bound_regular(
            directory_descriptor, registry_path.name
        )
        rebound = os.lstat(registry_path.parent)
        if not _matches_observation(rebound, directory_observation):
            raise OSError(errno.EAGAIN, "registry directory identity changed")
    except FileNotFoundError:
        try:
            rebound = os.lstat(registry_path.parent)
        except OSError as exc:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
        if not _matches_observation(rebound, directory_observation):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        return RegistrySnapshot(False, None, {})
    except (
        OSError,
    ) as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
    return _decode_registry_snapshot(raw, registry_observation)


def _readable_mode(mode: int, *, directory: bool = False) -> bool:
    read_mask = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    execute_mask = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    return bool(mode & read_mask) and (not directory or bool(mode & execute_mask))


def _read_owner_observation_at(
    directory_descriptor: int, name: str = "owner"
) -> tuple[OwnerObservation, Owner] | None:
    try:
        observed, observation = _read_bound_regular(directory_descriptor, name)
    except OSError:
        return None
    owner = _parse_owner_bytes(observed)
    if owner is None:
        return None
    return (
        OwnerObservation(
            observed=observed,
            device=observation.device,
            inode=observation.inode,
            mode=observation.mode,
        ),
        owner,
    )


def _read_owner_observation(path: Path) -> tuple[OwnerObservation, Owner] | None:
    descriptor: int | None = None
    try:
        descriptor, directory_observation = _open_bound_directory(path.parent)
        result = _read_owner_observation_at(descriptor, path.name)
        rebound = os.lstat(path.parent)
        if not _matches_observation(rebound, directory_observation):
            return None
        return result
    except OSError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _safe_run_entry_name(name: str) -> bool:
    return _safe_diagnostic_text(name) and "/" not in name and "\\" not in name


def _classify_runs(
    state_root: Path,
    registered_ids: frozenset[str],
    *,
    owner_target_ids: frozenset[str] = frozenset(),
) -> tuple[
    dict[str, RunState],
    dict[str, PlaceholderObservation],
    dict[str, OwnerObservation],
    FileObservation | None,
]:
    runs_root = state_root / ".codex-orchestrator/runs"
    root_descriptor: int | None = None
    try:
        root_descriptor, root_observation = _open_bound_directory(runs_root)
    except FileNotFoundError:
        return {}, {}, {}, None
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    if not _readable_mode(root_observation.mode, directory=True):
        os.close(root_descriptor)
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    try:
        names = os.listdir(root_descriptor)
    except OSError as exc:
        os.close(root_descriptor)
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc

    states: dict[str, RunState] = {}
    placeholders: dict[str, PlaceholderObservation] = {}
    owners: dict[str, OwnerObservation] = {}
    try:
        for name in sorted(names, key=os.fsencode):
            run_descriptor: int | None = None
            try:
                entry_stat = os.stat(
                    name, dir_fd=root_descriptor, follow_symlinks=False
                )
                if stat.S_ISREG(entry_stat.st_mode) and not name.startswith("."):
                    rebound_regular = os.stat(
                        name, dir_fd=root_descriptor, follow_symlinks=False
                    )
                    if _file_observation(rebound_regular) != _file_observation(entry_stat):
                        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                    continue
                if not _safe_run_entry_name(name) or name.startswith("."):
                    raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                if (
                    not stat.S_ISDIR(entry_stat.st_mode)
                    or stat.S_ISLNK(entry_stat.st_mode)
                    or not _readable_mode(entry_stat.st_mode, directory=True)
                ):
                    raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                run_descriptor, run_observation = _open_bound_child_directory(
                    root_descriptor, name, entry_stat
                )
                children = os.listdir(run_descriptor)
                child_names = set(children)
                has_journal = "journal.jsonl" in child_names
                has_owner = "owner" in child_names
                run_dir = runs_root / name
                if not has_journal:
                    rebound = os.stat(
                        name, dir_fd=root_descriptor, follow_symlinks=False
                    )
                    if not _matches_observation(rebound, run_observation):
                        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                    if name in registered_ids or has_owner:
                        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                    if "classify" not in ORPHAN_CLASSIFICATION_CONTROLS:
                        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                    if not children:
                        placeholders[name] = PlaceholderObservation(
                            path=run_dir,
                            device=run_observation.device,
                            inode=run_observation.inode,
                            mode=run_observation.mode,
                        )
                        continue
                    try:
                        rendered = run_dir.relative_to(state_root).as_posix()
                    except ValueError as exc:
                        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
                    if not _safe_diagnostic_text(rendered):
                        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                    raise CoordinationRefusal(
                        f"forge: new run refused — run directory {rendered} "
                        "lacks journal.jsonl"
                    )
                raw, journal_observation = _read_bound_regular(
                    run_descriptor, "journal.jsonl", require_nonempty=True
                )
                owner_result = _read_owner_observation_at(run_descriptor)
                rebound = os.stat(
                    name, dir_fd=root_descriptor, follow_symlinks=False
                )
                if not _matches_observation(rebound, run_observation):
                    raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                state = _scan_run(
                    run_dir,
                    raw=raw,
                    directory_observation=run_observation,
                    journal_observation=journal_observation,
                )
                if state.run_id in states:
                    raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                states[state.run_id] = state
                if owner_result is None:
                    if (
                        not state.pre_coordination
                        and not state.legacy
                        and state.run_id not in owner_target_ids
                    ):
                        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                else:
                    owners[state.run_id] = owner_result[0]
            except CoordinationRefusal:
                raise
            except OSError as exc:
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
            finally:
                if run_descriptor is not None:
                    os.close(run_descriptor)
        rebound_root = os.lstat(runs_root)
        if not _matches_observation(rebound_root, root_observation):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        return states, placeholders, owners, root_observation
    finally:
        os.close(root_descriptor)


def _reconcile_registry(
    snapshot: RegistrySnapshot, states: dict[str, RunState]
) -> dict[str, tuple[str, ...]]:
    persisted = {
        run_id: state.scope
        for run_id, state in states.items()
        if state.disposition == "open" and not state.pre_coordination
    }
    if snapshot.exists:
        if snapshot.open_runs != persisted:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    elif persisted or any(
        not state.legacy and not state.pre_coordination for state in states.values()
    ):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    admitted = dict(persisted)
    admitted.update(
        {
            run_id: state.scope
            for run_id, state in states.items()
            if state.disposition == "open" and state.pre_coordination
        }
    )
    return admitted


def _derive_reservations(states: dict[str, RunState]) -> dict[str, ScopeReservation]:
    children: dict[str, list[str]] = {run_id: [] for run_id in states}
    for run_id, state in states.items():
        predecessor_id = state.successor_of
        if predecessor_id is None:
            continue
        predecessor = states.get(predecessor_id)
        if predecessor is None or not predecessor.was_retired or predecessor.disposition != "retired":
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        children[predecessor_id].append(run_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(run_id: str) -> None:
        if run_id in visiting:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        if run_id in visited:
            return
        visiting.add(run_id)
        for child in children[run_id]:
            visit(child)
        visiting.remove(run_id)
        visited.add(run_id)

    for run_id in sorted(states, key=_byte_key):
        visit(run_id)
    if any(
        state.disposition in {"open", "closed"} and children[run_id]
        for run_id, state in states.items()
    ):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    if any(
        state.successor_of is not None
        and state.disposition == "closed"
        and state.close_judgment not in {"passed", "blocked"}
        for state in states.values()
    ):
        # Only an explicitly successful successor close releases its branch.
        # Legacy records without that judgment cannot prove release semantics.
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)

    effective: dict[str, tuple[frozenset[str], tuple[str, ...]]] = {}

    def effective_lineage(run_id: str) -> tuple[frozenset[str], tuple[str, ...]]:
        cached = effective.get(run_id)
        if cached is not None:
            return cached
        state = states[run_id]
        lineage = {run_id}
        combined = set(state.scope)
        predecessor_id = state.successor_of
        if predecessor_id is not None:
            predecessor_lineage, predecessor_scope = effective_lineage(predecessor_id)
            if not scopes_overlap(state.opening_scope, predecessor_scope):
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            lineage.update(predecessor_lineage)
            combined.update(predecessor_scope)
        result = (
            frozenset(lineage),
            tuple(sorted(combined, key=_byte_key)),
        )
        effective[run_id] = result
        return result

    for run_id in sorted(states, key=_byte_key):
        effective_lineage(run_id)

    if any(
        state.was_retired
        and state.disposition == "closed"
        and state.successor_of is None
        for state in states.values()
    ):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)

    reservations: dict[str, ScopeReservation] = {}
    for run_id, state in states.items():
        unresolved = state.disposition in {"open", "retired"}
        if (
            "release" not in SUCCESSOR_DAG_CONTROLS
            and state.disposition == "closed"
            and (state.successor_of is not None or state.was_retired)
        ):
            unresolved = True
        if not unresolved or children[run_id]:
            continue
        lineage, effective_scope = effective[run_id]
        disposition = state.disposition if state.disposition != "closed" else "retired"
        reservations[run_id] = ScopeReservation(
            run_id=run_id,
            disposition=disposition,
            scope=effective_scope,
            lineage=lineage,
        )
    return reservations


def _coordination_view(
    state_root: Path,
    *,
    owner_target_ids: frozenset[str] = frozenset(),
    locked: RegistryLock | None = None,
) -> CoordinationView:
    snapshot = _read_registry_snapshot(state_root, locked=locked)
    states, placeholders, owners, runs_root_observation = _classify_runs(
        state_root,
        frozenset(snapshot.open_runs),
        owner_target_ids=owner_target_ids,
    )
    open_runs = _reconcile_registry(snapshot, states)
    reservations = _derive_reservations(states)
    return CoordinationView(
        snapshot,
        states,
        open_runs,
        reservations,
        placeholders,
        owners,
        runs_root_observation,
    )


def _scan_runs(state_root: Path) -> dict[str, RunState]:
    return _coordination_view(state_root).states


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
    return _reconcile_registry(_read_registry_snapshot(state_root), states)


def _revalidate_placeholders(placeholders: dict[str, PlaceholderObservation]) -> None:
    for observation in placeholders.values():
        descriptor: int | None = None
        try:
            flags = os.O_RDONLY
            flags |= getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(observation.path, flags)
            current = os.fstat(descriptor)
            children = os.listdir(descriptor)
            rebound = os.lstat(observation.path)
        except (OSError, TypeError) as exc:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        if (
            current.st_dev != observation.device
            or current.st_ino != observation.inode
            or current.st_mode != observation.mode
            or rebound.st_dev != current.st_dev
            or rebound.st_ino != current.st_ino
            or rebound.st_mode != current.st_mode
            or not stat.S_ISDIR(current.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or children
        ):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)


def _assert_coordination_view_unchanged(
    state_root: Path, view: CoordinationView, *, locked: RegistryLock | None = None
) -> None:
    if _coordination_view(state_root, locked=locked) != view:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)


def _validate_new_run_claim(state_root: Path, claim: NewRunClaim) -> None:
    runs_root = state_root / ".codex-orchestrator/runs"
    root_descriptor: int | None = None
    run_descriptor: int | None = None
    try:
        root_descriptor, root_observation = _open_bound_directory(runs_root)
        if root_observation != claim.runs_root_observation:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        run_stat = os.stat(
            claim.run_id,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        run_descriptor, run_observation = _open_bound_child_directory(
            root_descriptor, claim.run_id, run_stat
        )
        if run_observation != claim.directory_observation:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        expected_names = {name for name, _, _ in claim.files}
        if set(os.listdir(run_descriptor)) != expected_names:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        for name, expected_observation, expected_payload in claim.files:
            raw, observed = _read_bound_regular(run_descriptor, name)
            if observed != expected_observation or raw != expected_payload:
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        rebound_run = os.stat(
            claim.run_id,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        rebound_root = os.lstat(runs_root)
        if (
            not _matches_observation(rebound_run, claim.directory_observation)
            or not _matches_observation(rebound_root, claim.runs_root_observation)
        ):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    except CoordinationRefusal:
        raise
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    finally:
        if run_descriptor is not None:
            os.close(run_descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)


def _validate_registry_publication(
    state_root: Path,
    open_runs: dict[str, tuple[str, ...]],
    view: CoordinationView,
    *,
    changed_run_id: str,
    appended_record: dict[str, object],
    expected_owner: Owner,
    locked: RegistryLock,
    expected_runs_root: FileObservation | None,
    new_run_claim: NewRunClaim | None = None,
) -> None:
    """Re-derive every persisted admission predicate at the publication fence."""

    _revalidate_placeholders(view.placeholders)
    _validate_registry_lock(state_root, locked)
    if new_run_claim is not None:
        _validate_new_run_claim(state_root, new_run_claim)
    snapshot = _read_registry_snapshot(state_root, locked=locked)
    if snapshot != view.registry:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    states, placeholders, owners, runs_root_observation = _classify_runs(
        state_root, frozenset(snapshot.open_runs)
    )
    if runs_root_observation != expected_runs_root:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    if placeholders != view.placeholders:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)

    expected_ids = set(view.states)
    if changed_run_id not in view.states:
        expected_ids.add(changed_run_id)
    if set(states) != expected_ids:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    for run_id, prior in view.states.items():
        if run_id == changed_run_id:
            continue
        if states.get(run_id) != prior:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    changed = states.get(changed_run_id)
    if changed is None:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    prior_changed = view.states.get(changed_run_id)
    expected_records = (
        (appended_record,)
        if prior_changed is None
        else prior_changed.records + (appended_record,)
    )
    if changed.records != expected_records:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)

    prior_owners = {
        run_id: owner
        for run_id, owner in view.owners.items()
        if run_id != changed_run_id
    }
    current_owners = {
        run_id: owner
        for run_id, owner in owners.items()
        if run_id != changed_run_id
    }
    if current_owners != prior_owners:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    changed_owner_observation = owners.get(changed_run_id)
    changed_owner = (
        _parse_owner_bytes(changed_owner_observation.observed)
        if changed_owner_observation is not None
        else None
    )
    if (
        changed_owner is None
        or changed_owner.pid != expected_owner.pid
        or changed_owner.host != expected_owner.host
    ):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)

    persistable = {
        run_id: scope
        for run_id, scope in open_runs.items()
        if scope != PRE_COORDINATION_SCOPE
    }
    derived = {
        run_id: state.scope
        for run_id, state in states.items()
        if state.disposition == "open" and not state.pre_coordination
    }
    if derived != persistable:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    _derive_reservations(states)
    if new_run_claim is not None:
        _validate_new_run_claim(state_root, new_run_claim)
    _validate_registry_lock(state_root, locked)


def _exchange_names_at(
    directory_descriptor: int, first_name: str, second_name: str
) -> None:
    """Atomically exchange two existing names without making either absent."""

    library = ctypes.CDLL(None, use_errno=True)
    first = os.fsencode(first_name)
    second = os.fsencode(second_name)
    if sys.platform.startswith("linux"):
        exchange = getattr(library, "renameat2", None)
        if exchange is None:
            raise OSError(errno.ENOTSUP, "atomic name exchange unavailable")
        exchange.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        exchange.restype = ctypes.c_int
        result = exchange(
            directory_descriptor,
            first,
            directory_descriptor,
            second,
            2,  # RENAME_EXCHANGE
        )
    elif sys.platform == "darwin":
        exchange = getattr(library, "renameatx_np", None)
        if exchange is None:
            raise OSError(errno.ENOTSUP, "atomic name exchange unavailable")
        exchange.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        exchange.restype = ctypes.c_int
        result = exchange(
            directory_descriptor,
            first,
            directory_descriptor,
            second,
            0x00000002,  # RENAME_SWAP
        )
    else:
        raise OSError(errno.ENOTSUP, "atomic name exchange unavailable")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _move_name_noreplace_at(
    directory_descriptor: int, source_name: str, destination_name: str
) -> None:
    """Atomically move one name only when the destination remains absent."""

    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform.startswith("linux"):
        move = getattr(library, "renameat2", None)
        if move is None:
            raise OSError(errno.ENOTSUP, "atomic no-replace move unavailable")
        move.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        move.restype = ctypes.c_int
        result = move(
            directory_descriptor,
            source,
            directory_descriptor,
            destination,
            1,  # RENAME_NOREPLACE
        )
    elif sys.platform == "darwin":
        move = getattr(library, "renameatx_np", None)
        if move is None:
            raise OSError(errno.ENOTSUP, "atomic no-replace move unavailable")
        move.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        move.restype = ctypes.c_int
        result = move(
            directory_descriptor,
            source,
            directory_descriptor,
            destination,
            0x00000004,  # RENAME_EXCL
        )
    else:
        raise OSError(errno.ENOTSUP, "atomic no-replace move unavailable")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _named_observation_at(
    directory_descriptor: int, name: str
) -> FileObservation:
    return _file_observation(
        os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    )


def _optional_exact_file_at(
    directory_descriptor: int, name: str
) -> ExactFile | None:
    try:
        raw, observation = _read_bound_regular(directory_descriptor, name)
    except FileNotFoundError:
        return None
    return ExactFile(raw, observation)


def _exchange_exact_at(
    directory_descriptor: int,
    first_name: str,
    second_name: str,
    first_before: ExactFile,
    second_before: ExactFile,
) -> NamespaceMutationOutcome:
    try:
        if (
            _optional_exact_file_at(directory_descriptor, first_name)
            != first_before
            or _optional_exact_file_at(directory_descriptor, second_name)
            != second_before
        ):
            return NamespaceMutationOutcome("foreign", None)
    except BaseException as exc:
        return NamespaceMutationOutcome("foreign", exc)
    failure: BaseException | None = None
    try:
        _exchange_names_at(directory_descriptor, first_name, second_name)
    except BaseException as exc:
        failure = exc
    try:
        first_after = _optional_exact_file_at(directory_descriptor, first_name)
        second_after = _optional_exact_file_at(directory_descriptor, second_name)
    except BaseException as exc:
        return NamespaceMutationOutcome("foreign", failure or exc)
    if first_after == second_before and second_after == first_before:
        return NamespaceMutationOutcome("post", failure)
    if first_after == first_before and second_after == second_before:
        return NamespaceMutationOutcome("pre", failure)
    return NamespaceMutationOutcome("foreign", failure)


def _link_exact_at(
    directory_descriptor: int,
    source_name: str,
    destination_name: str,
    expected: ExactFile,
) -> NamespaceMutationOutcome:
    try:
        if (
            _optional_exact_file_at(directory_descriptor, source_name)
            != expected
        ):
            return NamespaceMutationOutcome("foreign", None)
    except BaseException as exc:
        return NamespaceMutationOutcome("foreign", exc)
    try:
        destination_stat = os.stat(
            destination_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        pass
    except BaseException as exc:
        return NamespaceMutationOutcome("foreign", exc)
    else:
        if _matches_observation(destination_stat, expected.observation):
            # Another actor installed the exact intended hard link. Treat the
            # namespace as published so normal validation/rollback owns it.
            return NamespaceMutationOutcome("post", None)
        # The no-clobber destination was occupied before the syscall.  Its
        # type and contents are deliberately not inspected or followed.
        return NamespaceMutationOutcome("occupied", None)
    failure: BaseException | None = None
    try:
        os.link(
            source_name,
            destination_name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except BaseException as exc:
        failure = exc
    link_collision = isinstance(failure, FileExistsError) or (
        isinstance(failure, OSError) and failure.errno == errno.EEXIST
    )
    if link_collision:
        try:
            source_after_collision = _optional_exact_file_at(
                directory_descriptor, source_name
            )
        except BaseException as exc:
            return NamespaceMutationOutcome("foreign", failure or exc)
        if source_after_collision != expected:
            return NamespaceMutationOutcome("foreign", failure)
        try:
            destination_stat = os.stat(
                destination_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            # A transient collision is no longer observable; let the exact
            # pair classifier below determine whether state is PRE or foreign.
            pass
        except BaseException as exc:
            return NamespaceMutationOutcome("foreign", failure or exc)
        else:
            if _matches_observation(destination_stat, expected.observation):
                # Defensive fault-injection case: the candidate actually has
                # a canonical link despite the reported collision.
                return NamespaceMutationOutcome("post", failure)
            # EEXIST cannot partially create a link. The occupied destination
            # is observed without reading or following the node.
            return NamespaceMutationOutcome("occupied", failure)
    try:
        source_after = _optional_exact_file_at(
            directory_descriptor, source_name
        )
        destination_after = _optional_exact_file_at(
            directory_descriptor, destination_name
        )
    except BaseException as exc:
        return NamespaceMutationOutcome("foreign", failure or exc)
    if source_after == expected and destination_after == expected:
        return NamespaceMutationOutcome("post", failure)
    if source_after == expected and destination_after is None:
        return NamespaceMutationOutcome("pre", failure)
    return NamespaceMutationOutcome("foreign", failure)


def _move_exact_at(
    directory_descriptor: int,
    source_name: str,
    destination_name: str,
    expected: ExactFile,
) -> NamespaceMutationOutcome:
    try:
        if (
            _optional_exact_file_at(directory_descriptor, source_name)
            != expected
            or _optional_exact_file_at(directory_descriptor, destination_name)
            is not None
        ):
            return NamespaceMutationOutcome("foreign", None)
    except BaseException as exc:
        return NamespaceMutationOutcome("foreign", exc)
    failure: BaseException | None = None
    try:
        _move_name_noreplace_at(
            directory_descriptor, source_name, destination_name
        )
    except BaseException as exc:
        failure = exc
    try:
        source_after = _optional_exact_file_at(
            directory_descriptor, source_name
        )
        destination_after = _optional_exact_file_at(
            directory_descriptor, destination_name
        )
    except BaseException as exc:
        return NamespaceMutationOutcome("foreign", failure or exc)
    if source_after is None and destination_after == expected:
        return NamespaceMutationOutcome("post", failure)
    if source_after == expected and destination_after is None:
        return NamespaceMutationOutcome("pre", failure)
    return NamespaceMutationOutcome("foreign", failure)


def _reverse_exchange_with_exact_canonical_at(
    directory_descriptor: int,
    canonical_name: str,
    exchange_name: str,
    candidate_payload: bytes,
    candidate_observation: FileObservation,
) -> BaseException | None:
    """Reverse only while canonical retains the exact expected payload/inode."""

    try:
        canonical = _read_bound_regular(directory_descriptor, canonical_name)
        displaced_observation = _named_observation_at(
            directory_descriptor, exchange_name
        )
    except OSError as exc:
        raise NamespaceMutationAmbiguity from exc
    if canonical != (candidate_payload, candidate_observation):
        raise NamespaceMutationAmbiguity
    failure: BaseException | None = None
    try:
        _exchange_names_at(directory_descriptor, exchange_name, canonical_name)
    except BaseException as exc:
        failure = exc
    try:
        restored_canonical = _named_observation_at(
            directory_descriptor, canonical_name
        )
        retained_candidate = _read_bound_regular(
            directory_descriptor, exchange_name
        )
        if (
            restored_canonical != displaced_observation
            or retained_candidate
            != (candidate_payload, candidate_observation)
        ):
            raise NamespaceMutationAmbiguity
        return failure
    except NamespaceMutationAmbiguity:
        raise
    except BaseException as exc:
        raise NamespaceMutationAmbiguity from exc


def _reverse_exact_exchange_at(
    directory_descriptor: int,
    canonical_name: str,
    retention_name: str,
    canonical_expected: ExactFile,
    retention_expected: ExactFile,
) -> BaseException | None:
    """Exchange an authoritative exact pair back to its published ordering."""

    outcome = _exchange_exact_at(
        directory_descriptor,
        retention_name,
        canonical_name,
        retention_expected,
        canonical_expected,
    )
    if outcome.phase != "post":
        raise NamespaceMutationAmbiguity
    return outcome.failure


def _restore_exact_move_at(
    directory_descriptor: int,
    retention_name: str,
    canonical_name: str,
    expected: ExactFile,
) -> BaseException | None:
    outcome = _move_exact_at(
        directory_descriptor,
        retention_name,
        canonical_name,
        expected,
    )
    if outcome.phase != "post":
        raise NamespaceMutationAmbiguity
    return outcome.failure


def _verified_named_payload(
    locked: RegistryLock, name: str
) -> tuple[bytes, FileObservation]:
    try:
        return _read_bound_regular(locked.directory_descriptor, name)
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc


def _unlink_if_observed(
    directory_descriptor: int, name: str, observation: FileObservation
) -> None:
    try:
        current = os.stat(
            name, dir_fd=directory_descriptor, follow_symlinks=False
        )
        if _matches_observation(current, observation):
            os.unlink(name, dir_fd=directory_descriptor)
    except BaseException:
        pass


def _unlink_if_exact(
    directory_descriptor: int, name: str, expected: ExactFile
) -> None:
    """Best-effort cleanup without unlinking a substituted name."""

    try:
        if _optional_exact_file_at(directory_descriptor, name) == expected:
            os.unlink(name, dir_fd=directory_descriptor)
    except BaseException:
        pass


def _validate_restored_registry_publication(
    state_root: Path,
    locked: RegistryLock,
    publication: RegistryPublication,
) -> None:
    if _read_registry_snapshot(state_root, locked=locked) != publication.prior:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    _validate_registry_lock(state_root, locked)
    if _read_registry_snapshot(state_root, locked=locked) != publication.prior:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)


def _restore_registry_candidate_from_retention(
    state_root: Path,
    locked: RegistryLock,
    publication: RegistryPublication,
    retention_name: str,
    prior_exact: ExactFile | None,
) -> BaseException | None:
    candidate = ExactFile(
        publication.candidate_payload, publication.candidate_observation
    )
    _validate_registry_lock(state_root, locked)
    if prior_exact is not None:
        failure = _reverse_exact_exchange_at(
            locked.directory_descriptor,
            "run-registry.json",
            retention_name,
            prior_exact,
            candidate,
        )
    else:
        failure = _restore_exact_move_at(
            locked.directory_descriptor,
            retention_name,
            "run-registry.json",
            candidate,
        )
    if (
        _optional_exact_file_at(
            locked.directory_descriptor, "run-registry.json"
        )
        != candidate
    ):
        raise NamespaceMutationAmbiguity
    return failure


def _rollback_registry_publication(
    state_root: Path,
    locked: RegistryLock,
    publication: RegistryPublication,
) -> None:
    """Restore prior registry, retaining candidate until final proof succeeds."""

    candidate = ExactFile(
        publication.candidate_payload, publication.candidate_observation
    )
    retention_name: str | None = None
    prior_exact: ExactFile | None = None
    rollback_phase = "published"
    try:
        _validate_registry_lock(state_root, locked)
        if (
            _optional_exact_file_at(
                locked.directory_descriptor, "run-registry.json"
            )
            != candidate
        ):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        if publication.prior.exists:
            if (
                publication.backup_name is None
                or publication.prior.raw is None
                or publication.prior.observation is None
            ):
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            retention_name = publication.backup_name
            prior_exact = ExactFile(
                publication.prior.raw, publication.prior.observation
            )
            rollback_phase = "restoration-indeterminate"
            outcome = _exchange_exact_at(
                locked.directory_descriptor,
                retention_name,
                "run-registry.json",
                prior_exact,
                candidate,
            )
            if outcome.phase == "foreign":
                # If our exact prior became canonical, the exchange moved an
                # unexpected canonical into retention. Put it back only while
                # canonical is still that exact prior; otherwise preserve it.
                try:
                    _reverse_exchange_with_exact_canonical_at(
                        locked.directory_descriptor,
                        "run-registry.json",
                        retention_name,
                        prior_exact.payload,
                        prior_exact.observation,
                    )
                except NamespaceMutationAmbiguity:
                    pass
                raise RegistryRestorationRefusal(JOURNAL_ROLLBACK_FAILED)
            if outcome.phase != "post":
                raise RegistryRestorationRefusal(JOURNAL_ROLLBACK_FAILED)
            rollback_phase = "restored-unvalidated"
            pending_failure = outcome.failure
        else:
            retention_name = (
                f".run-registry.json.{uuid.uuid4().hex}.rollback"
            )
            rollback_phase = "restoration-indeterminate"
            outcome = _move_exact_at(
                locked.directory_descriptor,
                "run-registry.json",
                retention_name,
                candidate,
            )
            if outcome.phase != "post":
                raise RegistryRestorationRefusal(JOURNAL_ROLLBACK_FAILED)
            rollback_phase = "restored-unvalidated"
            pending_failure = outcome.failure

        assert retention_name is not None
        try:
            if pending_failure is not None:
                raise pending_failure
            _validate_restored_registry_publication(
                state_root, locked, publication
            )
        except BaseException as validation_failure:
            try:
                rollback_phase = "candidate-reapply-indeterminate"
                _restore_registry_candidate_from_retention(
                    state_root,
                    locked,
                    publication,
                    retention_name,
                    prior_exact,
                )
                rollback_phase = "published"
            except BaseException as restore_failure:
                raise RegistryRestorationRefusal(
                    JOURNAL_ROLLBACK_FAILED
                ) from restore_failure
            raise RegistryRestorationRefusal(
                JOURNAL_ROLLBACK_FAILED
            ) from validation_failure

        # From this point prior state is proven. Cleanup is deliberately
        # no-fail so callers can safely roll their journal append back.
        rollback_phase = "prior-committed"
        _unlink_if_observed(
            locked.directory_descriptor,
            retention_name,
            publication.candidate_observation,
        )
    except RegistryRestorationRefusal:
        raise
    except BaseException as exc:
        if rollback_phase == "prior-committed":
            raise
        if (
            rollback_phase
            in {"restoration-indeterminate", "restored-unvalidated"}
            and retention_name is not None
        ):
            try:
                canonical = _optional_exact_file_at(
                    locked.directory_descriptor, "run-registry.json"
                )
                retained = _optional_exact_file_at(
                    locked.directory_descriptor, retention_name
                )
                if canonical == candidate:
                    pass
                elif retained == candidate and canonical == prior_exact:
                    _restore_registry_candidate_from_retention(
                        state_root,
                        locked,
                        publication,
                        retention_name,
                        prior_exact,
                    )
                else:
                    raise NamespaceMutationAmbiguity
            except BaseException as restore_failure:
                raise RegistryRestorationRefusal(
                    JOURNAL_ROLLBACK_FAILED
                ) from restore_failure
        raise RegistryRestorationRefusal(JOURNAL_ROLLBACK_FAILED) from exc


def _begin_registry_publication(
    state_root: Path,
    locked: RegistryLock,
    prior: RegistrySnapshot,
    payload: bytes,
) -> RegistryPublication:
    """Publish candidate bytes while retaining a verified prior-inode backup."""

    _validate_registry_lock(state_root, locked)
    if _read_registry_snapshot(state_root, locked=locked) != prior:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    temporary = f".run-registry.json.{uuid.uuid4().hex}.candidate"
    candidate_observation: FileObservation | None = None
    backup_name: str | None = None
    publication: RegistryPublication | None = None
    candidate: ExactFile | None = None
    prior_exact: ExactFile | None = None
    phase = "unstaged"
    try:
        candidate_observation = _write_exclusive_at(
            locked.directory_descriptor, temporary, payload
        )
        candidate = ExactFile(payload, candidate_observation)
        phase = "staged"
        backup_name = (
            f".run-registry.json.{uuid.uuid4().hex}.previous"
            if prior.exists
            else None
        )
        publication = RegistryPublication(
            prior, candidate_observation, payload, backup_name
        )
        if prior.exists:
            if prior.raw is None or prior.observation is None:
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            prior_exact = ExactFile(prior.raw, prior.observation)
            assert backup_name is not None
            link_outcome = _link_exact_at(
                locked.directory_descriptor,
                "run-registry.json",
                backup_name,
                prior_exact,
            )
            if link_outcome.phase != "post":
                if link_outcome.failure is not None:
                    raise link_outcome.failure
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            phase = "backup"
            if link_outcome.failure is not None:
                raise link_outcome.failure
            phase = "exchange-indeterminate"
            exchange_outcome = _exchange_exact_at(
                locked.directory_descriptor,
                temporary,
                "run-registry.json",
                candidate,
                prior_exact,
            )
            if exchange_outcome.phase == "foreign":
                try:
                    reverse_failure = _reverse_exchange_with_exact_canonical_at(
                        locked.directory_descriptor,
                        "run-registry.json",
                        temporary,
                        payload,
                        candidate_observation,
                    )
                except NamespaceMutationAmbiguity as restore_exc:
                    raise RegistryRestorationRefusal(
                        JOURNAL_ROLLBACK_FAILED
                    ) from restore_exc
                phase = "backup"
                if reverse_failure is not None:
                    raise reverse_failure
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            if exchange_outcome.phase != "post":
                phase = "backup"
                if exchange_outcome.failure is not None:
                    raise exchange_outcome.failure
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            phase = "published"
            if exchange_outcome.failure is not None:
                raise exchange_outcome.failure
            _unlink_if_observed(
                locked.directory_descriptor,
                temporary,
                prior_exact.observation,
            )
        else:
            phase = "link-indeterminate"
            link_outcome = _link_exact_at(
                locked.directory_descriptor,
                temporary,
                "run-registry.json",
                candidate,
            )
            if link_outcome.phase != "post":
                if link_outcome.phase == "occupied":
                    # The exact staged candidate was verified before a
                    # no-follow occupancy check.  No link syscall occurred.
                    phase = "staged"
                    raise CoordinationRefusal(REGISTRY_UPDATE_FAILED)
                if link_outcome.phase == "foreign":
                    raise RegistryRestorationRefusal(
                        JOURNAL_ROLLBACK_FAILED
                    )
                phase = "staged"
                if link_outcome.failure is not None:
                    raise link_outcome.failure
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            phase = "published"
            if link_outcome.failure is not None:
                raise link_outcome.failure
            _unlink_if_observed(
                locked.directory_descriptor,
                temporary,
                candidate_observation,
            )
        if (
            _optional_exact_file_at(
                locked.directory_descriptor, "run-registry.json"
            )
            != candidate
        ):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        return publication
    except RegistryRestorationRefusal:
        # An exchanged name could not be put back without risking a foreign
        # inode. Preserve every remaining link for operator inspection.
        raise
    except BaseException:
        if phase in {"exchange-indeterminate", "link-indeterminate"}:
            try:
                canonical = _optional_exact_file_at(
                    locked.directory_descriptor, "run-registry.json"
                )
                staged = _optional_exact_file_at(
                    locked.directory_descriptor, temporary
                )
            except BaseException as exc:
                raise RegistryRestorationRefusal(
                    JOURNAL_ROLLBACK_FAILED
                ) from exc
            if canonical == candidate:
                phase = "published"
            elif (
                prior_exact is not None
                and canonical == prior_exact
                and staged == candidate
            ):
                phase = "backup"
            elif (
                prior_exact is None
                and canonical is None
                and staged == candidate
            ):
                phase = "staged"
            else:
                raise RegistryRestorationRefusal(JOURNAL_ROLLBACK_FAILED)
        if phase == "published":
            if publication is None:
                raise RegistryRestorationRefusal(JOURNAL_ROLLBACK_FAILED)
            _rollback_registry_publication(state_root, locked, publication)
            if prior_exact is not None:
                # A successful existing-registry rollback proves the
                # canonical prior state.  The exchange staging name then
                # holds only the exact displaced prior hard link.
                _unlink_if_exact(
                    locked.directory_descriptor, temporary, prior_exact
                )
        if candidate is not None:
            _unlink_if_exact(
                locked.directory_descriptor, temporary, candidate
            )
        if backup_name is not None and prior.observation is not None:
            _unlink_if_observed(
                locked.directory_descriptor,
                backup_name,
                prior.observation,
            )
        raise


def _commit_registry_publication(
    state_root: Path,
    locked: RegistryLock,
    publication: RegistryPublication,
) -> None:
    """Best-effort removal after consistent state is fully committed."""

    if publication.backup_name is None or publication.prior.observation is None:
        return
    try:
        _validate_registry_lock(state_root, locked)
        if (
            _optional_exact_file_at(
                locked.directory_descriptor, "run-registry.json"
            )
            != ExactFile(
                publication.candidate_payload,
                publication.candidate_observation,
            )
        ):
            return
        raw, observation = _verified_named_payload(
            locked, publication.backup_name
        )
        if (
            observation == publication.prior.observation
            and raw == publication.prior.raw
        ):
            os.unlink(
                publication.backup_name, dir_fd=locked.directory_descriptor
            )
    except BaseException:
        # Canonical registry/journal state is already consistent. A leftover
        # verified backup is inert; cleanup failure must not trigger rollback.
        return


def _validate_post_registry_publication(
    state_root: Path,
    locked: RegistryLock,
    expected_open_runs: dict[str, tuple[str, ...]],
    expected_payload: bytes,
    expected_runs_root: FileObservation | None,
    new_run_claim: NewRunClaim | None,
) -> None:
    _validate_registry_lock(state_root, locked)
    published = _read_registry_snapshot(state_root, locked=locked)
    if (
        published.raw != expected_payload
        or published.open_runs != expected_open_runs
    ):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    states, _placeholders, _owners, runs_root_observation = _classify_runs(
        state_root, frozenset(published.open_runs)
    )
    if runs_root_observation != expected_runs_root:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    reconciled = _reconcile_registry(published, states)
    if {
        run_id: scope
        for run_id, scope in reconciled.items()
        if scope != PRE_COORDINATION_SCOPE
    } != expected_open_runs:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    _derive_reservations(states)
    if new_run_claim is not None:
        _validate_new_run_claim(state_root, new_run_claim)
    _validate_registry_lock(state_root, locked)
    if _read_registry_snapshot(state_root, locked=locked) != published:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)


def _write_registry(
    state_root: Path,
    open_runs: dict[str, tuple[str, ...]],
    *,
    view: CoordinationView | None = None,
    changed_run_id: str | None = None,
    appended_record: dict[str, object] | None = None,
    expected_owner: Owner | None = None,
    locked: RegistryLock | None = None,
    expected_runs_root: FileObservation | None = None,
    new_run_claim: NewRunClaim | None = None,
) -> None:
    # Pre-coordination sentinel scopes are in-memory admission state, never
    # registry bytes: the persisted file holds only validatable pathspecs.
    persistable = {
        run_id: scope
        for run_id, scope in open_runs.items()
        if scope != PRE_COORDINATION_SCOPE
    }
    if view is not None:
        if (
            changed_run_id is None
            or appended_record is None
            or expected_owner is None
            or locked is None
        ):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        _validate_registry_publication(
            state_root,
            open_runs,
            view,
            changed_run_id=changed_run_id,
            appended_record=appended_record,
            expected_owner=expected_owner,
            locked=locked,
            expected_runs_root=expected_runs_root,
            new_run_claim=new_run_claim,
        )
    try:
        payload = _registry_payload(persistable)
        if locked is None:
            _atomic_replace(state_root / ".forge/tmp/run-registry.json", payload)
            return
        if new_run_claim is not None:
            _validate_new_run_claim(state_root, new_run_claim)
        _validate_registry_lock(state_root, locked)
        current_snapshot = _read_registry_snapshot(state_root, locked=locked)
        if view is not None and current_snapshot != view.registry:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        publication = _begin_registry_publication(
            state_root, locked, current_snapshot, payload
        )
        try:
            _validate_post_registry_publication(
                state_root,
                locked,
                persistable,
                payload,
                expected_runs_root,
                new_run_claim,
            )
        except BaseException:
            _rollback_registry_publication(state_root, locked, publication)
            raise
        _commit_registry_publication(state_root, locked, publication)
    except RegistryRestorationRefusal:
        # The registry's authoritative state is no longer provable. Callers
        # must retain their journal/run mutation rather than creating a known
        # mismatch by rolling it back.
        raise
    except CoordinationRefusal:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise CoordinationRefusal(REGISTRY_UPDATE_FAILED) from exc


def _owner_refusal(run_id: str, owner: Owner) -> JournalAppendRefusal:
    return JournalAppendRefusal(
        f"forge: journal append refused — run {run_id} has live owner {owner.pid}@{owner.host}"
    )


def _bound_run_descriptor(state: RunState) -> int:
    expected = state.directory_observation
    if expected is None:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    try:
        descriptor, observed = _open_bound_directory(state.run_dir)
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    if observed != expected:
        os.close(descriptor)
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    return descriptor


def _owner_result_for_state(
    state: RunState, *, locked: LockedJournal | None = None
) -> tuple[OwnerObservation, Owner] | None:
    close_descriptor = locked is None
    descriptor = (
        _bound_run_descriptor(state) if locked is None else locked.run_descriptor
    )
    try:
        expected = state.directory_observation
        if expected is None or not _matches_observation(
            os.fstat(descriptor), expected
        ):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        result = _read_owner_observation_at(descriptor)
        rebound = os.lstat(state.run_dir)
        if not _matches_observation(rebound, expected):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        return result
    finally:
        if close_descriptor:
            os.close(descriptor)


def _classify_owner(
    state: RunState,
    current: Owner,
    *,
    adopt_missing: bool = False,
    locked: LockedJournal | None = None,
) -> OwnerClassification:
    run_id = state.run_id
    owner_result = _owner_result_for_state(state, locked=locked)
    if owner_result is None:
        if adopt_missing:
            return OwnerClassification("adopt", None)
        raise JournalAppendRefusal(
            f"forge: journal append refused — owner record missing or malformed for run {run_id}"
        )
    observation, owner = owner_result
    if owner.host == current.host and owner.pid == current.pid:
        return OwnerClassification(
            "owned",
            observation.observed,
            owner,
            observation.device,
            observation.inode,
            observation.mode,
        )
    if owner.host != current.host:
        raise _owner_refusal(run_id, owner)
    live = _pid_is_live(owner.pid)
    if live is not False:
        raise _owner_refusal(run_id, owner)
    return OwnerClassification(
        "stale",
        observation.observed,
        owner,
        observation.device,
        observation.inode,
        observation.mode,
    )


def _atomic_replace_at(
    directory_descriptor: int, name: str, payload: bytes
) -> None:
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    descriptor: int | None = None
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_descriptor)
        remaining = memoryview(payload)
        while remaining:
            count = os.write(descriptor, remaining)
            if count <= 0:
                raise OSError(errno.EIO, "short atomic write")
            remaining = remaining[count:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(
            temporary,
            name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
        )
    except BaseException:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.unlink(temporary, dir_fd=directory_descriptor)
        except OSError:
            pass
        raise


def _write_exclusive_at(
    directory_descriptor: int, name: str, payload: bytes
) -> FileObservation:
    descriptor: int | None = None
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_descriptor)
        remaining = memoryview(payload)
        while remaining:
            count = os.write(descriptor, remaining)
            if count <= 0:
                raise OSError(errno.EIO, "short exclusive write")
            remaining = remaining[count:]
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        rebound = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
        observation = _file_observation(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(opened.st_mode)
            or not _matches_observation(rebound, observation)
        ):
            raise OSError(errno.EAGAIN, "exclusive file identity changed")
        return observation
    except BaseException:
        if descriptor is not None:
            try:
                opened = os.fstat(descriptor)
                rebound = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                if _file_observation(opened) == _file_observation(rebound):
                    os.unlink(name, dir_fd=directory_descriptor)
            except OSError:
                pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _classify_late_run_target(parent_descriptor: int, name: str) -> str:
    descriptor: int | None = None
    try:
        before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        descriptor, observation = _open_bound_child_directory(
            parent_descriptor, name, before
        )
        if not _readable_mode(observation.mode, directory=True):
            return "ambiguous"
        children = os.listdir(descriptor)
        rebound = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if not _matches_observation(rebound, observation):
            return "ambiguous"
        if not children:
            return "empty"
        if "owner" in children or "journal.jsonl" in children:
            return "ambiguous"
        return "nonempty"
    except OSError:
        return "ambiguous"
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _cleanup_claimed_run(
    parent_descriptor: int,
    name: str,
    directory_descriptor: int,
    directory_observation: FileObservation,
    created: dict[str, tuple[FileObservation, bytes]],
) -> bool:
    """Quarantine first, then remove only the exact claimed inode and contents."""

    quarantine = f".{name}.rollback.{uuid.uuid4().hex}"
    try:
        os.rename(
            name,
            quarantine,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        quarantined = os.stat(
            quarantine,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        return False

    def restore() -> bool:
        try:
            os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            return False
        except FileNotFoundError:
            pass
        except OSError:
            return False
        try:
            current = os.stat(
                quarantine,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            os.rename(
                quarantine,
                name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            restored = os.stat(
                name, dir_fd=parent_descriptor, follow_symlinks=False
            )
            return _file_observation(current) == _file_observation(restored)
        except OSError:
            return False

    if (
        not _matches_observation(quarantined, directory_observation)
        or not _matches_observation(
            os.fstat(directory_descriptor), directory_observation
        )
    ):
        restore()
        return False
    try:
        for file_name, (observation, payload) in created.items():
            raw, rebound = _read_bound_regular(directory_descriptor, file_name)
            if rebound != observation or raw != payload:
                restore()
                return False
        for file_name in created:
            os.unlink(file_name, dir_fd=directory_descriptor)
        if os.listdir(directory_descriptor):
            # Foreign children are never deleted. Restoring the quarantined
            # claimed directory after removing only our verified files is a
            # successful rollback of the candidate's bytes.
            return restore()
        if not _matches_observation(
            os.stat(
                quarantine,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            ),
            directory_observation,
        ):
            return False
        os.rmdir(quarantine, dir_fd=parent_descriptor)
        return True
    except OSError:
        restore()
        return False


def _classification_observation(
    classification: OwnerClassification,
) -> FileObservation:
    if (
        classification.device is None
        or classification.inode is None
        or classification.mode is None
    ):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    return FileObservation(
        classification.device,
        classification.inode,
        classification.mode,
    )


def _validate_owner_run_binding(locked: LockedJournal) -> None:
    expected = locked.state.directory_observation
    if expected is None:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    try:
        opened = os.fstat(locked.run_descriptor)
        rebound = os.lstat(locked.state.run_dir)
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    if (
        not _matches_observation(opened, expected)
        or not _matches_observation(rebound, expected)
    ):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)


def _validate_owner_takeover(
    locked: LockedJournal, takeover: OwnerTakeover
) -> None:
    _validate_owner_run_binding(locked)
    if takeover.candidate_observation is None:
        refreshed = _read_owner_observation_at(locked.run_descriptor)
        expected = takeover.prior
        if (
            refreshed is None
            or expected.observed is None
            or refreshed[0].observed != expected.observed
            or FileObservation(
                refreshed[0].device,
                refreshed[0].inode,
                refreshed[0].mode,
            )
            != _classification_observation(expected)
        ):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        return
    try:
        raw, observation = _read_bound_regular(locked.run_descriptor, "owner")
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    if (
        raw != takeover.candidate_payload
        or observation != takeover.candidate_observation
    ):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)


def _validate_restored_owner_takeover(
    locked: LockedJournal, prior: ExactFile | None
) -> None:
    _validate_owner_run_binding(locked)
    if _optional_exact_file_at(locked.run_descriptor, "owner") != prior:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    _validate_owner_run_binding(locked)


def _restore_owner_candidate_from_retention(
    locked: LockedJournal,
    takeover: OwnerTakeover,
    retention_name: str,
    prior_exact: ExactFile | None,
) -> BaseException | None:
    if (
        takeover.candidate_payload is None
        or takeover.candidate_observation is None
    ):
        raise NamespaceMutationAmbiguity
    candidate = ExactFile(
        takeover.candidate_payload, takeover.candidate_observation
    )
    _validate_owner_run_binding(locked)
    if prior_exact is not None:
        failure = _reverse_exact_exchange_at(
            locked.run_descriptor,
            "owner",
            retention_name,
            prior_exact,
            candidate,
        )
    else:
        failure = _restore_exact_move_at(
            locked.run_descriptor,
            retention_name,
            "owner",
            candidate,
        )
    if _optional_exact_file_at(locked.run_descriptor, "owner") != candidate:
        raise NamespaceMutationAmbiguity
    return failure


def _rollback_owner_takeover(
    locked: LockedJournal, takeover: OwnerTakeover
) -> None:
    """Restore exact prior owner, retaining candidate until final proof."""

    if takeover.candidate_observation is None:
        return
    if takeover.candidate_payload is None:
        raise OwnerRestorationRefusal(JOURNAL_ROLLBACK_FAILED)
    candidate = ExactFile(
        takeover.candidate_payload, takeover.candidate_observation
    )
    retention_name: str | None = None
    prior_exact: ExactFile | None = None
    rollback_phase = "published"
    try:
        _validate_owner_run_binding(locked)
        if (
            _optional_exact_file_at(locked.run_descriptor, "owner")
            != candidate
        ):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        prior = takeover.prior
        if prior.observed is None:
            retention_name = f".owner.{uuid.uuid4().hex}.rollback"
            rollback_phase = "restoration-indeterminate"
            outcome = _move_exact_at(
                locked.run_descriptor,
                "owner",
                retention_name,
                candidate,
            )
            if outcome.phase != "post":
                raise OwnerRestorationRefusal(JOURNAL_ROLLBACK_FAILED)
            rollback_phase = "restored-unvalidated"
            pending_failure = outcome.failure
        else:
            if takeover.backup_name is None:
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            retention_name = takeover.backup_name
            prior_exact = ExactFile(
                prior.observed, _classification_observation(prior)
            )
            rollback_phase = "restoration-indeterminate"
            outcome = _exchange_exact_at(
                locked.run_descriptor,
                retention_name,
                "owner",
                prior_exact,
                candidate,
            )
            if outcome.phase == "foreign":
                try:
                    _reverse_exchange_with_exact_canonical_at(
                        locked.run_descriptor,
                        "owner",
                        retention_name,
                        prior_exact.payload,
                        prior_exact.observation,
                    )
                except NamespaceMutationAmbiguity:
                    pass
                raise OwnerRestorationRefusal(JOURNAL_ROLLBACK_FAILED)
            if outcome.phase != "post":
                raise OwnerRestorationRefusal(JOURNAL_ROLLBACK_FAILED)
            rollback_phase = "restored-unvalidated"
            pending_failure = outcome.failure

        assert retention_name is not None
        try:
            if pending_failure is not None:
                raise pending_failure
            _validate_restored_owner_takeover(locked, prior_exact)
        except BaseException as validation_failure:
            try:
                rollback_phase = "candidate-reapply-indeterminate"
                _restore_owner_candidate_from_retention(
                    locked,
                    takeover,
                    retention_name,
                    prior_exact,
                )
                rollback_phase = "published"
            except BaseException as restore_failure:
                raise OwnerRestorationRefusal(
                    JOURNAL_ROLLBACK_FAILED
                ) from restore_failure
            raise OwnerRestorationRefusal(
                JOURNAL_ROLLBACK_FAILED
            ) from validation_failure

        rollback_phase = "prior-committed"
        _unlink_if_observed(
            locked.run_descriptor,
            retention_name,
            takeover.candidate_observation,
        )
    except OwnerRestorationRefusal:
        raise
    except BaseException as exc:
        if rollback_phase == "prior-committed":
            raise
        if (
            rollback_phase
            in {"restoration-indeterminate", "restored-unvalidated"}
            and retention_name is not None
        ):
            try:
                canonical = _optional_exact_file_at(
                    locked.run_descriptor, "owner"
                )
                retained = _optional_exact_file_at(
                    locked.run_descriptor, retention_name
                )
                if canonical == candidate:
                    pass
                elif retained == candidate and canonical == prior_exact:
                    _restore_owner_candidate_from_retention(
                        locked,
                        takeover,
                        retention_name,
                        prior_exact,
                    )
                else:
                    raise NamespaceMutationAmbiguity
            except BaseException as restore_failure:
                raise OwnerRestorationRefusal(
                    JOURNAL_ROLLBACK_FAILED
                ) from restore_failure
        raise OwnerRestorationRefusal(JOURNAL_ROLLBACK_FAILED) from exc


def _commit_owner_takeover(
    locked: LockedJournal, takeover: OwnerTakeover
) -> None:
    """Discard the retained prior-owner link after candidate success."""

    prior = takeover.prior
    if (
        takeover.backup_name is None
        or prior.observed is None
        or takeover.candidate_payload is None
        or takeover.candidate_observation is None
    ):
        return
    try:
        if (
            _optional_exact_file_at(locked.run_descriptor, "owner")
            != ExactFile(
                takeover.candidate_payload,
                takeover.candidate_observation,
            )
        ):
            return
        prior_observation = _classification_observation(prior)
        raw, observation = _read_bound_regular(
            locked.run_descriptor, takeover.backup_name
        )
        if raw == prior.observed and observation == prior_observation:
            os.unlink(takeover.backup_name, dir_fd=locked.run_descriptor)
    except BaseException:
        # The installed current owner is authoritative after success. A
        # retained verified hard link to the prior owner is inert.
        return


def _begin_owner_takeover(
    state: RunState,
    current: Owner,
    classification: OwnerClassification,
    *,
    adopt_missing: bool = False,
    locked: LockedJournal,
) -> OwnerTakeover:
    run_id = state.run_id
    refreshed = _classify_owner(
        state,
        current,
        adopt_missing=adopt_missing,
        locked=locked,
    )
    if refreshed != classification:
        raise JournalAppendRefusal(
            f"forge: journal append refused — owner record missing or malformed for run {run_id}"
        )
    if classification.disposition == "owned":
        return OwnerTakeover(classification, None, None, None)
    payload = _owner_bytes(current)
    temporary = f".owner.{uuid.uuid4().hex}.candidate"
    backup_name = (
        f".owner.{uuid.uuid4().hex}.previous"
        if classification.observed is not None
        else None
    )
    candidate_observation: FileObservation | None = None
    takeover: OwnerTakeover | None = None
    candidate: ExactFile | None = None
    prior_exact: ExactFile | None = None
    phase = "unstaged"
    try:
        candidate_observation = _write_exclusive_at(
            locked.run_descriptor, temporary, payload
        )
        candidate = ExactFile(payload, candidate_observation)
        phase = "staged"
        takeover = OwnerTakeover(
            classification,
            candidate_observation,
            payload,
            backup_name,
        )
        if classification.observed is None:
            phase = "link-indeterminate"
            link_outcome = _link_exact_at(
                locked.run_descriptor,
                temporary,
                "owner",
                candidate,
            )
            if link_outcome.phase != "post":
                if link_outcome.phase == "foreign":
                    raise OwnerRestorationRefusal(JOURNAL_ROLLBACK_FAILED)
                phase = "staged"
                if link_outcome.failure is not None:
                    raise link_outcome.failure
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            phase = "published"
            if link_outcome.failure is not None:
                raise link_outcome.failure
            _unlink_if_observed(
                locked.run_descriptor, temporary, candidate_observation
            )
        else:
            assert backup_name is not None
            prior_exact = ExactFile(
                classification.observed,
                _classification_observation(classification),
            )
            link_outcome = _link_exact_at(
                locked.run_descriptor,
                "owner",
                backup_name,
                prior_exact,
            )
            if link_outcome.phase != "post":
                if link_outcome.failure is not None:
                    raise link_outcome.failure
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            phase = "backup"
            if link_outcome.failure is not None:
                raise link_outcome.failure
            phase = "exchange-indeterminate"
            exchange_outcome = _exchange_exact_at(
                locked.run_descriptor,
                temporary,
                "owner",
                candidate,
                prior_exact,
            )
            if exchange_outcome.phase == "foreign":
                try:
                    reverse_failure = _reverse_exchange_with_exact_canonical_at(
                        locked.run_descriptor,
                        "owner",
                        temporary,
                        payload,
                        candidate_observation,
                    )
                except NamespaceMutationAmbiguity as exc:
                    raise OwnerRestorationRefusal(
                        JOURNAL_ROLLBACK_FAILED
                    ) from exc
                phase = "backup"
                if reverse_failure is not None:
                    raise reverse_failure
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            if exchange_outcome.phase != "post":
                phase = "backup"
                if exchange_outcome.failure is not None:
                    raise exchange_outcome.failure
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
            phase = "published"
            if exchange_outcome.failure is not None:
                raise exchange_outcome.failure
            _unlink_if_observed(
                locked.run_descriptor,
                temporary,
                prior_exact.observation,
            )
        _validate_owner_takeover(locked, takeover)
        return takeover
    except OwnerRestorationRefusal:
        raise
    except BaseException as exc:
        if phase in {"exchange-indeterminate", "link-indeterminate"}:
            try:
                canonical = _optional_exact_file_at(
                    locked.run_descriptor, "owner"
                )
                staged = _optional_exact_file_at(
                    locked.run_descriptor, temporary
                )
            except BaseException as observe_exc:
                raise OwnerRestorationRefusal(
                    JOURNAL_ROLLBACK_FAILED
                ) from observe_exc
            if canonical == candidate:
                phase = "published"
            elif (
                prior_exact is not None
                and canonical == prior_exact
                and staged == candidate
            ):
                phase = "backup"
            elif (
                prior_exact is None
                and canonical is None
                and staged == candidate
            ):
                phase = "staged"
            else:
                raise OwnerRestorationRefusal(JOURNAL_ROLLBACK_FAILED)
        if phase == "published" and takeover is not None:
            _rollback_owner_takeover(locked, takeover)
            if prior_exact is not None:
                # As with registry publication, the successful rollback has
                # proved the canonical prior owner before this redundant
                # displaced-prior link is removed.
                _unlink_if_exact(
                    locked.run_descriptor, temporary, prior_exact
                )
        if candidate_observation is not None:
            _unlink_if_observed(
                locked.run_descriptor, temporary, candidate_observation
            )
        if backup_name is not None and classification.observed is not None:
            _unlink_if_observed(
                locked.run_descriptor,
                backup_name,
                _classification_observation(classification),
            )
        if isinstance(exc, CoordinationRefusal):
            raise
        if not isinstance(exc, Exception):
            raise
        raise CoordinationRefusal(
            "forge: journal append refused — journal write failed"
        ) from exc


def _apply_owner_classification(
    state: RunState,
    current: Owner,
    classification: OwnerClassification,
    *,
    adopt_missing: bool = False,
    locked: LockedJournal,
) -> OwnerTakeover:
    return _begin_owner_takeover(
        state,
        current,
        classification,
        adopt_missing=adopt_missing,
        locked=locked,
    )


@contextmanager
def _owner_takeover_transaction(
    state: RunState,
    current: Owner,
    classification: OwnerClassification,
    *,
    adopt_missing: bool = False,
    locked: LockedJournal,
) -> Iterator[OwnerTakeover]:
    """Keep a prior-owner link until every candidate operation succeeds."""

    takeover = _apply_owner_classification(
        state,
        current,
        classification,
        adopt_missing=adopt_missing,
        locked=locked,
    )
    try:
        yield takeover
    except BaseException:
        _rollback_owner_takeover(locked, takeover)
        raise
    else:
        _commit_owner_takeover(locked, takeover)


def _append_with_locked_stream(
    stream: object,
    run_dir: Path,
    run_id: str,
    record: dict[str, object],
    *,
    payload: bytes | None = None,
) -> int:
    if payload is None:
        payload = _journal_payload(record)
    try:
        descriptor = stream.fileno()  # type: ignore[attr-defined]
        offset = os.lseek(descriptor, 0, os.SEEK_END)
        if isinstance(stream, LockedJournal):
            _validate_locked_journal_path(stream)
        remaining = memoryview(payload)
        while remaining:
            count = os.write(descriptor, remaining)
            if count <= 0:
                raise OSError(errno.EIO, "short journal write")
            remaining = remaining[count:]
        os.fsync(descriptor)
        if isinstance(stream, LockedJournal):
            try:
                _validate_locked_journal_path(stream)
            except CoordinationRefusal:
                os.ftruncate(descriptor, offset)
                os.fsync(descriptor)
                raise
        return offset
    except CoordinationRefusal:
        raise
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
        raise CoordinationRefusal(JOURNAL_ROLLBACK_FAILED) from exc


def _validate_locked_journal_path(locked: LockedJournal) -> None:
    state = locked.state
    expected_run = state.directory_observation
    expected_journal = state.journal_observation
    if expected_run is None or expected_journal is None:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    try:
        run_open = os.fstat(locked.run_descriptor)
        run_path = os.lstat(state.run_dir)
        journal_open = os.fstat(locked.fileno())
        journal_path = os.stat(
            "journal.jsonl",
            dir_fd=locked.run_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    if (
        not _matches_observation(run_open, expected_run)
        or not _matches_observation(run_path, expected_run)
        or not _matches_observation(journal_open, expected_journal)
        or not _matches_observation(journal_path, expected_journal)
    ):
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)


@contextmanager
def _locked_journal(state: RunState) -> Iterator[LockedJournal]:
    run_descriptor: int | None = None
    journal_descriptor: int | None = None
    stream: object | None = None
    try:
        expected_journal = state.journal_observation
        if expected_journal is None:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        run_descriptor = _bound_run_descriptor(state)
        before = os.stat(
            "journal.jsonl", dir_fd=run_descriptor, follow_symlinks=False
        )
        if not _matches_observation(before, expected_journal):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        try:
            journal_descriptor = os.open(
                "journal.jsonl",
                _regular_open_flags(writable=True),
                dir_fd=run_descriptor,
            )
        except OSError as exc:
            try:
                rebound_after_failure = os.stat(
                    "journal.jsonl",
                    dir_fd=run_descriptor,
                    follow_symlinks=False,
                )
            except OSError:
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
            if _matches_observation(rebound_after_failure, expected_journal):
                raise CoordinationRefusal(
                    "forge: journal append refused — journal write failed"
                ) from exc
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
        opened = os.fstat(journal_descriptor)
        if (
            not _matches_observation(opened, expected_journal)
            or not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(opened.st_mode)
        ):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        stream = os.fdopen(journal_descriptor, "r+b", buffering=0)
        journal_descriptor = None
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]
        after_lock = os.fstat(stream.fileno())  # type: ignore[attr-defined]
        rebound = os.stat(
            "journal.jsonl", dir_fd=run_descriptor, follow_symlinks=False
        )
        run_rebound = os.lstat(state.run_dir)
        if (
            not _matches_observation(after_lock, expected_journal)
            or not _matches_observation(rebound, expected_journal)
            or state.directory_observation is None
            or not _matches_observation(run_rebound, state.directory_observation)
        ):
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        raw = _read_descriptor(stream.fileno())  # type: ignore[attr-defined]
        if tuple(_parse_raw_records(raw)) != state.records:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        yield LockedJournal(stream, run_descriptor, state)
    except CoordinationRefusal:
        raise
    except OSError as exc:
        # A journal that disappears, changes identity, or cannot be proven to
        # be the classified regular file is persisted coordination ambiguity.
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    finally:
        if stream is not None:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                pass
            try:
                stream.close()  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                pass
        elif journal_descriptor is not None:
            os.close(journal_descriptor)
        if run_descriptor is not None:
            os.close(run_descriptor)


def _operation_run_id(operation: str, run_id: object) -> str:
    if not _valid_run_id(run_id):
        raise CoordinationRefusal(f"forge: {operation} refused — invalid run id")
    return str(run_id)


def _operation_scope(operation: str, values: object) -> tuple[str, ...]:
    try:
        scope = canonical_scope(values)
    except CoordinationRefusal as exc:
        raise CoordinationRefusal(f"forge: {operation} refused — invalid scope") from exc
    if not isinstance(values, (list, tuple)) or tuple(values) != scope:
        raise CoordinationRefusal(f"forge: {operation} refused — invalid scope")
    return scope


def _target_state(
    view: CoordinationView,
    run_id: str,
    operation: str,
    *,
    allow_reserving_retired_close: bool = False,
) -> RunState:
    state = view.states.get(run_id)
    if state is None:
        raise CoordinationRefusal(
            f"forge: {operation} refused — run {run_id} does not exist"
        )
    if state.disposition == "closed":
        raise CoordinationRefusal(
            f"forge: {operation} refused — run {run_id} is closed"
        )
    if state.disposition == "retired":
        reserving_leaf = view.reservations.get(run_id)
        if not (
            allow_reserving_retired_close
            and state.successor_of is not None
            and reserving_leaf is not None
            and reserving_leaf.disposition == "retired"
        ):
            raise CoordinationRefusal(
                f"forge: {operation} refused — run {run_id} is retired"
            )
    return state


def _conflict_refusal(
    run_id: str,
    scope: tuple[str, ...],
    reservations: dict[str, ScopeReservation],
    *,
    excluded: frozenset[str] = frozenset(),
) -> None:
    conflicts: list[tuple[str, str]] = []
    for other_id, reservation in reservations.items():
        if other_id in excluded or not scopes_overlap(scope, reservation.scope):
            continue
        if reservation.disposition == "open":
            diagnostic = (
                f"forge: new run refused — scope overlap between {run_id} and open run "
                f"{other_id}"
            )
        else:
            diagnostic = (
                f"forge: new run refused — scope overlap between {run_id} and "
                f"scope-reserving retired run {other_id}"
            )
        conflicts.append((other_id, diagnostic))
    if conflicts:
        raise CoordinationRefusal(
            "\n".join(line for _, line in sorted(conflicts, key=lambda item: _byte_key(item[0])))
        )


def _rollback_registry_failure(stream: object, offset: int, failure: BaseException) -> None:
    try:
        _rollback_append(stream, offset)
    except CoordinationRefusal as exc:
        raise CoordinationRefusal(JOURNAL_ROLLBACK_FAILED) from exc
    if isinstance(failure, CoordinationRefusal):
        raise failure
    raise CoordinationRefusal(REGISTRY_UPDATE_FAILED) from failure


def _preflight_existing_candidate(
    state_root: Path,
    run_id: str,
    operation: str,
    candidate: dict[str, object],
    *,
    repository: Path | None = None,
) -> tuple[RunState, Path]:
    """Perform the read-only candidate checks that precede DM-010 identity."""

    run_dir = state_root / ".codex-orchestrator/runs" / run_id
    try:
        os.lstat(run_dir)
    except FileNotFoundError as exc:
        raise CoordinationRefusal(
            f"forge: {operation} refused — run {run_id} does not exist"
        ) from exc
    except OSError as exc:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
    state = _scan_run(run_dir)
    if repository is None:
        repository = _recorded_repository_root(
            state.run_dir, state_root, records=state.records
        )
    _validate_append_citations(repository, state.run_dir, candidate)
    _validate_citation_targets(candidate, list(state.records))
    return state, repository


def append_owned_record(journal: Path, record: object) -> None:
    """Append one record only after the current session proves DM-010 ownership."""

    candidate = _validate_record_envelope(record)
    supplied = Path(os.path.abspath(os.fspath(journal.expanduser())))
    run_dir = supplied.parent
    run_id = _operation_run_id("journal append", run_dir.name)
    repository_probe = run_dir
    while not repository_probe.exists() and repository_probe.parent != repository_probe:
        repository_probe = repository_probe.parent
    _, state_root = _resolve_repository(repository_probe, "journal append")
    expected = state_root / ".codex-orchestrator/runs" / run_id / "journal.jsonl"
    if supplied != expected:
        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
    _preflight_existing_candidate(
        state_root, run_id, "journal append", candidate
    )
    current = _session_owner()
    with _registry_lock(state_root) as registry_lock:
        view = _coordination_view(
            state_root,
            owner_target_ids=frozenset({run_id}),
            locked=registry_lock,
        )
        state = _target_state(view, run_id, "journal append")
        repository = _recorded_repository_root(
            state.run_dir, state_root, records=state.records
        )
        with _locked_journal(state) as locked:
            prior = state.records
            _validate_append_citations(repository, state.run_dir, candidate)
            _validate_citation_targets(candidate, list(prior))
            owner = _classify_owner(
                state,
                current,
                adopt_missing=state.pre_coordination,
                locked=locked,
            )
            _validate_proposed_record(
                candidate,
                run_id=run_id,
                repo_root=repository,
                scope=view.open_runs[run_id],
                prior_records=prior,
            )
            if _ordinary_append_requires_lifecycle_command(candidate):
                raise CoordinationRefusal(
                    "forge: journal append refused — lifecycle command required"
                )
            payload = _journal_payload(candidate)
            with _owner_takeover_transaction(
                state,
                current,
                owner,
                adopt_missing=state.pre_coordination,
                locked=locked,
            ) as takeover:
                offset = _append_with_locked_stream(
                    locked,
                    state.run_dir,
                    run_id,
                    candidate,
                    payload=payload,
                )
                try:
                    _validate_registry_lock(state_root, registry_lock)
                    if (
                        _read_registry_snapshot(
                            state_root, locked=registry_lock
                        )
                        != view.registry
                    ):
                        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                    _validate_owner_takeover(locked, takeover)
                except BaseException:
                    _rollback_append(locked, offset)
                    raise


def open_run(
    repo: Path,
    run_id: str,
    scope_values: list[str],
    record: object,
    *,
    successor_of: str | None = None,
) -> Path:
    candidate = _validate_record_envelope(record)
    run_id = _operation_run_id("new run", run_id)
    repository, state_root = _resolve_repository(repo, "new run")
    scope = _operation_scope("new run", scope_values)
    target = state_root / ".codex-orchestrator/runs" / run_id
    opening = dict(candidate)
    opening["scope"] = list(scope)
    proposed_successor = opening.get("successor_of", _MISSING)
    if successor_of is not None:
        opening["successor_of"] = successor_of
    _validate_append_citations(repository, target, opening)
    _validate_citation_targets(opening, [])
    current = _session_owner()
    with _registry_lock(state_root) as registry_lock:
        predecessor_target = (
            frozenset({successor_of})
            if successor_of is not None and _valid_run_id(successor_of)
            else frozenset()
        )
        view = _coordination_view(
            state_root,
            owner_target_ids=predecessor_target,
            locked=registry_lock,
        )
        if run_id in view.states:
            raise CoordinationRefusal(
                f"forge: new run refused — run {run_id} already exists"
            )
        if run_id in view.placeholders:
            raise CoordinationRefusal(
                f"forge: new run refused — run {run_id} directory exists without journal.jsonl"
            )
        _validate_append_citations(repository, target, opening)
        _validate_citation_targets(opening, [])
        predecessor_owner: OwnerClassification | None = None
        predecessor: RunState | None = None
        predecessor_reservation: ScopeReservation | None = None
        if successor_of is not None and _valid_run_id(successor_of):
            predecessor = view.states.get(successor_of)
            predecessor_reservation = view.reservations.get(successor_of)
            if (
                "transfer" not in SUCCESSOR_DAG_CONTROLS
                or predecessor is None
                or predecessor.disposition != "retired"
                or predecessor_reservation is None
                or predecessor_reservation.disposition != "retired"
            ):
                raise CoordinationRefusal(
                    f"forge: successor run refused — predecessor {successor_of} is not a "
                    "scope-reserving retired run"
                )
            predecessor_owner = _classify_owner(predecessor, current)
        _validate_proposed_record(
            opening,
            run_id=run_id,
            repo_root=repository,
            scope=scope,
        )
        if (
            (successor_of is None and proposed_successor is not _MISSING)
            or (
                successor_of is not None
                and proposed_successor is not _MISSING
                and proposed_successor != successor_of
            )
        ):
            _invalid_record_field(
                "run_started", "successor_of", "must match designated predecessor"
            )
        if opening.get("type") != "run_started":
            raise CoordinationRefusal(
                "forge: journal append refused — lifecycle command required"
            )
        opening_payload = _journal_payload(opening)
        if predecessor_reservation is not None:
            if not scopes_overlap(scope, predecessor_reservation.scope):
                raise CoordinationRefusal(
                    f"forge: successor run refused — scope of {run_id} does not overlap "
                    f"scope-reserving retired run {predecessor_reservation.run_id}"
                )
        excluded = frozenset({successor_of}) if successor_of is not None else frozenset()
        _conflict_refusal(run_id, scope, view.reservations, excluded=excluded)
        _assert_coordination_view_unchanged(
            state_root, view, locked=registry_lock
        )
        if predecessor is not None and predecessor_owner is not None:
            refreshed = _classify_owner(predecessor, current)
            if refreshed != predecessor_owner:
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        runs_root = state_root / ".codex-orchestrator/runs"
        try:
            runs_root.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CoordinationRefusal(
                "forge: journal append refused — journal write failed"
            ) from exc
        runs_descriptor: int | None = None
        target_descriptor: int | None = None
        target_observation: FileObservation | None = None
        runs_root_observation: FileObservation | None = None
        created: dict[str, tuple[FileObservation, bytes]] = {}
        runs_parent_descriptor: int | None = None
        try:
            runs_parent_descriptor, _ = _open_bound_directory(runs_root.parent)
            if view.runs_root_observation is None:
                try:
                    os.mkdir("runs", 0o700, dir_fd=runs_parent_descriptor)
                except FileExistsError as exc:
                    raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
            root_stat = os.stat(
                "runs",
                dir_fd=runs_parent_descriptor,
                follow_symlinks=False,
            )
            runs_descriptor, runs_root_observation = _open_bound_child_directory(
                runs_parent_descriptor, "runs", root_stat
            )
            if (
                view.runs_root_observation is not None
                and runs_root_observation != view.runs_root_observation
            ):
                raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
        except CoordinationRefusal:
            if runs_descriptor is not None:
                os.close(runs_descriptor)
                runs_descriptor = None
            raise
        except OSError as exc:
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
        finally:
            if runs_parent_descriptor is not None:
                os.close(runs_parent_descriptor)
        try:
            os.mkdir(run_id, 0o700, dir_fd=runs_descriptor)
        except FileExistsError as exc:
            classification = _classify_late_run_target(
                runs_descriptor, run_id
            )
            if runs_descriptor is not None:
                os.close(runs_descriptor)
                runs_descriptor = None
            if classification == "empty":
                raise CoordinationRefusal(
                    f"forge: new run refused — run {run_id} directory exists "
                    "without journal.jsonl"
                ) from exc
            if classification == "nonempty":
                raise CoordinationRefusal(
                    "forge: new run refused — run directory "
                    f".codex-orchestrator/runs/{run_id} lacks journal.jsonl"
                ) from exc
            raise CoordinationRefusal(REGISTRY_UNAVAILABLE) from exc
        except OSError as exc:
            if runs_descriptor is not None:
                os.close(runs_descriptor)
                runs_descriptor = None
            raise CoordinationRefusal(
                "forge: journal append refused — journal write failed"
            ) from exc
        try:
            assert runs_descriptor is not None
            target_stat = os.stat(
                run_id, dir_fd=runs_descriptor, follow_symlinks=False
            )
            target_descriptor, target_observation = _open_bound_child_directory(
                runs_descriptor, run_id, target_stat
            )
            if os.listdir(target_descriptor):
                raise OSError(errno.EEXIST, "claimed run directory is not empty")
            owner_payload = _owner_bytes(current)
            created["owner"] = (
                _write_exclusive_at(target_descriptor, "owner", owner_payload),
                owner_payload,
            )
            created["journal.jsonl"] = (
                _write_exclusive_at(
                    target_descriptor, "journal.jsonl", opening_payload
                ),
                opening_payload,
            )
            assert runs_root_observation is not None
            assert target_observation is not None
            claim = NewRunClaim(
                run_id,
                runs_root_observation,
                target_observation,
                tuple(
                    (name, observation, payload)
                    for name, (observation, payload) in created.items()
                ),
            )
            updated = dict(view.open_runs)
            updated[run_id] = scope
            _write_registry(
                state_root,
                updated,
                view=view,
                changed_run_id=run_id,
                appended_record=opening,
                expected_owner=current,
                locked=registry_lock,
                expected_runs_root=runs_root_observation,
                new_run_claim=claim,
            )
        except RegistryRestorationRefusal:
            # Registry authority is ambiguous; retaining the candidate run is
            # safer than manufacturing a known journal/registry mismatch.
            raise
        except BaseException as exc:
            cleanup_succeeded = bool(
                target_descriptor is not None
                and target_observation is not None
                and runs_descriptor is not None
                and _cleanup_claimed_run(
                    runs_descriptor,
                    run_id,
                    target_descriptor,
                    target_observation,
                    created,
                )
            )
            if not cleanup_succeeded:
                raise CoordinationRefusal(JOURNAL_ROLLBACK_FAILED) from exc
            if isinstance(exc, CoordinationRefusal):
                raise
            diagnostic = (
                REGISTRY_UPDATE_FAILED
                if "journal.jsonl" in created
                else "forge: journal append refused — journal write failed"
            )
            raise CoordinationRefusal(diagnostic) from exc
        finally:
            if target_descriptor is not None:
                try:
                    os.close(target_descriptor)
                except OSError:
                    pass
            if runs_descriptor is not None:
                try:
                    os.close(runs_descriptor)
                except OSError:
                    pass
        return target


def append_run_record(repo: Path, run_id: str, record: object) -> None:
    candidate = _validate_record_envelope(record)
    run_id = _operation_run_id("journal append", run_id)
    _, state_root = _resolve_repository(repo, "journal append")
    _preflight_existing_candidate(
        state_root, run_id, "journal append", candidate
    )
    current = _session_owner()
    with _registry_lock(state_root) as registry_lock:
        view = _coordination_view(
            state_root,
            owner_target_ids=frozenset({run_id}),
            locked=registry_lock,
        )
        state = _target_state(view, run_id, "journal append")
        repository = _recorded_repository_root(
            state.run_dir, state_root, records=state.records
        )
        with _locked_journal(state) as locked:
            prior = state.records
            _validate_append_citations(repository, state.run_dir, candidate)
            _validate_citation_targets(candidate, list(prior))
            owner = _classify_owner(
                state,
                current,
                adopt_missing=state.pre_coordination,
                locked=locked,
            )
            _validate_proposed_record(
                candidate,
                run_id=run_id,
                repo_root=repository,
                scope=view.open_runs[run_id],
                prior_records=prior,
            )
            if _ordinary_append_requires_lifecycle_command(candidate):
                raise CoordinationRefusal(
                    "forge: journal append refused — lifecycle command required"
                )
            payload = _journal_payload(candidate)
            with _owner_takeover_transaction(
                state,
                current,
                owner,
                adopt_missing=state.pre_coordination,
                locked=locked,
            ) as takeover:
                offset = _append_with_locked_stream(
                    locked,
                    state.run_dir,
                    run_id,
                    candidate,
                    payload=payload,
                )
                try:
                    _validate_registry_lock(state_root, registry_lock)
                    if (
                        _read_registry_snapshot(
                            state_root, locked=registry_lock
                        )
                        != view.registry
                    ):
                        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)
                    _validate_owner_takeover(locked, takeover)
                except BaseException:
                    _rollback_append(locked, offset)
                    raise


def readmit_run(repo: Path, run_id: str, scope_values: list[str]) -> None:
    run_id = _operation_run_id("run readmit", run_id)
    repository, state_root = _resolve_repository(repo, "run readmit")
    scope = _operation_scope("run readmit", scope_values)
    record = _validate_record_envelope(
        {
            "type": "decision",
            "id": f"forge-scope-readmission-{uuid.uuid4().hex}",
            "resolution": READMISSION_RESOLUTION,
            "scope": list(scope),
            "recorded_at": _utc_now(),
        }
    )
    current = _session_owner()
    with _registry_lock(state_root) as registry_lock:
        view = _coordination_view(
            state_root,
            owner_target_ids=frozenset({run_id}),
            locked=registry_lock,
        )
        state = _target_state(view, run_id, "run readmit")
        with _locked_journal(state) as locked:
            prior = state.records
            _validate_append_citations(repository, state.run_dir, record)
            _validate_citation_targets(record, list(prior))
            owner = _classify_owner(
                state,
                current,
                adopt_missing=state.pre_coordination,
                locked=locked,
            )
            _validate_proposed_record(
                record,
                run_id=run_id,
                repo_root=repository,
                scope=scope,
                prior_records=prior,
            )
            if not _all_task_files_contained(list(prior), scope):
                raise CoordinationRefusal(
                    f"forge: journal append refused — task files exceed admitted scope "
                    f"for run {run_id}"
                )
            _conflict_refusal(
                run_id,
                scope,
                view.reservations,
                excluded=frozenset({run_id}),
            )
            payload = _journal_payload(record)
            with _owner_takeover_transaction(
                state,
                current,
                owner,
                adopt_missing=state.pre_coordination,
                locked=locked,
            ):
                offset = _append_with_locked_stream(
                    locked,
                    state.run_dir,
                    run_id,
                    record,
                    payload=payload,
                )
                try:
                    updated = dict(view.open_runs)
                    updated[run_id] = scope
                    _write_registry(
                        state_root,
                        updated,
                        view=view,
                        changed_run_id=run_id,
                        appended_record=record,
                        expected_owner=current,
                        locked=registry_lock,
                        expected_runs_root=view.runs_root_observation,
                    )
                except RegistryRestorationRefusal:
                    raise
                except BaseException as exc:
                    _rollback_registry_failure(locked, offset, exc)


def close_run(repo: Path, run_id: str, record: object) -> None:
    candidate = _validate_record_envelope(record)
    run_id = _operation_run_id("run close", run_id)
    repository, state_root = _resolve_repository(repo, "run close")
    _preflight_existing_candidate(
        state_root,
        run_id,
        "run close",
        candidate,
        repository=repository,
    )
    current = _session_owner()
    with _registry_lock(state_root) as registry_lock:
        view = _coordination_view(
            state_root,
            owner_target_ids=frozenset({run_id}),
            locked=registry_lock,
        )
        state = _target_state(
            view,
            run_id,
            "run close",
            allow_reserving_retired_close=True,
        )
        with _locked_journal(state) as locked:
            prior = state.records
            _validate_append_citations(repository, state.run_dir, candidate)
            _validate_citation_targets(candidate, list(prior))
            owner = _classify_owner(
                state,
                current,
                adopt_missing=state.pre_coordination,
                locked=locked,
            )
            _validate_proposed_record(
                candidate,
                run_id=run_id,
                repo_root=repository,
                scope=state.scope,
                prior_records=prior,
            )
            if candidate.get("type") != "run_closed":
                raise CoordinationRefusal(
                    "forge: journal append refused — lifecycle command required"
                )
            payload = _journal_payload(candidate)
            with _owner_takeover_transaction(
                state,
                current,
                owner,
                adopt_missing=state.pre_coordination,
                locked=locked,
            ):
                offset = _append_with_locked_stream(
                    locked,
                    state.run_dir,
                    run_id,
                    candidate,
                    payload=payload,
                )
                try:
                    updated = dict(view.open_runs)
                    updated.pop(run_id, None)
                    _write_registry(
                        state_root,
                        updated,
                        view=view,
                        changed_run_id=run_id,
                        appended_record=candidate,
                        expected_owner=current,
                        locked=registry_lock,
                        expected_runs_root=view.runs_root_observation,
                    )
                except RegistryRestorationRefusal:
                    raise
                except BaseException as exc:
                    _rollback_registry_failure(locked, offset, exc)


def retire_run(repo: Path, run_id: str) -> None:
    run_id = _operation_run_id("run retire", run_id)
    record = _validate_record_envelope(
        {
            "type": "decision",
            "id": "forge-run-retired",
            "resolution": RETIREMENT_RESOLUTION,
            "recorded_at": _utc_now(),
        }
    )
    current = _session_owner()
    repository, state_root = _resolve_repository(repo, "run retire")
    with _registry_lock(state_root) as registry_lock:
        view = _coordination_view(
            state_root,
            owner_target_ids=frozenset({run_id}),
            locked=registry_lock,
        )
        state = _target_state(view, run_id, "run retire")
        if state.pre_coordination:
            # Retirement exists so a successor can reuse an admitted scope; a
            # pre-coordination run has none, and its retired state (scope-less,
            # not closed) would poison every future scan. The state machine for
            # such runs is adopt -> close (or readmit to a real scope first).
            raise CoordinationRefusal(
                "forge: run retire refused — pre-coordination run "
                f"{run_id} has no admitted scope to reuse; adopt and close it instead"
            )
        with _locked_journal(state) as locked:
            prior = state.records
            _validate_append_citations(repository, state.run_dir, record)
            _validate_citation_targets(record, list(prior))
            owner = _classify_owner(
                state,
                current,
                adopt_missing=state.pre_coordination,
                locked=locked,
            )
            _validate_proposed_record(
                record,
                run_id=run_id,
                repo_root=repository,
                scope=state.scope,
                prior_records=prior,
            )
            payload = _journal_payload(record)
            with _owner_takeover_transaction(
                state,
                current,
                owner,
                adopt_missing=state.pre_coordination,
                locked=locked,
            ):
                offset = _append_with_locked_stream(
                    locked,
                    state.run_dir,
                    run_id,
                    record,
                    payload=payload,
                )
                try:
                    updated = dict(view.open_runs)
                    updated.pop(run_id, None)
                    _write_registry(
                        state_root,
                        updated,
                        view=view,
                        changed_run_id=run_id,
                        appended_record=record,
                        expected_owner=current,
                        locked=registry_lock,
                        expected_runs_root=view.runs_root_observation,
                    )
                except RegistryRestorationRefusal:
                    raise
                except BaseException as exc:
                    _rollback_registry_failure(locked, offset, exc)


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


# forge: modified from upstream — apply only explicitly declared pre-cutover compatibility legs
def _legacy_compatibility_declaration(
    records: list[dict[str, object]],
) -> dict[str, object] | None:
    for record in records:
        resolution = record.get("resolution")
        if (
            record.get("type") == "decision"
            and record.get("id") == LEGACY_COMPATIBILITY_DECLARATION_ID
            and isinstance(resolution, str)
            and resolution.startswith(LEGACY_COMPATIBILITY_RESOLUTION_PREFIX)
            and "\n" not in resolution
            and "\r" not in resolution
            and resolution[len(LEGACY_COMPATIBILITY_RESOLUTION_PREFIX) :].strip()
        ):
            return record
    return None


def _legacy_allows(
    leg: str, declaration_line: int | None, *records: dict[str, object]
) -> bool:
    return (
        leg in LEGACY_COMPATIBILITY_LEGS
        and declaration_line is not None
        and bool(records)
        and all(
            isinstance(record.get("_line"), int)
            and int(record["_line"]) < declaration_line
            for record in records
        )
    )


def _legacy_warning(record: dict[str, object], detail: str) -> str:
    return f"{record_line(record)}: legacy compatibility {detail}"


def _declared_path_is_missing(run_dir: Path, value: str) -> bool:
    try:
        return not resolve_run_path(run_dir, value).exists()
    except (OSError, RuntimeError, ValueError):
        return False


def check_declared_file(
    run_dir: Path,
    record: dict[str, object],
    field: str,
    issues: list[str],
    warnings: list[str],
    declaration_line: int | None,
) -> None:
    if field not in record:
        return
    value = record.get(field)
    if not isinstance(value, str):
        issues.append(f"{record_line(record)}: {field} must name a file")
        return
    if not value:
        if field == "events" and _legacy_allows(
            "empty-events", declaration_line, record
        ):
            warnings.append(
                _legacy_warning(
                    record,
                    "tolerated empty events reference; interpreted as an unavailable "
                    "legacy event stream",
                )
            )
        else:
            issues.append(f"{record_line(record)}: {field} must name a file")
        return
    if not declared_file_exists(run_dir, value):
        if _legacy_allows(
            "missing-execution-file", declaration_line, record
        ) and _declared_path_is_missing(run_dir, value):
            warnings.append(
                _legacy_warning(
                    record,
                    f"tolerated missing {field} file {value!r}; interpreted as "
                    "unavailable legacy execution metadata",
                )
            )
        else:
            issues.append(
                f"{record_line(record)}: referenced {field} file does not exist: {value}"
            )


# forge: modified from upstream — add opt-in checks over the existing journal schema
def check_gate_profile(
    records: list[dict[str, object]],
    issues: list[str],
    warnings: list[str],
    declaration_line: int | None,
) -> None:
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
        # These are the semantic records: the baseline checks have already
        # normalized a tolerated pre-declaration legacy status to its terminal
        # mapping, so a mapped result both counts as terminal and anchors the
        # last-result line here without any further tolerance.
        terminal_results = [
            record
            for record in records
            if record.get("type") == "execution_result"
            and record.get("status") in TERMINAL_EXECUTION_STATUSES
            and execution_key(record) in mutating_keys
        ]
        terminal_result_keys = {execution_key(record) for record in terminal_results}
        # The baseline checks already tolerate a pre-declaration execution
        # with no terminal result (missing-execution-result leg) and emit its
        # warning there; the veto honors the same tolerance, or a legacy
        # journal whose history left executions unterminated could never
        # close with passing gates.
        has_unterminated_mutation = any(
            execution_key(record) not in terminal_result_keys
            and not _legacy_allows(
                "missing-execution-result", declaration_line, record
            )
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
            message = (
                f"failed gate verification '{verification.get('id')}' "
                "has no subsequent passing recheck"
            )
            if _legacy_allows(
                "failed-gate-recheck", declaration_line, verification
            ):
                warnings.append(
                    _legacy_warning(
                        verification,
                        f"tolerated {message}; retained as a non-passing verification",
                    )
                )
            else:
                issues.append(message)


# forge: modified from upstream — accept the opt-in Level B gate profile
def validate_run(
    run_dir: Path,
    *,
    gates: bool = False,
    closed_legacy_compat: str | None = None,
) -> dict[str, object]:
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

    declaration = _legacy_compatibility_declaration(records)
    declaration_line_value = declaration.get("_line") if declaration is not None else None
    declaration_line = (
        int(declaration_line_value) if isinstance(declaration_line_value, int) else None
    )
    if declaration is not None:
        resolution = str(declaration["resolution"])
        justification = resolution[len(LEGACY_COMPATIBILITY_RESOLUTION_PREFIX) :]
        warnings.append(
            _legacy_warning(
                declaration,
                f"declaration active: {justification}",
            )
        )

    # forge: modified from upstream — FR-018(a) operator-directed closed-run keying.
    # The flag re-keys the identical FR-016 posture for a journal that can no longer
    # carry an in-journal declaration: the virtual declaration point sits immediately
    # before run_closed, so every earlier record is pre-declaration and run_closed
    # itself stays fully strict. The flag grants nothing while the dispensation leg
    # is disabled in memory, and it refuses outright when the journal has no
    # run_closed entry — for open runs the in-journal declaration remains the only
    # path. The justification grammar (nonempty single line, CR/LF forbidden) is the
    # caller's contract, revalidated here so no surface can widen it.
    if closed_legacy_compat is not None:
        if "closed-legacy-compat" in CLOSED_RUN_DISPENSATION_LEGS:
            stripped = closed_legacy_compat.strip()
            if (
                not stripped
                or "\r" in closed_legacy_compat
                or "\n" in closed_legacy_compat
            ):
                raise CoordinationRefusal(
                    "forge: closed-legacy-compat refused — justification must be a "
                    "nonempty single line"
                )
            closures = [
                record
                for record in records
                if record.get("type") == "run_closed"
                and isinstance(record.get("_line"), int)
            ]
            if not closures:
                raise CoordinationRefusal(CLOSED_LEGACY_COMPAT_REFUSAL)
            virtual_line = int(closures[-1]["_line"])
            if declaration_line is None or virtual_line > declaration_line:
                declaration_line = virtual_line
            warnings.append(
                f"line {virtual_line}: legacy compatibility closed-run flag active: "
                f"{stripped}"
            )

    raw_known_records: list[dict[str, object]] = []
    known_records: list[dict[str, object]] = []
    for index, raw_record in enumerate(records):
        kind = raw_record.get("type")
        if not isinstance(kind, str) or kind not in JOURNAL_ENTRY_TYPES:
            if kind == "observation" and _legacy_allows(
                "observation", declaration_line, raw_record
            ):
                warnings.append(
                    _legacy_warning(
                        raw_record,
                        "tolerated observation entry; excluded from semantic validation",
                    )
                )
            else:
                issues.append(
                    f"{record_line(raw_record)}: unknown journal entry type: {kind!r}"
                )
        else:
            raw_known_records.append(raw_record)
            try:
                _validate_citation_targets(raw_record, records[:index])
            except CoordinationRefusal as exc:
                issues.append(f"{record_line(raw_record)}: {exc}")

            record = dict(raw_record)
            if kind == "execution_result":
                status = record.get("status")
                mapped_status = (
                    LEGACY_EXECUTION_STATUS_MAP.get(status)
                    if isinstance(status, str)
                    else None
                )
                if mapped_status is not None and _legacy_allows(
                    "execution-result-status", declaration_line, raw_record
                ):
                    record["status"] = mapped_status
                    warnings.append(
                        _legacy_warning(
                            raw_record,
                            f"interpreted execution_result status {status!r} as status "
                            f"{mapped_status!r}",
                        )
                    )
            elif kind == "verification":
                result = record.get("result")
                if result == "pass" and _legacy_allows(
                    "verification-pass", declaration_line, raw_record
                ):
                    record["result"] = "passed"
                    warnings.append(
                        _legacy_warning(
                            raw_record,
                            "interpreted verification result 'pass' as 'passed'",
                        )
                    )
                elif (
                    "result" not in record
                    and record.get("status") == "pass"
                    and _legacy_allows(
                        "verification-pass", declaration_line, raw_record
                    )
                ):
                    record["result"] = "passed"
                    warnings.append(
                        _legacy_warning(
                            raw_record,
                            "interpreted verification result from status 'pass' with no "
                            "result as 'passed'",
                        )
                    )
                evidence = record.get("evidence")
                if (
                    isinstance(evidence, str)
                    and bool(evidence)
                    and _legacy_allows("string-evidence", declaration_line, raw_record)
                ):
                    record["evidence"] = [evidence]
                    warnings.append(
                        _legacy_warning(
                            raw_record,
                            f"interpreted string evidence {evidence!r} as a singleton list",
                        )
                    )
            known_records.append(record)

    starts = [
        record for record in raw_known_records if record.get("type") == "run_started"
    ]
    closures = [
        record for record in raw_known_records if record.get("type") == "run_closed"
    ]
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
    verification_occurrences: dict[str, list[dict[str, object]]] = {}
    for record in known_records:
        if record.get("type") != "verification":
            continue
        record_id = record.get("id")
        if isinstance(record_id, str) and record_id:
            verification_occurrences.setdefault(record_id, []).append(record)
    compatible_duplicate_verifications = {
        record_id
        for record_id, occurrences in verification_occurrences.items()
        if len(occurrences) > 1
        and _legacy_allows(
            "duplicate-verification-id", declaration_line, *occurrences
        )
    }
    warned_duplicate_verifications: set[str] = set()

    for record in known_records:
        kind = record.get("type")
        if kind in seen_ids:
            record_id = record.get("id")
            if isinstance(record_id, str) and record_id:
                if record_id in seen_ids[kind]:
                    if (
                        kind == "verification"
                        and record_id in compatible_duplicate_verifications
                    ):
                        if record_id not in warned_duplicate_verifications:
                            occurrence_lines = ", ".join(
                                str(occurrence["_line"])
                                for occurrence in verification_occurrences[record_id]
                            )
                            warnings.append(
                                _legacy_warning(
                                    record,
                                    f"tolerated duplicate verification id {record_id}; "
                                    f"occurrences at lines {occurrence_lines}",
                                )
                            )
                            warned_duplicate_verifications.add(record_id)
                    else:
                        issues.append(
                            f"{record_line(record)}: duplicate {kind} id {record_id}"
                        )
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
            check_declared_file(
                run_dir, record, "prompt", issues, warnings, declaration_line
            )
            check_declared_file(
                run_dir, record, "events", issues, warnings, declaration_line
            )
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

    for key, execution in executions.items():
        result = execution_results.get(key)
        if result is None:
            continue
        task_id = execution.get("task")
        result_task = result.get("task")
        if (
            isinstance(task_id, str)
            and isinstance(result_task, str)
            and result_task != task_id
            and task_id in tasks
            and result_task in tasks
            and _legacy_allows(
                "execution-task-mismatch", declaration_line, execution, result
            )
        ):
            result["task"] = task_id
            warnings.append(
                _legacy_warning(
                    result,
                    f"interpreted execution_result task {result_task!r} as execution "
                    f"task {task_id!r}",
                )
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
            message = f"execution {display_execution(key)} has no terminal execution_result"
            if _legacy_allows(
                "missing-execution-result", declaration_line, execution
            ):
                warnings.append(
                    _legacy_warning(
                        execution,
                        f"tolerated {message}; interpreted as an unterminated historical "
                        "execution",
                    )
                )
            else:
                issues.append(message)
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
        check_gate_profile(known_records, issues, warnings, declaration_line)

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
