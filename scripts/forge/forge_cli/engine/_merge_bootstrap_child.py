"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import base64
import hashlib
import json
import os
import selectors
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence
from forge_cli import chain_core, runtime
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
import sys


def _merge_bootstrap_child_main(encoded_payload: str) -> int:
    """Execute the Revision-12 composite child protocol.

    This entry point runs only inside the already fenced, isolated process
    group.  Full-patch stdout is fed directly into SHA-256 and is never added
    to a bytearray, protocol record, diagnostic, or parent pipe.
    """

    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload.encode("ascii")))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        os.write(1, chain_core.canonical_bytes({"schema": "forge-bootstrap-composite-error/1", "error": str(exc)}))
        return 2
    cap = int(payload.get("cap", runtime.OUTPUT_CAP_BYTES))
    worktree = Path(str(payload["worktree"]))
    candidate_head = str(payload["candidate_head"])
    supplied_tip = payload.get("remote_tip")
    run_bound = payload.get("run_bound") is True

    def stop(process: subprocess.Popen[bytes]) -> None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=chain_core.FENCED_CHILD_STOP_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=chain_core.FENCED_CHILD_REAP_SECONDS)
        except subprocess.TimeoutExpired:
            pass

    def run_constituent(
        argv: Sequence[str], *, retain_stdout: bool, stream_stdout: bool
    ) -> tuple[dict[str, Any], bytes]:
        direct_argv = [str(value) for value in argv]
        stdout_digest = hashlib.sha256()
        stderr_digest = hashlib.sha256()
        stdout_total = 0
        stderr_total = 0
        kept = bytearray()
        try:
            process = subprocess.Popen(
                direct_argv,
                cwd=worktree,
                env=dict(os.environ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=False,
            )
        except OSError:
            return (
                {
                    "argv": direct_argv,
                    "exit": None,
                    "output_digest": hashlib.sha256(b"").hexdigest(),
                    "stderr_digest": hashlib.sha256(b"").hexdigest(),
                    "launch_failed": True,
                    "output_limit_exceeded": False,
                },
                b"",
            )
        assert process.stdout is not None and process.stderr is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        limited = False
        try:
            while selector.get_map():
                for key, _mask in selector.select(0.05):
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "stdout":
                        stdout_digest.update(chunk)
                        stdout_total += len(chunk)
                        if retain_stdout and len(kept) < cap:
                            kept.extend(chunk[: cap - len(kept)])
                        if not stream_stdout and stdout_total > cap:
                            limited = True
                    else:
                        stderr_digest.update(chunk)
                        stderr_total += len(chunk)
                    if (
                        stderr_total > cap
                        if stream_stdout
                        else stdout_total + stderr_total > cap
                    ):
                        limited = True
                    if limited:
                        stop(process)
                        break
                if limited:
                    break
            if not limited:
                returncode = process.wait()
            else:
                returncode = process.returncode
        finally:
            selector.close()
            process.stdout.close()
            process.stderr.close()
        return (
            {
                "argv": direct_argv,
                "exit": returncode,
                "output_digest": stdout_digest.hexdigest(),
                "stderr_digest": stderr_digest.hexdigest(),
                "launch_failed": False,
                "output_limit_exceeded": limited,
            },
            bytes(kept),
        )

    def passed(record: Mapping[str, Any]) -> bool:
        return bool(
            record.get("exit") == 0
            and record.get("launch_failed") is False
            and record.get("output_limit_exceeded") is False
        )

    fetch_argv = payload.get("fetch_argv")
    if not isinstance(fetch_argv, list):
        return 2
    constituent_order: list[str] = ["fetch"]
    fetch, _fetch_output = run_constituent(
        [str(value) for value in fetch_argv],
        retain_stdout=False,
        stream_stdout=False,
    )
    resolved_tip: str | None = None
    if passed(fetch):
        if isinstance(supplied_tip, str):
            resolved_tip = supplied_tip
        else:
            try:
                raw = Path(str(payload["git_dir"]), "FETCH_HEAD").read_bytes()
                rows = raw.splitlines()
                oid = rows[0].split(b"\t", 1)[0].decode("ascii")
                if (
                    len(raw) > chain_core.MERGE_SCOPE_BINDING_CAP_BYTES
                    or not raw.endswith(b"\n")
                    or len(rows) != 1
                    or chain_core.COMMIT_RE.fullmatch(oid) is None
                ):
                    raise ValueError("invalid FETCH_HEAD")
                resolved_tip = oid
            except (OSError, UnicodeError, ValueError, IndexError):
                fetch = {**fetch, "exit": 1}

    scope: dict[str, Any] | None = None
    changed_paths: list[str] | None = None
    if passed(fetch) and resolved_tip is not None and run_bound:
        constituent_order.append("name-status")
        scope_argv = chain_core._merge_scope_argv(worktree, resolved_tip, candidate_head)
        scope, scope_output = run_constituent(
            scope_argv, retain_stdout=True, stream_stdout=False
        )
        if passed(scope):
            try:
                changed_paths = list(_parse_merge_name_status_output(scope_output))
            except (UnicodeError, ValueError):
                scope = {**scope, "exit": 1}
                changed_paths = None

    full_patch: dict[str, Any] | None = None
    if (
        passed(fetch)
        and resolved_tip is not None
        and (scope is None or passed(scope))
    ):
        constituent_order.append("full-patch")
        full_patch, _never_retained = run_constituent(
            chain_core._merge_full_patch_argv(worktree, resolved_tip, candidate_head),
            retain_stdout=False,
            stream_stdout=True,
        )
    protocol = {
        "schema": "forge-bootstrap-composite-result/1",
        "constituent_order": constituent_order,
        "environment_digest": _git_environment_digest(os.environ),
        "resolved_tip": resolved_tip,
        "fetch": fetch,
        "scope": scope,
        "scope_changed_paths": changed_paths,
        "full_patch": full_patch,
    }
    encoded = chain_core.canonical_bytes(protocol)
    if len(encoded) > runtime.OUTPUT_CAP_BYTES:
        return 3
    os.write(1, encoded)
    return 0


def _merge_bootstrap_child_argv(
    admission: MergeAdmission,
    *,
    fetch_argv: Sequence[str],
    remote_tip: str | None,
) -> list[str]:
    payload = {
        "schema": "forge-bootstrap-composite-request/1",
        "worktree": str(admission.worktree),
        "git_dir": str(admission.worktree_identity["git_dir"]),
        "candidate_head": admission.candidate_head,
        "remote_tip": remote_tip,
        "run_bound": admission.run_task is not None,
        "fetch_argv": list(fetch_argv),
        "cap": runtime.OUTPUT_CAP_BYTES,
    }
    encoded = base64.urlsafe_b64encode(chain_core.canonical_bytes(payload)).decode("ascii")
    return [
        sys.executable,
        "-c",
        _MERGE_BOOTSTRAP_CHILD_SOURCE,
        # phase 3: the re-exec target stays the shim entry point (scripts/forge/cli.py),
        # which forwards _merge_bootstrap_child_main to this module when loaded standalone;
        # resolved from runtime's own location so it does not depend on this file's depth.
        str(Path(runtime.__file__).resolve().parents[1] / "cli.py"),
        encoded,
    ]
