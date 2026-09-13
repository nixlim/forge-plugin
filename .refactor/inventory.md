# Inventory: scripts/forge/forge_cli/chain_core.py
- total lines: 20456
- top-level symbols: 316 (functions 218, classes 24, assignments 74)
- intra-module reference edges: 813

## Module-level mutable state (must get exactly ONE owning module)
- `STATES` (line 72) used by: validate_state
- `STATE_KEYS` (line 85) used by: validate_state
- `EVENT_KEYS` (line 109) used by: ChainStore, _ChainStoragePrimitives, _verify_and_build_ingest_records
- `MERGE_STATE_KEYS` (line 112) used by: _merge_recovery_proof_transition_valid, _merge_transition_valid, _replay_merge_event_bytes, validate_merge_state
- `_MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES` (line 142) used by: _merge_transition_valid
- `_MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES` (line 157) used by: _merge_inactive_post_attempt_recovery_ready
- `MERGE_EVENT_KEYS` (line 162) used by: _ChainStoragePrimitives, _replay_merge_event_bytes
- `MERGE_EVENT_NAMES` (line 177) used by: MergeChainStore, _replay_merge_event_bytes, validate_merge_state
- `MERGE_CONSEQUENTIAL_EVENTS` (line 211) used by: _build_merge_chain_journal_records
- `TIER_RANK` (line 222) used by: _merge_candidate_observation_binding, _merge_candidate_observation_record_valid, _merge_candidate_observation_step_specs, _verify_and_build_ingest_records
- `COMMON_LOCK_OWNER_KINDS` (line 276) used by: _validate_owner_record
- `COMMON_LOCK_OPERATIONS` (line 279) used by: _validate_owner_record
- `COMMON_LOCK_FENCE_OPERATIONS` (line 293) used by: _validate_fence_record, run_fenced_command
- `COMMON_LOCK_RECOVERY_KINDS` (line 311) used by: _validate_recovery_record
- `_COMMON_LOCK_OWNER_KEYS` (line 316) used by: _validate_owner_record
- `_COMMON_LOCK_FENCE_KEYS` (line 330) used by: _validate_fence_record
- `_COMMON_LOCK_RECOVERY_KEYS` (line 346) used by: _validate_recovery_record
- `_CHAIN_LEASE_KEYS` (line 372) used by: _validate_chain_lease_record
- `_REQUIRED_COMMON_LOCK_CONTROLS` (line 377) used by: COMMON_LOCK_CONTROLS, _require_common_lock_control
- `CHAIN_ID_RE` (line 403) used by: RecoveryReservation, _ChainStoragePrimitives, _valid_nullable_chain, _validate_chain_lease_record, _validate_fence_record, _validate_merge_scope_fetch_binding, _validate_owner_record, acquire_chain_lease, merge_gate_intent_digest, validate_merge_state, validate_state
- `SHA256_RE` (line 406) used by: _ChainStoragePrimitives, _bootstrap_fetch_observation_record_valid, _classify_merge_recovery_lifecycle, _epoch_ancestry_record_valid, _epoch_fetch_observation_record_valid, _epoch_fetch_result_intent_digest, _ingest_captured_paths, _merge_candidate_observation_binding, _merge_candidate_observation_record_valid, _merge_carried_gate_steps, _merge_cleanup_intent_valid, _merge_cleanup_observation_valid, _merge_cleanup_process_result_valid, _merge_current_authority_valid, _merge_epoch_valid, _merge_event_outbox, _merge_gate_plan_valid, _merge_gate_step_generation_digests, _merge_inactive_post_attempt_recovery_ready, _merge_plan_transition_valid, _merge_rebase_action, _merge_rebase_result_classification, _merge_scope_transition_valid, _merge_transition_valid, _published_recovery_evidence_valid, _recovery_classification_receipt_valid, _remote_containment_evidence_valid, _remote_observation_progress_valid, _replay_merge_event_bytes, _validate_fence_record, _validate_merge_scope_fetch_binding, _validate_merge_scope_proof, _validate_recovery_record, _verify_and_build_ingest_records, _verify_and_build_merge_ingest_records, merge_gate_intent_digest, run_fenced_command, validate_state
- `COMMIT_RE` (line 409) used by: Repository, _bootstrap_fetch_observation_record_valid, _epoch_fetch_result_intent_digest, _merge_bootstrap_classification_pending, _merge_candidate_observation_binding, _merge_candidate_observation_step_specs, _merge_cleanup_branch_observation, _merge_cleanup_expected_subject, _merge_cleanup_fetch_head_bytes, _merge_cleanup_worktree_inventory, _merge_latest_contained_attempt, _remote_observation_progress_valid, _validate_merge_scope_fetch_binding, _verify_and_build_ingest_records, _verify_and_build_merge_ingest_records, validate_state
- `RUN_ID_RE` (line 412) used by: validate_state
- `CHAIN_TOMBSTONE_KEYS` (line 421) used by: _ChainStoragePrimitives
- `_REQUIRED_MERGE_STORE_CONTROLS` (line 426) used by: MERGE_STORE_CONTROLS, _require_merge_store_control
- `_REQUIRED_MERGE_ADAPTER_CONTROLS` (line 447) used by: MERGE_ADAPTER_CONTROLS, _require_merge_adapter_control
- `_REQUIRED_MERGE_INTEGRATION_CONTROLS` (line 461) used by: MERGE_INTEGRATION_CONTROLS, _require_merge_integration_control
- `_REQUIRED_INGEST_PROOF_CONTROLS` (line 505) used by: INGEST_PROOF_CONTROLS, _require_ingest_proof, _verify_and_build_ingest_records
- `_WORKTREE_LOCKS_GUARD` (line 511) used by: _exclusive_descriptor_lock
- `_WORKTREE_LOCKS` (line 514) used by: _exclusive_descriptor_lock
- `_WORKTREE_LOCK_STATE` (line 517) used by: _exclusive_descriptor_lock
- `_MERGE_CLEANUP_FENCE_OPERATIONS` (line 2610) used by: _merge_cleanup_intent_valid
- `_MERGE_SCOPE_UNSET` (line 18027) used by: _merge_scope_environment_contract
- `_MERGE_SCOPE_OVERLAY` (line 18045) used by: _merge_scope_environment_contract
- `__all__` (line 20156) used by: nobody

