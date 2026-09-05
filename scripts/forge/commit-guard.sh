#!/usr/bin/env bash
# Claude Code PreToolUse guard for git commit and git push.
#
# The hook never executes the submitted command. It parses enough of the shell
# command to identify direct Git invocations, delegates halt enforcement to
# check-halt.sh, and validates the reviewed staged-diff marker for Forge repos.
# forge: new for plugin — enforce halt and reviewed-commit authorization at tool use
set -uo pipefail
umask 077

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)" || exit 0

python_code=""
IFS= read -r -d '' python_code <<'PY' || true
from __future__ import annotations

from dataclasses import dataclass
import dataclasses
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import stat
import subprocess
import sys


ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.DOTALL)
HASH = re.compile(r"[0-9a-f]{64}")
COMMIT_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
HALT_MESSAGE = re.compile(r"forge: operator halt engaged \(([^)]+)\)")
HEAD_PLUGIN_REF_LINE = re.compile(br"^plugin_ref: ", re.MULTILINE)
UPSTREAM_COMMIT_LINE = re.compile(br"^upstream_commit:(?: [^\r\n]*)?\r?$", re.MULTILINE)
UPSTREAM_REGION_LINE = re.compile(
    br"^region: [^ ()\t\r\n]+ \([^()\r\n]+\)\r?$",
    re.MULTILINE,
)
REDIRECTION = re.compile(
    r"(?:\d*(?:<<<|<<-?|>>|<>|>\||<&|>&|<|>)|&>>?)(.*)",
    re.DOTALL,
)
SHELL_VARIABLE = re.compile(
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))"
)
SAFE_GIT_ENV = {
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_WORK_TREE",
}
FLAG_GLOBAL_OPTIONS = {
    "-p",
    "-P",
    "--paginate",
    "--no-pager",
    "--bare",
    "--no-replace-objects",
    "--literal-pathspecs",
    "--glob-pathspecs",
    "--noglob-pathspecs",
    "--icase-pathspecs",
    "--no-lazy-fetch",
    "--no-optional-locks",
    "--no-advice",
    "--version",
    "--help",
}
ENV_NO_VALUE_OPTIONS = {
    "-i",
    "-0",
    "-v",
    "--ignore-environment",
    "--null",
    "--list-signal-handlers",
    "--debug",
}
ENV_VALUE_OPTIONS = {"-u", "-C", "-S", "-P"}
ENV_EQUALS_VALUE_OPTIONS = {"--unset", "--chdir", "--split-string"}
ENV_OPTIONAL_SIGNAL_OPTIONS = {
    "--block-signal",
    "--default-signal",
    "--ignore-signal",
}
FORGE_CLI_SINGLE_COMMANDS = frozenset({"status", "verify", "classify", "push"})
FORGE_CLI_PAIRED_COMMANDS = frozenset(
    {
        ("commit", "start"),
        ("commit", "restage"),
        ("commit", "rebase"),
        ("commit", "abort"),
        ("commit", "abort-disposition"),
        ("commit", "approve"),
        ("commit", "skip"),
        ("commit", "finalize"),
        ("gate", "run"),
        ("scan", "secrets"),
        ("review", "request"),
        ("review", "collect"),
        ("review", "attach"),
        ("review", "disposition"),
        ("merge", "start"),
        ("merge", "refresh"),
        ("merge", "verify"),
        ("merge", "gate"),
        ("merge", "finalize"),
        ("merge", "recover"),
        ("merge", "cleanup"),
        ("merge", "abort"),
    }
)
FORGE_CLI_GLOBAL_VALUE_OPTIONS = frozenset({"--chain-id", "--repo", "--run-id"})
FORGE_CLI_DENIALS = {
    "deny-approve": (
        "forge: operator verb denied — present the candidate and ask the operator "
        "to run this via ! (commit approve)"
    ),
    "deny-skip": (
        "forge: operator verb denied — present the candidate and ask the operator "
        "to run this via ! (commit skip)"
    ),
}
V2_CORPUS_FAILURE_DENIAL = (
    "forge: history mutation mode invalid — repair committed .forge-manifest "
    "through Forge CLI"
)
V2_CORPUS_SHA256 = (
    "310bfda5efdbfe3c99a1d189c8ff336782f90a79af741c4098ada4ae579bde27"
)
V2_DENIAL_FALLBACKS = {
    "deny-merge-approve": (
        "forge: operator verb denied — present the candidate and ask the operator "
        "to run this via ! (merge approve)"
    ),
    "deny-invalid-mode": V2_CORPUS_FAILURE_DENIAL,
    "deny-raw-commit": (
        "forge: raw git commit denied — use Forge CLI commit finalize"
    ),
    "deny-raw-push": (
        "forge: raw git push denied — use Forge CLI merge finalize or Forge CLI push"
    ),
}
V2_CASE_EXPECTATIONS = {
    "activation-enabled-raw-commit-worktree-legacy": "deny-raw-commit",
    "activation-enabled-raw-push-worktree-missing": "deny-raw-push",
    "activation-invalid-raw-commit": "deny-invalid-mode",
    "activation-invalid-raw-push": "deny-invalid-mode",
    "activation-legacy-raw-push-worktree-invalid": "allow",
    "activation-missing-raw-push-worktree-enabled": "allow",
    "activation-non-forge-raw-commit": "allow",
    "activation-upstream-raw-push": "allow",
    "allow-enabled-commit-finalize": "allow",
    "allow-enabled-merge-finalize": "allow",
    "allow-enabled-push": "allow",
    "allow-quoted-raw-text": "allow",
    "compound-merge-finalize-then-raw-commit": "deny-raw-commit",
    "compound-push-then-raw-push": "deny-raw-push",
    "deny-merge-approve-global-after-last": "deny-merge-approve",
    "deny-merge-approve-global-before-first": "deny-merge-approve",
    "deny-merge-approve-global-between-middle": "deny-merge-approve",
    "no-match-merge-approved": "no-match",
}
V2_ACTIVATION_CONTEXTS = frozenset(
    {
        "non-forge",
        "upstream",
        "plugin-mode-missing",
        "legacy-v1",
        "forge-verbs-v1",
        "invalid",
    }
)
V2_EXPECTATIONS = frozenset(
    {
        "allow",
        "no-match",
        "deny-merge-approve",
        "deny-invalid-mode",
        "deny-raw-commit",
        "deny-raw-push",
    }
)
V2_DENIAL_EXPECTATIONS = frozenset(
    {
        "deny-merge-approve",
        "deny-invalid-mode",
        "deny-raw-commit",
        "deny-raw-push",
    }
)
# Fail-closed parser bounds. The shell parser recurses once per nested
# substitution, case body, and Forge CLI segment, so hostile nesting must be
# denied before it can exhaust the interpreter stack or the hook deadline; a
# breached bound or an internal parser failure is a denial, never a traceback
# with a non-blocking exit. Exit 2 blocks on its own; both channels carry the
# literal so the model sees the same reason either way.
MAX_NESTING_DEPTH = 64
PARSE_TIME_BUDGET_SECONDS = 10.0
GUARD_FAILSAFE_DENIALS = {
    "nesting": (
        "forge: commit guard input bound exceeded — command nesting reached the "
        f"{MAX_NESTING_DEPTH}-level bound and was not classified; split the command"
    ),
    "time": (
        "forge: commit guard time budget exceeded — command was not classified "
        f"within {PARSE_TIME_BUDGET_SECONDS:g}s; split the command"
    ),
    "internal": (
        "forge: commit guard internal failure — command was not classified "
        "({failure}); split the command"
    ),
}
GUARD_FAILSAFE_REASON_CODES = {
    "nesting": "guard-input-bound",
    "time": "guard-time-budget",
    "internal": "guard-internal-failure",
}


# Post-parse resolution runs Git and check-halt per action; arguments never
# change the repository context, so memoize by the context-determining fields.
# Disabling this in memory makes distinct-argument floods linear in subprocess
# cost again, which the time budget then denies.
CONTEXT_MEMO_ENABLED = True
# The structured parse may swallow a case compound into one segment. Bash does
# not treat `case` as reserved after `#`, in heredoc bodies, or inside `${}`,
# `[[ ]]`, `(( ))`, so a swallow admitted there can hide the segments that a
# plain separator split exposes. Every command is therefore also split raw
# (swallow disabled) and the union of actions and denials is enforced; the raw
# split never invents actions for a genuine compound because its first token
# is `case`. Disabling this in memory re-opens the swallow class.
RAW_SEGMENT_PASS_ENABLED = True
_case_swallow_active = True
CASE_WORD = re.compile(r"(?<![A-Za-z0-9_])case(?![A-Za-z0-9_])")
COMMAND_POSITION_TAIL = re.compile(
    r"\s*(?:(?:if|then|elif|else|while|until|do)\s+)*(?:(?:[({]|!|time|-p)\s*)*"
)
IN_WORD = re.compile(r"(?<![A-Za-z0-9_])in(?![A-Za-z0-9_])")
ESAC_WORD = re.compile(r"(?<![A-Za-z0-9_])esac(?![A-Za-z0-9_])")


def _raw_segment_pass(function):
    """Run ``function`` with case-compound swallowing disabled."""
    global _case_swallow_active
    previous = _case_swallow_active
    _case_swallow_active = False
    try:
        return function()
    finally:
        _case_swallow_active = previous
_context_memo: dict[tuple[object, ...], "RepoContext | None"] = {}
_mode_memo: dict[tuple[object, ...], str] = {}
_sentinel_memo: dict[tuple[object, ...], str | None] = {}


def _reset_resolution_memos() -> None:
    _context_memo.clear()
    _mode_memo.clear()
    _sentinel_memo.clear()


def _context_key(action: "GitAction") -> tuple[object, ...]:
    return (
        str(action.shell_cwd),
        action.structural_globals,
        action.assignments,
    )


def _context_identity(context: "RepoContext") -> tuple[object, ...]:
    return (
        str(context.worktree_root),
        str(context.git_dir),
        str(context.index_file),
        str(context.common_dir),
        str(context.main_root),
        context.bare,
    )


def resolve_repo_context(action: "GitAction") -> "RepoContext | None":
    if not CONTEXT_MEMO_ENABLED:
        return repo_context(action)
    key = _context_key(action)
    if key not in _context_memo:
        _context_memo[key] = repo_context(action)
    return _context_memo[key]


def resolve_history_mutation_mode(context: "RepoContext") -> str:
    if not CONTEXT_MEMO_ENABLED:
        return committed_history_mutation_mode(context)
    key = _context_identity(context)
    if key not in _mode_memo:
        _mode_memo[key] = committed_history_mutation_mode(context)
    return _mode_memo[key]


def resolve_halt_sentinel(context: "RepoContext", check_halt: Path) -> str | None:
    if not CONTEXT_MEMO_ENABLED:
        return halt_sentinel(context, check_halt)
    key = _context_identity(context)
    if key not in _sentinel_memo:
        _sentinel_memo[key] = halt_sentinel(context, check_halt)
    return _sentinel_memo[key]


