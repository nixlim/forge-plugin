"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import copy
from pathlib import Path
from typing import Any, Mapping, Sequence
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
from forge_cli.chain_core._merge_release import _merge_attempted_release_preconditions_valid as _merge_attempted_release_preconditions_valid, _merge_release_preconditions_valid as _merge_release_preconditions_valid
from forge_cli.chain_core._merge_scope import _validate_merge_scope_proof as _validate_merge_scope_proof, _merge_scope_event_binding_valid as _merge_scope_event_binding_valid, _merge_scope_transition_valid as _merge_scope_transition_valid
from forge_cli.chain_core._merge_scope_binding import _merge_scope_environment_contract as _merge_scope_environment_contract, _validate_merge_scope_request as _validate_merge_scope_request, _merge_retained_inflight as _merge_retained_inflight, _validate_merge_scope_fetch_binding as _validate_merge_scope_fetch_binding, _merge_scope_binding_names as _merge_scope_binding_names, _merge_full_patch_argv as _merge_full_patch_argv, _merge_scope_argv as _merge_scope_argv, _merge_scope_binding_validator as _merge_scope_binding_validator
from forge_cli.chain_core._merge_state_shape import _merge_gate_plan_valid as _merge_gate_plan_valid, _merge_epoch_valid as _merge_epoch_valid, _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view as _merge_revision9_compatibility_view, _merge_state_shape_valid as _merge_state_shape_valid, _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot
from forge_cli.chain_core._remote_observation import _remote_containment_evidence_valid as _remote_containment_evidence_valid, _remote_observation_progress_valid as _remote_observation_progress_valid, _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed, _replayed_remote_observation_completed as _replayed_remote_observation_completed
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.policy import sha256_bytes


def _merge_recovery_proof_transition_valid(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    *,
    history: Sequence[Mapping[str, Any]] = (),
) -> bool:
    """Authenticate the durable reservation-held fence-death carrier."""

    payload = event.get("payload")
    if event.get("event") != "condition_recorded":
        return not (
            isinstance(payload, Mapping) and "recovery_proof" in payload
        )
    if not isinstance(payload, Mapping) or "recovery_proof" not in payload:
        return True
    proof = payload.get("recovery_proof")
    if (
        prior is None
        or not isinstance(proof, Mapping)
        or set(payload) != {"delta", "recovery_proof"}
        or payload.get("delta") != {}
        or set(proof)
        != {
            "schema",
            "chain_id",
            "reservation",
            "fence",
            "lifecycle",
            "recorded_at",
            "digest",
        }
        or proof.get("schema") != "forge-merge-fence-recovery-proof/1"
        or proof.get("chain_id") != current.get("chain_id")
        or proof.get("recorded_at") != event.get("at")
        or proof.get("digest")
        != sha256_bytes(
            canonical_bytes(
                {name: copy.deepcopy(value) for name, value in proof.items() if name != "digest"}
            )
        )
    ):
        return False
    common_dir = Path(str(current.get("worktree", {}).get("common_dir", "")))
    reservation = proof.get("reservation")
    fence = proof.get("fence")
    lifecycle = proof.get("lifecycle")
    if not (
        _published_recovery_evidence_valid(
            reservation,
            path=common_dir / COMMON_LOCK_RECOVERY_NAME,
            validator=_validate_recovery_record,
        )
        and isinstance(reservation, Mapping)
        and isinstance(lifecycle, Mapping)
        and set(lifecycle)
        == {
            "operation",
            "intent_digest",
            "classification",
            "state_digest",
            "tail_digest",
        }
        and isinstance(lifecycle.get("classification"), str)
        and bool(lifecycle.get("classification"))
        and lifecycle.get("state_digest")
        == sha256_bytes(canonical_bytes(dict(prior)))
        and lifecycle.get("tail_digest") == event.get("previous_digest")
    ):
        return False
    reservation_record = reservation.get("record")
    if not isinstance(reservation_record, Mapping):
        return False
    if fence is None:
        if not (
            reservation_record.get("recovery_kind") == "fallback-owner"
            and reservation_record.get("stale_owner_kind") == "merge"
            and reservation_record.get("stale_owner_chain_id")
            == current.get("chain_id")
            and reservation_record.get("stale_owner_inode") is not None
            and reservation_record.get("stale_owner_digest") is not None
            and reservation_record.get("owner_dead_at") is not None
            and lifecycle.get("operation") is None
            and lifecycle.get("intent_digest") is None
            and lifecycle.get("classification") == "owner-death-only"
        ):
            return False
        ignored = {"last_event_at", "inactive_after"}
        return all(
            prior.get(name) == current.get(name)
            for name in MERGE_STATE_KEYS - ignored
        )
    if not (
        _published_recovery_evidence_valid(
            fence,
            path=common_dir / COMMON_LOCK_INFLIGHT_NAME,
            validator=_validate_fence_record,
        )
        and isinstance(fence, Mapping)
    ):
        return False
    fence_record = fence.get("record")
    if not isinstance(fence_record, Mapping):
        return False
    recovery_kind = reservation_record.get("recovery_kind")
    if recovery_kind == "fallback-owner-and-fence":
        recovery_topology_valid = bool(
            reservation_record.get("stale_owner_kind") == "merge"
            and reservation_record.get("stale_owner_chain_id")
            == current.get("chain_id")
            and reservation_record.get("stale_owner_inode") is not None
            and reservation_record.get("stale_owner_digest") is not None
            and reservation_record.get("owner_dead_at") is not None
        )
    elif recovery_kind == "flock-held-dead-fence":
        recovery_topology_valid = all(
            reservation_record.get(name) is None
            for name in (
                "stale_owner_inode",
                "stale_owner_digest",
                "stale_owner_host",
                "stale_owner_pid",
                "stale_owner_kind",
                "stale_owner_chain_id",
                "owner_dead_at",
            )
        )
    else:
        recovery_topology_valid = False
    operation = fence_record.get("operation")
    label_prefix = (
        "fetch" if operation in {"fetch", "tip-resolution"} else operation
    )
    allowed_classifications = (
        {
            f"{label_prefix}-intent-pending",
            f"{label_prefix}-result-persisted",
        }
        if isinstance(label_prefix, str)
        and label_prefix
        in {
            "fetch",
            "gate",
            "remote-observation",
            "rebase",
            "continue",
            "abort",
            "push",
            "containment",
            "worktree-remove",
            "branch-delete",
        }
        else set()
    )
    if (
        not recovery_topology_valid
        or lifecycle.get("operation") != fence_record.get("operation")
        or lifecycle.get("intent_digest") != fence_record.get("intent_digest")
        or lifecycle.get("classification") not in allowed_classifications
        or reservation_record.get("inflight_inode") != fence.get("inode")
        or reservation_record.get("inflight_digest") != fence.get("digest")
        or reservation_record.get("inflight_host") != fence_record.get("host")
        or reservation_record.get("inflight_pgid") != fence_record.get("pgid")
        or reservation_record.get("inflight_owner_kind")
        != fence_record.get("owner_kind")
        or reservation_record.get("inflight_chain_id")
        != fence_record.get("chain_id")
        or reservation_record.get("group_dead_at") is None
        or fence_record.get("owner_kind") != "merge"
        or fence_record.get("chain_id") != current.get("chain_id")
    ):
        return False
    expected_classification = _classify_merge_recovery_lifecycle(
        prior,
        history,
        fence_record=fence_record,
        fence_digest=str(fence.get("digest")),
    )
    if lifecycle.get("classification") != expected_classification:
        return False
    for prior_event in history:
        prior_payload = prior_event.get("payload")
        prior_proof = (
            prior_payload.get("recovery_proof")
            if isinstance(prior_payload, Mapping)
            else None
        )
        if isinstance(prior_proof, Mapping) and (
            prior_proof.get("reservation") == reservation
            or (
                prior_proof.get("fence") is not None
                and prior_proof.get("fence") == fence
            )
        ):
            return False
    ignored = {"last_event_at", "inactive_after"}
    return all(
        prior.get(name) == current.get(name)
        for name in MERGE_STATE_KEYS - ignored
    )


