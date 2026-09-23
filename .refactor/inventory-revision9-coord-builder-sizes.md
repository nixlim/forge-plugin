# Revision9BuilderBatchTests: method and cluster sizes (code lines = non-blank, non-comment lines within the def; measured on 69bc28d)

## Clusters (inventory order, after hub peeling; hubs: @state:assertEqual, api_environment, run_dir, _new_repo, @state:assertRaisesRegex, @state:assertFalse, @state:assertTrue, start_task, @state:subTest, @state:repo, _open_legacy_run, open_run)

### cluster 1: 28 tests (1910 code lines), helpers ['setUp', '_leave_complete_intent', '_leave_two_record_receipt_gap', '_write_landed_intent_for_last_receipt', '_seed_gh17_wedge', '_assert_gh17_recovered', 'command']
- setUp L200-205 6 lines calls=['_new_repo'] verdict=ok
- test_typed_builder_round_trip_ids_receipts_and_idempotency L266-393 125 lines calls=['api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok
- _leave_complete_intent L395-432 37 lines calls=['open_run', 'run_dir', 'start_task'] verdict=ok
- test_exact_prefix_and_torn_receipt_recovery L453-481 29 lines calls=['_leave_complete_intent', '_new_repo', 'api_environment'] verdict=ok
- test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only L483-509 26 lines calls=['_leave_complete_intent', 'api_environment'] verdict=ok
- test_midflight_intent_hardlink_fifo_and_foreign_uid_fences L675-707 33 lines calls=['_leave_base_intent', '_new_repo', 'api_environment'] verdict=ok
- test_batch_controls_are_load_bearing L709-777 63 lines calls=['_leave_complete_intent', '_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok
- test_activated_scope_readmission_uses_typed_builder L828-906 76 lines calls=['api_environment', 'command', 'open_run', 'run_dir'] verdict=ok
- test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume L908-981 72 lines calls=['api_environment', 'command', 'open_run', 'run_dir'] verdict=ok
- test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps L1156-1231 73 lines calls=['_leave_complete_intent', '_leave_scope_receipt_gap', '_new_repo', '_write_landed_intent_for_last_receipt', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok
- test_batch_recover_repairs_one_n_record_gap L1233-1311 76 lines calls=['_leave_two_record_receipt_gap', 'api_environment'] verdict=ok
- test_batch_gap_repair_controls_are_independently_load_bearing L1313-1356 44 lines calls=['_leave_two_record_receipt_gap', '_new_repo', '_seed_gh17_wedge', 'api_environment'] verdict=ok
- test_activated_scope_change_rechecks_superset_containment_and_conflicts L1436-1510 74 lines calls=['api_environment', 'run_dir'] verdict=ok
- test_concurrent_admission_and_scope_change_remain_disjoint L1512-1636 119 lines calls=['api_environment', 'open_run', 'run_dir'] verdict=ok
- _leave_two_record_receipt_gap L1710-1754 45 lines calls=['_write_landed_intent_for_last_receipt', 'open_run', 'run_dir', 'start_task'] verdict=ok
- _write_landed_intent_for_last_receipt L1756-1784 29 lines calls=[] verdict=ok
- test_run_open_durable_receipt_survives_registry_failure_and_retry L2079-2114 34 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir'] verdict=ok
- test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze L2648-2704 54 lines calls=['_leave_complete_intent', '_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok
- test_ingest_requires_registered_proof_complete_authority L3332-3423 89 lines calls=['api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok
- test_activation_scan_skips_external_sibling_chain_and_run_lock L5694-5784 87 lines calls=['_legacy_receipted_chain_case', '_open_legacy_run', 'api_environment'] verdict=ok
- test_concurrent_legacy_activation_never_cross_acquires_run_locks L5786-5916 125 lines calls=['_legacy_receipted_chain_case', 'api_environment'] verdict=ok
- test_raw_open_writer_contract_refusal_is_load_bearing L6648-6677 29 lines calls=['api_environment', 'run_dir'] verdict=ok
- test_legacy_open_without_stderr_never_falls_back_to_stdout L6679-6719 41 lines calls=['api_environment', 'run_dir'] verdict=ok
- test_legacy_open_broken_stderr_never_changes_durable_success L6721-6768 46 lines calls=['api_environment', 'run_dir'] verdict=ok
- _seed_gh17_wedge L7846-8007 157 lines calls=['_open_legacy_run', '_write_landed_intent_for_last_receipt', 'run_dir'] verdict=ok
- _assert_gh17_recovered L8009-8086 77 lines calls=['_activation_markers'] verdict=ok
- test_gh17_shape_recovers_without_reapplication L8088-8145 56 lines calls=['_assert_gh17_recovered', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment'] verdict=ok
- test_gh17_shape_refuses_explicit_foreign_gap_run_id L8147-8167 21 lines calls=['_run_file_bytes', '_seed_gh17_wedge', 'api_environment'] verdict=ok
- test_recovery_activation_crash_matrix L8169-8285 112 lines calls=['_assert_gh17_recovered', '_new_repo', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment'] verdict=ok
- test_repair_receipt_n_record_members_rederived L8287-8407 119 lines calls=['_assert_gh17_recovered', '_new_repo', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment'] verdict=ok
- test_stable_reader_rederives_every_n_record_repair_member L8409-8515 105 lines calls=['_assert_gh17_recovered', '_new_repo', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment'] verdict=ok
- test_writer_activation_controls_are_independently_load_bearing L8517-8567 51 lines calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- command L8824-8833 10 lines calls=[] verdict=ok
- test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet L8835-8942 106 lines calls=['command', 'run_dir'] verdict=ok
- test_cli_singleton_and_idempotency_key_diagnostics L8944-8971 25 lines calls=['command'] verdict=ok

### cluster 2: 2 tests (59 code lines), helpers ['_leave_base_intent']
- _leave_base_intent L434-451 16 lines calls=['open_run', 'run_dir', 'start_task'] verdict=ok
- test_torn_intent_never_becomes_authoritative L511-542 32 lines calls=['_leave_base_intent', '_new_repo', 'api_environment', 'start_task'] verdict=ok
- test_intent_without_journal_and_reentrant_pending_read_refuse_exactly L646-673 27 lines calls=['_leave_base_intent', '_new_repo', 'api_environment'] verdict=ok

### cluster 3: 1 tests (40 code lines), helpers []
- test_self_consistent_intent_substitution_after_prepare_is_refused L544-585 40 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok

### cluster 4: 1 tests (23 code lines), helpers []
- test_activated_missing_stable_lock_or_receipt_ledger_diverges L587-609 23 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok

### cluster 5: 1 tests (34 code lines), helpers []
- test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze L611-644 34 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok

### cluster 6: 1 tests (46 code lines), helpers []
- test_builder_validation_controls_are_detected_in_memory L779-826 46 lines calls=['_new_repo', 'api_environment', 'open_run', 'start_task'] verdict=ok

### cluster 7: 1 tests (81 code lines), helpers []
- test_scope_change_recovers_intent_and_receipted_registry_publication L983-1065 81 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir'] verdict=ok

### cluster 8: 1 tests (87 code lines), helpers []
- test_scope_change_recovery_refuses_unproved_replace_and_disabled_control L1067-1154 87 lines calls=['_new_repo', 'api_environment', 'run_dir'] verdict=ok

### cluster 9: 4 tests (219 code lines), helpers ['_leave_scope_receipt_gap']
- test_repair_receipt_is_rederived_on_every_load L1358-1386 29 lines calls=['_leave_scope_receipt_gap', '_new_repo', 'api_environment'] verdict=ok
- test_torn_repair_receipt_resumes_only_its_derived_suffix L1388-1434 44 lines calls=['_leave_scope_receipt_gap', 'api_environment'] verdict=ok
- _leave_scope_receipt_gap L1638-1708 69 lines calls=['open_run', 'run_dir'] verdict=ok
- test_batch_recover_repairs_proven_readmission_gap_and_stale_intent L1786-1830 45 lines calls=['_leave_scope_receipt_gap', 'api_environment'] verdict=ok
- test_batch_gap_repair_refuses_unproved_bytes_and_intent L1832-1933 101 lines calls=['_leave_scope_receipt_gap', '_new_repo', 'api_environment'] verdict=ok

### cluster 10: 1 tests (16 code lines), helpers []
- test_typed_task_scope_refusal_names_offending_pathspec L1935-1950 16 lines calls=['api_environment', 'open_run'] verdict=ok

### cluster 11: 1 tests (53 code lines), helpers []
- test_builder_request_schema_and_digest_are_exact L1952-2005 53 lines calls=[] verdict=ok

### cluster 12: 1 tests (34 code lines), helpers []
- test_run_open_is_hidden_until_atomic_publication L2007-2042 34 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir'] verdict=ok

### cluster 13: 30 tests (1774 code lines), helpers ['_write_bound_chain_state', '_chain_drain_case', '_chain_drain_authorizer', '_append_test_landing', '_append_test_decision', '_terminal_control_repo', '_abort_bound_chain_fixture', '_activation_markers', '_plant_unreplayable_unrelated_chain', '_pad_valid_json_over_cap', '_guard_activation_artifact_read_budget', '_activation_outbox_case', '_compete_with_activation_outbox', '_invoke_raw_lifecycle']
- test_run_open_prepublication_crashes_leave_no_visible_run L2044-2077 32 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir'] verdict=ok
- test_batch_crashes_recover_stored_bytes_without_duplicate_receipt L2260-2326 62 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok
- _write_bound_chain_state L2706-2958 240 lines calls=[] verdict=ok
- _chain_drain_case L2960-2999 40 lines calls=['_terminal_control_repo', '_write_bound_chain_state'] verdict=ok
- _chain_drain_authorizer L3001-3096 93 lines calls=['run_dir'] verdict=ok
- test_chain_drain_valid_authorizer_new_and_repeated_paths L3098-3132 35 lines calls=['_chain_drain_authorizer', '_chain_drain_case', 'api_environment'] verdict=ok
- test_chain_drain_authorized_pending_and_lost_response_retry L3134-3196 61 lines calls=['_chain_drain_authorizer', '_chain_drain_case', 'api_environment', 'run_dir'] verdict=ok
- test_chain_drain_authorization_exact_field_bindings L3198-3277 80 lines calls=['_chain_drain_authorizer', '_chain_drain_case', 'api_environment', 'run_dir'] verdict=ok
- test_chain_drain_authorization_controls_are_load_bearing L3279-3330 52 lines calls=['_chain_drain_authorizer', '_chain_drain_case', 'api_environment', 'run_dir'] verdict=ok
- _append_test_landing L3425-3428 4 lines calls=['_append_test_decision'] verdict=ok
- _append_test_decision L3430-3475 46 lines calls=[] verdict=ok
- _terminal_control_repo L3477-3488 12 lines calls=['_new_repo', 'open_run', 'start_task'] verdict=ok
- test_terminal_builder_guards_pending_outbox_and_missing_landing L3490-3526 36 lines calls=['_terminal_control_repo', '_write_bound_chain_state', 'api_environment', 'run_dir'] verdict=ok
- _abort_bound_chain_fixture L3528-3565 38 lines calls=[] verdict=ok
- test_terminal_builder_accepts_authenticated_abort_disposition L3567-3675 93 lines calls=['_abort_bound_chain_fixture', '_append_test_decision', '_append_test_landing', '_terminal_control_repo', '_write_bound_chain_state', 'api_environment'] verdict=ok
- test_terminal_builder_accepts_only_explicit_absent_chain_tombstone L3805-3882 73 lines calls=['_append_test_landing', '_terminal_control_repo', '_write_bound_chain_state', 'api_environment'] verdict=ok
- test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine L3884-3975 86 lines calls=['_append_test_landing', '_terminal_control_repo', '_write_bound_chain_state', 'api_environment'] verdict=ok
- test_each_terminal_chain_control_is_load_bearing L3977-4089 106 lines calls=['_append_test_landing', '_terminal_control_repo', '_write_bound_chain_state', 'api_environment'] verdict=ok
- test_terminal_guard_refuses_chain_root_swap_after_enumeration L4091-4139 47 lines calls=['_terminal_control_repo', '_write_bound_chain_state', 'api_environment', 'run_dir'] verdict=ok
- _activation_markers L4178-4185 8 lines calls=[] verdict=wrap
- _plant_unreplayable_unrelated_chain L4195-4208 14 lines calls=[] verdict=ok
- _pad_valid_json_over_cap L4211-4215 5 lines calls=[] verdict=wrap
- _guard_activation_artifact_read_budget L4218-4267 46 lines calls=[] verdict=wrap
- _activation_outbox_case L4407-4494 87 lines calls=['_new_repo', '_open_legacy_run', '_write_bound_chain_state', 'run_dir'] verdict=ok
- _compete_with_activation_outbox L4496-4512 17 lines calls=[] verdict=ok
- _invoke_raw_lifecycle L4514-4538 25 lines calls=['run_dir'] verdict=ok
- test_commit_sibling_receipt_snapshot_recheck_is_load_bearing L5025-5123 97 lines calls=['_legacy_receipted_chain_case', 'api_environment', 'run_dir'] verdict=ok
- test_activation_scan_tolerates_unreplayable_unrelated_chain L5125-5172 46 lines calls=['_invoke_raw_lifecycle', '_new_repo', '_open_legacy_run', '_plant_unreplayable_unrelated_chain', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- test_activation_scan_warns_and_continues_on_oversized_unrelated_state L5174-5224 49 lines calls=['_guard_activation_artifact_read_budget', '_new_repo', '_open_legacy_run', '_pad_valid_json_over_cap', '_write_bound_chain_state', 'api_environment', 'start_task'] verdict=ok
- test_activation_scan_refuses_oversized_state_bound_to_this_run L5226-5268 41 lines calls=['_guard_activation_artifact_read_budget', '_new_repo', '_open_legacy_run', '_pad_valid_json_over_cap', '_write_bound_chain_state', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- test_activation_state_byte_cap_is_load_bearing_in_memory L5270-5304 33 lines calls=['_guard_activation_artifact_read_budget', '_new_repo', '_open_legacy_run', '_pad_valid_json_over_cap', '_write_bound_chain_state', 'api_environment'] verdict=ok
- test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one L5306-5355 48 lines calls=['_guard_activation_artifact_read_budget', '_new_repo', '_open_legacy_run', '_write_bound_chain_state', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- test_activation_events_byte_cap_is_load_bearing_in_memory L5357-5394 36 lines calls=['_guard_activation_artifact_read_budget', '_new_repo', '_open_legacy_run', '_write_bound_chain_state', 'api_environment'] verdict=ok
- test_activation_scan_converts_bounded_path_memory_errors L5396-5434 36 lines calls=['_new_repo', '_open_legacy_run', '_write_bound_chain_state', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- test_activation_replay_passes_scan_only_state_and_event_caps L5436-5516 78 lines calls=['_new_repo', '_open_legacy_run', '_write_bound_chain_state', 'api_environment', 'start_task'] verdict=ok
- test_activation_scan_unrelated_tolerance_is_load_bearing L5518-5537 18 lines calls=['_new_repo', '_open_legacy_run', '_plant_unreplayable_unrelated_chain', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- test_activation_outbox_blocks_raw_append_byte_exactly_then_drains L6143-6244 97 lines calls=['_activation_markers', '_activation_outbox_case', '_chain_drain_authorizer', '_invoke_raw_lifecycle', '_run_file_bytes', 'api_environment', 'run_dir'] verdict=ok
- test_activation_outbox_lifecycle_guard_is_load_bearing L6246-6284 37 lines calls=['_activation_outbox_case', '_invoke_raw_lifecycle', '_run_file_bytes', 'api_environment', 'run_dir'] verdict=ok
- test_raw_lifecycle_validation_precedes_batch_reservation L6324-6380 54 lines calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir'] verdict=ok
- test_raw_open_cannot_supply_writer_contract_before_any_mutation L6610-6646 37 lines calls=['_new_repo', 'api_environment', 'run_dir'] verdict=ok
- test_activation_outbox_reserves_first_use_then_drains_exact_batch L6770-6851 81 lines calls=['_activation_markers', '_activation_outbox_case', '_chain_drain_authorizer', '_compete_with_activation_outbox', '_run_file_bytes', 'api_environment', 'run_dir'] verdict=ok
- test_activation_outbox_missing_events_or_tampered_state_refuses_first_use L6853-6894 40 lines calls=['_activation_outbox_case', '_compete_with_activation_outbox', '_run_file_bytes', 'api_environment', 'run_dir'] verdict=ok
- test_legacy_activation_crash_matrix L6991-7159 165 lines calls=['_activation_markers', '_new_repo', '_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- test_unactivated_stale_ledger_raw_close_succeeds L7798-7815 18 lines calls=['_invoke_raw_lifecycle', '_new_repo', '_seed_unactivated_stale_ledger', 'api_environment'] verdict=ok

### cluster 14: 4 tests (235 code lines), helpers []
- test_run_open_process_death_keeps_staging_invisible_and_retryable L2117-2195 75 lines calls=['_new_repo', 'api_environment', 'run_dir'] verdict=unsupported
- test_id_only_legacy_opening_activates_with_matching_marker_run_id L5918-5959 40 lines calls=['api_environment', 'run_dir', 'start_task'] verdict=ok
- test_retired_successor_close_intent_recovers_and_releases_registry L8569-8607 39 lines calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir'] verdict=ok
- test_retired_successor_close_recovers_every_stored_suffix_prefix L8609-8689 81 lines calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir'] verdict=ok

### cluster 15: 1 tests (60 code lines), helpers []
- test_fr019_failure_phase_order_preserves_earlier_bytes L2197-2258 60 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok

### cluster 16: 1 tests (81 code lines), helpers []
- test_prepublication_intent_stage_crashes_retry_without_authority L2328-2410 81 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok

### cluster 17: 1 tests (17 code lines), helpers []
- test_foreign_request_intent_stage_is_not_deleted L2412-2428 17 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok

### cluster 18: 1 tests (67 code lines), helpers []
- test_intent_source_name_substitution_never_survives_canonical L2430-2498 67 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok

### cluster 19: 1 tests (85 code lines), helpers []
- test_intent_quarantine_preserves_a_second_canonical_swap L2500-2588 85 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok

### cluster 20: 1 tests (57 code lines), helpers []
- test_chain_drain_raw_records_without_capability_refuses L2590-2646 57 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir'] verdict=ok

### cluster 21: 1 tests (21 code lines), helpers []
- test_terminal_abort_disposition_fails_closed_on_shape L3677-3697 21 lines calls=[] verdict=ok

### cluster 22: 2 tests (58 code lines), helpers ['_self_event_fixture']
- _self_event_fixture L3699-3733 35 lines calls=[] verdict=ok
- test_abort_disposition_self_event_admission_controls_are_load_bearing L3735-3765 26 lines calls=['_self_event_fixture'] verdict=ok
- test_abort_disposition_self_event_source_fact_requires_aborted_unchanged_prior L3767-3803 32 lines calls=['_self_event_fixture'] verdict=ok

### cluster 23: 13 tests (866 code lines), helpers ['_run_file_bytes', '_restore_prefix_wedge_fixture', '_seed_unactivated_stale_ledger']
- _run_file_bytes L4188-4193 6 lines calls=[] verdict=wrap
- test_first_receipt_ledger_post_create_substitution_refuses L4343-4405 60 lines calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- test_persisted_activation_candidate_requires_allocated_id_and_contract L5961-6058 97 lines calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir'] verdict=ok
- test_activation_allocation_refuses_unicode_and_oversized_suffixes L6060-6115 55 lines calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- test_removed_batch_lock_after_activation_is_not_recreated L6117-6141 23 lines calls=['_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- test_legacy_raw_guard_intent_conditions_are_load_bearing L6286-6322 35 lines calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment', 'run_dir'] verdict=ok
- test_staged_first_use_intent_blocks_outbox_before_publication L6579-6608 29 lines calls=['_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir'] verdict=ok
- test_legacy_first_typed_use_atomically_activates L6896-6989 90 lines calls=['_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- test_typed_opened_run_bytes_are_unchanged L7161-7360 193 lines calls=['_run_file_bytes', 'api_environment', 'open_run', 'run_dir', 'start_task'] verdict=ok
- test_global_reconciliation_defers_torn_adopted_coverage L7362-7463 96 lines calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- _restore_prefix_wedge_fixture L7465-7502 37 lines calls=['_new_repo', 'run_dir'] verdict=ok
- _seed_unactivated_stale_ledger L7641-7708 66 lines calls=['_open_legacy_run', 'run_dir'] verdict=ok
- test_unactivated_stale_ledger_has_legible_refusal_and_raw_append L7710-7766 55 lines calls=['_run_file_bytes', '_seed_unactivated_stale_ledger', 'api_environment'] verdict=ok
- test_unactivated_stale_ledger_retire_then_typed_successor L7768-7796 28 lines calls=['_new_repo', '_seed_unactivated_stale_ledger', 'api_environment'] verdict=ok
- test_unactivated_stale_ledger_eof_guard_is_load_bearing L7817-7844 28 lines calls=['_new_repo', '_run_file_bytes', '_seed_unactivated_stale_ledger', 'api_environment'] verdict=ok
- test_retired_successor_recovery_rejects_other_run_mutation L8691-8769 77 lines calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir'] verdict=ok

### cluster 24: 2 tests (8 code lines), helpers ['_assert_first_batch_artifact_substitution_refuses']
- _assert_first_batch_artifact_substitution_refuses L4269-4331 60 lines calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- test_batch_lock_create_open_substitution_refuses L4333-4336 4 lines calls=['_assert_first_batch_artifact_substitution_refuses'] verdict=ok
- test_first_receipt_ledger_create_open_substitution_refuses L4338-4341 4 lines calls=['_assert_first_batch_artifact_substitution_refuses'] verdict=ok

### cluster 25: 2 tests (294 code lines), helpers ['_bound_chain_outbox', '_acknowledge_bound_chain', '_legacy_receipted_chain_case', '_rewrite_commit_events']
- _bound_chain_outbox L4540-4568 29 lines calls=[] verdict=ok
- _acknowledge_bound_chain L4570-4616 47 lines calls=[] verdict=ok
- _legacy_receipted_chain_case L4618-4697 80 lines calls=['_acknowledge_bound_chain', '_bound_chain_outbox', '_open_legacy_run', '_write_bound_chain_state'] verdict=ok
- _rewrite_commit_events L4699-4723 25 lines calls=[] verdict=ok
- test_commit_sibling_receipt_request_authentication_is_load_bearing L4725-4863 136 lines calls=['_legacy_receipted_chain_case', '_rewrite_commit_events', 'api_environment', 'run_dir'] verdict=ok
- test_commit_sibling_carried_binding_authentication_is_load_bearing L4865-5023 158 lines calls=['_legacy_receipted_chain_case', '_rewrite_commit_events', 'api_environment', 'run_dir'] verdict=ok

### cluster 26: 1 tests (48 code lines), helpers []
- test_activation_scan_ignores_unrelated_chain_created_between_scans L5539-5589 48 lines calls=['_new_repo', '_open_legacy_run', 'api_environment', 'start_task'] verdict=ok

### cluster 27: 1 tests (99 code lines), helpers []
- test_activation_scan_bound_chain_created_between_scans_refuses L5591-5692 99 lines calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir', 'start_task'] verdict=ok

### cluster 28: 1 tests (134 code lines), helpers []
- test_raw_lifecycle_lock_order_is_load_bearing L6382-6522 134 lines calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir'] verdict=ok

### cluster 29: 1 tests (50 code lines), helpers []
- test_published_first_use_intent_blocks_outbox_before_publication L6524-6577 50 lines calls=['_open_legacy_run', 'api_environment', 'run_dir', 'start_task'] verdict=ok

### cluster 30: 1 tests (129 code lines), helpers []
- test_pre_fix_golden_wedge_recovers_and_continues L7504-7639 129 lines calls=['_activation_markers', '_restore_prefix_wedge_fixture', 'api_environment'] verdict=ok

### cluster 31: 1 tests (51 code lines), helpers []
- test_internal_typed_flag_cannot_bypass_activated_batch_builders L8771-8822 51 lines calls=['_new_repo', 'api_environment', 'open_run', 'run_dir'] verdict=ok

### cluster 32: 0 tests (0 code lines), helpers ['api_environment']
- api_environment L238-240 3 lines calls=[] verdict=wrap

### cluster 33: 0 tests (0 code lines), helpers ['run_dir']
- run_dir L242-243 2 lines calls=[] verdict=ok

### cluster 34: 0 tests (0 code lines), helpers ['_new_repo']
- _new_repo L207-235 29 lines calls=[] verdict=ok

### cluster 35: 0 tests (0 code lines), helpers ['start_task']
- start_task L255-264 10 lines calls=[] verdict=ok

### cluster 36: 0 tests (0 code lines), helpers ['_open_legacy_run']
- _open_legacy_run L4141-4175 35 lines calls=[] verdict=ok

### cluster 37: 0 tests (0 code lines), helpers ['open_run']
- open_run L245-253 9 lines calls=[] verdict=ok

## Tests in source order with sizes

- test_typed_builder_round_trip_ids_receipts_and_idempotency L266-393 125 calls=['api_environment', 'open_run', 'run_dir', 'start_task']
- test_exact_prefix_and_torn_receipt_recovery L453-481 29 calls=['_leave_complete_intent', '_new_repo', 'api_environment']
- test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only L483-509 26 calls=['_leave_complete_intent', 'api_environment']
- test_torn_intent_never_becomes_authoritative L511-542 32 calls=['_leave_base_intent', '_new_repo', 'api_environment', 'start_task']
- test_self_consistent_intent_substitution_after_prepare_is_refused L544-585 40 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_activated_missing_stable_lock_or_receipt_ledger_diverges L587-609 23 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze L611-644 34 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_intent_without_journal_and_reentrant_pending_read_refuse_exactly L646-673 27 calls=['_leave_base_intent', '_new_repo', 'api_environment']
- test_midflight_intent_hardlink_fifo_and_foreign_uid_fences L675-707 33 calls=['_leave_base_intent', '_new_repo', 'api_environment']
- test_batch_controls_are_load_bearing L709-777 63 calls=['_leave_complete_intent', '_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_builder_validation_controls_are_detected_in_memory L779-826 46 calls=['_new_repo', 'api_environment', 'open_run', 'start_task']
- test_activated_scope_readmission_uses_typed_builder L828-906 76 calls=['api_environment', 'command', 'open_run', 'run_dir']
- test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume L908-981 72 calls=['api_environment', 'command', 'open_run', 'run_dir']
- test_scope_change_recovers_intent_and_receipted_registry_publication L983-1065 81 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir']
- test_scope_change_recovery_refuses_unproved_replace_and_disabled_control L1067-1154 87 calls=['_new_repo', 'api_environment', 'run_dir']
- test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps L1156-1231 73 calls=['_leave_complete_intent', '_leave_scope_receipt_gap', '_new_repo', '_write_landed_intent_for_last_receipt', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_batch_recover_repairs_one_n_record_gap L1233-1311 76 calls=['_leave_two_record_receipt_gap', 'api_environment']
- test_batch_gap_repair_controls_are_independently_load_bearing L1313-1356 44 calls=['_leave_two_record_receipt_gap', '_new_repo', '_seed_gh17_wedge', 'api_environment']
- test_repair_receipt_is_rederived_on_every_load L1358-1386 29 calls=['_leave_scope_receipt_gap', '_new_repo', 'api_environment']
- test_torn_repair_receipt_resumes_only_its_derived_suffix L1388-1434 44 calls=['_leave_scope_receipt_gap', 'api_environment']
- test_activated_scope_change_rechecks_superset_containment_and_conflicts L1436-1510 74 calls=['api_environment', 'run_dir']
- test_concurrent_admission_and_scope_change_remain_disjoint L1512-1636 119 calls=['api_environment', 'open_run', 'run_dir']
- test_batch_recover_repairs_proven_readmission_gap_and_stale_intent L1786-1830 45 calls=['_leave_scope_receipt_gap', 'api_environment']
- test_batch_gap_repair_refuses_unproved_bytes_and_intent L1832-1933 101 calls=['_leave_scope_receipt_gap', '_new_repo', 'api_environment']
- test_typed_task_scope_refusal_names_offending_pathspec L1935-1950 16 calls=['api_environment', 'open_run']
- test_builder_request_schema_and_digest_are_exact L1952-2005 53 calls=[]
- test_run_open_is_hidden_until_atomic_publication L2007-2042 34 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir']
- test_run_open_prepublication_crashes_leave_no_visible_run L2044-2077 32 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir']
- test_run_open_durable_receipt_survives_registry_failure_and_retry L2079-2114 34 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir']
- test_run_open_process_death_keeps_staging_invisible_and_retryable L2117-2195 75 calls=['_new_repo', 'api_environment', 'run_dir']
- test_fr019_failure_phase_order_preserves_earlier_bytes L2197-2258 60 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_batch_crashes_recover_stored_bytes_without_duplicate_receipt L2260-2326 62 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_prepublication_intent_stage_crashes_retry_without_authority L2328-2410 81 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_foreign_request_intent_stage_is_not_deleted L2412-2428 17 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_intent_source_name_substitution_never_survives_canonical L2430-2498 67 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_intent_quarantine_preserves_a_second_canonical_swap L2500-2588 85 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_chain_drain_raw_records_without_capability_refuses L2590-2646 57 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir']
- test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze L2648-2704 54 calls=['_leave_complete_intent', '_new_repo', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_chain_drain_valid_authorizer_new_and_repeated_paths L3098-3132 35 calls=['_chain_drain_authorizer', '_chain_drain_case', 'api_environment']
- test_chain_drain_authorized_pending_and_lost_response_retry L3134-3196 61 calls=['_chain_drain_authorizer', '_chain_drain_case', 'api_environment', 'run_dir']
- test_chain_drain_authorization_exact_field_bindings L3198-3277 80 calls=['_chain_drain_authorizer', '_chain_drain_case', 'api_environment', 'run_dir']
- test_chain_drain_authorization_controls_are_load_bearing L3279-3330 52 calls=['_chain_drain_authorizer', '_chain_drain_case', 'api_environment', 'run_dir']
- test_ingest_requires_registered_proof_complete_authority L3332-3423 89 calls=['api_environment', 'open_run', 'run_dir', 'start_task']
- test_terminal_builder_guards_pending_outbox_and_missing_landing L3490-3526 36 calls=['_terminal_control_repo', '_write_bound_chain_state', 'api_environment', 'run_dir']
- test_terminal_builder_accepts_authenticated_abort_disposition L3567-3675 93 calls=['_abort_bound_chain_fixture', '_append_test_decision', '_append_test_landing', '_terminal_control_repo', '_write_bound_chain_state', 'api_environment']
- test_terminal_abort_disposition_fails_closed_on_shape L3677-3697 21 calls=[]
- test_abort_disposition_self_event_admission_controls_are_load_bearing L3735-3765 26 calls=['_self_event_fixture']
- test_abort_disposition_self_event_source_fact_requires_aborted_unchanged_prior L3767-3803 32 calls=['_self_event_fixture']
- test_terminal_builder_accepts_only_explicit_absent_chain_tombstone L3805-3882 73 calls=['_append_test_landing', '_terminal_control_repo', '_write_bound_chain_state', 'api_environment']
- test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine L3884-3975 86 calls=['_append_test_landing', '_terminal_control_repo', '_write_bound_chain_state', 'api_environment']
- test_each_terminal_chain_control_is_load_bearing L3977-4089 106 calls=['_append_test_landing', '_terminal_control_repo', '_write_bound_chain_state', 'api_environment']
- test_terminal_guard_refuses_chain_root_swap_after_enumeration L4091-4139 47 calls=['_terminal_control_repo', '_write_bound_chain_state', 'api_environment', 'run_dir']
- test_batch_lock_create_open_substitution_refuses L4333-4336 4 calls=['_assert_first_batch_artifact_substitution_refuses']
- test_first_receipt_ledger_create_open_substitution_refuses L4338-4341 4 calls=['_assert_first_batch_artifact_substitution_refuses']
- test_first_receipt_ledger_post_create_substitution_refuses L4343-4405 60 calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir', 'start_task']
- test_commit_sibling_receipt_request_authentication_is_load_bearing L4725-4863 136 calls=['_legacy_receipted_chain_case', '_rewrite_commit_events', 'api_environment', 'run_dir']
- test_commit_sibling_carried_binding_authentication_is_load_bearing L4865-5023 158 calls=['_legacy_receipted_chain_case', '_rewrite_commit_events', 'api_environment', 'run_dir']
- test_commit_sibling_receipt_snapshot_recheck_is_load_bearing L5025-5123 97 calls=['_legacy_receipted_chain_case', 'api_environment', 'run_dir']
- test_activation_scan_tolerates_unreplayable_unrelated_chain L5125-5172 46 calls=['_invoke_raw_lifecycle', '_new_repo', '_open_legacy_run', '_plant_unreplayable_unrelated_chain', 'api_environment', 'run_dir', 'start_task']
- test_activation_scan_warns_and_continues_on_oversized_unrelated_state L5174-5224 49 calls=['_guard_activation_artifact_read_budget', '_new_repo', '_open_legacy_run', '_pad_valid_json_over_cap', '_write_bound_chain_state', 'api_environment', 'start_task']
- test_activation_scan_refuses_oversized_state_bound_to_this_run L5226-5268 41 calls=['_guard_activation_artifact_read_budget', '_new_repo', '_open_legacy_run', '_pad_valid_json_over_cap', '_write_bound_chain_state', 'api_environment', 'run_dir', 'start_task']
- test_activation_state_byte_cap_is_load_bearing_in_memory L5270-5304 33 calls=['_guard_activation_artifact_read_budget', '_new_repo', '_open_legacy_run', '_pad_valid_json_over_cap', '_write_bound_chain_state', 'api_environment']
- test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one L5306-5355 48 calls=['_guard_activation_artifact_read_budget', '_new_repo', '_open_legacy_run', '_write_bound_chain_state', 'api_environment', 'run_dir', 'start_task']
- test_activation_events_byte_cap_is_load_bearing_in_memory L5357-5394 36 calls=['_guard_activation_artifact_read_budget', '_new_repo', '_open_legacy_run', '_write_bound_chain_state', 'api_environment']
- test_activation_scan_converts_bounded_path_memory_errors L5396-5434 36 calls=['_new_repo', '_open_legacy_run', '_write_bound_chain_state', 'api_environment', 'run_dir', 'start_task']
- test_activation_replay_passes_scan_only_state_and_event_caps L5436-5516 78 calls=['_new_repo', '_open_legacy_run', '_write_bound_chain_state', 'api_environment', 'start_task']
- test_activation_scan_unrelated_tolerance_is_load_bearing L5518-5537 18 calls=['_new_repo', '_open_legacy_run', '_plant_unreplayable_unrelated_chain', 'api_environment', 'run_dir', 'start_task']
- test_activation_scan_ignores_unrelated_chain_created_between_scans L5539-5589 48 calls=['_new_repo', '_open_legacy_run', 'api_environment', 'start_task']
- test_activation_scan_bound_chain_created_between_scans_refuses L5591-5692 99 calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir', 'start_task']
- test_activation_scan_skips_external_sibling_chain_and_run_lock L5694-5784 87 calls=['_legacy_receipted_chain_case', '_open_legacy_run', 'api_environment']
- test_concurrent_legacy_activation_never_cross_acquires_run_locks L5786-5916 125 calls=['_legacy_receipted_chain_case', 'api_environment']
- test_id_only_legacy_opening_activates_with_matching_marker_run_id L5918-5959 40 calls=['api_environment', 'run_dir', 'start_task']
- test_persisted_activation_candidate_requires_allocated_id_and_contract L5961-6058 97 calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir']
- test_activation_allocation_refuses_unicode_and_oversized_suffixes L6060-6115 55 calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir', 'start_task']
- test_removed_batch_lock_after_activation_is_not_recreated L6117-6141 23 calls=['_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir', 'start_task']
- test_activation_outbox_blocks_raw_append_byte_exactly_then_drains L6143-6244 97 calls=['_activation_markers', '_activation_outbox_case', '_chain_drain_authorizer', '_invoke_raw_lifecycle', '_run_file_bytes', 'api_environment', 'run_dir']
- test_activation_outbox_lifecycle_guard_is_load_bearing L6246-6284 37 calls=['_activation_outbox_case', '_invoke_raw_lifecycle', '_run_file_bytes', 'api_environment', 'run_dir']
- test_legacy_raw_guard_intent_conditions_are_load_bearing L6286-6322 35 calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment', 'run_dir']
- test_raw_lifecycle_validation_precedes_batch_reservation L6324-6380 54 calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir']
- test_raw_lifecycle_lock_order_is_load_bearing L6382-6522 134 calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir']
- test_published_first_use_intent_blocks_outbox_before_publication L6524-6577 50 calls=['_open_legacy_run', 'api_environment', 'run_dir', 'start_task']
- test_staged_first_use_intent_blocks_outbox_before_publication L6579-6608 29 calls=['_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir']
- test_raw_open_cannot_supply_writer_contract_before_any_mutation L6610-6646 37 calls=['_new_repo', 'api_environment', 'run_dir']
- test_raw_open_writer_contract_refusal_is_load_bearing L6648-6677 29 calls=['api_environment', 'run_dir']
- test_legacy_open_without_stderr_never_falls_back_to_stdout L6679-6719 41 calls=['api_environment', 'run_dir']
- test_legacy_open_broken_stderr_never_changes_durable_success L6721-6768 46 calls=['api_environment', 'run_dir']
- test_activation_outbox_reserves_first_use_then_drains_exact_batch L6770-6851 81 calls=['_activation_markers', '_activation_outbox_case', '_chain_drain_authorizer', '_compete_with_activation_outbox', '_run_file_bytes', 'api_environment', 'run_dir']
- test_activation_outbox_missing_events_or_tampered_state_refuses_first_use L6853-6894 40 calls=['_activation_outbox_case', '_compete_with_activation_outbox', '_run_file_bytes', 'api_environment', 'run_dir']
- test_legacy_first_typed_use_atomically_activates L6896-6989 90 calls=['_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir', 'start_task']
- test_legacy_activation_crash_matrix L6991-7159 165 calls=['_activation_markers', '_new_repo', '_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir', 'start_task']
- test_typed_opened_run_bytes_are_unchanged L7161-7360 193 calls=['_run_file_bytes', 'api_environment', 'open_run', 'run_dir', 'start_task']
- test_global_reconciliation_defers_torn_adopted_coverage L7362-7463 96 calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', 'api_environment', 'run_dir', 'start_task']
- test_pre_fix_golden_wedge_recovers_and_continues L7504-7639 129 calls=['_activation_markers', '_restore_prefix_wedge_fixture', 'api_environment']
- test_unactivated_stale_ledger_has_legible_refusal_and_raw_append L7710-7766 55 calls=['_run_file_bytes', '_seed_unactivated_stale_ledger', 'api_environment']
- test_unactivated_stale_ledger_retire_then_typed_successor L7768-7796 28 calls=['_new_repo', '_seed_unactivated_stale_ledger', 'api_environment']
- test_unactivated_stale_ledger_raw_close_succeeds L7798-7815 18 calls=['_invoke_raw_lifecycle', '_new_repo', '_seed_unactivated_stale_ledger', 'api_environment']
- test_unactivated_stale_ledger_eof_guard_is_load_bearing L7817-7844 28 calls=['_new_repo', '_run_file_bytes', '_seed_unactivated_stale_ledger', 'api_environment']
- test_gh17_shape_recovers_without_reapplication L8088-8145 56 calls=['_assert_gh17_recovered', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment']
- test_gh17_shape_refuses_explicit_foreign_gap_run_id L8147-8167 21 calls=['_run_file_bytes', '_seed_gh17_wedge', 'api_environment']
- test_recovery_activation_crash_matrix L8169-8285 112 calls=['_assert_gh17_recovered', '_new_repo', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment']
- test_repair_receipt_n_record_members_rederived L8287-8407 119 calls=['_assert_gh17_recovered', '_new_repo', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment']
- test_stable_reader_rederives_every_n_record_repair_member L8409-8515 105 calls=['_assert_gh17_recovered', '_new_repo', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment']
- test_writer_activation_controls_are_independently_load_bearing L8517-8567 51 calls=['_new_repo', '_open_legacy_run', '_run_file_bytes', '_seed_gh17_wedge', 'api_environment', 'run_dir', 'start_task']
- test_retired_successor_close_intent_recovers_and_releases_registry L8569-8607 39 calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir']
- test_retired_successor_close_recovers_every_stored_suffix_prefix L8609-8689 81 calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir']
- test_retired_successor_recovery_rejects_other_run_mutation L8691-8769 77 calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir']
- test_internal_typed_flag_cannot_bypass_activated_batch_builders L8771-8822 51 calls=['_new_repo', 'api_environment', 'open_run', 'run_dir']
- test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet L8835-8942 106 calls=['command', 'run_dir']
- test_cli_singleton_and_idempotency_key_diagnostics L8944-8971 25 calls=['command']

## Helpers in source order

- setUp L200-205 6 decorators=[] calls=['_new_repo'] verdict=ok
- _new_repo L207-235 29 decorators=[] calls=[] verdict=ok
- api_environment L238-240 3 decorators=['contextmanager'] calls=[] verdict=wrap
- run_dir L242-243 2 decorators=[] calls=[] verdict=ok
- open_run L245-253 9 decorators=[] calls=[] verdict=ok
- start_task L255-264 10 decorators=[] calls=[] verdict=ok
- _leave_complete_intent L395-432 37 decorators=[] calls=['open_run', 'run_dir', 'start_task'] verdict=ok
- _leave_base_intent L434-451 16 decorators=[] calls=['open_run', 'run_dir', 'start_task'] verdict=ok
- _leave_scope_receipt_gap L1638-1708 69 decorators=[] calls=['open_run', 'run_dir'] verdict=ok
- _leave_two_record_receipt_gap L1710-1754 45 decorators=[] calls=['_write_landed_intent_for_last_receipt', 'open_run', 'run_dir', 'start_task'] verdict=ok
- _write_landed_intent_for_last_receipt L1756-1784 29 decorators=[] calls=[] verdict=ok
- _write_bound_chain_state L2706-2958 240 decorators=[] calls=[] verdict=ok
- _chain_drain_case L2960-2999 40 decorators=[] calls=['_terminal_control_repo', '_write_bound_chain_state'] verdict=ok
- _chain_drain_authorizer L3001-3096 93 decorators=[] calls=['run_dir'] verdict=ok
- _append_test_landing L3425-3428 4 decorators=[] calls=['_append_test_decision'] verdict=ok
- _append_test_decision L3430-3475 46 decorators=[] calls=[] verdict=ok
- _terminal_control_repo L3477-3488 12 decorators=[] calls=['_new_repo', 'open_run', 'start_task'] verdict=ok
- _abort_bound_chain_fixture L3528-3565 38 decorators=[] calls=[] verdict=ok
- _self_event_fixture L3699-3733 35 decorators=[] calls=[] verdict=ok
- _open_legacy_run L4141-4175 35 decorators=[] calls=[] verdict=ok
- _activation_markers L4178-4185 8 decorators=['staticmethod'] calls=[] verdict=wrap
- _run_file_bytes L4188-4193 6 decorators=['staticmethod'] calls=[] verdict=wrap
- _plant_unreplayable_unrelated_chain L4195-4208 14 decorators=[] calls=[] verdict=ok
- _pad_valid_json_over_cap L4211-4215 5 decorators=['staticmethod'] calls=[] verdict=wrap
- _guard_activation_artifact_read_budget L4218-4267 46 decorators=['contextmanager'] calls=[] verdict=wrap
- _assert_first_batch_artifact_substitution_refuses L4269-4331 60 decorators=[] calls=['_new_repo', '_open_legacy_run', 'api_environment', 'run_dir', 'start_task'] verdict=ok
- _activation_outbox_case L4407-4494 87 decorators=[] calls=['_new_repo', '_open_legacy_run', '_write_bound_chain_state', 'run_dir'] verdict=ok
- _compete_with_activation_outbox L4496-4512 17 decorators=[] calls=[] verdict=ok
- _invoke_raw_lifecycle L4514-4538 25 decorators=[] calls=['run_dir'] verdict=ok
- _bound_chain_outbox L4540-4568 29 decorators=[] calls=[] verdict=ok
- _acknowledge_bound_chain L4570-4616 47 decorators=[] calls=[] verdict=ok
- _legacy_receipted_chain_case L4618-4697 80 decorators=[] calls=['_acknowledge_bound_chain', '_bound_chain_outbox', '_open_legacy_run', '_write_bound_chain_state'] verdict=ok
- _rewrite_commit_events L4699-4723 25 decorators=[] calls=[] verdict=ok
- _restore_prefix_wedge_fixture L7465-7502 37 decorators=[] calls=['_new_repo', 'run_dir'] verdict=ok
- _seed_unactivated_stale_ledger L7641-7708 66 decorators=[] calls=['_open_legacy_run', 'run_dir'] verdict=ok
- _seed_gh17_wedge L7846-8007 157 decorators=[] calls=['_open_legacy_run', '_write_landed_intent_for_last_receipt', 'run_dir'] verdict=ok
- _assert_gh17_recovered L8009-8086 77 decorators=[] calls=['_activation_markers'] verdict=ok
- command L8824-8833 10 decorators=[] calls=[] verdict=ok
