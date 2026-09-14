"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import base64
import binascii
from typing import Any, Mapping, Sequence
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
from forge_cli.chain_core._merge_candidate_observation_steps import _merge_candidate_observation_step_specs as _merge_candidate_observation_step_specs, _merge_candidate_observation_step_names as _merge_candidate_observation_step_names, _merge_candidate_observation_binding as _merge_candidate_observation_binding
from forge_cli.chain_core._merge_cleanup_history import _merge_cleanup_evidence_history as _merge_cleanup_evidence_history, _merge_cleanup_history_summary as _merge_cleanup_history_summary, _merge_cleanup_unmatched_intent as _merge_cleanup_unmatched_intent, _merge_cleanup_retry_proof_valid as _merge_cleanup_retry_proof_valid, _merge_cleanup_intent_transition_valid as _merge_cleanup_intent_transition_valid, _merge_history_has_git_mutation_intent as _merge_history_has_git_mutation_intent
from forge_cli.chain_core._merge_cleanup_intent import _recovery_event_intent as _recovery_event_intent, _recovery_cleanup_intent as _recovery_cleanup_intent, _merge_cleanup_expected_subject as _merge_cleanup_expected_subject, _merge_cleanup_expected_argv as _merge_cleanup_expected_argv, _merge_cleanup_intent_valid as _merge_cleanup_intent_valid
from forge_cli.chain_core._merge_cleanup_observation import _merge_cleanup_process_output as _merge_cleanup_process_output, _merge_cleanup_process_complete as _merge_cleanup_process_complete, _merge_cleanup_branch_observation as _merge_cleanup_branch_observation, _merge_cleanup_worktree_inventory as _merge_cleanup_worktree_inventory, _merge_cleanup_fetch_head_bytes as _merge_cleanup_fetch_head_bytes, _merge_cleanup_observation_valid as _merge_cleanup_observation_valid
from forge_cli.chain_core._merge_cleanup_result import _merge_cleanup_process_result_valid as _merge_cleanup_process_result_valid, _merge_cleanup_step_result_valid as _merge_cleanup_step_result_valid, _merge_cleanup_results_valid as _merge_cleanup_results_valid, _merge_cleanup_result_transition_valid as _merge_cleanup_result_transition_valid
from forge_cli.chain_core._merge_events import _merge_event_outbox as _merge_event_outbox, _merge_payload_delta as _merge_payload_delta, reduce_merge_event as reduce_merge_event
from forge_cli.chain_core._merge_plan import _merge_plan_position_fact as _merge_plan_position_fact, _merge_carried_gate_steps as _merge_carried_gate_steps, _merge_gate_step_generation_digests as _merge_gate_step_generation_digests, _merge_current_authority_valid as _merge_current_authority_valid, _merge_remote_only_equality_proof as _merge_remote_only_equality_proof, _merge_carry_payload_valid as _merge_carry_payload_valid, _merge_plan_transition_valid as _merge_plan_transition_valid
from forge_cli.chain_core._merge_rebase import _parse_registered_worktrees as _parse_registered_worktrees, _merge_rebase_action as _merge_rebase_action, _merge_rebase_result_classification as _merge_rebase_result_classification, _merge_containment as _merge_containment, _merge_old_tip_all_false as _merge_old_tip_all_false, _merge_latest_contained_attempt as _merge_latest_contained_attempt, _merge_inactive_post_attempt_recovery_ready as _merge_inactive_post_attempt_recovery_ready, _remote_observation_heads as _remote_observation_heads, _remote_observation_fetch_argv as _remote_observation_fetch_argv, _remote_containment_argv as _remote_containment_argv
from forge_cli.chain_core._merge_release import _merge_attempted_release_preconditions_valid as _merge_attempted_release_preconditions_valid, _merge_release_preconditions_valid as _merge_release_preconditions_valid
from forge_cli.chain_core._merge_scope import _validate_merge_scope_proof as _validate_merge_scope_proof, _merge_scope_event_binding_valid as _merge_scope_event_binding_valid, _merge_scope_transition_valid as _merge_scope_transition_valid
from forge_cli.chain_core._merge_scope_binding import _merge_scope_environment_contract as _merge_scope_environment_contract, _validate_merge_scope_request as _validate_merge_scope_request, _merge_retained_inflight as _merge_retained_inflight, _validate_merge_scope_fetch_binding as _validate_merge_scope_fetch_binding, _merge_scope_binding_names as _merge_scope_binding_names, _merge_full_patch_argv as _merge_full_patch_argv, _merge_scope_argv as _merge_scope_argv, _merge_scope_binding_validator as _merge_scope_binding_validator
from forge_cli.chain_core._merge_state_shape import _merge_gate_plan_valid as _merge_gate_plan_valid, _merge_epoch_valid as _merge_epoch_valid, _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view as _merge_revision9_compatibility_view, _merge_state_shape_valid as _merge_state_shape_valid, _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot
from forge_cli.chain_core._remote_observation import _remote_containment_evidence_valid as _remote_containment_evidence_valid, _remote_observation_progress_valid as _remote_observation_progress_valid, _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed, _replayed_remote_observation_completed as _replayed_remote_observation_completed
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.policy import sha256_bytes
import copy


