"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import copy
from typing import Any, Mapping
from forge_cli import chain_core, runtime
from forge_cli.engine._approval import _success as _success, _issue_authorization as _issue_authorization, _pid_is_running as _pid_is_running, _authorization_problem as _authorization_problem, _verify_operator_harness as _verify_operator_harness
from forge_cli.engine._archive import _archive_module as _archive_module, _nul_git_paths as _nul_git_paths, _archive_close_tree_clean as _archive_close_tree_clean, _archive_parent_descriptor as _archive_parent_descriptor, _read_archive_candidate_at as _read_archive_candidate_at, _read_archive_candidate as _read_archive_candidate, _render_archive_bytes as _render_archive_bytes, _prepare_archive_candidate as _prepare_archive_candidate, _archive_recheck as _archive_recheck, _ARCHIVE_MODULE as _ARCHIVE_MODULE, _ARCHIVE_MODULE_LOCK as _ARCHIVE_MODULE_LOCK
from forge_cli.engine._candidate_ops import _invalidate_candidate_evidence as _invalidate_candidate_evidence, _candidate_patch_ref as _candidate_patch_ref, _install_candidate_snapshot as _install_candidate_snapshot, _adopt_out_of_band_candidate as _adopt_out_of_band_candidate, _stage_paths as _stage_paths
from forge_cli.engine._classification import _classification_argv as _classification_argv, _classification_environment as _classification_environment, _run_classification as _run_classification
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._command_lock import _new_state as _new_state, _prove_run_task_binding as _prove_run_task_binding, _peek_chain_state as _peek_chain_state, _peek_raw_abort_state as _peek_raw_abort_state, _peek_selected_chain as _peek_selected_chain, _command_run_lock_id as _command_run_lock_id, abort_disposition_refusal as abort_disposition_refusal, _serialize_worktree_command as _serialize_worktree_command
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._finalize import FinalizeContext as FinalizeContext, PRODUCED_COMMIT_CHECKS as PRODUCED_COMMIT_CHECKS, _finalize_produced_identity as _finalize_produced_identity, _finalize_halt as _finalize_halt, _finalize_lock as _finalize_lock, _finalize_candidate as _finalize_candidate, _finalize_evidence as _finalize_evidence, _finalize_fresh_reviewer_evals as _finalize_fresh_reviewer_evals, _finalize_ttl as _finalize_ttl, _finalize_tree_drift as _finalize_tree_drift, FINALIZE_CHECKS as FINALIZE_CHECKS
from forge_cli.engine._fresh_eval import _fresh_eval_requests as _fresh_eval_requests, _fresh_eval_request_for_step as _fresh_eval_request_for_step
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
from forge_cli.envelope import V2ReasonCode
from forge_cli.policy import sha256_bytes
import json
import sys
from pathlib import Path


def _merge_scope_from_candidate_observation(
    admission: MergeAdmission, observation: Mapping[str, Any]
) -> MergeScopeResult | None:
    snapshot = admission.run_task
    if snapshot is None:
        return None
    synthetic_state = {
        "chain_id": observation.get("chain_id"),
        "repository": str(admission.repository),
        "worktree": copy.deepcopy(admission.worktree_identity),
        "branch": admission.branch,
        "target": copy.deepcopy(admission.target),
        "run_binding": copy.deepcopy(snapshot.binding),
        "candidate": (
            {"generation_digest": observation.get("generation_digest")}
            if observation.get("generation_digest") is not None
            else None
        ),
    }
    outputs = _merge_candidate_observation_outputs(
        synthetic_state, observation
    )
    if outputs is None or "scope" not in outputs:
        raise chain_core._merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: merge start refused — durable run/task scope evidence is unavailable",
        )
    try:
        changed_paths = _parse_merge_scope_output(outputs["scope"])
    except ValueError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: merge start refused — durable run/task scope evidence is malformed",
            observed=str(exc),
        ) from exc
    _batch, _builders, journal = runtime._coordination_modules()
    out_of_scope = tuple(
        path
        for path in changed_paths
        if not any(
            journal.pathspec_contained(path, pattern)
            for pattern in snapshot.task_files
        )
        or not any(
            journal.pathspec_contained(path, pattern)
            for pattern in snapshot.admitted_scope
        )
    )
    argv = chain_core._merge_scope_argv(
        admission.worktree,
        str(observation["remote_tip"]),
        admission.candidate_head,
    )
    scope_record = next(
        record
        for record in observation["steps"]
        if record.get("step") == "scope"
    )
    return MergeScopeResult(
        argv=tuple(argv),
        command_digest=sha256_bytes(chain_core.canonical_bytes(argv)),
        environment_digest=sha256_bytes(
            chain_core.canonical_bytes(chain_core._merge_scope_environment_contract())
        ),
        output_digest=str(scope_record["child_result"]["output_digest"]),
        changed_paths=changed_paths,
        out_of_scope_paths=out_of_scope,
        result="exceeded" if out_of_scope else "contained",
    )


