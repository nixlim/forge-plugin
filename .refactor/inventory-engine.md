# Inventory: scripts/forge/forge_cli/engine.py
- total lines: 12178
- top-level symbols: 223 (functions 176, classes 14, assignments 33)
- intra-module reference edges: 295

## Module-level mutable state (must get exactly ONE owning module)
- `TERMINAL_STATES` (line 62) used by: Engine, _peek_selected_chain
- `TERMINAL_TOUCH_VERBS` (line 65) used by: Engine
- `STATE_TRANSITIONS` (line 68) used by: _transition_state
- `_REQUIRED_MERGE_LIFECYCLE_CONTROLS` (line 88) used by: MERGE_LIFECYCLE_CONTROLS, _require_merge_lifecycle_control
- `_REQUIRED_ARCHIVE_RECHECK_CONTROLS` (line 101) used by: ARCHIVE_RECHECK_CONTROLS, _archive_recheck
- `_CHAIN_CAPABILITY_LOCK` (line 109) used by: nobody
- `_CHAIN_CAPABILITIES` (line 112) used by: nobody
- `_ARCHIVE_MODULE_LOCK` (line 118) used by: _archive_module
- `_FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS` (line 127) used by: _fresh_eval_evaluation
- `PRODUCED_COMMIT_CHECKS` (line 550) used by: Engine, _finalize_produced_identity
- `FINALIZE_CHECKS` (line 900) used by: Engine
- `PLACEHOLDER_RE` (line 4041) used by: scan_added_secrets
- `_DERIVE_MERGE_SCOPE` (line 6682) used by: bind_merge_candidate_generation
- `_MERGE_INITIAL_INTEGRATION` (line 7188) used by: nobody
- `__all__` (line 11985) used by: nobody

## `global` statements (behavior hazard when moving)
- `_archive_module` declares global _ARCHIVE_MODULE

## Hub symbols (highest fan-in; removed before clustering: 12)
Move these FIRST into a small `_core.py`/`_state.py`/`_base.py` so the rest of the graph falls apart. A hub that is a class used as a base class or a module-wide config/logger belongs in `_core.py`; a hub that is pure utility belongs in `_util.py`.
- `FinalizeContext` (class, 9 LOC, fan-in 10, fan-out 1) (REMOVED)
- `MergeAdmission` (class, 13 LOC, fan-in 9, fan-out 0) (REMOVED)
- `_write_artifact` (function, 37 LOC, fan-in 6, fan-out 0) (REMOVED)
- `_read_bound_artifact` (function, 72 LOC, fan-in 6, fan-out 0) (REMOVED)
- `MergeScopeResult` (class, 8 LOC, fan-in 6, fan-out 0) (REMOVED)
- `_transition_state` (function, 13 LOC, fan-in 5, fan-out 1) (REMOVED)
- `ProducedCommitContext` (class, 6 LOC, fan-in 5, fan-out 0) (REMOVED)
- `_validated_fresh_reviewer_manifest` (function, 54 LOC, fan-in 5, fan-out 3) (REMOVED)
- `_require_merge_lifecycle_control` (function, 9 LOC, fan-in 4, fan-out 2) (REMOVED)
- `_fresh_eval_invalid_refusal` (function, 23 LOC, fan-in 4, fan-out 0) (REMOVED)
- `_record_process_step` (function, 46 LOC, fan-in 4, fan-out 2) (REMOVED)
- `_run_halt` (function, 43 LOC, fan-in 4, fan-out 0) (REMOVED)
- `_merge_owner_directory` (function, 12 LOC, fan-in 4, fan-out 0)
- `_archive_refusal` (function, 19 LOC, fan-in 3, fan-out 0)
- `_archive_contamination_refusal` (function, 12 LOC, fan-in 3, fan-out 1)
- after removing 12 hubs: 50 components, largest has 76 of 178 defs
- WARNING: still one dominant component. Use the label-propagation communities below, or re-run with --exclude-hubs N for larger N.

