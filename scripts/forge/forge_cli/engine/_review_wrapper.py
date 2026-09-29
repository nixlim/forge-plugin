"""Stdlib-only detached reviewer wrapper and source composer."""

from __future__ import annotations

import ctypes
import datetime
import fcntl
import hashlib
import json
import os
import re
import secrets
import signal
import stat
import sys
import threading
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any

if __name__ != "__main__":
    from forge_cli.engine._review_wrapper_io import (
        _failure_leaves,
        _open_events,
        _wrapper_options,
        open_owner_regular,
        parse_proc_stat,
    )

Patterns = list[tuple[bytes, bytes]]
IDENTITY_SCHEMA = "forge-review-identity/1"
EVENTS_LIMIT_BYTES, STDERR_LIMIT_BYTES = 16 * 1024 * 1024, 1024 * 1024
VERDICT_LIMIT_BYTES, STREAM_DRAIN_SECONDS = 65_536, 1.0
_TOP_EXTRACTOR_KEYS = frozenset("type subtype is_error result message modelUsage".split())
CLAUDE_INIT_MISMATCH = "claude init mismatch"
_EXTERNAL_TERM = False


def reap_detached(process: Any) -> None:
    with suppress(Exception):
        wait = getattr(process, "wait", None)
        if callable(wait):
            threading.Thread(target=wait, daemon=True).start()

if TYPE_CHECKING:
    def _completion(*args: Any) -> dict[str, object]: ...

    def _finalize(state: dict[str, Any]) -> None: ...

    def _signal_handler(signum: int, frame: object) -> None: ...

    def _spawn_and_drain(state: dict[str, Any]) -> None: ...

    def _terminate_group(pgid: int, grace: float) -> None: ...


class _ExternProcPrefix(ctypes.Union):
    _fields_ = [("p_starttime", ctypes.c_long * 2), ("links", ctypes.c_void_p * 2)]


class _KinfoProcPrefix(ctypes.Structure):
    _fields_ = [("kp_proc", _ExternProcPrefix)]


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


