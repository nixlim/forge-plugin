"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import copy
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
from forge_cli.chain_core._merge_recovery_proof import _merge_recovery_proof_transition_valid as _merge_recovery_proof_transition_valid, _epoch_fetch_observation_predecessor_valid as _epoch_fetch_observation_predecessor_valid, _recovered_absent_rebase_intent_digest as _recovered_absent_rebase_intent_digest
from forge_cli.chain_core._merge_release import _merge_attempted_release_preconditions_valid as _merge_attempted_release_preconditions_valid, _merge_release_preconditions_valid as _merge_release_preconditions_valid
from forge_cli.chain_core._merge_scope import _validate_merge_scope_proof as _validate_merge_scope_proof, _merge_scope_event_binding_valid as _merge_scope_event_binding_valid, _merge_scope_transition_valid as _merge_scope_transition_valid
from forge_cli.chain_core._merge_scope_binding import _merge_scope_environment_contract as _merge_scope_environment_contract, _validate_merge_scope_request as _validate_merge_scope_request, _merge_retained_inflight as _merge_retained_inflight, _validate_merge_scope_fetch_binding as _validate_merge_scope_fetch_binding, _merge_scope_binding_names as _merge_scope_binding_names, _merge_full_patch_argv as _merge_full_patch_argv, _merge_scope_argv as _merge_scope_argv, _merge_scope_binding_validator as _merge_scope_binding_validator
from forge_cli.chain_core._merge_state_shape import _merge_gate_plan_valid as _merge_gate_plan_valid, _merge_epoch_valid as _merge_epoch_valid, _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view as _merge_revision9_compatibility_view, _merge_state_shape_valid as _merge_state_shape_valid, _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar
from forge_cli.chain_core._merge_transition import _merge_transition_valid as _merge_transition_valid, _merge_ingest_transition_valid as _merge_ingest_transition_valid
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot
from forge_cli.chain_core._remote_observation import _remote_containment_evidence_valid as _remote_containment_evidence_valid, _remote_observation_progress_valid as _remote_observation_progress_valid, _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed, _replayed_remote_observation_completed as _replayed_remote_observation_completed
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.policy import sha256_bytes, PolicyError, parse_policy
from pathlib import Path
from forge_cli import runtime
import subprocess


def _merge_ingest_binding(
    builders: Any,
    state: dict[str, object],
    source_event_digest: str,
    review: dict[str, object] | None,
) -> dict[str, object]:
    candidate = builders._candidate_binding_for_state("merge", state)
    if candidate is None:
        raise ValueError("merge candidate cannot be bound")
    preimage: dict[str, object] = {
        "schema": "forge-gate-binding/1",
        "source_record": {
            "chain_id": state["chain_id"],
            "event_digest": source_event_digest,
        },
        "candidate": candidate,
        "review": copy.deepcopy(review),
    }
    return {
        **preimage,
        "binding_id": sha256_bytes(canonical_bytes(preimage)),
    }


def _merge_gate_event_fact(
    prior: Mapping[str, object] | None,
    current: Mapping[str, object],
) -> tuple[str, dict[str, object]] | None:
    """Return the one gate fact introduced by a DM-014 gate event."""

    if prior is None:
        return None
    prior_steps = prior.get("steps")
    current_steps = current.get("steps")
    if not isinstance(prior_steps, Mapping) or not isinstance(
        current_steps, Mapping
    ):
        return None
    changed = {
        name
        for name in set(prior_steps) | set(current_steps)
        if prior_steps.get(name) != current_steps.get(name)
    }
    if len(changed) != 1:
        return None
    step_id = next(iter(changed))
    old_value = prior_steps.get(step_id)
    new_value = current_steps.get(step_id)
    if isinstance(new_value, list):
        old_runs = old_value if isinstance(old_value, list) else []
        if len(new_value) != len(old_runs) + 1 or new_value[:-1] != old_runs:
            return None
        fact = new_value[-1]
    else:
        fact = new_value
    if not isinstance(step_id, str) or not isinstance(fact, dict):
        return None
    return step_id, copy.deepcopy(fact)


