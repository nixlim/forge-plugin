#!/usr/bin/env python3
# Serialization is provided by learn-proposals-locked.py; proposals remain advisory-only.
"""Materialize advisory learning proposals without control-write authority."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


ROOT_KEYS = {"schema_version", "input_head", "candidates", "gotchas"}
CANDIDATE_KEYS = {
    "id",
    "category",
    "agent",
    "expected_verdict",
    "run_id",
    "execution",
    "scenario",
    "expected",
}
GOTCHA_KEYS = {"run_id", "agent", "execution", "entries", "line"}
ENTRY_KEYS = {"type", "id"}
ENTRY_TYPES = {"decision", "verification"}
FAILURE_RESULTS = {"failed", "inconclusive"}
VERDICTS = {"PASS", "BLOCK", "FLAG"}
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
FULL_GIT_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
ARCHIVE_KEYS = {"decisions", "executions", "failed_or_inconclusive_verifications"}
ARCHIVE_DECISION_KEYS = {"id", "task"}
ARCHIVE_EXECUTION_KEYS = {
    "agent",
    "execution",
    "role",
    "task",
    "prompt",
    "prompt_sha256",
}
ARCHIVE_VERIFICATION_KEYS = {"id", "task", "result", "criterion", "observation"}
ARCHIVE_BEGIN = b"<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->\n"
ARCHIVE_END = b"<!-- END FORGE LEARNING PROVENANCE v1 -->"


class ProposalRefusal(Exception):
    """A fail-closed proposal validation or write refusal."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DuplicateObjectKey(ValueError):
    """Raised when JSON object text repeats a member name."""


class ContractArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ProposalRefusal("invalid-invocation")


@dataclass(frozen=True)
class CandidateWrite:
    candidate_id: str
    content: bytes


@dataclass(frozen=True)
class PreparedProposal:
    input_head: str
    candidates: tuple[CandidateWrite, ...]
    gotcha_lines: tuple[bytes, ...]
    committed_gotchas: bytes | None


@dataclass(frozen=True)
class ArchiveAuthority:
    path: str
    decisions: tuple[tuple[str, str], ...]
    executions: tuple[tuple[str, str, str, str, str, str], ...]
    verifications: tuple[tuple[str, str, str, object, object], ...]


def refuse(code: str) -> None:
    raise ProposalRefusal(code)


