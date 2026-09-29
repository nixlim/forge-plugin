"""Request-free primitives shared by the typed launch verb modules."""

from __future__ import annotations

import dataclasses
import errno
import fcntl
import json
import os
import re
import secrets
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import route_config
from route_config_git import owner_only_writable

from forge_cli import chain_core, policy, runtime
from forge_cli.engine import _cli_options, _review_attempt, _review_lane_api, _review_launch
from forge_cli.engine._core import _run_halt
from forge_cli.engine._state import CLAUDE_EXECUTABLE as CLAUDE_EXECUTABLE
from forge_cli.engine._state import CODEX_EXECUTABLE as CODEX_EXECUTABLE
from forge_cli.envelope import (
    REVISION9_OUTPUT_SCHEMA,
    Outcome,
    ReasonCode,
    Refusal,
    V2ReasonCode,
)
from forge_cli.policy import sha256_bytes

BRIEF_LIMIT_BYTES = 1024 * 1024
ROLE_BODY_LIMIT_BYTES = 1024 * 1024
PROMPT_LIMIT_BYTES = 4 * BRIEF_LIMIT_BYTES
RECORD_LIMIT_BYTES = 65_536
GIT_LIMIT_BYTES = 1024 * 1024
GIT_TIMEOUT_SECONDS = 30
GIT_PROBE_CAP_BYTES = 4096
MAX_AGENT_NUMBER = 99
LAUNCH_MARKER_SCHEMA = "forge-launch-marker/1"
IDEMPOTENCY_SCHEMA = "forge-launch-idempotency/1"
GLOBAL_HALT_SCOPE = ""
MARKER_NAME = "launch.json"
PID_NAME = "pid"
ATTEMPT_PATTERN = re.compile(r"attempt-[0-9a-f]{16}\Z")
EXECUTION_PATTERN = re.compile(r"execution-[0-9]{2}\Z")
OBJECT_ID_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
LAUNCH_ROLES = frozenset({"implementer", "plan"})
LAUNCH_PROVIDERS = frozenset({"codex", "claude"})
EVENT_SOURCES = {"codex": "exec", "claude": "claude"}
CLAUDE_IMPLEMENTER_TOOLS = "Read,Write,Edit,Bash,Grep,Glob"
CLAUDE_PLAN_TOOLS = "Read,Grep,Glob"
CONTEXT_SEPARATOR = b"--- committed agent-project-context ---\n"
GOTCHAS_SEPARATOR = b"\n--- committed gotchas (optional; empty when absent) ---\n"
ASSIGNMENT_SEPARATOR = b"\n--- task assignment ---\n"
LAUNCH_LEAVES = {
    "prompt": "prompt.md",
    "events": "events.jsonl",
    "stderr": "stderr.log",
    "capture": "handoff.md",
    "staging": "handoff.staging",
}
MARKER_STRING_KEYS = frozenset(
    {
        "schema",
        "run_id",
        "task",
        "agent",
        "execution",
        "attempt",
        "role",
        "provider",
        "model",
        "effort",
        "sandbox",
        "route_source",
        "route_sha256",
        "worktree",
        "head",
        "plugin_root",
        "role_body_path",
        "role_body_sha256",
        "argv_digest",
        "prompt_digest",
        "launcher_argv_digest",
        "requested_at",
    }
)
MARKER_NONSTRING_KEYS = frozenset(
    {
        "timeout_seconds",
        "environment_names",
        "omitted_short",
        "collected_at",
        "collected_status",
    }
)
MARKER_KEYS = MARKER_STRING_KEYS | MARKER_NONSTRING_KEYS
RECORD_BOUND_FIELDS = (
    "agent",
    "task",
    "execution",
    "role",
    "provider",
    "model",
    "effort",
    "sandbox",
    "route_source",
    "route_sha256",
    "worktree",
    "head",
)
WRAPPER_BINDING_FIELDS = (
    "attempt",
    "provider",
    "route_source",
    "route_sha256",
    "sandbox",
    "argv_digest",
    "prompt_digest",
    "environment_names",
    "omitted_short",
)

BRIEF_REFUSAL_MESSAGE = (
    "forge: launch refused — brief must be a canonical absolute owner-owned regular "
    "UTF-8 file writable only by its owner or owner-private group, with no NUL byte "
    "and size at most 1 MiB"
)
BRIEF_PATH_REFUSAL_MESSAGE = (
    "forge: launch refused — brief path is not canonical; pass its absolute realpath"
)
BRIEF_PATH_BINDING_REFUSAL_MESSAGE = (
    "forge: launch refused — opened brief path could not be verified against the "
    "checked canonical path"
)