@contextmanager
def attempt_publication_lock(directory: int, blocking: bool = True) -> Any:
    try:
        fcntl.flock(directory, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    except BlockingIOError:
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(directory, fcntl.LOCK_UN)


def _publish_before_external_term(directory: int, operation: Any) -> bool:
    with attempt_publication_lock(directory) as acquired:
        if not acquired:
            return False
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
        try:
            if _EXTERNAL_TERM or signal.SIGTERM in signal.sigpending():
                return False
            operation()
            return True
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def _linux_stat(pid: int) -> tuple[str, int, int]:
    with open(f"/proc/{pid}/stat", "rb") as handle:
        return parse_proc_stat(handle.read())


def _linux_identity(pid: int) -> dict[str, object] | None:
    try:
        _state, _pgid, starttime = _linux_stat(pid)
        with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as handle:
            boot_id = handle.read().strip()
    except (OSError, ValueError):
        return None
    if not boot_id:
        return None
    return {"kind": "linux-proc", "boot_id": boot_id, "starttime": starttime}


def _parse_macos_kinfo_start(data: bytes) -> tuple[int, int]:
    if len(data) < ctypes.sizeof(_KinfoProcPrefix):
        raise ValueError("short kinfo_proc")
    seconds, microseconds = _KinfoProcPrefix.from_buffer_copy(data).kp_proc.p_starttime
    if seconds < 0 or not 0 <= microseconds < 1_000_000:
        raise ValueError("invalid p_starttime")
    return seconds, microseconds


def _macos_identity(pid: int) -> dict[str, object] | None:
    sysctl = ctypes.CDLL(None, use_errno=True).sysctl
    try:
        mib = (ctypes.c_int * 4)(1, 14, 1, pid)
        length = ctypes.c_size_t()
        if sysctl(mib, 4, None, ctypes.byref(length), None, 0) or not length.value:
            raise OSError
        buffer = ctypes.create_string_buffer(length.value)
        if sysctl(mib, 4, buffer, ctypes.byref(length), None, 0):
            raise OSError
        seconds, microseconds = _parse_macos_kinfo_start(buffer.raw[: length.value])
    except (OSError, ValueError):
        return None
    return {"kind": "macos-starttime", "seconds": seconds, "microseconds": microseconds}


def birth_identity(pid: int) -> dict[str, object] | None:
    if sys.platform.startswith("linux"):
        return _linux_identity(pid)
    return _macos_identity(pid) if sys.platform == "darwin" else None


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short stream write")
        view = view[written:]


def _publish(directory: int, name: str, data: bytes, exclusive: bool) -> bool:
    temporary = f".{name}-{secrets.token_hex(8)}.tmp"
    descriptor = open_owner_regular(directory, temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        _write_all(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        operation = os.link if exclusive else os.replace
        operation(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
        return True
    except FileExistsError:
        return False
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory)


def exclusive_publish(directory: int, name: str, record: dict[str, object]) -> bool:
    text = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _publish(directory, name, (text + "\n").encode(), True)


def atomic_replace_json(directory: int, name: str, record: dict[str, object]) -> None:
    text = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    _publish(directory, name, (text + "\n").encode(), False)


REDACTION_EXEMPT_NAMES = frozenset({"USER", "LANG", "LC_ALL", "TERM"})


def _redaction_patterns(names: list[str]) -> Patterns:
    unique: dict[bytes, bytes] = {}
    for name in sorted(set(names) - REDACTION_EXEMPT_NAMES):
        value = os.environ[name]
        replacement = f"<redacted:{name}>".encode()
        encoded = (json.dumps(value, ensure_ascii=True), json.dumps(value, ensure_ascii=False))
        variants = {value.encode(), *(item[1:-1].encode() for item in encoded)}
        for variant in variants:
            if variant:
                unique.setdefault(variant, replacement)
    return sorted(unique.items(), key=lambda item: (-len(item[0]), item[0], item[1]))


class _StreamRedactor:
    def __init__(self, patterns: Patterns) -> None:
        self.patterns = patterns
        self.replacements = dict(patterns)
        alternatives = b"|".join(re.escape(pattern) for pattern, _value in patterns)
        self.matcher = re.compile(alternatives) if alternatives else None
        self.pending = b""
        self.carry_limit = max((len(pattern) for pattern, _value in patterns), default=1) - 1

    def _replace(self, value: bytes) -> bytes:
        if self.matcher is None:
            return value
        return self.matcher.sub(lambda match: self.replacements[match.group()], value)

    def feed(self, data: bytes, *, final: bool = False) -> bytes:
        source = self.pending + data
        if final:
            self.pending = b""
            return self._replace(source)
        carry = 0
        for width in range(min(self.carry_limit, len(source)), 0, -1):
            suffix = source[-width:]
            if any(pattern.startswith(suffix) for pattern, _value in self.patterns):
                carry = width
                break
        cutoff = len(source) - carry
        self.pending = source[cutoff:]
        return self._replace(source[:cutoff])


def _redact_text(value: str, patterns: Patterns) -> str:
    return _StreamRedactor(patterns).feed(value.encode(), final=True).decode()


def _original_key(value: str, patterns: Patterns) -> str:
    original = value
    for pattern, replacement in patterns:
        original = original.replace(replacement.decode(), pattern.decode())
    return original


def _protected_json_field(
    scope: str, key: object, container: dict[object, object]
) -> str | None:
    field = None
    if scope == "modelUsage":
        field = "modelUsage"
    elif scope == "message" and key == "model":
        field = "model"
    elif scope == "top":
        if key in _TOP_EXTRACTOR_KEYS:
            field = str(key)
        elif container.get("subtype") == "init":
            if key == "model":
                field = "model"
            elif key in {"permissionMode", "tools"}:
                field = f"init.{key}"
    return field


def _protected_json_key(
    scope: str, key: object, container: dict[object, object]
) -> bool:
    return _protected_json_field(scope, key, container) is not None


def _redact_json(
    value: object,
    patterns: Patterns,
    scope: str = "top",
) -> tuple[object, str | None]:
    if isinstance(value, str):
        redacted_text = _redact_text(value, patterns)
        damaged = scope if scope in {"init.permissionMode", "init.tools"} \
            and redacted_text != value else None
        return redacted_text, damaged
    if isinstance(value, list):
        values = [_redact_json(item, patterns, scope) for item in value]
        return [item for item, _damage in values], next(
            (damage for _item, damage in values if damage), None
        )
    if not isinstance(value, dict):
        return value, None
    transformed: dict[object, object] = {}
    origins: dict[object, object] = {}
    damage = None
    for key, item in value.items():
        new_key = _redact_text(key, patterns) if isinstance(key, str) else key
        original_key = _original_key(key, patterns) if isinstance(key, str) else key
        protected_field = _protected_json_field(scope, original_key, value)
        protected = protected_field is not None
        if protected and new_key != original_key:
            damage = damage or protected_field
        if new_key in transformed and (
            protected or _protected_json_key(scope, origins[new_key], value)
        ):
            damaged_key = original_key if protected else origins[new_key]
            damage = damage or _protected_json_field(scope, damaged_key, value)
        child_scope = ""
        if scope == "top" and original_key in {"message", "modelUsage"}:
            child_scope = str(original_key)
        elif (
            scope == "top"
            and value.get("subtype") == "init"
            and original_key in {"permissionMode", "tools"}
        ):
            child_scope = f"init.{original_key}"
        transformed_item, child_damage = _redact_json(item, patterns, child_scope)
        transformed[new_key] = transformed_item
        origins[new_key] = original_key
        damage = damage or child_damage
    return transformed, damage


def _claude_flag_value(
    argv: list[str], flag: str, *, required: bool
) -> str | None:
    count = argv.count(flag)
    if count > 1 or (required and count != 1):
        raise ValueError("launch configuration")
    if count == 0:
        return None
    index = argv.index(flag) + 1
    if index >= len(argv) or not argv[index] or argv[index].startswith("-"):
        raise ValueError("launch configuration")
    return argv[index]


def _claude_permission_mode(argv: list[str]) -> str:
    bypass_count = argv.count("--dangerously-skip-permissions")
    if bypass_count > 1:
        raise ValueError("launch configuration")
    explicit = _claude_flag_value(argv, "--permission-mode", required=False)
    if bypass_count and explicit is not None:
        raise ValueError("launch configuration")
    if bypass_count:
        return "bypassPermissions"
    return explicit or "default"


def _claude_init_expectation(argv: list[str]) -> tuple[str, tuple[str, ...]]:
    permission_mode = _claude_permission_mode(argv)
    tools_value = _claude_flag_value(argv, "--tools", required=True)
    if tools_value is None:
        raise ValueError("launch configuration")
    tools = tuple(sorted(tools_value.split(",")))
    if not tools or any(not tool for tool in tools) or len(tools) != len(set(tools)):
        raise ValueError("launch configuration")
    return permission_mode, tools


def _claude_init_error(
    event: dict[str, object], expectation: tuple[str, tuple[str, ...]]
) -> str | None:
    permission_mode, expected_tools = expectation
    tools = event.get("tools")
    valid_tools = (
        isinstance(tools, list)
        and all(isinstance(tool, str) for tool in tools)
        and len(tools) == len(set(tools))
        and set(tools) == set(expected_tools)
    )
    valid = (
        event.get("type") == "system"
        and event.get("subtype") == "init"
        and event.get("permissionMode") == permission_mode
        and valid_tools
    )
    return None if valid else CLAUDE_INIT_MISMATCH


class _EventCapture:
    def __init__(
        self,
        patterns: Patterns,
        claude_init: tuple[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.patterns = patterns
        self.claude_init = claude_init
        self.line = 0
        self.result: dict[str, object] | None = None
        self.observed_model: str | None = None
        self.codex_auth = False

    def _observe(self, event: dict[str, object]) -> None:
        self.codex_auth |= event.get("type") == "error" and "401 Unauthorized" in json.dumps(event)
        self.result = event if event.get("type") == "result" else self.result
        message = event.get("message")
        nested = message.get("model") if isinstance(message, dict) else None
        model = event.get("model") if event.get("subtype") == "init" else nested
        if isinstance(model, str):
            self.observed_model = model
        usage = event.get("modelUsage")
        if isinstance(usage, dict) and usage:
            self.observed_model = sorted(str(key) for key in usage)[0]

    def _structural_damage(self, event: dict[str, object]) -> str | None:
        markers = tuple(value.decode() for _pattern, value in self.patterns)
        message = event.get("message")
        fields = (
            ("type", event.get("type")),
            ("subtype", event.get("subtype")),
            ("model", event.get("model") if event.get("subtype") == "init" else None),
            ("model", message.get("model") if isinstance(message, dict) else None),
        )
        return next(
            (
                field
                for field, field_value in fields
                if isinstance(field_value, str)
                and any(marker in field_value for marker in markers)
            ),
            None,
        )

    def line_bytes(self, raw: bytes, *, terminated: bool) -> tuple[bytes, str | None]:
        self.line += 1
        try:
            event = json.loads(raw)
            if not terminated or not isinstance(event, dict):
                raise ValueError
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return raw + b"\n", f"bad line {self.line}"
        init_error = (
            _claude_init_error(event, self.claude_init)
            if self.line == 1 and self.claude_init is not None
            else None
        )
        redacted, damaged = _redact_json(event, self.patterns)
        assert isinstance(redacted, dict)
        damaged = damaged or self._structural_damage(redacted)
        self._observe(redacted)
        text = json.dumps(redacted, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        too_long = self.observed_model and len(self.observed_model.encode()) > 4096
        error = init_error or (f"redaction damaged {damaged}" if damaged else (
            "verdict invalid" if too_long else None
        ))
        return (text + "\n").encode(), error

    def final_error(self) -> str | None:
        if self.claude_init is not None and self.line == 0:
            return CLAUDE_INIT_MISMATCH
        return None


def _read_leaf(directory: int, name: str, limit: int | None = None) -> bytes:
    descriptor = open_owner_regular(directory, name, os.O_RDONLY)
    with os.fdopen(descriptor, "rb") as handle:
        data = handle.read() if limit is None else handle.read(limit + 1)
    if limit is not None and len(data) > limit:
        raise ValueError("verdict cap")
    return data


def _read_codex_verdict(directory: int, patterns: Patterns,
                        staging: str = "verdict.staging") -> bytes:
    try:
        data = _read_leaf(directory, staging, VERDICT_LIMIT_BYTES)
        verdict = _StreamRedactor(patterns).feed(data, final=True)
        if len(verdict) > VERDICT_LIMIT_BYTES:
            raise ValueError("verdict cap")
        return verdict
    finally:
        with suppress(FileNotFoundError):
            os.unlink(staging, dir_fd=directory)


def _capture_codex_verdict(
    directory: int, patterns: Patterns, staging: str = "verdict.staging"
) -> tuple[bytes, str | None, None]:
    try:
        verdict = _read_codex_verdict(directory, patterns, staging)
    except FileNotFoundError:
        return b"", "verdict missing", None
    except ValueError as exc:
        return b"", str(exc), None
    except OSError:
        return b"", "verdict invalid", None
    return verdict, None if verdict else "verdict empty", None


def _capture_verdict(
    directory: int, provider: str, capture: _EventCapture, patterns: Patterns,
    staging: str = "verdict.staging",
) -> tuple[bytes, str | None, str | None]:
    if provider == "codex":
        return _capture_codex_verdict(directory, patterns, staging)
    result = capture.result or {}
    observed = capture.observed_model
    text = result.get("result")
    if not result:
        return b"", "verdict missing", observed
    if result.get("is_error") is not False:
        logged_out = isinstance(text, str) and "Not logged in" in text
        return b"", "not-logged-in" if logged_out else "claude result error", observed
    if not isinstance(text, str) or not text:
        return b"", "verdict empty", observed
    verdict = text.encode()
    if len(verdict) > VERDICT_LIMIT_BYTES:
        return b"", "verdict cap", observed
    return verdict, None, observed


def _claim_identity(
    directory: int, config: dict[str, object]
) -> dict[str, object] | None:
    opened = os.fstat(directory)
    if not stat.S_ISDIR(opened.st_mode) or opened.st_uid != os.geteuid():
        raise OSError("unsafe attempt directory")
    pid, pgid, started_at = os.getpid(), os.getpgid(0), _utc_now()
    if pid != pgid or pid != os.getsid(0):
        raise OSError("wrapper is not process-group leader")
    identity: dict[str, object] = {
        "schema": IDENTITY_SCHEMA,
        "attempt": config["attempt"],
        "wrapper_pid": pid,
        "pgid": pgid,
        "wrapper_birth": birth_identity(pid),
        "reviewer_pid": None,
        "reviewer_birth": None,
        "started_at": started_at,
    }
    if not exclusive_publish(directory, "identity.json", identity):
        return None
    return identity


def _launch_inputs(
    directory: int, config: dict[str, object]
) -> tuple[Any, ...]:
    leaves, events_existing = _wrapper_options(config)
    argv, names = config["argv"], config["environment_names"]
    if not isinstance(argv, list) or _canonical_digest(argv) != config["argv_digest"]:
        raise ValueError("launch configuration")
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError("launch configuration")
    typed_names = [str(name) for name in names]
    if sorted(set(typed_names)) != typed_names:
        raise ValueError("launch configuration")
    prompt = _read_leaf(directory, leaves["prompt"])
    prompt_digest = hashlib.sha256(prompt).hexdigest()
    if prompt_digest != config["prompt_digest"]:
        raise ValueError("prompt digest")
    role_body_digest = config.get("role_body_digest")
    if role_body_digest is not None:
        role_body = _read_leaf(directory, "review-final-body.md")
        if hashlib.sha256(role_body).hexdigest() != role_body_digest:
            raise ValueError("role body digest")
    return argv, typed_names, prompt, prompt_digest, leaves, events_existing


def _run(directory: int, config: dict[str, object]) -> None:
    identity = _claim_identity(directory, config)
    if identity is None or identity["wrapper_birth"] is None:
        return
    argv, names, prompt, prompt_digest, leaves, events_existing = _launch_inputs(directory, config)
    claude_init = (
        _claude_init_expectation(argv) if config["provider"] == "claude" else None
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if config["provider"] == "codex":
        os.close(open_owner_regular(directory, leaves["staging"], flags))
    events_fd = _open_events(directory, leaves["events"], events_existing, open_owner_regular)
    stderr_fd = open_owner_regular(directory, leaves["stderr"], flags)
    patterns = _redaction_patterns(names)
    state: dict[str, Any] = {
        "directory": directory,
        "config": config,
        "identity": identity,
        "argv": argv,
        "prompt": prompt,
        "prompt_digest": prompt_digest,
        "patterns": patterns,
        "leaves": leaves,
        "environment": {name: os.environ[name] for name in names},
        "events_fd": events_fd,
        "stderr_fd": stderr_fd,
        "child": None,
        "returncode": None,
        "error": None,
        "capture": _EventCapture(patterns, claude_init),
        "stderr_raw": b"",
        "birth_identity": birth_identity,
        "replace_json": atomic_replace_json,
        "redactor": _StreamRedactor,
        "canonical_digest": _canonical_digest,
        "capture_verdict": _capture_verdict,
        "publish": _publish,
        "publication_lock": attempt_publication_lock,
        "publish_before_term": _publish_before_external_term,
    }
    try:
        if not _EXTERNAL_TERM:
            _spawn_and_drain(state)
    finally:
        for descriptor in (events_fd, stderr_fd):
            os.fsync(descriptor)
        state["events_bytes"] = os.fstat(events_fd).st_size
        for descriptor in (events_fd, stderr_fd):
            os.close(descriptor)
    if not _EXTERNAL_TERM:
        _finalize(state)


def wrapper_source() -> str:
    directory = os.path.dirname(__file__)
    try:
        with open(__file__, encoding="utf-8") as handle:
            source = handle.read()
        with open(os.path.join(directory, "_review_wrapper_io.py"), encoding="utf-8") as handle:
            io_source = handle.read()
    except OSError as exc:
        raise RuntimeError("review wrapper source is unavailable") from exc
    guard = '\nif __name__ == "__main__":'
    body, separator, ending = source.partition(guard)
    if not separator:
        raise RuntimeError("review wrapper main guard is unavailable")
    return body + "\n\n" + io_source + separator + ending


def _optional_leaf(directory: int, name: str) -> bytes:
    try:
        return _read_leaf(directory, name)
    except OSError:
        return b""


def _publish_wrapper_failure(directory: int, config: dict[str, object]) -> None:
    if "completion.json" in os.listdir(directory):
        return
    identity = json.loads(_read_leaf(directory, "identity.json"))
    state = {
        "config": config,
        "identity": identity,
        "argv": config.get("argv", []), "prompt_digest": config.get("prompt_digest"),
        "canonical_digest": _canonical_digest,
        "returncode": None,
        "events_bytes": len(_optional_leaf(directory, _failure_leaves(config)["events"])),
    }
    record = _completion(state, "wrapper failure", b"", None)

    def publish() -> None:
        atomic_replace_json(directory, "completion.json", record)

    if not _publish_before_external_term(directory, publish) or _EXTERNAL_TERM:
        return
    _terminate_group(int(identity["pgid"]), float(str(config["grace"])))


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 2:
        return 2
    os.umask(0o077)
    signal.signal(signal.SIGTERM, _signal_handler)
    config: dict[str, object] = {}
    try:
        value = json.loads(arguments[1])
        if not isinstance(value, dict):
            return 2
        config = value
        _run(int(arguments[0]), config)
    except BaseException:
        with suppress(BaseException):
            _publish_wrapper_failure(int(arguments[0]), config)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
