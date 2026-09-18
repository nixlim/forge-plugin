"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from typing import Any, Mapping, MutableMapping
from forge_cli import chain_core, fresh_evals as fresh_eval_module, runtime
from forge_cli.engine._archive import _archive_module as _archive_module, _nul_git_paths as _nul_git_paths, _archive_close_tree_clean as _archive_close_tree_clean, _archive_parent_descriptor as _archive_parent_descriptor, _read_archive_candidate_at as _read_archive_candidate_at, _read_archive_candidate as _read_archive_candidate, _render_archive_bytes as _render_archive_bytes, _prepare_archive_candidate as _prepare_archive_candidate, _archive_recheck as _archive_recheck, _ARCHIVE_MODULE as _ARCHIVE_MODULE, _ARCHIVE_MODULE_LOCK as _ARCHIVE_MODULE_LOCK
from forge_cli.engine._classification import _classification_argv as _classification_argv, _classification_environment as _classification_environment, _run_classification as _run_classification
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._command_lock import _new_state as _new_state, _prove_run_task_binding as _prove_run_task_binding, _peek_chain_state as _peek_chain_state, _peek_raw_abort_state as _peek_raw_abort_state, _peek_selected_chain as _peek_selected_chain, _command_run_lock_id as _command_run_lock_id, abort_disposition_refusal as abort_disposition_refusal, _serialize_worktree_command as _serialize_worktree_command
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._fresh_eval import _FreshEvalArtifactIO as _FreshEvalArtifactIO, _fresh_eval_requests as _fresh_eval_requests, _fresh_eval_request_for_step as _fresh_eval_request_for_step, _validated_fresh_reviewer_manifest as _validated_fresh_reviewer_manifest
from forge_cli.engine._journal import _read_ingest_sources as _read_ingest_sources, _install_ingest_sources as _install_ingest_sources, _capture_ingest_inputs as _capture_ingest_inputs, _binding_for_commit_event as _binding_for_commit_event, _passed_stack_cell_is_intermediate as _passed_stack_cell_is_intermediate, _build_chain_journal_records as _build_chain_journal_records
from forge_cli.engine._merge_bootstrap_result import _decode_merge_bootstrap_result as _decode_merge_bootstrap_result
from forge_cli.engine._merge_candidate import _reset_merge_nonmovement_counter as _reset_merge_nonmovement_counter, _materialize_merge_candidate_tuple as _materialize_merge_candidate_tuple, _retain_or_advance_merge_candidate as _retain_or_advance_merge_candidate, _merge_scope_request as _merge_scope_request, _merge_scope_proof as _merge_scope_proof, _merge_released_predecessor as _merge_released_predecessor, _resolve_recorded_merge_tip as _resolve_recorded_merge_tip
from forge_cli.engine._merge_claim import _validate_merge_claim_record as _validate_merge_claim_record, _merge_owner_directory as _merge_owner_directory, _merge_claim_identity as _merge_claim_identity, _read_merge_claim as _read_merge_claim, _publish_merge_claim as _publish_merge_claim, _merge_publication_failure as _merge_publication_failure, _remove_merge_claim as _remove_merge_claim, _merge_unpublished_claim_absent as _merge_unpublished_claim_absent
from forge_cli.engine._merge_conflict import _merge_conflict_path_is_canonical as _merge_conflict_path_is_canonical, _parse_merge_conflict_paths as _parse_merge_conflict_paths, _normalize_merge_conflict_paths as _normalize_merge_conflict_paths, _merge_nonconflict_index_bytes as _merge_nonconflict_index_bytes, _merge_nonconflict_status_bytes as _merge_nonconflict_status_bytes, _observe_merge_conflict as _observe_merge_conflict, _observe_merge_post_add as _observe_merge_post_add, _merge_conflict_record as _merge_conflict_record, _merge_conflict_record_matches as _merge_conflict_record_matches, _merge_rebase_result_failed as _merge_rebase_result_failed
from forge_cli.engine._merge_epoch import _merge_run_directory as _merge_run_directory, _write_merge_artifact as _write_merge_artifact, _read_merge_artifact as _read_merge_artifact, _merge_gate_suite as _merge_gate_suite, _merge_gate_current as _merge_gate_current, _merge_event_digest as _merge_event_digest, _merge_epoch_fetch_observation_digest as _merge_epoch_fetch_observation_digest, _merge_inactive as _merge_inactive, _merge_has_attempt as _merge_has_attempt, _merge_inactive_epoch_has_no_started_child as _merge_inactive_epoch_has_no_started_child, _require_active_merge_epoch as _require_active_merge_epoch, _merge_process_unresolved as _merge_process_unresolved, _MergeEpochBudget as _MergeEpochBudget, _merge_epoch_suite as _merge_epoch_suite, _remote_observation_intent as _remote_observation_intent
from forge_cli.engine._merge_rebase_integrated import _merge_branch_reflog_proves_integrated as _merge_branch_reflog_proves_integrated, _merge_rebase_integrated_observation_binding as _merge_rebase_integrated_observation_binding, _merge_rebase_operation_metadata_absent as _merge_rebase_operation_metadata_absent, _merge_rebase_integrated_predicate as _merge_rebase_integrated_predicate
from forge_cli.engine._merge_scope_binding import _merge_scope_child_result as _merge_scope_child_result, MergeScopeBindingInspection as MergeScopeBindingInspection, _unlink_merge_scope_temporary_at as _unlink_merge_scope_temporary_at, _classify_merge_scope_binding_at as _classify_merge_scope_binding_at, _classify_merge_scope_binding as _classify_merge_scope_binding, _resume_merge_scope_binding as _resume_merge_scope_binding, _publish_merge_scope_binding as _publish_merge_scope_binding
from forge_cli.engine._merge_scope_derive import _merge_scope_environment as _merge_scope_environment, _GitNoLazyFetchQualification as _GitNoLazyFetchQualification, _git_environment_digest as _git_environment_digest, _git_executable_qualification as _git_executable_qualification, _qualify_git_no_lazy_fetch as _qualify_git_no_lazy_fetch, _require_git_no_lazy_fetch_qualification as _require_git_no_lazy_fetch_qualification, _discover_merge_scope_fence_from_sidecar as _discover_merge_scope_fence_from_sidecar, _parse_merge_name_status_output as _parse_merge_name_status_output, _parse_merge_scope_output as _parse_merge_scope_output, _derive_merge_scope as _derive_merge_scope
from forge_cli.engine._merge_worktree import _merge_cleanup_process_record as _merge_cleanup_process_record, _read_merge_git_metadata as _read_merge_git_metadata, _merge_cleanup_remote_fetch_observation as _merge_cleanup_remote_fetch_observation, _parse_plugin_manifest as _parse_plugin_manifest, _parse_history_mutation_mode as _parse_history_mutation_mode, _absolute_git_path as _absolute_git_path, _registered_worktrees as _registered_worktrees, _merge_worktree_status as _merge_worktree_status, _merge_owned_rebase_metadata as _merge_owned_rebase_metadata, _require_loud_merge_recovery_mode as _require_loud_merge_recovery_mode
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._review_transport import _review_package_is_oversized as _review_package_is_oversized, _review_complete_package_refusal as _review_complete_package_refusal, _review_master_window_count as _review_master_window_count, _review_master_transport as _review_master_transport, _review_master_identity as _review_master_identity, _review_master_leaf_is_valid as _review_master_leaf_is_valid, _read_review_master_digest as _read_review_master_digest, _read_review_master_window as _read_review_master_window, _assert_review_master_stable as _assert_review_master_stable, _iter_verified_master_package_windows as _iter_verified_master_package_windows, iter_verified_master_package_windows as iter_verified_master_package_windows
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
import copy
from forge_cli.envelope import FrozenError
from forge_cli.policy import sha256_bytes


