"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping, MutableMapping
from forge_cli import chain_core, fresh_evals as fresh_eval_module
from forge_cli.engine._archive import _archive_module as _archive_module, _nul_git_paths as _nul_git_paths, _archive_close_tree_clean as _archive_close_tree_clean, _archive_parent_descriptor as _archive_parent_descriptor, _read_archive_candidate_at as _read_archive_candidate_at, _read_archive_candidate as _read_archive_candidate, _render_archive_bytes as _render_archive_bytes, _prepare_archive_candidate as _prepare_archive_candidate, _archive_recheck as _archive_recheck, _ARCHIVE_MODULE as _ARCHIVE_MODULE, _ARCHIVE_MODULE_LOCK as _ARCHIVE_MODULE_LOCK
from forge_cli.engine._classification import _classification_argv as _classification_argv, _classification_environment as _classification_environment, _run_classification as _run_classification
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._command_lock import _new_state as _new_state, _prove_run_task_binding as _prove_run_task_binding, _peek_chain_state as _peek_chain_state, _peek_raw_abort_state as _peek_raw_abort_state, _peek_selected_chain as _peek_selected_chain, _command_run_lock_id as _command_run_lock_id, abort_disposition_refusal as abort_disposition_refusal, _serialize_worktree_command as _serialize_worktree_command
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification, _fresh_eval_invalid_refusal as _fresh_eval_invalid_refusal
from forge_cli.engine._fresh_eval import _fresh_eval_requests as _fresh_eval_requests, _fresh_eval_request_for_step as _fresh_eval_request_for_step, _validated_fresh_reviewer_manifest as _validated_fresh_reviewer_manifest
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
from forge_cli.envelope import Refusal
import dataclasses
import re


def _current_test_paths(
    ctx: chain_core.CommandContext, state: Mapping[str, Any] | None = None
) -> list[str]:
    result: list[str] = []
    paths = state.get("paths", []) if isinstance(state, Mapping) else ctx.repo.staged_paths()
    for path in paths:
        name = Path(path).name.lower()
        if (
            "tests/" in path.replace("\\", "/")
            or name.startswith("test_")
            or name.endswith("_test.py")
            or ".test." in name
            or ".spec." in name
        ):
            result.append(path)
    return result


def _void_mismatched_gate_one_pair(
    ctx: chain_core.CommandContext, state: MutableMapping[str, Any]
) -> bool:
    """Void both observations when the newest Gate-1 pair changes context."""
    runs = state["steps"].get("gate-1")
    if not isinstance(runs, list) or len(runs) < 2:
        return False
    candidate = state["candidate"].get("sha256")
    current = [
        record
        for record in runs
        if isinstance(record, dict) and record.get("candidate") == candidate
    ]
    if len(current) < 2:
        return False
    previous, newest = current[-2:]
    if (
        previous.get("result") != "passed"
        or newest.get("result") != "passed"
        or previous.get("pair_voided")
        or newest.get("pair_voided")
        or previous.get("env_fingerprint") == newest.get("env_fingerprint")
    ):
        return False
    marker = {
        "at": chain_core.iso_z(),
        "reason": "DM-013 env_fingerprint mismatch voided the Gate-1 pair",
        "fingerprints": [
            str(previous.get("env_fingerprint")),
            str(newest.get("env_fingerprint")),
        ],
    }
    # Once a later observation invalidates the context sequence, no earlier
    # unvoided run may be paired across that boundary.  Two fresh observations
    # are required after the mismatch.
    for record in current:
        if record.get("result") == "passed" and not record.get("pair_voided"):
            record["pair_voided"] = copy.deepcopy(marker)
    ctx.store.persist(
        state,
        "gate_1_pair_voided",
        {"reason": marker["reason"], "fingerprints": marker["fingerprints"]},
    )
    return True


def _fresh_reviewer_pass_claimed(state: Mapping[str, Any]) -> bool:
    """Distinguish an absent fresh gate from malformed claimed-PASS evidence."""

    steps = state.get("steps")
    runs = (
        steps.get(chain_core.FRESH_REVIEWER_EVALS_GATE)
        if isinstance(steps, Mapping)
        else None
    )
    latest = runs[-1] if isinstance(runs, list) and runs else None
    candidate = state.get("candidate")
    expected = candidate.get("sha256") if isinstance(candidate, Mapping) else None
    return bool(
        isinstance(latest, Mapping)
        and latest.get("candidate") == expected
        and (
            latest.get("result") == "passed"
            or latest.get("outcome") == "PASS"
            or latest.get("exit_code") == 0
        )
    )


