"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import copy
import datetime as dt
from typing import Any, Mapping, MutableMapping, Sequence
from forge_cli.chain_core._bootstrap_observation import _bootstrap_fetch_observation_record_valid as _bootstrap_fetch_observation_record_valid, _bootstrap_fetch_observation_transition_valid as _bootstrap_fetch_observation_transition_valid
from forge_cli.chain_core._candidate_v2 import candidate_is_v2 as candidate_is_v2, _candidate_binding_for_state_with_candidate_v2 as _candidate_binding_for_state_with_candidate_v2, _binding_shape_valid_with_candidate_v2 as _binding_shape_valid_with_candidate_v2, _event_batch_records_with_candidate_v2 as _event_batch_records_with_candidate_v2, _binding_matches_source_fact_with_candidate_v2 as _binding_matches_source_fact_with_candidate_v2, _binding_is_current_with_candidate_v2 as _binding_is_current_with_candidate_v2
from forge_cli.chain_core._chain_state import validate_state as validate_state
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._fenced_child import _BlockedFenceChild as _BlockedFenceChild, _pipe_cloexec as _pipe_cloexec, _read_child_ack as _read_child_ack, _waitpid_nohang as _waitpid_nohang, _wait_for_child_exit as _wait_for_child_exit, _spawn_blocked_fence_child as _spawn_blocked_fence_child, _terminate_fenced_group as _terminate_fenced_group, _stop_unstarted_child as _stop_unstarted_child, _collect_fenced_child as _collect_fenced_child
from forge_cli.chain_core._ingest_capture import _read_ingest_input as _read_ingest_input, _capture_ingest_blob as _capture_ingest_blob, _capture_run_evidence as _capture_run_evidence, _capture_ingest_record_evidence as _capture_ingest_record_evidence
from forge_cli.chain_core._ingest_currency import _ingest_captured_paths as _ingest_captured_paths, _ingest_step_is_current as _ingest_step_is_current, _ingest_secret_scan_is_current as _ingest_secret_scan_is_current, _prove_ingest_live_chain as _prove_ingest_live_chain
from forge_cli.chain_core._lock_record_io import _read_owned_record_at as _read_owned_record_at, _same_published_record as _same_published_record, _open_lock_directory as _open_lock_directory, _opaque_path_evidence_at as _opaque_path_evidence_at, _inspect_common_lock_fd as _inspect_common_lock_fd, _create_private_record_at as _create_private_record_at, _publish_no_replace_link as _publish_no_replace_link, _revalidate_record_at as _revalidate_record_at, _unlink_revalidated_record_at as _unlink_revalidated_record_at, _record_at_if_present as _record_at_if_present
from forge_cli.chain_core._lock_record_validators import _validate_owner_record as _validate_owner_record, _validate_fence_record as _validate_fence_record, _validate_recovery_record as _validate_recovery_record, _validate_chain_lease_record as _validate_chain_lease_record
from forge_cli.chain_core._merge_candidate_observation import _merge_candidate_observation_record_valid as _merge_candidate_observation_record_valid, _merge_candidate_observation_transition_valid as _merge_candidate_observation_transition_valid, _merge_candidate_observation_evidence as _merge_candidate_observation_evidence, _merge_candidate_observation_evidence_valid as _merge_candidate_observation_evidence_valid
from forge_cli.chain_core._merge_candidate_observation_steps import _merge_candidate_observation_step_specs as _merge_candidate_observation_step_specs, _merge_candidate_observation_step_names as _merge_candidate_observation_step_names, _merge_candidate_observation_binding as _merge_candidate_observation_binding
from forge_cli.chain_core._merge_cleanup_history import _merge_cleanup_evidence_history as _merge_cleanup_evidence_history, _merge_cleanup_history_summary as _merge_cleanup_history_summary, _merge_cleanup_unmatched_intent as _merge_cleanup_unmatched_intent, _merge_cleanup_retry_proof_valid as _merge_cleanup_retry_proof_valid, _merge_cleanup_intent_transition_valid as _merge_cleanup_intent_transition_valid, _merge_history_has_git_mutation_intent as _merge_history_has_git_mutation_intent
from forge_cli.chain_core._merge_cleanup_intent import _recovery_event_intent as _recovery_event_intent, _recovery_cleanup_intent as _recovery_cleanup_intent, _merge_cleanup_expected_subject as _merge_cleanup_expected_subject, _merge_cleanup_expected_argv as _merge_cleanup_expected_argv, _merge_cleanup_intent_valid as _merge_cleanup_intent_valid
from forge_cli.chain_core._merge_cleanup_observation import _merge_cleanup_process_output as _merge_cleanup_process_output, _merge_cleanup_process_complete as _merge_cleanup_process_complete, _merge_cleanup_branch_observation as _merge_cleanup_branch_observation, _merge_cleanup_worktree_inventory as _merge_cleanup_worktree_inventory, _merge_cleanup_fetch_head_bytes as _merge_cleanup_fetch_head_bytes, _merge_cleanup_observation_valid as _merge_cleanup_observation_valid
from forge_cli.chain_core._merge_cleanup_result import _merge_cleanup_process_result_valid as _merge_cleanup_process_result_valid, _merge_cleanup_step_result_valid as _merge_cleanup_step_result_valid, _merge_cleanup_results_valid as _merge_cleanup_results_valid, _merge_cleanup_result_transition_valid as _merge_cleanup_result_transition_valid
from forge_cli.chain_core._merge_epoch import _epoch_fetch_observation_record_valid as _epoch_fetch_observation_record_valid, _epoch_fetch_observation_passed as _epoch_fetch_observation_passed, _epoch_ancestry_record_valid as _epoch_ancestry_record_valid, _epoch_fetch_result_intent_digest as _epoch_fetch_result_intent_digest
from forge_cli.chain_core._merge_events import _merge_event_outbox as _merge_event_outbox, _merge_payload_delta as _merge_payload_delta, reduce_merge_event as reduce_merge_event
from forge_cli.chain_core._merge_plan import _merge_plan_position_fact as _merge_plan_position_fact, _merge_carried_gate_steps as _merge_carried_gate_steps, _merge_gate_step_generation_digests as _merge_gate_step_generation_digests, _merge_current_authority_valid as _merge_current_authority_valid, _merge_remote_only_equality_proof as _merge_remote_only_equality_proof, _merge_carry_payload_valid as _merge_carry_payload_valid, _merge_plan_transition_valid as _merge_plan_transition_valid
from forge_cli.chain_core._merge_rebase import _parse_registered_worktrees as _parse_registered_worktrees, _merge_rebase_action as _merge_rebase_action, _merge_rebase_result_classification as _merge_rebase_result_classification, _merge_containment as _merge_containment, _merge_old_tip_all_false as _merge_old_tip_all_false, _merge_latest_contained_attempt as _merge_latest_contained_attempt, _merge_inactive_post_attempt_recovery_ready as _merge_inactive_post_attempt_recovery_ready, _remote_observation_heads as _remote_observation_heads, _remote_observation_fetch_argv as _remote_observation_fetch_argv, _remote_containment_argv as _remote_containment_argv
from forge_cli.chain_core._merge_recovery_lifecycle import _published_recovery_evidence_valid as _published_recovery_evidence_valid, _recovery_value_carries_inflight as _recovery_value_carries_inflight, _recovery_cleanup_result_matches as _recovery_cleanup_result_matches, _classify_merge_recovery_lifecycle as _classify_merge_recovery_lifecycle
from forge_cli.chain_core._merge_recovery_proof import _merge_recovery_proof_transition_valid as _merge_recovery_proof_transition_valid, _epoch_fetch_observation_predecessor_valid as _epoch_fetch_observation_predecessor_valid, _recovered_absent_rebase_intent_digest as _recovered_absent_rebase_intent_digest
from forge_cli.chain_core._merge_release import _merge_attempted_release_preconditions_valid as _merge_attempted_release_preconditions_valid, _merge_release_preconditions_valid as _merge_release_preconditions_valid
from forge_cli.chain_core._merge_scope import _validate_merge_scope_proof as _validate_merge_scope_proof, _merge_scope_event_binding_valid as _merge_scope_event_binding_valid, _merge_scope_transition_valid as _merge_scope_transition_valid
from forge_cli.chain_core._merge_scope_binding import _merge_scope_environment_contract as _merge_scope_environment_contract, _validate_merge_scope_request as _validate_merge_scope_request, _merge_retained_inflight as _merge_retained_inflight, _validate_merge_scope_fetch_binding as _validate_merge_scope_fetch_binding, _merge_scope_binding_names as _merge_scope_binding_names, _merge_full_patch_argv as _merge_full_patch_argv, _merge_scope_argv as _merge_scope_argv, _merge_scope_binding_validator as _merge_scope_binding_validator
from forge_cli.chain_core._merge_state_shape import _merge_gate_plan_valid as _merge_gate_plan_valid, _merge_epoch_valid as _merge_epoch_valid, _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view as _merge_revision9_compatibility_view, _merge_state_shape_valid as _merge_state_shape_valid, _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot
from forge_cli.chain_core._remote_observation import _remote_containment_evidence_valid as _remote_containment_evidence_valid, _remote_observation_progress_valid as _remote_observation_progress_valid, _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed, _replayed_remote_observation_completed as _replayed_remote_observation_completed
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY


def _merge_transition_valid(
    builders: Any,
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    *,
    context: MutableMapping[str, Any] | None,
    history: Sequence[Mapping[str, Any]] = (),
) -> bool:
    """Compose strict Revision-10 checks over the shared Revision-9 grammar."""

    chain_id = str(event.get("chain_id", ""))
    if (
        not _merge_state_shape_valid(builders, current, chain_id)
        or (prior is not None and not _merge_state_shape_valid(builders, prior, chain_id))
        or not _merge_plan_transition_valid(event, prior, current)
        or not _merge_scope_transition_valid(event, prior, current)
        or not _merge_recovery_proof_transition_valid(
            event, prior, current, history=history
        )
        or not _merge_cleanup_intent_transition_valid(
            event, prior, current, history
        )
        or not _merge_cleanup_result_transition_valid(event, prior, current)
        or not _merge_release_preconditions_valid(event, prior, history)
    ):
        return False
    compat_event, compat_current = _merge_revision9_compatibility_view(event, current)
    _unused, compat_prior = _merge_revision9_compatibility_view(None, prior)
    if compat_event is None or compat_current is None:
        return False
    prior_integration = prior.get("integration") if prior is not None else None
    current_integration = current.get("integration")
    gate_nonmovement_reset = bool(
        event.get("event") == "gate_recorded"
        and prior is not None
        and prior.get("state") == "reverifying"
        and current.get("state") == "reverification_failed"
        and isinstance(prior_integration, Mapping)
        and isinstance(current_integration, Mapping)
        and current_integration.get("remote_movement_count") == 0
        and all(
            prior_integration.get(name) == current_integration.get(name)
            for name in set(prior_integration)
            - {"epoch", "remote_movement_count"}
        )
    )
    if gate_nonmovement_reset and compat_prior is not None:
        compat_prior_integration = compat_prior.get("integration")
        compat_current_integration = compat_current.get("integration")
        if not isinstance(compat_prior_integration, dict) or not isinstance(
            compat_current_integration, dict
        ):
            return False
        compat_current_integration["remote_movement_count"] = (
            compat_prior_integration["remote_movement_count"]
        )
        compat_gate_payload = compat_event.get("payload")
        compat_delta = (
            compat_gate_payload.get("delta")
            if isinstance(compat_gate_payload, dict)
            else None
        )
        compat_delta_integration = (
            compat_delta.get("integration")
            if isinstance(compat_delta, dict)
            else None
        )
        if not isinstance(compat_delta_integration, dict):
            return False
        compat_delta_integration["remote_movement_count"] = (
            compat_prior_integration["remote_movement_count"]
        )
    compat_payload = compat_event.get("payload")
    if isinstance(compat_payload, dict) and isinstance(
        compat_payload.get("delta"), dict
    ):
        delta = compat_payload["delta"]
        if "integration" in delta and compat_prior is not None:
            if delta["integration"] == compat_prior.get("integration"):
                delta.pop("integration")
        if (
            event.get("event") == "generation_refreshed"
            and _merge_bootstrap_classification_pending(prior)
            and compat_prior is not None
        ):
            # Pending is projected to the legacy verifying/tier shape.  Do
            # not leave validator-only no-op members in the copied delta.
            for name in ("state", "tier"):
                if compat_prior.get(name) == compat_current.get(name):
                    delta.pop(name, None)
    trial_context = copy.deepcopy(dict(context)) if context is not None else {}
    current_epoch = current.get("integration", {}).get("epoch")
    replayed_epoch = trial_context.get("epoch_intent")
    if (
        isinstance(current_epoch, Mapping)
        and isinstance(current_epoch.get("gate_plan"), Mapping)
        and current_epoch["gate_plan"].get("status") == "sealed"
        and isinstance(replayed_epoch, dict)
        and replayed_epoch.get("digest") == current_epoch.get("intent_digest")
        and current_epoch.get("generation_digest")
        != replayed_epoch.get("generation_digest")
    ):
        # Revision 10 permits its authenticated sealer to bind the successor
        # generation while retaining the original epoch-event identity.
        replayed_epoch["generation_digest"] = current_epoch.get(
            "generation_digest"
        )
    if event.get("event") != "generation_carried_forward" and compat_prior is not None:
        prior_candidate = compat_prior.get("candidate")
        current_candidate = compat_current.get("candidate")
        if (
            isinstance(prior_candidate, Mapping)
            and isinstance(current_candidate, Mapping)
            and prior_candidate == current_candidate
        ):
            current_digest = str(current_candidate.get("generation_digest", ""))
            current_head = current_candidate.get("candidate_head")
            prior_authorization = compat_prior.get("authorization")
            current_authorization = compat_current.get("authorization")
            retained_authority = bool(
                isinstance(prior_authorization, dict)
                and isinstance(current_authorization, dict)
                and prior_authorization == current_authorization
                and prior_authorization.get("candidate_head") == current_head
                and prior_authorization.get("review_verdict") == "PASS"
                and SHA256_RE.fullmatch(
                    str(prior_authorization.get("generation_digest", ""))
                )
                is not None
                and prior_authorization.get("generation_digest") != current_digest
            )
            if retained_authority:
                prior_digest = str(prior_authorization["generation_digest"])
                historical_gate_digests = _merge_gate_step_generation_digests(
                    compat_prior.get("steps")
                )
                if historical_gate_digests and prior_digest not in (
                    historical_gate_digests
                ):
                    raise ValueError(
                        "merge carried gate facts lost their authorizing generation"
                    )
                for projection in (compat_prior, compat_current):
                    projection["steps"] = _merge_carried_gate_steps(
                        projection.get("steps"),
                        prior_generation_digests=historical_gate_digests,
                        successor_generation_digest=current_digest,
                    )
                    projection["authorization"] = copy.deepcopy(
                        projection["authorization"]
                    )
                    projection["authorization"][
                        "generation_digest"
                    ] = current_digest
                    approval = projection.get("approval")
                    if (
                        isinstance(approval, dict)
                        and approval.get("purpose") in {"gate-4", "remote-churn"}
                        and approval.get("candidate") == current_head
                    ):
                        projection["approval"] = copy.deepcopy(approval)
                        projection["approval"]["generation_digest"] = current_digest
                if isinstance(compat_payload, dict):
                    compat_delta = compat_payload.get("delta")
                    if isinstance(compat_delta, dict) and "steps" in compat_delta:
                        compat_delta["steps"] = _merge_carried_gate_steps(
                            compat_delta["steps"],
                            prior_generation_digests=historical_gate_digests,
                            successor_generation_digest=current_digest,
                        )
    if event.get("event") != "approval_recorded" and compat_prior is not None:
        prior_approval = prior.get("approval") if prior is not None else None
        current_approval = current.get("approval")
        if (
            isinstance(prior_approval, Mapping)
            and isinstance(current_approval, Mapping)
            and prior_approval == current_approval
            and prior_approval.get("purpose") == "remote-churn"
            and prior_approval.get("chain_id") == current.get("chain_id")
            and prior_approval.get("candidate")
            == current.get("candidate", {}).get("candidate_head")
            and SHA256_RE.fullmatch(
                str(prior_approval.get("generation_digest", ""))
            )
            is not None
        ):
            # Revision 9's shared validator predates the FR-232 churn re-arm
            # and recognizes only the retained Gate-4 purpose on later epoch
            # transitions.  Project the already replay-authenticated churn
            # acknowledgement back to that predecessor authority in memory;
            # the durable acknowledgement remains byte-for-byte unchanged.
            for projection in (compat_prior, compat_current):
                projection_approval = projection.get("approval")
                projection_candidate = projection.get("candidate")
                if not isinstance(projection_approval, dict) or not isinstance(
                    projection_candidate, Mapping
                ):
                    raise ValueError(
                        "merge remote-churn authority projection is malformed"
                    )
                projection_approval["purpose"] = "gate-4"
                projection_approval["generation_digest"] = projection_candidate[
                    "generation_digest"
                ]
    occupied_slot_above_minor_disposition = bool(
        event.get("event") == "review_disposition"
        and prior is not None
        and isinstance(prior.get("review"), Mapping)
        and isinstance(current.get("review"), Mapping)
        and prior["review"].get("operator_cosign_required") is True
        and isinstance(prior["review"].get("dispositions"), list)
        and isinstance(current["review"].get("dispositions"), list)
        and len(current["review"]["dispositions"])
        == len(prior["review"]["dispositions"]) + 1
        and current["review"]["dispositions"][:-1]
        == prior["review"]["dispositions"]
        and isinstance(current["review"]["dispositions"][-1], Mapping)
        and current["review"]["dispositions"][-1].get("severity")
        in {"CRITICAL", "MAJOR"}
    )
    if occupied_slot_above_minor_disposition:
        # Runtime serialization is not sufficient: replay is the system of
        # record, so a digest-valid carrier must not be able to introduce a
        # second above-MINOR disposition while the sole slot is occupied.
        return False
    pending_slot_minor_disposition = bool(
        event.get("event") == "review_disposition"
        and prior is not None
        and prior.get("state") == current.get("state")
        and prior.get("state") in {"reviewing", "revising"}
        and isinstance(prior.get("review"), Mapping)
        and isinstance(current.get("review"), Mapping)
        and prior["review"].get("operator_cosign_required") is True
        and current["review"].get("operator_cosign_required") is True
        and isinstance(prior["review"].get("dispositions"), list)
        and isinstance(current["review"].get("dispositions"), list)
        and len(current["review"]["dispositions"])
        == len(prior["review"]["dispositions"]) + 1
        and current["review"]["dispositions"][:-1]
        == prior["review"]["dispositions"]
        and isinstance(current["review"]["dispositions"][-1], Mapping)
        and current["review"]["dispositions"][-1].get("severity") == "MINOR"
    )
    if pending_slot_minor_disposition:
        projected_review = compat_current.get("review")
        projected_delta = (
            compat_event.get("payload", {}).get("delta")
            if isinstance(compat_event, Mapping)
            else None
        )
        projected_delta_review = (
            projected_delta.get("review")
            if isinstance(projected_delta, Mapping)
            else None
        )
        if not isinstance(projected_review, dict) or not isinstance(
            projected_delta_review, dict
        ):
            raise ValueError("merge MINOR disposition projection is malformed")
        # Revision 9 treated the flag as the severity of the newly appended
        # disposition.  Revision 10 makes it the one-slot aggregate.  Present
        # the legacy false value only to the shared validator; durable state
        # retains the already-occupied slot while the complete appended MINOR
        # object is still validated there.
        projected_review["operator_cosign_required"] = False
        projected_delta_review["operator_cosign_required"] = False
    remote_churn_approval_carrier = False
    if (
        event.get("event") == "approval_recorded"
        and prior is not None
        and compat_prior is not None
        and isinstance(prior.get("run_binding"), Mapping)
        and isinstance(prior.get("integration"), Mapping)
        and prior["integration"].get("condition") == "remote-churn"
        and isinstance(current.get("approval"), Mapping)
        and current["approval"].get("purpose") == "remote-churn"
    ):
        try:
            records, event_outbox, source_digest = builders._event_batch_records(
                copy.deepcopy(dict(event)), "merge"
            )
        except (KeyError, TypeError, ValueError):
            records, event_outbox, source_digest = (), None, None
        semantic_event = copy.deepcopy(compat_event)
        semantic_current = copy.deepcopy(compat_current)
        semantic_payload = semantic_event.get("payload")
        if isinstance(semantic_payload, dict):
            semantic_payload.pop("source_event_digest", None)
            semantic_payload.pop("journal_batch", None)
        semantic_current["journal_outbox"] = compat_prior.get("journal_outbox")
        remote_churn_approval_carrier = bool(
            len(records) == 1
            and records[0].get("type") == "decision"
            and records[0].get("outcome") == "chain-approval"
            and isinstance(source_digest, str)
            and SHA256_RE.fullmatch(source_digest) is not None
            and event_outbox == current.get("journal_outbox")
            and isinstance(records[0].get("binding"), Mapping)
            and builders._binding_matches_source_fact(
                records[0]["binding"],
                records[0],
                event,
                prior,
                current,
                family="merge",
            )
            and builders._merge_transition_valid(
                semantic_event,
                compat_prior,
                semantic_current,
                context=copy.deepcopy(trial_context),
            )
        )
    shared_pass = bool(
        remote_churn_approval_carrier
        or builders._merge_transition_valid(
            compat_event,
            compat_prior,
            compat_current,
            context=trial_context,
        )
    )
    recovery_proof_event = bool(
        event.get("event") == "condition_recorded"
        and isinstance(event.get("payload"), Mapping)
        and "recovery_proof" in event["payload"]
        and _merge_recovery_proof_transition_valid(
            event, prior, current, history=history
        )
    )
    if not shared_pass and recovery_proof_event:
        # The shared Revision-9 grammar has no state-neutral condition carrier.
        # Revision 12 adds exactly this authenticated proof without changing
        # any materialized lifecycle member.
        shared_pass = True
    if shared_pass and recovery_proof_event:
        recovery_proof = event.get("payload", {}).get("recovery_proof")
        lifecycle = (
            recovery_proof.get("lifecycle")
            if isinstance(recovery_proof, Mapping)
            else None
        )
        if isinstance(lifecycle, Mapping):
            trial_context["recovery_proof_bridge"] = {
                "event_digest": event.get("digest"),
                "previous_digest": event.get("previous_digest"),
                "operation": lifecycle.get("operation"),
                "intent_digest": lifecycle.get("intent_digest"),
                "classification": lifecycle.get("classification"),
            }
        if (
            isinstance(lifecycle, Mapping)
            and lifecycle.get("classification") == "fetch-intent-pending"
            and SHA256_RE.fullmatch(str(lifecycle.get("intent_digest", "")))
            is not None
        ):
            trial_context["bootstrap_recovery_proof"] = {
                "event_digest": event.get("digest"),
                "fetch_intent_event_digest": lifecycle.get("intent_digest"),
            }
    event_name = event.get("event")
    replay_event_at = builders._utc_value(event.get("at"))
    replay_prior_deadline = (
        builders._utc_value(prior.get("inactive_after"))
        if prior is not None
        else None
    )
    replay_current_integration = current.get("integration")
    replay_current_intent = (
        replay_current_integration.get("intent")
        if isinstance(replay_current_integration, Mapping)
        else None
    )
    inactive_post_push_observation = bool(
        event_name == "push_observed"
        and replay_event_at is not None
        and replay_prior_deadline is not None
        and replay_event_at >= replay_prior_deadline
        and isinstance(replay_current_intent, Mapping)
        and replay_current_intent.get("schema")
        == "forge-remote-observation-intent/1"
        and replay_current_intent.get("phase") == "post-push"
    )
    if inactive_post_push_observation:
        if not _replayed_remote_observation_completed(
            event, current, trial_context
        ):
            return False
        _require_merge_integration_control("observation-first-recovery")
    epoch_fetch_intent_digest = _epoch_fetch_result_intent_digest(
        event, prior, current, trial_context
    )
    interposed_epoch_fetch = bool(
        event_name == "fetch_result"
        and prior is not None
        and prior.get("state") == "rebasing"
        and isinstance(trial_context.get("epoch_fetch_observation"), Mapping)
    )
    if interposed_epoch_fetch and epoch_fetch_intent_digest is None:
        return False
    if not shared_pass and epoch_fetch_intent_digest is not None:
        bridged_event = copy.deepcopy(compat_event)
        bridged_event["previous_digest"] = epoch_fetch_intent_digest
        bridged_current = copy.deepcopy(compat_current)
        if (
            prior is not None
            and prior.get("state") == "rebasing"
            and current.get("state") == "reverifying"
        ):
            bridged_current["state"] = "rebasing"
            bridged_payload = bridged_event.get("payload")
            bridged_delta = (
                bridged_payload.get("delta")
                if isinstance(bridged_payload, dict)
                else None
            )
            if not isinstance(bridged_delta, dict):
                return False
            bridged_delta.pop("state", None)
        bridged_context = copy.deepcopy(trial_context)
        for name in (
            "epoch_fetch_observation",
            "candidate_observation_active",
            "candidate_observation",
            "epoch_ancestry_observation",
        ):
            bridged_context.pop(name, None)
        if builders._merge_transition_valid(
            bridged_event,
            compat_prior,
            bridged_current,
            context=bridged_context,
        ):
            shared_pass = True
            trial_context = bridged_context
    replayed_bootstrap = trial_context.get("bootstrap_fetch_observation")
    bootstrap_candidate = trial_context.get("candidate_observation")
    bootstrap_evidence = (
        replayed_bootstrap.get("evidence")
        if isinstance(replayed_bootstrap, Mapping)
        and isinstance(replayed_bootstrap.get("evidence"), Mapping)
        else None
    )
    bootstrap_result_predecessor = bool(
        isinstance(bootstrap_evidence, Mapping)
        and (
            event.get("previous_digest")
            == replayed_bootstrap.get("restore_event_digest")
            or (
                isinstance(bootstrap_candidate, Mapping)
                and bootstrap_candidate.get("source_intent")
                == bootstrap_evidence.get("source_intent")
                and event.get("previous_digest")
                == bootstrap_candidate.get("restore_event_digest")
            )
        )
    )
    if (
        not shared_pass
        and event_name == "fetch_result"
        and prior is not None
        and isinstance(replayed_bootstrap, Mapping)
        and isinstance(replayed_bootstrap.get("evidence"), Mapping)
        and prior.get("integration", {}).get("intent")
        == replayed_bootstrap["evidence"].get("source_intent")
        and bootstrap_result_predecessor
    ):
        bridged_event = copy.deepcopy(compat_event)
        bridged_event["previous_digest"] = replayed_bootstrap.get(
            "fetch_intent_event_digest"
        )
        bridged_context = copy.deepcopy(trial_context)
        for name in (
            "bootstrap_fetch_observation",
            "candidate_observation_active",
            "candidate_observation",
        ):
            bridged_context.pop(name, None)
        if builders._merge_transition_valid(
            bridged_event,
            compat_prior,
            compat_current,
            context=bridged_context,
        ):
            shared_pass = True
            trial_context = bridged_context
    recovery_bridge = trial_context.get("bootstrap_recovery_proof")
    if (
        not shared_pass
        and event_name == "fetch_result"
        and prior is not None
        and isinstance(recovery_bridge, Mapping)
        and event.get("previous_digest") == recovery_bridge.get("event_digest")
        and prior.get("integration", {}).get("intent", {}).get("operation")
        == "fetch"
    ):
        bridged_event = copy.deepcopy(compat_event)
        bridged_event["previous_digest"] = recovery_bridge.get(
            "fetch_intent_event_digest"
        )
        bridged_context = copy.deepcopy(trial_context)
        bridged_context.pop("bootstrap_recovery_proof", None)
        if builders._merge_transition_valid(
            bridged_event,
            compat_prior,
            compat_current,
            context=bridged_context,
        ):
            shared_pass = True
            trial_context = bridged_context
    raw_result = trial_context.get("rebase_raw_result")
    replayed_rebase_intent = trial_context.get("rebase_intent")
    if (
        not shared_pass
        and event_name in {"rebase_conflict", "rebase_result"}
        and prior is not None
        and isinstance(raw_result, Mapping)
        and isinstance(replayed_rebase_intent, Mapping)
        and raw_result.get("digest") == event.get("previous_digest")
        and raw_result.get("intent_digest") == replayed_rebase_intent.get("digest")
        and raw_result.get("generation_digest") == event.get("generation_digest")
        and raw_result.get("evidence") == prior.get("integration", {}).get("intent")
        and _merge_rebase_result_classification(prior) in {"success", "failed"}
    ):
        bridged_event = copy.deepcopy(compat_event)
        bridged_event["previous_digest"] = replayed_rebase_intent["digest"]
        bridged_context = copy.deepcopy(trial_context)
        bridged_context.pop("rebase_raw_result", None)
        if builders._merge_transition_valid(
            bridged_event,
            compat_prior,
            compat_current,
            context=bridged_context,
        ):
            shared_pass = True
            trial_context = bridged_context
    recovered_absent_rebase_intent = _recovered_absent_rebase_intent_digest(
        event, prior, trial_context
    )
    if not shared_pass and recovered_absent_rebase_intent is not None:
        bridged_event = copy.deepcopy(compat_event)
        bridged_event["previous_digest"] = recovered_absent_rebase_intent
        bridged_context = copy.deepcopy(trial_context)
        for name in (
            "candidate_observation_active",
            "candidate_observation",
            "recovery_proof_bridge",
        ):
            bridged_context.pop(name, None)
        if builders._merge_transition_valid(
            bridged_event,
            compat_prior,
            compat_current,
            context=bridged_context,
        ):
            shared_pass = True
            trial_context = bridged_context
    if (
        shared_pass
        and event_name == "rebase_result"
        and prior is not None
        and prior.get("state") == current.get("state") == "rebasing"
        and prior.get("candidate") == current.get("candidate")
        and _merge_rebase_result_classification(current) in {"success", "failed"}
        and isinstance(trial_context.get("rebase_intent"), Mapping)
    ):
        trial_context["rebase_raw_result"] = {
            "digest": event.get("digest"),
            "intent_digest": trial_context["rebase_intent"].get("digest"),
            "generation_digest": event.get("generation_digest"),
            "evidence": copy.deepcopy(current.get("integration", {}).get("intent")),
        }
    if not shared_pass:
        direct_retry = bool(
            event_name == "epoch_intent"
            and prior is not None
            and prior.get("state") == "reverification_failed"
            and current.get("state") == "reverifying"
        )
        fact = _merge_plan_position_fact(prior or {}, current)
        scoped_position = bool(
            event_name == "gate_recorded"
            and isinstance(fact, Mapping)
            and fact.get("gate_plan_position", {}).get("kind") == "scoped-mutation"
            and prior is not None
            and prior.get("state") == current.get("state") == "reverifying"
        )
        payload = event.get("payload")
        prior_push = (
            prior_integration.get("push")
            if isinstance(prior_integration, Mapping)
            else None
        )
        current_push = (
            current_integration.get("push")
            if isinstance(current_integration, Mapping)
            else None
        )
        event_at = builders._utc_value(event.get("at"))
        prior_deadline = (
            builders._utc_value(prior.get("inactive_after"))
            if prior is not None
            else None
        )
        current_deadline = builders._utc_value(current.get("inactive_after"))
        active_event = bool(
            event_at is not None
            and prior_deadline is not None
            and current_deadline is not None
            and event_at < prior_deadline
            and current.get("last_event_at") == event.get("at")
            and current_deadline == event_at + dt.timedelta(hours=24)
        )
        delta = payload.get("delta") if isinstance(payload, Mapping) else None
        plain_delta = bool(
            isinstance(payload, Mapping)
            and set(payload) == {"delta"}
            and isinstance(delta, Mapping)
        )
        replayed_push = trial_context.get("push_intent")
        replayed_remote_observation = trial_context.get("remote_observation")
        scope_exceeded_result = bool(
            event_name == "fetch_result"
            and prior is not None
            and current.get("candidate") is not None
            and current.get("state") == "classifying"
            and isinstance(payload, Mapping)
            and isinstance(payload.get("scope_proof"), Mapping)
            and payload["scope_proof"].get("result") == "exceeded"
        )
        sealed_fetch_to_reverify = bool(
            event_name == "fetch_result"
            and epoch_fetch_intent_digest is None
            and prior is not None
            and prior.get("state") == "rebasing"
            and current.get("state") == "reverifying"
            and isinstance(current_integration, Mapping)
            and isinstance(current_integration.get("epoch"), Mapping)
            and current_integration["epoch"].get("gate_plan", {}).get("status")
            == "sealed"
        )
        sealed_rebase_successor = bool(
            event_name == "rebase_result"
            and prior is not None
            and prior.get("state") in {"rebasing", "rebase_conflict"}
            and current.get("state") == "reverifying"
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and isinstance(prior_integration.get("epoch"), Mapping)
            and isinstance(current_integration.get("epoch"), Mapping)
            and prior_integration["epoch"].get("gate_plan", {}).get("status")
            == "unsealed"
            and current_integration["epoch"].get("gate_plan", {}).get("status")
            == "sealed"
            and prior.get("candidate") != current.get("candidate")
        )
        current_remote_intent = (
            current_integration.get("intent")
            if isinstance(current_integration, Mapping)
            else None
        )
        remote_observation_intent_valid = bool(
            isinstance(current_remote_intent, Mapping)
            and set(current_remote_intent)
            == {
                "schema",
                "transaction",
                "chain_id",
                "attempt_identity",
                "phase",
                "push_intent_digest",
            }
            and current_remote_intent.get("schema")
            == "forge-remote-observation-intent/1"
            and current_remote_intent.get("transaction") == "merge"
            and current_remote_intent.get("chain_id") == current.get("chain_id")
            and isinstance(current_epoch, Mapping)
            and current_remote_intent.get("attempt_identity")
            == current_epoch.get("intent_digest")
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest") == current_epoch.get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and (
                (
                    current_remote_intent.get("phase") == "final-prepush"
                    and current_remote_intent.get("push_intent_digest") is None
                    and replayed_epoch.get("push_consumed") is False
                )
                or (
                    current_remote_intent.get("phase") == "post-push"
                    and replayed_epoch.get("push_consumed") is True
                    and isinstance(replayed_push, Mapping)
                    and replayed_push.get("generation_digest")
                    == event.get("generation_digest")
                    and current_remote_intent.get("push_intent_digest")
                    == replayed_push.get("digest")
                )
            )
        )
        inactive_post_attempt_observation_intent = bool(
            prior is not None
            and isinstance(prior_integration, Mapping)
            and remote_observation_intent_valid
            and _merge_inactive_post_attempt_recovery_ready(prior, history)
            and event_at is not None
            and prior_deadline is not None
            and event_at >= prior_deadline
            and current_deadline == prior_deadline
            and current.get("last_event_at") == event.get("at")
            and current_remote_intent.get("phase") == "post-push"
            and current_remote_intent.get("attempt_identity")
            == prior_integration.get("epoch", {}).get("intent_digest")
        )
        observation_progress_restore = bool(
            prior is not None
            and isinstance(prior_integration, Mapping)
            and isinstance(prior_integration.get("intent"), Mapping)
            and isinstance(current_remote_intent, Mapping)
            and _remote_observation_progress_valid(
                prior, prior_integration["intent"]
            )
            and prior_integration["intent"].get("stage")
            in {"fetch-result", "containment-result"}
            and isinstance(replayed_remote_observation, Mapping)
            and replayed_remote_observation.get("generation_digest")
            == event.get("generation_digest")
            and replayed_remote_observation.get("progress_event_digest")
            == event.get("previous_digest")
            and replayed_remote_observation.get("progress")
            == prior_integration["intent"]
            and replayed_remote_observation.get("intent")
            == current_remote_intent
        )
        observation_intent = bool(
            event_name == "condition_recorded"
            and prior is not None
            and prior.get("state") == current.get("state")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and current_integration.get("condition")
            == prior_integration.get("condition")
            and current_integration.get("primary_condition")
            == prior_integration.get("primary_condition")
            and isinstance(current_integration.get("intent"), Mapping)
            and current_integration["intent"].get("schema")
            == "forge-remote-observation-intent/1"
            and remote_observation_intent_valid
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"intent"}
            )
            and plain_delta
            and delta == {"integration": current_integration}
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {"last_event_at", "inactive_after", "integration"}
            )
            and (
                active_event
                or inactive_post_attempt_observation_intent
                or observation_progress_restore
            )
        )
        push_result_recorded = bool(
            event_name == "condition_recorded"
            and prior is not None
            and prior.get("state") == current.get("state") == "pushing"
            and isinstance(prior_push, Mapping)
            and isinstance(current_push, Mapping)
            and prior_push.get("result") is None
            and isinstance(current_push.get("result"), Mapping)
            and all(
                prior_push.get(name) == current_push.get(name)
                for name in set(prior_push) - {"result"}
            )
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"push"}
            )
        )
        candidate_observation_progress = bool(
            event_name == "condition_recorded"
            and prior is not None
            and prior.get("state") == current.get("state")
            and plain_delta
            and delta == {"integration": current_integration}
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {"last_event_at", "inactive_after", "integration"}
            )
            and _merge_candidate_observation_transition_valid(prior, current)
        )
        bootstrap_fetch_observation = bool(
            event_name == "condition_recorded"
            and prior is not None
            and prior.get("state") == current.get("state") == "classifying"
            and plain_delta
            and delta == {"integration": current_integration}
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {"last_event_at", "inactive_after", "integration"}
            )
            and _bootstrap_fetch_observation_transition_valid(prior, current)
        )
        stable_push_boundary = bool(
            prior is not None
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {
                    "last_event_at",
                    "inactive_after",
                    "state",
                    "review",
                    "approval",
                    "authorization",
                    "integration",
                }
            )
        )
        current_intent = (
            current_integration.get("intent")
            if isinstance(current_integration, Mapping)
            else None
        )
        prior_intent = (
            prior_integration.get("intent")
            if isinstance(prior_integration, Mapping)
            else None
        )
        remote_observation_progress_predecessor = bool(
            isinstance(replayed_remote_observation, Mapping)
            and replayed_remote_observation.get("generation_digest")
            == event.get("generation_digest")
            and isinstance(replayed_remote_observation.get("intent"), Mapping)
            and isinstance(current_intent, Mapping)
            and all(
                replayed_remote_observation["intent"].get(name)
                == current_intent.get(name)
                for name in {
                    "transaction",
                    "chain_id",
                    "attempt_identity",
                    "phase",
                    "push_intent_digest",
                }
            )
            and (
                (
                    replayed_remote_observation.get("intent_event_digest")
                    == event.get("previous_digest")
                    and replayed_remote_observation.get("intent") == prior_intent
                    and replayed_remote_observation.get("progress_event_digest")
                    is None
                    and replayed_remote_observation.get("restore_event_digest")
                    is None
                    and replayed_remote_observation.get("completed_progress") is None
                )
                or (
                    replayed_remote_observation.get("progress_event_digest")
                    == event.get("previous_digest")
                    and replayed_remote_observation.get("progress") == prior_intent
                )
            )
        )
        replayed_fetch_observation = trial_context.get("epoch_fetch_observation")
        replayed_candidate_observation = trial_context.get(
            "candidate_observation"
        )
        epoch_fetch_observation = bool(
            event_name == "condition_recorded"
            and prior is not None
            and prior.get("state") == current.get("state") == "rebasing"
            and active_event
            and plain_delta
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and isinstance(prior_intent, Mapping)
            and prior_intent.get("operation") == "fetch"
            and isinstance(current_intent, Mapping)
            and _epoch_fetch_observation_record_valid(current, current_intent)
            and _epoch_fetch_observation_predecessor_valid(
                event, current_intent, prior_intent, trial_context
            )
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"intent"}
            )
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {"last_event_at", "inactive_after", "integration"}
            )
            and delta == {"integration": current_integration}
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
        )
        ancestry_intent_transition = bool(
            isinstance(current_intent, Mapping)
            and current_intent.get("phase") == "intent"
            and _epoch_ancestry_record_valid(current, current_intent)
            and isinstance(prior_intent, Mapping)
            and _epoch_fetch_observation_record_valid(prior or {}, prior_intent)
            and _epoch_fetch_observation_passed(prior_intent)
            and isinstance(replayed_fetch_observation, Mapping)
            and current_intent.get("fetch_observation_event_digest")
            == replayed_fetch_observation.get("digest")
            and replayed_fetch_observation.get("evidence") == prior_intent
            and isinstance(replayed_candidate_observation, Mapping)
            and replayed_candidate_observation.get("source_intent")
            == prior_intent
            and current_intent.get("candidate_observation_digest")
            == replayed_candidate_observation.get("evidence_digest")
            and event.get("previous_digest")
            == replayed_candidate_observation.get("restore_event_digest")
            and prior is not None
            and prior.get("state") == current.get("state") == "rebasing"
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"intent"}
            )
        )
        ancestry_result_transition = bool(
            isinstance(prior_intent, Mapping)
            and prior_intent.get("phase") == "intent"
            and _epoch_ancestry_record_valid(prior or {}, prior_intent)
            and isinstance(current_intent, Mapping)
            and current_intent.get("phase") == "result"
            and _epoch_ancestry_record_valid(current, current_intent)
            and current_intent.get("intent_event_digest")
            == event.get("previous_digest")
            and all(
                prior_intent.get(name) == current_intent.get(name)
                for name in set(prior_intent) - {"phase", "recorded_at"}
            )
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"intent", "epoch"}
            )
            and isinstance(prior_integration.get("epoch"), Mapping)
            and isinstance(current_integration.get("epoch"), Mapping)
            and all(
                prior_integration["epoch"].get(name)
                == current_integration["epoch"].get(name)
                for name in set(prior_integration["epoch"])
            )
            and current_integration["epoch"].get("gate_plan", {}).get("status")
            == "unsealed"
            and prior is not None
            and prior.get("state") == current.get("state") == "rebasing"
        )
        epoch_ancestry_progress = bool(
            event_name == "condition_recorded"
            and prior is not None
            and active_event
            and plain_delta
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {"last_event_at", "inactive_after", "integration"}
            )
            and (ancestry_intent_transition or ancestry_result_transition)
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and delta
            == {"integration": current_integration}
        )
        post_push_observation_intent = bool(
            isinstance(current_intent, Mapping)
            and set(current_intent)
            == {
                "schema",
                "transaction",
                "chain_id",
                "attempt_identity",
                "phase",
                "push_intent_digest",
            }
            and current_intent.get("schema")
            == "forge-remote-observation-intent/1"
            and current_intent.get("transaction") == "merge"
            and current_intent.get("chain_id") == current.get("chain_id")
            and current_intent.get("phase") == "post-push"
            and isinstance(current_epoch, Mapping)
            and current_intent.get("attempt_identity")
            == current_epoch.get("intent_digest")
            and isinstance(replayed_push, Mapping)
            and current_intent.get("push_intent_digest")
            == replayed_push.get("digest")
        )
        observation_progress = bool(
            event_name == "condition_recorded"
            and stable_push_boundary
            and prior is not None
            and prior.get("state") == current.get("state")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"intent"}
            )
            and _remote_observation_progress_transition_valid(prior, current)
            and isinstance(current_intent, Mapping)
            and remote_observation_progress_predecessor
            and (
                current_intent.get("stage") != "containment-intent"
                or active_event
                or replayed_remote_observation.get("admitted_inactive") is True
            )
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and (
                (
                    current_intent.get("phase") == "final-prepush"
                    and replayed_epoch.get("push_consumed") is False
                    and current_intent.get("push_intent_digest") is None
                )
                or (
                    current_intent.get("phase") == "post-push"
                    and replayed_epoch.get("push_consumed") is True
                    and isinstance(replayed_push, Mapping)
                    and current_intent.get("push_intent_digest")
                    == replayed_push.get("digest")
                )
            )
            and plain_delta
            and delta == {"integration": current_integration}
        )
        inactive_observation_completed = _replayed_remote_observation_completed(
            event, current, trial_context
        )
        push_result = (
            current_push.get("result")
            if isinstance(current_push, Mapping)
            else None
        )
        normalized_old_tip_observation = bool(
            event_name == "push_observed"
            and active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") == current.get("state") == "pushing"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and isinstance(prior_push, Mapping)
            and prior_push == current_push
            and isinstance(push_result, Mapping)
            and push_result.get("classification")
            in {"outcome-unknown", "non-fast-forward"}
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and post_push_observation_intent
            and _merge_old_tip_all_false(current)
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {"condition", "primary_condition", "observed"}
            )
            and plain_delta
            and delta == {"integration": current_integration}
        )
        push_stable_except_landed = bool(
            isinstance(prior_push, Mapping)
            and isinstance(current_push, Mapping)
            and set(prior_push) == set(current_push)
            and all(
                prior_push.get(name) == current_push.get(name)
                for name in set(prior_push) - {"landed_head"}
            )
        )
        latest_contained_attempt = _merge_latest_contained_attempt(current)
        inactive_current_observation = bool(
            event_name == "push_observed"
            and not active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") in _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES
            and prior.get("state") != "pushed"
            and current.get("state") == "pushed"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and push_stable_except_landed
            and isinstance(current_push, Mapping)
            and current_push.get("landed_head") == latest_contained_attempt
            and latest_contained_attempt == current_push.get("intended_head")
            and isinstance(current.get("candidate"), Mapping)
            and latest_contained_attempt
            == current["candidate"].get("candidate_head")
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and post_push_observation_intent
            and inactive_observation_completed
            and _merge_containment(current)[0] == "current"
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "remote_movement_count",
                    "observed",
                    "push",
                }
            )
            and plain_delta
            and delta == {"state": "pushed", "integration": current_integration}
        )
        inactive_all_false_observation = bool(
            event_name == "push_observed"
            and not active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") in _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES
            and current.get("state") == "pushing"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and push_stable_except_landed
            and isinstance(current_push, Mapping)
            and current_push.get("landed_head") is None
            and latest_contained_attempt is None
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and post_push_observation_intent
            and inactive_observation_completed
            and _merge_containment(current)[0] == "all-false"
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "remote_movement_count",
                    "observed",
                    "push",
                }
            )
            and plain_delta
            and delta
            == (
                {"integration": current_integration}
                if prior.get("state") == "pushing"
                else {"state": "pushing", "integration": current_integration}
            )
        )
        inactive_older_observation = bool(
            event_name == "push_observed"
            and not active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") in _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES
            and current.get("state") == "pushing"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and push_stable_except_landed
            and isinstance(current_push, Mapping)
            and current_push.get("landed_head") == latest_contained_attempt
            and latest_contained_attempt is not None
            and latest_contained_attempt != current_push.get("intended_head")
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and post_push_observation_intent
            and inactive_observation_completed
            and _merge_containment(current)[0] == "older"
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "remote_movement_count",
                    "observed",
                    "push",
                }
            )
            and plain_delta
            and delta
            == (
                {"integration": current_integration}
                if prior.get("state") == "pushing"
                else {"state": "pushing", "integration": current_integration}
            )
        )
        inactive_unavailable_observation = bool(
            event_name == "push_observed"
            and not active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") in _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES
            and current.get("state") == "pushing"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and push_stable_except_landed
            and isinstance(current_push, Mapping)
            and current_push.get("landed_head") is None
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and post_push_observation_intent
            and inactive_observation_completed
            and _merge_containment(current)[0] == "unresolved"
            and isinstance(current_integration.get("observed"), Mapping)
            and current_integration["observed"].get("exists") is None
            and current_integration["observed"].get("oid") is None
            and current_integration["observed"].get("contains_intended_head")
            is None
            and current_integration.get("condition") == "push-outcome-unknown"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "remote_movement_count",
                    "observed",
                    "push",
                }
            )
            and plain_delta
            and delta
            == (
                {"integration": current_integration}
                if prior.get("state") == "pushing"
                else {"state": "pushing", "integration": current_integration}
            )
        )

        retry_epoch = (
            prior_integration.get("epoch")
            if isinstance(prior_integration, Mapping)
            else None
        )
        retry_plan = (
            retry_epoch.get("gate_plan")
            if isinstance(retry_epoch, Mapping)
            else None
        )
        retry_intent = (
            prior_integration.get("intent")
            if isinstance(prior_integration, Mapping)
            else None
        )
        replayed_retry_observation = trial_context.get("push_retry_observation")
        preceding_retry_observation = (
            replayed_retry_observation.get("previous")
            if isinstance(replayed_retry_observation, Mapping)
            else None
        )
        prior_observed = (
            prior_integration.get("observed")
            if isinstance(prior_integration, Mapping)
            else None
        )
        retry_attempts = (
            prior_push.get("attempted_heads")
            if isinstance(prior_push, Mapping)
            else None
        )
        current_attempts = (
            current_push.get("attempted_heads")
            if isinstance(current_push, Mapping)
            else None
        )
        candidate = current.get("candidate")
        current_authority = _merge_current_authority_valid(current)
        retry_push_intent = bool(
            event_name == "push_intent"
            and active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") == current.get("state") == "pushing"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and isinstance(prior_push, Mapping)
            and (
                prior_push.get("result") is None
                or isinstance(prior_push.get("result"), Mapping)
            )
            and isinstance(current_push, Mapping)
            and isinstance(retry_epoch, Mapping)
            and current_epoch == retry_epoch
            and isinstance(retry_plan, Mapping)
            and retry_plan.get("status") == "sealed"
            and retry_plan.get("cursor") == len(retry_plan.get("suite", []))
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest") == retry_epoch.get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == retry_epoch.get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and isinstance(retry_intent, Mapping)
            and set(retry_intent)
            == {
                "schema",
                "transaction",
                "chain_id",
                "attempt_identity",
                "phase",
                "push_intent_digest",
            }
            and retry_intent.get("schema")
            == "forge-remote-observation-intent/1"
            and retry_intent.get("transaction") == "merge"
            and retry_intent.get("chain_id") == prior.get("chain_id")
            and retry_intent.get("attempt_identity")
            == retry_epoch.get("intent_digest")
            and retry_intent.get("phase") == "post-push"
            and retry_intent.get("push_intent_digest")
            == (
                replayed_push.get("digest")
                if isinstance(replayed_push, Mapping)
                else None
            )
            and isinstance(replayed_retry_observation, Mapping)
            and set(replayed_retry_observation)
            == {
                "digest",
                "generation_digest",
                "push_intent_digest",
                "inflight_digest",
                "old_tip_all_false",
                "previous",
            }
            and replayed_retry_observation.get("generation_digest")
            == retry_epoch.get("generation_digest")
            and replayed_retry_observation.get("push_intent_digest")
            == retry_intent.get("push_intent_digest")
            and isinstance(prior_observed, Mapping)
            and replayed_retry_observation.get("inflight_digest")
            == prior_observed.get("inflight_digest")
            and replayed_retry_observation.get("old_tip_all_false") is True
            and isinstance(preceding_retry_observation, Mapping)
            and set(preceding_retry_observation)
            == {
                "digest",
                "push_intent_digest",
                "inflight_digest",
                "old_tip_all_false",
            }
            and preceding_retry_observation.get("push_intent_digest")
            == retry_intent.get("push_intent_digest")
            and preceding_retry_observation.get("old_tip_all_false") is True
            and replayed_retry_observation.get("digest")
            != preceding_retry_observation.get("digest")
            and replayed_retry_observation.get("inflight_digest")
            != preceding_retry_observation.get("inflight_digest")
            and _merge_old_tip_all_false(prior)
            and current_authority
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and current_integration.get("observed") is None
            and isinstance(current_intent, Mapping)
            and set(current_intent) == {"operation", "operation_nonce", "attempt"}
            and current_intent.get("operation") == "push"
            and current_intent.get("operation_nonce")
            == retry_epoch.get("operation_nonce")
            and isinstance(retry_attempts, list)
            and isinstance(current_attempts, list)
            and current_attempts
            == [*retry_attempts, candidate.get("candidate_head")]
            and current_intent.get("attempt") == len(current_attempts)
            and current_push.get("expected_old_tip")
            == candidate.get("remote_tip")
            and current_push.get("intended_head")
            == candidate.get("candidate_head")
            and current_push.get("destination_ref")
            == candidate.get("destination_ref")
            and current_push.get("intended_at") == event.get("at")
            and current_push.get("result") is None
            and current_push.get("landed_head") == prior_push.get("landed_head")
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "intent",
                    "observed",
                    "push",
                }
            )
            and plain_delta
            and delta == {"integration": current_integration}
        )

        invalid_mode_intent = (
            current_integration.get("intent")
            if isinstance(current_integration, Mapping)
            else None
        )
        prior_plan = (
            prior_integration.get("epoch", {}).get("gate_plan")
            if isinstance(prior_integration, Mapping)
            and isinstance(prior_integration.get("epoch"), Mapping)
            else None
        )
        prior_mode_intent = (
            prior_integration.get("intent")
            if isinstance(prior_integration, Mapping)
            else None
        )
        prior_mode_observed = (
            prior_integration.get("observed")
            if isinstance(prior_integration, Mapping)
            else None
        )
        prior_iteration = (
            prior.get("review", {}).get("iteration")
            if prior is not None and isinstance(prior.get("review"), Mapping)
            else None
        )
        expected_invalid_delta = (
            {
                name: current.get(name)
                for name in (
                    "state",
                    "review",
                    "approval",
                    "authorization",
                    "integration",
                )
                if prior is not None and prior.get(name) != current.get(name)
            }
            if prior is not None
            else {}
        )
        invalid_final_mode_park = bool(
            event_name == "reverification_result"
            and active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") in {"rebasing", "reverifying"}
            and current.get("state") == "revising"
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and prior_integration.get("condition") == "none"
            and prior_integration.get("primary_condition") == "none"
            and isinstance(prior_plan, Mapping)
            and prior_plan.get("status") == "sealed"
            and prior_plan.get("cursor") == len(prior_plan.get("suite", []))
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == prior_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == prior_integration.get("epoch", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is False
            and isinstance(prior_mode_intent, Mapping)
            and set(prior_mode_intent)
            == {
                "schema",
                "transaction",
                "chain_id",
                "attempt_identity",
                "phase",
                "push_intent_digest",
            }
            and prior_mode_intent.get("schema")
            == "forge-remote-observation-intent/1"
            and prior_mode_intent.get("transaction") == "merge"
            and prior_mode_intent.get("chain_id") == prior.get("chain_id")
            and prior_mode_intent.get("attempt_identity")
            == prior_integration.get("epoch", {}).get("intent_digest")
            and prior_mode_intent.get("phase") == "final-prepush"
            and prior_mode_intent.get("push_intent_digest") is None
            and isinstance(prior_mode_observed, Mapping)
            and prior_mode_observed.get("exists") is True
            and prior_mode_observed.get("oid")
            == current.get("candidate", {}).get("remote_tip")
            and current_integration.get("epoch") is None
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and isinstance(invalid_mode_intent, Mapping)
            and set(invalid_mode_intent)
            == {
                "schema",
                "operation",
                "candidate_head",
                "manifest_digest",
                "result",
                "recorded_at",
            }
            and invalid_mode_intent.get("schema")
            == "forge-history-mutation-mode-result/1"
            and invalid_mode_intent.get("operation") == "history-mutation-mode"
            and invalid_mode_intent.get("candidate_head")
            == candidate.get("candidate_head")
            and SHA256_RE.fullmatch(
                str(invalid_mode_intent.get("manifest_digest", ""))
            )
            is not None
            and invalid_mode_intent.get("result") == "invalid"
            and builders._utc_value(invalid_mode_intent.get("recorded_at"))
            is not None
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "remote_movement_count",
                    "epoch",
                    "intent",
                }
            )
            and current.get("review")
            == ({"iteration": prior_iteration} if type(prior_iteration) is int else {})
            and current.get("approval") == {}
            and current.get("authorization") == {}
            and plain_delta
            and delta == expected_invalid_delta
        )
        parked_completed_plan = bool(
            event_name == "reverification_result"
            and prior is not None
            and prior.get("state") == "reverifying"
            and current.get("state") == "reviewing"
            and isinstance(prior_integration, Mapping)
            and isinstance(prior_integration.get("epoch"), Mapping)
            and isinstance(
                prior_integration["epoch"].get("gate_plan"), Mapping
            )
            and prior_integration["epoch"]["gate_plan"].get("status")
            == "sealed"
            and prior_integration["epoch"]["gate_plan"].get("cursor")
            == len(prior_integration["epoch"]["gate_plan"].get("suite", []))
            and isinstance(current_integration, Mapping)
            and current_integration.get("epoch") is None
            and current.get("steps") == prior.get("steps")
        )
        prior_candidate = prior.get("candidate") if prior is not None else None
        carried_candidate = current.get("candidate")
        prior_review = prior.get("review") if prior is not None else None
        prior_iteration = (
            prior_review.get("iteration")
            if isinstance(prior_review, Mapping)
            else None
        )
        gate_tuple_reclassified = bool(
            event_name == "generation_refreshed"
            and prior is not None
            and prior.get("state") == "reverifying"
            and current.get("state") == "verifying"
            and isinstance(prior_candidate, Mapping)
            and isinstance(carried_candidate, Mapping)
            and carried_candidate.get("generation")
            == int(prior_candidate.get("generation", 0)) + 1
            and carried_candidate != prior_candidate
            and isinstance(prior_integration, Mapping)
            and isinstance(prior_integration.get("epoch"), Mapping)
            and isinstance(current_integration, Mapping)
            and current_integration.get("epoch") is None
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "epoch",
                    "remote_movement_count",
                }
            )
            and current_integration.get("remote_movement_count") == 0
            and current.get("steps") == {}
            and current.get("review")
            == ({"iteration": prior_iteration} if type(prior_iteration) is int else {})
            and current.get("approval") == {}
            and current.get("authorization") == {}
        )
        remote_only_carry = bool(
            event_name == "generation_carried_forward"
            and prior is not None
            and active_event
            and prior.get("state") in {"rebasing", "reverifying"}
            and current.get("state") in {"authorized", "awaiting_approval"}
            and isinstance(prior_candidate, Mapping)
            and isinstance(carried_candidate, Mapping)
            and carried_candidate.get("remote_tip")
            != prior_candidate.get("remote_tip")
            and all(
                carried_candidate.get(name) == prior_candidate.get(name)
                for name in _MERGE_REMOTE_ONLY_IDENTITY_FIELDS
            )
            and carried_candidate.get("generation")
            == int(prior_candidate.get("generation", 0)) + 1
            and prior.get("tier") == current.get("tier")
            and prior.get("policy_source") == current.get("policy_source")
            and current.get("steps") == prior.get("steps")
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and current_integration.get("epoch") is None
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("condition")
            in {"remote-moved", "remote-churn"}
            and current_integration.get("remote_movement_count")
            == int(prior_integration.get("remote_movement_count", 0)) + 1
            and isinstance(current_integration.get("observed"), Mapping)
            and current_integration["observed"].get("exists") is True
            and current_integration["observed"].get("oid")
            == carried_candidate.get("remote_tip")
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {"condition", "epoch", "remote_movement_count", "observed"}
            )
            and _merge_carry_payload_valid(
                event, prior_candidate, carried_candidate
            )
        )
        if not (
            direct_retry
            or scoped_position
            or scope_exceeded_result
            or sealed_fetch_to_reverify
            or sealed_rebase_successor
            or observation_intent
            or candidate_observation_progress
            or bootstrap_fetch_observation
            or epoch_fetch_observation
            or observation_progress
            or epoch_ancestry_progress
            or push_result_recorded
            or normalized_old_tip_observation
            or inactive_current_observation
            or inactive_all_false_observation
            or inactive_older_observation
            or inactive_unavailable_observation
            or retry_push_intent
            or invalid_final_mode_park
            or parked_completed_plan
            or gate_tuple_reclassified
            or remote_only_carry
        ):
            return False
        if normalized_old_tip_observation or retry_push_intent:
            _require_merge_integration_control("push-retry")
        if (
            inactive_current_observation
            or inactive_all_false_observation
            or inactive_older_observation
            or inactive_unavailable_observation
        ):
            _require_merge_integration_control("observation-first-recovery")
        if context is not None and observation_intent:
            if observation_progress_restore:
                completed_observation = copy.deepcopy(
                    dict(replayed_remote_observation)
                )
                completed_observation.update(
                    {
                        "intent_event_digest": event.get("digest"),
                        "intent": copy.deepcopy(current_intent),
                        "progress_event_digest": None,
                        "progress": None,
                        "restore_event_digest": event.get("digest"),
                        "completed_progress": copy.deepcopy(prior_intent),
                    }
                )
                trial_context["remote_observation"] = completed_observation
            else:
                trial_context["remote_observation"] = {
                    "intent_event_digest": event.get("digest"),
                    "generation_digest": event.get("generation_digest"),
                    "intent": copy.deepcopy(current_intent),
                    "admitted_inactive": inactive_post_attempt_observation_intent,
                    "progress_event_digest": None,
                    "progress": None,
                    "restore_event_digest": None,
                    "completed_progress": None,
                }
        if context is not None and observation_progress:
            active_observation = copy.deepcopy(dict(replayed_remote_observation))
            active_observation.update(
                {
                    "progress_event_digest": event.get("digest"),
                    "progress": copy.deepcopy(current_intent),
                    "restore_event_digest": None,
                    "completed_progress": None,
                }
            )
            trial_context["remote_observation"] = active_observation
        if candidate_observation_progress:
            _require_merge_integration_control("observation-first-recovery")
            observation_record = (
                current_intent
                if _merge_candidate_observation_record_valid(
                    current, current_intent
                )
                else prior_intent
                if prior is not None
                and _merge_candidate_observation_record_valid(
                    prior, prior_intent
                )
                else None
            )
            if not isinstance(observation_record, Mapping):
                return False
            active = trial_context.get("candidate_observation_active")
            if (
                isinstance(current_intent, Mapping)
                and current_intent.get("schema")
                == _MERGE_CANDIDATE_OBSERVATION_SCHEMA
                and current_intent.get("stage") == "intent"
            ):
                step_names = _merge_candidate_observation_step_names(
                    current,
                    remote_tip=str(current_intent.get("remote_tip", "")),
                    expected_head=str(current_intent.get("expected_head", "")),
                    classify=current_intent.get("classify"),
                    declared_tier=current_intent.get("declared_tier"),
                )
                if step_names is None:
                    return False
                if current_intent.get("step") == step_names[0]:
                    active = {
                        "observation_binding": current_intent.get(
                            "observation_binding"
                        ),
                        "steps": [],
                    }
                    trial_context["candidate_observation_active"] = active
                elif (
                    not isinstance(active, Mapping)
                    or active.get("observation_binding")
                    != current_intent.get("observation_binding")
                    or not isinstance(active.get("steps"), list)
                    or len(active["steps"]) >= len(step_names)
                    or current_intent.get("step")
                    != step_names[len(active["steps"])]
                ):
                    return False
            elif (
                isinstance(current_intent, Mapping)
                and current_intent.get("schema")
                == _MERGE_CANDIDATE_OBSERVATION_SCHEMA
                and current_intent.get("stage") == "result"
            ):
                if (
                    not isinstance(active, Mapping)
                    or active.get("observation_binding")
                    != current_intent.get("observation_binding")
                    or not isinstance(active.get("steps"), list)
                ):
                    return False
                active_steps = copy.deepcopy(active["steps"])
                active_steps.append(copy.deepcopy(dict(current_intent)))
                evidence = _merge_candidate_observation_evidence(
                    current, active_steps
                )
                trial_context["candidate_observation_active"] = {
                    "observation_binding": current_intent.get(
                        "observation_binding"
                    ),
                    "steps": active_steps,
                }
                if evidence is not None:
                    trial_context["candidate_observation"] = {
                        "event_digest": event.get("digest"),
                        "generation_digest": event.get("generation_digest"),
                        "source_intent": copy.deepcopy(
                            current_intent.get("source_intent")
                        ),
                        "evidence": evidence,
                        "evidence_digest": evidence["evidence_digest"],
                    }
            elif (
                isinstance(prior_intent, Mapping)
                and prior_intent.get("schema")
                == _MERGE_CANDIDATE_OBSERVATION_SCHEMA
                and prior_intent.get("stage") == "result"
                and current_intent == prior_intent.get("source_intent")
            ):
                completed = trial_context.get("candidate_observation")
                if (
                    isinstance(completed, dict)
                    and completed.get("event_digest")
                    == event.get("previous_digest")
                ):
                    completed["restore_event_digest"] = event.get("digest")
        if bootstrap_fetch_observation:
            _require_merge_integration_control("post-fetch-scope-proof")
            selected_bootstrap = (
                current_intent
                if _bootstrap_fetch_observation_record_valid(
                    current, current_intent
                )
                else prior_intent
                if prior is not None
                and _bootstrap_fetch_observation_record_valid(
                    prior, prior_intent
                )
                else None
            )
            if not isinstance(selected_bootstrap, Mapping):
                return False
            if _bootstrap_fetch_observation_record_valid(
                current, current_intent
            ):
                trial_context["bootstrap_fetch_observation"] = {
                    "digest": event.get("digest"),
                    "generation_digest": event.get("generation_digest"),
                    "evidence": copy.deepcopy(current_intent),
                    "fetch_intent_event_digest": current_intent.get(
                        "fetch_intent_event_digest"
                    ),
                }
            else:
                retained_bootstrap = trial_context.get(
                    "bootstrap_fetch_observation"
                )
                if (
                    isinstance(retained_bootstrap, dict)
                    and retained_bootstrap.get("evidence") == prior_intent
                ):
                    retained_bootstrap["restore_event_digest"] = event.get(
                        "digest"
                    )
        if epoch_fetch_observation or epoch_ancestry_progress:
            _require_merge_integration_control("successor-ancestry-observation")
        if invalid_final_mode_park:
            _require_merge_integration_control("final-intended-head-mode")
        if context is not None and direct_retry:
            trial_context["epoch_intent"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "push_consumed": False,
            }
        if context is not None and retry_push_intent:
            trial_context["push_intent"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "evidence": copy.deepcopy(current_intent),
                "admitted_active": True,
            }
        if context is not None and epoch_fetch_observation:
            trial_context["epoch_fetch_observation"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "evidence": copy.deepcopy(current_intent),
            }
        if (
            context is not None
            and ancestry_result_transition
            and isinstance(current_intent, Mapping)
        ):
            trial_context["epoch_ancestry_observation"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "evidence": copy.deepcopy(current_intent),
            }
        if invalid_final_mode_park:
            trial_context.pop("epoch_intent", None)
        if gate_tuple_reclassified:
            trial_context.pop("epoch_intent", None)
    if context is not None and event_name == "push_intent":
        trial_context.pop("push_retry_observation", None)
    elif context is not None and event_name == "push_observed":
        trial_context.pop("remote_observation", None)
        accepted_integration = current.get("integration")
        accepted_intent = (
            accepted_integration.get("intent")
            if isinstance(accepted_integration, Mapping)
            else None
        )
        accepted_observed = (
            accepted_integration.get("observed")
            if isinstance(accepted_integration, Mapping)
            else None
        )
        if (
            isinstance(accepted_intent, Mapping)
            and accepted_intent.get("phase") == "post-push"
            and isinstance(accepted_observed, Mapping)
        ):
            previous_observation = trial_context.get("push_retry_observation")
            previous_evidence = None
            if (
                isinstance(previous_observation, Mapping)
                and previous_observation.get("push_intent_digest")
                == accepted_intent.get("push_intent_digest")
            ):
                previous_evidence = {
                    name: previous_observation.get(name)
                    for name in (
                        "digest",
                        "push_intent_digest",
                        "inflight_digest",
                        "old_tip_all_false",
                    )
                }
            trial_context["push_retry_observation"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "push_intent_digest": accepted_intent.get("push_intent_digest"),
                "inflight_digest": accepted_observed.get("inflight_digest"),
                "old_tip_all_false": _merge_old_tip_all_false(current),
                "previous": previous_evidence,
            }
    if context is not None and epoch_fetch_intent_digest is not None:
        for name in (
            "epoch_fetch_observation",
            "candidate_observation_active",
            "candidate_observation",
            "epoch_ancestry_observation",
            "recovery_proof_bridge",
        ):
            trial_context.pop(name, None)
    if context is not None:
        context.clear()
        context.update(trial_context)
    return True


def _merge_ingest_transition_valid(
    builders: Any,
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    *,
    context: MutableMapping[str, Any],
    history: Sequence[Mapping[str, Any]] = (),
) -> bool:
    """Keep captured Revision-9 epochs on their immutable grammar."""

    if not _merge_history_uses_additive_grammar((*history, event)):
        return bool(
            builders._merge_transition_valid(
                event, prior, current, context=context
            )
        )
    return _merge_transition_valid(
        builders,
        event,
        prior,
        current,
        context=context,
        history=history,
    )