class GuardInputBoundExceeded(Exception):
    """A command exceeded one of the fail-closed parser bounds."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


_nesting_depth = 0


def _enter_nesting() -> None:
    """Count one nested parse level and deny past MAX_NESTING_DEPTH."""
    global _nesting_depth
    if _nesting_depth >= MAX_NESTING_DEPTH:
        raise GuardInputBoundExceeded("nesting")
    _nesting_depth += 1


def _exit_nesting() -> None:
    global _nesting_depth
    _nesting_depth -= 1


def _failsafe_failure_name(exc: BaseException) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "", type(exc).__name__) or "unknown"


GIT_SUBCOMMANDS = frozenset(
    {"add", "commit", "push", "reset", "restore", "rm", "stash"}
)
CHAIN_SCHEMA = "forge-chain/1"
CHAIN_KIND = "commit"
CHAIN_ID = re.compile(r"c-\d{4}-\d{2}-\d{2}T\d{6}Z-[0-9a-f]{4}")
CHAIN_TOKEN = re.compile(r"[0-9a-f]{32}")
CHAIN_STATES = frozenset(
    {
        "classifying",
        "verifying",
        "reviewing",
        "revising",
        "awaiting_approval",
        "authorized",
        "committing",
        "closed",
        "aborted",
    }
)
CHAIN_TERMINAL_STATES = frozenset({"closed", "aborted"})
CHAIN_STATE_KEYS = frozenset(
    {
        "schema",
        "chain_id",
        "kind",
        "state",
        "created_at",
        "last_event_at",
        "inactive_after",
        "repo_head",
        "policy_source",
        "paths",
        "staging",
        "candidate",
        "tier",
        "steps",
        "review",
        "approval",
        "authorization",
        "commit_result",
    }
)
CHAIN_OBJECT_KEYS = (
    "policy_source",
    "staging",
    "candidate",
    "tier",
    "steps",
    "review",
    "approval",
    "authorization",
    "commit_result",
)
AUTHORIZATION_KEYS = frozenset(
    {"token", "candidate", "issued_at", "expires_at", "consumed", "consumed_at"}
)
CHAIN_STATE_MAX_BYTES = 1024 * 1024


@dataclass(frozen=True)
class GitAction:
    subcommand: str
    executable: str
    shell_cwd: Path
    structural_globals: tuple[str, ...]
    assignments: tuple[tuple[str, str], ...]
    subcommand_args: tuple[str, ...]
    preceded_by_command: bool = False


@dataclass(frozen=True)
class RepoContext:
    action: GitAction
    worktree_root: Path
    git_dir: Path
    index_file: Path
    common_dir: Path
    main_root: Path
    git_env: dict[str, str]
    bare: bool


def _matching_backtick(command: str, index: int) -> int | None:
    """Return the closing offset for one executable backtick substitution."""
    cursor = index + 1
    escaped = False
    while cursor < len(command):
        char = command[cursor]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "`":
            return cursor
        cursor += 1
    return None


def _shell_word_end(command: str, index: int) -> int:
    cursor = index
    while cursor < len(command) and (
        command[cursor].isalnum() or command[cursor] == "_"
    ):
        cursor += 1
    return cursor


def _reserved_word_start(command: str, index: int) -> bool:
    return index == 0 or command[index - 1].isspace() or command[index - 1] in ";|&(){}"


def _reserved_word_opens_command(word: str) -> bool:
    """Return whether a shell control word is followed by a command position."""
    return word in {"if", "then", "elif", "else", "while", "until", "do", "time"}


def _matching_executable_parenthesis(command: str, index: int) -> int | None:
    """Return the closing offset for `$(`, `<(`, or `>(` at ``index``."""
    _enter_nesting()
    try:
        return _matching_executable_parenthesis_body(command, index)
    finally:
        _exit_nesting()


def _matching_executable_parenthesis_body(command: str, index: int) -> int | None:
    cursor = index + 2
    depth = 1
    quote: str | None = None
    escaped = False
    case_states: list[str] = []
    case_subject_seen: list[bool] = []
    case_pattern_seen: list[bool] = []
    command_position = True
    while cursor < len(command):
        char = command[cursor]
        if escaped:
            escaped = False
            cursor += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            cursor += 1
            continue
        if quote == "'":
            if char == "'":
                quote = None
            cursor += 1
            continue
        if quote == '"':
            if char == '"':
                quote = None
                cursor += 1
                continue
            if command.startswith("$(", cursor):
                closing = _matching_executable_parenthesis(command, cursor)
                cursor = closing + 1 if closing is not None else cursor + 2
                continue
            if char == "`":
                closing = _matching_backtick(command, cursor)
                cursor = closing + 1 if closing is not None else cursor + 1
                continue
            cursor += 1
            continue
        if char in ("'", '"'):
            quote = char
            cursor += 1
            continue
        if command.startswith(("$(", "<(", ">("), cursor):
            closing = _matching_executable_parenthesis(command, cursor)
            cursor = closing + 1 if closing is not None else cursor + 2
            continue
        if char == "`":
            closing = _matching_backtick(command, cursor)
            cursor = closing + 1 if closing is not None else cursor + 1
            continue
        if case_states and case_states[-1] == "body":
            case_separator = next(
                (
                    separator
                    for separator in (";;&", ";;", ";&")
                    if command.startswith(separator, cursor)
                ),
                None,
            )
            if case_separator is not None:
                case_states[-1] = "pattern"
                case_pattern_seen[-1] = False
                command_position = False
                cursor += len(case_separator)
                continue
        if (
            (char.isalpha() or char == "_")
            and _reserved_word_start(command, cursor)
        ):
            word_end = _shell_word_end(command, cursor)
            word = command[cursor:word_end]
            if case_states and case_states[-1] == "await-in":
                if word == "in" and case_subject_seen[-1]:
                    case_states[-1] = "pattern"
                    case_pattern_seen[-1] = False
                    command_position = False
                else:
                    case_subject_seen[-1] = True
            elif (
                case_states
                and word == "esac"
                and case_states[-1] == "pattern"
                and not case_pattern_seen[-1]
            ):
                case_states.pop()
                case_subject_seen.pop()
                case_pattern_seen.pop()
                command_position = False
            elif command_position and word == "case":
                if len(case_states) >= MAX_NESTING_DEPTH:
                    raise GuardInputBoundExceeded("nesting")
                case_states.append("await-in")
                case_subject_seen.append(False)
                case_pattern_seen.append(False)
                command_position = False
            elif case_states and case_states[-1] == "pattern":
                case_pattern_seen[-1] = True
            elif command_position and not _reserved_word_opens_command(word):
                command_position = False
            cursor = word_end
            continue
        if (
            case_states
            and case_states[-1] == "pattern"
            and case_pattern_seen[-1]
            and char == ")"
        ):
            case_states[-1] = "body"
            command_position = True
            cursor += 1
            continue
        if case_states and case_states[-1] == "pattern" and not char.isspace():
            case_pattern_seen[-1] = True
        separator = next(
            (
                item
                for item in ("&&", "||", ";", "|", "&", "\n")
                if command.startswith(item, cursor)
            ),
            None,
        )
        if separator is not None:
            if not case_states or case_states[-1] != "pattern":
                command_position = True
            cursor += len(separator)
            continue
        if char == "(":
            depth += 1
            command_position = True
        elif char == ")":
            depth -= 1
            if depth == 0:
                return cursor
        cursor += 1
    return None


def _executable_parenthesis_at(
    command: str, index: int, quote: str | None
) -> bool:
    """Return whether an executable parenthesized substitution starts here."""
    if command.startswith("$(", index):
        return quote != "'"
    return quote is None and command.startswith(("<(", ">("), index)


def _opaque_executable_end(
    command: str, index: int, quote: str | None
) -> int | None:
    """Return the end of an executable span which outer splitting must skip."""
    if _executable_parenthesis_at(command, index, quote):
        return _matching_executable_parenthesis(command, index)
    if command[index] == "`" and quote != "'":
        return _matching_backtick(command, index)
    return None


def _case_swallow_admissible(syntax: str, command: str, index: int) -> bool:
    """Admit a case-compound swallow only at command position in the masked view.

    Quoted text is already masked to `x` in the view, so no separate quote
    check is needed. Deliberately a named seam: tests disable it in memory to
    show that the raw-pass union, not this admission, carries the guarantee
    that a swallow never hides a segment.
    """
    return _case_swallow_active and _case_starts_command(
        syntax[:index], command, index
    )


def split_segments(command: str) -> list[tuple[str, str | None]]:
    """Split on shell operators outside quotes and executable substitutions."""
    segments: list[tuple[str, str | None]] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    syntax: str | None = None

    while index < len(command):
        char = command[index]
        if escaped:
            current.append(char)
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            current.append(char)
            escaped = True
            index += 1
            continue
        if quote == "'":
            current.append(char)
            if char == "'":
                quote = None
            index += 1
            continue
        if quote == '"' and char == '"':
            current.append(char)
            quote = None
            index += 1
            continue
        if quote is None and char in ("'", '"'):
            quote = char
            current.append(char)
            index += 1
            continue
        closing = _opaque_executable_end(command, index, quote)
        if closing is not None:
            current.extend(command[index : closing + 1])
            index = closing + 1
            continue
        if command.startswith("case", index):
            if syntax is None:
                syntax = _shell_syntax_view(command)
            if _case_swallow_admissible(syntax, command, index):
                case_end = _matching_case_end(command, index, syntax)
                if case_end is not None:
                    current.extend(command[index:case_end])
                    index = case_end
                    continue
        if quote == '"':
            current.append(char)
            index += 1
            continue

        separator: str | None = None
        if command.startswith("&&", index) or command.startswith("||", index):
            separator = command[index : index + 2]
        elif char in ";|&\n":
            separator = char
        if separator is not None:
            segments.append(("".join(current), separator))
            current = []
            index += len(separator)
            continue

        current.append(char)
        index += 1

    segments.append(("".join(current), None))
    return segments


def executable_subcommands(command: str) -> list[str]:
    """Return executable substitution bodies, excluding quoted or escaped data."""
    nested: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote == "'":
            if char == "'":
                quote = None
            index += 1
            continue
        if quote == '"' and char == '"':
            quote = None
            index += 1
            continue
        if quote is None and char in ("'", '"'):
            quote = char
            index += 1
            continue
        if _executable_parenthesis_at(command, index, quote):
            closing = _matching_executable_parenthesis(command, index)
            if closing is not None:
                nested.append(command[index + 2 : closing])
                index = closing + 1
            else:
                index += 2
            continue
        if char == "`" and quote != "'":
            closing = _matching_backtick(command, index)
            if closing is None:
                index += 1
            else:
                nested.append(_legacy_backtick_body(command[index + 1 : closing]))
                index = closing + 1
            continue
        index += 1
    return nested


def _legacy_backtick_body(body: str) -> str:
    """Expose escaped nested backticks before recursively parsing their body."""
    normalized: list[str] = []
    index = 0
    while index < len(body):
        if body[index] == "\\" and index + 1 < len(body) and body[index + 1] == "`":
            normalized.append("`")
            index += 2
            continue
        normalized.append(body[index])
        index += 1
    return "".join(normalized)


def _shell_syntax_view(command: str) -> str:
    """Mask quoted, escaped, and substitution text while preserving offsets."""
    view = list(command)
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if char == "\\" and quote != "'":
            view[index] = "x"
            if index + 1 < len(command):
                view[index + 1] = "x"
            index += 2
            continue
        if quote == "'":
            view[index] = "x"
            if char == "'":
                quote = None
            index += 1
            continue
        if quote == '"':
            view[index] = "x"
            if char == '"':
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            view[index] = "x"
            index += 1
            continue
        if _executable_parenthesis_at(command, index, quote):
            closing = _matching_executable_parenthesis(command, index)
            if closing is not None:
                view[index : closing + 1] = "x" * (closing + 1 - index)
                index = closing + 1
                continue
        if char == "`":
            closing = _matching_backtick(command, index)
            if closing is not None:
                view[index : closing + 1] = "x" * (closing + 1 - index)
                index = closing + 1
                continue
        index += 1
    return "".join(view)


def _case_starts_command(prefix: str, command: str, index: int) -> bool:
    if not _reserved_word_start(command, index):
        return False
    word_end = index + 4
    if word_end < len(command) and (
        command[word_end].isalnum() or command[word_end] == "_"
    ):
        return False
    # Only the tail after the last separator can put `case` at command
    # position; an earlier separator's tail would contain that separator.
    tail_start = max(prefix.rfind(separator) for separator in ";|&\n") + 1
    return COMMAND_POSITION_TAIL.fullmatch(prefix, tail_start) is not None


def _matching_case_end(
    command: str, index: int, syntax: str | None = None
) -> int | None:
    """Return the exclusive end of a balanced unquoted case compound."""
    if syntax is None:
        syntax = _shell_syntax_view(command)
    case_states: list[str] = []
    subject_seen: list[bool] = []
    pattern_seen: list[bool] = []
    command_position = True
    cursor = index
    while cursor < len(syntax):
        if case_states and case_states[-1] == "body":
            case_separator = next(
                (
                    separator
                    for separator in (";;&", ";;", ";&")
                    if syntax.startswith(separator, cursor)
                ),
                None,
            )
            if case_separator is not None:
                case_states[-1] = "pattern"
                pattern_seen[-1] = False
                command_position = False
                cursor += len(case_separator)
                continue
        char = syntax[cursor]
        if (
            (char.isalpha() or char == "_")
            and _reserved_word_start(syntax, cursor)
        ):
            word_end = _shell_word_end(syntax, cursor)
            word = syntax[cursor:word_end]
            if case_states and case_states[-1] == "await-in":
                if word == "in" and subject_seen[-1]:
                    case_states[-1] = "pattern"
                    pattern_seen[-1] = False
                    command_position = False
                else:
                    subject_seen[-1] = True
            elif (
                case_states
                and word == "esac"
                and case_states[-1] == "pattern"
                and not pattern_seen[-1]
            ):
                case_states.pop()
                subject_seen.pop()
                pattern_seen.pop()
                if not case_states:
                    return word_end
                command_position = False
            elif command_position and word == "case":
                if len(case_states) >= MAX_NESTING_DEPTH:
                    raise GuardInputBoundExceeded("nesting")
                case_states.append("await-in")
                subject_seen.append(False)
                pattern_seen.append(False)
                command_position = False
            elif case_states and case_states[-1] == "pattern":
                pattern_seen[-1] = True
            elif command_position and not _reserved_word_opens_command(word):
                command_position = False
            cursor = word_end
            continue
        if (
            case_states
            and case_states[-1] == "pattern"
            and pattern_seen[-1]
            and char == ")"
        ):
            case_states[-1] = "body"
            command_position = True
            cursor += 1
            continue
        if case_states and case_states[-1] == "pattern" and not char.isspace():
            pattern_seen[-1] = True
        separator = next(
            (
                item
                for item in ("&&", "||", ";", "|", "&", "\n")
                if syntax.startswith(item, cursor)
            ),
            None,
        )
        if separator is not None:
            if not case_states or case_states[-1] != "pattern":
                command_position = True
            cursor += len(separator)
            continue
        if char == "(" and (not case_states or case_states[-1] != "pattern"):
            command_position = True
        cursor += 1
    return None


def _nested_case_end(command: str, syntax: str, index: int) -> int | None:
    """Return a nested case end when one begins at this arm-body offset."""
    if not syntax.startswith("case", index):
        return None
    end = index + 4
    if (index and (syntax[index - 1].isalnum() or syntax[index - 1] == "_")) or (
        end < len(syntax) and (syntax[end].isalnum() or syntax[end] == "_")
    ):
        return None
    return _matching_case_end(command, index, syntax)


def _case_arm_end(
    command: str,
    syntax: str,
    body_start: int,
    outer_esac: int,
) -> tuple[int, int]:
    """Find an outer arm terminator while skipping complete nested cases."""
    cursor = body_start
    while cursor < outer_esac:
        nested_end = _nested_case_end(command, syntax, cursor)
        if nested_end is not None and nested_end <= outer_esac:
            cursor = nested_end
            continue
        delimiter = next(
            (
                item
                for item in (";;&", ";;", ";&")
                if syntax.startswith(item, cursor)
            ),
            None,
        )
        if delimiter is not None:
            return cursor, len(delimiter)
        cursor += 1
    return outer_esac, 0


def _executable_case_body_spans(command: str) -> list[tuple[int, int]]:
    """Return absolute (start, end) spans of unquoted case-arm bodies."""
    spans: list[tuple[int, int]] = []
    syntax = _shell_syntax_view(command)
    cursor = 0
    while cursor < len(command):
        match = CASE_WORD.search(syntax, cursor)
        if match is None:
            break
        case_start = match.start()
        if not _case_starts_command(syntax[:case_start], syntax, case_start):
            cursor = case_start + 4
            continue
        case_end = _matching_case_end(command, case_start, syntax)
        if case_end is None:
            break
        case_syntax = syntax[case_start:case_end]
        case_command = command[case_start:case_end]
        in_match = IN_WORD.search(case_syntax, 4)
        esac_match = list(ESAC_WORD.finditer(case_syntax))
        if in_match is None or not esac_match:
            cursor = case_end
            continue
        arm_cursor = in_match.end()
        outer_esac = esac_match[-1].start()
        while arm_cursor < outer_esac:
            pattern_end = case_syntax.find(")", arm_cursor, outer_esac)
            if pattern_end < 0:
                break
            body_start = pattern_end + 1
            body_end, delimiter_length = _case_arm_end(
                case_command,
                case_syntax,
                body_start,
                outer_esac,
            )
            spans.append((case_start + body_start, case_start + body_end))
            if body_end == outer_esac:
                break
            arm_cursor = body_end + delimiter_length
        cursor = case_end
    return spans


def _case_bodies_from_spans(command: str, spans: list[tuple[int, int]]) -> list[str]:
    bodies: list[str] = []
    for start, end in spans:
        body = command[start:end].strip()
        if body:
            bodies.append(body)
    return bodies


def executable_case_bodies(
    command: str, spans: list[tuple[int, int]] | None = None
) -> list[str]:
    """Return case-arm command bodies for recursive action classification."""
    if spans is None:
        spans = _executable_case_body_spans(command)
    return _case_bodies_from_spans(command, spans)


def _without_case_bodies(command: str, spans: list[tuple[int, int]]) -> str:
    """Blank case-arm bodies so their substitutions are visited once, via the body."""
    if not spans:
        return command
    view = list(command)
    for start, end in spans:
        view[start:end] = " " * (end - start)
    return "".join(view)


def _nested_executables(segment: str) -> list[str]:
    """Substitutions outside case-arm bodies, then the bodies themselves."""
    spans = _executable_case_body_spans(segment)
    return [
        *executable_subcommands(_without_case_bodies(segment, spans)),
        *executable_case_bodies(segment, spans),
    ]


def _mask_case_compounds(command: str, syntax: str) -> str:
    """Hide complete case syntax from group-delimiter classification."""
    masked = list(syntax)
    cursor = 0
    while cursor < len(syntax):
        match = CASE_WORD.search(syntax, cursor)
        if match is None:
            break
        case_start = match.start()
        if not _case_starts_command(syntax[:case_start], syntax, case_start):
            cursor = case_start + 4
            continue
        case_end = _matching_case_end(command, case_start, syntax)
        if case_end is None:
            break
        masked[case_start:case_end] = "x" * (case_end - case_start)
        cursor = case_end
    return "".join(masked)


def _standalone_brace(syntax: str, index: int) -> bool:
    return (
        (index == 0 or syntax[index - 1].isspace())
        and (index + 1 == len(syntax) or syntax[index + 1].isspace())
    )


def _mask_word_parentheses(syntax: str) -> str:
    """Mask balanced word-level parentheses which are not command groups."""
    masked = list(syntax)
    index = 0
    while index < len(syntax):
        if syntax[index] != "(":
            index += 1
            continue
        prefix = syntax[:index].rstrip()
        previous = syntax[index - 1] if index else ""
        is_array = previous == "="
        is_extglob = previous in "?*+@!" and bool(previous)
        is_function = (
            index + 1 < len(syntax)
            and syntax[index + 1] == ")"
            and re.search(r"(?:^|\s)[A-Za-z_][A-Za-z0-9_]*$", prefix) is not None
        )
        if not (is_array or is_extglob or is_function):
            index += 1
            continue
        depth = 1
        cursor = index + 1
        while cursor < len(syntax) and depth:
            if syntax[cursor] == "(":
                depth += 1
            elif syntax[cursor] == ")":
                depth -= 1
            cursor += 1
        if depth:
            index += 1
            continue
        masked[index:cursor] = "x" * (cursor - index)
        index = cursor
    return "".join(masked)


def _shell_prefix_end(syntax: str, start: int, positions: set[int]) -> int:
    """Skip shell negation/time prefixes which precede a command-position group."""
    index = start
    while index < len(syntax) and syntax[index].isspace():
        index += 1
    while index < len(syntax):
        if syntax[index] == "!" and (
            index + 1 == len(syntax) or syntax[index + 1].isspace()
        ):
            positions.add(index)
            index += 1
        elif syntax.startswith("time", index) and (
            index + 4 == len(syntax) or syntax[index + 4].isspace()
        ):
            positions.update(range(index, index + 4))
            index += 4
            while index < len(syntax) and syntax[index].isspace():
                index += 1
            if syntax.startswith("-p", index) and (
                index + 2 == len(syntax) or syntax[index + 2].isspace()
            ):
                positions.update(range(index, index + 2))
                index += 2
        else:
            break
        while index < len(syntax) and syntax[index].isspace():
            index += 1
    return index


def shell_group_structure(segment: str) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Remove structural group tokens and return their ordered scope events."""
    syntax = _shell_syntax_view(segment)
    syntax = _mask_case_compounds(segment, syntax)
    syntax = _mask_word_parentheses(syntax)
    openers: list[str] = []
    positions: set[int] = set()
    index = _shell_prefix_end(syntax, 0, positions)
    while index < len(syntax):
        char = syntax[index]
        if char == "(" or (char == "{" and _standalone_brace(syntax, index)):
            openers.append(char)
            positions.add(index)
            index += 1
            while index < len(syntax) and syntax[index].isspace():
                index += 1
            index = _shell_prefix_end(syntax, index, positions)
            continue
        break

    closers: list[str] = []
    for cursor in range(index, len(syntax)):
        char = syntax[cursor]
        if char == ")" or (char == "}" and _standalone_brace(syntax, cursor)):
            closers.append(char)
            positions.add(cursor)

    normalized = list(segment)
    for position in positions:
        normalized[position] = " "
    return "".join(normalized), tuple(openers), tuple(closers)


