"""Authenticate replay vocabulary; no journal or run authority."""

from __future__ import annotations

REVIEW_ROLES = frozenset({"review-cheap", "review-final"})


REVIEW_VERDICTS = frozenset({"PASS", "BLOCK"})


_MERGE_DERIVED_STATE_FIELDS = frozenset({"last_event_at", "inactive_after", "journal_outbox"})


_MERGE_BOOTSTRAP_FETCH_EVIDENCE_FIELDS = frozenset(
    {
        "repository",
        "worktree",
        "branch",
        "target",
        "pre_fetch_head",
        "policy_digest",
        "operation_nonce",
        "attempt",
    }
)


_MERGE_REMOTE_OBSERVATION_INTENT_FIELDS = frozenset(
    {"schema", "transaction", "chain_id", "attempt_identity", "phase", "push_intent_digest"}
)


_MERGE_STATES = frozenset(
    {
        "classifying",
        "verifying",
        "reviewing",
        "revising",
        "awaiting_approval",
        "authorized",
        "rebasing",
        "rebase_conflict",
        "reverifying",
        "reverification_failed",
        "pushing",
        "pushed",
        "cleanup_pending",
        "closed",
        "aborted",
    }
)


_MERGE_STATE_KEYS = frozenset(
    {
        "schema",
        "chain_id",
        "kind",
        "state",
        "created_at",
        "last_event_at",
        "inactive_after",
        "owner",
        "run",
        "repository",
        "worktree",
        "branch",
        "target",
        "policy_source",
        "candidate",
        "tier",
        "steps",
        "review",
        "approval",
        "authorization",
        "integration",
        "cleanup",
    }
)


_MERGE_EVENT_EVIDENCE_FIELDS: dict[str, frozenset[str]] = {
    "ownership_intent": frozenset(
        {
            "worktree_digest",
            "claim_path",
            "intended_claim_digest",
            "predecessor_chain_id",
            "predecessor_release_digest",
        }
    ),
    "ownership_claimed": frozenset(
        {
            "ownership_intent_digest",
            "claim_inode",
            "claim_digest",
            "predecessor_chain_id",
            "predecessor_release_digest",
        }
    ),
    "ownership_release_intent": frozenset(
        {
            "target_terminal",
            "terminal_disposition",
            "source_state",
            "terminal_preconditions_digest",
            "release_mode",
        }
    ),
    "ownership_released": frozenset(
        {
            "release_intent_digest",
            "release_mode",
            "terminal_disposition",
            "claim_inode",
            "claim_digest",
            "claim_observation_digest",
        }
    ),
}


_MERGE_EVENT_NAMES = frozenset(
    {
        "chain_started",
        "ownership_intent",
        "ownership_claimed",
        "ownership_release_intent",
        "ownership_released",
        "gate_recorded",
        "review_requested",
        "review_attached",
        "review_disposition",
        "approval_recorded",
        "generation_refreshed",
        "generation_carried_forward",
        "epoch_intent",
        "fetch_intent",
        "fetch_result",
        "rebase_intent",
        "rebase_conflict",
        "rebase_result",
        "reverification_result",
        "push_intent",
        "push_observed",
        "cleanup_intent",
        "cleanup_result",
        "condition_recorded",
        "lock_release_result",
        "aborted",
        "closed",
        "journal_receipted",
    }
)


_MERGE_EVENT_REQUIRED_CHANGES: dict[str, frozenset[str]] = {
    "ownership_intent": frozenset({"worktree"}),
    "ownership_claimed": frozenset({"worktree"}),
    "ownership_release_intent": frozenset({"worktree"}),
    "ownership_released": frozenset({"worktree"}),
    "gate_recorded": frozenset({"steps"}),
    "review_requested": frozenset({"review"}),
    "review_attached": frozenset({"review"}),
    "review_disposition": frozenset({"review"}),
    "approval_recorded": frozenset({"approval"}),
    "generation_refreshed": frozenset({"integration"}),
    "generation_carried_forward": frozenset({"candidate", "integration"}),
    "epoch_intent": frozenset({"integration"}),
    "fetch_intent": frozenset({"integration"}),
    "fetch_result": frozenset({"integration"}),
    "rebase_intent": frozenset({"integration"}),
    "rebase_conflict": frozenset({"state", "integration"}),
    "rebase_result": frozenset({"integration"}),
    "reverification_result": frozenset({"steps", "integration"}),
    "push_intent": frozenset({"state", "integration"}),
    "push_observed": frozenset({"integration"}),
    "cleanup_intent": frozenset({"cleanup"}),
    "cleanup_result": frozenset({"cleanup"}),
    "condition_recorded": frozenset(),
    "lock_release_result": frozenset({"integration"}),
    "aborted": frozenset({"state"}),
    "closed": frozenset({"state"}),
}


