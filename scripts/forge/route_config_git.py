"""Bounded, environment-scrubbed Git calls for route configuration."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

SCRUBBED_GIT_ENVIRONMENT = frozenset(
    {
        "GIT_DIR",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_WORK_TREE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    }
)


class RouteRefusal(RuntimeError):
    """A fail-closed route configuration refusal."""


def _git_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in SCRUBBED_GIT_ENVIRONMENT:
        environment.pop(name, None)
    return environment


def _signal_group(process: subprocess.Popen[bytes], signum: signal.Signals) -> None:
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def _stop_group(process: subprocess.Popen[bytes], timeout: float) -> None:
    grace = max(0.01, min(timeout, 1.0))
    _signal_group(process, signal.SIGTERM)
    time.sleep(grace)
    _signal_group(process, signal.SIGKILL)
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        process.kill()
    if process.stdout is not None:
        process.stdout.close()


def run_git(
    repo: Path,
    *arguments: str,
    timeout: float,
    resolution: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    """Run Git for ``repo`` with fixed bounds and no ambient repository selectors."""

    command = ["git", "-C", str(repo), *arguments]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_git_environment(),
        start_new_session=True,
    )
    try:
        stdout, _stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _stop_group(process, timeout)
        subject = "route resolution" if resolution else "routes file"
        raise RouteRefusal(f"forge: {subject} refused — git timed out") from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, None)


def git_path(repo: Path, argument: str, *, timeout: float) -> Path:
    """Resolve one Git path query or refuse as unreadable."""

    result = run_git(repo, "rev-parse", argument, timeout=timeout)
    if result.returncode != 0:
        raise RouteRefusal("forge: routes file refused — unreadable")
    try:
        raw = result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RouteRefusal("forge: routes file refused — unreadable") from exc
    if not raw:
        raise RouteRefusal("forge: routes file refused — unreadable")
    path = Path(raw)
    return (path if path.is_absolute() else repo / path).resolve()
