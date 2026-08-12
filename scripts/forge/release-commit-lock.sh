#!/usr/bin/env bash
# Release the repository commit lock owned by this session.
# forge: modified from upstream — ownership uses FORGE_SESSION_PID and shared lock state lives under the main checkout's .forge/tmp
set -euo pipefail

session_pid="${FORGE_SESSION_PID:-}"
if [[ -z "$session_pid" ]]; then
    echo "forge: FORGE_SESSION_PID must be exported before releasing the commit lock" >&2
    echo "Usage: export FORGE_SESSION_PID=\$\$ && $0" >&2
    exit 1
fi
if ! [[ "$session_pid" =~ ^[0-9]+$ ]] || [[ "$session_pid" -eq 0 ]]; then
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
    echo "forge: cannot release the commit lock outside a git repository" >&2
    exit 1
}

lock_path=".forge/tmp/commit-lock"
if [[ "$#" -eq 1 ]]; then
    lock_path="$1"
elif [[ "$#" -ne 0 ]]; then
    echo "forge: release-commit-lock.sh accepts at most one repository-relative lock path" >&2
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
event_lock=0
if [[ "$lock_path" == ".forge/tmp/events.lock" ]]; then
    event_lock=1
fi

if [[ ! -f "$lock_file" ]]; then
    if [[ "$event_lock" -eq 1 ]]; then
        echo "forge: event lock is missing; ownership is unverifiable; refusing release" >&2
        exit 1
    fi
    echo "forge: no commit lock to release"
    exit 0
fi

lock_pid=""
lock_timestamp=""
lock_extra=""
IFS=' ' read -r lock_pid lock_timestamp lock_extra <"$lock_file" || true

if ! [[ "$lock_pid" =~ ^[0-9]+$ ]] || ! [[ "$lock_timestamp" =~ ^[0-9]+$ ]] ||
    [[ -n "$lock_extra" ]]; then
    if [[ "$event_lock" -eq 1 ]]; then
        echo "forge: corrupt event lock has no verifiable owner; refusing to release it" >&2
        exit 1
    fi
    echo "forge: corrupt commit lock has no valid owner; removing it" >&2
    rm -f "$lock_file"
    exit 0
fi

if [[ "$event_lock" -eq 1 ]] && [[ "$lock_pid" -eq 0 ]]; then
    echo "forge: corrupt event lock has no verifiable owner; refusing to release it" >&2
    exit 1
fi

if [[ "$lock_pid" != "$session_pid" ]]; then
    if [[ "$event_lock" -eq 1 ]]; then
        echo "forge: event lock is owned by PID $lock_pid, not this session ($session_pid)" >&2
        echo "forge: refusing to release a foreign event lock" >&2
        exit 1
    fi
    echo "forge: commit lock is owned by PID $lock_pid, not this session ($session_pid)" >&2
    echo "forge: refusing to release a foreign commit lock" >&2
    exit 1
fi

rm -f "$lock_file"
if [[ "$event_lock" -eq 1 ]]; then
    echo "forge: event lock released (PID $lock_pid)"
    exit 0
fi
echo "forge: commit lock released (PID $lock_pid)"
exit 0