class GitOutputLimitError(OSError):
    """A bounded Git read exceeded the caller's output budget."""


@dataclasses.dataclass(frozen=True)
class PromptRequest:
    role: str
    provider: str
    worktree: Path
    head: str
    brief: Path


@dataclasses.dataclass(frozen=True)
class PromptMaterial:
    prompt: bytes
    plugin_root: Path
    role_body_path: Path
    role_body_sha256: str


@dataclasses.dataclass(frozen=True)
class RunState:
    """Hold the lazily loaded coordination modules and one scanned run."""

    batch: Any
    builders: Any
    journal: Any
    repository: Path
    run_dir: Path
    state: Any


@dataclasses.dataclass(frozen=True)
class CompletionResult:
    """Map a bound wrapper completion to one journal result."""

    status: str
    summary: str
    files_changed: tuple[str, ...]
    caveats: tuple[str, ...]
    handoff: str | None
    message: str


@dataclasses.dataclass(frozen=True)
class LaunchPaths:
    run_dir: Path
    agent: str
    execution: str

    def __post_init__(self) -> None:
        if not valid_component(self.agent) or not valid_component(self.execution):
            raise ValueError("launch owner path has an unsafe component")

    @property
    def relative(self) -> Path:
        return Path(self.agent) / self.execution

    @property
    def directory(self) -> Path:
        return self.run_dir / self.relative

    def leaf(self, name: str) -> Path:
        return self.directory / name

    def reference(self, name: str) -> str:
        return (self.relative / name).as_posix()


def valid_component(value: object) -> bool:
    return (
        isinstance(value, str)
        and value not in {"", ".", ".."}
        and "/" not in value
        and "\\" not in value
    )


def require_no_halt(ctx: chain_core.CommandContext) -> None:
    """Translate the global halt checkpoint into the Revision-9 reason vocabulary."""

    try:
        # The empty scope asks check-halt.sh for the global sentinel only.
        _run_halt(ctx, scope=GLOBAL_HALT_SCOPE)
    except Refusal as exc:
        if exc.reason_code is not ReasonCode.HALT_ENGAGED:
            raise
        raise Refusal(
            V2ReasonCode.HALT_ENGAGED,
            exc.message,
            expected=exc.expected,
            observed=exc.observed,
            remediation=exc.remediation,
            next_required_step=exc.next_required_step,
        ) from exc


def require_run_id(ctx: chain_core.CommandContext) -> str:
    """Return the explicit launch run identity or raise the shared refusal."""

    run_id = ctx.options.run_id
    if run_id is None:
        raise Refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            _cli_options.LAUNCH_RUN_ID_REQUIRED,
        )
    return run_id


def run_state(ctx: chain_core.CommandContext, run_id: str) -> RunState:
    """Resolve and scan one run while retaining its lazy coordination modules."""

    batch, builders, journal = runtime._coordination_modules()
    repository, state_root = journal._resolve_repository(ctx.repo.root, "launch")
    run_dir = state_root / ".codex-orchestrator" / "runs" / run_id
    return RunState(
        batch=batch,
        builders=builders,
        journal=journal,
        repository=repository,
        run_dir=run_dir,
        state=journal._scan_run(run_dir),
    )


def role_body_path(plugin_root: Path, provider: str, role: str) -> Path:
    """Return the committed provider role body consumed by a launch cell."""

    return plugin_root / f"system/{provider}/prompts/{role}.md"


def _codex_argv(
    role: str, model: str, effort: str, worktree: Path, staging: Path
) -> tuple[str, ...]:
    sandbox = route_config.profile_sandbox("codex", role)
    return (
        CODEX_EXECUTABLE,
        "exec",
        "--json",
        "--output-last-message",
        str(staging),
        "-s",
        sandbox,
        "-c",
        "approval_policy=never",
        "-c",
        f"model={model}",
        "-c",
        f"model_reasoning_effort={effort}",
        "-C",
        str(worktree),
        "-",
    )


