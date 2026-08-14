#!/usr/bin/env bash
# Aggregate Markdown delivery telemetry and FR-157 decision events.
#
# Usage:
#   aggregate-telemetry.sh <decisions-dir> --csv <path>
#       [--since <UTC-ISO-8601> --until <UTC-ISO-8601>]
#   aggregate-telemetry.sh <decisions-dir> --append-csv <path>
#       --session <session-id> [--since <UTC-ISO-8601> --until <UTC-ISO-8601>]
# The window defaults to the current UTC quarter.
# forge: modified from upstream — state is re-rooted to .forge/tmp and non-Forge repos are silent
set -uo pipefail

[[ -f .forge-manifest ]] || exit 0

csv=""
append_csv=""
session=""
since=""
until=""
position_seen=0

usage_error() {
    echo "forge: invalid aggregate-telemetry arguments: $1" >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --csv|--append-csv|--session|--since|--until)
            option="$1"
            [[ $# -ge 2 ]] || usage_error "$option requires a value"
            value="$2"
            [[ -n "$value" ]] || usage_error "$option requires a nonempty value"
            case "$value" in
                --*|-h) usage_error "$option requires a value" ;;
            esac
            shift 2
            case "$option" in
                --csv) [[ -z "$csv" ]] || usage_error "--csv may be supplied once"; csv="$value" ;;
                --append-csv) [[ -z "$append_csv" ]] || usage_error "--append-csv may be supplied once"; append_csv="$value" ;;
                --session) [[ -z "$session" ]] || usage_error "--session may be supplied once"; session="$value" ;;
                --since) [[ -z "$since" ]] || usage_error "--since may be supplied once"; since="$value" ;;
                --until) [[ -z "$until" ]] || usage_error "--until may be supplied once"; until="$value" ;;
            esac
            ;;
        --help|-h)
            sed -n '2,8p' "$0"
            exit 0
            ;;
        --*) usage_error "unknown option $1" ;;
        *)
            [[ "$position_seen" -eq 0 ]] || usage_error "multiple decisions directories"
            [[ -n "$1" ]] || usage_error "decisions directory must be nonempty"
            decisions_dir="$1"
            position_seen=1
            shift
            ;;
    esac
done

if [[ -n "$csv" && -n "$append_csv" ]]; then
    usage_error "--csv and --append-csv are mutually exclusive"
fi
if [[ -z "$csv" && -z "$append_csv" ]]; then
    usage_error "--csv is required"
fi
[[ "$position_seen" -eq 1 ]] || usage_error "decisions directory is required"
if [[ -n "$append_csv" && -z "$session" ]]; then
    usage_error "--session is required with --append-csv"
fi
if [[ -n "$csv" && -n "$session" ]]; then
    usage_error "--session requires --append-csv"
fi
if [[ -n "$since" && -z "$until" ]] || [[ -z "$since" && -n "$until" ]]; then
    usage_error "--since and --until must be supplied together"
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)" || {
    echo "forge: aggregate telemetry failed: cannot resolve script directory" >&2
    exit 2
}

python3 - "$decisions_dir" "${csv:-$append_csv}" "$since" "$until" "$session" "$script_dir" <<'PY'
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import stat
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

decisions_dir = Path(sys.argv[1])
csv_path = Path(sys.argv[2])
since_arg = sys.argv[3]
until_arg = sys.argv[4]
session = sys.argv[5]
script_dir = Path(sys.argv[6])
append_mode = bool(session)
header = [
    "unit", "feature", "model", "elapsed_s", "critical_path_s", "tokens",
    "cost_usd", "review_iterations", "rework_s", "eligible_commits",
    "fast_allowed", "fast_denied_policy", "fast_denied_eligibility",
    "user_skips", "review_blocks", "halt_events", "guard_denies",
    "assertion_blocking", "assertion_advisory", "assertion_waived",
    "review_cheap_findings", "review_final_findings",
]
events = {
    "gate_commit", "fast_allowed", "fast_denied_policy",
    "fast_denied_eligibility", "user_skip", "review_block", "guard_deny",
    "halt_event", "assertion_blocking", "assertion_advisory",
    "assertion_waived", "review_cheap_finding", "review_final_finding",
}
gate_outcomes = {
    "gate_commit", "fast_allowed", "fast_denied_policy",
    "fast_denied_eligibility", "user_skip", "review_block", "guard_deny",
}
required = {"at", "candidate", "event", "policy_sha", "reason", "surface"}
safe_text = re.compile(r"/?[A-Za-z0-9][A-Za-z0-9._:/-]*\Z")
EVENT_RECOVERY_CHARS = 65_536
EVENT_RECOVERY_CANDIDATES = 64


