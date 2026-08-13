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
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
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


def split_segments(command: str) -> list[tuple[str, str | None]]:
    """Split on requested shell operators without splitting quoted text."""
    segments: list[tuple[str, str | None]] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0

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
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
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

    if index >= len(tokens) or tokens[index] not in ("commit", "push"):
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
    if separator == "|" or not tokens or tokens[0] != "cd":
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


def find_actions(command: str) -> list[GitAction]:
    actions: list[GitAction] = []
    cwd = Path.cwd().resolve()
    executable_seen = False
    for segment, separator in split_segments(command):
        try:
            tokens = shlex.split(segment, comments=False, posix=True)
        except ValueError:
            continue
        command_tokens = without_redirections(tokens)
        for candidate_tokens in (tokens, command_tokens):
            action = parse_action(candidate_tokens, cwd)
            if action is not None and action not in actions:
                actions.append(dataclasses.replace(action, preceded_by_command=executable_seen))
        if command_tokens and command_tokens[0] != "cd":
            executable_seen = True
        cwd = updated_cwd(command_tokens, cwd, separator)
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
    try:
        subprocess.run(
            [
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
            check=False,
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        pass


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


def marker_failure(context: RepoContext, classifier: Path) -> str | None:
    marker = context.main_root / ".forge" / "tmp" / "commit-authorized"
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

    try:
        diff = run_context_git(context, "diff", "--cached")
    except OSError:
        return "marker hash mismatch"
    if diff.returncode != 0:
        return "marker hash mismatch"
    if hashlib.sha256(diff.stdout).hexdigest() != lines[0]:
        return "marker hash mismatch"
    if policy_sha is None:
        return None
    if policy_drift(context, policy_sha):
        return "fast-path policy drift"
    if not classifier_eligible(context, policy_sha, classifier):
        return "fast-path eligibility drift"
    return None


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

    actions = find_actions(command)
    contexts = [(action, repo_context(action)) for action in actions]
    check_halt = Path(sys.argv[1])
    classifier = Path(sys.argv[2])
    emitter = Path(sys.argv[3])

    # Halt is the first authority check across every relevant segment.
    for action, context in contexts:
        if context is None:
            continue
        sentinel = halt_sentinel(context, check_halt)
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

    for action, context in contexts:
        if action.subcommand != "commit" or context is None:
            continue
        if not manifest_requires_marker(context):
            continue
        marker_state = marker_failure(context, classifier)
        failure = (
            marker_state
            if marker_state is not None
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
PY

exec python3 -c "$python_code" \
    "$script_dir/check-halt.sh" \
    "$script_dir/risk_tier.py" \
    "$script_dir/emit-decision-event.py"
