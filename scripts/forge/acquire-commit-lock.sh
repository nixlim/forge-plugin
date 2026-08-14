#!/usr/bin/env bash
# Acquire the repository commit lock.
#
# FORGE_COMMIT_LOCK_TIMEOUT may override the 300-second timeout with a positive
# integer for diagnostics and tests. The production poll interval remains 2 s.
# forge: modified from upstream — ownership uses FORGE_SESSION_PID and shared lock state lives under the main checkout's .forge/tmp
set -euo pipefail

session_pid="${FORGE_SESSION_PID:-}"
recovery_invocation=0
if [[ "${1:-}" == "--recover-only" ]] || [[ "${1:-}" == "--state-critical-recover" ]]; then
    recovery_invocation=1
fi
if [[ "$recovery_invocation" -eq 0 ]] && [[ -z "$session_pid" ]]; then
    echo "forge: FORGE_SESSION_PID must be exported before acquiring the commit lock" >&2
    echo "Usage: export FORGE_SESSION_PID=\$\$ && $0" >&2
    exit 1
fi
if [[ "$recovery_invocation" -eq 0 ]] &&
    { ! [[ "$session_pid" =~ ^[0-9]+$ ]] || [[ "$session_pid" -eq 0 ]]; }; then
    echo "forge: FORGE_SESSION_PID must be a positive integer, got: $session_pid" >&2
    exit 1
fi