def _fresh_reviewer_block_claimed(state: Mapping[str, Any]) -> bool:
    """Recognize the current terminal BLOCK that an operator may waive."""

    steps = state.get("steps")
    runs = (
        steps.get(chain_core.FRESH_REVIEWER_EVALS_GATE)
        if isinstance(steps, Mapping)
        else None
    )
    latest = runs[-1] if isinstance(runs, list) and runs else None
    candidate = state.get("candidate")
    expected = candidate.get("sha256") if isinstance(candidate, Mapping) else None
    return bool(
        isinstance(latest, Mapping)
        and latest.get("candidate") == expected
        and latest.get("result") == "failed"
        and latest.get("outcome") == "BLOCK"
    )


def _mechanical_complete(ctx: chain_core.CommandContext, state: Mapping[str, Any]) -> bool:
    needed = chain_core._required_steps(ctx, state)
    gate_one_seen = False
    for step_id in needed:
        if step_id == "gate-1":
            if gate_one_seen:
                continue
            gate_one_seen = True
            if not chain_core._gate_one_complete(state):
                return False
        elif step_id == chain_core.FRESH_REVIEWER_EVALS_GATE:
            if chain_core._user_skip(state, step_id) is not None:
                continue
            if not _fresh_reviewer_pass_claimed(state):
                return False
            try:
                _validated_fresh_reviewer_manifest(
                    ctx, state, reobserve_index=False
                )
            except fresh_eval_module.FreshEvalError as exc:
                raise _fresh_eval_invalid_refusal(state, str(exc)) from exc
            except Refusal as exc:
                raise _fresh_eval_invalid_refusal(
                    state, exc.message, evidence_refs=exc.evidence_refs
                ) from exc
        elif not chain_core._gate_satisfied(state, step_id):
            return False
    return True


def _next_incomplete(ctx: chain_core.CommandContext, state: Mapping[str, Any]) -> str | None:
    gate_one_counted = 0
    candidate = state["candidate"].get("sha256")
    runs = state["steps"].get("gate-1", [])
    current_gate_runs = [
        record
        for record in runs
        if isinstance(record, dict)
        and record.get("candidate") == candidate
        and record.get("result") == "passed"
        and not record.get("pair_voided")
    ] if isinstance(runs, list) else []
    for step_id in chain_core._required_steps(ctx, state):
        if step_id == "gate-1":
            gate_one_counted += 1
            if chain_core._user_skip(state, "gate-1") is not None:
                continue
            if gate_one_counted == 1:
                if not current_gate_runs:
                    return "gate-1"
                continue
            if not chain_core._gate_one_complete(state):
                return "gate-1"
            continue
        if step_id == chain_core.FRESH_REVIEWER_EVALS_GATE:
            if chain_core._user_skip(state, step_id) is not None:
                continue
            if not _fresh_reviewer_pass_claimed(state):
                return step_id
            try:
                _validated_fresh_reviewer_manifest(
                    ctx, state, reobserve_index=False
                )
            except fresh_eval_module.FreshEvalError as exc:
                raise _fresh_eval_invalid_refusal(state, str(exc)) from exc
            except Refusal as exc:
                raise _fresh_eval_invalid_refusal(
                    state, exc.message, evidence_refs=exc.evidence_refs
                ) from exc
            continue
        if not chain_core._gate_satisfied(state, step_id):
            return step_id
    return None


@dataclasses.dataclass(frozen=True)
class SecretFinding:
    rule_id: str
    path: str
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {"line": self.line, "path": self.path, "rule_id": self.rule_id}


def scan_added_secrets(diff: bytes) -> list[SecretFinding]:
    text = diff.decode("utf-8", "replace")
    current_path = ""
    new_line = 0
    findings: list[SecretFinding] = []
    env_assignments: dict[str, list[int]] = {}
    for raw_line in text.splitlines():
        if raw_line.startswith("+++ "):
            label = raw_line[4:]
            current_path = label[2:] if label.startswith("b/") else label
            continue
        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
        if hunk:
            new_line = int(hunk.group(1))
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            content = raw_line[1:]
            for rule_id, pattern in SECRET_RULES:
                match = pattern.search(content)
                if not match:
                    continue
                if rule_id == "generic-secret-assignment" and PLACEHOLDER_RE.fullmatch(
                    match.group(1)
                ):
                    continue
                findings.append(SecretFinding(rule_id, current_path, new_line))
            if re.fullmatch(r"(?:^|.*/)\.env(?:\.[^/]*)?", current_path) and re.match(
                r"^[A-Za-z_][A-Za-z0-9_]*=.+", content
            ):
                env_assignments.setdefault(current_path, []).append(new_line)
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            continue
        elif raw_line.startswith(" "):
            new_line += 1
    for path, lines in env_assignments.items():
        if len(lines) >= 5:
            findings.append(SecretFinding("env-file-bulk-add", path, lines[0]))
    unique = {(item.rule_id, item.path, item.line): item for item in findings}
    return [unique[key] for key in sorted(unique)]
