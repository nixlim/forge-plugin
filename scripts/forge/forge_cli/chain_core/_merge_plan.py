"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
from typing import Any, Mapping, Collection
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
import copy


def _merge_plan_position_fact(
    prior: Mapping[str, Any], current: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    prior_steps = prior.get("steps")
    current_steps = current.get("steps")
    if not isinstance(prior_steps, Mapping) or not isinstance(current_steps, Mapping):
        return None
    for step_id, current_value in current_steps.items():
        prior_value = prior_steps.get(step_id)
        if current_value == prior_value:
            continue
        if isinstance(current_value, list) and current_value:
            fact = current_value[-1]
            if isinstance(fact, Mapping) and isinstance(
                fact.get("gate_plan_position"), Mapping
            ):
                return fact
    return None


def _merge_carried_gate_steps(
    steps: object,
    *,
    prior_generation_digests: Collection[str],
    successor_generation_digest: str,
) -> dict[str, Any]:
    """Build a compatibility projection without rewriting durable gate facts.

    FR-234 retains the predecessor records byte-for-byte.  The shared
    Revision-9 validator predates that rule and expects current-generation
    mechanical facts while it validates the next epoch, so this helper is
    used only on an in-memory compatibility copy.  Fresh successor facts may
    already be present later in a run list and are left unchanged.
    """

    if not isinstance(steps, Mapping):
        raise ValueError("merge carried gate steps are malformed")
    carried = copy.deepcopy(dict(steps))
    admitted_predecessors = frozenset(prior_generation_digests)
    if not all(SHA256_RE.fullmatch(digest) for digest in admitted_predecessors):
        raise ValueError("merge carried gate generation history is malformed")

    def rebind(value: object) -> None:
        if isinstance(value, dict):
            if "generation_digest" in value:
                if value["generation_digest"] in admitted_predecessors:
                    value["generation_digest"] = successor_generation_digest
                elif value["generation_digest"] != successor_generation_digest:
                    raise ValueError("merge carried gate fact is not predecessor-bound")
            for member in value.values():
                rebind(member)
        elif isinstance(value, list):
            for member in value:
                rebind(member)

    rebind(carried)
    return carried


def _merge_gate_step_generation_digests(steps: object) -> frozenset[str]:
    """Collect only generation digests from an authenticated prior step tree."""

    if not isinstance(steps, Mapping):
        raise ValueError("merge carried gate steps are malformed")
    digests: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, Mapping):
            if "generation_digest" in value:
                digest = value["generation_digest"]
                if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                    raise ValueError("merge carried gate generation history is malformed")
                digests.add(digest)
            for member in value.values():
                collect(member)
        elif isinstance(value, list):
            for member in value:
                collect(member)

    collect(steps)
    return frozenset(digests)


def _merge_current_authority_valid(state: Mapping[str, Any]) -> bool:
    """Recognize retained Gate-4 authority and an exact churn re-arm."""

    candidate = state.get("candidate")
    authorization = state.get("authorization")
    review = state.get("review")
    verdict = review.get("verdict") if isinstance(review, Mapping) else None
    if not isinstance(candidate, Mapping) or not isinstance(
        authorization, Mapping
    ):
        return False
    authorization_digest = str(authorization.get("generation_digest", ""))
    if not (
        authorization.get("candidate_head") == candidate.get("candidate_head")
        and SHA256_RE.fullmatch(authorization_digest) is not None
        and isinstance(verdict, Mapping)
        and verdict.get("verdict") == "PASS"
    ):
        return False
    tier = state.get("tier")
    approval = state.get("approval")
    if not isinstance(tier, Mapping):
        return False
    if tier.get("control") is not True and not (
        isinstance(approval, Mapping) and approval.get("purpose") == "remote-churn"
    ):
        return True
    if not (
        isinstance(approval, Mapping)
        and approval.get("chain_id") == state.get("chain_id")
        and approval.get("candidate") == candidate.get("candidate_head")
    ):
        return False
    purpose = approval.get("purpose")
    approval_digest = str(approval.get("generation_digest", ""))
    if purpose == "gate-4":
        return approval_digest == authorization_digest
    if purpose == "remote-churn":
        # Replay admits this record only after eight authenticated remote-only
        # defeats of an already-authorized tuple.  It acknowledges that exact
        # candidate and re-arms one later epoch without rewriting the retained
        # Gate-4 decision or its immutable generation binding.
        return SHA256_RE.fullmatch(approval_digest) is not None
    return False