def exact_object(value: object, keys: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        refuse(code)
    return value


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateObjectKey(key)
        result[key] = value
    return result


def nonempty_text(value: object, code: str, *, one_line: bool = False) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        refuse(code)
    if one_line and value.splitlines() != [value]:
        refuse(code)
    return value


def safe_segment(value: object, code: str) -> str:
    text = nonempty_text(value, code, one_line=True)
    if text in {".", ".."} or SAFE_SEGMENT.fullmatch(text) is None:
        refuse(code)
    return text


def execution_id(value: object) -> str:
    return safe_segment(value, "invalid-execution")


def repository(value: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProposalRefusal("invalid-repository") from exc
    if not path.is_dir():
        refuse("invalid-repository")
    return path


def fixed_git(repo: Path, arguments: list[str], code: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(repo), *arguments],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise ProposalRefusal(code) from exc
    if result.returncode != 0:
        refuse(code)
    return result.stdout


def committed_input_head(repo: Path, value: object) -> str:
    head = nonempty_text(value, "invalid-input-head", one_line=True)
    if FULL_GIT_OID.fullmatch(head) is None:
        refuse("invalid-input-head")
    resolved = fixed_git(repo, ["rev-parse", "--verify", f"{head}^{{commit}}"], "invalid-input-head")
    if resolved != head.encode("ascii") + b"\n":
        refuse("invalid-input-head")
    require_current_head(repo, head)
    return head


def require_current_head(repo: Path, input_head: str) -> None:
    current = fixed_git(repo, ["rev-parse", "--verify", "HEAD"], "input-head-stale")
    if current != input_head.encode("ascii") + b"\n":
        refuse("input-head-stale")


def committed_entry(
    repo: Path, input_head: str, path: str
) -> tuple[bytes, bytes, bytes] | None:
    listing = fixed_git(
        repo,
        ["ls-tree", "-z", "--full-tree", input_head, "--", path],
        "committed-state-unavailable",
    )
    if not listing:
        return None
    entries = [entry for entry in listing.split(b"\0") if entry]
    if len(entries) != 1 or b"\t" not in entries[0]:
        refuse("committed-state-invalid")
    header, recorded_path = entries[0].split(b"\t", 1)
    fields = header.split()
    if len(fields) != 3 or recorded_path != path.encode("utf-8"):
        refuse("committed-state-invalid")
    return fields[0], fields[1], fields[2]


def committed_blob(repo: Path, input_head: str, path: str) -> bytes | None:
    entry = committed_entry(repo, input_head, path)
    if entry is None:
        return None
    mode, kind, object_id = entry
    if mode not in {b"100644", b"100755"} or kind != b"blob":
        refuse("committed-state-invalid")
    return fixed_git(
        repo,
        ["cat-file", "blob", object_id.decode("ascii")],
        "committed-state-unavailable",
    )


def committed_archive(repo: Path, input_head: str, run_id: str) -> ArchiveAuthority:
    path = f".forge/history/runs/{run_id}.md"
    raw = fixed_git(repo, ["cat-file", "blob", f"{input_head}:{path}"], "archive-unavailable")
    if raw.count(ARCHIVE_BEGIN) != 1 or raw.count(ARCHIVE_END) != 1:
        refuse("invalid-archive-provenance")
    encoded = raw.split(ARCHIVE_BEGIN, 1)[1].split(ARCHIVE_END, 1)[0]
    if not encoded.startswith(b"```json\n") or not encoded.endswith(b"\n```\n"):
        refuse("invalid-archive-provenance")
    encoded_json = encoded[len(b"```json\n") : -len(b"\n```\n")]
    try:
        parsed = json.loads(
            encoded_json.decode("utf-8"),
            object_pairs_hook=unique_object,
        )
    except (UnicodeError, json.JSONDecodeError, DuplicateObjectKey) as exc:
        raise ProposalRefusal("invalid-archive-provenance") from exc
    canonical = json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    if encoded_json != canonical:
        refuse("invalid-archive-provenance")
    authority = exact_object(parsed, ARCHIVE_KEYS, "invalid-archive-provenance")
    raw_decisions = authority["decisions"]
    raw_executions = authority["executions"]
    raw_verifications = authority["failed_or_inconclusive_verifications"]
    if not all(isinstance(value, list) for value in (raw_decisions, raw_executions, raw_verifications)):
        refuse("invalid-archive-provenance")

    decisions: list[tuple[str, str]] = []
    for raw_decision in raw_decisions:
        decision = exact_object(raw_decision, ARCHIVE_DECISION_KEYS, "invalid-archive-provenance")
        decisions.append(
            (
                safe_segment(decision["id"], "invalid-archive-provenance"),
                nonempty_text(decision["task"], "invalid-archive-provenance", one_line=True),
            )
        )
    executions: list[tuple[str, str, str, str, str, str]] = []
    for raw_execution in raw_executions:
        execution = exact_object(raw_execution, ARCHIVE_EXECUTION_KEYS, "invalid-archive-provenance")
        executions.append(
            (
                safe_segment(execution["agent"], "invalid-archive-provenance"),
                execution_id(execution["execution"]),
                nonempty_text(
                    execution["role"], "invalid-archive-provenance", one_line=True
                ),
                nonempty_text(execution["task"], "invalid-archive-provenance", one_line=True),
                nonempty_text(execution["prompt"], "invalid-archive-provenance", one_line=True),
                nonempty_text(
                    execution["prompt_sha256"],
                    "invalid-archive-provenance",
                    one_line=True,
                ),
            )
        )
        if FULL_GIT_OID.fullmatch(executions[-1][5]) is None or len(executions[-1][5]) != 64:
            refuse("invalid-archive-provenance")
    verifications: list[tuple[str, str, str, object, object]] = []
    for raw_verification in raw_verifications:
        verification = exact_object(
            raw_verification, ARCHIVE_VERIFICATION_KEYS, "invalid-archive-provenance"
        )
        result = nonempty_text(
            verification["result"], "invalid-archive-provenance", one_line=True
        )
        if result not in FAILURE_RESULTS:
            refuse("invalid-archive-provenance")
        for field in ("criterion", "observation"):
            if verification[field] is not None and not isinstance(verification[field], str):
                refuse("invalid-archive-provenance")
        verifications.append(
            (
                safe_segment(verification["id"], "invalid-archive-provenance"),
                nonempty_text(verification["task"], "invalid-archive-provenance", one_line=True),
                result,
                verification["criterion"],
                verification["observation"],
            )
        )
    if (
        len({identity for identity, _task in decisions}) != len(decisions)
        or len(
            {
                (agent, execution)
                for agent, execution, _role, _task, _prompt, _digest in executions
            }
        )
        != len(executions)
        or len({identity for identity, _task, _result, _criterion, _observation in verifications})
        != len(verifications)
    ):
        refuse("invalid-archive-provenance")
    return ArchiveAuthority(path, tuple(decisions), tuple(executions), tuple(verifications))


def proposal_json(value: str) -> dict[str, Any]:
    try:
        raw = Path(value).read_bytes()
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateObjectKey) as exc:
        raise ProposalRefusal("invalid-proposal") from exc
    return exact_object(parsed, ROOT_KEYS, "invalid-proposal")


def contained_existing_directory(parent: Path, child: Path, code: str) -> Path:
    try:
        resolved_parent = parent.resolve(strict=True)
        resolved_child = child.resolve(strict=True)
        resolved_child.relative_to(resolved_parent)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProposalRefusal(code) from exc
    if not resolved_child.is_dir():
        refuse(code)
    return resolved_child


def journal_records(repo: Path, run_id: str) -> tuple[Path, list[dict[str, Any]]]:
    runs_root = repo / ".codex-orchestrator" / "runs"
    run_dir = runs_root / run_id
    for source in (repo / ".codex-orchestrator", runs_root, run_dir):
        if source.is_symlink():
            refuse("invalid-run")
    resolved_runs = contained_existing_directory(repo, runs_root, "invalid-run")
    resolved_run = contained_existing_directory(resolved_runs, run_dir, "invalid-run")
    journal = resolved_run / "journal.jsonl"
    try:
        if journal.is_symlink() or not journal.is_file():
            refuse("invalid-journal")
        lines = journal.read_bytes().splitlines()
    except OSError as exc:
        raise ProposalRefusal("invalid-journal") from exc

    records: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line.decode("utf-8"), object_pairs_hook=unique_object)
        except (UnicodeError, json.JSONDecodeError, DuplicateObjectKey) as exc:
            raise ProposalRefusal("invalid-journal") from exc
        if not isinstance(record, dict):
            refuse("invalid-journal")
        records.append(record)

    starts = [item for item in records if item.get("type") == "run_started"]
    if len(starts) != 1:
        refuse("invalid-journal")
    recorded_run_id = starts[0].get("run_id", starts[0].get("id"))
    if recorded_run_id != run_id:
        refuse("invalid-journal")
    require_closed_run(records)
    return resolved_run, records