def fail(message: str) -> None:
    print(f"forge: aggregate telemetry failed: {message}", file=sys.stderr)
    raise SystemExit(2)


def parse_time(value: str, label: str, *, fatal: bool = True) -> dt.datetime:
    if not value.endswith("Z"):
        message = f"{label} must be UTC ISO-8601 ending in Z"
        if fatal:
            fail(message)
        raise ValueError(message)
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        message = f"{label} is not a valid UTC ISO-8601 timestamp"
        if fatal:
            fail(message)
        raise ValueError(message)
    if parsed.utcoffset() != dt.timedelta(0):
        message = f"{label} must be UTC"
        if fatal:
            fail(message)
        raise ValueError(message)
    return parsed


def validate_event(item: object) -> tuple[str, str, dt.datetime]:
    if not isinstance(item, dict) or set(item) != required:
        raise ValueError("wrong keys")
    if not all(isinstance(item[key], str) for key in required):
        raise ValueError("non-string value")
    if item["event"] not in events:
        raise ValueError("unknown event")
    candidate = item["candidate"]
    event = item["event"]
    if event in {"gate_commit", "fast_allowed"}:
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", candidate):
            raise ValueError("invalid commit candidate")
    elif event in {
        "fast_denied_policy", "fast_denied_eligibility", "user_skip", "review_block",
    }:
        if candidate and not re.fullmatch(r"[0-9a-f]{64}", candidate):
            raise ValueError("invalid optional diff candidate")
    elif event in {
        "assertion_blocking", "assertion_advisory", "assertion_waived",
        "review_cheap_finding", "review_final_finding",
    }:
        if not re.fullmatch(r"[0-9a-f]{64}", candidate):
            raise ValueError("invalid reviewed diff candidate")
    elif candidate and not re.fullmatch(r"[0-9a-f]{64}", candidate):
        raise ValueError("invalid optional diff candidate")
    if item["policy_sha"] and not re.fullmatch(
        r"(?:[0-9a-f]{40}|[0-9a-f]{64})", item["policy_sha"]
    ):
        raise ValueError("invalid policy_sha")
    if not safe_text.fullmatch(item["surface"]):
        raise ValueError("invalid surface")
    if item["reason"] and not safe_text.fullmatch(item["reason"]):
        raise ValueError("invalid reason")
    return event, candidate, parse_time(item["at"], "event timestamp", fatal=False)


def parse_event_line(line: str) -> tuple[str, str, dt.datetime, bool]:
    try:
        event, candidate, at = validate_event(json.loads(line))
        return event, candidate, at, False
    except (json.JSONDecodeError, ValueError) as original:
        window_start = max(1, len(line) - EVENT_RECOVERY_CHARS)
        offset = len(line)
        attempts = 0
        while attempts < EVENT_RECOVERY_CANDIDATES:
            offset = line.rfind("{", window_start, offset)
            if offset < window_start:
                break
            attempts += 1
            try:
                event, candidate, at = validate_event(json.loads(line[offset:]))
            except (json.JSONDecodeError, ValueError):
                continue
            return event, candidate, at, True
        raise ValueError(str(original)) from original


now = dt.datetime.now(dt.timezone.utc)
if since_arg:
    since = parse_time(since_arg, "--since")
    until = parse_time(until_arg, "--until")
