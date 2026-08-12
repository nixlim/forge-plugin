#!/usr/bin/env bash
# Advisory Stop/SessionStart nudge. Never launches semantic drift review.
set -uo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -f "${repo_root}/.forge-manifest" ] || exit 0

python3 - "$repo_root" <<'PY' || exit 0
from __future__ import annotations

import datetime as dt
from pathlib import Path
import re
import subprocess
import sys

WARNING = "forge: drift report stale — run /forge:drift"
CONFIG_WARNING = (
    "forge: malformed drift-config — using defaults "
    "(cadence: 14d, retention: forever, event-retention: 400d)"
)


def decimal_at_least(raw_digits: str, minimum: int) -> bool:
    normalized = raw_digits.lstrip("0") or "0"
    floor = str(minimum)
    return len(normalized) > len(floor) or (
        len(normalized) == len(floor) and normalized >= floor
    )


def bounded_days(raw_digits: str) -> int:
    normalized = raw_digits.lstrip("0") or "0"
    maximum = str(dt.timedelta.max.days)
    if len(normalized) > len(maximum) or (
        len(normalized) == len(maximum) and normalized > maximum
    ):
        return dt.timedelta.max.days
    return int(normalized)

repo = Path(sys.argv[1])
policy_result = subprocess.run(
    ["git", "show", "HEAD:forge-project.md"],
    cwd=repo,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
    check=False,
)
cadence = 14
malformed = policy_result.returncode != 0
if not malformed:
    policy = policy_result.stdout
    begin = "<!-- FORGE:REGION drift-config BEGIN -->"
    end = "<!-- FORGE:REGION drift-config END -->"
    lines = policy.splitlines()
    if lines.count(begin) != 1 or lines.count(end) != 1 or lines.index(end) <= lines.index(begin):
        malformed = True
    else:
        values: dict[str, str] = {}
        body = "\n".join(lines[lines.index(begin) + 1:lines.index(end)])
        body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("<!--"):
                continue
            if ":" not in line:
                malformed = True
                break
            key, value = (part.strip() for part in line.split(":", 1))
            if key not in {"cadence", "retention", "event-retention"} or key in values:
                malformed = True
                break
            values[key] = value
        cadence_match = re.fullmatch(r"([0-9]+)d", values.get("cadence", ""), re.ASCII)
        retention = values.get("retention", "")
        event_match = re.fullmatch(r"([0-9]+)d", values.get("event-retention", ""), re.ASCII)
        if (
            set(values) != {"cadence", "retention", "event-retention"}
            or not cadence_match
            or not decimal_at_least(cadence_match.group(1), 1)
            or not (retention == "forever" or re.fullmatch(r"[1-9][0-9]*d", retention, re.ASCII))
            or not event_match
            or not decimal_at_least(event_match.group(1), 366)
        ):
            malformed = True
        else:
            cadence = bounded_days(cadence_match.group(1))
if malformed:
    print(CONFIG_WARNING, file=sys.stderr)

raw_now = __import__("os").environ.get("FORGE_DRIFT_NOW", "")
try:
    now = (
        dt.datetime.strptime(raw_now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        if raw_now
        else dt.datetime.now(dt.timezone.utc)
    )
except ValueError:
    now = dt.datetime.now(dt.timezone.utc)

tree = subprocess.run(
    ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", ".forge/history/drift"],
    cwd=repo,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
    check=False,
)
newest: dt.datetime | None = None
if tree.returncode == 0:
    for line in tree.stdout.splitlines():
        path = Path(line)
        if path.parent.as_posix() != ".forge/history/drift":
            continue
        name = path.name
        match = re.fullmatch(
            r"(\d{4}-\d{2}-\d{2}T\d{6}Z)(?:-(?:0[2-9]|[1-9][0-9]+))?\.md",
            name,
        )
        if not match:
            continue
        try:
            stamp = dt.datetime.strptime(match.group(1), "%Y-%m-%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        if newest is None or stamp > newest:
            newest = stamp
if newest is None or now - newest > dt.timedelta(days=cadence):
    print(WARNING, file=sys.stderr)
PY