def require_closed_run(records: list[dict[str, Any]]) -> None:
    closures = [record for record in records if record.get("type") == "run_closed"]
    if (
        len(closures) != 1
        or records[-1] is not closures[0]
        or closures[0].get("judgment") not in {"passed", "blocked"}
    ):
        refuse("run-not-closed")


def matching_execution(
    records: list[dict[str, Any]], agent: str, execution: str
) -> dict[str, Any]:
    matches = [
        item
        for item in records
        if item.get("type") == "execution"
        and item.get("agent") == agent
        and item.get("execution") == execution
    ]
    if len(matches) != 1:
        refuse("execution-unavailable")
    return matches[0]


def require_archive_execution(
    authority: ArchiveAuthority,
    run_dir: Path,
    records: list[dict[str, Any]],
    execution: dict[str, Any],
    agent: str,
    execution_id_value: str,
) -> tuple[str, bytes]:
    matches = [
        (role, task, prompt, digest)
        for recorded_agent, recorded_execution, role, task, prompt, digest in authority.executions
        if recorded_agent == agent and recorded_execution == execution_id_value
    ]
    if len(matches) != 1:
        refuse("archive-execution-unavailable")
    role, task, prompt, digest = matches[0]
    if execution.get("task") != task or execution.get("role") != role:
        refuse("archive-journal-mismatch")
    hydrated_prompt = prompt_bytes(run_dir, execution)
    if (
        execution.get("prompt") != prompt
        or hashlib.sha256(hydrated_prompt).hexdigest() != digest
    ):
        refuse("archive-prompt-mismatch")
    failures = [
        verification
        for verification in authority.verifications
        if verification[1] == task
    ]
    if not failures:
        refuse("archive-failure-unavailable")
    for identity, recorded_task, result, criterion, observation in failures:
        journal_matches = [
            record
            for record in records
            if record.get("type") == "verification"
            and record.get("id") == identity
            and record.get("task") == recorded_task
            and record.get("result") == result
            and record.get("criterion") == criterion
            and record.get("observation") == observation
        ]
        if len(journal_matches) != 1:
            refuse("archive-journal-mismatch")
    return task, hydrated_prompt