def _claude_argv(
    role: str, model: str, effort: str, plugin_root: Path
) -> tuple[str, ...]:
    role_body = role_body_path(plugin_root, "claude", role)
    prompt_flag = "--append-system-prompt-file" if role == "implementer" else "--system-prompt-file"
    tools = CLAUDE_IMPLEMENTER_TOOLS if role == "implementer" else CLAUDE_PLAN_TOOLS
    argv = [
        CLAUDE_EXECUTABLE,
        "-p",
        "--safe-mode",
        "--strict-mcp-config",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--effort",
        effort,
        prompt_flag,
        str(role_body),
        "--tools",
        tools,
    ]
    if role == "implementer":
        argv.extend(("--permission-mode", "acceptEdits", "--allowedTools", "Bash"))
    argv.extend(("--permission-prompts", "none", "--no-session-persistence"))
    return tuple(argv)


def launch_argv(  # noqa: PLR0913 - the public cell signature is specification-bound.
    provider: str,
    role: str,
    model: str,
    effort: str,
    *,
    worktree: Path,
    plugin_root: Path,
    staging: Path,
) -> tuple[str, ...]:
    """Render the exact specification-bound provider argv for a typed launch."""

    if provider not in LAUNCH_PROVIDERS or role not in LAUNCH_ROLES:
        raise ValueError(f"unsupported launch cell: {provider}/{role}")
    if provider == "codex":
        return _codex_argv(role, model, effort, worktree, staging)
    return _claude_argv(role, model, effort, plugin_root)


