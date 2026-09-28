"""Public request-free primitives shared by Forge review and typed launch lanes."""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from forge_cli import chain_core
from forge_cli.engine import _review_attempt
from forge_cli.engine._review_wrapper import reap_detached, wrapper_source
from forge_cli.engine._review_wrapper_io import COMPLETION_SCHEMA as COMPLETION_SCHEMA
from forge_cli.envelope import ReasonCode, Refusal, V2ReasonCode

COMPLETION_KEYS = _review_attempt.COMPLETION_KEYS
COMPLETION_ERRORS = _review_attempt.COMPLETION_ERRORS
NO_SIGNAL_OUTCOMES = frozenset({
    "identity-unproven",
    "wrapper-identity-unproven",
    "recorded-identity-unproven",
})
CANCEL_REQUIRED_OUTCOMES = frozenset({
    "wrapper-dead / child-alive",
    *NO_SIGNAL_OUTCOMES,
})
IMMUTABLE_IDENTITY_FIELDS = ("attempt", "wrapper_pid", "pgid", "wrapper_birth")
REFRESH_RECHECK_FIELDS = frozenset({"reviewer_pid", "reviewer_birth", "started_at"})
LOST_OUTCOMES = frozenset({
    "group-empty",
    "identity-mismatch",
    "boot-id-changed",
    "wrapper-lost",
})
_VERDICT_LINES = frozenset({"VERDICT: PASS", "VERDICT: BLOCK"})
_FINDING_LINE = re.compile(r"finding: (CRITICAL|MAJOR|MINOR) .+")


def _scope_refusal(state: Mapping[str, Any], observed: str) -> Refusal:
    message = (
        "forge: review request refused — no truthful current-candidate Gate 1 scope record"
    )
    expected = "a recorded operator/docs-class skip or a cited current Gate 1 PASS"
    if state.get("kind") == "merge":
        chain_id = str(state.get("chain_id") or "")
        remediation = "forge merge gate run gate-1"
        if chain_id:
            remediation += f" --chain-id {chain_id}"
        return chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            message,
            expected=expected,
            observed=observed,
            remediation=remediation,
            chain=state,
        )
    command_state = state if isinstance(state.get("chain_id"), str) else None
    return Refusal(
        ReasonCode.EVIDENCE_INCOMPLETE,
        message,
        expected=expected,
        observed=observed,
        remediation=chain_core._forge_command(command_state, "gate run gate-1"),
        chain=state,
    )


def _passed_scope(state: Mapping[str, Any], record: Mapping[str, Any]) -> bytes:
    digest = record.get("stdout_stderr_digest")
    if not isinstance(digest, str) or chain_core.SHA256_RE.fullmatch(digest) is None:
        raise _scope_refusal(state, "current Gate 1 PASS has no recorded evidence digest")
    return (
        "\nGate 1 full unittest discovery passed on this exact candidate. "
        f"The chain records that run with stdout/stderr SHA-256 {digest}. "
        "Do not run full unittest discovery or the Gate 1 cell. Run only focused "
        "test modules for the change, plus your own in-memory disable checks. "
        "Finish well within the review timeout.\n"
    ).encode()


def _operator_skip_scope(state: Mapping[str, Any], record: Mapping[str, Any]) -> bytes:
    reason = record.get("reason")
    if not isinstance(reason, str) or not reason:
        raise _scope_refusal(state, "operator Gate 1 skip has no recorded reason")
    return (
        "\nGate 1 full unittest discovery was operator-skipped on this exact candidate. "
        f"The chain's recorded skip reason is {json.dumps(reason)}. "
        "The review timeout is fixed; choose tests that fit within it.\n"
    ).encode()


def _docs_skip_scope(state: Mapping[str, Any]) -> bytes:
    reason = json.dumps(chain_core.DOCS_CLASS_SKIP_REASON)
    return (
        "\nGate 1 full unittest discovery was skipped on this exact docs-class candidate. "
        f"The chain's recorded skip reason is {reason}. "
        "The review timeout is fixed; choose tests that fit within it.\n"
    ).encode()


def _commit_review_scope(state: Mapping[str, Any]) -> bytes:
    steps = state.get("steps")
    candidate = state.get("candidate")
    if not isinstance(steps, Mapping) or not isinstance(candidate, Mapping):
        raise _scope_refusal(state, "commit Gate 1 state is malformed")
    runs = steps.get("gate-1")
    current = (
        [
            record
            for record in runs
            if isinstance(record, Mapping)
            and record.get("candidate") == candidate.get("sha256")
        ]
        if isinstance(runs, list)
        else []
    )
    newest = current[-1] if current else None
    if isinstance(newest, Mapping) and newest.get("result") == "passed":
        return _passed_scope(state, newest)
    skips = steps.get("user_skips")
    operator_skip = skips.get("gate-1") if isinstance(skips, Mapping) else None
    if isinstance(operator_skip, Mapping):
        return _operator_skip_scope(state, operator_skip)
    if newest is None:
        raise _scope_refusal(state, "no Gate 1 record matches the current candidate")
    if (
        newest.get("result") == "skipped"
        and newest.get("reason") == chain_core.DOCS_CLASS_SKIP_REASON
    ):
        return _docs_skip_scope(state)
    raise _scope_refusal(state, f"newest current Gate 1 result is {newest.get('result')!r}")