def require_archive_entries(
    authority: ArchiveAuthority,
    task: str,
    entries: tuple[tuple[str, str], ...],
) -> None:
    for entry_type, identity in entries:
        if entry_type == "decision":
            matches = [
                recorded_task
                for recorded_id, recorded_task in authority.decisions
                if recorded_id == identity
            ]
        else:
            matches = [
                recorded_task
                for recorded_id, recorded_task, _result, _criterion, _observation
                in authority.verifications
                if recorded_id == identity
            ]
        if matches != [task]:
            refuse("archive-entry-unavailable")


def prompt_bytes(run_dir: Path, execution: dict[str, Any]) -> bytes:
    prompt = nonempty_text(execution.get("prompt"), "invalid-prompt-path", one_line=True)
    if "\\" in prompt:
        refuse("invalid-prompt-path")
    relative = Path(prompt)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        refuse("invalid-prompt-path")
    source = run_dir
    for part in relative.parts:
        source = source / part
        if source.is_symlink():
            refuse("invalid-prompt-path")
    try:
        resolved_run_dir = run_dir.resolve(strict=True)
        resolved = source.resolve(strict=True)
        resolved.relative_to(resolved_run_dir)
        metadata = resolved.lstat()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProposalRefusal("invalid-prompt-path") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        refuse("invalid-prompt-path")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                refuse("invalid-prompt-path")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                return handle.read()
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise ProposalRefusal("prompt-unavailable") from exc


def frontmatter_value(value: object, code: str) -> str:
    return safe_segment(value, code)


def markdown_fence(prompt: bytes) -> bytes:
    longest = 0
    current = 0
    for byte in prompt:
        if byte == ord("`"):
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return b"`" * max(3, longest + 1)


def render_candidate(
    candidate: dict[str, Any], prompt: bytes, input_head: str, archive_path: str
) -> bytes:
    candidate_id = frontmatter_value(candidate["id"], "invalid-candidate-id")
    category = frontmatter_value(candidate["category"], "invalid-category")
    agent = frontmatter_value(candidate["agent"], "invalid-agent")
    verdict = nonempty_text(candidate["expected_verdict"], "invalid-verdict", one_line=True)
    if verdict not in VERDICTS:
        refuse("invalid-verdict")
    run_id = safe_segment(candidate["run_id"], "invalid-run-id")
    execution = execution_id(candidate["execution"])
    scenario = nonempty_text(candidate["scenario"], "invalid-scenario")
    expected = nonempty_text(candidate["expected"], "invalid-expected")
    fence = markdown_fence(prompt)

    prefix = (
        "---\n"
        f"id: {candidate_id}\n"
        f"category: {category}\n"
        f"agent: {agent}\n"
        f"expected_verdict: {verdict}\n"
        "---\n\n"
        "## Scenario\n\n"
        f"{scenario}\n\n"
        "## Input\n\n"
    ).encode("utf-8") + fence + b"\n"
    suffix = (
        "\n"
    ).encode("utf-8") + fence + (
        "\n\n## Expected\n\n"
        f"{expected}\n\n"
        "## Provenance\n\n"
        f"- run-id: `{run_id}`\n"
        f"- agent: `{agent}`\n"
        f"- execution-id: `{execution}`\n"
        f"- archive: `{input_head}:{archive_path}`\n"
    ).encode("utf-8")
    return prefix + prompt + suffix