def _merge_current_gate_facts(
    step_id: str,
    value: object,
    generation_digest: str,
) -> tuple[dict[str, object], ...] | None:
    """Validate the final current-generation fact(s) for one merge gate."""

    if isinstance(value, dict):
        facts = (value,)
    elif isinstance(value, list) and value and all(
        isinstance(item, dict) for item in value
    ):
        current = [item for item in value if isinstance(item, dict)]
        if step_id.startswith("stack:"):
            latest = current[-1]
            batch_id = latest.get("batch_id")
            cell_count = latest.get("cell_count")
            if (
                not isinstance(batch_id, str)
                or type(cell_count) is not int
                or cell_count <= 0
            ):
                return None
            facts = tuple(
                item for item in current if item.get("batch_id") == batch_id
            )
            if (
                len(facts) != cell_count
                or {item.get("cell_index") for item in facts}
                != set(range(1, cell_count + 1))
            ):
                return None
        else:
            facts = (current[-1],)
    else:
        return None
    expected_prefix = "gate-1: " if step_id == "gate-1" else "gate-2: "
    if any(
        fact.get("result") != "passed"
        or fact.get("generation_digest") != generation_digest
        or not isinstance(fact.get("criterion"), str)
        or not str(fact["criterion"]).startswith(expected_prefix)
        for fact in facts
    ):
        return None
    return tuple(copy.deepcopy(fact) for fact in facts)


def _merge_ingest_record_templates(
    builders: Any,
    journal: Any,
    event: dict[str, object],
    prior: dict[str, object] | None,
    current: dict[str, object],
    *,
    task: str,
    approval_required: bool,
    required_gate_ids: frozenset[str],
) -> tuple[tuple[dict[str, object], str | None], ...]:
    """Derive ordinary records solely from one authenticated merge delta."""

    event_name = event.get("event")
    templates: list[tuple[dict[str, object], str | None]] = []
    if event_name == "gate_recorded":
        introduced = _merge_gate_event_fact(prior, current)
        if introduced is None:
            return ()
        step_id, fact = introduced
        if step_id not in required_gate_ids:
            return ()
        result = fact.get("result")
        criterion = fact.get("criterion")
        if result not in {"passed", "failed"} or not isinstance(
            criterion, str
        ):
            return ()
        argv = fact.get("command_argv")
        transcript = fact.get("transcript")
        templates.append(
            (
                {
                    "type": "verification",
                    "task": task,
                    "criterion": criterion,
                    "method": "Forge CLI merge chain",
                    "check": (
                        " ".join(str(value) for value in argv)
                        if isinstance(argv, list) and argv
                        else step_id
                    ),
                    "result": result,
                    "observation": (
                        f"Forge CLI recorded merge {step_id} result {result}"
                    ),
                    "evidence": (
                        [transcript] if isinstance(transcript, str) else []
                    ),
                },
                step_id,
            )
        )

    if event_name in {"review_attached", "generation_carried_forward"}:
        authority_state = (
            prior
            if event_name == "generation_carried_forward" and prior is not None
            else current
        )
        review = builders._review_binding_for_state(authority_state)
        if (
            isinstance(review, dict)
            and review.get("verdict") in {"PASS", "BLOCK"}
            and review.get("reviewer_role") == "review-final"
        ):
            review_result = (
                "passed" if review["verdict"] == "PASS" else "failed"
            )
            review_state = current.get("review")
            verdict = (
                review_state.get("verdict")
                if isinstance(review_state, dict)
                else None
            )
            verdict_path = (
                verdict.get("verdict_path")
                if isinstance(verdict, dict)
                else None
            )
            templates.append(
                (
                    {
                        "type": "verification",
                        "task": task,
                        "criterion": journal.GATE_3_CRITERION,
                        "method": "independent review-final",
                        "check": "validated merge review-final verdict transport",
                        "result": review_result,
                        "observation": (
                            "Forge CLI recorded merge review-final verdict "
                            f"{review['verdict']}"
                        ),
                        "evidence": (
                            [verdict_path]
                            if isinstance(verdict_path, str)
                            else []
                        ),
                    },
                    None,
                )
            )

    if event_name in {
        "approval_recorded",
        "generation_carried_forward",
    }:
        authority_state = (
            prior
            if event_name == "generation_carried_forward" and prior is not None
            else current
        )
        approval = authority_state.get("approval")
        candidate = authority_state.get("candidate")
        gate4_approval = bool(
            approval_required
            and isinstance(approval, dict)
            and isinstance(candidate, dict)
            and approval.get("purpose") == "gate-4"
            and approval.get("chain_id") == authority_state.get("chain_id")
            and approval.get("candidate") == candidate.get("candidate_head")
            and approval.get("generation_digest")
            == candidate.get("generation_digest")
        )
        churn_approval = bool(
            isinstance(approval, dict)
            and approval.get("purpose") == "remote-churn"
            and _merge_current_authority_valid(authority_state)
        )
        if gate4_approval or churn_approval:
            templates.append(
                (
                    {
                        "type": "decision",
                        "task": task,
                        "resolution": (
                            "Forge merge chain Gate-4 approval recorded"
                            if gate4_approval
                            else "Forge merge chain remote-churn acknowledgement recorded"
                        ),
                        "outcome": "chain-approval",
                        "basis": [],
                    },
                    None,
                )
            )

    if event_name == "push_observed":
        integration = current.get("integration")
        push = (
            integration.get("push")
            if isinstance(integration, dict)
            else None
        )
        landed = push.get("landed_head") if isinstance(push, dict) else None
        if (
            isinstance(landed, str)
            and isinstance(prior, dict)
            and prior.get("state") != "pushed"
            and current.get("state") == "pushed"
            and builders._merge_current_head_contained(current)
        ):
            templates.append(
                (
                    {
                        "type": "decision",
                        "task": task,
                        "resolution": (
                            f"Forge merge chain landing recorded: {landed}"
                        ),
                        "outcome": "chain-landing",
                        "basis": [],
                    },
                    None,
                )
            )
    return tuple(templates)


