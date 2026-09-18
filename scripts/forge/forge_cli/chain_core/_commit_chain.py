"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import dataclasses
from forge_cli.chain_core._activation import _ChainActivationSnapshot as _ChainActivationSnapshot, _chain_activation_ownership_summary as _chain_activation_ownership_summary, _validate_chain_activation_lineage as _validate_chain_activation_lineage
from forge_cli.chain_core._activation_outbox import _resolve_chain_activation_projection as _resolve_chain_activation_projection, _require_no_pending_chain_activation_outbox as _require_no_pending_chain_activation_outbox
from forge_cli.chain_core._bootstrap_observation import _bootstrap_fetch_observation_record_valid as _bootstrap_fetch_observation_record_valid, _bootstrap_fetch_observation_transition_valid as _bootstrap_fetch_observation_transition_valid
from forge_cli.chain_core._candidate_v2 import candidate_is_v2 as candidate_is_v2, _candidate_binding_for_state_with_candidate_v2 as _candidate_binding_for_state_with_candidate_v2, _binding_shape_valid_with_candidate_v2 as _binding_shape_valid_with_candidate_v2, _event_batch_records_with_candidate_v2 as _event_batch_records_with_candidate_v2, _binding_matches_source_fact_with_candidate_v2 as _binding_matches_source_fact_with_candidate_v2, _binding_is_current_with_candidate_v2 as _binding_is_current_with_candidate_v2, _commit_transition_valid_with_candidate_v2 as _commit_transition_valid_with_candidate_v2
from forge_cli.chain_core._chain_batch_authorize import _authorize_chain_batch as _authorize_chain_batch
from forge_cli.chain_core._chain_batch_carrier import _coordination_refusal as _coordination_refusal, _drain_chain_batch_capability as _drain_chain_batch_capability, _validate_chain_batch_target as _validate_chain_batch_target, _prevalidate_chain_batch_carrier as _prevalidate_chain_batch_carrier
from forge_cli.chain_core._chain_state import validate_state as validate_state
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._fenced_child import _BlockedFenceChild as _BlockedFenceChild, _pipe_cloexec as _pipe_cloexec, _read_child_ack as _read_child_ack, _waitpid_nohang as _waitpid_nohang, _wait_for_child_exit as _wait_for_child_exit, _spawn_blocked_fence_child as _spawn_blocked_fence_child, _terminate_fenced_group as _terminate_fenced_group, _stop_unstarted_child as _stop_unstarted_child, _collect_fenced_child as _collect_fenced_child
from forge_cli.chain_core._ingest_capture import _read_ingest_input as _read_ingest_input, _capture_ingest_blob as _capture_ingest_blob, _capture_run_evidence as _capture_run_evidence, _capture_ingest_record_evidence as _capture_ingest_record_evidence
from forge_cli.chain_core._ingest_currency import _ingest_captured_paths as _ingest_captured_paths, _ingest_step_is_current as _ingest_step_is_current, _ingest_secret_scan_is_current as _ingest_secret_scan_is_current, _prove_ingest_live_chain as _prove_ingest_live_chain
from forge_cli.chain_core._ingest_merge import _merge_ingest_binding as _merge_ingest_binding, _merge_gate_event_fact as _merge_gate_event_fact, _merge_current_gate_facts as _merge_current_gate_facts, _merge_ingest_record_templates as _merge_ingest_record_templates, _verify_and_build_merge_ingest_records as _verify_and_build_merge_ingest_records, _ingest_allocation_records as _ingest_allocation_records
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
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot
from forge_cli.chain_core._remote_observation import _remote_containment_evidence_valid as _remote_containment_evidence_valid, _remote_observation_progress_valid as _remote_observation_progress_valid, _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed, _replayed_remote_observation_completed as _replayed_remote_observation_completed
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.chain_core._storage import _ChainStoragePrimitives as _ChainStoragePrimitives
from forge_cli import runtime, fresh_evals as fresh_eval_module, candidate as candidate_module
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence, Callable, Iterable
from forge_cli.envelope import Refusal, V2ReasonCode, FrozenError, REVISION9_OUTPUT_SCHEMA, ReasonCode
from forge_cli.policy import PolicyError, parse_policy, sha256_bytes, Policy
import copy
import json
import threading
import contextlib
import os
import datetime as dt


@dataclasses.dataclass
class CLIOptions:
    json: bool = False
    verbose: bool = False
    chain_id: str | None = None
    repo: str | None = None
    run_id: str | None = None
    original_argv: tuple[str, ...] = ()
    revision9_face: bool = False


def register_activation_reservation_seam() -> None:
    """Install the grammar-aware first-use scanner without healing other seams."""

    batch, builders, _journal = runtime._coordination_modules()
    existing_scanner = builders._require_no_pending_activation_outbox
    original_scanner = getattr(
        builders, "_FORGE_CLI_ORIGINAL_ACTIVATION_SCANNER", None
    )
    if original_scanner is None:
        if (
            getattr(existing_scanner, "__name__", None)
            != "_require_no_pending_activation_outbox"
            or getattr(existing_scanner, "__module__", None)
            != builders.__name__
        ):
            raise RuntimeError("activation reservation scanner registration conflict")
        builders._FORGE_CLI_ORIGINAL_ACTIVATION_SCANNER = existing_scanner
        original_scanner = existing_scanner
    if existing_scanner is original_scanner:
        builders._require_no_pending_activation_outbox = (
            _require_no_pending_chain_activation_outbox
        )
    elif existing_scanner is not _require_no_pending_chain_activation_outbox:
        raise RuntimeError("activation reservation scanner registration conflict")


