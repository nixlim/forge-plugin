"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import copy
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
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
from forge_cli.chain_core._merge_release import _merge_attempted_release_preconditions_valid as _merge_attempted_release_preconditions_valid, _merge_release_preconditions_valid as _merge_release_preconditions_valid
from forge_cli.chain_core._merge_scope import _validate_merge_scope_proof as _validate_merge_scope_proof, _merge_scope_event_binding_valid as _merge_scope_event_binding_valid, _merge_scope_transition_valid as _merge_scope_transition_valid
from forge_cli.chain_core._merge_scope_binding import _merge_scope_environment_contract as _merge_scope_environment_contract, _validate_merge_scope_request as _validate_merge_scope_request, _merge_retained_inflight as _merge_retained_inflight, _validate_merge_scope_fetch_binding as _validate_merge_scope_fetch_binding, _merge_scope_binding_names as _merge_scope_binding_names, _merge_full_patch_argv as _merge_full_patch_argv, _merge_scope_argv as _merge_scope_argv, _merge_scope_binding_validator as _merge_scope_binding_validator
from forge_cli.chain_core._merge_state_shape import _merge_gate_plan_valid as _merge_gate_plan_valid, _merge_epoch_valid as _merge_epoch_valid, _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view as _merge_revision9_compatibility_view, _merge_state_shape_valid as _merge_state_shape_valid, _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot
from forge_cli.chain_core._remote_observation import _remote_containment_evidence_valid as _remote_containment_evidence_valid, _remote_observation_progress_valid as _remote_observation_progress_valid, _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed, _replayed_remote_observation_completed as _replayed_remote_observation_completed
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.policy import sha256_bytes


def _published_recovery_evidence_valid(
    value: object,
    *,
    path: Path,
    validator: Callable[[Any], dict[str, Any]],
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "path",
        "device",
        "inode",
        "digest",
        "record",
    }:
        return False
    try:
        record = validator(copy.deepcopy(value.get("record")))
    except (TypeError, ValueError):
        return False
    return bool(
        value.get("path") == str(path)
        and _valid_nonnegative_int(value.get("device"))
        and _valid_nonnegative_int(value.get("inode"))
        and SHA256_RE.fullmatch(str(value.get("digest", ""))) is not None
        and value.get("digest") == sha256_bytes(canonical_bytes(record))
    )


def _recovery_value_carries_inflight(value: object, digest: str) -> bool:
    """Find only an explicitly named child-result fence digest."""

    if isinstance(value, Mapping):
        return (
            value.get("inflight_digest") == digest
            or value.get("fence_digest") == digest
            or any(
                _recovery_value_carries_inflight(member, digest)
                for name, member in value.items()
                if name != "recovery_proof"
            )
        )
    if isinstance(value, list):
        return any(
            _recovery_value_carries_inflight(member, digest) for member in value
        )
    return False


def _recovery_cleanup_result_matches(
    event: Mapping[str, Any],
    state: Mapping[str, Any],
    intent: Mapping[str, Any],
    *,
    intent_digest: str,
    fence_digest: str,
    fence_operation: str,
) -> bool:
    payload = event.get("payload")
    results = (
        payload.get("cleanup_results") if isinstance(payload, Mapping) else None
    )
    result = (
        results[0]
        if isinstance(results, list)
        and len(results) == 1
        and isinstance(results[0], Mapping)
        else None
    )
    process = result.get("process") if isinstance(result, Mapping) else None
    return bool(
        event.get("event") == "cleanup_result"
        and isinstance(result, Mapping)
        and isinstance(process, Mapping)
        and result.get("intent_event_digest") == intent_digest
        and result.get("fence_operation") == fence_operation
        and process.get("fence_digest") == fence_digest
        and _merge_cleanup_step_result_valid(
            result, state, intent, intent_digest
        )
    )


