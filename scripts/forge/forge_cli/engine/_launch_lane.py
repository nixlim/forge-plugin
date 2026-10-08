"""Request-free primitives shared by the typed launch verb modules."""

from __future__ import annotations

import contextlib
import dataclasses
import errno
import fcntl
import json
import os
import re
import secrets
import stat
import sys
from collections.abc import Iterator, Mapping, Sequence
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
MAX_AGENT_NUMBER = 99
LAUNCH_MARKER_SCHEMA = "forge-launch-marker/1"
GLOBAL_HALT_SCOPE = ""
MARKER_NAME = "launch.json"
WRAPPER_CONFIG_NAME = "wrapper-config.json"
PID_NAME = "pid"
WORKTREE_NAME = "worktree"
EXECUTION_IDS_NAME = ".execution-ids"
ATTEMPT_PATTERN = re.compile(r"attempt-[0-9a-f]{16}\Z")
EXECUTION_PATTERN = re.compile(r"execution-[0-9]{2}\Z")
OBJECT_ID_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
LAUNCH_ROLES = frozenset({"implementer", "plan"})
LAUNCH_PROVIDERS = frozenset({"codex", "claude"})
EVENT_SOURCES = {"codex": "exec", "claude": "claude"}
CLAUDE_IMPLEMENTER_TOOLS = "Read,Write,Edit,Bash,Grep,Glob"
CLAUDE_PLAN_TOOLS = "Read,Grep,Glob"
CONTEXT_SEPARATOR = b"--- committed agent-project-context ---\n"
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
WRAPPER_BINDING_FIELDS = (
    "run_id",
    "task",
    "agent",
    "execution",
    "attempt",
    "role",
    "provider",
    "model",
    "effort",
    "worktree",
    "head",
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
    """Locate one run and its plain journal writer."""

    journal: Any
    repository: Path
    run_dir: Path


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
            V2ReasonCode.STATE_PRECONDITION,
            _cli_options.LAUNCH_RUN_ID_REQUIRED,
        )
    return run_id


