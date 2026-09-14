"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import os
from typing import Any, Mapping, Callable, Sequence
from forge_cli.chain_core._activation import _ChainActivationSnapshot as _ChainActivationSnapshot, _chain_activation_ownership_summary as _chain_activation_ownership_summary, _validate_chain_activation_lineage as _validate_chain_activation_lineage
from forge_cli.chain_core._activation_outbox import _resolve_chain_activation_projection as _resolve_chain_activation_projection
from forge_cli.chain_core._bootstrap_observation import _bootstrap_fetch_observation_record_valid as _bootstrap_fetch_observation_record_valid, _bootstrap_fetch_observation_transition_valid as _bootstrap_fetch_observation_transition_valid
from forge_cli.chain_core._candidate_v2 import candidate_is_v2 as candidate_is_v2, _candidate_binding_for_state_with_candidate_v2 as _candidate_binding_for_state_with_candidate_v2, _binding_shape_valid_with_candidate_v2 as _binding_shape_valid_with_candidate_v2, _event_batch_records_with_candidate_v2 as _event_batch_records_with_candidate_v2, _binding_matches_source_fact_with_candidate_v2 as _binding_matches_source_fact_with_candidate_v2, _binding_is_current_with_candidate_v2 as _binding_is_current_with_candidate_v2
from forge_cli.chain_core._chain_batch_authorize import _authorize_chain_batch as _authorize_chain_batch
from forge_cli.chain_core._chain_batch_carrier import _coordination_refusal as _coordination_refusal, _drain_chain_batch_capability as _drain_chain_batch_capability
from forge_cli.chain_core._chain_state import validate_state as validate_state
from forge_cli.chain_core._commit_chain import CLIOptions as CLIOptions, register_activation_reservation_seam as register_activation_reservation_seam, _validate_bound_chain_state as _validate_bound_chain_state, _user_skip as _user_skip, _gate_one_complete as _gate_one_complete, _latest_current_pass as _latest_current_pass, _gate_satisfied as _gate_satisfied, _verify_and_build_ingest_records as _verify_and_build_ingest_records, _ingest_proof_verifier as _ingest_proof_verifier, register_coordination_seams as register_coordination_seams, ChainStore as ChainStore, CommandContext as CommandContext, _policy_for_state as _policy_for_state, _fresh_reviewer_evals_required as _fresh_reviewer_evals_required, _required_steps as _required_steps
from forge_cli.chain_core._common_lock import _acquire_secondary_flock as _acquire_secondary_flock, acquire_common_lock as acquire_common_lock, hold_common_lock as hold_common_lock
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._fenced_child import _BlockedFenceChild as _BlockedFenceChild, _pipe_cloexec as _pipe_cloexec, _read_child_ack as _read_child_ack, _waitpid_nohang as _waitpid_nohang, _wait_for_child_exit as _wait_for_child_exit, _spawn_blocked_fence_child as _spawn_blocked_fence_child, _terminate_fenced_group as _terminate_fenced_group, _stop_unstarted_child as _stop_unstarted_child, _collect_fenced_child as _collect_fenced_child
from forge_cli.chain_core._ingest_capture import _read_ingest_input as _read_ingest_input, _capture_ingest_blob as _capture_ingest_blob, _capture_run_evidence as _capture_run_evidence, _capture_ingest_record_evidence as _capture_ingest_record_evidence
from forge_cli.chain_core._ingest_currency import _ingest_captured_paths as _ingest_captured_paths, _ingest_step_is_current as _ingest_step_is_current, _ingest_secret_scan_is_current as _ingest_secret_scan_is_current, _prove_ingest_live_chain as _prove_ingest_live_chain
from forge_cli.chain_core._ingest_merge import _merge_ingest_binding as _merge_ingest_binding, _merge_gate_event_fact as _merge_gate_event_fact, _merge_current_gate_facts as _merge_current_gate_facts, _merge_ingest_record_templates as _merge_ingest_record_templates, _verify_and_build_merge_ingest_records as _verify_and_build_merge_ingest_records
from forge_cli.chain_core._lock_owner import _new_owner_record as _new_owner_record, _fence_matches_owner as _fence_matches_owner, _release_portable_identity as _release_portable_identity, _publish_portable_owner as _publish_portable_owner
from forge_cli.chain_core._lock_record_io import _read_owned_record_at as _read_owned_record_at, _same_published_record as _same_published_record, _open_lock_directory as _open_lock_directory, _opaque_path_evidence_at as _opaque_path_evidence_at, _inspect_common_lock_fd as _inspect_common_lock_fd, _create_private_record_at as _create_private_record_at, _publish_no_replace_link as _publish_no_replace_link, _revalidate_record_at as _revalidate_record_at, _unlink_revalidated_record_at as _unlink_revalidated_record_at, _record_at_if_present as _record_at_if_present
from forge_cli.chain_core._lock_record_validators import _validate_owner_record as _validate_owner_record, _validate_fence_record as _validate_fence_record, _validate_recovery_record as _validate_recovery_record, _validate_chain_lease_record as _validate_chain_lease_record
from forge_cli.chain_core._lock_recovery import _fence_death_proof as _fence_death_proof, _require_recovery_proof_recorder as _require_recovery_proof_recorder, _persist_recovery_proof as _persist_recovery_proof, _read_fence_for_recovery as _read_fence_for_recovery, _common_fence_path_present as _common_fence_path_present, _recover_stale_portable_owner as _recover_stale_portable_owner
from forge_cli.chain_core._lock_reservation import _open_owned_directory as _open_owned_directory, RecoveryReservation as RecoveryReservation, _publish_recovery_reservation as _publish_recovery_reservation, _reservation_evidence as _reservation_evidence, _clear_owned_reservation as _clear_owned_reservation, _recovery_record as _recovery_record
from forge_cli.chain_core._merge_candidate_observation import _merge_candidate_observation_record_valid as _merge_candidate_observation_record_valid, _merge_candidate_observation_transition_valid as _merge_candidate_observation_transition_valid, _merge_candidate_observation_evidence as _merge_candidate_observation_evidence, _merge_candidate_observation_evidence_valid as _merge_candidate_observation_evidence_valid
from forge_cli.chain_core._merge_candidate_observation_steps import _merge_candidate_observation_step_specs as _merge_candidate_observation_step_specs, _merge_candidate_observation_step_names as _merge_candidate_observation_step_names, _merge_candidate_observation_binding as _merge_candidate_observation_binding
from forge_cli.chain_core._merge_chain import _build_merge_chain_journal_records as _build_merge_chain_journal_records, _new_merge_record_is_current as _new_merge_record_is_current, _prove_merge_run_task_binding as _prove_merge_run_task_binding, _repository_recovery_reservation_present as _repository_recovery_reservation_present, MergeChainStore as MergeChainStore, _recovery_classification_receipt_valid as _recovery_classification_receipt_valid, CommonRebaseLock as CommonRebaseLock, _clear_reserved_fence as _clear_reserved_fence, ChainLease as ChainLease, _lease_exclusion_is_current as _lease_exclusion_is_current, _lease_reclaim_authority_is_current as _lease_reclaim_authority_is_current, _reconcile_merge_projection_for_lease_reclaim as _reconcile_merge_projection_for_lease_reclaim, acquire_chain_lease as acquire_chain_lease
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
from forge_cli.chain_core._merge_replay import validate_merge_state as validate_merge_state, MergeReplayResult as MergeReplayResult, _replay_merge_event_bytes as _replay_merge_event_bytes
from forge_cli.chain_core._merge_scope import _validate_merge_scope_proof as _validate_merge_scope_proof, _merge_scope_event_binding_valid as _merge_scope_event_binding_valid, _merge_scope_transition_valid as _merge_scope_transition_valid
from forge_cli.chain_core._merge_scope_binding import _merge_scope_environment_contract as _merge_scope_environment_contract, _validate_merge_scope_request as _validate_merge_scope_request, _merge_retained_inflight as _merge_retained_inflight, _validate_merge_scope_fetch_binding as _validate_merge_scope_fetch_binding, _merge_scope_binding_names as _merge_scope_binding_names, _merge_full_patch_argv as _merge_full_patch_argv, _merge_scope_argv as _merge_scope_argv, _merge_scope_binding_validator as _merge_scope_binding_validator
from forge_cli.chain_core._merge_state_shape import _merge_gate_plan_valid as _merge_gate_plan_valid, _merge_epoch_valid as _merge_epoch_valid, _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view as _merge_revision9_compatibility_view, _merge_state_shape_valid as _merge_state_shape_valid, _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar
from forge_cli.chain_core._merge_transition import _merge_transition_valid as _merge_transition_valid, _merge_ingest_transition_valid as _merge_ingest_transition_valid
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot
from forge_cli.chain_core._remote_observation import _remote_containment_evidence_valid as _remote_containment_evidence_valid, _remote_observation_progress_valid as _remote_observation_progress_valid, _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed, _replayed_remote_observation_completed as _replayed_remote_observation_completed
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.chain_core._storage import _ChainStoragePrimitives as _ChainStoragePrimitives
import dataclasses
import secrets
import time
from pathlib import Path
from forge_cli import runtime