## Hub symbols (highest fan-in; removed before clustering: 12)
Move these FIRST into a small `_core.py`/`_state.py`/`_base.py` so the rest of the graph falls apart. A hub that is a class used as a base class or a module-wide config/logger belongs in `_core.py`; a hub that is pure utility belongs in `_util.py`.
- `canonical_bytes` (function, 4 LOC, fan-in 31, fan-out 0) (REMOVED)
- `PublishedLockRecord` (class, 17 LOC, fan-in 27, fan-out 0) (REMOVED)
- `_require_common_lock_control` (function, 9 LOC, fan-in 22, fan-out 2) (REMOVED)
- `_valid_utc_second` (function, 7 LOC, fan-in 14, fan-out 2) (REMOVED)
- `RecoveryReservation` (class, 75 LOC, fan-in 13, fan-out 7) (REMOVED)
- `_read_owned_record_at` (function, 56 LOC, fan-in 10, fan-out 3) (REMOVED)
- `iso_z` (function, 4 LOC, fan-in 9, fan-out 0) (REMOVED)
- `_valid_nonce` (function, 2 LOC, fan-in 9, fan-out 0) (REMOVED)
- `_validate_fence_record` (function, 27 LOC, fan-in 9, fan-out 9) (REMOVED)
- `_same_published_record` (function, 9 LOC, fan-in 9, fan-out 1) (REMOVED)
- `_unlink_revalidated_record_at` (function, 10 LOC, fan-in 9, fan-out 3) (REMOVED)
- `_valid_positive_int` (function, 2 LOC, fan-in 8, fan-out 0) (REMOVED)
- `_revalidate_record_at` (function, 11 LOC, fan-in 8, fan-out 3)
- `CommonRebaseLock` (class, 227 LOC, fan-in 8, fan-out 20)
- `CommonLockBoundaryCrash` (class, 8 LOC, fan-in 7, fan-out 0)
- after removing 12 hubs: 3 components, largest has 228 of 230 defs
- WARNING: still one dominant component. Use the label-propagation communities below, or re-run with --exclude-hubs N for larger N.