def run_state(ctx: chain_core.CommandContext, run_id: str) -> RunState:
    """Load the writer on demand from the sibling scripts package."""

    scripts = str(runtime.SCRIPT_DIR.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from codex_orchestrator import journal  # noqa: PLC0415

    repository = ctx.repo.git_common_dir().parent
    return RunState(journal, repository, journal.run_directory(repository, run_id))


@contextlib.contextmanager
def journal_lock(run: RunState) -> Iterator[int]:
    """Serialize launch ids and the start append on the journal descriptor."""

    descriptor = run.journal.open_append_lock(run.repository, run.run_dir.name)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def append_record(run: RunState, record: dict[str, object], descriptor: int | None = None) -> None:
    """Best-effort append of a launch fact without granting it authority."""

    try:
        if descriptor is None:
            run.journal.append_run_record(run.repository, run.run_dir.name, record)
        else:
            run.journal.append_locked_record(descriptor, run.run_dir / "journal.jsonl", record)
    except (OSError, run.journal.CoordinationRefusal):
        print(run.journal.APPEND_IO_ERROR, file=sys.stderr)


def markers(run: RunState) -> list[dict[str, Any]]:
    """Read launch markers without treating journal contents as launch authority."""

    found: list[dict[str, Any]] = []
    for path in run.run_dir.glob("*/execution-*/launch.json"):
        try:
            found.append(read_marker(path))
        except (OSError, ValueError):
            try:
                worktree = (
                    read_private_record(path.parent / WORKTREE_NAME)
                    .decode("utf-8")
                    .rstrip("\n")
                )
            except (OSError, UnicodeError):
                worktree = None
            found.append({"agent": path.parent.parent.name,
                          "execution": path.parent.name, "collected_at": None,
                          "worktree": worktree, "invalid": True})
    return found


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


def committed_file(worktree: Path, head: str, relative: str) -> bytes:
    """Read one file from the selected committed worktree snapshot."""

    return git_bytes(worktree, ["show", f"{head}:{relative}"])


def _committed_prompt_parts(request: PromptRequest) -> bytes:
    project = committed_file(request.worktree, request.head, "forge-project.md")
    regions = policy._parse_regions(project)
    context = regions["agent-project-context"].encode("utf-8")
    return context


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
        context = _committed_prompt_parts(request)
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
            record.get("task") == task
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


def in_flight_execution(run: RunState, worktree: Path) -> str | None:
    """Use marker and completion artefacts to identify a pending launch."""

    for marker in markers(run):
        if marker.get("worktree") != str(worktree):
            continue
        if marker.get("invalid") or marker.get("collected_at") is None:
            return str(marker["execution"])
        try:
            paths = LaunchPaths(run.run_dir, str(marker["agent"]), str(marker["execution"]))
            if not completion_present(paths):
                return str(marker["execution"])
        except (OSError, ValueError):
            return str(marker["execution"])
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


def bind_wrapper_config(marker: Mapping[str, Any], paths: LaunchPaths) -> str | None:
    """Bind the marker to the separate config saved before wrapper launch."""

    try:
        config = json.loads(
            read_private_record(paths.leaf(WRAPPER_CONFIG_NAME)),
            object_pairs_hook=_unique_object,
        )
    except (OSError, UnicodeError, ValueError):
        return "wrapper_config"
    if not isinstance(config, dict):
        return "wrapper_config"
    # ponytail: a launcher that writes both artefacts dishonestly is not detected;
    # upgrade with independently authenticated launch evidence if that threat matters.
    for field in WRAPPER_BINDING_FIELDS:
        if marker.get(field) != config.get(field):
            return field
    if list(marker_argv(marker, paths)) != config.get("argv"):
        return "argv_digest"
    return None


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
    paths: LaunchPaths,
) -> str | None:
    """Compare marker fields with independent owner paths, bytes, and completion."""

    sidecar = read_private_record(paths.leaf(WORKTREE_NAME)).decode("utf-8")
    worktree = sidecar[:-1] if sidecar.endswith("\n") else None
    if worktree is not None and os.path.realpath(worktree) != worktree:
        worktree = None
    owner = re.fullmatch(r"(codex|claude)-(implementer|plan)-[0-9]{2}", paths.agent)
    for field, expected in (
        ("run_id", paths.run_dir.name),
        ("agent", paths.agent),
        ("execution", paths.execution),
        ("worktree", worktree),
        ("provider", owner.group(1) if owner else None),
        ("role", owner.group(2) if owner else None),
    ):
        if marker.get(field) != expected:
            return field
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
    try:
        completion = json.loads(read_private_record(paths.leaf(_review_attempt.COMPLETION_NAME)))
    except FileNotFoundError:
        return None
    if not isinstance(completion, dict):
        return "completion"
    return next((field for field, recorded in (
        ("attempt", "attempt"), ("provider", "provider"),
        ("sandbox", "sandbox"), ("route_source", "route_source"),
        ("route_sha256", "route_sha256"),
        ("argv_digest", "argv_digest"), ("prompt_digest", "prompt_digest"),
    ) if marker.get(field) != completion.get(recorded)), None)


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
) -> dict[str, object]:
    """Log completion; the marker remains the recovery and idempotence source."""

    marker = read_marker(paths.leaf(MARKER_NAME))
    try:
        completion = json.loads(completion_raw)
    except (ValueError, UnicodeError):
        completion = {}
    returncode = completion.get("returncode") if isinstance(completion, dict) else None
    record: dict[str, object] = {
        "kind": "execution_finished", "run_id": run.run_dir.name,
        "execution_id": paths.execution, "attempt_id": marker["attempt"],
        "agent": paths.agent, "task_id": task, "role": marker["role"],
        "provider": marker["provider"], "model": marker["model"],
        "effort": marker["effort"], "sandbox": marker["sandbox"],
        "route_source": marker["route_source"], "route_sha256": marker["route_sha256"],
        "worktree": marker["worktree"], "ended_at": chain_core.iso_z(),
        "started_at": marker["requested_at"],
        "status": result.status, "exit_status": returncode if type(returncode) is int else None,
        "summary": result.summary,
        "files_changed": list(result.files_changed), "caveats": list(result.caveats),
        "output": result.handoff or paths.reference(LAUNCH_LEAVES["stderr"]),
        "handoff": result.handoff,
        "completion": paths.reference(_review_attempt.COMPLETION_NAME),
    }
    append_record(run, record)
    return record


def mark_collected(
    paths: LaunchPaths, marker: dict[str, Any], status: object
) -> None:
    """Mark a completion as collected using the marker's status."""

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


def open_attempt(paths: LaunchPaths) -> int:
    return _review_lane_api.open_attempt_directory(paths.directory)
