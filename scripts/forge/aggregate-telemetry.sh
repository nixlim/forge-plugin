#!/usr/bin/env bash
# Aggregate Markdown delivery telemetry and FR-157 decision events.
#
# Usage:
#   aggregate-telemetry.sh <decisions-dir> --csv <path>
#       [--since <UTC-ISO-8601> --until <UTC-ISO-8601>]
# Defaults: decisions-dir=.forge/tmp/decisions and the current UTC quarter.
# forge: modified from upstream — state is re-rooted to .forge/tmp and non-Forge repos are silent
set -uo pipefail

[[ -f .forge-manifest ]] || exit 0

decisions_dir=".forge/tmp/decisions"
csv=""
since=""
until=""
position_seen=0

usage_error() {
    echo "forge: invalid aggregate-telemetry arguments: $1" >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --csv|--since|--until)
            option="$1"
            [[ $# -ge 2 ]] || usage_error "$option requires a value"
            value="$2"
            shift 2
            case "$option" in
                --csv) [[ -z "$csv" ]] || usage_error "--csv may be supplied once"; csv="$value" ;;
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
            decisions_dir="$1"
            position_seen=1
            shift
            ;;
    esac
done

[[ -n "$csv" ]] || usage_error "--csv is required"
if [[ -n "$since" && -z "$until" ]] || [[ -z "$since" && -n "$until" ]]; then
    usage_error "--since and --until must be supplied together"
fi

python3 - "$decisions_dir" "$csv" "$since" "$until" <<'PY'
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

decisions_dir = Path(sys.argv[1])
csv_path = Path(sys.argv[2])
since_arg = sys.argv[3]
until_arg = sys.argv[4]
header = [
    "unit", "feature", "model", "elapsed_s", "critical_path_s", "tokens",
    "cost_usd", "review_iterations", "rework_s", "eligible_commits",
    "fast_allowed", "fast_denied_policy", "fast_denied_eligibility",
    "user_skips", "review_blocks", "halt_events", "guard_denies",
]
events = {
    "gate_commit", "fast_allowed", "fast_denied_policy",
    "fast_denied_eligibility", "user_skip", "review_block", "guard_deny",
    "halt_event",
}
required = {"at", "candidate", "event", "policy_sha", "reason", "surface"}
safe_text = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*\Z")


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

if not decisions_dir.is_dir():
    print(f"No decisions directory at '{decisions_dir}' — nothing to aggregate.")
    raise SystemExit(0)


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
events_exists = events_path.exists()
if events_exists:
    try:
        with events_path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                try:
                    item = json.loads(line)
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
                        "fast_denied_policy", "fast_denied_eligibility",
                        "user_skip", "review_block",
                    }:
                        if candidate and not re.fullmatch(r"[0-9a-f]{64}", candidate):
                            raise ValueError("invalid optional diff candidate")
                    elif candidate and not re.fullmatch(r"[0-9a-f]{64}", candidate):
                        raise ValueError("invalid optional diff candidate")
                    if item["policy_sha"] and not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", item["policy_sha"]):
                        raise ValueError("invalid policy_sha")
                    if not item["surface"] or "\n" in item["surface"] or "\r" in item["surface"] or " " in item["surface"]:
                        raise ValueError("invalid surface")
                    if item["reason"] and not safe_text.fullmatch(item["reason"]):
                        raise ValueError("invalid reason")
                    at = parse_time(item["at"], "event timestamp", fatal=False)
                    if not since <= at < until:
                        continue
                    if candidate and event != "halt_event":
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
]
try:
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        for unit in units:
            writer.writerow([*unit, *("" for _ in range(8))])
        writer.writerow(["__decision_totals__", *("" for _ in range(8)), *totals])
except (OSError, UnicodeError, csv.Error) as exc:
    fail(f"cannot write CSV '{csv_path}': {exc}")

print(f"Per-unit CSV written to {csv_path}")
PY
status=$?
exit "$status"
