#!/usr/bin/env bash
# Operator halt check (kill-switch).
#
# Usage: check-halt.sh [scope]
#   Always checks AGENT_HALT. When scope is non-empty, also checks
#   AGENT_HALT_<scope>. Both sentinels live at the main-checkout root shared by
#   every linked worktree.
#
# Exit 0 = clear to proceed. Exit 1 = a halt is engaged.
# forge: modified from upstream — audit state is re-rooted to .forge/tmp for plugin-local governance state
set -uo pipefail

scope="${1:-}"
probe_only="${FORGE_HALT_PROBE_ONLY:-0}"

if ! common_dir="$(git rev-parse --git-common-dir 2>/dev/null)"; then
    echo "forge: warning: outside a git repository — halt check skipped" >&2
    exit 0
fi

if [[ "$common_dir" != /* ]]; then
    common_dir="$(pwd)/$common_dir"
fi

if ! common_dir="$(cd "$common_dir" 2>/dev/null && pwd -P)"; then
    echo "forge: warning: could not resolve the git common directory — halt check skipped" >&2
    exit 0
fi

main_root="$(cd "$(dirname "$common_dir")" && pwd -P)" || {
    echo "forge: warning: could not resolve the main checkout — halt check skipped" >&2
    exit 0
}

sentinels=("$main_root/AGENT_HALT")
if [[ -n "$scope" ]]; then
    sentinels+=("$main_root/AGENT_HALT_$scope")
fi

# Agents must never create, delete, or bypass halt sentinels without explicit
# user direction.
for sentinel_path in "${sentinels[@]}"; do
    [[ -f "$sentinel_path" ]] || continue

    # The commit guard probes first so it can deliver its deny JSON before
    # asking this script to perform the advisory audit/event append.
    if [[ "$probe_only" == "1" ]]; then
        exit 1
    fi

    sentinel_name="${sentinel_path##*/}"
    echo "forge: operator halt engaged ($sentinel_name)" >&2
    echo "AI SDLC activity is paused. Do not start new work, commit, push, or" >&2
    echo "perform external or irreversible actions. Sentinel reason (if given):" >&2
    echo "----" >&2
    cat "$sentinel_path" >&2 2>/dev/null || true

    # Prepare the immutable event identity, then detach the advisory append.
    # The worker waits for this halt-check PID to disappear, so the caller
    # observes exit 1 before any attempt to acquire events.lock.
    halt_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    mkdir -p "$main_root/.forge/tmp" 2>/dev/null || true
    printf '%s halt detected (pid %s, cwd %s, sentinel %s)\n' \
        "$halt_at" "$$" "$(pwd)" "$sentinel_name" \
        >>"$main_root/.forge/tmp/halt-audit.log" 2>/dev/null || true
    halt_candidate=""
    staged_file="$(mktemp "${TMPDIR:-/tmp}/forge-halt-staged.XXXXXX")" || staged_file=""
    if [[ -n "$staged_file" ]] && git diff --cached >"$staged_file" 2>/dev/null; then
        halt_candidate="$(shasum -a 256 <"$staged_file" 2>/dev/null | awk '{print $1}')" || halt_candidate=""
    fi
    [[ -z "$staged_file" ]] || rm -f "$staged_file"
    halt_policy_sha="$(git rev-parse HEAD 2>/dev/null)" || halt_policy_sha=""
    [[ "$halt_policy_sha" =~ ^[0-9a-f]{40}$ || "$halt_policy_sha" =~ ^[0-9a-f]{64}$ ]] || halt_policy_sha=""
    plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
    halt_pid="$$"
    pending_event="$main_root/.forge/tmp/halt-event-pending.$$"
    : >"$pending_event" 2>/dev/null || pending_event=""
    (
        if [[ -n "$pending_event" ]]; then
            trap 'rm -f "$pending_event"' EXIT
        fi
        halt_wait_attempts=0
        while [[ "$halt_wait_attempts" -lt 200 ]] && kill -0 "$halt_pid" 2>/dev/null; do
            sleep 0.01
            halt_wait_attempts=$((halt_wait_attempts + 1))
        done
        python3 "$plugin_root/scripts/forge/emit-decision-event.py" \
            --at "$halt_at" \
            --candidate "$halt_candidate" \
            --event halt_event \
            --policy-sha "$halt_policy_sha" \
            --reason "$sentinel_name" \
            --surface check-halt \
            >/dev/null 2>&1 || true
    ) </dev/null >/dev/null 2>&1 &
    exit 1
done

exit 0