def read_bounded_regular(
    path: Path, *, limit: int, owned: bool, private: bool = False
) -> bytes:
    """Read a bounded regular file without following symlinks."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        valid = stat.S_ISREG(metadata.st_mode) and (
            not owned or metadata.st_uid == os.geteuid()
        )
        valid = valid and (not private or metadata.st_mode & 0o077 == 0)
        if not valid or metadata.st_size > limit:
            raise OSError("file is not a bounded owner-controlled regular file")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > limit:
            raise OSError("file exceeds its byte limit")
        return data
    finally:
        os.close(descriptor)


def read_private_record(path: Path) -> bytes:
    """Read one owner-only launch record under the shared record limit."""

    return read_bounded_regular(
        path,
        limit=RECORD_LIMIT_BYTES,
        owned=True,
        private=True,
    )


def _brief_open_flags() -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    return flags | getattr(os, "O_NONBLOCK", 0)


def _brief_path_is_canonical(path: Path) -> bool:
    try:
        return path == path.resolve(strict=True)
    except RuntimeError:
        return False
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return False
        raise


def _brief_descriptor_path(descriptor: int) -> Path:
    if sys.platform.startswith("linux"):
        return Path(os.readlink(f"/proc/self/fd/{descriptor}"))
    get_path = getattr(fcntl, "F_GETPATH", None)
    if sys.platform == "darwin" and get_path is not None:
        value = fcntl.fcntl(descriptor, get_path, b"\0" * 1024)
        if isinstance(value, bytes):
            encoded = value.split(b"\0", 1)[0]
            if encoded:
                return Path(os.fsdecode(encoded))
    raise OSError(errno.ENOTSUP, "descriptor path lookup unavailable")


def _brief_descriptor_matches_path(descriptor: int, path: Path) -> bool:
    try:
        return _brief_descriptor_path(descriptor) == path
    except OSError:
        return False


def _brief_metadata_is_safe(descriptor: int, metadata: os.stat_result) -> bool:
    return bool(
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == os.geteuid()
        and metadata.st_size <= BRIEF_LIMIT_BYTES
        and owner_only_writable(descriptor, metadata)
    )


def _read_brief_descriptor(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    remaining = BRIEF_LIMIT_BYTES + 1
    while remaining:
        chunk = os.read(descriptor, min(65_536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if len(data) > BRIEF_LIMIT_BYTES:
        raise OSError("brief exceeds its byte limit")
    return data


def _read_owner_brief(path: Path) -> bytes:
    """Open and read the canonical brief through one no-follow descriptor."""

    descriptor = os.open(path, _brief_open_flags())
    try:
        if not _brief_descriptor_matches_path(descriptor, path):
            raise Refusal(
                V2ReasonCode.STATE_PRECONDITION,
                BRIEF_PATH_BINDING_REFUSAL_MESSAGE,
            )
        if not _brief_metadata_is_safe(descriptor, os.fstat(descriptor)):
            raise OSError("brief is not owner-controlled")
        return _read_brief_descriptor(descriptor)
    finally:
        os.close(descriptor)


def read_brief(path: Path) -> bytes:
    """Read and validate the owner-controlled absolute launch brief."""

    try:
        if not path.is_absolute():
            raise OSError("brief path is not absolute")
        if not _brief_path_is_canonical(path):
            raise Refusal(
                V2ReasonCode.STATE_PRECONDITION,
                BRIEF_PATH_REFUSAL_MESSAGE,
            )
        data = _read_owner_brief(path)
        data.decode("utf-8")
        if b"\0" in data:
            raise ValueError("brief contains NUL")
        return data
    except Refusal:
        raise
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            BRIEF_REFUSAL_MESSAGE,
        ) from exc


def git_bytes(
    worktree: Path,
    arguments: Sequence[str],
    *,
    limit: int = GIT_LIMIT_BYTES,
) -> bytes:
    """Run a bounded Git read in one worktree."""

    result = runtime.run_bounded(
        ["git", "-C", str(worktree), *arguments],
        cwd=worktree,
        timeout=GIT_TIMEOUT_SECONDS,
        cap=limit,
    )
    if result.output_limit:
        raise GitOutputLimitError("bounded Git output exceeded its byte limit")
    if result.returncode or result.timed_out:
        raise OSError("bounded Git read failed")
    return result.output


def _git_object_exists(worktree: Path, spec: str) -> bool:
    result = runtime.run_bounded(
        ["git", "-C", str(worktree), "cat-file", "-e", spec],
        cwd=worktree,
        timeout=GIT_TIMEOUT_SECONDS,
        cap=GIT_PROBE_CAP_BYTES,
    )
    if result.timed_out or result.output_limit:
        raise OSError("bounded Git existence check failed")
    return result.returncode == 0


def committed_file(worktree: Path, head: str, relative: str) -> bytes:
    """Read one file from the selected committed worktree snapshot."""

    return git_bytes(worktree, ["show", f"{head}:{relative}"])


def _committed_prompt_parts(request: PromptRequest) -> tuple[bytes, bytes]:
    project = committed_file(request.worktree, request.head, "forge-project.md")
    regions = policy._parse_regions(project)
    context = regions["agent-project-context"].encode("utf-8")
    relative = ".forge/history/gotchas.md"
    gotchas = (
        committed_file(request.worktree, request.head, relative)
        if _git_object_exists(request.worktree, f"{request.head}:{relative}")
        else b""
    )
    return context, gotchas


def prepare_prompt(ctx: chain_core.CommandContext, request: PromptRequest) -> PromptMaterial:
    """Assemble exact provider stdin from committed context and the launch brief.

    Codex receives its role body inline. Claude receives only the leading newline
    because its role body is supplied separately by the system-prompt argv flag.
    """

    plugin_root = ctx.plugin_root()
    role_path = role_body_path(plugin_root, request.provider, request.role)
    try:
        role_body = read_bounded_regular(
            role_path,
            limit=ROLE_BODY_LIMIT_BYTES,
            owned=False,
        )
        brief = read_brief(request.brief)
        context, gotchas = _committed_prompt_parts(request)
    except Refusal:
        raise
    except (KeyError, OSError, UnicodeError, ValueError, policy.PolicyError) as exc:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: launch refused — committed prompt inputs unavailable at {request.head}",
        ) from exc
    prefix = role_body + b"\n" if request.provider == "codex" else b"\n"
    prompt = (
        prefix
        + CONTEXT_SEPARATOR
        + context
        + GOTCHAS_SEPARATOR
        + gotchas
        + ASSIGNMENT_SEPARATOR
        + brief
    )
    return PromptMaterial(prompt, plugin_root, role_path, sha256_bytes(role_body))


def git_text(worktree: Path, *arguments: str) -> str:
    value = os.fsdecode(git_bytes(worktree, arguments)).rstrip("\n")
    if not value or "\n" in value or "\r" in value:
        raise OSError("Git fact unavailable")
    return value


def _decode_worktree_path(value: bytes) -> str:
    """Decode one Git -z path for the journal's strict UTF-8 string schema."""

    return value.decode("utf-8")


