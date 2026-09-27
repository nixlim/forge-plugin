from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path

from forge_cli.engine._review_wrapper import (
    _parse_macos_kinfo_start as _parse_macos_kinfo_start,
)
from forge_cli.engine._review_wrapper import (
    birth_identity as birth_identity,
)
from forge_cli.engine._review_wrapper import (
    parse_proc_stat as _wrapper_parse_proc_stat,
)


def parse_proc_stat(data: bytes) -> tuple[str, int, int]:
    return _wrapper_parse_proc_stat(data)


def _reaped_child(pid: int) -> bool:
    try:
        return os.waitpid(pid, os.WNOHANG)[0] == pid
    except (ChildProcessError, OSError):
        return False


def _linux_snapshot(pid: int) -> dict[str, object]:
    try:
        state, pgid, starttime = parse_proc_stat(
            Path(f"/proc/{pid}/stat").read_bytes()
        )
    except FileNotFoundError:
        return {"status": "gone"}
    except (OSError, UnicodeError, ValueError):
        return {"status": "identity-unproven"}
    birth = birth_identity(pid)
    if state == "Z":
        return {"status": "zombie", "pgid": pgid, "birth": birth}
    proven = birth is not None and birth.get("starttime") == starttime
    status = "alive" if proven else "identity-unproven"
    return {"status": status, "pgid": pgid, "birth": birth}


def _remaining_timeout(deadline: float | None) -> float | None:
    if deadline is None:
        return 2.0
    remaining = deadline - time.monotonic()
    return min(2.0, remaining) if remaining > 0 else None


def _darwin_process_state(pid: int, deadline: float | None) -> str | None:
    timeout = _remaining_timeout(deadline)
    if timeout is None:
        return None
    try:
        result = subprocess.run(
            ["/bin/ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    state = result.stdout.lstrip()[:1]
    return state if result.returncode == 0 and state else None


def _portable_snapshot(pid: int, deadline: float | None) -> dict[str, object]:
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return {"status": "gone"}
    except OSError:
        return {"status": "identity-unproven"}
    if sys.platform == "darwin":
        state = _darwin_process_state(pid, deadline)
        if state is None:
            return {"status": "identity-unproven"}
        if state == "Z":
            return {"status": "zombie", "pgid": pgid}
    birth = birth_identity(pid)
    status = "alive" if birth is not None else "identity-unproven"
    return {"status": status, "pgid": pgid, "birth": birth}


def process_snapshot(pid: int, deadline: float | None = None) -> dict[str, object]:
    if _reaped_child(pid):
        return {"status": "gone"}
    if sys.platform.startswith("linux"):
        return _linux_snapshot(pid)
    return _portable_snapshot(pid, deadline)


def process_probe(pid: int, expected_birth: object, expected_pgid: int) -> tuple[str, int]:
    snapshot = process_snapshot(pid)
    status = str(snapshot.get("status"))
    actual_pgid = snapshot.get("pgid")
    actual_birth = snapshot.get("birth")
    if status != "alive" or expected_birth is None:
        return ("identity-unproven" if status == "alive" else status), pid
    if isinstance(expected_birth, Mapping) and expected_birth.get("kind") == "linux-proc":
        if isinstance(actual_birth, Mapping) and actual_birth.get("boot_id") != expected_birth.get(
            "boot_id"
        ):
            return "boot-id-changed", pid
    if actual_birth != expected_birth or actual_pgid != expected_pgid:
        return "identity-mismatch", pid
    return "match", pid


def _linux_group_members(
    pgid: int, deadline: float | None
) -> tuple[tuple[int, ...], bool]:
    members: list[int] = []
    complete = True
    try:
        entries = os.scandir("/proc")
    except OSError:
        return (), False
    with entries:
        for entry in entries:
            if deadline is not None and time.monotonic() >= deadline:
                complete = False
                break
            if not entry.name.isdigit():
                continue
            try:
                state, group, _starttime = parse_proc_stat(
                    Path(f"/proc/{entry.name}/stat").read_bytes()
                )
            except FileNotFoundError:
                continue
            except (OSError, UnicodeError, ValueError):
                complete = False
                continue
            if group == pgid and state != "Z":
                members.append(int(entry.name))
    return tuple(sorted(set(members))), complete


def _mac_group_members(pgid: int, deadline: float | None) -> tuple[tuple[int, ...], bool]:
    timeout = _remaining_timeout(deadline)
    if timeout is None:
        return (), False
    try:
        result = subprocess.run(
            ["/usr/bin/pgrep", "-g", str(pgid)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return (), False
    if result.returncode not in (0, 1):
        return (), False
    members: list[int] = []
    complete = True
    for line in result.stdout.splitlines():
        if not line.isdigit():
            complete = False
            continue
        pid = int(line)
        status = process_snapshot(pid, deadline).get("status")
        if status == "alive":
            members.append(pid)
        elif status not in {"gone", "zombie"}:
            members.append(pid)
            complete = False
    return tuple(sorted(set(members))), complete


def group_members(pgid: int, deadline: float | None = None) -> tuple[tuple[int, ...], bool]:
    if sys.platform.startswith("linux"):
        return _linux_group_members(pgid, deadline)
    if sys.platform == "darwin":
        return _mac_group_members(pgid, deadline)
    return (), False


def wait_group_empty(pgid: int, seconds: float) -> tuple[tuple[int, ...], bool]:
    deadline = time.monotonic() + max(0.0, seconds)
    members: tuple[int, ...] = ()
    while True:
        if time.monotonic() >= deadline:
            return members, False
        members, complete = group_members(pgid, deadline)
        if complete and not members:
            return (), True
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def send_group_signal(pgid: int, sig: signal.Signals) -> str:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        return "gone"
    except OSError:
        return "denied"
    return "sent"
