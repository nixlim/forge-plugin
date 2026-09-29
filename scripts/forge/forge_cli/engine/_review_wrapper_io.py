"""Stdlib-only concurrent stream pump for the detached review wrapper.

``wrapper_source`` appends this module before the wrapper's ``__main__`` guard,
so the launched ``-c`` program stays one source string.  The package wrapper's
conditional import exposes the same helpers to ordinary callers and tests.
"""

import datetime
import errno
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from typing import Any

_EXTERNAL_TERM = False
_SELF_TERMINATING = False
COMPLETION_SCHEMA = "forge-review-process/2"
EVENTS_LIMIT_BYTES = 16 * 1024 * 1024
STDERR_LIMIT_BYTES = 1024 * 1024
STREAM_DRAIN_SECONDS = 1.0
_STATUS_401 = re.compile(rb"(?<![0-9])401(?![0-9])")
_DEFAULT_LEAVES = {
    "prompt": "prompt.txt",
    "events": "events.jsonl",
    "stderr": "stderr.log",
    "capture": "verdict.txt",
    "staging": "verdict.staging",
}
_RESERVED_LEAVES = frozenset({
    "completion.json",
    "identity.json",
    "package.txt",
    "review-final-body.md",
    "stale.json",
})


def parse_proc_stat(data: bytes) -> tuple[str, int, int]:
    closing = data.rfind(b")")
    if closing < 1 or data[closing + 1 : closing + 2] != b" ":
        raise ValueError("malformed proc stat")
    suffix = data[closing + 2 :].decode("ascii").split()
    if len(suffix) < 20 or len(suffix[0]) != 1:
        raise ValueError("malformed proc stat")
    return suffix[0], int(suffix[2]), int(suffix[19])


