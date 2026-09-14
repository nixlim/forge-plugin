"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.policy import sha256_bytes
from typing import Any, Mapping, Sequence
import copy


def _merge_gate_plan_valid(
    value: object,
    *,
    generation_digest: str | None = None,
    policy_digest: str | None = None,
) -> bool:
    """Validate Revision-10's exact sealed/unsealed epoch plan grammar."""

    if not isinstance(value, dict) or set(value) != {
        "status",
        "generation_digest",
        "policy_digest",
        "suite",
        "suite_digest",
        "cursor",
        "seal_event_digest",
    }:
        return False
    if value.get("status") == "unsealed":
        return all(value.get(name) is None for name in set(value) - {"status"})
    if value.get("status") != "sealed":
        return False
    suite = value.get("suite")
    cursor = value.get("cursor")
    if (
        not isinstance(value.get("generation_digest"), str)
        or SHA256_RE.fullmatch(str(value["generation_digest"])) is None
        or not isinstance(value.get("policy_digest"), str)
        or SHA256_RE.fullmatch(str(value["policy_digest"])) is None
        or not isinstance(suite, list)
        or type(cursor) is not int
        or int(cursor) < 0
        or int(cursor) > len(suite)
        or not isinstance(value.get("suite_digest"), str)
        or value.get("suite_digest") != sha256_bytes(canonical_bytes(suite))
        or not isinstance(value.get("seal_event_digest"), str)
        or SHA256_RE.fullmatch(str(value["seal_event_digest"])) is None
        or (
            generation_digest is not None
            and value.get("generation_digest") != generation_digest
        )
        or (
            policy_digest is not None
            and value.get("policy_digest") != policy_digest
        )
    ):
        return False
    for member in suite:
        if (
            not isinstance(member, dict)
            or set(member) != {"kind", "id"}
            or member.get("kind") not in {"gate", "scoped-mutation"}
            or not isinstance(member.get("id"), str)
            or not member["id"]
            or (
                member.get("kind") == "scoped-mutation"
                and member.get("id") != "scoped-mutation"
            )
        ):
            return False
    return True


def _merge_epoch_valid(state: Mapping[str, Any]) -> bool:
    integration = state.get("integration")
    if not isinstance(integration, Mapping):
        return False
    epoch = integration.get("epoch")
    if epoch is None:
        return True
    candidate = state.get("candidate")
    policy = state.get("policy_source")
    if (
        not isinstance(epoch, Mapping)
        or set(epoch)
        != {
            "operation_nonce",
            "generation_digest",
            "intent_digest",
            "started_at",
            "gate_plan",
        }
        or not _valid_nonce(epoch.get("operation_nonce"))
        or not isinstance(epoch.get("generation_digest"), str)
        or SHA256_RE.fullmatch(str(epoch["generation_digest"])) is None
        or not isinstance(epoch.get("intent_digest"), str)
        or SHA256_RE.fullmatch(str(epoch["intent_digest"])) is None
        or not _valid_utc_second(epoch.get("started_at"))
        or not isinstance(candidate, Mapping)
        or epoch.get("generation_digest") != candidate.get("generation_digest")
        or not isinstance(policy, Mapping)
        or not _merge_gate_plan_valid(
            epoch.get("gate_plan"),
            generation_digest=str(candidate.get("generation_digest", "")),
            policy_digest=(
                str(policy.get("digest", ""))
                if isinstance(epoch.get("gate_plan"), Mapping)
                and epoch["gate_plan"].get("status") == "sealed"
                else None
            ),
        )
    ):
        return False
    return True


def _merge_bootstrap_classification_pending(
    state: Mapping[str, Any] | None,
) -> bool:
    """Recognize Revision-12's sole complete-but-unclassified generation.

    The shared Revision-9 builder couples a non-null candidate to a populated
    tier.  Revision 12 deliberately separates those facts across the
    successful ``fetch_result`` and the later ``generation_refreshed`` event,
    so this predicate is kept deliberately narrow before the compatibility
    projection supplies the legacy validator's in-memory tier shape.
    """

    if not isinstance(state, Mapping):
        return False
    candidate = state.get("candidate")
    policy_source = state.get("policy_source")
    worktree = state.get("worktree")
    claim = worktree.get("claim") if isinstance(worktree, Mapping) else None
    review = state.get("review")
    integration = state.get("integration")
    intent = integration.get("intent") if isinstance(integration, Mapping) else None
    return bool(
        state.get("state") in {"classifying", "aborted"}
        and isinstance(candidate, Mapping)
        and isinstance(policy_source, Mapping)
        and policy_source.get("commit") == candidate.get("policy_commit")
        and policy_source.get("digest") == candidate.get("policy_digest")
        and isinstance(claim, Mapping)
        and (
            state.get("state") == "classifying"
            and claim.get("status") in {"owned", "releasing", "released"}
            or state.get("state") == "aborted"
            and claim.get("status") == "released"
        )
        and state.get("tier") is None
        and state.get("steps") == {}
        and (
            review == {}
            or isinstance(review, Mapping)
            and set(review) == {"iteration"}
            and type(review.get("iteration")) is int
            and 0 <= int(review["iteration"]) <= 8
        )
        and state.get("approval") == {}
        and state.get("authorization") == {}
        and isinstance(integration, Mapping)
        and integration.get("condition") == "none"
        and integration.get("primary_condition") == "none"
        and integration.get("epoch") is None
        and integration.get("observed") is None
        and integration.get("pre_rebase") is None
        and integration.get("conflict") is None
        and integration.get("push") is None
        and isinstance(intent, Mapping)
        and set(intent)
        == {
            "operation",
            "operation_nonce",
            "attempt",
            "result",
            "resolved_tip",
        }
        and intent.get("operation") == "fetch-result"
        and _valid_nonce(intent.get("operation_nonce"))
        and _valid_positive_int(intent.get("attempt"))
        and intent.get("result") == "success"
        and COMMIT_RE.fullmatch(str(intent.get("resolved_tip", ""))) is not None
        and intent.get("resolved_tip") == candidate.get("remote_tip")
    )


