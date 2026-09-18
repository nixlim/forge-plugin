"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import dataclasses
from typing import TYPE_CHECKING, Any, MutableMapping, Callable, Mapping

if TYPE_CHECKING:
    from forge_cli.engine._engine import Engine
from forge_cli.engine._approval import _success as _success, _issue_authorization as _issue_authorization, _pid_is_running as _pid_is_running, _authorization_problem as _authorization_problem, _verify_operator_harness as _verify_operator_harness
from forge_cli.engine._archive import _archive_module as _archive_module, _nul_git_paths as _nul_git_paths, _archive_close_tree_clean as _archive_close_tree_clean, _archive_parent_descriptor as _archive_parent_descriptor, _read_archive_candidate_at as _read_archive_candidate_at, _read_archive_candidate as _read_archive_candidate, _render_archive_bytes as _render_archive_bytes, _prepare_archive_candidate as _prepare_archive_candidate, _archive_recheck as _archive_recheck, _ARCHIVE_MODULE as _ARCHIVE_MODULE, _ARCHIVE_MODULE_LOCK as _ARCHIVE_MODULE_LOCK
from forge_cli.engine._candidate_ops import _invalidate_candidate_evidence as _invalidate_candidate_evidence, _candidate_patch_ref as _candidate_patch_ref, _install_candidate_snapshot as _install_candidate_snapshot, _adopt_out_of_band_candidate as _adopt_out_of_band_candidate, _stage_paths as _stage_paths
from forge_cli.engine._classification import _classification_argv as _classification_argv, _classification_environment as _classification_environment, _run_classification as _run_classification
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._command_lock import _new_state as _new_state, _prove_run_task_binding as _prove_run_task_binding, _peek_chain_state as _peek_chain_state, _peek_raw_abort_state as _peek_raw_abort_state, _peek_selected_chain as _peek_selected_chain, _command_run_lock_id as _command_run_lock_id, abort_disposition_refusal as abort_disposition_refusal, _serialize_worktree_command as _serialize_worktree_command
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification, _fresh_eval_invalid_refusal as _fresh_eval_invalid_refusal
from forge_cli.engine._fresh_eval import _fresh_eval_requests as _fresh_eval_requests, _fresh_eval_request_for_step as _fresh_eval_request_for_step, _validated_fresh_reviewer_manifest as _validated_fresh_reviewer_manifest
from forge_cli.engine._gate_checks import _current_test_paths as _current_test_paths, _void_mismatched_gate_one_pair as _void_mismatched_gate_one_pair, _fresh_reviewer_pass_claimed as _fresh_reviewer_pass_claimed, _mechanical_complete as _mechanical_complete, _next_incomplete as _next_incomplete, SecretFinding as SecretFinding, scan_added_secrets as scan_added_secrets
from forge_cli.engine._journal import _read_ingest_sources as _read_ingest_sources, _install_ingest_sources as _install_ingest_sources, _capture_ingest_inputs as _capture_ingest_inputs, _binding_for_commit_event as _binding_for_commit_event, _passed_stack_cell_is_intermediate as _passed_stack_cell_is_intermediate, _build_chain_journal_records as _build_chain_journal_records
from forge_cli.engine._merge_bootstrap_child import _merge_bootstrap_child_main as _merge_bootstrap_child_main, _merge_bootstrap_child_argv as _merge_bootstrap_child_argv
from forge_cli.engine._merge_bootstrap_result import _decode_merge_bootstrap_result as _decode_merge_bootstrap_result
from forge_cli.engine._merge_candidate import _reset_merge_nonmovement_counter as _reset_merge_nonmovement_counter, _materialize_merge_candidate_tuple as _materialize_merge_candidate_tuple, _retain_or_advance_merge_candidate as _retain_or_advance_merge_candidate, _merge_scope_request as _merge_scope_request, _merge_scope_proof as _merge_scope_proof, _merge_released_predecessor as _merge_released_predecessor, _resolve_recorded_merge_tip as _resolve_recorded_merge_tip
from forge_cli.engine._merge_candidate_observation import _merge_candidate_observation_outputs as _merge_candidate_observation_outputs, _parse_merge_candidate_observation as _parse_merge_candidate_observation
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
from forge_cli.policy import Policy, sha256_bytes
from forge_cli import candidate as candidate_module, chain_core, runtime, fresh_evals as fresh_eval_module
import copy
from forge_cli.envelope import FrozenError, OUTPUT_SCHEMA, Outcome, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal
import os
import re


