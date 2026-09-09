"""Canonical runtime controls for the Forge CLI (cli split phase 2a, bead forge-plugin-95e.3).

Every module of the split reads these names by attribute through this one module, so a
single in-memory patch (``mock.patch.object(runtime, ...)``) disables a control everywhere:
the clock, the bounded process runner, the merge lifecycle flag, the Revision-9 state
controls, the path roots, the lazily imported coordination modules, and the fast-tier
mechanical-skip predicate. Definitions were moved verbatim from scripts/forge/cli.py.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import sys
import threading
import time
from typing import Any, Mapping, Sequence


COMMAND_TIMEOUT_SECONDS = 1200.0


OUTPUT_CAP_BYTES = 65536


_REQUIRED_REVISION9_STATE_CONTROLS = frozenset(
    {"run-binding-shape", "journal-outbox-shape"}
)


REVISION9_STATE_CONTROLS = _REQUIRED_REVISION9_STATE_CONTROLS


MERGE_LIFECYCLE_ACTIVE = False


_COORDINATION_MODULE_CACHE: tuple[Any, Any, Any] | None = None


_COORDINATION_MODULE_LOCK = threading.Lock()


# The shim's directory (scripts/forge), computed from this package file so the value
# is identical to the one the shim used to compute from its own __file__.
SCRIPT_DIR = Path(__file__).resolve().parents[1]


PLUGIN_ROOT = SCRIPT_DIR.parents[1]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _coordination_modules() -> tuple[Any, Any, Any]:
    """Load the task-03 package from the plugin's scripts parent on demand."""

    global _COORDINATION_MODULE_CACHE
    if _COORDINATION_MODULE_CACHE is not None:
        return _COORDINATION_MODULE_CACHE
    with _COORDINATION_MODULE_LOCK:
        if _COORDINATION_MODULE_CACHE is not None:
            return _COORDINATION_MODULE_CACHE
        scripts_parent = str(PLUGIN_ROOT / "scripts")
        if scripts_parent not in sys.path:
            sys.path.insert(0, scripts_parent)
        from codex_orchestrator import batch, builders, journal

        _COORDINATION_MODULE_CACHE = (batch, builders, journal)
        return _COORDINATION_MODULE_CACHE


@dataclasses.dataclass
class ProcessResult:
    argv: list[str]
    returncode: int
    duration_seconds: float
    output: bytes
    output_digest: str
    timed_out: bool = False
    output_limit: bool = False
    pid: int | None = None
    process_group_id: int | None = None
    process_group_survived: bool = False


def _process_group_exists(process_group: int) -> bool:
    """Return true unless process-group absence is proven by ``ESRCH``."""

    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.terminate()
        except OSError:
            return
    grace_deadline = time.monotonic() + 0.25
    try:
        process.wait(timeout=0.25)
    except subprocess.TimeoutExpired:
        pass
    remaining_grace = grace_deadline - time.monotonic()
    if remaining_grace > 0:
        time.sleep(remaining_grace)
    if not _process_group_exists(process.pid):
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.kill()
        except OSError:
            pass


