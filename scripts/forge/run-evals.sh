#!/usr/bin/env bash
# Offline evaluation harness for Forge AI components.
#
# Exit codes: 0 = no regressions, 1 = a golden task regressed (or STRICT=1
# with a pending result), 2 = a fixture is malformed or the suite is empty.
# forge: modified from upstream — fixtures are repo-local under .forge/evals/tasks
set -uo pipefail

TASK_DIR=".forge/evals/tasks"
REQUIRED_KEYS="id category agent expected_verdict"
VALID_VERDICTS="PASS BLOCK FLAG"
STRICT="${STRICT:-0}"

# frontmatter <file> <key> -> value (reads the leading --- ... --- block only)
frontmatter() {
    awk -v k="$2" '
        NR == 1 && /^---[[:space:]]*$/ { in_frontmatter=1; next }
        in_frontmatter && /^---[[:space:]]*$/ { exit }
        in_frontmatter && $0 ~ "^" k ":" {
            sub("^" k ":[[:space:]]*", "")
            sub(/[[:space:]]*$/, "")
            print
            exit
        }
    ' "$1"
}

if [[ ! -d "$TASK_DIR" ]]; then
    echo "no tasks dir: $TASK_DIR"
    exit 2
fi

total=0
pass=0
fail=0
pending=0
malformed=0

shopt -s nullglob
for fixture in "$TASK_DIR"/*.md; do
    total=$((total + 1))
    base="$(basename "$fixture" .md)"
    id="$(frontmatter "$fixture" id)"

    missing=""
    for key in $REQUIRED_KEYS; do
        [[ -z "$(frontmatter "$fixture" "$key")" ]] && missing="$missing $key"
    done
    if [[ -n "$missing" ]]; then
        echo "MALFORMED $base: missing frontmatter:$missing"
        malformed=$((malformed + 1))
        continue
    fi
    if [[ "$id" != "$base" ]]; then
        echo "MALFORMED $base: id '$id' does not match filename stem"
        malformed=$((malformed + 1))
        continue
    fi

    agent="$(frontmatter "$fixture" agent)"
    expected="$(frontmatter "$fixture" expected_verdict)"
    case " $VALID_VERDICTS " in
        *" $expected "*) ;;
        *)
            echo "MALFORMED $id: expected_verdict '$expected' not in {$VALID_VERDICTS}"
            malformed=$((malformed + 1))
            continue
            ;;
    esac

    # Review agents have a binary PASS/BLOCK verdict and can never emit FLAG.
    case "$(printf '%s' "$agent" | tr '[:upper:]' '[:lower:]')" in
        *review*)
            if [[ "$expected" == "FLAG" ]]; then
                echo "MALFORMED $id: review agent '$agent' cannot emit FLAG (use BLOCK)"
                malformed=$((malformed + 1))
                continue
            fi
            ;;
    esac

    result_path="$TASK_DIR/$id.result"
    if [[ -f "$result_path" ]]; then
        actual="$(tr -d '[:space:]' <"$result_path")"
        case " $VALID_VERDICTS " in
            *" $actual "*) ;;
            *)
                echo "MALFORMED $id: .result contains '$actual', expected one of {$VALID_VERDICTS}"
                malformed=$((malformed + 1))
                continue
                ;;
        esac
        if [[ "$actual" == "$expected" ]]; then
            echo "PASS $id"
            pass=$((pass + 1))
        else
            echo "FAIL $id (expected $expected, got $actual)"
            fail=$((fail + 1))
        fi
    else
        echo "PENDING $id"
        pending=$((pending + 1))
    fi
done

# Orphan result files are suspicious but do not turn a valid recorded suite into
# a regression; retain the upstream warning behavior.
for result_path in "$TASK_DIR"/*.result; do
    [[ -e "$result_path" ]] || continue
    stem="$(basename "$result_path" .result)"
    if [[ ! -f "$TASK_DIR/$stem.md" ]]; then
        echo "WARNING: orphan result $(basename "$result_path") has no matching fixture"
    fi
done

echo "----"
echo "tasks=$total pass=$pass fail=$fail pending=$pending malformed=$malformed strict=$STRICT"

# An empty suite must never vacuously pass the control-class gate.
if [[ "$total" -eq 0 ]]; then
    echo "NO TASKS FOUND — gate vacuously satisfied"
    exit 2
fi
if [[ "$malformed" -gt 0 ]]; then
    echo "FIXTURES MALFORMED"
    exit 2
fi
if [[ "$fail" -gt 0 ]]; then
    echo "REGRESSION: golden task(s) failed"
    exit 1
fi
if [[ "$STRICT" == "1" && "$pending" -gt 0 ]]; then
    echo "STRICT: $pending pending task(s) have no recorded result"
    exit 1
fi

echo "OK (no regressions in recorded results)"
exit 0