def _fresh_reviewer_evidence_package(
    ctx: chain_core.CommandContext, state: Mapping[str, Any]
) -> bytes:
    """Build the complete, explicitly untrusted Gate-3 evidence segment."""

    if (
        chain_core._user_skip(state, chain_core.FRESH_REVIEWER_EVALS_GATE)
        is not None
        or not chain_core._fresh_reviewer_evals_required(ctx, state)
    ):
        return b""
    manifest, manifest_raw = _validated_fresh_reviewer_manifest(
        ctx, state, reobserve_index=True
    )
    baseline_runs = state.get("steps", {}).get("strict-evals")
    baseline = baseline_runs[-1] if isinstance(baseline_runs, list) and baseline_runs else None
    candidate = state.get("candidate", {}).get("sha256")
    if (
        not isinstance(baseline, Mapping)
        or baseline.get("candidate") != candidate
        or baseline.get("result") != "passed"
        or not isinstance(baseline.get("transcript"), str)
        or not isinstance(baseline.get("stdout_stderr_digest"), str)
    ):
        raise fresh_eval_module.FreshEvalError(
            "recorded-baseline integrity transcript is absent or stale"
        )
    baseline_raw = _read_bound_artifact(
        ctx,
        state,
        str(baseline["transcript"]),
        str(baseline["stdout_stderr_digest"]),
        "recorded-baseline integrity",
        max_bytes=runtime.OUTPUT_CAP_BYTES,
    )
    artifacts = _FreshEvalArtifactIO(ctx, state)
    results = manifest.get("results")
    suite = manifest.get("suite")
    if not isinstance(results, list) or not isinstance(suite, Mapping):
        raise fresh_eval_module.FreshEvalError(
            "fresh reviewer manifest summary is malformed"
        )
    verdict_sections: list[bytes] = []
    summaries: list[dict[str, object]] = []
    artifact_refs: list[dict[str, object]] = []
    for result in results:
        if not isinstance(result, Mapping):
            raise fresh_eval_module.FreshEvalError(
                "fresh reviewer manifest result is malformed"
            )
        fixture_id = str(result.get("fixture_id"))
        verdict_raw = artifacts.read(
            str(result.get("verdict_path")),
            str(result.get("verdict_sha256")),
            max_bytes=fresh_eval_module.VERDICT_CAP_BYTES,
        )
        verdict_sections.append(
            (
                f"\n--- fresh verdict {fixture_id} "
                f"sha256={result.get('verdict_sha256')} ---\n"
            ).encode("utf-8")
            + verdict_raw
        )
        summaries.append(
            {
                "actual_verdict": result.get("actual_verdict"),
                "expected_verdict": result.get("expected_verdict"),
                "fixture_id": fixture_id,
            }
        )
        artifact_refs.append(
            {
                "completion": {
                    "path": result.get("completion_path"),
                    "sha256": result.get("completion_sha256"),
                    "byte_count": result.get("completion_byte_count"),
                },
                "events": {
                    "path": result.get("events_path"),
                    "sha256": result.get("events_sha256"),
                    "byte_count": result.get("events_byte_count"),
                },
                "fixture_id": fixture_id,
                "prompt": {
                    "path": result.get("prompt_path"),
                    "sha256": result.get("prompt_sha256"),
                    "byte_count": result.get("prompt_byte_count"),
                },
                "verdict": {
                    "path": result.get("verdict_path"),
                    "sha256": result.get("verdict_sha256"),
                    "byte_count": result.get("verdict_byte_count"),
                },
            }
        )
    inventory = suite.get("inventory")
    excluded = [
        {
            "disposition": item.get("disposition"),
            "fixture_id": item.get("id"),
        }
        for item in (inventory if isinstance(inventory, list) else [])
        if isinstance(item, Mapping)
        and item.get("disposition") == "subject-specific-baseline-only"
    ]
    gate_runs = state["steps"][chain_core.FRESH_REVIEWER_EVALS_GATE]
    gate_record = gate_runs[-1]
    summary = {
        "artifact_refs": artifact_refs,
        "excluded_fixtures": excluded,
        "fresh_manifest": {
            "path": gate_record.get("manifest"),
            "sha256": gate_record.get("manifest_sha256"),
            "byte_count": gate_record.get("manifest_byte_count"),
        },
        "recorded_baseline": {
            "path": baseline.get("transcript"),
            "sha256": baseline.get("stdout_stderr_digest"),
        },
        "schema": "forge-review-fresh-eval-evidence/1",
        "trigger": manifest.get("trigger"),
        "verdict_summary": summaries,
    }
    segment = b"\n--- BEGIN UNTRUSTED FRESH REVIEWER EVALUATION EVIDENCE ---\n"
    segment += b"--- Recorded-baseline integrity transcript ---\n" + baseline_raw
    segment += b"\n--- canonical fresh reviewer manifest ---\n" + manifest_raw
    segment += b"\n--- fresh reviewer evidence summary ---\n"
    segment += chain_core.canonical_bytes(summary) + b"\n"
    segment += b"".join(verdict_sections)
    segment += b"\n--- END UNTRUSTED FRESH REVIEWER EVALUATION EVIDENCE ---\n"
    return segment


