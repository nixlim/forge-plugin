#!/usr/bin/env python3
"""Render and stage the deterministic durable-intent archive for a closed run."""

from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
import html
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

# Use the journal reader shared by validation. The script lives one directory
# below the import root when installed by the plugin.
SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from codex_orchestrator import builders as journal_builders
from codex_orchestrator import journal as journal_engine
from codex_orchestrator.chain_paths import chain_storage_root
from codex_orchestrator.journal import (
    read_journal as read_shared_journal,
    validate_run,
)
from commitment_paths import (
    commitment_surface,
    parse_run_captured_path,
    path_tokens,
    validate_surface_path,
)


CONTAMINATION = "forge: archive refused — close tree contains unrelated changes"
LEGACY_APPROVAL_REFUSAL = (
    "forge: archive refused — legacy recovery approval missing or mismatched"
)
NONE = "None recorded"
UNBOUND = "UNBOUND"
HEX_HEAD = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
LEARNING_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
HEAD_IN_TEXT = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?:[0-9a-f]{24})?(?![0-9a-f])")
HEAD_RANGE_IN_TEXT = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{40}(?:[0-9a-f]{24})?"
    r"\.\."
    r"[0-9a-f]{40}(?:[0-9a-f]{24})?(?![0-9a-f])"
)
ITERATION_IN_TEXT = re.compile(r"\biteration\s+(\d+)\b", re.IGNORECASE)
VERDICT_IN_TEXT = re.compile(r"\b(PASS|BLOCK)\b")
LEGACY_STAGED_REVIEW = re.compile(
    r"^review-final (?:subagent|confirmation round) over staged diff "
    r"(?P<candidate>[0-9a-f]{64})$"
)
LEGACY_RANGE_REVIEW = re.compile(
    r"^review-final (?:(?:subagent|merge-composition review) )?over git diff "
    r"(?P<base>[0-9a-f]{40}(?:[0-9a-f]{24})?)\.\.\."
    r"(?P<head>[0-9a-f]{40}(?:[0-9a-f]{24})?)$"
)
LEGACY_TWO_DOT_REVIEW = re.compile(
    r"^review-final over git diff "
    r"(?P<base>[0-9a-f]{40}(?:[0-9a-f]{24})?)\.\."
    r"(?P<head>[0-9a-f]{40}(?:[0-9a-f]{24})?)$"
)
LEGACY_REVIEW_OBSERVATION = re.compile(
    r"^(?P<verdict>PASS|BLOCK); [0-9]+ CRITICAL/MAJOR findings; "
    r"severities CRITICAL=[0-9]+,MAJOR=[0-9]+,MINOR=[0-9]+; "
    r"reviewer review-final; iteration (?P<iteration>[1-9][0-9]*) of 8\."
    r"(?: [^\r\n]*)?$"
)
LEGACY_SHORT_REVIEW_OBSERVATION = re.compile(
    r"^(?P<verdict>PASS|BLOCK); [0-9]+ CRITICAL/MAJOR findings; "
    r"iteration (?P<iteration>[1-9][0-9]*) of 8\.$"
)
CHAIN_ID_IN_TEXT = re.compile(
    r"(?<![A-Za-z0-9_.-])c-\d{4}-\d{2}-\d{2}T\d{6}Z-[0-9a-f]{4}"
    r"(?![A-Za-z0-9_.-])"
)
LEGACY_APPROVAL = re.compile(
    r"^(?P<run>[A-Za-z0-9][A-Za-z0-9._-]{0,127}):"
    r"(?P<decision>[A-Za-z0-9][A-Za-z0-9._-]{0,127})$"
)

WRITER_CONTRACT = "forge-journal-binding/1"
CHAIN_STATE_SCHEMA = "forge-chain/1"
MERGE_STATE_SCHEMA = "forge-merge-chain/1"
CHAIN_STATE_MARKER = "FORGE:CHAIN-STATE"
CHAIN_EVIDENCE_MARKER = "FORGE:CHAIN-EVIDENCE"
EVENT_EMBED_LIMIT = 2_097_152
ARCHIVE_SIZE_LIMIT = 16_777_216

# DM-001 is a closed control enum.  The disposition set is deliberately
# separate so a newly-added spelling cannot silently become display-only.
DISCREPANCY_CODES = (
    "ambiguous_legacy_candidate",
    "ignored_nonreview_verdict",
    "legacy_decision_shape",
    "missing_chain_artifact",
    "result_verdict_conflict",
    "snapshot_changed",
    "structured_chain_mismatch",
    "unbound_approval",
)
AUTHORITATIVE_DISCREPANCIES = frozenset(
    {
        "structured_chain_mismatch",
        "result_verdict_conflict",
        "unbound_approval",
        "missing_chain_artifact",
        "snapshot_changed",
    }
)
LEGACY_DISPLAY_DISCREPANCIES = frozenset(DISCREPANCY_CODES) - AUTHORITATIVE_DISCREPANCIES
RENDERER_CONTROLS = frozenset(
    {
        "binding-only",
        "closed-discrepancies",
        "chain-snapshot",
        "chain-replay",
        "archive-size",
        "legacy-approval",
        "candidate-rerender",
        "merge-reducer",
        "basis-snapshot",
        "carried-record-equality",
        "html-escape",
        "captured-ingest-classification",
        "captured-ingest-replay",
        "captured-ingest-binding",
        "captured-ingest-eligibility",
    }
)


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    mode: int
    uid: int
    links: int
    size: int
    modified_ns: int


@dataclass(frozen=True)
class ExactFile:
    name: str
    raw: bytes
    identity: FileIdentity


@dataclass(frozen=True)
class ChainSnapshot:
    chain_id: str
    state_file: ExactFile
    events_file: ExactFile
    state: dict[str, object]
    events: tuple[dict[str, object], ...]
    family: str
    event_head: str
    first_at: str | None
    last_at: str | None


@dataclass(frozen=True)
class ChainPackage:
    root: Path | None
    root_identity: FileIdentity | None
    names: tuple[str, ...]
    chains: tuple[ChainSnapshot, ...]
    captured: tuple[CapturedIngestSnapshot, ...] = ()


@dataclass(frozen=True)
class Discrepancy:
    code: str
    record_line: int | None
    record_id: str
    detail: str
    chain_id: str | None = None


@dataclass(frozen=True)
class ClosingMode:
    head: str
    legacy_approval: str | None = None


@dataclass(frozen=True)
class BasisDocument:
    label: str
    content: str
    path: Path
    exact: ExactFile
    root: Path
    relative: Path
    directory_identities: tuple[tuple[str, FileIdentity], ...]


ReplayEntry = tuple[
    dict[str, object],
    dict[str, object] | None,
    dict[str, object],
    tuple[dict[str, object], ...],
    str | None,
]


@dataclass(frozen=True)
class CapturedIngestSnapshot:
    """One retrospective ingest's content-addressed, replayed authority."""

    chain: ChainSnapshot
    citations: tuple[str, str, str]
    documents: tuple[BasisDocument, BasisDocument, BasisDocument]
    outcome_map: dict[str, object]
    replay_entries: tuple[ReplayEntry, ...]
    selected_event_digests: tuple[str, ...]
    eligible_records: tuple[EligibleIngestRecord, ...]


@dataclass(frozen=True)
class EligibleIngestRecord:
    """One record independently required by replay and final chain state."""

    event_digest: str
    record_type: str
    criterion: str | None = None
    result: str | None = None
    outcome: str | None = None


class ArchiveRefusal(Exception):
    """A fail-closed archive precondition or transaction failure."""

    def __init__(self, message: str, *, contamination: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.contamination = contamination


class ContractArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ArchiveRefusal(f"forge: archive refused — invalid invocation: {message}")


def authoritative_discrepancy(code: str) -> None:
    """Refuse with the one DM-001 authoritative-discrepancy diagnostic."""

    if (
        "closed-discrepancies" not in RENDERER_CONTROLS
        or code not in AUTHORITATIVE_DISCREPANCIES
        or frozenset(DISCREPANCY_CODES)
        != AUTHORITATIVE_DISCREPANCIES | LEGACY_DISPLAY_DISCREPANCIES
    ):
        raise ArchiveRefusal("forge: archive refused — renderer discrepancy control unavailable")
    raise ArchiveRefusal(
        f"forge: archive refused — authoritative chain discrepancy: {code}"
    )


def file_identity(value: os.stat_result) -> FileIdentity:
    return FileIdentity(
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_uid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
    )


def owner_regular(value: os.stat_result) -> bool:
    return bool(
        stat.S_ISREG(value.st_mode)
        and value.st_uid == os.geteuid()
        and value.st_nlink == 1
    )


def owner_directory(value: os.stat_result) -> bool:
    return bool(stat.S_ISDIR(value.st_mode) and value.st_uid == os.geteuid())


def read_exact_file(directory: int, name: str) -> ExactFile:
    descriptor: int | None = None
    try:
        before = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if not owner_regular(before):
            authoritative_discrepancy("missing_chain_artifact")
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory,
        )
        opened = os.fstat(descriptor)
        if file_identity(opened) != file_identity(before):
            authoritative_discrepancy("snapshot_changed")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        rebound = os.stat(name, dir_fd=directory, follow_symlinks=False)
        identity = file_identity(before)
        if (
            file_identity(after) != identity
            or file_identity(rebound) != identity
            or len(raw) != before.st_size
        ):
            authoritative_discrepancy("snapshot_changed")
        return ExactFile(name, raw, identity)
    except ArchiveRefusal:
        raise
    except (OSError, ValueError):
        authoritative_discrepancy("missing_chain_artifact")
        raise AssertionError("unreachable")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def stable_journal_snapshot(run_dir: Path) -> tuple[list[dict[str, Any]], bytes]:
    """Return one reader-locked journal snapshot and its decoded records."""

    try:
        raw = journal_engine._stable_journal_read(run_dir / "journal.jsonl")
        records, issues = journal_engine._decode_journal_snapshot(
            raw, allow_partial_final_line=False
        )
    except (OSError, RuntimeError, ValueError, journal_engine.CoordinationRefusal) as exc:
        raise ArchiveRefusal("forge: archive refused — invalid run journal") from exc
    if issues:
        raise ArchiveRefusal("forge: archive refused — invalid run journal")
    return [dict(record) for record in records], raw


def journal_raw_lines(raw: bytes) -> dict[int, bytes]:
    return {
        number: line
        for number, line in enumerate(raw.splitlines(keepends=True), start=1)
    }


def _merge_event_outbox(payload: Mapping[str, object]) -> dict[str, object] | None:
    has_source = "source_event_digest" in payload
    has_batch = "journal_batch" in payload
    if not has_source and not has_batch:
        return None
    source = payload.get("source_event_digest")
    carried = payload.get("journal_batch")
    if (
        not has_source
        or not has_batch
        or not isinstance(source, str)
        or journal_engine.HEX_SHA256_PATTERN.fullmatch(source) is None
        or not isinstance(carried, dict)
        or set(carried)
        != {"idempotency_key", "batch_digest", "record_count", "records"}
        or carried.get("idempotency_key") != source
        or not isinstance(carried.get("batch_digest"), str)
        or journal_engine.HEX_SHA256_PATTERN.fullmatch(str(carried["batch_digest"]))
        is None
        or type(carried.get("record_count")) is not int
        or int(carried["record_count"]) <= 0
        or not isinstance(carried.get("records"), list)
        or len(carried["records"]) != carried["record_count"]
    ):
        raise ValueError("merge journal batch is malformed")
    return {
        "idempotency_key": source,
        "batch_digest": carried["batch_digest"],
        "record_count": carried["record_count"],
        "source_event_digest": source,
    }


def _merge_transition_reducer(
    previous: dict[str, object] | None, event: dict[str, object]
) -> dict[str, object]:
    """Rebuild DM-014 state from explicit deltas; never trust payload.state."""

    if not isinstance(event, dict) or not isinstance(event.get("payload"), dict):
        raise ValueError("merge event payload is malformed")
    payload = event["payload"]
    assert isinstance(payload, dict)
    event_name = event.get("event")
    at = event.get("at")
    if not isinstance(at, str) or not at.endswith("Z"):
        raise ValueError("merge event timestamp is malformed")
    parsed_at = dt.datetime.fromisoformat(at[:-1] + "+00:00")
    if parsed_at.tzinfo is None:
        raise ValueError("merge event timestamp is malformed")
    parsed_at = parsed_at.astimezone(dt.timezone.utc)

    if event_name == "journal_receipted":
        if previous is None or set(payload) != {
            "idempotency_key",
            "batch_digest",
            "receipt_digest",
        }:
            raise ValueError("merge receipt transition is malformed")
        state: dict[str, object] = copy.deepcopy(previous)
        state["journal_outbox"] = None
    else:
        try:
            delta = journal_builders._merge_payload_delta(event, previous)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("merge transition lacks an explicit state delta")
        assert isinstance(delta, dict)
        if previous is None:
            if event_name != "chain_started":
                raise ValueError("merge history does not start with chain_started")
            state = copy.deepcopy(delta)
        else:
            if event_name == "chain_started":
                raise ValueError("merge chain_started is not repeatable")
            state = copy.deepcopy(previous)
            for name, value in delta.items():
                state[name] = copy.deepcopy(value)
        outbox = _merge_event_outbox(payload)
        if outbox is not None:
            state["journal_outbox"] = outbox
        elif "journal_outbox" not in state:
            state["journal_outbox"] = None
    prior_deadline: dt.datetime | None = None
    if previous is not None:
        deadline = previous.get("inactive_after")
        if not isinstance(deadline, str) or not deadline.endswith("Z"):
            raise ValueError("merge prior inactivity deadline is malformed")
        prior_deadline = dt.datetime.fromisoformat(deadline[:-1] + "+00:00")
        if prior_deadline.tzinfo is None:
            raise ValueError("merge prior inactivity deadline is malformed")
        prior_deadline = prior_deadline.astimezone(dt.timezone.utc)
    state["last_event_at"] = at
    inactive = (
        prior_deadline
        if prior_deadline is not None and parsed_at >= prior_deadline
        else parsed_at + dt.timedelta(hours=24)
    )
    state["inactive_after"] = inactive.isoformat().replace("+00:00", "Z")
    return state


setattr(_merge_transition_reducer, "_forge_cli_revision9_seam", True)


def register_archive_merge_reducer() -> None:
    """Install this process's equivalent, delta-only DM-014 replay seam."""

    if "merge-reducer" not in RENDERER_CONTROLS:
        authoritative_discrepancy("structured_chain_mismatch")
    existing = journal_builders.MERGE_TRANSITION_REDUCER
    if existing is None:
        try:
            journal_builders.register_merge_transition_reducer(
                _merge_transition_reducer
            )
        except (RuntimeError, TypeError, ValueError):
            authoritative_discrepancy("structured_chain_mismatch")
    elif existing is not _merge_transition_reducer and not getattr(
        existing, "_forge_cli_revision9_seam", False
    ):
        authoritative_discrepancy("structured_chain_mismatch")


def run_git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=repo,
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise ArchiveRefusal(f"forge: archive refused — git failed: {exc}") from exc


def git_stdout(repo: Path, *arguments: str) -> bytes:
    result = run_git(repo, *arguments)
    if result.returncode != 0:
        diagnostic = result.stderr.decode("utf-8", errors="replace").strip()
        suffix = f": {diagnostic}" if diagnostic else ""
        raise ArchiveRefusal(f"forge: archive refused — git failed{suffix}")
    return result.stdout