def _publish_fence(
    lock: CommonRebaseLock,
    record: Mapping[str, Any],
) -> PublishedLockRecord:
    temporary, temporary_identity = _create_private_record_at(
        lock._common,
        lock.common_dir,
        "agent-rebase.inflight",
        record,
        boundary=lock._boundary,
        stage="fence-temp-fsynced",
    )
    link_created = False
    try:
        _publish_no_replace_link(
            lock._common,
            temporary,
            lock._common,
            COMMON_LOCK_INFLIGHT_NAME,
        )
        link_created = True
        os.fsync(lock._common)
        observed = _read_owned_record_at(
            lock._common,
            COMMON_LOCK_INFLIGHT_NAME,
            lock.common_dir / COMMON_LOCK_INFLIGHT_NAME,
            _validate_fence_record,
        )
        if not _same_published_record(observed, temporary_identity):
            raise OSError("published fence changed inode or digest")
        lock._emit_boundary("fence-published")
        _unlink_revalidated_record_at(
            lock._common,
            temporary,
            lock.common_dir / temporary,
            temporary_identity,
            _validate_fence_record,
        )
        os.fsync(lock._common)
        lock._emit_boundary("fence-temp-unlinked")
        return observed
    except BaseException as exc:
        if isinstance(exc, CommonLockBoundaryCrash):
            raise
        cleanup_errors: list[str] = []
        removed_name = False
        if link_created:
            try:
                _unlink_revalidated_record_at(
                    lock._common,
                    COMMON_LOCK_INFLIGHT_NAME,
                    lock.common_dir / COMMON_LOCK_INFLIGHT_NAME,
                    temporary_identity,
                    _validate_fence_record,
                )
                removed_name = True
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as cleanup_error:
                cleanup_errors.append(f"canonical: {cleanup_error}")
        try:
            _unlink_revalidated_record_at(
                lock._common,
                temporary,
                lock.common_dir / temporary,
                temporary_identity,
                _validate_fence_record,
            )
            removed_name = True
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as cleanup_error:
            cleanup_errors.append(f"temporary: {cleanup_error}")
        if removed_name:
            try:
                os.fsync(lock._common)
            except OSError as cleanup_error:
                cleanup_errors.append(f"directory fsync: {cleanup_error}")
        if cleanup_errors:
            raise _PublicationCleanupFailure(
                "fence publication cleanup could not prove durable removal: "
                + "; ".join(cleanup_errors)
            ) from exc
        raise