## Suggested clusters (connected components after hub removal; showing >= 150 LOC)
### Cluster 1: 18808 LOC, 228 symbols
- members: `_exclusive_descriptor_lock`, `_chain_storage_root`, `_validated_commitment_path`, `_parsed_run_captured_path`, `_require_ingest_proof`, `_merge_event_outbox`, `reduce_merge_event`, `_merge_gate_plan_valid`, `_merge_epoch_valid`, `_merge_payload_delta`, `_merge_bootstrap_classification_pending`, `_merge_revision9_compatibility_view`, `_merge_state_shape_valid`, `_merge_ingest_state_shape_valid`, `_merge_history_uses_additive_grammar`, `_merge_ingest_transition_valid`, `_merge_plan_position_fact`, `_merge_carried_gate_steps`, `_merge_gate_step_generation_digests`, `_merge_current_authority_valid`, `_merge_remote_only_equality_proof`, `_merge_carry_payload_valid`, `_merge_plan_transition_valid`, `_validate_merge_scope_proof`, `_merge_scope_event_binding_valid`, `_merge_scope_transition_valid`, `_published_recovery_evidence_valid`, `_recovery_event_intent`, `_recovery_value_carries_inflight`, `_recovery_cleanup_intent`, `_recovery_cleanup_result_matches`, `_classify_merge_recovery_lifecycle`, `_merge_recovery_proof_transition_valid`, `_epoch_fetch_observation_predecessor_valid`, `_recovered_absent_rebase_intent_digest`, `_merge_attempted_release_preconditions_valid`, `_merge_cleanup_expected_subject`, `_merge_cleanup_expected_argv`, `_merge_cleanup_intent_valid`, `_merge_cleanup_process_result_valid` ...
- referenced from outside cluster by: RecoveryReservation, _unlink_revalidated_record_at, _valid_utc_second, _validate_fence_record
- references outside cluster: CHAIN_ID_RE, CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS, CHAIN_TOMBSTONE_SCHEMA, COMMIT_RE, COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_INFLIGHT_NAME, COMMON_LOCK_INTENT_NAME, COMMON_LOCK_OPERATIONS, COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OWNER_NAME, COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES
### Cluster 2: 9 LOC, 1 symbols
- members: `_binding_shape_valid_with_candidate_v2`
- referenced from outside cluster by: none (leaf-safe)
- references outside cluster: none
### Cluster 3: 8 LOC, 1 symbols
- members: `_candidate_binding_for_state_with_candidate_v2`
- referenced from outside cluster by: none (leaf-safe)
- references outside cluster: none

