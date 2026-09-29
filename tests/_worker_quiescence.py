from __future__ import annotations

import os
import signal
import time
from pathlib import Path

PENDING_PATTERNS = (
    "decision-event-pending.*",
    "halt-event-pending.*",
)
QUIESCENCE_DEADLINE_SECONDS = 60.0
_POLL_SECONDS = 0.05
_KILL_WAIT_SECONDS = 5.0
_PROC = Path("/proc")
_ProcessStatus = tuple[bytes, bytes]
_ProcessDetails = tuple[int, int, bytes, str]


def _parse_process_status(stat: bytes) -> _ProcessStatus | None:
    closing_paren = stat.rfind(b")")
    if closing_paren < 0 or stat[closing_paren + 1 : closing_paren + 2] != b" ":
        return None
    fields = stat[closing_paren + 2 :].split()
    if len(fields) < 20:
        return None
    return fields[0], fields[19]


def _process_status(process_dir: Path) -> _ProcessStatus | None:
    try:
        stat = (process_dir / "stat").read_bytes()
    except OSError:
        return None
    return _parse_process_status(stat)


def _cwd_is_inside(process_dir: Path, root: Path) -> bool:
    try:
        cwd = (process_dir / "cwd").resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    return cwd == root or root in cwd.parents


def resident_processes(root: Path) -> list[int] | None:
    """Return non-zombie processes resident below root.

    Linux exposes this through ``/proc/<pid>/cwd``. On macOS and other hosts
    without procfs, return ``None`` so callers deliberately fall back to the
    pending-marker protocol.
    """
    if not (_PROC / "self" / "cwd").exists():
        return None
    resolved_root = root.resolve()
    residents: list[int] = []
    try:
        entries = list(_PROC.iterdir())
    except OSError:
        return None
    for process_dir in entries:
        if not process_dir.name.isdecimal():
            continue
        pid = int(process_dir.name)
        status = _process_status(process_dir)
        if pid == os.getpid() or status is None or status[0] == b"Z":
            continue
        if _cwd_is_inside(process_dir, resolved_root):
            residents.append(pid)
    return sorted(residents)


def _pending_markers(root: Path) -> list[Path]:
    markers: set[Path] = set()
    for pattern in PENDING_PATTERNS:
        try:
            markers.update(root.rglob(pattern))
        except OSError:
            continue
    return sorted(markers, key=str)


def _read_cmdline(pid: int) -> str:
    try:
        with (_PROC / str(pid) / "cmdline").open("rb") as handle:
            payload = handle.read(4096)
    except OSError:
        return "<unavailable>"
    return payload.replace(b"\0", b" ").decode("utf-8", "replace").strip()


def _identity_matches(root: Path, details: _ProcessDetails) -> bool:
    pid, pgid, start_time, _cmdline = details
    process_dir = _PROC / str(pid)
    status = _process_status(process_dir)
    if status is None or status[0] == b"Z" or status[1] != start_time:
        return False
    if not _cwd_is_inside(process_dir, root):
        return False
    try:
        return os.getpgid(pid) == pgid
    except OSError:
        return False


def _process_details(root: Path, pids: list[int]) -> list[_ProcessDetails]:
    details: list[_ProcessDetails] = []
    for pid in pids:
        process_dir = _PROC / str(pid)
        status = _process_status(process_dir)
        if status is None or status[0] == b"Z" or not _cwd_is_inside(process_dir, root):
            continue
        try:
            pgid = os.getpgid(pid)
        except OSError:
            continue
        observed = (pid, pgid, status[1], _read_cmdline(pid))
        if _identity_matches(root, observed):
            details.append(observed)
    return details


def _kill_processes(root: Path, details: list[_ProcessDetails]) -> None:
    current_group = os.getpgid(0)
    for details_item in details:
        pid, pgid, _start_time, _cmdline = details_item
        if not _identity_matches(root, details_item):
            continue
        try:
            if pgid == pid and pgid != current_group:
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        except OSError:
            continue


def _wait_for_process_exit(root: Path, details: list[_ProcessDetails]) -> None:
    expires_at = time.monotonic() + _KILL_WAIT_SECONDS
    while any(_identity_matches(root, item) for item in details):
        remaining = expires_at - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(_POLL_SECONDS, remaining))


def _fail_quiescence(root: Path, markers: list[Path], pids: list[int]) -> None:
    details = _process_details(root, pids)
    displayed = [(pid, pgid, cmdline) for pid, pgid, _start, cmdline in details]
    _kill_processes(root, details)
    _wait_for_process_exit(root, details)
    raise AssertionError(
        f"worker quiescence deadline expired for {root}: "
        f"markers={[str(marker) for marker in markers]!r}; "
        f"processes={displayed!r}; resident_pids={pids!r}"
    )


def wait_for_quiescence(
    root: Path,
    deadline: float = QUIESCENCE_DEADLINE_SECONDS,
) -> None:
    root = root.resolve()
    expires_at = time.monotonic() + deadline
    while True:
        markers = _pending_markers(root)
        residents = resident_processes(root)
        pids = residents or []
        if not markers and not pids:
            return
        remaining = expires_at - time.monotonic()
        if remaining <= 0:
            _fail_quiescence(root, markers, pids)
            return
        time.sleep(min(_POLL_SECONDS, remaining))
