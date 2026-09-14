"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
from typing import Any, Mapping
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


def _remote_containment_evidence_valid(
    state: Mapping[str, Any], value: object, *, head: str, tip: str
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "head",
        "tip",
        "argv",
        "authorized",
        "exit",
        "inflight_digest",
        "output_digest",
        "launch_failed",
        "timed_out",
        "output_limit_exceeded",
        "group_survived",
        "contained",
    }:
        return False
    exit_code = value.get("exit")
    ordinary = bool(
        value.get("authorized") is True
        and type(exit_code) is int
        and exit_code in {0, 1}
        and value.get("launch_failed") is False
        and value.get("timed_out") is False
        and value.get("output_limit_exceeded") is False
        and value.get("group_survived") is False
    )
    return bool(
        value.get("head") == head
        and value.get("tip") == tip
        and value.get("argv") == _remote_containment_argv(state, head, tip)
        and type(value.get("authorized")) is bool
        and (exit_code is None or type(exit_code) is int)
        and SHA256_RE.fullmatch(str(value.get("inflight_digest", ""))) is not None
        and SHA256_RE.fullmatch(str(value.get("output_digest", ""))) is not None
        and type(value.get("launch_failed")) is bool
        and type(value.get("timed_out")) is bool
        and type(value.get("output_limit_exceeded")) is bool
        and type(value.get("group_survived")) is bool
        and value.get("contained")
        == ((exit_code == 0) if ordinary else None)
    )


def _remote_observation_progress_valid(
    state: Mapping[str, Any], value: object
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "transaction",
        "chain_id",
        "attempt_identity",
        "phase",
        "push_intent_digest",
        "stage",
        "fetch_result",
        "heads",
        "cursor",
        "head",
        "argv",
        "completed",
        "recorded_at",
    }:
        return False
    integration = state.get("integration")
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    phase = value.get("phase")
    push_intent_digest = value.get("push_intent_digest")
    if (
        value.get("schema") != "forge-remote-observation-progress/1"
        or value.get("transaction") != "merge"
        or value.get("chain_id") != state.get("chain_id")
        or not isinstance(epoch, Mapping)
        or value.get("attempt_identity") != epoch.get("intent_digest")
        or phase not in {"final-prepush", "post-push"}
        or (
            phase == "final-prepush" and push_intent_digest is not None
        )
        or (
            phase == "post-push"
            and SHA256_RE.fullmatch(str(push_intent_digest or "")) is None
        )
        or not _valid_utc_second(value.get("recorded_at"))
    ):
        return False
    heads = value.get("heads")
    expected_heads = _remote_observation_heads(state)
    if heads != expected_heads:
        return False
    fetch = value.get("fetch_result")
    if not isinstance(fetch, Mapping) or set(fetch) != {
        "argv",
        "authorized",
        "exit",
        "exists",
        "oid",
        "inflight_digest",
        "output_digest",
        "launch_failed",
        "timed_out",
        "output_limit_exceeded",
        "group_survived",
    }:
        return False
    exists = fetch.get("exists")
    oid = fetch.get("oid")
    exit_code = fetch.get("exit")
    if (
        fetch.get("argv") != _remote_observation_fetch_argv(state)
        or fetch.get("authorized") is not True
        or (exit_code is not None and type(exit_code) is not int)
        or (exists is not True and exists is not False and exists is not None)
        or (
            exists is True
            and (
                not isinstance(oid, str) or COMMIT_RE.fullmatch(oid) is None
            )
        )
        or (exists is not True and oid is not None)
        or SHA256_RE.fullmatch(str(fetch.get("inflight_digest", ""))) is None
        or SHA256_RE.fullmatch(str(fetch.get("output_digest", ""))) is None
        or type(fetch.get("launch_failed")) is not bool
        or type(fetch.get("timed_out")) is not bool
        or type(fetch.get("output_limit_exceeded")) is not bool
        or type(fetch.get("group_survived")) is not bool
    ):
        return False
    completed = value.get("completed")
    if not isinstance(completed, list) or len(completed) > len(expected_heads):
        return False
    tip = str(oid or "")
    if any(
        not _remote_containment_evidence_valid(
            state, evidence, head=expected_heads[index], tip=tip
        )
        for index, evidence in enumerate(completed)
    ):
        return False
    stage = value.get("stage")
    cursor = value.get("cursor")
    head = value.get("head")
    argv = value.get("argv")
    if stage == "fetch-result":
        return bool(
            cursor == 0
            and head is None
            and argv is None
            and completed == []
        )
    if exists is not True or type(cursor) is not int:
        return False
    if stage == "containment-intent":
        return bool(
            cursor == len(completed)
            and cursor < len(expected_heads)
            and head == expected_heads[cursor]
            and argv == _remote_containment_argv(state, str(head), tip)
            and all(item.get("contained") is not None for item in completed)
        )
    if stage == "containment-result":
        return bool(
            completed
            and cursor == len(completed) - 1
            and cursor < len(expected_heads)
            and head == expected_heads[cursor]
            and argv == _remote_containment_argv(state, str(head), tip)
            and completed[-1].get("head") == head
        )
    return False


