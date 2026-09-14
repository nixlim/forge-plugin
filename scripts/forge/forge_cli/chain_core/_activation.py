"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import dataclasses
from forge_cli.chain_core._bootstrap_observation import _bootstrap_fetch_observation_record_valid as _bootstrap_fetch_observation_record_valid, _bootstrap_fetch_observation_transition_valid as _bootstrap_fetch_observation_transition_valid
from forge_cli.chain_core._candidate_v2 import candidate_is_v2 as candidate_is_v2, _candidate_binding_for_state_with_candidate_v2 as _candidate_binding_for_state_with_candidate_v2, _binding_shape_valid_with_candidate_v2 as _binding_shape_valid_with_candidate_v2, _event_batch_records_with_candidate_v2 as _event_batch_records_with_candidate_v2, _binding_matches_source_fact_with_candidate_v2 as _binding_matches_source_fact_with_candidate_v2, _binding_is_current_with_candidate_v2 as _binding_is_current_with_candidate_v2
from forge_cli.chain_core._chain_state import validate_state as validate_state
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._fenced_child import _BlockedFenceChild as _BlockedFenceChild, _pipe_cloexec as _pipe_cloexec, _read_child_ack as _read_child_ack, _waitpid_nohang as _waitpid_nohang, _wait_for_child_exit as _wait_for_child_exit, _spawn_blocked_fence_child as _spawn_blocked_fence_child, _terminate_fenced_group as _terminate_fenced_group, _stop_unstarted_child as _stop_unstarted_child, _collect_fenced_child as _collect_fenced_child
from forge_cli.chain_core._ingest_capture import _read_ingest_input as _read_ingest_input, _capture_ingest_blob as _capture_ingest_blob, _capture_run_evidence as _capture_run_evidence, _capture_ingest_record_evidence as _capture_ingest_record_evidence
from forge_cli.chain_core._ingest_currency import _ingest_captured_paths as _ingest_captured_paths, _ingest_step_is_current as _ingest_step_is_current, _ingest_secret_scan_is_current as _ingest_secret_scan_is_current, _prove_ingest_live_chain as _prove_ingest_live_chain
from forge_cli.chain_core._ingest_merge import _merge_ingest_binding as _merge_ingest_binding, _merge_gate_event_fact as _merge_gate_event_fact, _merge_current_gate_facts as _merge_current_gate_facts, _merge_ingest_record_templates as _merge_ingest_record_templates, _verify_and_build_merge_ingest_records as _verify_and_build_merge_ingest_records
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
from forge_cli.chain_core._merge_replay import validate_merge_state as validate_merge_state, MergeReplayResult as MergeReplayResult, _replay_merge_event_bytes as _replay_merge_event_bytes
from forge_cli.chain_core._merge_scope import _validate_merge_scope_proof as _validate_merge_scope_proof, _merge_scope_event_binding_valid as _merge_scope_event_binding_valid, _merge_scope_transition_valid as _merge_scope_transition_valid
from forge_cli.chain_core._merge_scope_binding import _merge_scope_environment_contract as _merge_scope_environment_contract, _validate_merge_scope_request as _validate_merge_scope_request, _merge_retained_inflight as _merge_retained_inflight, _validate_merge_scope_fetch_binding as _validate_merge_scope_fetch_binding, _merge_scope_binding_names as _merge_scope_binding_names, _merge_full_patch_argv as _merge_full_patch_argv, _merge_scope_argv as _merge_scope_argv, _merge_scope_binding_validator as _merge_scope_binding_validator
from forge_cli.chain_core._merge_state_shape import _merge_gate_plan_valid as _merge_gate_plan_valid, _merge_epoch_valid as _merge_epoch_valid, _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view as _merge_revision9_compatibility_view, _merge_state_shape_valid as _merge_state_shape_valid, _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar
from forge_cli.chain_core._merge_transition import _merge_transition_valid as _merge_transition_valid, _merge_ingest_transition_valid as _merge_ingest_transition_valid
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot, _ChainReceiptSnapshotVerifier as _ChainReceiptSnapshotVerifier
from forge_cli.chain_core._remote_observation import _remote_containment_evidence_valid as _remote_containment_evidence_valid, _remote_observation_progress_valid as _remote_observation_progress_valid, _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed, _replayed_remote_observation_completed as _replayed_remote_observation_completed
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
import copy
import json
from pathlib import Path
from typing import Mapping
from forge_cli import runtime
from forge_cli.envelope import FrozenError
import hashlib


