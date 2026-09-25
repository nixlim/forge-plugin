"""Bounded provider availability probes for developer-local Forge routes."""

from __future__ import annotations

import json
import os
import selectors
import signal
import stat
import subprocess
import tempfile
import time
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

PROBE_TIMEOUT_SECONDS = 120
TERMINATE_GRACE_SECONDS = 5
STDOUT_LIMIT_BYTES = 16 * 1024 * 1024
STDERR_LIMIT_BYTES = 1024 * 1024
PROBE_BRIEF = b"Confirm that this model route is available and reply briefly.\n"
CODEX_NOT_LOGGED_IN = (
    "forge: codex launch refused — codex CLI is not logged in; "
    "run codex login manually and retry"
)
CLAUDE_NOT_LOGGED_IN = (
    "forge: claude launch refused — claude CLI is not logged in; "
    "run interactive /login manually and retry"
)

_BASE_ENVIRONMENT = frozenset({"HOME", "PATH", "LANG", "LC_ALL", "USER", "TMPDIR", "TERM"})
_CLAUDE_ENVIRONMENT = frozenset(
    {"ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "CLOUD_ML_REGION",
     "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"}
)


@dataclass(frozen=True)
class ProbeSpec:
    """One resolved provider/model/effort route and the roles that selected it."""

    provider: str
    model: str
    effort: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class ProbeOutcome:
    """A JSON-serializable report and an optional user-facing refusal."""

    report: dict[str, object]
    diagnostic: str | None

    @property
    def ok(self) -> bool:
        """Return whether the provider probe satisfied its success contract."""

        return self.diagnostic is None


class UnsafeDirectoryError(OSError):
    """A sensitive routing directory failed no-follow validation."""


@dataclass(frozen=True)
class _LaunchRequest:
    provider: str
    argv: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]


@dataclass(frozen=True)
class _LaunchResult:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    launch_error: bool
    auth_refusal: bool
    output_limit: str | None


@dataclass(frozen=True)
class _ClaudeStream:
    final_result: dict[str, object] | None
    observed_model: str | None
    permission_denials: list[object]
    malformed: bool


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _secure_child(parent: int, name: str) -> int:
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent)
    except FileExistsError:
        pass
    try:
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent)
        metadata = os.fstat(descriptor)
    except OSError as exc:
        raise UnsafeDirectoryError(name) from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        os.close(descriptor)
        raise UnsafeDirectoryError(name)
    return descriptor


