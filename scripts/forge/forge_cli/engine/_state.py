"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import threading
from typing import Any
import re


TERMINAL_STATES = {"closed", "aborted"}


TERMINAL_TOUCH_VERBS = frozenset({"status", "commit abort", "commit abort-disposition"})


STATE_TRANSITIONS: dict[str, frozenset[str]] = {
    "classifying": frozenset({"verifying", "aborted"}),
    "verifying": frozenset(
        {"classifying", "reviewing", "revising", "authorized", "aborted"}
    ),
    "reviewing": frozenset(
        {"classifying", "revising", "awaiting_approval", "authorized", "aborted"}
    ),
    "revising": frozenset({"classifying", "aborted"}),
    "awaiting_approval": frozenset({"classifying", "authorized", "aborted"}),
    "authorized": frozenset({"classifying", "committing", "aborted"}),
    "committing": frozenset({"authorized", "closed", "aborted"}),
    "closed": frozenset(),
    "aborted": frozenset(),
}


TOKEN_TTL_SECONDS = 30 * 60


_REQUIRED_MERGE_LIFECYCLE_CONTROLS = frozenset(
    {
        "dormant-parser-gate",
        "atomic-worktree-ownership",
        "admission-priority",
        "candidate-bound-approval",
    }
)


MERGE_LIFECYCLE_CONTROLS = _REQUIRED_MERGE_LIFECYCLE_CONTROLS


_REQUIRED_ARCHIVE_RECHECK_CONTROLS = frozenset(
    {"start", "authorization", "commit"}
)


ARCHIVE_RECHECK_CONTROLS = _REQUIRED_ARCHIVE_RECHECK_CONTROLS


_CHAIN_CAPABILITY_LOCK = threading.Lock()


_CHAIN_CAPABILITIES: dict[object, dict[str, Any]] = {}


CODEX_EXECUTABLE = "codex"


FRESH_REVIEWER_EVAL_REQUEST_SCHEMA = "forge-fresh-reviewer-eval-request/1"


_FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS = frozenset(
    {
        "schema",
        "sha256",
        "authorization_id",
        "object_format",
        "tree_oid",
        "base_commit_oid",
        "review_diff_sha256",
        "review_diff_byte_count",
        "computed_at",
    }
)


# FR-216 Revision-10: keep direct reviewer input comfortably below the observed
# 1 MiB transport ceiling; larger packages use the single-master window reader.
REVIEW_DIRECT_PACKAGE_MAX_BYTES = 786_432


# FR-216 Revision-10 fixes raw transport views at exactly 64 KiB.
REVIEW_MASTER_WINDOW_BYTES = 65_536


REVIEW_COMPLETE_PACKAGE_REFUSAL = (
    "forge: review refused — reviewer cannot inspect the complete authoritative package"
)


PRODUCED_COMMIT_MISMATCH = (
    "forge: produced commit does not match authorized candidate — chain frozen; "
    "commit left untouched"
)


REVIEW_INSTRUCTION = """Review these changes adversarially using `{constitution_path}`.

Apply all 8 lenses (Ambiguity, Incompleteness, Inconsistency, Infeasibility, Insecurity,
Inoperability, Incorrectness, Overcomplexity) as the baseline, and additionally apply the
matching per-artefact profile recorded in this package. The profile extends the baseline; it
never lets you skip a lens. Pay special attention to:
- Hallucinated function/method/module names that don't exist (COR-07)
- Plausible-looking but incorrect logic (COR-05)
- Missing error handling or edge cases (INC-01, INC-07)
- Security issues (SEC-06, SEC-05, SEC-12)

Apply every committed project-focus item, matching project trigger, and completeness item in
this package. Format findings with principle IDs, complete the Review Completeness Check, and
provide a PASS or BLOCK verdict with severity-ranked findings.
"""