def _merge_candidate_observation_record_valid(
    state: Mapping[str, Any], value: object
) -> bool:
    if not isinstance(value, Mapping):
        return False
    base_keys = {
        "schema",
        "chain_id",
        "generation_digest",
        "source_intent",
        "verb",
        "remote_tip",
        "expected_head",
        "classify",
        "declared_tier",
        "observation_binding",
        "stage",
        "step",
        "cwd",
        "argv",
        "started_at",
    }
    stage = value.get("stage")
    expected_keys = (
        base_keys
        if stage == "intent"
        else {*base_keys, "child_result", "recorded_at"}
        if stage == "result"
        else set()
    )
    candidate = state.get("candidate")
    generation_digest = (
        candidate.get("generation_digest") if isinstance(candidate, Mapping) else None
    )
    binding = _merge_candidate_observation_binding(
        state,
        value.get("source_intent"),
        verb=str(value.get("verb", "")),
        remote_tip=str(value.get("remote_tip", "")),
        expected_head=str(value.get("expected_head", "")),
        classify=value.get("classify") if type(value.get("classify")) is bool else False,
        declared_tier=(
            value.get("declared_tier")
            if isinstance(value.get("declared_tier"), str)
            else None
        ),
    )
    specs = _merge_candidate_observation_step_specs(
        state,
        remote_tip=str(value.get("remote_tip", "")),
        expected_head=str(value.get("expected_head", "")),
        classify=value.get("classify") if type(value.get("classify")) is bool else False,
        declared_tier=(
            value.get("declared_tier")
            if isinstance(value.get("declared_tier"), str)
            else None
        ),
    )
    expected_step = next(
        (
            (str(cwd), argv)
            for name, cwd, argv in (specs or ())
            if name == value.get("step")
        ),
        None,
    )
    if (
        set(value) != expected_keys
        or value.get("schema") != _MERGE_CANDIDATE_OBSERVATION_SCHEMA
        or value.get("chain_id") != state.get("chain_id")
        or value.get("generation_digest") != generation_digest
        or type(value.get("classify")) is not bool
        or (
            value.get("declared_tier") is not None
            and value.get("declared_tier") not in TIER_RANK
        )
        or binding is None
        or value.get("observation_binding") != binding
        or expected_step is None
        or value.get("cwd") != expected_step[0]
        or value.get("argv") != expected_step[1]
        or not isinstance(value.get("step"), str)
        or not value.get("step")
        or not isinstance(value.get("argv"), list)
        or not value.get("argv")
        or not all(isinstance(member, str) and member for member in value["argv"])
        or not _valid_utc_second(value.get("started_at"))
    ):
        return False
    if stage == "intent":
        return True
    child = value.get("child_result")
    if not isinstance(child, Mapping) or set(child) != {
        "authorized",
        "exit",
        "inflight_digest",
        "output_digest",
        "stored_output_digest",
        "output_b64",
        "launch_failed",
        "timed_out",
        "output_limit_exceeded",
        "group_survived",
    }:
        return False
    try:
        output = base64.b64decode(str(child.get("output_b64", "")), validate=True)
    except (ValueError, binascii.Error):
        return False
    return bool(
        type(child.get("authorized")) is bool
        and (child.get("exit") is None or type(child.get("exit")) is int)
        and SHA256_RE.fullmatch(str(child.get("inflight_digest", ""))) is not None
        and SHA256_RE.fullmatch(str(child.get("output_digest", ""))) is not None
        and len(output) <= runtime.OUTPUT_CAP_BYTES
        and SHA256_RE.fullmatch(str(child.get("stored_output_digest", "")))
        is not None
        and sha256_bytes(output) == child.get("stored_output_digest")
        and all(
            type(child.get(name)) is bool
            for name in (
                "launch_failed",
                "timed_out",
                "output_limit_exceeded",
                "group_survived",
            )
        )
        and _valid_utc_second(value.get("recorded_at"))
    )


