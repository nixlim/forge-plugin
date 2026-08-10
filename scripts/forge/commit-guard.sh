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
HALT_MESSAGE = re.compile(r"forge: operator halt engaged \(([^)]+)\)")
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


@dataclass(frozen=True)
class RepoContext:
    action: GitAction
    worktree_root: Path
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
        elif char in ";|\n":
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
    for segment, separator in split_segments(command):
        try:
            tokens = shlex.split(segment, comments=False, posix=True)
        except ValueError:
            continue
        command_tokens = without_redirections(tokens)
        for candidate_tokens in (tokens, command_tokens):
            action = parse_action(candidate_tokens, cwd)
            if action is not None and action not in actions:
                actions.append(action)
        cwd = updated_cwd(command_tokens, cwd, separator)
    return actions


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


def halt_sentinel(context: RepoContext, check_halt: Path) -> str | None:
    environment = os.environ.copy()
    # check-halt.sh intentionally accepts only a scope. Supply the already
    # resolved repository identity via Git's standard environment so explicit
    # --git-dir/--work-tree invocations retain the same main-checkout root.
    environment["GIT_DIR"] = str(context.common_dir)
    environment["GIT_COMMON_DIR"] = str(context.common_dir)
    if context.bare:
        environment.pop("GIT_WORK_TREE", None)
    else:
        environment["GIT_WORK_TREE"] = str(context.worktree_root)
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
        return None
    if result.returncode == 0:
        return None
    match = HALT_MESSAGE.search(result.stderr)
    return match.group(1) if match is not None else None


def manifest_requires_marker(context: RepoContext) -> bool:
    if not context.bare and os.path.lexists(context.worktree_root / ".forge-manifest"):
        return True
    try:
        result = run_action_git(
            context.action,
            "cat-file",
            "-e",
            "HEAD:.forge-manifest",
        )
    except OSError:
        return False
    return result.returncode == 0


def marker_failure(context: RepoContext) -> str | None:
    marker = context.main_root / ".forge" / "tmp" / "commit-authorized"
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return "missing"
    except (OSError, UnicodeError):
        return "malformed"

    if len(lines) not in (2, 3):
        return "malformed"
    if HASH.fullmatch(lines[0]) is None:
        return "malformed"
    if len(lines) == 3 and lines[2] != "skip: user-directed":
        return "malformed"
    try:
        reviewed_at = datetime.strptime(lines[1], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return "malformed"
    age_seconds = (datetime.now(timezone.utc) - reviewed_at).total_seconds()
    # More than two minutes ahead is malformed; smaller skew remains acceptable.
    if age_seconds < -120:
        return "malformed"
    if age_seconds > 1800:
        return "stale"

    try:
        diff = run_action_git(context.action, "diff", "--cached")
    except OSError:
        return "hash mismatch"
    if diff.returncode != 0:
        return "hash mismatch"
    if hashlib.sha256(diff.stdout).hexdigest() != lines[0]:
        return "hash mismatch"
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
        return 0

    for action, context in contexts:
        if action.subcommand != "commit" or context is None:
            continue
        if not manifest_requires_marker(context):
            continue
        failure = marker_failure(context)
        if failure is None:
            continue
        reason = f"forge: commit not authorized — run /forge:commit (marker {failure})"
        audit_block(context, action.executable, f"marker-{failure.replace(' ', '-')}", command)
        emit_deny(reason)
        return 0
    return 0


try:
    raise SystemExit(main())
except BrokenPipeError:
    raise SystemExit(0)
PY

exec python3 -c "$python_code" "$script_dir/check-halt.sh"