## Suggested clusters (connected components after hub removal; showing >= 150 LOC)
### Cluster 1: 6217 LOC, 76 symbols
- members: `_read_ingest_sources`, `_install_ingest_sources`, `_capture_ingest_inputs`, `commit_message_bytes`, `chain_id_now`, `promoted_tier`, `_record_produced_identity`, `_produced_mismatch_outcome`, `_finalize_evidence`, `_finalize_ttl`, `_new_state`, `_commit_start_binding_refusal`, `_prove_run_task_binding`, `_archive_module`, `_archive_refusal`, `_archive_contamination_refusal`, `_nul_git_paths`, `_archive_close_tree_clean`, `_archive_parent_descriptor`, `_read_archive_candidate_at`, `_read_archive_candidate`, `_render_archive_bytes`, `_prepare_archive_candidate`, `_archive_recheck`, `_archive_metadata`, `_env_fingerprint`, `_evidence_record`, `_review_package_is_oversized`, `_review_complete_package_refusal`, `_review_master_window_count`, `_review_master_transport`, `_review_master_pointer_prompt`, `_review_master_identity`, `_review_master_leaf_is_valid`, `_read_review_master_digest`, `_read_review_master_window`, `_assert_review_master_stable`, `_iter_verified_master_package_windows`, `iter_verified_master_package_windows`, `_FreshEvalArtifactIO` ...
- referenced from outside cluster by: FINALIZE_CHECKS, FinalizeContext, _record_process_step, _validated_fresh_reviewer_manifest
- references outside cluster: ABORT_DISPOSITION_PRECONDITIONS, ARCHIVE_CONTAMINATION, ARCHIVE_RECHECK_CONTROLS, CODEX_EXECUTABLE, FINALIZE_CHECKS, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, FinalizeContext, PLACEHOLDER_RE, PRODUCED_COMMIT_CHECKS, PRODUCED_COMMIT_MISMATCH, REVIEW_COMPLETE_PACKAGE_REFUSAL, REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE, REVIEW_MASTER_WINDOW_BYTES
### Cluster 2: 1247 LOC, 18 symbols
- members: `MergeCandidateGeneration`, `_parse_plugin_manifest`, `_parse_history_mutation_mode`, `_merge_worktree_status`, `_merge_scope_environment`, `_GitNoLazyFetchQualification`, `_git_environment_digest`, `_git_executable_qualification`, `_qualify_git_no_lazy_fetch`, `_require_git_no_lazy_fetch_qualification`, `_merge_bootstrap_child_main`, `_parse_merge_name_status_output`, `_parse_merge_scope_output`, `_derive_merge_scope`, `_merge_scope_from_candidate_observation`, `bind_merge_candidate_generation`, `_merge_candidate_observation_outputs`, `_parse_merge_candidate_observation`
- referenced from outside cluster by: none (leaf-safe)
- references outside cluster: MergeAdmission, MergeScopeResult, _DERIVE_MERGE_SCOPE
### Cluster 3: 393 LOC, 7 symbols
- members: `_merge_scope_child_result`, `MergeScopeBindingInspection`, `_unlink_merge_scope_temporary_at`, `_classify_merge_scope_binding_at`, `_classify_merge_scope_binding`, `_resume_merge_scope_binding`, `_publish_merge_scope_binding`
- referenced from outside cluster by: none (leaf-safe)
- references outside cluster: none
### Cluster 4: 377 LOC, 3 symbols
- members: `_binding_for_commit_event`, `_passed_stack_cell_is_intermediate`, `_build_chain_journal_records`
- referenced from outside cluster by: none (leaf-safe)
- references outside cluster: none
### Cluster 5: 274 LOC, 8 symbols
- members: `_validate_merge_claim_record`, `_merge_owner_directory`, `_merge_claim_identity`, `_read_merge_claim`, `_publish_merge_claim`, `_merge_publication_failure`, `_remove_merge_claim`, `_merge_unpublished_claim_absent`
- referenced from outside cluster by: none (leaf-safe)
- references outside cluster: _require_merge_lifecycle_control
### Cluster 6: 241 LOC, 4 symbols
- members: `_merge_branch_reflog_proves_integrated`, `_merge_rebase_integrated_observation_binding`, `_merge_rebase_operation_metadata_absent`, `_merge_rebase_integrated_predicate`
- referenced from outside cluster by: none (leaf-safe)
- references outside cluster: none
### Cluster 7: 216 LOC, 1 symbols
- members: `_merge_released_predecessor`
- referenced from outside cluster by: none (leaf-safe)
- references outside cluster: none
### Cluster 8: 196 LOC, 1 symbols
- members: `_decode_merge_bootstrap_result`
- referenced from outside cluster by: none (leaf-safe)
- references outside cluster: none
### Cluster 9: 162 LOC, 5 symbols
- members: `_merge_cleanup_process_record`, `_merge_cleanup_remote_fetch_observation`, `_read_merge_git_metadata`, `_merge_owned_rebase_metadata`, `_require_loud_merge_recovery_mode`
- referenced from outside cluster by: none (leaf-safe)
- references outside cluster: none

