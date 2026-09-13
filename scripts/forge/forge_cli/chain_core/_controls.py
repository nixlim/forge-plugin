"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations


COMMON_LOCK_OWNER_KINDS = frozenset({"merge", "push", "phase5"})


COMMON_LOCK_OPERATIONS = frozenset(
    {
        "start",
        "refresh",
        "finalize",
        "recover",
        "cleanup",
        "abort",
        "push",
        "phase5-scan",
    }
)


COMMON_LOCK_FENCE_OPERATIONS = frozenset(
    {
        "gate",
        "fetch",
        "tip-resolution",
        "remote-observation",
        "attribution-observation",
        "rebase",
        "continue",
        "abort",
        "push",
        "containment",
        "worktree-remove",
        "branch-delete",
    }
)


COMMON_LOCK_RECOVERY_KINDS = frozenset(
    {"fallback-owner", "fallback-owner-and-fence", "flock-held-dead-fence"}
)


_COMMON_LOCK_OWNER_KEYS = frozenset(
    {
        "schema",
        "owner_kind",
        "chain_id",
        "host",
        "pid",
        "nonce",
        "operation",
        "started_at",
    }
)


_COMMON_LOCK_FENCE_KEYS = frozenset(
    {
        "schema",
        "owner_kind",
        "chain_id",
        "operation",
        "host",
        "pid",
        "pgid",
        "started_at",
        "intent_digest",
        "nonce",
    }
)


_COMMON_LOCK_RECOVERY_KEYS = frozenset(
    {
        "schema",
        "recovery_kind",
        "host",
        "pid",
        "nonce",
        "started_at",
        "stale_owner_inode",
        "stale_owner_digest",
        "stale_owner_host",
        "stale_owner_pid",
        "stale_owner_kind",
        "stale_owner_chain_id",
        "inflight_inode",
        "inflight_digest",
        "inflight_host",
        "inflight_pgid",
        "inflight_owner_kind",
        "inflight_chain_id",
        "owner_dead_at",
        "group_dead_at",
    }
)


_CHAIN_LEASE_KEYS = frozenset(
    {"chain_id", "host", "nonce", "pid", "session", "started_at"}
)


_REQUIRED_COMMON_LOCK_CONTROLS = frozenset(
    {
        "canonical-records",
        "no-replace-publication",
        "portable-before-flock",
        "single-deadline",
        "three-topology-recovery",
        "immutable-recovery-reservation",
        "reservation-held-lifecycle-classification",
        "death-proof-revalidation",
        "reverse-release-order",
        "release-identity-revalidation",
        "fence-start-pipe",
        "fence-intent-revalidation",
        "fence-result-before-release",
        "process-group-termination",
        "bounded-output",
        "chain-lease-hardlink",
        "chain-lease-write-revalidation",
    }
)


COMMON_LOCK_CONTROLS = _REQUIRED_COMMON_LOCK_CONTROLS


CHAIN_TOMBSTONE_SCHEMA = "forge-chain-tombstone/1"


CHAIN_TOMBSTONE_EVENT = "frozen-abort"


CHAIN_TOMBSTONE_KEYS = frozenset(
    {"schema", "chain_id", "event", "reason", "recorded_at", "operator", "artifacts"}
)


_REQUIRED_MERGE_STORE_CONTROLS = frozenset(
    {
        "event-first-family",
        "family-isolated-enumeration",
        "separate-merge-grammar",
        "lease-tail-authentication",
        "nonrecursive-source-digest",
        "typed-journal-builders",
        "consequential-event-set",
        "projected-journal-outbox",
        "builder-transition-validation",
        "event-before-state",
        "post-serialization-journal-drain",
        "replay-projection-repair",
    }
)


MERGE_STORE_CONTROLS = _REQUIRED_MERGE_STORE_CONTROLS


_REQUIRED_MERGE_ADAPTER_CONTROLS = frozenset(
    {
        "admission-and-generation",
        "halt",
        "ordered-gate-suite",
        "mandatory-review-final",
        "run-relative-evidence",
    }
)


MERGE_ADAPTER_CONTROLS = _REQUIRED_MERGE_ADAPTER_CONTROLS


_REQUIRED_MERGE_INTEGRATION_CONTROLS = frozenset(
    {
        "bounded-epoch-budget",
        "composite-bootstrap-streaming",
        "conflict-continue-contract",
        "final-intended-head-mode",
        "loud-recover-flags",
        "nonmovement-counter-reset",
        "sealed-gate-plan",
        "post-fetch-scope-proof",
        "observation-first-recovery",
        "nonforce-cleanup",
        "push-retry",
        "rebase-result-proof",
        "scope-release-clean-status",
        "scope-sidecar-recovery",
        "successor-ancestry-observation",
    }
)


MERGE_INTEGRATION_CONTROLS = _REQUIRED_MERGE_INTEGRATION_CONTROLS


INGEST_PROOF_ORDER = (
    "chain-schema-and-digest-replay",
    "materialized-state",
    "repository",
    "policy",
    "generation",
    "current-gates",
    "review-package",
    "reviewer-role",
    "reviewer-iteration",
    "reviewer-verdict",
    "operator-approval",
    "landing-proof",
    "monotonic-transitions",
    "closing-head-containment",
    "task-membership",
    "scope-membership",
)


_REQUIRED_INGEST_PROOF_CONTROLS = frozenset(INGEST_PROOF_ORDER)


INGEST_PROOF_CONTROLS = _REQUIRED_INGEST_PROOF_CONTROLS


_MERGE_CLEANUP_INTENT_SCHEMA = "forge-merge-cleanup-step-intent/1"


_MERGE_CLEANUP_RESULT_SCHEMA = "forge-merge-cleanup-step-result/1"


_MERGE_CLEANUP_CLOSE_SCHEMA = "forge-merge-close-preconditions/2"


_MERGE_CLEANUP_RECOVERY_SCHEMA = "forge-merge-cleanup-recovery/1"


_MERGE_CLEANUP_FENCE_OPERATIONS = {
    "remote-fetch": "remote-observation",
    "remote-containment": "containment",
    "worktree-observation": "worktree-remove",
    "worktree-remove": "worktree-remove",
    "branch-observation": "branch-delete",
    "branch-delete": "branch-delete",
}


_EPOCH_FETCH_OBSERVATION_SCHEMA = "forge-epoch-fetch-observation/1"


_MERGE_CANDIDATE_OBSERVATION_SCHEMA = "forge-merge-candidate-observation/1"


_MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA = (
    "forge-merge-candidate-observation-evidence/1"
)


_BOOTSTRAP_FETCH_OBSERVATION_SCHEMA = "forge-bootstrap-fetch-observation/1"