def _unique_cwds(cwds: tuple[Path, ...] | list[Path]) -> tuple[Path, ...]:
    return tuple(dict.fromkeys(cwds))


def cwd_after_group_exit(
    opener: str,
    inherited: tuple[Path, ...],
    current: tuple[Path, ...],
    isolated: bool,
) -> tuple[Path, ...]:
    """Apply group persistence without leaking pipeline/background cwd."""
    return inherited if opener == "(" or isolated else current


# Deliberately a named seam: tests disable it in memory to prove the async
# list cwd inheritance is load-bearing.
def cwd_after_async_list(
    inherited: tuple[Path, ...], current: tuple[Path, ...]
) -> tuple[Path, ...]:
    """Restore the parent cwd after a complete asynchronous AND/OR list."""
    del current
    return inherited


def without_shell_grouping(tokens: list[str]) -> list[str]:
    """Remove only command-position subshell/brace delimiters from one segment."""
    result = list(tokens)
    while result and result[0] in {"(", "{"}:
        result.pop(0)
    if result and result[0].startswith("("):
        result[0] = result[0].lstrip("(")
        if not result[0]:
            result.pop(0)
    while result and result[-1] in {")",
        "}",
    }:
        result.pop()
    if result and result[-1].endswith(")"):
        result[-1] = result[-1].rstrip(")")
        if not result[-1]:
            result.pop()
    return result


def _without_forge_global_options(tokens: list[str]) -> list[str]:
    """Remove the three singleton CLI globals without reordering verb tokens."""
    result: list[str] = []
    index = 0
    while index < len(tokens):
        word = tokens[index]
        if word in FORGE_CLI_GLOBAL_VALUE_OPTIONS:
            if index + 1 >= len(tokens) or tokens[index + 1] == "":
                return list(tokens)
            index += 2
            continue
        matching_option = next(
            (
                option
                for option in FORGE_CLI_GLOBAL_VALUE_OPTIONS
                if word.startswith(f"{option}=")
            ),
            None,
        )
        if matching_option is not None:
            if word == f"{matching_option}=":
                return list(tokens)
            index += 1
            continue
        result.append(word)
        index += 1
    return result


def _skip_forge_cli_prefix(tokens: list[str]) -> int:
    """Return the index of the interpreter after assignment and env prefixes.

    Bash applies leading ``VAR=value`` words and ``env`` to the command that
    follows, so ``FORGE_SESSION_PID=123 python3 scripts/forge/cli.py commit
    approve`` is the same operator verb as the bare form. Deliberately a named
    seam: tests disable it in memory to prove the prefix skip is load-bearing.
    """
    index = 0
    while index < len(tokens) and ASSIGNMENT.fullmatch(tokens[index]):
        index += 1
    if tokens[index : index + 1] == ["env"]:
        index += 1
        while index < len(tokens) and ASSIGNMENT.fullmatch(tokens[index]):
            index += 1
    return index