_MERGE_HISTORICAL_ABORT_EVIDENCE_FIELDS = frozenset(
    {"terminal_disposition", "landed_head", "superseded_head", "observation_digest"}
)


_MERGE_BOOTSTRAP_EVENTS = frozenset(
    {
        "chain_started",
        "ownership_intent",
        "ownership_claimed",
        "fetch_intent",
        "fetch_result",
        "condition_recorded",
        "lock_release_result",
        "ownership_release_intent",
        "ownership_released",
        "aborted",
    }
)


_MERGE_QUARANTINE_EVIDENCE_FIELDS = frozenset({"condition", "quarantine", "observation_digest"})


_MERGE_MUTABLE_PREPUSH_STATES = frozenset(
    {"classifying", "verifying", "reviewing", "revising", "awaiting_approval", "authorized"}
)


_MERGE_NONTERMINAL_STATES = _MERGE_STATES - {"closed", "aborted"}


_MERGE_INITIAL_DELTA_FIELDS = _MERGE_STATE_KEYS - _MERGE_DERIVED_STATE_FIELDS


_MERGE_EVENT_TOP_LEVEL_CHANGES: dict[str, frozenset[str]] = {
    "chain_started": _MERGE_INITIAL_DELTA_FIELDS,
    "ownership_intent": frozenset({"worktree"}),
    "ownership_claimed": frozenset({"worktree"}),
    "ownership_release_intent": frozenset({"worktree"}),
    "ownership_released": frozenset({"worktree"}),
    "gate_recorded": frozenset({"state", "steps"}),
    "review_requested": frozenset({"review"}),
    "review_attached": frozenset({"state", "review", "approval", "authorization"}),
    "review_disposition": frozenset({"review"}),
    "approval_recorded": frozenset({"state", "review", "approval", "authorization", "integration"}),
    "generation_refreshed": frozenset(
        {
            "state",
            "policy_source",
            "candidate",
            "tier",
            "steps",
            "review",
            "approval",
            "authorization",
            "integration",
        }
    ),
    "generation_carried_forward": frozenset({"state", "candidate", "steps", "integration"}),
    "epoch_intent": frozenset({"state", "integration"}),
    "fetch_intent": frozenset({"state", "integration"}),
    "fetch_result": frozenset(
        {
            "state",
            "policy_source",
            "candidate",
            "tier",
            "steps",
            "review",
            "approval",
            "authorization",
            "integration",
        }
    ),
    "rebase_intent": frozenset({"state", "integration"}),
    "rebase_conflict": frozenset({"state", "integration"}),
    "rebase_result": frozenset(
        {
            "state",
            "policy_source",
            "candidate",
            "tier",
            "steps",
            "review",
            "approval",
            "authorization",
            "integration",
        }
    ),
    "reverification_result": frozenset(
        {"state", "steps", "review", "approval", "authorization", "integration"}
    ),
    "push_intent": frozenset({"state", "integration", "authorization"}),
    "push_observed": frozenset({"state", "integration"}),
    "cleanup_intent": frozenset({"state", "cleanup"}),
    "cleanup_result": frozenset({"state", "cleanup"}),
    "condition_recorded": frozenset({"state", "integration", "authorization"}),
    "lock_release_result": frozenset({"state", "integration"}),
    "aborted": frozenset({"state"}),
    "closed": frozenset({"state"}),
    "journal_receipted": frozenset({"journal_outbox"}),
}


_CONTINUE_REPLAY = object()
