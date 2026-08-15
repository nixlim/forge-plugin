#!/usr/bin/env bash
# Continuous mechanical drift sensing. This surface never launches semantic or
# model work; its only stdout is the canonical Drift summary schema v1 object.
set -uo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || repo_root=""
plugin_root="${CLAUDE_PLUGIN_ROOT:-}"
exec python3 - "$repo_root" "$plugin_root" "$@" <<'PY'
from __future__ import annotations

import datetime as dt
import fnmatch
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

OUTPUT_LIMIT = 65_536
NON_MUTATION_TIMEOUT = 1200
JOURNAL_PATTERNS_TIMEOUT_SECONDS = 30.0
EVENT_RECOVERY_BYTES = 65_536
EVENT_RECOVERY_CANDIDATES = 64
CONFIG_WARNING = (
    "forge: malformed drift-config — using defaults "
    "(cadence: 14d, retention: forever, event-retention: 400d)"
)
EVENTS = {
    "gate_commit",
    "fast_allowed",
    "fast_denied_policy",
    "fast_denied_eligibility",
    "user_skip",
    "review_block",
    "halt_event",
    "guard_deny",
    "assertion_blocking",
    "assertion_advisory",
    "assertion_waived",
    "review_cheap_finding",
    "review_final_finding",
}
REGION_ORDER = (
    "project-overview",
    "file-categories",
    "stack-validations",
    "gate1-test-command",
    "changelog-policy",
    "review-prompt-project-focus",
    "project-triggers",
    "completeness-project-items",
    "agent-project-context",
    "mutation-testing",
    "invariants",
    "risk-tiers",
    "drift-config",
    "trigger-paths",
)
DEDUPE_EVENTS = {
    "gate_commit",
    "fast_allowed",
    "fast_denied_policy",
    "fast_denied_eligibility",
    "user_skip",
    "review_block",
    "guard_deny",
}
EVENT_KEYS = {"at", "candidate", "event", "policy_sha", "reason", "surface"}
FULL_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
DIFF_SHA = re.compile(r"[0-9a-f]{64}\Z")
SAFE_TEXT = re.compile(r"/?[A-Za-z0-9][A-Za-z0-9._:/-]*\Z")
ISO_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
FENCE = re.compile(r"^\s*```(?:bash|sh)\s*$\n(.*?)^\s*```\s*$", re.MULTILINE | re.DOTALL)
STACKS: dict[str, tuple[tuple[str, ...], str]] = {
    "node": (("package.json",), "npm"),
    "python": (("pyproject.toml", "setup.py", "requirements*.txt"), "python"),
    "go": (("go.mod",), "go"),
    "rust": (("Cargo.toml",), "rust"),
    "java-maven": (("pom.xml", "mvnw"), "java"),
    "java-gradle-kotlin": (("build.gradle", "build.gradle.kts", "gradlew"), "jvm"),
    "terraform": (("*.tf",), "terraform"),
    "docker": (("Dockerfile*", "docker-compose*.yml"), "docker"),
    "helm": (("Chart.yaml",), "helm"),
}


class Failure(RuntimeError):
    def __init__(self, code: str, check: str, summary: str):
        super().__init__(summary)
        self.code = code
        self.check = check
        self.summary = summary