def _classify_forge_cli_segment(segment: str) -> str:
    normalized_segment, _openers, _closers = shell_group_structure(segment)
    try:
        tokens = shlex.split(normalized_segment, comments=False, posix=True)
    except ValueError:
        return "no-match"

    tokens = without_shell_grouping(tokens)
    index = _skip_forge_cli_prefix(tokens)
    if len(tokens) < index + 3:
        return "no-match"

    interpreter = tokens[index]
    script = tokens[index + 1]
    if interpreter not in {"python", "python3"} and Path(interpreter).name not in {
        "python",
        "python3",
    }:
        return "no-match"
    if tuple(Path(script).parts[-3:]) != ("scripts", "forge", "cli.py"):
        return "no-match"

    subcommands = tokens[index + 2 :]
    pair = tuple(subcommands[:2])
    if pair == ("commit", "approve"):
        return "deny-approve"
    if pair == ("commit", "skip"):
        return "deny-skip"
    normalized_subcommands = _without_forge_global_options(subcommands)
    normalized_pair = tuple(normalized_subcommands[:2])
    if normalized_pair == ("commit", "approve"):
        return "deny-approve"
    if normalized_pair == ("commit", "skip"):
        return "deny-skip"
    if normalized_pair == ("merge", "approve"):
        return "deny-merge-approve"
    if (
        subcommands[0] in FORGE_CLI_SINGLE_COMMANDS
        or pair in FORGE_CLI_PAIRED_COMMANDS
        or (
            normalized_subcommands
            and (
                normalized_subcommands[0] in FORGE_CLI_SINGLE_COMMANDS
                or normalized_pair in FORGE_CLI_PAIRED_COMMANDS
            )
        )
    ):
        return "allow"
    return "no-match"


def classify_forge_cli_invocation(command: str) -> str:
    """Classify FR-221 Forge CLI invocations in a model Bash command."""
    if not isinstance(command, str) or not command or "\x00" in command:
        return "no-match"
    structured = _classify_forge_cli_invocation_bounded(command)
    if structured.startswith("deny-") or not RAW_SEGMENT_PASS_ENABLED:
        return structured
    raw = _raw_segment_pass(lambda: _classify_forge_cli_invocation_bounded(command))
    if raw.startswith("deny-"):
        return raw
    return "allow" if "allow" in (structured, raw) else structured


def _classify_forge_cli_invocation_bounded(command: str) -> str:
    _enter_nesting()
    try:
        return _classify_forge_cli_invocation_nested(command)
    finally:
        _exit_nesting()


def _classify_forge_cli_invocation_nested(command: str) -> str:
    classification = "no-match"
    for segment, _separator in split_segments(command):
        segment_class = _classify_forge_cli_segment(segment)
        if segment_class.startswith("deny-"):
            return segment_class
        if segment_class == "allow":
            classification = "allow"
        for nested in _nested_executables(segment):
            nested_class = _classify_forge_cli_invocation_bounded(nested)
            if nested_class.startswith("deny-"):
                return nested_class
            if nested_class == "allow":
                classification = "allow"
    return classification


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def load_v2_denials(corpus_path: Path) -> dict[str, str]:
    """Load the additive DM-016 denial literals from the shipped corpus."""
    raw = corpus_path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("v2 hook corpus exceeds size limit")
    if hashlib.sha256(raw).hexdigest() != V2_CORPUS_SHA256:
        raise ValueError("v2 hook corpus bytes are not the manifested generation")
    payload = json.loads(
        raw.decode("utf-8"), object_pairs_hook=_unique_json_object
    )
    if not isinstance(payload, dict) or tuple(payload) != (
        "schema",
        "v1",
        "case_count",
        "cases",
    ):
        raise ValueError("v2 hook corpus root is invalid")
    if payload.get("schema") != "fr223-hook-argv/2":
        raise ValueError("v2 hook corpus schema is invalid")
    v1 = payload.get("v1")
    if not isinstance(v1, dict) or tuple(v1) != (
        "path",
        "schema",
        "sha256",
        "case_count",
    ) or type(v1.get("case_count")) is not int or v1 != {
        "path": "system/fr223/hook-argv-cases-v1.json",
        "schema": "fr223-hook-argv/1",
        "sha256": (
            "1850257d7899a4c7199e9bcbe12ffd39"
            "b0905bb44e49d16348c10e438ea05db7"
        ),
        "case_count": 112,
    }:
        raise ValueError("v2 hook corpus v1 reference is invalid")
    cases = payload.get("cases")
    if (
        type(payload.get("case_count")) is not int
        or payload.get("case_count") != 18
        or not isinstance(cases, list)
        or len(cases) != 18
    ):
        raise ValueError("v2 hook corpus count is invalid")

    observed_expectations: dict[str, str] = {}
    denial_reasons: dict[str, set[str]] = {
        expectation: set() for expectation in V2_DENIAL_EXPECTATIONS
    }
    identifiers: list[str] = []
    for case in cases:
        if not isinstance(case, dict) or tuple(case) != (
            "id",
            "command",
            "activation",
            "expect",
            "reason",
        ):
            raise ValueError("v2 hook corpus case is invalid")
        identifier = case.get("id")
        command = case.get("command")
        activation = case.get("activation")
        expectation = case.get("expect")
        reason = case.get("reason")
        if (
            not isinstance(identifier, str)
            or not identifier
            or not isinstance(command, str)
            or not command
            or not isinstance(reason, str)
            or not reason
            or "\x00" in command
            or "\x00" in reason
            or "\r" in reason
            or "\n" in reason
        ):
            raise ValueError("v2 hook corpus case strings are invalid")
        try:
            identifier.encode("utf-8")
            command.encode("utf-8")
            reason.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("v2 hook corpus strings are not UTF-8 encodable") from exc
        if expectation not in V2_EXPECTATIONS:
            raise ValueError("v2 hook corpus expectation is invalid")
        if not isinstance(activation, dict) or tuple(activation) != (
            "head_manifest",
            "worktree_manifest",
        ):
            raise ValueError("v2 hook corpus activation is invalid")
        if activation.get("head_manifest") not in V2_ACTIVATION_CONTEXTS:
            raise ValueError("v2 hook corpus HEAD activation is invalid")
        if (
            activation.get("worktree_manifest") is not None
            and activation.get("worktree_manifest") not in V2_ACTIVATION_CONTEXTS
        ):
            raise ValueError("v2 hook corpus worktree activation is invalid")
        identifiers.append(identifier)
        observed_expectations[identifier] = expectation
        if expectation in denial_reasons:
            denial_reasons[expectation].add(reason)

    if identifiers != sorted(identifiers) or len(set(identifiers)) != 18:
        raise ValueError("v2 hook corpus identifiers are invalid")
    if observed_expectations != V2_CASE_EXPECTATIONS:
        raise ValueError("v2 hook corpus expectation partition is invalid")
    if any(len(reasons) != 1 for reasons in denial_reasons.values()):
        raise ValueError("v2 hook corpus denial literals are ambiguous")
    resolved = {
        expectation: next(iter(reasons))
        for expectation, reasons in denial_reasons.items()
    }
    if resolved != V2_DENIAL_FALLBACKS:
        raise ValueError("v2 hook corpus denial literals are invalid")
    return resolved


def is_git_token(token: str) -> bool:
    return token == "git" or token.endswith("/git")


def is_env_token(token: str) -> bool:
    return token == "env" or token.endswith("/env")


def is_signal_value(token: str) -> bool:
    """Recognize an unambiguous separated GNU env signal operand."""
    valid_numbers = {int(value) for value in signal.valid_signals()}
    for value in token.split(","):
        if value.isascii() and value.isdigit() and int(value) in valid_numbers:
            continue
        name = value.upper()
        if not name.startswith("SIG"):
            name = f"SIG{name}"
        if name not in signal.Signals.__members__:
            return False
    return bool(token)


def skip_env_prefix(
    tokens: list[str],
    index: int,
    assignments: list[tuple[str, str]],
    cwd: Path,
) -> tuple[int, Path] | None:
    """Skip nested env commands, their options, and interleaved assignments."""
    options_enabled = True
    env_cwd = cwd
    layer_base = cwd
    pending_cwd: Path | None = None
    seen_env = False
    while index < len(tokens):
        token = tokens[index]
        if is_env_token(token):
            if seen_env and pending_cwd is not None:
                env_cwd = pending_cwd
            seen_env = True
            layer_base = env_cwd
            pending_cwd = None
            index += 1
            options_enabled = True
            continue
        if ASSIGNMENT.fullmatch(token):
            key, value = token.split("=", 1)
            assignments.append((key, value))
            index += 1
            continue
        if not options_enabled:
            break
        if token == "--":
            index += 1
            options_enabled = False
            continue
        if token in ENV_NO_VALUE_OPTIONS or re.fullmatch(r"-[i0v]+", token):
            index += 1
            continue
        if token in ENV_VALUE_OPTIONS:
            if index + 1 >= len(tokens):
                return None
            value = tokens[index + 1]
            if token == "-C":
                pending_cwd = resolve_env_cwd(value, layer_base)
            elif token == "-S":
                try:
                    split_tokens = shlex.split(value, comments=False, posix=True)
                except ValueError:
                    return None
                tokens[index : index + 2] = split_tokens
                continue
            index += 2
            continue
        attached_option = next(
            (
                option
                for option in ENV_VALUE_OPTIONS
                if token.startswith(option) and token != option
            ),
            None,
        )
        if attached_option is not None:
            value = token[len(attached_option) :]
            if attached_option == "-C":
                pending_cwd = resolve_env_cwd(value, layer_base)
            elif attached_option == "-S":
                try:
                    split_tokens = shlex.split(value, comments=False, posix=True)
                except ValueError:
                    return None
                tokens[index : index + 1] = split_tokens
                continue
            index += 1
            continue
        if token in ENV_EQUALS_VALUE_OPTIONS:
            if index + 1 >= len(tokens):
                return None
            value = tokens[index + 1]
            if token == "--chdir":
                pending_cwd = resolve_env_cwd(value, layer_base)
            elif token == "--split-string":
                try:
                    split_tokens = shlex.split(value, comments=False, posix=True)
                except ValueError:
                    return None
                tokens[index : index + 2] = split_tokens
                continue
            index += 2
            continue
        equals_option = next(
            (
                option
                for option in ENV_EQUALS_VALUE_OPTIONS
                if token.startswith(f"{option}=")
            ),
            None,
        )
        if equals_option is not None:
            value = token.split("=", 1)[1]
            if equals_option == "--chdir":
                pending_cwd = resolve_env_cwd(value, layer_base)
            elif equals_option == "--split-string":
                try:
                    split_tokens = shlex.split(value, comments=False, posix=True)
                except ValueError:
                    return None
                tokens[index : index + 1] = split_tokens
                continue
            index += 1
            continue
        if token in ENV_OPTIONAL_SIGNAL_OPTIONS:
            index += 1
            if index < len(tokens) and is_signal_value(tokens[index]):
                index += 1
            continue
        if any(token.startswith(f"{option}=") for option in ENV_OPTIONAL_SIGNAL_OPTIONS):
            index += 1
            continue
        break
    return index, pending_cwd or env_cwd


def expand_shell_path(value: str, cwd: Path) -> str:
    """Conservatively resolve inherited simple variables and tilde in path operands."""
    environment = os.environ.copy()
    environment["PWD"] = str(cwd)

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        return environment.get(name, match.group(0))

    return os.path.expanduser(SHELL_VARIABLE.sub(substitute, value))


def resolve_env_cwd(value: str, cwd: Path) -> Path:
    """Apply env -C/--chdir before resolving Git's own -C options."""
    candidate = Path(expand_shell_path(value, cwd))
    if not candidate.is_absolute():
        candidate = cwd / candidate
    try:
        return candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        return candidate


def without_redirections(tokens: list[str]) -> list[str]:
    """Remove shell redirections, which are not command argv tokens."""
    command_tokens: list[str] = []
    index = 0
    while index < len(tokens):
        match = REDIRECTION.fullmatch(tokens[index])
        if match is None:
            command_tokens.append(tokens[index])
            index += 1
            continue
        index += 1
        if match.group(1) == "" and index < len(tokens):
            index += 1
    return command_tokens