def repository_root() -> Path:
    result = run_git(Path.cwd(), "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        raise ArchiveRefusal("forge: archive refused — current directory is not a repository")
    try:
        return Path(result.stdout.decode("utf-8").strip()).resolve(strict=True)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ArchiveRefusal("forge: archive refused — repository root is invalid") from exc


def nul_paths(value: bytes) -> list[bytes]:
    return [item for item in value.split(b"\0") if item]


def dirty_paths(repo: Path) -> list[bytes]:
    return nul_paths(
        git_stdout(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    )


def prove_clean(repo: Path) -> None:
    if dirty_paths(repo):
        raise ArchiveRefusal(CONTAMINATION, contamination=True)


def prove_clean_with_untracked_archive(repo: Path, relative: str) -> None:
    """Allow exactly one pre-rendered untracked archive and no other dirt."""

    expected = [b"?? " + os.fsencode(relative)]
    if dirty_paths(repo) != expected:
        raise ArchiveRefusal(CONTAMINATION, contamination=True)


def refuse_preexisting_archive(archive_path: Path, relative: str) -> None:
    """Retain the append-only refusal as one independently killable control."""

    if archive_path.exists() or archive_path.is_symlink():
        raise ArchiveRefusal(f"forge: archive refused — archive already exists: {relative}")


def archive_leaf(relative: str) -> str:
    parts = Path(relative).parts
    if (
        len(parts) != 4
        or parts[:3] != (".forge", "history", "runs")
        or parts[3] in {"", ".", ".."}
        or "/" in parts[3]
    ):
        raise ArchiveRefusal("forge: archive refused — unsafe archive candidate path")
    return parts[3]


def archive_candidate_matches_surface(
    repo: Path, relative: str, *, require_file: bool
) -> bool:
    """Apply the shared FR-017 archive-candidate row."""

    try:
        surface = commitment_surface("archive.candidate")
    except KeyError:
        return False
    return validate_surface_path(
        surface,
        relative,
        repository=repo,
        direct_parent=repo / ".forge" / "history" / "runs",
        require_file=require_file,
    ) is not None


def open_archive_parent(repo: Path, *, create: bool) -> int:
    """Open `.forge/history/runs` one owner-controlled component at a time."""

    descriptor = -1
    try:
        root_before = os.lstat(repo)
        if not owner_directory(root_before):
            raise ArchiveRefusal("forge: archive refused — unsafe archive parent")
        descriptor = os.open(
            repo,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        if file_identity(os.fstat(descriptor)) != file_identity(root_before):
            raise ArchiveRefusal("forge: archive refused — unsafe archive parent")
        for component in (".forge", "history", "runs"):
            if create:
                try:
                    os.mkdir(component, mode=0o755, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            before = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            if not owner_directory(before):
                raise ArchiveRefusal("forge: archive refused — unsafe archive parent")
            child = os.open(
                component,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            if file_identity(os.fstat(child)) != file_identity(before):
                os.close(child)
                raise ArchiveRefusal("forge: archive refused — unsafe archive parent")
            os.close(descriptor)
            descriptor = child
        return descriptor
    except FileNotFoundError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except ArchiveRefusal:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise ArchiveRefusal("forge: archive refused — unsafe archive parent") from exc


def snapshot_archive_at(parent: int, leaf: str, relative: str) -> ExactFile:
    descriptor: int | None = None
    diagnostic = (
        "forge: archive refused — pre-existing archive is unsafe or changed: "
        f"{relative}"
    )
    try:
        before = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        if not owner_regular(before):
            raise ArchiveRefusal(diagnostic)
        descriptor = os.open(
            leaf,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        identity = file_identity(before)
        if file_identity(os.fstat(descriptor)) != identity:
            raise ArchiveRefusal(diagnostic)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        if (
            file_identity(os.fstat(descriptor)) != identity
            or file_identity(os.stat(leaf, dir_fd=parent, follow_symlinks=False))
            != identity
            or len(raw) != identity.size
        ):
            raise ArchiveRefusal(diagnostic)
        return ExactFile(relative, raw, identity)
    except ArchiveRefusal:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise ArchiveRefusal(diagnostic) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def snapshot_existing_archive(repo: Path, relative: str) -> ExactFile:
    parent = open_archive_parent(repo, create=False)
    try:
        return snapshot_archive_at(parent, archive_leaf(relative), relative)
    finally:
        os.close(parent)


def archive_candidate_absent(repo: Path, relative: str) -> bool:
    """Check absence through the same no-follow parent used for mutation."""

    try:
        parent = open_archive_parent(repo, create=False)
    except FileNotFoundError:
        return True
    try:
        try:
            os.stat(
                archive_leaf(relative), dir_fd=parent, follow_symlinks=False
            )
        except FileNotFoundError:
            return True
        return False
    except (OSError, RuntimeError, ValueError) as exc:
        raise ArchiveRefusal(
            "forge: archive refused — transaction rollback failed"
        ) from exc
    finally:
        os.close(parent)


def untracked_archive_snapshot(
    repo: Path, archive_path: Path, relative: str
) -> ExactFile | None:
    """Classify an absent path or one safe, index-absent candidate file."""

    leaf = archive_leaf(relative)
    try:
        parent = open_archive_parent(repo, create=False)
    except FileNotFoundError:
        return None
    try:
        try:
            os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ArchiveRefusal(
                "forge: archive refused — pre-existing archive is unsafe or changed: "
                f"{relative}"
            ) from exc
    finally:
        os.close(parent)
    indexed = run_git(repo, "ls-files", "--error-unmatch", "--", relative)
    if indexed.returncode == 0:
        refuse_preexisting_archive(archive_path, relative)
    if indexed.returncode != 1:
        raise ArchiveRefusal("forge: archive refused — could not inspect archive index")
    return snapshot_existing_archive(repo, relative)


def resolve_run_dir(value: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ArchiveRefusal("forge: archive refused — run directory does not exist") from exc
    if not path.is_dir():
        raise ArchiveRefusal("forge: archive refused — run directory does not exist")
    return path


def read_json_file(path_value: str, purpose: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArchiveRefusal(f"forge: archive refused — invalid {purpose}") from exc
    if not isinstance(value, dict):
        raise ArchiveRefusal(f"forge: archive refused — invalid {purpose}")
    return value


def read_journal(run_dir: Path) -> list[dict[str, Any]]:
    records, issues = read_shared_journal(run_dir / "journal.jsonl")
    if issues:
        raise ArchiveRefusal("forge: archive refused — invalid run journal")
    return records


def decode_event_log(
    chain_id: str, raw: bytes
) -> tuple[tuple[dict[str, object], ...], str, str | None, str | None]:
    """Verify a commit/merge digest chain without inventing state authority."""

    if "chain-replay" not in RENDERER_CONTROLS or not raw or not raw.endswith(b"\n"):
        authoritative_discrepancy("structured_chain_mismatch")
    events: list[dict[str, object]] = []
    family: str | None = None
    previous = "0" * 64
    first_at: str | None = None
    last_at: str | None = None
    for sequence, encoded in enumerate(raw.splitlines(keepends=True), start=1):
        try:
            event = json.loads(encoded.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):
            authoritative_discrepancy("structured_chain_mismatch")
        if not isinstance(event, dict):
            authoritative_discrepancy("structured_chain_mismatch")
        commit = set(event) == {"sequence", "prev_digest", "payload", "digest"}
        merge = set(event) == {
            "schema",
            "chain_id",
            "sequence",
            "at",
            "event",
            "generation_digest",
            "previous_digest",
            "payload",
            "digest",
        }
        current_family = "commit" if commit else "merge" if merge else None
        if current_family is None or (family is not None and current_family != family):
            authoritative_discrepancy("structured_chain_mismatch")
        family = current_family
        predecessor = event.get("prev_digest" if commit else "previous_digest")
        if (
            event.get("sequence") != sequence
            or predecessor != previous
            or not isinstance(event.get("digest"), str)
            or journal_engine.HEX_SHA256_PATTERN.fullmatch(str(event["digest"])) is None
        ):
            authoritative_discrepancy("structured_chain_mismatch")
        if merge and (
            event.get("schema") != "forge-merge-event/1"
            or event.get("chain_id") != chain_id
        ):
            authoritative_discrepancy("structured_chain_mismatch")
        canonical = journal_engine._canonical_json_bytes(event) + b"\n"
        if encoded != canonical:
            authoritative_discrepancy("structured_chain_mismatch")
        unsigned = {name: value for name, value in event.items() if name != "digest"}
        if hashlib.sha256(journal_engine._canonical_json_bytes(unsigned)).hexdigest() != event["digest"]:
            authoritative_discrepancy("structured_chain_mismatch")
        if commit:
            payload = event.get("payload")
            if not isinstance(payload, dict) or set(payload) != {
                "at",
                "details",
                "event",
                "state",
            }:
                authoritative_discrepancy("structured_chain_mismatch")
            timestamp = payload.get("at")
        else:
            timestamp = event.get("at")
        if timestamp is not None and not isinstance(timestamp, str):
            authoritative_discrepancy("structured_chain_mismatch")
        if sequence == 1:
            first_at = timestamp
        last_at = timestamp
        previous = str(event["digest"])
        events.append(event)
    assert family is not None
    return tuple(events), family, first_at, last_at


def replay_chain_state(
    repo: Path,
    directory: int,
    chain_id: str,
    state: dict[str, object],
    events: tuple[dict[str, object], ...],
    family: str,
) -> None:
    """Prove the materialized state equals authoritative event replay."""

    modern = "run_binding" in state or "journal_outbox" in state
    if modern and not {"run_binding", "journal_outbox"} <= set(state):
        authoritative_discrepancy("structured_chain_mismatch")
    if modern:
        register_archive_merge_reducer()
        try:
            replayed = journal_builders._resolve_binding_from_descriptor(
                repo,
                directory,
                chain_id,
                "0" * 64,
                expected_type=None,
                expected_fields=None,
                expected_run_id=None,
                expected_task_id=None,
                replay_only=True,
                allow_pending=False,
            )
        except (OSError, RuntimeError, ValueError, journal_engine.CoordinationRefusal):
            authoritative_discrepancy("structured_chain_mismatch")
        if replayed != state:
            authoritative_discrepancy("structured_chain_mismatch")
        return
    if family != "commit":
        # DM-014 is delta-carried.  A payload.state member is never an
        # authorized substitute for the registered reducer.
        authoritative_discrepancy("structured_chain_mismatch")
    final_payload = events[-1].get("payload")
    if not isinstance(final_payload, dict) or final_payload.get("state") != state:
        authoritative_discrepancy("structured_chain_mismatch")
    if (
        state.get("schema") != CHAIN_STATE_SCHEMA
        or state.get("kind") != "commit"
        or state.get("chain_id") != chain_id
    ):
        authoritative_discrepancy("structured_chain_mismatch")


def capture_chain_package(
    repo: Path,
    run_dir: Path,
    required_chain_ids: set[str],
    *,
    activated: bool,
) -> ChainPackage:
    """Snapshot only run-cited chain pairs with no-follow identity fences.

    Activated authority remains in the Git-common ``.forge/chains``.  The run-local
    fallback exists solely for pre-activation runs whose interim disposition
    copied then-live DM-012 files under the run directory before Revision 9.
    """

    if not required_chain_ids:
        return ChainPackage(None, None, (), ())
    run_capture = run_dir / "chains"
    root = chain_storage_root(repo)
    if not activated and run_capture.is_dir() and not run_capture.is_symlink():
        root = run_capture
    try:
        root_before = os.lstat(root)
    except FileNotFoundError:
        if required_chain_ids:
            authoritative_discrepancy("missing_chain_artifact")
        return ChainPackage(None, None, (), ())
    except OSError:
        authoritative_discrepancy("missing_chain_artifact")
    if "chain-snapshot" not in RENDERER_CONTROLS or not owner_directory(root_before):
        authoritative_discrepancy("missing_chain_artifact")
    directory: int | None = None
    try:
        directory = os.open(
            root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        root_identity = file_identity(root_before)
        if file_identity(os.fstat(directory)) != root_identity:
            authoritative_discrepancy("snapshot_changed")
        names = tuple(
            name
            for chain_id in sorted(required_chain_ids, key=os.fsencode)
            for name in (f"{chain_id}.json", f"{chain_id}.events.jsonl")
        )
        chains: list[ChainSnapshot] = []
        for chain_id in sorted(required_chain_ids, key=os.fsencode):
            if journal_engine.CHAIN_ID_PATTERN.fullmatch(chain_id) is None:
                authoritative_discrepancy("missing_chain_artifact")
            state_file = read_exact_file(directory, f"{chain_id}.json")
            events_file = read_exact_file(directory, f"{chain_id}.events.jsonl")
            try:
                state = json.loads(state_file.raw.decode("utf-8"))
            except (UnicodeError, ValueError, RecursionError):
                authoritative_discrepancy("structured_chain_mismatch")
            if not isinstance(state, dict):
                authoritative_discrepancy("structured_chain_mismatch")
            events, family, first_at, last_at = decode_event_log(
                chain_id, events_file.raw
            )
            expected_schema = CHAIN_STATE_SCHEMA if family == "commit" else MERGE_STATE_SCHEMA
            if state.get("schema") != expected_schema or state.get("kind") != family:
                authoritative_discrepancy("structured_chain_mismatch")
            replay_chain_state(repo, directory, chain_id, state, events, family)
            chains.append(
                ChainSnapshot(
                    chain_id,
                    state_file,
                    events_file,
                    state,
                    events,
                    family,
                    str(events[-1]["digest"]),
                    first_at,
                    last_at,
                )
            )
        rebound = os.lstat(root)
        if (
            file_identity(os.fstat(directory)) != root_identity
            or file_identity(rebound) != root_identity
        ):
            authoritative_discrepancy("snapshot_changed")
        return ChainPackage(root, root_identity, names, tuple(chains))
    except ArchiveRefusal:
        raise
    except (OSError, RuntimeError, ValueError):
        authoritative_discrepancy("missing_chain_artifact")
        raise AssertionError("unreachable")
    finally:
        if directory is not None:
            os.close(directory)


def recheck_chain_package(package: ChainPackage) -> None:
    if package.root is None:
        return
    captured_ids = {snapshot.chain.chain_id for snapshot in package.captured}
    directory: int | None = None
    try:
        current_root = os.lstat(package.root)
        directory = os.open(
            package.root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        if (
            file_identity(current_root) != package.root_identity
            or file_identity(os.fstat(directory)) != package.root_identity
        ):
            authoritative_discrepancy("snapshot_changed")
        for chain in package.chains:
            if chain.chain_id in captured_ids:
                continue
            for exact in (chain.state_file, chain.events_file):
                current = read_exact_file(directory, exact.name)
                if current.identity != exact.identity or current.raw != exact.raw:
                    authoritative_discrepancy("snapshot_changed")
    except ArchiveRefusal:
        raise
    except (OSError, RuntimeError, ValueError):
        authoritative_discrepancy("snapshot_changed")
    finally:
        if directory is not None:
            os.close(directory)


def _looks_like_ingest_capture(value: object, run_id: str) -> bool:
    if not isinstance(value, str):
        return False
    return bool(
        parse_run_captured_path(value, run_id=run_id) is not None
        or "/captured/sha256/" in f"/{value}"
    )


def _captured_ingest_triplet(
    run_dir: Path, basis: object
) -> tuple[str, str, str] | None:
    """Recognize only the exact ordered paths emitted by ingest-chain."""

    if not isinstance(basis, list) or len(basis) != 3:
        return None
    expected_names = ("state.json", "events.jsonl", "outcome-map.json")
    result: list[str] = []
    for value, expected_name in zip(basis, expected_names):
        if not isinstance(value, str):
            return None
        captured = parse_run_captured_path(value, run_id=run_dir.name)
        if captured is None:
            return None
        if captured.name != expected_name:
            return None
        result.append(value)
    return result[0], result[1], result[2]


def classify_captured_ingest_citations(
    run_dir: Path,
    records: list[dict[str, Any]],
    required_chain_ids: set[str],
) -> dict[str, tuple[str, str, str]]:
    """Map only retrospectively ingested chain IDs to their three citations."""

    required = required_binding_records(records, True)
    result: dict[str, tuple[str, str, str]] = {}
    for chain_id in sorted(required_chain_ids, key=os.fsencode):
        landings: list[dict[str, Any]] = []
        for record in required:
            if record.get("type") != "decision" or record.get("outcome") != "chain-landing":
                continue
            binding = record.get("binding")
            source = binding.get("source_record") if isinstance(binding, dict) else None
            if isinstance(source, dict) and source.get("chain_id") == chain_id:
                landings.append(record)
        capture_like = any(
            any(
                _looks_like_ingest_capture(value, run_dir.name)
                for value in record.get("basis", ())
            )
            if isinstance(record.get("basis"), list)
            else False
            for record in landings
        )
        if not capture_like:
            continue
        if "captured-ingest-classification" not in RENDERER_CONTROLS:
            authoritative_discrepancy("structured_chain_mismatch")
        if len(landings) != 1:
            authoritative_discrepancy("structured_chain_mismatch")
        citations = _captured_ingest_triplet(run_dir, landings[0].get("basis"))
        if citations is None:
            authoritative_discrepancy("structured_chain_mismatch")
        result[chain_id] = citations
    return result


def replay_captured_unbound_chain(
    chain_id: str,
    state: dict[str, object],
    events: tuple[dict[str, object], ...],
    family: str,
) -> tuple[ReplayEntry, ...]:
    """Replay an ingest-captured unbound chain without trusting payload state."""

    if "captured-ingest-replay" not in RENDERER_CONTROLS:
        authoritative_discrepancy("structured_chain_mismatch")
    if (
        family not in {"commit", "merge"}
        or not journal_builders._state_shape_valid(state, chain_id, family)
        or state.get("state") != "closed"
        or state.get("run_binding") is not None
        or state.get("journal_outbox") is not None
        or (family == "merge" and state.get("run") is not None)
    ):
        authoritative_discrepancy("structured_chain_mismatch")
    if family == "merge":
        register_archive_merge_reducer()

    replayed: dict[str, object] | None = None
    entries: list[ReplayEntry] = []
    merge_context: dict[str, object] = {}
    for event in events:
        prior = copy.deepcopy(replayed)
        payload = event.get("payload")
        if not isinstance(payload, dict):
            authoritative_discrepancy("structured_chain_mismatch")
        try:
            if family == "commit":
                details = payload.get("details")
                candidate = payload.get("state")
                if (
                    not isinstance(details, dict)
                    or "journal_batch" in details
                    or "source_event_digest" in details
                    or not isinstance(candidate, dict)
                    or not journal_builders._state_shape_valid(
                        candidate, chain_id, family
                    )
                    or candidate.get("run_binding") is not None
                    or candidate.get("journal_outbox") is not None
                    or not journal_builders._commit_transition_valid(
                        event, replayed, candidate
                    )
                ):
                    authoritative_discrepancy("structured_chain_mismatch")
                next_state = copy.deepcopy(candidate)
            else:
                if (
                    "state" in payload
                    or "journal_batch" in payload
                    or "source_event_digest" in payload
                    or event.get("event") == "journal_receipted"
                ):
                    authoritative_discrepancy("structured_chain_mismatch")
                reducer = journal_builders.MERGE_TRANSITION_REDUCER
                if reducer is None:
                    authoritative_discrepancy("structured_chain_mismatch")
                next_state = reducer(copy.deepcopy(replayed), copy.deepcopy(event))
                if (
                    not journal_builders._state_shape_valid(
                        next_state, chain_id, family
                    )
                    or next_state.get("run_binding") is not None
                    or next_state.get("journal_outbox") is not None
                    or next_state.get("run") is not None
                    or not journal_builders._merge_transition_valid(
                        event,
                        replayed,
                        next_state,
                        context=merge_context,
                    )
                ):
                    authoritative_discrepancy("structured_chain_mismatch")
        except ArchiveRefusal:
            raise
        except (KeyError, TypeError, ValueError, RuntimeError):
            authoritative_discrepancy("structured_chain_mismatch")
        replayed = copy.deepcopy(next_state)
        entries.append((event, prior, copy.deepcopy(next_state), (), str(event["digest"])))
    if replayed != state:
        authoritative_discrepancy("structured_chain_mismatch")
    return tuple(entries)


_CLI_INGEST_AUTHORITY: object | None = None


def _load_cli_ingest_authority() -> object:
    """Load the import-safe sibling CLI that owns ingest selection templates."""

    global _CLI_INGEST_AUTHORITY
    required = (
        "_ingest_step_is_current",
        "_ingest_secret_scan_is_current",
        "_user_skip",
        "_binding_for_commit_event",
        "_latest_current_pass",
        "_fast_mechanical_skips",
        "_required_steps",
        "_gate_one_complete",
        "_gate_satisfied",
        "_merge_current_gate_facts",
        "_merge_ingest_record_templates",
        "_merge_ingest_binding",
        "parse_policy",
        "Repository",
        "ChainStore",
        "CLIOptions",
        "CommandContext",
    )
    if _CLI_INGEST_AUTHORITY is not None and all(
        callable(getattr(_CLI_INGEST_AUTHORITY, name, None)) for name in required
    ):
        return _CLI_INGEST_AUTHORITY
    cli_path = Path(__file__).resolve().with_name("cli.py")
    for module in tuple(sys.modules.values()):
        module_path = getattr(module, "__file__", None)
        try:
            same_path = (
                isinstance(module_path, str)
                and Path(module_path).resolve() == cli_path
            )
        except (OSError, RuntimeError, ValueError):
            same_path = False
        if same_path and all(callable(getattr(module, name, None)) for name in required):
            _CLI_INGEST_AUTHORITY = module
            return module
    name = "_forge_archive_ingest_cli_authority"
    try:
        specification = importlib.util.spec_from_file_location(name, cli_path)
        if specification is None or specification.loader is None:
            raise ImportError("CLI module has no loader")
        module = importlib.util.module_from_spec(specification)
        sys.modules[name] = module
        specification.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        authoritative_discrepancy("structured_chain_mismatch")
    if not all(callable(getattr(module, item, None)) for item in required):
        authoritative_discrepancy("structured_chain_mismatch")
    _CLI_INGEST_AUTHORITY = module
    return module


def _eligible_descriptor(
    digest: str, record: Mapping[str, object]
) -> EligibleIngestRecord:
    return EligibleIngestRecord(
        digest,
        str(record.get("type")),
        record.get("criterion")
        if isinstance(record.get("criterion"), str)
        else None,
        record.get("result") if isinstance(record.get("result"), str) else None,
        record.get("outcome") if isinstance(record.get("outcome"), str) else None,
    )


def _commit_required_steps(
    repo: Path, cli: object, state: dict[str, object]
) -> tuple[str, ...]:
    """Re-run the CLI's committed-policy and current-gate ingest proof."""

    candidate = state.get("candidate")
    policy_source = state.get("policy_source")
    staging = state.get("staging")
    tier = state.get("tier")
    steps = state.get("steps")
    try:
        canonical_repo = repo.resolve(strict=True)
    except OSError:
        authoritative_discrepancy("structured_chain_mismatch")
    if (
        state.get("kind") != "commit"
        or state.get("state") != "closed"
        or state.get("run_binding") is not None
        or state.get("journal_outbox") is not None
        or not all(
            isinstance(value, dict)
            for value in (candidate, policy_source, staging, tier, steps)
        )
    ):
        authoritative_discrepancy("structured_chain_mismatch")
    assert isinstance(candidate, dict)
    assert isinstance(policy_source, dict)
    assert isinstance(staging, dict)
    assert isinstance(tier, dict)
    candidate_digest = candidate.get("sha256")
    policy_sha = policy_source.get("sha")
    policy_digest = policy_source.get("digest")
    tier_rank = getattr(cli, "TIER_RANK", None)
    if (
        staging.get("worktree_root") != str(canonical_repo)
        or not isinstance(candidate_digest, str)
        or journal_engine.HEX_SHA256_PATTERN.fullmatch(candidate_digest) is None
        or not isinstance(policy_sha, str)
        or not isinstance(policy_digest, str)
        or journal_engine.HEX_SHA256_PATTERN.fullmatch(policy_digest) is None
        or not isinstance(tier_rank, dict)
        or tier.get("effective") not in tier_rank
        or tier.get("derived") not in tier_rank
        or (
            tier.get("declared") is not None
            and tier.get("declared") not in tier_rank
        )
        or type(tier.get("control")) is not bool
    ):
        authoritative_discrepancy("structured_chain_mismatch")
    policy = run_git(repo, "show", f"{policy_sha}:forge-project.md")
    if (
        policy.returncode != 0
        or hashlib.sha256(policy.stdout).hexdigest() != policy_digest
    ):
        authoritative_discrepancy("structured_chain_mismatch")
    try:
        parsed_policy = cli.parse_policy(policy_sha, policy.stdout)
        repository = cli.Repository(canonical_repo)
        context = cli.CommandContext(
            repo=repository,
            store=cli.ChainStore(repository.common_root()),
            options=cli.CLIOptions(
                repo=str(canonical_repo), revision9_face=True
            ),
            policy=parsed_policy,
        )
        if (
            not cli._latest_current_pass(state, "classification")
            or (
                tier.get("effective") == "fast"
                and (
                    bool(cli._fast_mechanical_skips(state))
                    or not cli._latest_current_pass(state, "fast-eligibility")
                    or not cli._latest_current_pass(
                        state, "fast-finalize-eligibility"
                    )
                )
            )
        ):
            authoritative_discrepancy("structured_chain_mismatch")
        required_steps = tuple(cli._required_steps(context, state))
        if (
            not required_steps
            or not all(isinstance(step, str) and step for step in required_steps)
            or not cli._gate_one_complete(state)
            or not all(
                cli._gate_satisfied(state, step)
                for step in set(required_steps) - {"gate-1"}
            )
        ):
            authoritative_discrepancy("structured_chain_mismatch")
    except ArchiveRefusal:
        raise
    except (KeyError, OSError, TypeError, ValueError, RuntimeError, UnicodeError):
        authoritative_discrepancy("structured_chain_mismatch")
    return required_steps


def _commit_eligible_records(
    repo: Path,
    cli: object,
    state: dict[str, object],
    replay_entries: tuple[ReplayEntry, ...],
    task: str,
) -> tuple[EligibleIngestRecord, ...]:
    _commit_required_steps(repo, cli, state)
    tier = state.get("tier")
    review = state.get("review")
    approval = state.get("approval")
    result = state.get("commit_result")
    candidate = state.get("candidate")
    if not all(
        isinstance(value, dict)
        for value in (tier, review, approval, result, candidate)
    ):
        authoritative_discrepancy("structured_chain_mismatch")
    assert isinstance(tier, dict)
    assert isinstance(review, dict)
    assert isinstance(approval, dict)
    assert isinstance(result, dict)
    assert isinstance(candidate, dict)
    final_candidate = candidate.get("sha256")
    commit_sha = result.get("commit_sha")
    approval_required = bool(
        tier.get("control") or review.get("operator_cosign_required")
    )
    eligible: list[EligibleIngestRecord] = []
    for event, prior, event_state, _carried, digest_value in replay_entries:
        digest = str(digest_value)
        payload = event.get("payload")
        if not isinstance(payload, dict):
            authoritative_discrepancy("structured_chain_mismatch")
        details = payload.get("details")
        event_name = payload.get("event")
        if not isinstance(details, dict) or not isinstance(event_name, str):
            authoritative_discrepancy("structured_chain_mismatch")
        active = False
        expected: dict[str, object] | None = None
        binding_review: object = None
        if event_name == "step_recorded":
            active = bool(
                cli._ingest_step_is_current(state, event_state, details)
            )
            if active:
                step_id = details.get("step_id")
                run_number = details.get("run")
                steps = event_state.get("steps")
                runs = steps.get(step_id) if isinstance(steps, dict) else None
                fact = (
                    runs[run_number - 1]
                    if isinstance(runs, list)
                    and type(run_number) is int
                    and 0 < run_number <= len(runs)
                    else None
                )
                result_value = fact.get("result") if isinstance(fact, dict) else None
                if (
                    not isinstance(step_id, str)
                    or result_value not in {"passed", "failed"}
                    or details.get("result") != result_value
                ):
                    authoritative_discrepancy("structured_chain_mismatch")
                expected = {
                    "type": "verification",
                    "task": task,
                    "criterion": (
                        f"gate-1: {step_id}"
                        if step_id == "gate-1"
                        else f"gate-2: {step_id}"
                    ),
                    "result": result_value,
                }
        elif event_name == "secret_scan_recorded":
            active = bool(
                cli._ingest_secret_scan_is_current(
                    state, event, prior, event_state
                )
            )
            if active:
                introduced = journal_builders._commit_secret_scan_delta(
                    event, prior, event_state
                )
                if introduced is None:
                    authoritative_discrepancy("structured_chain_mismatch")
                expected = {
                    "type": "verification",
                    "task": task,
                    "criterion": "gate-2: secret-scan",
                    "result": introduced[1].get("result"),
                }
        elif event_name in {"review_passed", "review_blocked"}:
            active = bool(
                tier.get("effective") == "hard"
                and event_name == "review_passed"
                and event_state.get("review", {}).get("verdict")
                == review.get("verdict")
            )
            if active:
                binding_review = journal_builders._review_binding_for_state(event_state)
                if not isinstance(binding_review, dict):
                    authoritative_discrepancy("structured_chain_mismatch")
                expected = {
                    "type": "verification",
                    "task": task,
                    "criterion": journal_engine.GATE_3_CRITERION,
                    "result": "passed",
                }
        elif event_name == "operator_approved":
            active = bool(
                approval_required and event_state.get("approval") == approval
            )
            if active:
                expected = {
                    "type": "decision",
                    "task": task,
                    "outcome": "chain-approval",
                }
        elif event_name == "operator_skip":
            gate_id = details.get("gate_id")
            active = bool(
                isinstance(gate_id, str)
                and cli._user_skip(state, gate_id)
                == cli._user_skip(event_state, gate_id)
            )
            if active:
                expected = {
                    "type": "decision",
                    "task": task,
                    "outcome": "chain-skip",
                }
        elif event_name in {"commit_produced", "commit_close_recovered"}:
            active = details.get("commit_sha") == commit_sha
            if active:
                expected = {
                    "type": "decision",
                    "task": task,
                    "outcome": "chain-landing",
                }
        event_candidate = event_state.get("candidate")
        if not active or not isinstance(event_candidate, dict) or event_candidate.get(
            "sha256"
        ) != final_candidate:
            continue
        if expected is None:
            authoritative_discrepancy("structured_chain_mismatch")
        binding = cli._binding_for_commit_event(
            event_state, digest, binding_review
        )
        bound = {**expected, "binding": binding}
        if not journal_builders._binding_matches_source_fact(
            binding,
            bound,
            event,
            prior,
            event_state,
            family="commit",
        ) or not journal_builders._binding_is_current(
            state,
            binding,
            bound,
            event,
            prior,
            event_state,
            replay_entries,
            chain_family="commit",
        ):
            authoritative_discrepancy("structured_chain_mismatch")
        eligible.append(_eligible_descriptor(digest, expected))
    review_count = sum(
        item.criterion == journal_engine.GATE_3_CRITERION for item in eligible
    )
    approval_count = sum(item.outcome == "chain-approval" for item in eligible)
    landing_count = sum(item.outcome == "chain-landing" for item in eligible)
    if (
        review_count != (1 if tier.get("effective") == "hard" else 0)
        or approval_count != (1 if approval_required else 0)
        or landing_count != 1
    ):
        authoritative_discrepancy("structured_chain_mismatch")
    return tuple(eligible)


def _merge_required_gate_ids(
    repo: Path, cli: object, state: dict[str, object]
) -> frozenset[str]:
    candidate = state.get("candidate")
    policy_source = state.get("policy_source")
    tier = state.get("tier")
    if not all(isinstance(value, dict) for value in (candidate, policy_source, tier)):
        authoritative_discrepancy("structured_chain_mismatch")
    assert isinstance(candidate, dict)
    assert isinstance(policy_source, dict)
    assert isinstance(tier, dict)
    policy_commit = candidate.get("policy_commit")
    policy_digest = candidate.get("policy_digest")
    categories = tier.get("categories")
    if (
        not isinstance(policy_commit, str)
        or not isinstance(policy_digest, str)
        or policy_commit not in policy_source.values()
        or policy_digest not in policy_source.values()
        or not isinstance(categories, list)
        or not all(isinstance(value, str) and value for value in categories)
    ):
        authoritative_discrepancy("structured_chain_mismatch")
    policy = run_git(repo, "show", f"{policy_commit}:forge-project.md")
    if policy.returncode != 0 or hashlib.sha256(policy.stdout).hexdigest() != policy_digest:
        authoritative_discrepancy("structured_chain_mismatch")
    try:
        parsed = cli.parse_policy(policy_commit, policy.stdout)
        invariant_ids = {
            f"invariant:{invariant['row_number']}"
            for invariant in parsed.invariants
            if invariant["enforcement"] == "merge"
        }
    except (KeyError, TypeError, ValueError, UnicodeError):
        authoritative_discrepancy("structured_chain_mismatch")
    return frozenset(
        {
            "gate-1",
            "assertion-sensor",
            *(f"stack:{category}" for category in sorted(set(categories))),
            *invariant_ids,
        }
    )


def _merge_eligible_records(
    repo: Path,
    cli: object,
    state: dict[str, object],
    replay_entries: tuple[ReplayEntry, ...],
    task: str,
) -> tuple[EligibleIngestRecord, ...]:
    required_gate_ids = _merge_required_gate_ids(repo, cli, state)
    candidate = state.get("candidate")
    tier = state.get("tier")
    steps = state.get("steps")
    if not all(isinstance(value, dict) for value in (candidate, tier, steps)):
        authoritative_discrepancy("structured_chain_mismatch")
    assert isinstance(candidate, dict)
    assert isinstance(tier, dict)
    assert isinstance(steps, dict)
    generation_digest = candidate.get("generation_digest")
    if not isinstance(generation_digest, str) or any(
        cli._merge_current_gate_facts(
            gate_id, steps.get(gate_id), generation_digest
        )
        is None
        for gate_id in required_gate_ids
    ):
        authoritative_discrepancy("structured_chain_mismatch")
    approval_required = bool(tier.get("control"))
    eligible: list[EligibleIngestRecord] = []
    covered_gates: set[str] = set()
    gate3_count = 0
    approval_count = 0
    landing_count = 0
    for event, prior, event_state, _carried, digest_value in replay_entries:
        digest = str(digest_value)
        templates = cli._merge_ingest_record_templates(
            journal_builders,
            journal_engine,
            event,
            prior,
            event_state,
            task=task,
            approval_required=approval_required,
            required_gate_ids=required_gate_ids,
        )
        for template, gate_id in templates:
            review = (
                journal_builders._review_binding_for_state(event_state)
                if template.get("criterion") == journal_engine.GATE_3_CRITERION
                else None
            )
            binding = cli._merge_ingest_binding(
                journal_builders, event_state, digest, review
            )
            expected = {**template, "binding": binding}
            if not journal_builders._binding_matches_source_fact(
                binding,
                expected,
                event,
                prior,
                event_state,
                family="merge",
            ) or not journal_builders._binding_is_current(
                state,
                binding,
                expected,
                event,
                prior,
                event_state,
                replay_entries,
                chain_family="merge",
            ):
                continue
            eligible.append(_eligible_descriptor(digest, template))
            if gate_id is not None:
                covered_gates.add(gate_id)
            if template.get("criterion") == journal_engine.GATE_3_CRITERION:
                gate3_count += 1
            if template.get("outcome") == "chain-approval":
                approval_count += 1
            if template.get("outcome") == "chain-landing":
                landing_count += 1
    if (
        covered_gates != set(required_gate_ids)
        or gate3_count != 1
        or approval_count != (1 if approval_required else 0)
        or landing_count != 1
    ):
        authoritative_discrepancy("structured_chain_mismatch")
    return tuple(eligible)


def derive_captured_ingest_eligible_records(
    repo: Path,
    state: dict[str, object],
    replay_entries: tuple[ReplayEntry, ...],
    family: str,
    task: str,
) -> tuple[EligibleIngestRecord, ...]:
    """Derive exact ingest output cardinality without outcome-map/journal input."""

    if "captured-ingest-eligibility" not in RENDERER_CONTROLS:
        authoritative_discrepancy("structured_chain_mismatch")
    cli = _load_cli_ingest_authority()
    try:
        if family == "commit":
            return _commit_eligible_records(repo, cli, state, replay_entries, task)
        if family == "merge":
            return _merge_eligible_records(repo, cli, state, replay_entries, task)
    except ArchiveRefusal:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError):
        authoritative_discrepancy("structured_chain_mismatch")
    authoritative_discrepancy("structured_chain_mismatch")
    raise AssertionError("unreachable")


def _captured_document(
    repo: Path, run_dir: Path, citation: str
) -> BasisDocument:
    captured = parse_run_captured_path(citation, run_id=run_dir.name)
    if captured is None:
        authoritative_discrepancy("structured_chain_mismatch")
    relative = Path(captured.relative)
    capture_relative = relative.as_posix()
    try:
        surface = commitment_surface("ingest.captured_package")
    except KeyError:
        authoritative_discrepancy("structured_chain_mismatch")
    if validate_surface_path(
        surface,
        capture_relative,
        repository=repo,
        run_dir=run_dir,
        direct_parent=(run_dir / relative).parent,
        require_file=True,
    ) is None:
        authoritative_discrepancy("structured_chain_mismatch")
    try:
        exact, directories = snapshot_basis_document(run_dir, relative, citation)
    except FileNotFoundError:
        authoritative_discrepancy("missing_chain_artifact")
    digest = captured.digest
    if hashlib.sha256(exact.raw).hexdigest() != digest:
        authoritative_discrepancy("structured_chain_mismatch")
    try:
        content = exact.raw.decode("utf-8")
    except UnicodeError:
        authoritative_discrepancy("structured_chain_mismatch")
    return BasisDocument(
        citation,
        content,
        run_dir / relative,
        exact,
        run_dir,
        relative,
        directories,
    )


def capture_captured_ingest_packages(
    repo: Path,
    run_dir: Path,
    citations_by_chain: Mapping[str, tuple[str, str, str]],
) -> tuple[CapturedIngestSnapshot, ...]:
    """Snapshot, parse, and replay every content-addressed ingest package."""

    if citations_by_chain and "chain-snapshot" not in RENDERER_CONTROLS:
        authoritative_discrepancy("missing_chain_artifact")
    snapshots: list[CapturedIngestSnapshot] = []
    for chain_id in sorted(citations_by_chain, key=os.fsencode):
        citations = citations_by_chain[chain_id]
        documents = tuple(
            _captured_document(repo, run_dir, value) for value in citations
        )
        state_document, events_document, outcome_document = documents
        try:
            state = json.loads(state_document.exact.raw.decode("utf-8"))
            outcome_map = json.loads(outcome_document.exact.raw.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):
            authoritative_discrepancy("structured_chain_mismatch")
        if not isinstance(state, dict) or not isinstance(outcome_map, dict):
            authoritative_discrepancy("structured_chain_mismatch")
        events, family, first_at, last_at = decode_event_log(
            chain_id, events_document.exact.raw
        )
        expected_schema = CHAIN_STATE_SCHEMA if family == "commit" else MERGE_STATE_SCHEMA
        if (
            state.get("schema") != expected_schema
            or state.get("chain_id") != chain_id
            or state.get("kind") != family
        ):
            authoritative_discrepancy("structured_chain_mismatch")
        replay_entries = replay_captured_unbound_chain(
            chain_id, state, events, family
        )
        if (
            set(outcome_map)
            != {"schema", "chain_id", "task", "task_status", "event_digests"}
            or outcome_map.get("schema") != "forge-chain-ingest-outcome-map/1"
            or outcome_map.get("chain_id") != chain_id
            or not isinstance(outcome_map.get("task"), str)
            or not outcome_map.get("task")
            or outcome_map.get("task_status")
            not in journal_engine.TERMINAL_TASK_STATUSES
            or not isinstance(outcome_map.get("event_digests"), list)
            or not outcome_map["event_digests"]
            or not all(
                isinstance(value, str)
                and journal_engine.HEX_SHA256_PATTERN.fullmatch(value) is not None
                for value in outcome_map["event_digests"]
            )
        ):
            authoritative_discrepancy("structured_chain_mismatch")
        selected = tuple(str(value) for value in outcome_map["event_digests"])
        eligible_records = derive_captured_ingest_eligible_records(
            repo,
            state,
            replay_entries,
            family,
            str(outcome_map["task"]),
        )
        eligible_events: list[str] = []
        for eligible in eligible_records:
            if eligible.event_digest not in eligible_events:
                eligible_events.append(eligible.event_digest)
        if selected != tuple(eligible_events):
            authoritative_discrepancy("structured_chain_mismatch")
        chain = ChainSnapshot(
            chain_id,
            state_document.exact,
            events_document.exact,
            state,
            events,
            family,
            str(events[-1]["digest"]),
            first_at,
            last_at,
        )
        snapshots.append(
            CapturedIngestSnapshot(
                chain,
                citations,
                documents,
                outcome_map,
                replay_entries,
                selected,
                eligible_records,
            )
        )
    return tuple(snapshots)


def capture_archive_chain_package(
    repo: Path,
    run_dir: Path,
    records: list[dict[str, Any]],
    required_chain_ids: set[str],
    *,
    activated: bool,
) -> ChainPackage:
    """Capture live event-carried and retrospective chain authority together."""

    citations = (
        classify_captured_ingest_citations(run_dir, records, required_chain_ids)
        if activated
        else {}
    )
    live_ids = required_chain_ids - set(citations)
    live = capture_chain_package(repo, run_dir, live_ids, activated=activated)
    captured = capture_captured_ingest_packages(repo, run_dir, citations)
    chains = tuple(
        sorted(
            (*live.chains, *(snapshot.chain for snapshot in captured)),
            key=lambda chain: os.fsencode(chain.chain_id),
        )
    )
    return ChainPackage(
        live.root,
        live.root_identity,
        live.names,
        chains,
        captured,
    )


def recheck_captured_ingest_packages(package: ChainPackage) -> None:
    """Re-open every captured package component and require exact identities."""

    for snapshot in package.captured:
        for document in snapshot.documents:
            try:
                current, directories = snapshot_basis_document(
                    document.root, document.relative, document.label
                )
            except (FileNotFoundError, ArchiveRefusal):
                authoritative_discrepancy("snapshot_changed")
            if (
                current.identity != document.exact.identity
                or current.raw != document.exact.raw
                or directories != document.directory_identities
            ):
                authoritative_discrepancy("snapshot_changed")


def captured_chain_evidence_paths(package: ChainPackage) -> frozenset[Path]:
    """Paths already carried through the bounded DM-012 evidence blocks."""

    return frozenset(
        document.path
        for snapshot in package.captured
        for document in snapshot.documents[:2]
    )


def verbatim_basis_documents(
    package: ChainPackage, documents: Sequence[BasisDocument]
) -> tuple[BasisDocument, ...]:
    """Exclude state/events already carried by their one bounded DM-012 block."""

    evidence_paths = captured_chain_evidence_paths(package)
    return tuple(document for document in documents if document.path not in evidence_paths)


def only_record(records: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    matches = [record for record in records if record.get("type") == kind]
    if len(matches) != 1:
        raise ArchiveRefusal("forge: archive refused — invalid run journal")
    return matches[0]


def display(value: object) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return NONE


def markdown_list(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return [NONE]
    rendered = [f"- {display(item)}" for item in value]
    return rendered or [NONE]


def table_cell(value: object) -> str:
    if "html-escape" not in RENDERER_CONTROLS:
        raise ArchiveRefusal(
            "forge: archive refused — renderer escaping control unavailable"
        )
    text = html.escape(display(value), quote=False)
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", "<br>")
    )


def canonical_json(value: object) -> list[str]:
    if value is None:
        return [NONE]
    return ["```json", json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), "```"]


def learning_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and "\x00" not in value
        and value.splitlines() == [value]
    )


def learning_segment(value: object) -> bool:
    return (
        learning_text(value)
        and value not in {".", ".."}
        and LEARNING_SAFE_SEGMENT.fullmatch(value) is not None
    )


def recorded_prompt_provenance(
    run_dir: Path, record: dict[str, Any]
) -> tuple[str, str]:
    prompt = record.get("prompt")
    if not isinstance(prompt, str) or not prompt or "\\" in prompt:
        raise ArchiveRefusal("forge: archive refused — invalid recorded prompt")
    relative = Path(prompt)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ArchiveRefusal("forge: archive refused — invalid recorded prompt")
    source = run_dir
    for part in relative.parts:
        source = source / part
        if source.is_symlink():
            raise ArchiveRefusal("forge: archive refused — invalid recorded prompt")
    try:
        resolved_run_dir = run_dir.resolve(strict=True)
        resolved = source.resolve(strict=True)
        resolved.relative_to(resolved_run_dir)
        metadata = resolved.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ArchiveRefusal("forge: archive refused — invalid recorded prompt")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise ArchiveRefusal("forge: archive refused — invalid recorded prompt")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
        finally:
            os.close(descriptor)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ArchiveRefusal("forge: archive refused — invalid recorded prompt") from exc
    return prompt, digest


def execution_learning_provenance(
    run_dir: Path, record: dict[str, Any]
) -> dict[str, object] | None:
    if not (
        learning_segment(record.get("agent"))
        and learning_segment(record.get("execution"))
        and learning_text(record.get("role"))
        and learning_text(record.get("task"))
        and learning_text(record.get("prompt"))
    ):
        return None
    try:
        prompt, digest = recorded_prompt_provenance(run_dir, record)
    except ArchiveRefusal:
        # Learning provenance is advisory. A missing or unsafe recorded prompt
        # removes this execution's citation authority; it must not invalidate an
        # otherwise canonical close/archive transaction.
        return None
    return {
        **{key: record.get(key) for key in ("agent", "execution", "role", "task")},
        "prompt": prompt,
        "prompt_sha256": digest,
    }


def learning_provenance(
    records: list[dict[str, Any]], run_dir: Path
) -> dict[str, object]:
    """Expose only the journal identities a read-only learning pass may cite."""

    decisions = [
        {key: record[key] for key in ("id", "task")}
        for record in records
        if record.get("type") == "decision"
        and learning_segment(record.get("id"))
        and learning_text(record.get("task"))
    ]
    executions = []
    for record in records:
        if record.get("type") != "execution":
            continue
        authority = execution_learning_provenance(run_dir, record)
        if authority is not None:
            executions.append(authority)
    verifications = [
        {
            key: record.get(key)
            for key in ("id", "task", "result", "criterion", "observation")
        }
        for record in records
        if record.get("type") == "verification"
        and record.get("result") in {"failed", "inconclusive"}
        and learning_segment(record.get("id"))
        and learning_text(record.get("task"))
        and all(
            record.get(key) is None or isinstance(record.get(key), str)
            for key in ("criterion", "observation")
        )
    ]
    return {
        "decisions": decisions,
        "executions": executions,
        "failed_or_inconclusive_verifications": verifications,
    }


def canonical_payload(value: object) -> dict[str, object] | None:
    """Return a validation payload without dictionary insertion-order concerns."""

    if not isinstance(value, dict):
        return None
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def is_passing_gated_payload(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("ok") is True
        and value.get("profile") == "gates"
        and value.get("issues") == []
    )


def recompute_pre_close_validation(
    run_dir: Path, records: list[dict[str, Any]]
) -> dict[str, object] | None:
    """Run gated validation against the journal prefix before ``run_closed``."""

    if not records or records[-1].get("type") != "run_closed":
        raise ArchiveRefusal("forge: archive refused — run_closed must be final")
    try:
        prefix = b"".join(
            json.dumps(
                {key: value for key, value in record.items() if key != "_line"},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
            for record in records[:-1]
        )
        with tempfile.TemporaryDirectory(prefix="forge-pre-close-") as temporary:
            mirror = Path(temporary) / run_dir.name
            mirror.mkdir()
            for child in run_dir.iterdir():
                if child.name == "journal.jsonl":
                    continue
                if child.name in {
                    journal_engine.BATCH_LOCK_NAME,
                    journal_engine.BATCH_RECEIPTS_NAME,
                }:
                    directory: int | None = None
                    try:
                        directory, _observation = journal_engine._open_bound_directory(
                            run_dir
                        )
                        sidecar, _file_observation = journal_engine._read_bound_regular(
                            directory, child.name
                        )
                    finally:
                        if directory is not None:
                            os.close(directory)
                    if child.name == journal_engine.BATCH_RECEIPTS_NAME:
                        retained: list[bytes] = []
                        for line in sidecar.splitlines(keepends=True):
                            try:
                                receipt = json.loads(line.decode("utf-8"))
                            except (UnicodeError, ValueError, RecursionError) as exc:
                                raise ArchiveRefusal(
                                    "forge: archive refused — invalid batch receipt ledger"
                                ) from exc
                            size = receipt.get("journal_size") if isinstance(receipt, dict) else None
                            if (
                                type(size) is int
                                and 0 < int(size) <= len(prefix)
                                and receipt.get("journal_sha256")
                                == hashlib.sha256(prefix[: int(size)]).hexdigest()
                            ):
                                retained.append(line)
                        sidecar = b"".join(retained)
                    (mirror / child.name).write_bytes(sidecar)
                    continue
                os.symlink(
                    child.resolve(),
                    mirror / child.name,
                    target_is_directory=child.is_dir(),
                )
            (mirror / "journal.jsonl").write_bytes(prefix)
            return canonical_payload(validate_run(mirror, gates=True))
    except (OSError, TypeError, ValueError) as exc:
        raise ArchiveRefusal(
            f"forge: archive refused — could not recompute pre-close validation: {exc}"
        ) from exc


def candidate_for(record: dict[str, Any]) -> str:
    candidate = record.get("candidate")
    if isinstance(candidate, str) and candidate:
        return candidate
    check = record.get("check")
    if not isinstance(check, str):
        return NONE
    reviewed_range = HEAD_RANGE_IN_TEXT.search(check)
    if reviewed_range:
        return reviewed_range.group(0)
    matches = HEAD_IN_TEXT.findall(check)
    return matches[-1] if matches else NONE


def verdict_for(record: dict[str, Any]) -> str:
    verdict = record.get("verdict")
    if isinstance(verdict, str) and verdict:
        return verdict
    observation = record.get("observation")
    match = VERDICT_IN_TEXT.search(observation) if isinstance(observation, str) else None
    return match.group(1) if match else NONE


def iteration_for(record: dict[str, Any]) -> str:
    iteration = record.get("iteration")
    if isinstance(iteration, int) and not isinstance(iteration, bool) and iteration > 0:
        return str(iteration)
    for field in ("observation", "check"):
        value = record.get(field)
        match = ITERATION_IN_TEXT.search(value) if isinstance(value, str) else None
        if match:
            return match.group(1)
    return NONE


def record_identifier(record: dict[str, Any]) -> str:
    value = record.get("id")
    return value if isinstance(value, str) and value else display(record.get("type"))


def record_line_number(record: dict[str, Any]) -> int | None:
    value = record.get("_line")
    return value if isinstance(value, int) and value > 0 else None


def result_verdict_conflicts(record: dict[str, Any]) -> bool:
    binding = record.get("binding")
    review = binding.get("review") if isinstance(binding, dict) else None
    if not isinstance(review, dict):
        return False
    verdict = review.get("verdict")
    return bool(
        (verdict == "PASS" and record.get("result") != "passed")
        or (verdict == "BLOCK" and record.get("result") != "failed")
    )


def required_binding_records(
    records: list[dict[str, Any]], activated: bool
) -> list[dict[str, Any]]:
    if not activated:
        return []
    if "binding-only" not in RENDERER_CONTROLS:
        authoritative_discrepancy("structured_chain_mismatch")
    result: list[dict[str, Any]] = []
    for record in records:
        kind = record.get("type")
        criterion = record.get("criterion")
        is_gate = bool(
            kind == "verification"
            and isinstance(criterion, str)
            and criterion.startswith(("gate-1: ", "gate-2: ", "gate-3: "))
        )
        is_chain_decision = bool(
            kind == "decision"
            and record.get("outcome") in journal_engine.CHAIN_DECISION_OUTCOMES
        )
        required = is_gate or is_chain_decision
        carries_binding = "binding" in record
        if not (required or carries_binding):
            continue
        if result_verdict_conflicts(record):
            authoritative_discrepancy("result_verdict_conflict")
        if not isinstance(record.get("binding"), dict):
            if required and record.get("outcome") == "chain-approval":
                authoritative_discrepancy("unbound_approval")
            authoritative_discrepancy("structured_chain_mismatch")
        if not journal_engine._binding_shape_valid(record["binding"], record=record):
            if result_verdict_conflicts(record):
                authoritative_discrepancy("result_verdict_conflict")
            authoritative_discrepancy("structured_chain_mismatch")
        result.append(record)
    return result


def binding_chain_ids(records: list[dict[str, Any]], activated: bool) -> set[str]:
    result: set[str] = set()
    for record in required_binding_records(records, activated):
        binding = record["binding"]
        assert isinstance(binding, dict)
        source = binding.get("source_record")
        assert isinstance(source, dict)
        chain_id = source.get("chain_id")
        assert isinstance(chain_id, str)
        result.add(chain_id)
    return result


def require_exact_carried_record(
    chain: ChainSnapshot,
    binding_id: str,
    journal_record: Mapping[str, object],
) -> None:
    """Require the selected event-carried record to equal the journal record.

    The task-03 resolver intentionally accepts an expected-field subset.  Archive
    rendering has the stronger DM-001 obligation: after removing only the
    reader-added ``_line`` member, the complete key set and every value must be
    canonically identical to exactly one record carried by the cited event.
    """

    expected = {
        name: value for name, value in journal_record.items() if name != "_line"
    }
    carried: list[dict[str, object]] = []
    for event in chain.events:
        payload = event.get("payload")
        carrier = (
            payload.get("details")
            if chain.family == "commit" and isinstance(payload, dict)
            else payload
        )
        batch = carrier.get("journal_batch") if isinstance(carrier, dict) else None
        batch_records = batch.get("records") if isinstance(batch, dict) else None
        if not isinstance(batch_records, list):
            continue
        for candidate in batch_records:
            candidate_binding = (
                candidate.get("binding") if isinstance(candidate, dict) else None
            )
            if (
                isinstance(candidate, dict)
                and isinstance(candidate_binding, dict)
                and candidate_binding.get("binding_id") == binding_id
            ):
                carried.append(candidate)
    if (
        "carried-record-equality" not in RENDERER_CONTROLS
        or len(carried) != 1
        or journal_engine._canonical_json_bytes(carried[0])
        != journal_engine._canonical_json_bytes(expected)
    ):
        authoritative_discrepancy("structured_chain_mismatch")


def resolve_captured_ingest_bindings(
    snapshot: CapturedIngestSnapshot,
    chain_records: Sequence[dict[str, Any]],
    all_records: Sequence[dict[str, Any]],
) -> dict[int, dict[str, object]]:
    """Resolve every ingest-created binding against captured replay entries."""

    if "captured-ingest-binding" not in RENDERER_CONTROLS:
        authoritative_discrepancy("structured_chain_mismatch")
    chain_id = snapshot.chain.chain_id
    task = snapshot.outcome_map.get("task")
    task_status = snapshot.outcome_map.get("task_status")
    if not chain_records or not isinstance(task, str):
        authoritative_discrepancy("structured_chain_mismatch")

    landings = [
        record
        for record in chain_records
        if record.get("type") == "decision"
        and record.get("outcome") == "chain-landing"
    ]
    if (
        len(landings) != 1
        or landings[0].get("basis") != list(snapshot.citations)
        or any(record.get("task") != task for record in chain_records)
    ):
        authoritative_discrepancy("structured_chain_mismatch")

    chain_lines = [record_line_number(record) for record in chain_records]
    if any(line is None for line in chain_lines):
        authoritative_discrepancy("structured_chain_mismatch")
    terminal = [
        record
        for record in all_records
        if record.get("type") == "task"
        and record.get("id") == task
        and record.get("status") == task_status
        and isinstance(record_line_number(record), int)
        and record_line_number(record) > max(int(line) for line in chain_lines)
    ]
    if len(terminal) != 1:
        authoritative_discrepancy("structured_chain_mismatch")

    eligible = snapshot.eligible_records
    if len(chain_records) != len(eligible):
        authoritative_discrepancy("structured_chain_mismatch")
    resolved: dict[int, dict[str, object]] = {}
    for record, expected in zip(chain_records, eligible):
        binding = record.get("binding")
        source = binding.get("source_record") if isinstance(binding, dict) else None
        digest = source.get("event_digest") if isinstance(source, dict) else None
        if (
            not isinstance(binding, dict)
            or not isinstance(source, dict)
            or source.get("chain_id") != chain_id
            or not isinstance(digest, str)
            or digest != expected.event_digest
            or record.get("type") != expected.record_type
            or (
                expected.criterion is not None
                and record.get("criterion") != expected.criterion
            )
            or (
                expected.result is not None
                and record.get("result") != expected.result
            )
            or (
                expected.outcome is not None
                and record.get("outcome") != expected.outcome
            )
        ):
            authoritative_discrepancy("structured_chain_mismatch")
        matches = [
            entry for entry in snapshot.replay_entries if entry[4] == digest
        ]
        if len(matches) != 1:
            authoritative_discrepancy("structured_chain_mismatch")
        event, prior, event_state, _carried, _source_digest = matches[0]
        try:
            valid = journal_builders._binding_matches_source_fact(
                binding,
                record,
                event,
                prior,
                event_state,
                family=snapshot.chain.family,
            ) and journal_builders._binding_is_current(
                snapshot.chain.state,
                binding,
                record,
                event,
                prior,
                event_state,
                snapshot.replay_entries,
                chain_family=snapshot.chain.family,
            )
        except (KeyError, TypeError, ValueError, RuntimeError):
            valid = False
        if not valid:
            authoritative_discrepancy("structured_chain_mismatch")
        line = record_line_number(record)
        if line is None or line in resolved:
            authoritative_discrepancy("structured_chain_mismatch")
        resolved[line] = dict(binding)
    return resolved


def resolve_archive_bindings(
    repo: Path,
    run_dir: Path,
    records: list[dict[str, Any]],
    package: ChainPackage,
    activated: bool,
) -> dict[int, dict[str, object]]:
    required = required_binding_records(records, activated)
    if not required:
        return {}
    captured = {snapshot.chain.chain_id: snapshot for snapshot in package.captured}
    required_by_chain: dict[str, list[dict[str, Any]]] = {}
    for record in required:
        binding = record.get("binding")
        source = binding.get("source_record") if isinstance(binding, dict) else None
        chain_id = source.get("chain_id") if isinstance(source, dict) else None
        if not isinstance(chain_id, str):
            authoritative_discrepancy("structured_chain_mismatch")
        required_by_chain.setdefault(chain_id, []).append(record)
    live_ids = set(required_by_chain) - set(captured)
    if live_ids and package.root is None:
        authoritative_discrepancy("missing_chain_artifact")
    directory: int | None = None
    resolved: dict[int, dict[str, object]] = {}
    try:
        if live_ids:
            assert package.root is not None
            directory = os.open(
                package.root,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
            )
            if file_identity(os.fstat(directory)) != package.root_identity:
                authoritative_discrepancy("snapshot_changed")
        register_archive_merge_reducer()
        chains = {chain.chain_id: chain for chain in package.chains}
        if set(required_by_chain) - set(chains):
            authoritative_discrepancy("missing_chain_artifact")
        for chain_id, snapshot in captured.items():
            chain_resolved = resolve_captured_ingest_bindings(
                snapshot, required_by_chain.get(chain_id, ()), records
            )
            if set(chain_resolved) & set(resolved):
                authoritative_discrepancy("structured_chain_mismatch")
            resolved.update(chain_resolved)
        for record in (
            record
            for chain_id in sorted(live_ids, key=os.fsencode)
            for record in required_by_chain[chain_id]
        ):
            binding = record.get("binding")
            assert isinstance(binding, dict)
            source = binding.get("source_record")
            assert isinstance(source, dict)
            chain_id = str(source["chain_id"])
            expected_fields = {
                name: value
                for name, value in record.items()
                if name not in {"_line", "binding"}
            }
            require_exact_carried_record(
                chains[chain_id], str(binding["binding_id"]), record
            )
            task_id = record.get("task")
            try:
                assert directory is not None
                replayed = journal_builders._resolve_binding_from_descriptor(
                    repo,
                    directory,
                    chain_id,
                    str(binding["binding_id"]),
                    expected_type=str(record.get("type")),
                    expected_fields=expected_fields,
                    expected_run_id=run_dir.name,
                    expected_task_id=task_id if isinstance(task_id, str) else None,
                )
            except (OSError, RuntimeError, ValueError, journal_engine.CoordinationRefusal):
                authoritative_discrepancy("structured_chain_mismatch")
            if replayed != binding:
                authoritative_discrepancy("structured_chain_mismatch")
            line = record_line_number(record)
            if line is None or line in resolved:
                authoritative_discrepancy("structured_chain_mismatch")
            resolved[line] = dict(binding)
        return resolved
    finally:
        if directory is not None:
            os.close(directory)


def legacy_candidate(record: dict[str, Any]) -> str | None:
    """Recognize only full historical review-final candidate sentences."""

    check = record.get("check")
    if not isinstance(check, str):
        return None
    staged = LEGACY_STAGED_REVIEW.fullmatch(check)
    if staged is not None:
        return staged.group("candidate")
    reviewed_range = LEGACY_RANGE_REVIEW.fullmatch(check)
    if reviewed_range is not None:
        return f"{reviewed_range.group('base')}...{reviewed_range.group('head')}"
    reviewed_range = LEGACY_TWO_DOT_REVIEW.fullmatch(check)
    if reviewed_range is not None:
        return f"{reviewed_range.group('base')}..{reviewed_range.group('head')}"
    return None


def legacy_review_values(
    record: dict[str, Any], discrepancies: list[Discrepancy]
) -> tuple[str, str, str]:
    """Render pre-activation prose as bounded display, never authority."""

    criterion = record.get("criterion")
    is_review = criterion == "gate-3: review-final verdict"
    prose = "\n".join(
        value
        for name in ("check", "observation")
        if isinstance((value := record.get(name)), str)
    )
    if not is_review:
        if VERDICT_IN_TEXT.search(prose):
            discrepancies.append(
                Discrepancy(
                    "ignored_nonreview_verdict",
                    record_line_number(record),
                    record_identifier(record),
                    "PASS/BLOCK prose on a non-review gate was ignored",
                )
            )
        return NONE, NONE, NONE
    candidate = legacy_candidate(record)
    check = record.get("check")
    if candidate is None and isinstance(check, str) and HEAD_IN_TEXT.search(check):
        discrepancies.append(
            Discrepancy(
                "ambiguous_legacy_candidate",
                record_line_number(record),
                record_identifier(record),
                "hash-bearing review prose did not match one anchored legacy candidate shape",
            )
        )
        candidate = UNBOUND
    elif candidate is None:
        candidate = UNBOUND
    observation = record.get("observation")
    review = None
    if isinstance(observation, str):
        review = LEGACY_REVIEW_OBSERVATION.fullmatch(observation)
        if review is None:
            review = LEGACY_SHORT_REVIEW_OBSERVATION.fullmatch(observation)
    verdict = review.group("verdict") if review is not None else UNBOUND
    iteration = review.group("iteration") if review is not None else UNBOUND
    if (
        (verdict == "PASS" and record.get("result") != "passed")
        or (verdict == "BLOCK" and record.get("result") != "failed")
    ):
        authoritative_discrepancy("result_verdict_conflict")
    return candidate, verdict, iteration


def legacy_discrepancies(
    records: list[dict[str, Any]], activated: bool
) -> list[Discrepancy]:
    result: list[Discrepancy] = []
    for record in records:
        legacy_decision = isinstance(record.get("decision"), str)
        structured_decision = isinstance(record.get("resolution"), str)
        if (
            record.get("type") == "decision"
            and legacy_decision
            and (not activated or structured_decision)
        ):
            result.append(
                Discrepancy(
                    "legacy_decision_shape",
                    record_line_number(record),
                    record_identifier(record),
                    "legacy decision field retained as escaped display material",
                )
            )
        criterion = record.get("criterion")
        if (
            not activated
            and
            record.get("type") == "verification"
            and isinstance(criterion, str)
            and criterion.startswith(("gate-1: ", "gate-2: ", "gate-3: "))
        ):
            legacy_review_values(record, result)
    if any(item.code not in LEGACY_DISPLAY_DISCREPANCIES for item in result):
        authoritative_discrepancy("structured_chain_mismatch")
    return result


def longest_backtick_run(value: str) -> int:
    return max((len(match.group(0)) for match in re.finditer(r"`+", value)), default=0)


def render_chain_state_block(raw: bytes) -> str:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeError:
        authoritative_discrepancy("structured_chain_mismatch")
    fence = max(3, longest_backtick_run(decoded) + 1)
    digest = hashlib.sha256(raw).hexdigest()
    separator = "" if raw.endswith(b"\n") else "\n"
    ticks = "`" * fence
    return (
        f"<!-- {CHAIN_STATE_MARKER} v1 bytes={len(raw)} sha256={digest} fence={fence} -->\n"
        f"{ticks}json\n"
        f"{decoded}{separator}"
        f"{ticks}\n"
        f"<!-- /{CHAIN_STATE_MARKER} -->\n"
    )


def render_chain_event_block(raw: bytes) -> str:
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) <= EVENT_EMBED_LIMIT:
        payload = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        return (
            f"<!-- {CHAIN_EVIDENCE_MARKER} v1 encoding=base64url "
            f"bytes={len(raw)} sha256={digest} -->\n"
            f"{payload}\n"
            f"<!-- /{CHAIN_EVIDENCE_MARKER} -->\n"
        )
    return (
        f"<!-- {CHAIN_EVIDENCE_MARKER} v1 encoding=UNEMBEDDED "
        f"bytes={len(raw)} sha256={digest} -->\n"
        f"<!-- /{CHAIN_EVIDENCE_MARKER} -->\n"
    )


def binding_candidate_display(binding: dict[str, object]) -> str:
    candidate = binding.get("candidate")
    if not isinstance(candidate, dict):
        return UNBOUND
    value = candidate.get("value")
    if candidate.get("kind") == "git-range" and isinstance(value, dict):
        return f"{value.get('base')}..{value.get('head')}"
    return display(value)


def render_discrepancy_section(discrepancies: list[Discrepancy]) -> list[str]:
    lines = ["## Binding discrepancies", ""]
    if not discrepancies:
        return [*lines, NONE, ""]
    for item in discrepancies:
        location = f"journal line {item.record_line}" if item.record_line else "journal"
        chain = f"; chain {item.chain_id}" if item.chain_id else ""
        lines.append(
            f"- `{item.code}` — {location}; record {item.record_id}{chain}; {item.detail}"
        )
    lines.append("")
    return lines


def render_chain_sections(
    package: ChainPackage,
    records: list[dict[str, Any]],
    bindings: dict[int, dict[str, object]],
    discrepancies: list[Discrepancy],
) -> list[str]:
    lines = ["## Chain evidence", ""]
    if not package.chains:
        return [*lines, NONE, ""]
    for chain in package.chains:
        selected = [
            (line, binding)
            for line, binding in sorted(bindings.items())
            if isinstance(binding.get("source_record"), dict)
            and binding["source_record"].get("chain_id") == chain.chain_id
        ]
        related = [item for item in discrepancies if item.chain_id == chain.chain_id]
        lines.extend(
            [
                f"### {chain.chain_id}",
                "",
                f"Chain family: {chain.family}",
                "",
                f"State bytes: {len(chain.state_file.raw)}",
                "",
                f"State SHA-256: {hashlib.sha256(chain.state_file.raw).hexdigest()}",
                "",
                f"Event bytes: {len(chain.events_file.raw)}",
                "",
                f"Event SHA-256: {hashlib.sha256(chain.events_file.raw).hexdigest()}",
                "",
                f"Event count: {len(chain.events)}",
                "",
                f"First event timestamp: {display(chain.first_at)}",
                "",
                f"Last event timestamp: {display(chain.last_at)}",
                "",
                f"Digest-chain head: {chain.event_head}",
                "",
                "Selected binding IDs:",
                "",
                *(
                    [f"- {binding['binding_id']}" for _, binding in selected]
                    if selected
                    else [NONE]
                ),
                "",
                "Journal-line mappings:",
                "",
                *(
                    [
                        f"- line {line}: {binding['binding_id']}"
                        for line, binding in selected
                    ]
                    if selected
                    else [NONE]
                ),
                "",
                "Discrepancies:",
                "",
                *(
                    [f"- `{item.code}`: {item.detail}" for item in related]
                    if related
                    else [NONE]
                ),
                "",
                render_chain_state_block(chain.state_file.raw).removesuffix("\n"),
                render_chain_event_block(chain.events_file.raw).removesuffix("\n"),
            ]
        )
    return lines


def enforce_archive_size(content: str) -> bytes:
    encoded = content.encode("utf-8")
    if "archive-size" not in RENDERER_CONTROLS or len(encoded) > ARCHIVE_SIZE_LIMIT:
        raise ArchiveRefusal("forge: archive refused — rendered archive exceeds 16 MiB")
    return encoded


def document_references(value: str) -> list[str]:
    """Extract document paths while retaining ``value`` as the archive label."""

    return path_tokens(value, context="basis")


def basis_label(value: str) -> str:
    """Keep the basis text as the delimiter label after resolving references."""

    return value


def safe_basis_relative(value: str) -> Path | None:
    relative = Path(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        return None
    return relative


def snapshot_basis_document(
    root: Path, relative: Path, label: str
) -> tuple[ExactFile, tuple[tuple[str, FileIdentity], ...]]:
    """Read a cited document through a stable no-follow descriptor chain."""

    descriptors: list[int] = []
    components: list[tuple[str, FileIdentity]] = []
    diagnostic = f"forge: archive refused — unsafe basis document: {label}"
    try:
        if (
            "basis-snapshot" not in RENDERER_CONTROLS
            or safe_basis_relative(os.fspath(relative)) != relative
        ):
            raise ArchiveRefusal(diagnostic)
        root_before = os.lstat(root)
        if not owner_directory(root_before):
            raise ArchiveRefusal(diagnostic)
        root_descriptor = os.open(
            root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        descriptors.append(root_descriptor)
        root_identity = file_identity(root_before)
        if file_identity(os.fstat(root_descriptor)) != root_identity:
            raise ArchiveRefusal(diagnostic)
        components.append((".", root_identity))

        parent = root_descriptor
        traversed: list[str] = []
        for component in relative.parts[:-1]:
            before = os.stat(component, dir_fd=parent, follow_symlinks=False)
            if not owner_directory(before):
                raise ArchiveRefusal(diagnostic)
            child = os.open(
                component,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent,
            )
            descriptors.append(child)
            identity = file_identity(before)
            if file_identity(os.fstat(child)) != identity:
                raise ArchiveRefusal(diagnostic)
            traversed.append(component)
            components.append((os.fspath(Path(*traversed)), identity))
            parent = child

        leaf = relative.parts[-1]
        before = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        if not owner_regular(before):
            raise ArchiveRefusal(diagnostic)
        descriptor = os.open(
            leaf,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        descriptors.append(descriptor)
        identity = file_identity(before)
        if file_identity(os.fstat(descriptor)) != identity:
            raise ArchiveRefusal(diagnostic)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        if (
            file_identity(os.fstat(descriptor)) != identity
            or file_identity(os.stat(leaf, dir_fd=parent, follow_symlinks=False))
            != identity
            or len(raw) != identity.size
            or file_identity(os.lstat(root)) != root_identity
        ):
            raise ArchiveRefusal(diagnostic)
        for index, (_, expected) in enumerate(components):
            if file_identity(os.fstat(descriptors[index])) != expected:
                raise ArchiveRefusal(diagnostic)
            if index:
                rebound = os.stat(
                    relative.parts[index - 1],
                    dir_fd=descriptors[index - 1],
                    follow_symlinks=False,
                )
                if file_identity(rebound) != expected:
                    raise ArchiveRefusal(diagnostic)
        return ExactFile(os.fspath(relative), raw, identity), tuple(components)
    except FileNotFoundError:
        raise
    except ArchiveRefusal:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise ArchiveRefusal(diagnostic) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def document_path(repo: Path, run_dir: Path, value: str) -> Path | None:
    relative = safe_basis_relative(value)
    if relative is None:
        return None
    for root in (run_dir, repo):
        try:
            snapshot_basis_document(root, relative, value)
        except FileNotFoundError:
            continue
        return root / relative
    return None


def basis_documents(
    repo: Path, run_dir: Path, decisions: list[dict[str, Any]]
) -> list[BasisDocument]:
    documents: list[BasisDocument] = []
    seen: set[tuple[int, int]] = set()
    for decision in decisions:
        basis = decision.get("basis")
        if not isinstance(basis, list):
            continue
        for value in basis:
            if not isinstance(value, str) or not value:
                continue
            for reference in document_references(value):
                relative = safe_basis_relative(reference)
                if relative is None:
                    continue
                captured: tuple[
                    Path, ExactFile, tuple[tuple[str, FileIdentity], ...]
                ] | None = None
                for root in (run_dir, repo):
                    try:
                        exact, directories = snapshot_basis_document(
                            root, relative, value
                        )
                    except FileNotFoundError:
                        continue
                    captured = (root, exact, directories)
                    break
                if captured is None:
                    continue
                root, exact, directories = captured
                identity_key = (exact.identity.device, exact.identity.inode)
                if identity_key in seen:
                    continue
                try:
                    # Decode exact bytes directly; universal-newline conversion
                    # would change the delimited source body.
                    content = exact.raw.decode("utf-8")
                except UnicodeError as exc:
                    raise ArchiveRefusal(
                        f"forge: archive refused — basis document is not UTF-8: {value}"
                    ) from exc
                seen.add(identity_key)
                documents.append(
                    BasisDocument(
                        value,
                        content,
                        root / relative,
                        exact,
                        root,
                        relative,
                        directories,
                    )
                )
    return documents


def recheck_basis_documents(documents: Sequence[BasisDocument]) -> None:
    for document in documents:
        try:
            current, directories = snapshot_basis_document(
                document.root, document.relative, document.label
            )
        except FileNotFoundError:
            raise ArchiveRefusal(
                "forge: archive refused — basis document changed during rendering: "
                f"{document.label}"
            )
        if (
            current.identity != document.exact.identity
            or current.raw != document.exact.raw
            or directories != document.directory_identities
        ):
            raise ArchiveRefusal(
                "forge: archive refused — basis document changed during rendering: "
                f"{document.label}"
            )


def render_archive(
    *,
    repo: Path,
    run_dir: Path,
    records: list[dict[str, Any]],
    journal_raw: bytes | None = None,
    closing: ClosingMode | None = None,
    closing_head: str | None = None,
    post_close: dict[str, Any],
    audit_fragment: str,
    package: ChainPackage | None = None,
    bindings: dict[int, dict[str, object]] | None = None,
    discrepancies: list[Discrepancy] | None = None,
    documents: Sequence[BasisDocument] | None = None,
    dispense_targets: Sequence[str] = (),
    dispense_reason: str | None = None,
) -> str:
    started = only_record(records, "run_started")
    closed = only_record(records, "run_closed")
    if closing is None:
        if closing_head is None:
            raise ArchiveRefusal("forge: archive refused — invalid closing HEAD")
        closing = ClosingMode(closing_head)
    elif closing_head is not None:
        raise ArchiveRefusal("forge: archive refused — invalid closing HEAD")
    if journal_raw is None:
        journal_raw = b"".join(
            json.dumps(
                {name: value for name, value in record.items() if name != "_line"},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
            for record in records
        )
    if package is None:
        package = ChainPackage(None, None, (), ())
    if bindings is None:
        bindings = {}
    if discrepancies is None:
        discrepancies = legacy_discrepancies(
            records, started.get("writer_contract") == WRITER_CONTRACT
        )
    if documents is None:
        decisions_for_documents = [
            record for record in records if record.get("type") == "decision"
        ]
        documents = basis_documents(repo, run_dir, decisions_for_documents)
    run_id = run_dir.name
    if started.get("run_id") != run_id or closed.get("judgment") != "passed":
        raise ArchiveRefusal("forge: archive refused — invalid run journal")
    recorded_repo = started.get("repo")
    try:
        same_repo = (
            isinstance(recorded_repo, str)
            and Path(recorded_repo).expanduser().resolve(strict=True) == repo
        )
    except (OSError, RuntimeError, ValueError):
        same_repo = False
    if not same_repo:
        raise ArchiveRefusal(
            "forge: archive refused — run repository does not match current repository"
        )
    starting_head = started.get("repo_head")
    if not isinstance(starting_head, str) or not HEX_HEAD.fullmatch(starting_head):
        raise ArchiveRefusal("forge: archive refused — invalid starting HEAD")
    start_commit = run_git(repo, "cat-file", "-e", f"{starting_head}^{{commit}}")
    if start_commit.returncode != 0:
        raise ArchiveRefusal("forge: archive refused — starting HEAD is not a repository commit")
    pre_close = canonical_payload(closed.get("validation"))
    if not is_passing_gated_payload(pre_close):
        raise ArchiveRefusal("forge: archive refused — pre-close gated validation did not pass")

    latest_tasks: dict[str, dict[str, Any]] = {}
    task_order: list[str] = []
    for record in records:
        if record.get("type") != "task":
            continue
        task_id = record.get("id")
        if not isinstance(task_id, str) or not task_id:
            continue
        if task_id not in latest_tasks:
            task_order.append(task_id)
        # Terminal task updates are permitted to be terse. Carry the durable
        # task contract forward while taking the final outcome from the latest
        # entry.
        previous = latest_tasks.get(task_id, {})
        merged = dict(record)
        if "goal" not in record and "goal" in previous:
            merged["goal"] = previous["goal"]
        if "acceptance" not in record and "acceptance" in previous:
            merged["acceptance"] = previous["acceptance"]
        latest_tasks[task_id] = merged
    decisions = [record for record in records if record.get("type") == "decision"]
    activated = started.get("writer_contract") == WRITER_CONTRACT
    raw_lines = journal_raw_lines(journal_raw)
    gates = [
        record
        for record in records
        if record.get("type") == "verification"
        and isinstance(record.get("criterion"), str)
        and record["criterion"].startswith(("gate-1: ", "gate-2: ", "gate-3: "))
    ]

    lines = [
        f"# Durable intent archive: {run_id}",
        "",
        "## Goal",
        "",
        display(started.get("goal")),
        "",
        "## Tasks",
        "",
    ]
    if not task_order:
        lines.extend([NONE, ""])
    for task_id in task_order:
        task = latest_tasks[task_id]
        final_outcome = task.get("outcome")
        lines.extend(
            [
                f"### {task_id}",
                "",
                f"Goal: {display(task.get('goal'))}",
                "",
                "Acceptance criteria:",
                "",
                *markdown_list(task.get("acceptance")),
                "",
                f"Final status: {display(task.get('status'))}",
                "",
                f"Final outcome: {display(final_outcome)}",
                "",
            ]
        )

    lines.extend(["## Decisions", ""])
    if not decisions:
        lines.extend([NONE, ""])
    for number, decision in enumerate(decisions, start=1):
        decision_id = display(decision.get("id"))
        if decision_id == NONE:
            decision_id = f"Decision {number}"
        lines.extend(
            [
                f"### {decision_id}",
                "",
                f"Task: {display(decision.get('task'))}",
                "",
                f"Finding: {display(decision.get('finding'))}",
                "",
                f"Outcome: {display(decision.get('outcome'))}",
                "",
                f"Resolution: {display(decision.get('resolution'))}",
                "",
                "Basis:",
                "",
                *markdown_list(decision.get("basis")),
                "",
            ]
        )
        legacy_value = decision.get("decision")
        if isinstance(legacy_value, str):
            physical_line = record_line_number(decision)
            raw_line = raw_lines.get(physical_line or -1)
            if raw_line is None:
                authoritative_discrepancy("snapshot_changed")
            escaped = html.escape(
                json.dumps(legacy_value, ensure_ascii=False), quote=False
            )
            lines.extend(
                [
                    "Decision (legacy field):",
                    "",
                    f"<pre>{escaped}</pre>",
                    "",
                    f"Physical journal line: {physical_line}",
                    "",
                    f"Raw-line SHA-256: {hashlib.sha256(raw_line).hexdigest()}",
                    "",
                ]
            )

    lines.extend(
        [
            "## Learning provenance",
            "",
            "<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->",
            *canonical_json(learning_provenance(records, run_dir)),
            "<!-- END FORGE LEARNING PROVENANCE v1 -->",
            "",
        ]
    )

    lines.extend(["## Verbatim basis documents", ""])
    referenced_documents = {
        path
        for decision in decisions
        for value in decision.get("basis", [])
        if isinstance(value, str)
        for reference in document_references(value)
        if (path := document_path(repo, run_dir, reference)) is not None
    }
    if {document.path for document in documents} != referenced_documents:
        raise ArchiveRefusal("forge: archive refused — could not copy every basis document")
    verbatim_documents = verbatim_basis_documents(package, documents)
    if not verbatim_documents:
        lines.extend([NONE, ""])
    for document in verbatim_documents:
        source = document.label
        content = document.content
        lines.extend([f"### {source}", "", f"<!-- BEGIN VERBATIM DOCUMENT: {source} -->"])
        # Do not normalize, trim, or add bytes inside the delimited source body.
        lines[-1] += "\n" + content + f"<!-- END VERBATIM DOCUMENT: {source} -->"
        lines.append("")

    lines.extend(
        [
            "## Gate evidence",
            "",
            "| Gate | Check | Candidate | Result | Reviewer verdict | Iteration | Binding source | Binding status |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    if not gates:
        lines.append(
            f"| {NONE} | {NONE} | {NONE} | {NONE} | {NONE} | {NONE} | {NONE} | {NONE} |"
        )
    else:
        for gate in gates:
            check = gate.get("check")
            line = record_line_number(gate)
            binding = bindings.get(line or -1)
            if activated:
                if binding is None:
                    authoritative_discrepancy("structured_chain_mismatch")
                source = binding.get("source_record")
                review = binding.get("review")
                assert isinstance(source, dict)
                candidate = binding_candidate_display(binding)
                verdict = review.get("verdict") if isinstance(review, dict) else NONE
                iteration = review.get("iteration") if isinstance(review, dict) else NONE
                binding_source = f"{source['chain_id']}@{source['event_digest']}"
                binding_status = f"BOUND ({binding['binding_id']})"
            else:
                candidate, verdict, iteration = legacy_review_values(gate, [])
                binding_source = UNBOUND
                binding_status = UNBOUND
            lines.append(
                "| "
                + " | ".join(
                    table_cell(value)
                    for value in (
                        gate.get("criterion"),
                        check,
                        candidate,
                        gate.get("result"),
                        verdict,
                        iteration,
                        binding_source,
                        binding_status,
                    )
                )
                + " |"
            )
    lines.extend(
        [
            "",
            *render_discrepancy_section(discrepancies),
            *render_chain_sections(package, records, bindings, discrepancies),
            audit_fragment.rstrip("\n"),
            "",
            "## Provenance",
            "",
        ]
    )
    # FR-018(b): a dispensed archive records the exact operator-directed flags so the
    # committed record shows precisely what was excused and under which direction.
    dispensation_lines: list[str] = []
    if dispense_targets:
        dispensation_lines = [
            "### Operator-directed dispensation",
            "",
            *[
                f"- `--dispense-citation {target}`"
                for target in dispense_targets
            ],
            f"- `--dispense-reason {dispense_reason}`",
            "",
        ]
    closing_lines = (
        [
            f"Legacy recovered closing HEAD: {closing.head}",
            "",
            f"Legacy recovery approval: {closing.legacy_approval}",
            "",
        ]
        if closing.legacy_approval is not None
        else [f"Closing HEAD: {closing.head}", ""]
    )
    lines.extend(
        [
            f"Run ID: {run_id}",
            "",
            f"Starting HEAD: {starting_head}",
            "",
            *closing_lines,
            *dispensation_lines,
            "### Pre-close validation payload embedded in `run_closed`",
            "",
            *canonical_json(pre_close),
            "",
            "### Post-close validation result",
            "",
            *canonical_json(post_close),
            "",
        ]
    )
    return "\n".join(lines)


def run_audit(
    run_dir: Path,
    dispense_targets: Sequence[str] = (),
    dispense_reason: str | None = None,
) -> str:
    audit = Path(__file__).with_name("audit-commitments.py")
    command = [sys.executable, str(audit), "--run-dir", str(run_dir)]
    # FR-018(b): pass operator-directed dispensation through to the audit rerun so the
    # rendered fragment carries the visible Dispensed Citations section.
    for target in dispense_targets:
        command.extend(["--dispense-citation", target])
    if dispense_reason is not None:
        command.extend(["--dispense-reason", dispense_reason])
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise ArchiveRefusal(f"forge: archive refused — commitments audit failed: {exc}") from exc
    if result.returncode:
        if result.stdout:
            sys.stdout.buffer.write(result.stdout)
        if result.stderr:
            sys.stderr.buffer.write(result.stderr)
        raise SystemExit(result.returncode)
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
    try:
        fragment = result.stdout.decode("utf-8")
    except UnicodeError as exc:
        raise ArchiveRefusal("forge: archive refused — commitments audit output is invalid") from exc
    if not fragment.endswith("\n"):
        raise ArchiveRefusal("forge: archive refused — commitments audit output is invalid")
    return fragment


def legacy_closing_mode(
    *,
    repo: Path,
    target_run_dir: Path,
    recovered_head: str,
    approval: str,
    prove_approval: bool,
) -> ClosingMode:
    if (
        not isinstance(recovered_head, str)
        or HEX_HEAD.fullmatch(recovered_head) is None
        or not isinstance(approval, str)
        or (match := LEGACY_APPROVAL.fullmatch(approval)) is None
    ):
        raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL)
    if run_git(repo, "cat-file", "-e", f"{recovered_head}^{{commit}}").returncode != 0:
        raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL)
    try:
        target_records, target_raw = stable_journal_snapshot(target_run_dir)
        started = only_record(target_records, "run_started")
        closed = only_record(target_records, "run_closed")
    except ArchiveRefusal as exc:
        raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL) from exc
    if (
        started.get("writer_contract") == WRITER_CONTRACT
        or started.get("run_id") != target_run_dir.name
        or closed.get("judgment") != "passed"
        or not target_records
        or target_records[-1] is not closed
    ):
        raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL)
    recovery_run_id = match.group("run")
    decision_id = match.group("decision")
    if recovery_run_id == target_run_dir.name:
        raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL)
    if prove_approval:
        if "legacy-approval" not in RENDERER_CONTROLS:
            raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL)
        recovery_dir = repo / ".codex-orchestrator" / "runs" / recovery_run_id
        try:
            recovery_dir = recovery_dir.resolve(strict=True)
            recovery_dir.relative_to(
                (repo / ".codex-orchestrator" / "runs").resolve(strict=True)
            )
        except (OSError, RuntimeError, ValueError):
            raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL)
        try:
            current_owner = journal_engine._session_owner()
            owner_before = journal_engine._read_owner_observation(
                recovery_dir / "owner"
            )
        except (OSError, RuntimeError, ValueError, journal_engine.CoordinationRefusal) as exc:
            raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL) from exc
        if (
            owner_before is None
            or owner_before[1].pid != current_owner.pid
            or owner_before[1].host != current_owner.host
        ):
            raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL)
        try:
            recovery_records, recovery_raw = stable_journal_snapshot(recovery_dir)
        except ArchiveRefusal as exc:
            raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL) from exc
        starts = [
            record
            for record in recovery_records
            if record.get("type") == "run_started"
        ]
        decisions = [
            record
            for record in recovery_records
            if record.get("type") == "decision" and record.get("id") == decision_id
        ]
        expected_prefix = (
            f"legacy-archive-recovery: {target_run_dir.name} recovered closing HEAD "
            f"{recovered_head}; "
        )
        start_scope = starts[0].get("scope") if starts else None
        valid = bool(
            len(starts) == 1
            and starts[0].get("run_id") == recovery_run_id
            and starts[0].get("writer_contract") == WRITER_CONTRACT
            and isinstance(start_scope, list)
            and all(isinstance(item, str) and item for item in start_scope)
            and not any(
                record.get("type") == "run_closed" for record in recovery_records
            )
            and len(decisions) == 1
            and "decision" not in decisions[0]
            and decisions[0].get("outcome") == "operator_approval"
            and isinstance(decisions[0].get("resolution"), str)
            and decisions[0]["resolution"].startswith(expected_prefix)
            and decisions[0]["resolution"][len(expected_prefix) :].strip()
            and "\r" not in decisions[0]["resolution"]
            and "\n" not in decisions[0]["resolution"]
        )
        recorded_repo = starts[0].get("repo") if starts else None
        try:
            valid = bool(
                valid
                and isinstance(recorded_repo, str)
                and Path(recorded_repo).expanduser().resolve(strict=True) == repo
            )
        except (OSError, RuntimeError, ValueError):
            valid = False
        if valid:
            canonical_records = tuple(
                {
                    name: value
                    for name, value in record.items()
                    if name != "_line"
                }
                for record in recovery_records
            )
            try:
                for index, proposed in enumerate(canonical_records):
                    journal_engine._validate_proposed_record(
                        proposed,
                        run_id=recovery_run_id,
                        repo_root=repo,
                        scope=tuple(start_scope),
                        prior_records=canonical_records[:index],
                    )
            except (journal_engine.CoordinationRefusal, KeyError, TypeError, ValueError):
                valid = False
        if not valid:
            raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL)
        if journal_engine._stable_journal_read(recovery_dir / "journal.jsonl") != recovery_raw:
            authoritative_discrepancy("snapshot_changed")
        owner_after = journal_engine._read_owner_observation(recovery_dir / "owner")
        if (
            owner_after is None
            or owner_after[0] != owner_before[0]
            or owner_after[1].pid != current_owner.pid
            or owner_after[1].host != current_owner.host
        ):
            authoritative_discrepancy("snapshot_changed")
    if journal_engine._stable_journal_read(target_run_dir / "journal.jsonl") != target_raw:
        authoritative_discrepancy("snapshot_changed")
    return ClosingMode(recovered_head, approval)


def closing_mode_from_options(
    *,
    repo: Path,
    run_dir: Path,
    closing_head: str | None,
    legacy_recovered_head: str | None,
    legacy_approval: str | None,
    prove_legacy_approval: bool,
) -> ClosingMode:
    normal = closing_head is not None
    legacy = legacy_recovered_head is not None or legacy_approval is not None
    if normal == legacy:
        if legacy:
            raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL)
        raise ArchiveRefusal(
            "forge: archive refused — choose normal or paired legacy closing mode"
        )
    if normal:
        if legacy_approval is not None or not isinstance(closing_head, str) or not HEX_HEAD.fullmatch(closing_head):
            raise ArchiveRefusal("forge: archive refused — invalid closing HEAD")
        if run_git(repo, "cat-file", "-e", f"{closing_head}^{{commit}}").returncode != 0:
            raise ArchiveRefusal("forge: archive refused — closing HEAD is not a repository commit")
        return ClosingMode(closing_head)
    if legacy_recovered_head is None or legacy_approval is None:
        raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL)
    return legacy_closing_mode(
        repo=repo,
        target_run_dir=run_dir,
        recovered_head=legacy_recovered_head,
        approval=legacy_approval,
        prove_approval=prove_legacy_approval,
    )


def _render_archive_candidate(
    *,
    repo: Path,
    run_dir: Path,
    closing_head: str | None,
    legacy_recovered_head: str | None,
    legacy_approval: str | None,
    post_close_validation: Path,
    dispense_targets: Sequence[str],
    dispense_reason: str | None,
    prove_legacy_approval: bool,
) -> bytes:
    """Read, replay, and render exact candidate bytes without destination mutation."""

    try:
        records, journal_raw = stable_journal_snapshot(run_dir)
    except ArchiveRefusal as exc:
        if legacy_recovered_head is not None or legacy_approval is not None:
            raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL) from exc
        raise
    relative = f".forge/history/runs/{run_dir.name}.md"
    listed = run_git(repo, "ls-tree", "-z", "--name-only", "HEAD", "--", relative)
    if listed.returncode != 0:
        raise ArchiveRefusal("forge: archive refused — could not inspect archive history")
    if listed.stdout:
        raise ArchiveRefusal(f"forge: archive refused — archive already exists: {relative}")
    started = only_record(records, "run_started")
    closed = only_record(records, "run_closed")
    closing = closing_mode_from_options(
        repo=repo,
        run_dir=run_dir,
        closing_head=closing_head,
        legacy_recovered_head=legacy_recovered_head,
        legacy_approval=legacy_approval,
        prove_legacy_approval=prove_legacy_approval,
    )
    embedded_pre_close = canonical_payload(closed.get("validation"))
    if not is_passing_gated_payload(embedded_pre_close):
        raise ArchiveRefusal("forge: archive refused — pre-close gated validation did not pass")
    post_close = canonical_payload(
        read_json_file(os.fspath(post_close_validation), "post-close gated validation")
    )
    if not is_passing_gated_payload(post_close):
        raise ArchiveRefusal("forge: archive refused — post-close gated validation did not pass")
    audit_fragment = run_audit(run_dir, dispense_targets, dispense_reason)
    fresh_pre_close = recompute_pre_close_validation(run_dir, records)
    if not is_passing_gated_payload(fresh_pre_close) or embedded_pre_close != fresh_pre_close:
        raise ArchiveRefusal(
            "forge: archive refused — pre-close gated validation is stale or does not match journal"
        )
    fresh_validation = canonical_payload(validate_run(run_dir, gates=True))
    if not is_passing_gated_payload(fresh_validation) or post_close != fresh_validation:
        raise ArchiveRefusal(
            "forge: archive refused — post-close gated validation is stale or does not match journal"
        )
    activated = started.get("writer_contract") == WRITER_CONTRACT
    required_ids = binding_chain_ids(records, activated)
    if not activated:
        try:
            decoded_journal = journal_raw.decode("utf-8")
        except UnicodeError:
            raise ArchiveRefusal("forge: archive refused — invalid run journal")
        required_ids = set(CHAIN_ID_IN_TEXT.findall(decoded_journal))
    package = capture_archive_chain_package(
        repo,
        run_dir,
        records,
        required_ids,
        activated=activated,
    )
    bindings = resolve_archive_bindings(repo, run_dir, records, package, activated)
    discrepancies = legacy_discrepancies(records, activated)
    decisions = [record for record in records if record.get("type") == "decision"]
    documents = basis_documents(repo, run_dir, decisions)
    content = render_archive(
        repo=repo,
        run_dir=run_dir,
        records=records,
        journal_raw=journal_raw,
        closing=closing,
        post_close=post_close,
        audit_fragment=audit_fragment,
        package=package,
        bindings=bindings,
        discrepancies=discrepancies,
        documents=documents,
        dispense_targets=dispense_targets,
        dispense_reason=dispense_reason,
    )
    encoded = enforce_archive_size(content)
    recheck_chain_package(package)
    recheck_captured_ingest_packages(package)
    recheck_basis_documents(documents)
    try:
        final_journal = journal_engine._stable_journal_read(run_dir / "journal.jsonl")
    except (OSError, RuntimeError, ValueError, journal_engine.CoordinationRefusal):
        authoritative_discrepancy("snapshot_changed")
    if final_journal != journal_raw:
        authoritative_discrepancy("snapshot_changed")
    return encoded