def _merge_revision9_compatibility_view(
    event: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Project only Revision-10 additive members away for the shared validator."""

    classification_pending = _merge_bootstrap_classification_pending(state)
    compat_state = copy.deepcopy(dict(state)) if isinstance(state, Mapping) else None
    if compat_state is not None:
        if classification_pending:
            # Validator-only projection.  This value is never durable and is
            # intentionally not the result of risk classification.
            if compat_state.get("state") == "classifying":
                compat_state["state"] = "verifying"
            compat_state["tier"] = {"control": False, "categories": []}
        steps = compat_state.get("steps")
        if isinstance(steps, dict):
            # Revision 10 gives scoped mutation its own sealed-plan position;
            # Revision 9 represented the same proof only inside Gate 1.
            steps.pop("scoped-mutation", None)
        integration = compat_state.get("integration")
        if isinstance(integration, dict):
            epoch = integration.get("epoch")
            if isinstance(epoch, dict):
                epoch.pop("gate_plan", None)
            intent = integration.get("intent")
            if isinstance(intent, dict):
                intent.pop("scope_request", None)
    compat_event = copy.deepcopy(dict(event)) if isinstance(event, Mapping) else None
    if compat_event is not None and isinstance(compat_event.get("payload"), dict):
        payload = compat_event["payload"]
        if compat_event.get("event") == "fetch_intent":
            payload.pop("scope_request", None)
        if compat_event.get("event") == "fetch_result":
            payload.pop("scope_fetch_binding", None)
            payload.pop("scope_proof", None)
        if compat_event.get("event") == "cleanup_result":
            payload.pop("cleanup_results", None)
        if compat_event.get("event") == "generation_carried_forward":
            payload.pop("prior_generation_digest", None)
            payload.pop("successor_generation_digest", None)
            payload.pop("equality_proof", None)
        if compat_event.get("event") == "condition_recorded":
            payload.pop("recovery_proof", None)
        if (
            classification_pending
            and compat_event.get("event") == "ownership_release_intent"
            and payload.get("source_state") == "classifying"
        ):
            payload["source_state"] = "verifying"
        delta = payload.get("delta")
        if (
            classification_pending
            and compat_event.get("event") == "fetch_result"
            and isinstance(delta, dict)
        ):
            # The successful fetch introduces the candidate while the durable
            # tier remains null.  Mirror only the compatibility state's
            # validator-only legacy shape in the copied event delta.
            delta["state"] = "verifying"
            delta["tier"] = {"control": False, "categories": []}
        if isinstance(delta, dict) and isinstance(delta.get("steps"), dict):
            delta["steps"].pop("scoped-mutation", None)
        if isinstance(delta, dict) and isinstance(delta.get("integration"), dict):
            epoch = delta["integration"].get("epoch")
            if isinstance(epoch, dict):
                epoch.pop("gate_plan", None)
            intent = delta["integration"].get("intent")
            if isinstance(intent, dict):
                intent.pop("scope_request", None)
    return compat_event, compat_state


def _merge_state_shape_valid(
    builders: Any, state: Mapping[str, Any], chain_id: str
) -> bool:
    if not _merge_epoch_valid(state):
        return False
    _event, compat = _merge_revision9_compatibility_view(None, state)
    return bool(
        compat is not None and builders._state_shape_valid(compat, chain_id, "merge")
    )


def _merge_ingest_state_shape_valid(
    builders: Any, state: Mapping[str, Any], chain_id: str
) -> bool:
    """Accept immutable Revision-9 captures without widening live replay."""

    return bool(
        _merge_state_shape_valid(builders, state, chain_id)
        or builders._state_shape_valid(state, chain_id, "merge")
    )


def _merge_history_uses_additive_grammar(
    history: Sequence[Mapping[str, Any]],
) -> bool:
    """Select the strict grammar only after a genuine additive carrier."""

    for event in history:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        if any(
            name in payload
            for name in ("scope_request", "scope_fetch_binding", "cleanup_results")
        ):
            return True
        delta = payload.get("delta")
        if not isinstance(delta, Mapping):
            continue
        cleanup = delta.get("cleanup")
        cleanup_intent = (
            cleanup.get("intent") if isinstance(cleanup, Mapping) else None
        )
        if (
            event.get("event") == "cleanup_intent"
            and isinstance(cleanup_intent, Mapping)
            and cleanup_intent.get("schema")
            == "forge-merge-cleanup-step-intent/1"
        ):
            return True
        integration = delta.get("integration")
        epoch = (
            integration.get("epoch") if isinstance(integration, Mapping) else None
        )
        if isinstance(epoch, Mapping) and "gate_plan" in epoch:
            return True
        approval = delta.get("approval")
        if (
            event.get("event") == "approval_recorded"
            and isinstance(approval, Mapping)
            and approval.get("purpose") == "remote-churn"
        ):
            return True
    return False
