"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from typing import Any, MutableMapping, Mapping, Sequence
from forge_cli.engine._archive import _archive_module as _archive_module, _nul_git_paths as _nul_git_paths, _archive_close_tree_clean as _archive_close_tree_clean, _archive_parent_descriptor as _archive_parent_descriptor, _read_archive_candidate_at as _read_archive_candidate_at, _read_archive_candidate as _read_archive_candidate, _render_archive_bytes as _render_archive_bytes, _prepare_archive_candidate as _prepare_archive_candidate, _archive_recheck as _archive_recheck, _ARCHIVE_MODULE as _ARCHIVE_MODULE, _ARCHIVE_MODULE_LOCK as _ARCHIVE_MODULE_LOCK
from forge_cli.engine._classification import _classification_argv as _classification_argv, _classification_environment as _classification_environment, _run_classification as _run_classification
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._command_lock import _new_state as _new_state, _prove_run_task_binding as _prove_run_task_binding, _peek_chain_state as _peek_chain_state, _peek_raw_abort_state as _peek_raw_abort_state, _peek_selected_chain as _peek_selected_chain, _command_run_lock_id as _command_run_lock_id, abort_disposition_refusal as abort_disposition_refusal, _serialize_worktree_command as _serialize_worktree_command
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._fresh_eval import _fresh_eval_requests as _fresh_eval_requests, _fresh_eval_request_for_step as _fresh_eval_request_for_step
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
from pathlib import Path
from forge_cli import candidate as candidate_module, chain_core
from forge_cli.envelope import ReasonCode, Refusal, FrozenError, V2ReasonCode


def _invalidate_candidate_evidence(
    state: MutableMapping[str, Any],
    *,
    preserve_diff_scoped: bool = False,
    preserve_operator_cosign: bool = False,
) -> None:
    preserved: dict[str, Any] = {}
    if preserve_diff_scoped:
        for key in ("secret-scan",):
            if key in state["steps"]:
                preserved[key] = state["steps"][key]
    state["steps"] = preserved
    operator_cosign = bool(state["review"].get("operator_cosign_required"))
    state["review"]["request"] = None
    state["review"]["verdict"] = None
    state["review"]["dispositions"] = []
    state["review"]["operator_cosign_required"] = (
        operator_cosign if preserve_operator_cosign else False
    )
    state["approval"] = {}
    state["authorization"] = {}
    state["commit_result"] = {}


def _candidate_patch_ref(state: Mapping[str, Any]) -> str:
    record = state.get("candidate")
    if not isinstance(record, Mapping):
        return ""
    authorization_id = record.get("authorization_id")
    review_digest = record.get("review_diff_sha256")
    if not isinstance(authorization_id, str) or not isinstance(review_digest, str):
        return ""
    return (
        Path(".forge")
        / "chains"
        / str(state["chain_id"])
        / "candidate"
        / f"{authorization_id}-{review_digest}.patch"
    ).as_posix()


def _candidate_snapshot(
    ctx: chain_core.CommandContext, state: Mapping[str, Any]
) -> candidate_module.CandidateSnapshot:
    try:
        return ctx.repo.candidate_snapshot(computed_at=chain_core.iso_z())
    except candidate_module.CandidateError as exc:
        reason = (
            ReasonCode.STATE_PRECONDITION
            if exc.kind == "state-precondition"
            else ReasonCode.EVIDENCE_INCOMPLETE
        )
        raise Refusal(
            reason,
            f"candidate snapshot could not be completed: {exc}",
            expected="a complete bounded Git-tree candidate snapshot",
            observed=str(exc),
            remediation=chain_core._forge_command(
                state, "commit restage --paths <path>..."
            ),
            chain=state,
        ) from exc


def _install_candidate_snapshot(
    ctx: chain_core.CommandContext,
    state: MutableMapping[str, Any],
    snapshot: candidate_module.CandidateSnapshot,
) -> None:
    if state.get("run_binding") is not None:
        invalid_paths = [
            path
            for path in snapshot.paths
            if not candidate_module.valid_scope_path(path)
        ]
        if invalid_paths:
            raise Refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: commit start refused — run/task binding is invalid",
                expected=(
                    "every concrete candidate path satisfies the committed "
                    "run-scope pathname contract"
                ),
                observed=", ".join(repr(path) for path in invalid_paths),
                remediation="inspect the named run/task and retry the exact paired start",
                chain=state,
            )
    state["candidate"] = snapshot.state_record()
    state["paths"] = list(snapshot.paths)
    state["staging"]["staged_paths"] = list(snapshot.paths)
    relative = (
        Path("candidate")
        / f"{snapshot.authorization_id}-{snapshot.review_diff_sha256}.patch"
    ).as_posix()
    expected_ref = (
        Path(".forge") / "chains" / str(state["chain_id"]) / relative
    ).as_posix()
    try:
        _write_artifact(ctx, state, relative, snapshot.review_diff, exclusive=True)
    except FileExistsError:
        existing = _read_bound_artifact(
            ctx,
            state,
            expected_ref,
            snapshot.review_diff_sha256,
            "candidate review patch",
            max_bytes=candidate_module.REVIEW_DIFF_MAX_BYTES,
        )
        if existing != snapshot.review_diff:
            raise FrozenError(
                "candidate review patch identity collision",
                chain_id=str(state["chain_id"]),
                state=str(state["state"]),
            )