def worktree_files(worktree: Path, head: str) -> tuple[str, ...]:
    paths: set[str] = set()
    commands = (("diff", "--name-only", "-z", "--no-renames", head, "--"),
                ("ls-files", "--others", "--exclude-standard", "-z"))
    remaining = GIT_LIMIT_BYTES
    for command in commands:
        output = git_bytes(worktree, command, limit=remaining)
        if len(output) > remaining:
            raise GitOutputLimitError("combined Git path output exceeded its byte limit")
        remaining -= len(output)
        pieces = output.rstrip(b"\0").split(b"\0") if output else ()
        paths.update(_decode_worktree_path(piece) for piece in pieces if piece)
    return tuple(sorted(paths))


def _agent_pattern(prefix: str) -> re.Pattern[str]:
    return re.compile(rf"{re.escape(prefix)}[0-9]{{2}}\Z")


def _reusable_agent(
    records: Sequence[Mapping[str, object]],
    pattern: re.Pattern[str],
    provider: str,
    role: str,
    task: str,
) -> str | None:
    for record in records:
        agent = record.get("agent")
        if (
            record.get("type") == "execution"
            and record.get("task") == task
            and (record.get("provider"), record.get("role")) == (provider, role)
            and isinstance(agent, str)
            and pattern.fullmatch(agent) is not None
        ):
            return agent
    return None


def _first_free_agent(
    records: Sequence[Mapping[str, object]], pattern: re.Pattern[str], prefix: str
) -> str:
    used = {
        int(agent.removeprefix(prefix))
        for record in records
        if isinstance((agent := record.get("agent")), str)
        and pattern.fullmatch(agent) is not None
    }
    available = set(range(1, MAX_AGENT_NUMBER + 1)) - used
    if not available:
        raise ValueError(f"all {MAX_AGENT_NUMBER} launch agent names are allocated")
    return f"{prefix}{min(available):02d}"


def allocate_agent(
    records: Sequence[Mapping[str, object]], provider: str, role: str, task: str
) -> str:
    """Reuse the task's exact routed agent or allocate the first free name."""

    prefix = f"{provider}-{role}-"
    pattern = _agent_pattern(prefix)
    return _reusable_agent(records, pattern, provider, role, task) or _first_free_agent(
        records,
        pattern,
        prefix,
    )


def in_flight_execution(
    records: Sequence[Mapping[str, object]], worktree: Path
) -> str | None:
    """Return the first unterminated typed execution in one worktree."""

    terminal = {
        str(record.get("execution"))
        for record in records
        if record.get("type") == "execution_result"
    }
    for record in records:
        execution = record.get("execution")
        if (
            record.get("type") == "execution"
            and record.get("launch_marker")
            and record.get("worktree") == str(worktree)
            and isinstance(execution, str)
            and execution not in terminal
        ):
            return execution
    return None