def parse_action(tokens: list[str], cwd: Path) -> GitAction | None:
    if not tokens:
        return None

    tokens = list(tokens)

    assignments: list[tuple[str, str]] = []
    git_index = 0
    while git_index < len(tokens) and ASSIGNMENT.fullmatch(tokens[git_index]):
        key, value = tokens[git_index].split("=", 1)
        assignments.append((key, value))
        git_index += 1
    if git_index < len(tokens) and is_env_token(tokens[git_index]):
        parsed_index = skip_env_prefix(tokens, git_index, assignments, cwd)
        if parsed_index is None:
            return None
        git_index, cwd = parsed_index

    if git_index >= len(tokens) or not is_git_token(tokens[git_index]):
        return None

    executable = tokens[git_index]
    index = git_index + 1
    structural: list[str] = []
    while index < len(tokens):
        token = tokens[index]
        if token in ("-C", "-c"):
            if index + 1 >= len(tokens):
                return None
            if token == "-C":
                structural.extend((token, expand_shell_path(tokens[index + 1], cwd)))
            index += 2
            continue
        if token in ("--git-dir", "--work-tree"):
            if index + 1 >= len(tokens):
                return None
            structural.extend((token, expand_shell_path(tokens[index + 1], cwd)))
            index += 2
            continue
        if token.startswith("--") and "=" in token:
            if token.startswith("--git-dir=") or token.startswith("--work-tree="):
                option, value = token.split("=", 1)
                structural.append(f"{option}={expand_shell_path(value, cwd)}")
            index += 1
            continue
        if token == "--bare":
            structural.append(token)
            index += 1
            continue
        if token in FLAG_GLOBAL_OPTIONS:
            index += 1
            continue
        if token.startswith("-") and token != "-":
            # Git grows new no-argument global flags over time. Treat unknown
            # flags conservatively as flags so they cannot hide commit/push.
            index += 1
            continue
        if token == "--":
            index += 1
        break

    if index >= len(tokens) or tokens[index] not in GIT_SUBCOMMANDS:
        return None
    return GitAction(
        subcommand=tokens[index],
        executable=executable,
        shell_cwd=cwd,
        structural_globals=tuple(structural),
        assignments=tuple(assignments),
        subcommand_args=tuple(tokens[index + 1 :]),
    )


def updated_cwd(tokens: list[str], cwd: Path, separator: str | None) -> Path:
    """Track a literal, successful shell cd for following non-pipe segments."""
    if separator in {"|", "&"} or not tokens or tokens[0] != "cd":
        return cwd
    operands = tokens[1:]
    if operands and operands[0] == "--":
        operands = operands[1:]
    if len(operands) != 1:
        return cwd
    candidate = Path(expand_shell_path(operands[0], cwd))
    if not candidate.is_absolute():
        candidate = cwd / candidate
    try:
        candidate = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return cwd
    return candidate if candidate.is_dir() else cwd


def updated_cwd_states(
    tokens: list[str],
    cwds: tuple[Path, ...],
    separator: str | None,
    *,
    may_skip: bool,
    isolated: bool,
) -> tuple[Path, ...]:
    """Advance every plausible cwd while retaining a conditional skip path."""
    advanced = (
        cwds
        if isolated
        else tuple(updated_cwd(tokens, cwd, separator) for cwd in cwds)
    )
    return _unique_cwds((*cwds, *advanced) if may_skip else advanced)


def segment_advances_executable_seen(tokens: list[str]) -> bool:
    """Treat every preceding shell command, including cd, as executable.

    Deliberately a named seam: tests disable it in memory to prove the
    preceded-by-command qualification is load-bearing.
    """
    return bool(tokens)


def _find_actions_recursive(
    command: str,
    cwd: Path,
    *,
    executable_seen: bool,
) -> list[GitAction]:
    _enter_nesting()
    try:
        return _find_actions_recursive_body(
            command, cwd, executable_seen=executable_seen
        )
    finally:
        _exit_nesting()


def _find_actions_recursive_body(
    command: str,
    cwd: Path,
    *,
    executable_seen: bool,
) -> list[GitAction]:
    actions: list[GitAction] = []
    cwds = (cwd,)
    group_stack: list[
        tuple[str, tuple[Path, ...], bool, bool, tuple[Path, ...]]
    ] = []
    and_or_entry_cwds = cwds
    previous_separator: str | None = None
    for segment, separator in split_segments(command):
        normalized_segment, openers, closers = shell_group_structure(segment)
        may_skip = previous_separator in {"&&", "||"}
        for index, opener in enumerate(openers):
            group_stack.append(
                (
                    opener,
                    cwds,
                    may_skip if index == 0 else False,
                    previous_separator == "|" if index == 0 else False,
                    and_or_entry_cwds,
                )
            )
            and_or_entry_cwds = cwds
        for shell_cwd in cwds:
            for nested in _nested_executables(segment):
                for action in _find_actions_recursive(
                    nested,
                    shell_cwd,
                    executable_seen=True,
                ):
                    if action not in actions:
                        actions.append(action)
        try:
            tokens = shlex.split(normalized_segment, comments=False, posix=True)
        except ValueError:
            previous_separator = separator
            continue
        command_tokens = without_redirections(tokens)
        candidates = [tokens, command_tokens]
        for candidate_tokens in candidates:
            for shell_cwd in cwds:
                action = parse_action(candidate_tokens, shell_cwd)
                if action is not None:
                    qualified_action = dataclasses.replace(
                        action, preceded_by_command=executable_seen
                    )
                    if qualified_action not in actions:
                        actions.append(qualified_action)
        if segment_advances_executable_seen(command_tokens):
            executable_seen = True
        isolated_segment = separator in {"|", "&"} or (
            previous_separator == "|" and not openers
        )
        cwds = updated_cwd_states(
            command_tokens,
            cwds,
            separator,
            may_skip=may_skip,
            isolated=isolated_segment,
        )
        for closer in closers:
            expected = "(" if closer == ")" else "{"
            if not group_stack or group_stack[-1][0] != expected:
                continue
            (
                opener,
                inherited_cwds,
                group_may_skip,
                piped_from_left,
                outer_and_or_entry_cwds,
            ) = group_stack.pop()
            cwds = cwd_after_group_exit(
                opener,
                inherited_cwds,
                cwds,
                separator in {"|", "&"} or piped_from_left,
            )
            if group_may_skip:
                cwds = _unique_cwds((*inherited_cwds, *cwds))
            and_or_entry_cwds = outer_and_or_entry_cwds
        if separator == "&":
            cwds = cwd_after_async_list(and_or_entry_cwds, cwds)
        if separator in {";", "\n", "&"}:
            and_or_entry_cwds = cwds
        previous_separator = separator
    return actions


def find_actions(command: str) -> list[GitAction]:
    try:
        cwd = Path.cwd().resolve()
    except (OSError, RuntimeError):
        cwd = Path.cwd()
    actions = _find_actions_recursive(command, cwd, executable_seen=False)
    if not RAW_SEGMENT_PASS_ENABLED:
        return actions
    raw_actions = _raw_segment_pass(
        lambda: _find_actions_recursive(command, cwd, executable_seen=False)
    )
    for action in raw_actions:
        if action not in actions:
            actions.append(action)
    return actions


def commit_candidate_is_stable(action: GitAction, command: str) -> bool:
    """Reject commit argv/shell forms that can change or select candidate bytes."""
    if action.subcommand != "commit":
        return True
    if action.preceded_by_command:
        return False
    if "$(" in command or "`" in command or "<(" in command or ">(" in command:
        return False
    args = list(action.subcommand_args)
    options_with_values = {
        "-m", "--message", "--author", "--date", "--cleanup",
        "--trailer", "--fixup", "--squash",
    }
    benign_flags = {
        "-q", "--quiet", "-v", "--verbose", "-n", "--no-verify",
        "-s", "--signoff", "--no-edit", "-S", "--gpg-sign",
    }
    unsafe_flags = {
        "-a", "--all", "-i", "--include", "-o", "--only",
        "--amend", "--allow-empty", "--allow-empty-message",
        "-p", "--patch", "--interactive",
    }
    unsafe_options_with_values = {
        "-F", "--file", "-C", "--reuse-message", "-c", "--reedit-message",
    }
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            return False
        if token in unsafe_flags or token in unsafe_options_with_values or token.startswith((
            "--file=", "--reuse-message=", "--reedit-message=", "--fixup=",
            "--squash=", "--pathspec-from-file=", "--pathspec-file-nul"
        )):
            return False
        if token in benign_flags:
            index += 1
            continue
        if token in options_with_values:
            index += 2
            continue
        if token.startswith(("--message=", "--author=", "--date=", "--cleanup=", "--trailer=", "--gpg-sign=")):
            index += 1
            continue
        if token.startswith("-S") and token not in ("-S", "-S-"):
            index += 1
            continue
        if token.startswith("-"):
            return False
        return False
    return True


def is_index_mutating_action(action: GitAction) -> bool:
    if action.subcommand in {"add", "reset", "stash"}:
        return True
    option_args = list(action.subcommand_args)
    if "--" in option_args:
        option_args = option_args[: option_args.index("--")]
    if action.subcommand == "restore":
        return "--staged" in option_args or any(
            re.fullmatch(r"-[^-]*S[^-]*", token) is not None
            for token in option_args
        )
    if action.subcommand == "rm":
        return "--cached" in option_args
    return False


def action_environment(action: GitAction) -> dict[str, str]:
    environment = os.environ.copy()
    for key, value in action.assignments:
        if key in SAFE_GIT_ENV:
            environment[key] = expand_shell_path(value, action.shell_cwd)
    return environment


def run_action_git(
    action: GitAction,
    *arguments: str,
    text: bool = False,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *action.structural_globals, *arguments],
        cwd=action.shell_cwd,
        env=action_environment(action),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        check=False,
    )


def context_environment(context: RepoContext) -> dict[str, str]:
    """Pin every post-resolution Git consumer to one repository and index."""
    environment = context.git_env.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        environment.pop(key, None)
    environment["GIT_DIR"] = str(context.git_dir)
    environment["GIT_COMMON_DIR"] = str(context.common_dir)
    environment["GIT_INDEX_FILE"] = str(context.index_file)
    if not context.bare:
        environment["GIT_WORK_TREE"] = str(context.worktree_root)
    return environment


def run_context_git(
    context: RepoContext,
    *arguments: str,
    text: bool = False,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments],
        cwd=context.worktree_root,
        env=context_environment(context),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        check=False,
    )


def effective_git_cwd(action: GitAction) -> Path:
    """Return the directory Git sees after applying the action's -C options."""
    current = action.shell_cwd
    index = 0
    while index < len(action.structural_globals):
        token = action.structural_globals[index]
        if token == "-C" and index + 1 < len(action.structural_globals):
            value = action.structural_globals[index + 1]
            if value:
                candidate = Path(value)
                if not candidate.is_absolute():
                    candidate = current / candidate
                try:
                    current = candidate.resolve(strict=True)
                except (OSError, RuntimeError):
                    return current
            index += 2
            continue
        index += 1
    return current