REVIEW_LAUNCHER_CODE = r'''
import datetime
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys

attempt_fd = int(sys.argv[1])
verdict_fd = int(sys.argv[2])
argv_json, expected_digest, expected_prompt_digest = sys.argv[3:]
argv = json.loads(argv_json)
actual_digest = hashlib.sha256(
    json.dumps(argv, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
).hexdigest()
started = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
returncode = 127
reviewer_pid = None
error = None
actual_prompt_digest = ""
verdict_digest = ""
verdict_size = 0

def open_regular(name, flags):
    descriptor = os.open(
        name,
        flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0),
        dir_fd=attempt_fd,
    )
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
        os.close(descriptor)
        raise OSError(f"{name} is not an owner-controlled regular file")
    return descriptor

try:
    attempt_stat = os.fstat(attempt_fd)
    verdict_stat = os.fstat(verdict_fd)
    if not stat.S_ISDIR(attempt_stat.st_mode) or attempt_stat.st_uid != os.geteuid():
        raise OSError("attempt directory is unsafe")
    if not stat.S_ISREG(verdict_stat.st_mode) or verdict_stat.st_uid != os.geteuid():
        raise OSError("verdict descriptor is unsafe")
    if actual_digest != expected_digest:
        raise ValueError("reviewer argv digest mismatch")
    prompt_fd = open_regular("prompt.md", os.O_RDONLY)
    try:
        prompt_parts = []
        while True:
            chunk = os.read(prompt_fd, 65536)
            if not chunk:
                break
            prompt_parts.append(chunk)
        prompt_data = b"".join(prompt_parts)
    finally:
        os.close(prompt_fd)
    actual_prompt_digest = hashlib.sha256(prompt_data).hexdigest()
    if actual_prompt_digest != expected_prompt_digest:
        raise ValueError("reviewer prompt digest mismatch")
    events_fd = open_regular("events.jsonl", os.O_WRONLY | os.O_APPEND)
    try:
        child = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=events_fd,
            stderr=events_fd,
            close_fds=True,
            pass_fds=(verdict_fd,),
        )
        reviewer_pid = child.pid
        child.communicate(prompt_data)
        returncode = child.returncode
    finally:
        os.close(events_fd)
    # Re-open the verdict by name under the guarded attempt directory: the
    # reviewer writes --output-last-message by path and may replace the
    # inode (atomic rename), so the pre-opened descriptor can go stale.
    read_fd = open_regular("verdict.txt", os.O_RDONLY)
    try:
        verdict_parts = []
        while True:
            chunk = os.read(read_fd, 65536)
            if not chunk:
                break
            verdict_parts.append(chunk)
            if sum(len(part) for part in verdict_parts) > 65536:
                raise ValueError("reviewer verdict exceeds 65536 bytes")
    finally:
        os.close(read_fd)
    verdict_data = b"".join(verdict_parts)
    verdict_digest = hashlib.sha256(verdict_data).hexdigest()
    verdict_size = len(verdict_data)
except BaseException as exc:
    error = type(exc).__name__
completed = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
record = {
    "argv_digest": actual_digest,
    "completed_at": completed,
    "error": error,
    "prompt_digest": actual_prompt_digest,
    "returncode": returncode,
    "reviewer_pid": reviewer_pid,
    "schema": "forge-review-process/1",
    "started_at": started,
    "verdict_digest": verdict_digest,
    "verdict_size": verdict_size,
    "wrapper_pid": os.getpid(),
}
temporary_name = f".completion-{secrets.token_hex(8)}.tmp"
descriptor = os.open(
    temporary_name,
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
    0o600,
    dir_fd=attempt_fd,
)
try:
    data = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
    os.fchmod(descriptor, 0o600)
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError("short completion write")
        offset += written
    os.fsync(descriptor)
    os.close(descriptor)
    descriptor = -1
    os.replace(
        temporary_name,
        "completion.json",
        src_dir_fd=attempt_fd,
        dst_dir_fd=attempt_fd,
    )
    os.fsync(attempt_fd)
finally:
    if descriptor >= 0:
        os.close(descriptor)
    try:
        os.unlink(temporary_name, dir_fd=attempt_fd)
    except FileNotFoundError:
        pass
'''


GLOBAL_OPTIONS_HELP = """\
global options (accepted before or after the verb; parsed ahead of argparse):
  --repo PATH        a directory inside the target repository (default: cwd)
  --run-id RUN_ID    bind a new chain to this explicitly identified open
                     orchestration run; `commit start` then requires --task,
                     and later chain verbs inherit the binding (no --run-id)
  --chain-id ID      select the chain a shared verb addresses; required by
                     merge shared verbs and `chain tombstone`
  --json             machine-readable JSON output
  --verbose          include diagnostic detail in refusals and receipts

--task TASK_ID is not global: it is a verb option of `commit start`, `merge start`,
and `journal ingest-chain` (accepted only after the verb) naming the run task the
chain's gate verifications cite.
"""


ARCHIVE_CONTAMINATION = (
    "forge: archive refused — close tree contains unrelated changes"
)


SECRET_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key-block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    (
        "generic-secret-assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|password|passwd|credential|client[_-]?secret)\b\s*[:=]\s*['\"]?([^\s,'\"}#]{8,})"
        ),
    ),
)


PLACEHOLDER_RE = re.compile(
    r"(?i)^(?:example|placeholder|changeme|redacted|dummy|test|none|null|x+|\$\{[^}]+\}|<[^>]+>)$"
)


ABORT_DISPOSITION_PRECONDITIONS = (
    "run-bound",
    "aborted",
    "null-outbox",
    "candidate",
    "never-landed",
    "uncarried-abort",
    "journal-readable",
    "no-journaled-decision",
)


_MERGE_CANDIDATE_IDENTITY_FIELDS = (
    "remote",
    "destination_ref",
    "remote_tip",
    "candidate_head",
    "diff_sha256",
    "policy_commit",
    "policy_digest",
    "worktree_identity",
)


_MERGE_BOOTSTRAP_CHILD_SOURCE = (
    "import importlib.util,sys;"
    "p=sys.argv[1];"
    "s=importlib.util.spec_from_file_location('forge_bootstrap_child',p);"
    "m=importlib.util.module_from_spec(s);"
    "sys.modules[s.name]=m;"
    "s.loader.exec_module(m);"
    "raise SystemExit(m._merge_bootstrap_child_main(sys.argv[2]))"
)


_DERIVE_MERGE_SCOPE = object()


_MERGE_INITIAL_INTEGRATION = {
    "condition": "none",
    "primary_condition": "none",
    "epoch": None,
    "remote_movement_count": 0,
    "intent": None,
    "observed": None,
    "pre_rebase": None,
    "conflict": None,
    "push": None,
}