def write_owner_file(directory: Path, name: str, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(directory / name, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError("short owner-file write")
        offset += written


def _fsync_path(path: Path, *, directory: bool = False) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def replace_owner_file(directory: Path, name: str, data: bytes) -> None:
    """Atomically replace one owner-only file and durably publish its directory entry."""

    path = directory / name
    temporary = directory / f".{name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            _write_all(descriptor, data)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        _fsync_path(path)
        _fsync_path(directory, directory=True)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_marker(path: Path, marker: Mapping[str, object]) -> None:
    """Atomically replace the canonical owner-only launch marker."""

    data = chain_core.canonical_bytes(dict(marker)) + b"\n"
    replace_owner_file(path.parent, path.name, data)


def write_pid(paths: LaunchPaths, pid: int) -> None:
    """Publish the legacy informational three-line PID sidecar."""

    data = f"{pid}\n{pid}\n{chain_core.iso_z()}\n".encode("ascii")
    replace_owner_file(paths.directory, PID_NAME, data)


def _validate_marker_strings(marker: Mapping[str, Any]) -> None:
    if any(
        not isinstance(marker.get(field), str) or not marker[field]
        for field in MARKER_STRING_KEYS
    ):
        raise ValueError("string field")
    if marker["role"] not in LAUNCH_ROLES or marker["provider"] not in LAUNCH_PROVIDERS:
        raise ValueError("profile")


def _validate_marker_lists(marker: Mapping[str, Any]) -> None:
    for field in ("environment_names", "omitted_short"):
        value = marker[field]
        if (
            not isinstance(value, list)
            or value != sorted(set(map(str, value)))
            or not all(isinstance(item, str) and item for item in value)
        ):
            raise ValueError(field)


def _validate_marker_lifecycle(marker: Mapping[str, Any]) -> None:
    if marker["collected_status"] not in {None, "complete", "failed"}:
        raise ValueError("collected_status")
    if (marker["collected_at"] is None) != (marker["collected_status"] is None):
        raise ValueError("collected lifecycle")
    chain_core.parse_time(str(marker["requested_at"]))
    if marker["collected_at"] is not None:
        chain_core.parse_time(str(marker["collected_at"]))


def validate_marker(marker: object) -> dict[str, Any]:
    """Validate the closed marker schema and its cross-field invariants."""

    if not isinstance(marker, dict) or set(marker) != MARKER_KEYS:
        raise ValueError("key set")
    _validate_marker_strings(marker)
    if marker["schema"] != LAUNCH_MARKER_SCHEMA:
        raise ValueError("schema")
    if ATTEMPT_PATTERN.fullmatch(str(marker["attempt"])) is None:
        raise ValueError("attempt")
    if EXECUTION_PATTERN.fullmatch(str(marker["execution"])) is None:
        raise ValueError("execution")
    if type(marker["timeout_seconds"]) is not int or marker["timeout_seconds"] <= 0:
        raise ValueError("timeout_seconds")
    digests = ("route_sha256", "role_body_sha256", "argv_digest", "prompt_digest",
               "launcher_argv_digest")
    if any(re.fullmatch(r"[0-9a-f]{64}", str(marker[field])) is None for field in digests):
        raise ValueError("digest")
    paths = ("worktree", "plugin_root", "role_body_path")
    if not all(Path(str(marker[field])).is_absolute() for field in paths):
        raise ValueError("path")
    if OBJECT_ID_PATTERN.fullmatch(str(marker["head"])) is None:
        raise ValueError("head")
    _validate_marker_lists(marker)
    _validate_marker_lifecycle(marker)
    return dict(marker)


def read_marker(path: Path) -> dict[str, Any]:
    """Read one canonical owner-only marker and reject duplicate JSON keys."""

    data = read_private_record(path)
    try:
        value = json.loads(data, object_pairs_hook=_unique_object)
        return validate_marker(value)
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise ValueError("launch marker is invalid") from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError("duplicate key")
    return value


def marker_binding(marker: Mapping[str, Any]) -> dict[str, Any]:
    return {field: marker[field] for field in WRAPPER_BINDING_FIELDS}


def marker_argv(marker: Mapping[str, Any], paths: LaunchPaths) -> tuple[str, ...]:
    """Reconstruct the provider argv bound by a launch marker."""

    return launch_argv(
        str(marker["provider"]),
        str(marker["role"]),
        str(marker["model"]),
        str(marker["effort"]),
        worktree=Path(str(marker["worktree"])),
        plugin_root=Path(str(marker["plugin_root"])),
        staging=paths.leaf(LAUNCH_LEAVES["staging"]),
    )


def bind_marker(
    ctx: chain_core.CommandContext,
    marker: Mapping[str, Any],
    record: Mapping[str, object],
    paths: LaunchPaths,
) -> str | None:
    """Return the first field for which marker, journal, or owner bytes diverge."""

    for field in RECORD_BOUND_FIELDS:
        if marker.get(field) != record.get(field):
            return field
    expected_ref = paths.reference(MARKER_NAME)
    if record.get("launch_marker") != expected_ref:
        return "launch_marker"
    prompt = read_bounded_regular(
        paths.leaf(LAUNCH_LEAVES["prompt"]),
        limit=PROMPT_LIMIT_BYTES,
        owned=True,
        private=True,
    )
    if sha256_bytes(prompt) != marker.get("prompt_digest"):
        return "prompt_digest"
    argv = marker_argv(marker, paths)
    if ctx.command_digest(argv) != marker.get("argv_digest"):
        return "argv_digest"
    return None


def wrapper_config(marker: Mapping[str, Any], argv: Sequence[str]) -> dict[str, object]:
    return {
        **marker_binding(marker),
        "argv": list(argv),
        "timeout": marker["timeout_seconds"],
        "grace": _review_launch.TERMINATE_GRACE_SECONDS,
        "environment_names": list(marker["environment_names"]),
        "omitted_short": list(marker["omitted_short"]),
        "role_body_digest": None,
        "leaves": dict(LAUNCH_LEAVES),
        "events_existing": True,
    }


def result_record(
    state: Any, execution: str, agent: object
) -> dict[str, object] | None:
    """Return the newest terminal result for one exact execution owner."""

    matches = [
        dict(record)
        for record in state.records
        if record.get("type") == "execution_result"
        and record.get("execution") == execution
        and record.get("agent") == agent
    ]
    return matches[-1] if matches else None


def completion_summary(
    status: str,
    returncode: object,
    error: object,
    timed_out: object,
    handoff_bytes: int,
    observed_model: object,
) -> str:
    """Render the byte-stable summary shared by normal and failed starts."""

    rendered_returncode = returncode if returncode is not None else "none"
    rendered_error = error if error is not None else "none"
    rendered_timeout = str(bool(timed_out)).lower()
    rendered_model = observed_model if observed_model is not None else "none"
    return (
        f"launch collect: {status}; returncode {rendered_returncode}; error "
        f"{rendered_error}; timed_out {rendered_timeout}; handoff {handoff_bytes} "
        f"bytes; observed_model {rendered_model}"
    )


def plan_caveats(role: object, changed: Sequence[str]) -> tuple[str, ...]:
    return ("plan execution changed files",) if role == "plan" and changed else ()


def worktree_changes(worktree: Path, head: str, execution: str) -> tuple[str, ...]:
    """Collect sorted worktree facts or raise the canonical collect refusal."""

    try:
        return worktree_files(worktree, head)
    except GitOutputLimitError as exc:
        raise Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: launch collect refused — worktree path list exceeds 1 MiB "
            f"for {execution}; reduce changed or untracked paths, then retry "
            "launch collect",
        ) from exc
    except UnicodeError as exc:
        raise Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: launch collect refused — worktree paths are not UTF-8 for "
            f"{execution}; restore changed tracked paths or rename/remove untracked "
            "paths, then retry launch collect",
        ) from exc
    except OSError as exc:
        raise Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: launch collect refused — worktree facts unavailable for {execution}",
        ) from exc