def run_fenced_command(
    lock: CommonRebaseLock,
    *,
    operation: str,
    intent_digest: str,
    intent_validator: Callable[[], bool],
    argv: Sequence[str],
    cwd: Path,
    persist_result: Callable[[FencedProcessResult], Any],
    env: Mapping[str, str] | None = None,
    timeout: float = runtime.COMMAND_TIMEOUT_SECONDS,
    cap: int = runtime.OUTPUT_CAP_BYTES,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    group_probe: Callable[[int], str] | None = None,
    signal_group: Callable[[int, int], Any] = os.killpg,
    verbose: bool = False,
    result_transform: (
        Callable[[FencedProcessResult], FencedProcessResult] | None
    ) = None,
) -> FencedProcessResult:
    """Authorize exactly one child through FR-236's durable start-pipe fence."""

    _require_common_lock_control("fence-start-pipe")
    _require_common_lock_control("fence-intent-revalidation")
    _require_common_lock_control("fence-result-before-release")
    if operation not in COMMON_LOCK_FENCE_OPERATIONS:
        raise ValueError("invalid fenced operation")
    if operation == "attribution-observation" and lock.owner.record["owner_kind"] != "push":
        raise ValueError("attribution observation requires standalone push ownership")
    if lock.owner.record["owner_kind"] not in {"merge", "push"}:
        raise ValueError("phase5 ownership cannot publish an FR-236 fence")
    if not SHA256_RE.fullmatch(intent_digest):
        raise ValueError("fenced intent digest must be a lowercase SHA-256")
    if (
        not callable(intent_validator)
        or not callable(persist_result)
        or (result_transform is not None and not callable(result_transform))
    ):
        raise ValueError("fenced command requires intent and result persistence callbacks")
    if (
        not isinstance(timeout, (int, float))
        or timeout <= 0
        or cap <= 0
        or cap > runtime.OUTPUT_CAP_BYTES
    ):
        raise ValueError(
            "fenced timeout must be positive and output cap must be within the fixed maximum"
        )
    lock.assert_held()
    if not intent_validator():
        raise CommonLockUnavailable(
            {
                "common_dir": str(lock.common_dir),
                "detail": "durable operation intent did not validate before child fork",
            }
        )
    probe = group_probe or lock._group_probe
    child: _BlockedFenceChild | None = None
    fence: PublishedLockRecord | None = None
    authorized = False
    fence_ack_window = min(
        max(float(timeout), FENCED_CHILD_ACK_TIMEOUT_SECONDS),
        COMMON_LOCK_TIMEOUT_SECONDS,
    )
    publication_deadline = lock._clock() + COMMON_LOCK_TIMEOUT_SECONDS
    fence_ack_deadline = min(
        publication_deadline,
        lock._clock() + fence_ack_window,
    )
    try:
        while True:
            try:
                child = _spawn_blocked_fence_child(
                    argv,
                    cwd=Path(cwd),
                    env=env,
                    deadline=fence_ack_deadline,
                    clock=lock._clock,
                    sleeper=lock._sleeper,
                )
            except ChildProcessError as exc:
                raise CommonLockUnavailable(
                    {
                        "common_dir": str(lock.common_dir),
                        "detail": "blocked child could not be reaped after acknowledgement failure",
                        "error": str(exc),
                    }
                ) from exc
            except OSError as exc:
                if not _sleep_with_deadline(
                    publication_deadline, lock._clock, lock._sleeper
                ):
                    raise CommonLockUnavailable(
                        {
                            "common_dir": str(lock.common_dir),
                            "detail": "blocked-child acknowledgement exhausted the fence-publication retry deadline",
                            "error": str(exc),
                        }
                    ) from exc
                fence_ack_deadline = min(
                    publication_deadline,
                    lock._clock() + fence_ack_window,
                )
                lock.assert_held(allow_fence=True)
                continue
            lock._emit_boundary("fence-child-blocked")
            record = _validate_fence_record(
                {
                    "schema": "forge-rebase-inflight/1",
                    "owner_kind": lock.owner.record["owner_kind"],
                    "chain_id": lock.owner.record["chain_id"],
                    "operation": operation,
                    "host": lock.owner.record["host"],
                    "pid": child.pid,
                    "pgid": child.pgid,
                    "started_at": iso_z(),
                    "intent_digest": intent_digest,
                    "nonce": secrets.token_hex(16),
                }
            )
            try:
                fence = _publish_fence(lock, record)
                break
            except _PublicationCleanupFailure as exc:
                stopped = _stop_unstarted_child(
                    child,
                    clock=lock._clock,
                    sleeper=lock._sleeper,
                )
                child = None
                if not stopped:
                    detail = "publication cleanup and blocked-child reap both failed"
                else:
                    detail = "fence publication cleanup could not prove durable removal"
                raise CommonLockUnavailable(
                    {
                        "common_dir": str(lock.common_dir),
                        "detail": detail,
                        "error": str(exc),
                    }
                ) from exc
            except (OSError, ValueError) as exc:
                stopped = _stop_unstarted_child(
                    child,
                    clock=lock._clock,
                    sleeper=lock._sleeper,
                )
                child = None
                if not stopped:
                    raise CommonLockUnavailable(
                        {
                            "common_dir": str(lock.common_dir),
                            "detail": "blocked child could not be reaped after failed fence publication",
                        }
                    )
                if not _sleep_with_deadline(
                    publication_deadline, lock._clock, lock._sleeper
                ):
                    detail = (
                        "existing in-flight fence exhausted the fence-publication deadline"
                        if isinstance(exc, FileExistsError)
                        else "incomplete fence publication exhausted the fence-publication deadline"
                    )
                    raise CommonLockUnavailable(
                        {
                            "common_dir": str(lock.common_dir),
                            "detail": detail,
                            "error": str(exc),
                        }
                    )
                fence_ack_deadline = min(
                    publication_deadline,
                    lock._clock() + fence_ack_window,
                )
                lock.assert_held(allow_fence=True)
        lock.assert_held(allow_fence=True)
        assert child is not None and fence is not None
        _revalidate_record_at(
            lock._common,
            COMMON_LOCK_INFLIGHT_NAME,
            lock.common_dir / COMMON_LOCK_INFLIGHT_NAME,
            fence,
            _validate_fence_record,
        )
        if not intent_validator():
            stopped = _stop_unstarted_child(
                child,
                clock=lock._clock,
                sleeper=lock._sleeper,
            )
            child = None
            if not stopped:
                lock._unresolved_fence = fence
                raise CommonLockUnavailable(
                    {
                        "common_dir": str(lock.common_dir),
                        "detail": "blocked child could not be reaped after intent revalidation failed",
                    }
                )
            _unlink_revalidated_record_at(
                lock._common,
                COMMON_LOCK_INFLIGHT_NAME,
                lock.common_dir / COMMON_LOCK_INFLIGHT_NAME,
                fence,
                _validate_fence_record,
            )
            os.fsync(lock._common)
            fence = None
            raise CommonLockUnavailable(
                {
                    "common_dir": str(lock.common_dir),
                    "detail": "durable operation intent changed before the start byte",
                }
            )
        lock._emit_boundary("fence-before-authorization")
        os.write(child.start_descriptor, b"\x01")
        os.close(child.start_descriptor)
        child.start_descriptor = -1
        authorized = True
        lock._emit_boundary("fence-after-authorization")
        started = clock()
        (
            returncode,
            output,
            output_digest,
            timed_out,
            output_limit,
            launch_failed,
            group_survived,
        ) = _collect_fenced_child(
            child,
            argv=argv,
            started=started,
            timeout=float(timeout),
            cap=cap,
            clock=clock,
            sleeper=sleeper,
            group_probe=probe,
            signal_group=signal_group,
            verbose=verbose,
        )
        child = None
        result = FencedProcessResult(
            argv=list(argv),
            returncode=returncode,
            duration_seconds=clock() - started,
            output=output,
            output_digest=output_digest,
            timed_out=timed_out,
            output_limit=output_limit,
            launch_failed=launch_failed,
            group_survived=group_survived,
            authorized=authorized,
            fence_digest=fence.digest,
            fence_inode=fence.inode,
        )
        if result_transform is not None:
            result = result_transform(result)
            if not isinstance(result, FencedProcessResult):
                raise TypeError("fenced result transform returned a malformed result")
        # The collection loop's final probe and result transformation precede
        # the durable callback.  Re-prove group death once more here so the
        # persisted envelope can never claim ``group_survived=false`` and then
        # be contradicted by the pre-unlink probe.
        if result.group_survived or probe(int(fence.record["pgid"])) != "dead":
            result = dataclasses.replace(result, group_survived=True)
        lock._emit_boundary("fence-before-result")
        persist_result(result)
        lock._emit_boundary("fence-result-persisted")
        if result.group_survived:
            lock._unresolved_fence = fence
            raise FencedChildSurvived(result)
        if probe(int(fence.record["pgid"])) != "dead":
            lock._unresolved_fence = fence
            raise FencedChildSurvived(dataclasses.replace(result, group_survived=True))
        try:
            _unlink_revalidated_record_at(
                lock._common,
                COMMON_LOCK_INFLIGHT_NAME,
                lock.common_dir / COMMON_LOCK_INFLIGHT_NAME,
                fence,
                _validate_fence_record,
            )
            os.fsync(lock._common)
            lock._emit_boundary("fence-released")
        except (OSError, ValueError) as exc:
            lock._unresolved_fence = fence
            lock._release_pending = True
            raise CommonLockReleaseFailure(
                {
                    "path": str(lock.common_dir / COMMON_LOCK_INFLIGHT_NAME),
                    "inode": fence.inode,
                    "digest": fence.digest,
                    "error": str(exc),
                }
            ) from exc
        return result
    except BaseException as exc:
        if isinstance(exc, CommonLockBoundaryCrash):
            raise
        if child is not None:
            if child.start_descriptor >= 0 and not authorized:
                stopped = _stop_unstarted_child(
                    child,
                    clock=lock._clock,
                    sleeper=lock._sleeper,
                )
                if not stopped:
                    if fence is not None:
                        lock._unresolved_fence = fence
                    raise CommonLockUnavailable(
                        {
                            "common_dir": str(lock.common_dir),
                            "detail": "blocked child could not be reaped during failure cleanup",
                        }
                    ) from exc
            else:
                try:
                    _terminate_fenced_group(
                        child,
                        signal_group=signal_group,
                        group_probe=probe,
                        clock=clock,
                        sleeper=sleeper,
                    )
                finally:
                    for descriptor in (
                        child.output_descriptor,
                        child.exec_error_descriptor,
                    ):
                        try:
                            os.close(descriptor)
                        except OSError:
                            pass
        if fence is not None and not isinstance(
            exc, (FencedChildSurvived, CommonLockReleaseFailure)
        ):
            # Once authorization may have occurred, an absent durable result
            # is a recovery fact: retain the fence for observation.  Before
            # authorization, ordinary validation/publication failures may
            # release the proven fence after the blocked child exits.
            if authorized:
                lock._unresolved_fence = fence
        raise