def bind_merge_candidate_generation(
    ctx: chain_core.CommandContext,
    admission: MergeAdmission,
    remote_tip: str,
    *,
    generation: int = 1,
    scope_result: MergeScopeResult | None | object = _DERIVE_MERGE_SCOPE,
    fixed_tip_bound: bool = False,
    observation: Mapping[str, Any] | None = None,
    diff_output_digest: str | None = None,
) -> MergeCandidateGeneration:
    """Bind one fixed fetched base to the exact DM-014 generation tuple."""

    chain_core._require_merge_adapter_control("admission-and-generation")
    if (
        chain_core.COMMIT_RE.fullmatch(remote_tip) is None
        or generation <= 0
        or (
            diff_output_digest is not None
            and chain_core.SHA256_RE.fullmatch(diff_output_digest) is None
        )
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.FETCH_FAILED,
            "forge: merge start refused — fetched target tip is invalid",
            expected="a full fixed Git object ID and positive generation",
            observed=remote_tip,
        )
    candidate_repo = chain_core.Repository(admission.worktree)
    observed_paths: tuple[str, ...] | None = None
    classifier_output: bytes | None = None
    if observation is not None:
        observation_generation = observation.get("generation_digest")
        observation_state: dict[str, Any] = {
            "chain_id": observation.get("chain_id"),
            "repository": str(admission.repository),
            "worktree": copy.deepcopy(admission.worktree_identity),
            "branch": admission.branch,
            "target": copy.deepcopy(admission.target),
            "run_binding": (
                copy.deepcopy(admission.run_task.binding)
                if admission.run_task is not None
                else None
            ),
            "candidate": (
                {"generation_digest": observation_generation}
                if observation_generation is not None
                else None
            ),
        }
        if (
            observation.get("expected_head") != admission.candidate_head
            or observation.get("remote_tip") != remote_tip
            or observation.get("classify") is not True
            or observation.get("declared_tier") != admission.declared_tier
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: merge start refused — candidate observation is not generation-bound",
                expected="one complete generation-bound classification observation",
                observed=str(observation.get("evidence_digest")),
            )
        (
            candidate_repo,
            observed_policy,
            observed_paths,
            diff,
            classifier_output,
        ) = _parse_merge_candidate_observation(
            observation_state,
            observation,
            verb=str(observation.get("verb", "merge start")),
            require_current_generation=False,
        )
        if (
            observed_policy.sha != admission.policy.sha
            or observed_policy.digest != admission.policy.digest
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.CANDIDATE_STALE,
                "forge: merge start refused — committed candidate policy changed",
                expected=admission.policy.digest,
                observed=observed_policy.digest,
            )
    elif not fixed_tip_bound:
        resolved_tip = candidate_repo.git(
            ["rev-parse", "--verify", f"{remote_tip}^{{commit}}"], check=False
        )
        if (
            resolved_tip.returncode != 0
            or resolved_tip.stdout.decode("ascii", "replace").strip() != remote_tip
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.FETCH_FAILED,
                "forge: merge start refused — fetched target tip is invalid",
                expected="a locally available full fixed commit object ID",
                observed=remote_tip,
            )
    if observation is None and candidate_repo.head() != admission.candidate_head:
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            "forge: merge start refused — candidate HEAD changed after admission",
            expected=admission.candidate_head,
            observed=candidate_repo.head(),
        )
    if observation is None:
        _merge_worktree_status(
            candidate_repo, Path(admission.worktree_identity["git_dir"])
        )
        if diff_output_digest is None:
            try:
                diff = candidate_repo.git(
                    ["diff", f"{remote_tip}...{admission.candidate_head}"]
                ).stdout
            except OSError as exc:
                raise chain_core._merge_refusal(
                    V2ReasonCode.EVIDENCE_INCOMPLETE,
                    "forge: merge start refused — fixed candidate diff is unavailable",
                    expected=f"git diff {remote_tip}...{admission.candidate_head}",
                    observed=str(exc),
                ) from exc
    generation_preimage: dict[str, Any] = {
        "remote": "origin",
        "destination_ref": admission.target["destination_ref"],
        "remote_tip": remote_tip,
        "candidate_head": admission.candidate_head,
        "diff_sha256": (
            diff_output_digest
            if diff_output_digest is not None
            else sha256_bytes(diff)
        ),
        "policy_commit": admission.candidate_head,
        "policy_digest": admission.policy.digest,
        "worktree_identity": copy.deepcopy(admission.worktree_identity),
        "generation": generation,
    }
    candidate = {
        **generation_preimage,
        "generation_digest": sha256_bytes(chain_core.canonical_bytes(generation_preimage)),
    }
    # FR-231 requires the run-bound scope proof before classification.  The
    # lifecycle adapter invokes this function immediately after its fenced
    # fixed-tip fetch; this pure adapter must not reverse those two judgments.
    scope = (
        _merge_scope_from_candidate_observation(admission, observation)
        if observation is not None and scope_result is _DERIVE_MERGE_SCOPE
        else _derive_merge_scope(admission, remote_tip)
        if scope_result is _DERIVE_MERGE_SCOPE
        else scope_result
    )
    if scope is not None and not isinstance(scope, MergeScopeResult):
        raise TypeError("merge scope override is malformed")
    if scope is not None:
        changed_paths = scope.changed_paths
    elif observed_paths is not None:
        changed_paths = observed_paths
    else:
        try:
            names = candidate_repo.git(
                [
                    "diff",
                    "--name-only",
                    "-z",
                    "--diff-filter=ACDMRTUXB",
                    f"{remote_tip}...{admission.candidate_head}",
                    "--",
                ]
            ).stdout
        except OSError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: merge start refused — candidate path set is unavailable",
                expected="the complete fixed-range changed-path set",
                observed=str(exc),
            ) from exc
        try:
            changed_paths = tuple(
                sorted(
                    {
                        value.decode("utf-8")
                        for value in names.split(b"\0")
                        if value
                    },
                    key=lambda value: value.encode("utf-8"),
                )
            )
        except UnicodeDecodeError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.WORKTREE_INVALID,
                "forge: merge start refused — candidate paths are not UTF-8",
                observed=str(exc),
            ) from exc
    if classifier_output is None:
        argv = [
            sys.executable,
            str(ctx.helper("risk_tier.py")),
            "--repo",
            str(admission.worktree),
            "--policy-sha",
            admission.candidate_head,
            "--range",
            f"{remote_tip}...{admission.candidate_head}",
        ]
        if admission.declared_tier is not None:
            argv.extend(["--declared-tier", admission.declared_tier])
        try:
            process = runtime.run_bounded(
                argv,
                cwd=admission.worktree,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=ctx.options.verbose,
            )
        except OSError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: merge start refused — risk-tier classification did not pass",
                expected="risk_tier.py --range to launch within the fixed bounds",
                observed=str(exc),
            ) from exc
        if (
            process.returncode != 0
            or process.timed_out
            or process.output_limit
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: merge start refused — risk-tier classification did not pass",
                expected="risk_tier.py --range exit 0 within the fixed bounds",
                observed=f"exit={process.returncode}",
            )
        classifier_output = process.output
    try:
        evidence = json.loads(classifier_output)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: merge start refused — risk-tier classification is malformed",
            observed=str(exc),
        ) from exc
    if (
        not isinstance(evidence, dict)
        or evidence.get("policy_sha") != admission.candidate_head
        or evidence.get("derived_tier") not in chain_core.TIER_RANK
        or evidence.get("effective_tier") not in chain_core.TIER_RANK
        or not isinstance(evidence.get("paths"), list)
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: merge start refused — risk-tier evidence is not candidate-bound",
            expected=admission.candidate_head,
            observed=str(evidence),
        )
    categories: set[str] = set()
    control = False
    classified_paths: list[str] = []
    for path_evidence in evidence["paths"]:
        path_tier = (
            path_evidence.get("path_tier")
            if isinstance(path_evidence, dict)
            and "path_tier" in path_evidence
            else path_evidence.get("tier")
            if isinstance(path_evidence, dict)
            else None
        )
        if (
            not isinstance(path_evidence, dict)
            or not isinstance(path_evidence.get("path"), str)
            or not isinstance(path_evidence.get("categories"), list)
            or not all(
                isinstance(value, str) and value
                for value in path_evidence["categories"]
            )
            or path_tier not in chain_core.TIER_RANK
            or (
                "path_tier" in path_evidence
                and "tier" in path_evidence
                and path_evidence.get("path_tier") != path_evidence.get("tier")
            )
            or type(path_evidence.get("control_floor")) is not bool
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: merge start refused — risk-tier evidence is not candidate-bound",
                expected="one complete classifier row for every exact changed path",
                observed=str(path_evidence),
            )
        classified_paths.append(str(path_evidence["path"]))
        categories.update(
            str(value)
            for value in path_evidence["categories"]
        )
        control = control or bool(path_evidence.get("control_floor"))
    if (
        len(classified_paths) != len(set(classified_paths))
        or tuple(
            sorted(classified_paths, key=lambda value: value.encode("utf-8"))
        )
        != changed_paths
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: merge start refused — risk-tier evidence is not candidate-bound",
            expected=str(changed_paths),
            observed=str(classified_paths),
        )
    return MergeCandidateGeneration(
        candidate=candidate,
        tier={"control": control, "categories": sorted(categories)},
        classification=copy.deepcopy(evidence),
        changed_paths=changed_paths,
        scope=scope,
    )