@contextmanager
def secure_directory(
    root: Path, components: tuple[str, ...], *, final_mode: int | None = 0o700
) -> Iterator[tuple[Path, int]]:
    """Create and traverse owner-controlled directories without following links."""

    try:
        descriptor = os.open(root, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise UnsafeDirectoryError(str(root)) from exc
    try:
        for component in components:
            child = _secure_child(descriptor, component)
            os.close(descriptor)
            descriptor = child
        if final_mode is not None:
            os.fchmod(descriptor, final_mode)
        yield root.joinpath(*components), descriptor
    finally:
        os.close(descriptor)


def _environment_name_is_allowed(provider: str, name: str) -> bool:
    if provider == "codex":
        return name in _BASE_ENVIRONMENT or name == "CODEX_HOME"
    if provider == "claude":
        return (
            name in _BASE_ENVIRONMENT
            or name in _CLAUDE_ENVIRONMENT
            or name.startswith("AWS_")
            or name.startswith("GOOGLE_")
        )
    raise ValueError(f"unsupported route provider: {provider}")


def _allowed_environment(
    provider: str, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Copy only the FR-245 names admitted for ``provider`` from ``environ``."""

    source = os.environ if environ is None else environ
    return {
        name: value
        for name, value in source.items()
        if _environment_name_is_allowed(provider, name)
    }


def _deduplicate_specs(specs: Iterable[ProbeSpec]) -> list[ProbeSpec]:
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for spec in specs:
        key = (spec.provider, spec.model, spec.effort)
        roles = grouped.setdefault(key, [])
        roles.extend(role for role in spec.roles if role not in roles)
    return [ProbeSpec(*key, tuple(roles)) for key, roles in grouped.items()]


def _codex_argv(spec: ProbeSpec, scratch: Path, capture: Path) -> tuple[str, ...]:
    return (
        "codex", "exec", "--json", "--output-last-message", str(capture),
        "-s", "read-only", "-c", "approval_policy=never", "-c", f"model={spec.model}",
        "-c", f"model_reasoning_effort={spec.effort}", "-C", str(scratch), "-",
    )


def _claude_argv(spec: ProbeSpec, plugin_root: Path) -> tuple[str, ...]:
    return (
        "claude", "-p", "--safe-mode", "--strict-mcp-config",
        "--output-format", "stream-json", "--verbose", "--model", spec.model,
        "--effort", spec.effort, "--system-prompt-file",
        str(plugin_root / "system" / "claude" / "prompts" / "plan.md"),
        "--tools", "Read,Grep,Glob,LS", "--permission-prompts", "none",
    )


def _signal_group(process: subprocess.Popen[bytes], signum: signal.Signals) -> None:
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def _group_is_alive(process: subprocess.Popen[bytes]) -> bool:
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    _signal_group(process, signal.SIGTERM)
    deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
    while _group_is_alive(process) and time.monotonic() < deadline:
        process.poll()
        time.sleep(0.01)
    if _group_is_alive(process):
        _signal_group(process, signal.SIGKILL)
    try:
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _signal_group(process, signal.SIGKILL)
        process.wait(timeout=TERMINATE_GRACE_SECONDS)


def _stream_selector(
    process: subprocess.Popen[bytes],
    stdout: bytearray,
    stderr: bytearray,
) -> selectors.BaseSelector:
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    streams = (
        (process.stdout, stdout, STDOUT_LIMIT_BYTES, "stdout"),
        (process.stderr, stderr, STDERR_LIMIT_BYTES, "stderr"),
    )
    for stream, destination, limit, name in streams:
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, (destination, limit, name))
    return selector


def _drain_ready(selector: selectors.BaseSelector, timeout: float) -> str | None:
    exceeded = None
    for key, _mask in selector.select(timeout):
        try:
            chunk = os.read(key.fd, 64 * 1024)
        except BlockingIOError:
            continue
        if chunk:
            destination, limit, name = key.data
            available = max(0, limit - len(destination))
            destination.extend(chunk[:available])
            if len(chunk) > available:
                exceeded = name
            continue
        selector.unregister(key.fileobj)
        key.fileobj.close()
    return exceeded


def _close_selector(selector: selectors.BaseSelector) -> None:
    for key in list(selector.get_map().values()):
        selector.unregister(key.fileobj)
        key.fileobj.close()
    selector.close()


def _write_brief(process: subprocess.Popen[bytes]) -> None:
    assert process.stdin is not None
    try:
        process.stdin.write(PROBE_BRIEF)
        process.stdin.flush()
    except BrokenPipeError:
        pass
    try:
        process.stdin.close()
    except BrokenPipeError:
        pass


def _json_object(raw_line: bytes) -> dict[str, object] | None:
    try:
        event = json.loads(raw_line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return event if isinstance(event, dict) else None


def _codex_error_lines(lines: Iterable[bytes]) -> bool:
    for raw_line in lines:
        event = _json_object(raw_line)
        if event and event.get("type") == "error":
            message = event.get("message")
            if isinstance(message, str) and "401 Unauthorized" in message:
                return True
    return False


def _claude_login_line(raw_line: bytes) -> bool:
    event = _json_object(raw_line)
    if not event or event.get("type") != "result" or event.get("is_error") is not True:
        return False
    result = event.get("result")
    return isinstance(result, str) and "Not logged in" in result


def _complete_lines(buffer: bytearray, offset: int) -> tuple[list[bytes], int]:
    boundary = buffer.rfind(b"\n") + 1
    if boundary <= offset:
        return [], offset
    return bytes(buffer[offset:boundary]).splitlines(), boundary


def _auth_refusal_seen(
    provider: str,
    stdout: bytearray,
    stderr: bytearray,
    offsets: list[int],
) -> bool:
    lines, offsets[0] = _complete_lines(stdout, offsets[0])
    stderr_start = max(0, offsets[1] - len(b"401 Unauthorized"))
    new_stderr = bytes(stderr[stderr_start:])
    offsets[1] = len(stderr)
    if provider == "codex":
        return b"401 Unauthorized" in new_stderr or _codex_error_lines(lines)
    return any(_claude_login_line(line) for line in lines)


def _wait_for_activity(
    process: subprocess.Popen[bytes],
    selector: selectors.BaseSelector,
    timeout: float,
) -> str | None:
    if selector.get_map():
        return _drain_ready(selector, timeout)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pass
    return None


def _drain_after_stop(selector: selectors.BaseSelector) -> None:
    deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
    while selector.get_map() and time.monotonic() < deadline:
        _drain_ready(selector, max(0.0, deadline - time.monotonic()))


def _monitor_launch(
    process: subprocess.Popen[bytes], provider: str
) -> tuple[bytes, bytes, bool, bool, str | None]:
    stdout = bytearray()
    stderr = bytearray()
    selector = _stream_selector(process, stdout, stderr)
    deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
    timed_out = False
    auth_refusal = False
    output_limit = None
    auth_offsets = [0, 0]
    while process.poll() is None or selector.get_map():
        if _auth_refusal_seen(provider, stdout, stderr, auth_offsets):
            auth_refusal = True
            _terminate_group(process)
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            _terminate_group(process)
            break
        output_limit = _wait_for_activity(process, selector, min(remaining, 0.05))
        if output_limit is not None:
            _terminate_group(process)
            break
    _drain_after_stop(selector)
    _close_selector(selector)
    return bytes(stdout), bytes(stderr), timed_out, auth_refusal, output_limit


def _execute(request: _LaunchRequest) -> _LaunchResult:
    try:
        process = subprocess.Popen(
            request.argv,
            cwd=request.cwd,
            env=request.environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError:
        return _LaunchResult(None, b"", b"", False, True, False, None)
    _write_brief(process)
    stdout, stderr, timed_out, auth_refusal, output_limit = _monitor_launch(
        process, request.provider
    )
    return _LaunchResult(
        process.returncode,
        stdout,
        stderr,
        timed_out,
        False,
        auth_refusal,
        output_limit,
    )


def _codex_unauthorized(stdout: bytes, stderr: bytes) -> bool:
    return b"401 Unauthorized" in stderr or _codex_error_lines(stdout.splitlines())


def _capture_is_nonempty(capture: Path) -> bool:
    try:
        return bool(capture.read_bytes().strip())
    except OSError:
        return False


def _event_model(event: dict[str, object]) -> str | None:
    if event.get("type") == "system" and event.get("subtype") == "init":
        model = event.get("model")
        return model if isinstance(model, str) else None
    if event.get("type") == "init":
        model = event.get("model")
        return model if isinstance(model, str) else None
    if event.get("type") == "assistant" and isinstance(event.get("message"), dict):
        model = event["message"].get("model")
        return model if isinstance(model, str) else None
    return None


def _claude_stream(stdout: bytes) -> _ClaudeStream:
    final_result: dict[str, object] | None = None
    observed_model: str | None = None
    malformed = False
    for raw_line in stdout.splitlines():
        try:
            event = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed = True
            continue
        if not isinstance(event, dict):
            malformed = True
            continue
        observed_model = _event_model(event) or observed_model
        if event.get("type") == "result":
            final_result = event
    denials = final_result.get("permission_denials", []) if final_result else []
    return _ClaudeStream(
        final_result,
        observed_model,
        list(denials) if isinstance(denials, list) else [],
        malformed,
    )


def _base_report(
    spec: ProbeSpec,
    launch: _LaunchResult,
    environment: Mapping[str, str],
) -> dict[str, object]:
    return {
        "provider": spec.provider,
        "model": spec.model,
        "effort": spec.effort,
        "roles": list(spec.roles),
        "ok": False,
        "returncode": launch.returncode,
        "timed_out": launch.timed_out,
        "output_limit": launch.output_limit,
        "observed_model": None,
        "permission_denials": [],
        "environment_names": sorted(environment),
    }


def _generic_diagnostic(spec: ProbeSpec, launch: _LaunchResult) -> str:
    prefix = f"forge: {spec.provider} launch refused — "
    if launch.launch_error:
        return f"{prefix}{spec.provider} CLI could not be started"
    if launch.timed_out:
        return f"{prefix}route probe timed out"
    if launch.output_limit is not None:
        return f"{prefix}route probe {launch.output_limit} exceeded limit"
    return f"{prefix}route probe failed"


def _codex_outcome(
    spec: ProbeSpec,
    launch: _LaunchResult,
    capture: Path,
    environment: Mapping[str, str],
) -> ProbeOutcome:
    report = _base_report(spec, launch, environment)
    if launch.auth_refusal or _codex_unauthorized(launch.stdout, launch.stderr):
        return ProbeOutcome(report, CODEX_NOT_LOGGED_IN)
    if (
        launch.returncode == 0
        and not launch.timed_out
        and launch.output_limit is None
        and _capture_is_nonempty(capture)
    ):
        report["ok"] = True
        return ProbeOutcome(report, None)
    return ProbeOutcome(report, _generic_diagnostic(spec, launch))


def _claude_outcome(
    spec: ProbeSpec,
    launch: _LaunchResult,
    environment: Mapping[str, str],
) -> ProbeOutcome:
    stream = _claude_stream(launch.stdout)
    report = _base_report(spec, launch, environment)
    report["observed_model"] = stream.observed_model
    report["permission_denials"] = stream.permission_denials
    result = stream.final_result
    if launch.auth_refusal or (
        result
        and result.get("is_error") is True
        and isinstance(result.get("result"), str)
        and "Not logged in" in result["result"]
    ):
        return ProbeOutcome(report, CLAUDE_NOT_LOGGED_IN)
    if (
        launch.returncode == 0
        and not launch.timed_out
        and launch.output_limit is None
        and not stream.malformed
        and result is not None
        and result.get("is_error") is False
    ):
        report["ok"] = True
        return ProbeOutcome(report, None)
    return ProbeOutcome(report, _generic_diagnostic(spec, launch))


def _probe_one(
    probe_root: Path,
    plugin_root: Path,
    spec: ProbeSpec,
    environ: Mapping[str, str] | None,
) -> ProbeOutcome:
    environment = _allowed_environment(spec.provider, environ)
    with tempfile.TemporaryDirectory(prefix="probe-", dir=probe_root) as directory:
        scratch = Path(directory)
        capture = scratch / "last-message.txt"
        if spec.provider == "codex":
            request = _LaunchRequest(
                spec.provider,
                _codex_argv(spec, scratch, capture),
                scratch,
                environment,
            )
            return _codex_outcome(spec, _execute(request), capture, environment)
        request = _LaunchRequest(
            spec.provider,
            _claude_argv(spec, plugin_root),
            scratch,
            environment,
        )
        return _claude_outcome(spec, _execute(request), environment)


def _unsafe_directory_outcome(
    spec: ProbeSpec, environ: Mapping[str, str] | None
) -> ProbeOutcome:
    environment = _allowed_environment(spec.provider, environ)
    launch = _LaunchResult(None, b"", b"", False, True, False, None)
    report = _base_report(spec, launch, environment)
    return ProbeOutcome(report, "forge: route probe refused — unsafe scratch directory")


def probe_routes(
    common_root: Path,
    plugin_root: Path,
    specs: Iterable[ProbeSpec],
    *,
    environ: Mapping[str, str] | None = None,
) -> list[ProbeOutcome]:
    """Probe every distinct route once, preserving pair and role encounter order."""

    deduplicated = _deduplicate_specs(specs)
    try:
        with secure_directory(common_root, (".forge", "tmp", "route-probe")) as entry:
            probe_root, _descriptor = entry
            return [
                _probe_one(probe_root, plugin_root, spec, environ)
                for spec in deduplicated
            ]
    except UnsafeDirectoryError:
        return [_unsafe_directory_outcome(spec, environ) for spec in deduplicated]