def _record_fresh_eval_terminal(
    ctx: chain_core.CommandContext,
    state: MutableMapping[str, Any],
    request: Mapping[str, Any],
    *,
    exit_code: int,
    diagnostic: str,
    duration_seconds: float,
    manifest_ref: str | None = None,
    manifest_sha256: str | None = None,
    manifest_byte_count: int | None = None,
) -> dict[str, Any]:
    """Atomically persist a terminal suite fact and its generation effect."""

    outcome = {0: "PASS", 1: "BLOCK", 2: "INVALID"}.get(exit_code)
    iteration = request.get("iteration")
    review = state.get("review")
    if (
        outcome is None
        or type(iteration) is not int
        or not 1 <= iteration <= 8
        or not isinstance(review, MutableMapping)
        or int(review.get("iteration", -1)) != iteration - 1
    ):
        raise FrozenError(
            "fresh reviewer terminal generation is malformed",
            chain_id=str(state.get("chain_id") or "unknown"),
            state=str(state.get("state") or "unknown"),
        )
    if exit_code in {1, 2}:
        review["iteration"] = iteration
        if exit_code == 1:
            _transition_state(state, "revising")
        if iteration >= 8:
            review["residual_risk"] = {
                "at": chain_core.iso_z(),
                "reason": "fresh reviewer evaluation iteration cap reached",
                "findings": [{"severity": "MAJOR", "text": diagnostic}],
            }

    output = diagnostic.encode("utf-8", "replace") + b"\n"
    synthetic = runtime.ProcessResult(
        argv=["forge", "gate", "run", chain_core.FRESH_REVIEWER_EVALS_GATE],
        returncode=exit_code,
        duration_seconds=duration_seconds,
        output=output,
        output_digest=sha256_bytes(output),
    )
    record_details: dict[str, Any] = {
        "kind": chain_core.FRESH_REVIEWER_EVALS_GATE,
        "request_id": request.get("request_id"),
        "iteration": iteration,
        "manifest": manifest_ref,
        "manifest_sha256": manifest_sha256,
        "outcome": outcome,
        "trigger": copy.deepcopy(request.get("trigger")),
        "diagnostic": diagnostic,
    }
    if manifest_byte_count is not None:
        record_details["manifest_byte_count"] = manifest_byte_count
    return _record_process_step(
        ctx,
        state,
        chain_core.FRESH_REVIEWER_EVALS_GATE,
        synthetic.argv,
        synthetic,
        details=record_details,
    )