def render_archive_candidate(
    *,
    repo: Path,
    run_dir: Path,
    closing_head: str | None,
    legacy_recovered_head: str | None,
    legacy_approval: str | None,
    post_close_validation: Path,
    dispense_targets: Sequence[str] = (),
    dispense_reason: str | None = None,
) -> bytes:
    """Return deterministic archive bytes after every normal/legacy proof.

    This is the read-only integration seam used by archive-only commit and
    report rerenders.  It never creates, stages, authorizes, or commits a path.
    """

    return _render_archive_candidate(
        repo=repo,
        run_dir=run_dir,
        closing_head=closing_head,
        legacy_recovered_head=legacy_recovered_head,
        legacy_approval=legacy_approval,
        post_close_validation=post_close_validation,
        dispense_targets=dispense_targets,
        dispense_reason=dispense_reason,
        prove_legacy_approval=True,
    )


def preview_legacy_archive_candidate(
    *,
    repo: Path,
    run_dir: Path,
    legacy_recovered_head: str,
    proposed_legacy_approval: str,
    post_close_validation: Path,
    dispense_targets: Sequence[str] = (),
    dispense_reason: str | None = None,
) -> bytes:
    """Render non-authorizing preview bytes before the approval decision exists.

    The returned bytes may be hashed for an operator prompt.  No mutation or
    commit path calls this function; the authoritative rerender must use
    :func:`render_archive_candidate`, which resolves the exact FR-172 decision.
    """

    return _render_archive_candidate(
        repo=repo,
        run_dir=run_dir,
        closing_head=None,
        legacy_recovered_head=legacy_recovered_head,
        legacy_approval=proposed_legacy_approval,
        post_close_validation=post_close_validation,
        dispense_targets=dispense_targets,
        dispense_reason=dispense_reason,
        prove_legacy_approval=False,
    )


