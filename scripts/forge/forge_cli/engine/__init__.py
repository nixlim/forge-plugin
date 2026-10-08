"""Forge commit/merge engine public exports.

The owning modules implement command admission, chain-local evidence, review,
classification, gates, approval, finalize and merge bootstrap/recovery. Runtime
controls are read through forge_cli.runtime. Re-exports are snapshots; tests
patch the owning module through patch_engine.
"""

from __future__ import annotations

from typing import Any as Any, Mapping as Mapping, MutableMapping as MutableMapping, Sequence as Sequence
from pathlib import Path as Path
from forge_cli import chain_core as chain_core, runtime as runtime
import copy as copy
import hashlib as hashlib
import json as json
import os as os
import re as re
import secrets as secrets
import stat as stat
import subprocess as subprocess
import sys as sys
import time as time

from forge_cli.envelope import FrozenError as FrozenError, Outcome as Outcome, REVISION9_OUTPUT_SCHEMA as REVISION9_OUTPUT_SCHEMA, ReasonCode as ReasonCode, Refusal as Refusal, V2ReasonCode as V2ReasonCode
from forge_cli.policy import PolicyError as PolicyError, parse_policy as parse_policy, sha256_bytes as sha256_bytes

from ._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, CLAUDE_EXECUTABLE as CLAUDE_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
from ._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from ._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from ._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from ._command_lock import _new_state as _new_state, _serialize_worktree_command as _serialize_worktree_command
from ._review_transport import _review_package_is_oversized as _review_package_is_oversized, _review_complete_package_refusal as _review_complete_package_refusal, _review_master_window_count as _review_master_window_count, _review_master_transport as _review_master_transport, _review_master_identity as _review_master_identity, _review_master_leaf_is_valid as _review_master_leaf_is_valid, _read_review_master_digest as _read_review_master_digest, _read_review_master_window as _read_review_master_window, _assert_review_master_stable as _assert_review_master_stable, _iter_verified_master_package_windows as _iter_verified_master_package_windows, iter_verified_master_package_windows as iter_verified_master_package_windows
from ._fresh_eval import _fresh_eval_requests as _fresh_eval_requests, _fresh_eval_request_for_step as _fresh_eval_request_for_step
from ._classification import _classification_argv as _classification_argv, _classification_environment as _classification_environment, _run_classification as _run_classification
from ._merge_candidate import _reset_merge_nonmovement_counter as _reset_merge_nonmovement_counter, _materialize_merge_candidate_tuple as _materialize_merge_candidate_tuple, _retain_or_advance_merge_candidate as _retain_or_advance_merge_candidate, _merge_released_predecessor as _merge_released_predecessor, _resolve_recorded_merge_tip as _resolve_recorded_merge_tip
from ._merge_worktree import _merge_cleanup_process_record as _merge_cleanup_process_record, _read_merge_git_metadata as _read_merge_git_metadata, _merge_cleanup_remote_fetch_observation as _merge_cleanup_remote_fetch_observation, _parse_plugin_manifest as _parse_plugin_manifest, _parse_history_mutation_mode as _parse_history_mutation_mode, _absolute_git_path as _absolute_git_path, _registered_worktrees as _registered_worktrees, _merge_worktree_status as _merge_worktree_status, _merge_owned_rebase_metadata as _merge_owned_rebase_metadata, _require_loud_merge_recovery_mode as _require_loud_merge_recovery_mode
from ._merge_conflict import _merge_conflict_path_is_canonical as _merge_conflict_path_is_canonical, _parse_merge_conflict_paths as _parse_merge_conflict_paths, _normalize_merge_conflict_paths as _normalize_merge_conflict_paths, _merge_nonconflict_index_bytes as _merge_nonconflict_index_bytes, _merge_nonconflict_status_bytes as _merge_nonconflict_status_bytes, _observe_merge_conflict as _observe_merge_conflict, _observe_merge_post_add as _observe_merge_post_add, _merge_conflict_record as _merge_conflict_record, _merge_conflict_record_matches as _merge_conflict_record_matches, _merge_rebase_result_failed as _merge_rebase_result_failed
from ._merge_rebase_integrated import _merge_branch_reflog_proves_integrated as _merge_branch_reflog_proves_integrated, _merge_rebase_integrated_observation_binding as _merge_rebase_integrated_observation_binding, _merge_rebase_operation_metadata_absent as _merge_rebase_operation_metadata_absent, _merge_rebase_integrated_predicate as _merge_rebase_integrated_predicate
from ._merge_scope_derive import _merge_scope_environment as _merge_scope_environment, _GitNoLazyFetchQualification as _GitNoLazyFetchQualification, _git_environment_digest as _git_environment_digest, _git_executable_qualification as _git_executable_qualification, _qualify_git_no_lazy_fetch as _qualify_git_no_lazy_fetch, _require_git_no_lazy_fetch_qualification as _require_git_no_lazy_fetch_qualification, _discover_merge_scope_fence_from_sidecar as _discover_merge_scope_fence_from_sidecar
from ._merge_bootstrap_result import _decode_merge_bootstrap_result as _decode_merge_bootstrap_result
from ._merge_claim import _validate_merge_claim_record as _validate_merge_claim_record, _merge_owner_directory as _merge_owner_directory, _merge_claim_identity as _merge_claim_identity, _read_merge_claim as _read_merge_claim, _publish_merge_claim as _publish_merge_claim, _merge_publication_failure as _merge_publication_failure, _remove_merge_claim as _remove_merge_claim, _merge_unpublished_claim_absent as _merge_unpublished_claim_absent
from ._merge_epoch import _write_merge_artifact as _write_merge_artifact, _read_merge_artifact as _read_merge_artifact, _merge_gate_suite as _merge_gate_suite, _merge_gate_current as _merge_gate_current, _merge_event_digest as _merge_event_digest, _merge_epoch_fetch_observation_digest as _merge_epoch_fetch_observation_digest, _merge_inactive as _merge_inactive, _merge_has_attempt as _merge_has_attempt, _merge_inactive_epoch_has_no_started_child as _merge_inactive_epoch_has_no_started_child, _require_active_merge_epoch as _require_active_merge_epoch, _merge_process_unresolved as _merge_process_unresolved, _MergeEpochBudget as _MergeEpochBudget, _merge_epoch_suite as _merge_epoch_suite, _remote_observation_intent as _remote_observation_intent
from ._merge_scope_binding import _merge_scope_child_result as _merge_scope_child_result, MergeScopeBindingInspection as MergeScopeBindingInspection, _unlink_merge_scope_temporary_at as _unlink_merge_scope_temporary_at, _classify_merge_scope_binding_at as _classify_merge_scope_binding_at, _classify_merge_scope_binding as _classify_merge_scope_binding, _resume_merge_scope_binding as _resume_merge_scope_binding, _publish_merge_scope_binding as _publish_merge_scope_binding
from ._candidate_ops import _invalidate_candidate_evidence as _invalidate_candidate_evidence, _candidate_patch_ref as _candidate_patch_ref, _install_candidate_snapshot as _install_candidate_snapshot, _adopt_out_of_band_candidate as _adopt_out_of_band_candidate, _stage_paths as _stage_paths
from ._gate_checks import _current_test_paths as _current_test_paths, _record_docs_class_gate_one_skip as _record_docs_class_gate_one_skip, _fresh_reviewer_pass_claimed as _fresh_reviewer_pass_claimed, _mechanical_complete as _mechanical_complete, _next_incomplete as _next_incomplete, SecretFinding as SecretFinding, scan_added_secrets as scan_added_secrets
from ._approval import _success as _success, _issue_authorization as _issue_authorization, _pid_is_running as _pid_is_running, _authorization_problem as _authorization_problem, _verify_operator_harness as _verify_operator_harness
from ._merge_bootstrap_child import _merge_bootstrap_child_main as _merge_bootstrap_child_main, _merge_bootstrap_child_argv as _merge_bootstrap_child_argv
from ._merge_candidate_observation import _merge_candidate_observation_outputs as _merge_candidate_observation_outputs, _parse_merge_candidate_observation as _parse_merge_candidate_observation
from ._merge_candidate_generation import bind_merge_candidate_generation as bind_merge_candidate_generation
from ._finalize import FinalizeContext as FinalizeContext, PRODUCED_COMMIT_CHECKS as PRODUCED_COMMIT_CHECKS, _finalize_produced_identity as _finalize_produced_identity, _finalize_halt as _finalize_halt, _finalize_lock as _finalize_lock, _finalize_candidate as _finalize_candidate, _finalize_evidence as _finalize_evidence, _finalize_fresh_reviewer_evals as _finalize_fresh_reviewer_evals, _finalize_ttl as _finalize_ttl, _finalize_tree_drift as _finalize_tree_drift, FINALIZE_CHECKS as FINALIZE_CHECKS
from ._core import _fresh_eval_invalid_refusal as _fresh_eval_invalid_refusal
from ._candidate_ops import _candidate_snapshot as _candidate_snapshot, _candidate_review_diff as _candidate_review_diff
from ._gate_checks import _fresh_reviewer_block_claimed as _fresh_reviewer_block_claimed
from ._review_transport import _review_master_pointer_prompt as _review_master_pointer_prompt
from ._fresh_eval import _FreshEvalArtifactIO as _FreshEvalArtifactIO, _FreshEvalControlAbort as _FreshEvalControlAbort, _fresh_eval_evaluation as _fresh_eval_evaluation, _validated_fresh_reviewer_manifest as _validated_fresh_reviewer_manifest
from ._fresh_eval_evidence import _fresh_reviewer_evidence_package as _fresh_reviewer_evidence_package, _record_fresh_eval_terminal as _record_fresh_eval_terminal
from ._finalize import ProducedCommitContext as ProducedCommitContext, _produced_exact_message as _produced_exact_message, _produced_exact_tree as _produced_exact_tree, _produced_head_moved as _produced_head_moved, _produced_single_parent as _produced_single_parent, _produced_mismatch_outcome as _produced_mismatch_outcome, _record_produced_identity as _record_produced_identity
from ._review_launch import IDENTITY_DEADLINE_SECONDS as IDENTITY_DEADLINE_SECONDS, PROFILE_TIMEOUT_SECONDS as PROFILE_TIMEOUT_SECONDS, TERMINATE_GRACE_SECONDS as TERMINATE_GRACE_SECONDS, VERSION_PROBE_LIMIT_BYTES as VERSION_PROBE_LIMIT_BYTES, VERSION_PROBE_TIMEOUT_SECONDS as VERSION_PROBE_TIMEOUT_SECONDS, ReviewLaunch as ReviewLaunch, ReviewPaths as ReviewPaths, ReviewRoute as ReviewRoute, allowed_environment as allowed_environment, close_review_launch as close_review_launch, launch_review_wrapper as launch_review_wrapper, materialize_review_final_body as materialize_review_final_body, prepare_review_launch as prepare_review_launch, prepare_review_paths as prepare_review_paths, probe_provider_version as probe_provider_version, require_distinct_final_route as require_distinct_final_route, resolve_review_route as resolve_review_route, reviewer_argv as reviewer_argv
from ._review_launch import CLAUDE_NOT_LOGGED_IN as CLAUDE_NOT_LOGGED_IN, CODEX_NOT_LOGGED_IN as CODEX_NOT_LOGGED_IN
from ._review_lane_api import CANCEL_REQUIRED_OUTCOMES as CANCEL_REQUIRED_OUTCOMES, IMMUTABLE_IDENTITY_FIELDS as IMMUTABLE_IDENTITY_FIELDS, LOST_OUTCOMES as LOST_OUTCOMES, NO_SIGNAL_OUTCOMES as NO_SIGNAL_OUTCOMES, new_attempt_id as new_attempt_id, open_attempt_directory as open_attempt_directory, publish_or_read_terminal as publish_or_read_terminal, spawn_wrapper as spawn_wrapper, wrapper_launcher as wrapper_launcher
from ._review_attempt import COMPLETION_ERRORS as COMPLETION_ERRORS, COMPLETION_KEYS as COMPLETION_KEYS, NEWER_SHAPE_LITERAL as NEWER_SHAPE_LITERAL, AttemptObservation as AttemptObservation, AttemptRecordError as AttemptRecordError, AttemptShapeNewer as AttemptShapeNewer, GroupProof as GroupProof, GroupTermination as GroupTermination, attempt_publication_lock as attempt_publication_lock, cancel_identity_unproven_message as cancel_identity_unproven_message, claim_abandoned as claim_abandoned, launch_failure as launch_failure, make_terminal_completion as make_terminal_completion, mark_stale_attempts as mark_stale_attempts, observe_attempt as observe_attempt, prove_group_ownership as prove_group_ownership, publish_terminal_completion as publish_terminal_completion, read_completion as read_completion, read_identity as read_identity, record_stale as record_stale, terminate_owned_group as terminate_owned_group, validate_completion_binding as validate_completion_binding, with_stale_evidence as with_stale_evidence
from ._engine import Engine as Engine
from ._state import _FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS as _FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS


# cli split phase 2b: ._journal binds the journal-record builder onto the late-bound
# runtime seam right after its definition; tests patch it on forge_cli.runtime.


__all__ = [
    'AttemptObservation',
    'AttemptRecordError',
    'AttemptShapeNewer',
    'CLAUDE_EXECUTABLE',
    'CLAUDE_NOT_LOGGED_IN',
    'CODEX_EXECUTABLE',
    'CODEX_NOT_LOGGED_IN',
    'COMPLETION_ERRORS',
    'COMPLETION_KEYS',
    'CANCEL_REQUIRED_OUTCOMES',
    'ContractArgumentParser',
    'Engine',
    'FINALIZE_CHECKS',
    'FRESH_REVIEWER_EVAL_REQUEST_SCHEMA',
    'FinalizeContext',
    'GLOBAL_OPTIONS_HELP',
    'GroupProof',
    'GroupTermination',
    'IDENTITY_DEADLINE_SECONDS',
    'IMMUTABLE_IDENTITY_FIELDS',
    'LOST_OUTCOMES',
    'MERGE_LIFECYCLE_CONTROLS',
    'NEWER_SHAPE_LITERAL',
    'NO_SIGNAL_OUTCOMES',
    'MergeAdmission',
    'MergeBootstrapClassification',
    'MergeCandidateGeneration',
    'MergeScopeBindingInspection',
    'PLACEHOLDER_RE',
    'PRODUCED_COMMIT_CHECKS',
    'PRODUCED_COMMIT_MISMATCH',
    'PROFILE_TIMEOUT_SECONDS',
    'REVIEW_COMPLETE_PACKAGE_REFUSAL',
    'REVIEW_DIRECT_PACKAGE_MAX_BYTES',
    'REVIEW_INSTRUCTION',
    'REVIEW_MASTER_WINDOW_BYTES',
    'ReviewLaunch',
    'ReviewPaths',
    'ReviewRoute',
    'SECRET_RULES',
    'STATE_TRANSITIONS',
    'SecretFinding',
    'TERMINAL_STATES',
    'TERMINAL_TOUCH_VERBS',
    'TERMINATE_GRACE_SECONDS',
    'TOKEN_TTL_SECONDS',
    'VERSION_PROBE_LIMIT_BYTES',
    'VERSION_PROBE_TIMEOUT_SECONDS',
    '_CHAIN_CAPABILITIES',
    '_CHAIN_CAPABILITY_LOCK',
    '_GitNoLazyFetchQualification',
    '_MERGE_BOOTSTRAP_CHILD_SOURCE',
    '_MERGE_CANDIDATE_IDENTITY_FIELDS',
    '_MERGE_INITIAL_INTEGRATION',
    '_MergeEpochBudget',
    '_REQUIRED_MERGE_LIFECYCLE_CONTROLS',
    '_absolute_git_path',
    '_adopt_out_of_band_candidate',
    '_attach_merge_lifecycle_parser',
    '_authorization_problem',
    '_classification_argv',
    '_classification_environment',
    '_classify_merge_scope_binding',
    '_classify_merge_scope_binding_at',
    '_current_test_paths',
    '_decode_merge_bootstrap_result',
    '_discover_merge_scope_fence_from_sidecar',
    '_env_fingerprint',
    '_evidence_record',
    '_extract_global_options',
    '_finalize_candidate',
    '_finalize_evidence',
    '_finalize_fresh_reviewer_evals',
    '_finalize_halt',
    '_finalize_lock',
    '_finalize_produced_identity',
    '_finalize_tree_drift',
    '_finalize_ttl',
    '_git_environment_digest',
    '_git_executable_qualification',
    '_invalidate_candidate_evidence',
    '_install_candidate_snapshot',
    '_issue_authorization',
    '_materialize_merge_candidate_tuple',
    '_mechanical_complete',
    '_merge_bootstrap_child_argv',
    '_merge_bootstrap_child_main',
    '_merge_branch_reflog_proves_integrated',
    '_merge_candidate_observation_outputs',
    '_merge_claim_identity',
    '_merge_cleanup_process_record',
    '_merge_cleanup_remote_fetch_observation',
    '_merge_conflict_path_is_canonical',
    '_merge_conflict_record',
    '_merge_conflict_record_matches',
    '_merge_epoch_fetch_observation_digest',
    '_merge_epoch_suite',
    '_merge_event_digest',
    '_merge_gate_current',
    '_merge_gate_suite',
    '_merge_has_attempt',
    '_merge_inactive',
    '_merge_inactive_epoch_has_no_started_child',
    '_merge_nonconflict_index_bytes',
    '_merge_nonconflict_status_bytes',
    '_merge_owned_rebase_metadata',
    '_merge_owner_directory',
    '_merge_process_unresolved',
    '_merge_publication_failure',
    '_merge_rebase_integrated_observation_binding',
    '_merge_rebase_integrated_predicate',
    '_merge_rebase_operation_metadata_absent',
    '_merge_rebase_result_failed',
    '_merge_released_predecessor',
    '_merge_scope_child_result',
    '_merge_scope_environment',
    '_merge_unpublished_claim_absent',
    '_merge_worktree_status',
    '_message_from_args',
    '_new_state',
    '_next_incomplete',
    '_normalize_merge_conflict_paths',
    '_observe_merge_conflict',
    '_observe_merge_post_add',
    '_parse_history_mutation_mode',
    '_parse_merge_candidate_observation',
    '_parse_merge_conflict_paths',
    '_parse_plugin_manifest',
    '_pid_is_running',
    '_publish_merge_claim',
    '_publish_merge_scope_binding',
    '_qualify_git_no_lazy_fetch',
    '_raw_top_level_command',
    '_read_bound_artifact',
    '_read_merge_artifact',
    '_read_merge_claim',
    '_read_merge_git_metadata',
    '_read_review_master_window',
    '_record_process_step',
    '_registered_worktrees',
    '_remote_observation_intent',
    '_review_master_pointer_prompt',
    '_review_master_transport',
    '_review_master_window_count',
    '_review_package_is_oversized',
    '_remove_merge_claim',
    '_require_active_merge_epoch',
    '_require_git_no_lazy_fetch_qualification',
    '_require_loud_merge_recovery_mode',
    '_require_merge_lifecycle_control',
    '_reset_merge_nonmovement_counter',
    '_resolve_recorded_merge_tip',
    '_resume_merge_scope_binding',
    '_retain_or_advance_merge_candidate',
    '_run_classification',
    '_run_halt',
    '_serialize_worktree_command',
    '_stage_paths',
    '_success',
    '_transition_state',
    '_unlink_merge_scope_temporary_at',
    '_validate_merge_claim_record',
    '_validate_revision9_cross_options',
    '_verify_operator_harness',
    '_record_docs_class_gate_one_skip',
    '_write_artifact',
    '_write_merge_artifact',
    'allowed_environment',
    'attempt_publication_lock',
    'bind_merge_candidate_generation',
    'build_parser',
    'cancel_identity_unproven_message',
    'chain_id_now',
    'commit_message_bytes',
    'claim_abandoned',
    'close_review_launch',
    'inspect_common_lock',
    'iter_verified_master_package_windows',
    'launch_review_wrapper',
    'launch_failure',
    'make_terminal_completion',
    'mark_stale_attempts',
    'materialize_review_final_body',
    'new_attempt_id',
    'observe_attempt',
    'open_attempt_directory',
    'prepare_review_launch',
    'prepare_review_paths',
    'probe_provider_version',
    'prove_group_ownership',
    'publish_terminal_completion',
    'publish_or_read_terminal',
    'read_completion',
    'read_identity',
    'record_stale',
    'render',
    'resolve_review_route',
    'require_distinct_final_route',
    'reviewer_argv',
    'scan_added_secrets',
    'spawn_wrapper',
    'terminate_owned_group',
    'validate_completion_binding',
    'with_stale_evidence',
    'wrapper_launcher',
]