def _ingest_allocation_records(
    canonical_repository: Path, run_state: Any
) -> list[dict[str, object]]:
    """Project the batch-owned activation marker before ingest ID allocation."""

    batch, builders, journal = runtime._coordination_modules()
    if journal._writer_contract_active(run_state.records):
        return list(run_state.records)
    preamble = batch.prepare_outbox_records(
        canonical_repository, run_state, ()
    )
    projected_state = batch._state_with_activation_preamble(
        run_state, preamble
    )
    if (
        len(preamble) != 1
        or not journal._writer_activation_marker(preamble[0])
        or not journal._writer_activation_id_is_allocated(
            projected_state.records, preamble[0]
        )
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    return list(projected_state.records)


def _verify_and_build_merge_ingest_records(
    *,
    canonical_repository: Path,
    run_id: str,
    run_dir: Path,
    inputs: dict[str, object],
    materialized: dict[str, object],
    outcome_map: object,
    events: Sequence[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
        ]
    ],
    existing_records: tuple[dict[str, object], ...] | None,
    base_records: list[dict[str, object]] | None,
    captured_state: bytes,
    captured_events: bytes,
    completed_proofs: list[str],
) -> tuple[Sequence[dict[str, object]], tuple[str, ...]]:
    """Prove a closed DM-014 landing and synthesize its ordinary journal rows."""

    _batch, builders, journal = runtime._coordination_modules()

    # Proof 3: the terminal, previously unbound merge chain belongs to the
    # repository selected by the caller.
    _require_ingest_proof("repository", completed_proofs)
    candidate = materialized.get("candidate")
    worktree = materialized.get("worktree")
    integration = materialized.get("integration")
    cleanup = materialized.get("cleanup")
    policy_source = materialized.get("policy_source")
    tier = materialized.get("tier")
    run_state = journal._scan_run(run_dir)
    proof_records = base_records if base_records is not None else run_state.records
    opening = proof_records[0] if proof_records else None
    try:
        opening_repository = (
            Path(str(opening.get("repo", ""))).resolve(strict=True)
            if isinstance(opening, dict)
            else None
        )
    except OSError as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    if (
        materialized.get("schema") != "forge-merge-chain/1"
        or materialized.get("kind") != "merge"
        or materialized.get("state") != "closed"
        or materialized.get("run") is not None
        or materialized.get("run_binding") is not None
        or materialized.get("journal_outbox") is not None
        or materialized.get("repository") != str(canonical_repository)
        or not isinstance(candidate, dict)
        or opening_repository != canonical_repository
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 4: the final generation names exact committed policy bytes.
    # ``policy_source``'s inner field names were not fixed by DM-014, so require
    # it to carry both normative values rather than accepting guessed aliases.
    _require_ingest_proof("policy", completed_proofs)
    if (
        not isinstance(policy_source, dict)
        or candidate.get("policy_digest") not in policy_source.values()
        or candidate.get("policy_commit") not in policy_source.values()
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    policy = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "show",
            f"{candidate['policy_commit']}:forge-project.md",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if (
        policy.returncode != 0
        or sha256_bytes(policy.stdout) != candidate.get("policy_digest")
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    try:
        parsed_policy = parse_policy(str(candidate["policy_commit"]), policy.stdout)
    except (KeyError, PolicyError, UnicodeError) as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc

    # Proof 5: the generation is well formed and is still the exact live chain
    # materialization under task-03's native event lock.
    _require_ingest_proof("generation", completed_proofs)
    generation = builders._merge_generation(candidate)
    if generation is None:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    generation_digest = str(candidate["generation_digest"])
    candidate_head = str(candidate["candidate_head"])
    remote_tip = str(candidate["remote_tip"])
    _prove_ingest_live_chain(
        canonical_repository,
        str(materialized["chain_id"]),
        materialized,
        captured_state,
        captured_events,
    )

    # Proof 6: every gate required by the final policy/tier is present, passing,
    # and bound to the current generation.
    _require_ingest_proof("current-gates", completed_proofs)
    if (
        not isinstance(tier, dict)
        or type(tier.get("control")) is not bool
        or not isinstance(tier.get("categories"), list)
        or not all(
            isinstance(category, str) and category
            for category in tier["categories"]
        )
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    required_gate_ids = {
        "gate-1",
        "assertion-sensor",
        *(
            f"stack:{category}"
            for category in sorted(set(str(value) for value in tier["categories"]))
        ),
        *(
            f"invariant:{invariant['row_number']}"
            for invariant in parsed_policy.invariants
            if invariant["enforcement"] == "merge"
        ),
    }
    steps = materialized.get("steps")
    if not isinstance(steps, dict) or any(
        _merge_current_gate_facts(
            gate_id, steps.get(gate_id), generation_digest
        )
        is None
        for gate_id in required_gate_ids
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proofs 7–10: re-open the exact package, then bind role, iteration, and
    # verdict independently in the normative order.
    review = materialized.get("review")
    review_binding = builders._review_binding_for_state(materialized)
    request = review.get("request") if isinstance(review, dict) else None
    verdict = review.get("verdict") if isinstance(review, dict) else None

    _require_ingest_proof("review-package", completed_proofs)
    if (
        not isinstance(review, dict)
        or not isinstance(review_binding, dict)
        or not isinstance(request, dict)
        or not isinstance(verdict, dict)
        or request.get("candidate") != candidate_head
        or not isinstance(request.get("package"), str)
        or not isinstance(request.get("package_digest"), str)
        or SHA256_RE.fullmatch(str(request["package_digest"])) is None
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    package = _read_ingest_input(
        canonical_repository,
        str(request["package"]),
        "ingest.reviewer_package",
    )
    if sha256_bytes(package) != request.get("package_digest"):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    _require_ingest_proof("reviewer-role", completed_proofs)
    if (
        review_binding.get("reviewer_role") != "review-final"
        or request.get("reviewer") != "review-final"
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    _require_ingest_proof("reviewer-iteration", completed_proofs)
    if (
        type(review.get("iteration")) is not int
        or int(review["iteration"]) <= 0
        or request.get("iteration") != review.get("iteration")
        or review_binding.get("iteration") != review.get("iteration")
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    _require_ingest_proof("reviewer-verdict", completed_proofs)
    if (
        review_binding.get("verdict") != "PASS"
        or verdict.get("verdict") != "PASS"
        or verdict.get("candidate") != candidate_head
        or verdict.get("package_digest") != request.get("package_digest")
        or review_binding.get("package_digest") != request.get("package_digest")
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 11: a control generation requires authenticated operator authority.
    # An exact remote-churn acknowledgement is the current authority only after
    # replay has proved the retained Gate-4/review tuple that it re-armed.
    _require_ingest_proof("operator-approval", completed_proofs)
    approval = materialized.get("approval")
    approval_required = bool(
        tier["control"]
        or isinstance(approval, Mapping)
        and approval.get("purpose") == "remote-churn"
    )
    if approval_required and not _merge_current_authority_valid(materialized):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 12: recompute the exact DM-014 range and prove the durable remote
    # landing observation.  Closing-HEAD containment remains a separate proof.
    _require_ingest_proof("landing-proof", completed_proofs)
    if (
        not isinstance(worktree, dict)
        or set(worktree) != {"path", "git_dir", "common_dir", "claim"}
        or not isinstance(worktree.get("claim"), dict)
        or set(worktree["claim"]) != {"status", "path", "inode", "digest"}
        or worktree["claim"].get("status") != "released"
        or not isinstance(integration, dict)
        or set(integration)
        != {
            "condition",
            "primary_condition",
            "epoch",
            "remote_movement_count",
            "intent",
            "observed",
            "pre_rebase",
            "conflict",
            "push",
        }
        or integration.get("condition") != "none"
        or integration.get("primary_condition") != "none"
        or not isinstance(cleanup, dict)
        or cleanup.get("condition") != "none"
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    diff = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "diff",
            f"{remote_tip}...{candidate_head}",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    names = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "diff",
            "--name-only",
            "-z",
            f"{remote_tip}...{candidate_head}",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if (
        diff.returncode != 0
        or names.returncode != 0
        or sha256_bytes(diff.stdout) != candidate.get("diff_sha256")
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    try:
        changed_paths = tuple(
            item.decode("utf-8") for item in names.stdout.split(b"\0") if item
        )
    except UnicodeDecodeError as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    if not changed_paths or not all(
        journal._valid_scope_item(path) for path in changed_paths
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    push = integration.get("push")
    observed = integration.get("observed")
    if (
        not isinstance(push, dict)
        or set(push)
        != {
            "expected_old_tip",
            "intended_head",
            "destination_ref",
            "intended_at",
            "result",
            "attempted_heads",
            "landed_head",
        }
        or push.get("intended_head") != candidate_head
        or push.get("destination_ref") != candidate.get("destination_ref")
        or push.get("landed_head") != candidate_head
        or not isinstance(push.get("attempted_heads"), list)
        or not push["attempted_heads"]
        or push["attempted_heads"][-1] != candidate_head
        or not all(
            isinstance(head, str) and COMMIT_RE.fullmatch(head) is not None
            for head in push["attempted_heads"]
        )
        or not isinstance(observed, dict)
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
        or observed.get("exists") is not True
        or observed.get("contains_intended_head") is not True
        or not isinstance(observed.get("oid"), str)
        or COMMIT_RE.fullmatch(str(observed["oid"])) is None
        or not isinstance(observed.get("attempted_head_containment"), list)
        or len(observed["attempted_head_containment"])
        != len(push["attempted_heads"])
        or any(
            not isinstance(entry, dict)
            or set(entry) != {"head", "contained"}
            or entry.get("head") != head
            or type(entry.get("contained")) is not bool
            for entry, head in zip(
                observed["attempted_head_containment"],
                push["attempted_heads"],
            )
        )
        or observed["attempted_head_containment"][-1].get("contained") is not True
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    remote_contains = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "merge-base",
            "--is-ancestor",
            candidate_head,
            str(observed["oid"]),
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if remote_contains.returncode != 0:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 13: every DM-014 transition is monotonic.  This is intentionally
    # deferred until after the landing proof instead of being conflated with
    # digest replay.
    _require_ingest_proof("monotonic-transitions", completed_proofs)
    merge_context: dict[str, object] = {}
    merge_history: list[dict[str, Any]] = []
    for event, prior_state, event_state in events:
        if not _merge_ingest_transition_valid(
            builders,
            event,
            prior_state,
            event_state,
            context=merge_context,
            history=tuple(merge_history),
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        merge_history.append(copy.deepcopy(event))

    # Proof 14: the landed head is contained by the caller's proposed closing
    # HEAD, independently of the durable remote observation above.
    _require_ingest_proof("closing-head-containment", completed_proofs)
    closing_head = inputs.get("closing_head")
    if (
        not isinstance(closing_head, str)
        or COMMIT_RE.fullmatch(closing_head) is None
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    closing_contains = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "merge-base",
            "--is-ancestor",
            candidate_head,
            closing_head,
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if closing_contains.returncode != 0:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 15: the explicit task belongs to this run/repository and remains
    # active until this one terminal batch is appended.
    _require_ingest_proof("task-membership", completed_proofs)
    task = inputs.get("task")
    task_status = inputs.get("task_status")
    task_records = [
        record
        for record in proof_records
        if record.get("type") == "task" and record.get("id") == task
    ]
    if (
        not isinstance(task, str)
        or not task_records
        or task_records[-1].get("status") != "active"
        or task_status not in journal.TERMINAL_TASK_STATUSES
        or not isinstance(outcome_map, dict)
        or set(outcome_map)
        != {"schema", "chain_id", "task", "task_status", "event_digests"}
        or outcome_map.get("schema")
        != "forge-chain-ingest-outcome-map/1"
        or outcome_map.get("chain_id") != materialized.get("chain_id")
        or outcome_map.get("task") != task
        or outcome_map.get("task_status") != task_status
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    if existing_records is not None:
        terminal_tasks = [
            record
            for record in existing_records
            if record.get("type") == "task" and record.get("id") == task
        ]
        if (
            len(terminal_tasks) != 1
            or terminal_tasks[0].get("status") != task_status
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    task_record = task_records[-1]

    # Proof 16: every changed path is admitted by both task and run scope.
    _require_ingest_proof("scope-membership", completed_proofs)
    files = task_record.get("files")
    if not isinstance(files, list) or not files:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    try:
        mechanical_outputs = _committed_changelog_output_paths(parsed_policy)
    except PolicyError as exc:
        raise journal.CoordinationRefusal(
            builders.INGEST_PROOF_INVALID
        ) from exc
    for path in changed_paths:
        if path in mechanical_outputs:
            continue
        if not any(
            isinstance(pattern, str)
            and journal.pathspec_contained(path, pattern)
            for pattern in files
        ) or not any(
            journal.pathspec_contained(path, admitted)
            for admitted in run_state.scope
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    assert isinstance(outcome_map, dict)
    if (
        not isinstance(outcome_map.get("event_digests"), list)
        or not all(
            isinstance(value, str) and SHA256_RE.fullmatch(value) is not None
            for value in outcome_map["event_digests"]
        )
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    replay_entries = tuple(
        (event, prior, event_state, (), str(event["digest"]))
        for event, prior, event_state in events
    )
    projected = _ingest_allocation_records(
        canonical_repository, run_state
    )
    records: list[dict[str, object]] = []
    selected_digests: list[str] = []
    covered_gates: set[str] = set()
    captured = _ingest_captured_paths(
        canonical_repository, run_dir, inputs
    )
    captured_citations = [
        captured["state_file"],
        captured["events_file"],
        captured["outcome_map"],
    ]
    gate3_count = 0
    approval_count = 0
    landing_count = 0
    for event, prior, event_state in events:
        accepted_event = False
        templates = _merge_ingest_record_templates(
            builders,
            journal,
            event,
            prior,
            event_state,
            task=task,
            approval_required=approval_required,
            required_gate_ids=frozenset(required_gate_ids),
        )
        for template, gate_id in templates:
            record = copy.deepcopy(template)
            record_type = str(record["type"])
            record["id"] = builders._allocate_id(projected, record_type)
            record["run_id"] = run_id
            record["recorded_at"] = event["at"]
            review_for_binding = (
                review_binding
                if record.get("criterion") == journal.GATE_3_CRITERION
                else None
            )
            record["binding"] = _merge_ingest_binding(
                builders,
                event_state,
                str(event["digest"]),
                review_for_binding,
            )
            _capture_ingest_record_evidence(
                canonical_repository,
                run_dir,
                record,
            )
            if record.get("outcome") == "chain-landing":
                record["basis"] = list(captured_citations)
            binding = record["binding"]
            assert isinstance(binding, dict)
            if not builders._binding_matches_source_fact(
                binding,
                record,
                event,
                prior,
                event_state,
                family="merge",
            ) or not builders._binding_is_current(
                materialized,
                binding,
                record,
                event,
                prior,
                event_state,
                replay_entries,
                chain_family="merge",
            ):
                continue
            accepted_event = True
            if gate_id is not None:
                covered_gates.add(gate_id)
            if record.get("criterion") == journal.GATE_3_CRITERION:
                gate3_count += 1
            if record.get("outcome") == "chain-approval":
                approval_count += 1
            if record.get("outcome") == "chain-landing":
                landing_count += 1
            records.append(record)
            projected.append(record)
        if accepted_event:
            selected_digests.append(str(event["digest"]))

    if (
        selected_digests != outcome_map["event_digests"]
        or covered_gates != required_gate_ids
        or gate3_count != 1
        or landing_count != 1
        or approval_count != (1 if approval_required else 0)
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    terminal = {
        "type": "task",
        "id": task,
        "status": task_status,
        "goal": task_record["goal"],
        "acceptance": copy.deepcopy(task_record["acceptance"]),
        "files": copy.deepcopy(task_record["files"]),
        "run_id": run_id,
        "recorded_at": events[-1][0]["at"],
    }
    records.append(terminal)
    completed_records = tuple(records)
    if existing_records is not None:
        if completed_records != existing_records:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        completed_records = existing_records
    completed = tuple(completed_proofs)
    if completed != INGEST_PROOF_ORDER:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    return completed_records, completed