@dataclasses.dataclass
class FinalizeContext:
    engine: Engine
    state: MutableMapping[str, Any]
    policy: Policy
    message: str
    lock_acquired: bool = False
    lock_session_pid: str = ""
    produced_sha: str | None = None
    produced_identity: dict[str, Any] | None = None


@dataclasses.dataclass(frozen=True)
class ProducedCommitContext:
    pre_head: str
    expected_tree_oid: str
    expected_message_digest: str
    produced_sha: str
    commit: candidate_module.CommitObject


def _produced_head_moved(context: ProducedCommitContext) -> bool:
    return context.produced_sha != context.pre_head


def _produced_single_parent(context: ProducedCommitContext) -> bool:
    return context.commit.parent_headers == (context.pre_head,)


def _produced_exact_tree(context: ProducedCommitContext) -> bool:
    return context.commit.tree_headers == (context.expected_tree_oid,)


def _produced_exact_message(context: ProducedCommitContext) -> bool:
    return sha256_bytes(context.commit.message) == context.expected_message_digest


PRODUCED_COMMIT_CHECKS: dict[str, Callable[[ProducedCommitContext], bool]] = {
    "head-movement": _produced_head_moved,
    "exact-single-parent": _produced_single_parent,
    "exact-tree": _produced_exact_tree,
    "exact-message": _produced_exact_message,
}


def _finalize_produced_identity(context: FinalizeContext) -> bool:
    """Inspect one produced commit through bounded plumbing and all four seams."""

    state = context.state
    intent = state.get("commit_result", {}).get("intent")
    produced_sha = context.produced_sha
    if not isinstance(intent, Mapping) or not isinstance(produced_sha, str):
        context.produced_identity = {
            "result": "failed",
            "produced_sha": str(produced_sha or ""),
            "expected": {},
            "observed": {"error": "produced commit intent is incomplete"},
            "checks": {name: False for name in PRODUCED_COMMIT_CHECKS},
        }
        return False
    expected = {
        "parent": str(intent.get("pre_head") or ""),
        "tree": str(intent.get("expected_tree_oid") or ""),
        "message_digest": str(intent.get("message_digest") or ""),
    }
    try:
        commit = context.engine.ctx.repo.read_commit_object(produced_sha)
        produced_context = ProducedCommitContext(
            pre_head=expected["parent"],
            expected_tree_oid=expected["tree"],
            expected_message_digest=expected["message_digest"],
            produced_sha=produced_sha,
            commit=commit,
        )
        checks = {
            name: bool(predicate(produced_context))
            for name, predicate in PRODUCED_COMMIT_CHECKS.items()
        }
        observed = {
            "parent": list(commit.parent_headers[:2]),
            "parent_count": len(commit.parent_headers),
            "tree": list(commit.tree_headers[:2]),
            "tree_count": len(commit.tree_headers),
            "message_digest": sha256_bytes(commit.message),
        }
        raw = commit.raw
    except (candidate_module.CandidateError, OSError, ValueError) as exc:
        checks = {name: False for name in PRODUCED_COMMIT_CHECKS}
        observed = {"error": str(exc), "parent": [], "tree": [], "message_digest": ""}
        raw = chain_core.canonical_bytes({"error": str(exc), "produced_sha": produced_sha})
    result = "passed" if all(checks.values()) else "failed"
    transcript_ref = _write_artifact(
        context.engine.ctx,
        state,
        f"commit/identity-{produced_sha}.txt",
        raw,
        exclusive=False,
    )
    context.produced_identity = {
        "result": result,
        "produced_sha": produced_sha,
        "expected": expected,
        "observed": observed,
        "checks": checks,
        "transcript": transcript_ref,
    }
    return result == "passed"


def _record_produced_identity(
    context: FinalizeContext,
) -> dict[str, Any]:
    state = context.state
    existing = state.get("commit_result", {}).get("identity")
    if isinstance(existing, dict):
        return existing
    result = context.produced_identity
    if not isinstance(result, dict):
        raise FrozenError(
            "produced commit identity result is unavailable",
            chain_id=str(state["chain_id"]),
            state="committing",
        )
    state["commit_result"]["identity"] = copy.deepcopy(result)
    if result.get("result") == "failed":
        state["commit_result"]["mismatch_latched"] = True
    context.engine.ctx.store.persist(
        state,
        "commit_identity_checked",
        copy.deepcopy(result),
    )
    return result


