"""Forge CLI chain core: the fenced process runner, the FR-235 common-lock arbiter and
chain leases, chain and merge-chain storage, merge state/transition validation, and the
ingest verifiers (cli split phase 2b, bead forge-plugin-95e.3).

Moved verbatim from scripts/forge/cli.py. Runtime controls are read through
``forge_cli.runtime``; the chain journal-record builder stays in the shim and is reached
through the late-bound ``runtime._build_chain_journal_records`` seam.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence
from pathlib import Path
import contextlib
import copy
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
from forge_cli.policy import sha256_bytes
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
from ._ingest_merge import _merge_ingest_binding as _merge_ingest_binding, _merge_gate_event_fact as _merge_gate_event_fact, _merge_current_gate_facts as _merge_current_gate_facts, _merge_ingest_record_templates as _merge_ingest_record_templates, _ingest_allocation_records as _ingest_allocation_records, _verify_and_build_merge_ingest_records as _verify_and_build_merge_ingest_records
from ._merge_replay import (
    validate_merge_state as validate_merge_state,
    MergeReplayResult as MergeReplayResult,
    _replay_merge_event_bytes as _replay_merge_event_bytes,
)
from ._chain_batch_carrier import _prevalidate_chain_batch_carrier as _prevalidate_chain_batch_carrier, _coordination_refusal as _coordination_refusal, _validate_chain_batch_target as _validate_chain_batch_target, _drain_chain_batch_capability as _drain_chain_batch_capability
from ._activation import _ChainActivationSnapshot as _ChainActivationSnapshot, _resolve_chain_activation_snapshot as _resolve_chain_activation_snapshot, _chain_activation_ownership_summary as _chain_activation_ownership_summary, _validate_chain_activation_lineage as _validate_chain_activation_lineage
from ._storage import (
    _ChainStoragePrimitives as _ChainStoragePrimitives,
)
from ._activation_outbox import (
    _resolve_chain_activation_projection as _resolve_chain_activation_projection,
    _require_no_pending_chain_activation_outbox as _require_no_pending_chain_activation_outbox,
    _prepare_merge_activation_preamble as _prepare_merge_activation_preamble,
)
from ._chain_batch_authorize import (
    _authorize_chain_batch as _authorize_chain_batch,
)
from ._commit_chain import (
    CLIOptions as CLIOptions,
    register_activation_reservation_seam as register_activation_reservation_seam,
    _validate_bound_chain_state as _validate_bound_chain_state,
    _user_skip as _user_skip,
    _gate_one_complete as _gate_one_complete,
    _latest_current_pass as _latest_current_pass,
    _gate_satisfied as _gate_satisfied,
    _verify_and_build_ingest_records as _verify_and_build_ingest_records,
    _ingest_proof_verifier as _ingest_proof_verifier,
    register_coordination_seams as register_coordination_seams,
    _chain_batch_lock as _chain_batch_lock,
    ChainStore as ChainStore,
    CommandContext as CommandContext,
    _policy_for_state as _policy_for_state,
    _fresh_reviewer_evals_required as _fresh_reviewer_evals_required,
    _required_steps as _required_steps,
)
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


def _build_merge_chain_journal_records(
    repository: Path,
    event: dict[str, Any],
    prior: dict[str, Any] | None,
    current: dict[str, Any],
    source_event_digest: str,
) -> tuple[dict[str, Any], ...]:
    """Build live merge rows through the retrospective ingest templates."""

    binding = current.get("run_binding")
    if not isinstance(binding, Mapping):
        return ()
    _require_merge_store_control("typed-journal-builders")
    _require_merge_store_control("consequential-event-set")
    if MERGE_CONSEQUENTIAL_EVENTS != {
        "gate_recorded",
        "review_attached",
        "approval_recorded",
        "generation_carried_forward",
        "push_observed",
    }:
        raise FrozenError(
            "merge consequential event authority is unavailable",
            chain_id=str(current.get("chain_id") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    run_id = str(binding["run_id"])
    task_id = str(binding["task_id"])
    batch, builders, journal = runtime._coordination_modules()
    _canonical_repository, state_root = journal._resolve_repository(
        repository, "journal batch"
    )
    run_dir = state_root / ".codex-orchestrator" / "runs" / run_id
    run_state = journal._scan_run(run_dir)
    task_records = [
        record
        for record in run_state.records
        if record.get("type") == "task" and record.get("id") == task_id
    ]
    if not task_records or task_records[-1].get("status") != "active":
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)

    introduced = _merge_gate_event_fact(prior, current)
    if (
        introduced is not None
        and isinstance(introduced[1], Mapping)
        and isinstance(introduced[1].get("gate_plan_position"), Mapping)
        and introduced[1]["gate_plan_position"].get("kind") == "scoped-mutation"
    ):
        return ()
    required_gate_ids = frozenset(
        {introduced[0]} if introduced is not None else set()
    )
    templates = _merge_ingest_record_templates(
        builders,
        journal,
        event,
        prior,
        current,
        task=task_id,
        approval_required=bool(
            isinstance(current.get("tier"), Mapping)
            and current["tier"].get("control") is True
        ),
        required_gate_ids=required_gate_ids,
    )
    if templates and event.get("event") not in MERGE_CONSEQUENTIAL_EVENTS:
        raise FrozenError(
            "non-consequential merge event attempted to carry journal records",
            chain_id=str(current.get("chain_id") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if not templates:
        return ()
    activation_preamble = (
        ()
        if journal._writer_contract_active(run_state.records)
        else _prepare_merge_activation_preamble(
            _canonical_repository, run_state
        )
    )
    projected = [*run_state.records, *activation_preamble]
    records: list[dict[str, Any]] = []
    review_binding = builders._review_binding_for_state(current)
    for template, _gate_id in templates:
        record = copy.deepcopy(template)
        record_type = str(record["type"])
        record["id"] = builders._allocate_id(projected, record_type)
        record["run_id"] = run_id
        record["recorded_at"] = event["at"]
        record["binding"] = _merge_ingest_binding(
            builders,
            current,
            source_event_digest,
            (
                review_binding
                if record.get("criterion") == journal.GATE_3_CRITERION
                else None
            ),
        )
        evidence = record.get("evidence")
        if isinstance(evidence, list):
            for citation in evidence:
                if (
                    not isinstance(citation, str)
                    or _parsed_run_captured_path(citation, run_id) is None
                ):
                    raise journal.CoordinationRefusal(
                        journal.INVALID_JOURNAL_RECORD
                    )
        records.append(record)
        projected.append(record)
    carried_records = (*activation_preamble, *records)
    batch._prevalidate_records(
        _canonical_repository,
        run_state,
        carried_records,
        close=False,
        defer_binding=True,
    )
    return carried_records


def _new_merge_record_is_current(
    builders: Any,
    state: dict[str, Any],
    binding: dict[str, Any],
    record: dict[str, Any],
    source_event: dict[str, Any],
    source_prior: dict[str, Any] | None,
    source_state: dict[str, Any],
    replay_entries: Sequence[
        tuple[
            dict[str, Any],
            dict[str, Any] | None,
            dict[str, Any],
            tuple[dict[str, Any], ...],
            str | None,
        ]
    ],
) -> bool:
    """Apply currentness only to the newly proposed carried merge fact."""

    if builders._binding_is_current(
        state,
        binding,
        record,
        source_event,
        source_prior,
        source_state,
        replay_entries,
        chain_family="merge",
    ):
        return True
    return bool(
        record.get("type") == "decision"
        and record.get("outcome") == "chain-landing"
        and state.get("state") == "pushed"
        and builders._merge_current_head_contained(state)
        and builders._binding_matches_source_fact(
            binding,
            record,
            source_event,
            source_prior,
            source_state,
            family="merge",
        )
    )


class MergeChainStore(_ChainStoragePrimitives):
    """DM-014 delta log with lease-owned event-first materialization."""

    _TRANSITION_CONTROLS = (
        "lease-tail-authentication",
        "nonrecursive-source-digest",
        "typed-journal-builders",
        "projected-journal-outbox",
        "builder-transition-validation",
        "event-before-state",
        "post-serialization-journal-drain",
    )

    @staticmethod
    def _session(value: str | None) -> str:
        selected = (
            value
            or os.environ.get("CLAUDE_SESSION_ID")
            or os.environ.get("FORGE_SESSION_PID")
            or f"forge-merge-store-{os.getpid()}"
        )
        if not selected or "\x00" in selected:
            raise ValueError("merge store session must be nonempty and NUL-free")
        return selected

    @contextlib.contextmanager
    def _journal_outer(
        self, binding: Mapping[str, Any] | None, *, create: bool = True
    ) -> Iterable[None]:
        if not isinstance(binding, Mapping):
            yield
            return
        register_coordination_seams()
        batch, _builders, journal = runtime._coordination_modules()
        run_dir = (
            self.common_root
            / ".codex-orchestrator"
            / "runs"
            / str(binding["run_id"])
        )
        try:
            with _chain_batch_lock(
                run_dir,
                Path(str(binding["repository"])),
                str(binding["run_id"]),
                create=create,
            ):
                yield
        except journal.CoordinationRefusal as exc:
            raise _coordination_refusal(exc) from exc

    def _read_replay_locked(
        self, chain_id: str, *, verify_receipts: bool = True
    ) -> MergeReplayResult:
        try:
            raw = self._read_root_bytes(self.events_path(chain_id).name)
        except FileNotFoundError as exc:
            raise FrozenError(
                "merge event log is missing",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        except OSError as exc:
            raise FrozenError(
                "merge event log is unreadable",
                chain_id=chain_id,
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        return _replay_merge_event_bytes(
            chain_id, raw, verify_receipts=verify_receipts
        )

    def _projection_status(
        self, replay: MergeReplayResult
    ) -> tuple[str, bytes | None]:
        state_name = self.state_path(str(replay.state["chain_id"])).name
        try:
            raw = self._read_root_bytes(state_name)
        except FileNotFoundError:
            return "missing", None
        except OSError as exc:
            raise FrozenError(
                "merge materialized state is unreadable",
                chain_id=str(replay.state["chain_id"]),
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        final = canonical_bytes(replay.state) + b"\n"
        if raw == final:
            return "current", raw
        if raw in replay.prefix_state_bytes[:-1]:
            return "stale", raw
        raise FrozenError(
            "merge materialized state contradicts authenticated event replay",
            chain_id=str(replay.state["chain_id"]),
            observed=sha256_bytes(raw),
            schema=REVISION9_OUTPUT_SCHEMA,
        )

    def _resolve_replayed_projection(
        self, replay: MergeReplayResult
    ) -> dict[str, Any]:
        binding = replay.state.get("run_binding")
        if _merge_history_uses_additive_grammar(replay.events):
            if isinstance(binding, Mapping):
                try:
                    snapshot = _prove_merge_run_task_binding(
                        Path(str(binding["repository"])),
                        self.common_root,
                        str(binding["run_id"]),
                        str(binding["task_id"]),
                        str(binding["policy_digest"]),
                    )
                except (KeyError, OSError, Refusal, ValueError) as exc:
                    raise FrozenError(
                        "merge binding authority replay failed",
                        chain_id=str(replay.state["chain_id"]),
                        observed=str(exc),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    ) from exc
                if snapshot.binding != dict(binding):
                    raise FrozenError(
                        "merge binding authority replay changed",
                        chain_id=str(replay.state["chain_id"]),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
            return copy.deepcopy(replay.state)
        register_coordination_seams()
        _batch, builders, journal = runtime._coordination_modules()
        try:
            with self.root_descriptor() as root:
                root_observation = journal._file_observation(os.fstat(root))
                authoritative = builders._resolve_binding_from_descriptor(
                    Path(
                        str(
                            binding["repository"]
                            if isinstance(binding, Mapping)
                            else replay.state["repository"]
                        )
                    ),
                    root,
                    str(replay.state["chain_id"]),
                    ZERO_DIGEST,
                    expected_type=None,
                    expected_fields=None,
                    expected_run_id=None,
                    expected_task_id=None,
                    replay_only=True,
                    allow_pending=True,
                )
                if (
                    authoritative != replay.state
                    or journal._file_observation(os.fstat(root))
                    != root_observation
                ):
                    raise ValueError("authoritative merge replay changed")
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            RuntimeError,
            journal.CoordinationRefusal,
        ) as exc:
            raise FrozenError(
                "merge binding authority replay failed",
                chain_id=str(replay.state["chain_id"]),
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        return copy.deepcopy(replay.state)

    def _load_with_outer(
        self, chain_id: str, *, session: str | None
    ) -> dict[str, Any]:
        with self.event_lock(chain_id):
            replay = self._read_replay_locked(chain_id)
            projection_status, _raw = self._projection_status(replay)
        if projection_status != "current":
            _require_merge_store_control("replay-projection-repair")
            lease = acquire_chain_lease(
                self.root,
                chain_id=chain_id,
                session=self._session(session),
            )
            try:
                with self.event_lock(chain_id):
                    replay = self._read_replay_locked(chain_id)
                    projection_status, _raw = self._projection_status(replay)
                    if projection_status != "current":
                        lease.before_state_replace()
                        self._atomic_state(replay.state)
                        self._boundary("merge-replay-state-replaced")
            finally:
                lease.release()
        with self.event_lock(chain_id):
            replay = self._read_replay_locked(chain_id)
            if self._projection_status(replay)[0] != "current":
                raise FrozenError(
                    "merge projection did not stabilize after replay repair",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            state = self._resolve_replayed_projection(replay)
            self._remember_version(
                state, replay.tail_sequence, replay.tail_digest
            )
            return state

    def load(
        self, chain_id: str, *, session: str | None = None
    ) -> dict[str, Any]:
        self._validate_id(chain_id)
        if self.chain_family(chain_id) != "merge":
            raise FrozenError(
                "merge store refused a commit-family chain",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        with self.event_lock(chain_id):
            preliminary = self._read_replay_locked(
                chain_id, verify_receipts=False
            )
        binding = preliminary.state.get("run_binding")
        with self._journal_outer(
            binding if isinstance(binding, Mapping) else None,
            create=False,
        ):
            return self._load_with_outer(chain_id, session=session)

    def _prepare_event(
        self,
        replay: MergeReplayResult | None,
        *,
        chain_id: str,
        event_name: str,
        generation_digest: str | None,
        payload: Mapping[str, Any],
        at: str,
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        tuple[dict[str, Any], ...],
        dict[str, Any] | None,
    ]:
        _require_merge_store_control("nonrecursive-source-digest")
        if event_name not in MERGE_EVENT_NAMES or event_name == "journal_receipted":
            raise ValueError("public merge transition event is invalid")
        if "source_event_digest" in payload or "journal_batch" in payload:
            raise ValueError("merge journal carrier members are store-owned")
        previous_state = replay.state if replay is not None else None
        sequence = replay.tail_sequence + 1 if replay is not None else 1
        previous_digest = replay.tail_digest if replay is not None else ZERO_DIGEST
        unsigned_source: dict[str, Any] = {
            "schema": "forge-merge-event/1",
            "chain_id": chain_id,
            "sequence": sequence,
            "at": at,
            "event": event_name,
            "generation_digest": generation_digest,
            "previous_digest": previous_digest,
            "payload": copy.deepcopy(dict(payload)),
        }
        source_event_digest = sha256_bytes(canonical_bytes(unsigned_source))
        provisional_event = {
            **copy.deepcopy(unsigned_source),
            "digest": source_event_digest,
        }
        try:
            provisional_state = reduce_merge_event(
                copy.deepcopy(previous_state), copy.deepcopy(provisional_event)
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            raise FrozenError(
                "proposed merge delta cannot be reduced",
                chain_id=chain_id,
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        records = _build_merge_chain_journal_records(
            Path(str(provisional_state.get("repository"))),
            provisional_event,
            copy.deepcopy(previous_state),
            provisional_state,
            source_event_digest,
        )
        final_payload = copy.deepcopy(dict(payload))
        pending_outbox: dict[str, Any] | None = None
        if records:
            _require_merge_store_control("projected-journal-outbox")
            _batch, _builders, journal = runtime._coordination_modules()
            batch_bytes = b"".join(journal._journal_line(record) for record in records)
            batch_digest = sha256_bytes(batch_bytes)
            final_payload.update(
                {
                    "source_event_digest": source_event_digest,
                    "journal_batch": {
                        "idempotency_key": source_event_digest,
                        "batch_digest": batch_digest,
                        "record_count": len(records),
                        "records": copy.deepcopy(list(records)),
                    },
                }
            )
            pending_outbox = {
                "idempotency_key": source_event_digest,
                "batch_digest": batch_digest,
                "record_count": len(records),
                "source_event_digest": source_event_digest,
            }
        unsigned_outer = {**unsigned_source, "payload": final_payload}
        event = {
            **unsigned_outer,
            "digest": sha256_bytes(canonical_bytes(unsigned_outer)),
        }
        try:
            current = reduce_merge_event(
                copy.deepcopy(previous_state), copy.deepcopy(event)
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            raise FrozenError(
                "proposed merge carrier cannot be reduced",
                chain_id=chain_id,
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        _require_merge_store_control("builder-transition-validation")
        _batch, builders, _journal = runtime._coordination_modules()
        validation_context = (
            copy.deepcopy(replay.context) if replay is not None else {}
        )
        if not _merge_state_shape_valid(builders, current, chain_id) or not (
            _merge_transition_valid(
                builders,
                event,
                copy.deepcopy(previous_state),
                current,
                context=validation_context,
                history=(replay.events if replay is not None else ()),
            )
        ):
            raise FrozenError(
                "proposed merge transition is not admitted by DM-014",
                chain_id=chain_id,
                state=str(current.get("state")),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if bool(records) != bool(pending_outbox):
            raise FrozenError(
                "merge journal outbox projection is inconsistent",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if records:
            replay_entries = tuple(replay.entries if replay is not None else ()) + (
                (
                    copy.deepcopy(event),
                    copy.deepcopy(previous_state),
                    copy.deepcopy(current),
                    tuple(copy.deepcopy(records)),
                    source_event_digest,
                ),
            )
            activation_preamble = (
                records[:1]
                if records
                and _journal._writer_activation_candidate(records[0])
                else ()
            )
            for record in records[len(activation_preamble) :]:
                record_binding = record.get("binding")
                if (
                    not isinstance(record_binding, dict)
                    or not builders._binding_matches_source_fact(
                        record_binding,
                        record,
                        event,
                        copy.deepcopy(previous_state),
                        current,
                        family="merge",
                    )
                    or not _new_merge_record_is_current(
                        builders,
                        current,
                        record_binding,
                        record,
                        event,
                        copy.deepcopy(previous_state),
                        current,
                        replay_entries,
                    )
                ):
                    raise FrozenError(
                        "new merge journal binding is not current",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
        return event, current, records, pending_outbox

    def _write_transition_with_outer(
        self,
        snapshot: dict[str, Any] | None,
        *,
        chain_id: str,
        event_name: str,
        generation_digest: str | None,
        payload: Mapping[str, Any],
        at: str,
        session: str | None,
        initial: bool,
        drain: bool,
        lease: ChainLease | None = None,
    ) -> dict[str, Any]:
        for control in self._TRANSITION_CONTROLS:
            _require_merge_store_control(control)
        self.ensure_root()
        owned_lease = lease is None
        active_lease = lease or acquire_chain_lease(
            self.root,
            chain_id=chain_id,
            session=self._session(session),
        )
        if active_lease.chain_id != chain_id:
            raise FrozenError(
                "merge transition lease names another chain",
                chain_id=chain_id,
                observed=active_lease.chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        exclusion = getattr(active_lease, "_exclusion", None)
        event_lock_arguments: dict[str, Any] = {}
        if isinstance(exclusion, RecoveryReservation):
            event_lock_arguments = {
                "deadline": exclusion.deadline,
                "clock": exclusion.clock,
                "sleeper": exclusion.sleeper,
            }
        records: tuple[dict[str, Any], ...] = ()
        pending_outbox: dict[str, Any] | None = None
        try:
            with self.event_lock(chain_id, **event_lock_arguments):
                replay: MergeReplayResult | None = None
                if initial:
                    if self._root_entry_exists(
                        self.events_path(chain_id).name
                    ) or self._root_entry_exists(self.state_path(chain_id).name):
                        raise FrozenError(
                            "generated merge chain identity already exists",
                            chain_id=chain_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                else:
                    replay = self._read_replay_locked(chain_id)
                    if snapshot is None:
                        raise ValueError("merge transition requires a loaded snapshot")
                    _require_merge_store_control("lease-tail-authentication")
                    self._require_tail_version(
                        snapshot,
                        replay.tail_sequence,
                        replay.tail_digest,
                        family="merge",
                        refusal_chain=replay.state,
                    )
                    if canonical_bytes(snapshot) != canonical_bytes(replay.state):
                        raise FrozenError(
                            "merge transition snapshot contradicts event replay",
                            chain_id=chain_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    if replay.state.get("journal_outbox") is not None:
                        raise Refusal(
                            V2ReasonCode.JOURNAL_OUTBOX_PENDING,
                            "forge: merge transition refused — journal outbox is pending",
                            remediation=f"forge status --chain-id {chain_id}",
                            chain=replay.state,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                event, current, records, pending_outbox = self._prepare_event(
                    replay,
                    chain_id=chain_id,
                    event_name=event_name,
                    generation_digest=generation_digest,
                    payload=payload,
                    at=at,
                )
                _require_merge_store_control("event-before-state")
                active_lease.before_event_append()
                self._append_event_bytes(
                    chain_id,
                    canonical_bytes(event) + b"\n",
                    initial=initial,
                )
                self._boundary("merge-event-appended")
                active_lease.before_state_replace()
                self._atomic_state(current)
                self._boundary("merge-state-replaced")
                with self.root_descriptor() as root:
                    os.fsync(root)
                self._boundary("merge-directory-fsynced")
                self._remember_version(
                    current,
                    int(event["sequence"]),
                    str(event["digest"]),
                )
        finally:
            if owned_lease:
                active_lease.release()
                self._boundary("merge-chain-serialization-released")
        if pending_outbox is not None and drain:
            _require_merge_store_control("post-serialization-journal-drain")
            receipt = _drain_chain_batch_capability(
                current,
                pending_outbox,
                records,
            )
            self._boundary("merge-journal-drained")
            return self._append_receipt_with_outer(
                current,
                receipt,
                session=session,
                lease=lease,
            )
        return current

    def _append_receipt_with_outer(
        self,
        snapshot: dict[str, Any],
        receipt: Mapping[str, Any],
        *,
        session: str | None,
        lease: ChainLease | None = None,
    ) -> dict[str, Any]:
        for control in (
            "lease-tail-authentication",
            "builder-transition-validation",
            "event-before-state",
        ):
            _require_merge_store_control(control)
        chain_id = str(snapshot["chain_id"])
        if set(receipt) != {
            "idempotency_key",
            "batch_digest",
            "receipt_digest",
        }:
            raise FrozenError(
                "merge journal receipt is malformed",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        owned_lease = lease is None
        active_lease = lease or acquire_chain_lease(
            self.root,
            chain_id=chain_id,
            session=self._session(session),
        )
        if active_lease.chain_id != chain_id:
            raise FrozenError(
                "merge receipt lease names another chain",
                chain_id=chain_id,
                observed=active_lease.chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        exclusion = getattr(active_lease, "_exclusion", None)
        event_lock_arguments: dict[str, Any] = {}
        if isinstance(exclusion, RecoveryReservation):
            event_lock_arguments = {
                "deadline": exclusion.deadline,
                "clock": exclusion.clock,
                "sleeper": exclusion.sleeper,
            }
        try:
            with self.event_lock(chain_id, **event_lock_arguments):
                replay = self._read_replay_locked(chain_id)
                self._require_tail_version(
                    snapshot,
                    replay.tail_sequence,
                    replay.tail_digest,
                    family="merge",
                    refusal_chain=replay.state,
                )
                pending = replay.state.get("journal_outbox")
                if not isinstance(pending, dict) or (
                    receipt.get("idempotency_key")
                    != pending.get("idempotency_key")
                    or receipt.get("batch_digest") != pending.get("batch_digest")
                ):
                    raise FrozenError(
                        "merge journal receipt does not match pending outbox",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                unsigned = {
                    "schema": "forge-merge-event/1",
                    "chain_id": chain_id,
                    "sequence": replay.tail_sequence + 1,
                    "at": iso_z(),
                    "event": "journal_receipted",
                    "generation_digest": (
                        replay.state.get("candidate", {}).get("generation_digest")
                        if isinstance(replay.state.get("candidate"), dict)
                        else None
                    ),
                    "previous_digest": replay.tail_digest,
                    "payload": copy.deepcopy(dict(receipt)),
                }
                event = {
                    **unsigned,
                    "digest": sha256_bytes(canonical_bytes(unsigned)),
                }
                current = reduce_merge_event(
                    copy.deepcopy(replay.state), copy.deepcopy(event)
                )
                _batch, builders, _journal = runtime._coordination_modules()
                context = copy.deepcopy(replay.context)
                if not _merge_state_shape_valid(
                    builders, current, chain_id
                ) or not _merge_transition_valid(
                    builders,
                    event,
                    replay.state,
                    current,
                    context=context,
                    history=replay.events,
                ):
                    raise FrozenError(
                        "merge journal receipt transition is invalid",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                active_lease.before_event_append()
                self._append_event_bytes(
                    chain_id, canonical_bytes(event) + b"\n", initial=False
                )
                self._boundary("merge-receipt-appended")
                active_lease.before_state_replace()
                self._atomic_state(current)
                self._boundary("merge-receipt-state-replaced")
                self._remember_version(
                    current,
                    int(event["sequence"]),
                    str(event["digest"]),
                )
        finally:
            if owned_lease:
                active_lease.release()
        return current

    def create(
        self,
        initial_delta: Mapping[str, Any],
        *,
        at: str | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        chain_id = str(initial_delta.get("chain_id", ""))
        self._validate_id(chain_id)
        binding = initial_delta.get("run_binding")
        with self._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ):
            return self._write_transition_with_outer(
                None,
                chain_id=chain_id,
                event_name="chain_started",
                generation_digest=None,
                payload={"delta": copy.deepcopy(dict(initial_delta))},
                at=at or iso_z(),
                session=session,
                initial=True,
                drain=True,
            )

    def transition(
        self,
        snapshot: dict[str, Any],
        event_name: str,
        payload: Mapping[str, Any],
        *,
        generation_digest: str | None,
        at: str | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        validate_merge_state(snapshot, str(snapshot.get("chain_id", "")))
        chain_id = str(snapshot["chain_id"])
        if self.chain_family(chain_id) != "merge":
            raise FrozenError(
                "merge transition routed to a non-merge family",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        binding = snapshot.get("run_binding")
        with self._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ):
            return self._write_transition_with_outer(
                snapshot,
                chain_id=chain_id,
                event_name=event_name,
                generation_digest=generation_digest,
                payload=payload,
                at=at or iso_z(),
                session=session,
                initial=False,
                drain=True,
            )

    def transition_locked(
        self,
        snapshot: dict[str, Any],
        event_name: str,
        payload: Mapping[str, Any],
        *,
        generation_digest: str | None,
        lease: ChainLease,
        at: str | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        """Append while an outer journal/common-lock/chain-lease epoch is held."""

        validate_merge_state(snapshot, str(snapshot.get("chain_id", "")))
        chain_id = str(snapshot["chain_id"])
        if self.chain_family(chain_id) != "merge":
            raise FrozenError(
                "merge transition routed to a non-merge family",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return self._write_transition_with_outer(
            snapshot,
            chain_id=chain_id,
            event_name=event_name,
            generation_digest=generation_digest,
            payload=payload,
            at=at or iso_z(),
            session=session,
            initial=False,
            drain=True,
            lease=lease,
        )

    def load_locked(self, chain_id: str, *, lease: ChainLease) -> dict[str, Any]:
        """Re-read one current projection while its external lease is owned."""

        self._validate_id(chain_id)
        if lease.chain_id != chain_id or self.chain_family(chain_id) != "merge":
            raise FrozenError(
                "merge locked load has a mismatched family or lease",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        lease._revalidate("locked-load")
        exclusion = getattr(lease, "_exclusion", None)
        event_lock_arguments: dict[str, Any] = {}
        if isinstance(exclusion, RecoveryReservation):
            event_lock_arguments = {
                "deadline": exclusion.deadline,
                "clock": exclusion.clock,
                "sleeper": exclusion.sleeper,
            }
        with self.event_lock(chain_id, **event_lock_arguments):
            replay = self._read_replay_locked(chain_id)
            if self._projection_status(replay)[0] != "current":
                raise FrozenError(
                    "merge projection is stale inside a locked epoch",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            state = self._resolve_replayed_projection(replay)
            self._remember_version(state, replay.tail_sequence, replay.tail_digest)
            return state

    def recover_pending_outbox(
        self, chain_id: str, *, session: str | None = None
    ) -> dict[str, Any]:
        _require_merge_store_control("post-serialization-journal-drain")
        self._validate_id(chain_id)
        if self.chain_family(chain_id) != "merge":
            raise FrozenError(
                "merge outbox recovery routed to a non-merge family",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        with self.event_lock(chain_id):
            preliminary = self._read_replay_locked(
                chain_id, verify_receipts=False
            )
        binding = preliminary.state.get("run_binding")
        if not isinstance(binding, Mapping):
            raise FrozenError(
                "pending merge outbox lacks an immutable run binding",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        with self._journal_outer(binding):
            state = self._load_with_outer(chain_id, session=session)
            pending = state.get("journal_outbox")
            if pending is None:
                return state
            with self.event_lock(chain_id):
                replay = self._read_replay_locked(chain_id)
                carrier = replay.entries[-1]
                records = carrier[3]
                if (
                    not records
                    or carrier[4] != pending.get("source_event_digest")
                ):
                    raise FrozenError(
                        "pending merge outbox lacks its exact carried batch",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
            receipt = _drain_chain_batch_capability(state, pending, records)
            self._boundary("merge-journal-drained")
            return self._append_receipt_with_outer(
                state,
                receipt,
                session=session,
            )


def _fence_death_proof(
    fence: PublishedLockRecord,
    *,
    group_dead_at: str,
) -> dict[str, Any]:
    return {
        "schema": "forge-rebase-fence-death/1",
        "operation": fence.record["operation"],
        "intent_digest": fence.record["intent_digest"],
        "fence_digest": fence.digest,
        "host": fence.record["host"],
        "pgid": fence.record["pgid"],
        "group_dead_at": group_dead_at,
    }


def _require_recovery_proof_recorder(
    owner_kinds: Sequence[str],
    recorder: Callable[[dict[str, Any]], Any] | None,
    *,
    no_transaction_record: bool,
) -> None:
    _require_common_lock_control("death-proof-revalidation")
    if (
        recorder is None
        and not no_transaction_record
        and any(kind in {"merge", "push"} for kind in owner_kinds)
    ):
        raise OSError(
            "common-lock recovery recorder is required before proof-dependent unlink"
        )


def _persist_recovery_proof(
    proof: Mapping[str, Any],
    recorder: Callable[[dict[str, Any]], Any] | None,
    *,
    owner_kinds: Sequence[str],
    no_transaction_record: bool,
    proof_already_persisted: bool = False,
) -> None:
    _require_recovery_proof_recorder(
        owner_kinds,
        recorder,
        no_transaction_record=no_transaction_record,
    )
    if proof_already_persisted or recorder is None:
        return
    recorder(copy.deepcopy(dict(proof)))


def _recovery_classification_receipt_valid(
    value: object,
    *,
    reservation: RecoveryReservation,
    fence: PublishedLockRecord | None,
) -> bool:
    """Validate the exact receipt returned by transactional classification."""

    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "chain_id",
        "chain_store",
        "reservation_digest",
        "fence_digest",
        "proof_digest",
        "event_digest",
    }:
        return False
    try:
        selected_chain = reservation.affected_merge_chain()
    except OSError:
        return False
    fields_valid = bool(
        value.get("schema") == "forge-merge-fence-recovery-receipt/1"
        and value.get("chain_id") == selected_chain
        and isinstance(value.get("chain_store"), str)
        and os.path.isabs(str(value.get("chain_store")))
        and value.get("reservation_digest") == reservation.identity.digest
        and value.get("fence_digest")
        == (fence.digest if fence is not None else None)
        and SHA256_RE.fullmatch(str(value.get("proof_digest", ""))) is not None
        and SHA256_RE.fullmatch(str(value.get("event_digest", ""))) is not None
    )
    if not fields_valid:
        return False
    try:
        chain_store = Path(str(value["chain_store"]))
        store = MergeChainStore(chain_store.parent.parent)
        if Path(os.path.realpath(store.root)) != Path(
            os.path.realpath(chain_store)
        ):
            return False
        reservation.assert_current(
            "reservation-held recovery receipt validation"
        )
        with store.event_lock(
            selected_chain,
            deadline=reservation.deadline,
            clock=reservation.clock,
            sleeper=reservation.sleeper,
        ):
            replay = store._read_replay_locked(selected_chain)
        if replay.tail_digest != value.get("event_digest") or not replay.events:
            return False
        retained_event = replay.events[-1]
        retained_payload = retained_event.get("payload")
        retained_proof = (
            retained_payload.get("recovery_proof")
            if isinstance(retained_payload, Mapping)
            else None
        )
        return bool(
            retained_event.get("event") == "condition_recorded"
            and retained_event.get("digest") == value.get("event_digest")
            and isinstance(retained_proof, Mapping)
            and retained_proof.get("digest") == value.get("proof_digest")
            and retained_proof.get("chain_id") == selected_chain
            and retained_proof.get("reservation")
            == reservation.identity.evidence()
            and retained_proof.get("fence")
            == (fence.evidence() if fence is not None else None)
        )
    except (FrozenError, OSError, ValueError):
        return False


class CommonRebaseLock:
    """One long-lived FR-235 portable owner and optional secondary flock."""

    def __init__(
        self,
        *,
        common_dir: Path,
        common_descriptor: int,
        owner: PublishedLockRecord,
        flock_descriptor: int | None,
        flock_impl: Callable[[int, int], Any],
        boundary: Callable[[str], None] | None,
        deadline: float,
        clock: Callable[[], float],
        sleeper: Callable[[float], None],
        pid_probe: Callable[[int], str],
        group_probe: Callable[[int], str],
        recovery_recorder: Callable[[dict[str, Any]], Any] | None,
        no_transaction_record: bool,
    ) -> None:
        self.common_dir = common_dir
        self._common = common_descriptor
        self.owner = owner
        self._flock = flock_descriptor
        self._flock_impl = flock_impl
        self._boundary = boundary
        self.deadline = deadline
        self._clock = clock
        self._sleeper = sleeper
        self._pid_probe = pid_probe
        self._group_probe = group_probe
        self._recovery_recorder = recovery_recorder
        self._no_transaction_record = no_transaction_record
        self._flock_released = flock_descriptor is None
        self._released = False
        self._release_pending = False
        self._unresolved_fence: PublishedLockRecord | None = None

    @property
    def record(self) -> dict[str, Any]:
        return copy.deepcopy(self.owner.record)

    @property
    def digest(self) -> str:
        return self.owner.digest

    @property
    def released(self) -> bool:
        return self._released

    def _emit_boundary(self, stage: str) -> None:
        if self._boundary is not None:
            self._boundary(stage)

    def assert_held(self, *, allow_fence: bool = False) -> None:
        if self._released or self._common < 0:
            raise OSError("common rebase lock is already released")
        if self._release_pending:
            raise OSError("common rebase lock admits release recovery only")
        inspection = _inspect_common_lock_fd(self._common, self.common_dir)
        if (
            inspection.topology != "complete"
            or inspection.outer is None
            or not _same_published_record(inspection.outer, self.owner)
        ):
            raise OSError("common rebase lock portable identity changed")
        if not self._flock_released and self._flock is None:
            raise OSError("common rebase lock lost its secondary flock descriptor")
        if _reservation_evidence(self._common, self.common_dir) is not None:
            raise OSError("common rebase lock has an unresolved recovery reservation")
        fence_present = _common_fence_path_present(self._common)
        if fence_present and not allow_fence:
            raise OSError("common rebase lock has an unresolved in-flight fence")

    def recover_owned_fence(
        self,
        fence: PublishedLockRecord,
        *,
        persist_proof: Callable[[dict[str, Any]], Any] | None = None,
        lifecycle_classifier: (
            Callable[[RecoveryReservation, PublishedLockRecord | None], Any] | None
        ) = None,
    ) -> None:
        """Classify and release a proven-dead fence under one reservation."""

        release_was_pending = self._release_pending
        if release_was_pending:
            # This method is itself the sole admitted release-recovery step.
            self._release_pending = False
        try:
            self.assert_held(allow_fence=True)
        finally:
            self._release_pending = release_was_pending
        current = _revalidate_record_at(
            self._common,
            COMMON_LOCK_INFLIGHT_NAME,
            self.common_dir / COMMON_LOCK_INFLIGHT_NAME,
            fence,
            _validate_fence_record,
        )
        if current.record.get("host") != self.owner.record.get("host"):
            raise OSError("in-flight fence host is not local")
        if not _fence_matches_owner(current, self.owner):
            raise OSError("in-flight fence does not belong to this common-lock owner")
        if self._group_probe(int(current.record["pgid"])) != "dead":
            raise OSError("in-flight process group is live or unprovable")
        recorder = (
            persist_proof
            if persist_proof is not None
            else self._recovery_recorder
        )
        _require_recovery_proof_recorder(
            (str(current.record["owner_kind"]),),
            recorder,
            no_transaction_record=self._no_transaction_record,
        )
        classifier = lifecycle_classifier
        reservation: RecoveryReservation | None = None
        try:
            reservation = _publish_recovery_reservation(
                self._common,
                self.common_dir,
                _recovery_record(
                    "flock-held-dead-fence",
                    stale_owner=None,
                    inflight=current,
                    host=str(self.owner.record["host"]),
                    pid=int(self.owner.record["pid"]),
                    now=runtime.utc_now,
                ),
                self._boundary,
                deadline=self.deadline,
                clock=self._clock,
                sleeper=self._sleeper,
            )
            if reservation is None:
                raise OSError("another recovery reservation won publication")
            _clear_reserved_fence(
                self._common,
                self.common_dir,
                reservation,
                group_probe=self._group_probe,
                deadline=self.deadline,
                clock=self._clock,
                boundary=self._boundary,
                recovery_recorder=recorder,
                no_transaction_record=self._no_transaction_record,
                lifecycle_classifier=classifier,
            )
            _clear_owned_reservation(
                self._common, self.common_dir, reservation, self._boundary
            )
            reservation = None
            self._unresolved_fence = None
            self._emit_boundary("fence-recovered")
        except BaseException as exc:
            if isinstance(exc, CommonLockBoundaryCrash):
                raise
            if reservation is not None:
                if self._no_transaction_record:
                    try:
                        _clear_owned_reservation(
                            self._common,
                            self.common_dir,
                            reservation,
                            boundary=None,
                        )
                    except (OSError, ValueError):
                        pass
            raise

    def release(self) -> None:
        if self._released:
            return
        evidence = {
            "intent_path": str(self.common_dir / COMMON_LOCK_INTENT_NAME),
            "inode": self.owner.inode,
            "digest": self.owner.digest,
        }
        try:
            if self._unresolved_fence is not None:
                raise OSError("an unresolved fenced process permits only fence recovery")
            if _common_fence_path_present(self._common):
                raise OSError("in-flight fence remains at common-lock release")
            _require_common_lock_control("reverse-release-order")
            if not self._flock_released:
                assert self._flock is not None
                self._flock_impl(self._flock, fcntl.LOCK_UN)
                os.close(self._flock)
                self._flock = None
                self._flock_released = True
                self._emit_boundary("release-flock")
            _release_portable_identity(
                self._common,
                self.common_dir,
                self.owner,
                boundary=self._boundary,
                prefix="release",
                complete_partial=False,
            )
            self._released = True
            self._release_pending = False
            os.close(self._common)
            self._common = -1
        except BaseException as exc:
            if isinstance(exc, CommonLockBoundaryCrash):
                raise
            self._release_pending = True
            evidence["error"] = str(exc)
            evidence["flock_released"] = self._flock_released
            raise CommonLockReleaseFailure(evidence) from exc

    def retry_release(self) -> None:
        """Retry only the recorded reverse-order release after a failure."""

        if not self._release_pending:
            self.release()
            return
        self._release_pending = False
        self.release()

    def __enter__(self) -> "CommonRebaseLock":
        self.assert_held()
        return self

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        self.release()


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


def _read_fence_for_recovery(
    common: int, common_dir: Path
) -> tuple[PublishedLockRecord | None, str | None, dict[str, Any] | None]:
    try:
        return (
            _record_at_if_present(
                common,
                COMMON_LOCK_INFLIGHT_NAME,
                common_dir / COMMON_LOCK_INFLIGHT_NAME,
                _validate_fence_record,
            ),
            None,
            None,
        )
    except (OSError, ValueError) as exc:
        return (
            None,
            str(exc),
            {
                "fence": _opaque_path_evidence_at(
                    common,
                    COMMON_LOCK_INFLIGHT_NAME,
                    common_dir / COMMON_LOCK_INFLIGHT_NAME,
                )
            },
        )


def _common_fence_path_present(common: int) -> bool:
    """Observe only whether the physical fence name exists.

    Revision 12 permits an ordinary contender to notice that the reserved
    name is occupied, but not to open, parse, probe, classify, or clear the
    occupant.  In particular this check runs before portable/flock
    publication so an ordinary refusal is byte preserving for every lock
    artifact.
    """

    try:
        os.stat(
            COMMON_LOCK_INFLIGHT_NAME,
            dir_fd=common,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return False
    return True


def _recover_stale_portable_owner(
    common: int,
    common_dir: Path,
    stale: PublishedLockRecord,
    inflight: PublishedLockRecord | None,
    reservation: RecoveryReservation,
    *,
    pid_probe: Callable[[int], str],
    group_probe: Callable[[int], str],
    deadline: float,
    clock: Callable[[], float],
    boundary: Callable[[str], None] | None,
    recovery_recorder: Callable[[dict[str, Any]], Any] | None,
    no_transaction_record: bool,
    proof_already_persisted: bool = False,
) -> None:
    _require_common_lock_control("death-proof-revalidation")
    reservation.assert_current("stale-owner reservation revalidation")
    canonical_reservation = _revalidate_record_at(
        common,
        COMMON_LOCK_RECOVERY_NAME,
        common_dir / COMMON_LOCK_RECOVERY_NAME,
        reservation.identity,
        _validate_recovery_record,
    )
    inspection = _inspect_common_lock_fd(common, common_dir)
    if (
        not inspection.recoverable
        or inspection.outer is None
        or not _same_published_record(inspection.outer, stale)
    ):
        raise OSError("stale portable owner changed after reservation")
    if pid_probe(int(stale.record["pid"])) != "dead":
        raise OSError("stale portable owner death could not be re-proved")
    _require_deadline_open(deadline, clock, "stale-owner death proof")
    proof = copy.deepcopy(canonical_reservation.record)
    current_inflight: PublishedLockRecord | None = None
    if inflight is not None:
        current_inflight = _revalidate_record_at(
            common,
            COMMON_LOCK_INFLIGHT_NAME,
            common_dir / COMMON_LOCK_INFLIGHT_NAME,
            inflight,
            _validate_fence_record,
        )
        if group_probe(int(current_inflight.record["pgid"])) != "dead":
            raise OSError("in-flight group death could not be re-proved")
        _require_deadline_open(deadline, clock, "in-flight group death proof")
    _persist_recovery_proof(
        proof,
        recovery_recorder,
        owner_kinds=(str(stale.record["owner_kind"]),),
        no_transaction_record=no_transaction_record,
        proof_already_persisted=proof_already_persisted,
    )
    if current_inflight is not None:
        _persist_recovery_proof(
            _fence_death_proof(
                current_inflight,
                group_dead_at=str(canonical_reservation.record["group_dead_at"]),
            ),
            recovery_recorder,
            owner_kinds=(str(current_inflight.record["owner_kind"]),),
            no_transaction_record=no_transaction_record,
            proof_already_persisted=proof_already_persisted,
        )
    if pid_probe(int(stale.record["pid"])) != "dead":
        raise OSError("stale portable owner PID became live or unprovable")
    reservation.assert_current("stale-owner release")
    _release_portable_identity(
        common,
        common_dir,
        stale,
        boundary=boundary,
        prefix="recovery-release",
        complete_partial=True,
    )
    if boundary is not None:
        boundary("recovery-stale-owner-released")


def _clear_reserved_fence(
    common: int,
    common_dir: Path,
    reservation: RecoveryReservation,
    *,
    group_probe: Callable[[int], str],
    deadline: float,
    clock: Callable[[], float],
    boundary: Callable[[str], None] | None,
    recovery_recorder: Callable[[dict[str, Any]], Any] | None,
    no_transaction_record: bool,
    lifecycle_classifier: (
        Callable[[RecoveryReservation, PublishedLockRecord | None], Any] | None
    ),
    classification_already_performed: bool = False,
    proof_already_persisted: bool = False,
) -> None:
    _require_common_lock_control("death-proof-revalidation")
    record = reservation.identity.record
    if record.get("inflight_inode") is None:
        return
    reservation.assert_current("reservation-held fence inspection")
    fence = _read_owned_record_at(
        common,
        COMMON_LOCK_INFLIGHT_NAME,
        common_dir / COMMON_LOCK_INFLIGHT_NAME,
        _validate_fence_record,
    )
    if (
        fence.inode != record["inflight_inode"]
        or fence.digest != record["inflight_digest"]
        or fence.record.get("host") != record["inflight_host"]
        or fence.record.get("pgid") != record["inflight_pgid"]
    ):
        raise OSError("in-flight fence changed after recovery reservation")
    if group_probe(int(fence.record["pgid"])) != "dead":
        raise OSError("in-flight group death could not be re-proved")
    _require_deadline_open(deadline, clock, "in-flight group death proof")
    _require_common_lock_control("reservation-held-lifecycle-classification")
    if not classification_already_performed:
        if lifecycle_classifier is None:
            raise OSError(
                "reservation-held lifecycle classification is required before fence clearing"
            )
        reservation.assert_current(
            "reservation-held lifecycle classification"
        )
        classification_result = lifecycle_classifier(reservation, fence)
        receipt_valid = _recovery_classification_receipt_valid(
            classification_result,
            reservation=reservation,
            fence=fence,
        )
        if not no_transaction_record and not receipt_valid:
            raise OSError(
                "reservation-held lifecycle classification did not return its exact durable receipt"
            )
        if receipt_valid:
            proof_already_persisted = True
    reservation.assert_current("reservation-held fence revalidation")
    _revalidate_record_at(
        common,
        COMMON_LOCK_INFLIGHT_NAME,
        common_dir / COMMON_LOCK_INFLIGHT_NAME,
        fence,
        _validate_fence_record,
    )
    if boundary is not None:
        boundary("recovery-fence-lifecycle-classified")
    if proof_already_persisted:
        _persist_recovery_proof(
            record,
            recovery_recorder,
            owner_kinds=(str(fence.record["owner_kind"]),),
            no_transaction_record=no_transaction_record,
            proof_already_persisted=True,
        )
    else:
        _persist_recovery_proof(
            record,
            recovery_recorder,
            owner_kinds=(str(fence.record["owner_kind"]),),
            no_transaction_record=no_transaction_record,
        )
        _persist_recovery_proof(
            _fence_death_proof(
                fence,
                group_dead_at=str(record["group_dead_at"]),
            ),
            recovery_recorder,
            owner_kinds=(str(fence.record["owner_kind"]),),
            no_transaction_record=no_transaction_record,
        )
    if group_probe(int(fence.record["pgid"])) != "dead":
        raise OSError("in-flight group became live or unprovable")
    reservation.assert_current("in-flight fence release")
    _unlink_revalidated_record_at(
        common,
        COMMON_LOCK_INFLIGHT_NAME,
        common_dir / COMMON_LOCK_INFLIGHT_NAME,
        fence,
        _validate_fence_record,
    )
    os.fsync(common)
    if boundary is not None:
        boundary("recovery-fence-cleared")


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


class ChainLease:
    """FR-237 hard-link lease with mandatory pre-write ABA checks."""

    def __init__(
        self,
        *,
        chains_dir: Path,
        directory_descriptor: int,
        identity: PublishedLockRecord,
        boundary: Callable[[str], None] | None,
        exclusion: CommonRebaseLock | RecoveryReservation | None,
    ) -> None:
        self.chains_dir = chains_dir
        self._directory = directory_descriptor
        self.identity = identity
        self._boundary = boundary
        self._exclusion = exclusion
        self._released = False

    @property
    def record(self) -> dict[str, Any]:
        return copy.deepcopy(self.identity.record)

    @property
    def chain_id(self) -> str:
        return str(self.identity.record["chain_id"])

    @property
    def path(self) -> Path:
        return self.chains_dir / f"{self.chain_id}.lock"

    def _revalidate(self, operation: str) -> None:
        _require_common_lock_control("chain-lease-write-revalidation")
        if self._released or self._directory < 0:
            raise OSError("chain lease is already released")
        if self._exclusion is not None and not _lease_exclusion_is_current(
            self._exclusion, self.chain_id
        ):
            raise OSError(
                "chain lease lost its repository-wide recovery exclusion"
            )
        _revalidate_record_at(
            self._directory,
            self.path.name,
            self.path,
            self.identity,
            _validate_chain_lease_record,
        )
        if self._boundary is not None:
            self._boundary(f"chain-lease-before-{operation}")

    def before_event_append(self) -> None:
        self._revalidate("append")

    def before_state_replace(self) -> None:
        self._revalidate("state-replace")

    def protected_append(self, writer: Callable[[], Any]) -> Any:
        self.before_event_append()
        return writer()

    def protected_state_replace(self, writer: Callable[[], Any]) -> Any:
        self.before_state_replace()
        return writer()

    def release(self) -> None:
        if self._released:
            return
        _require_common_lock_control("chain-lease-write-revalidation")
        try:
            self._revalidate("release")
            _unlink_revalidated_record_at(
                self._directory,
                self.path.name,
                self.path,
                self.identity,
                _validate_chain_lease_record,
            )
            if self._boundary is not None:
                self._boundary("chain-lease-unlinked")
            os.fsync(self._directory)
            if self._boundary is not None:
                self._boundary("chain-lease-parent-fsynced")
            self._released = True
            os.close(self._directory)
            self._directory = -1
        except BaseException:
            raise

    def __enter__(self) -> "ChainLease":
        self._revalidate("use")
        return self

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        self.release()


def _lease_exclusion_is_current(
    exclusion: CommonRebaseLock | RecoveryReservation | None,
    chain_id: str,
) -> bool:
    if isinstance(exclusion, CommonRebaseLock):
        try:
            exclusion.assert_held(allow_fence=True)
        except OSError:
            return False
        owner = exclusion.owner.record
        return owner.get("owner_kind") == "merge" and owner.get("chain_id") == chain_id
    if isinstance(exclusion, RecoveryReservation):
        if not exclusion.matches_chain(chain_id):
            return False
        try:
            exclusion.assert_current("chain lease recovery exclusion")
            return True
        except (OSError, TimeoutError, ValueError):
            return False
    return False


def _lease_reclaim_authority_is_current(
    exclusion: CommonRebaseLock | RecoveryReservation | None,
    chain_id: str,
) -> bool:
    """Require bare-recover authority, not merely an ordinary held lock."""

    if isinstance(exclusion, RecoveryReservation):
        return _lease_exclusion_is_current(exclusion, chain_id)
    if isinstance(exclusion, CommonRebaseLock):
        return bool(
            exclusion.owner.record.get("operation") == "recover"
            and _lease_exclusion_is_current(exclusion, chain_id)
        )
    return False


def _repository_recovery_reservation_present(chains_dir: Path) -> bool:
    """Observe only the repository-wide reservation name from a lease path."""

    try:
        (chains_dir.parent.parent / COMMON_LOCK_RECOVERY_NAME).lstat()
    except FileNotFoundError:
        return False
    return True


def _reconcile_merge_projection_for_lease_reclaim(
    chains_dir: Path,
    chain_id: str,
    *,
    exclusion: CommonRebaseLock | RecoveryReservation,
    repair_with: ChainLease | None,
    deadline: float,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> None:
    """Authenticate event truth and repair only after the new lease exists."""

    events_path = chains_dir / f"{chain_id}.events.jsonl"
    state_path = chains_dir / f"{chain_id}.json"
    try:
        events_path.lstat()
        events_exists = True
    except FileNotFoundError:
        events_exists = False
    try:
        state_path.lstat()
        state_exists = True
    except FileNotFoundError:
        state_exists = False
    if not events_exists and not state_exists:
        # Low-level lock-mechanism tests deliberately have no transaction.
        if (
            isinstance(exclusion, CommonRebaseLock)
            and exclusion._no_transaction_record
        ):
            return
        raise FrozenError(
            "stale merge lease lacks event/state evidence for reconciliation",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    common_root = chains_dir.parent.parent
    store = MergeChainStore(common_root)
    if Path(os.path.realpath(store.root)) != chains_dir:
        raise FrozenError(
            "stale merge lease storage identity is not canonical",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    with store.event_lock(
        chain_id,
        deadline=deadline,
        clock=clock,
        sleeper=sleeper,
    ):
        replay = store._read_replay_locked(chain_id)
        status, _raw = store._projection_status(replay)
        if status not in {"current", "stale", "missing"}:
            raise FrozenError(
                "stale merge lease projection cannot be reconciled",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if repair_with is not None and status != "current":
            repair_with.before_state_replace()
            store._atomic_state(replay.state)
            store._boundary("merge-replay-state-replaced")
            replay = store._read_replay_locked(chain_id)
            if store._projection_status(replay)[0] != "current":
                raise FrozenError(
                    "stale merge lease projection repair did not stabilize",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )


def acquire_chain_lease(
    chains_dir: Path,
    *,
    chain_id: str,
    session: str,
    timeout: float = COMMON_LOCK_TIMEOUT_SECONDS,
    exclusion: CommonRebaseLock | RecoveryReservation | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    now: Callable[[], dt.datetime] = runtime.utc_now,
    host: str | None = None,
    pid: int | None = None,
    pid_probe: Callable[[int], str] = _process_probe,
    boundary: Callable[[str], None] | None = None,
    single_attempt: bool = False,
) -> ChainLease:
    """Acquire one FR-237 lease, reclaiming only under repository exclusion."""

    _require_common_lock_control("chain-lease-hardlink")
    _require_common_lock_control("single-deadline")
    if not CHAIN_ID_RE.fullmatch(chain_id):
        raise ValueError("invalid chain identifier for lease")
    if not isinstance(session, str) or not session or "\x00" in session:
        raise ValueError("chain lease session must be nonempty and NUL-free")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("chain lease timeout must be positive")
    if type(single_attempt) is not bool:
        raise ValueError("chain lease single-attempt selector must be boolean")
    canonical, directory = _open_owned_directory(chains_dir)
    local_host = host or socket.gethostname()
    claimant_pid = pid or os.getpid()
    record = _validate_chain_lease_record(
        {
            "chain_id": chain_id,
            "host": local_host,
            "nonce": secrets.token_hex(16),
            "pid": claimant_pid,
            "session": session,
            "started_at": iso_z(now()),
        }
    )
    path = canonical / f"{chain_id}.lock"
    if isinstance(exclusion, RecoveryReservation):
        if exclusion.affected_merge_chain() != chain_id:
            raise ValueError(
                "recovery reservation does not bind the requested chain lease"
            )
        clock = exclusion.clock
        sleeper = exclusion.sleeper
        deadline = exclusion.deadline
        exclusion.assert_current("chain lease acquisition")
    else:
        deadline = clock() + float(timeout)
    last_evidence: dict[str, Any] = {"path": str(path)}
    reclaimed_stale = False
    try:
        while True:
            if clock() >= deadline:
                raise ChainLeaseUnavailable(chain_id, last_evidence)
            existing: PublishedLockRecord | None
            try:
                existing = _record_at_if_present(
                    directory, path.name, path, _validate_chain_lease_record
                )
            except (OSError, ValueError) as exc:
                existing = None
                last_evidence = {
                    "lease": _opaque_path_evidence_at(directory, path.name, path),
                    "detail": f"lease is malformed or unreadable: {exc}",
                }
                if single_attempt:
                    raise ChainLeaseUnavailable(chain_id, last_evidence) from exc
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise ChainLeaseUnavailable(chain_id, last_evidence)
                continue
            if existing is not None:
                last_evidence = {"lease": existing.evidence()}
                stale = (
                    existing.record.get("host") == local_host
                    and pid_probe(int(existing.record["pid"])) == "dead"
                )
                if stale and _lease_reclaim_authority_is_current(
                    exclusion, chain_id
                ):
                    _require_common_lock_control("death-proof-revalidation")
                    if pid_probe(int(existing.record["pid"])) != "dead":
                        last_evidence["detail"] = "lease PID death could not be re-proved"
                    else:
                        assert exclusion is not None
                        _reconcile_merge_projection_for_lease_reclaim(
                            canonical,
                            chain_id,
                            exclusion=exclusion,
                            repair_with=None,
                            deadline=deadline,
                            clock=clock,
                            sleeper=sleeper,
                        )
                        if not _lease_exclusion_is_current(exclusion, chain_id):
                            raise OSError(
                                "repository exclusion changed during stale lease reconciliation"
                            )
                        if pid_probe(int(existing.record["pid"])) != "dead":
                            raise OSError(
                                "lease PID death changed after reconciliation"
                            )
                        _unlink_revalidated_record_at(
                            directory,
                            path.name,
                            path,
                            existing,
                            _validate_chain_lease_record,
                        )
                        os.fsync(directory)
                        if boundary is not None:
                            boundary("chain-lease-stale-reclaimed")
                        reclaimed_stale = True
                        continue
                else:
                    last_evidence["detail"] = (
                        "lease owner is live/foreign/unprovable or repository exclusion is absent"
                    )
                if single_attempt:
                    raise ChainLeaseUnavailable(chain_id, last_evidence)
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise ChainLeaseUnavailable(chain_id, last_evidence)
                continue
            if exclusion is not None and not _lease_exclusion_is_current(
                exclusion, chain_id
            ):
                raise OSError(
                    "repository exclusion changed before chain lease publication"
                )
            if exclusion is None and _repository_recovery_reservation_present(
                canonical
            ):
                last_evidence["detail"] = (
                    "repository recovery reservation excludes ordinary lease publication"
                )
                if single_attempt:
                    raise ChainLeaseUnavailable(chain_id, last_evidence)
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise ChainLeaseUnavailable(chain_id, last_evidence)
                continue
            temporary, temporary_identity = _create_private_record_at(
                directory,
                canonical,
                f"{chain_id}.lock",
                record,
                boundary=boundary,
                stage="chain-lease-temp-fsynced",
            )
            try:
                try:
                    if exclusion is not None and not _lease_exclusion_is_current(
                        exclusion, chain_id
                    ):
                        raise OSError(
                            "repository exclusion changed before chain lease publication"
                        )
                    if (
                        exclusion is None
                        and _repository_recovery_reservation_present(canonical)
                    ):
                        raise OSError(
                            "repository recovery reservation appeared before chain lease publication"
                        )
                    _publish_no_replace_link(
                        directory, temporary, directory, path.name
                    )
                except FileExistsError:
                    _unlink_revalidated_record_at(
                        directory,
                        temporary,
                        canonical / temporary,
                        temporary_identity,
                        _validate_chain_lease_record,
                    )
                    os.fsync(directory)
                    if single_attempt:
                        raise ChainLeaseUnavailable(chain_id, last_evidence)
                    if not _sleep_with_deadline(deadline, clock, sleeper):
                        raise ChainLeaseUnavailable(chain_id, last_evidence)
                    continue
                os.fsync(directory)
                canonical_identity = _read_owned_record_at(
                    directory,
                    path.name,
                    path,
                    _validate_chain_lease_record,
                )
                if not _same_published_record(canonical_identity, temporary_identity):
                    raise OSError("published chain lease changed inode or digest")
                if boundary is not None:
                    boundary("chain-lease-published")
                _unlink_revalidated_record_at(
                    directory,
                    temporary,
                    canonical / temporary,
                    temporary_identity,
                    _validate_chain_lease_record,
                )
                os.fsync(directory)
                if boundary is not None:
                    boundary("chain-lease-temp-unlinked")
                acquired = ChainLease(
                    chains_dir=canonical,
                    directory_descriptor=directory,
                    identity=canonical_identity,
                    boundary=boundary,
                    exclusion=exclusion,
                )
                if reclaimed_stale:
                    _reconcile_merge_projection_for_lease_reclaim(
                        canonical,
                        chain_id,
                        exclusion=exclusion,
                        repair_with=acquired,
                        deadline=deadline,
                        clock=clock,
                        sleeper=sleeper,
                    )
                return acquired
            except BaseException as exc:
                if isinstance(exc, (CommonLockBoundaryCrash, ChainLeaseUnavailable)):
                    raise
                try:
                    os.unlink(temporary, dir_fd=directory)
                    os.fsync(directory)
                except (FileNotFoundError, OSError):
                    pass
                raise
    except BaseException:
        os.close(directory)
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


def _prove_merge_run_task_binding(
    repository: Path,
    common_root: Path,
    run_id: str,
    task_id: str,
    policy_digest: str,
    *,
    create_batch_lock: bool = False,
) -> MergeRunTaskSnapshot:
    batch, _builders, journal = runtime._coordination_modules()
    run_dir = common_root / ".codex-orchestrator" / "runs" / run_id
    try:
        with _chain_batch_lock(
            run_dir,
            repository,
            run_id,
            create=create_batch_lock,
        ):
            run_state = journal._scan_run(run_dir)
            opening = run_state.records[0] if run_state.records else None
            if (
                run_state.disposition != "open"
                or not isinstance(opening, dict)
                or Path(str(opening.get("repo", ""))).resolve(strict=True)
                != repository
            ):
                raise ValueError("run is not open for the merge repository")
            tasks = [
                record
                for record in run_state.records
                if record.get("type") == "task" and record.get("id") == task_id
            ]
            if not tasks or tasks[-1].get("status") != "active":
                raise ValueError("task is not active")
            files = tasks[-1].get("files")
            scope = run_state.scope
            if (
                not isinstance(files, list)
                or not files
                or not all(isinstance(value, str) and value for value in files)
                or not isinstance(scope, tuple)
                or not scope
                or not all(isinstance(value, str) and value for value in scope)
            ):
                raise ValueError("task files or admitted scope are malformed")
    except (OSError, RuntimeError, ValueError, journal.CoordinationRefusal) as exc:
        raise _merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: merge start refused — run/task binding is invalid",
            expected="matching repository, active task, immutable scope, and committed policy",
            observed=str(exc),
            remediation="inspect the named run/task and retry the exact paired start",
        ) from exc
    return MergeRunTaskSnapshot(
        binding={
            "run_id": run_id,
            "task_id": task_id,
            "repository": str(repository),
            "policy_digest": policy_digest,
        },
        task_files=tuple(sorted(set(files), key=lambda value: value.encode("utf-8"))),
        admitted_scope=tuple(
            sorted(set(scope), key=lambda value: value.encode("utf-8"))
        ),
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