else:
    quarter_month = ((now.month - 1) // 3) * 3 + 1
    since = dt.datetime(now.year, quarter_month, 1, tzinfo=dt.timezone.utc)
    until = now
if since >= until:
    fail("--since must precede --until")

try:
    decisions_mode = decisions_dir.stat().st_mode
except FileNotFoundError:
    print(f"No decisions directory at '{decisions_dir}' — nothing to aggregate.")
    raise SystemExit(0)
except OSError as exc:
    fail(f"cannot inspect decisions directory '{decisions_dir}': {exc}")
if not stat.S_ISDIR(decisions_mode):
    fail(f"decisions path is not a directory: '{decisions_dir}'")


def numeric(value: str, integer: bool = True):
    try:
        return int(float(value)) if integer else float(value)
    except ValueError:
        return 0 if integer else 0.0


units: list[list[object]] = []
unit_details: list[dict[str, object]] = []
telemetry_pattern = re.compile(r"^```telemetry\s*$")
try:
    markdown_files = sorted(decisions_dir.glob("*.md"))
    for path in markdown_files:
        lines = path.read_text(encoding="utf-8").splitlines()
        inside = False
        block: dict[str, str] = {}
        for line in lines:
            if not inside and telemetry_pattern.match(line):
                inside = True
                block = {}
                continue
            if inside and re.match(r"^```\s*$", line):
                inside = False
                if block:
                    row = [
                        block.get("unit", "?"), block.get("feature", "(unattributed)"),
                        block.get("model", "?"), numeric(block.get("elapsed_s", "0")),
                        numeric(block.get("critical_path_s", "0")),
                        numeric(block.get("tokens", "0")),
                        numeric(block.get("cost_usd", "0"), False),
                        numeric(block.get("review_iterations", "0")),
                        numeric(block.get("rework_s", "0")),
                    ]
                    units.append(row)
                    unit_details.append({"row": row, "block": dict(block)})
                continue
            if inside:
                content = line.split("#", 1)[0].strip()
                if ":" in content:
                    key, value = content.split(":", 1)
                    block[key.strip()] = value.strip()
except (OSError, UnicodeError) as exc:
    fail(f"cannot read decision logs: {exc}")

counts: Counter[str] = Counter()
seen: set[tuple[str, str]] = set()
events_path = decisions_dir / "events.jsonl"
try:
    events_path.stat()
except FileNotFoundError:
    events_exists = False
except OSError as exc:
    fail(f"cannot inspect decision events: {exc}")
else:
    events_exists = True
if events_exists:
    try:
        with events_path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                try:
                    event, candidate, at, recovered = parse_event_line(line)
                    if recovered:
                        print(
                            f"forge: warning: ignoring malformed decision event prefix "
                            f"{events_path}:{number}", file=sys.stderr,
                        )
                    if not since <= at < until:
                        continue
                    if candidate and event in gate_outcomes:
                        key = (event, candidate)
                        if key in seen:
                            continue
                        seen.add(key)
                    counts[event] += 1
                except (json.JSONDecodeError, ValueError) as exc:
                    print(
                        f"forge: warning: ignoring malformed decision event "
                        f"{events_path}:{number}: {exc}", file=sys.stderr,
                    )
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read decision events: {exc}")

if not units and not events_exists:
    print(f"No telemetry or decision events in '{decisions_dir}' — nothing to aggregate.")
    raise SystemExit(0)

if units:
    print(f"AI-SDLC delivery telemetry — {len(units)} unit(s)")
    print("=" * 60)
    print("\nPer-unit (seconds, tokens, $cost):")
    print(
        f"  {'UNIT':<24} {'FEATURE':<14} {'MODEL':<8} {'ELAPSED':>8} "
        f"{'CRITPATH':>8} {'TOKENS':>9} {'COST':>7} {'ITER':>5} {'REWORK':>6}"
    )
    for row in units:
        print(
            f"  {str(row[0]):<24} {str(row[1]):<14} {str(row[2]):<8} "
            f"{int(row[3]):>8} {int(row[4]):>8} {int(row[5]):>9} "
            f"{float(row[6]):>7.2f} {int(row[7]):>5} {int(row[8]):>6}"
        )

    stage_totals: Counter[str] = Counter()
    serial_totals: Counter[str] = Counter()
    critical_stage_totals: Counter[str] = Counter()
    feature_rollup: dict[str, list[float]] = defaultdict(lambda: [0.0] * 6)
    review_iterations: list[int] = []
    for detail in unit_details:
        row = detail["row"]
        block = detail["block"]
        assert isinstance(row, list) and isinstance(block, dict)
        feature = str(row[1])
        aggregate = feature_rollup[feature]
        aggregate[0] += 1
        aggregate[1] += int(row[3])
        aggregate[2] += int(row[4])
        aggregate[3] += int(row[5])
        aggregate[4] += float(row[6])
        aggregate[5] += int(row[8])
        if int(row[7]) > 0:
            review_iterations.append(int(row[7]))
        critical_names = {
            item for item in re.split(r"[ ,]+", str(block.get("on_critical_path", "")))
            if item
        }
        for key, raw_value in block.items():
            if key.startswith("stage.") and key.endswith("_s"):
                category = key[len("stage."):-len("_s")]
                value = numeric(str(raw_value))
                stage_totals[category] += value
                if category in critical_names:
                    critical_stage_totals[category] += value
            elif key.startswith("serialisation.") and key.endswith("_s"):
                category = key[len("serialisation."):-len("_s")]
                serial_totals[category] += numeric(str(raw_value))

    def print_breakdown(title: str, values: Counter[str], empty: str) -> None:
        print(f"\n{title}")
        total = sum(values.values())
        if not values:
            print(f"  {empty}")
            return
        for name, value in values.most_common():
            percentage = 100 * value / total if total else 0
            print(f"  {name:<22} {value:>8} s  {percentage:>5.1f}%")

    print_breakdown(
        "Activity-time by category (COST lens — largest total time first):",
        stage_totals,
        "(none recorded)",
    )
    print_breakdown(
        "Serialisation causes (why parallelism was lost — largest first):",
        serial_totals,
        "(none recorded — no forced serialisation, or unmeasured)",
    )
    print_breakdown(
        "Critical-path stage breakdown (DURATION lens — optimise these to ship faster):",
        critical_stage_totals,
        "(no on_critical_path data recorded)",
    )
    print("\nPer-feature roll-up (cost & duration per delivered feature/fix):")
    print(
        f"  {'FEATURE':<18} {'UNITS':>6} {'ELAPSED':>10} {'CRITPATH':>10} "
        f"{'TOKENS':>9} {'COST':>8}"
    )
    for feature, aggregate in feature_rollup.items():
        print(
            f"  {feature:<18} {int(aggregate[0]):>6} {int(aggregate[1]):>10} "
            f"{int(aggregate[2]):>10} {int(aggregate[3]):>9} {aggregate[4]:>8.2f}"
        )
    elapsed = sum(int(row[3]) for row in units)
    critical_path = sum(int(row[4]) for row in units)
    tokens = sum(int(row[5]) for row in units)
    cost = sum(float(row[6]) for row in units)
    rework = sum(int(row[8]) for row in units)
    mean_suffix = (
        f"  mean-review-iters={sum(review_iterations) / len(review_iterations):.1f}"
        if review_iterations else ""
    )
    print(
        f"\nTotals: elapsed={elapsed}s  critical-path={critical_path}s  tokens={tokens} "
        f"cost=${cost:.2f}  rework={rework}s{mean_suffix}"
    )
    print(
        "Duration analysis: total work (serial baseline)="
        f"{elapsed}s  on-critical-path stage time={sum(critical_stage_totals.values())}s  "
        f"measured duration tax (forced serialisation)={sum(serial_totals.values())}s"
    )
    print(
        "  (theoretical-best across units needs the cross-unit dependency DAG, "
        "not in the per-unit schema)"
    )

totals = [
    counts["gate_commit"], counts["fast_allowed"],
    counts["fast_denied_policy"], counts["fast_denied_eligibility"],
    counts["user_skip"], counts["review_block"], counts["halt_event"],
    counts["fast_denied_policy"] + counts["fast_denied_eligibility"] + counts["guard_deny"],
    counts["assertion_blocking"], counts["assertion_advisory"],
    counts["assertion_waived"], counts["review_cheap_finding"],
    counts["review_final_finding"],
]
ordinary_rows = [
    [*unit, *("" for _ in range(13))]
    for unit in units
]
ordinary_rows.append(["__decision_totals__", *("" for _ in range(8)), *totals])


def encode_rows(rows: list[list[object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def main_checkout_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    common = Path(result.stdout.decode("utf-8", "strict").strip())
    return common.resolve(strict=True).parent


def append_transaction() -> None:
    append_header = ["session", *header]
    exact_header = encode_rows([append_header])
    block = encode_rows([[session, *row] for row in ordinary_rows])
    try:
        main_root = main_checkout_root()
    except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
        fail(f"cannot resolve repository root for telemetry append: {exc}")
    target = csv_path if csv_path.is_absolute() else main_root / csv_path
    acquire = script_dir / "acquire-commit-lock.sh"
    release = script_dir / "release-commit-lock.sh"
    env = os.environ.copy()
    env["FORGE_SESSION_PID"] = str(os.getpid())
    try:
        acquired = subprocess.run(
            ["bash", str(acquire), ".forge/tmp/telemetry.lock"], cwd=main_root,
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, check=False,
        )
    except OSError as exc:
        fail(f"cannot acquire telemetry lock: {exc}")
    if acquired.returncode != 0:
        fail("cannot acquire telemetry lock")
    preexisting = b""
    existed = False
    appended = False
    failure = ""

    def restore_target() -> str:
        try:
            if existed:
                target.write_bytes(preexisting)
            else:
                target.unlink(missing_ok=True)
        except OSError as exc:
            return f"; rollback failed: {exc}"
        return ""

    try:
        try:
            preexisting = target.read_bytes()
            existed = True
        except FileNotFoundError:
            pass
        except OSError as exc:
            failure = f"cannot read append CSV '{target}': {exc}"
        if existed and not target.is_file():
            failure = f"append CSV is not a regular file: '{target}'"
        if preexisting and not failure:
            malformed = not preexisting.startswith(exact_header) or not preexisting.endswith(b"\n")
            try:
                decoded = preexisting.decode("utf-8", "strict")
                parsed_rows = list(csv.reader(io.StringIO(decoded, newline=""), strict=True))
            except (UnicodeError, csv.Error):
                malformed = True
                parsed_rows = []
            if (
                malformed
                or not parsed_rows
                or parsed_rows[0] != append_header
                or sum(row == append_header for row in parsed_rows) != 1
                or any(len(row) != len(append_header) for row in parsed_rows)
            ):
                failure = f"malformed append CSV header in '{target}'"
            payload = block
        elif not failure:
            payload = exact_header + block
        if not failure:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError("short append")
                    view = view[written:]
                appended = True
                os.fsync(descriptor)
            except OSError as exc:
                failure = f"cannot append CSV '{target}': {exc}"
                failure += restore_target()
                appended = False
            finally:
                os.close(descriptor)
    except (OSError, UnicodeError, csv.Error) as exc:
        failure = f"cannot append CSV '{target}': {exc}"
        if appended:
            failure += restore_target()
            appended = False

    try:
        try:
            released = subprocess.run(
                ["bash", str(release), ".forge/tmp/telemetry.lock"], cwd=main_root,
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError as exc:
            released = None
            release_failure = f"cannot release telemetry lock: {exc}"
        else:
            release_failure = "" if released.returncode == 0 else "cannot release telemetry lock"
        if release_failure:
            if appended:
                release_failure += restore_target()
                appended = False
            failure = failure or release_failure
    finally:
        if failure:
            fail(failure)


if append_mode:
    append_transaction()
else:
    try:
        csv_path.write_bytes(encode_rows([header, *ordinary_rows]))
    except (OSError, UnicodeError, csv.Error) as exc:
        fail(f"cannot write CSV '{csv_path}': {exc}")

print(f"Per-unit CSV {'appended to' if append_mode else 'written to'} {csv_path}")
PY
status=$?
exit "$status"