def repo_context(action: GitAction) -> RepoContext | None:
    try:
        bare_result = run_action_git(
            action,
            "rev-parse",
            "--is-bare-repository",
            text=True,
        )
    except OSError:
        return None
    is_bare = bare_result.returncode == 0 and bare_result.stdout.strip() == "true"

    try:
        top_result = run_action_git(action, "rev-parse", "--show-toplevel", text=True)
    except OSError:
        return None
    if top_result.returncode == 0:
        try:
            worktree_root = Path(top_result.stdout.strip()).resolve(strict=True)
        except (OSError, RuntimeError):
            return None
    elif is_bare:
        try:
            worktree_root = effective_git_cwd(action).resolve(strict=True)
        except (OSError, RuntimeError):
            return None
    else:
        return None

    try:
        git_dir_result = run_action_git(
            action,
            "rev-parse",
            "--absolute-git-dir",
            text=True,
        )
        if git_dir_result.returncode != 0:
            git_dir_result = run_action_git(
                action,
                "rev-parse",
                "--git-dir",
                text=True,
            )
        index_result = run_action_git(
            action,
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "index",
            text=True,
        )
        if index_result.returncode != 0:
            index_result = run_action_git(
                action,
                "rev-parse",
                "--git-path",
                "index",
                text=True,
            )
    except OSError:
        return None
    if git_dir_result.returncode != 0 or index_result.returncode != 0:
        return None
    try:
        raw_git_dir = Path(git_dir_result.stdout.strip())
        if not raw_git_dir.is_absolute():
            raw_git_dir = effective_git_cwd(action) / raw_git_dir
        git_dir = raw_git_dir.resolve(strict=True)
        # An inherited alternate index need not exist yet (and its parent may
        # be created later), so canonicalize the selected pathname lexically.
        # Legacy `rev-parse --git-path index` already expresses a relative
        # result from Git's effective cwd (including any setup-time chdir).
        raw_index = Path(index_result.stdout.strip())
        if not raw_index.is_absolute():
            raw_index = effective_git_cwd(action) / raw_index
        index_file = Path(os.path.abspath(os.path.normpath(raw_index)))
    except (OSError, RuntimeError):
        return None

    try:
        common_result = run_action_git(
            action,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
            text=True,
        )
        absolute_common_dir = common_result.returncode == 0
        if not absolute_common_dir:
            # Git before 2.31 has no --path-format. Keep the guard portable by
            # resolving its traditional relative result against Git's -C cwd.
            common_result = run_action_git(
                action,
                "rev-parse",
                "--git-common-dir",
                text=True,
            )
    except OSError:
        return None
    if common_result.returncode != 0:
        return None
    common_dir = Path(common_result.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = effective_git_cwd(action) / common_dir
    try:
        common_dir = common_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return RepoContext(
        action=action,
        worktree_root=worktree_root,
        git_dir=git_dir,
        index_file=index_file,
        common_dir=common_dir,
        main_root=common_dir.parent,
        git_env=action_environment(action),
        bare=is_bare,
    )


def invoking_repo_context() -> RepoContext | None:
    """Resolve the hook's current Git context for non-Git CLI denials."""
    try:
        cwd = Path.cwd().resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return repo_context(
        GitAction(
            subcommand="commit",
            executable="forge-cli",
            shell_cwd=cwd,
            structural_globals=(),
            assignments=(),
            subcommand_args=(),
        )
    )


def redact_excerpt(command: str) -> str:
    redacted = re.sub(
        r"-----BEGIN [A-Z0-9 ]+-----.*?-----END [A-Z0-9 ]+-----",
        "[REDACTED PEM BLOCK]",
        command,
        flags=re.IGNORECASE | re.DOTALL,
    )
    redacted = re.sub(
        r"(?i)(\bbearer[ \t]+)[A-Za-z0-9._~+/=-]+",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(\b(?:[a-z][a-z0-9]*_)*(?:api[-_]?key|api[-_]?token|"
        r"access[-_]?token|bearer(?:[-_]?token)?|password|token)\b"
        r"(?:\s*[:=]\s*|\s+))(?:\"[^\"]*\"|'[^']*'|[^\s;&|]+)",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{8,}|"
        r"xox[baprs]-[A-Za-z0-9-]{8,}|(?:pk|sk)_(?:live|test)_[A-Za-z0-9]{8,})\b",
        "[REDACTED TOKEN]",
        redacted,
    )
    return re.sub(r"\s+", " ", redacted).strip()[:200]


def audit_block(
    context: RepoContext,
    executable: str,
    reason_code: str,
    command: str,
) -> None:
    audit_path = context.main_root / ".forge" / "tmp" / "halt-audit.log"
    safe_executable = re.sub(r"\s+", "_", executable)[:100]
    line = (
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} "
        f"executable={safe_executable} deny={reason_code} "
        f"excerpt={redact_excerpt(command)}\n"
    )
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            audit_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
            os.write(descriptor, line.encode("utf-8", errors="replace"))
        finally:
            os.close(descriptor)
    except OSError:
        pass


def emit_deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )
    sys.stdout.flush()


def audit_event_launch_failure(context: RepoContext) -> bool:
    """Count an advisory emitter launch failure without changing hook output."""
    audit_path = context.main_root / ".forge" / "tmp" / "halt-audit.log"
    payload = (
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} "
        "decision event append skipped (code event-append-launch-failed)\n"
    ).encode("utf-8")
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            audit_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
            if os.write(descriptor, payload) != len(payload):
                raise OSError("short audit write")
        finally:
            os.close(descriptor)
        return True
    except OSError:
        return False


def marker_matches_descriptor(marker: Path, descriptor: int) -> bool:
    """Return whether marker still names the inode opened by this event."""
    try:
        marker_stat = marker.stat(follow_symlinks=False)
        descriptor_stat = os.fstat(descriptor)
    except OSError:
        return False
    return (
        stat.S_ISREG(marker_stat.st_mode)
        and stat.S_ISREG(descriptor_stat.st_mode)
        and
        marker_stat.st_dev == descriptor_stat.st_dev
        and marker_stat.st_ino == descriptor_stat.st_ino
    )


def write_event_marker(descriptor: int, payload: bytes) -> bool:
    """Replace marker contents through its already-open, identity-stable FD."""
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short outcome-marker write")
        os.ftruncate(descriptor, len(payload))
        os.fsync(descriptor)
        return True
    except OSError:
        return False


def publish_event_failure_marker(marker: Path, payload: bytes) -> bool:
    """Create a separate exact terminal marker without reusing pending text."""
    failed_marker = marker.with_name(
        marker.name.replace("decision-event-pending.", "decision-event-failed.", 1)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(
            failed_marker,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short failure-marker write")
        os.fsync(descriptor)
        if not marker_matches_descriptor(failed_marker, descriptor):
            raise OSError("failure-marker identity changed")
        return True
    except OSError:
        if descriptor is not None and marker_matches_descriptor(
            failed_marker, descriptor
        ):
            try:
                failed_marker.unlink()
            except OSError:
                pass
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def preserve_event_failure_marker(
    marker: Path,
    descriptor: int,
    code: str,
) -> bool:
    """Leave one per-event diagnostic when detached emission cannot finish.

    The marker is populated before launch, so it remains a countable fallback
    even when the event stream and halt audit become unavailable together.
    """
    diagnostic = f"forge: decision event append skipped ({code})\n".encode("utf-8")
    outcome_written = write_event_marker(descriptor, diagnostic)
    failed_marker = marker.with_name(
        marker.name.replace("decision-event-pending.", "decision-event-failed.", 1)
    )
    if outcome_written:
        if marker_matches_descriptor(marker, descriptor):
            try:
                os.rename(marker, failed_marker)
                return True
            except OSError:
                # The still-named marker already contains the exact code.
                return True
        # The birth inode contains the exact code, but its original name was
        # substituted. Never mutate that pathname.
        return True

    # Do not rename unchanged outcome-unconfirmed text. Publish a fresh exact
    # terminal marker; if even that fails, retain the pending marker as an
    # honest, countable unknown outcome.
    published = publish_event_failure_marker(marker, diagnostic)
    if published and marker_matches_descriptor(marker, descriptor):
        try:
            marker.unlink()
        except OSError:
            pass
    return published


def create_event_pending_marker(context: RepoContext) -> tuple[Path, int] | None:
    pending_dir = context.main_root / ".forge" / "tmp"
    try:
        pending_dir.mkdir(parents=True, exist_ok=True)
        for _ in range(8):
            marker = pending_dir / (
                f"decision-event-pending.{os.getpid()}-{os.urandom(16).hex()}"
            )
            try:
                descriptor = os.open(
                    marker,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
            except FileExistsError:
                continue
            try:
                payload = (
                    "forge: decision event outcome pending "
                    "(code event-append-outcome-unconfirmed)\n"
                ).encode("utf-8")
                if os.write(descriptor, payload) != len(payload):
                    raise OSError("short pending-marker write")
                os.fsync(descriptor)
                if not marker_matches_descriptor(marker, descriptor):
                    raise OSError("pending-marker identity changed")
            except OSError:
                if marker_matches_descriptor(marker, descriptor):
                    try:
                        marker.unlink()
                    except OSError:
                        pass
                os.close(descriptor)
                raise
            return marker, descriptor
    except OSError:
        pass
    audit_event_launch_failure(context)
    return None


EVENT_EMITTER_WORKER = """
from pathlib import Path
import os
import stat
import subprocess
import sys

marker = Path(sys.argv[1])
marker_descriptor = int(sys.argv[2])
audit_path = Path(sys.argv[3])
audit_payload = sys.argv[4].encode("utf-8")
failed_marker = marker.with_name(
    marker.name.replace("decision-event-pending.", "decision-event-failed.", 1)
)
def marker_matches_descriptor():
    try:
        marker_stat = marker.stat(follow_symlinks=False)
        descriptor_stat = os.fstat(marker_descriptor)
    except OSError:
        return False
    return (
        stat.S_ISREG(marker_stat.st_mode)
        and stat.S_ISREG(descriptor_stat.st_mode)
        and
        marker_stat.st_dev == descriptor_stat.st_dev
        and marker_stat.st_ino == descriptor_stat.st_ino
    )

def write_marker(payload):
    try:
        os.lseek(marker_descriptor, 0, os.SEEK_SET)
        if os.write(marker_descriptor, payload) != len(payload):
            raise OSError("short outcome-marker write")
        os.ftruncate(marker_descriptor, len(payload))
        os.fsync(marker_descriptor)
        return True
    except OSError:
        return False

def publish_failure_marker(payload):
    descriptor = None
    try:
        descriptor = os.open(
            failed_marker,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short failure-marker write")
        os.fsync(descriptor)
        marker_stat = failed_marker.stat(follow_symlinks=False)
        descriptor_stat = os.fstat(descriptor)
        if not (
            stat.S_ISREG(marker_stat.st_mode)
            and stat.S_ISREG(descriptor_stat.st_mode)
            and marker_stat.st_dev == descriptor_stat.st_dev
            and marker_stat.st_ino == descriptor_stat.st_ino
        ):
            raise OSError("failure-marker identity changed")
        return True
    except OSError:
        if descriptor is not None:
            try:
                marker_stat = failed_marker.stat(follow_symlinks=False)
                descriptor_stat = os.fstat(descriptor)
                if (
                    marker_stat.st_dev == descriptor_stat.st_dev
                    and marker_stat.st_ino == descriptor_stat.st_ino
                ):
                    failed_marker.unlink()
            except OSError:
                pass
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)

try:
    try:
        result = subprocess.run(
            sys.argv[5:],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        diagnostic = result.stderr or b""
    except OSError:
        result = None
        diagnostic = b""
    diagnostic_offset = diagnostic.find(
        b"forge: decision event append skipped ("
    )
    emitter_failed = diagnostic_offset >= 0
    worker_failed = result is None or result.returncode != 0
    failed = emitter_failed or worker_failed
    if worker_failed and not emitter_failed:
        try:
            descriptor = os.open(
                audit_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
            )
            try:
                os.fchmod(descriptor, 0o600)
                if os.write(descriptor, audit_payload) != len(audit_payload):
                    raise OSError("short audit write")
            finally:
                os.close(descriptor)
        except OSError:
            pass
    if emitter_failed:
        diagnostic_end = diagnostic.find(b"\\n", diagnostic_offset)
        if diagnostic_end < 0:
            diagnostic_end = len(diagnostic)
        else:
            diagnostic_end += 1
        outcome_payload = diagnostic[diagnostic_offset:diagnostic_end]
    elif failed:
        outcome_payload = (
            "forge: decision event append skipped (event-append-launch-failed)\\n"
        ).encode("utf-8")
    else:
        outcome_payload = "forge: decision event appended\\n".encode("utf-8")
    outcome_written = write_marker(outcome_payload)
    if failed and outcome_written:
        if marker_matches_descriptor():
            try:
                os.rename(marker, failed_marker)
            except OSError:
                # The pending pathname already contains the exact failure.
                pass
    elif failed:
        # Never relabel unchanged outcome-unconfirmed text as an exact result.
        # Prefer a separately created exact marker; retain pending when every
        # durable exact-code destination is unavailable.
        published = publish_failure_marker(outcome_payload)
        if published and marker_matches_descriptor():
            try:
                marker.unlink()
            except OSError:
                pass
    elif outcome_written and marker_matches_descriptor():
        try:
            marker.unlink()
        except OSError:
            pass
    # If a success-marker update fails, retain outcome-unconfirmed. It is an
    # honest, countable fallback and must not be silently discarded.
except BaseException:
    # The pre-created pending marker deliberately remains outcome-unconfirmed.
    # A later operator/pruner can count this crash without mistaking it for success.
    raise
"""


def emit_decision_event(
    emitter: Path,
    context: RepoContext,
    *,
    event: str,
    candidate: str,
    policy_sha: str,
    reason: str,
) -> None:
    """Best-effort telemetry after the denial has already been delivered."""
    environment = context_environment(context)
    pending = create_event_pending_marker(context)
    if pending is None:
        return
    marker, marker_descriptor = pending
    launch_failure_payload = (
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} "
        "decision event append skipped (code event-append-launch-failed)\n"
    )
    try:
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                EVENT_EMITTER_WORKER,
                str(marker),
                str(marker_descriptor),
                str(context.main_root / ".forge" / "tmp" / "halt-audit.log"),
                launch_failure_payload,
                sys.executable,
                str(emitter),
                "--event",
                event,
                "--candidate",
                candidate,
                "--policy-sha",
                policy_sha,
                "--reason",
                reason,
                "--surface",
                "commit-guard",
            ],
            cwd=context.worktree_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            pass_fds=(marker_descriptor,),
            start_new_session=True,
        )
    except OSError:
        surfaced = preserve_event_failure_marker(
            marker, marker_descriptor, "event-append-launch-failed"
        )
        counted = audit_event_launch_failure(context)
        del surfaced, counted
    finally:
        os.close(marker_descriptor)