resolve_main_root() {
    local common_dir=""
    local modern_common_dir=""

    modern_common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || true
    if [[ "$modern_common_dir" == /* ]] && [[ "$modern_common_dir" != *$'\n'* ]]; then
        common_dir="$(cd "$modern_common_dir" 2>/dev/null && pwd -P)" || common_dir=""
    fi

    if [[ -z "$common_dir" ]]; then
        common_dir="$(git rev-parse --git-common-dir 2>/dev/null)" || return 1
        [[ "$common_dir" != *$'\n'* ]] || return 1
        # Older Git versions can only provide a path relative to the invoking worktree.
        if [[ "$common_dir" != /* ]]; then
            common_dir="$(pwd)/$common_dir"
        fi
        common_dir="$(cd "$common_dir" 2>/dev/null && pwd -P)" || return 1
    fi

    (cd "$(dirname "$common_dir")" 2>/dev/null && pwd -P)
}

main_root="$(resolve_main_root)" || {
    echo "forge: cannot acquire the commit lock outside a git repository" >&2
    exit 1
}

internal_state_critical=0
state_operation="acquire"
explicit_lock_path=0
lock_path=".forge/tmp/commit-lock"
if [[ "${1:-}" == "--state-critical" ]]; then
    internal_state_critical=1
    if [[ "$#" -eq 2 ]]; then
        lock_path="$2"
        explicit_lock_path=1
    elif [[ "$#" -ne 1 ]]; then
        echo "forge: invalid internal commit-lock invocation" >&2
        exit 1
    fi
elif [[ "${1:-}" == "--state-critical-recover" ]]; then
    internal_state_critical=1
    state_operation="recover"
    if [[ "$#" -eq 2 ]]; then
        lock_path="$2"
        explicit_lock_path=1
    else
        echo "forge: invalid internal event-lock recovery invocation" >&2
        exit 1
    fi
elif [[ "${1:-}" == "--recover-only" ]]; then
    state_operation="recover"
    if [[ "$#" -eq 2 ]]; then
        lock_path="$2"
        explicit_lock_path=1
    else
        echo "forge: --recover-only requires one repository-relative lock path" >&2
        exit 1
    fi
elif [[ "$#" -eq 1 ]]; then
    lock_path="$1"
    explicit_lock_path=1
elif [[ "$#" -ne 0 ]]; then
    echo "forge: acquire-commit-lock.sh accepts at most one repository-relative lock path" >&2
    exit 1
fi

if [[ "$state_operation" == "recover" ]] && [[ "$lock_path" != ".forge/tmp/events.lock" ]]; then
    echo "forge: recovery-only mode is restricted to .forge/tmp/events.lock" >&2
    exit 1
fi

if [[ -z "$lock_path" ]] || [[ "$lock_path" == /* ]] || [[ "$lock_path" == *$'\n'* ]] ||
    [[ "$lock_path" == "." ]] || [[ "$lock_path" == ".." ]] ||
    [[ "$lock_path" == ./* ]] || [[ "$lock_path" == */./* ]] ||
    [[ "$lock_path" == ../* ]] || [[ "$lock_path" == */../* ]] ||
    [[ "$lock_path" == */. ]] || [[ "$lock_path" == */.. ]] ||
    [[ "$lock_path" == *//* ]]; then
    echo "forge: lock path must be a normalized repository-relative path: $lock_path" >&2
    exit 1
fi

lock_file="$main_root/$lock_path"
lock_dir="$(dirname "$lock_file")"
# A kernel-backed, short-lived state lock serializes stale removal with atomic
# lock creation and is released automatically if its process dies.
# forge: modified from upstream — close the stale-takeover race with a non-orphanable portable state lock
if [[ "$explicit_lock_path" -eq 0 ]]; then
    # Preserve the historical no-argument paths byte-for-byte.  Explicit lock
    # names receive their own state namespace beside the lock record.
    legacy_state_guard="$lock_dir/commit-lock.state"
    state_lock_file="$lock_dir/commit-lock.state.lock"
else
    legacy_state_guard="$lock_file.state"
    state_lock_file="$lock_file.state.lock"
fi
# forge: modified from upstream — namespace the diagnostic timeout override for the forge plugin
if [[ "$explicit_lock_path" -eq 1 ]] && [[ "$lock_path" == ".forge/tmp/events.lock" ]]; then
    # FR-157's advisory event stream has its own hard bound and never inherits
    # the 300-second commit-lock diagnostic override.
    max_wait_seconds=5
else
    max_wait_seconds="${FORGE_COMMIT_LOCK_TIMEOUT:-300}"
fi
poll_interval=2

if ! [[ "$max_wait_seconds" =~ ^[0-9]+$ ]] || [[ "$max_wait_seconds" -eq 0 ]]; then
    echo "forge: FORGE_COMMIT_LOCK_TIMEOUT must be a positive integer, got: $max_wait_seconds" >&2
    exit 1
fi

mkdir -p "$lock_dir"
if [[ -d "$state_lock_file" ]] || ! : >>"$state_lock_file"; then
    echo "forge: cannot initialize commit-lock state file: $state_lock_file" >&2
    exit 1
fi

recover_legacy_state_guard() {
    local owner_path=""
    local owner_name=""
    local owner_pid=""
    local owner_timestamp=""
    local owner_extra=""
    local now=""
    local age=0
    local saw_owner=0
    local live_owner=0
    local stale_reason=""

    [[ -d "$legacy_state_guard" ]] || return 0
    now="$(date +%s)"

    for owner_path in "$legacy_state_guard"/owner "$legacy_state_guard"/owner.*; do
        [[ -f "$owner_path" ]] || continue
        saw_owner=1
        owner_name="${owner_path##*/}"
        owner_pid=""
        owner_timestamp=""
        owner_extra=""

        if [[ "$owner_name" =~ ^owner\.([0-9]+)\.([0-9]+)$ ]]; then
            owner_pid="${BASH_REMATCH[1]}"
            owner_timestamp="${BASH_REMATCH[2]}"
        else
            IFS=' ' read -r owner_pid owner_timestamp owner_extra <"$owner_path" || true
        fi

        stale_reason=""
        if ! [[ "$owner_pid" =~ ^[0-9]+$ ]] || [[ "$owner_pid" -eq 0 ]] ||
            ! [[ "$owner_timestamp" =~ ^[0-9]+$ ]] || [[ -n "$owner_extra" ]]; then
            stale_reason="malformed owner record"
        else
            if [[ "$now" -ge "$owner_timestamp" ]]; then
                age=$((now - owner_timestamp))
            else
                age=0
            fi
            if ! kill -0 "$owner_pid" 2>/dev/null; then
                stale_reason="dead owner PID $owner_pid"
            fi
        fi

        if [[ -n "$stale_reason" ]]; then
            echo "forge: recovering stale commit-lock state mutex ($stale_reason)" >&2
            rm -f "$owner_path"
        else
            live_owner=1
        fi
    done

    if [[ "$live_owner" -eq 1 ]]; then
        return 75
    fi

    # A process can die between mkdir and writing its owner. Give a live creator
    # one bounded grace period, then recover an ownerless directory.
    if [[ "$saw_owner" -eq 0 ]]; then
        if [[ "$lock_path" == ".forge/tmp/events.lock" ]]; then
            sleep 0.1
        else
            sleep 1
        fi
        for owner_path in "$legacy_state_guard"/owner "$legacy_state_guard"/owner.*; do
            [[ -f "$owner_path" ]] && return 75
        done
        if [[ "$lock_path" == ".forge/tmp/events.lock" ]]; then
            echo "forge: recovering ownerless event-lock state mutex" >&2
        else
            echo "forge: recovering ownerless commit-lock state mutex" >&2
        fi
    fi

    if ! rmdir "$legacy_state_guard" 2>/dev/null; then
        echo "forge: cannot recover legacy commit-lock state mutex: $legacy_state_guard" >&2
        return 1
    fi
    return 0
}

is_lock_stale() {
    local candidate="$1"
    local lock_pid=""
    local lock_timestamp=""
    local lock_extra=""

    [[ -f "$candidate" ]] || return 1
    IFS=' ' read -r lock_pid lock_timestamp lock_extra <"$candidate" || true

    # Empty, corrupt, and malformed lock records have no valid owner.
    if ! [[ "$lock_pid" =~ ^[0-9]+$ ]] || [[ "$lock_pid" -eq 0 ]] ||
        ! [[ "$lock_timestamp" =~ ^[0-9]+$ ]] || [[ -n "$lock_extra" ]]; then
        return 0
    fi

    # forge: modified from upstream — use a shell liveness probe where process listing may be unavailable
    # Session locks are owned by processes of the same operator account.
    if kill -0 "$lock_pid" 2>/dev/null; then
        return 1
    fi
    return 0
}

create_lock() {
    local candidate="$1"
    printf '%s %s\n' "$session_pid" "$(date +%s)" >"$candidate"
}

state_critical_attempt() {
    if [[ -d "$legacy_state_guard" ]]; then
        if recover_legacy_state_guard; then
            :
        else
            return $?
        fi
    fi

    if is_lock_stale "$lock_file"; then
        if [[ "$lock_path" == ".forge/tmp/events.lock" ]]; then
            # FR-157 confines fail-closed ownership handling to release.  A
            # dead or malformed event-lock owner is stale for acquisition and
            # may be taken over just like the ordinary commit lock.
            echo "forge: removing stale event lock" >&2
        else
            echo "forge: removing stale commit lock" >&2
        fi
        rm -f "$lock_file"
    fi

    # noclobber keeps main-lock creation atomic while the kernel state lock keeps
    # stale observation and replacement in one non-orphanable critical section.
    if (set -o noclobber; create_lock "$lock_file") 2>/dev/null; then
        return 0
    fi
    return 75
}

event_lock_recovery_status() {
    local lock_record=""
    local lock_pid=""
    local lock_timestamp=""
    local lock_extra=""

    # An unreadable record is infrastructure uncertainty, not proof that the
    # live owner record is malformed. Preserve it and surface the failure.
    if ! lock_record="$(<"$lock_file")"; then
        echo "forge: cannot read event-lock ownership record; refusing recovery" >&2
        return 1
    fi
    IFS=' ' read -r lock_pid lock_timestamp lock_extra <<<"$lock_record"

    if [[ "$lock_record" == *$'\n'* ]] ||
        ! [[ "$lock_pid" =~ ^[0-9]+$ ]] || [[ "$lock_pid" -eq 0 ]] ||
        ! [[ "$lock_timestamp" =~ ^[0-9]+$ ]] || [[ -n "$lock_extra" ]]; then
        return 0
    fi
    if kill -0 "$lock_pid" 2>/dev/null; then
        return 75
    fi
    return 0
}

recover_event_lock_only() {
    local recovered_kind=""
    local recovery_status=0

    if [[ -d "$legacy_state_guard" ]]; then
        if recover_legacy_state_guard; then
            :
        else
            return $?
        fi
    fi

    # Re-read the primary record only after entering events.lock.state.lock.
    # A symlink is not a valid owner record; unlinking it removes the link, not
    # its target. Other non-regular nodes are infrastructure failures and are
    # deliberately preserved.
    if [[ ! -e "$lock_file" ]] && [[ ! -L "$lock_file" ]]; then
        return 0
    fi
    if [[ -L "$lock_file" ]]; then
        recovered_kind="malformed symlink"
    elif [[ ! -f "$lock_file" ]]; then
        echo "forge: event lock is not a regular ownership record; refusing recovery" >&2
        return 1
    elif event_lock_recovery_status; then
        recovered_kind="malformed or dead-owner record"
    else
        recovery_status=$?
        return "$recovery_status"
    fi

    echo "forge: recovering stale event lock ($recovered_kind)" >&2
    rm -f -- "$lock_file" || return 1
    if [[ -e "$lock_file" ]] || [[ -L "$lock_file" ]]; then
        echo "forge: stale event lock remains after recovery" >&2
        return 1
    fi
    return 0
}

if [[ "$internal_state_critical" -eq 1 ]]; then
    if [[ "$state_operation" == "recover" ]]; then
        state_critical_action="recover_event_lock_only"
    else
        state_critical_action="state_critical_attempt"
    fi
    if "$state_critical_action"; then
        exit 0
    else
        exit $?
    fi
fi

script_path="${BASH_SOURCE[0]}"
if [[ "$script_path" != /* ]]; then
    script_path="$(pwd)/$script_path"
fi
script_path="$(cd "$(dirname "$script_path")" 2>/dev/null && pwd -P)/$(basename "$script_path")" || {
    echo "forge: cannot resolve acquire-commit-lock.sh for state locking" >&2
    exit 1
}

if command -v flock >/dev/null 2>&1; then
    state_lock_backend="flock"
elif command -v lockf >/dev/null 2>&1; then
    state_lock_backend="lockf"
else
    echo "forge: no portable commit-lock state mechanism is available (need flock or lockf)" >&2
    exit 1
fi

run_state_critical() {
    local state_status=0
    local internal_args=(--state-critical)

    if [[ "$state_operation" == "recover" ]]; then
        internal_args=(--state-critical-recover)
    fi

    if [[ "$explicit_lock_path" -eq 1 ]]; then
        internal_args+=("$lock_path")
    fi

    if [[ "$state_lock_backend" == "flock" ]]; then
        if flock -E 75 -n "$state_lock_file" bash "$script_path" "${internal_args[@]}"; then
            return 0
        else
            state_status=$?
        fi
    else
        if lockf -k -t 0 "$state_lock_file" bash "$script_path" "${internal_args[@]}"; then
            return 0
        else
            state_status=$?
        fi
    fi
    return "$state_status"
}

if [[ "$state_operation" == "recover" ]]; then
    if run_state_critical; then
        exit 0
    else
        recovery_status=$?
    fi
    if [[ "$recovery_status" -eq 75 ]]; then
        exit 75
    fi
    echo "forge: event-lock recovery critical section failed (status $recovery_status)" >&2
    exit 1
fi

show_lock_holder() {
    local candidate="$1"
    local lock_pid=""
    local lock_timestamp=""
    local lock_extra=""
    local now
    local age

    [[ -f "$candidate" ]] || return 0
    IFS=' ' read -r lock_pid lock_timestamp lock_extra <"$candidate" || true
    if ! [[ "$lock_pid" =~ ^[0-9]+$ ]] || ! [[ "$lock_timestamp" =~ ^[0-9]+$ ]]; then
        if [[ "$lock_path" == ".forge/tmp/events.lock" ]]; then
            echo "forge: event lock holder record is malformed ($candidate)" >&2
        else
            echo "forge: commit lock holder record is malformed ($candidate)" >&2
        fi
        return 0
    fi

    now="$(date +%s)"
    if [[ "$now" -ge "$lock_timestamp" ]]; then
        age=$((now - lock_timestamp))
    else
        age=0
    fi
    if [[ "$lock_path" == ".forge/tmp/events.lock" ]]; then
        echo "forge: event lock held by PID $lock_pid (age ${age}s)" >&2
    else
        echo "forge: commit lock held by PID $lock_pid (age ${age}s)" >&2
    fi
}

events_lock_profile=0
if [[ "$explicit_lock_path" -eq 1 ]] && [[ "$lock_path" == ".forge/tmp/events.lock" ]]; then
    events_lock_profile=1
    start_millis="$(python3 -c 'import time; print(time.monotonic_ns() // 1_000_000)')" || {
        echo "forge: cannot initialize the event-lock monotonic clock" >&2
        exit 1
    }
else
    start_time="$(date +%s)"
fi
announced=0

while true; do
    # The first acquisition attempt is immediate. Every retry checks the
    # event-lock deadline before entering recovery/critical-section work.
    if [[ "$events_lock_profile" -eq 1 ]] && [[ "$announced" -eq 1 ]]; then
        now_millis="$(python3 -c 'import time; print(time.monotonic_ns() // 1_000_000)')" || {
            echo "forge: cannot read the event-lock monotonic clock" >&2
            exit 1
        }
        elapsed_millis=$((now_millis - start_millis))
        if [[ "$elapsed_millis" -ge $((max_wait_seconds * 1000)) ]]; then
            echo "forge: failed to acquire event lock after ${max_wait_seconds}s" >&2
            show_lock_holder "$lock_file"
            echo "forge: inspect the holder before retrying or removing $lock_file" >&2
            exit 1
        fi
    fi
    acquired=0
    state_status=75
    if run_state_critical; then
        state_status=0
    else
        state_status=$?
    fi

    if [[ "$state_status" -eq 0 ]]; then
        acquired=1
    elif [[ "$state_status" -ne 75 ]]; then
        echo "forge: commit-lock state critical section failed (status $state_status)" >&2
        exit 1
    fi

    if [[ "$acquired" -eq 1 ]]; then
        if [[ "$lock_path" == ".forge/tmp/events.lock" ]]; then
            echo "forge: event lock acquired (PID $session_pid)"
        else
            echo "forge: commit lock acquired (PID $session_pid)"
        fi
        exit 0
    fi

    if [[ "$events_lock_profile" -eq 1 ]]; then
        now_millis="$(python3 -c 'import time; print(time.monotonic_ns() // 1_000_000)')" || {
            echo "forge: cannot read the event-lock monotonic clock" >&2
            exit 1
        }
        elapsed_millis=$((now_millis - start_millis))
        elapsed=$((elapsed_millis / 1000))
    else
        now="$(date +%s)"
        elapsed=$((now - start_time))
    fi
    if [[ "$announced" -eq 0 ]]; then
        if [[ "$lock_path" == ".forge/tmp/events.lock" ]]; then
            echo "forge: another session is pruning events; waiting up to ${max_wait_seconds}s" >&2
        else
            echo "forge: another session is committing; waiting up to ${max_wait_seconds}s" >&2
        fi
        show_lock_holder "$lock_file"
        announced=1
    fi

    if { [[ "$events_lock_profile" -eq 1 ]] &&
        [[ "$elapsed_millis" -ge $((max_wait_seconds * 1000)) ]]; } ||
        { [[ "$events_lock_profile" -eq 0 ]] && [[ "$elapsed" -ge "$max_wait_seconds" ]]; }; then
        if [[ "$lock_path" == ".forge/tmp/events.lock" ]]; then
            echo "forge: failed to acquire event lock after ${max_wait_seconds}s" >&2
        else
            echo "forge: failed to acquire commit lock after ${max_wait_seconds}s" >&2
        fi
        show_lock_holder "$lock_file"
        if [[ -d "$legacy_state_guard" ]]; then
            echo "forge: legacy commit-lock state mutex is still held at $legacy_state_guard" >&2
        fi
        echo "forge: inspect the holder before retrying or removing $lock_file" >&2
        exit 1
    fi

    if [[ "$events_lock_profile" -eq 1 ]]; then
        remaining_millis=$((max_wait_seconds * 1000 - elapsed_millis))
        sleep_millis=$((poll_interval * 1000))
        if [[ "$remaining_millis" -lt "$sleep_millis" ]]; then
            sleep_millis="$remaining_millis"
        fi
        sleep_for="$((sleep_millis / 1000)).$(printf '%03d' "$((sleep_millis % 1000))")"
    else
        remaining=$((max_wait_seconds - elapsed))
        sleep_for="$poll_interval"
        if [[ "$remaining" -lt "$sleep_for" ]]; then
            sleep_for="$remaining"
        fi
    fi
    sleep "$sleep_for"
done