@dataclasses.dataclass(frozen=True)
class _ChainActivationSnapshot:
    """One bounded, event-authoritative chain projection and its carrier."""

    family: str
    state: dict[str, object]
    raw_events: bytes
    raw_state: bytes
    tail_records: tuple[dict[str, object], ...]
    tail_source_event_digest: str | None


def _resolve_chain_activation_snapshot(
    repository: Path,
    chains_descriptor: int,
    chain_id: str,
    *,
    allow_pending: bool,
    validate_lineage: bool,
    verify_external: bool = True,
    state_cap: int | None = None,
    events_cap: int | None = None,
    expected_binding: Mapping[str, object] | None = None,
    receipt_verifier: _ChainReceiptSnapshotVerifier | None = None,
) -> _ChainActivationSnapshot:
    """Replay one bound chain for first-use reservation or authorization.

    The shared builder remains authoritative for commit and historical merge
    histories.  Revision-10 additive merge histories use the DM-014 replay
    owned by this module; the shared Revision-9 transition validator cannot
    consume their additive compatibility projection.
    """

    _batch, builders, journal = runtime._coordination_modules()
    effective_state_cap = (
        builders._ACTIVATION_STATE_CAP_BYTES
        if state_cap is None
        else state_cap
    )
    effective_events_cap = (
        builders._ACTIVATION_EVENTS_CAP_BYTES
        if events_cap is None
        else events_cap
    )
    authority = builders._activation_event_one_binding_authority(
        chains_descriptor, chain_id
    )
    try:
        raw_events = builders._read_regular_bytes_at(
            chains_descriptor,
            f"{chain_id}.events.jsonl",
            cap=effective_events_cap,
        )
        try:
            first_event = json.loads(raw_events.splitlines()[0].decode("utf-8"))
        except (IndexError, UnicodeError, ValueError, RecursionError) as exc:
            raise builders._binding_replay_refusal() from exc
        merge_history = bool(
            isinstance(first_event, dict)
            and first_event.get("schema") == "forge-merge-event/1"
        )
        if expected_binding is not None and (
            authority is None
            or authority[0] != ("merge" if merge_history else "commit")
            or authority[1] != dict(expected_binding)
        ):
            raise builders._binding_replay_refusal()
        if merge_history:
            authority_binding = authority[1] if authority is not None else None
            if authority is not None and authority[0] != "merge":
                raise builders._binding_replay_refusal()
            replay = _replay_merge_event_bytes(
                chain_id,
                raw_events,
                verify_receipts=verify_external,
                receipt_repository=repository,
                expected_run_binding=(
                    dict(expected_binding)
                    if expected_binding is not None
                    else authority_binding
                    if isinstance(authority_binding, Mapping)
                    else None
                ),
                receipt_verifier=receipt_verifier,
            )
            if receipt_verifier is not None:
                receipt_verifier.recheck()
            if _merge_history_uses_additive_grammar(replay.events):
                raw_state = builders._read_regular_bytes_at(
                    chains_descriptor,
                    f"{chain_id}.json",
                    cap=effective_state_cap,
                )
                try:
                    materialized = json.loads(raw_state.decode("utf-8"))
                except (UnicodeError, ValueError, RecursionError) as exc:
                    raise builders._binding_replay_refusal() from exc
                if (
                    raw_state != canonical_bytes(replay.state) + b"\n"
                    or materialized != replay.state
                ):
                    raise builders._binding_replay_refusal()
                replay_binding = replay.state.get("run_binding")
                if expected_binding is not None:
                    if (
                        authority is None
                        or not isinstance(replay_binding, dict)
                        or replay_binding != dict(expected_binding)
                        or authority_binding != replay_binding
                    ):
                        raise builders._binding_replay_refusal()
                elif replay_binding is not None:
                    if (
                        not isinstance(replay_binding, dict)
                        or not builders._run_binding_valid(replay_binding)
                        or replay_binding.get("repository") != str(repository)
                        or authority_binding != replay_binding
                    ):
                        raise builders._binding_replay_refusal()
                elif authority is not None and authority_binding is not None:
                    raise builders._binding_replay_refusal()
                if (
                    replay.state.get("journal_outbox") is not None
                    and not allow_pending
                ):
                    raise journal.CoordinationRefusal(builders.JOURNAL_OUTBOX_PENDING)
                if validate_lineage:
                    _validate_chain_activation_lineage(
                        repository,
                        chains_descriptor,
                        chain_id,
                        replay.state,
                        raw_events=raw_events,
                        raw_state=raw_state,
                    )
                if (
                    builders._read_regular_bytes_at(
                        chains_descriptor,
                        f"{chain_id}.events.jsonl",
                        cap=effective_events_cap,
                    )
                    != raw_events
                ):
                    raise builders._binding_replay_refusal()
                if receipt_verifier is not None:
                    receipt_verifier.recheck()
                tail = replay.entries[-1]
                return _ChainActivationSnapshot(
                    family="merge",
                    state=copy.deepcopy(replay.state),
                    raw_events=raw_events,
                    raw_state=raw_state,
                    tail_records=tuple(copy.deepcopy(tail[3])),
                    tail_source_event_digest=tail[4],
                )

        builder_verify_external = verify_external and (
            receipt_verifier is None or not merge_history
        )
        builder_receipt_verifier = (
            receipt_verifier
            if verify_external and not merge_history
            else None
        )
        replayed = builders._resolve_binding_from_descriptor(
            repository,
            chains_descriptor,
            chain_id,
            ZERO_DIGEST,
            expected_type=None,
            expected_fields=None,
            expected_run_id=None,
            expected_task_id=None,
            replay_only=True,
            allow_pending=allow_pending,
            validate_lineage=False,
            verify_external=builder_verify_external,
            receipt_verifier=builder_receipt_verifier,
            resolve_tombstone=False,
            state_cap=effective_state_cap,
            events_cap=effective_events_cap,
        )
        rebound_events = builders._read_regular_bytes_at(
            chains_descriptor,
            f"{chain_id}.events.jsonl",
            cap=effective_events_cap,
        )
        raw_state = builders._read_regular_bytes_at(
            chains_descriptor,
            f"{chain_id}.json",
            cap=effective_state_cap,
        )
        family = replayed.get("kind")
        binding = replayed.get("run_binding")
        if (
            raw_events != rebound_events
            or raw_state != canonical_bytes(replayed) + b"\n"
            or family not in {"commit", "merge"}
            or (
                authority is not None
                and (authority[0] != family or authority[1] != binding)
            )
            or (binding is not None and authority is None)
            or (
                binding is not None
                and (
                    not isinstance(binding, dict)
                    or not builders._run_binding_valid(binding)
                    or binding.get("repository") != str(repository)
                )
            )
            or (
                expected_binding is not None
                and (
                    authority is None
                    or binding != dict(expected_binding)
                )
            )
        ):
            raise builders._binding_replay_refusal()
        try:
            tail_event = json.loads(raw_events.splitlines()[-1].decode("utf-8"))
        except (IndexError, UnicodeError, ValueError, RecursionError) as exc:
            raise builders._binding_replay_refusal() from exc
        if not isinstance(tail_event, dict):
            raise builders._binding_replay_refusal()
        tail_records, _tail_outbox, tail_source = builders._event_batch_records(
            tail_event, str(family)
        )
        if family == "merge" and validate_lineage:
            _validate_chain_activation_lineage(
                repository,
                chains_descriptor,
                chain_id,
                replayed,
                raw_events=raw_events,
                raw_state=raw_state,
            )
        if receipt_verifier is not None:
            receipt_verifier.recheck()
        return _ChainActivationSnapshot(
            family=str(family),
            state=copy.deepcopy(replayed),
            raw_events=raw_events,
            raw_state=raw_state,
            tail_records=tuple(copy.deepcopy(tail_records)),
            tail_source_event_digest=tail_source,
        )
    except journal.CoordinationRefusal:
        raise
    except (FrozenError, MemoryError, OSError) as exc:
        raise builders._binding_replay_refusal() from exc


