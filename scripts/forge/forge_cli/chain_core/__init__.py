"""Forge CLI chain core: the fenced process runner, the FR-235 common-lock arbiter and
chain leases, chain and merge-chain storage, merge state/transition validation, and the
ingest verifiers (cli split phase 2b, bead forge-plugin-95e.3).

Moved verbatim from scripts/forge/cli.py. Runtime controls are read through
``forge_cli.runtime``; the chain journal-record builder stays in the shim and is reached
through the late-bound ``runtime._build_chain_journal_records`` seam.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence
from pathlib import Path
import dataclasses
import datetime as dt
import errno
import fcntl
import os
import secrets
import socket
import stat
import sys
import time

from forge_cli import runtime
from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode
from ._state import (
    SCHEMA as SCHEMA,
    KIND as KIND,
    FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE,
    FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS,
    FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT,
    STATES as STATES,
    STATE_KEYS as STATE_KEYS,
    EVENT_KEYS as EVENT_KEYS,
    MERGE_STATE_KEYS as MERGE_STATE_KEYS,
    _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES,
    _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES,
    MERGE_EVENT_KEYS as MERGE_EVENT_KEYS,
    MERGE_EVENT_NAMES as MERGE_EVENT_NAMES,
    MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS,
    TIER_RANK as TIER_RANK,
    INACTIVE_SECONDS as INACTIVE_SECONDS,
    FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS,
    FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS,
    FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES,
    FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS,
    FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS,
    ZERO_DIGEST as ZERO_DIGEST,
    COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS,
    COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS,
    COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES,
    MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES,
    COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME,
    COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME,
    COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME,
    COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME,
    COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME,
    COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME,
    CHAIN_ID_RE as CHAIN_ID_RE,
    SHA256_RE as SHA256_RE,
    COMMIT_RE as COMMIT_RE,
    RUN_ID_RE as RUN_ID_RE,
    _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD,
    _WORKTREE_LOCKS as _WORKTREE_LOCKS,
    _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE,
    _exclusive_descriptor_lock as _exclusive_descriptor_lock,
    _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS,
    _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET,
    _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY,
)
from ._controls import (
    COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS,
    COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS,
    COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS,
    COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS,
    _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS,
    _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS,
    _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS,
    _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS,
    _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS,
    COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS,
    CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA,
    CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT,
    CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS,
    _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS,
    MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS,
    _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS,
    MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS,
    _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS,
    MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS,
    INGEST_PROOF_ORDER as INGEST_PROOF_ORDER,
    _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS,
    INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS,
    _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA,
    _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA,
    _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA,
    _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA,
    _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS,
    _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA,
    _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA,
    _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA,
    _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA,
)
from ._core import (
    canonical_bytes as canonical_bytes,
    _chain_storage_root as _chain_storage_root,
    _validated_commitment_path as _validated_commitment_path,
    _parsed_run_captured_path as _parsed_run_captured_path,
    _require_ingest_proof as _require_ingest_proof,
    iso_z as iso_z,
    parse_time as parse_time,
    _require_merge_store_control as _require_merge_store_control,
    _require_merge_adapter_control as _require_merge_adapter_control,
    _require_merge_integration_control as _require_merge_integration_control,
    _require_common_lock_control as _require_common_lock_control,
    CommonLockBoundaryCrash as CommonLockBoundaryCrash,
    PublishedLockRecord as PublishedLockRecord,
    CommonLockInspection as CommonLockInspection,
    CommonLockUnavailable as CommonLockUnavailable,
    CommonLockReleaseFailure as CommonLockReleaseFailure,
    ChainLeaseUnavailable as ChainLeaseUnavailable,
    FencedChildSurvived as FencedChildSurvived,
    _valid_utc_second as _valid_utc_second,
    _valid_positive_int as _valid_positive_int,
    _valid_nonnegative_int as _valid_nonnegative_int,
    _valid_host as _valid_host,
    _valid_nonce as _valid_nonce,
    _valid_nullable_chain as _valid_nullable_chain,
    _write_all as _write_all,
    _PublicationCleanupFailure as _PublicationCleanupFailure,
    _process_probe as _process_probe,
    _group_probe as _group_probe,
    _sleep_with_deadline as _sleep_with_deadline,
    _require_deadline_open as _require_deadline_open,
    FencedProcessResult as FencedProcessResult,
    merge_gate_intent_digest as merge_gate_intent_digest,
    _forge_command as _forge_command,
    MergeRunTaskSnapshot as MergeRunTaskSnapshot,
    _merge_refusal as _merge_refusal,
    _valid_sorted_unique_strings as _valid_sorted_unique_strings,
)
from ._candidate_v2 import candidate_is_v2 as candidate_is_v2, _candidate_binding_for_state_with_candidate_v2 as _candidate_binding_for_state_with_candidate_v2, _binding_shape_valid_with_candidate_v2 as _binding_shape_valid_with_candidate_v2, _event_batch_records_with_candidate_v2 as _event_batch_records_with_candidate_v2, _binding_matches_source_fact_with_candidate_v2 as _binding_matches_source_fact_with_candidate_v2, _binding_is_current_with_candidate_v2 as _binding_is_current_with_candidate_v2, _commit_transition_valid_with_candidate_v2 as _commit_transition_valid_with_candidate_v2
from ._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot, _ChainReceiptSnapshotVerifier as _ChainReceiptSnapshotVerifier
from ._merge_plan import (
    _merge_plan_position_fact as _merge_plan_position_fact,
    _merge_carried_gate_steps as _merge_carried_gate_steps,
    _merge_gate_step_generation_digests as _merge_gate_step_generation_digests,
    _merge_current_authority_valid as _merge_current_authority_valid,
    _merge_remote_only_equality_proof as _merge_remote_only_equality_proof,
    _merge_carry_payload_valid as _merge_carry_payload_valid,
    _merge_plan_transition_valid as _merge_plan_transition_valid,
)
from ._bootstrap_observation import (
    _bootstrap_fetch_observation_record_valid as _bootstrap_fetch_observation_record_valid,
    _bootstrap_fetch_observation_transition_valid as _bootstrap_fetch_observation_transition_valid,
)
from ._fenced_child import (
    _BlockedFenceChild as _BlockedFenceChild,
    _pipe_cloexec as _pipe_cloexec,
    _read_child_ack as _read_child_ack,
    _waitpid_nohang as _waitpid_nohang,
    _wait_for_child_exit as _wait_for_child_exit,
    _spawn_blocked_fence_child as _spawn_blocked_fence_child,
    _terminate_fenced_group as _terminate_fenced_group,
    _stop_unstarted_child as _stop_unstarted_child,
    _collect_fenced_child as _collect_fenced_child,
)
from ._ingest_capture import (
    _read_ingest_input as _read_ingest_input,
    _capture_ingest_blob as _capture_ingest_blob,
    _capture_run_evidence as _capture_run_evidence,
    _capture_ingest_record_evidence as _capture_ingest_record_evidence,
)
from ._chain_state import (
    validate_state as validate_state,
)
from ._ingest_currency import (
    _ingest_captured_paths as _ingest_captured_paths,
    _ingest_step_is_current as _ingest_step_is_current,
    _ingest_secret_scan_is_current as _ingest_secret_scan_is_current,
    _prove_ingest_live_chain as _prove_ingest_live_chain,
)
from ._lock_record_validators import (
    _validate_owner_record as _validate_owner_record,
    _validate_fence_record as _validate_fence_record,
    _validate_recovery_record as _validate_recovery_record,
    _validate_chain_lease_record as _validate_chain_lease_record,
)
from ._merge_cleanup_intent import (
    _recovery_event_intent as _recovery_event_intent,
    _recovery_cleanup_intent as _recovery_cleanup_intent,
    _merge_cleanup_expected_subject as _merge_cleanup_expected_subject,
    _merge_cleanup_expected_argv as _merge_cleanup_expected_argv,
    _merge_cleanup_intent_valid as _merge_cleanup_intent_valid,
)
from ._merge_events import (
    _merge_event_outbox as _merge_event_outbox,
    _merge_payload_delta as _merge_payload_delta,
    reduce_merge_event as reduce_merge_event,
)
from ._merge_rebase import (
    _parse_registered_worktrees as _parse_registered_worktrees,
    _merge_rebase_action as _merge_rebase_action,
    _merge_rebase_result_classification as _merge_rebase_result_classification,
    _merge_containment as _merge_containment,
    _merge_old_tip_all_false as _merge_old_tip_all_false,
    _merge_latest_contained_attempt as _merge_latest_contained_attempt,
    _merge_inactive_post_attempt_recovery_ready as _merge_inactive_post_attempt_recovery_ready,
    _remote_observation_heads as _remote_observation_heads,
    _remote_observation_fetch_argv as _remote_observation_fetch_argv,
    _remote_containment_argv as _remote_containment_argv,
)
from ._merge_state_shape import (
    _merge_gate_plan_valid as _merge_gate_plan_valid,
    _merge_epoch_valid as _merge_epoch_valid,
    _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending,
    _merge_revision9_compatibility_view as _merge_revision9_compatibility_view,
    _merge_state_shape_valid as _merge_state_shape_valid,
    _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid,
    _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar,
)
from ._repository import (
    Repository as Repository,
    _committed_changelog_output_paths as _committed_changelog_output_paths,
)
from ._lock_record_io import (
    _read_owned_record_at as _read_owned_record_at,
    _same_published_record as _same_published_record,
    _open_lock_directory as _open_lock_directory,
    _opaque_path_evidence_at as _opaque_path_evidence_at,
    _inspect_common_lock_fd as _inspect_common_lock_fd,
    _create_private_record_at as _create_private_record_at,
    _publish_no_replace_link as _publish_no_replace_link,
    _revalidate_record_at as _revalidate_record_at,
    _unlink_revalidated_record_at as _unlink_revalidated_record_at,
    _record_at_if_present as _record_at_if_present,
)
from ._merge_cleanup_history import (
    _merge_cleanup_evidence_history as _merge_cleanup_evidence_history,
    _merge_cleanup_history_summary as _merge_cleanup_history_summary,
    _merge_cleanup_unmatched_intent as _merge_cleanup_unmatched_intent,
    _merge_cleanup_retry_proof_valid as _merge_cleanup_retry_proof_valid,
    _merge_cleanup_intent_transition_valid as _merge_cleanup_intent_transition_valid,
    _merge_history_has_git_mutation_intent as _merge_history_has_git_mutation_intent,
)
from ._merge_cleanup_observation import (
    _merge_cleanup_process_output as _merge_cleanup_process_output,
    _merge_cleanup_process_complete as _merge_cleanup_process_complete,
    _merge_cleanup_branch_observation as _merge_cleanup_branch_observation,
    _merge_cleanup_worktree_inventory as _merge_cleanup_worktree_inventory,
    _merge_cleanup_fetch_head_bytes as _merge_cleanup_fetch_head_bytes,
    _merge_cleanup_observation_valid as _merge_cleanup_observation_valid,
)
from ._merge_scope_binding import (
    _merge_scope_environment_contract as _merge_scope_environment_contract,
    _validate_merge_scope_request as _validate_merge_scope_request,
    _merge_retained_inflight as _merge_retained_inflight,
    _validate_merge_scope_fetch_binding as _validate_merge_scope_fetch_binding,
    _merge_scope_binding_names as _merge_scope_binding_names,
    _merge_full_patch_argv as _merge_full_patch_argv,
    _merge_scope_argv as _merge_scope_argv,
    _merge_scope_binding_validator as _merge_scope_binding_validator,
)
from ._remote_observation import (
    _remote_containment_evidence_valid as _remote_containment_evidence_valid,
    _remote_observation_progress_valid as _remote_observation_progress_valid,
    _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid,
    _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed,
    _replayed_remote_observation_completed as _replayed_remote_observation_completed,
)
from ._merge_candidate_observation_steps import (
    _merge_candidate_observation_step_specs as _merge_candidate_observation_step_specs,
    _merge_candidate_observation_step_names as _merge_candidate_observation_step_names,
    _merge_candidate_observation_binding as _merge_candidate_observation_binding,
)
from ._merge_cleanup_result import (
    _merge_cleanup_process_result_valid as _merge_cleanup_process_result_valid,
    _merge_cleanup_step_result_valid as _merge_cleanup_step_result_valid,
    _merge_cleanup_results_valid as _merge_cleanup_results_valid,
    _merge_cleanup_result_transition_valid as _merge_cleanup_result_transition_valid,
)
from ._merge_release import (
    _merge_attempted_release_preconditions_valid as _merge_attempted_release_preconditions_valid,
    _merge_release_preconditions_valid as _merge_release_preconditions_valid,
)
from ._merge_scope import (
    _validate_merge_scope_proof as _validate_merge_scope_proof,
    _merge_scope_event_binding_valid as _merge_scope_event_binding_valid,
    _merge_scope_transition_valid as _merge_scope_transition_valid,
)
from ._merge_candidate_observation import (
    _merge_candidate_observation_record_valid as _merge_candidate_observation_record_valid,
    _merge_candidate_observation_transition_valid as _merge_candidate_observation_transition_valid,
    _merge_candidate_observation_evidence as _merge_candidate_observation_evidence,
    _merge_candidate_observation_evidence_valid as _merge_candidate_observation_evidence_valid,
)
from ._merge_epoch import (
    _epoch_fetch_observation_record_valid as _epoch_fetch_observation_record_valid,
    _epoch_fetch_observation_passed as _epoch_fetch_observation_passed,
    _epoch_ancestry_record_valid as _epoch_ancestry_record_valid,
    _epoch_fetch_result_intent_digest as _epoch_fetch_result_intent_digest,
)
from ._merge_recovery_lifecycle import (
    _published_recovery_evidence_valid as _published_recovery_evidence_valid,
    _recovery_value_carries_inflight as _recovery_value_carries_inflight,
    _recovery_cleanup_result_matches as _recovery_cleanup_result_matches,
    _classify_merge_recovery_lifecycle as _classify_merge_recovery_lifecycle,
)
from ._merge_recovery_proof import (
    _merge_recovery_proof_transition_valid as _merge_recovery_proof_transition_valid,
    _epoch_fetch_observation_predecessor_valid as _epoch_fetch_observation_predecessor_valid,
    _recovered_absent_rebase_intent_digest as _recovered_absent_rebase_intent_digest,
)
from ._merge_transition import (
    _merge_transition_valid as _merge_transition_valid,
    _merge_ingest_transition_valid as _merge_ingest_transition_valid,
)
from ._ingest_merge import _merge_ingest_binding as _merge_ingest_binding, _merge_gate_event_fact as _merge_gate_event_fact, _merge_current_gate_facts as _merge_current_gate_facts, _merge_ingest_record_templates as _merge_ingest_record_templates, _verify_and_build_merge_ingest_records as _verify_and_build_merge_ingest_records, _ingest_allocation_records as _ingest_allocation_records
from ._merge_replay import (
    validate_merge_state as validate_merge_state,
    MergeReplayResult as MergeReplayResult,
    _replay_merge_event_bytes as _replay_merge_event_bytes,
)
from ._chain_batch_carrier import _coordination_refusal as _coordination_refusal, _drain_chain_batch_capability as _drain_chain_batch_capability, _prevalidate_chain_batch_carrier as _prevalidate_chain_batch_carrier, _validate_chain_batch_target as _validate_chain_batch_target
from ._activation import _ChainActivationSnapshot as _ChainActivationSnapshot, _chain_activation_ownership_summary as _chain_activation_ownership_summary, _validate_chain_activation_lineage as _validate_chain_activation_lineage, _resolve_chain_activation_snapshot as _resolve_chain_activation_snapshot
from ._storage import (
    _ChainStoragePrimitives as _ChainStoragePrimitives,
)
from ._activation_outbox import _resolve_chain_activation_projection as _resolve_chain_activation_projection, _require_no_pending_chain_activation_outbox as _require_no_pending_chain_activation_outbox, _prepare_merge_activation_preamble as _prepare_merge_activation_preamble
from ._chain_batch_authorize import (
    _authorize_chain_batch as _authorize_chain_batch,
)
from ._commit_chain import CLIOptions as CLIOptions, register_activation_reservation_seam as register_activation_reservation_seam, _validate_bound_chain_state as _validate_bound_chain_state, _user_skip as _user_skip, _gate_one_complete as _gate_one_complete, _latest_current_pass as _latest_current_pass, _gate_satisfied as _gate_satisfied, _verify_and_build_ingest_records as _verify_and_build_ingest_records, _ingest_proof_verifier as _ingest_proof_verifier, register_coordination_seams as register_coordination_seams, ChainStore as ChainStore, CommandContext as CommandContext, _policy_for_state as _policy_for_state, _fresh_reviewer_evals_required as _fresh_reviewer_evals_required, _required_steps as _required_steps, _chain_batch_lock as _chain_batch_lock
from ._lock_reservation import (
    _open_owned_directory as _open_owned_directory,
    RecoveryReservation as RecoveryReservation,
    _publish_recovery_reservation as _publish_recovery_reservation,
    _reservation_evidence as _reservation_evidence,
    _clear_owned_reservation as _clear_owned_reservation,
    _recovery_record as _recovery_record,
)
from ._lock_owner import (
    _new_owner_record as _new_owner_record,
    _fence_matches_owner as _fence_matches_owner,
    _release_portable_identity as _release_portable_identity,
    _publish_portable_owner as _publish_portable_owner,
)
from ._lock_recovery import (
    _fence_death_proof as _fence_death_proof,
    _require_recovery_proof_recorder as _require_recovery_proof_recorder,
    _persist_recovery_proof as _persist_recovery_proof,
    _read_fence_for_recovery as _read_fence_for_recovery,
    _common_fence_path_present as _common_fence_path_present,
    _recover_stale_portable_owner as _recover_stale_portable_owner,
)
from forge_cli.chain_core._merge_chain import (
    _build_merge_chain_journal_records,
    _new_merge_record_is_current,
    _prove_merge_run_task_binding,
    _repository_recovery_reservation_present,
    MergeChainStore,
    _recovery_classification_receipt_valid,
    CommonRebaseLock,
    _clear_reserved_fence,
    ChainLease,
    _lease_exclusion_is_current,
    _lease_reclaim_authority_is_current,
    _reconcile_merge_projection_for_lease_reclaim,
    acquire_chain_lease,
)


# The Revision-9 seam marker rides on the callables themselves so the registrar above can
# tell an already-installed forge seam from a foreign registration (moved here from the
# shim in cli split phase 3; the shim no longer defines any seam callable).
for _seam in (
    reduce_merge_event,
    _authorize_chain_batch,
    _ingest_proof_verifier,
    _require_no_pending_chain_activation_outbox,
):
    setattr(_seam, "_forge_cli_revision9_seam", True)


def _acquire_secondary_flock(
    common: int,
    common_dir: Path,
    owner_record: Mapping[str, Any],
    *,
    deadline: float,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
    flock_impl: Callable[[int, int], Any],
    boundary: Callable[[str], None] | None,
) -> int:
    descriptor = os.open(
        COMMON_LOCK_FLOCK_NAME,
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=common,
    )
    acquired = False
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
            raise OSError("secondary flock path is not owner-controlled and regular")
        os.fchmod(descriptor, 0o600)
        while True:
            try:
                flock_impl(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                _require_deadline_open(deadline, clock, "secondary flock acquisition")
                break
            except (BlockingIOError, InterruptedError) as exc:
                if isinstance(exc, BlockingIOError) and exc.errno not in {
                    None,
                    errno.EACCES,
                    errno.EAGAIN,
                }:
                    raise
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise TimeoutError("secondary flock exhausted the shared deadline")
        if boundary is not None:
            boundary("flock-acquired")
        encoded = canonical_bytes(dict(owner_record))
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.ftruncate(descriptor, 0)
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
        if boundary is not None:
            boundary("flock-record-fsynced")
        return descriptor
    except BaseException:
        if acquired:
            try:
                flock_impl(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(descriptor)
        raise


def acquire_common_lock(
    common_dir: Path,
    *,
    owner_kind: str,
    chain_id: str | None,
    operation: str,
    timeout: float = COMMON_LOCK_TIMEOUT_SECONDS,
    use_flock: bool | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    now: Callable[[], dt.datetime] = runtime.utc_now,
    host: str | None = None,
    pid: int | None = None,
    pid_probe: Callable[[int], str] = _process_probe,
    group_probe: Callable[[int], str] = _group_probe,
    flock_impl: Callable[[int, int], Any] = fcntl.flock,
    admission_recheck: Callable[[], bool] | None = None,
    recovery_recorder: Callable[[dict[str, Any]], Any] | None = None,
    recovery_classifier: (
        Callable[[RecoveryReservation, PublishedLockRecord | None], Any] | None
    ) = None,
    no_transaction_record: bool = False,
    boundary: Callable[[str], None] | None = None,
) -> CommonRebaseLock:
    """Acquire the universal FR-235 common lock under one monotonic budget."""

    _require_common_lock_control("single-deadline")
    _require_common_lock_control("portable-before-flock")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("common-lock timeout must be positive")
    if recovery_recorder is not None and not callable(recovery_recorder):
        raise ValueError("common-lock recovery recorder must be callable")
    if recovery_classifier is not None and not callable(recovery_classifier):
        raise ValueError("common-lock recovery classifier must be callable")
    if recovery_classifier is not None and operation != "recover":
        raise ValueError(
            "common-lock recovery classifier requires an explicit recovery operation"
        )
    if not isinstance(no_transaction_record, bool):
        raise ValueError("common-lock no-transaction opt-out must be boolean")
    local_host = host or socket.gethostname()
    claimant_pid = pid or os.getpid()
    owner_record = _new_owner_record(
        owner_kind,
        chain_id,
        operation,
        host=local_host,
        pid=claimant_pid,
        now=now,
    )
    if recovery_recorder is not None and no_transaction_record:
        raise ValueError(
            "common-lock recovery recorder conflicts with no-transaction opt-out"
        )
    if owner_kind in {"merge", "push"}:
        try:
            _require_recovery_proof_recorder(
                (owner_kind,),
                recovery_recorder,
                no_transaction_record=no_transaction_record,
            )
        except OSError as exc:
            raise ValueError(str(exc)) from exc
    lifecycle_classifier = recovery_classifier
    flock_enabled = hasattr(fcntl, "flock") if use_flock is None else use_flock
    canonical, common = _open_owned_directory(common_dir)
    deadline = clock() + float(timeout)
    last_evidence: dict[str, Any] = {"common_dir": str(canonical)}
    reservation: RecoveryReservation | None = None
    classified_reservation_digest: str | None = None
    proof_persisted_reservation_digest: str | None = None
    portable: PublishedLockRecord | None = None
    flock_descriptor: int | None = None
    try:
        while True:
            if clock() >= deadline:
                raise CommonLockUnavailable(last_evidence)
            existing_reservation = _reservation_evidence(common, canonical)
            if existing_reservation is not None and reservation is None:
                last_evidence = {
                    "common_dir": str(canonical),
                    **existing_reservation,
                }
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise CommonLockUnavailable(last_evidence)
                continue
            if operation != "recover":
                try:
                    fence_name_present = _common_fence_path_present(common)
                except OSError as exc:
                    fence_name_present = True
                    last_evidence = {
                        "common_dir": str(canonical),
                        "detail": (
                            "surviving in-flight fence requires explicit "
                            f"recovery: {exc}"
                        ),
                    }
                if fence_name_present:
                    last_evidence = {
                        **last_evidence,
                        "detail": (
                            "surviving in-flight fence requires explicit recovery"
                        ),
                    }
                    if not _sleep_with_deadline(deadline, clock, sleeper):
                        raise CommonLockUnavailable(last_evidence)
                    continue
            inspection = _inspect_common_lock_fd(common, canonical)
            last_evidence = inspection.evidence(canonical)
            if inspection.topology == "free":
                try:
                    _require_deadline_open(
                        deadline, clock, "portable owner publication"
                    )
                    portable = _publish_portable_owner(
                        common, canonical, owner_record, boundary
                    )
                except FileExistsError:
                    portable = None
                    if not _sleep_with_deadline(deadline, clock, sleeper):
                        raise CommonLockUnavailable(last_evidence)
                    continue
                except (OSError, ValueError) as exc:
                    portable = None
                    last_evidence = {
                        **last_evidence,
                        "mechanism": "no-replace hard-link publication",
                        "error": str(exc),
                    }
                    if reservation is not None or not _sleep_with_deadline(
                        deadline, clock, sleeper
                    ):
                        raise CommonLockUnavailable(last_evidence)
                    continue
            elif reservation is None and inspection.recoverable and inspection.outer is not None:
                stale = inspection.outer
                if stale.record.get("host") != local_host:
                    last_evidence["detail"] = "portable owner host is foreign"
                elif pid_probe(int(stale.record["pid"])) != "dead":
                    last_evidence["detail"] = "portable owner PID is live or unprovable"
                elif (
                    operation != "recover"
                    and stale.record.get("owner_kind") == "merge"
                ):
                    last_evidence["detail"] = (
                        "stale merge portable owner requires explicit recovery"
                    )
                elif operation != "recover" and _common_fence_path_present(
                    common
                ):
                    last_evidence["detail"] = (
                        "surviving in-flight fence requires explicit recovery"
                    )
                else:
                    if operation == "recover":
                        fence, fence_error, fence_evidence = (
                            _read_fence_for_recovery(common, canonical)
                        )
                    else:
                        # Ordinary legacy-owner recovery is admitted only
                        # after the presence-only check above.  It never opens,
                        # parses, probes, classifies, or clears a fence.
                        fence, fence_error, fence_evidence = None, None, None
                    recovery_kind = "fallback-owner"
                    if fence_error is not None:
                        last_evidence["detail"] = f"in-flight fence is unprovable: {fence_error}"
                        if fence_evidence is not None:
                            last_evidence.update(fence_evidence)
                    elif fence is not None:
                        if (
                            not _fence_matches_owner(fence, stale)
                            or fence.record.get("host") != local_host
                            or group_probe(int(fence.record["pgid"])) != "dead"
                        ):
                            last_evidence["detail"] = "in-flight fence is live, foreign, mismatched, or unprovable"
                        else:
                            recovery_kind = "fallback-owner-and-fence"
                    if fence_error is None and (
                        fence is None or recovery_kind == "fallback-owner-and-fence"
                    ):
                        if (
                            operation != "recover"
                            and stale.record.get("owner_kind") == "merge"
                        ):
                            # A dead portable owner is still transaction
                            # evidence.  Ordinary acquisition has no authority
                            # to classify or remove it (with or without a
                            # surviving fence); explicit recovery must first
                            # publish the immutable reservation and durable
                            # lifecycle/death proof.
                            last_evidence["detail"] = (
                                "stale portable owner requires explicit recovery"
                            )
                            if not _sleep_with_deadline(
                                deadline, clock, sleeper
                            ):
                                raise CommonLockUnavailable(last_evidence)
                            continue
                        _require_recovery_proof_recorder(
                            (
                                str(stale.record["owner_kind"]),
                                *(
                                    (str(fence.record["owner_kind"]),)
                                    if fence is not None
                                    else ()
                                ),
                            ),
                            recovery_recorder,
                            no_transaction_record=no_transaction_record,
                        )
                        _require_deadline_open(
                            deadline, clock, "stale-owner and fence proof"
                        )
                        record = _recovery_record(
                            recovery_kind,
                            stale_owner=stale,
                            inflight=fence,
                            host=local_host,
                            pid=claimant_pid,
                            now=now,
                        )
                        reservation = _publish_recovery_reservation(
                            common,
                            canonical,
                            record,
                            boundary,
                            deadline=deadline,
                            clock=clock,
                            sleeper=sleeper,
                        )
                        if reservation is not None:
                            _require_deadline_open(
                                deadline, clock, "recovery reservation publication"
                            )
                            try:
                                transactional_recovery = bool(
                                    stale.record.get("owner_kind")
                                    in {"merge", "push"}
                                    or (
                                        fence is not None
                                        and fence.record.get("owner_kind")
                                        in {"merge", "push"}
                                    )
                                )
                                if not transactional_recovery and fence is None:
                                    classification_result = None
                                else:
                                    _require_common_lock_control(
                                        "reservation-held-lifecycle-classification"
                                    )
                                    if lifecycle_classifier is None:
                                        raise OSError(
                                            "reservation-held lifecycle classification is required before stale-owner recovery"
                                        )
                                    reservation.assert_current(
                                        "reservation-held lifecycle classification"
                                    )
                                    classification_result = lifecycle_classifier(
                                        reservation, fence
                                    )
                                    if (
                                        transactional_recovery
                                        and not no_transaction_record
                                        and not (
                                            _recovery_classification_receipt_valid(
                                                classification_result,
                                                reservation=reservation,
                                                fence=fence,
                                            )
                                        )
                                    ):
                                        raise OSError(
                                            "reservation-held lifecycle classification did not return its exact durable receipt"
                                        )
                            except BaseException as classification_error:
                                if isinstance(
                                    classification_error,
                                    CommonLockBoundaryCrash,
                                ):
                                    raise
                                if isinstance(classification_error, Refusal):
                                    _clear_owned_reservation(
                                        common,
                                        canonical,
                                        reservation,
                                        boundary=None,
                                    )
                                    reservation = None
                                    raise
                                if no_transaction_record:
                                    _clear_owned_reservation(
                                        common,
                                        canonical,
                                        reservation,
                                        boundary=None,
                                    )
                                    reservation = None
                                if isinstance(classification_error, FrozenError):
                                    raise
                                raise CommonLockUnavailable(
                                    {
                                        **last_evidence,
                                        "detail": str(classification_error),
                                    }
                                ) from classification_error
                            classified_reservation_digest = (
                                reservation.identity.digest
                            )
                            if _recovery_classification_receipt_valid(
                                classification_result,
                                reservation=reservation,
                                fence=fence,
                            ):
                                proof_persisted_reservation_digest = (
                                    reservation.identity.digest
                                )
                            if fence is not None and boundary is not None:
                                boundary(
                                    "recovery-fence-lifecycle-classified"
                                )
                            _recover_stale_portable_owner(
                                common,
                                canonical,
                                stale,
                                fence,
                                reservation,
                                pid_probe=pid_probe,
                                group_probe=group_probe,
                                deadline=deadline,
                                clock=clock,
                                boundary=boundary,
                                recovery_recorder=recovery_recorder,
                                no_transaction_record=no_transaction_record,
                                proof_already_persisted=(
                                    proof_persisted_reservation_digest
                                    == reservation.identity.digest
                                ),
                            )
                            continue
            if portable is None:
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise CommonLockUnavailable(last_evidence)
                continue
            try:
                if flock_enabled:
                    flock_descriptor = _acquire_secondary_flock(
                        common,
                        canonical,
                        owner_record,
                        deadline=deadline,
                        clock=clock,
                        sleeper=sleeper,
                        flock_impl=flock_impl,
                        boundary=boundary,
                    )
                _require_deadline_open(
                    deadline, clock, "in-flight admission inspection"
                )
                if operation != "recover":
                    if _common_fence_path_present(common):
                        raise OSError(
                            "surviving in-flight fence requires explicit recovery"
                        )
                    fence, fence_error, fence_evidence = None, None, None
                else:
                    if (
                        reservation is None
                        and flock_descriptor is None
                        and _common_fence_path_present(common)
                    ):
                        raise OSError(
                            "outer-owner-absent fence recovery requires the secondary flock"
                        )
                    fence, fence_error, fence_evidence = _read_fence_for_recovery(
                        common, canonical
                    )
                if fence_error is not None:
                    raise OSError(
                        canonical_bytes(
                            {
                                "detail": f"in-flight fence is unprovable: {fence_error}",
                                **(fence_evidence or {}),
                            }
                        ).decode("utf-8")
                    )
                if fence is not None:
                    if reservation is not None:
                        _clear_reserved_fence(
                            common,
                            canonical,
                            reservation,
                            group_probe=group_probe,
                            deadline=deadline,
                            clock=clock,
                            boundary=boundary,
                            recovery_recorder=recovery_recorder,
                            no_transaction_record=no_transaction_record,
                            lifecycle_classifier=lifecycle_classifier,
                            classification_already_performed=(
                                classified_reservation_digest
                                == reservation.identity.digest
                            ),
                            proof_already_persisted=(
                                proof_persisted_reservation_digest
                                == reservation.identity.digest
                            ),
                        )
                    elif (
                        operation == "recover"
                        and flock_descriptor is not None
                        and _fence_matches_owner(fence, portable)
                        and fence.record.get("host") == local_host
                        and group_probe(int(fence.record["pgid"])) == "dead"
                    ):
                        _require_deadline_open(
                            deadline, clock, "dead-fence recovery proof"
                        )
                        record = _recovery_record(
                            "flock-held-dead-fence",
                            stale_owner=None,
                            inflight=fence,
                            host=local_host,
                            pid=claimant_pid,
                            now=now,
                        )
                        _require_recovery_proof_recorder(
                            (str(fence.record["owner_kind"]),),
                            recovery_recorder,
                            no_transaction_record=no_transaction_record,
                        )
                        reservation = _publish_recovery_reservation(
                            common,
                            canonical,
                            record,
                            boundary,
                            deadline=deadline,
                            clock=clock,
                            sleeper=sleeper,
                        )
                        if reservation is None:
                            raise OSError("another recovery reservation won publication")
                        _clear_reserved_fence(
                            common,
                            canonical,
                            reservation,
                            group_probe=group_probe,
                            deadline=deadline,
                            clock=clock,
                            boundary=boundary,
                            recovery_recorder=recovery_recorder,
                            no_transaction_record=no_transaction_record,
                            lifecycle_classifier=lifecycle_classifier,
                        )
                    else:
                        raise OSError("in-flight fence is live, mismatched, or unrecoverable")
                if reservation is not None:
                    _require_deadline_open(
                        deadline, clock, "recovery reservation release"
                    )
                    _clear_owned_reservation(common, canonical, reservation, boundary)
                    reservation = None
                    classified_reservation_digest = None
                    proof_persisted_reservation_digest = None
                if admission_recheck is not None and not admission_recheck():
                    raise OSError("locked admission recheck did not pass")
                if clock() >= deadline:
                    raise TimeoutError("locked admission recheck exhausted the shared deadline")
                return CommonRebaseLock(
                    common_dir=canonical,
                    common_descriptor=common,
                    owner=portable,
                    flock_descriptor=flock_descriptor,
                    flock_impl=flock_impl,
                    boundary=boundary,
                    deadline=deadline,
                    clock=clock,
                    sleeper=sleeper,
                    pid_probe=pid_probe,
                    group_probe=group_probe,
                    recovery_recorder=recovery_recorder,
                    no_transaction_record=no_transaction_record,
                )
            except BaseException as exc:
                if isinstance(exc, CommonLockBoundaryCrash):
                    raise
                last_evidence = {
                    "common_dir": str(canonical),
                    "owner": portable.evidence(),
                    "error": str(exc),
                }
                if reservation is not None and (
                    no_transaction_record or owner_kind not in {"merge", "push"}
                ):
                    try:
                        _clear_owned_reservation(
                            common, canonical, reservation, boundary=None
                        )
                        reservation = None
                    except (OSError, ValueError) as reservation_error:
                        last_evidence["reservation_release_error"] = str(
                            reservation_error
                        )
                        raise CommonLockUnavailable(last_evidence) from reservation_error
                if flock_descriptor is not None:
                    try:
                        flock_impl(flock_descriptor, fcntl.LOCK_UN)
                    finally:
                        os.close(flock_descriptor)
                    flock_descriptor = None
                try:
                    _release_portable_identity(
                        common,
                        canonical,
                        portable,
                        boundary=None,
                        prefix="failed-acquisition",
                        complete_partial=False,
                    )
                except (OSError, ValueError) as release_error:
                    last_evidence["release_error"] = str(release_error)
                    raise CommonLockUnavailable(last_evidence) from release_error
                portable = None
                if isinstance(exc, FrozenError):
                    raise
                if isinstance(exc, CommonLockUnavailable):
                    raise
                if reservation is not None:
                    raise CommonLockUnavailable(last_evidence) from exc
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise CommonLockUnavailable(last_evidence) from exc
    except BaseException as exc:
        if flock_descriptor is not None:
            try:
                flock_impl(flock_descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(flock_descriptor)
        os.close(common)
        if isinstance(exc, TimeoutError):
            raise CommonLockUnavailable(
                {**last_evidence, "error": str(exc)}
            ) from exc
        raise


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


def hold_common_lock(
    repository: Repository,
    *,
    owner_kind: str,
    chain_id: str | None,
    operation: str,
    ready_fd: int,
    input_stream: Any | None = None,
) -> Outcome:
    """Long-lived wrapper protocol for future non-Python lock consumers.

    The caller supplies a writable descriptor numbered three or higher.  Once
    the complete common lock is held, the wrapper writes exactly one canonical
    LF-terminated ``forge-common-lock-ready/1`` record there.  It then accepts
    exactly one stdin frame, the eight bytes ``release\n``, and closes stdin.
    Only after the
    reverse-order release completes does stdout receive the ordinary single
    ``forge-cli/2`` outcome from ``main``.
    """

    if not isinstance(ready_fd, int) or isinstance(ready_fd, bool) or ready_fd < 3:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: common-lock hold refused — --ready-fd must name a writable inherited descriptor >= 3",
            expected="one writable inherited readiness descriptor numbered 3 or higher",
            observed=str(ready_fd),
            remediation="open a dedicated readiness pipe and retry common-lock hold",
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    try:
        os.fstat(ready_fd)
        os.write(ready_fd, b"")
    except OSError as exc:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: common-lock hold refused — readiness descriptor is unavailable",
            expected="a writable inherited readiness descriptor",
            observed=str(exc),
            remediation="open a dedicated readiness pipe and retry common-lock hold",
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc
    try:
        lock = acquire_common_lock(
            repository.git_common_dir(),
            owner_kind=owner_kind,
            chain_id=chain_id,
            operation=operation,
            # This dormant physical-lock wrapper has no transaction store.
            # Consuming merge/push verbs must replace this explicit opt-out
            # with their synchronous transaction recorder before activation.
            no_transaction_record=owner_kind in {"merge", "push"},
        )
    except ValueError as exc:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: common-lock hold refused — owner tuple is invalid",
            expected="an FR-235 owner-kind, chain-id, and operation tuple",
            observed=str(exc),
            remediation="supply the exact owner tuple for the calling Forge operation",
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc
    protocol_error: Refusal | None = None
    try:
        ready = {
            "schema": "forge-common-lock-ready/1",
            "owner_digest": lock.digest,
            "nonce": lock.owner.record["nonce"],
            "pid": lock.owner.record["pid"],
        }
        try:
            _write_all(ready_fd, canonical_bytes(ready) + b"\n")
        except OSError as exc:
            protocol_error = Refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: common-lock hold refused — readiness acknowledgement failed",
                expected="one complete readiness record",
                observed=str(exc),
                remediation="repair the readiness pipe and retry common-lock hold",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if protocol_error is None:
            stream = input_stream if input_stream is not None else sys.stdin.buffer
            try:
                frame = stream.readline(129)
                trailing = stream.read(1) if frame == b"release\n" else b""
            except (OSError, ValueError) as exc:
                frame = b""
                trailing = b""
                protocol_error = Refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: common-lock hold refused — release frame could not be read",
                    observed=str(exc),
                    remediation="send exactly release followed by LF on stdin",
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            if protocol_error is None and (frame != b"release\n" or trailing != b""):
                protocol_error = Refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: common-lock hold refused — invalid release frame",
                    expected="the exact stdin bytes release followed by LF",
                    observed=repr(frame + trailing),
                    remediation="send exactly release followed by LF on stdin",
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
    finally:
        lock.release()
    if protocol_error is not None:
        raise protocol_error
    return Outcome(
        ok=True,
        reason_code=V2ReasonCode.OK,
        message="forge: common rebase lock released",
        chain_id=chain_id,
        next_required_step="none — common rebase lock released",
        evidence_refs=(
            str(lock.common_dir / COMMON_LOCK_INTENT_NAME),
        ),
        schema=REVISION9_OUTPUT_SCHEMA,
    )


__all__ = [
    'CHAIN_ID_RE',
    'CHAIN_TOMBSTONE_EVENT',
    'CHAIN_TOMBSTONE_KEYS',
    'CHAIN_TOMBSTONE_SCHEMA',
    'CLIOptions',
    'COMMIT_RE',
    'COMMON_LOCK_CONTROLS',
    'COMMON_LOCK_DIRECTORY_NAME',
    'COMMON_LOCK_FENCE_OPERATIONS',
    'COMMON_LOCK_FLOCK_NAME',
    'COMMON_LOCK_INFLIGHT_NAME',
    'COMMON_LOCK_INTENT_NAME',
    'COMMON_LOCK_OPERATIONS',
    'COMMON_LOCK_OWNER_KINDS',
    'COMMON_LOCK_OWNER_NAME',
    'COMMON_LOCK_POLL_SECONDS',
    'COMMON_LOCK_RECORD_CAP_BYTES',
    'COMMON_LOCK_RECOVERY_KINDS',
    'COMMON_LOCK_RECOVERY_NAME',
    'COMMON_LOCK_TIMEOUT_SECONDS',
    'ChainLease',
    'ChainLeaseUnavailable',
    'ChainStore',
    'CommandContext',
    'CommonLockBoundaryCrash',
    'CommonLockInspection',
    'CommonLockReleaseFailure',
    'CommonLockUnavailable',
    'CommonRebaseLock',
    'EVENT_KEYS',
    'FENCED_CHILD_ACK_TIMEOUT_SECONDS',
    'FENCED_CHILD_DRAIN_CAP_BYTES',
    'FENCED_CHILD_DRAIN_SECONDS',
    'FENCED_CHILD_REAP_SECONDS',
    'FENCED_CHILD_STOP_GRACE_SECONDS',
    'FRESH_REVIEWER_EVALS_GATE',
    'FRESH_REVIEWER_EVALS_REQUESTED_EVENT',
    'FRESH_REVIEWER_EVALS_REQUESTS',
    'FencedChildSurvived',
    'FencedProcessResult',
    'INACTIVE_SECONDS',
    'INGEST_PROOF_CONTROLS',
    'INGEST_PROOF_ORDER',
    'KIND',
    'MERGE_ADAPTER_CONTROLS',
    'MERGE_CONSEQUENTIAL_EVENTS',
    'MERGE_EVENT_KEYS',
    'MERGE_EVENT_NAMES',
    'MERGE_INTEGRATION_CONTROLS',
    'MERGE_SCOPE_BINDING_CAP_BYTES',
    'MERGE_STATE_KEYS',
    'MERGE_STORE_CONTROLS',
    'MergeChainStore',
    'MergeReplayResult',
    'MergeRunTaskSnapshot',
    'PublishedLockRecord',
    'RUN_ID_RE',
    'RecoveryReservation',
    'Repository',
    'candidate_is_v2',
    '_binding_is_current_with_candidate_v2',
    '_binding_matches_source_fact_with_candidate_v2',
    '_binding_shape_valid_with_candidate_v2',
    '_candidate_binding_for_state_with_candidate_v2',
    '_event_batch_records_with_candidate_v2',
    'SCHEMA',
    'SHA256_RE',
    'STATES',
    'STATE_KEYS',
    'TIER_RANK',
    'ZERO_DIGEST',
    '_BOOTSTRAP_FETCH_OBSERVATION_SCHEMA',
    '_BlockedFenceChild',
    '_CHAIN_LEASE_KEYS',
    '_COMMON_LOCK_FENCE_KEYS',
    '_COMMON_LOCK_OWNER_KEYS',
    '_COMMON_LOCK_RECOVERY_KEYS',
    '_ChainStoragePrimitives',
    '_EPOCH_FETCH_OBSERVATION_SCHEMA',
    '_MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA',
    '_MERGE_CANDIDATE_OBSERVATION_SCHEMA',
    '_MERGE_CLEANUP_CLOSE_SCHEMA',
    '_MERGE_CLEANUP_FENCE_OPERATIONS',
    '_MERGE_CLEANUP_INTENT_SCHEMA',
    '_MERGE_CLEANUP_RECOVERY_SCHEMA',
    '_MERGE_CLEANUP_RESULT_SCHEMA',
    '_MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES',
    '_MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES',
    '_MERGE_REMOTE_ONLY_IDENTITY_FIELDS',
    '_MERGE_SCOPE_OVERLAY',
    '_MERGE_SCOPE_UNSET',
    '_PublicationCleanupFailure',
    '_REQUIRED_COMMON_LOCK_CONTROLS',
    '_REQUIRED_INGEST_PROOF_CONTROLS',
    '_REQUIRED_MERGE_ADAPTER_CONTROLS',
    '_REQUIRED_MERGE_INTEGRATION_CONTROLS',
    '_REQUIRED_MERGE_STORE_CONTROLS',
    '_WORKTREE_LOCKS',
    '_WORKTREE_LOCKS_GUARD',
    '_WORKTREE_LOCK_STATE',
    '_acquire_secondary_flock',
    '_authorize_chain_batch',
    '_bootstrap_fetch_observation_record_valid',
    '_bootstrap_fetch_observation_transition_valid',
    '_build_merge_chain_journal_records',
    '_capture_ingest_blob',
    '_capture_ingest_record_evidence',
    '_capture_run_evidence',
    '_chain_storage_root',
    '_classify_merge_recovery_lifecycle',
    '_clear_owned_reservation',
    '_clear_reserved_fence',
    '_collect_fenced_child',
    '_committed_changelog_output_paths',
    '_common_fence_path_present',
    '_coordination_refusal',
    '_create_private_record_at',
    '_drain_chain_batch_capability',
    '_epoch_ancestry_record_valid',
    '_epoch_fetch_observation_passed',
    '_epoch_fetch_observation_predecessor_valid',
    '_epoch_fetch_observation_record_valid',
    '_epoch_fetch_result_intent_digest',
    '_exclusive_descriptor_lock',
    '_fence_death_proof',
    '_fence_matches_owner',
    '_forge_command',
    '_fresh_reviewer_evals_required',
    '_gate_one_complete',
    '_gate_satisfied',
    '_group_probe',
    '_ingest_captured_paths',
    '_ingest_proof_verifier',
    '_ingest_secret_scan_is_current',
    '_ingest_step_is_current',
    '_inspect_common_lock_fd',
    '_latest_current_pass',
    '_lease_exclusion_is_current',
    '_lease_reclaim_authority_is_current',
    '_merge_attempted_release_preconditions_valid',
    '_merge_bootstrap_classification_pending',
    '_merge_candidate_observation_binding',
    '_merge_candidate_observation_evidence',
    '_merge_candidate_observation_evidence_valid',
    '_merge_candidate_observation_record_valid',
    '_merge_candidate_observation_step_names',
    '_merge_candidate_observation_step_specs',
    '_merge_candidate_observation_transition_valid',
    '_merge_carried_gate_steps',
    '_merge_carry_payload_valid',
    '_merge_cleanup_branch_observation',
    '_merge_cleanup_evidence_history',
    '_merge_cleanup_expected_argv',
    '_merge_cleanup_expected_subject',
    '_merge_cleanup_fetch_head_bytes',
    '_merge_cleanup_history_summary',
    '_merge_cleanup_intent_transition_valid',
    '_merge_cleanup_intent_valid',
    '_merge_cleanup_observation_valid',
    '_merge_cleanup_process_complete',
    '_merge_cleanup_process_output',
    '_merge_cleanup_process_result_valid',
    '_merge_cleanup_result_transition_valid',
    '_merge_cleanup_results_valid',
    '_merge_cleanup_retry_proof_valid',
    '_merge_cleanup_step_result_valid',
    '_merge_cleanup_unmatched_intent',
    '_merge_cleanup_worktree_inventory',
    '_merge_containment',
    '_merge_current_authority_valid',
    '_merge_current_gate_facts',
    '_merge_epoch_valid',
    '_merge_event_outbox',
    '_merge_full_patch_argv',
    '_merge_gate_event_fact',
    '_merge_gate_plan_valid',
    '_merge_gate_step_generation_digests',
    '_merge_history_has_git_mutation_intent',
    '_merge_history_uses_additive_grammar',
    '_merge_inactive_post_attempt_recovery_ready',
    '_merge_ingest_binding',
    '_merge_ingest_record_templates',
    '_merge_ingest_state_shape_valid',
    '_merge_ingest_transition_valid',
    '_merge_latest_contained_attempt',
    '_merge_old_tip_all_false',
    '_merge_payload_delta',
    '_merge_plan_position_fact',
    '_merge_plan_transition_valid',
    '_merge_rebase_action',
    '_merge_rebase_result_classification',
    '_merge_recovery_proof_transition_valid',
    '_merge_refusal',
    '_merge_release_preconditions_valid',
    '_merge_remote_only_equality_proof',
    '_merge_retained_inflight',
    '_merge_revision9_compatibility_view',
    '_merge_scope_argv',
    '_merge_scope_binding_names',
    '_merge_scope_binding_validator',
    '_merge_scope_environment_contract',
    '_merge_scope_event_binding_valid',
    '_merge_scope_transition_valid',
    '_merge_state_shape_valid',
    '_merge_transition_valid',
    '_new_merge_record_is_current',
    '_new_owner_record',
    '_opaque_path_evidence_at',
    '_open_lock_directory',
    '_open_owned_directory',
    '_parse_registered_worktrees',
    '_parsed_run_captured_path',
    '_persist_recovery_proof',
    '_pipe_cloexec',
    '_policy_for_state',
    '_process_probe',
    '_prove_ingest_live_chain',
    '_prove_merge_run_task_binding',
    '_publish_fence',
    '_publish_no_replace_link',
    '_publish_portable_owner',
    '_publish_recovery_reservation',
    '_published_recovery_evidence_valid',
    '_read_child_ack',
    '_read_fence_for_recovery',
    '_read_ingest_input',
    '_read_owned_record_at',
    '_reconcile_merge_projection_for_lease_reclaim',
    '_record_at_if_present',
    '_recover_stale_portable_owner',
    '_recovered_absent_rebase_intent_digest',
    '_recovery_classification_receipt_valid',
    '_recovery_cleanup_intent',
    '_recovery_cleanup_result_matches',
    '_recovery_event_intent',
    '_recovery_record',
    '_recovery_value_carries_inflight',
    '_release_portable_identity',
    '_remote_containment_argv',
    '_remote_containment_evidence_valid',
    '_remote_observation_fetch_argv',
    '_remote_observation_heads',
    '_remote_observation_progress_matches_observed',
    '_remote_observation_progress_transition_valid',
    '_remote_observation_progress_valid',
    '_replay_merge_event_bytes',
    '_replayed_remote_observation_completed',
    '_repository_recovery_reservation_present',
    '_require_common_lock_control',
    '_require_deadline_open',
    '_require_ingest_proof',
    '_require_merge_adapter_control',
    '_require_merge_integration_control',
    '_require_merge_store_control',
    '_require_recovery_proof_recorder',
    '_required_steps',
    '_reservation_evidence',
    '_revalidate_record_at',
    '_same_published_record',
    '_sleep_with_deadline',
    '_spawn_blocked_fence_child',
    '_stop_unstarted_child',
    '_terminate_fenced_group',
    '_unlink_revalidated_record_at',
    '_user_skip',
    '_valid_host',
    '_valid_nonce',
    '_valid_nonnegative_int',
    '_valid_nullable_chain',
    '_valid_positive_int',
    '_valid_sorted_unique_strings',
    '_valid_utc_second',
    '_validate_bound_chain_state',
    '_validate_chain_lease_record',
    '_validate_fence_record',
    '_validate_merge_scope_fetch_binding',
    '_validate_merge_scope_proof',
    '_validate_merge_scope_request',
    '_validate_owner_record',
    '_validate_recovery_record',
    '_validated_commitment_path',
    '_verify_and_build_ingest_records',
    '_verify_and_build_merge_ingest_records',
    '_wait_for_child_exit',
    '_waitpid_nohang',
    '_write_all',
    'acquire_chain_lease',
    'acquire_common_lock',
    'canonical_bytes',
    'hold_common_lock',
    'iso_z',
    'merge_gate_intent_digest',
    'parse_time',
    'reduce_merge_event',
    'register_coordination_seams',
    'run_fenced_command',
    'validate_merge_state',
    'validate_state', "_ReceiptRunSnapshot", "_chain_receipt_snapshot_lock", "_receipt_run_snapshot", "_ChainActivationSnapshot", "_chain_activation_ownership_summary", "_validate_chain_activation_lineage", "_resolve_chain_activation_projection", "register_activation_reservation_seam",
]
