#!/usr/bin/env bash

# PostToolUse early-warning sensor for committed executable invariants. Gate-time
# enforcement remains authoritative; every outcome from this hook is advisory.

# Deliberately ignore the hook's stdin payload; its untrusted fields are never interpolated into policy commands.

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -f "${repo_root}/.forge-manifest" ] || exit 0

emit_policy_advisory() {
    # Every caller supplies a fixed, JSON-safe reason string.
    printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"forge: invariant advisory — policy (%s)\\n"}}\n' "$1"
}

if ! command -v python3 >/dev/null 2>&1; then
    emit_policy_advisory 'python3 unavailable'
    exit 0
fi

policy_tmp_dir="$(mktemp -d 2>/dev/null)" || {
    emit_policy_advisory 'temporary storage unavailable'
    exit 0
}
policy_path="${policy_tmp_dir}/forge-project.md"

cleanup() {
    rm -f "$policy_path"
    rmdir "$policy_tmp_dir" 2>/dev/null || :
}
trap cleanup EXIT

if ! git -C "$repo_root" show HEAD:forge-project.md >"$policy_path" 2>/dev/null; then
    emit_policy_advisory 'committed forge-project.md unavailable'
    exit 0
fi

# Python provides portable process-group timeout and bounded-pipe handling on
# both macOS and Linux. The policy path above contains only `git show` output;
# the working-tree forge-project.md is never opened.
python3 - "$repo_root" "$policy_path" 2>/dev/null <<'PY' || \
    emit_policy_advisory 'guard execution failed'
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time


BEGIN = "<!-- FORGE:REGION invariants BEGIN -->"
END = "<!-- FORGE:REGION invariants END -->"
HEADER = ["invariant", "check command", "enforcement point"]
POINTS = {"commit", "merge", "hook"}
OUTPUT_LIMIT = 65_536
DIAGNOSTIC_NAME_LIMIT = 2_048
DIAGNOSTIC_REASON_LIMIT = 256
# Leave room for hook orchestration while keeping the complete launched check
# below FR-148's hard two-second ceiling.
TIME_LIMIT_SECONDS = 1.8


class PolicyError(Exception):
    pass


def table_cells(line: str) -> list[str]:
    r"""Parse logical cells; Markdown's ``\|`` encoding becomes the cell's ``|``."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        raise PolicyError

    cells: list[str] = []
    current: list[str] = []
    index = 1
    final = len(stripped) - 1
    while index < final:
        char = stripped[index]
        if char == "\\" and index + 1 < final and stripped[index + 1] == "|":
            current.append("|")
            index += 2
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return cells


def is_separator(cells: list[str]) -> bool:
    return len(cells) == 3 and all(
        re.fullmatch(r":?-{3,}:?", cell) is not None for cell in cells
    )


def parse_rows(policy: str) -> list[tuple[str, str, str]]:
    lines = policy.splitlines()
    begin_indexes = [index for index, line in enumerate(lines) if line == BEGIN]
    end_indexes = [index for index, line in enumerate(lines) if line == END]
    if len(begin_indexes) != 1 or len(end_indexes) != 1:
        raise PolicyError
    begin = begin_indexes[0]
    end = end_indexes[0]
    if end <= begin:
        raise PolicyError

    table_lines: list[str] = []
    for line in lines[begin + 1 : end]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            continue
        table_lines.append(line)

    # An empty region declares no hook-time invariants. A nonempty region must
    # be exactly the executable table contract.
    if not table_lines:
        return []
    parsed = [table_cells(line) for line in table_lines]
    if len(parsed) < 2 or parsed[0] != HEADER or not is_separator(parsed[1]):
        raise PolicyError

    rows: list[tuple[str, str, str]] = []
    for cells in parsed[2:]:
        if len(cells) != 3:
            raise PolicyError
        invariant, command, point = cells
        if not invariant or not command or point not in POINTS:
            raise PolicyError
        if "\n" in command or "\r" in command or "\x00" in command:
            raise PolicyError
        rows.append((invariant, command, point))
    return rows


def kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.1)
    except subprocess.TimeoutExpired:
        pass


diagnostics: list[str] = []


def truncate_utf8(value: str, byte_limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= byte_limit:
        return value
    suffix = "…".encode("utf-8")
    return (encoded[: byte_limit - len(suffix)].decode("utf-8", "ignore") + "…")


def emit_advisory(invariant: str, reason: str) -> None:
    safe_invariant = truncate_utf8(
        invariant.replace("\r", " ").replace("\n", " "),
        DIAGNOSTIC_NAME_LIMIT,
    )
    safe_reason = truncate_utf8(
        reason.replace("\r", " ").replace("\n", " "),
        DIAGNOSTIC_REASON_LIMIT,
    )
    rendered = f"forge: invariant advisory — {safe_invariant} ({safe_reason})\n"
    candidate = "".join((*diagnostics, rendered))
    response = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": candidate,
            }
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len((response + "\n").encode("utf-8")) > OUTPUT_LIMIT:
        return
    diagnostics.append(rendered)


def run_check(command: str, cwd: Path) -> str | None:
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            ["bash", "-c", command, "forge"],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except (OSError, ValueError):
        return "launch failed"

    assert process.stdout is not None
    descriptor = process.stdout.fileno()
    os.set_blocking(descriptor, False)
    selector = selectors.DefaultSelector()
    selector.register(descriptor, selectors.EVENT_READ)
    deadline = started + TIME_LIMIT_SECONDS
    output_bytes = 0
    reached_eof = False

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                kill_process_group(process)
                return "timed out"

            events = selector.select(remaining)
            if events:
                try:
                    chunk = os.read(descriptor, 8192)
                except BlockingIOError:
                    chunk = b""
                if chunk:
                    output_bytes += len(chunk)
                    if output_bytes > OUTPUT_LIMIT:
                        kill_process_group(process)
                        return "output limit exceeded"
                else:
                    reached_eof = True
                    try:
                        selector.unregister(descriptor)
                    except KeyError:
                        pass

            return_code = process.poll()
            if return_code is not None and reached_eof:
                if return_code == 0:
                    return None
                return f"exit {return_code}"
    finally:
        selector.close()
        process.stdout.close()
        # A successful shell can leave descendants running after closing its
        # output descriptors. Always terminate the isolated process group,
        # even when the group leader has already exited and been reaped.
        kill_process_group(process)


try:
    policy_text = Path(sys.argv[2]).read_text(encoding="utf-8")
    rows = parse_rows(policy_text)
except (OSError, UnicodeError, PolicyError):
    emit_advisory("policy", "executable policy row malformed")
    rows = []

repository_root = Path(sys.argv[1])
for invariant, command, point in rows:
    if point != "hook":
        continue
    reason = run_check(command, repository_root)
    if reason is not None:
        emit_advisory(invariant, reason)

if diagnostics:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "".join(diagnostics),
                }
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
PY

exit 0
