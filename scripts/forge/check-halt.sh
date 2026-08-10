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

    sentinel_name="${sentinel_path##*/}"
    echo "forge: operator halt engaged ($sentinel_name)" >&2
    echo "AI SDLC activity is paused. Do not start new work, commit, push, or" >&2
    echo "perform external or irreversible actions. Sentinel reason (if given):" >&2
    echo "----" >&2
    cat "$sentinel_path" >&2 2>/dev/null || true

    # Auditing is best-effort and must never turn a detected halt into success.
    mkdir -p "$main_root/.forge/tmp" 2>/dev/null || true
    printf '%s halt detected (pid %s, cwd %s, sentinel %s)\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$$" "$(pwd)" "$sentinel_name" \
        >>"$main_root/.forge/tmp/halt-audit.log" 2>/dev/null || true
    exit 1
done

exit 0