def _chain_activation_ownership_summary(
    repository: Path,
    chains_descriptor: int,
    chain_id: str,
    *,
    receipt_verifier: _ChainReceiptSnapshotVerifier | None = None,
) -> dict[str, object]:
    """Return one bounded ownership summary through the current grammar."""

    _batch, builders, _journal = runtime._coordination_modules()
    owns_verifier = receipt_verifier is None
    if receipt_verifier is None:
        receipt_verifier = _ChainReceiptSnapshotVerifier(repository)
    snapshot = _resolve_chain_activation_snapshot(
        repository,
        chains_descriptor,
        chain_id,
        allow_pending=True,
        validate_lineage=False,
        verify_external=True,
        state_cap=builders._ACTIVATION_STATE_CAP_BYTES,
        events_cap=builders._ACTIVATION_EVENTS_CAP_BYTES,
        receipt_verifier=receipt_verifier,
    )
    if snapshot.family == "commit":
        summary = {
            "family": "commit",
            "snapshot_event_digest": hashlib.sha256(
                snapshot.raw_events
            ).hexdigest(),
            "snapshot_state": copy.deepcopy(snapshot.state),
        }
        if owns_verifier:
            receipt_verifier.recheck()
        return summary
    try:
        events = tuple(
            json.loads(line.decode("utf-8"))
            for line in snapshot.raw_events.splitlines(keepends=False)
        )
        if not all(isinstance(event, dict) for event in events):
            raise ValueError("merge ownership event is not an object")
        summary = builders._merge_ownership_summary(
            chain_id,
            snapshot.state,
            events,
            snapshot.raw_events,
        )
        if owns_verifier:
            receipt_verifier.recheck()
        return summary
    except (
        UnicodeError,
        ValueError,
        RecursionError,
        MemoryError,
        _journal.CoordinationRefusal,
    ) as exc:
        raise builders._binding_replay_refusal() from exc