def render_gotcha(
    gotcha: dict[str, Any],
    entries: tuple[tuple[str, str], ...],
    input_head: str,
    archive_path: str,
) -> bytes:
    run_id = safe_segment(gotcha["run_id"], "invalid-run-id")
    agent = safe_segment(gotcha["agent"], "invalid-agent")
    execution = execution_id(gotcha["execution"])
    line = nonempty_text(gotcha["line"], "invalid-gotcha", one_line=True)
    citations = ",".join(f"{entry_type}:{entry_id}" for entry_type, entry_id in entries)
    return (
        f"- {line} [journal: run-id={run_id}; agent={agent}; "
        f"execution-id={execution}; entries={citations}] "
        f"[archive: {input_head}:{archive_path}]"
    ).encode("utf-8")


def validate_gotcha_entries(
    records: list[dict[str, Any]],
    execution: dict[str, Any],
    value: object,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list) or not value:
        refuse("invalid-gotcha-entry")
    task = nonempty_text(
        execution.get("task"), "invalid-gotcha-entry", one_line=True
    )
    seen: set[tuple[str, str]] = set()
    citations: list[tuple[str, str]] = []
    for raw in value:
        entry = exact_object(raw, ENTRY_KEYS, "invalid-gotcha-entry")
        entry_type = nonempty_text(
            entry["type"], "invalid-gotcha-entry", one_line=True
        )
        if entry_type not in ENTRY_TYPES:
            refuse("invalid-gotcha-entry")
        entry_id = safe_segment(entry["id"], "invalid-gotcha-entry")
        identity = (entry_type, entry_id)
        if identity in seen:
            refuse("duplicate-gotcha-entry")
        seen.add(identity)
        matches = [
            record
            for record in records
            if record.get("type") == entry_type and record.get("id") == entry_id
        ]
        if len(matches) != 1 or matches[0].get("task") != task:
            refuse("gotcha-entry-unavailable")
        citations.append(identity)
    return tuple(citations)