def unlink_archive_candidate(
    repo: Path, relative: str, expected: ExactFile
) -> None:
    """Quarantine then remove only the inode created by this transaction.

    Renaming the live leaf into a private sibling directory is the atomic
    ownership boundary.  The original archive pathname is never unlinked, so a
    replacement appearing before or after the rename is preserved.  A moved
    mismatching inode is restored without overwrite when possible and otherwise
    left quarantined for operator recovery.
    """

    parent = -1
    quarantine = -1
    quarantine_name: str | None = None
    moved = False
    empty = False
    try:
        parent = open_archive_parent(repo, create=False)
        leaf = archive_leaf(relative)
        for _ in range(32):
            candidate = (
                f".{leaf}.rollback-{os.getpid()}-{os.urandom(16).hex()}"
            )
            try:
                os.mkdir(candidate, mode=0o700, dir_fd=parent)
            except FileExistsError:
                continue
            quarantine_name = candidate
            break
        if quarantine_name is None:
            raise ArchiveRefusal("forge: archive refused — transaction rollback failed")
        empty = True
        before = os.stat(
            quarantine_name, dir_fd=parent, follow_symlinks=False
        )
        if not owner_directory(before):
            raise ArchiveRefusal("forge: archive refused — transaction rollback failed")
        quarantine = os.open(
            quarantine_name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        if file_identity(os.fstat(quarantine)) != file_identity(before):
            raise ArchiveRefusal("forge: archive refused — transaction rollback failed")
        os.rename(
            leaf,
            "candidate",
            src_dir_fd=parent,
            dst_dir_fd=quarantine,
        )
        moved = True
        empty = False
        os.fsync(parent)
        os.fsync(quarantine)
        moved_stat = os.stat(
            "candidate", dir_fd=quarantine, follow_symlinks=False
        )
        matches = bool(
            moved_stat.st_dev == expected.identity.device
            and moved_stat.st_ino == expected.identity.inode
        )
        if not matches:
            try:
                os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                leaf_absent = False
            except FileNotFoundError:
                leaf_absent = True
            if leaf_absent:
                try:
                    os.link(
                        "candidate",
                        leaf,
                        src_dir_fd=quarantine,
                        dst_dir_fd=parent,
                        follow_symlinks=False,
                    )
                    restored = os.stat(
                        leaf, dir_fd=parent, follow_symlinks=False
                    )
                    quarantined = os.stat(
                        "candidate", dir_fd=quarantine, follow_symlinks=False
                    )
                    if (
                        restored.st_dev != quarantined.st_dev
                        or restored.st_ino != quarantined.st_ino
                    ):
                        raise OSError("restored archive identity differs")
                    os.unlink("candidate", dir_fd=quarantine)
                    moved = False
                    empty = True
                    os.fsync(parent)
                    os.fsync(quarantine)
                except OSError:
                    # Preserve the mismatching object in quarantine.  Never
                    # overwrite or delete a leaf that appeared concurrently.
                    pass
            raise ArchiveRefusal("forge: archive refused — transaction rollback failed")

        os.unlink("candidate", dir_fd=quarantine)
        moved = False
        empty = True
        os.fsync(quarantine)
        try:
            os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            replacement_present = False
        else:
            replacement_present = True
        os.rmdir(quarantine_name, dir_fd=parent)
        quarantine_name = None
        empty = False
        os.fsync(parent)
        if replacement_present:
            raise ArchiveRefusal("forge: archive refused — transaction rollback failed")
    except BaseException as exc:
        if (
            parent >= 0
            and quarantine_name is not None
            and empty
            and not moved
        ):
            try:
                os.rmdir(quarantine_name, dir_fd=parent)
                os.fsync(parent)
            except OSError:
                pass
        if isinstance(exc, ArchiveRefusal):
            raise
        raise ArchiveRefusal("forge: archive refused — transaction rollback failed") from exc
    finally:
        if quarantine >= 0:
            os.close(quarantine)
        if parent >= 0:
            os.close(parent)


def cleanup_archive(
    repo: Path,
    archive_path: Path,
    relative: str,
    *,
    preserve_worktree: ExactFile | None = None,
    created_worktree: ExactFile | None = None,
) -> None:
    if (preserve_worktree is None) == (created_worktree is None):
        raise ArchiveRefusal("forge: archive refused — transaction rollback failed")
    expected_worktree = preserve_worktree or created_worktree
    assert expected_worktree is not None
    failed = False
    try:
        removed = run_git(
            repo, "rm", "--cached", "--force", "--ignore-unmatch", "--", relative
        )
        failed = removed.returncode != 0
    except BaseException:
        # Unlinking must still be attempted if Git cannot be launched.
        failed = True
    if preserve_worktree is None:
        try:
            unlink_archive_candidate(repo, relative, expected_worktree)
        except BaseException:
            failed = True
    try:
        staged = nul_paths(git_stdout(repo, "diff", "--cached", "--name-only", "-z"))
        failed = failed or os.fsencode(relative) in staged
    except BaseException:
        failed = True
    try:
        failed = failed or (
            preserve_worktree is None
            and not archive_candidate_absent(repo, relative)
        )
        if preserve_worktree is not None:
            current = snapshot_existing_archive(repo, relative)
            failed = failed or (
                current.identity != preserve_worktree.identity
                or current.raw != preserve_worktree.raw
            )
    except BaseException:
        failed = True
    if failed:
        raise ArchiveRefusal("forge: archive refused — transaction rollback failed")


def create_archive_file(
    repo: Path, archive_path: Path, relative: str, content: str
) -> ExactFile:
    """Create one new archive while retaining rollback on every exception."""

    parent = -1
    descriptor = -1
    exact: ExactFile | None = None
    raw = content.encode("utf-8")
    try:
        parent = open_archive_parent(repo, create=True)
        leaf = archive_leaf(relative)
        try:
            descriptor = os.open(
                leaf,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o644,
                dir_fd=parent,
            )
        except FileExistsError as exc:
            raise ArchiveRefusal(
                f"forge: archive refused — archive already exists: {relative}"
            ) from exc
        opened = os.fstat(descriptor)
        if not owner_regular(opened):
            raise ArchiveRefusal("forge: archive refused — unsafe archive candidate path")
        exact = ExactFile(relative, b"", file_identity(opened))
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise OSError("short archive write")
            offset += written
        os.fsync(descriptor)
        exact = ExactFile(relative, raw, file_identity(os.fstat(descriptor)))
        os.close(descriptor)
        descriptor = -1
        rebound = snapshot_archive_at(parent, leaf, relative)
        if rebound.identity != exact.identity or rebound.raw != raw:
            raise ArchiveRefusal("forge: archive refused — archive changed during creation")
        if not archive_candidate_matches_surface(
            repo, relative, require_file=True
        ):
            raise ArchiveRefusal(
                "forge: archive refused — unsafe archive candidate path"
            )
        os.fsync(parent)
        return exact
    except BaseException as original:
        if descriptor >= 0:
            os.close(descriptor)
            descriptor = -1
        if exact is not None:
            try:
                unlink_archive_candidate(repo, relative, exact)
            except ArchiveRefusal as rollback:
                raise rollback from original
        if isinstance(original, OSError):
            raise ArchiveRefusal(
                f"forge: archive refused — could not write archive: {original}"
            ) from original
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent >= 0:
            os.close(parent)


def write_and_stage(
    repo: Path,
    relative: str,
    content: str,
    *,
    preexisting: ExactFile | None = None,
) -> None:
    archive_path = repo / relative
    created: ExactFile | None = None
    if preexisting is None:
        created = create_archive_file(repo, archive_path, relative, content)
    else:
        if not archive_candidate_matches_surface(
            repo, relative, require_file=True
        ):
            raise ArchiveRefusal(
                "forge: archive refused — unsafe archive candidate path"
            )
        current = snapshot_existing_archive(repo, relative)
        if (
            "candidate-rerender" not in RENDERER_CONTROLS
            or current.identity != preexisting.identity
            or current.raw != preexisting.raw
            or current.raw != content.encode("utf-8")
        ):
            raise ArchiveRefusal(
                "forge: archive refused — pre-existing archive differs from "
                f"deterministic rerender: {relative}"
            )

    add_attempted = False
    try:
        if nul_paths(git_stdout(repo, "diff", "--name-only", "-z")):
            raise ArchiveRefusal(CONTAMINATION, contamination=True)
        if nul_paths(git_stdout(repo, "diff", "--cached", "--name-only", "-z")):
            raise ArchiveRefusal(CONTAMINATION, contamination=True)
        if nul_paths(git_stdout(repo, "ls-files", "--others", "--exclude-standard", "-z")) != [
            os.fsencode(relative)
        ]:
            raise ArchiveRefusal(CONTAMINATION, contamination=True)

        add_attempted = True
        add = run_git(repo, "add", "--", relative)
        if add.returncode != 0:
            raise ArchiveRefusal("forge: archive refused — could not stage archive")

        staged_blob = git_stdout(repo, "show", f":{relative}")
        rendered_bytes = content.encode("utf-8")
        if staged_blob != rendered_bytes:
            raise ArchiveRefusal(
                "forge: archive refused — staged archive bytes differ from rendered archive"
            )
        expected_worktree = preexisting or created
        assert expected_worktree is not None
        if expected_worktree is not None:
            rebound = snapshot_existing_archive(repo, relative)
            if (
                rebound.identity != expected_worktree.identity
                or rebound.raw != expected_worktree.raw
            ):
                raise ArchiveRefusal(
                    "forge: archive refused — archive candidate is unsafe or "
                    f"changed: {relative}"
                )

        staged = nul_paths(git_stdout(repo, "diff", "--cached", "--name-only", "-z"))
        unstaged = nul_paths(git_stdout(repo, "diff", "--name-only", "-z"))
        untracked = nul_paths(git_stdout(repo, "ls-files", "--others", "--exclude-standard", "-z"))
        if staged != [os.fsencode(relative)] or unstaged or untracked:
            raise ArchiveRefusal(CONTAMINATION, contamination=True)
        if expected_worktree is not None:
            rebound = snapshot_existing_archive(repo, relative)
            if (
                rebound.identity != expected_worktree.identity
                or rebound.raw != expected_worktree.raw
            ):
                raise ArchiveRefusal(
                    "forge: archive refused — archive candidate is unsafe or "
                    f"changed: {relative}"
                )
    except BaseException as original:
        try:
            if add_attempted:
                cleanup_archive(
                    repo,
                    archive_path,
                    relative,
                    preserve_worktree=preexisting,
                    created_worktree=created,
                )
            elif preexisting is None:
                assert created is not None
                unlink_archive_candidate(repo, relative, created)
        except ArchiveRefusal as rollback:
            raise rollback from original
        raise


def parser() -> argparse.ArgumentParser:
    result = ContractArgumentParser(description=__doc__)
    result.add_argument("--run-dir", required=True)
    closing = result.add_mutually_exclusive_group(required=True)
    closing.add_argument("--closing-head")
    closing.add_argument("--legacy-recovered-head")
    result.add_argument("--legacy-approval")
    result.add_argument("--post-close-validation", required=True)
    # FR-018(b): operator-directed dispensation, forwarded verbatim to the audit.
    result.add_argument("--dispense-citation", action="append", default=[])
    result.add_argument("--dispense-reason", default=None)
    return result


def archive(arguments: argparse.Namespace) -> str:
    repo = repository_root()
    run_dir = resolve_run_dir(arguments.run_dir)
    run_id = run_dir.name
    relative = f".forge/history/runs/{run_id}.md"
    archive_path = repo / relative

    preexisting = untracked_archive_snapshot(repo, archive_path, relative)
    if preexisting is None:
        prove_clean(repo)
    else:
        prove_clean_with_untracked_archive(repo, relative)

    closing_head = arguments.closing_head
    if closing_head is not None:
        if not isinstance(closing_head, str) or not HEX_HEAD.fullmatch(closing_head):
            raise ArchiveRefusal("forge: archive refused — invalid closing HEAD")
        recorded_head = git_stdout(repo, "rev-parse", "HEAD").decode("ascii").strip()
        if closing_head != recorded_head:
            raise ArchiveRefusal("forge: archive refused — closing HEAD does not match repository HEAD")

    ignored = run_git(repo, "check-ignore", "-q", "--", relative)
    if ignored.returncode == 0:
        raise ArchiveRefusal(f"forge: archive refused — archive path is ignored: {relative}")
    if ignored.returncode != 1:
        raise ArchiveRefusal("forge: archive refused — could not verify archive ignore state")

    dispense_targets = tuple(arguments.dispense_citation)
    dispense_reason = arguments.dispense_reason
    content = render_archive_candidate(
        repo=repo,
        run_dir=run_dir,
        closing_head=closing_head,
        legacy_recovered_head=arguments.legacy_recovered_head,
        legacy_approval=arguments.legacy_approval,
        post_close_validation=Path(arguments.post_close_validation),
        dispense_targets=dispense_targets,
        dispense_reason=dispense_reason,
    )
    rendered = content.decode("utf-8")
    if preexisting is not None and (
        "candidate-rerender" not in RENDERER_CONTROLS
        or preexisting.raw != content
    ):
        raise ArchiveRefusal(
            "forge: archive refused — pre-existing archive differs from "
            f"deterministic rerender: {relative}"
        )
    write_and_stage(
        repo, relative, rendered, preexisting=preexisting
    )
    return relative


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
        relative = archive(arguments)
    except ArchiveRefusal as exc:
        print(exc.message, file=sys.stderr)
        return 1
    print(relative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