def _candidate_review_diff(
    ctx: chain_core.CommandContext, state: Mapping[str, Any]
) -> bytes:
    record = state.get("candidate")
    reference = _candidate_patch_ref(state)
    if not chain_core.candidate_is_v2(state) or not reference:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "legacy candidate must be restaged before evidence can advance",
            expected=candidate_module.CANDIDATE_SCHEMA,
            observed=str(record.get("schema") if isinstance(record, Mapping) else None),
            remediation=chain_core._forge_command(
                state, "commit restage --paths <path>..."
            ),
            chain=state,
        )
    assert isinstance(record, Mapping)
    data = _read_bound_artifact(
        ctx,
        state,
        reference,
        str(record["review_diff_sha256"]),
        "candidate review patch",
        max_bytes=candidate_module.REVIEW_DIFF_MAX_BYTES,
    )
    if len(data) != record.get("review_diff_byte_count"):
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "candidate review patch byte count changed",
            expected=str(record.get("review_diff_byte_count")),
            observed=str(len(data)),
            remediation=chain_core._forge_command(state, "commit restage --paths <path>..."),
            chain=state,
            evidence_refs=[reference],
        )
    return data


def _adopt_out_of_band_candidate(
    ctx: chain_core.CommandContext,
    state: MutableMapping[str, Any],
    observed_candidate: str,
    *,
    detected_by: str,
) -> tuple[str, bool]:
    """Adopt the complete staged set, invalidate evidence, and reclassify."""
    old_candidate = str(state["candidate"].get("sha256") or "")
    old_paths = list(state.get("paths", []))
    snapshot = _candidate_snapshot(ctx, state)
    if snapshot.authorization_id != observed_candidate:
        raise FrozenError(
            "candidate changed during out-of-band adoption",
            chain_id=str(state["chain_id"]),
            state=str(state["state"]),
        )
    _install_candidate_snapshot(ctx, state, snapshot)
    staged_paths = list(snapshot.paths)
    anomaly = {
        "at": chain_core.iso_z(),
        "kind": "out-of-band-index-change",
        "old_candidate": old_candidate,
        "new_candidate": observed_candidate,
        "old_paths": old_paths,
        "new_paths": list(staged_paths),
        "detected_by": detected_by,
    }
    state["staging"]["anomalies"].append(anomaly)
    _invalidate_candidate_evidence(state, preserve_operator_cosign=True)
    _transition_state(state, "classifying")
    ctx.store.persist(
        state,
        "candidate_invalidated",
        {
            "old_candidate": old_candidate,
            "new_candidate": observed_candidate,
            "old_paths": old_paths,
            "new_paths": list(staged_paths),
            "out_of_band": True,
            "detected_by": detected_by,
        },
    )
    has_candidate_bytes = bool(snapshot.paths)
    if has_candidate_bytes:
        _run_classification(ctx, state)
    return old_candidate, has_candidate_bytes


def _stage_paths(
    ctx: chain_core.CommandContext,
    state: MutableMapping[str, Any],
    paths: Sequence[str],
    *,
    clear_old: bool,
) -> tuple[str | None, str]:
    old_candidate = state["candidate"].get("sha256")
    if clear_old:
        staged_before = ctx.repo.staged_paths()
        if staged_before:
            ctx.repo.git(["reset", "-q", "HEAD", "--", *staged_before])
    ctx.repo.git(["add", "--", *paths])
    snapshot = _candidate_snapshot(ctx, state)
    if not snapshot.paths:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "staging produced an empty candidate",
            expected="nonempty git diff --cached",
            observed="empty staged diff",
            remediation="edit the named paths before starting/restaging",
            chain=state,
        )
    if snapshot.base_commit_oid != state.get("repo_head"):
        raise Refusal(
            ReasonCode.HEAD_MOVED,
            "candidate base changed while staging",
            expected=str(state.get("repo_head")),
            observed=str(snapshot.base_commit_oid),
            remediation=chain_core._forge_command(state, "commit rebase"),
            chain=state,
        )
    _install_candidate_snapshot(ctx, state, snapshot)
    state["staging"]["staged_at"] = chain_core.iso_z()
    return (
        str(old_candidate) if old_candidate else None,
        snapshot.authorization_id,
    )