def _merge_candidate_observation_transition_valid(
    prior: Mapping[str, Any], current: Mapping[str, Any]
) -> bool:
    prior_integration = prior.get("integration")
    current_integration = current.get("integration")
    if not isinstance(prior_integration, Mapping) or not isinstance(
        current_integration, Mapping
    ):
        return False
    prior_intent = prior_integration.get("intent")
    current_intent = current_integration.get("intent")
    if any(
        prior_integration.get(name) != current_integration.get(name)
        for name in (set(prior_integration) | set(current_integration)) - {"intent"}
    ):
        return False
    prior_observation = _merge_candidate_observation_record_valid(
        prior, prior_intent
    )
    current_observation = _merge_candidate_observation_record_valid(
        current, current_intent
    )
    if current_observation:
        assert isinstance(current_intent, Mapping)
        if current_intent.get("stage") == "intent":
            return bool(
                not prior_observation
                and current_intent.get("source_intent") == prior_intent
            )
        if not prior_observation or not isinstance(prior_intent, Mapping):
            return False
        return bool(
            prior_intent.get("stage") == "intent"
            and all(
                prior_intent.get(name) == current_intent.get(name)
                for name in set(prior_intent) - {"stage"}
            )
        )
    return bool(
        prior_observation
        and isinstance(prior_intent, Mapping)
        and prior_intent.get("stage") == "result"
        and current_intent == prior_intent.get("source_intent")
    )


def _merge_candidate_observation_evidence(
    state: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Build the pure, digest-bound view of already durable child results."""

    if not records:
        return None
    first = records[0]
    binding = first.get("observation_binding")
    names = _merge_candidate_observation_step_names(
        state,
        remote_tip=str(first.get("remote_tip", "")),
        expected_head=str(first.get("expected_head", "")),
        classify=first.get("classify") if type(first.get("classify")) is bool else False,
        declared_tier=(
            first.get("declared_tier")
            if isinstance(first.get("declared_tier"), str)
            else None
        ),
    )
    if names is None or tuple(record.get("step") for record in records) != names:
        return None
    normalized: list[dict[str, Any]] = []
    for record in records:
        if (
            not _merge_candidate_observation_record_valid(state, record)
            or record.get("stage") != "result"
            or record.get("observation_binding") != binding
            or any(
                record.get(name) != first.get(name)
                for name in (
                    "chain_id",
                    "generation_digest",
                    "source_intent",
                    "verb",
                    "remote_tip",
                    "expected_head",
                    "classify",
                    "declared_tier",
                )
            )
        ):
            return None
        normalized.append(copy.deepcopy(dict(record)))
    evidence: dict[str, Any] = {
        "schema": _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA,
        "chain_id": first.get("chain_id"),
        "generation_digest": first.get("generation_digest"),
        "source_intent": copy.deepcopy(first.get("source_intent")),
        "verb": first.get("verb"),
        "remote_tip": first.get("remote_tip"),
        "expected_head": first.get("expected_head"),
        "classify": first.get("classify"),
        "declared_tier": first.get("declared_tier"),
        "observation_binding": binding,
        "steps": normalized,
    }
    evidence["evidence_digest"] = sha256_bytes(canonical_bytes(evidence))
    return evidence


def _merge_candidate_observation_evidence_valid(
    state: Mapping[str, Any], value: object
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "chain_id",
        "generation_digest",
        "source_intent",
        "verb",
        "remote_tip",
        "expected_head",
        "classify",
        "declared_tier",
        "observation_binding",
        "steps",
        "evidence_digest",
    }:
        return False
    steps = value.get("steps")
    rebuilt = (
        _merge_candidate_observation_evidence(state, steps)
        if isinstance(steps, list)
        and all(isinstance(record, Mapping) for record in steps)
        else None
    )
    return bool(rebuilt is not None and dict(value) == rebuilt)