def _validate_chain_activation_lineage(
    repository: Path,
    chains_descriptor: int,
    chain_id: str,
    state: dict[str, object],
    *,
    raw_events: bytes,
    raw_state: bytes,
) -> None:
    """Apply DM-014's bounded ownership graph to either merge grammar."""

    _batch, builders, journal = runtime._coordination_modules()
    current_worktree = builders._merge_worktree_claim(state)
    if current_worktree is None:
        raise builders._binding_replay_refusal()
    current_identity = {
        name: current_worktree[0][name]
        for name in ("path", "git_dir", "common_dir")
    }
    try:
        names = builders._activation_chain_names(chains_descriptor)
    except OSError as exc:
        raise builders._binding_replay_refusal() from exc
    relevant_names = frozenset(
        name
        for name in names
        if (
            name.endswith(".events.jsonl")
            and journal.CHAIN_ID_PATTERN.fullmatch(
                name.removesuffix(".events.jsonl")
            )
            is not None
        )
        or (
            name.endswith(".json")
            and journal.CHAIN_ID_PATTERN.fullmatch(name.removesuffix(".json"))
            is not None
        )
    )
    chain_ids = sorted(
        {
            candidate_id
            for name in relevant_names
            for candidate_id in (
                name.removesuffix(".events.jsonl")
                if name.endswith(".events.jsonl")
                else name.removesuffix(".json")
                if name.endswith(".json")
                else "",
            )
            if journal.CHAIN_ID_PATTERN.fullmatch(candidate_id) is not None
        }
    )
    if chain_id not in chain_ids:
        raise builders._binding_replay_refusal()
    cap = len(chain_ids)
    summaries: dict[str, dict[str, object]] = {}
    snapshots: dict[str, dict[str, object]] = {}
    receipt_verifier = _ChainReceiptSnapshotVerifier(repository)
    for candidate_id in chain_ids:
        try:
            summary = _chain_activation_ownership_summary(
                repository,
                chains_descriptor,
                candidate_id,
                receipt_verifier=receipt_verifier,
            )
        except (journal.CoordinationRefusal, MemoryError) as exc:
            raise builders._binding_replay_refusal() from exc
        snapshots[candidate_id] = summary
        if summary.get("family") == "commit":
            continue
        if summary.get("identity") == current_identity:
            summaries[candidate_id] = summary
    current = summaries.get(chain_id)
    if (
        current is None
        or current.get("chain_id") != chain_id
        or current.get("snapshot_event_digest")
        != hashlib.sha256(raw_events).hexdigest()
        or current.get("snapshot_state") != state
        or canonical_bytes(current.get("snapshot_state")) + b"\n" != raw_state
    ):
        raise builders._binding_replay_refusal()
    current_is_durable_predecessor = bool(
        current.get("terminal") is True
        and current.get("claim_status") == "released"
    )

    acquired = {
        name: summary
        for name, summary in summaries.items()
        if summary.get("acquired") is True
    }
    children: dict[tuple[object, object], list[str]] = {}
    for name, summary in acquired.items():
        predecessor = (
            summary.get("predecessor_chain_id"),
            summary.get("predecessor_release_digest"),
        )
        children.setdefault(predecessor, []).append(name)
        predecessor_chain, predecessor_digest = predecessor
        if predecessor_chain is None:
            if predecessor_digest is not None:
                raise builders._binding_replay_refusal()
            continue
        predecessor_summary = acquired.get(str(predecessor_chain))
        if not current_is_durable_predecessor and (
            predecessor_summary is None
            or predecessor_summary.get("released_digest") != predecessor_digest
            or predecessor_summary.get("terminal") is not True
            or predecessor_summary.get("claim_status") != "released"
            or predecessor_summary.get("identity") != current_identity
        ):
            raise builders._binding_replay_refusal()

    cursor: dict[str, object] | None = current
    visited: set[str] = set()
    for _ in range(cap + 1):
        if cursor is None:
            break
        predecessor_chain = cursor.get("predecessor_chain_id")
        predecessor_digest = cursor.get("predecessor_release_digest")
        if predecessor_chain is None:
            if predecessor_digest is not None:
                raise builders._binding_replay_refusal()
            cursor = None
            break
        if not isinstance(predecessor_chain, str) or predecessor_chain in visited:
            raise builders._binding_replay_refusal()
        visited.add(predecessor_chain)
        predecessor = acquired.get(predecessor_chain)
        if (
            predecessor is None
            or predecessor.get("released_digest") != predecessor_digest
            or predecessor.get("terminal") is not True
        ):
            raise builders._binding_replay_refusal()
        cursor = predecessor
    if cursor is not None:
        raise builders._binding_replay_refusal()

    if not current_is_durable_predecessor:
        if any(len(values) > 1 for values in children.values()):
            raise builders._binding_replay_refusal()
        others = {
            name: value for name, value in acquired.items() if name != chain_id
        }
        parent_names = {
            str(value.get("predecessor_chain_id"))
            for value in others.values()
            if value.get("predecessor_chain_id") is not None
        }
        tails = [
            value
            for name, value in others.items()
            if name not in parent_names
            and value.get("terminal") is True
            and value.get("released_digest") is not None
        ]
        expected = (
            (None, None)
            if not others
            else (
                (tails[0].get("chain_id"), tails[0].get("released_digest"))
                if len(tails) == 1
                else None
            )
        )
        observed = (
            current.get("predecessor_chain_id"),
            current.get("predecessor_release_digest"),
        )
        if expected is None or observed != expected:
            raise builders._binding_replay_refusal()
    else:
        current_edge = (
            current.get("predecessor_chain_id"),
            current.get("predecessor_release_digest"),
        )
        terminal_siblings = [
            name
            for name in children.get(current_edge, [])
            if name != chain_id
            and acquired[name].get("terminal") is True
            and acquired[name].get("claim_status") == "released"
        ]
        if terminal_siblings:
            raise builders._binding_replay_refusal()

    for candidate_id, snapshot in snapshots.items():
        try:
            raw_events = builders._read_regular_bytes_at(
                chains_descriptor,
                f"{candidate_id}.events.jsonl",
                cap=builders._ACTIVATION_EVENTS_CAP_BYTES,
            )
            raw_state = builders._read_regular_bytes_at(
                chains_descriptor,
                f"{candidate_id}.json",
                cap=builders._ACTIVATION_STATE_CAP_BYTES,
            )
        except (journal.CoordinationRefusal, MemoryError) as exc:
            raise builders._binding_replay_refusal() from exc
        if (
            hashlib.sha256(raw_events).hexdigest()
            != snapshot.get("snapshot_event_digest")
            or raw_state
            != canonical_bytes(snapshot.get("snapshot_state")) + b"\n"
        ):
            raise builders._binding_replay_refusal()
    try:
        final_names = builders._activation_chain_names(chains_descriptor)
    except OSError as exc:
        raise builders._binding_replay_refusal() from exc
    final_relevant_names = frozenset(
        name
        for name in final_names
        if (
            name.endswith(".events.jsonl")
            and journal.CHAIN_ID_PATTERN.fullmatch(
                name.removesuffix(".events.jsonl")
            )
            is not None
        )
        or (
            name.endswith(".json")
            and journal.CHAIN_ID_PATTERN.fullmatch(name.removesuffix(".json"))
            is not None
        )
    )
    if final_relevant_names != relevant_names:
        raise builders._binding_replay_refusal()
    receipt_verifier.recheck()
