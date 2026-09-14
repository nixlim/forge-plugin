"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
from typing import Any, Mapping
from forge_cli import runtime
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
from forge_cli.chain_core._merge_transition import _merge_transition_valid as _merge_transition_valid, _merge_ingest_transition_valid as _merge_ingest_transition_valid
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot, _ChainReceiptSnapshotVerifier as _ChainReceiptSnapshotVerifier
from forge_cli.chain_core._remote_observation import _remote_containment_evidence_valid as _remote_containment_evidence_valid, _remote_observation_progress_valid as _remote_observation_progress_valid, _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed, _replayed_remote_observation_completed as _replayed_remote_observation_completed
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA
import dataclasses
import copy
import json
from pathlib import Path
from forge_cli.policy import sha256_bytes


def validate_merge_state(
    state: Any, chain_id: str | None = None
) -> dict[str, Any]:
    """Validate the separate 24-key DM-014 materialized projection."""

    _require_merge_store_control("separate-merge-grammar")
    if not isinstance(state, dict) or set(state) != MERGE_STATE_KEYS:
        raise FrozenError(
            "materialized merge state has an invalid top-level key set",
            chain_id=chain_id,
            observed=(
                ",".join(sorted(state))
                if isinstance(state, dict)
                else type(state).__name__
            ),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    actual_id = state.get("chain_id")
    if not isinstance(actual_id, str) or CHAIN_ID_RE.fullmatch(actual_id) is None:
        raise FrozenError(
            "merge state has an invalid chain_id",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if chain_id is not None and actual_id != chain_id:
        raise FrozenError(
            "merge filename and payload identity diverge",
            chain_id=chain_id,
            observed=str(actual_id),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    _batch, builders, _journal = runtime._coordination_modules()
    if (
        MERGE_STATE_KEYS != builders._MERGE_STATE_KEYS
        or MERGE_EVENT_NAMES != builders._MERGE_EVENT_NAMES
        or not _merge_state_shape_valid(builders, state, actual_id)
    ):
        raise FrozenError(
            "materialized merge state is invalid",
            chain_id=actual_id,
            state=str(state.get("state")),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    return state


@dataclasses.dataclass(frozen=True)
class MergeReplayResult:
    """Authenticated DM-014 replay before materialized-state comparison."""

    state: dict[str, Any]
    events: tuple[dict[str, Any], ...]
    entries: tuple[
        tuple[
            dict[str, Any],
            dict[str, Any] | None,
            dict[str, Any],
            tuple[dict[str, Any], ...],
            str | None,
        ],
        ...,
    ]
    prefix_state_bytes: tuple[bytes, ...]
    context: dict[str, Any]
    raw_events: bytes
    tail_sequence: int
    tail_digest: str


def _replay_merge_event_bytes(
    chain_id: str,
    raw_events: bytes,
    *,
    verify_receipts: bool = True,
    receipt_repository: Path | None = None,
    expected_run_binding: Mapping[str, object] | None = None,
    receipt_verifier: _ChainReceiptSnapshotVerifier | None = None,
) -> MergeReplayResult:
    """Replay DM-014 by composing the registered reducer and builder grammar."""

    _require_merge_store_control("separate-merge-grammar")
    if not raw_events or not raw_events.endswith(b"\n"):
        raise FrozenError(
            "merge event log is empty or has a partial final record",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    _batch, builders, _journal = runtime._coordination_modules()
    if (
        MERGE_STATE_KEYS != builders._MERGE_STATE_KEYS
        or MERGE_EVENT_NAMES != builders._MERGE_EVENT_NAMES
    ):
        raise FrozenError(
            "merge grammar authority is unavailable",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    previous_digest = ZERO_DIGEST
    replayed: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []
    entries: list[
        tuple[
            dict[str, Any],
            dict[str, Any] | None,
            dict[str, Any],
            tuple[dict[str, Any], ...],
            str | None,
        ]
    ] = []
    prefix_state_bytes: list[bytes] = []
    context: dict[str, Any] = {}
    pending_outbox: dict[str, Any] | None = None
    pending_records: tuple[dict[str, Any], ...] = ()
    for sequence, raw in enumerate(raw_events.splitlines(keepends=True), 1):
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise FrozenError(
                f"merge event {sequence} is malformed",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        if (
            not isinstance(event, dict)
            or set(event) != MERGE_EVENT_KEYS
            or event.get("schema") != "forge-merge-event/1"
            or event.get("chain_id") != chain_id
            or event.get("sequence") != sequence
            or event.get("previous_digest") != previous_digest
            or event.get("event") not in MERGE_EVENT_NAMES
            or builders._utc_value(event.get("at")) is None
        ):
            raise FrozenError(
                f"merge event {sequence} has an invalid identity or key set",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if raw != canonical_bytes(event) + b"\n":
            raise FrozenError(
                f"merge event {sequence} is not canonical",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        projection = {name: event[name] for name in event if name != "digest"}
        digest = event.get("digest")
        if (
            not isinstance(digest, str)
            or SHA256_RE.fullmatch(digest) is None
            or digest != sha256_bytes(canonical_bytes(projection))
        ):
            raise FrozenError(
                f"merge event {sequence} digest is invalid",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        prior = copy.deepcopy(replayed)
        try:
            records, event_outbox, source_digest = builders._event_batch_records(
                event, "merge"
            )
            event_name = event.get("event")
            is_receipt = event_name == "journal_receipted"
            if pending_outbox is not None and not is_receipt:
                raise ValueError("pending merge outbox was bypassed")
            if pending_outbox is None and is_receipt:
                raise ValueError("merge receipt has no pending outbox")
            receipt = (
                builders._receipt_metadata(event, "merge")
                if is_receipt
                else None
            )
            if is_receipt:
                if (
                    receipt is None
                    or records
                    or event_outbox is not None
                    or source_digest is not None
                    or receipt.get("idempotency_key")
                    != pending_outbox.get("idempotency_key")
                    or receipt.get("batch_digest")
                    != pending_outbox.get("batch_digest")
                    or replayed is None
                ):
                    raise ValueError("merge receipt identity is invalid")
                if verify_receipts:
                    if (
                        expected_run_binding is not None
                        and replayed.get("run_binding")
                        != dict(expected_run_binding)
                    ):
                        raise ValueError(
                            "merge receipt replay changed its run binding"
                        )
                    receipt_repository_value = (
                        receipt_repository
                        if receipt_repository is not None
                        else Path(str(replayed["repository"]))
                    )
                    verifier = receipt_verifier or builders._verify_receipted_batch
                    verifier(
                        receipt_repository_value,
                        chain_id,
                        replayed,
                        pending_outbox,
                        pending_records,
                        receipt,
                    )
            elif event_outbox is not None and pending_outbox is not None:
                raise ValueError("merge event introduced a second pending outbox")

            current = reduce_merge_event(prior, copy.deepcopy(event))
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            RuntimeError,
            _journal.CoordinationRefusal,
        ) as exc:
            raise FrozenError(
                f"merge event {sequence} payload is invalid",
                chain_id=chain_id,
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        additive_history = _merge_history_uses_additive_grammar((*events, event))
        state_shape_valid = (
            _merge_state_shape_valid(builders, current, chain_id)
            if additive_history
            else builders._state_shape_valid(current, chain_id, "merge")
        )
        if not state_shape_valid or not (
            _merge_ingest_transition_valid(
                builders,
                event,
                prior,
                current,
                context=context,
                history=tuple(events),
            )
        ):
            raise FrozenError(
                f"merge event {sequence} transition is invalid",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if is_receipt:
            if current.get("journal_outbox") is not None or prior is None:
                raise FrozenError(
                    f"merge event {sequence} receipt did not clear its outbox",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            ignored = {"last_event_at", "inactive_after", "journal_outbox"}
            if any(
                prior.get(name) != current.get(name)
                for name in MERGE_STATE_KEYS - ignored
            ):
                raise FrozenError(
                    f"merge event {sequence} receipt changed chain authority",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            pending_outbox = None
            pending_records = ()
        elif event_outbox is not None:
            if current.get("journal_outbox") != event_outbox:
                raise FrozenError(
                    f"merge event {sequence} outbox projection is invalid",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            pending_outbox = copy.deepcopy(event_outbox)
            pending_records = tuple(copy.deepcopy(records))
        elif current.get("journal_outbox") != pending_outbox:
            raise FrozenError(
                f"merge event {sequence} changed its pending outbox",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        activation_preamble = (
            records[:1]
            if records
            and _journal._writer_activation_candidate(records[0])
            else ()
        )
        for carried_record in records[len(activation_preamble) :]:
            carried_binding = carried_record.get("binding")
            if not isinstance(
                carried_binding, dict
            ) or not builders._binding_matches_source_fact(
                carried_binding,
                carried_record,
                event,
                prior,
                current,
                family="merge",
            ):
                raise FrozenError(
                    f"merge event {sequence} carries an invalid journal binding",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
        replayed = copy.deepcopy(current)
        event_copy = copy.deepcopy(event)
        current_copy = copy.deepcopy(current)
        events.append(event_copy)
        entries.append(
            (
                event_copy,
                prior,
                current_copy,
                tuple(copy.deepcopy(records)),
                source_digest,
            )
        )
        prefix_state_bytes.append(canonical_bytes(current) + b"\n")
        previous_digest = digest
    if replayed is None or not events:
        raise FrozenError(
            "merge event replay is empty",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    replayed_state = (
        validate_merge_state(replayed, chain_id)
        if _merge_history_uses_additive_grammar(events)
        else copy.deepcopy(replayed)
    )
    if (
        expected_run_binding is not None
        and replayed_state.get("run_binding") != dict(expected_run_binding)
    ):
        raise FrozenError(
            "merge replay changed its immutable run binding",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    return MergeReplayResult(
        state=replayed_state,
        events=tuple(events),
        entries=tuple(entries),
        prefix_state_bytes=tuple(prefix_state_bytes),
        context=copy.deepcopy(context),
        raw_events=raw_events,
        tail_sequence=len(events),
        tail_digest=previous_digest,
    )