def staged_candidate(context: RepoContext) -> str:
    try:
        result = run_context_git(context, "diff", "--cached")
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return hashlib.sha256(result.stdout).hexdigest()


def head_policy_sha(context: RepoContext) -> str:
    try:
        result = run_context_git(context, "rev-parse", "HEAD", text=True)
    except OSError:
        return ""
    value = result.stdout.strip() if result.returncode == 0 else ""
    return value if COMMIT_SHA.fullmatch(value) is not None else ""


def run_halt_check(
    context: RepoContext, check_halt: Path, *, probe_only: bool
) -> tuple[int, str]:
    environment = context_environment(context)
    # check-halt.sh intentionally accepts only a scope. Supply the already
    # resolved repository and index identity via Git's standard environment.
    if probe_only:
        environment["FORGE_HALT_PROBE_ONLY"] = "1"
    else:
        environment.pop("FORGE_HALT_PROBE_ONLY", None)
    try:
        result = subprocess.run(
            ["bash", str(check_halt), "commit"],
            cwd=context.worktree_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError:
        return 0, ""
    return result.returncode, result.stderr


def halt_sentinel(context: RepoContext, check_halt: Path) -> str | None:
    status, stderr = run_halt_check(context, check_halt, probe_only=True)
    if status == 0:
        return None
    # Probe mode is intentionally silent, so resolve the sentinel name from
    # the shared main-checkout state without starting advisory event work.
    candidates = [context.main_root / "AGENT_HALT", context.main_root / "AGENT_HALT_commit"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.name
    match = HALT_MESSAGE.search(stderr)
    return match.group(1) if match is not None else None


def manifest_requires_marker(context: RepoContext) -> bool:
    try:
        result = run_context_git(
            context,
            "show",
            "HEAD:.forge-manifest",
        )
    except OSError:
        result = None
    if (
        result is not None
        and result.returncode == 0
        and HEAD_PLUGIN_REF_LINE.search(result.stdout) is not None
    ):
        return True

    if context.bare:
        return False
    manifest = context.worktree_root / ".forge-manifest"
    if not os.path.lexists(manifest):
        return False
    try:
        contents = manifest.read_bytes()
    except OSError:
        # A directory, broken link, or unreadable manifest is malformed rather
        # than an upstream manifest, so it remains fail-closed.
        return True
    is_upstream = (
        UPSTREAM_COMMIT_LINE.search(contents) is not None
        or UPSTREAM_REGION_LINE.search(contents) is not None
    )
    return not is_upstream


def committed_history_mutation_mode(context: RepoContext) -> str:
    """Classify DM-015 using only the invoking repository's committed HEAD."""
    try:
        result = run_context_git(context, "show", "HEAD:.forge-manifest")
    except OSError:
        return "non-forge"
    if result.returncode != 0:
        return "non-forge"
    raw = result.stdout
    if HEAD_PLUGIN_REF_LINE.search(raw) is None:
        if (
            UPSTREAM_COMMIT_LINE.search(raw) is not None
            or UPSTREAM_REGION_LINE.search(raw) is not None
        ):
            return "upstream"
        return "non-forge"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "invalid"
    if not text.endswith("\n") or "\r" in text or "\x00" in text:
        return "invalid"
    lines = text[:-1].split("\n")
    history_rows: list[tuple[int, str]] = []
    suspicious_history_row = False
    for index, line in enumerate(lines):
        field = line.split(":", 1)[0].strip(" \t")
        if field == "history_mutation_mode":
            history_rows.append((index, line))
        elif line.lstrip(" \t").startswith("history_mutation_mode"):
            suspicious_history_row = True
    if suspicious_history_row:
        return "invalid"
    if not history_rows:
        return "plugin-mode-missing"
    if len(history_rows) != 1:
        return "invalid"
    row_index, row = history_rows[0]
    if row not in {
        "history_mutation_mode: legacy-v1",
        "history_mutation_mode: forge-verbs-v1",
    }:
        return "invalid"
    init_rows = [
        index
        for index, line in enumerate(lines)
        if line in {"init_completed: true", "init_completed: false"}
    ]
    if len(init_rows) != 1 or row_index != init_rows[0] + 1:
        return "invalid"
    if any(
        line.startswith("region: ") and index < row_index
        for index, line in enumerate(lines)
    ):
        return "invalid"
    return row.split(": ", 1)[1]


def policy_region(policy: bytes, name: str) -> bytes | None:
    """Extract one complete committed policy region, including its delimiters."""
    begin = f"<!-- FORGE:REGION {name} BEGIN -->".encode()
    end = f"<!-- FORGE:REGION {name} END -->".encode()
    if policy.count(begin) != 1 or policy.count(end) != 1:
        return None
    start = policy.find(begin)
    finish = policy.find(end, start + len(begin))
    if finish < 0:
        return None
    return policy[start : finish + len(end)]


def committed_policy(context: RepoContext, revision: str) -> bytes | None:
    try:
        result = run_context_git(context, "show", f"{revision}:forge-project.md")
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def policy_drift(context: RepoContext, revision: str) -> bool:
    """Authenticate a historical policy and compare its enforcement regions."""
    if COMMIT_SHA.fullmatch(revision) is None:
        return True
    try:
        resolved = run_context_git(
            context,
            "rev-parse",
            "--verify",
            f"{revision}^{{commit}}",
            text=True,
        )
        ancestor = run_context_git(
            context,
            "merge-base",
            "--is-ancestor",
            revision,
            "HEAD",
        )
    except OSError:
        return True
    if (
        resolved.returncode != 0
        or resolved.stdout.strip() != revision
        or ancestor.returncode != 0
    ):
        return True
    current = committed_policy(context, "HEAD")
    historical = committed_policy(context, revision)
    if current is None or historical is None:
        return True
    for name in ("risk-tiers", "trigger-paths", "file-categories"):
        current_region = policy_region(current, name)
        historical_region = policy_region(historical, name)
        if name == "trigger-paths" and current_region is None and historical_region is None:
            continue
        if current_region is None or historical_region is None:
            return True
        if current_region != historical_region:
            return True
    return False


def classifier_eligible(context: RepoContext, revision: str, classifier: Path) -> bool:
    """Independently derive fast eligibility for the exact staged diff."""
    environment = context_environment(context)
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(classifier),
                "--repo",
                str(context.worktree_root),
                "--policy-sha",
                revision,
                "--staged",
                "--declared-tier",
                "fast",
                "--require-effective",
                "fast",
            ],
            cwd=context.worktree_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def marker_failure(
    context: RepoContext,
    classifier: Path,
    candidate: str,
) -> str | None:
    marker = context.main_root / ".forge" / "tmp" / "authorized" / candidate
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return "marker missing"
    except (OSError, UnicodeError):
        return "marker malformed"

    if len(lines) not in (2, 3, 4):
        return "marker malformed"
    if HASH.fullmatch(lines[0]) is None:
        return "marker malformed"
    if len(lines) == 3 and lines[2] != "skip: user-directed":
        return "marker malformed"
    policy_sha: str | None = None
    if len(lines) == 4:
        if lines[2] != "tier: fast" or not lines[3].startswith("policy: "):
            return "marker malformed"
        policy_sha = lines[3][len("policy: ") :]
        if COMMIT_SHA.fullmatch(policy_sha) is None:
            return "marker malformed"
    try:
        reviewed_at = datetime.strptime(lines[1], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return "marker malformed"
    age_seconds = (datetime.now(timezone.utc) - reviewed_at).total_seconds()
    # More than two minutes ahead is malformed; smaller skew remains acceptable.
    if age_seconds < -120:
        return "marker malformed"
    if age_seconds > 1800:
        return "marker stale"

    if candidate != lines[0]:
        return "marker hash mismatch"
    if policy_sha is None:
        return None
    if policy_drift(context, policy_sha):
        return "fast-path policy drift"
    if not classifier_eligible(context, policy_sha, classifier):
        return "fast-path eligibility drift"
    return None


def sweep_stale_markers(context: RepoContext) -> None:
    """Best-effort cleanup after the invoking candidate has been validated."""
    marker_dir = context.main_root / ".forge" / "tmp" / "authorized"
    try:
        markers = list(marker_dir.iterdir())
    except OSError:
        return

    now = datetime.now(timezone.utc)
    for marker in markers:
        if HASH.fullmatch(marker.name) is None:
            continue
        try:
            lines = marker.read_text(encoding="utf-8").splitlines()
            reviewed_at = datetime.strptime(
                lines[1], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
        except (IndexError, OSError, UnicodeError, ValueError):
            continue
        if (now - reviewed_at).total_seconds() <= 1800:
            continue
        try:
            marker.unlink()
        except OSError:
            pass


def _chain_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _read_chain_state(directory: int, name: str) -> dict[str, object] | None:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory,
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_size > CHAIN_STATE_MAX_BYTES
        ):
            return None
        chunks: list[bytes] = []
        byte_count = 0
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            byte_count += len(chunk)
            if byte_count > CHAIN_STATE_MAX_BYTES:
                return None
            chunks.append(chunk)
        loaded = json.loads(b"".join(chunks).decode("utf-8"))
    except (MemoryError, OSError, RecursionError, UnicodeError, json.JSONDecodeError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)

    chain_id = name[:-5]
    if not isinstance(loaded, dict) or set(loaded) != CHAIN_STATE_KEYS:
        return None
    if (
        loaded.get("schema") != CHAIN_SCHEMA
        or loaded.get("kind") != CHAIN_KIND
        or loaded.get("chain_id") != chain_id
        or CHAIN_ID.fullmatch(chain_id) is None
        or loaded.get("state") not in CHAIN_STATES
    ):
        return None
    if not isinstance(loaded.get("paths"), list) or not all(
        isinstance(item, str) for item in loaded["paths"]
    ):
        return None
    if any(not isinstance(loaded.get(key), dict) for key in CHAIN_OBJECT_KEYS):
        return None
    if any(
        _chain_timestamp(loaded.get(key)) is None
        for key in ("created_at", "last_event_at", "inactive_after")
    ):
        return None
    candidate = loaded["candidate"].get("sha256")
    if candidate is not None and (
        not isinstance(candidate, str) or HASH.fullmatch(candidate) is None
    ):
        return None
    return loaded


def _chain_states(context: RepoContext) -> list[dict[str, object]]:
    common: int | None = None
    forge: int | None = None
    directory: int | None = None
    try:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        common = os.open(context.main_root, flags)
        forge = os.open(".forge", flags, dir_fd=common)
        directory = os.open("chains", flags, dir_fd=forge)
        for descriptor in (common, forge, directory):
            opened = os.fstat(descriptor)
            if not stat.S_ISDIR(opened.st_mode) or opened.st_uid != os.geteuid():
                return []
        names = sorted(os.listdir(directory))
        states: list[dict[str, object]] = []
        for name in names:
            if not name.endswith(".json") or CHAIN_ID.fullmatch(name[:-5]) is None:
                continue
            state = _read_chain_state(directory, name)
            if state is not None:
                states.append(state)
        return states
    except OSError:
        return []
    finally:
        if directory is not None:
            os.close(directory)
        if forge is not None:
            os.close(forge)
        if common is not None:
            os.close(common)


def _live_chain_states(context: RepoContext) -> list[dict[str, object]]:
    now = datetime.now(timezone.utc)
    worktree_root = str(context.worktree_root)
    states: list[dict[str, object]] = []
    for state in _chain_states(context):
        if state["state"] in CHAIN_TERMINAL_STATES:
            continue
        inactive_after = _chain_timestamp(state["inactive_after"])
        if inactive_after is None or now >= inactive_after:
            continue
        staging = state["staging"]
        if staging.get("worktree_root") != worktree_root:
            continue
        states.append(state)
    return states


def chain_authorizes_commit(context: RepoContext, candidate: str) -> bool:
    if HASH.fullmatch(candidate) is None:
        return False
    now = datetime.now(timezone.utc)
    for state in _live_chain_states(context):
        if state["state"] != "authorized":
            continue
        candidate_record = state["candidate"]
        if candidate_record.get("sha256") != candidate:
            continue
        authorization = state["authorization"]
        if set(authorization) != AUTHORIZATION_KEYS:
            continue
        token = authorization.get("token")
        if not isinstance(token, str) or CHAIN_TOKEN.fullmatch(token) is None:
            continue
        if authorization.get("consumed") is not False:
            continue
        if authorization.get("consumed_at") is not None:
            continue
        if authorization.get("candidate") != candidate:
            continue
        issued_at = _chain_timestamp(authorization.get("issued_at"))
        expires_at = _chain_timestamp(authorization.get("expires_at"))
        if issued_at is None or expires_at is None:
            continue
        try:
            derived_expiry = issued_at + timedelta(minutes=30)
        except OverflowError:
            continue
        if now < issued_at or expires_at != derived_expiry or now >= derived_expiry:
            continue
        return True
    return False


def foreign_live_chain(context: RepoContext) -> dict[str, object] | None:
    invoking_session = os.environ.get("CLAUDE_SESSION_ID", "")
    if not invoking_session:
        return None
    for state in _live_chain_states(context):
        session_identity = state["staging"].get("session_identity")
        if (
            isinstance(session_identity, str)
            and session_identity
            and session_identity != invoking_session
        ):
            return state
    return None


ResolvedCommand = tuple[
    list[GitAction],
    str,
    list[tuple[GitAction, "RepoContext | None"]],
    dict[tuple[object, ...], str],
    dict[tuple[object, ...], str | None],
]


def _resolve_command(command: str, check_halt: Path) -> ResolvedCommand:
    """Parse, then resolve every action's context, mode, and halt probe once."""
    actions = find_actions(command)
    cli_class = classify_forge_cli_invocation(command)
    contexts = [(action, resolve_repo_context(action)) for action in actions]
    modes: dict[tuple[object, ...], str] = {}
    sentinels: dict[tuple[object, ...], str | None] = {}
    for action, context in contexts:
        if context is None or action.subcommand not in {"commit", "push"}:
            continue
        identity = _context_identity(context)
        if identity not in sentinels:
            sentinels[identity] = resolve_halt_sentinel(context, check_halt)
        if identity not in modes:
            modes[identity] = resolve_history_mutation_mode(context)
    return actions, cli_class, contexts, modes, sentinels


def _classify_command_bounded(
    command: str, check_halt: Path | None = None
) -> ResolvedCommand | tuple[list[GitAction], str]:
    """Run parsing and per-action resolution under the fail-closed bounds.

    Without ``check_halt`` only the parse phase runs (the in-process test
    surface); with it, context, mode, and halt resolution are covered by the
    same budget so a flood of distinct actions cannot outrun the hook deadline.
    """
    global _nesting_depth
    _nesting_depth = 0
    _reset_resolution_memos()
    budget = PARSE_TIME_BUDGET_SECONDS
    armed = False
    previous_handler: object = None

    def expired(_signum: int, _frame: object) -> None:
        raise GuardInputBoundExceeded("time")

    if budget and budget > 0 and hasattr(signal, "setitimer"):
        previous_handler = signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, float(budget))
        armed = True
    try:
        if check_halt is None:
            return find_actions(command), classify_forge_cli_invocation(command)
        return _resolve_command(command, check_halt)
    finally:
        if armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)


