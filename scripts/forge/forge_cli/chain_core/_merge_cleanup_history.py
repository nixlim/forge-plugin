"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import copy
from typing import Any, Mapping, Sequence
from forge_cli.chain_core._bootstrap_observation import _bootstrap_fetch_observation_record_valid as _bootstrap_fetch_observation_record_valid, _bootstrap_fetch_observation_transition_valid as _bootstrap_fetch_observation_transition_valid
from forge_cli.chain_core._candidate_v2 import candidate_is_v2 as candidate_is_v2, _candidate_binding_for_state_with_candidate_v2 as _candidate_binding_for_state_with_candidate_v2, _binding_shape_valid_with_candidate_v2 as _binding_shape_valid_with_candidate_v2, _event_batch_records_with_candidate_v2 as _event_batch_records_with_candidate_v2, _binding_matches_source_fact_with_candidate_v2 as _binding_matches_source_fact_with_candidate_v2, _binding_is_current_with_candidate_v2 as _binding_is_current_with_candidate_v2
from forge_cli.chain_core._chain_state import validate_state as validate_state
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._fenced_child import _BlockedFenceChild as _BlockedFenceChild, _pipe_cloexec as _pipe_cloexec, _read_child_ack as _read_child_ack, _waitpid_nohang as _waitpid_nohang, _wait_for_child_exit as _wait_for_child_exit, _spawn_blocked_fence_child as _spawn_blocked_fence_child, _terminate_fenced_group as _terminate_fenced_group, _stop_unstarted_child as _stop_unstarted_child, _collect_fenced_child as _collect_fenced_child
from forge_cli.chain_core._ingest_capture import _read_ingest_input as _read_ingest_input, _capture_ingest_blob as _capture_ingest_blob, _capture_run_evidence as _capture_run_evidence, _capture_ingest_record_evidence as _capture_ingest_record_evidence
from forge_cli.chain_core._ingest_currency import _ingest_captured_paths as _ingest_captured_paths, _ingest_step_is_current as _ingest_step_is_current, _ingest_secret_scan_is_current as _ingest_secret_scan_is_current, _prove_ingest_live_chain as _prove_ingest_live_chain
from forge_cli.chain_core._lock_record_validators import _validate_owner_record as _validate_owner_record, _validate_fence_record as _validate_fence_record, _validate_recovery_record as _validate_recovery_record, _validate_chain_lease_record as _validate_chain_lease_record
from forge_cli.chain_core._merge_cleanup_intent import _recovery_event_intent as _recovery_event_intent, _recovery_cleanup_intent as _recovery_cleanup_intent, _merge_cleanup_expected_subject as _merge_cleanup_expected_subject, _merge_cleanup_expected_argv as _merge_cleanup_expected_argv, _merge_cleanup_intent_valid as _merge_cleanup_intent_valid
from forge_cli.chain_core._merge_events import _merge_event_outbox as _merge_event_outbox, _merge_payload_delta as _merge_payload_delta, reduce_merge_event as reduce_merge_event
from forge_cli.chain_core._merge_plan import _merge_plan_position_fact as _merge_plan_position_fact, _merge_carried_gate_steps as _merge_carried_gate_steps, _merge_gate_step_generation_digests as _merge_gate_step_generation_digests, _merge_current_authority_valid as _merge_current_authority_valid, _merge_remote_only_equality_proof as _merge_remote_only_equality_proof, _merge_carry_payload_valid as _merge_carry_payload_valid, _merge_plan_transition_valid as _merge_plan_transition_valid
from forge_cli.chain_core._merge_rebase import _parse_registered_worktrees as _parse_registered_worktrees, _merge_rebase_action as _merge_rebase_action, _merge_rebase_result_classification as _merge_rebase_result_classification, _merge_containment as _merge_containment, _merge_old_tip_all_false as _merge_old_tip_all_false, _merge_latest_contained_attempt as _merge_latest_contained_attempt, _merge_inactive_post_attempt_recovery_ready as _merge_inactive_post_attempt_recovery_ready, _remote_observation_heads as _remote_observation_heads, _remote_observation_fetch_argv as _remote_observation_fetch_argv, _remote_containment_argv as _remote_containment_argv
from forge_cli.chain_core._merge_state_shape import _merge_gate_plan_valid as _merge_gate_plan_valid, _merge_epoch_valid as _merge_epoch_valid, _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view as _merge_revision9_compatibility_view, _merge_state_shape_valid as _merge_state_shape_valid, _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY


def _merge_cleanup_evidence_history(
    history: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Project every cleanup carrier, including immutable Revision-9 facts."""

    evidence: list[dict[str, Any]] = []
    for member in history:
        payload = member.get("payload")
        if (
            member.get("event") not in {"cleanup_intent", "cleanup_result"}
            or not isinstance(payload, Mapping)
        ):
            continue
        evidence.append(
            {
                "event": member.get("event"),
                "event_digest": member.get("digest"),
                "payload": copy.deepcopy(dict(payload)),
            }
        )
    return evidence


def _merge_cleanup_history_summary(
    history: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reduce authenticated cleanup results for retry and close admission."""

    results: list[Mapping[str, Any]] = []
    for item in _merge_cleanup_evidence_history(history):
        payload = item.get("payload")
        carried = (
            payload.get("cleanup_results")
            if isinstance(payload, Mapping)
            else None
        )
        if (
            item.get("event") == "cleanup_result"
            and isinstance(carried, list)
            and len(carried) == 1
            and isinstance(carried[0], Mapping)
        ):
            results.append(carried[0])
    remote_fetch: Mapping[str, Any] | None = None
    remote_containment: Mapping[str, Any] | None = None
    worktree_complete = False
    branch_complete = False
    worktree_observed_present = False
    branch_observed_present = False
    branch_observed_absent = False
    for result in results:
        operation = result.get("operation")
        outcome = result.get("outcome")
        if operation == "remote-fetch":
            remote_fetch = result if outcome == "passed" else None
            remote_containment = None
            branch_observed_present = False
            branch_observed_absent = False
        elif operation == "remote-containment":
            observation = result.get("observation")
            fetched = (
                remote_fetch.get("observation")
                if isinstance(remote_fetch, Mapping)
                else None
            )
            if (
                outcome == "passed"
                and isinstance(observation, Mapping)
                and isinstance(fetched, Mapping)
                and observation.get("remote_tip") == fetched.get("oid")
            ):
                remote_containment = result
            else:
                remote_containment = None
        elif operation == "worktree-observation":
            worktree_observed_present = outcome == "passed"
            worktree_complete = outcome == "already-absent"
        elif operation == "worktree-remove":
            worktree_complete = bool(
                outcome == "passed" and worktree_observed_present
            )
            worktree_observed_present = False
        elif operation == "branch-observation":
            branch_observed_present = outcome == "passed"
            branch_observed_absent = outcome == "already-absent"
            branch_complete = branch_observed_absent
        elif operation == "branch-delete":
            branch_complete = bool(
                outcome == "passed" and branch_observed_present
            )
            branch_observed_present = False
            branch_observed_absent = False
    return {
        "results": results,
        "last_result": results[-1] if results else None,
        "remote_fetch": remote_fetch,
        "remote_containment": remote_containment,
        "worktree_complete": worktree_complete,
        "branch_complete": branch_complete,
        "worktree_observed_present": worktree_observed_present,
        "branch_observed_present": branch_observed_present,
        "branch_observed_absent": branch_observed_absent,
    }


def _merge_cleanup_unmatched_intent(
    history: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Return the sole strict cleanup intent without its immediate result."""

    unmatched: Mapping[str, Any] | None = None
    for event in history:
        if event.get("event") == "cleanup_intent":
            intent = _recovery_cleanup_intent(event)
            if (
                isinstance(intent, Mapping)
                and intent.get("schema") == _MERGE_CLEANUP_INTENT_SCHEMA
            ):
                unmatched = event
        elif event.get("event") == "cleanup_result" and unmatched is not None:
            payload = event.get("payload")
            results = (
                payload.get("cleanup_results")
                if isinstance(payload, Mapping)
                else None
            )
            result = (
                results[0]
                if isinstance(results, list)
                and len(results) == 1
                and isinstance(results[0], Mapping)
                else None
            )
            if (
                isinstance(result, Mapping)
                and result.get("intent_event_digest") == unmatched.get("digest")
            ):
                unmatched = None
    return unmatched


def _merge_cleanup_retry_proof_valid(
    history: Sequence[Mapping[str, Any]],
    unmatched: Mapping[str, Any],
) -> bool:
    """Admit a restart only after exact recovery closed the intent window."""

    if not history or history[-1].get("event") != "condition_recorded":
        return False
    recovery_event = history[-1]
    payload = recovery_event.get("payload")
    proof = payload.get("recovery_proof") if isinstance(payload, Mapping) else None
    lifecycle = proof.get("lifecycle") if isinstance(proof, Mapping) else None
    fence = proof.get("fence") if isinstance(proof, Mapping) else None
    intent = _recovery_cleanup_intent(unmatched)
    if not (
        recovery_event.get("previous_digest") == unmatched.get("digest")
        and isinstance(intent, Mapping)
        and isinstance(lifecycle, Mapping)
    ):
        return False
    if fence is None:
        return bool(
            lifecycle.get("operation") is None
            and lifecycle.get("intent_digest") is None
            and lifecycle.get("classification") == "owner-death-only"
        )
    fence_record = fence.get("record") if isinstance(fence, Mapping) else None
    fence_operation = intent.get("fence_operation")
    return bool(
        isinstance(fence_record, Mapping)
        and fence_record.get("intent_digest") == unmatched.get("digest")
        and fence_record.get("operation") == fence_operation
        and lifecycle.get("operation") == fence_operation
        and lifecycle.get("intent_digest") == unmatched.get("digest")
        and lifecycle.get("classification")
        == f"{fence_operation}-intent-pending"
    )


def _merge_cleanup_intent_transition_valid(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
) -> bool:
    if event.get("event") != "cleanup_intent":
        return True
    if prior is None:
        return False
    payload = event.get("payload")
    prior_cleanup = prior.get("cleanup")
    cleanup = current.get("cleanup")
    intent = cleanup.get("intent") if isinstance(cleanup, Mapping) else None
    if not (
        isinstance(payload, Mapping)
        and isinstance(prior_cleanup, Mapping)
        and isinstance(cleanup, Mapping)
        and set(cleanup) == {"condition", "intent"}
        and cleanup.get("condition") == prior_cleanup.get("condition")
        and payload.get("delta") == {"cleanup": cleanup}
        and _merge_cleanup_intent_valid(intent, current)
    ):
        return False
    summary = _merge_cleanup_history_summary(history)
    operation = intent.get("operation") if isinstance(intent, Mapping) else None
    last = summary["last_result"]
    unmatched = _merge_cleanup_unmatched_intent(history)
    recovery = intent.get("recovery") if isinstance(intent, Mapping) else None
    if unmatched is not None:
        unmatched_intent = _recovery_cleanup_intent(unmatched)
        if not (
            operation == "remote-fetch"
            and isinstance(unmatched_intent, Mapping)
            and _merge_cleanup_retry_proof_valid(history, unmatched)
            and isinstance(recovery, Mapping)
            and recovery
            == {
                "schema": _MERGE_CLEANUP_RECOVERY_SCHEMA,
                "intent_event_digest": unmatched.get("digest"),
                "operation": unmatched_intent.get("operation"),
                "fence_operation": unmatched_intent.get("fence_operation"),
                "recovery_event_digest": history[-1].get("digest"),
            }
        ):
            return False
    elif recovery is not None:
        return False
    if operation == "remote-fetch":
        return True
    if not isinstance(last, Mapping) or last.get("outcome") == "failed":
        return False
    if operation == "remote-containment":
        subject = intent.get("subject")
        observation = last.get("observation")
        return bool(
            last.get("operation") == "remote-fetch"
            and last.get("outcome") == "passed"
            and isinstance(subject, Mapping)
            and isinstance(observation, Mapping)
            and subject.get("remote_tip") == observation.get("oid")
        )
    if summary["remote_containment"] is None:
        return False
    if operation == "branch-observation":
        return bool(
            not summary["branch_observed_present"]
            and not summary["branch_observed_absent"]
            and (
                not summary["worktree_complete"]
                or not summary["branch_complete"]
            )
        )
    if operation == "worktree-observation":
        return bool(
            not summary["worktree_complete"]
            and (
                summary["branch_observed_present"]
                or summary["branch_observed_absent"]
            )
        )
    if operation == "worktree-remove":
        return bool(
            last.get("operation") == "worktree-observation"
            and last.get("outcome") == "passed"
        )
    if operation == "branch-delete":
        return bool(
            summary["worktree_complete"]
            and not summary["branch_complete"]
            and summary["branch_observed_present"]
        )
    return False


def _merge_history_has_git_mutation_intent(
    history: Sequence[Mapping[str, Any]],
) -> bool:
    """Recognize every FR-231 scope-release Git-mutation intent carrier."""

    for member in history:
        if member.get("event") in {"rebase_intent", "push_intent", "cleanup_intent"}:
            return True
        intent = _recovery_event_intent(member)
        if not isinstance(intent, Mapping):
            continue
        if intent.get("operation") in {
            "rebase",
            "continue",
            "abort",
            "push",
            "containment",
            "worktree-remove",
            "branch-delete",
        }:
            return True
        if (
            intent.get("schema") == "forge-remote-observation-progress/1"
            and intent.get("stage") in {"containment-intent", "containment-result"}
        ) or (
            intent.get("schema") == "forge-epoch-ancestry-intent/1"
            and intent.get("phase") in {"intent", "result"}
        ):
            return True
    return False
