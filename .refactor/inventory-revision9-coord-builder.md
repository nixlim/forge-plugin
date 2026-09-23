{
  "name": "Revision9BuilderBatchTests",
  "bases": [
    "unittest.TestCase"
  ],
  "metaclass": [],
  "decorators": [],
  "statements": [],
  "slots": false,
  "methods": [
    {
      "name": "setUp",
      "line": 200,
      "end_line": 205,
      "decorators": [],
      "reads": [
        "_new_repo",
        "addCleanup",
        "env",
        "temporary"
      ],
      "writes": [
        "env",
        "head",
        "repo",
        "temporary"
      ],
      "calls": [
        "_new_repo",
        "addCleanup"
      ],
      "globals": [
        "os",
        "tempfile"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_new_repo",
      "line": 207,
      "end_line": 235,
      "decorators": [],
      "reads": [
        "temporary"
      ],
      "writes": [],
      "calls": [],
      "globals": [
        "Path",
        "subprocess"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "api_environment",
      "line": 238,
      "end_line": 240,
      "decorators": [
        "contextmanager"
      ],
      "reads": [
        "env"
      ],
      "writes": [],
      "calls": [],
      "globals": [
        "mock",
        "os"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "wrap"
    },
    {
      "name": "run_dir",
      "line": 242,
      "end_line": 243,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "open_run",
      "line": 245,
      "end_line": 253,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "builders",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "start_task",
      "line": 255,
      "end_line": 264,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "builders",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "line": 266,
      "end_line": 393,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "head",
        "open_run",
        "repo",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "json",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_leave_complete_intent",
      "line": 395,
      "end_line": 432,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertNotIn",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertNotIn",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "base64",
        "batch",
        "journal",
        "json",
        "mock",
        "os"
      ],
      "nested_defs": [
        "crash_after_journal"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_leave_base_intent",
      "line": 434,
      "end_line": 451,
      "decorators": [],
      "reads": [
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "journal",
        "json",
        "mock"
      ],
      "nested_defs": [
        "crash_after_intent"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_exact_prefix_and_torn_receipt_recovery",
      "line": 453,
      "end_line": 481,
      "decorators": [],
      "reads": [
        "_leave_complete_intent",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue"
      ],
      "writes": [],
      "calls": [
        "_leave_complete_intent",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue"
      ],
      "globals": [
        "base64",
        "batch",
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only",
      "line": 483,
      "end_line": 509,
      "decorators": [],
      "reads": [
        "_leave_complete_intent",
        "api_environment",
        "assertEqual",
        "repo",
        "temporary"
      ],
      "writes": [],
      "calls": [
        "_leave_complete_intent",
        "api_environment",
        "assertEqual"
      ],
      "globals": [
        "Path",
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_torn_intent_never_becomes_authoritative",
      "line": 511,
      "end_line": 542,
      "decorators": [],
      "reads": [
        "_leave_base_intent",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_leave_base_intent",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "start_task",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_self_consistent_intent_substitution_after_prepare_is_refused",
      "line": 544,
      "end_line": 585,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "base64",
        "batch",
        "copy",
        "journal",
        "json",
        "key",
        "mock"
      ],
      "nested_defs": [
        "substitute"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activated_missing_stable_lock_or_receipt_ledger_diverges",
      "line": 587,
      "end_line": 609,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "globals": [
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze",
      "line": 611,
      "end_line": 644,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "globals": [
        "journal",
        "json",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_intent_without_journal_and_reentrant_pending_read_refuse_exactly",
      "line": 646,
      "end_line": 673,
      "decorators": [],
      "reads": [
        "_leave_base_intent",
        "_new_repo",
        "api_environment",
        "assertEqual"
      ],
      "writes": [],
      "calls": [
        "_leave_base_intent",
        "_new_repo",
        "api_environment",
        "assertEqual"
      ],
      "globals": [
        "batch",
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_midflight_intent_hardlink_fifo_and_foreign_uid_fences",
      "line": 675,
      "end_line": 707,
      "decorators": [],
      "reads": [
        "_leave_base_intent",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "subTest",
        "temporary"
      ],
      "writes": [],
      "calls": [
        "_leave_base_intent",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "subTest"
      ],
      "globals": [
        "Path",
        "batch",
        "journal",
        "mock",
        "nullcontext",
        "os"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_batch_controls_are_load_bearing",
      "line": 709,
      "end_line": 777,
      "decorators": [],
      "reads": [
        "_leave_complete_intent",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "open_run",
        "repo",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_leave_complete_intent",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "journal",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_builder_validation_controls_are_detected_in_memory",
      "line": 779,
      "end_line": 826,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "open_run",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "open_run",
        "start_task"
      ],
      "globals": [
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activated_scope_readmission_uses_typed_builder",
      "line": 828,
      "end_line": 906,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertIsInstance",
        "assertRaisesRegex",
        "assertTrue",
        "command",
        "open_run",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertIsInstance",
        "assertRaisesRegex",
        "assertTrue",
        "command",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume",
      "line": 908,
      "end_line": 981,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "command",
        "open_run",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "command",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "builders",
        "journal",
        "json",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_scope_change_recovers_intent_and_receipted_registry_publication",
      "line": 983,
      "end_line": 1065,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "open_run",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "open_run",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "batch",
        "builders",
        "contextmanager",
        "journal",
        "json",
        "key",
        "mock"
      ],
      "nested_defs": [
        "counted_registry_lock"
      ],
      "nonlocal_names": [
        "registry_epochs"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_scope_change_recovery_refuses_unproved_replace_and_disabled_control",
      "line": 1067,
      "end_line": 1154,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "line": 1156,
      "end_line": 1231,
      "decorators": [],
      "reads": [
        "_leave_complete_intent",
        "_leave_scope_receipt_gap",
        "_new_repo",
        "_write_landed_intent_for_last_receipt",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_leave_complete_intent",
        "_leave_scope_receipt_gap",
        "_new_repo",
        "_write_landed_intent_for_last_receipt",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [
        "assert_unchanged_refusal"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_batch_recover_repairs_one_n_record_gap",
      "line": 1233,
      "end_line": 1311,
      "decorators": [],
      "reads": [
        "_leave_two_record_receipt_gap",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "repo"
      ],
      "writes": [],
      "calls": [
        "_leave_two_record_receipt_gap",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_batch_gap_repair_controls_are_independently_load_bearing",
      "line": 1313,
      "end_line": 1356,
      "decorators": [],
      "reads": [
        "_leave_two_record_receipt_gap",
        "_new_repo",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_leave_two_record_receipt_gap",
        "_new_repo",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_repair_receipt_is_rederived_on_every_load",
      "line": 1358,
      "end_line": 1386,
      "decorators": [],
      "reads": [
        "_leave_scope_receipt_gap",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertIs",
        "assertRaisesRegex",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_leave_scope_receipt_gap",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertIs",
        "assertRaisesRegex",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "json",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_torn_repair_receipt_resumes_only_its_derived_suffix",
      "line": 1388,
      "end_line": 1434,
      "decorators": [],
      "reads": [
        "_leave_scope_receipt_gap",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "repo"
      ],
      "writes": [],
      "calls": [
        "_leave_scope_receipt_gap",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue"
      ],
      "globals": [
        "batch",
        "journal",
        "mock"
      ],
      "nested_defs": [
        "tear_repair"
      ],
      "nonlocal_names": [
        "tore"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activated_scope_change_rechecks_superset_containment_and_conflicts",
      "line": 1436,
      "end_line": 1510,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertIn",
        "assertRaises",
        "repo",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertIn",
        "assertRaises",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_concurrent_admission_and_scope_change_remain_disjoint",
      "line": 1512,
      "end_line": 1636,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertIn",
        "open_run",
        "repo",
        "run_dir",
        "temporary"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertIn",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "Path",
        "ROOT",
        "batch",
        "journal",
        "json",
        "subprocess",
        "sys"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_leave_scope_receipt_gap",
      "line": 1638,
      "end_line": 1708,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "open_run",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "json",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_leave_two_record_receipt_gap",
      "line": 1710,
      "end_line": 1754,
      "decorators": [],
      "reads": [
        "_write_landed_intent_for_last_receipt",
        "assertEqual",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_write_landed_intent_for_last_receipt",
        "assertEqual",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "builders",
        "journal",
        "json",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_write_landed_intent_for_last_receipt",
      "line": 1756,
      "end_line": 1784,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "batch",
        "journal",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_batch_recover_repairs_proven_readmission_gap_and_stale_intent",
      "line": 1786,
      "end_line": 1830,
      "decorators": [],
      "reads": [
        "_leave_scope_receipt_gap",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "repo"
      ],
      "writes": [],
      "calls": [
        "_leave_scope_receipt_gap",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_batch_gap_repair_refuses_unproved_bytes_and_intent",
      "line": 1832,
      "end_line": 1933,
      "decorators": [],
      "reads": [
        "_leave_scope_receipt_gap",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_leave_scope_receipt_gap",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "subTest"
      ],
      "globals": [
        "base64",
        "batch",
        "journal",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_typed_task_scope_refusal_names_offending_pathspec",
      "line": 1935,
      "end_line": 1950,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertRaisesRegex",
        "open_run",
        "repo"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertRaisesRegex",
        "open_run"
      ],
      "globals": [
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_builder_request_schema_and_digest_are_exact",
      "line": 1952,
      "end_line": 2005,
      "decorators": [],
      "reads": [
        "assertEqual",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual"
      ],
      "globals": [
        "batch",
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_run_open_is_hidden_until_atomic_publication",
      "line": 2007,
      "end_line": 2042,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "open_run",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "journal",
        "mock"
      ],
      "nested_defs": [
        "observe"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_run_open_prepublication_crashes_leave_no_visible_run",
      "line": 2044,
      "end_line": 2077,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertRaises",
        "open_run",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertRaises",
        "open_run",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "journal",
        "mock"
      ],
      "nested_defs": [
        "fail_journal"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_run_open_durable_receipt_survives_registry_failure_and_retry",
      "line": 2079,
      "end_line": 2114,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertRaisesRegex",
        "assertTrue",
        "open_run",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertRaisesRegex",
        "assertTrue",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "journal",
        "json",
        "mock"
      ],
      "nested_defs": [
        "fail_once"
      ],
      "nonlocal_names": [
        "failures"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_run_open_process_death_keeps_staging_invisible_and_retryable",
      "line": 2117,
      "end_line": 2195,
      "decorators": [
        "unittest.skipUnless(hasattr(os, 'fork'), 'requires macOS/Linux fork semantics')"
      ],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertTrue",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertTrue",
        "run_dir"
      ],
      "globals": [
        "builders",
        "journal",
        "json",
        "key",
        "mock",
        "os"
      ],
      "nested_defs": [
        "invoke_open",
        "die_after_staged_journal"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [
        "unknown decorator"
      ],
      "verdict": "unsupported"
    },
    {
      "name": "test_fr019_failure_phase_order_preserves_earlier_bytes",
      "line": 2197,
      "end_line": 2258,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "line": 2260,
      "end_line": 2326,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "open_run",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "open_run",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "json",
        "key",
        "mock"
      ],
      "nested_defs": [
        "crash_intent",
        "crash_after_journal",
        "crash_verify",
        "crash_unlink"
      ],
      "nonlocal_names": [
        "receipt_appends"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_prepublication_intent_stage_crashes_retry_without_authority",
      "line": 2328,
      "end_line": 2410,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "open_run",
        "run_dir",
        "skipTest",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "open_run",
        "run_dir",
        "skipTest",
        "start_task",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "crash_write",
        "crash_move"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_foreign_request_intent_stage_is_not_deleted",
      "line": 2412,
      "end_line": 2428,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_intent_source_name_substitution_never_survives_canonical",
      "line": 2430,
      "end_line": 2498,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "substitute_source"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_intent_quarantine_preserves_a_second_canonical_swap",
      "line": 2500,
      "end_line": 2588,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "write_name",
        "swap_twice"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_chain_drain_raw_records_without_capability_refuses",
      "line": 2590,
      "end_line": 2646,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "batch",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "line": 2648,
      "end_line": 2704,
      "decorators": [],
      "reads": [
        "_leave_complete_intent",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "assertTrue",
        "open_run",
        "run_dir",
        "start_task",
        "subTest",
        "temporary"
      ],
      "writes": [],
      "calls": [
        "_leave_complete_intent",
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "assertTrue",
        "open_run",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "globals": [
        "Path",
        "batch",
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "replace_then_recover"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_write_bound_chain_state",
      "line": 2706,
      "end_line": 2958,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "builders",
        "copy",
        "journal",
        "key"
      ],
      "nested_defs": [
        "append_event"
      ],
      "nonlocal_names": [
        "previous"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_chain_drain_case",
      "line": 2960,
      "end_line": 2999,
      "decorators": [],
      "reads": [
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "assertEqual"
      ],
      "writes": [],
      "calls": [
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "assertEqual"
      ],
      "globals": [
        "copy",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_chain_drain_authorizer",
      "line": 3001,
      "end_line": 3096,
      "decorators": [],
      "reads": [
        "assertEqual",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "run_dir"
      ],
      "globals": [
        "batch",
        "copy",
        "journal",
        "key",
        "os"
      ],
      "nested_defs": [
        "exact",
        "authorize"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_chain_drain_valid_authorizer_new_and_repeated_paths",
      "line": 3098,
      "end_line": 3132,
      "decorators": [],
      "reads": [
        "_chain_drain_authorizer",
        "_chain_drain_case",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue"
      ],
      "writes": [],
      "calls": [
        "_chain_drain_authorizer",
        "_chain_drain_case",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue"
      ],
      "globals": [
        "batch",
        "journal",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_chain_drain_authorized_pending_and_lost_response_retry",
      "line": 3134,
      "end_line": 3196,
      "decorators": [],
      "reads": [
        "_chain_drain_authorizer",
        "_chain_drain_case",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_chain_drain_authorizer",
        "_chain_drain_case",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "mock"
      ],
      "nested_defs": [
        "crash_recovery"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_chain_drain_authorization_exact_field_bindings",
      "line": 3198,
      "end_line": 3277,
      "decorators": [],
      "reads": [
        "_chain_drain_authorizer",
        "_chain_drain_case",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertRaisesRegex",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_chain_drain_authorizer",
        "_chain_drain_case",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertRaisesRegex",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_chain_drain_authorization_controls_are_load_bearing",
      "line": 3279,
      "end_line": 3330,
      "decorators": [],
      "reads": [
        "_chain_drain_authorizer",
        "_chain_drain_case",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_chain_drain_authorizer",
        "_chain_drain_case",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_ingest_requires_registered_proof_complete_authority",
      "line": 3332,
      "end_line": 3423,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "head",
        "open_run",
        "repo",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "open_run",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "globals": [
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [
        "ingest"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_append_test_landing",
      "line": 3425,
      "end_line": 3428,
      "decorators": [],
      "reads": [
        "_append_test_decision"
      ],
      "writes": [],
      "calls": [
        "_append_test_decision"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_append_test_decision",
      "line": 3430,
      "end_line": 3475,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse"
      ],
      "globals": [
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_terminal_control_repo",
      "line": 3477,
      "end_line": 3488,
      "decorators": [],
      "reads": [
        "_new_repo",
        "open_run",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "open_run",
        "start_task"
      ],
      "globals": [
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_terminal_builder_guards_pending_outbox_and_missing_landing",
      "line": 3490,
      "end_line": 3526,
      "decorators": [],
      "reads": [
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertFalse",
        "assertRaisesRegex",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertFalse",
        "assertRaisesRegex",
        "run_dir"
      ],
      "globals": [
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_abort_bound_chain_fixture",
      "line": 3528,
      "end_line": 3565,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "copy",
        "journal",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_terminal_builder_accepts_authenticated_abort_disposition",
      "line": 3567,
      "end_line": 3675,
      "decorators": [],
      "reads": [
        "_abort_bound_chain_fixture",
        "_append_test_decision",
        "_append_test_landing",
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex"
      ],
      "writes": [],
      "calls": [
        "_abort_bound_chain_fixture",
        "_append_test_decision",
        "_append_test_landing",
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex"
      ],
      "globals": [
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_terminal_abort_disposition_fails_closed_on_shape",
      "line": 3677,
      "end_line": 3697,
      "decorators": [],
      "reads": [
        "assertFalse",
        "assertTrue"
      ],
      "writes": [],
      "calls": [
        "assertFalse",
        "assertTrue"
      ],
      "globals": [
        "builders"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_self_event_fixture",
      "line": 3699,
      "end_line": 3733,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "copy",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_abort_disposition_self_event_admission_controls_are_load_bearing",
      "line": 3735,
      "end_line": 3765,
      "decorators": [],
      "reads": [
        "_self_event_fixture",
        "assertFalse",
        "assertTrue"
      ],
      "writes": [],
      "calls": [
        "_self_event_fixture",
        "assertFalse",
        "assertTrue"
      ],
      "globals": [
        "builders",
        "copy",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_abort_disposition_self_event_source_fact_requires_aborted_unchanged_prior",
      "line": 3767,
      "end_line": 3803,
      "decorators": [],
      "reads": [
        "_self_event_fixture",
        "assertFalse",
        "assertTrue"
      ],
      "writes": [],
      "calls": [
        "_self_event_fixture",
        "assertFalse",
        "assertTrue"
      ],
      "globals": [
        "builders",
        "copy"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_terminal_builder_accepts_only_explicit_absent_chain_tombstone",
      "line": 3805,
      "end_line": 3882,
      "decorators": [],
      "reads": [
        "_append_test_landing",
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex"
      ],
      "writes": [],
      "calls": [
        "_append_test_landing",
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex"
      ],
      "globals": [
        "builders",
        "journal",
        "key",
        "mock",
        "os"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine",
      "line": 3884,
      "end_line": 3975,
      "decorators": [],
      "reads": [
        "_append_test_landing",
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex"
      ],
      "writes": [],
      "calls": [
        "_append_test_landing",
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex"
      ],
      "globals": [
        "builders",
        "journal",
        "key",
        "mock",
        "os"
      ],
      "nested_defs": [
        "captured"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_each_terminal_chain_control_is_load_bearing",
      "line": 3977,
      "end_line": 4089,
      "decorators": [],
      "reads": [
        "_append_test_landing",
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "temporary"
      ],
      "writes": [],
      "calls": [
        "_append_test_landing",
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex"
      ],
      "globals": [
        "Path",
        "builders",
        "journal",
        "json",
        "key",
        "mock",
        "os"
      ],
      "nested_defs": [
        "resolve_outbox_fixture"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_terminal_guard_refuses_chain_root_swap_after_enumeration",
      "line": 4091,
      "end_line": 4139,
      "decorators": [],
      "reads": [
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_terminal_control_repo",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "run_dir"
      ],
      "globals": [
        "builders",
        "contextmanager",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [
        "swap_before_chain_lock"
      ],
      "nonlocal_names": [
        "swapped"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_open_legacy_run",
      "line": 4141,
      "end_line": 4175,
      "decorators": [],
      "reads": [
        "assertEqual"
      ],
      "writes": [],
      "calls": [
        "assertEqual"
      ],
      "globals": [
        "io",
        "journal",
        "redirect_stderr",
        "subprocess"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_activation_markers",
      "line": 4178,
      "end_line": 4185,
      "decorators": [
        "staticmethod"
      ],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "wrap"
    },
    {
      "name": "_run_file_bytes",
      "line": 4188,
      "end_line": 4193,
      "decorators": [
        "staticmethod"
      ],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "wrap"
    },
    {
      "name": "_plant_unreplayable_unrelated_chain",
      "line": 4195,
      "end_line": 4208,
      "decorators": [],
      "reads": [
        "assertEqual"
      ],
      "writes": [],
      "calls": [
        "assertEqual"
      ],
      "globals": [
        "UNREPLAYABLE_CHAIN_FIXTURE",
        "UNREPLAYABLE_CHAIN_FIXTURE_SHA256",
        "builders",
        "hashlib",
        "os",
        "shutil"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_pad_valid_json_over_cap",
      "line": 4211,
      "end_line": 4215,
      "decorators": [
        "staticmethod"
      ],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "wrap"
    },
    {
      "name": "_guard_activation_artifact_read_budget",
      "line": 4218,
      "end_line": 4267,
      "decorators": [
        "contextmanager"
      ],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "builders",
        "mock",
        "os"
      ],
      "nested_defs": [
        "monitored_reader",
        "counted_read"
      ],
      "nonlocal_names": [
        "total"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "wrap"
    },
    {
      "name": "_assert_first_batch_artifact_substitution_refuses",
      "line": 4269,
      "end_line": 4331,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotEqual",
        "assertRaisesRegex",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotEqual",
        "assertRaisesRegex",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "journal",
        "key",
        "mock",
        "os"
      ],
      "nested_defs": [
        "substitute_after_create"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_batch_lock_create_open_substitution_refuses",
      "line": 4333,
      "end_line": 4336,
      "decorators": [],
      "reads": [
        "_assert_first_batch_artifact_substitution_refuses"
      ],
      "writes": [],
      "calls": [
        "_assert_first_batch_artifact_substitution_refuses"
      ],
      "globals": [
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_first_receipt_ledger_create_open_substitution_refuses",
      "line": 4338,
      "end_line": 4341,
      "decorators": [],
      "reads": [
        "_assert_first_batch_artifact_substitution_refuses"
      ],
      "writes": [],
      "calls": [
        "_assert_first_batch_artifact_substitution_refuses"
      ],
      "globals": [
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_first_receipt_ledger_post_create_substitution_refuses",
      "line": 4343,
      "end_line": 4405,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotEqual",
        "assertRaisesRegex",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotEqual",
        "assertRaisesRegex",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "substitute_after_ensure"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_activation_outbox_case",
      "line": 4407,
      "end_line": 4494,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "assertEqual",
        "assertTrue",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "assertEqual",
        "assertTrue",
        "run_dir"
      ],
      "globals": [
        "batch",
        "builders",
        "copy",
        "journal",
        "json",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_compete_with_activation_outbox",
      "line": 4496,
      "end_line": 4512,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "builders",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_invoke_raw_lifecycle",
      "line": 4514,
      "end_line": 4538,
      "decorators": [],
      "reads": [
        "assertEqual",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "run_dir"
      ],
      "globals": [
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_bound_chain_outbox",
      "line": 4540,
      "end_line": 4568,
      "decorators": [],
      "reads": [
        "assertEqual"
      ],
      "writes": [],
      "calls": [
        "assertEqual"
      ],
      "globals": [
        "builders",
        "copy",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_acknowledge_bound_chain",
      "line": 4570,
      "end_line": 4616,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "batch",
        "builders",
        "copy",
        "journal",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_legacy_receipted_chain_case",
      "line": 4618,
      "end_line": 4697,
      "decorators": [],
      "reads": [
        "_acknowledge_bound_chain",
        "_bound_chain_outbox",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "assertEqual"
      ],
      "writes": [],
      "calls": [
        "_acknowledge_bound_chain",
        "_bound_chain_outbox",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "assertEqual"
      ],
      "globals": [
        "batch",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_rewrite_commit_events",
      "line": 4699,
      "end_line": 4723,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "builders",
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_commit_sibling_receipt_request_authentication_is_load_bearing",
      "line": 4725,
      "end_line": 4863,
      "decorators": [],
      "reads": [
        "_legacy_receipted_chain_case",
        "_rewrite_commit_events",
        "api_environment",
        "assertEqual",
        "assertRaises",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_legacy_receipted_chain_case",
        "_rewrite_commit_events",
        "api_environment",
        "assertEqual",
        "assertRaises",
        "run_dir"
      ],
      "globals": [
        "CHAIN_CORE",
        "builders",
        "journal",
        "json",
        "key",
        "mock",
        "os"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_commit_sibling_carried_binding_authentication_is_load_bearing",
      "line": 4865,
      "end_line": 5023,
      "decorators": [],
      "reads": [
        "_legacy_receipted_chain_case",
        "_rewrite_commit_events",
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_legacy_receipted_chain_case",
        "_rewrite_commit_events",
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "run_dir"
      ],
      "globals": [
        "CHAIN_CORE",
        "builders",
        "journal",
        "json",
        "key",
        "mock",
        "os"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_commit_sibling_receipt_snapshot_recheck_is_load_bearing",
      "line": 5025,
      "end_line": 5123,
      "decorators": [],
      "reads": [
        "_legacy_receipted_chain_case",
        "api_environment",
        "assertEqual",
        "assertRaises",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_legacy_receipted_chain_case",
        "api_environment",
        "assertEqual",
        "assertRaises",
        "run_dir"
      ],
      "globals": [
        "CHAIN_CORE",
        "builders",
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "mutate_after_resolve"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "line": 5125,
      "end_line": 5172,
      "decorators": [],
      "reads": [
        "_invoke_raw_lifecycle",
        "_new_repo",
        "_open_legacy_run",
        "_plant_unreplayable_unrelated_chain",
        "api_environment",
        "assertEqual",
        "assertTrue",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_invoke_raw_lifecycle",
        "_new_repo",
        "_open_legacy_run",
        "_plant_unreplayable_unrelated_chain",
        "api_environment",
        "assertEqual",
        "assertTrue",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "globals": [
        "UNREPLAYABLE_CHAIN_ID",
        "io",
        "journal",
        "redirect_stderr"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
      "line": 5174,
      "end_line": 5224,
      "decorators": [],
      "reads": [
        "_guard_activation_artifact_read_budget",
        "_new_repo",
        "_open_legacy_run",
        "_pad_valid_json_over_cap",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertTrue",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_guard_activation_artifact_read_budget",
        "_new_repo",
        "_open_legacy_run",
        "_pad_valid_json_over_cap",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertTrue",
        "start_task"
      ],
      "globals": [
        "builders",
        "io",
        "journal",
        "key",
        "redirect_stderr"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "line": 5226,
      "end_line": 5268,
      "decorators": [],
      "reads": [
        "_guard_activation_artifact_read_budget",
        "_new_repo",
        "_open_legacy_run",
        "_pad_valid_json_over_cap",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_guard_activation_artifact_read_budget",
        "_new_repo",
        "_open_legacy_run",
        "_pad_valid_json_over_cap",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_state_byte_cap_is_load_bearing_in_memory",
      "line": 5270,
      "end_line": 5304,
      "decorators": [],
      "reads": [
        "_guard_activation_artifact_read_budget",
        "_new_repo",
        "_open_legacy_run",
        "_pad_valid_json_over_cap",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex"
      ],
      "writes": [],
      "calls": [
        "_guard_activation_artifact_read_budget",
        "_new_repo",
        "_open_legacy_run",
        "_pad_valid_json_over_cap",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex"
      ],
      "globals": [
        "builders",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "line": 5306,
      "end_line": 5355,
      "decorators": [],
      "reads": [
        "_guard_activation_artifact_read_budget",
        "_new_repo",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_guard_activation_artifact_read_budget",
        "_new_repo",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_events_byte_cap_is_load_bearing_in_memory",
      "line": 5357,
      "end_line": 5394,
      "decorators": [],
      "reads": [
        "_guard_activation_artifact_read_budget",
        "_new_repo",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex"
      ],
      "writes": [],
      "calls": [
        "_guard_activation_artifact_read_budget",
        "_new_repo",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex"
      ],
      "globals": [
        "builders",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_scan_converts_bounded_path_memory_errors",
      "line": 5396,
      "end_line": 5434,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertIsNone",
        "assertRaises",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertIsNone",
        "assertRaises",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_replay_passes_scan_only_state_and_event_caps",
      "line": 5436,
      "end_line": 5516,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertTrue",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "_write_bound_chain_state",
        "api_environment",
        "assertEqual",
        "assertTrue",
        "start_task"
      ],
      "globals": [
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [
        "observe_reader"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_scan_unrelated_tolerance_is_load_bearing",
      "line": 5518,
      "end_line": 5537,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "_plant_unreplayable_unrelated_chain",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "_plant_unreplayable_unrelated_chain",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "builders",
        "journal",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_scan_ignores_unrelated_chain_created_between_scans",
      "line": 5539,
      "end_line": 5589,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertTrue",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertTrue",
        "start_task"
      ],
      "globals": [
        "builders",
        "io",
        "journal",
        "mock",
        "redirect_stderr"
      ],
      "nested_defs": [
        "names_with_unrelated_start"
      ],
      "nonlocal_names": [
        "scans"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_scan_bound_chain_created_between_scans_refuses",
      "line": 5591,
      "end_line": 5692,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "globals": [
        "builders",
        "journal",
        "key",
        "mock",
        "nullcontext",
        "patch_chain_core"
      ],
      "nested_defs": [
        "names_with_bound_start"
      ],
      "nonlocal_names": [
        "scans"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_scan_skips_external_sibling_chain_and_run_lock",
      "line": 5694,
      "end_line": 5784,
      "decorators": [],
      "reads": [
        "_legacy_receipted_chain_case",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertNotIn",
        "assertTrue",
        "repo",
        "temporary"
      ],
      "writes": [],
      "calls": [
        "_legacy_receipted_chain_case",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertNotIn",
        "assertTrue"
      ],
      "globals": [
        "Path",
        "batch",
        "builders",
        "contextmanager",
        "journal",
        "key",
        "mock",
        "subprocess"
      ],
      "nested_defs": [
        "probed_lock"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_concurrent_legacy_activation_never_cross_acquires_run_locks",
      "line": 5786,
      "end_line": 5916,
      "decorators": [],
      "reads": [
        "_legacy_receipted_chain_case",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "repo",
        "temporary"
      ],
      "writes": [],
      "calls": [
        "_legacy_receipted_chain_case",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertTrue"
      ],
      "globals": [
        "Path",
        "batch",
        "builders",
        "contextmanager",
        "journal",
        "key",
        "mock",
        "subprocess",
        "threading"
      ],
      "nested_defs": [
        "probed_lock",
        "activate"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_id_only_legacy_opening_activates_with_matching_marker_run_id",
      "line": 5918,
      "end_line": 5959,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertTrue",
        "repo",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertTrue",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "journal",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "line": 5961,
      "end_line": 6058,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "line": 6060,
      "end_line": 6115,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_removed_batch_lock_after_activation_is_not_recreated",
      "line": 6117,
      "end_line": 6141,
      "decorators": [],
      "reads": [
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "repo",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "line": 6143,
      "end_line": 6244,
      "decorators": [],
      "reads": [
        "_activation_markers",
        "_activation_outbox_case",
        "_chain_drain_authorizer",
        "_invoke_raw_lifecycle",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_activation_markers",
        "_activation_outbox_case",
        "_chain_drain_authorizer",
        "_invoke_raw_lifecycle",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_outbox_lifecycle_guard_is_load_bearing",
      "line": 6246,
      "end_line": 6284,
      "decorators": [],
      "reads": [
        "_activation_outbox_case",
        "_invoke_raw_lifecycle",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_activation_outbox_case",
        "_invoke_raw_lifecycle",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "builders",
        "mock",
        "patch_chain_core"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "line": 6286,
      "end_line": 6322,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_raw_lifecycle_validation_precedes_batch_reservation",
      "line": 6324,
      "end_line": 6380,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "journal",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_raw_lifecycle_lock_order_is_load_bearing",
      "line": 6382,
      "end_line": 6522,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "contextmanager",
        "journal",
        "mock"
      ],
      "nested_defs": [
        "observed_guard",
        "observed_registry_lock",
        "observed_locked_journal",
        "observed_write_registry"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_published_first_use_intent_blocks_outbox_before_publication",
      "line": 6524,
      "end_line": 6577,
      "decorators": [],
      "reads": [
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "repo",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "mock"
      ],
      "nested_defs": [
        "publish_then_crash"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_staged_first_use_intent_blocks_outbox_before_publication",
      "line": 6579,
      "end_line": 6608,
      "decorators": [],
      "reads": [
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "run_dir"
      ],
      "globals": [
        "batch",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_raw_open_cannot_supply_writer_contract_before_any_mutation",
      "line": 6610,
      "end_line": 6646,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_raw_open_writer_contract_refusal_is_load_bearing",
      "line": 6648,
      "end_line": 6677,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "head",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "run_dir"
      ],
      "globals": [
        "journal",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_legacy_open_without_stderr_never_falls_back_to_stdout",
      "line": 6679,
      "end_line": 6719,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertTrue",
        "head",
        "repo",
        "run_dir",
        "temporary"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertTrue",
        "run_dir"
      ],
      "globals": [
        "ORCH_TOOLS",
        "Path",
        "io",
        "json",
        "mock",
        "redirect_stdout"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_legacy_open_broken_stderr_never_changes_durable_success",
      "line": 6721,
      "end_line": 6768,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertTrue",
        "head",
        "repo",
        "run_dir",
        "temporary"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertTrue",
        "run_dir"
      ],
      "globals": [
        "ORCH_TOOLS",
        "Path",
        "io",
        "json",
        "mock",
        "redirect_stdout"
      ],
      "nested_defs": [
        "write",
        "flush"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "line": 6770,
      "end_line": 6851,
      "decorators": [],
      "reads": [
        "_activation_markers",
        "_activation_outbox_case",
        "_chain_drain_authorizer",
        "_compete_with_activation_outbox",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_activation_markers",
        "_activation_outbox_case",
        "_chain_drain_authorizer",
        "_compete_with_activation_outbox",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "run_dir"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "json",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_activation_outbox_missing_events_or_tampered_state_refuses_first_use",
      "line": 6853,
      "end_line": 6894,
      "decorators": [],
      "reads": [
        "_activation_outbox_case",
        "_compete_with_activation_outbox",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_activation_outbox_case",
        "_compete_with_activation_outbox",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "journal",
        "json",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_legacy_first_typed_use_atomically_activates",
      "line": 6896,
      "end_line": 6989,
      "decorators": [],
      "reads": [
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertRaisesRegex",
        "assertTrue",
        "repo",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "json",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_legacy_activation_crash_matrix",
      "line": 6991,
      "end_line": 7159,
      "decorators": [],
      "reads": [
        "_activation_markers",
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_activation_markers",
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "json",
        "mock"
      ],
      "nested_defs": [
        "crash_append"
      ],
      "nonlocal_names": [
        "crashed"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_typed_opened_run_bytes_are_unchanged",
      "line": 7161,
      "end_line": 7360,
      "decorators": [],
      "reads": [
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertIsNotNone",
        "assertTrue",
        "head",
        "open_run",
        "repo",
        "run_dir",
        "start_task"
      ],
      "writes": [],
      "calls": [
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertIsNotNone",
        "assertTrue",
        "open_run",
        "run_dir",
        "start_task"
      ],
      "globals": [
        "batch",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [
        "capture_open",
        "capture_task_intent"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_global_reconciliation_defers_torn_adopted_coverage",
      "line": 7362,
      "end_line": 7463,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [
        "crash_before_receipt"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_restore_prefix_wedge_fixture",
      "line": 7465,
      "end_line": 7502,
      "decorators": [],
      "reads": [
        "_new_repo",
        "assertEqual",
        "assertIsNotNone",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "assertEqual",
        "assertIsNotNone",
        "run_dir"
      ],
      "globals": [
        "PREFIX_WEDGE_FIXTURE",
        "PREFIX_WEDGE_FIXTURE_SHA256",
        "Path",
        "hashlib",
        "journal",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_pre_fix_golden_wedge_recovers_and_continues",
      "line": 7504,
      "end_line": 7639,
      "decorators": [],
      "reads": [
        "_activation_markers",
        "_restore_prefix_wedge_fixture",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertGreater",
        "assertTrue",
        "fail"
      ],
      "writes": [],
      "calls": [
        "_activation_markers",
        "_restore_prefix_wedge_fixture",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertGreater",
        "assertTrue",
        "fail"
      ],
      "globals": [
        "Path",
        "batch",
        "builders",
        "hashlib",
        "journal",
        "json",
        "key",
        "mock",
        "os"
      ],
      "nested_defs": [
        "reject_recorded_realpath",
        "restored_chain_storage_root"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_seed_unactivated_stale_ledger",
      "line": 7641,
      "end_line": 7708,
      "decorators": [],
      "reads": [
        "_open_legacy_run",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_open_legacy_run",
        "run_dir"
      ],
      "globals": [
        "batch",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
      "line": 7710,
      "end_line": 7766,
      "decorators": [],
      "reads": [
        "_run_file_bytes",
        "_seed_unactivated_stale_ledger",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertIsInstance",
        "assertLess",
        "assertRaises",
        "repo"
      ],
      "writes": [],
      "calls": [
        "_run_file_bytes",
        "_seed_unactivated_stale_ledger",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertIsInstance",
        "assertLess",
        "assertRaises"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_unactivated_stale_ledger_retire_then_typed_successor",
      "line": 7768,
      "end_line": 7796,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_seed_unactivated_stale_ledger",
        "api_environment",
        "assertEqual",
        "assertTrue"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_seed_unactivated_stale_ledger",
        "api_environment",
        "assertEqual",
        "assertTrue"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_unactivated_stale_ledger_raw_close_succeeds",
      "line": 7798,
      "end_line": 7815,
      "decorators": [],
      "reads": [
        "_invoke_raw_lifecycle",
        "_new_repo",
        "_seed_unactivated_stale_ledger",
        "api_environment",
        "assertEqual"
      ],
      "writes": [],
      "calls": [
        "_invoke_raw_lifecycle",
        "_new_repo",
        "_seed_unactivated_stale_ledger",
        "api_environment",
        "assertEqual"
      ],
      "globals": [
        "batch",
        "journal",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_unactivated_stale_ledger_eof_guard_is_load_bearing",
      "line": 7817,
      "end_line": 7844,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_run_file_bytes",
        "_seed_unactivated_stale_ledger",
        "api_environment",
        "assertNotEqual",
        "assertRaises"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_run_file_bytes",
        "_seed_unactivated_stale_ledger",
        "api_environment",
        "assertNotEqual",
        "assertRaises"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_seed_gh17_wedge",
      "line": 7846,
      "end_line": 8007,
      "decorators": [],
      "reads": [
        "_open_legacy_run",
        "_write_landed_intent_for_last_receipt",
        "assertEqual",
        "assertGreaterEqual",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_open_legacy_run",
        "_write_landed_intent_for_last_receipt",
        "assertEqual",
        "assertGreaterEqual",
        "run_dir"
      ],
      "globals": [
        "batch",
        "journal",
        "key"
      ],
      "nested_defs": [
        "raw_verification"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_assert_gh17_recovered",
      "line": 8009,
      "end_line": 8086,
      "decorators": [],
      "reads": [
        "_activation_markers",
        "assertEqual",
        "assertFalse",
        "assertIsInstance"
      ],
      "writes": [],
      "calls": [
        "_activation_markers",
        "assertEqual",
        "assertFalse",
        "assertIsInstance"
      ],
      "globals": [
        "journal",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_gh17_shape_recovers_without_reapplication",
      "line": 8088,
      "end_line": 8145,
      "decorators": [],
      "reads": [
        "_assert_gh17_recovered",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertIsInstance",
        "assertRaisesRegex",
        "assertTrue",
        "repo"
      ],
      "writes": [],
      "calls": [
        "_assert_gh17_recovered",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertIsInstance",
        "assertRaisesRegex",
        "assertTrue"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_gh17_shape_refuses_explicit_foreign_gap_run_id",
      "line": 8147,
      "end_line": 8167,
      "decorators": [],
      "reads": [
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertNotIn",
        "assertRaisesRegex",
        "repo"
      ],
      "writes": [],
      "calls": [
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertNotIn",
        "assertRaisesRegex"
      ],
      "globals": [
        "batch",
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_recovery_activation_crash_matrix",
      "line": 8169,
      "end_line": 8285,
      "decorators": [],
      "reads": [
        "_assert_gh17_recovered",
        "_new_repo",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "assertTrue",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_assert_gh17_recovered",
        "_new_repo",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "assertTrue",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "mock"
      ],
      "nested_defs": [
        "crash_prefix",
        "crash_append"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_repair_receipt_n_record_members_rederived",
      "line": 8287,
      "end_line": 8407,
      "decorators": [],
      "reads": [
        "_assert_gh17_recovered",
        "_new_repo",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertIsInstance",
        "assertRaisesRegex",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_assert_gh17_recovered",
        "_new_repo",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertIsInstance",
        "assertRaisesRegex",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_stable_reader_rederives_every_n_record_repair_member",
      "line": 8409,
      "end_line": 8515,
      "decorators": [],
      "reads": [
        "_assert_gh17_recovered",
        "_new_repo",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertIsInstance",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_assert_gh17_recovered",
        "_new_repo",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertIsInstance",
        "subTest"
      ],
      "globals": [
        "batch",
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_writer_activation_controls_are_independently_load_bearing",
      "line": 8517,
      "end_line": 8567,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertRaises",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "_run_file_bytes",
        "_seed_gh17_wedge",
        "api_environment",
        "assertEqual",
        "assertRaises",
        "run_dir",
        "start_task",
        "subTest"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_retired_successor_close_intent_recovers_and_releases_registry",
      "line": 8569,
      "end_line": 8607,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir"
      ],
      "globals": [
        "batch",
        "builders",
        "journal",
        "json",
        "key",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_retired_successor_close_recovers_every_stored_suffix_prefix",
      "line": 8609,
      "end_line": 8689,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "base64",
        "batch",
        "builders",
        "journal",
        "json",
        "key",
        "mock",
        "os"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_retired_successor_recovery_rejects_other_run_mutation",
      "line": 8691,
      "end_line": 8769,
      "decorators": [],
      "reads": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "_open_legacy_run",
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "assertRaisesRegex",
        "assertTrue",
        "run_dir"
      ],
      "globals": [
        "base64",
        "batch",
        "builders",
        "journal",
        "json",
        "key",
        "mock",
        "os"
      ],
      "nested_defs": [
        "mutate_after_first_fence"
      ],
      "nonlocal_names": [
        "fence_calls"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_internal_typed_flag_cannot_bypass_activated_batch_builders",
      "line": 8771,
      "end_line": 8822,
      "decorators": [],
      "reads": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "open_run",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "_new_repo",
        "api_environment",
        "assertEqual",
        "assertRaisesRegex",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "command",
      "line": 8824,
      "end_line": 8833,
      "decorators": [],
      "reads": [
        "env",
        "repo"
      ],
      "writes": [],
      "calls": [],
      "globals": [
        "TOOLS",
        "subprocess",
        "sys"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet",
      "line": 8835,
      "end_line": 8942,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertIsInstance",
        "command",
        "head",
        "repo",
        "run_dir",
        "temporary"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertIsInstance",
        "command",
        "run_dir"
      ],
      "globals": [
        "Path",
        "journal",
        "json",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_cli_singleton_and_idempotency_key_diagnostics",
      "line": 8944,
      "end_line": 8971,
      "decorators": [],
      "reads": [
        "assertEqual",
        "command",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "command"
      ],
      "globals": [
        "journal",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    }
  ],
  "edges": [
    [
      "_activation_outbox_case",
      "@state:assertEqual"
    ],
    [
      "_activation_outbox_case",
      "@state:assertTrue"
    ],
    [
      "_activation_outbox_case",
      "_new_repo"
    ],
    [
      "_activation_outbox_case",
      "_open_legacy_run"
    ],
    [
      "_activation_outbox_case",
      "_write_bound_chain_state"
    ],
    [
      "_activation_outbox_case",
      "run_dir"
    ],
    [
      "_append_test_decision",
      "@state:assertEqual"
    ],
    [
      "_append_test_decision",
      "@state:assertFalse"
    ],
    [
      "_append_test_landing",
      "_append_test_decision"
    ],
    [
      "_assert_first_batch_artifact_substitution_refuses",
      "@state:assertEqual"
    ],
    [
      "_assert_first_batch_artifact_substitution_refuses",
      "@state:assertFalse"
    ],
    [
      "_assert_first_batch_artifact_substitution_refuses",
      "@state:assertNotEqual"
    ],
    [
      "_assert_first_batch_artifact_substitution_refuses",
      "@state:assertRaisesRegex"
    ],
    [
      "_assert_first_batch_artifact_substitution_refuses",
      "_new_repo"
    ],
    [
      "_assert_first_batch_artifact_substitution_refuses",
      "_open_legacy_run"
    ],
    [
      "_assert_first_batch_artifact_substitution_refuses",
      "api_environment"
    ],
    [
      "_assert_first_batch_artifact_substitution_refuses",
      "run_dir"
    ],
    [
      "_assert_first_batch_artifact_substitution_refuses",
      "start_task"
    ],
    [
      "_assert_gh17_recovered",
      "@state:assertEqual"
    ],
    [
      "_assert_gh17_recovered",
      "@state:assertFalse"
    ],
    [
      "_assert_gh17_recovered",
      "@state:assertIsInstance"
    ],
    [
      "_assert_gh17_recovered",
      "_activation_markers"
    ],
    [
      "_bound_chain_outbox",
      "@state:assertEqual"
    ],
    [
      "_chain_drain_authorizer",
      "@state:assertEqual"
    ],
    [
      "_chain_drain_authorizer",
      "run_dir"
    ],
    [
      "_chain_drain_case",
      "@state:assertEqual"
    ],
    [
      "_chain_drain_case",
      "_terminal_control_repo"
    ],
    [
      "_chain_drain_case",
      "_write_bound_chain_state"
    ],
    [
      "_invoke_raw_lifecycle",
      "@state:assertEqual"
    ],
    [
      "_invoke_raw_lifecycle",
      "run_dir"
    ],
    [
      "_leave_base_intent",
      "@state:assertRaisesRegex"
    ],
    [
      "_leave_base_intent",
      "open_run"
    ],
    [
      "_leave_base_intent",
      "run_dir"
    ],
    [
      "_leave_base_intent",
      "start_task"
    ],
    [
      "_leave_complete_intent",
      "@state:assertEqual"
    ],
    [
      "_leave_complete_intent",
      "@state:assertNotIn"
    ],
    [
      "_leave_complete_intent",
      "@state:assertRaisesRegex"
    ],
    [
      "_leave_complete_intent",
      "open_run"
    ],
    [
      "_leave_complete_intent",
      "run_dir"
    ],
    [
      "_leave_complete_intent",
      "start_task"
    ],
    [
      "_leave_scope_receipt_gap",
      "@state:assertEqual"
    ],
    [
      "_leave_scope_receipt_gap",
      "@state:assertRaises"
    ],
    [
      "_leave_scope_receipt_gap",
      "@state:assertTrue"
    ],
    [
      "_leave_scope_receipt_gap",
      "open_run"
    ],
    [
      "_leave_scope_receipt_gap",
      "run_dir"
    ],
    [
      "_leave_two_record_receipt_gap",
      "@state:assertEqual"
    ],
    [
      "_leave_two_record_receipt_gap",
      "_write_landed_intent_for_last_receipt"
    ],
    [
      "_leave_two_record_receipt_gap",
      "open_run"
    ],
    [
      "_leave_two_record_receipt_gap",
      "run_dir"
    ],
    [
      "_leave_two_record_receipt_gap",
      "start_task"
    ],
    [
      "_legacy_receipted_chain_case",
      "@state:assertEqual"
    ],
    [
      "_legacy_receipted_chain_case",
      "_acknowledge_bound_chain"
    ],
    [
      "_legacy_receipted_chain_case",
      "_bound_chain_outbox"
    ],
    [
      "_legacy_receipted_chain_case",
      "_open_legacy_run"
    ],
    [
      "_legacy_receipted_chain_case",
      "_write_bound_chain_state"
    ],
    [
      "_new_repo",
      "@state:temporary"
    ],
    [
      "_open_legacy_run",
      "@state:assertEqual"
    ],
    [
      "_plant_unreplayable_unrelated_chain",
      "@state:assertEqual"
    ],
    [
      "_restore_prefix_wedge_fixture",
      "@state:assertEqual"
    ],
    [
      "_restore_prefix_wedge_fixture",
      "@state:assertIsNotNone"
    ],
    [
      "_restore_prefix_wedge_fixture",
      "_new_repo"
    ],
    [
      "_restore_prefix_wedge_fixture",
      "run_dir"
    ],
    [
      "_seed_gh17_wedge",
      "@state:assertEqual"
    ],
    [
      "_seed_gh17_wedge",
      "@state:assertGreaterEqual"
    ],
    [
      "_seed_gh17_wedge",
      "_open_legacy_run"
    ],
    [
      "_seed_gh17_wedge",
      "_write_landed_intent_for_last_receipt"
    ],
    [
      "_seed_gh17_wedge",
      "run_dir"
    ],
    [
      "_seed_unactivated_stale_ledger",
      "_open_legacy_run"
    ],
    [
      "_seed_unactivated_stale_ledger",
      "run_dir"
    ],
    [
      "_terminal_control_repo",
      "_new_repo"
    ],
    [
      "_terminal_control_repo",
      "open_run"
    ],
    [
      "_terminal_control_repo",
      "start_task"
    ],
    [
      "api_environment",
      "@state:env"
    ],
    [
      "command",
      "@state:env"
    ],
    [
      "command",
      "@state:repo"
    ],
    [
      "setUp",
      "@state:addCleanup"
    ],
    [
      "setUp",
      "@state:env"
    ],
    [
      "setUp",
      "@state:head"
    ],
    [
      "setUp",
      "@state:repo"
    ],
    [
      "setUp",
      "@state:temporary"
    ],
    [
      "setUp",
      "_new_repo"
    ],
    [
      "test_abort_disposition_self_event_admission_controls_are_load_bearing",
      "@state:assertFalse"
    ],
    [
      "test_abort_disposition_self_event_admission_controls_are_load_bearing",
      "@state:assertTrue"
    ],
    [
      "test_abort_disposition_self_event_admission_controls_are_load_bearing",
      "_self_event_fixture"
    ],
    [
      "test_abort_disposition_self_event_source_fact_requires_aborted_unchanged_prior",
      "@state:assertFalse"
    ],
    [
      "test_abort_disposition_self_event_source_fact_requires_aborted_unchanged_prior",
      "@state:assertTrue"
    ],
    [
      "test_abort_disposition_self_event_source_fact_requires_aborted_unchanged_prior",
      "_self_event_fixture"
    ],
    [
      "test_activated_missing_stable_lock_or_receipt_ledger_diverges",
      "@state:assertEqual"
    ],
    [
      "test_activated_missing_stable_lock_or_receipt_ledger_diverges",
      "@state:assertFalse"
    ],
    [
      "test_activated_missing_stable_lock_or_receipt_ledger_diverges",
      "@state:assertRaisesRegex"
    ],
    [
      "test_activated_missing_stable_lock_or_receipt_ledger_diverges",
      "@state:subTest"
    ],
    [
      "test_activated_missing_stable_lock_or_receipt_ledger_diverges",
      "_new_repo"
    ],
    [
      "test_activated_missing_stable_lock_or_receipt_ledger_diverges",
      "api_environment"
    ],
    [
      "test_activated_missing_stable_lock_or_receipt_ledger_diverges",
      "open_run"
    ],
    [
      "test_activated_missing_stable_lock_or_receipt_ledger_diverges",
      "run_dir"
    ],
    [
      "test_activated_missing_stable_lock_or_receipt_ledger_diverges",
      "start_task"
    ],
    [
      "test_activated_scope_change_rechecks_superset_containment_and_conflicts",
      "@state:assertEqual"
    ],
    [
      "test_activated_scope_change_rechecks_superset_containment_and_conflicts",
      "@state:assertIn"
    ],
    [
      "test_activated_scope_change_rechecks_superset_containment_and_conflicts",
      "@state:assertRaises"
    ],
    [
      "test_activated_scope_change_rechecks_superset_containment_and_conflicts",
      "@state:repo"
    ],
    [
      "test_activated_scope_change_rechecks_superset_containment_and_conflicts",
      "@state:subTest"
    ],
    [
      "test_activated_scope_change_rechecks_superset_containment_and_conflicts",
      "api_environment"
    ],
    [
      "test_activated_scope_change_rechecks_superset_containment_and_conflicts",
      "run_dir"
    ],
    [
      "test_activated_scope_readmission_uses_typed_builder",
      "@state:assertEqual"
    ],
    [
      "test_activated_scope_readmission_uses_typed_builder",
      "@state:assertFalse"
    ],
    [
      "test_activated_scope_readmission_uses_typed_builder",
      "@state:assertIsInstance"
    ],
    [
      "test_activated_scope_readmission_uses_typed_builder",
      "@state:assertRaisesRegex"
    ],
    [
      "test_activated_scope_readmission_uses_typed_builder",
      "@state:assertTrue"
    ],
    [
      "test_activated_scope_readmission_uses_typed_builder",
      "@state:repo"
    ],
    [
      "test_activated_scope_readmission_uses_typed_builder",
      "api_environment"
    ],
    [
      "test_activated_scope_readmission_uses_typed_builder",
      "command"
    ],
    [
      "test_activated_scope_readmission_uses_typed_builder",
      "open_run"
    ],
    [
      "test_activated_scope_readmission_uses_typed_builder",
      "run_dir"
    ],
    [
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "@state:assertEqual"
    ],
    [
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "@state:assertFalse"
    ],
    [
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "@state:assertRaisesRegex"
    ],
    [
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "@state:assertTrue"
    ],
    [
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "@state:subTest"
    ],
    [
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "_new_repo"
    ],
    [
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "_open_legacy_run"
    ],
    [
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "_run_file_bytes"
    ],
    [
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "api_environment"
    ],
    [
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "run_dir"
    ],
    [
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "start_task"
    ],
    [
      "test_activation_events_byte_cap_is_load_bearing_in_memory",
      "@state:assertEqual"
    ],
    [
      "test_activation_events_byte_cap_is_load_bearing_in_memory",
      "@state:assertRaisesRegex"
    ],
    [
      "test_activation_events_byte_cap_is_load_bearing_in_memory",
      "_guard_activation_artifact_read_budget"
    ],
    [
      "test_activation_events_byte_cap_is_load_bearing_in_memory",
      "_new_repo"
    ],
    [
      "test_activation_events_byte_cap_is_load_bearing_in_memory",
      "_open_legacy_run"
    ],
    [
      "test_activation_events_byte_cap_is_load_bearing_in_memory",
      "_write_bound_chain_state"
    ],
    [
      "test_activation_events_byte_cap_is_load_bearing_in_memory",
      "api_environment"
    ],
    [
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "@state:assertEqual"
    ],
    [
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "@state:assertFalse"
    ],
    [
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "@state:assertRaisesRegex"
    ],
    [
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "@state:subTest"
    ],
    [
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "_activation_markers"
    ],
    [
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "_activation_outbox_case"
    ],
    [
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "_chain_drain_authorizer"
    ],
    [
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "_invoke_raw_lifecycle"
    ],
    [
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "_run_file_bytes"
    ],
    [
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "api_environment"
    ],
    [
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "run_dir"
    ],
    [
      "test_activation_outbox_lifecycle_guard_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_activation_outbox_lifecycle_guard_is_load_bearing",
      "@state:assertNotEqual"
    ],
    [
      "test_activation_outbox_lifecycle_guard_is_load_bearing",
      "@state:subTest"
    ],
    [
      "test_activation_outbox_lifecycle_guard_is_load_bearing",
      "_activation_outbox_case"
    ],
    [
      "test_activation_outbox_lifecycle_guard_is_load_bearing",
      "_invoke_raw_lifecycle"
    ],
    [
      "test_activation_outbox_lifecycle_guard_is_load_bearing",
      "_run_file_bytes"
    ],
    [
      "test_activation_outbox_lifecycle_guard_is_load_bearing",
      "api_environment"
    ],
    [
      "test_activation_outbox_lifecycle_guard_is_load_bearing",
      "run_dir"
    ],
    [
      "test_activation_outbox_missing_events_or_tampered_state_refuses_first_use",
      "@state:assertEqual"
    ],
    [
      "test_activation_outbox_missing_events_or_tampered_state_refuses_first_use",
      "@state:assertRaisesRegex"
    ],
    [
      "test_activation_outbox_missing_events_or_tampered_state_refuses_first_use",
      "@state:subTest"
    ],
    [
      "test_activation_outbox_missing_events_or_tampered_state_refuses_first_use",
      "_activation_outbox_case"
    ],
    [
      "test_activation_outbox_missing_events_or_tampered_state_refuses_first_use",
      "_compete_with_activation_outbox"
    ],
    [
      "test_activation_outbox_missing_events_or_tampered_state_refuses_first_use",
      "_run_file_bytes"
    ],
    [
      "test_activation_outbox_missing_events_or_tampered_state_refuses_first_use",
      "api_environment"
    ],
    [
      "test_activation_outbox_missing_events_or_tampered_state_refuses_first_use",
      "run_dir"
    ],
    [
      "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "@state:assertEqual"
    ],
    [
      "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "@state:assertFalse"
    ],
    [
      "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "@state:assertRaisesRegex"
    ],
    [
      "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "_activation_markers"
    ],
    [
      "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "_activation_outbox_case"
    ],
    [
      "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "_chain_drain_authorizer"
    ],
    [
      "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "_compete_with_activation_outbox"
    ],
    [
      "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "_run_file_bytes"
    ],
    [
      "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "api_environment"
    ],
    [
      "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "run_dir"
    ],
    [
      "test_activation_replay_passes_scan_only_state_and_event_caps",
      "@state:assertEqual"
    ],
    [
      "test_activation_replay_passes_scan_only_state_and_event_caps",
      "@state:assertTrue"
    ],
    [
      "test_activation_replay_passes_scan_only_state_and_event_caps",
      "_new_repo"
    ],
    [
      "test_activation_replay_passes_scan_only_state_and_event_caps",
      "_open_legacy_run"
    ],
    [
      "test_activation_replay_passes_scan_only_state_and_event_caps",
      "_write_bound_chain_state"
    ],
    [
      "test_activation_replay_passes_scan_only_state_and_event_caps",
      "api_environment"
    ],
    [
      "test_activation_replay_passes_scan_only_state_and_event_caps",
      "start_task"
    ],
    [
      "test_activation_scan_bound_chain_created_between_scans_refuses",
      "@state:assertEqual"
    ],
    [
      "test_activation_scan_bound_chain_created_between_scans_refuses",
      "@state:assertRaisesRegex"
    ],
    [
      "test_activation_scan_bound_chain_created_between_scans_refuses",
      "@state:assertTrue"
    ],
    [
      "test_activation_scan_bound_chain_created_between_scans_refuses",
      "@state:subTest"
    ],
    [
      "test_activation_scan_bound_chain_created_between_scans_refuses",
      "_new_repo"
    ],
    [
      "test_activation_scan_bound_chain_created_between_scans_refuses",
      "_open_legacy_run"
    ],
    [
      "test_activation_scan_bound_chain_created_between_scans_refuses",
      "api_environment"
    ],
    [
      "test_activation_scan_bound_chain_created_between_scans_refuses",
      "run_dir"
    ],
    [
      "test_activation_scan_bound_chain_created_between_scans_refuses",
      "start_task"
    ],
    [
      "test_activation_scan_converts_bounded_path_memory_errors",
      "@state:assertEqual"
    ],
    [
      "test_activation_scan_converts_bounded_path_memory_errors",
      "@state:assertIsNone"
    ],
    [
      "test_activation_scan_converts_bounded_path_memory_errors",
      "@state:assertRaises"
    ],
    [
      "test_activation_scan_converts_bounded_path_memory_errors",
      "_new_repo"
    ],
    [
      "test_activation_scan_converts_bounded_path_memory_errors",
      "_open_legacy_run"
    ],
    [
      "test_activation_scan_converts_bounded_path_memory_errors",
      "_write_bound_chain_state"
    ],
    [
      "test_activation_scan_converts_bounded_path_memory_errors",
      "api_environment"
    ],
    [
      "test_activation_scan_converts_bounded_path_memory_errors",
      "run_dir"
    ],
    [
      "test_activation_scan_converts_bounded_path_memory_errors",
      "start_task"
    ],
    [
      "test_activation_scan_ignores_unrelated_chain_created_between_scans",
      "@state:assertEqual"
    ],
    [
      "test_activation_scan_ignores_unrelated_chain_created_between_scans",
      "@state:assertTrue"
    ],
    [
      "test_activation_scan_ignores_unrelated_chain_created_between_scans",
      "_new_repo"
    ],
    [
      "test_activation_scan_ignores_unrelated_chain_created_between_scans",
      "_open_legacy_run"
    ],
    [
      "test_activation_scan_ignores_unrelated_chain_created_between_scans",
      "api_environment"
    ],
    [
      "test_activation_scan_ignores_unrelated_chain_created_between_scans",
      "start_task"
    ],
    [
      "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "@state:assertEqual"
    ],
    [
      "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "@state:assertFalse"
    ],
    [
      "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "@state:assertRaises"
    ],
    [
      "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "_guard_activation_artifact_read_budget"
    ],
    [
      "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "_new_repo"
    ],
    [
      "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "_open_legacy_run"
    ],
    [
      "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "_write_bound_chain_state"
    ],
    [
      "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "api_environment"
    ],
    [
      "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "run_dir"
    ],
    [
      "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "start_task"
    ],
    [
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "@state:assertEqual"
    ],
    [
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "@state:assertFalse"
    ],
    [
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "@state:assertRaises"
    ],
    [
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "_guard_activation_artifact_read_budget"
    ],
    [
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "_new_repo"
    ],
    [
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "_open_legacy_run"
    ],
    [
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "_pad_valid_json_over_cap"
    ],
    [
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "_write_bound_chain_state"
    ],
    [
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "api_environment"
    ],
    [
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "run_dir"
    ],
    [
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "start_task"
    ],
    [
      "test_activation_scan_skips_external_sibling_chain_and_run_lock",
      "@state:assertEqual"
    ],
    [
      "test_activation_scan_skips_external_sibling_chain_and_run_lock",
      "@state:assertNotIn"
    ],
    [
      "test_activation_scan_skips_external_sibling_chain_and_run_lock",
      "@state:assertTrue"
    ],
    [
      "test_activation_scan_skips_external_sibling_chain_and_run_lock",
      "@state:repo"
    ],
    [
      "test_activation_scan_skips_external_sibling_chain_and_run_lock",
      "@state:temporary"
    ],
    [
      "test_activation_scan_skips_external_sibling_chain_and_run_lock",
      "_legacy_receipted_chain_case"
    ],
    [
      "test_activation_scan_skips_external_sibling_chain_and_run_lock",
      "_open_legacy_run"
    ],
    [
      "test_activation_scan_skips_external_sibling_chain_and_run_lock",
      "api_environment"
    ],
    [
      "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "@state:assertEqual"
    ],
    [
      "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "@state:assertTrue"
    ],
    [
      "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "@state:subTest"
    ],
    [
      "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "_invoke_raw_lifecycle"
    ],
    [
      "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "_new_repo"
    ],
    [
      "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "_open_legacy_run"
    ],
    [
      "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "_plant_unreplayable_unrelated_chain"
    ],
    [
      "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "api_environment"
    ],
    [
      "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "run_dir"
    ],
    [
      "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "start_task"
    ],
    [
      "test_activation_scan_unrelated_tolerance_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_activation_scan_unrelated_tolerance_is_load_bearing",
      "@state:assertRaisesRegex"
    ],
    [
      "test_activation_scan_unrelated_tolerance_is_load_bearing",
      "_new_repo"
    ],
    [
      "test_activation_scan_unrelated_tolerance_is_load_bearing",
      "_open_legacy_run"
    ],
    [
      "test_activation_scan_unrelated_tolerance_is_load_bearing",
      "_plant_unreplayable_unrelated_chain"
    ],
    [
      "test_activation_scan_unrelated_tolerance_is_load_bearing",
      "api_environment"
    ],
    [
      "test_activation_scan_unrelated_tolerance_is_load_bearing",
      "run_dir"
    ],
    [
      "test_activation_scan_unrelated_tolerance_is_load_bearing",
      "start_task"
    ],
    [
      "test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
      "@state:assertEqual"
    ],
    [
      "test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
      "@state:assertTrue"
    ],
    [
      "test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
      "_guard_activation_artifact_read_budget"
    ],
    [
      "test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
      "_new_repo"
    ],
    [
      "test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
      "_open_legacy_run"
    ],
    [
      "test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
      "_pad_valid_json_over_cap"
    ],
    [
      "test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
      "_write_bound_chain_state"
    ],
    [
      "test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
      "api_environment"
    ],
    [
      "test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
      "start_task"
    ],
    [
      "test_activation_state_byte_cap_is_load_bearing_in_memory",
      "@state:assertEqual"
    ],
    [
      "test_activation_state_byte_cap_is_load_bearing_in_memory",
      "@state:assertRaisesRegex"
    ],
    [
      "test_activation_state_byte_cap_is_load_bearing_in_memory",
      "_guard_activation_artifact_read_budget"
    ],
    [
      "test_activation_state_byte_cap_is_load_bearing_in_memory",
      "_new_repo"
    ],
    [
      "test_activation_state_byte_cap_is_load_bearing_in_memory",
      "_open_legacy_run"
    ],
    [
      "test_activation_state_byte_cap_is_load_bearing_in_memory",
      "_pad_valid_json_over_cap"
    ],
    [
      "test_activation_state_byte_cap_is_load_bearing_in_memory",
      "_write_bound_chain_state"
    ],
    [
      "test_activation_state_byte_cap_is_load_bearing_in_memory",
      "api_environment"
    ],
    [
      "test_batch_controls_are_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_batch_controls_are_load_bearing",
      "@state:assertFalse"
    ],
    [
      "test_batch_controls_are_load_bearing",
      "@state:assertRaisesRegex"
    ],
    [
      "test_batch_controls_are_load_bearing",
      "@state:assertTrue"
    ],
    [
      "test_batch_controls_are_load_bearing",
      "@state:repo"
    ],
    [
      "test_batch_controls_are_load_bearing",
      "_leave_complete_intent"
    ],
    [
      "test_batch_controls_are_load_bearing",
      "_new_repo"
    ],
    [
      "test_batch_controls_are_load_bearing",
      "api_environment"
    ],
    [
      "test_batch_controls_are_load_bearing",
      "open_run"
    ],
    [
      "test_batch_controls_are_load_bearing",
      "run_dir"
    ],
    [
      "test_batch_controls_are_load_bearing",
      "start_task"
    ],
    [
      "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "@state:assertEqual"
    ],
    [
      "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "@state:assertFalse"
    ],
    [
      "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "@state:assertRaises"
    ],
    [
      "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "@state:assertTrue"
    ],
    [
      "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "@state:subTest"
    ],
    [
      "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "_new_repo"
    ],
    [
      "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "api_environment"
    ],
    [
      "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "open_run"
    ],
    [
      "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "run_dir"
    ],
    [
      "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "start_task"
    ],
    [
      "test_batch_gap_repair_controls_are_independently_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_batch_gap_repair_controls_are_independently_load_bearing",
      "@state:assertRaisesRegex"
    ],
    [
      "test_batch_gap_repair_controls_are_independently_load_bearing",
      "@state:subTest"
    ],
    [
      "test_batch_gap_repair_controls_are_independently_load_bearing",
      "_leave_two_record_receipt_gap"
    ],
    [
      "test_batch_gap_repair_controls_are_independently_load_bearing",
      "_new_repo"
    ],
    [
      "test_batch_gap_repair_controls_are_independently_load_bearing",
      "_seed_gh17_wedge"
    ],
    [
      "test_batch_gap_repair_controls_are_independently_load_bearing",
      "api_environment"
    ],
    [
      "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "@state:assertEqual"
    ],
    [
      "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "@state:assertRaisesRegex"
    ],
    [
      "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "_leave_complete_intent"
    ],
    [
      "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "_leave_scope_receipt_gap"
    ],
    [
      "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "_new_repo"
    ],
    [
      "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "_write_landed_intent_for_last_receipt"
    ],
    [
      "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "api_environment"
    ],
    [
      "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "open_run"
    ],
    [
      "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "run_dir"
    ],
    [
      "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "start_task"
    ],
    [
      "test_batch_gap_repair_refuses_unproved_bytes_and_intent",
      "@state:assertEqual"
    ],
    [
      "test_batch_gap_repair_refuses_unproved_bytes_and_intent",
      "@state:assertRaisesRegex"
    ],
    [
      "test_batch_gap_repair_refuses_unproved_bytes_and_intent",
      "@state:subTest"
    ],
    [
      "test_batch_gap_repair_refuses_unproved_bytes_and_intent",
      "_leave_scope_receipt_gap"
    ],
    [
      "test_batch_gap_repair_refuses_unproved_bytes_and_intent",
      "_new_repo"
    ],
    [
      "test_batch_gap_repair_refuses_unproved_bytes_and_intent",
      "api_environment"
    ],
    [
      "test_batch_lock_create_open_substitution_refuses",
      "_assert_first_batch_artifact_substitution_refuses"
    ],
    [
      "test_batch_recover_repairs_one_n_record_gap",
      "@state:assertEqual"
    ],
    [
      "test_batch_recover_repairs_one_n_record_gap",
      "@state:assertFalse"
    ],
    [
      "test_batch_recover_repairs_one_n_record_gap",
      "@state:assertTrue"
    ],
    [
      "test_batch_recover_repairs_one_n_record_gap",
      "@state:repo"
    ],
    [
      "test_batch_recover_repairs_one_n_record_gap",
      "_leave_two_record_receipt_gap"
    ],
    [
      "test_batch_recover_repairs_one_n_record_gap",
      "api_environment"
    ],
    [
      "test_batch_recover_repairs_proven_readmission_gap_and_stale_intent",
      "@state:assertEqual"
    ],
    [
      "test_batch_recover_repairs_proven_readmission_gap_and_stale_intent",
      "@state:assertFalse"
    ],
    [
      "test_batch_recover_repairs_proven_readmission_gap_and_stale_intent",
      "@state:assertTrue"
    ],
    [
      "test_batch_recover_repairs_proven_readmission_gap_and_stale_intent",
      "@state:repo"
    ],
    [
      "test_batch_recover_repairs_proven_readmission_gap_and_stale_intent",
      "_leave_scope_receipt_gap"
    ],
    [
      "test_batch_recover_repairs_proven_readmission_gap_and_stale_intent",
      "api_environment"
    ],
    [
      "test_builder_request_schema_and_digest_are_exact",
      "@state:assertEqual"
    ],
    [
      "test_builder_request_schema_and_digest_are_exact",
      "@state:repo"
    ],
    [
      "test_builder_validation_controls_are_detected_in_memory",
      "@state:assertEqual"
    ],
    [
      "test_builder_validation_controls_are_detected_in_memory",
      "@state:assertRaisesRegex"
    ],
    [
      "test_builder_validation_controls_are_detected_in_memory",
      "_new_repo"
    ],
    [
      "test_builder_validation_controls_are_detected_in_memory",
      "api_environment"
    ],
    [
      "test_builder_validation_controls_are_detected_in_memory",
      "open_run"
    ],
    [
      "test_builder_validation_controls_are_detected_in_memory",
      "start_task"
    ],
    [
      "test_chain_drain_authorization_controls_are_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_chain_drain_authorization_controls_are_load_bearing",
      "@state:assertFalse"
    ],
    [
      "test_chain_drain_authorization_controls_are_load_bearing",
      "@state:assertRaisesRegex"
    ],
    [
      "test_chain_drain_authorization_controls_are_load_bearing",
      "@state:subTest"
    ],
    [
      "test_chain_drain_authorization_controls_are_load_bearing",
      "_chain_drain_authorizer"
    ],
    [
      "test_chain_drain_authorization_controls_are_load_bearing",
      "_chain_drain_case"
    ],
    [
      "test_chain_drain_authorization_controls_are_load_bearing",
      "api_environment"
    ],
    [
      "test_chain_drain_authorization_controls_are_load_bearing",
      "run_dir"
    ],
    [
      "test_chain_drain_authorization_exact_field_bindings",
      "@state:assertEqual"
    ],
    [
      "test_chain_drain_authorization_exact_field_bindings",
      "@state:assertFalse"
    ],
    [
      "test_chain_drain_authorization_exact_field_bindings",
      "@state:assertRaises"
    ],
    [
      "test_chain_drain_authorization_exact_field_bindings",
      "@state:assertRaisesRegex"
    ],
    [
      "test_chain_drain_authorization_exact_field_bindings",
      "@state:subTest"
    ],
    [
      "test_chain_drain_authorization_exact_field_bindings",
      "_chain_drain_authorizer"
    ],
    [
      "test_chain_drain_authorization_exact_field_bindings",
      "_chain_drain_case"
    ],
    [
      "test_chain_drain_authorization_exact_field_bindings",
      "api_environment"
    ],
    [
      "test_chain_drain_authorization_exact_field_bindings",
      "run_dir"
    ],
    [
      "test_chain_drain_authorized_pending_and_lost_response_retry",
      "@state:assertEqual"
    ],
    [
      "test_chain_drain_authorized_pending_and_lost_response_retry",
      "@state:assertFalse"
    ],
    [
      "test_chain_drain_authorized_pending_and_lost_response_retry",
      "@state:assertRaises"
    ],
    [
      "test_chain_drain_authorized_pending_and_lost_response_retry",
      "@state:assertTrue"
    ],
    [
      "test_chain_drain_authorized_pending_and_lost_response_retry",
      "@state:subTest"
    ],
    [
      "test_chain_drain_authorized_pending_and_lost_response_retry",
      "_chain_drain_authorizer"
    ],
    [
      "test_chain_drain_authorized_pending_and_lost_response_retry",
      "_chain_drain_case"
    ],
    [
      "test_chain_drain_authorized_pending_and_lost_response_retry",
      "api_environment"
    ],
    [
      "test_chain_drain_authorized_pending_and_lost_response_retry",
      "run_dir"
    ],
    [
      "test_chain_drain_raw_records_without_capability_refuses",
      "@state:assertEqual"
    ],
    [
      "test_chain_drain_raw_records_without_capability_refuses",
      "@state:assertFalse"
    ],
    [
      "test_chain_drain_raw_records_without_capability_refuses",
      "@state:assertRaisesRegex"
    ],
    [
      "test_chain_drain_raw_records_without_capability_refuses",
      "_new_repo"
    ],
    [
      "test_chain_drain_raw_records_without_capability_refuses",
      "api_environment"
    ],
    [
      "test_chain_drain_raw_records_without_capability_refuses",
      "open_run"
    ],
    [
      "test_chain_drain_raw_records_without_capability_refuses",
      "run_dir"
    ],
    [
      "test_chain_drain_valid_authorizer_new_and_repeated_paths",
      "@state:assertEqual"
    ],
    [
      "test_chain_drain_valid_authorizer_new_and_repeated_paths",
      "@state:assertFalse"
    ],
    [
      "test_chain_drain_valid_authorizer_new_and_repeated_paths",
      "@state:assertRaisesRegex"
    ],
    [
      "test_chain_drain_valid_authorizer_new_and_repeated_paths",
      "@state:assertTrue"
    ],
    [
      "test_chain_drain_valid_authorizer_new_and_repeated_paths",
      "_chain_drain_authorizer"
    ],
    [
      "test_chain_drain_valid_authorizer_new_and_repeated_paths",
      "_chain_drain_case"
    ],
    [
      "test_chain_drain_valid_authorizer_new_and_repeated_paths",
      "api_environment"
    ],
    [
      "test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet",
      "@state:assertEqual"
    ],
    [
      "test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet",
      "@state:assertFalse"
    ],
    [
      "test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet",
      "@state:assertIsInstance"
    ],
    [
      "test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet",
      "@state:head"
    ],
    [
      "test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet",
      "@state:repo"
    ],
    [
      "test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet",
      "@state:temporary"
    ],
    [
      "test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet",
      "command"
    ],
    [
      "test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet",
      "run_dir"
    ],
    [
      "test_cli_singleton_and_idempotency_key_diagnostics",
      "@state:assertEqual"
    ],
    [
      "test_cli_singleton_and_idempotency_key_diagnostics",
      "@state:repo"
    ],
    [
      "test_cli_singleton_and_idempotency_key_diagnostics",
      "command"
    ],
    [
      "test_commit_sibling_carried_binding_authentication_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_commit_sibling_carried_binding_authentication_is_load_bearing",
      "@state:assertRaises"
    ],
    [
      "test_commit_sibling_carried_binding_authentication_is_load_bearing",
      "@state:assertTrue"
    ],
    [
      "test_commit_sibling_carried_binding_authentication_is_load_bearing",
      "@state:repo"
    ],
    [
      "test_commit_sibling_carried_binding_authentication_is_load_bearing",
      "_legacy_receipted_chain_case"
    ],
    [
      "test_commit_sibling_carried_binding_authentication_is_load_bearing",
      "_rewrite_commit_events"
    ],
    [
      "test_commit_sibling_carried_binding_authentication_is_load_bearing",
      "api_environment"
    ],
    [
      "test_commit_sibling_carried_binding_authentication_is_load_bearing",
      "run_dir"
    ],
    [
      "test_commit_sibling_receipt_request_authentication_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_commit_sibling_receipt_request_authentication_is_load_bearing",
      "@state:assertRaises"
    ],
    [
      "test_commit_sibling_receipt_request_authentication_is_load_bearing",
      "@state:repo"
    ],
    [
      "test_commit_sibling_receipt_request_authentication_is_load_bearing",
      "_legacy_receipted_chain_case"
    ],
    [
      "test_commit_sibling_receipt_request_authentication_is_load_bearing",
      "_rewrite_commit_events"
    ],
    [
      "test_commit_sibling_receipt_request_authentication_is_load_bearing",
      "api_environment"
    ],
    [
      "test_commit_sibling_receipt_request_authentication_is_load_bearing",
      "run_dir"
    ],
    [
      "test_commit_sibling_receipt_snapshot_recheck_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_commit_sibling_receipt_snapshot_recheck_is_load_bearing",
      "@state:assertRaises"
    ],
    [
      "test_commit_sibling_receipt_snapshot_recheck_is_load_bearing",
      "@state:repo"
    ],
    [
      "test_commit_sibling_receipt_snapshot_recheck_is_load_bearing",
      "_legacy_receipted_chain_case"
    ],
    [
      "test_commit_sibling_receipt_snapshot_recheck_is_load_bearing",
      "api_environment"
    ],
    [
      "test_commit_sibling_receipt_snapshot_recheck_is_load_bearing",
      "run_dir"
    ],
    [
      "test_concurrent_admission_and_scope_change_remain_disjoint",
      "@state:assertEqual"
    ],
    [
      "test_concurrent_admission_and_scope_change_remain_disjoint",
      "@state:assertIn"
    ],
    [
      "test_concurrent_admission_and_scope_change_remain_disjoint",
      "@state:repo"
    ],
    [
      "test_concurrent_admission_and_scope_change_remain_disjoint",
      "@state:temporary"
    ],
    [
      "test_concurrent_admission_and_scope_change_remain_disjoint",
      "api_environment"
    ],
    [
      "test_concurrent_admission_and_scope_change_remain_disjoint",
      "open_run"
    ],
    [
      "test_concurrent_admission_and_scope_change_remain_disjoint",
      "run_dir"
    ],
    [
      "test_concurrent_legacy_activation_never_cross_acquires_run_locks",
      "@state:assertEqual"
    ],
    [
      "test_concurrent_legacy_activation_never_cross_acquires_run_locks",
      "@state:assertFalse"
    ],
    [
      "test_concurrent_legacy_activation_never_cross_acquires_run_locks",
      "@state:assertTrue"
    ],
    [
      "test_concurrent_legacy_activation_never_cross_acquires_run_locks",
      "@state:repo"
    ],
    [
      "test_concurrent_legacy_activation_never_cross_acquires_run_locks",
      "@state:temporary"
    ],
    [
      "test_concurrent_legacy_activation_never_cross_acquires_run_locks",
      "_legacy_receipted_chain_case"
    ],
    [
      "test_concurrent_legacy_activation_never_cross_acquires_run_locks",
      "api_environment"
    ],
    [
      "test_each_terminal_chain_control_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_each_terminal_chain_control_is_load_bearing",
      "@state:assertRaisesRegex"
    ],
    [
      "test_each_terminal_chain_control_is_load_bearing",
      "@state:temporary"
    ],
    [
      "test_each_terminal_chain_control_is_load_bearing",
      "_append_test_landing"
    ],
    [
      "test_each_terminal_chain_control_is_load_bearing",
      "_terminal_control_repo"
    ],
    [
      "test_each_terminal_chain_control_is_load_bearing",
      "_write_bound_chain_state"
    ],
    [
      "test_each_terminal_chain_control_is_load_bearing",
      "api_environment"
    ],
    [
      "test_exact_prefix_and_torn_receipt_recovery",
      "@state:assertEqual"
    ],
    [
      "test_exact_prefix_and_torn_receipt_recovery",
      "@state:assertFalse"
    ],
    [
      "test_exact_prefix_and_torn_receipt_recovery",
      "@state:assertTrue"
    ],
    [
      "test_exact_prefix_and_torn_receipt_recovery",
      "_leave_complete_intent"
    ],
    [
      "test_exact_prefix_and_torn_receipt_recovery",
      "_new_repo"
    ],
    [
      "test_exact_prefix_and_torn_receipt_recovery",
      "api_environment"
    ],
    [
      "test_first_receipt_ledger_create_open_substitution_refuses",
      "_assert_first_batch_artifact_substitution_refuses"
    ],
    [
      "test_first_receipt_ledger_post_create_substitution_refuses",
      "@state:assertEqual"
    ],
    [
      "test_first_receipt_ledger_post_create_substitution_refuses",
      "@state:assertFalse"
    ],
    [
      "test_first_receipt_ledger_post_create_substitution_refuses",
      "@state:assertNotEqual"
    ],
    [
      "test_first_receipt_ledger_post_create_substitution_refuses",
      "@state:assertRaisesRegex"
    ],
    [
      "test_first_receipt_ledger_post_create_substitution_refuses",
      "_new_repo"
    ],
    [
      "test_first_receipt_ledger_post_create_substitution_refuses",
      "_open_legacy_run"
    ],
    [
      "test_first_receipt_ledger_post_create_substitution_refuses",
      "api_environment"
    ],
    [
      "test_first_receipt_ledger_post_create_substitution_refuses",
      "run_dir"
    ],
    [
      "test_first_receipt_ledger_post_create_substitution_refuses",
      "start_task"
    ],
    [
      "test_foreign_request_intent_stage_is_not_deleted",
      "@state:assertEqual"
    ],
    [
      "test_foreign_request_intent_stage_is_not_deleted",
      "@state:assertFalse"
    ],
    [
      "test_foreign_request_intent_stage_is_not_deleted",
      "@state:assertRaisesRegex"
    ],
    [
      "test_foreign_request_intent_stage_is_not_deleted",
      "_new_repo"
    ],
    [
      "test_foreign_request_intent_stage_is_not_deleted",
      "api_environment"
    ],
    [
      "test_foreign_request_intent_stage_is_not_deleted",
      "open_run"
    ],
    [
      "test_foreign_request_intent_stage_is_not_deleted",
      "run_dir"
    ],
    [
      "test_foreign_request_intent_stage_is_not_deleted",
      "start_task"
    ],
    [
      "test_fr019_failure_phase_order_preserves_earlier_bytes",
      "@state:assertEqual"
    ],
    [
      "test_fr019_failure_phase_order_preserves_earlier_bytes",
      "@state:assertFalse"
    ],
    [
      "test_fr019_failure_phase_order_preserves_earlier_bytes",
      "@state:assertRaisesRegex"
    ],
    [
      "test_fr019_failure_phase_order_preserves_earlier_bytes",
      "_new_repo"
    ],
    [
      "test_fr019_failure_phase_order_preserves_earlier_bytes",
      "api_environment"
    ],
    [
      "test_fr019_failure_phase_order_preserves_earlier_bytes",
      "open_run"
    ],
    [
      "test_fr019_failure_phase_order_preserves_earlier_bytes",
      "run_dir"
    ],
    [
      "test_fr019_failure_phase_order_preserves_earlier_bytes",
      "start_task"
    ],
    [
      "test_gh17_shape_recovers_without_reapplication",
      "@state:assertEqual"
    ],
    [
      "test_gh17_shape_recovers_without_reapplication",
      "@state:assertIsInstance"
    ],
    [
      "test_gh17_shape_recovers_without_reapplication",
      "@state:assertRaisesRegex"
    ],
    [
      "test_gh17_shape_recovers_without_reapplication",
      "@state:assertTrue"
    ],
    [
      "test_gh17_shape_recovers_without_reapplication",
      "@state:repo"
    ],
    [
      "test_gh17_shape_recovers_without_reapplication",
      "_assert_gh17_recovered"
    ],
    [
      "test_gh17_shape_recovers_without_reapplication",
      "_run_file_bytes"
    ],
    [
      "test_gh17_shape_recovers_without_reapplication",
      "_seed_gh17_wedge"
    ],
    [
      "test_gh17_shape_recovers_without_reapplication",
      "api_environment"
    ],
    [
      "test_gh17_shape_refuses_explicit_foreign_gap_run_id",
      "@state:assertEqual"
    ],
    [
      "test_gh17_shape_refuses_explicit_foreign_gap_run_id",
      "@state:assertNotIn"
    ],
    [
      "test_gh17_shape_refuses_explicit_foreign_gap_run_id",
      "@state:assertRaisesRegex"
    ],
    [
      "test_gh17_shape_refuses_explicit_foreign_gap_run_id",
      "@state:repo"
    ],
    [
      "test_gh17_shape_refuses_explicit_foreign_gap_run_id",
      "_run_file_bytes"
    ],
    [
      "test_gh17_shape_refuses_explicit_foreign_gap_run_id",
      "_seed_gh17_wedge"
    ],
    [
      "test_gh17_shape_refuses_explicit_foreign_gap_run_id",
      "api_environment"
    ],
    [
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "@state:assertEqual"
    ],
    [
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "@state:assertFalse"
    ],
    [
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "@state:assertRaisesRegex"
    ],
    [
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "@state:assertTrue"
    ],
    [
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "@state:subTest"
    ],
    [
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "_new_repo"
    ],
    [
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "_open_legacy_run"
    ],
    [
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "_run_file_bytes"
    ],
    [
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "api_environment"
    ],
    [
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "run_dir"
    ],
    [
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "start_task"
    ],
    [
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "@state:assertEqual"
    ],
    [
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "@state:assertRaisesRegex"
    ],
    [
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "@state:assertTrue"
    ],
    [
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "@state:subTest"
    ],
    [
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "@state:temporary"
    ],
    [
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "_leave_complete_intent"
    ],
    [
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "_new_repo"
    ],
    [
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "api_environment"
    ],
    [
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "open_run"
    ],
    [
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "run_dir"
    ],
    [
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "start_task"
    ],
    [
      "test_id_only_legacy_opening_activates_with_matching_marker_run_id",
      "@state:assertEqual"
    ],
    [
      "test_id_only_legacy_opening_activates_with_matching_marker_run_id",
      "@state:assertFalse"
    ],
    [
      "test_id_only_legacy_opening_activates_with_matching_marker_run_id",
      "@state:assertNotIn"
    ],
    [
      "test_id_only_legacy_opening_activates_with_matching_marker_run_id",
      "@state:assertTrue"
    ],
    [
      "test_id_only_legacy_opening_activates_with_matching_marker_run_id",
      "@state:repo"
    ],
    [
      "test_id_only_legacy_opening_activates_with_matching_marker_run_id",
      "api_environment"
    ],
    [
      "test_id_only_legacy_opening_activates_with_matching_marker_run_id",
      "run_dir"
    ],
    [
      "test_id_only_legacy_opening_activates_with_matching_marker_run_id",
      "start_task"
    ],
    [
      "test_ingest_requires_registered_proof_complete_authority",
      "@state:assertEqual"
    ],
    [
      "test_ingest_requires_registered_proof_complete_authority",
      "@state:assertFalse"
    ],
    [
      "test_ingest_requires_registered_proof_complete_authority",
      "@state:assertRaisesRegex"
    ],
    [
      "test_ingest_requires_registered_proof_complete_authority",
      "@state:head"
    ],
    [
      "test_ingest_requires_registered_proof_complete_authority",
      "@state:repo"
    ],
    [
      "test_ingest_requires_registered_proof_complete_authority",
      "@state:subTest"
    ],
    [
      "test_ingest_requires_registered_proof_complete_authority",
      "api_environment"
    ],
    [
      "test_ingest_requires_registered_proof_complete_authority",
      "open_run"
    ],
    [
      "test_ingest_requires_registered_proof_complete_authority",
      "run_dir"
    ],
    [
      "test_ingest_requires_registered_proof_complete_authority",
      "start_task"
    ],
    [
      "test_intent_quarantine_preserves_a_second_canonical_swap",
      "@state:assertEqual"
    ],
    [
      "test_intent_quarantine_preserves_a_second_canonical_swap",
      "@state:assertFalse"
    ],
    [
      "test_intent_quarantine_preserves_a_second_canonical_swap",
      "@state:assertRaisesRegex"
    ],
    [
      "test_intent_quarantine_preserves_a_second_canonical_swap",
      "_new_repo"
    ],
    [
      "test_intent_quarantine_preserves_a_second_canonical_swap",
      "api_environment"
    ],
    [
      "test_intent_quarantine_preserves_a_second_canonical_swap",
      "open_run"
    ],
    [
      "test_intent_quarantine_preserves_a_second_canonical_swap",
      "run_dir"
    ],
    [
      "test_intent_quarantine_preserves_a_second_canonical_swap",
      "start_task"
    ],
    [
      "test_intent_source_name_substitution_never_survives_canonical",
      "@state:assertEqual"
    ],
    [
      "test_intent_source_name_substitution_never_survives_canonical",
      "@state:assertFalse"
    ],
    [
      "test_intent_source_name_substitution_never_survives_canonical",
      "@state:assertRaisesRegex"
    ],
    [
      "test_intent_source_name_substitution_never_survives_canonical",
      "_new_repo"
    ],
    [
      "test_intent_source_name_substitution_never_survives_canonical",
      "api_environment"
    ],
    [
      "test_intent_source_name_substitution_never_survives_canonical",
      "open_run"
    ],
    [
      "test_intent_source_name_substitution_never_survives_canonical",
      "run_dir"
    ],
    [
      "test_intent_source_name_substitution_never_survives_canonical",
      "start_task"
    ],
    [
      "test_intent_without_journal_and_reentrant_pending_read_refuse_exactly",
      "@state:assertEqual"
    ],
    [
      "test_intent_without_journal_and_reentrant_pending_read_refuse_exactly",
      "_leave_base_intent"
    ],
    [
      "test_intent_without_journal_and_reentrant_pending_read_refuse_exactly",
      "_new_repo"
    ],
    [
      "test_intent_without_journal_and_reentrant_pending_read_refuse_exactly",
      "api_environment"
    ],
    [
      "test_internal_typed_flag_cannot_bypass_activated_batch_builders",
      "@state:assertEqual"
    ],
    [
      "test_internal_typed_flag_cannot_bypass_activated_batch_builders",
      "@state:assertRaisesRegex"
    ],
    [
      "test_internal_typed_flag_cannot_bypass_activated_batch_builders",
      "_new_repo"
    ],
    [
      "test_internal_typed_flag_cannot_bypass_activated_batch_builders",
      "api_environment"
    ],
    [
      "test_internal_typed_flag_cannot_bypass_activated_batch_builders",
      "open_run"
    ],
    [
      "test_internal_typed_flag_cannot_bypass_activated_batch_builders",
      "run_dir"
    ],
    [
      "test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze",
      "@state:assertEqual"
    ],
    [
      "test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze",
      "@state:assertRaisesRegex"
    ],
    [
      "test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze",
      "@state:subTest"
    ],
    [
      "test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze",
      "_new_repo"
    ],
    [
      "test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze",
      "api_environment"
    ],
    [
      "test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze",
      "open_run"
    ],
    [
      "test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze",
      "run_dir"
    ],
    [
      "test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze",
      "start_task"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "@state:assertEqual"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "@state:assertFalse"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "@state:assertRaisesRegex"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "@state:assertTrue"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "@state:subTest"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "_activation_markers"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "_new_repo"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "_open_legacy_run"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "_run_file_bytes"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "api_environment"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "run_dir"
    ],
    [
      "test_legacy_activation_crash_matrix",
      "start_task"
    ],
    [
      "test_legacy_first_typed_use_atomically_activates",
      "@state:assertEqual"
    ],
    [
      "test_legacy_first_typed_use_atomically_activates",
      "@state:assertFalse"
    ],
    [
      "test_legacy_first_typed_use_atomically_activates",
      "@state:assertNotIn"
    ],
    [
      "test_legacy_first_typed_use_atomically_activates",
      "@state:assertRaisesRegex"
    ],
    [
      "test_legacy_first_typed_use_atomically_activates",
      "@state:assertTrue"
    ],
    [
      "test_legacy_first_typed_use_atomically_activates",
      "@state:repo"
    ],
    [
      "test_legacy_first_typed_use_atomically_activates",
      "_open_legacy_run"
    ],
    [
      "test_legacy_first_typed_use_atomically_activates",
      "_run_file_bytes"
    ],
    [
      "test_legacy_first_typed_use_atomically_activates",
      "api_environment"
    ],
    [
      "test_legacy_first_typed_use_atomically_activates",
      "run_dir"
    ],
    [
      "test_legacy_first_typed_use_atomically_activates",
      "start_task"
    ],
    [
      "test_legacy_open_broken_stderr_never_changes_durable_success",
      "@state:assertEqual"
    ],
    [
      "test_legacy_open_broken_stderr_never_changes_durable_success",
      "@state:assertTrue"
    ],
    [
      "test_legacy_open_broken_stderr_never_changes_durable_success",
      "@state:head"
    ],
    [
      "test_legacy_open_broken_stderr_never_changes_durable_success",
      "@state:repo"
    ],
    [
      "test_legacy_open_broken_stderr_never_changes_durable_success",
      "@state:temporary"
    ],
    [
      "test_legacy_open_broken_stderr_never_changes_durable_success",
      "api_environment"
    ],
    [
      "test_legacy_open_broken_stderr_never_changes_durable_success",
      "run_dir"
    ],
    [
      "test_legacy_open_without_stderr_never_falls_back_to_stdout",
      "@state:assertEqual"
    ],
    [
      "test_legacy_open_without_stderr_never_falls_back_to_stdout",
      "@state:assertTrue"
    ],
    [
      "test_legacy_open_without_stderr_never_falls_back_to_stdout",
      "@state:head"
    ],
    [
      "test_legacy_open_without_stderr_never_falls_back_to_stdout",
      "@state:repo"
    ],
    [
      "test_legacy_open_without_stderr_never_falls_back_to_stdout",
      "@state:temporary"
    ],
    [
      "test_legacy_open_without_stderr_never_falls_back_to_stdout",
      "api_environment"
    ],
    [
      "test_legacy_open_without_stderr_never_falls_back_to_stdout",
      "run_dir"
    ],
    [
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "@state:assertNotEqual"
    ],
    [
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "@state:assertRaisesRegex"
    ],
    [
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "@state:assertTrue"
    ],
    [
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "@state:subTest"
    ],
    [
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "_new_repo"
    ],
    [
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "_open_legacy_run"
    ],
    [
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "_run_file_bytes"
    ],
    [
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "_seed_gh17_wedge"
    ],
    [
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "api_environment"
    ],
    [
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "run_dir"
    ],
    [
      "test_midflight_intent_hardlink_fifo_and_foreign_uid_fences",
      "@state:assertEqual"
    ],
    [
      "test_midflight_intent_hardlink_fifo_and_foreign_uid_fences",
      "@state:assertRaisesRegex"
    ],
    [
      "test_midflight_intent_hardlink_fifo_and_foreign_uid_fences",
      "@state:subTest"
    ],
    [
      "test_midflight_intent_hardlink_fifo_and_foreign_uid_fences",
      "@state:temporary"
    ],
    [
      "test_midflight_intent_hardlink_fifo_and_foreign_uid_fences",
      "_leave_base_intent"
    ],
    [
      "test_midflight_intent_hardlink_fifo_and_foreign_uid_fences",
      "_new_repo"
    ],
    [
      "test_midflight_intent_hardlink_fifo_and_foreign_uid_fences",
      "api_environment"
    ],
    [
      "test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only",
      "@state:assertEqual"
    ],
    [
      "test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only",
      "@state:repo"
    ],
    [
      "test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only",
      "@state:temporary"
    ],
    [
      "test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only",
      "_leave_complete_intent"
    ],
    [
      "test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only",
      "api_environment"
    ],
    [
      "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "@state:assertEqual"
    ],
    [
      "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "@state:assertFalse"
    ],
    [
      "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "@state:assertRaisesRegex"
    ],
    [
      "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "@state:assertTrue"
    ],
    [
      "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "@state:subTest"
    ],
    [
      "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "_new_repo"
    ],
    [
      "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "_open_legacy_run"
    ],
    [
      "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "_run_file_bytes"
    ],
    [
      "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "api_environment"
    ],
    [
      "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "run_dir"
    ],
    [
      "test_pre_fix_golden_wedge_recovers_and_continues",
      "@state:assertEqual"
    ],
    [
      "test_pre_fix_golden_wedge_recovers_and_continues",
      "@state:assertFalse"
    ],
    [
      "test_pre_fix_golden_wedge_recovers_and_continues",
      "@state:assertGreater"
    ],
    [
      "test_pre_fix_golden_wedge_recovers_and_continues",
      "@state:assertTrue"
    ],
    [
      "test_pre_fix_golden_wedge_recovers_and_continues",
      "@state:fail"
    ],
    [
      "test_pre_fix_golden_wedge_recovers_and_continues",
      "_activation_markers"
    ],
    [
      "test_pre_fix_golden_wedge_recovers_and_continues",
      "_restore_prefix_wedge_fixture"
    ],
    [
      "test_pre_fix_golden_wedge_recovers_and_continues",
      "api_environment"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority",
      "@state:assertEqual"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority",
      "@state:assertFalse"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority",
      "@state:assertRaisesRegex"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority",
      "@state:assertTrue"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority",
      "@state:skipTest"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority",
      "@state:subTest"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority",
      "_new_repo"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority",
      "api_environment"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority",
      "open_run"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority",
      "run_dir"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority",
      "start_task"
    ],
    [
      "test_published_first_use_intent_blocks_outbox_before_publication",
      "@state:assertEqual"
    ],
    [
      "test_published_first_use_intent_blocks_outbox_before_publication",
      "@state:assertFalse"
    ],
    [
      "test_published_first_use_intent_blocks_outbox_before_publication",
      "@state:assertRaisesRegex"
    ],
    [
      "test_published_first_use_intent_blocks_outbox_before_publication",
      "@state:assertTrue"
    ],
    [
      "test_published_first_use_intent_blocks_outbox_before_publication",
      "@state:repo"
    ],
    [
      "test_published_first_use_intent_blocks_outbox_before_publication",
      "_open_legacy_run"
    ],
    [
      "test_published_first_use_intent_blocks_outbox_before_publication",
      "api_environment"
    ],
    [
      "test_published_first_use_intent_blocks_outbox_before_publication",
      "run_dir"
    ],
    [
      "test_published_first_use_intent_blocks_outbox_before_publication",
      "start_task"
    ],
    [
      "test_raw_lifecycle_lock_order_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_raw_lifecycle_lock_order_is_load_bearing",
      "@state:assertTrue"
    ],
    [
      "test_raw_lifecycle_lock_order_is_load_bearing",
      "@state:subTest"
    ],
    [
      "test_raw_lifecycle_lock_order_is_load_bearing",
      "_new_repo"
    ],
    [
      "test_raw_lifecycle_lock_order_is_load_bearing",
      "_open_legacy_run"
    ],
    [
      "test_raw_lifecycle_lock_order_is_load_bearing",
      "api_environment"
    ],
    [
      "test_raw_lifecycle_lock_order_is_load_bearing",
      "run_dir"
    ],
    [
      "test_raw_lifecycle_validation_precedes_batch_reservation",
      "@state:assertEqual"
    ],
    [
      "test_raw_lifecycle_validation_precedes_batch_reservation",
      "@state:assertFalse"
    ],
    [
      "test_raw_lifecycle_validation_precedes_batch_reservation",
      "@state:assertRaises"
    ],
    [
      "test_raw_lifecycle_validation_precedes_batch_reservation",
      "@state:subTest"
    ],
    [
      "test_raw_lifecycle_validation_precedes_batch_reservation",
      "_new_repo"
    ],
    [
      "test_raw_lifecycle_validation_precedes_batch_reservation",
      "_open_legacy_run"
    ],
    [
      "test_raw_lifecycle_validation_precedes_batch_reservation",
      "_run_file_bytes"
    ],
    [
      "test_raw_lifecycle_validation_precedes_batch_reservation",
      "api_environment"
    ],
    [
      "test_raw_lifecycle_validation_precedes_batch_reservation",
      "run_dir"
    ],
    [
      "test_raw_open_cannot_supply_writer_contract_before_any_mutation",
      "@state:assertEqual"
    ],
    [
      "test_raw_open_cannot_supply_writer_contract_before_any_mutation",
      "@state:assertFalse"
    ],
    [
      "test_raw_open_cannot_supply_writer_contract_before_any_mutation",
      "@state:assertRaises"
    ],
    [
      "test_raw_open_cannot_supply_writer_contract_before_any_mutation",
      "@state:subTest"
    ],
    [
      "test_raw_open_cannot_supply_writer_contract_before_any_mutation",
      "_new_repo"
    ],
    [
      "test_raw_open_cannot_supply_writer_contract_before_any_mutation",
      "api_environment"
    ],
    [
      "test_raw_open_cannot_supply_writer_contract_before_any_mutation",
      "run_dir"
    ],
    [
      "test_raw_open_writer_contract_refusal_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_raw_open_writer_contract_refusal_is_load_bearing",
      "@state:assertFalse"
    ],
    [
      "test_raw_open_writer_contract_refusal_is_load_bearing",
      "@state:assertRaises"
    ],
    [
      "test_raw_open_writer_contract_refusal_is_load_bearing",
      "@state:head"
    ],
    [
      "test_raw_open_writer_contract_refusal_is_load_bearing",
      "@state:repo"
    ],
    [
      "test_raw_open_writer_contract_refusal_is_load_bearing",
      "api_environment"
    ],
    [
      "test_raw_open_writer_contract_refusal_is_load_bearing",
      "run_dir"
    ],
    [
      "test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume",
      "@state:assertEqual"
    ],
    [
      "test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume",
      "@state:assertFalse"
    ],
    [
      "test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume",
      "@state:assertTrue"
    ],
    [
      "test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume",
      "@state:repo"
    ],
    [
      "test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume",
      "api_environment"
    ],
    [
      "test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume",
      "command"
    ],
    [
      "test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume",
      "open_run"
    ],
    [
      "test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume",
      "run_dir"
    ],
    [
      "test_recovery_activation_crash_matrix",
      "@state:assertEqual"
    ],
    [
      "test_recovery_activation_crash_matrix",
      "@state:assertRaisesRegex"
    ],
    [
      "test_recovery_activation_crash_matrix",
      "@state:assertTrue"
    ],
    [
      "test_recovery_activation_crash_matrix",
      "@state:subTest"
    ],
    [
      "test_recovery_activation_crash_matrix",
      "_assert_gh17_recovered"
    ],
    [
      "test_recovery_activation_crash_matrix",
      "_new_repo"
    ],
    [
      "test_recovery_activation_crash_matrix",
      "_run_file_bytes"
    ],
    [
      "test_recovery_activation_crash_matrix",
      "_seed_gh17_wedge"
    ],
    [
      "test_recovery_activation_crash_matrix",
      "api_environment"
    ],
    [
      "test_removed_batch_lock_after_activation_is_not_recreated",
      "@state:assertEqual"
    ],
    [
      "test_removed_batch_lock_after_activation_is_not_recreated",
      "@state:assertFalse"
    ],
    [
      "test_removed_batch_lock_after_activation_is_not_recreated",
      "@state:assertRaisesRegex"
    ],
    [
      "test_removed_batch_lock_after_activation_is_not_recreated",
      "@state:assertTrue"
    ],
    [
      "test_removed_batch_lock_after_activation_is_not_recreated",
      "@state:repo"
    ],
    [
      "test_removed_batch_lock_after_activation_is_not_recreated",
      "_open_legacy_run"
    ],
    [
      "test_removed_batch_lock_after_activation_is_not_recreated",
      "_run_file_bytes"
    ],
    [
      "test_removed_batch_lock_after_activation_is_not_recreated",
      "api_environment"
    ],
    [
      "test_removed_batch_lock_after_activation_is_not_recreated",
      "run_dir"
    ],
    [
      "test_removed_batch_lock_after_activation_is_not_recreated",
      "start_task"
    ],
    [
      "test_repair_receipt_is_rederived_on_every_load",
      "@state:assertEqual"
    ],
    [
      "test_repair_receipt_is_rederived_on_every_load",
      "@state:assertIs"
    ],
    [
      "test_repair_receipt_is_rederived_on_every_load",
      "@state:assertRaisesRegex"
    ],
    [
      "test_repair_receipt_is_rederived_on_every_load",
      "@state:subTest"
    ],
    [
      "test_repair_receipt_is_rederived_on_every_load",
      "_leave_scope_receipt_gap"
    ],
    [
      "test_repair_receipt_is_rederived_on_every_load",
      "_new_repo"
    ],
    [
      "test_repair_receipt_is_rederived_on_every_load",
      "api_environment"
    ],
    [
      "test_repair_receipt_n_record_members_rederived",
      "@state:assertEqual"
    ],
    [
      "test_repair_receipt_n_record_members_rederived",
      "@state:assertIsInstance"
    ],
    [
      "test_repair_receipt_n_record_members_rederived",
      "@state:assertRaisesRegex"
    ],
    [
      "test_repair_receipt_n_record_members_rederived",
      "@state:subTest"
    ],
    [
      "test_repair_receipt_n_record_members_rederived",
      "_assert_gh17_recovered"
    ],
    [
      "test_repair_receipt_n_record_members_rederived",
      "_new_repo"
    ],
    [
      "test_repair_receipt_n_record_members_rederived",
      "_run_file_bytes"
    ],
    [
      "test_repair_receipt_n_record_members_rederived",
      "_seed_gh17_wedge"
    ],
    [
      "test_repair_receipt_n_record_members_rederived",
      "api_environment"
    ],
    [
      "test_retired_successor_close_intent_recovers_and_releases_registry",
      "@state:assertEqual"
    ],
    [
      "test_retired_successor_close_intent_recovers_and_releases_registry",
      "@state:assertFalse"
    ],
    [
      "test_retired_successor_close_intent_recovers_and_releases_registry",
      "@state:assertNotIn"
    ],
    [
      "test_retired_successor_close_intent_recovers_and_releases_registry",
      "@state:assertRaisesRegex"
    ],
    [
      "test_retired_successor_close_intent_recovers_and_releases_registry",
      "@state:assertTrue"
    ],
    [
      "test_retired_successor_close_intent_recovers_and_releases_registry",
      "_new_repo"
    ],
    [
      "test_retired_successor_close_intent_recovers_and_releases_registry",
      "_open_legacy_run"
    ],
    [
      "test_retired_successor_close_intent_recovers_and_releases_registry",
      "api_environment"
    ],
    [
      "test_retired_successor_close_intent_recovers_and_releases_registry",
      "run_dir"
    ],
    [
      "test_retired_successor_close_recovers_every_stored_suffix_prefix",
      "@state:assertEqual"
    ],
    [
      "test_retired_successor_close_recovers_every_stored_suffix_prefix",
      "@state:assertFalse"
    ],
    [
      "test_retired_successor_close_recovers_every_stored_suffix_prefix",
      "@state:assertNotIn"
    ],
    [
      "test_retired_successor_close_recovers_every_stored_suffix_prefix",
      "@state:assertRaisesRegex"
    ],
    [
      "test_retired_successor_close_recovers_every_stored_suffix_prefix",
      "@state:assertTrue"
    ],
    [
      "test_retired_successor_close_recovers_every_stored_suffix_prefix",
      "@state:subTest"
    ],
    [
      "test_retired_successor_close_recovers_every_stored_suffix_prefix",
      "_new_repo"
    ],
    [
      "test_retired_successor_close_recovers_every_stored_suffix_prefix",
      "_open_legacy_run"
    ],
    [
      "test_retired_successor_close_recovers_every_stored_suffix_prefix",
      "api_environment"
    ],
    [
      "test_retired_successor_close_recovers_every_stored_suffix_prefix",
      "run_dir"
    ],
    [
      "test_retired_successor_recovery_rejects_other_run_mutation",
      "@state:assertEqual"
    ],
    [
      "test_retired_successor_recovery_rejects_other_run_mutation",
      "@state:assertNotEqual"
    ],
    [
      "test_retired_successor_recovery_rejects_other_run_mutation",
      "@state:assertRaisesRegex"
    ],
    [
      "test_retired_successor_recovery_rejects_other_run_mutation",
      "@state:assertTrue"
    ],
    [
      "test_retired_successor_recovery_rejects_other_run_mutation",
      "_new_repo"
    ],
    [
      "test_retired_successor_recovery_rejects_other_run_mutation",
      "_open_legacy_run"
    ],
    [
      "test_retired_successor_recovery_rejects_other_run_mutation",
      "api_environment"
    ],
    [
      "test_retired_successor_recovery_rejects_other_run_mutation",
      "run_dir"
    ],
    [
      "test_run_open_durable_receipt_survives_registry_failure_and_retry",
      "@state:assertEqual"
    ],
    [
      "test_run_open_durable_receipt_survives_registry_failure_and_retry",
      "@state:assertFalse"
    ],
    [
      "test_run_open_durable_receipt_survives_registry_failure_and_retry",
      "@state:assertIn"
    ],
    [
      "test_run_open_durable_receipt_survives_registry_failure_and_retry",
      "@state:assertRaisesRegex"
    ],
    [
      "test_run_open_durable_receipt_survives_registry_failure_and_retry",
      "@state:assertTrue"
    ],
    [
      "test_run_open_durable_receipt_survives_registry_failure_and_retry",
      "_new_repo"
    ],
    [
      "test_run_open_durable_receipt_survives_registry_failure_and_retry",
      "api_environment"
    ],
    [
      "test_run_open_durable_receipt_survives_registry_failure_and_retry",
      "open_run"
    ],
    [
      "test_run_open_durable_receipt_survives_registry_failure_and_retry",
      "run_dir"
    ],
    [
      "test_run_open_is_hidden_until_atomic_publication",
      "@state:assertEqual"
    ],
    [
      "test_run_open_is_hidden_until_atomic_publication",
      "@state:assertFalse"
    ],
    [
      "test_run_open_is_hidden_until_atomic_publication",
      "@state:assertTrue"
    ],
    [
      "test_run_open_is_hidden_until_atomic_publication",
      "_new_repo"
    ],
    [
      "test_run_open_is_hidden_until_atomic_publication",
      "api_environment"
    ],
    [
      "test_run_open_is_hidden_until_atomic_publication",
      "open_run"
    ],
    [
      "test_run_open_is_hidden_until_atomic_publication",
      "run_dir"
    ],
    [
      "test_run_open_prepublication_crashes_leave_no_visible_run",
      "@state:assertEqual"
    ],
    [
      "test_run_open_prepublication_crashes_leave_no_visible_run",
      "@state:assertFalse"
    ],
    [
      "test_run_open_prepublication_crashes_leave_no_visible_run",
      "@state:assertNotIn"
    ],
    [
      "test_run_open_prepublication_crashes_leave_no_visible_run",
      "@state:assertRaises"
    ],
    [
      "test_run_open_prepublication_crashes_leave_no_visible_run",
      "@state:subTest"
    ],
    [
      "test_run_open_prepublication_crashes_leave_no_visible_run",
      "_new_repo"
    ],
    [
      "test_run_open_prepublication_crashes_leave_no_visible_run",
      "api_environment"
    ],
    [
      "test_run_open_prepublication_crashes_leave_no_visible_run",
      "open_run"
    ],
    [
      "test_run_open_prepublication_crashes_leave_no_visible_run",
      "run_dir"
    ],
    [
      "test_run_open_process_death_keeps_staging_invisible_and_retryable",
      "@state:assertEqual"
    ],
    [
      "test_run_open_process_death_keeps_staging_invisible_and_retryable",
      "@state:assertFalse"
    ],
    [
      "test_run_open_process_death_keeps_staging_invisible_and_retryable",
      "@state:assertNotIn"
    ],
    [
      "test_run_open_process_death_keeps_staging_invisible_and_retryable",
      "@state:assertTrue"
    ],
    [
      "test_run_open_process_death_keeps_staging_invisible_and_retryable",
      "_new_repo"
    ],
    [
      "test_run_open_process_death_keeps_staging_invisible_and_retryable",
      "api_environment"
    ],
    [
      "test_run_open_process_death_keeps_staging_invisible_and_retryable",
      "run_dir"
    ],
    [
      "test_scope_change_recovers_intent_and_receipted_registry_publication",
      "@state:assertEqual"
    ],
    [
      "test_scope_change_recovers_intent_and_receipted_registry_publication",
      "@state:assertFalse"
    ],
    [
      "test_scope_change_recovers_intent_and_receipted_registry_publication",
      "@state:assertRaisesRegex"
    ],
    [
      "test_scope_change_recovers_intent_and_receipted_registry_publication",
      "@state:assertTrue"
    ],
    [
      "test_scope_change_recovers_intent_and_receipted_registry_publication",
      "@state:subTest"
    ],
    [
      "test_scope_change_recovers_intent_and_receipted_registry_publication",
      "_new_repo"
    ],
    [
      "test_scope_change_recovers_intent_and_receipted_registry_publication",
      "api_environment"
    ],
    [
      "test_scope_change_recovers_intent_and_receipted_registry_publication",
      "open_run"
    ],
    [
      "test_scope_change_recovers_intent_and_receipted_registry_publication",
      "run_dir"
    ],
    [
      "test_scope_change_recovery_refuses_unproved_replace_and_disabled_control",
      "@state:assertEqual"
    ],
    [
      "test_scope_change_recovery_refuses_unproved_replace_and_disabled_control",
      "@state:assertFalse"
    ],
    [
      "test_scope_change_recovery_refuses_unproved_replace_and_disabled_control",
      "@state:assertRaisesRegex"
    ],
    [
      "test_scope_change_recovery_refuses_unproved_replace_and_disabled_control",
      "@state:assertTrue"
    ],
    [
      "test_scope_change_recovery_refuses_unproved_replace_and_disabled_control",
      "@state:subTest"
    ],
    [
      "test_scope_change_recovery_refuses_unproved_replace_and_disabled_control",
      "_new_repo"
    ],
    [
      "test_scope_change_recovery_refuses_unproved_replace_and_disabled_control",
      "api_environment"
    ],
    [
      "test_scope_change_recovery_refuses_unproved_replace_and_disabled_control",
      "run_dir"
    ],
    [
      "test_self_consistent_intent_substitution_after_prepare_is_refused",
      "@state:assertEqual"
    ],
    [
      "test_self_consistent_intent_substitution_after_prepare_is_refused",
      "@state:assertRaisesRegex"
    ],
    [
      "test_self_consistent_intent_substitution_after_prepare_is_refused",
      "_new_repo"
    ],
    [
      "test_self_consistent_intent_substitution_after_prepare_is_refused",
      "api_environment"
    ],
    [
      "test_self_consistent_intent_substitution_after_prepare_is_refused",
      "open_run"
    ],
    [
      "test_self_consistent_intent_substitution_after_prepare_is_refused",
      "run_dir"
    ],
    [
      "test_self_consistent_intent_substitution_after_prepare_is_refused",
      "start_task"
    ],
    [
      "test_stable_reader_rederives_every_n_record_repair_member",
      "@state:assertEqual"
    ],
    [
      "test_stable_reader_rederives_every_n_record_repair_member",
      "@state:assertIsInstance"
    ],
    [
      "test_stable_reader_rederives_every_n_record_repair_member",
      "@state:subTest"
    ],
    [
      "test_stable_reader_rederives_every_n_record_repair_member",
      "_assert_gh17_recovered"
    ],
    [
      "test_stable_reader_rederives_every_n_record_repair_member",
      "_new_repo"
    ],
    [
      "test_stable_reader_rederives_every_n_record_repair_member",
      "_run_file_bytes"
    ],
    [
      "test_stable_reader_rederives_every_n_record_repair_member",
      "_seed_gh17_wedge"
    ],
    [
      "test_stable_reader_rederives_every_n_record_repair_member",
      "api_environment"
    ],
    [
      "test_staged_first_use_intent_blocks_outbox_before_publication",
      "@state:assertEqual"
    ],
    [
      "test_staged_first_use_intent_blocks_outbox_before_publication",
      "@state:assertRaisesRegex"
    ],
    [
      "test_staged_first_use_intent_blocks_outbox_before_publication",
      "@state:repo"
    ],
    [
      "test_staged_first_use_intent_blocks_outbox_before_publication",
      "_open_legacy_run"
    ],
    [
      "test_staged_first_use_intent_blocks_outbox_before_publication",
      "_run_file_bytes"
    ],
    [
      "test_staged_first_use_intent_blocks_outbox_before_publication",
      "api_environment"
    ],
    [
      "test_staged_first_use_intent_blocks_outbox_before_publication",
      "run_dir"
    ],
    [
      "test_terminal_abort_disposition_fails_closed_on_shape",
      "@state:assertFalse"
    ],
    [
      "test_terminal_abort_disposition_fails_closed_on_shape",
      "@state:assertTrue"
    ],
    [
      "test_terminal_builder_accepts_authenticated_abort_disposition",
      "@state:assertEqual"
    ],
    [
      "test_terminal_builder_accepts_authenticated_abort_disposition",
      "@state:assertRaisesRegex"
    ],
    [
      "test_terminal_builder_accepts_authenticated_abort_disposition",
      "_abort_bound_chain_fixture"
    ],
    [
      "test_terminal_builder_accepts_authenticated_abort_disposition",
      "_append_test_decision"
    ],
    [
      "test_terminal_builder_accepts_authenticated_abort_disposition",
      "_append_test_landing"
    ],
    [
      "test_terminal_builder_accepts_authenticated_abort_disposition",
      "_terminal_control_repo"
    ],
    [
      "test_terminal_builder_accepts_authenticated_abort_disposition",
      "_write_bound_chain_state"
    ],
    [
      "test_terminal_builder_accepts_authenticated_abort_disposition",
      "api_environment"
    ],
    [
      "test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine",
      "@state:assertEqual"
    ],
    [
      "test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine",
      "@state:assertRaisesRegex"
    ],
    [
      "test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine",
      "_append_test_landing"
    ],
    [
      "test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine",
      "_terminal_control_repo"
    ],
    [
      "test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine",
      "_write_bound_chain_state"
    ],
    [
      "test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine",
      "api_environment"
    ],
    [
      "test_terminal_builder_accepts_only_explicit_absent_chain_tombstone",
      "@state:assertEqual"
    ],
    [
      "test_terminal_builder_accepts_only_explicit_absent_chain_tombstone",
      "@state:assertRaisesRegex"
    ],
    [
      "test_terminal_builder_accepts_only_explicit_absent_chain_tombstone",
      "_append_test_landing"
    ],
    [
      "test_terminal_builder_accepts_only_explicit_absent_chain_tombstone",
      "_terminal_control_repo"
    ],
    [
      "test_terminal_builder_accepts_only_explicit_absent_chain_tombstone",
      "_write_bound_chain_state"
    ],
    [
      "test_terminal_builder_accepts_only_explicit_absent_chain_tombstone",
      "api_environment"
    ],
    [
      "test_terminal_builder_guards_pending_outbox_and_missing_landing",
      "@state:assertFalse"
    ],
    [
      "test_terminal_builder_guards_pending_outbox_and_missing_landing",
      "@state:assertRaisesRegex"
    ],
    [
      "test_terminal_builder_guards_pending_outbox_and_missing_landing",
      "_terminal_control_repo"
    ],
    [
      "test_terminal_builder_guards_pending_outbox_and_missing_landing",
      "_write_bound_chain_state"
    ],
    [
      "test_terminal_builder_guards_pending_outbox_and_missing_landing",
      "api_environment"
    ],
    [
      "test_terminal_builder_guards_pending_outbox_and_missing_landing",
      "run_dir"
    ],
    [
      "test_terminal_guard_refuses_chain_root_swap_after_enumeration",
      "@state:assertEqual"
    ],
    [
      "test_terminal_guard_refuses_chain_root_swap_after_enumeration",
      "@state:assertRaisesRegex"
    ],
    [
      "test_terminal_guard_refuses_chain_root_swap_after_enumeration",
      "_terminal_control_repo"
    ],
    [
      "test_terminal_guard_refuses_chain_root_swap_after_enumeration",
      "_write_bound_chain_state"
    ],
    [
      "test_terminal_guard_refuses_chain_root_swap_after_enumeration",
      "api_environment"
    ],
    [
      "test_terminal_guard_refuses_chain_root_swap_after_enumeration",
      "run_dir"
    ],
    [
      "test_torn_intent_never_becomes_authoritative",
      "@state:assertEqual"
    ],
    [
      "test_torn_intent_never_becomes_authoritative",
      "@state:assertRaisesRegex"
    ],
    [
      "test_torn_intent_never_becomes_authoritative",
      "@state:subTest"
    ],
    [
      "test_torn_intent_never_becomes_authoritative",
      "_leave_base_intent"
    ],
    [
      "test_torn_intent_never_becomes_authoritative",
      "_new_repo"
    ],
    [
      "test_torn_intent_never_becomes_authoritative",
      "api_environment"
    ],
    [
      "test_torn_intent_never_becomes_authoritative",
      "start_task"
    ],
    [
      "test_torn_repair_receipt_resumes_only_its_derived_suffix",
      "@state:assertEqual"
    ],
    [
      "test_torn_repair_receipt_resumes_only_its_derived_suffix",
      "@state:assertFalse"
    ],
    [
      "test_torn_repair_receipt_resumes_only_its_derived_suffix",
      "@state:assertRaisesRegex"
    ],
    [
      "test_torn_repair_receipt_resumes_only_its_derived_suffix",
      "@state:assertTrue"
    ],
    [
      "test_torn_repair_receipt_resumes_only_its_derived_suffix",
      "@state:repo"
    ],
    [
      "test_torn_repair_receipt_resumes_only_its_derived_suffix",
      "_leave_scope_receipt_gap"
    ],
    [
      "test_torn_repair_receipt_resumes_only_its_derived_suffix",
      "api_environment"
    ],
    [
      "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "@state:assertEqual"
    ],
    [
      "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "@state:assertFalse"
    ],
    [
      "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "@state:assertRaisesRegex"
    ],
    [
      "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "@state:assertTrue"
    ],
    [
      "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "@state:head"
    ],
    [
      "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "@state:repo"
    ],
    [
      "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "api_environment"
    ],
    [
      "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "open_run"
    ],
    [
      "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "run_dir"
    ],
    [
      "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "start_task"
    ],
    [
      "test_typed_opened_run_bytes_are_unchanged",
      "@state:assertEqual"
    ],
    [
      "test_typed_opened_run_bytes_are_unchanged",
      "@state:assertFalse"
    ],
    [
      "test_typed_opened_run_bytes_are_unchanged",
      "@state:assertIsNotNone"
    ],
    [
      "test_typed_opened_run_bytes_are_unchanged",
      "@state:assertTrue"
    ],
    [
      "test_typed_opened_run_bytes_are_unchanged",
      "@state:head"
    ],
    [
      "test_typed_opened_run_bytes_are_unchanged",
      "@state:repo"
    ],
    [
      "test_typed_opened_run_bytes_are_unchanged",
      "_run_file_bytes"
    ],
    [
      "test_typed_opened_run_bytes_are_unchanged",
      "api_environment"
    ],
    [
      "test_typed_opened_run_bytes_are_unchanged",
      "open_run"
    ],
    [
      "test_typed_opened_run_bytes_are_unchanged",
      "run_dir"
    ],
    [
      "test_typed_opened_run_bytes_are_unchanged",
      "start_task"
    ],
    [
      "test_typed_task_scope_refusal_names_offending_pathspec",
      "@state:assertRaisesRegex"
    ],
    [
      "test_typed_task_scope_refusal_names_offending_pathspec",
      "@state:repo"
    ],
    [
      "test_typed_task_scope_refusal_names_offending_pathspec",
      "api_environment"
    ],
    [
      "test_typed_task_scope_refusal_names_offending_pathspec",
      "open_run"
    ],
    [
      "test_unactivated_stale_ledger_eof_guard_is_load_bearing",
      "@state:assertNotEqual"
    ],
    [
      "test_unactivated_stale_ledger_eof_guard_is_load_bearing",
      "@state:assertRaises"
    ],
    [
      "test_unactivated_stale_ledger_eof_guard_is_load_bearing",
      "_new_repo"
    ],
    [
      "test_unactivated_stale_ledger_eof_guard_is_load_bearing",
      "_run_file_bytes"
    ],
    [
      "test_unactivated_stale_ledger_eof_guard_is_load_bearing",
      "_seed_unactivated_stale_ledger"
    ],
    [
      "test_unactivated_stale_ledger_eof_guard_is_load_bearing",
      "api_environment"
    ],
    [
      "test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
      "@state:assertEqual"
    ],
    [
      "test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
      "@state:assertFalse"
    ],
    [
      "test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
      "@state:assertIsInstance"
    ],
    [
      "test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
      "@state:assertLess"
    ],
    [
      "test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
      "@state:assertRaises"
    ],
    [
      "test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
      "@state:repo"
    ],
    [
      "test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
      "_run_file_bytes"
    ],
    [
      "test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
      "_seed_unactivated_stale_ledger"
    ],
    [
      "test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
      "api_environment"
    ],
    [
      "test_unactivated_stale_ledger_raw_close_succeeds",
      "@state:assertEqual"
    ],
    [
      "test_unactivated_stale_ledger_raw_close_succeeds",
      "_invoke_raw_lifecycle"
    ],
    [
      "test_unactivated_stale_ledger_raw_close_succeeds",
      "_new_repo"
    ],
    [
      "test_unactivated_stale_ledger_raw_close_succeeds",
      "_seed_unactivated_stale_ledger"
    ],
    [
      "test_unactivated_stale_ledger_raw_close_succeeds",
      "api_environment"
    ],
    [
      "test_unactivated_stale_ledger_retire_then_typed_successor",
      "@state:assertEqual"
    ],
    [
      "test_unactivated_stale_ledger_retire_then_typed_successor",
      "@state:assertTrue"
    ],
    [
      "test_unactivated_stale_ledger_retire_then_typed_successor",
      "_new_repo"
    ],
    [
      "test_unactivated_stale_ledger_retire_then_typed_successor",
      "_seed_unactivated_stale_ledger"
    ],
    [
      "test_unactivated_stale_ledger_retire_then_typed_successor",
      "api_environment"
    ],
    [
      "test_writer_activation_controls_are_independently_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_writer_activation_controls_are_independently_load_bearing",
      "@state:assertRaises"
    ],
    [
      "test_writer_activation_controls_are_independently_load_bearing",
      "@state:subTest"
    ],
    [
      "test_writer_activation_controls_are_independently_load_bearing",
      "_new_repo"
    ],
    [
      "test_writer_activation_controls_are_independently_load_bearing",
      "_open_legacy_run"
    ],
    [
      "test_writer_activation_controls_are_independently_load_bearing",
      "_run_file_bytes"
    ],
    [
      "test_writer_activation_controls_are_independently_load_bearing",
      "_seed_gh17_wedge"
    ],
    [
      "test_writer_activation_controls_are_independently_load_bearing",
      "api_environment"
    ],
    [
      "test_writer_activation_controls_are_independently_load_bearing",
      "run_dir"
    ],
    [
      "test_writer_activation_controls_are_independently_load_bearing",
      "start_task"
    ]
  ],
  "clusters": [
    [
      "setUp",
      "test_typed_builder_round_trip_ids_receipts_and_idempotency",
      "_leave_complete_intent",
      "test_exact_prefix_and_torn_receipt_recovery",
      "test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only",
      "test_midflight_intent_hardlink_fifo_and_foreign_uid_fences",
      "test_batch_controls_are_load_bearing",
      "test_activated_scope_readmission_uses_typed_builder",
      "test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume",
      "test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
      "test_batch_recover_repairs_one_n_record_gap",
      "test_batch_gap_repair_controls_are_independently_load_bearing",
      "test_activated_scope_change_rechecks_superset_containment_and_conflicts",
      "test_concurrent_admission_and_scope_change_remain_disjoint",
      "_leave_two_record_receipt_gap",
      "_write_landed_intent_for_last_receipt",
      "test_run_open_durable_receipt_survives_registry_failure_and_retry",
      "test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze",
      "test_ingest_requires_registered_proof_complete_authority",
      "test_activation_scan_skips_external_sibling_chain_and_run_lock",
      "test_concurrent_legacy_activation_never_cross_acquires_run_locks",
      "test_raw_open_writer_contract_refusal_is_load_bearing",
      "test_legacy_open_without_stderr_never_falls_back_to_stdout",
      "test_legacy_open_broken_stderr_never_changes_durable_success",
      "_seed_gh17_wedge",
      "_assert_gh17_recovered",
      "test_gh17_shape_recovers_without_reapplication",
      "test_gh17_shape_refuses_explicit_foreign_gap_run_id",
      "test_recovery_activation_crash_matrix",
      "test_repair_receipt_n_record_members_rederived",
      "test_stable_reader_rederives_every_n_record_repair_member",
      "test_writer_activation_controls_are_independently_load_bearing",
      "command",
      "test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet",
      "test_cli_singleton_and_idempotency_key_diagnostics"
    ],
    [
      "_leave_base_intent",
      "test_torn_intent_never_becomes_authoritative",
      "test_intent_without_journal_and_reentrant_pending_read_refuse_exactly"
    ],
    [
      "test_self_consistent_intent_substitution_after_prepare_is_refused"
    ],
    [
      "test_activated_missing_stable_lock_or_receipt_ledger_diverges"
    ],
    [
      "test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze"
    ],
    [
      "test_builder_validation_controls_are_detected_in_memory"
    ],
    [
      "test_scope_change_recovers_intent_and_receipted_registry_publication"
    ],
    [
      "test_scope_change_recovery_refuses_unproved_replace_and_disabled_control"
    ],
    [
      "test_repair_receipt_is_rederived_on_every_load",
      "test_torn_repair_receipt_resumes_only_its_derived_suffix",
      "_leave_scope_receipt_gap",
      "test_batch_recover_repairs_proven_readmission_gap_and_stale_intent",
      "test_batch_gap_repair_refuses_unproved_bytes_and_intent"
    ],
    [
      "test_typed_task_scope_refusal_names_offending_pathspec"
    ],
    [
      "test_builder_request_schema_and_digest_are_exact"
    ],
    [
      "test_run_open_is_hidden_until_atomic_publication"
    ],
    [
      "test_run_open_prepublication_crashes_leave_no_visible_run",
      "test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
      "_write_bound_chain_state",
      "_chain_drain_case",
      "_chain_drain_authorizer",
      "test_chain_drain_valid_authorizer_new_and_repeated_paths",
      "test_chain_drain_authorized_pending_and_lost_response_retry",
      "test_chain_drain_authorization_exact_field_bindings",
      "test_chain_drain_authorization_controls_are_load_bearing",
      "_append_test_landing",
      "_append_test_decision",
      "_terminal_control_repo",
      "test_terminal_builder_guards_pending_outbox_and_missing_landing",
      "_abort_bound_chain_fixture",
      "test_terminal_builder_accepts_authenticated_abort_disposition",
      "test_terminal_builder_accepts_only_explicit_absent_chain_tombstone",
      "test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine",
      "test_each_terminal_chain_control_is_load_bearing",
      "test_terminal_guard_refuses_chain_root_swap_after_enumeration",
      "_activation_markers",
      "_plant_unreplayable_unrelated_chain",
      "_pad_valid_json_over_cap",
      "_guard_activation_artifact_read_budget",
      "_activation_outbox_case",
      "_compete_with_activation_outbox",
      "_invoke_raw_lifecycle",
      "test_commit_sibling_receipt_snapshot_recheck_is_load_bearing",
      "test_activation_scan_tolerates_unreplayable_unrelated_chain",
      "test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
      "test_activation_scan_refuses_oversized_state_bound_to_this_run",
      "test_activation_state_byte_cap_is_load_bearing_in_memory",
      "test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
      "test_activation_events_byte_cap_is_load_bearing_in_memory",
      "test_activation_scan_converts_bounded_path_memory_errors",
      "test_activation_replay_passes_scan_only_state_and_event_caps",
      "test_activation_scan_unrelated_tolerance_is_load_bearing",
      "test_activation_outbox_blocks_raw_append_byte_exactly_then_drains",
      "test_activation_outbox_lifecycle_guard_is_load_bearing",
      "test_raw_lifecycle_validation_precedes_batch_reservation",
      "test_raw_open_cannot_supply_writer_contract_before_any_mutation",
      "test_activation_outbox_reserves_first_use_then_drains_exact_batch",
      "test_activation_outbox_missing_events_or_tampered_state_refuses_first_use",
      "test_legacy_activation_crash_matrix",
      "test_unactivated_stale_ledger_raw_close_succeeds"
    ],
    [
      "test_run_open_process_death_keeps_staging_invisible_and_retryable",
      "test_id_only_legacy_opening_activates_with_matching_marker_run_id",
      "test_retired_successor_close_intent_recovers_and_releases_registry",
      "test_retired_successor_close_recovers_every_stored_suffix_prefix"
    ],
    [
      "test_fr019_failure_phase_order_preserves_earlier_bytes"
    ],
    [
      "test_prepublication_intent_stage_crashes_retry_without_authority"
    ],
    [
      "test_foreign_request_intent_stage_is_not_deleted"
    ],
    [
      "test_intent_source_name_substitution_never_survives_canonical"
    ],
    [
      "test_intent_quarantine_preserves_a_second_canonical_swap"
    ],
    [
      "test_chain_drain_raw_records_without_capability_refuses"
    ],
    [
      "test_terminal_abort_disposition_fails_closed_on_shape"
    ],
    [
      "_self_event_fixture",
      "test_abort_disposition_self_event_admission_controls_are_load_bearing",
      "test_abort_disposition_self_event_source_fact_requires_aborted_unchanged_prior"
    ],
    [
      "_run_file_bytes",
      "test_first_receipt_ledger_post_create_substitution_refuses",
      "test_persisted_activation_candidate_requires_allocated_id_and_contract",
      "test_activation_allocation_refuses_unicode_and_oversized_suffixes",
      "test_removed_batch_lock_after_activation_is_not_recreated",
      "test_legacy_raw_guard_intent_conditions_are_load_bearing",
      "test_staged_first_use_intent_blocks_outbox_before_publication",
      "test_legacy_first_typed_use_atomically_activates",
      "test_typed_opened_run_bytes_are_unchanged",
      "test_global_reconciliation_defers_torn_adopted_coverage",
      "_restore_prefix_wedge_fixture",
      "_seed_unactivated_stale_ledger",
      "test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
      "test_unactivated_stale_ledger_retire_then_typed_successor",
      "test_unactivated_stale_ledger_eof_guard_is_load_bearing",
      "test_retired_successor_recovery_rejects_other_run_mutation"
    ],
    [
      "_assert_first_batch_artifact_substitution_refuses",
      "test_batch_lock_create_open_substitution_refuses",
      "test_first_receipt_ledger_create_open_substitution_refuses"
    ],
    [
      "_bound_chain_outbox",
      "_acknowledge_bound_chain",
      "_legacy_receipted_chain_case",
      "_rewrite_commit_events",
      "test_commit_sibling_receipt_request_authentication_is_load_bearing",
      "test_commit_sibling_carried_binding_authentication_is_load_bearing"
    ],
    [
      "test_activation_scan_ignores_unrelated_chain_created_between_scans"
    ],
    [
      "test_activation_scan_bound_chain_created_between_scans_refuses"
    ],
    [
      "test_raw_lifecycle_lock_order_is_load_bearing"
    ],
    [
      "test_published_first_use_intent_blocks_outbox_before_publication"
    ],
    [
      "test_pre_fix_golden_wedge_recovers_and_continues"
    ],
    [
      "test_internal_typed_flag_cannot_bypass_activated_batch_builders"
    ],
    [
      "api_environment"
    ],
    [
      "run_dir"
    ],
    [
      "_new_repo"
    ],
    [
      "start_task"
    ],
    [
      "_open_legacy_run"
    ],
    [
      "open_run"
    ]
  ],
  "hubs": [
    "@state:assertEqual",
    "api_environment",
    "run_dir",
    "_new_repo",
    "@state:assertRaisesRegex",
    "@state:assertFalse",
    "@state:assertTrue",
    "start_task",
    "@state:subTest",
    "@state:repo",
    "_open_legacy_run",
    "open_run"
  ],
  "prerequisites": [
    {
      "name": "ROOT",
      "line": 23,
      "users": [
        {
          "method": "Revision9BuilderBatchTests.test_concurrent_admission_and_scope_change_remain_disjoint",
          "line": 1512
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "TOOLS",
      "line": 24,
      "users": [
        {
          "method": "Revision9BuilderBatchTests.command",
          "line": 8824
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "PREFIX_WEDGE_FIXTURE",
      "line": 26,
      "users": [
        {
          "method": "Revision9BuilderBatchTests._restore_prefix_wedge_fixture",
          "line": 7465
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "UNREPLAYABLE_CHAIN_ID",
      "line": 27,
      "users": [
        {
          "method": "Revision9BuilderBatchTests.test_activation_scan_tolerates_unreplayable_unrelated_chain",
          "line": 5125
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "UNREPLAYABLE_CHAIN_FIXTURE",
      "line": 28,
      "users": [
        {
          "method": "Revision9BuilderBatchTests._plant_unreplayable_unrelated_chain",
          "line": 4195
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "PREFIX_WEDGE_FIXTURE_SHA256",
      "line": 44,
      "users": [
        {
          "method": "Revision9BuilderBatchTests._restore_prefix_wedge_fixture",
          "line": 7465
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "UNREPLAYABLE_CHAIN_FIXTURE_SHA256",
      "line": 51,
      "users": [
        {
          "method": "Revision9BuilderBatchTests._plant_unreplayable_unrelated_chain",
          "line": 4195
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "key",
      "line": 61,
      "users": [
        {
          "method": "Revision9BuilderBatchTests.open_run",
          "line": 245
        },
        {
          "method": "Revision9BuilderBatchTests.start_task",
          "line": 255
        },
        {
          "method": "Revision9BuilderBatchTests.test_typed_builder_round_trip_ids_receipts_and_idempotency",
          "line": 266
        },
        {
          "method": "Revision9BuilderBatchTests.test_self_consistent_intent_substitution_after_prepare_is_refused",
          "line": 544
        },
        {
          "method": "Revision9BuilderBatchTests.test_activated_missing_stable_lock_or_receipt_ledger_diverges",
          "line": 587
        },
        {
          "method": "Revision9BuilderBatchTests.test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze",
          "line": 611
        },
        {
          "method": "Revision9BuilderBatchTests.test_builder_validation_controls_are_detected_in_memory",
          "line": 779
        },
        {
          "method": "Revision9BuilderBatchTests.test_activated_scope_readmission_uses_typed_builder",
          "line": 828
        },
        {
          "method": "Revision9BuilderBatchTests.test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume",
          "line": 908
        },
        {
          "method": "Revision9BuilderBatchTests.test_scope_change_recovers_intent_and_receipted_registry_publication",
          "line": 983
        },
        {
          "method": "Revision9BuilderBatchTests.test_scope_change_recovery_refuses_unproved_replace_and_disabled_control",
          "line": 1067
        },
        {
          "method": "Revision9BuilderBatchTests.test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps",
          "line": 1156
        },
        {
          "method": "Revision9BuilderBatchTests.test_batch_recover_repairs_one_n_record_gap",
          "line": 1233
        },
        {
          "method": "Revision9BuilderBatchTests.test_repair_receipt_is_rederived_on_every_load",
          "line": 1358
        },
        {
          "method": "Revision9BuilderBatchTests.test_activated_scope_change_rechecks_superset_containment_and_conflicts",
          "line": 1436
        },
        {
          "method": "Revision9BuilderBatchTests._leave_scope_receipt_gap",
          "line": 1638
        },
        {
          "method": "Revision9BuilderBatchTests._leave_two_record_receipt_gap",
          "line": 1710
        },
        {
          "method": "Revision9BuilderBatchTests.test_batch_recover_repairs_proven_readmission_gap_and_stale_intent",
          "line": 1786
        },
        {
          "method": "Revision9BuilderBatchTests.test_typed_task_scope_refusal_names_offending_pathspec",
          "line": 1935
        },
        {
          "method": "Revision9BuilderBatchTests.test_run_open_process_death_keeps_staging_invisible_and_retryable",
          "line": 2117
        },
        {
          "method": "Revision9BuilderBatchTests.test_fr019_failure_phase_order_preserves_earlier_bytes",
          "line": 2197
        },
        {
          "method": "Revision9BuilderBatchTests.test_batch_crashes_recover_stored_bytes_without_duplicate_receipt",
          "line": 2260
        },
        {
          "method": "Revision9BuilderBatchTests.test_foreign_request_intent_stage_is_not_deleted",
          "line": 2412
        },
        {
          "method": "Revision9BuilderBatchTests.test_chain_drain_raw_records_without_capability_refuses",
          "line": 2590
        },
        {
          "method": "Revision9BuilderBatchTests._write_bound_chain_state",
          "line": 2706
        },
        {
          "method": "Revision9BuilderBatchTests._chain_drain_authorizer",
          "line": 3001
        },
        {
          "method": "Revision9BuilderBatchTests.test_ingest_requires_registered_proof_complete_authority",
          "line": 3332
        },
        {
          "method": "Revision9BuilderBatchTests._append_test_decision",
          "line": 3430
        },
        {
          "method": "Revision9BuilderBatchTests._terminal_control_repo",
          "line": 3477
        },
        {
          "method": "Revision9BuilderBatchTests.test_terminal_builder_guards_pending_outbox_and_missing_landing",
          "line": 3490
        },
        {
          "method": "Revision9BuilderBatchTests.test_terminal_builder_accepts_authenticated_abort_disposition",
          "line": 3567
        },
        {
          "method": "Revision9BuilderBatchTests._self_event_fixture",
          "line": 3699
        },
        {
          "method": "Revision9BuilderBatchTests.test_terminal_builder_accepts_only_explicit_absent_chain_tombstone",
          "line": 3805
        },
        {
          "method": "Revision9BuilderBatchTests.test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine",
          "line": 3884
        },
        {
          "method": "Revision9BuilderBatchTests.test_each_terminal_chain_control_is_load_bearing",
          "line": 3977
        },
        {
          "method": "Revision9BuilderBatchTests.test_terminal_guard_refuses_chain_root_swap_after_enumeration",
          "line": 4091
        },
        {
          "method": "Revision9BuilderBatchTests._assert_first_batch_artifact_substitution_refuses",
          "line": 4269
        },
        {
          "method": "Revision9BuilderBatchTests._activation_outbox_case",
          "line": 4407
        },
        {
          "method": "Revision9BuilderBatchTests._compete_with_activation_outbox",
          "line": 4496
        },
        {
          "method": "Revision9BuilderBatchTests._legacy_receipted_chain_case",
          "line": 4618
        },
        {
          "method": "Revision9BuilderBatchTests.test_commit_sibling_receipt_request_authentication_is_load_bearing",
          "line": 4725
        },
        {
          "method": "Revision9BuilderBatchTests.test_commit_sibling_carried_binding_authentication_is_load_bearing",
          "line": 4865
        },
        {
          "method": "Revision9BuilderBatchTests.test_activation_scan_warns_and_continues_on_oversized_unrelated_state",
          "line": 5174
        },
        {
          "method": "Revision9BuilderBatchTests.test_activation_scan_refuses_oversized_state_bound_to_this_run",
          "line": 5226
        },
        {
          "method": "Revision9BuilderBatchTests.test_activation_state_byte_cap_is_load_bearing_in_memory",
          "line": 5270
        },
        {
          "method": "Revision9BuilderBatchTests.test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one",
          "line": 5306
        },
        {
          "method": "Revision9BuilderBatchTests.test_activation_events_byte_cap_is_load_bearing_in_memory",
          "line": 5357
        },
        {
          "method": "Revision9BuilderBatchTests.test_activation_scan_converts_bounded_path_memory_errors",
          "line": 5396
        },
        {
          "method": "Revision9BuilderBatchTests.test_activation_replay_passes_scan_only_state_and_event_caps",
          "line": 5436
        },
        {
          "method": "Revision9BuilderBatchTests.test_activation_scan_bound_chain_created_between_scans_refuses",
          "line": 5591
        },
        {
          "method": "Revision9BuilderBatchTests.test_activation_scan_skips_external_sibling_chain_and_run_lock",
          "line": 5694
        },
        {
          "method": "Revision9BuilderBatchTests.test_concurrent_legacy_activation_never_cross_acquires_run_locks",
          "line": 5786
        },
        {
          "method": "Revision9BuilderBatchTests.test_persisted_activation_candidate_requires_allocated_id_and_contract",
          "line": 5961
        },
        {
          "method": "Revision9BuilderBatchTests.test_removed_batch_lock_after_activation_is_not_recreated",
          "line": 6117
        },
        {
          "method": "Revision9BuilderBatchTests.test_legacy_raw_guard_intent_conditions_are_load_bearing",
          "line": 6286
        },
        {
          "method": "Revision9BuilderBatchTests.test_staged_first_use_intent_blocks_outbox_before_publication",
          "line": 6579
        },
        {
          "method": "Revision9BuilderBatchTests.test_activation_outbox_missing_events_or_tampered_state_refuses_first_use",
          "line": 6853
        },
        {
          "method": "Revision9BuilderBatchTests.test_legacy_first_typed_use_atomically_activates",
          "line": 6896
        },
        {
          "method": "Revision9BuilderBatchTests.test_typed_opened_run_bytes_are_unchanged",
          "line": 7161
        },
        {
          "method": "Revision9BuilderBatchTests.test_global_reconciliation_defers_torn_adopted_coverage",
          "line": 7362
        },
        {
          "method": "Revision9BuilderBatchTests.test_pre_fix_golden_wedge_recovers_and_continues",
          "line": 7504
        },
        {
          "method": "Revision9BuilderBatchTests._seed_unactivated_stale_ledger",
          "line": 7641
        },
        {
          "method": "Revision9BuilderBatchTests.test_unactivated_stale_ledger_has_legible_refusal_and_raw_append",
          "line": 7710
        },
        {
          "method": "Revision9BuilderBatchTests.test_unactivated_stale_ledger_retire_then_typed_successor",
          "line": 7768
        },
        {
          "method": "Revision9BuilderBatchTests.test_unactivated_stale_ledger_eof_guard_is_load_bearing",
          "line": 7817
        },
        {
          "method": "Revision9BuilderBatchTests._seed_gh17_wedge",
          "line": 7846
        },
        {
          "method": "Revision9BuilderBatchTests.test_gh17_shape_recovers_without_reapplication",
          "line": 8088
        },
        {
          "method": "Revision9BuilderBatchTests.test_repair_receipt_n_record_members_rederived",
          "line": 8287
        },
        {
          "method": "Revision9BuilderBatchTests.test_stable_reader_rederives_every_n_record_repair_member",
          "line": 8409
        },
        {
          "method": "Revision9BuilderBatchTests.test_writer_activation_controls_are_independently_load_bearing",
          "line": 8517
        },
        {
          "method": "Revision9BuilderBatchTests.test_retired_successor_close_intent_recovers_and_releases_registry",
          "line": 8569
        },
        {
          "method": "Revision9BuilderBatchTests.test_retired_successor_close_recovers_every_stored_suffix_prefix",
          "line": 8609
        },
        {
          "method": "Revision9BuilderBatchTests.test_retired_successor_recovery_rejects_other_run_mutation",
          "line": 8691
        },
        {
          "method": "Revision9BuilderBatchTests.test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet",
          "line": 8835
        },
        {
          "method": "Revision9BuilderBatchTests.test_cli_singleton_and_idempotency_key_diagnostics",
          "line": 8944
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    }
  ],
  "census": [],
  "census_complete": false
}
