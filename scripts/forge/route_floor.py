"""Check provider CLI versions against Forge's committed floors."""

from __future__ import annotations

import argparse
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, NoReturn, cast

FLOORS = {"claude": (2, 1, 283), "codex": (0, 155, 0)}
_VERSION_RE = re.compile(rb"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)")
FloorRefusalKind = Literal[
    "unavailable", "timeout", "limit", "exit", "unparseable", "below"
]


class FloorRefusal(RuntimeError):
    """A provider version-floor refusal with a stable machine-readable kind."""

    def __init__(self, message: str, kind: FloorRefusalKind) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind


def _refuse(message: str, kind: FloorRefusalKind) -> NoReturn:
    raise FloorRefusal(message, kind)


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _terminate_probe(process: subprocess.Popen[bytes], grace_seconds: float) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + grace_seconds
    while _group_exists(process.pid) and time.monotonic() < deadline:
        process.poll()
        time.sleep(0.01)
    if _group_exists(process.pid):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _bounded_output(
    process: subprocess.Popen[bytes],
    timeout_seconds: float,
    limit_bytes: int,
    grace_seconds: float,
) -> tuple[bytes, bytes, str | None]:
    assert process.stdout is not None and process.stderr is not None
    streams = {process.stdout.fileno(): "stdout", process.stderr.fileno(): "stderr"}
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    for descriptor, name in streams.items():
        selector.register(descriptor, selectors.EVENT_READ, name)
    deadline = time.monotonic() + timeout_seconds
    outcome: str | None = None
    while selector.get_map() and outcome is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            outcome = "timeout"
            break
        for key, _mask in selector.select(min(remaining, 0.1)):
            chunk = os.read(key.fd, limit_bytes + 1)
            if not chunk:
                selector.unregister(key.fd)
                continue
            buffer = buffers[str(key.data)]
            buffer.extend(chunk[: limit_bytes + 1 - len(buffer)])
            if len(buffer) > limit_bytes:
                outcome = "limit"
                break
    selector.close()
    if outcome is None:
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            outcome = "timeout"
    if outcome is not None:
        _terminate_probe(process, grace_seconds)
    stdout, stderr = bytes(buffers["stdout"]), bytes(buffers["stderr"])
    process.stdout.close()
    process.stderr.close()
    return stdout, stderr, outcome


def check_floor(  # noqa: PLR0913 - the public probe signature is specification-bound.
    provider: str,
    executable: str,
    environment: Mapping[str, str],
    *,
    cwd: Path,
    verb: str,
    timeout_seconds: float = 10,
    limit_bytes: int = 4096,
    grace_seconds: float = 5,
) -> str:
    """Return the provider version, or raise a stable floor refusal."""

    if not isinstance(limit_bytes, int):
        raise TypeError("limit_bytes must be an integer")
    try:
        process = subprocess.Popen(
            [executable, "--version"],
            cwd=str(cwd),
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        message = (
            f"forge: {verb} refused — {provider} executable is unavailable: {executable}"
        )
        raise FloorRefusal(message, "unavailable") from exc
    stdout, stderr, outcome = _bounded_output(
        process, timeout_seconds, limit_bytes, grace_seconds
    )
    if outcome == "timeout":
        _refuse(
            f"forge: {verb} refused — {provider} version probe timed out "
            f"after {timeout_seconds} s",
            "timeout",
        )
    if outcome == "limit":
        _refuse(
            f"forge: {verb} refused — {provider} version probe output "
            f"exceeded {limit_bytes} bytes",
            "limit",
        )
    if process.returncode != 0:
        _refuse(
            f"forge: {verb} refused — {provider} version probe failed "
            f"with exit {process.returncode}",
            "exit",
        )
    match = _VERSION_RE.search(stdout + b"\n" + stderr)
    if match is None:
        _refuse(
            f"forge: {verb} refused — {provider} version output is unparseable",
            "unparseable",
        )
    version = tuple(int(part) for part in match.groups())
    floor = FLOORS[provider]
    rendered = ".".join(str(part) for part in version)
    if version < floor:
        required = ".".join(str(part) for part in floor)
        _refuse(
            f"forge: {verb} refused — {provider} version {rendered} "
            f"is below required {required}",
            "below",
        )
    return rendered


class _UsageError(RuntimeError):
    pass


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _UsageError(message)


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def _parser() -> _ArgumentParser:
    parser = _ArgumentParser(prog="route_floor.py")
    parser.add_argument("--repo", required=True, type=_absolute_path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the interpreter-invoked route-floor command."""

    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
    except _UsageError as exc:
        parser.print_usage(sys.stderr)
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return 2
    try:
        route_config = cast(Any, __import__("route_config"))
        resolution = route_config.load(arguments.repo, head="HEAD")
        support = route_config._probe_support()
        providers = sorted({str(route.provider) for route in resolution.routes})
        for provider in providers:
            environment = support._allowed_environment(provider)
            check_floor(
                provider,
                provider,
                environment,
                cwd=arguments.repo,
                verb="route floor",
            )
    except FloorRefusal as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