def run_bounded(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float = COMMAND_TIMEOUT_SECONDS,
    cap: int = OUTPUT_CAP_BYTES,
    verbose: bool = False,
    input_bytes: bytes | None = None,
    watched_path: Path | None = None,
    watched_cap: int | None = None,
) -> ProcessResult:
    """Run one process group while bounding output, one artifact, and wall time."""

    if (watched_path is None) != (watched_cap is None) or (
        watched_cap is not None and watched_cap < 0
    ):
        raise ValueError("watched path and cap must be supplied together")
    watched_descriptor: int | None = None
    watched_identity: tuple[int, int] | None = None

    def open_watched_path() -> tuple[int, tuple[int, int]]:
        assert watched_path is not None
        descriptor = -1
        try:
            path_metadata = watched_path.lstat()
            if (
                not stat.S_ISREG(path_metadata.st_mode)
                or path_metadata.st_uid != os.geteuid()
            ):
                raise OSError("watched path is not owner-controlled and regular")
            descriptor = os.open(
                watched_path,
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            )
            metadata = os.fstat(descriptor)
            identity = (metadata.st_dev, metadata.st_ino)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or (path_metadata.st_dev, path_metadata.st_ino) != identity
            ):
                raise OSError("watched path changed while it was opened")
            return descriptor, identity
        except OSError:
            if descriptor >= 0:
                os.close(descriptor)
            raise

    if watched_path is not None:
        try:
            watched_descriptor, watched_identity = open_watched_path()
            metadata = os.fstat(watched_descriptor)
        except OSError as exc:
            raise ValueError("watched path is unavailable") from exc
        if metadata.st_size > int(watched_cap):
            os.close(watched_descriptor)
            watched_descriptor = None
            raise ValueError("watched path is not a bounded regular file")

    def watch_exceeded() -> bool:
        nonlocal watched_descriptor, watched_identity
        if watched_descriptor is None or watched_path is None:
            return False
        try:
            descriptor_metadata = os.fstat(watched_descriptor)
            path_metadata = watched_path.lstat()
        except OSError:
            return True
        if (
            not stat.S_ISREG(descriptor_metadata.st_mode)
            or descriptor_metadata.st_uid != os.geteuid()
            or descriptor_metadata.st_size > int(watched_cap)
            or not stat.S_ISREG(path_metadata.st_mode)
            or path_metadata.st_uid != os.geteuid()
        ):
            return True
        path_identity = (path_metadata.st_dev, path_metadata.st_ino)
        if path_identity == watched_identity:
            return False

        # ``codex exec --output-last-message`` may publish its final message
        # with an atomic rename.  Reopen the replacement without following a
        # symlink, prove the guarded name and descriptor still identify the
        # same owner-controlled regular file, and continue enforcing the cap
        # against that new inode.  Any ambiguous replacement remains a hard
        # process-bound violation.
        try:
            replacement, replacement_identity = open_watched_path()
            replacement_metadata = os.fstat(replacement)
        except OSError:
            return True
        if replacement_metadata.st_size > int(watched_cap):
            os.close(replacement)
            return True
        previous = watched_descriptor
        watched_descriptor = replacement
        watched_identity = replacement_identity
        os.close(previous)
        return False

    def truncate_watched_evidence() -> None:
        if watched_descriptor is None or watched_path is None:
            return
        retained = int(watched_cap) + 1
        try:
            if os.fstat(watched_descriptor).st_size > retained:
                os.ftruncate(watched_descriptor, retained)
        except OSError:
            pass
        try:
            path_metadata = watched_path.lstat()
        except OSError:
            return
        if (
            not stat.S_ISREG(path_metadata.st_mode)
            or path_metadata.st_uid != os.geteuid()
            or (path_metadata.st_dev, path_metadata.st_ino) == watched_identity
        ):
            return
        replacement: int | None = None
        try:
            replacement = os.open(
                watched_path,
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            )
            replacement_metadata = os.fstat(replacement)
            if (
                stat.S_ISREG(replacement_metadata.st_mode)
                and replacement_metadata.st_uid == os.geteuid()
                and (
                    replacement_metadata.st_dev,
                    replacement_metadata.st_ino,
                )
                == (path_metadata.st_dev, path_metadata.st_ino)
                and replacement_metadata.st_size > retained
            ):
                os.ftruncate(replacement, retained)
        except OSError:
            pass
        finally:
            if replacement is not None:
                os.close(replacement)

    started = time.monotonic()
    try:
        process = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=dict(env) if env is not None else None,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except BaseException:
        if watched_descriptor is not None:
            os.close(watched_descriptor)
        raise
    writer: threading.Thread | None = None
    selector: selectors.BaseSelector | None = None
    watched_limit = False
    try:
        try:
            if input_bytes is not None:
                assert process.stdin is not None

                def write_input() -> None:
                    try:
                        view = memoryview(input_bytes)
                        while view:
                            written = process.stdin.write(view)
                            if written is None or written <= 0:
                                break
                            view = view[written:]
                        process.stdin.flush()
                    except (BrokenPipeError, OSError, ValueError):
                        pass
                    finally:
                        try:
                            process.stdin.close()
                        except OSError:
                            pass

                pending_writer = threading.Thread(target=write_input, daemon=True)
                pending_writer.start()
                writer = pending_writer
            assert process.stdout is not None
            descriptor = process.stdout.fileno()
            os.set_blocking(descriptor, False)
            selector = selectors.DefaultSelector()
            selector.register(descriptor, selectors.EVENT_READ)
            kept = bytearray()
            digest = hashlib.sha256()
            total = 0
            timed_out = False
            output_limit = False
            eof = False
            while not eof:
                if not watched_limit and watch_exceeded():
                    watched_limit = True
                    output_limit = True
                    _kill_process_group(process)
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    timed_out = True
                    _kill_process_group(process)
                    remaining = 0
                events = selector.select(min(max(remaining, 0.0), 0.1))
                if not events:
                    if timed_out:
                        break
                    if process.poll() is not None:
                        try:
                            chunk = os.read(descriptor, 8192)
                        except BlockingIOError:
                            continue
                        if not chunk:
                            eof = True
                            break
                        events = [(None, None)]
                    else:
                        continue
                if events and events[0][0] is None:
                    # The post-exit drain above already populated ``chunk``.
                    chunks = [chunk]
                else:
                    chunks = []
                    while True:
                        try:
                            part = os.read(descriptor, 8192)
                        except BlockingIOError:
                            break
                        if not part:
                            eof = True
                            break
                        chunks.append(part)
                for part in chunks:
                    digest.update(part)
                    total += len(part)
                    if len(kept) < cap:
                        kept.extend(part[: cap - len(kept)])
                    if verbose:
                        sys.stderr.write(part.decode("utf-8", "replace"))
                        sys.stderr.flush()
                    if total > cap and not output_limit:
                        output_limit = True
                        _kill_process_group(process)
                if output_limit:
                    # Drain whatever was already in the pipe, without waiting on
                    # the terminated producer.
                    if process.poll() is not None and not chunks:
                        break
            if not watched_limit and watch_exceeded():
                watched_limit = True
                output_limit = True
                _kill_process_group(process)
            try:
                returncode = process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                _kill_process_group(process)
                returncode = process.wait()
        finally:
            if watched_limit:
                truncate_watched_evidence()
            if selector is not None:
                selector.close()
            if process.stdout is not None:
                process.stdout.close()
            if writer is not None:
                writer.join(timeout=0.5)
            if watched_descriptor is not None:
                os.close(watched_descriptor)
        process_group_survived = _process_group_exists(process.pid)
        if process_group_survived:
            _kill_process_group(process)
        return ProcessResult(
            argv=list(argv),
            returncode=returncode,
            duration_seconds=time.monotonic() - started,
            output=bytes(kept),
            output_digest=digest.hexdigest(),
            timed_out=timed_out,
            output_limit=output_limit,
            pid=process.pid,
            process_group_id=process.pid,
            process_group_survived=process_group_survived,
        )
    except BaseException:
        _kill_process_group(process)
        process.wait()
        raise