def _handoff(
    paths: LaunchPaths, completion: Mapping[str, Any]
) -> tuple[bytes, str | None, bool]:
    try:
        data = read_private_record(paths.leaf(LAUNCH_LEAVES["capture"]))
    except OSError:
        return b"", None, False
    reference = paths.reference(LAUNCH_LEAVES["capture"])
    valid = (
        bool(data)
        and sha256_bytes(data) == completion.get("verdict_digest")
        and len(data) == completion.get("verdict_size")
    )
    return data, reference, valid


def _completion_caveat(
    completion: Mapping[str, Any], provider: object, handoff_valid: bool
) -> str | None:
    error = completion.get("error")
    if error == "not-logged-in":
        return (
            _review_launch.CODEX_NOT_LOGGED_IN
            if provider == "codex"
            else _review_launch.CLAUDE_NOT_LOGGED_IN
        )
    if error is not None:
        return str(error)
    if completion.get("timed_out") is True:
        return "timeout"
    if not handoff_valid:
        return "handoff does not bind completion"
    return None


def map_completion(
    record: Mapping[str, object],
    paths: LaunchPaths,
    completion: Mapping[str, Any],
) -> CompletionResult:
    """Map a validated wrapper completion into the exact journal result fields."""

    handoff_data, handoff, handoff_valid = _handoff(paths, completion)
    success = (
        completion.get("returncode") == 0
        and completion.get("error") is None
        and completion.get("timed_out") is False
        and handoff_valid
    )
    status = "complete" if success else "failed"
    caveat = _completion_caveat(completion, record.get("provider"), handoff_valid)
    changed = worktree_changes(
        Path(str(record["worktree"])),
        str(record["head"]),
        paths.execution,
    )
    caveats = (() if caveat is None else (caveat,)) + plan_caveats(
        record.get("role"),
        changed,
    )
    summary = completion_summary(
        status,
        completion.get("returncode"),
        completion.get("error"),
        completion.get("timed_out"),
        len(handoff_data),
        completion.get("observed_model"),
    )
    message = caveat if completion.get("error") == "not-logged-in" else None
    return CompletionResult(
        status=status,
        summary=summary,
        files_changed=changed,
        caveats=caveats,
        handoff=handoff,
        message=message or f"launch collect: {status}",
    )