def _merge_remote_only_equality_proof(
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Return DM-014's explicit equality witness for a remote-only successor."""

    return {
        name: copy.deepcopy(candidate.get(name))
        for name in _MERGE_REMOTE_ONLY_IDENTITY_FIELDS
    }


def _merge_carry_payload_valid(
    event: Mapping[str, Any],
    prior_candidate: Mapping[str, Any],
    carried_candidate: Mapping[str, Any],
) -> bool:
    payload = event.get("payload")
    required = {
        "delta",
        "prior_generation_digest",
        "successor_generation_digest",
        "equality_proof",
    }
    if not isinstance(payload, Mapping):
        return False
    members = frozenset(payload)
    if members not in {
        frozenset(required),
        frozenset({*required, "source_event_digest", "journal_batch"}),
    }:
        return False
    proof = payload.get("equality_proof")
    expected = _merge_remote_only_equality_proof(prior_candidate)
    return bool(
        payload.get("prior_generation_digest")
        == prior_candidate.get("generation_digest")
        and payload.get("successor_generation_digest")
        == carried_candidate.get("generation_digest")
        and proof == expected
        and proof == _merge_remote_only_equality_proof(carried_candidate)
    )


def _merge_plan_transition_valid(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> bool:
    if prior is None:
        return current.get("integration", {}).get("epoch") is None
    prior_integration = prior.get("integration")
    current_integration = current.get("integration")
    if not isinstance(prior_integration, Mapping) or not isinstance(
        current_integration, Mapping
    ):
        return False
    before = prior_integration.get("epoch")
    after = current_integration.get("epoch")
    event_name = event.get("event")
    if event_name == "epoch_intent":
        if not isinstance(after, Mapping) or after == before:
            return False
        plan = after.get("gate_plan")
        normal = (
            prior.get("state") == "authorized"
            and current.get("state") == "rebasing"
            and isinstance(plan, Mapping)
            and plan.get("status") == "unsealed"
        )
        retry = (
            prior.get("state") == "reverification_failed"
            and current.get("state") == "reverifying"
            and isinstance(plan, Mapping)
            and plan.get("status") == "sealed"
            and plan.get("seal_event_digest") == event.get("digest")
        )
        return bool(
            (normal or retry)
            and after.get("intent_digest") == event.get("digest")
        )
    if before is None:
        return after is None
    if after is None:
        return event_name in {
            "generation_refreshed",
            "generation_carried_forward",
            "fetch_result",
            "push_intent",
            "push_observed",
            "rebase_result",
            "reverification_result",
            "condition_recorded",
            "ownership_release_intent",
            "aborted",
            "closed",
        }
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return False
    identity_changed = any(
        before.get(name) != after.get(name)
        for name in ("operation_nonce", "generation_digest", "intent_digest", "started_at")
    )
    if identity_changed:
        successor = bool(
            event_name in {"rebase_result", "generation_carried_forward"}
            and before.get("operation_nonce") == after.get("operation_nonce")
            and before.get("intent_digest") == after.get("intent_digest")
            and before.get("started_at") == after.get("started_at")
            and before.get("gate_plan", {}).get("status") == "unsealed"
            and after.get("gate_plan", {}).get("status") == "sealed"
        )
        if not successor:
            return False
    before_plan = before.get("gate_plan")
    after_plan = after.get("gate_plan")
    if before_plan == after_plan:
        return True
    if not isinstance(before_plan, Mapping) or not isinstance(after_plan, Mapping):
        return False
    if (
        before_plan.get("status") == "unsealed"
        and after_plan.get("status") == "sealed"
    ):
        return bool(
            event_name
            in {"fetch_result", "rebase_result", "generation_carried_forward"}
            and after_plan.get("seal_event_digest") == event.get("digest")
            and after_plan.get("cursor") == 0
        )
    if event_name != "gate_recorded":
        return False
    immutable = {
        "status",
        "generation_digest",
        "policy_digest",
        "suite",
        "suite_digest",
        "seal_event_digest",
    }
    if any(before_plan.get(name) != after_plan.get(name) for name in immutable):
        return False
    cursor = before_plan.get("cursor")
    suite = before_plan.get("suite")
    if (
        type(cursor) is not int
        or not isinstance(suite, list)
        or cursor >= len(suite)
        or after_plan.get("cursor") != cursor + 1
    ):
        return False
    fact = _merge_plan_position_fact(prior, current)
    position = fact.get("gate_plan_position") if isinstance(fact, Mapping) else None
    selected = suite[cursor]
    return bool(
        isinstance(position, Mapping)
        and set(position)
        == {"seal_event_digest", "suite_digest", "cursor", "kind", "id"}
        and position.get("seal_event_digest") == before_plan.get("seal_event_digest")
        and position.get("suite_digest") == before_plan.get("suite_digest")
        and position.get("cursor") == cursor
        and position.get("kind") == selected.get("kind")
        and position.get("id") == selected.get("id")
        and fact.get("gate_intent_digest") is not None
        and SHA256_RE.fullmatch(str(fact["gate_intent_digest"])) is not None
        and fact.get("inflight_digest") is not None
        and SHA256_RE.fullmatch(str(fact["inflight_digest"])) is not None
    )