def open_owner_regular(directory: int, name: str, flags: int, mode: int = 0o600) -> int:
    if not name or "/" in name or name in {".", ".."}:
        raise OSError("unsafe attempt leaf")
    safe_flags = (
        flags | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(name, safe_flags, mode, dir_fd=directory)
    except OSError as exc:
        if exc.errno == errno.ENXIO:
            raise OSError("unsafe attempt file") from exc
        raise
    try:
        opened = os.fstat(descriptor)
        unsafe = not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid()
        if unsafe or opened.st_mode & 0o077:
            raise OSError("unsafe attempt file")
        os.set_blocking(descriptor, True)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _valid_attempt_leaf(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and "/" not in value
        and value not in {".", ".."}
        and "\x00" not in value
    )


def _distinct_attempt_leaves(leaves: dict[str, str]) -> bool:
    return len(set(leaves.values())) == len(leaves)


def _leaves_avoid_control_artifacts(leaves: dict[str, str]) -> bool:
    return set(leaves.values()).isdisjoint(_RESERVED_LEAVES)


def _known_leaf_keys(value: dict[object, object]) -> bool:
    return set(value) == set(_DEFAULT_LEAVES)


def _events_existing(config: dict[str, object]) -> bool:
    value = config.get("events_existing", False)
    if type(value) is not bool:
        raise ValueError("launch configuration")
    return value


def _wrapper_options(config: dict[str, object]) -> tuple[dict[str, str], bool]:
    if "leaves" not in config:
        leaves = dict(_DEFAULT_LEAVES)
    else:
        raw = config["leaves"]
        if not isinstance(raw, dict) or not _known_leaf_keys(raw):
            raise ValueError("launch configuration")
        if not all(_valid_attempt_leaf(value) for value in raw.values()):
            raise ValueError("launch configuration")
        leaves = {name: str(raw[name]) for name in _DEFAULT_LEAVES}
    if not _distinct_attempt_leaves(leaves) or not _leaves_avoid_control_artifacts(leaves):
        raise ValueError("launch configuration")
    return leaves, _events_existing(config)


def _failure_leaves(config: dict[str, object]) -> dict[str, str]:
    try:
        return _wrapper_options(config)[0]
    except (TypeError, ValueError):
        return dict(_DEFAULT_LEAVES)


def _events_file_empty(descriptor: int) -> bool:
    return os.fstat(descriptor).st_size == 0


def _open_events(
    directory: int, name: str, existing: bool, opener: Any
) -> int:
    flags = os.O_WRONLY | os.O_APPEND
    if not existing:
        flags |= os.O_CREAT | os.O_EXCL
    descriptor = opener(directory, name, flags)
    if existing and not _events_file_empty(descriptor):
        os.close(descriptor)
        raise OSError("existing events file is not empty")
    return descriptor


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short stream write")
        view = view[written:]


def _persist_stream(state: dict[str, Any], label: str, data: bytes) -> bool:
    """Persist one already-redacted chunk without crossing its durable cap."""

    if not state["persisting"]:
        return False
    limit = state["limits"][label]
    if state["written"][label] + len(data) > limit:
        state["error"] = "events cap" if label == "stdout" else "stderr cap"
        state["persisting"] = False
        return False
    descriptor = state["events_fd" if label == "stdout" else "stderr_fd"]
    _write_all(descriptor, data)
    state["written"][label] += len(data)
    return True


def _close_registered(selector: selectors.BaseSelector, stream: Any) -> None:
    try:
        selector.unregister(stream)
    except (KeyError, ValueError):
        pass
    stream.close()


def _register(
    selector: selectors.BaseSelector,
    stream: Any,
    events: int,
    label: str,
) -> None:
    if stream is None:
        raise OSError("missing reviewer pipe")
    os.set_blocking(stream.fileno(), False)
    selector.register(stream, events, label)


def _persist_stdout_line(
    state: dict[str, Any], raw: bytes, terminated: bool
) -> None:
    if _codex_auth_event(raw):
        state["capture"].codex_auth = True
    persisted, error = state["capture"].line_bytes(raw, terminated=terminated)
    if error and error.startswith("bad line "):
        framed = raw + b"\n"
        persisted = state["stdout_redactor"].feed(framed, final=not terminated)
    if _persist_stream(state, "stdout", persisted):
        state["error"] = error
        state["persisting"] = error is None


def _status_401(value: bytes) -> bool:
    return _STATUS_401.search(value) is not None


def _codex_auth_event(raw: bytes) -> bool:
    try:
        event = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        return False
    return (
        isinstance(event, dict)
        and event.get("type") == "error"
        and _status_401(raw)
    )


def _consume_stdout(state: dict[str, Any], chunk: bytes, *, final: bool = False) -> None:
    state["stdout_buffer"].extend(chunk)
    buffer = state["stdout_buffer"]
    while b"\n" in buffer and state["error"] is None:
        raw, _, remainder = buffer.partition(b"\n")
        buffer[:] = remainder
        _persist_stdout_line(state, raw, True)
    if final and state["error"] is None and buffer:
        raw = bytes(buffer)
        buffer.clear()
        _persist_stdout_line(state, raw, False)
    if final and state["error"] is None:
        error = state["capture"].final_error()
        if error is not None:
            state["error"] = error
            state["persisting"] = False


def _consume_stderr(state: dict[str, Any], chunk: bytes, *, final: bool = False) -> None:
    if chunk:
        state["stderr_raw"].extend(chunk)
    redacted = state["stderr_redactor"].feed(chunk, final=final)
    _persist_stream(state, "stderr", redacted)


def _read_pipe(
    state: dict[str, Any],
    key: selectors.SelectorKey,
    selector: selectors.BaseSelector,
) -> None:
    label = str(key.data)
    stream: Any = key.fileobj
    try:
        chunk = os.read(stream.fileno(), 65_536)
    except BlockingIOError:
        return
    if not chunk:
        if label == "stdout":
            _consume_stdout(state, b"", final=True)
        else:
            _consume_stderr(state, b"", final=True)
        _close_registered(selector, stream)
        return
    state["read"][label] += len(chunk)
    if state["read"][label] > state["limits"][label]:
        state["error"] = "events cap" if label == "stdout" else "stderr cap"
        state["persisting"] = False
    elif label == "stdout":
        _consume_stdout(state, chunk)
    else:
        _consume_stderr(state, chunk)


def _write_prompt(
    state: dict[str, Any],
    key: selectors.SelectorKey,
    selector: selectors.BaseSelector,
) -> None:
    stream: Any = key.fileobj
    try:
        remaining = state["prompt"][state["prompt_offset"] :]
        state["prompt_offset"] += os.write(stream.fileno(), remaining)
    except BrokenPipeError:
        state["prompt_offset"] = len(state["prompt"])
    if state["prompt_offset"] >= len(state["prompt"]):
        _close_registered(selector, stream)


def _consume_ready(
    state: dict[str, Any],
    key: selectors.SelectorKey,
    selector: selectors.BaseSelector,
) -> None:
    if key.data == "stdin":
        _write_prompt(state, key, selector)
    else:
        _read_pipe(state, key, selector)


def _finish_buffers(state: dict[str, Any]) -> None:
    _consume_stdout(state, b"", final=True)
    if state["error"] is None:
        _consume_stderr(state, b"", final=True)


def _close_selector(selector: selectors.BaseSelector) -> None:
    for key in list(selector.get_map().values()):
        _close_registered(selector, key.fileobj)
    selector.close()


def _reviewer_streams_open(selector: selectors.BaseSelector) -> bool:
    return any(key.data in {"stdout", "stderr"} for key in selector.get_map().values())


def _drain_loop(
    child: Any,
    state: dict[str, Any],
    selector: selectors.BaseSelector,
    deadline: float,
) -> None:
    drain_deadline = None
    while state["error"] is None and not state["stop"]():
        now = time.monotonic()
        if now >= deadline:
            state["error"] = "timeout"
            return
        if child.poll() is not None and drain_deadline is None:
            drain_deadline = now + state["drain_seconds"]
        if drain_deadline is not None and now >= drain_deadline:
            return
        wait_until = min(deadline, drain_deadline or deadline)
        for key, _mask in selector.select(min(0.1, max(0.0, wait_until - now))):
            _consume_ready(state, key, selector)
            if state["error"] is not None:
                return
        if child.poll() is not None and not _reviewer_streams_open(selector):
            return


def _drain_child(child: Any, state: dict[str, Any], timeout: float) -> None:
    """Drain concurrently, with a bounded tail after the reviewer has exited."""

    selector = selectors.DefaultSelector()
    _register(selector, child.stdout, selectors.EVENT_READ, "stdout")
    _register(selector, child.stderr, selectors.EVENT_READ, "stderr")
    _register(selector, child.stdin, selectors.EVENT_WRITE, "stdin")
    deadline = time.monotonic() + timeout
    try:
        _drain_loop(child, state, selector, deadline)
    except InterruptedError:
        if not state["stop"]():
            raise
    finally:
        if state["error"] is None and not state["stop"]():
            _finish_buffers(state)
        _close_selector(selector)
        state["returncode"] = child.poll()


def _signal_handler(_signum: int, _frame: object) -> None:
    global _EXTERNAL_TERM
    if _SELF_TERMINATING:
        return
    _EXTERNAL_TERM = True


def _linux_group_stat(pid: int) -> tuple[str, int]:
    with open(f"/proc/{pid}/stat", "rb") as handle:
        state, pgid, _starttime = parse_proc_stat(handle.read())
    return state, pgid


def _group_members(pgid: int) -> list[int]:
    members: list[int] = []
    if sys.platform.startswith("linux"):
        for name in filter(str.isdigit, os.listdir("/proc")):
            try:
                state, member_group = _linux_group_stat(int(name))
            except (OSError, ValueError):
                continue
            if state != "Z" and member_group == pgid:
                members.append(int(name))
    elif sys.platform == "darwin":
        result = subprocess.run(
            ["/usr/bin/pgrep", "-g", str(pgid)],
            check=False,
            capture_output=True,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            timeout=5,
        )
        members = [int(item) for item in result.stdout.split() if item.isdigit()]
    return members


def _reap_children() -> None:
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _terminate_group(pgid: int, grace: float) -> None:
    global _SELF_TERMINATING
    _SELF_TERMINATING = True
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        _reap_children()
        if not [pid for pid in _group_members(pgid) if pid != os.getpid()]:
            return
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _spawn_reviewer(state: dict[str, Any]) -> subprocess.Popen[bytes] | None:
    with state["publication_lock"](state["directory"], False) as acquired:
        if not acquired:
            return None
        child = subprocess.Popen(
            state["argv"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            env=dict(state["environment"]),
        )
        state["child"] = child
        state["identity"].update(
            reviewer_pid=child.pid,
            reviewer_birth=state["birth_identity"](child.pid),
        )
        state["replace_json"](state["directory"], "identity.json", state["identity"])
    return child


def _spawn_and_drain(state: dict[str, Any]) -> None:
    try:
        child = _spawn_reviewer(state)
    except OSError:
        state["returncode"], state["error"] = 127, "provider exit 127"
        return
    if child is None:
        return
    io_state = {
        "capture": state["capture"],
        "stderr_redactor": state["redactor"](state["patterns"]),
        "stdout_redactor": state["redactor"](state["patterns"]),
        "stderr_raw": bytearray(),
        "stdout_buffer": bytearray(),
        "read": {"stdout": 0, "stderr": 0},
        "written": {"stdout": 0, "stderr": 0},
        "limits": {"stdout": EVENTS_LIMIT_BYTES, "stderr": STDERR_LIMIT_BYTES},
        "error": None,
        "persisting": True,
        "prompt": state["prompt"],
        "prompt_offset": 0,
        "events_fd": state["events_fd"],
        "stderr_fd": state["stderr_fd"],
        "stop": lambda: _EXTERNAL_TERM,
        "drain_seconds": STREAM_DRAIN_SECONDS,
    }
    _drain_child(child, io_state, float(str(state["config"]["timeout"])))
    state.update(
        returncode=io_state["returncode"],
        error=io_state["error"],
        stderr_raw=bytes(io_state["stderr_raw"]),
    )


def _completion(
    state: dict[str, Any],
    error: str | None,
    verdict: bytes,
    observed_model: str | None,
) -> dict[str, object]:
    config, identity = state["config"], state["identity"]
    return {
        "argv_digest": state["canonical_digest"](state["argv"]),
        "completed_at": _utc_now(),
        "error": None if error == "timeout" else error,
        "prompt_digest": state["prompt_digest"],
        "returncode": state["returncode"],
        "reviewer_pid": identity["reviewer_pid"],
        "schema": COMPLETION_SCHEMA,
        "started_at": identity["started_at"],
        "verdict_digest": hashlib.sha256(verdict).hexdigest() if verdict else None,
        "verdict_size": len(verdict),
        "wrapper_pid": identity["wrapper_pid"],
        "provider": config["provider"],
        "route_source": config["route_source"],
        "route_sha256": config["route_sha256"],
        "sandbox": config["sandbox"],
        "observed_model": observed_model,
        "timed_out": error == "timeout",
        "events_bytes": state["events_bytes"],
        "pgid": identity["pgid"],
        "attempt": config["attempt"],
        "environment_names": config["environment_names"],
        "omitted_short": config["omitted_short"],
    }


def _publish_result(
    state: dict[str, Any],
    error: str | None,
    verdict: bytes,
    observed_model: str | None,
) -> bool:
    """Publish only when completion wins the ordering race with external TERM."""

    def publish() -> None:
        if verdict:
            state["publish"](
                state["directory"],
                state.get("leaves", _DEFAULT_LEAVES)["capture"],
                verdict,
                False,
            )
        state["replace_json"](
            state["directory"],
            "completion.json",
            _completion(state, error, verdict, observed_model),
        )

    return state["publish_before_term"](state["directory"], publish)


def _claude_capture(
    state: dict[str, Any], capture: Any
) -> tuple[bytes, str | None, str | None] | None:
    if state["config"]["provider"] != "claude":
        return None
    return state["capture_verdict"](
        state["directory"], "claude", capture, state["patterns"],
        state.get("leaves", _DEFAULT_LEAVES)["staging"],
    )


def _finalize(state: dict[str, Any]) -> None:
    config, error = state["config"], state["error"]
    capture, stderr_raw = state["capture"], state["stderr_raw"]
    if error is None and config["provider"] == "codex" and (
        capture.codex_auth or _status_401(stderr_raw)
    ):
        error = "not-logged-in"
    verdict = b""
    observed_model = capture.observed_model
    captured = _claude_capture(state, capture) if error is None else None
    if captured is not None and captured[1] == "not-logged-in":
        verdict, error, observed_model = captured
    if error is None and state["returncode"] != 0:
        code = state["returncode"]
        error = "wrapper failure" if code is None else f"provider exit {code}"
    if error is None:
        if captured is None:
            captured = state["capture_verdict"](
                state["directory"], str(config["provider"]), capture, state["patterns"],
                state.get("leaves", _DEFAULT_LEAVES)["staging"],
            )
        verdict, error, observed_model = captured
    early_stop = {"timeout", "events cap", "stderr cap", "claude init mismatch"}
    if error in early_stop or (error or "").startswith("bad line "):
        state["returncode"] = None
    if not _publish_result(state, error, verdict, observed_model):
        return
    if _EXTERNAL_TERM:
        return
    if state["child"] is not None:
        _terminate_group(int(state["identity"]["pgid"]), float(str(config["grace"])))