## Communities (label propagation on the hub-free graph; use when a component is still too big)
### Community 1: 4090 LOC, 56 symbols; in-edges from 12 outside symbols, out-edges to 17
- members: `_chain_storage_root`, `_merge_history_uses_additive_grammar`, `_merge_ingest_transition_valid`, `_merge_current_authority_valid`, `_ReceiptRunSnapshot`, `_chain_receipt_snapshot_lock`, `_receipt_run_snapshot`, `_ChainReceiptSnapshotVerifier`, `_ChainActivationSnapshot`, `_resolve_chain_activation_snapshot`, `_resolve_chain_activation_projection`, `_chain_activation_ownership_summary`, `_validate_chain_activation_lineage`, `_require_no_pending_chain_activation_outbox`, `_prepare_merge_activation_preamble`, `_authorize_chain_batch`, `_merge_ingest_binding`, `_merge_gate_event_fact`, `_merge_ingest_record_templates`, `_ingest_proof_verifier`, `register_activation_reservation_seam`, `register_coordination_seams`, `_coordination_refusal`, `_validate_chain_batch_target`, `_chain_batch_lock`, `_require_merge_store_control`, `validate_merge_state`, `MergeReplayResult`, `_replay_merge_event_bytes`, `_drain_chain_batch_capability`, `_build_merge_chain_journal_records`, `_new_merge_record_is_current`, `MergeChainStore`, `ChainLeaseUnavailable`, `_validate_chain_lease_record`, `_open_owned_directory`, `_revalidate_record_at`, `_record_at_if_present`, `_process_probe`, `_require_deadline_open` ...
### Community 2: 3444 LOC, 54 symbols; in-edges from 12 outside symbols, out-edges to 19
- members: `_published_recovery_evidence_valid`, `_recovery_event_intent`, `_recovery_value_carries_inflight`, `_recovery_cleanup_intent`, `_recovery_cleanup_result_matches`, `_classify_merge_recovery_lifecycle`, `_merge_recovery_proof_transition_valid`, `_merge_cleanup_expected_subject`, `_merge_cleanup_expected_argv`, `_merge_cleanup_intent_valid`, `_merge_cleanup_process_result_valid`, `_merge_cleanup_step_result_valid`, `_merge_cleanup_results_valid`, `_merge_cleanup_unmatched_intent`, `_merge_cleanup_retry_proof_valid`, `_merge_cleanup_intent_transition_valid`, `_merge_cleanup_result_transition_valid`, `_merge_history_has_git_mutation_intent`, `CommonLockBoundaryCrash`, `CommonLockInspection`, `CommonLockUnavailable`, `CommonLockReleaseFailure`, `FencedChildSurvived`, `_valid_nonnegative_int`, `_valid_host`, `_validate_owner_record`, `_valid_nullable_chain`, `_validate_recovery_record`, `_write_all`, `_open_lock_directory`, `_inspect_common_lock_fd`, `_PublicationCleanupFailure`, `_create_private_record_at`, `_publish_no_replace_link`, `_group_probe`, `_sleep_with_deadline`, `_new_owner_record`, `_fence_matches_owner`, `_publish_portable_owner`, `_release_portable_identity` ...
### Community 3: 3424 LOC, 36 symbols; in-edges from 5 outside symbols, out-edges to 13
- members: `_validated_commitment_path`, `_parsed_run_captured_path`, `_require_ingest_proof`, `_prevalidate_chain_batch_carrier`, `_read_ingest_input`, `_capture_ingest_blob`, `_capture_run_evidence`, `_capture_ingest_record_evidence`, `_ingest_captured_paths`, `_ingest_step_is_current`, `_ingest_secret_scan_is_current`, `_prove_ingest_live_chain`, `_merge_current_gate_facts`, `_ingest_allocation_records`, `_verify_and_build_merge_ingest_records`, `_verify_and_build_ingest_records`, `candidate_is_v2`, `_event_batch_records_with_candidate_v2`, `_binding_matches_source_fact_with_candidate_v2`, `_binding_is_current_with_candidate_v2`, `_commit_transition_valid_with_candidate_v2`, `Repository`, `_committed_changelog_output_paths`, `_require_merge_adapter_control`, `ChainStore`, `CLIOptions`, `CommandContext`, `_policy_for_state`, `_validate_bound_chain_state`, `_latest_current_pass`, `_user_skip`, `_gate_satisfied`, `_fresh_reviewer_evals_required`, `_required_steps`, `_gate_one_complete`, `_forge_command`
### Community 4: 2971 LOC, 18 symbols; in-edges from 3 outside symbols, out-edges to 21
- members: `_merge_carried_gate_steps`, `_merge_gate_step_generation_digests`, `_epoch_fetch_observation_predecessor_valid`, `_recovered_absent_rebase_intent_digest`, `_merge_transition_valid`, `_require_merge_integration_control`, `_merge_rebase_action`, `_merge_rebase_result_classification`, `_merge_latest_contained_attempt`, `_merge_inactive_post_attempt_recovery_ready`, `_epoch_fetch_observation_record_valid`, `_epoch_fetch_observation_passed`, `_epoch_fetch_result_intent_digest`, `_epoch_ancestry_record_valid`, `_remote_observation_progress_transition_valid`, `_bootstrap_fetch_observation_record_valid`, `_bootstrap_fetch_observation_transition_valid`, `_merge_candidate_observation_evidence_valid`
### Community 5: 2105 LOC, 12 symbols; in-edges from 7 outside symbols, out-edges to 4
- members: `_exclusive_descriptor_lock`, `_merge_event_outbox`, `reduce_merge_event`, `_merge_payload_delta`, `_merge_attempted_release_preconditions_valid`, `parse_time`, `validate_state`, `_ChainStoragePrimitives`, `_merge_containment`, `_merge_old_tip_all_false`, `_remote_observation_progress_matches_observed`, `_replayed_remote_observation_completed`
### Community 6: 1155 LOC, 19 symbols; in-edges from 3 outside symbols, out-edges to 1
- members: `_validate_merge_scope_proof`, `_merge_scope_event_binding_valid`, `_merge_scope_transition_valid`, `FencedProcessResult`, `_merge_scope_environment_contract`, `_valid_sorted_unique_strings`, `_validate_merge_scope_request`, `_merge_retained_inflight`, `_validate_merge_scope_fetch_binding`, `_merge_scope_binding_names`, `_merge_scope_binding_validator`, `_merge_scope_argv`, `_merge_full_patch_argv`, `_merge_candidate_observation_step_specs`, `_merge_candidate_observation_step_names`, `_merge_candidate_observation_binding`, `_merge_candidate_observation_record_valid`, `_merge_candidate_observation_transition_valid`, `_merge_candidate_observation_evidence`
### Community 7: 418 LOC, 8 symbols; in-edges from 1 outside symbols, out-edges to 1
- members: `_BlockedFenceChild`, `_pipe_cloexec`, `_spawn_blocked_fence_child`, `_waitpid_nohang`, `_wait_for_child_exit`, `_terminate_fenced_group`, `_stop_unstarted_child`, `_collect_fenced_child`
### Community 8: 333 LOC, 7 symbols; in-edges from 1 outside symbols, out-edges to 0
- members: `_merge_cleanup_process_output`, `_merge_cleanup_process_complete`, `_merge_cleanup_branch_observation`, `_merge_cleanup_worktree_inventory`, `_merge_cleanup_fetch_head_bytes`, `_merge_cleanup_observation_valid`, `_parse_registered_worktrees`
### Community 9: 260 LOC, 6 symbols; in-edges from 5 outside symbols, out-edges to 0
- members: `_merge_gate_plan_valid`, `_merge_epoch_valid`, `_merge_bootstrap_classification_pending`, `_merge_revision9_compatibility_view`, `_merge_state_shape_valid`, `_merge_ingest_state_shape_valid`
### Community 10: 223 LOC, 3 symbols; in-edges from 2 outside symbols, out-edges to 2
- members: `_merge_cleanup_evidence_history`, `_merge_cleanup_history_summary`, `_merge_release_preconditions_valid`
### Community 11: 204 LOC, 5 symbols; in-edges from 4 outside symbols, out-edges to 0
- members: `_remote_observation_heads`, `_remote_observation_fetch_argv`, `_remote_containment_argv`, `_remote_containment_evidence_valid`, `_remote_observation_progress_valid`