def _merge_review_scope(state: Mapping[str, Any]) -> bytes:
    candidate = state.get("candidate")
    steps = state.get("steps")
    if not isinstance(candidate, Mapping) or not isinstance(steps, Mapping):
        raise _scope_refusal(state, "merge Gate 1 state is malformed")
    facts = chain_core._merge_current_gate_facts(
        "gate-1", steps.get("gate-1"), str(candidate.get("generation_digest") or "")
    )
    if facts is None or len(facts) != 1:
        raise _scope_refusal(state, "no current-generation Gate 1 PASS is recorded")
    return _passed_scope(state, facts[0])


def review_scope_paragraph(state: Mapping[str, Any]) -> bytes:
    """Render the truthful Gate 1 scope instruction from persisted chain evidence."""

    if state.get("kind") == "commit":
        return _commit_review_scope(state)
    if state.get("kind") == "merge":
        return _merge_review_scope(state)
    raise _scope_refusal(state, f"unknown chain kind {state.get('kind')!r}")


def verdict_transport(data: bytes) -> bytes:
    """Extract one strict trailing transport from a reviewer's raw final message."""

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("verdict is not UTF-8") from exc
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    verdict_indexes = [index for index, line in enumerate(lines) if line in _VERDICT_LINES]
    if not verdict_indexes:
        raise ValueError("reviewer final message has no exact verdict line")
    if len(verdict_indexes) != 1:
        raise ValueError("reviewer final message has more than one exact verdict line")
    verdict_index = verdict_indexes[0]
    for line in lines:
        if line.startswith("VERDICT:") and line not in _VERDICT_LINES:
            raise ValueError(f"unexpected VERDICT-prefixed line: {line}")
    transport = lines[verdict_index:]
    for line in transport[1:]:
        if line.startswith(("candidate: ", "package: ")):
            continue
        if line.startswith("finding: "):
            if _FINDING_LINE.fullmatch(line):
                continue
            raise ValueError("finding line has invalid grammar")
        raise ValueError(f"unexpected verdict line: {line}")
    return "\n".join(transport).encode("utf-8")


def verdict_block_instruction(candidate: str, package_digest: str) -> bytes:
    """Render the invariant trailing final-message contract."""

    return (
        "\nThe reviewer's final message must END with exactly one verdict block. "
        "Nothing may follow that block, including an Iteration: line.\n"
        "The block must start with a first line that is exactly VERDICT: PASS or "
        "exactly VERDICT: BLOCK, followed by these exact lines:\n"
        f"candidate: {candidate}\n"
        f"package: {package_digest}\n"
        "Zero or more lines: finding: <CRITICAL|MAJOR|MINOR> <text>\n"
        "No other line of the final message may begin with VERDICT:.\n"
    ).encode()


def verdict_prompt_instruction(
    candidate: str, package_digest: str, state: Mapping[str, Any]
) -> bytes:
    """Render the evidence-derived scope followed by the trailing verdict contract."""

    return review_scope_paragraph(state) + verdict_block_instruction(
        candidate, package_digest
    )


def cancel_kill_unconfirmed_message(members: Sequence[int]) -> str:
    return f"forge: review cancel refused — kill-unconfirmed: {list(members)}"


def new_attempt_id() -> str:
    """Mint one attempt identifier accepted by the review-record validators."""

    return f"attempt-{secrets.token_hex(8)}"


def open_attempt_directory(path: Path) -> int:
    """Open and prove an owner-controlled attempt directory."""

    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(path, flags)
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
        os.close(descriptor)
        raise OSError("review attempt directory is not owner-controlled")
    return descriptor


def wrapper_launcher(
    ctx: chain_core.CommandContext,
    attempt_fd: int,
    config: Mapping[str, object],
) -> tuple[str, tuple[str, ...], str]:
    """Bind canonical config and exact standalone wrapper source into one launcher."""

    config_json = chain_core.canonical_bytes(dict(config)).decode("utf-8")
    launcher_argv = (
        sys.executable,
        "-I",
        "-c",
        wrapper_source(),
        str(attempt_fd),
        config_json,
    )
    return config_json, launcher_argv, ctx.command_digest(launcher_argv)


def spawn_wrapper(
    launcher_argv: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    attempt_fd: int,
) -> subprocess.Popen[bytes]:
    """Spawn one isolated detached wrapper while inheriting only its attempt fd."""

    process = subprocess.Popen(
        list(launcher_argv),
        cwd=str(cwd),
        env=dict(environment),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        pass_fds=(attempt_fd,),
    )
    reap_detached(process)
    return process


def publish_or_read_terminal(
    directory_fd: int,
    binding: Mapping[str, Any],
    error: str,
    identity: Mapping[str, Any] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Exclusively publish a terminal completion or validate the race winner."""

    record = _review_attempt.make_terminal_completion(
        binding, error, identity=identity
    )
    published = _review_attempt.publish_terminal_completion(directory_fd, record)
    if published:
        return True, record
    existing = _review_attempt.read_completion(
        directory_fd, str(binding.get("attempt") or "")
    )
    if existing is None:
        raise _review_attempt.AttemptRecordError(
            "completion publication raced but is unreadable"
        )
    _review_attempt.validate_completion_binding(existing, binding, identity)
    return False, existing
