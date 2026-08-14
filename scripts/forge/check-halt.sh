#!/usr/bin/env bash
# Operator halt check (kill-switch).
#
# Usage: check-halt.sh [scope]
#   Always checks AGENT_HALT. When scope is non-empty, also checks
#   AGENT_HALT_<scope>. Both sentinels live at the main-checkout root shared by
#   every linked worktree.
#
# Exit 0 = clear to proceed. Exit 1 = a halt is engaged.
# forge: modified from upstream — audit state is re-rooted to .forge/tmp for plugin-local governance state
set -uo pipefail

scope="${1:-}"
probe_only="${FORGE_HALT_PROBE_ONLY:-0}"

if ! common_dir="$(git rev-parse --git-common-dir 2>/dev/null)"; then
    echo "forge: warning: outside a git repository — halt check skipped" >&2
    exit 0
fi

if [[ "$common_dir" != /* ]]; then
    common_dir="$(pwd)/$common_dir"
fi

if ! common_dir="$(cd "$common_dir" 2>/dev/null && pwd -P)"; then
    echo "forge: warning: could not resolve the git common directory — halt check skipped" >&2
    exit 0
fi

main_root="$(cd "$(dirname "$common_dir")" && pwd -P)" || {
    echo "forge: warning: could not resolve the main checkout — halt check skipped" >&2
    exit 0
}

sentinels=("$main_root/AGENT_HALT")
if [[ -n "$scope" ]]; then
    sentinels+=("$main_root/AGENT_HALT_$scope")
fi

# Agents must never create, delete, or bypass halt sentinels without explicit
# user direction.
for sentinel_path in "${sentinels[@]}"; do
    [[ -f "$sentinel_path" ]] || continue

    # The commit guard probes first so it can deliver its deny JSON before
    # asking this script to perform the advisory audit/event append.
    if [[ "$probe_only" == "1" ]]; then
        exit 1
    fi

    sentinel_name="${sentinel_path##*/}"
    echo "forge: operator halt engaged ($sentinel_name)" >&2
    echo "AI SDLC activity is paused. Do not start new work, commit, push, or" >&2
    echo "perform external or irreversible actions. Sentinel reason (if given):" >&2
    echo "----" >&2
    cat "$sentinel_path" >&2 2>/dev/null || true

    # Prepare the immutable event identity, then detach the advisory append.
    # The worker waits for this halt-check PID to disappear, so the caller
    # observes exit 1 before writer registration and the lock-free append.
    halt_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    mkdir -p "$main_root/.forge/tmp" 2>/dev/null || true
    printf '%s halt detected (pid %s, cwd %s, sentinel %s)\n' \
        "$halt_at" "$$" "$(pwd)" "$sentinel_name" \
        >>"$main_root/.forge/tmp/halt-audit.log" 2>/dev/null || true
    halt_candidate=""
    staged_file="$(mktemp "${TMPDIR:-/tmp}/forge-halt-staged.XXXXXX")" || staged_file=""
    if [[ -n "$staged_file" ]] && git diff --cached >"$staged_file" 2>/dev/null; then
        halt_candidate="$(shasum -a 256 <"$staged_file" 2>/dev/null | awk '{print $1}')" || halt_candidate=""
    fi
    [[ -z "$staged_file" ]] || rm -f "$staged_file"
    halt_policy_sha="$(git rev-parse HEAD 2>/dev/null)" || halt_policy_sha=""
    [[ "$halt_policy_sha" =~ ^[0-9a-f]{40}$ || "$halt_policy_sha" =~ ^[0-9a-f]{64}$ ]] || halt_policy_sha=""
    plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
    pending_event=""
    # Give the detached worker a private FIFO read end. The temporary RDWR
    # descriptor makes both endpoint opens nonblocking; after launcher success
    # it is closed and the FIFO pathname is removed. This halt-check shell then
    # owns the only write end, so EOF cannot reach the worker until process
    # teardown closes that descriptor.
    halt_exit_dir=""
    halt_exit_fifo=""
    if halt_exit_dir="$(mktemp -d "${TMPDIR:-/tmp}/forge-halt-exit.XXXXXX" 2>/dev/null)"; then
        halt_exit_fifo="$halt_exit_dir/exit"
    else
        halt_exit_dir=""
    fi
    halt_exit_dummy=""
    halt_exit_write=""
    halt_worker_launched=0
    if [[ -n "$halt_exit_dir" ]] && mkfifo -m 600 "$halt_exit_fifo" 2>/dev/null && \
        exec {halt_exit_dummy}<>"$halt_exit_fifo" && \
        exec {halt_exit_write}>"$halt_exit_fifo" && \
        python3 /dev/fd/3 "$halt_exit_fifo" \
        "$pending_event" "$main_root/.forge/tmp/halt-audit.log" \
        "$plugin_root/scripts/forge/emit-decision-event.py" \
        "$halt_at" "$halt_candidate" "$halt_policy_sha" "$sentinel_name" \
        {halt_exit_dummy}>&- {halt_exit_write}>&- 3<<'PY'
import os
from pathlib import Path
import stat
import subprocess
import sys

fifo = sys.argv[1]
pending, audit, emitter, at, candidate, policy_sha, reason = sys.argv[2:]
try:
    fifo_stat = os.lstat(fifo)
    if not __import__("stat").S_ISFIFO(fifo_stat.st_mode):
        raise OSError("exit gate is not a FIFO")
    read_fd = os.open(fifo, os.O_RDONLY)
    read_stat = os.fstat(read_fd)
    if (fifo_stat.st_dev, fifo_stat.st_ino) != (read_stat.st_dev, read_stat.st_ino):
        raise OSError("exit gate identity changed")
except OSError:
    raise SystemExit(1)
worker = r'''
import os
from pathlib import Path
import stat
import subprocess
import sys

read_fd = int(sys.argv[1])
pending = Path(sys.argv[2]) if sys.argv[2] else None
audit = Path(sys.argv[3])
marker_fd = int(sys.argv[4]) if sys.argv[4] else None

def marker_matches():
    if pending is None or marker_fd is None:
        return False
    try:
        path_stat = pending.stat(follow_symlinks=False)
        fd_stat = os.fstat(marker_fd)
    except OSError:
        return False
    return path_stat.st_dev == fd_stat.st_dev and path_stat.st_ino == fd_stat.st_ino

def write_marker(payload):
    if marker_fd is None:
        return False
    try:
        encoded = payload.encode("utf-8")
        os.lseek(marker_fd, 0, os.SEEK_SET)
        if os.write(marker_fd, encoded) != len(encoded):
            raise OSError("short marker write")
        os.ftruncate(marker_fd, len(encoded))
        os.fsync(marker_fd)
        return True
    except OSError:
        return False

def publish_failure_marker(payload):
    if pending is None:
        return False
    failed_path = pending.with_name(
        pending.name.replace("halt-event-pending.", "halt-event-failed.", 1)
    )
    descriptor = None
    try:
        descriptor = os.open(
            failed_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        encoded = payload.encode("utf-8")
        if os.write(descriptor, encoded) != len(encoded):
            raise OSError("short failure-marker write")
        os.fsync(descriptor)
        path_stat = failed_path.stat(follow_symlinks=False)
        fd_stat = os.fstat(descriptor)
        if not (
            stat.S_ISREG(path_stat.st_mode)
            and stat.S_ISREG(fd_stat.st_mode)
            and path_stat.st_dev == fd_stat.st_dev
            and path_stat.st_ino == fd_stat.st_ino
        ):
            raise OSError("failure-marker identity changed")
        return True
    except OSError:
        if descriptor is not None:
            try:
                path_stat = failed_path.stat(follow_symlinks=False)
                fd_stat = os.fstat(descriptor)
                if (
                    path_stat.st_dev == fd_stat.st_dev
                    and path_stat.st_ino == fd_stat.st_ino
                ):
                    failed_path.unlink()
            except OSError:
                pass
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)

armed = b""
while True:
    chunk = os.read(read_fd, 4096)
    if not chunk:
        break
    armed += chunk
os.close(read_fd)
if armed != b"\x01":
    raise SystemExit(0)
try:
    result = subprocess.run(
        sys.argv[5:], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, check=False,
    )
    raw_diagnostic = result.stderr.decode("utf-8", "replace")
except OSError:
    result = None
    raw_diagnostic = ""
audit_unavailable = "forge: decision event failure audit unavailable" in raw_diagnostic
diagnostic_lines = [
    line for line in raw_diagnostic.splitlines()
    if "decision event append skipped" in line
]
diagnostic = diagnostic_lines[-1] + "\n" if diagnostic_lines else ""
failed = bool(diagnostic_lines) or result is None or result.returncode != 0
if not failed:
    if marker_matches():
        try: pending.unlink()
        except OSError: pass
    raise SystemExit(0)
if not diagnostic:
    diagnostic = "forge: decision event append skipped (event-append-launch-failed)\n"
outcome_written = write_marker(diagnostic)
if outcome_written:
    if marker_matches():
        failed_path = pending.with_name(pending.name.replace("halt-event-pending.", "halt-event-failed.", 1))
        try:
            pending.replace(failed_path)
            raise SystemExit(0)
        except OSError:
            pass
elif publish_failure_marker(diagnostic):
    if marker_matches():
        try:
            pending.unlink()
        except OSError:
            pass
    raise SystemExit(0)
if result is not None and result.returncode == 0 and not audit_unavailable:
    # The emitter already durably counted this append failure. A second
    # fallback append here would duplicate it when no marker exists.
    raise SystemExit(0)
try:
    fd = os.open(audit, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    code_prefix = "decision event append skipped ("
    code_start = diagnostic.find(code_prefix)
    code = "event-append-launch-failed"
    if code_start >= 0:
        code_start += len(code_prefix)
        code_end = diagnostic.find(")", code_start)
        if code_end >= 0:
            extracted = diagnostic[code_start:code_end]
            if extracted.startswith("code "):
                extracted = extracted[len("code "):]
            if extracted:
                code = extracted
    payload = (
        sys.argv[8] + " decision event append skipped (code " + code + ")\n"
    ).encode("utf-8")
    try:
        if os.write(fd, payload) != len(payload): raise OSError("short audit write")
    finally:
        os.close(fd)
except OSError:
    pass
'''
marker_fd = None
if not pending:
    pending_dir = Path(audit).parent
    marker_path = None
    try:
        pending_dir.mkdir(parents=True, exist_ok=True)
        for _ in range(8):
            marker_path = pending_dir / (
                "halt-event-pending." + str(os.getpid()) + "-" + os.urandom(16).hex()
            )
            try:
                marker_fd = os.open(
                    marker_path,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
            except FileExistsError:
                continue
            pending = str(marker_path)
            payload = (
                "forge: decision event outcome pending "
                "(code event-append-outcome-unconfirmed)\n"
            ).encode("utf-8")
            if os.write(marker_fd, payload) != len(payload):
                raise OSError("short pending-marker write")
            os.fsync(marker_fd)
            marker_stat = os.lstat(pending)
            fd_stat = os.fstat(marker_fd)
            if (marker_stat.st_dev, marker_stat.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
                raise OSError("pending marker identity changed")
            break
    except OSError:
        if marker_path is not None and marker_fd is not None:
            try:
                marker_stat = os.lstat(marker_path)
                fd_stat = os.fstat(marker_fd)
                if (marker_stat.st_dev, marker_stat.st_ino) == (fd_stat.st_dev, fd_stat.st_ino):
                    marker_path.unlink()
            except OSError:
                pass
        if marker_fd is not None:
            os.close(marker_fd)
        marker_fd = None
        pending = ""
pass_fds = [read_fd]
if marker_fd is not None:
    pass_fds.append(marker_fd)
process = subprocess.Popen(
    [sys.executable, "-c", worker, str(read_fd), pending, audit,
     "" if marker_fd is None else str(marker_fd),
     sys.executable, emitter, "--at", at, "--candidate", candidate,
     "--event", "halt_event", "--policy-sha", policy_sha,
     "--reason", reason, "--surface", "check-halt"],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    close_fds=True, pass_fds=tuple(pass_fds), start_new_session=True,
)
if marker_fd is not None:
    os.close(marker_fd)
PY
    then
        if printf '\1' >&"$halt_exit_write" 2>/dev/null; then
            halt_worker_launched=1
        fi
    fi
    [[ -z "$halt_exit_dummy" ]] || exec {halt_exit_dummy}>&-
    [[ -z "$halt_exit_fifo" ]] || rm -f -- "$halt_exit_fifo" 2>/dev/null || true
    [[ -z "$halt_exit_dir" ]] || rmdir "$halt_exit_dir" 2>/dev/null || true
    if [[ "$halt_worker_launched" != "1" ]]; then
        [[ -z "$halt_exit_write" ]] || exec {halt_exit_write}>&-
        printf '%s %s\n' "$halt_at" \
            'forge: decision event append skipped (event-append-launch-failed)' \
            >>"$main_root/.forge/tmp/halt-audit.log" 2>/dev/null || true
    fi
    exit 1
done

exit 0