## Largest symbols
- `_merge_transition_valid` (function, lines 3741-5724, 1984 LOC, fan-in 2, fan-out 40)
- `_ChainStoragePrimitives` (class, lines 10723-11812, 1090 LOC, fan-in 2, fan-out 16)
- `MergeChainStore` (class, lines 12688-13506, 819 LOC, fan-in 2, fan-out 23)
- `_verify_and_build_ingest_records` (function, lines 8518-9319, 802 LOC, fan-in 1, fan-out 35)
- `ChainStore` (class, lines 11815-12515, 701 LOC, fan-in 3, fan-out 19)
- `_verify_and_build_merge_ingest_records` (function, lines 7928-8515, 588 LOC, fan-in 1, fan-out 15)
- `acquire_common_lock` (function, lines 15386-15929, 544 LOC, fan-in 1, fan-out 29)
- `validate_state` (function, lines 9856-10286, 431 LOC, fan-in 3, fan-out 9)
- `run_fenced_command` (function, lines 17026-17370, 345 LOC, fan-in 0, fan-out 25)
- `_classify_merge_recovery_lifecycle` (function, lines 1885-2193, 309 LOC, fan-in 1, fan-out 11)
- `__all__` (assignment, lines 20156-20455, 300 LOC, fan-in 0, fan-out 0)
- `_replay_merge_event_bytes` (function, lines 10391-10669, 279 LOC, fan-in 3, fan-out 14)
- `_resolve_chain_activation_snapshot` (function, lines 5966-6205, 240 LOC, fan-in 3, fan-out 7)
- `acquire_chain_lease` (function, lines 16148-16382, 235 LOC, fan-in 1, fan-out 25)
- `_validate_chain_activation_lineage` (function, lines 6298-6531, 234 LOC, fan-in 1, fan-out 3)