def _remote_observation_progress_transition_valid(
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
    if not _remote_observation_progress_valid(current, current_intent):
        return False
    assert isinstance(current_intent, Mapping)
    stage = current_intent.get("stage")
    identity_fields = {
        "schema",
        "transaction",
        "chain_id",
        "attempt_identity",
        "phase",
        "push_intent_digest",
        "fetch_result",
        "heads",
    }
    if stage == "fetch-result":
        return bool(
            isinstance(prior_intent, Mapping)
            and set(prior_intent)
            == {
                "schema",
                "transaction",
                "chain_id",
                "attempt_identity",
                "phase",
                "push_intent_digest",
            }
            and prior_intent.get("schema")
            == "forge-remote-observation-intent/1"
            and all(
                prior_intent.get(name) == current_intent.get(name)
                for name in {
                    "transaction",
                    "chain_id",
                    "attempt_identity",
                    "phase",
                    "push_intent_digest",
                }
            )
        )
    if not _remote_observation_progress_valid(prior, prior_intent):
        return False
    assert isinstance(prior_intent, Mapping)
    if any(prior_intent.get(name) != current_intent.get(name) for name in identity_fields):
        return False
    if stage == "containment-intent":
        return bool(
            prior_intent.get("stage") in {"fetch-result", "containment-result"}
            and prior_intent.get("completed") == current_intent.get("completed")
            and current_intent.get("cursor")
            == len(current_intent.get("completed", []))
        )
    if stage == "containment-result":
        prior_completed = prior_intent.get("completed")
        current_completed = current_intent.get("completed")
        return bool(
            prior_intent.get("stage") == "containment-intent"
            and prior_intent.get("cursor") == current_intent.get("cursor")
            and prior_intent.get("head") == current_intent.get("head")
            and prior_intent.get("argv") == current_intent.get("argv")
            and isinstance(prior_completed, list)
            and isinstance(current_completed, list)
            and current_completed[:-1] == prior_completed
        )
    return False


def _remote_observation_progress_matches_observed(
    state: Mapping[str, Any],
    progress: object,
    observed: object,
    *,
    event_at: object,
) -> bool:
    """Bind a final observation vector to its authenticated child progress."""

    if (
        not _remote_observation_progress_valid(state, progress)
        or not isinstance(progress, Mapping)
        or not isinstance(observed, Mapping)
        or set(observed)
        != {
            "exists",
            "oid",
            "contains_intended_head",
            "attempted_head_containment",
            "observed_at",
            "inflight_digest",
            "output_digest",
        }
    ):
        return False
    fetch = progress.get("fetch_result")
    heads = progress.get("heads")
    completed = progress.get("completed")
    if not (
        isinstance(fetch, Mapping)
        and isinstance(heads, list)
        and isinstance(completed, list)
    ):
        return False
    exists = fetch.get("exists")
    oid = fetch.get("oid")
    complete_containment = bool(
        exists is True
        and len(completed) == len(heads)
        and all(type(member.get("contained")) is bool for member in completed)
    )
    if complete_containment:
        vector_values: list[bool | None] = [
            bool(member["contained"]) for member in completed
        ]
    elif exists is False:
        vector_values = [False for _head in heads]
    else:
        exists = None
        oid = None
        vector_values = [None for _head in heads]
    integration = state.get("integration")
    push = integration.get("push") if isinstance(integration, Mapping) else None
    attempts = (
        list(push.get("attempted_heads", []))
        if isinstance(push, Mapping)
        else []
    )
    attempted_vector = [
        {"head": head, "contained": contained}
        for head, contained in zip(attempts, vector_values[-len(attempts) :])
    ]
    contains_intended = vector_values[-1] if vector_values else None
    progress_at = (
        parse_time(str(progress.get("recorded_at")))
        if _valid_utc_second(progress.get("recorded_at"))
        else None
    )
    observed_at = (
        parse_time(str(observed.get("observed_at")))
        if _valid_utc_second(observed.get("observed_at"))
        else None
    )
    recorded_event_at = (
        parse_time(str(event_at)) if _valid_utc_second(event_at) else None
    )
    return bool(
        progress_at is not None
        and observed_at is not None
        and recorded_event_at is not None
        and progress_at <= observed_at <= recorded_event_at
        and observed.get("exists") is exists
        and observed.get("oid") == oid
        and observed.get("contains_intended_head") is contains_intended
        and observed.get("attempted_head_containment") == attempted_vector
        and observed.get("inflight_digest") == fetch.get("inflight_digest")
        and observed.get("output_digest") == fetch.get("output_digest")
    )


def _replayed_remote_observation_completed(
    event: Mapping[str, Any],
    state: Mapping[str, Any],
    context: Mapping[str, Any],
) -> bool:
    """Require a final vector to immediately follow its restored progress."""

    integration = state.get("integration")
    intent = integration.get("intent") if isinstance(integration, Mapping) else None
    observed = (
        integration.get("observed") if isinstance(integration, Mapping) else None
    )
    replayed = context.get("remote_observation")
    return bool(
        isinstance(intent, Mapping)
        and intent.get("schema") == "forge-remote-observation-intent/1"
        and intent.get("phase") == "post-push"
        and isinstance(replayed, Mapping)
        and replayed.get("generation_digest") == event.get("generation_digest")
        and replayed.get("intent_event_digest") == event.get("previous_digest")
        and replayed.get("restore_event_digest") == event.get("previous_digest")
        and replayed.get("intent") == intent
        and isinstance(replayed.get("completed_progress"), Mapping)
        and _remote_observation_progress_matches_observed(
            state,
            replayed["completed_progress"],
            observed,
            event_at=event.get("at"),
        )
    )