def prepare(repo: Path, payload: dict[str, Any]) -> PreparedProposal:
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        refuse("invalid-schema-version")
    input_head = committed_input_head(repo, payload.get("input_head"))
    raw_candidates = payload.get("candidates")
    raw_gotchas = payload.get("gotchas")
    if not isinstance(raw_candidates, list) or not isinstance(raw_gotchas, list):
        refuse("invalid-proposal")
    if not raw_candidates and not raw_gotchas:
        refuse("empty-proposal")

    journals: dict[str, tuple[Path, list[dict[str, Any]]]] = {}
    archives: dict[str, ArchiveAuthority] = {}

    def execution_for(
        run_id: str, agent: str, execution: str
    ) -> tuple[
        Path, list[dict[str, Any]], dict[str, Any], ArchiveAuthority, str, bytes
    ]:
        if run_id not in archives:
            archives[run_id] = committed_archive(repo, input_head, run_id)
        if run_id not in journals:
            journals[run_id] = journal_records(repo, run_id)
        run_dir, records = journals[run_id]
        record = matching_execution(records, agent, execution)
        authority = archives[run_id]
        task, hydrated_prompt = require_archive_execution(
            authority, run_dir, records, record, agent, execution
        )
        return run_dir, records, record, authority, task, hydrated_prompt

    candidates: list[CandidateWrite] = []
    candidate_ids: set[str] = set()
    for raw in raw_candidates:
        candidate = exact_object(raw, CANDIDATE_KEYS, "invalid-candidate")
        candidate_id = safe_segment(candidate["id"], "invalid-candidate-id")
        if candidate_id.endswith(".result"):
            refuse("invalid-candidate-id")
        if candidate_id in candidate_ids:
            refuse("duplicate-candidate")
        candidate_ids.add(candidate_id)
        run_id = safe_segment(candidate["run_id"], "invalid-run-id")
        agent = safe_segment(candidate["agent"], "invalid-agent")
        execution = execution_id(candidate["execution"])
        _run_dir, _records, record, authority, _task, hydrated_prompt = execution_for(
            run_id, agent, execution
        )
        if candidate["expected_verdict"] == "FLAG" and record.get("role") != "monitoring":
            refuse("invalid-verdict")
        candidates.append(
            CandidateWrite(
                candidate_id,
                render_candidate(
                    candidate,
                    hydrated_prompt,
                    input_head,
                    authority.path,
                ),
            )
        )

    gotcha_lines: list[bytes] = []
    seen_gotchas: set[bytes] = set()
    for raw in raw_gotchas:
        gotcha = exact_object(raw, GOTCHA_KEYS, "invalid-gotcha")
        run_id = safe_segment(gotcha["run_id"], "invalid-run-id")
        agent = safe_segment(gotcha["agent"], "invalid-agent")
        execution = execution_id(gotcha["execution"])
        _run_dir, records, record, authority, task, _hydrated_prompt = execution_for(
            run_id, agent, execution
        )
        entries = validate_gotcha_entries(records, record, gotcha["entries"])
        require_archive_entries(authority, task, entries)
        if not any(entry_type == "verification" for entry_type, _identity in entries):
            refuse("unearned-gotcha")
        rendered = render_gotcha(gotcha, entries, input_head, authority.path)
        if rendered in seen_gotchas:
            refuse("duplicate-gotcha")
        seen_gotchas.add(rendered)
        gotcha_lines.append(rendered)
    for candidate in candidates:
        candidate_path = f".forge/evals/candidates/{candidate.candidate_id}.md"
        if committed_entry(repo, input_head, candidate_path) is not None:
            refuse("candidate-collision")
    committed_gotchas = (
        committed_blob(repo, input_head, ".forge/history/gotchas.md")
        if gotcha_lines
        else None
    )
    return PreparedProposal(
        input_head,
        tuple(candidates),
        tuple(gotcha_lines),
        committed_gotchas,
    )


def lexical_exists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def read_gotchas_file(path: Path) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ProposalRefusal("unsafe-output-path") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        refuse("unsafe-output-path")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                refuse("unsafe-output-path")
            with os.fdopen(descriptor, "rb", closefd=False) as source:
                return source.read()
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise ProposalRefusal("unsafe-output-path") from exc


def validate_gotcha_prefix(path: Path, committed: bytes | None) -> bytes:
    current = read_gotchas_file(path)
    if committed is not None and not current.startswith(committed):
        refuse("gotcha-prefix-mismatch")
    return current


def create_output_directory(
    repo: Path,
    relative: Path,
    created_directories: list[tuple[Path, int, str]],
) -> tuple[Path, int]:
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    current = repo
    try:
        current_descriptor = os.open(repo, directory_flags)
    except OSError as exc:
        raise ProposalRefusal("unsafe-output-path") from exc
    try:
        validate_opened_directory(repo, current, current_descriptor)
        for part in relative.parts:
            current = current / part
            try:
                os.mkdir(part, dir_fd=current_descriptor)
            except FileExistsError:
                pass
            except OSError as exc:
                code = (
                    "unsafe-output-path"
                    if exc.errno in {errno.ELOOP, errno.ENOTDIR}
                    else "write-failed"
                )
                raise ProposalRefusal(code) from exc
            else:
                try:
                    cleanup_descriptor = os.dup(current_descriptor)
                except OSError as exc:
                    try:
                        os.rmdir(part, dir_fd=current_descriptor)
                    except OSError:
                        pass
                    raise ProposalRefusal("write-failed") from exc
                created_directories.append(
                    (current, cleanup_descriptor, part)
                )
            try:
                next_descriptor = os.open(
                    part, directory_flags, dir_fd=current_descriptor
                )
            except OSError as exc:
                code = (
                    "unsafe-output-path"
                    if exc.errno in {errno.ELOOP, errno.ENOTDIR}
                    else "write-failed"
                )
                raise ProposalRefusal(code) from exc
            os.close(current_descriptor)
            current_descriptor = next_descriptor
            validate_opened_directory(repo, current, current_descriptor)
        result_descriptor = current_descriptor
        current_descriptor = -1
        return current, result_descriptor
    finally:
        if current_descriptor >= 0:
            os.close(current_descriptor)