def _classify_merge_recovery_lifecycle(
    state: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    *,
    fence_record: Mapping[str, Any],
    fence_digest: str,
) -> str | None:
    """Recompute the closed lifecycle label from authenticated prefix events."""

    operation = fence_record.get("operation")
    intent_digest = fence_record.get("intent_digest")
    chain_id = state.get("chain_id")
    if (
        operation
        not in {
            "fetch",
            "tip-resolution",
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
        or not isinstance(intent_digest, str)
        or SHA256_RE.fullmatch(intent_digest) is None
        or SHA256_RE.fullmatch(fence_digest) is None
    ):
        return None
    events = [event for event in history if isinstance(event, Mapping)]
    by_digest = {
        str(event.get("digest")): event
        for event in events
        if SHA256_RE.fullmatch(str(event.get("digest", ""))) is not None
    }
    attributed = by_digest.get(intent_digest)
    prefix = "fetch" if operation in {"fetch", "tip-resolution"} else str(operation)
    result_names: set[str]
    intent_valid = False

    if operation in {"fetch", "tip-resolution"}:
        intent_valid = bool(
            attributed is not None and attributed.get("event") == "fetch_intent"
        )
        result_names = {"fetch_result"}
        if not intent_valid:
            return None
        fetch_results = [
            event
            for event in events
            if event.get("event") == "fetch_result"
            and event.get("previous_digest") == intent_digest
        ]
        raw_fetch_results: list[Mapping[str, Any]] = []
        for event in events:
            if event.get("event") != "condition_recorded":
                continue
            payload = event.get("payload")
            delta = payload.get("delta") if isinstance(payload, Mapping) else None
            integration = (
                delta.get("integration") if isinstance(delta, Mapping) else None
            )
            observation = (
                integration.get("intent")
                if isinstance(integration, Mapping)
                else None
            )
            if (
                isinstance(observation, Mapping)
                and observation.get("schema") == _EPOCH_FETCH_OBSERVATION_SCHEMA
                and observation.get("fetch_intent_event_digest") == intent_digest
                and observation.get("child_result", {}).get("inflight_digest")
                == fence_digest
                and _epoch_fetch_observation_record_valid(state, observation)
            ):
                raw_fetch_results.append(event)
        if len(fetch_results) > 1 or len(raw_fetch_results) > 1:
            return None
        if raw_fetch_results:
            return "fetch-result-persisted"
        if fetch_results:
            result_event = fetch_results[0]
            payload = result_event.get("payload")
            delta = payload.get("delta") if isinstance(payload, Mapping) else None
            integration = (
                delta.get("integration") if isinstance(delta, Mapping) else None
            )
            result_intent = (
                integration.get("intent")
                if isinstance(integration, Mapping)
                else None
            )
            result = (
                result_intent.get("result")
                if isinstance(result_intent, Mapping)
                else None
            )
            binding = (
                payload.get("scope_fetch_binding")
                if isinstance(payload, Mapping)
                else None
            )
            proof = (
                payload.get("scope_proof")
                if isinstance(payload, Mapping)
                else None
            )
            copied_fence = _recovery_value_carries_inflight(
                binding, fence_digest
            )
            failed_result = bool(
                result_intent is not None
                and result_intent.get("operation") == "fetch-result"
                and result == "failed"
                and proof is None
                and (
                    (binding is None and result_event.get("generation_digest") is None)
                    or (isinstance(binding, Mapping) and copied_fence)
                )
            )
            successful_result = bool(
                result_intent is not None
                and result_intent.get("operation") == "fetch-result"
                and result == "success"
                and isinstance(binding, Mapping)
                and copied_fence
            )
            if not (failed_result or successful_result):
                return None
            return "fetch-result-persisted"
    elif operation == "gate":
        result_names = {"gate_recorded"}
        result_facts = [
            event
            for event in events
            if event.get("event") == "gate_recorded"
            and _recovery_value_carries_inflight(event.get("payload"), fence_digest)
            and any(
                isinstance(member, Mapping)
                and member.get("gate_intent_digest") == intent_digest
                for member in (
                    event.get("payload", {}).get("delta", {}).get("steps", {}).values()
                    if isinstance(event.get("payload"), Mapping)
                    and isinstance(event.get("payload", {}).get("delta"), Mapping)
                    and isinstance(
                        event.get("payload", {}).get("delta", {}).get("steps"),
                        Mapping,
                    )
                    else ()
                )
            )
        ]
        if result_facts:
            intent_valid = True
        else:
            integration = state.get("integration")
            epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
            plan = epoch.get("gate_plan") if isinstance(epoch, Mapping) else None
            cursor = plan.get("cursor") if isinstance(plan, Mapping) else None
            suite = plan.get("suite") if isinstance(plan, Mapping) else None
            if (
                isinstance(plan, Mapping)
                and plan.get("status") == "sealed"
                and _valid_nonnegative_int(cursor)
                and isinstance(suite, list)
                and int(cursor) < len(suite)
                and isinstance(suite[int(cursor)], Mapping)
            ):
                authorizer = (
                    str(plan.get("seal_event_digest"))
                    if int(cursor) == 0
                    else next(
                        (
                            str(event.get("digest"))
                            for event in reversed(events)
                            if event.get("event") == "gate_recorded"
                        ),
                        "",
                    )
                )
                member = suite[int(cursor)]
                try:
                    intent_valid = merge_gate_intent_digest(
                        chain_id=str(chain_id),
                        epoch_intent_digest=str(epoch.get("intent_digest")),
                        seal_event_digest=str(plan.get("seal_event_digest")),
                        generation_digest=str(plan.get("generation_digest")),
                        policy_digest=str(plan.get("policy_digest")),
                        suite_digest=str(plan.get("suite_digest")),
                        cursor=int(cursor),
                        kind=str(member.get("kind")),
                        gate_id=str(member.get("id")),
                        authorizing_event_digest=authorizer,
                    ) == intent_digest
                except (TypeError, ValueError):
                    intent_valid = False
    elif operation == "remote-observation":
        result_names = {"condition_recorded", "cleanup_result"}
        for event in events:
            intent = _recovery_event_intent(event)
            if not isinstance(intent, Mapping):
                continue
            base = {
                name: copy.deepcopy(intent.get(name))
                for name in (
                    "schema",
                    "transaction",
                    "chain_id",
                    "attempt_identity",
                    "phase",
                    "push_intent_digest",
                )
            }
            if (
                base.get("schema") == "forge-remote-observation-intent/1"
                and base.get("transaction") == "merge"
                and base.get("chain_id") == chain_id
                and base.get("phase") in {"final-prepush", "post-push"}
                and sha256_bytes(canonical_bytes(base)) == intent_digest
            ):
                intent_valid = True
                break
        if not intent_valid:
            cleanup_intent = _recovery_cleanup_intent(attributed)
            intent_valid = bool(
                attributed is not None
                and attributed.get("event") == "cleanup_intent"
                and isinstance(cleanup_intent, Mapping)
                and cleanup_intent.get("fence_operation") == operation
                and _merge_cleanup_intent_valid(cleanup_intent, state)
            )
    elif operation in {"rebase", "continue", "abort"}:
        result_names = {"rebase_intent"}
        intent = _recovery_event_intent(attributed) if attributed is not None else None
        intent_valid = bool(
            attributed is not None
            and attributed.get("event") in {"rebase_intent", "condition_recorded"}
            and isinstance(intent, Mapping)
            and intent.get("operation") == operation
        )
    elif operation == "push":
        result_names = {"condition_recorded"}
        intent_valid = bool(
            attributed is not None and attributed.get("event") == "push_intent"
        )
    elif operation in {"worktree-remove", "branch-delete"}:
        result_names = {"cleanup_result"}
        cleanup_intent = _recovery_cleanup_intent(attributed)
        intent_valid = bool(
            attributed is not None
            and attributed.get("event") == "cleanup_intent"
            and isinstance(cleanup_intent, Mapping)
            and cleanup_intent.get("fence_operation") == operation
            and _merge_cleanup_intent_valid(cleanup_intent, state)
        )
    else:  # containment
        result_names = {"condition_recorded", "cleanup_result", "rebase_intent"}
        cleanup_intent = _recovery_cleanup_intent(attributed)
        intent_valid = bool(
            attributed is not None
            and (
                attributed.get("event")
                in {"condition_recorded", "fetch_result", "rebase_intent"}
                or attributed.get("event") == "cleanup_intent"
                and isinstance(cleanup_intent, Mapping)
                and cleanup_intent.get("fence_operation") == operation
                and _merge_cleanup_intent_valid(cleanup_intent, state)
            )
        )
        if not intent_valid:
            intent_valid = any(
                isinstance(_recovery_event_intent(event), Mapping)
                and sha256_bytes(
                    canonical_bytes(dict(_recovery_event_intent(event) or {}))
                )
                == intent_digest
                for event in events
            )
    if not intent_valid:
        return None

    cleanup_intent = _recovery_cleanup_intent(attributed)
    results = []
    for event in events:
        if event.get("event") not in result_names:
            continue
        if event.get("event") == "cleanup_result" and isinstance(
            cleanup_intent, Mapping
        ):
            matched = _recovery_cleanup_result_matches(
                event,
                state,
                cleanup_intent,
                intent_digest=intent_digest,
                fence_digest=fence_digest,
                fence_operation=str(operation),
            )
        else:
            matched = _recovery_value_carries_inflight(
                event.get("payload"), fence_digest
            )
        if matched:
            results.append(event)
    if len(results) > 1:
        return None
    return f"{prefix}-result-persisted" if results else f"{prefix}-intent-pending"