def _epoch_fetch_observation_predecessor_valid(
    event: Mapping[str, Any],
    current_intent: Mapping[str, Any],
    prior_intent: Mapping[str, Any],
    context: Mapping[str, Any],
) -> bool:
    """Admit direct adjacency or one exact owner-death recovery carrier."""

    intent_digest = current_intent.get("fetch_intent_event_digest")
    if event.get("previous_digest") == intent_digest:
        return True
    bridge = context.get("recovery_proof_bridge")
    admitted = context.get("fetch_intent")
    return bool(
        isinstance(bridge, Mapping)
        and isinstance(admitted, Mapping)
        and event.get("previous_digest") == bridge.get("event_digest")
        and bridge.get("previous_digest") == intent_digest
        and bridge.get("operation") is None
        and bridge.get("intent_digest") is None
        and bridge.get("classification") == "owner-death-only"
        and admitted.get("digest") == intent_digest
        and admitted.get("generation_digest") == event.get("generation_digest")
        and admitted.get("evidence") == prior_intent
        and admitted.get("admitted_active") is True
    )


def _recovered_absent_rebase_intent_digest(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    context: Mapping[str, Any],
) -> str | None:
    """Authenticate the observation interposed before an absent rebase result."""

    if (
        event.get("event") != "rebase_result"
        or prior is None
        or _merge_rebase_result_classification(prior) != "absent"
    ):
        return None
    prior_integration = prior.get("integration")
    prior_intent = (
        prior_integration.get("intent")
        if isinstance(prior_integration, Mapping)
        else None
    )
    prior_candidate = prior.get("candidate")
    replayed = context.get("rebase_intent")
    candidate = context.get("candidate_observation")
    evidence = candidate.get("evidence") if isinstance(candidate, Mapping) else None
    if not (
        isinstance(prior_intent, Mapping)
        and isinstance(prior_candidate, Mapping)
        and isinstance(replayed, Mapping)
        and isinstance(candidate, Mapping)
        and isinstance(evidence, Mapping)
        and isinstance(replayed.get("digest"), str)
        and replayed.get("evidence") == prior_intent
        and replayed.get("admitted_active") is True
        and candidate.get("source_intent") == prior_intent
        and candidate.get("generation_digest") == event.get("generation_digest")
        and event.get("generation_digest")
        == prior_candidate.get("generation_digest")
        and candidate.get("restore_event_digest")
        == event.get("previous_digest")
        and candidate.get("evidence_digest") == evidence.get("evidence_digest")
        and _merge_candidate_observation_evidence_valid(prior, evidence)
        and evidence.get("source_intent") == prior_intent
        and evidence.get("verb") == "merge recover"
        and evidence.get("classify") is False
        and evidence.get("remote_tip") == prior_candidate.get("remote_tip")
        and evidence.get("expected_head")
        == prior_candidate.get("candidate_head")
    ):
        return None
    return str(replayed["digest"])