## Communities (label propagation on the hub-free graph; use when a component is still too big)
### Community 1: 4080 LOC, 14 symbols; in-edges from 0 outside symbols, out-edges to 31
- members: `commit_message_bytes`, `chain_id_now`, `_record_produced_identity`, `_new_state`, `_review_package_is_oversized`, `_record_fresh_eval_terminal`, `_current_test_paths`, `_void_mismatched_gate_one_pair`, `_fresh_reviewer_block_claimed`, `_success`, `_pid_is_running`, `_verify_operator_harness`, `abort_disposition_refusal`, `Engine`
### Community 2: 1174 LOC, 16 symbols; in-edges from 0 outside symbols, out-edges to 1
- members: `MergeCandidateGeneration`, `_merge_worktree_status`, `_merge_scope_environment`, `_GitNoLazyFetchQualification`, `_git_environment_digest`, `_git_executable_qualification`, `_qualify_git_no_lazy_fetch`, `_require_git_no_lazy_fetch_qualification`, `_merge_bootstrap_child_main`, `_parse_merge_name_status_output`, `_parse_merge_scope_output`, `_derive_merge_scope`, `_merge_scope_from_candidate_observation`, `bind_merge_candidate_generation`, `_merge_candidate_observation_outputs`, `_parse_merge_candidate_observation`
### Community 3: 393 LOC, 7 symbols; in-edges from 0 outside symbols, out-edges to 0
- members: `_merge_scope_child_result`, `MergeScopeBindingInspection`, `_unlink_merge_scope_temporary_at`, `_classify_merge_scope_binding_at`, `_classify_merge_scope_binding`, `_resume_merge_scope_binding`, `_publish_merge_scope_binding`
### Community 4: 377 LOC, 3 symbols; in-edges from 0 outside symbols, out-edges to 0
- members: `_binding_for_commit_event`, `_passed_stack_cell_is_intermediate`, `_build_chain_journal_records`
### Community 5: 274 LOC, 8 symbols; in-edges from 0 outside symbols, out-edges to 0
- members: `_validate_merge_claim_record`, `_merge_owner_directory`, `_merge_claim_identity`, `_read_merge_claim`, `_publish_merge_claim`, `_merge_publication_failure`, `_remove_merge_claim`, `_merge_unpublished_claim_absent`
### Community 6: 241 LOC, 4 symbols; in-edges from 0 outside symbols, out-edges to 0
- members: `_merge_branch_reflog_proves_integrated`, `_merge_rebase_integrated_observation_binding`, `_merge_rebase_operation_metadata_absent`, `_merge_rebase_integrated_predicate`
### Community 7: 235 LOC, 2 symbols; in-edges from 1 outside symbols, out-edges to 0
- members: `_FreshEvalArtifactIO`, `_fresh_reviewer_evidence_package`
### Community 8: 222 LOC, 7 symbols; in-edges from 2 outside symbols, out-edges to 3
- members: `_produced_mismatch_outcome`, `_archive_module`, `_archive_refusal`, `_render_archive_bytes`, `_archive_recheck`, `_archive_metadata`, `_issue_authorization`
### Community 9: 216 LOC, 1 symbols; in-edges from 0 outside symbols, out-edges to 0
- members: `_merge_released_predecessor`
### Community 10: 203 LOC, 5 symbols; in-edges from 2 outside symbols, out-edges to 3
- members: `_archive_contamination_refusal`, `_archive_parent_descriptor`, `_read_archive_candidate_at`, `_read_archive_candidate`, `_prepare_archive_candidate`
### Community 11: 196 LOC, 1 symbols; in-edges from 0 outside symbols, out-edges to 0
- members: `_decode_merge_bootstrap_result`
### Community 12: 186 LOC, 4 symbols; in-edges from 2 outside symbols, out-edges to 1
- members: `promoted_tier`, `_classification_argv`, `_classification_environment`, `_run_classification`
### Community 13: 178 LOC, 5 symbols; in-edges from 1 outside symbols, out-edges to 1
- members: `_invalidate_candidate_evidence`, `_candidate_snapshot`, `_install_candidate_snapshot`, `_adopt_out_of_band_candidate`, `_stage_paths`
### Community 14: 172 LOC, 4 symbols; in-edges from 1 outside symbols, out-edges to 0
- members: `_finalize_evidence`, `_fresh_reviewer_pass_claimed`, `_mechanical_complete`, `_next_incomplete`
### Community 15: 162 LOC, 5 symbols; in-edges from 0 outside symbols, out-edges to 0
- members: `_merge_cleanup_process_record`, `_merge_cleanup_remote_fetch_observation`, `_read_merge_git_metadata`, `_merge_owned_rebase_metadata`, `_require_loud_merge_recovery_mode`
### Community 16: 154 LOC, 6 symbols; in-edges from 1 outside symbols, out-edges to 0
- members: `_review_master_identity`, `_review_master_leaf_is_valid`, `_read_review_master_digest`, `_read_review_master_window`, `_assert_review_master_stable`, `_iter_verified_master_package_windows`
### Community 17: 152 LOC, 4 symbols; in-edges from 1 outside symbols, out-edges to 0
- members: `_FreshEvalControlAbort`, `_fresh_eval_requests`, `_fresh_eval_request_for_step`, `_fresh_eval_evaluation`

