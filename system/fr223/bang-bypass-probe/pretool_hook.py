"""Nonce-scoped PreToolUse logger and positive-control denial for FR-223(a)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


NONCE = re.compile(r"^[0-9a-f]{64}$")
MAX_INPUT_BYTES = 1024 * 1024
DENIAL = "forge: FR-223 bang-bypass probe observed model Bash path"


def _canonical_line(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _append_observation(path: Path, payload: object) -> None:
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        data = _canonical_line(payload)
        if os.write(descriptor, data) != len(data):
            raise OSError("short observation-log write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _deny_payload() -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": DENIAL,
        }
    }


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        return 0
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    command = tool_input.get("command")
    nonce = os.environ.get("FORGE_FR223_PROBE_NONCE", "")
    log_value = os.environ.get("FORGE_FR223_PROBE_LOG", "")
    if (
        not isinstance(command, str)
        or NONCE.fullmatch(nonce) is None
        or nonce not in command
        or not log_value
    ):
        return 0

    observation = {
        "schema": "fr223-pretool-observation/1",
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "nonce": nonce,
        "tool_name": "Bash",
        "command": command,
        "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "decision": "deny",
        "reason": DENIAL,
    }
    try:
        log_path = Path(log_value)
        if not log_path.is_absolute() or not log_path.parent.is_dir():
            raise OSError("probe log path is not an absolute path in an existing directory")
        _append_observation(log_path, observation)
    except (OSError, ValueError):
        # The command remains denied. Missing log evidence makes the experiment fail closed.
        pass
    sys.stdout.buffer.write(_canonical_line(_deny_payload()))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