def _failsafe_deny(command: str, kind: str, emitter: Path, failure: str) -> int:
    """Deny an unclassifiable command on both channels with exit 2."""
    reason = GUARD_FAILSAFE_DENIALS[kind]
    if kind == "internal":
        reason = reason.format(failure=failure or "unknown")
    emit_deny(reason)
    reason_code = GUARD_FAILSAFE_REASON_CODES[kind]
    context = invoking_repo_context()
    if context is not None:
        audit_block(context, "guard", reason_code, command)
        emit_decision_event(
            emitter,
            context,
            event="guard_deny",
            candidate=staged_candidate(context),
            policy_sha=head_policy_sha(context),
            reason=reason_code,
        )
    sys.stderr.write(f"{reason}\n")
    sys.stderr.flush()
    return 2


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeError, OSError):
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    command = tool_input.get("command")
    if not isinstance(command, str):
        return 0

    check_halt = Path(sys.argv[1])
    classifier = Path(sys.argv[2])
    emitter = Path(sys.argv[3])
    v2_corpus = Path(sys.argv[4])
    try:
        _actions, cli_class, contexts, modes, sentinels = _classify_command_bounded(
            command, check_halt
        )
    except GuardInputBoundExceeded as exc:
        return _failsafe_deny(command, exc.kind, emitter, "")
    except Exception as exc:  # fail closed on any parser or resolution failure
        return _failsafe_deny(command, "internal", emitter, _failsafe_failure_name(exc))
    v2_denials: dict[str, str] | None = None
    v2_corpus_failed = False

    def v2_denial(expectation: str) -> str:
        nonlocal v2_corpus_failed, v2_denials
        if v2_denials is None:
            try:
                v2_denials = load_v2_denials(v2_corpus)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                v2_denials = {}
                v2_corpus_failed = True
        reason = v2_denials.get(expectation)
        if reason is None:
            v2_corpus_failed = True
            return V2_DENIAL_FALLBACKS[expectation]
        return reason

    def v2_status(reason: str) -> int:
        if not v2_corpus_failed:
            return 0
        # Exit 2 is itself a blocking hook outcome. Retain the applicable exact
        # FR-239 literal on both output channels even when corpus bytes are bad.
        sys.stderr.write(f"{reason}\n")
        sys.stderr.flush()
        return 2

    # Halt is the first authority check across every relevant segment.
    for action, context in contexts:
        if action.subcommand not in {"commit", "push"}:
            continue
        if context is None:
            continue
        sentinel = sentinels.get(_context_identity(context))
        if sentinel is None:
            continue
        reason = f"forge: operator halt engaged ({sentinel})"
        audit_block(context, action.executable, "operator-halt", command)
        emit_deny(reason)
        # The deny JSON above is flushed before either advisory event append.
        # Record the guard denial separately from check-halt's halt metric.
        emit_decision_event(
            emitter,
            context,
            event="guard_deny",
            candidate=staged_candidate(context),
            policy_sha=head_policy_sha(context),
            reason="operator-halt",
        )
        # Preserve the primary hook decision while check-halt records its own
        # audit and halt_event append.
        run_halt_check(context, check_halt, probe_only=False)
        return 0

    operator_context: RepoContext | None = None
    if cli_class.startswith("deny-"):
        operator_context = invoking_repo_context()
        if operator_context is not None:
            sentinel = halt_sentinel(operator_context, check_halt)
            if sentinel is not None:
                reason = f"forge: operator halt engaged ({sentinel})"
                audit_block(operator_context, "forge-cli", "operator-halt", command)
                emit_deny(reason)
                emit_decision_event(
                    emitter,
                    operator_context,
                    event="guard_deny",
                    candidate=staged_candidate(operator_context),
                    policy_sha=head_policy_sha(operator_context),
                    reason="operator-halt",
                )
                run_halt_check(operator_context, check_halt, probe_only=False)
                return 0
    if cli_class in FORGE_CLI_DENIALS:
        emit_deny(FORGE_CLI_DENIALS[cli_class])
        context = operator_context
        if context is not None:
            reason_code = f"operator-verb-{cli_class[len('deny-'):]}"
            audit_block(context, "forge-cli", reason_code, command)
            emit_decision_event(
                emitter,
                context,
                event="guard_deny",
                candidate=staged_candidate(context),
                policy_sha=head_policy_sha(context),
                reason=reason_code,
            )
        return 0
    if cli_class == "deny-merge-approve":
        reason = v2_denial(cli_class)
        emit_deny(reason)
        context = operator_context
        if context is not None:
            audit_block(context, "forge-cli", "operator-verb-merge-approve", command)
            emit_decision_event(
                emitter,
                context,
                event="guard_deny",
                candidate=staged_candidate(context),
                policy_sha=head_policy_sha(context),
                reason="operator-verb-merge-approve",
            )
        return v2_status(reason)

    activation_contexts = [
        (action, context, modes[_context_identity(context)])
        for action, context in contexts
        if context is not None and action.subcommand in {"commit", "push"}
    ]
    for action, context, mode in activation_contexts:
        if mode != "invalid":
            continue
        reason_code = "activation-policy-invalid"
        audit_block(context, action.executable, reason_code, command)
        reason = v2_denial("deny-invalid-mode")
        emit_deny(reason)
        emit_decision_event(
            emitter,
            context,
            event="guard_deny",
            candidate=staged_candidate(context),
            policy_sha=head_policy_sha(context),
            reason=reason_code,
        )
        return v2_status(reason)
    for action, context, mode in activation_contexts:
        if mode != "forge-verbs-v1":
            continue
        expectation = f"deny-raw-{action.subcommand}"
        reason_code = f"raw-git-{action.subcommand}-denied"
        audit_block(context, action.executable, reason_code, command)
        reason = v2_denial(expectation)
        emit_deny(reason)
        emit_decision_event(
            emitter,
            context,
            event="guard_deny",
            candidate=staged_candidate(context),
            policy_sha=head_policy_sha(context),
            reason=reason_code,
        )
        return v2_status(reason)

    for action, context in contexts:
        if context is None or not is_index_mutating_action(action):
            continue
        chain = foreign_live_chain(context)
        if chain is None:
            continue
        chain_id = str(chain["chain_id"])
        reason = (
            "forge: index verb denied — live commit chain "
            f"{chain_id} owns this worktree index; use the chain verbs or abort it"
        )
        audit_block(context, action.executable, "foreign-chain-index-owner", command)
        emit_deny(reason)
        emit_decision_event(
            emitter,
            context,
            event="guard_deny",
            candidate=staged_candidate(context),
            policy_sha=head_policy_sha(context),
            reason="foreign-chain-index-owner",
        )
        return 0

    for action, context in contexts:
        if action.subcommand != "commit" or context is None:
            continue
        if not manifest_requires_marker(context):
            continue
        candidate = staged_candidate(context)
        marker_state = (
            marker_failure(context, classifier, candidate)
            if candidate
            else "marker hash mismatch"
        )
        chain_authorized = chain_authorizes_commit(context, candidate)
        # FR-090 requires the current candidate's state to be determined before
        # the age sweep, so a present stale marker retains its exact denial.
        sweep_stale_markers(context)
        failure = (
            marker_state
            if marker_state is not None and not chain_authorized
            else (None if commit_candidate_is_stable(action, command) else "marker hash mismatch")
        )
        if failure is None:
            continue
        reason = f"forge: commit not authorized — run /forge:commit ({failure})"
        audit_block(context, action.executable, failure.replace(" ", "-"), command)
        emit_deny(reason)
        if failure == "fast-path policy drift":
            event = "fast_denied_policy"
            event_reason = "fast-path-policy-drift"
        elif failure == "fast-path eligibility drift":
            event = "fast_denied_eligibility"
            event_reason = "fast-path-eligibility-drift"
        else:
            event = "guard_deny"
            event_reason = failure.replace(" ", "-")
        emit_decision_event(
            emitter,
            context,
            event=event,
            candidate=staged_candidate(context),
            policy_sha=head_policy_sha(context),
            reason=event_reason,
        )
        return 0
    return 0


try:
    raise SystemExit(main())
except BrokenPipeError:
    raise SystemExit(0)
except Exception as exc:  # fail closed: never a bare traceback with exit 1
    failsafe_reason = GUARD_FAILSAFE_DENIALS["internal"].format(
        failure=_failsafe_failure_name(exc)
    )
    try:
        emit_deny(failsafe_reason)
    except Exception:
        pass
    sys.stderr.write(f"{failsafe_reason}\n")
    raise SystemExit(2)
PY

exec python3 -c "$python_code" \
    "$script_dir/check-halt.sh" \
    "$script_dir/risk_tier.py" \
    "$script_dir/emit-decision-event.py" \
    "$script_dir/../../system/fr223/hook-argv-cases-v2.json"
