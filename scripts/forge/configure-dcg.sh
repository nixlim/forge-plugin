#!/usr/bin/env bash

# Configure the project-scoped dcg exception needed by forge worktree cleanup.
# dcg is an optional integration: absence or failure must not stop init.

set -u

RULE_ID='core.git:branch-force-delete'
REASON='forge worktree-merge deletes branches only after merge-base containment proof'
PROJECT_ENTRY='{"type":"rule","value":"core.git:branch-force-delete"}[project]'

if ! command -v dcg >/dev/null 2>&1; then
    printf '%s\n' 'forge: dcg not found — no project allowlist change'
    exit 0
fi

if ! allowlist_output=$(dcg allowlist list 2>&1); then
    printf '%s\n' 'forge: dcg allowlist update failed'
    exit 0
fi

# dcg renders the scope directly beside each entry. Remove only whitespace so
# formatting changes cannot affect the fixed-string, project-scoped match.
normalized_output=$(printf '%s\n' "${allowlist_output}" | tr -d '[:space:]')
if printf '%s\n' "${normalized_output}" | grep -Fq -- "${PROJECT_ENTRY}"; then
    printf '%s\n' \
        'forge: dcg allowlist already contains core.git:branch-force-delete for this project'
    exit 0
fi

if dcg allow "${RULE_ID}" --project --reason "${REASON}" >/dev/null 2>&1; then
    printf '%s\n' \
        'forge: dcg allowlisted core.git:branch-force-delete for this project'
else
    printf '%s\n' 'forge: dcg allowlist update failed'
fi

exit 0