def _produced_mismatch_outcome(
    state: Mapping[str, Any], result: Mapping[str, Any]
) -> Outcome:
    expected = chain_core.canonical_bytes(result.get("expected", {})).decode("utf-8")
    observed = chain_core.canonical_bytes(result.get("observed", {})).decode("utf-8")
    transcript = result.get("transcript")
    revision9 = state.get("run_binding") is not None or _archive_metadata(state) is not None
    return Outcome(
        ok=False,
        reason_code=ReasonCode.FROZEN_CHAIN,
        message=PRODUCED_COMMIT_MISMATCH,
        chain_id=str(state["chain_id"]),
        state="committing",
        expected=expected,
        observed=observed,
        remediation=chain_core._forge_command(state, "status"),
        next_required_step=chain_core._forge_command(state, "status"),
        evidence_refs=(str(transcript),) if isinstance(transcript, str) else (),
        schema=REVISION9_OUTPUT_SCHEMA if revision9 else OUTPUT_SCHEMA,
    )


def _finalize_halt(context: FinalizeContext) -> bool:
    _run_halt(context.engine.ctx, context.state)
    return True


def _finalize_lock(context: FinalizeContext) -> bool:
    session_pid = os.environ.get("FORGE_SESSION_PID") or str(os.getpid())
    if not re.fullmatch(r"[1-9][0-9]*", session_pid):
        session_pid = str(os.getpid())
    environment = os.environ.copy()
    environment["FORGE_SESSION_PID"] = session_pid
    try:
        process = runtime.run_bounded(
            ["bash", str(context.engine.ctx.helper("acquire-commit-lock.sh"))],
            cwd=context.engine.ctx.repo.root,
            env=environment,
            timeout=305.0,
            verbose=context.engine.ctx.options.verbose,
        )
    except OSError as exc:
        raise Refusal(
            ReasonCode.LOCK_UNAVAILABLE,
            f"commit lock could not be launched: {exc}",
            expected="acquire-commit-lock.sh exit 0",
            observed=str(exc),
            remediation=chain_core._forge_command(context.state, "commit finalize --message <message>"),
            chain=context.state,
        ) from exc
    if process.returncode != 0 or process.timed_out or process.output_limit:
        raise Refusal(
            ReasonCode.LOCK_UNAVAILABLE,
            "commit lock acquisition failed or timed out",
            expected="acquire-commit-lock.sh exit 0",
            observed=process.output.decode("utf-8", "replace").strip() or f"exit {process.returncode}",
            remediation=chain_core._forge_command(context.state, "commit finalize --message <message>"),
            chain=context.state,
        )
    context.lock_acquired = True
    context.lock_session_pid = session_pid
    return True


def _finalize_candidate(context: FinalizeContext) -> bool:
    current_head = context.engine.ctx.repo.head()
    if current_head != context.state["repo_head"]:
        context.engine._record_head_moved(context.state, current_head)
        raise Refusal(
            ReasonCode.HEAD_MOVED,
            (
                "out-of-band commit, not chain corruption: "
                f"{context.state['repo_head']} -> {current_head}"
            ),
            expected=str(context.state["repo_head"]),
            observed=current_head,
            remediation=chain_core._forge_command(context.state, "commit rebase"),
            chain=context.state,
        )
    record = context.state["candidate"]
    if not chain_core.candidate_is_v2(context.state):
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "legacy candidate must be restaged before finalize",
            expected=candidate_module.CANDIDATE_SCHEMA,
            observed=str(record.get("schema")),
            remediation=chain_core._forge_command(
                context.state, "commit restage --paths <path>..."
            ),
            chain=context.state,
        )
    expected = str(record.get("sha256"))
    try:
        observation = context.engine.ctx.repo.candidate_observation()
    except candidate_module.CandidateError as exc:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "finalize candidate byte-identity check failed",
            expected=expected,
            observed=str(exc),
            remediation=chain_core._forge_command(
                context.state, "commit restage --paths <path>..."
            ),
            chain=context.state,
        ) from exc
    observed = observation.authorization_id
    if (
        observed != expected
        or observation.object_format != record.get("object_format")
        or observation.tree_oid != record.get("tree_oid")
    ):
        raise Refusal(
            ReasonCode.CANDIDATE_STALE,
            "finalize candidate byte-identity check failed",
            expected=expected,
            observed=observed,
            remediation=chain_core._forge_command(context.state, "commit restage --paths <path>..."),
            chain=context.state,
        )
    return True


