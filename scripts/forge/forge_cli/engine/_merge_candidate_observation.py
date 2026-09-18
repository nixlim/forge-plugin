"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import base64
import binascii
from typing import Any, Mapping
from forge_cli import chain_core
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
import os
from pathlib import Path
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, V2ReasonCode
from forge_cli.policy import Policy, PolicyError, parse_policy, sha256_bytes


def _merge_candidate_observation_outputs(
    state: Mapping[str, Any], value: object
) -> dict[str, bytes] | None:
    if not chain_core._merge_candidate_observation_evidence_valid(state, value):
        return None
    assert isinstance(value, Mapping)
    outputs: dict[str, bytes] = {}
    for record in value["steps"]:
        child = record["child_result"]
        try:
            output = base64.b64decode(child["output_b64"], validate=True)
        except (ValueError, binascii.Error):
            return None
        if (
            child.get("authorized") is not True
            or child.get("exit") != 0
            or child.get("launch_failed") is not False
            or child.get("timed_out") is not False
            or child.get("output_limit_exceeded") is not False
            or child.get("group_survived") is not False
        ):
            return None
        outputs[str(record["step"])] = output
    return outputs


def _parse_merge_candidate_observation(
    state: Mapping[str, Any],
    value: object,
    *,
    verb: str,
    require_current_generation: bool,
) -> tuple[chain_core.Repository, Policy, tuple[str, ...], bytes, bytes | None]:
    """Consume only authenticated durable bytes; this function launches nothing."""

    outputs = _merge_candidate_observation_outputs(state, value)
    if outputs is None or not isinstance(value, Mapping) or value.get("verb") != verb:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: {verb} refused — candidate observation evidence is invalid",
            chain=state,
        )
    worktree = state.get("worktree")
    target = state.get("target")
    if not isinstance(worktree, Mapping) or not isinstance(target, Mapping):
        raise FrozenError(
            "merge candidate observation lacks its recorded identity",
            chain_id=str(state.get("chain_id", "")) or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    expected_head = str(value.get("expected_head", ""))
    remote_tip = str(value.get("remote_tip", ""))
    identity = outputs["identity"]
    try:
        identity_lines = identity.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree identity is invalid",
            observed=str(exc),
            chain=state,
        ) from exc
    if (
        len(identity_lines) != 4
        or any(not line.endswith("\n") or "\r" in line for line in identity_lines)
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree identity is invalid",
            observed="malformed combined rev-parse output",
            chain=state,
        )
    git_dir_raw, common_dir_raw, root_raw, head_raw = (
        line.removesuffix("\n") for line in identity_lines
    )
    if chain_core.COMMIT_RE.fullmatch(head_raw) is None:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree HEAD is invalid",
            observed=head_raw,
            chain=state,
        )
    observed_identity = {
        "path": os.path.realpath(root_raw),
        "git_dir": os.path.realpath(git_dir_raw),
        "common_dir": os.path.realpath(common_dir_raw),
    }
    expected_identity = {
        name: str(worktree.get(name, ""))
        for name in ("path", "git_dir", "common_dir")
    }
    if observed_identity != expected_identity:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree identity changed",
            expected=chain_core.canonical_bytes(expected_identity).decode("utf-8"),
            observed=chain_core.canonical_bytes(observed_identity).decode("utf-8"),
            chain=state,
        )
    try:
        inventory = chain_core._parse_registered_worktrees(outputs["worktrees"])
    except OSError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — registered worktree inventory is invalid",
            observed=str(exc),
            chain=state,
        ) from exc
    matches = [
        entry
        for entry in inventory
        if os.path.realpath(str(entry.get("worktree", "")))
        == expected_identity["path"]
    ]
    if (
        len(matches) != 1
        or not inventory
        or os.path.realpath(str(inventory[0].get("worktree", "")))
        == expected_identity["path"]
        or matches[0].get("HEAD") != head_raw
        or matches[0].get("branch") != state.get("branch")
        or outputs["branch"] != f"{state.get('branch')}\n".encode("utf-8")
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree registration changed",
            expected="one exact registered non-main worktree/branch/HEAD tuple",
            observed=str(matches),
            chain=state,
        )
    if head_raw != expected_head:
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            f"forge: {verb} refused — candidate HEAD is stale",
            expected=expected_head,
            observed=head_raw,
            chain=state,
        )
    if outputs["status"] != b"":
        raise chain_core._merge_refusal(
            V2ReasonCode.DIRTY_WORKTREE,
            f"forge: {verb} refused — source worktree is not clean",
            expected="zero exact status bytes",
            observed=outputs["status"].decode("utf-8", "replace"),
            chain=state,
        )
    for marker in (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "rebase-apply",
        "rebase-merge",
        "sequencer",
    ):
        try:
            os.lstat(Path(expected_identity["git_dir"]) / marker)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.WORKTREE_INVALID,
                f"forge: {verb} refused — Git operation metadata is unreadable",
                observed=str(exc),
                chain=state,
            ) from exc
        raise chain_core._merge_refusal(
            V2ReasonCode.DIRTY_WORKTREE,
            f"forge: {verb} refused — source worktree is not clean",
            observed=f"in-progress Git operation: {marker}",
            chain=state,
        )
    main_head = outputs["main-head"]
    manifest_commit = str(target.get("manifest_commit", ""))
    if main_head != f"{manifest_commit}\n".encode("ascii"):
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            f"forge: {verb} refused — fixed merge target changed",
            expected=manifest_commit,
            observed=main_head.decode("ascii", "replace").strip(),
            chain=state,
        )
    try:
        default_branch = _parse_plugin_manifest(outputs["manifest"])
    except (UnicodeError, ValueError) as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            f"forge: {verb} refused — committed target manifest is invalid",
            observed=str(exc),
            chain=state,
        ) from exc
    observed_target = {
        "remote": "origin",
        "destination_ref": f"refs/heads/{default_branch}",
        "manifest_commit": manifest_commit,
    }
    if observed_target != dict(target) or not outputs["origin"].strip():
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            f"forge: {verb} refused — fixed merge target changed",
            expected=chain_core.canonical_bytes(dict(target)).decode("utf-8"),
            observed=chain_core.canonical_bytes(observed_target).decode("utf-8"),
            chain=state,
        )
    try:
        policy = parse_policy(expected_head, outputs["policy"])
    except (PolicyError, UnicodeError) as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.POLICY_UNREADABLE,
            f"forge: {verb} refused — committed candidate policy is unreadable: {exc}",
            observed=str(exc),
            chain=state,
        ) from exc
    if outputs["tip"] != f"{remote_tip}\n".encode("ascii"):
        raise chain_core._merge_refusal(
            V2ReasonCode.FETCH_FAILED,
            f"forge: {verb} refused — fetched target tip is invalid",
            expected=remote_tip,
            observed=outputs["tip"].decode("ascii", "replace").strip(),
            chain=state,
        )
    try:
        changed_paths = tuple(
            sorted(
                {
                    item.decode("utf-8")
                    for item in outputs["names"].split(b"\0")
                    if item
                },
                key=lambda path: path.encode("utf-8"),
            )
        )
    except UnicodeDecodeError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — candidate paths are not UTF-8",
            observed=str(exc),
            chain=state,
        ) from exc
    if require_current_generation:
        candidate = state.get("candidate")
        policy_source = state.get("policy_source")
        if not isinstance(candidate, Mapping) or not isinstance(
            policy_source, Mapping
        ):
            raise FrozenError(
                "merge candidate tuple is unavailable",
                chain_id=str(state.get("chain_id", "")) or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if (
            policy.sha != policy_source.get("commit")
            or policy.digest != policy_source.get("digest")
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.CANDIDATE_STALE,
                f"forge: {verb} refused — committed candidate policy changed",
                expected=str(policy_source.get("digest")),
                observed=policy.digest,
                chain=state,
            )
        preimage = {
            "remote": "origin",
            "destination_ref": str(target["destination_ref"]),
            "remote_tip": remote_tip,
            "candidate_head": expected_head,
            "diff_sha256": sha256_bytes(outputs["diff"]),
            "policy_commit": policy.sha,
            "policy_digest": policy.digest,
            "worktree_identity": observed_identity,
            "generation": candidate.get("generation"),
        }
        observed_candidate = {
            **preimage,
            "generation_digest": sha256_bytes(chain_core.canonical_bytes(preimage)),
        }
        if observed_candidate != dict(candidate):
            raise chain_core._merge_refusal(
                V2ReasonCode.CANDIDATE_STALE,
                f"forge: {verb} refused — merge generation tuple is stale",
                expected=str(candidate.get("generation_digest")),
                observed=observed_candidate["generation_digest"],
                chain=state,
            )
    return (
        chain_core.Repository(Path(expected_identity["path"])),
        policy,
        changed_paths,
        outputs["diff"],
        outputs.get("classifier"),
    )