def utc_timestamp(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_now() -> dt.datetime:
    raw = os.environ.get("FORGE_DRIFT_NOW", "")
    if not raw:
        return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    if not ISO_UTC.fullmatch(raw):
        raise Failure("invalid-clock", "worktree-clean", "invalid UTC clock")
    return dt.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def empty_telemetry() -> dict[str, Any]:
    return {
        "assertion_advisory": 0,
        "assertion_blocking": 0,
        "assertion_waived": 0,
        "available": False,
        "eligible_commits": 0,
        "event_prune": {"entries_removed": 0, "failure": "", "new_oldest_at": ""},
        "fast_allowed": 0,
        "fast_denied_eligibility": 0,
        "fast_denied_policy": 0,
        "guard_denies": 0,
        "halt_events": 0,
        "review_blocks": 0,
        "review_cheap_findings": 0,
        "review_final_findings": 0,
        "user_skips": 0,
        "window_end": "",
        "window_start": "",
    }


def empty_journal_patterns(failure: str = "not-run") -> dict[str, Any]:
    return {
        "available": False,
        "decision_outcomes": {},
        "diagnostics": [],
        "failure": failure,
        "findings": {"by_reviewer_role": {}, "by_severity": {}},
        "routing": [],
        "tasks": [],
    }


def check(identifier: str, started: float, outcome: str, summary: str) -> dict[str, Any]:
    return {
        "check": identifier,
        "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
        "outcome": outcome,
        "summary": summary,
    }


def finding(identifier: str, code: str, evidence: list[str], summary: str, severity: str = "MAJOR") -> dict[str, Any]:
    return {
        "check": identifier,
        "code": code,
        "evidence": evidence,
        "severity": severity,
        "summary": summary,
    }


def run(
    argv: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout if isinstance(exc.stdout, bytes) else b""
        return subprocess.CompletedProcess(argv, 124, stdout=output, stderr=None)
    except OSError as exc:
        return subprocess.CompletedProcess(
            argv,
            126,
            stdout=str(exc).encode("utf-8", "replace"),
            stderr=None,
        )


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return run(["git", *args], repo)


def region(policy: str, name: str) -> str:
    begin = f"<!-- FORGE:REGION {name} BEGIN -->"
    end = f"<!-- FORGE:REGION {name} END -->"
    lines = policy.splitlines()
    if lines.count(begin) != 1 or lines.count(end) != 1:
        raise Failure("policy-malformed", "region-staleness", f"{name} region malformed")
    first = lines.index(begin)
    last = lines.index(end)
    if last <= first:
        raise Failure("policy-malformed", "region-staleness", f"{name} region malformed")
    return "\n".join(lines[first + 1:last]).strip("\n")


def validate_region_inventory(policy: str) -> bool:
    marker = re.compile(r"<!-- FORGE:REGION ([a-z0-9-]+) (BEGIN|END) -->", re.ASCII)
    order: list[str] = []
    open_region: str | None = None
    for line in policy.splitlines():
        match = marker.fullmatch(line)
        if match is None:
            if "<!-- FORGE:REGION " in line:
                return False
            continue
        name, boundary = match.groups()
        if boundary == "BEGIN":
            if open_region is not None:
                return False
            open_region = name
            order.append(name)
        elif open_region != name:
            return False
        else:
            open_region = None
    return open_region is None and tuple(order) == REGION_ORDER


def bounded_days(raw_digits: str) -> int:
    normalized = raw_digits.lstrip("0") or "0"
    maximum = str(dt.timedelta.max.days)
    if len(normalized) > len(maximum) or (
        len(normalized) == len(maximum) and normalized > maximum
    ):
        return dt.timedelta.max.days
    return int(normalized)


def decimal_at_least(raw_digits: str, minimum: int) -> bool:
    normalized = raw_digits.lstrip("0") or "0"
    floor = str(minimum)
    return len(normalized) > len(floor) or (
        len(normalized) == len(floor) and normalized >= floor
    )


def parse_config(policy: str) -> tuple[int, bool]:
    malformed = False
    try:
        body = region(policy, "drift-config")
        body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
        values: dict[str, str] = {}
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("<!--"):
                continue
            if ":" not in line:
                malformed = True
                break
            key, value = (piece.strip() for piece in line.split(":", 1))
            if key not in {"cadence", "retention", "event-retention"} or key in values:
                malformed = True
                break
            values[key] = value
        cadence = values.get("cadence", "")
        retention = values.get("retention", "")
        event_retention = values.get("event-retention", "")
        cadence_match = re.fullmatch(r"([0-9]+)d", cadence, re.ASCII)
        retention_match = retention == "forever" or bool(re.fullmatch(r"[1-9][0-9]*d", retention, re.ASCII))
        event_match = re.fullmatch(r"([0-9]+)d", event_retention, re.ASCII)
        if (
            set(values) != {"cadence", "retention", "event-retention"}
            or not cadence_match
            or not decimal_at_least(cadence_match.group(1), 1)
            or not retention_match
            or not event_match
            or not decimal_at_least(event_match.group(1), 366)
        ):
            malformed = True
    except Failure:
        malformed = True
    if malformed:
        print(CONFIG_WARNING, file=sys.stderr)
        return 400, True
    return bounded_days(event_match.group(1)), False


def dirty_paths(repo: Path) -> list[str]:
    result = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if result.returncode != 0:
        raise Failure("git-status", "worktree-clean", "worktree status unavailable")
    tokens = result.stdout.split(b"\0")
    paths: set[bytes] = set()
    index = 0
    while index < len(tokens):
        entry = tokens[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4:
            raise Failure("git-status", "worktree-clean", "worktree status malformed")
        status = entry[:2]
        paths.add(entry[3:])
        if b"R" in status or b"C" in status:
            if index >= len(tokens) or not tokens[index]:
                raise Failure("git-status", "worktree-clean", "worktree status malformed")
            paths.add(tokens[index])
            index += 1
    return [value.decode("utf-8", "surrogateescape") for value in sorted(paths)]


def load_mutation(plugin: Path):
    helper = plugin / "scripts/forge/run-scoped-mutation.py"
    spec = importlib.util.spec_from_file_location("forge_drift_mutation", helper)
    if spec is None or spec.loader is None:
        raise Failure("mutation-runner-unavailable", "mutation-full", "runner failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise Failure("mutation-runner-unavailable", "mutation-full", "runner failed") from exc
    return module


def execute_command(module: Any, command: str, timeout: int, repo: Path) -> Any:
    try:
        return module.run_command(command, [], timeout, repo)
    except Exception as exc:
        raise Failure("command-launch", "policy-command", "runner failed") from exc


def parse_fenced_commands(body: str) -> list[str]:
    commands = [match.group(1).strip("\n") for match in FENCE.finditer(body)]
    if not commands or any(not command or "\x00" in command for command in commands):
        raise Failure("policy-malformed", "gate-2", "validation policy malformed")
    return commands


def parse_gate_one(body: str) -> str:
    commands = parse_fenced_commands(body)
    if len(commands) != 1:
        raise Failure("gate-1-policy", "gate-1", "Gate 1 policy malformed")
    return commands[0]


def parse_invariants(module: Any, policy: str) -> list[tuple[str, str, str]]:
    body = region(policy, "invariants")
    lines = [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("<!--")]
    if not lines:
        return []
    parsed = [module.split_markdown_row(line) for line in lines]
    if (
        len(parsed) < 2
        or [cell.casefold() for cell in parsed[0]] != ["invariant", "check command", "enforcement point"]
        or not module.is_separator(parsed[1])
    ):
        raise Failure("invariant-policy", "invariant-sweep", "runner failed")
    rows: list[tuple[str, str, str]] = []
    for cells in parsed[2:]:
        if (
            len(cells) != 3
            or not cells[0]
            or not module.is_one_command_line(cells[1])
            or cells[2] not in {"commit", "merge", "hook"}
        ):
            raise Failure("invariant-policy", "invariant-sweep", "runner failed")
        rows.append((cells[0], cells[1], cells[2]))
    return rows


def tracked_paths(repo: Path) -> list[str]:
    result = git(repo, "ls-files", "-z")
    if result.returncode != 0:
        raise Failure("tracked-files", "file-category-coverage", "tracked files unavailable")
    return [raw.decode("utf-8", "surrogateescape") for raw in result.stdout.split(b"\0") if raw]


def stack_gaps(paths: list[str], categories: dict[str, list[str]]) -> list[str]:
    configured = {category.casefold() for category in categories}
    found: list[str] = []
    for stack, (markers, category) in STACKS.items():
        detected = any(
            any(
                fnmatch.fnmatchcase(
                    path if "/" in marker else PurePosixPath(path).name,
                    marker,
                )
                for marker in markers
            )
            for path in paths
        )
        if detected and category.casefold() not in configured:
            found.append(stack)
    return found


def rendered_divergence(repo: Path, policy: str) -> list[str]:
    evidence: list[str] = []
    agents = repo / "AGENTS.md"
    if not agents.is_file():
        evidence.append("AGENTS.md")
    else:
        text = agents.read_text(encoding="utf-8", errors="replace")
        begin = "<!-- FORGE:BEGIN -->"
        end = "<!-- FORGE:END -->"
        if text.count(begin) != 1 or text.count(end) != 1:
            evidence.append("AGENTS.md")
        else:
            rendered = text.split(begin, 1)[1].split(end, 1)[0].strip("\n")
            if rendered != policy.strip("\n"):
                evidence.append("AGENTS.md")
    claude = repo / "CLAUDE.md"
    if not claude.is_file() or "@forge-project.md" not in claude.read_text(encoding="utf-8", errors="replace").splitlines():
        evidence.append("CLAUDE.md")
    return evidence


def deleted_command_paths(repo: Path, policy: str, current_paths: list[str]) -> list[str]:
    # A deleted tracked path remains named in committed policy after a deletion
    # commit. Limit extraction to path-shaped shell tokens to avoid treating
    # executables/options as repository paths.
    result = git(repo, "log", "--diff-filter=D", "--name-only", "--pretty=format:", "HEAD", "--")
    if result.returncode != 0:
        raise Failure("deleted-path-scan", "region-staleness", "deleted path scan failed")
    deleted = sorted(
        {line for line in result.stdout.decode("utf-8", "surrogateescape").splitlines() if line}
        - set(current_paths)
    )
    command_regions = ("gate1-test-command", "stack-validations", "mutation-testing", "invariants")
    bodies = "\n".join(region(policy, name) for name in command_regions)
    return [path for path in deleted if re.search(r"(?<![A-Za-z0-9_.-])" + re.escape(path) + r"(?![A-Za-z0-9_.-])", bodies)]


def parse_event(item: Any) -> tuple[dt.datetime, str, str, str]:
    if not isinstance(item, dict) or set(item) != EVENT_KEYS or not all(isinstance(item[key], str) for key in EVENT_KEYS):
        raise ValueError
    raw_at = item["at"]
    if not raw_at.endswith("Z"):
        raise ValueError
    try:
        at = dt.datetime.fromisoformat(raw_at[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError from exc
    if at.utcoffset() != dt.timedelta(0):
        raise ValueError
    event = item["event"]
    candidate = item["candidate"]
    if event not in EVENTS:
        raise ValueError
    if event in {"gate_commit", "fast_allowed"}:
        if not FULL_SHA.fullmatch(candidate):
            raise ValueError
    elif event in {
        "assertion_blocking",
        "assertion_advisory",
        "assertion_waived",
        "review_cheap_finding",
        "review_final_finding",
    }:
        if not DIFF_SHA.fullmatch(candidate):
            raise ValueError
    elif candidate and not DIFF_SHA.fullmatch(candidate):
        raise ValueError
    if item["policy_sha"] and not FULL_SHA.fullmatch(item["policy_sha"]):
        raise ValueError
    if not SAFE_TEXT.fullmatch(item["surface"]) or (item["reason"] and not SAFE_TEXT.fullmatch(item["reason"])):
        raise ValueError
    return at, event, candidate, raw_at


def parse_event_line(raw: bytes) -> tuple[dict[str, str], dt.datetime, str, str, str, bool]:
    """Parse a normal event line or a bounded valid-object suffix after corruption."""
    try:
        item = json.loads(raw.decode("utf-8"))
        at, event, candidate, raw_at = parse_event(item)
        return item, at, event, candidate, raw_at, False
    except (UnicodeError, json.JSONDecodeError, ValueError) as original:
        window_start = max(1, len(raw) - EVENT_RECOVERY_BYTES)
        offset = len(raw)
        attempts = 0
        while attempts < EVENT_RECOVERY_CANDIDATES:
            offset = raw.rfind(b"{", window_start, offset)
            if offset < window_start:
                break
            attempts += 1
            try:
                item = json.loads(raw[offset:].decode("utf-8"))
                at, event, candidate, raw_at = parse_event(item)
            except (UnicodeError, json.JSONDecodeError, ValueError):
                continue
            return item, at, event, candidate, raw_at, True
        raise ValueError from original


def quarter_start(now: dt.datetime) -> dt.datetime:
    month = ((now.month - 1) // 3) * 3 + 1
    return dt.datetime(now.year, month, 1, tzinfo=dt.timezone.utc)


def atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def registered_event_writer_pids(repo: Path) -> tuple[list[int], bool]:
    writer_dir = repo / ".forge/tmp/event-writers"
    try:
        tokens = list(writer_dir.iterdir())
    except FileNotFoundError:
        return [], False
    except OSError:
        return [], True
    live: list[int] = []
    uncertain = False
    for token in tokens:
        if not token.is_file():
            uncertain = True
            continue
        raw_pid = token.name.split("-", 1)[0]
        if re.fullmatch(r"[1-9][0-9]*", raw_pid, re.ASCII) is None:
            uncertain = True
            continue
        pid = int(raw_pid)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            try:
                token.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                uncertain = True
        except PermissionError:
            uncertain = True
        except OSError:
            uncertain = True
        else:
            live.append(pid)
    return live, uncertain


def drain_event_writers(repo: Path) -> bool:
    # The events lock is already held. A writer registers before checking that
    # lock, so no writer can open the append target after an empty scan here.
    deadline = time.monotonic() + 5
    while True:
        live, uncertain = registered_event_writer_pids(repo)
        if not live and not uncertain:
            return True
        if uncertain or time.monotonic() >= deadline:
            return False
        time.sleep(0.01)


def aggregate_and_prune(repo: Path, plugin: Path, now: dt.datetime, retention_days: int) -> dict[str, Any]:
    window_start = quarter_start(now)
    counts = {event: 0 for event in EVENTS}
    events_path = repo / ".forge/tmp/decisions/events.jsonl"
    seen: set[tuple[str, str]] = set()
    if events_path.exists():
        try:
            raw_lines = events_path.read_bytes().splitlines(keepends=True)
        except OSError as exc:
            raise Failure("telemetry-read", "telemetry", "telemetry aggregation failed") from exc
        for raw in raw_lines:
            try:
                _item, at, event, candidate, _raw_at, recovered = parse_event_line(raw)
            except ValueError:
                print("forge: malformed decision event ignored", file=sys.stderr)
                continue
            if recovered:
                print("forge: malformed decision event prefix ignored", file=sys.stderr)
            if window_start <= at < now:
                key = (event, candidate)
                if event in DEDUPE_EVENTS and candidate:
                    if key in seen:
                        continue
                    seen.add(key)
                counts[event] += 1

    telemetry = {
        "assertion_advisory": counts["assertion_advisory"],
        "assertion_blocking": counts["assertion_blocking"],
        "assertion_waived": counts["assertion_waived"],
        "available": True,
        "eligible_commits": counts["gate_commit"],
        "event_prune": {"entries_removed": 0, "failure": "", "new_oldest_at": ""},
        "fast_allowed": counts["fast_allowed"],
        "fast_denied_eligibility": counts["fast_denied_eligibility"],
        "fast_denied_policy": counts["fast_denied_policy"],
        "guard_denies": counts["fast_denied_policy"] + counts["fast_denied_eligibility"] + counts["guard_deny"],
        "halt_events": counts["halt_event"],
        "review_blocks": counts["review_block"],
        "review_cheap_findings": counts["review_cheap_finding"],
        "review_final_findings": counts["review_final_finding"],
        "user_skips": counts["user_skip"],
        "window_end": utc_timestamp(now),
        "window_start": utc_timestamp(window_start),
    }

    if not events_path.exists():
        return telemetry

    lock_env = dict(os.environ)
    lock_env["FORGE_SESSION_PID"] = str(os.getpid())
    acquire = plugin / "scripts/forge/acquire-commit-lock.sh"
    release = plugin / "scripts/forge/release-commit-lock.sh"
    acquired = run([str(acquire), ".forge/tmp/events.lock"], repo, env=lock_env)
    if acquired.returncode != 0:
        telemetry["event_prune"]["failure"] = "event-prune-lock"
        return telemetry
    try:
        if not drain_event_writers(repo):
            telemetry["event_prune"]["failure"] = "event-prune-writer-drain"
            return telemetry
        # Re-read while holding the lock: emitters may have appended between
        # aggregation and acquisition. Registered emitters have drained, and
        # new emitters observe this lock before opening the append target.
        try:
            current_lines = events_path.read_bytes().splitlines(keepends=True)
        except OSError:
            telemetry["event_prune"]["failure"] = "event-prune-read"
            return telemetry
        prune_retention_days = retention_days
        # Test-only seam: production policy validation still requires at least 366d.
        unsafe_override = os.environ.get("FORGE_DRIFT_RETENTION_DAYS_UNSAFE")
        if unsafe_override is not None:
            if re.fullmatch(r"[1-9][0-9]*", unsafe_override, re.ASCII) is None:
                telemetry["event_prune"]["failure"] = "event-prune-config"
                return telemetry
            prune_retention_days = bounded_days(unsafe_override)
        try:
            retention_cutoff = now - dt.timedelta(days=prune_retention_days)
        except OverflowError:
            retention_cutoff = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        cutoff = min(retention_cutoff, window_start)
        retained: list[bytes] = []
        retained_times: list[tuple[dt.datetime, str]] = []
        removed = 0
        for raw in current_lines:
            try:
                item, at, _event, _candidate, raw_at, recovered = parse_event_line(raw)
            except ValueError:
                removed += 1
                continue
            if recovered:
                removed += 1
            if at < cutoff:
                removed += 1
            else:
                if recovered:
                    retained.append(
                        json.dumps(
                            item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                        ).encode("utf-8") + b"\n"
                    )
                else:
                    retained.append(raw if raw.endswith(b"\n") else raw + b"\n")
                retained_times.append((at, raw_at))
        try:
            atomic_replace(events_path, b"".join(retained))
        except OSError:
            telemetry["event_prune"]["failure"] = "event-prune-replace"
            return telemetry
        telemetry["event_prune"]["entries_removed"] = removed
        if retained_times:
            telemetry["event_prune"]["new_oldest_at"] = min(
                retained_times, key=lambda value: value[0]
            )[1]
    finally:
        released = run([str(release), ".forge/tmp/events.lock"], repo, env=lock_env)
        if released.returncode != 0:
            telemetry["event_prune"] = {
                "entries_removed": 0,
                "failure": "event-prune-release",
                "new_oldest_at": "",
            }
    return telemetry


def nonnegative_integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def valid_journal_patterns(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "available",
        "decision_outcomes",
        "diagnostics",
        "failure",
        "findings",
        "routing",
        "tasks",
    }:
        return False
    if type(value["available"]) is not bool or not isinstance(value["failure"], str):
        return False
    outcomes = value["decision_outcomes"]
    if not isinstance(outcomes, dict) or not all(
        isinstance(key, str) and nonnegative_integer(count)
        for key, count in outcomes.items()
    ):
        return False
    diagnostics = value["diagnostics"]
    if not isinstance(diagnostics, list):
        return False
    for item in diagnostics:
        if (
            not isinstance(item, dict)
            or set(item) != {"count", "diagnostic"}
            or not isinstance(item["diagnostic"], str)
            or type(item["count"]) is not int
            or item["count"] <= 0
        ):
            return False
    if diagnostics != sorted(
        diagnostics, key=lambda item: item["diagnostic"].encode("utf-8")
    ):
        return False
    finding_counts = value["findings"]
    if not isinstance(finding_counts, dict) or set(finding_counts) != {
        "by_reviewer_role",
        "by_severity",
    }:
        return False
    for counts in finding_counts.values():
        if not isinstance(counts, dict) or not all(
            isinstance(key, str) and nonnegative_integer(count)
            for key, count in counts.items()
        ):
            return False
    routing = value["routing"]
    if not isinstance(routing, list):
        return False
    for item in routing:
        if not isinstance(item, dict) or set(item) != {
            "agent",
            "committed_effort",
            "committed_model",
            "execution",
            "recorded_effort",
            "recorded_model",
            "run_id",
            "status",
        }:
            return False
        if not all(isinstance(item[key], str) for key in item):
            return False
        if item["status"] not in {"matched", "mismatched", "unavailable"}:
            return False
    if routing != sorted(
        routing,
        key=lambda item: (
            item["run_id"].encode("utf-8"),
            item["execution"].encode("utf-8"),
        ),
    ):
        return False
    tasks = value["tasks"]
    if not isinstance(tasks, list):
        return False
    for item in tasks:
        if not isinstance(item, dict) or set(item) != {
            "block_to_pass_latency_ms",
            "iterations",
            "results",
            "run_id",
            "task",
        }:
            return False
        if not isinstance(item["run_id"], str) or not isinstance(item["task"], str):
            return False
        if not nonnegative_integer(item["iterations"]):
            return False
        latency = item["block_to_pass_latency_ms"]
        if latency is not None and not nonnegative_integer(latency):
            return False
        if not isinstance(item["results"], list) or not all(
            isinstance(result, str) for result in item["results"]
        ):
            return False
    if tasks != sorted(
        tasks,
        key=lambda item: (
            item["run_id"].encode("utf-8"),
            item["task"].encode("utf-8"),
        ),
    ):
        return False
    if value["available"]:
        return value["failure"] == ""
    return value == empty_journal_patterns(value["failure"])


def extract_journal_patterns(
    repo: Path, plugin: Path, policy_sha: str
) -> tuple[dict[str, Any], str]:
    try:
        journals = sorted(
            (
                path
                for path in (repo / ".codex-orchestrator/runs").glob("*/journal.jsonl")
                if path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
            ),
            key=lambda path: str(path.relative_to(repo)).encode("utf-8"),
        )
    except OSError:
        return empty_journal_patterns("journal-patterns-discovery"), "journal-patterns-discovery"
    result = run(
        [
            sys.executable,
            str(plugin / "scripts/forge/journal-patterns.py"),
            "--repo",
            str(repo),
            "--revision",
            policy_sha,
            *(str(path) for path in journals),
        ],
        repo,
        timeout_seconds=JOURNAL_PATTERNS_TIMEOUT_SECONDS,
    )
    if result.returncode == 124:
        return empty_journal_patterns("journal-patterns-timeout"), "journal-patterns-timeout"
    try:
        patterns = json.loads(result.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        return empty_journal_patterns("journal-patterns-output"), "journal-patterns-output"
    canonical = (
        json.dumps(patterns, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if result.stdout != canonical or not valid_journal_patterns(patterns):
        return empty_journal_patterns("journal-patterns-output"), "journal-patterns-output"
    if result.returncode == 0 and patterns["available"]:
        return patterns, ""
    failure = patterns["failure"]
    if (
        result.returncode != 0
        and not patterns["available"]
        and re.fullmatch(r"[a-z0-9][a-z0-9-]*", failure)
        and failure != "not-run"
    ):
        return patterns, failure
    return empty_journal_patterns("journal-patterns-execution"), "journal-patterns-execution"


def emit(repo: Path | None, now: dt.datetime, policy_sha: str, checks: list[dict[str, Any]], findings: list[dict[str, Any]], status: dict[str, Any], telemetry: dict[str, Any], exit_code: int, journal_patterns: dict[str, Any] | None = None) -> None:
    summary = {
        "checks": checks,
        "findings": findings,
        "generated_at": utc_timestamp(now),
        "journal_patterns": journal_patterns or empty_journal_patterns(),
        "policy_sha": policy_sha,
        "schema_version": 1,
        "status": status,
        "telemetry": telemetry,
    }
    payload = (json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if repo is not None:
        target = repo / ".forge/tmp/drift" / f"{now:%Y-%m-%d}.json"
        try:
            atomic_replace(target, payload)
        except OSError:
            # This is the sole case where byte-identical file output is
            # physically unavailable. Preserve the always-emitted schema.
            summary["status"] = {"failure": "summary-write", "state": "failed"}
            summary["findings"] = []
            payload = (json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            exit_code = 2
    sys.stdout.buffer.write(payload)
    raise SystemExit(exit_code)


def main() -> None:
    repo_text, plugin_text = sys.argv[1:3]
    try:
        now = parse_now()
    except Failure:
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    repo = Path(repo_text) if repo_text else None
    plugin = Path(plugin_text) if plugin_text else None
    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    policy_sha = ""
    telemetry = empty_telemetry()

    started = time.monotonic()
    if repo is None:
        checks.append(check("worktree-clean", started, "failed", "forge repository unavailable"))
        emit(repo, now, "", checks, [], {"failure": "repository-unavailable", "state": "failed"}, telemetry, 2)
    assert repo is not None
    try:
        dirty = dirty_paths(repo)
    except (Failure, UnicodeError) as exc:
        failure = exc if isinstance(exc, Failure) else Failure("policy-encoding", "worktree-clean", "committed policy unavailable")
        checks.append(check(failure.check, started, "failed", failure.summary))
        emit(repo, now, policy_sha, checks, [], {"failure": failure.code, "state": "failed"}, telemetry, 2)
    if dirty:
        # Dirtiness is determined before HEAD or policy resolution. Resolve HEAD
        # only as schema metadata for this terminal outcome; no later control runs.
        head = git(repo, "rev-parse", "--verify", "HEAD")
        if head.returncode == 0:
            try:
                policy_sha = head.stdout.decode("ascii").strip()
            except UnicodeError:
                policy_sha = ""
        checks.append(check("worktree-clean", started, "failed", "dirty worktree"))
        emit(repo, now, policy_sha, checks, [], {"dirty_paths": dirty, "failure": "dirty-worktree", "state": "failed"}, telemetry, 2)
    if plugin is None:
        checks.append(check("worktree-clean", started, "failed", "plugin root unavailable"))
        emit(repo, now, "", checks, [], {"failure": "plugin-root", "state": "failed"}, telemetry, 2)
    if not (repo / ".forge-manifest").is_file():
        checks.append(check("worktree-clean", started, "failed", "forge repository unavailable"))
        emit(repo, now, policy_sha, checks, [], {"failure": "repository-unavailable", "state": "failed"}, telemetry, 2)
    checks.append(check("worktree-clean", started, "passed", "clean"))

    try:
        head = git(repo, "rev-parse", "--verify", "HEAD")
        if head.returncode != 0:
            raise Failure("head-unavailable", "worktree-clean", "HEAD unavailable")
        policy_sha = head.stdout.decode("ascii").strip()
        policy_result = git(repo, "show", f"{policy_sha}:forge-project.md")
        if policy_result.returncode != 0:
            raise Failure("policy-unavailable", "worktree-clean", "committed policy unavailable")
        policy = policy_result.stdout.decode("utf-8")
        region_inventory_current = validate_region_inventory(policy)
    except (Failure, UnicodeError) as exc:
        failure = exc if isinstance(exc, Failure) else Failure("policy-encoding", "worktree-clean", "committed policy unavailable")
        checks.append(check(failure.check, started, "failed", failure.summary))
        emit(repo, now, policy_sha, checks, [], {"failure": failure.code, "state": "failed"}, telemetry, 2)

    retention_days, _malformed_config = parse_config(policy)
    try:
        mutation = load_mutation(plugin)
    except Failure as failure:
        started = time.monotonic()
        checks.append(check(failure.check, started, "failed", failure.summary))
        emit(repo, now, policy_sha, checks, [], {"failure": failure.code, "state": "failed"}, telemetry, 2)

    started = time.monotonic()
    eval_env = dict(os.environ)
    eval_env["STRICT"] = "1"
    eval_result = run([str(plugin / "scripts/forge/run-evals.sh")], repo, env=eval_env)
    if eval_result.returncode != 0:
        code = "eval-regression" if eval_result.returncode == 1 else "eval-execution"
        if eval_result.returncode == 1:
            checks.append(check("evals-strict", started, "finding", "STRICT evals found regressions"))
            findings.append(finding("evals-strict", code, ["exit=1"], "STRICT evaluation regression", "CRITICAL"))
        else:
            checks.append(check("evals-strict", started, "failed", "STRICT evals failed to execute"))
            emit(repo, now, policy_sha, checks, [], {"failure": code, "state": "failed"}, telemetry, 2)
    else:
        checks.append(check("evals-strict", started, "passed", "STRICT evals passed"))

    started = time.monotonic()
    try:
        gate_one_body = region(policy, "gate1-test-command")
        if "forge-init:" in gate_one_body:
            raise Failure("gate-1-policy", "gate-1", "Gate 1 policy malformed")
        gate_one = parse_gate_one(gate_one_body)
        gate_result = execute_command(mutation, gate_one, NON_MUTATION_TIMEOUT, repo)
        if gate_result.result != "passed":
            raise Failure("gate-1-execution", "gate-1", "Gate 1 failed on clean tree")
        checks.append(check("gate-1", started, "passed", "Gate 1 passed on clean tree"))
    except Failure as failure:
        if failure.code == "command-launch":
            failure = Failure("gate-1-execution", "gate-1", "Gate 1 failed on clean tree")
        checks.append(check("gate-1", started, "failed", failure.summary))
        emit(repo, now, policy_sha, checks, [], {"failure": failure.code, "state": "failed"}, telemetry, 2)

    started = time.monotonic()
    try:
        gate_two_body = region(policy, "stack-validations")
        if "forge-init:" in gate_two_body:
            raise Failure("gate-2-policy", "gate-2", "validation policy malformed")
        gate_two_commands = parse_fenced_commands(gate_two_body)
        for command in gate_two_commands:
            outcome = execute_command(mutation, command, NON_MUTATION_TIMEOUT, repo)
            if outcome.result != "passed":
                raise Failure("gate-2-execution", "gate-2", "Gate 2 failed on clean tree")
        checks.append(check("gate-2", started, "passed", f"{len(gate_two_commands)} validations passed"))
    except Failure as failure:
        if failure.code == "command-launch":
            failure = Failure("gate-2-execution", "gate-2", "Gate 2 failed on clean tree")
        checks.append(check("gate-2", started, "failed", failure.summary))
        emit(repo, now, policy_sha, checks, [], {"failure": failure.code, "state": "failed"}, telemetry, 2)

    started = time.monotonic()
    try:
        invariant_rows = parse_invariants(mutation, policy)
        for name, command, _point in invariant_rows:
            outcome = execute_command(mutation, command, NON_MUTATION_TIMEOUT, repo)
            if outcome.result != "passed":
                raise Failure("invariant-execution", "invariant-sweep", "runner failed")
        checks.append(check("invariant-sweep", started, "passed", f"{len(invariant_rows)} invariants passed"))
    except Failure as failure:
        if failure.code == "command-launch":
            failure = Failure("invariant-execution", "invariant-sweep", "runner failed")
        checks.append(check("invariant-sweep", started, "failed", failure.summary))
        emit(repo, now, policy_sha, checks, [], {"failure": failure.code, "state": "failed"}, telemetry, 2)

    started = time.monotonic()
    try:
        rows, _absences = mutation.parse_mutation_region(policy)
        mutation_failures: list[dict[str, Any]] = []
        for row in rows:
            outcome = execute_command(mutation, row.command, row.timeout, repo)
            if outcome.result == "passed":
                continue
            output_lower = outcome.output.casefold()
            if "surviv" in output_lower and "mutant" in output_lower:
                code = "mutation-survivor"
                summary = "full-suite mutation left a surviving mutant"
            elif outcome.outcome == "timed-out":
                code = "mutation-timeout"
                summary = "full-suite mutation timed out"
            elif outcome.outcome == "output-limit-exceeded":
                code = "mutation-output-limit"
                summary = "full-suite mutation exceeded output limit"
            else:
                code = "mutation-failed"
                summary = "full-suite mutation failed"
            mutation_failures.append(finding("mutation-full", code, [f"category={row.category}"], summary))
        if mutation_failures:
            findings.extend(mutation_failures)
            checks.append(check("mutation-full", started, "finding", mutation_failures[0]["summary"]))
        else:
            summary = f"{len(rows)} mutation commands passed" if rows else "no mutation commands configured"
            checks.append(check("mutation-full", started, "passed", summary))
    except mutation.PolicyError:
        # Malformed mutation policy is complete advisory evidence, not an
        # execution failure; the remaining mechanical inventory continues.
        findings.append(finding("mutation-full", "mutation-policy-malformed", ["forge: executable policy row malformed"], "mutation policy is malformed"))
        checks.append(check("mutation-full", started, "finding", "mutation policy malformed"))
    except Failure:
        checks.append(check("mutation-full", started, "failed", "runner failed"))
        emit(repo, now, policy_sha, checks, [], {"failure": "mutation-execution", "state": "failed"}, telemetry, 2)
    except Exception:
        checks.append(check("mutation-full", started, "failed", "runner failed"))
        emit(repo, now, policy_sha, checks, [], {"failure": "mutation-execution", "state": "failed"}, telemetry, 2)

    started = time.monotonic()
    try:
        paths = tracked_paths(repo)
        categories = mutation.parse_file_categories(policy)
        unmatched = [
            path
            for path in paths
            if not any(mutation.path_matches(path, pattern) for patterns in categories.values() for pattern in patterns)
        ]
        if unmatched:
            findings.append(finding("file-category-coverage", "uncategorized-files", unmatched, "tracked files have no file category"))
            checks.append(check("file-category-coverage", started, "finding", f"{len(unmatched)} tracked files uncategorized"))
        else:
            checks.append(check("file-category-coverage", started, "passed", "all tracked files categorized"))
    except Exception:
        checks.append(check("file-category-coverage", started, "failed", "category coverage failed"))
        emit(repo, now, policy_sha, checks, [], {"failure": "category-execution", "state": "failed"}, telemetry, 2)

    started = time.monotonic()
    try:
        evidence: list[str] = []
        if not region_inventory_current:
            evidence.append("region-inventory")
        if "forge-init:" in policy:
            evidence.append("unfilled-sentinel")
        evidence.extend(f"stack={stack}" for stack in stack_gaps(paths, categories))
        evidence.extend(f"rendered={path}" for path in rendered_divergence(repo, policy))
        evidence.extend(f"deleted-path={path}" for path in deleted_command_paths(repo, policy, paths))
        if evidence:
            findings.append(finding("region-staleness", "stale-policy-region", evidence, "committed policy regions are stale"))
            checks.append(check("region-staleness", started, "finding", "stale committed policy"))
        else:
            checks.append(check("region-staleness", started, "passed", "policy regions current"))
    except (Failure, OSError):
        checks.append(check("region-staleness", started, "failed", "staleness scan failed"))
        emit(repo, now, policy_sha, checks, [], {"failure": "staleness-execution", "state": "failed"}, telemetry, 2)

    started = time.monotonic()
    try:
        telemetry = aggregate_and_prune(repo, plugin, now, retention_days)
        checks.append(check("telemetry", started, "passed", "telemetry aggregated"))
    except Failure as failure:
        checks.append(check("telemetry", started, "failed", failure.summary))
        emit(repo, now, policy_sha, checks, [], {"failure": failure.code, "state": "failed"}, empty_telemetry(), 2)

    started = time.monotonic()
    journal_patterns, journal_failure = extract_journal_patterns(repo, plugin, policy_sha)
    if journal_failure:
        checks.append(
            check(
                "journal-patterns",
                started,
                "failed",
                "journal pattern extraction failed",
            )
        )
        emit(
            repo,
            now,
            policy_sha,
            checks,
            [],
            {"failure": journal_failure, "state": "failed"},
            telemetry,
            2,
            journal_patterns,
        )
    checks.append(
        check("journal-patterns", started, "passed", "journal patterns extracted")
    )

    state = "findings" if findings else "ok"
    emit(
        repo,
        now,
        policy_sha,
        checks,
        findings,
        {"state": state},
        telemetry,
        1 if findings else 0,
        journal_patterns,
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        try:
            fallback_now = parse_now()
        except BaseException:
            fallback_now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        fallback_repo: Path | None = None
        try:
            candidate = Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else None
            if candidate is not None and candidate.is_dir():
                fallback_repo = candidate
        except (OSError, ValueError):
            fallback_repo = None
        fallback_check = check("worktree-clean", time.monotonic(), "failed", "drift execution failed")
        payload = {
            "checks": [fallback_check],
            "findings": [],
            "generated_at": utc_timestamp(fallback_now),
            "journal_patterns": empty_journal_patterns(),
            "policy_sha": "",
            "schema_version": 1,
            "status": {"failure": "drift-execution", "state": "failed"},
            "telemetry": empty_telemetry(),
        }
        encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        if fallback_repo is not None:
            try:
                destination = fallback_repo / ".forge/tmp/drift" / f"{fallback_now:%Y-%m-%d}.json"
                destination.parent.mkdir(parents=True, exist_ok=True)
                atomic_replace(destination, encoded)
            except BaseException:
                pass
        sys.stdout.buffer.write(encoded)
        raise SystemExit(2)
PY