def validate_destinations(repo: Path, proposal: PreparedProposal) -> None:
    candidate_dir = repo / ".forge" / "evals" / "candidates"
    history_dir = repo / ".forge" / "history"
    if proposal.candidates:
        for candidate in proposal.candidates:
            target = candidate_dir / f"{candidate.candidate_id}.md"
            if lexical_exists(target):
                refuse("candidate-collision")
    if proposal.gotcha_lines:
        gotchas = history_dir / "gotchas.md"
        if lexical_exists(gotchas):
            validate_gotcha_prefix(gotchas, proposal.committed_gotchas)
        elif proposal.committed_gotchas is not None:
            refuse("gotcha-prefix-mismatch")


def validate_opened_output(repo: Path, path: Path, descriptor: int) -> os.stat_result:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(repo)
        intended = resolved.stat(follow_symlinks=False)
        opened = os.fstat(descriptor)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProposalRefusal("unsafe-output-path") from exc
    if (
        resolved != path
        or not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or (opened.st_dev, opened.st_ino) != (intended.st_dev, intended.st_ino)
    ):
        refuse("unsafe-output-path")
    return opened


def validate_opened_directory(
    repo: Path, path: Path, descriptor: int
) -> os.stat_result:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(repo)
        intended = resolved.stat(follow_symlinks=False)
        opened = os.fstat(descriptor)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProposalRefusal("unsafe-output-path") from exc
    if (
        resolved != path
        or not stat.S_ISDIR(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != (intended.st_dev, intended.st_ino)
    ):
        refuse("unsafe-output-path")
    return opened


def unlink_if_opened(
    parent_descriptor: int, name: str, identity: tuple[int, int]
) -> None:
    try:
        current = os.stat(
            name, dir_fd=parent_descriptor, follow_symlinks=False
        )
        if (current.st_dev, current.st_ino) == identity:
            os.unlink(name, dir_fd=parent_descriptor)
    except OSError:
        pass


def open_output_file(
    repo: Path,
    path: Path,
    flags: int,
    *,
    must_be_new: bool,
    parent_descriptor: int,
) -> int:
    open_flags = flags | getattr(os, "O_NOFOLLOW", 0)
    if must_be_new:
        open_flags |= os.O_CREAT | os.O_EXCL
    try:
        validate_opened_directory(repo, path.parent, parent_descriptor)
        if must_be_new:
            descriptor = os.open(
                path.name,
                open_flags,
                0o666,
                dir_fd=parent_descriptor,
            )
        else:
            descriptor = os.open(path, open_flags, 0o666)
    except FileExistsError:
        raise
    except OSError as exc:
        code = (
            "unsafe-output-path"
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}
            else "write-failed"
        )
        raise ProposalRefusal(code) from exc
    try:
        validate_opened_output(repo, path, descriptor)
    except BaseException:
        if must_be_new:
            opened = os.fstat(descriptor)
            unlink_if_opened(
                parent_descriptor,
                path.name,
                (opened.st_dev, opened.st_ino),
            )
        os.close(descriptor)
        raise
    return descriptor


