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
    try:
        process.wait(timeout=0.25)
        return
    except subprocess.TimeoutExpired:
        pass
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
) -> ProcessResult:
    """Run one process group while bounding combined output and wall time."""

    started = time.monotonic()
    process = subprocess.Popen(
        list(argv),
        cwd=str(cwd),
        env=dict(env) if env is not None else None,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
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
    try:
        while not eof:
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
        try:
            returncode = process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            _kill_process_group(process)
            returncode = process.wait()
    finally:
        selector.close()
        process.stdout.close()
    return ProcessResult(
        argv=list(argv),
        returncode=returncode,
        duration_seconds=time.monotonic() - started,
        output=bytes(kept),
        output_digest=digest.hexdigest(),
        timed_out=timed_out,
        output_limit=output_limit,
    )


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
    'run_bounded',
    'utc_now',
]