def _fast_mechanical_skips(state: Mapping[str, Any]) -> list[str]:
    if state["tier"].get("effective") != "fast":
        return []
    skips = state["steps"].get("user_skips", {})
    if not isinstance(skips, dict):
        return []
    return sorted(str(gate_id) for gate_id in skips if gate_id != "review")


# Late-bound seam (cli split phase 2b): the shim assigns its
# _build_chain_journal_records here at import time so chain_core can drain chain
# outboxes without importing the shim; tests patch the seam on this module. When
# several shim instances are loaded in one process (tests only), the seam holds the
# most recently loaded shim's builder; production runs exactly one shim.
_build_chain_journal_records: Any = None


__all__ = [
    '_build_chain_journal_records',
    'COMMAND_TIMEOUT_SECONDS',
    'MERGE_LIFECYCLE_ACTIVE',
    'OUTPUT_CAP_BYTES',
    'PLUGIN_ROOT',
    'ProcessResult',
    'REVISION9_STATE_CONTROLS',
    'SCRIPT_DIR',
    '_COORDINATION_MODULE_CACHE',
    '_COORDINATION_MODULE_LOCK',
    '_REQUIRED_REVISION9_STATE_CONTROLS',
    '_coordination_modules',
    '_fast_mechanical_skips',
    '_kill_process_group',
    '_process_group_exists',
    'run_bounded',
    'utc_now',
]