def append_gotchas(
    repo: Path,
    path: Path,
    lines: tuple[bytes, ...],
    committed: bytes | None,
    parent_descriptor: int,
) -> None:
    if not lines:
        return
    existed = lexical_exists(path)
    descriptor = -1
    prior_size: int | None = None
    try:
        if not existed and committed is not None:
            refuse("gotcha-prefix-mismatch")
        descriptor = open_output_file(
            repo,
            path,
            os.O_RDWR | os.O_APPEND,
            must_be_new=not existed,
            parent_descriptor=parent_descriptor,
        )
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            source.seek(0)
            prior = source.read()
        if committed is not None and not prior.startswith(committed):
            refuse("gotcha-prefix-mismatch")
        prior_size = len(prior)
        needs_separator = bool(prior) and not prior.endswith(b"\n")
        payload = (
            (b"\n" if needs_separator else b"") + b"\n".join(lines) + b"\n"
        )
        with os.fdopen(descriptor, "ab", closefd=False) as output:
            output.seek(0, os.SEEK_END)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except BaseException as exc:
        try:
            if descriptor >= 0:
                if existed and prior_size is not None:
                    os.ftruncate(descriptor, prior_size)
                    os.fsync(descriptor)
                elif not existed:
                    opened = os.fstat(descriptor)
                    unlink_if_opened(
                        parent_descriptor,
                        path.name,
                        (opened.st_dev, opened.st_ino),
                    )
        except OSError:
            pass
        if isinstance(exc, OSError):
            raise ProposalRefusal("write-failed") from exc
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def write(repo: Path, proposal: PreparedProposal) -> list[str]:
    require_current_head(repo, proposal.input_head)
    validate_destinations(repo, proposal)
    written: list[str] = []
    created_candidates: list[Path] = []
    created_candidate_identities: dict[Path, tuple[int, int]] = {}
    created_directories: list[tuple[Path, int, str]] = []
    candidate_dir_descriptor = -1
    history_dir_descriptor = -1
    try:
        if proposal.candidates:
            candidate_dir, candidate_dir_descriptor = create_output_directory(
                repo, Path(".forge/evals/candidates"), created_directories
            )
            for candidate in proposal.candidates:
                target = candidate_dir / f"{candidate.candidate_id}.md"
                descriptor = -1
                try:
                    descriptor = open_output_file(
                        repo,
                        target,
                        os.O_WRONLY,
                        must_be_new=True,
                        parent_descriptor=candidate_dir_descriptor,
                    )
                    opened = os.fstat(descriptor)
                    created_candidates.append(target)
                    created_candidate_identities[target] = (
                        opened.st_dev,
                        opened.st_ino,
                    )
                    with os.fdopen(descriptor, "wb", closefd=False) as output:
                        output.write(candidate.content)
                        output.flush()
                        os.fsync(output.fileno())
                except FileExistsError as exc:
                    raise ProposalRefusal("candidate-collision") from exc
                except OSError as exc:
                    raise ProposalRefusal("write-failed") from exc
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)
                written.append(target.relative_to(repo).as_posix())

        if proposal.gotcha_lines:
            history_dir, history_dir_descriptor = create_output_directory(
                repo, Path(".forge/history"), created_directories
            )
            gotchas = history_dir / "gotchas.md"
            append_gotchas(
                repo,
                gotchas,
                proposal.gotcha_lines,
                proposal.committed_gotchas,
                history_dir_descriptor,
            )
            written.append(gotchas.relative_to(repo).as_posix())
    except BaseException:
        for target in reversed(created_candidates):
            unlink_if_opened(
                candidate_dir_descriptor,
                target.name,
                created_candidate_identities[target],
            )
        for directory in reversed(created_directories):
            _, parent_descriptor, name = directory
            try:
                os.rmdir(name, dir_fd=parent_descriptor)
            except OSError:
                pass
        raise
    finally:
        if candidate_dir_descriptor >= 0:
            os.close(candidate_dir_descriptor)
        if history_dir_descriptor >= 0:
            os.close(history_dir_descriptor)
        for _, parent_descriptor, _ in created_directories:
            os.close(parent_descriptor)
    return written


def parser() -> argparse.ArgumentParser:
    result = ContractArgumentParser(description=__doc__)
    result.add_argument("--repo", required=True)
    result.add_argument("--proposal", required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        repo = repository(args.repo)
        payload = proposal_json(args.proposal)
        prepared = prepare(repo, payload)
        written = write(repo, prepared)
    except ProposalRefusal as exc:
        print(f"forge: learning proposal refused — {exc.code}", file=sys.stderr)
        return 2
    except BaseException:
        print("forge: learning proposal refused — execution-failed", file=sys.stderr)
        return 2
    for relative in written:
        print(relative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