def _validate_bound_chain_state(state: Mapping[str, Any]) -> None:
    """Re-prove a bound chain against current journal and committed policy."""

    binding = state.get("run_binding")
    if not isinstance(binding, Mapping):
        return
    batch, _builders, journal = runtime._coordination_modules()
    repository = Path(str(binding.get("repository", "")))
    run_id = str(binding.get("run_id", ""))
    task_id = str(binding.get("task_id", ""))
    try:
        canonical_repository, state_root = journal._resolve_repository(
            repository, "chain binding"
        )
        run_dir = state_root / ".codex-orchestrator" / "runs" / run_id
        with batch.batch_lock(run_dir, create=False):
            run_state = journal._scan_run(run_dir)
            opening = run_state.records[0] if run_state.records else None
            if (
                run_state.disposition != "open"
                or not isinstance(opening, dict)
                or Path(str(opening.get("repo", ""))).resolve(strict=True)
                != canonical_repository
            ):
                raise ValueError("run is terminal or belongs to another repository")
            tasks = [
                record
                for record in run_state.records
                if record.get("type") == "task" and record.get("id") == task_id
            ]
            if not tasks or tasks[-1].get("status") != "active":
                raise ValueError("bound task is not active")
            files = tasks[-1].get("files")
            if not isinstance(files, list) or not files:
                raise ValueError("bound task files are malformed")
            policy_source = state.get("policy_source")
            if not isinstance(policy_source, Mapping):
                raise ValueError("chain policy source is malformed")
            policy = subprocess.run(
                [
                    "git",
                    "-C",
                    str(canonical_repository),
                    "show",
                    f"{policy_source.get('sha')}:forge-project.md",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            if (
                policy.returncode != 0
                or sha256_bytes(policy.stdout) != policy_source.get("digest")
                or policy_source.get("digest") != binding.get("policy_digest")
            ):
                raise ValueError("committed policy identity changed")
            try:
                parsed_policy = parse_policy(
                    str(policy_source.get("sha")), policy.stdout
                )
                mechanical_outputs = _committed_changelog_output_paths(
                    parsed_policy
                )
            except (PolicyError, UnicodeError) as exc:
                raise ValueError("committed policy is malformed") from exc
            for path in state.get("paths", ()):
                if path in mechanical_outputs:
                    continue
                if not isinstance(path, str) or not any(
                    journal.pathspec_contained(path, pattern)
                    for pattern in files
                    if isinstance(pattern, str)
                ):
                    raise ValueError(
                        f"chain path {path} is outside bound task membership"
                    )
                if not any(
                    journal.pathspec_contained(path, admitted)
                    for admitted in run_state.scope
                ):
                    raise ValueError(
                        f"chain path {path} is outside admitted run scope"
                    )
    except (OSError, RuntimeError, ValueError, journal.CoordinationRefusal) as exc:
        raise Refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: chain transition refused — run/task binding is invalid",
            expected="open run, active task, matching repository/scope/policy binding",
            observed=str(exc),
            remediation=_forge_command(state, "status"),
            chain=state,
        ) from exc


def _user_skip(state: Mapping[str, Any], gate_id: str) -> dict[str, Any] | None:
    value = state["steps"].get("user_skips", {})
    if not isinstance(value, dict):
        return None
    record = value.get(gate_id)
    return record if isinstance(record, dict) else None


def _gate_one_complete(state: Mapping[str, Any]) -> bool:
    runs = state["steps"].get("gate-1")
    if _user_skip(state, "gate-1") is not None:
        return True
    if not isinstance(runs, list) or len(runs) < 2:
        return False
    candidate = state["candidate"].get("sha256")
    current_runs = [
        record
        for record in runs
        if isinstance(record, dict) and record.get("candidate") == candidate
    ]
    if len(current_runs) < 2:
        return False
    last_two = current_runs[-2:]
    return all(
        record.get("result") == "passed" and not record.get("pair_voided")
        for record in last_two
    ) and last_two[0].get("env_fingerprint") == last_two[1].get("env_fingerprint")


def _latest_current_pass(state: Mapping[str, Any], step_id: str) -> bool:
    value = state["steps"].get(step_id)
    candidate = state["candidate"].get("sha256")
    if isinstance(value, list) and value:
        record = value[-1]
        return record.get("candidate") == candidate and record.get("result") == "passed"
    return False


def _gate_satisfied(state: Mapping[str, Any], gate_id: str) -> bool:
    # Recorded-baseline integrity is mandatory for control candidates.  Keep
    # the legacy generic skip behavior only where this gate is not a binding
    # control-class requirement.
    if gate_id == "strict-evals" and bool(state.get("tier", {}).get("control")):
        return _latest_current_pass(state, gate_id)
    if _user_skip(state, gate_id) is not None:
        return True
    # Without an explicit operator skip, the fresh-reviewer gate retains its
    # stronger candidate/request/manifest validation instead of falling back
    # to the generic latest-process-result predicate.
    if gate_id == FRESH_REVIEWER_EVALS_GATE:
        try:
            return fresh_eval_module.current_step_satisfied(
                state,
                expected_candidate=str(state["candidate"].get("sha256") or ""),
            )
        except (KeyError, TypeError, fresh_eval_module.FreshEvalError):
            return False
    if gate_id.startswith("stack:"):
        runs = state["steps"].get(gate_id)
        if not isinstance(runs, list) or not runs:
            return False
        latest = runs[-1]
        batch_id = latest.get("batch_id")
        count = latest.get("cell_count")
        if not isinstance(batch_id, str) or not isinstance(count, int) or count < 1:
            return False
        batch = [record for record in runs if record.get("batch_id") == batch_id]
        return (
            len(batch) == count
            and {record.get("cell_index") for record in batch} == set(range(1, count + 1))
            and all(
                record.get("candidate") == state["candidate"].get("sha256")
                and record.get("result") == "passed"
                for record in batch
            )
        )
    return _latest_current_pass(state, gate_id)


def _verify_and_build_ingest_records(
    repository: Path, run_id: str, inputs: dict[str, object]
) -> tuple[Sequence[dict[str, object]], tuple[str, ...]]:
    """Prove and synthesize one terminal, previously unbound commit/merge chain.

    The specification intentionally leaves the outcome-map dialect open.  This
    implementation owns one strict, versioned form: exactly ``schema``,
    ``chain_id``, ``task``, ``task_status``, and the ordered
    ``event_digests`` selected for ordinary records.  Unknown members fail
    closed instead of becoming implicit authority.
    """

    _batch, builders, journal = runtime._coordination_modules()
    if (
        INGEST_PROOF_CONTROLS != _REQUIRED_INGEST_PROOF_CONTROLS
        or tuple(builders._INGEST_PROOF_ORDER) != INGEST_PROOF_ORDER
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    required_inputs = {
        "task",
        "state_file",
        "events_file",
        "outcome_map",
        "state_file_sha256",
        "events_file_sha256",
        "outcome_map_sha256",
        "closing_head",
        "task_status",
    }
    if set(inputs) != required_inputs:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    canonical_repository, state_root = journal._resolve_repository(
        repository, "journal ingest-chain"
    )
    run_dir = state_root / ".codex-orchestrator" / "runs" / run_id

    # Matching intent/receipt recovery is handled by task-03's pre-allocation
    # lookup before this verifier is entered.  Proof must never search receipts
    # by request digest or re-authorize an already receipted terminal batch.
    existing_records: tuple[dict[str, object], ...] | None = None
    base_records: list[dict[str, object]] | None = None
    captured_paths = _ingest_captured_paths(
        canonical_repository, run_dir, inputs
    )
    raw: dict[str, bytes] = {}
    capture_names = {
        "state_file": "state.json",
        "events_file": "events.jsonl",
        "outcome_map": "outcome-map.json",
    }
    for field in ("state_file", "events_file", "outcome_map"):
        path = inputs.get(field)
        digest = inputs.get(f"{field}_sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        raw[field] = _read_ingest_input(
            canonical_repository,
            captured_paths[field],
            f"ingest.{field}",
            run_dir=run_dir,
            expected_capture_name=capture_names[field],
        )
        if sha256_bytes(raw[field]) != digest:
            raise journal.CoordinationRefusal(
                "forge: journal append refused — record cites path outside run or "
                "repository: ingest.captured_package: "
                f"{captured_paths[field]}"
            )
    try:
        materialized = json.loads(raw["state_file"].decode("utf-8"))
        outcome_map = json.loads(raw["outcome_map"].decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    if not isinstance(materialized, dict):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    chain_id = materialized.get("chain_id")
    family = materialized.get("kind")
    if not isinstance(chain_id, str):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    if family == "commit":
        try:
            validate_state(materialized, chain_id)
        except FrozenError as exc:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    elif family == "merge":
        if not _merge_ingest_state_shape_valid(builders, materialized, chain_id):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    else:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    completed_proofs: list[str] = []

    # Proof 1: canonical schema and digest replay in original event order.
    _require_ingest_proof(
        "chain-schema-and-digest-replay", completed_proofs
    )
    event_bytes = raw["events_file"]
    if not event_bytes or not event_bytes.endswith(b"\n"):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    replayed: dict[str, object] | None = None
    events: list[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
        ]
    ] = []
    previous_digest = ZERO_DIGEST
    for sequence, line in enumerate(event_bytes.splitlines(keepends=True), 1):
        try:
            event = json.loads(line.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
        if family == "commit":
            event_shape_valid = bool(
                isinstance(event, dict)
                and set(event) == EVENT_KEYS
                and event.get("sequence") == sequence
                and event.get("prev_digest") == previous_digest
            )
        else:
            event_shape_valid = bool(
                isinstance(event, dict)
                and set(event)
                == {
                    "schema",
                    "chain_id",
                    "sequence",
                    "at",
                    "event",
                    "generation_digest",
                    "previous_digest",
                    "payload",
                    "digest",
                }
                and event.get("schema") == "forge-merge-event/1"
                and event.get("chain_id") == chain_id
                and event.get("sequence") == sequence
                and event.get("previous_digest") == previous_digest
            )
        if (
            not event_shape_valid
            or not isinstance(event, dict)
            or line != canonical_bytes(event) + b"\n"
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        projection = {name: event[name] for name in event if name != "digest"}
        if sha256_bytes(canonical_bytes(projection)) != event.get("digest"):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        payload = event.get("payload")
        prior_state = copy.deepcopy(replayed)
        if family == "commit":
            if not isinstance(payload, dict) or set(payload) != {
                "at",
                "details",
                "event",
                "state",
            }:
                raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
            details = payload.get("details")
            state = payload.get("state")
            if (
                not isinstance(details, dict)
                or "journal_batch" in details
                or "source_event_digest" in details
                or not isinstance(state, dict)
            ):
                raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
            try:
                validate_state(state, chain_id)
            except FrozenError as exc:
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                ) from exc
            next_state = copy.deepcopy(state)
        else:
            if (
                not isinstance(payload, dict)
                or "state" in payload
                or "journal_batch" in payload
                or "source_event_digest" in payload
                or event.get("event") == "journal_receipted"
            ):
                raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
            try:
                next_state = reduce_merge_event(replayed, event)
            except (KeyError, TypeError, ValueError, RuntimeError) as exc:
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                ) from exc
            if (
                not _merge_ingest_state_shape_valid(builders, next_state, chain_id)
            ):
                raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        replayed = copy.deepcopy(next_state)
        events.append((event, prior_state, copy.deepcopy(next_state)))
        previous_digest = str(event["digest"])
    # Proof 2: the exact replay result is the caller-supplied materialization.
    _require_ingest_proof("materialized-state", completed_proofs)
    if replayed != materialized:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    if family == "merge":
        return _verify_and_build_merge_ingest_records(
            canonical_repository=canonical_repository,
            run_id=run_id,
            run_dir=run_dir,
            inputs=inputs,
            materialized=materialized,
            outcome_map=outcome_map,
            events=events,
            existing_records=existing_records,
            base_records=base_records,
            captured_state=raw["state_file"],
            captured_events=raw["events_file"],
            completed_proofs=completed_proofs,
        )

    # Proof 3: the terminal unbound chain names this repository.  A bound or
    # carried chain belongs to the autoappend path and cannot be ingested.
    _require_ingest_proof("repository", completed_proofs)
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
        materialized.get("kind") != "commit"
        or materialized.get("state") != "closed"
        or materialized.get("run_binding") is not None
        or materialized.get("journal_outbox") is not None
        or materialized.get("staging", {}).get("worktree_root")
        != str(canonical_repository)
        or not isinstance(materialized.get("candidate"), dict)
        or SHA256_RE.fullmatch(
            str(materialized.get("candidate", {}).get("sha256", ""))
        )
        is None
        or opening_repository != canonical_repository
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 4: the generation's policy identity resolves to exact committed
    # bytes, not a mutable worktree copy.
    _require_ingest_proof("policy", completed_proofs)
    policy_source = materialized.get("policy_source")
    if not isinstance(policy_source, dict):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    policy = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "show",
            f"{policy_source.get('sha')}:forge-project.md",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if (
        policy.returncode != 0
        or sha256_bytes(policy.stdout) != policy_source.get("digest")
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    try:
        parsed_policy = parse_policy(str(policy_source["sha"]), policy.stdout)
    except (KeyError, PolicyError, UnicodeError) as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc

    # Proof 5: freshness is established against the live authoritative chain
    # while holding its native event lock, including byte-identical events.
    _require_ingest_proof("generation", completed_proofs)
    _prove_ingest_live_chain(
        canonical_repository,
        chain_id,
        materialized,
        raw["state_file"],
        raw["events_file"],
    )

    # Proof 6: every required gate remains satisfied by the current candidate.
    _require_ingest_proof("current-gates", completed_proofs)
    context = CommandContext(
        repo=Repository(canonical_repository),
        store=ChainStore(Repository(canonical_repository).common_root()),
        options=CLIOptions(repo=str(canonical_repository), revision9_face=True),
        policy=parsed_policy,
    )
    tier = materialized.get("tier")
    if (
        not isinstance(tier, dict)
        or tier.get("effective") not in TIER_RANK
        or tier.get("derived") not in TIER_RANK
        or (
            tier.get("declared") is not None
            and tier.get("declared") not in TIER_RANK
        )
        or type(tier.get("control")) is not bool
        or not _latest_current_pass(materialized, "classification")
        or (
            tier.get("effective") == "fast"
            and (
                bool(runtime._fast_mechanical_skips(materialized))
                or not _latest_current_pass(materialized, "fast-eligibility")
                or not _latest_current_pass(
                    materialized, "fast-finalize-eligibility"
                )
            )
        )
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    required_steps = _required_steps(context, materialized)
    if (
        not _gate_one_complete(materialized)
        or not all(
            _gate_satisfied(materialized, step)
            for step in set(required_steps) - {"gate-1"}
        )
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proofs 7–10: independently re-open the current review package, then bind
    # role, iteration, and verdict in normative order.  Fast chains make the
    # predicates vacuous, but every control remains load-bearing.
    review = materialized.get("review")
    if not isinstance(review, dict) or not isinstance(tier, dict):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    review_required = tier.get("effective") != "fast"
    request = review.get("request")
    verdict = review.get("verdict")

    _require_ingest_proof("review-package", completed_proofs)
    if review_required:
        if (
            not isinstance(request, dict)
            or not isinstance(verdict, dict)
            or request.get("candidate")
            != materialized["candidate"]["sha256"]
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
    if review_required:
        assert isinstance(request, dict)
        expected_role = (
            "review-cheap"
            if tier.get("effective") == "standard"
            else "review-final"
        )
        if request.get("reviewer") != expected_role:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    _require_ingest_proof("reviewer-iteration", completed_proofs)
    if review_required:
        assert isinstance(request, dict)
        if (
            type(review.get("iteration")) is not int
            or int(review["iteration"]) <= 0
            or request.get("iteration") != review.get("iteration")
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    _require_ingest_proof("reviewer-verdict", completed_proofs)
    if review_required:
        assert isinstance(request, dict) and isinstance(verdict, dict)
        if (
            verdict.get("verdict") != "PASS"
            or verdict.get("candidate")
            != materialized["candidate"]["sha256"]
            or verdict.get("package_digest") != request.get("package_digest")
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 11: approval is required exactly for the native parked classes.
    _require_ingest_proof("operator-approval", completed_proofs)
    approval_required = bool(
        tier.get("control") or review.get("operator_cosign_required")
    )
    approval = materialized.get("approval")
    if approval_required and (
        not isinstance(approval, dict)
        or approval.get("candidate") != materialized["candidate"]["sha256"]
        or not isinstance(approval.get("approved_at"), str)
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 12: the staged candidate is exactly the produced commit.
    _require_ingest_proof("landing-proof", completed_proofs)
    result = materialized.get("commit_result")
    commit_sha = result.get("commit_sha") if isinstance(result, dict) else None
    intent = result.get("intent") if isinstance(result, dict) else None
    if (
        not isinstance(commit_sha, str)
        or COMMIT_RE.fullmatch(commit_sha) is None
        or not isinstance(intent, dict)
        or intent.get("candidate") != materialized["candidate"]["sha256"]
        or not isinstance(intent.get("pre_head"), str)
        or COMMIT_RE.fullmatch(str(intent["pre_head"])) is None
        or not isinstance(intent.get("message_digest"), str)
        or SHA256_RE.fullmatch(str(intent["message_digest"])) is None
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    if candidate_is_v2(materialized):
        candidate_record = materialized["candidate"]
        identity = result.get("identity") if isinstance(result, dict) else None
        if (
            intent.get("authorization_id") != candidate_record.get("authorization_id")
            or intent.get("object_format") != candidate_record.get("object_format")
            or intent.get("expected_tree_oid") != candidate_record.get("tree_oid")
            or candidate_record.get("base_commit_oid") != intent.get("pre_head")
            or not isinstance(identity, dict)
            or identity.get("result") != "passed"
            or identity.get("produced_sha") != commit_sha
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        try:
            candidate_context = candidate_module.discover_context(canonical_repository)
            committed = candidate_module.read_commit_object(
                candidate_context, commit_sha
            )
            parent_object = candidate_module.read_commit_object(
                candidate_context, str(intent["pre_head"])
            )
            if len(parent_object.tree_headers) != 1:
                raise candidate_module.CandidateError(
                    "pre-commit object has malformed tree headers"
                )
            _path_bytes, changed_paths = candidate_module.enumerate_tree_pair(
                candidate_context,
                parent_object.tree_headers[0],
                str(candidate_record["tree_oid"]),
            )
        except (candidate_module.CandidateError, KeyError, OSError) as exc:
            raise journal.CoordinationRefusal(
                builders.INGEST_PROOF_INVALID
            ) from exc
        if (
            committed.parent_headers != (str(intent["pre_head"]),)
            or committed.tree_headers != (str(candidate_record["tree_oid"]),)
            or sha256_bytes(committed.message) != intent["message_digest"]
            or tuple(materialized.get("paths", ())) != changed_paths
            or not changed_paths
            or not all(journal._valid_scope_item(path) for path in changed_paths)
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    else:
        parent = subprocess.run(
            ["git", "-C", str(canonical_repository), "rev-parse", f"{commit_sha}^"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if parent.returncode != 0:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        parent_sha = parent.stdout.decode("ascii", "replace").strip()
        commit_object = subprocess.run(
            ["git", "-C", str(canonical_repository), "cat-file", "commit", commit_sha],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            commit_headers, commit_message = commit_object.stdout.split(b"\n\n", 1)
        except IndexError as exc:
            raise journal.CoordinationRefusal(
                builders.INGEST_PROOF_INVALID
            ) from exc
        parent_headers = [
            line[len(b"parent ") :]
            for line in commit_headers.splitlines()
            if line.startswith(b"parent ")
        ]
        diff = subprocess.run(
            ["git", "-C", str(canonical_repository), "diff", parent_sha, commit_sha],
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
                parent_sha,
                commit_sha,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            changed_paths = tuple(
                item.decode("utf-8") for item in names.stdout.split(b"\0") if item
            )
        except UnicodeDecodeError as exc:
            raise journal.CoordinationRefusal(
                builders.INGEST_PROOF_INVALID
            ) from exc
        if (
            parent_sha != intent["pre_head"]
            or commit_object.returncode != 0
            or parent_headers != [str(intent["pre_head"]).encode("ascii")]
            or sha256_bytes(commit_message) != intent["message_digest"]
            or diff.returncode != 0
            or names.returncode != 0
            or sha256_bytes(diff.stdout) != materialized["candidate"]["sha256"]
            or not changed_paths
            or not all(journal._valid_scope_item(path) for path in changed_paths)
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 13: every native transition is monotonic in its original order.
    _require_ingest_proof("monotonic-transitions", completed_proofs)
    if any(
        not _commit_transition_valid_with_candidate_v2(
            builders, event, prior_state, event_state
        )
        for event, prior_state, event_state in events
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 14: the landed commit is contained by the caller's proposed
    # closing HEAD.
    _require_ingest_proof("closing-head-containment", completed_proofs)
    closing_head = inputs.get("closing_head")
    if not isinstance(closing_head, str) or COMMIT_RE.fullmatch(closing_head) is None:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    contained = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "merge-base",
            "--is-ancestor",
            commit_sha,
            closing_head,
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if contained.returncode != 0:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 15: the explicit task belongs to this run and is still active.
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
        or outcome_map.get("chain_id") != chain_id
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

    # Proof 16: every landed path is admitted by both task and run scope.
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
        if (
            not any(
                journal.pathspec_contained(path, pattern)
                for pattern in files
                if isinstance(pattern, str)
            )
            or not any(
                journal.pathspec_contained(path, admitted)
                for admitted in run_state.scope
            )
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

    binding = {
        "run_id": run_id,
        "task_id": task,
        "repository": str(canonical_repository),
        "policy_digest": policy_source["digest"],
    }
    selected: list[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
        ]
    ] = []
    final_candidate = materialized["candidate"]["sha256"]
    for event, prior_state, event_state in events:
        payload = event["payload"]
        assert isinstance(payload, dict)
        details = payload["details"]
        assert isinstance(details, dict)
        event_name = payload.get("event")
        active = False
        if event_name == "step_recorded":
            active = _ingest_step_is_current(materialized, event_state, details)
        elif event_name == "secret_scan_recorded":
            active = _ingest_secret_scan_is_current(
                materialized, event, prior_state, event_state
            )
        elif event_name in {"review_passed", "review_blocked"}:
            active = bool(
                tier.get("effective") == "hard"
                and event_name == "review_passed"
                and event_state.get("review", {}).get("verdict")
                == materialized.get("review", {}).get("verdict")
            )
        elif event_name == "operator_approved":
            active = bool(approval_required and event_state.get("approval") == approval)
        elif event_name == "operator_skip":
            gate_id = details.get("gate_id")
            active = bool(
                isinstance(gate_id, str)
                and _user_skip(materialized, gate_id)
                == _user_skip(event_state, gate_id)
            )
        elif event_name == "commit_identity_checked":
            active = bool(
                event_state.get("commit_result", {}).get("identity")
                == materialized.get("commit_result", {}).get("identity")
                and details.get("result") == "passed"
            )
        elif event_name in {"commit_produced", "commit_close_recovered"}:
            active = details.get("commit_sha") == commit_sha
        if active and event_state.get("candidate", {}).get("sha256") == final_candidate:
            selected.append((event, prior_state, event_state))
    selected_digests = [
        str(event["digest"]) for event, _prior, _state in selected
    ]
    if selected_digests != outcome_map["event_digests"]:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    projected = _ingest_allocation_records(
        canonical_repository, run_state
    )
    records: list[dict[str, object]] = []
    captured_citations = [
        captured_paths["state_file"],
        captured_paths["events_file"],
        captured_paths["outcome_map"],
    ]
    replay_entries = tuple(
        (
            event,
            prior_state,
            event_state,
            (),
            str(event["digest"]),
        )
        for event, prior_state, event_state in events
    )
    for event, prior_state, event_state in selected:
        payload = event["payload"]
        assert isinstance(payload, dict)
        details = payload["details"]
        assert isinstance(details, dict)
        event_name = str(payload["event"])
        bound_state = copy.deepcopy(event_state)
        bound_state["run_binding"] = copy.deepcopy(binding)
        generated = runtime._build_chain_journal_records(
            canonical_repository,
            bound_state,
            event_name,
            details,
            str(event["digest"]),
            retrospective_ingest=True,
        )
        for generated_record in generated:
            record = copy.deepcopy(generated_record)
            record_type = str(record["type"])
            record["id"] = builders._allocate_id(projected, record_type)
            record["run_id"] = run_id
            record["recorded_at"] = payload["at"]
            _capture_ingest_record_evidence(
                canonical_repository,
                run_dir,
                record,
            )
            if record.get("outcome") == "chain-landing":
                record["basis"] = list(captured_citations)
            record_binding = record.get("binding")
            if (
                not isinstance(record_binding, dict)
                or not _binding_matches_source_fact_with_candidate_v2(
                    builders,
                    journal,
                    record_binding,
                    record,
                    event,
                    prior_state,
                    event_state,
                    family="commit",
                )
                or not _binding_is_current_with_candidate_v2(
                    builders,
                    journal,
                    materialized,
                    record_binding,
                    record,
                    event,
                    prior_state,
                    event_state,
                    replay_entries,
                    chain_family="commit",
                )
            ):
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                )
            records.append(record)
            projected.append(record)
    if not any(record.get("outcome") == "chain-landing" for record in records):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    if approval_required and not any(
        record.get("outcome") == "chain-approval" for record in records
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
        "recorded_at": events[-1][0]["payload"]["at"],
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


def _ingest_proof_verifier(
    repository: Path, run_id: str, inputs: dict[str, object]
) -> tuple[Sequence[dict[str, object]], tuple[str, ...]]:
    return _verify_and_build_ingest_records(repository, run_id, inputs)


# The Revision-9 seam marker rides on the callables themselves so register_coordination_seams below can
# tell an already-installed forge seam from a foreign registration (moved from the shim in cli split phase 3 and
# from the chain_core package root in the engine split, bead forge-plugin-4j7).
for _seam in (
    reduce_merge_event,
    _authorize_chain_batch,
    _ingest_proof_verifier,
    _require_no_pending_chain_activation_outbox,
):
    _seam._forge_cli_revision9_seam = True  # type: ignore[union-attr]


def register_coordination_seams() -> None:
    """Idempotently install task-04 authority in the shared task-03 modules."""

    batch, builders, _journal = runtime._coordination_modules()
    register_activation_reservation_seam()

    existing_reducer = builders.MERGE_TRANSITION_REDUCER
    if existing_reducer is None:
        builders.register_merge_transition_reducer(reduce_merge_event)
    elif not getattr(existing_reducer, "_forge_cli_revision9_seam", False):
        raise RuntimeError("merge transition reducer registration conflict")

    existing_verifier = builders._INGEST_PROOF_VERIFIER
    if existing_verifier is None:
        builders._register_ingest_proof_verifier(_ingest_proof_verifier)
    elif not getattr(existing_verifier, "_forge_cli_revision9_seam", False):
        raise RuntimeError("ingest proof verifier registration conflict")

    existing_authorizer = batch._CHAIN_BATCH_AUTHORIZER
    if existing_authorizer is None:
        if not hasattr(batch, "_FORGE_CLI_CHAIN_CAPABILITIES"):
            batch._FORGE_CLI_CHAIN_CAPABILITIES = {}
            batch._FORGE_CLI_CHAIN_CAPABILITIES_LOCK = threading.Lock()
        batch._register_chain_batch_authorizer(_authorize_chain_batch)
    elif not getattr(existing_authorizer, "_forge_cli_revision9_seam", False):
        raise RuntimeError("chain batch authorizer registration conflict")
    elif not hasattr(batch, "_FORGE_CLI_CHAIN_CAPABILITIES"):
        # A module-alias import may reach the shared registrar after another
        # alias installed the callback; the registry itself lives on task-03's
        # shared batch module so both aliases exchange the same capabilities.
        batch._FORGE_CLI_CHAIN_CAPABILITIES = {}
        batch._FORGE_CLI_CHAIN_CAPABILITIES_LOCK = threading.Lock()


@contextlib.contextmanager
def _chain_batch_lock(
    run_dir: Path,
    repository: Path,
    run_id: str,
    *,
    create: bool,
    before_create: Callable[[], None] | None = None,
) -> Iterable[None]:
    """Conditionally create a mutation lock only around a validated run target."""

    register_coordination_seams()
    batch, _builders, journal = runtime._coordination_modules()
    create_missing = False
    if create:
        try:
            os.lstat(run_dir / journal.BATCH_LOCK_NAME)
        except FileNotFoundError:
            _validate_chain_batch_target(repository, run_id)
            if before_create is not None:
                before_create()
            create_missing = True
        except OSError:
            # Let the stable batch-lock implementation classify every unsafe
            # or unreadable existing topology with its established diagnostic.
            pass
    with batch.batch_lock(run_dir, create=create_missing):
        if create_missing:
            # Creation reserves only the stable outer lock. Every mutation
            # that admitted this missing target re-proves it under the required
            # batch -> registry -> journal order before any write is reached.
            _validate_chain_batch_target(repository, run_id)
        yield


class ChainStore(_ChainStoragePrimitives):
    """Commit-family snapshot log over the shared storage primitives."""

    def _events(self, chain_id: str) -> list[dict[str, Any]]:
        with self.event_lock(chain_id):
            return self._events_unlocked(chain_id)

    def _events_unlocked(self, chain_id: str) -> list[dict[str, Any]]:
        path = self.events_path(chain_id)
        try:
            data = self._read_root_bytes(path.name)
        except FileNotFoundError as exc:
            raise FrozenError(
                "chain event log is missing",
                chain_id=chain_id,
                observed=str(path),
            ) from exc
        except OSError as exc:
            raise FrozenError(
                "chain event log is unreadable", chain_id=chain_id, observed=str(exc)
            ) from exc
        if not data or not data.endswith(b"\n"):
            raise FrozenError(
                "chain event log is empty or has a partial final record",
                chain_id=chain_id,
            )
        events: list[dict[str, Any]] = []
        previous = ZERO_DIGEST
        for sequence, line in enumerate(data.splitlines(keepends=True), 1):
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FrozenError(
                    f"chain event {sequence} is malformed", chain_id=chain_id
                ) from exc
            if not isinstance(event, dict) or set(event) != EVENT_KEYS:
                raise FrozenError(
                    f"chain event {sequence} has an invalid key set", chain_id=chain_id
                )
            if line != canonical_bytes(event) + b"\n":
                raise FrozenError(
                    f"chain event {sequence} is not canonical", chain_id=chain_id
                )
            if event["sequence"] != sequence or event["prev_digest"] != previous:
                raise FrozenError(
                    f"chain event {sequence} sequence/digest predecessor is invalid",
                    chain_id=chain_id,
                )
            unsigned = {
                "sequence": event["sequence"],
                "prev_digest": event["prev_digest"],
                "payload": event["payload"],
            }
            expected = sha256_bytes(canonical_bytes(unsigned))
            if event["digest"] != expected:
                raise FrozenError(
                    f"chain event {sequence} digest is invalid", chain_id=chain_id
                )
            payload = event["payload"]
            if not isinstance(payload, dict) or set(payload) != {
                "at",
                "details",
                "event",
                "state",
            }:
                raise FrozenError(
                    f"chain event {sequence} payload is malformed", chain_id=chain_id
                )
            validate_state(payload["state"], chain_id)
            previous = event["digest"]
            events.append(event)
        return events

    def load(
        self, chain_id: str, *, family_proven: bool = False
    ) -> dict[str, Any]:
        self._validate_id(chain_id)
        if not family_proven and self.chain_family(chain_id) != "commit":
            raise FrozenError(
                "commit store refused a merge-family chain",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        with self.event_lock(chain_id):
            return self._load_locked(chain_id)

    def _validate_bound_event_history(
        self,
        chain_id: str,
        events: Sequence[dict[str, Any]],
        binding: Mapping[str, Any],
    ) -> None:
        """Validate the nonrecursive batch/receipt algebra before repair.

        Materialized state is recoverable from an fsynced event, so the
        task-03 resolver cannot be called until after a missing/stale state
        projection is repaired.  This pre-repair pass applies its transition,
        source-projection, carried-record, pending-outbox, and durable receipt
        predicates to the event authority first.
        """

        register_coordination_seams()
        batch, builders, journal = runtime._coordination_modules()
        run_dir = (
            self.common_root
            / ".codex-orchestrator"
            / "runs"
            / str(binding.get("run_id"))
        )
        if batch._active_locks().get(os.path.abspath(os.fspath(run_dir))) is None:
            raise FrozenError(
                "bound chain replay lacks the outer journal lock",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        repository = Path(str(binding.get("repository")))
        replayed: dict[str, object] | None = None
        pending: dict[str, object] | None = None
        pending_records: tuple[dict[str, object], ...] = ()
        replay_entries: list[
            tuple[
                dict[str, object],
                dict[str, object] | None,
                dict[str, object],
                tuple[dict[str, object], ...],
                str | None,
            ]
        ] = []
        try:
            for event in events:
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    raise ValueError("event payload is malformed")
                current = payload.get("state")
                if not isinstance(current, dict) or not _commit_transition_valid_with_candidate_v2(
                    builders, event, replayed, current
                ):
                    raise ValueError("commit transition is invalid")
                records, event_outbox, source_digest = _event_batch_records_with_candidate_v2(
                    builders, journal, event, "commit"
                )
                event_name = payload.get("event")
                is_receipt = event_name == "journal_receipted"
                if pending is not None and not is_receipt:
                    raise ValueError("pending outbox was bypassed")
                if pending is None and is_receipt:
                    raise ValueError("receipt has no pending outbox")
                if is_receipt:
                    acknowledgement = builders._receipt_metadata(event, "commit")
                    if (
                        acknowledgement is None
                        or records
                        or event_outbox is not None
                        or source_digest is not None
                        or acknowledgement.get("idempotency_key")
                        != pending.get("idempotency_key")
                        or acknowledgement.get("batch_digest")
                        != pending.get("batch_digest")
                        or replayed is None
                    ):
                        raise ValueError("receipt transition is invalid")
                    builders._verify_receipted_batch(
                        repository,
                        chain_id,
                        replayed,
                        pending,
                        pending_records,
                        acknowledgement,
                    )
                    if current.get("journal_outbox") is not None:
                        raise ValueError("receipt did not clear outbox")
                    pending = None
                    pending_records = ()
                elif event_outbox is not None:
                    if pending is not None or current.get("journal_outbox") != event_outbox:
                        raise ValueError("event outbox projection is invalid")
                    pending = event_outbox
                    pending_records = records
                elif current.get("journal_outbox") != pending:
                    raise ValueError("event changed the pending outbox")
                activation_preamble = (
                    records[:1]
                    if records
                    and journal._writer_activation_candidate(records[0])
                    else ()
                )
                for record in records[len(activation_preamble) :]:
                    record_binding = record.get("binding")
                    if (
                        not isinstance(record_binding, dict)
                        or not _binding_matches_source_fact_with_candidate_v2(
                            builders,
                            journal,
                            record_binding,
                            record,
                            event,
                            replayed,
                            current,
                            family="commit",
                        )
                    ):
                        raise ValueError("carried binding fact is invalid")
                replay_entries.append(
                    (
                        copy.deepcopy(event),
                        copy.deepcopy(replayed),
                        copy.deepcopy(current),
                        tuple(copy.deepcopy(records)),
                        source_digest,
                    )
                )
                replayed = copy.deepcopy(current)
            if replayed is None:
                raise ValueError("bound chain replay is empty")
            frozen_entries = tuple(replay_entries)
            latest_record_index = next(
                (
                    index
                    for index in range(len(frozen_entries) - 1, -1, -1)
                    if frozen_entries[index][3]
                ),
                None,
            )
            for index, (
                event,
                prior,
                current,
                records,
                _source_digest,
            ) in enumerate(frozen_entries):
                # Receipted records are authenticated historical facts.  Only
                # the newest appended set can still be live authority, and it
                # is checked against the exact state/prefix at its append.
                if index != latest_record_index:
                    continue
                appended_history = frozen_entries[: index + 1]
                activation_preamble = (
                    records[:1]
                    if records
                    and journal._writer_activation_candidate(records[0])
                    else ()
                )
                for record in records[len(activation_preamble) :]:
                    record_binding = record.get("binding")
                    current_fact = bool(
                        isinstance(record_binding, dict)
                        and _binding_is_current_with_candidate_v2(
                            builders,
                            journal,
                            current,
                            record_binding,
                            record,
                            event,
                            prior,
                            current,
                            appended_history,
                            chain_family="commit",
                        )
                    )
                    # A receipted v2 landing remains current in the narrow
                    # committing crash window only after the durable produced
                    # identity PASS that authorized the landing projection.
                    if not current_fact and isinstance(record_binding, dict):
                        final_result = current.get("commit_result")
                        final_candidate = current.get("candidate")
                        source_payload = event.get("payload")
                        source_details = (
                            source_payload.get("details")
                            if isinstance(source_payload, dict)
                            else None
                        )
                        bound_candidate = record_binding.get("candidate")
                        legacy_binding = bool(
                            isinstance(bound_candidate, dict)
                            and bound_candidate.get("kind")
                            == "staged-diff-sha256"
                            and bound_candidate.get("value")
                            == final_candidate.get("sha256")
                        )
                        v2_value = (
                            bound_candidate.get("value")
                            if isinstance(bound_candidate, dict)
                            and bound_candidate.get("kind")
                            == "git-tree-candidate-v2"
                            else None
                        )
                        identity = (
                            final_result.get("identity")
                            if isinstance(final_result, dict)
                            else None
                        )
                        v2_binding = bool(
                            candidate_is_v2(current)
                            and isinstance(v2_value, dict)
                            and v2_value
                            == {
                                "authorization_id": final_candidate.get(
                                    "authorization_id"
                                ),
                                "object_format": final_candidate.get("object_format"),
                                "tree_oid": final_candidate.get("tree_oid"),
                            }
                            and isinstance(identity, dict)
                            and identity.get("result") == "passed"
                            and identity.get("produced_sha")
                            == final_result.get("commit_sha")
                        )
                        current_fact = bool(
                            record.get("outcome") == "chain-landing"
                            and current.get("state") == "committing"
                            and isinstance(final_result, dict)
                            and isinstance(final_candidate, dict)
                            and isinstance(source_payload, dict)
                            and source_payload.get("event") == "commit_produced"
                            and isinstance(source_details, dict)
                            and (legacy_binding or v2_binding)
                            and isinstance(final_result.get("intent"), dict)
                            and final_result["intent"].get("candidate")
                            == final_candidate.get("sha256")
                            and source_details.get("commit_sha")
                            == final_result.get("commit_sha")
                        )
                    if (
                        not isinstance(record_binding, dict)
                        or not current_fact
                    ):
                        raise ValueError("carried binding fact is stale")
        except (KeyError, TypeError, ValueError, RuntimeError, journal.CoordinationRefusal) as exc:
            raise FrozenError(
                "bound chain event replay failed",
                chain_id=chain_id,
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc

    def _load_locked(self, chain_id: str) -> dict[str, Any]:
        events = self._events_unlocked(chain_id)
        replayed = copy.deepcopy(events[-1]["payload"]["state"])
        binding = replayed.get("run_binding")
        if isinstance(binding, Mapping):
            self._validate_bound_event_history(chain_id, events, binding)
        path = self.state_path(chain_id)
        materialized: dict[str, Any] | None = None
        try:
            raw = self._read_root_bytes(path.name)
            loaded = json.loads(raw)
            materialized = validate_state(loaded, chain_id)
        except FileNotFoundError:
            materialized = None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, FrozenError):
            materialized = None
        if materialized is None or canonical_bytes(materialized) != canonical_bytes(replayed):
            # Event-first persistence makes the last valid event authoritative.
            # A materialized committing snapshot is never replaced by an older
            # event; that ordering would be impossible without external writes.
            if materialized and materialized.get("state") == "committing" and replayed.get(
                "state"
            ) != "committing":
                raise FrozenError(
                    "materialized committing state is ahead of its event log",
                    chain_id=chain_id,
                    state="committing",
                )
            self._atomic_state(replayed)
        if isinstance(binding, Mapping):
            _batch, builders, journal = runtime._coordination_modules()
            try:
                with self.root_descriptor() as root:
                    root_observation = journal._file_observation(os.fstat(root))
                    authoritative = builders._resolve_binding_from_descriptor(
                        Path(str(binding["repository"])),
                        root,
                        chain_id,
                        ZERO_DIGEST,
                        expected_type=None,
                        expected_fields=None,
                        expected_run_id=None,
                        expected_task_id=None,
                        replay_only=True,
                        allow_pending=True,
                    )
                    if (
                        authoritative != replayed
                        or journal._file_observation(os.fstat(root))
                        != root_observation
                    ):
                        raise ValueError("authoritative replay changed")
            except (KeyError, OSError, TypeError, ValueError, RuntimeError, journal.CoordinationRefusal) as exc:
                raise FrozenError(
                    "bound chain authority replay failed",
                    chain_id=chain_id,
                    observed=str(exc),
                    schema=REVISION9_OUTPUT_SCHEMA,
                ) from exc
        self._remember_version(
            replayed,
            int(events[-1]["sequence"]),
            str(events[-1]["digest"]),
        )
        return replayed

    def create(self, state: dict[str, Any], event: str, details: Mapping[str, Any]) -> None:
        self.ensure_root()
        chain_id = str(state["chain_id"])
        if self._root_entry_exists(self.state_path(chain_id).name) or self._root_entry_exists(
            self.events_path(chain_id).name
        ):
            raise FrozenError("generated chain identity already exists", chain_id=chain_id)
        self.persist(state, event, details, initial=True)

    def persist(
        self,
        state: dict[str, Any],
        event: str,
        details: Mapping[str, Any],
        *,
        initial: bool = False,
        touch: bool = True,
        _journal_locked: bool = False,
    ) -> None:
        validate_state(state, str(state.get("chain_id")))
        self.ensure_root()
        chain_id = str(state["chain_id"])
        binding = state.get("run_binding")
        if isinstance(binding, Mapping) and not _journal_locked:
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
                    create=True,
                ):
                    self.persist(
                        state,
                        event,
                        details,
                        initial=initial,
                        touch=touch,
                        _journal_locked=True,
                    )
                return
            except journal.CoordinationRefusal as exc:
                raise _coordination_refusal(exc) from exc
        if isinstance(binding, Mapping):
            _validate_bound_chain_state(state)
        if state.get("journal_outbox") is not None and event != "journal_receipted":
            raise Refusal(
                V2ReasonCode.JOURNAL_OUTBOX_PENDING,
                "forge: chain transition refused — journal outbox is pending",
                expected="a receipted null journal_outbox",
                observed=str(state.get("journal_outbox")),
                remediation=_forge_command(state, "status"),
                chain=state,
            )
        carried_records: tuple[dict[str, Any], ...] = ()
        pending_outbox: dict[str, Any] | None = None
        with self.event_lock(chain_id):
            existing: list[dict[str, Any]] = []
            if not initial:
                existing = self._events_unlocked(chain_id)
                self._require_tail_version(
                    state,
                    int(existing[-1]["sequence"]),
                    str(existing[-1]["digest"]),
                    family="commit",
                    refusal_chain=existing[-1]["payload"]["state"],
                )
            elif self._root_entry_exists(self.events_path(chain_id).name):
                raise FrozenError("initial event log already exists", chain_id=chain_id)
            when = runtime.utc_now()
            if touch:
                state["last_event_at"] = iso_z(when)
                state["inactive_after"] = iso_z(
                    when + dt.timedelta(seconds=INACTIVE_SECONDS)
                )
            validate_state(state, chain_id)
            sequence = len(existing) + 1
            previous = existing[-1]["digest"] if existing else ZERO_DIGEST
            payload = {
                "at": iso_z(when),
                "details": dict(details),
                "event": event,
                "state": copy.deepcopy(state),
            }
            unsigned = {
                "sequence": sequence,
                "prev_digest": previous,
                "payload": payload,
            }
            if isinstance(binding, Mapping) and event != "journal_receipted":
                source_event_digest = sha256_bytes(canonical_bytes(unsigned))
                carried_records = runtime._build_chain_journal_records(
                    Path(str(binding["repository"])),
                    state,
                    event,
                    details,
                    source_event_digest,
                )
                if carried_records:
                    _batch, _builders, journal = runtime._coordination_modules()
                    batch_bytes = b"".join(
                        journal._journal_line(record)
                        for record in carried_records
                    )
                    batch_digest = sha256_bytes(batch_bytes)
                    pending_outbox = {
                        "idempotency_key": source_event_digest,
                        "batch_digest": batch_digest,
                        "record_count": len(carried_records),
                        "source_event_digest": source_event_digest,
                    }
                    prospective_state = copy.deepcopy(state)
                    prospective_state["journal_outbox"] = copy.deepcopy(
                        pending_outbox
                    )
                    payload["state"] = prospective_state
                    payload["details"] = {
                        **dict(details),
                        "source_event_digest": source_event_digest,
                        "journal_batch": {
                            "idempotency_key": source_event_digest,
                            "batch_digest": batch_digest,
                            "record_count": len(carried_records),
                            "records": copy.deepcopy(list(carried_records)),
                        },
                    }
                    unsigned["payload"] = payload
            record = {**unsigned, "digest": sha256_bytes(canonical_bytes(unsigned))}
            if pending_outbox is not None:
                assert isinstance(binding, Mapping)
                prospective_events = (*existing, record)
                self._validate_bound_event_history(
                    chain_id, prospective_events, binding
                )
                prospective_state = record["payload"]["state"]
                assert isinstance(prospective_state, Mapping)
                _prevalidate_chain_batch_carrier(
                    prospective_state,
                    pending_outbox,
                    carried_records,
                )
                state["journal_outbox"] = copy.deepcopy(pending_outbox)
            encoded = canonical_bytes(record) + b"\n"
            self._append_event_bytes(chain_id, encoded, initial=initial)
            self._atomic_state(state)
            self._remember_version(state, sequence, str(record["digest"]))
        if pending_outbox is not None:
            self._drain_pending_batch(
                state,
                pending_outbox,
                carried_records,
                journal_locked=True,
            )

    def _drain_pending_batch(
        self,
        state: dict[str, Any],
        pending_outbox: Mapping[str, Any],
        carried_records: Sequence[dict[str, Any]],
        *,
        journal_locked: bool,
    ) -> None:
        binding = state.get("run_binding")
        if not isinstance(binding, Mapping):
            raise FrozenError(
                "pending journal outbox lacks an immutable run binding",
                chain_id=str(state.get("chain_id") or "") or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if not journal_locked:
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
                    create=True,
                ):
                    self._drain_pending_batch(
                        state,
                        pending_outbox,
                        carried_records,
                        journal_locked=True,
                    )
                return
            except journal.CoordinationRefusal as exc:
                raise _coordination_refusal(exc) from exc

        receipt_details = _drain_chain_batch_capability(
            state,
            pending_outbox,
            carried_records,
        )
        if state.get("journal_outbox") != pending_outbox:
            raise FrozenError(
                "pending journal outbox identity changed before acknowledgement",
                chain_id=str(state["chain_id"]),
                state=str(state.get("state")),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        state["journal_outbox"] = None
        self.persist(
            state,
            "journal_receipted",
            receipt_details,
            _journal_locked=True,
        )

    def recover_pending_outbox(self, state: dict[str, Any]) -> dict[str, Any]:
        """Replay and receipt the exact last unacknowledged carried batch."""

        pending = state.get("journal_outbox")
        if pending is None:
            return state
        binding = state.get("run_binding")
        if not isinstance(binding, Mapping) or not isinstance(pending, dict):
            raise FrozenError(
                "pending journal outbox is not recoverable",
                chain_id=str(state.get("chain_id") or "") or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
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
                create=True,
            ):
                with self.event_lock(str(state["chain_id"])):
                    fresh = self._load_locked(str(state["chain_id"]))
                    current_pending = fresh.get("journal_outbox")
                    if current_pending is None:
                        return fresh
                    if current_pending != pending:
                        raise FrozenError(
                            "pending journal outbox changed during replay",
                            chain_id=str(state["chain_id"]),
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    events = self._events_unlocked(str(state["chain_id"]))
                    carrier = events[-1]["payload"].get("details")
                    carried = (
                        carrier.get("journal_batch")
                        if isinstance(carrier, dict)
                        else None
                    )
                    if (
                        not isinstance(carried, dict)
                        or set(carried)
                        != {
                            "idempotency_key",
                            "batch_digest",
                            "record_count",
                            "records",
                        }
                        or carried.get("idempotency_key")
                        != current_pending.get("idempotency_key")
                        or carried.get("batch_digest")
                        != current_pending.get("batch_digest")
                        or carried.get("record_count")
                        != current_pending.get("record_count")
                        or not isinstance(carried.get("records"), list)
                    ):
                        raise FrozenError(
                            "pending journal outbox lacks its exact carried batch",
                            chain_id=str(state["chain_id"]),
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    records = tuple(copy.deepcopy(carried["records"]))
                self._drain_pending_batch(
                    fresh,
                    current_pending,
                    records,
                    journal_locked=True,
                )
                return fresh
        except journal.CoordinationRefusal as exc:
            raise _coordination_refusal(exc) from exc


@dataclasses.dataclass
class CommandContext:
    repo: Repository
    store: ChainStore
    options: CLIOptions
    policy: Policy | None = None

    def scripts_dir(self) -> Path:
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if plugin_root:
            return (Path(plugin_root).resolve() / "scripts" / "forge")
        return runtime.SCRIPT_DIR

    def plugin_root(self) -> Path:
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if plugin_root:
            return Path(plugin_root).resolve()
        return runtime.PLUGIN_ROOT

    def helper(self, name: str) -> Path:
        return self.scripts_dir() / name

    def command_digest(self, argv: Sequence[str]) -> str:
        return sha256_bytes(canonical_bytes(list(argv)))

    def validate_run_id(self) -> Path | None:
        if self.options.run_id is None:
            return None
        candidates = [
            self.repo.root / ".codex-orchestrator" / "runs" / self.options.run_id,
            self.store.common_root
            / ".codex-orchestrator"
            / "runs"
            / self.options.run_id,
        ]
        for candidate in candidates:
            resolved = Path(os.path.realpath(candidate))
            if resolved.is_dir():
                for allowed in (self.repo.root, self.store.common_root):
                    try:
                        resolved.relative_to(Path(os.path.realpath(allowed)))
                        return resolved
                    except ValueError:
                        continue
        raise Refusal(
            ReasonCode.CITATION_OUT_OF_ROOT,
            f"explicit run id does not resolve to a repository-contained run: {self.options.run_id}",
            expected="an existing .codex-orchestrator/runs/<run-id> directory",
            observed=self.options.run_id,
            remediation="rerun without --run-id or pass the exact open run id",
        )


def _policy_for_state(ctx: CommandContext, state: Mapping[str, Any]) -> Policy:
    sha = str(state["policy_source"].get("sha", ""))
    try:
        resolved, raw = ctx.repo.policy(sha)
        policy = parse_policy(resolved, raw)
    except (OSError, PolicyError, UnicodeError) as exc:
        raise Refusal(
            ReasonCode.POLICY_UNREADABLE,
            f"committed policy is unreadable while loading chain: {exc}",
            expected=f"git show {sha}:forge-project.md",
            observed=str(exc),
            remediation="restore readable committed policy, then abort and restart the chain",
            chain=state,
        ) from exc
    if policy.digest != state["policy_source"].get("digest"):
        raise FrozenError(
            "pinned committed policy digest no longer matches its Git object",
            chain_id=str(state["chain_id"]),
            state=str(state["state"]),
        )
    ctx.policy = policy
    return policy


def _fresh_reviewer_evals_required(
    ctx: CommandContext, state: Mapping[str, Any]
) -> bool:
    """Derive fresh-eval applicability from the pinned base policy and tree pair.

    A malformed/unreadable trigger derivation remains required for a control
    candidate so the dedicated gate can surface its exit-2 INVALID result.  It
    must never degrade into an untriggered fast path.
    """

    if not bool(state.get("tier", {}).get("control")):
        return False
    policy = ctx.policy or _policy_for_state(ctx, state)
    try:
        trigger = fresh_eval_module.derive_trigger(
            ctx.repo.candidate_context(),
            policy,
            state["candidate"],
            tuple(str(path) for path in state.get("paths", ())),
        )
    except (KeyError, TypeError, fresh_eval_module.FreshEvalError):
        return True
    return fresh_eval_module.trigger_required(trigger)


def _required_steps(ctx: CommandContext, state: Mapping[str, Any]) -> list[str]:
    policy = ctx.policy or _policy_for_state(ctx, state)
    result: list[str] = []
    if policy.changelog is not None:
        result.append("changelog")
    result.extend(["gate-1", "gate-1"])
    categories = [str(value) for value in state["tier"].get("categories", [])]
    for category in sorted(set(categories)):
        result.append(f"stack:{category}")
    result.append("assertion-sensor")
    for invariant in policy.invariants:
        if invariant["enforcement"] == "commit":
            result.append(f"invariant:{invariant['row_number']}")
    result.append("secret-scan")
    if state["tier"].get("control"):
        result.append("strict-evals")
        if _fresh_reviewer_evals_required(ctx, state):
            result.append(FRESH_REVIEWER_EVALS_GATE)
    return result