## Leaves (fan-out 0 within module; safest to extract first)
`canonical_bytes`, `_chain_storage_root`, `_validated_commitment_path`, `_parsed_run_captured_path`, `_merge_payload_delta`, `_merge_history_uses_additive_grammar`, `_merge_plan_position_fact`, `_recovery_event_intent`, `_recovery_value_carries_inflight`, `_recovery_cleanup_intent`, `_epoch_fetch_observation_predecessor_valid`, `_merge_cleanup_expected_argv`, `_merge_cleanup_process_output`, `_merge_cleanup_process_complete`, `_merge_cleanup_evidence_history`, `_ReceiptRunSnapshot`, `_chain_receipt_snapshot_lock`, `_ChainActivationSnapshot`, `_prevalidate_chain_batch_carrier`, `_ingest_step_is_current`, `_ingest_secret_scan_is_current`, `_merge_gate_event_fact`, `_merge_current_gate_facts`, `_ingest_allocation_records`, `_coordination_refusal`, `_validate_chain_batch_target`, `iso_z`, `parse_time`, `candidate_is_v2`, `_candidate_binding_for_state_with_candidate_v2`, `_binding_shape_valid_with_candidate_v2`, `_event_batch_records_with_candidate_v2`, `_binding_matches_source_fact_with_candidate_v2`, `_binding_is_current_with_candidate_v2`, `_commit_transition_valid_with_candidate_v2`, `_committed_changelog_output_paths`, `MergeReplayResult`, `_drain_chain_batch_capability`, `_new_merge_record_is_current`, `CommonLockBoundaryCrash`, `PublishedLockRecord`, `FencedChildSurvived`, `_valid_positive_int`, `_valid_nonnegative_int`, `_valid_host`, `_valid_nonce`, `_write_all`, `_PublicationCleanupFailure`, `_process_probe`, `_group_probe`, `FencedProcessResult`, `_BlockedFenceChild`, `_pipe_cloexec`, `_waitpid_nohang`, `CLIOptions`, `_latest_current_pass`, `_user_skip`, `_forge_command`, `MergeRunTaskSnapshot`, `_merge_refusal`