def _finalize_evidence(context: FinalizeContext) -> bool:
    state = context.state
    if not chain_core._latest_current_pass(state, "classification"):
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "finalize requires current-candidate classification evidence",
            expected=f"classification PASS naming {state['candidate'].get('sha256')}",
            observed=str(state["steps"].get("classification")),
            remediation=chain_core._forge_command(state, "classify"),
            chain=state,
        )
    fast_skips = runtime._fast_mechanical_skips(state)
    if fast_skips:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "fast tier cannot rely on an operator skip for a mechanical control",
            expected="all fast-tier mechanical rows PASS without skips",
            observed=", ".join(fast_skips),
            remediation=chain_core._forge_command(state, "commit restage --paths <path>..."),
            chain=state,
        )
    if state["tier"].get("effective") == "fast" and not chain_core._latest_current_pass(
        state, "fast-eligibility"
    ):
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "fast finalize requires authorization-time eligibility evidence",
            expected="current-candidate fast-eligibility PASS",
            observed=str(state["steps"].get("fast-eligibility")),
            remediation=chain_core._forge_command(state, "verify"),
            chain=state,
        )
    if not _mechanical_complete(context.engine.ctx, state):
        missing = _next_incomplete(context.engine.ctx, state)
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            f"finalize evidence is incomplete at required step: {missing}",
            expected="every required mechanical step current-candidate PASS or operator skip",
            observed=str(missing),
            remediation=chain_core._forge_command(state, "verify"),
            chain=state,
        )
    effective = state["tier"].get("effective")
    if effective != "fast":
        review = state["review"].get("verdict")
        skipped_review = chain_core._user_skip(state, "review") is not None
        if not (
            isinstance(review, dict)
            and review.get("verdict") == "PASS"
            and review.get("candidate") == state["candidate"].get("sha256")
        ) and not skipped_review:
            raise Refusal(
                ReasonCode.EVIDENCE_INCOMPLETE,
                "required reviewer PASS is absent or bound to a stale candidate",
                expected=f"PASS naming {state['candidate'].get('sha256')}",
                observed=str(review),
                remediation=chain_core._forge_command(state, "review request"),
                chain=state,
            )
    if state["tier"].get("control") or state["review"].get(
        "operator_cosign_required"
    ):
        approval = state.get("approval", {})
        if approval.get("candidate") != state["candidate"].get("sha256") or not approval.get(
            "approved_at"
        ) or not isinstance(approval.get("qualification"), dict) or not chain_core._latest_current_pass(
            state, "approval-qualification"
        ):
            raise Refusal(
                ReasonCode.APPROVAL_REQUIRED,
                "finalize requires qualified operator approval naming the current candidate",
                expected=str(state["candidate"].get("sha256")),
                observed=str(approval.get("candidate")),
                remediation=chain_core._forge_command(
                    state,
                    f"commit approve --candidate {state['candidate'].get('sha256')}",
                ),
                chain=state,
            )
    return True


def _finalize_fresh_reviewer_evals(context: FinalizeContext) -> bool:
    """Re-prove triggered fresh evidence, including a live index observation."""

    if (
        chain_core._user_skip(
            context.state, chain_core.FRESH_REVIEWER_EVALS_GATE
        )
        is not None
    ):
        return True
    if not chain_core._fresh_reviewer_evals_required(
        context.engine.ctx, context.state
    ):
        return True
    try:
        _validated_fresh_reviewer_manifest(
            context.engine.ctx, context.state, reobserve_index=True
        )
    except fresh_eval_module.FreshEvalError as exc:
        raise _fresh_eval_invalid_refusal(context.state, str(exc)) from exc
    except Refusal as exc:
        raise _fresh_eval_invalid_refusal(
            context.state, exc.message, evidence_refs=exc.evidence_refs
        ) from exc
    return True


def _finalize_ttl(context: FinalizeContext) -> bool:
    problem = _authorization_problem(context.state)
    if problem is not None:
        raise problem
    return True


def _finalize_tree_drift(context: FinalizeContext) -> bool:
    paths = list(context.state.get("paths", []))
    drift = context.engine.ctx.repo.tree_index_drift(paths)
    if drift and chain_core._user_skip(context.state, "index-drift") is None:
        raise Refusal(
            ReasonCode.DRIFT_TREE_INDEX,
            f"working tree differs from staged candidate at finalize: {', '.join(drift)}",
            expected="tree bytes equal staged bytes or operator index-drift skip",
            observed=", ".join(drift),
            remediation=chain_core._forge_command(context.state, "commit restage --paths <path>..."),
            chain=context.state,
        )
    return True


FINALIZE_CHECKS: dict[str, Callable[[FinalizeContext], bool | None]] = {
    "evidence-completeness": _finalize_evidence,
    "fresh-reviewer-evals": _finalize_fresh_reviewer_evals,
    "candidate-byte-identity": _finalize_candidate,
    "produced-commit-identity": _finalize_produced_identity,
    "ttl-token": _finalize_ttl,
    "tree-index-drift": _finalize_tree_drift,
    "halt": _finalize_halt,
    "lock": _finalize_lock,
}