def append_execution_result(
    run: RunState,
    paths: LaunchPaths,
    *,
    task: str,
    result: CompletionResult,
    completion_raw: bytes,
) -> tuple[dict[str, object], bool]:
    """Append one idempotent result, returning its record and repeat status."""

    key = completion_idempotency(
        paths.run_dir.name,
        paths.execution,
        sha256_bytes(completion_raw),
    )
    with run.batch.batch_lock(run.run_dir, create=True):
        state = run.journal._scan_run(run.run_dir)
        existing = result_record(state, paths.execution, paths.agent)
        if existing is not None:
            return existing, True
        try:
            outcome = run.builders.execution_result(
                run.repository,
                paths.run_dir.name,
                idempotency_key=key,
                execution=paths.execution,
                agent=paths.agent,
                task=task,
                status=result.status,
                summary=result.summary,
                files_changed=result.files_changed,
                caveats=result.caveats,
                handoff=result.handoff,
            )
        except run.journal.CoordinationRefusal as exc:
            fresh = run.journal._scan_run(run.run_dir)
            existing = result_record(fresh, paths.execution, paths.agent)
            if existing is not None:
                return existing, True
            raise chain_core._coordination_refusal(exc) from exc
    records = [
        record for record in outcome.records if record.get("type") == "execution_result"
    ]
    if len(records) != 1:
        raise chain_core._coordination_refusal(
            run.journal.CoordinationRefusal(run.journal.BATCH_DIVERGED)
        )
    return dict(records[0]), bool(outcome.repeated)


def mark_collected(
    paths: LaunchPaths, marker: dict[str, Any], status: object
) -> None:
    """Repair an uncollected marker after its one terminal result exists."""

    if marker["collected_at"] is not None:
        return
    marker["collected_at"] = chain_core.iso_z()
    marker["collected_status"] = "complete" if status == "complete" else "failed"
    write_marker(paths.leaf(MARKER_NAME), marker)


def completion_present(paths: LaunchPaths) -> bool:
    """Return whether a bounded owner-only completion exists without reading it."""

    path = paths.leaf(_review_attempt.COMPLETION_NAME)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return False
    try:
        metadata = os.fstat(descriptor)
        return (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == os.geteuid()
            and metadata.st_mode & 0o077 == 0
            and metadata.st_size <= RECORD_LIMIT_BYTES
        )
    finally:
        os.close(descriptor)


def terminal_outcome(
    paths: LaunchPaths,
    result: Mapping[str, object],
    message: str | None = None,
) -> Outcome:
    """Render a terminal result; a fresh collect may supply its mapping message."""

    status = str(result.get("status"))
    normalized = status if status in {"complete", "failed"} else "failed"
    caveats = result.get("caveats")
    messages = list(caveats) if isinstance(caveats, list) else []
    login = {_review_launch.CODEX_NOT_LOGGED_IN, _review_launch.CLAUDE_NOT_LOGGED_IN}
    login_message = next((str(item) for item in messages if item in login), None)
    refs = [paths.reference(MARKER_NAME)]
    if completion_present(paths):
        refs.append(paths.reference(_review_attempt.COMPLETION_NAME))
    if isinstance(result.get("handoff"), str):
        refs.append(str(result["handoff"]))
    return Outcome(
        ok=True,
        reason_code=V2ReasonCode.OK,
        message=message or login_message or f"launch collect: {normalized}",
        state=normalized,
        next_required_step="none — launch execution is terminal",
        evidence_refs=tuple(refs),
        schema=REVISION9_OUTPUT_SCHEMA,
    )


def completion_idempotency(run_id: str, execution: str, digest: str) -> str:
    return sha256_bytes(
        chain_core.canonical_bytes(
            {
                "schema": IDEMPOTENCY_SCHEMA,
                "step": "execution-result",
                "run_id": run_id,
                "execution": execution,
                "completion_sha256": digest,
            }
        )
    )


def start_idempotency(marker: Mapping[str, Any]) -> str:
    return sha256_bytes(
        chain_core.canonical_bytes(
            {
                "schema": IDEMPOTENCY_SCHEMA,
                "step": "execution-start",
                "run_id": marker["run_id"],
                "agent": marker["agent"],
                "execution": marker["execution"],
                "prompt_digest": marker["prompt_digest"],
                "requested_at": marker["requested_at"],
            }
        )
    )


def open_attempt(paths: LaunchPaths) -> int:
    return _review_lane_api.open_attempt_directory(paths.directory)
