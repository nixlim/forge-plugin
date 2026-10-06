"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import threading
from typing import Any
import re


TERMINAL_STATES = {"closed", "aborted"}


TERMINAL_TOUCH_VERBS = frozenset(
    {"status", "commit abort", "review cancel"}
)


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


_CHAIN_CAPABILITY_LOCK = threading.Lock()


_CHAIN_CAPABILITIES: dict[object, dict[str, Any]] = {}


CODEX_EXECUTABLE = "codex"


CLAUDE_EXECUTABLE = "claude"


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


GLOBAL_OPTIONS_HELP = """\
global options (accepted before or after the verb; parsed ahead of argparse):
  --repo PATH        a directory inside the target repository (default: cwd)
  --run-id RUN_ID    name the launch journal
  --chain-id ID      select the chain a shared verb addresses; required by
                     merge shared verbs and `chain tombstone`
  --json             machine-readable JSON output
  --verbose          include diagnostic detail in refusals and receipts

--task TASK_ID is a launch option naming the task.
"""




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