## Largest symbols
- `Engine` (class, lines 8305-11982, 3678 LOC, fan-in 1, fan-out 61)
- `_build_chain_journal_records` (function, lines 1446-1781, 336 LOC, fan-in 0, fan-out 2)
- `bind_merge_candidate_generation` (function, lines 6756-7068, 313 LOC, fan-in 0, fan-out 8)
- `_parse_merge_candidate_observation` (function, lines 8038-8302, 265 LOC, fan-in 1, fan-out 2)
- `_merge_released_predecessor` (function, lines 7546-7761, 216 LOC, fan-in 0, fan-out 0)
- `_merge_bootstrap_child_main` (function, lines 6136-6335, 200 LOC, fan-in 0, fan-out 2)
- `_decode_merge_bootstrap_result` (function, lines 6366-6561, 196 LOC, fan-in 0, fan-out 0)
- `__all__` (assignment, lines 11985-12177, 193 LOC, fan-in 0, fan-out 0)
- `_publish_merge_scope_binding` (function, lines 5920-6092, 173 LOC, fan-in 0, fan-out 2)
- `REVIEW_LAUNCHER_CODE` (assignment, lines 179-322, 144 LOC, fan-in 1, fan-out 0)
- `_extract_global_options` (function, lines 923-1060, 138 LOC, fan-in 0, fan-out 0)
- `_run_classification` (function, lines 3458-3590, 133 LOC, fan-in 2, fan-out 6)
- `_fresh_reviewer_evidence_package` (function, lines 3128-3258, 131 LOC, fan-in 1, fan-out 3)
- `_fresh_eval_evaluation` (function, lines 2948-3069, 122 LOC, fan-in 2, fan-out 5)
- `_discover_merge_scope_fence_from_sidecar` (function, lines 5807-5917, 111 LOC, fan-in 0, fan-out 0)

## Leaves (fan-out 0 within module; safest to extract first)
`_merge_cleanup_process_record`, `_read_ingest_sources`, `_install_ingest_sources`, `commit_message_bytes`, `chain_id_now`, `promoted_tier`, `_reset_merge_nonmovement_counter`, `ProducedCommitContext`, `ContractArgumentParser`, `_extract_global_options`, `_message_from_args`, `_validate_revision9_cross_options`, `render`, `_raw_top_level_command`, `_binding_for_commit_event`, `_passed_stack_cell_is_intermediate`, `inspect_common_lock`, `_new_state`, `_commit_start_binding_refusal`, `_archive_refusal`, `_nul_git_paths`, `_archive_parent_descriptor`, `_read_archive_candidate_at`, `_archive_metadata`, `_env_fingerprint`, `_review_master_identity`, `_read_review_master_digest`, `_read_review_master_window`, `_write_artifact`, `_read_bound_artifact`, `_FreshEvalControlAbort`, `_fresh_eval_requests`, `_fresh_eval_invalid_refusal`, `_classification_argv`, `_classification_environment`, `_invalidate_candidate_evidence`, `_candidate_patch_ref`, `_candidate_snapshot`, `_current_test_paths`, `_void_mismatched_gate_one_pair`, `_fresh_reviewer_pass_claimed`, `_fresh_reviewer_block_claimed`, `SecretFinding`, `_success`, `_pid_is_running`, `_run_halt`, `_peek_chain_state`, `_peek_raw_abort_state`, `MergeAdmission`, `MergeScopeResult`, `_parse_plugin_manifest`, `_absolute_git_path`, `_registered_worktrees`, `_merge_worktree_status`, `_read_merge_git_metadata`, `_merge_conflict_path_is_canonical`, `_merge_nonconflict_index_bytes`, `_merge_nonconflict_status_bytes`, `_merge_conflict_record`, `_merge_conflict_record_matches`
