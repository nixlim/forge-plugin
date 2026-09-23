{
  "name": "Revision9BoundCLIIntegrationTests",
  "bases": [
    "CLI_FIXTURE_SUPPORT.ForgeCLIFixture"
  ],
  "metaclass": [],
  "decorators": [],
  "statements": [],
  "slots": false,
  "methods": [
    {
      "name": "revision9_environment",
      "line": 1255,
      "end_line": 1256,
      "decorators": [],
      "reads": [
        "environment"
      ],
      "writes": [],
      "calls": [
        "environment"
      ],
      "globals": [
        "os"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "cli_process_context",
      "line": 1259,
      "end_line": 1269,
      "decorators": [
        "contextlib.contextmanager"
      ],
      "reads": [
        "helpers",
        "revision9_environment"
      ],
      "writes": [],
      "calls": [
        "revision9_environment"
      ],
      "globals": [
        "ROOT",
        "RUNTIME",
        "mock",
        "os",
        "patch_engine"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "wrap"
    },
    {
      "name": "invoke_cli",
      "line": 1271,
      "end_line": 1272,
      "decorators": [],
      "reads": [
        "invoke_cli_at",
        "repo"
      ],
      "writes": [],
      "calls": [
        "invoke_cli_at"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "invoke_cli_at",
      "line": 1274,
      "end_line": 1289,
      "decorators": [],
      "reads": [
        "assertEqual",
        "cli_process_context"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "cli_process_context"
      ],
      "globals": [
        "CLI",
        "ENVELOPE_KEYS",
        "contextlib",
        "io",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "open_run_and_task",
      "line": 1291,
      "end_line": 1364,
      "decorators": [],
      "reads": [
        "assertTrue",
        "cli_process_context",
        "git",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertTrue",
        "cli_process_context",
        "git"
      ],
      "globals": [
        "CLI",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "start_bound_chain",
      "line": 1366,
      "end_line": 1384,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIsInstance",
        "assertTrue",
        "change",
        "invoke_cli",
        "open_run_and_task"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIsInstance",
        "assertTrue",
        "change",
        "invoke_cli",
        "open_run_and_task"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "start_bound_fast_chain",
      "line": 1386,
      "end_line": 1412,
      "decorators": [],
      "reads": [
        "assertEqual",
        "change",
        "invoke_cli",
        "open_run_and_task",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "change",
        "invoke_cli",
        "open_run_and_task",
        "state"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "configure_changelog_gate",
      "line": 1414,
      "end_line": 1422,
      "decorators": [],
      "reads": [
        "git",
        "repo"
      ],
      "writes": [],
      "calls": [
        "git"
      ],
      "globals": [
        "CLI_FIXTURE_SUPPORT"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "start_bound_multicell_stack_chain",
      "line": 1424,
      "end_line": 1467,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertGreaterEqual",
        "change",
        "git",
        "invoke_cli",
        "open_run_and_task",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertGreaterEqual",
        "change",
        "git",
        "invoke_cli",
        "open_run_and_task"
      ],
      "globals": [
        "CLI_FIXTURE_SUPPORT"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_bound_multicell_stack_journals_one_completed_batch",
      "line": 1469,
      "end_line": 1614,
      "decorators": [],
      "reads": [
        "assertEqual",
        "cli_process_context",
        "events",
        "events_path",
        "gate_lines",
        "gate_log",
        "invoke_cli",
        "repo",
        "start_bound_multicell_stack_chain",
        "state",
        "state_path"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "cli_process_context",
        "events",
        "events_path",
        "gate_lines",
        "invoke_cli",
        "start_bound_multicell_stack_chain",
        "state",
        "state_path"
      ],
      "globals": [
        "CLI"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "line": 1616,
      "end_line": 1889,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertNotEqual",
        "assertNotIn",
        "change",
        "cli_process_context",
        "events",
        "gate_lines",
        "helpers",
        "invoke_cli",
        "repo",
        "start_bound_multicell_stack_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertNotEqual",
        "assertNotIn",
        "change",
        "cli_process_context",
        "events",
        "gate_lines",
        "invoke_cli",
        "start_bound_multicell_stack_chain",
        "state"
      ],
      "globals": [
        "CLI"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_bound_multicell_stack_journal_deferral_is_load_bearing",
      "line": 1891,
      "end_line": 1926,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIn",
        "assertNotIn",
        "gate_lines",
        "invoke_cli",
        "start_bound_multicell_stack_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIn",
        "assertNotIn",
        "gate_lines",
        "invoke_cli",
        "start_bound_multicell_stack_chain",
        "state"
      ],
      "globals": [
        "patch_engine"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_bound_changelog_output_is_committed_policy_machinery",
      "line": 1928,
      "end_line": 1956,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIn",
        "assertTrue",
        "configure_changelog_gate",
        "invoke_cli",
        "start_bound_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIn",
        "assertTrue",
        "configure_changelog_gate",
        "invoke_cli",
        "start_bound_chain",
        "state"
      ],
      "globals": [
        "patch_chain_core"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_bound_non_changelog_output_still_names_out_of_scope_path",
      "line": 1958,
      "end_line": 1977,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIn",
        "change",
        "configure_changelog_gate",
        "invoke_cli",
        "open_run_and_task"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIn",
        "change",
        "configure_changelog_gate",
        "invoke_cli",
        "open_run_and_task"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "selected_commit_ingest_event_digests",
      "line": 1979,
      "end_line": 2044,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "CLI"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "normalized_journal_records",
      "line": 2047,
      "end_line": 2053,
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
      "name": "prepare_unbound_fast_ingest",
      "line": 2055,
      "end_line": 2312,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertIsNone",
        "assertNotIn",
        "change",
        "cli_process_context",
        "events",
        "events_path",
        "git",
        "invoke_cli",
        "open_run_and_task",
        "repo",
        "selected_commit_ingest_event_digests",
        "state",
        "state_path",
        "wait_for_review_completion"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertIsNone",
        "assertNotIn",
        "change",
        "cli_process_context",
        "events",
        "events_path",
        "git",
        "invoke_cli",
        "open_run_and_task",
        "selected_commit_ingest_event_digests",
        "state",
        "state_path",
        "wait_for_review_completion"
      ],
      "globals": [
        "CLI",
        "RUNTIME",
        "SimpleNamespace",
        "contextlib",
        "key",
        "mock",
        "warnings"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_real_unbound_fast_chain_ingests_and_receipted_retry_skips_reproof",
      "line": 2314,
      "end_line": 2427,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertTrue",
        "invoke_cli",
        "normalized_journal_records",
        "prepare_unbound_fast_ingest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertTrue",
        "invoke_cli",
        "normalized_journal_records",
        "prepare_unbound_fast_ingest"
      ],
      "globals": [
        "CLI",
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
      "name": "test_real_unbound_multicell_stack_ingest_keeps_every_head_record",
      "line": 2429,
      "end_line": 2534,
      "decorators": [],
      "reads": [
        "assertEqual",
        "invoke_cli",
        "normalized_journal_records",
        "prepare_unbound_fast_ingest",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "invoke_cli",
        "normalized_journal_records",
        "prepare_unbound_fast_ingest"
      ],
      "globals": [
        "CLI",
        "hashlib"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_legacy_run_ingest_first_typed_use_activates_once_and_is_receipted",
      "line": 2536,
      "end_line": 2585,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "invoke_cli",
        "normalized_journal_records",
        "prepare_unbound_fast_ingest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "invoke_cli",
        "normalized_journal_records",
        "prepare_unbound_fast_ingest"
      ],
      "globals": [
        "CLI",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_legacy_run_ingest_allocation_projection_is_load_bearing",
      "line": 2587,
      "end_line": 2643,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertGreaterEqual",
        "cli_process_context",
        "prepare_unbound_fast_ingest",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertGreaterEqual",
        "cli_process_context",
        "prepare_unbound_fast_ingest"
      ],
      "globals": [
        "CLI",
        "contextlib",
        "io",
        "json",
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
      "name": "test_captured_commit_and_merge_sources_reopen_from_the_run_root",
      "line": 2645,
      "end_line": 2694,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertRaisesRegex",
        "cli_process_context",
        "open_run_and_task",
        "repo",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertRaisesRegex",
        "cli_process_context",
        "open_run_and_task",
        "subTest"
      ],
      "globals": [
        "CLI",
        "hashlib"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_captured_source_substitution_before_intent_refuses_without_append",
      "line": 2696,
      "end_line": 2740,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "invoke_cli",
        "prepare_unbound_fast_ingest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "invoke_cli",
        "prepare_unbound_fast_ingest"
      ],
      "globals": [
        "CLI",
        "mock",
        "os"
      ],
      "nested_defs": [
        "substitute_capture"
      ],
      "nonlocal_names": [
        "substituted"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_captured_source_substitution_before_builder_keeps_exact_diagnostic",
      "line": 2742,
      "end_line": 2787,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "invoke_cli",
        "prepare_unbound_fast_ingest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "invoke_cli",
        "prepare_unbound_fast_ingest"
      ],
      "globals": [
        "CLI",
        "mock",
        "os"
      ],
      "nested_defs": [
        "substitute_capture"
      ],
      "nonlocal_names": [
        "substituted"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_each_ingest_proof_control_refuses_at_its_named_boundary",
      "line": 2789,
      "end_line": 2849,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "prepare_unbound_fast_ingest",
        "repo",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "prepare_unbound_fast_ingest",
        "subTest"
      ],
      "globals": [
        "CLI",
        "patch_chain_core"
      ],
      "nested_defs": [
        "track_boundary"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_fast_mechanical_skip_is_rejected_at_current_gates_proof",
      "line": 2851,
      "end_line": 2890,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "prepare_unbound_fast_ingest",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "prepare_unbound_fast_ingest"
      ],
      "globals": [
        "CLI",
        "patch_chain_core"
      ],
      "nested_defs": [
        "track_boundary"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "line": 2892,
      "end_line": 3018,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertGreaterEqual",
        "assertIsNone",
        "assertTrue",
        "change",
        "cli_process_context",
        "invoke_cli",
        "normalized_journal_records",
        "open_run_and_task",
        "repo",
        "state",
        "wait_for_review_completion"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertGreaterEqual",
        "assertIsNone",
        "assertTrue",
        "change",
        "cli_process_context",
        "invoke_cli",
        "normalized_journal_records",
        "open_run_and_task",
        "state",
        "wait_for_review_completion"
      ],
      "globals": [
        "CLI",
        "hashlib",
        "json",
        "key",
        "warnings"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_lockless_bound_start_refuses_nonexistent_run_without_creating_it",
      "line": 3020,
      "end_line": 3049,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "change",
        "git",
        "invoke_cli",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "change",
        "git",
        "invoke_cli"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_lockless_bound_start_halt_precedes_stable_lock_creation",
      "line": 3051,
      "end_line": 3099,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "change",
        "git",
        "helpers",
        "invoke_cli",
        "open_run_and_task",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "change",
        "git",
        "invoke_cli",
        "open_run_and_task"
      ],
      "globals": [
        "CLI"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_start_lock_disappearance_never_recreates_before_halt",
      "line": 3101,
      "end_line": 3152,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "change",
        "git",
        "helpers",
        "invoke_cli",
        "open_run_and_task",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "change",
        "git",
        "invoke_cli",
        "open_run_and_task"
      ],
      "globals": [
        "CLI",
        "mock",
        "os"
      ],
      "nested_defs": [
        "disappear_after_observation"
      ],
      "nonlocal_names": [
        "disappeared"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_legacy_first_use_chain_receipt_bootstrap_is_load_bearing",
      "line": 3154,
      "end_line": 3227,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertIsNone",
        "change",
        "invoke_cli",
        "open_run_and_task",
        "repo",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertIsNone",
        "change",
        "invoke_cli",
        "open_run_and_task",
        "state"
      ],
      "globals": [
        "CLI",
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
      "name": "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "line": 3229,
      "end_line": 3287,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertIsInstance",
        "assertNotEqual",
        "change",
        "events",
        "invoke_cli",
        "open_run_and_task",
        "repo",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertIsInstance",
        "assertNotEqual",
        "change",
        "events",
        "invoke_cli",
        "open_run_and_task",
        "state"
      ],
      "globals": [
        "CLI",
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
      "name": "test_commit_activation_rejects_event_one_rebinding_before_replay",
      "line": 3289,
      "end_line": 3338,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIsInstance",
        "assertRaises",
        "change",
        "invoke_cli",
        "open_run_and_task",
        "repo",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIsInstance",
        "assertRaises",
        "change",
        "invoke_cli",
        "open_run_and_task",
        "state"
      ],
      "globals": [
        "CLI",
        "CORE",
        "copy",
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
      "name": "test_lockless_bound_start_refuses_foreign_owner_without_creating_lock",
      "line": 3340,
      "end_line": 3383,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "change",
        "git",
        "invoke_cli",
        "open_run_and_task",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "change",
        "git",
        "invoke_cli",
        "open_run_and_task"
      ],
      "globals": [
        "CLI"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_lockless_bound_start_refuses_other_worktree_without_creating_lock",
      "line": 3385,
      "end_line": 3419,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "git",
        "git_at",
        "invoke_cli_at",
        "open_run_and_task",
        "repo",
        "temp_root"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "git",
        "git_at",
        "invoke_cli_at",
        "open_run_and_task"
      ],
      "globals": [
        "CLI"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_lockless_bound_start_creation_control_is_load_bearing",
      "line": 3421,
      "end_line": 3460,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "change",
        "git",
        "invoke_cli",
        "open_run_and_task",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "change",
        "git",
        "invoke_cli",
        "open_run_and_task"
      ],
      "globals": [
        "CLI",
        "contextlib",
        "mock"
      ],
      "nested_defs": [
        "disabled_creation"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_lockless_chain_batch_creation_revalidates_in_lock_order",
      "line": 3462,
      "end_line": 3546,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertTrue",
        "cli_process_context",
        "open_run_and_task",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertTrue",
        "cli_process_context",
        "open_run_and_task"
      ],
      "globals": [
        "CLI",
        "CORE",
        "contextlib",
        "mock"
      ],
      "nested_defs": [
        "observed_batch_lock",
        "observed_registry_lock",
        "observed_locked_journal"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_existing_chain_batch_lock_skips_creation_only_validation",
      "line": 3548,
      "end_line": 3588,
      "decorators": [],
      "reads": [
        "assertEqual",
        "cli_process_context",
        "open_run_and_task",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "cli_process_context",
        "open_run_and_task"
      ],
      "globals": [
        "CLI",
        "CORE",
        "contextlib",
        "mock",
        "patch_chain_core"
      ],
      "nested_defs": [
        "observed_batch_lock"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_existing_locked_bound_start_succeeds_without_session_pid",
      "line": 3590,
      "end_line": 3628,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertTrue",
        "change",
        "helpers",
        "open_run_and_task",
        "repo",
        "revision9_environment"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertTrue",
        "change",
        "open_run_and_task",
        "revision9_environment"
      ],
      "globals": [
        "CLI",
        "ROOT",
        "RUNTIME",
        "contextlib",
        "io",
        "json",
        "mock",
        "os",
        "patch_engine"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_existing_locked_bound_start_preserves_foreign_owner_behavior",
      "line": 3630,
      "end_line": 3659,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertTrue",
        "change",
        "invoke_cli",
        "open_run_and_task",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertTrue",
        "change",
        "invoke_cli",
        "open_run_and_task"
      ],
      "globals": [
        "CLI"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_lockless_merge_start_binding_creates_stable_batch_lock",
      "line": 3661,
      "end_line": 3693,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertTrue",
        "cli_process_context",
        "open_run_and_task",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertTrue",
        "cli_process_context",
        "open_run_and_task"
      ],
      "globals": [
        "CLI",
        "CORE",
        "contextlib",
        "key",
        "mock"
      ],
      "nested_defs": [
        "observed_batch_lock"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_lockless_read_only_binding_validator_does_not_create_batch_lock",
      "line": 3695,
      "end_line": 3729,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "cli_process_context",
        "open_run_and_task",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "cli_process_context",
        "open_run_and_task"
      ],
      "globals": [
        "CLI",
        "CORE",
        "contextlib",
        "key",
        "mock"
      ],
      "nested_defs": [
        "observed_batch_lock"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_bound_start_persists_exact_immutable_binding",
      "line": 3731,
      "end_line": 3750,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIs",
        "assertIsNone",
        "events",
        "repo",
        "start_bound_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIs",
        "assertIsNone",
        "events",
        "start_bound_chain",
        "state"
      ],
      "globals": [
        "CLI"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_fresh_key_cannot_replay_typed_verification_or_decision_binding",
      "line": 3752,
      "end_line": 3865,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "cli_process_context",
        "open_run_and_task",
        "repo",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "cli_process_context",
        "open_run_and_task",
        "subTest"
      ],
      "globals": [
        "CLI",
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
      "name": "test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive",
      "line": 3867,
      "end_line": 3986,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "cli_process_context",
        "git",
        "invoke_cli_at",
        "repo",
        "temp_root"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "cli_process_context",
        "git",
        "invoke_cli_at"
      ],
      "globals": [
        "CLI",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_historical_receipted_binding_replays_after_restage",
      "line": 3988,
      "end_line": 4051,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertNotEqual",
        "assertTrue",
        "change",
        "cli_process_context",
        "events",
        "events_path",
        "invoke_cli",
        "repo",
        "start_bound_chain",
        "state",
        "state_path"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertNotEqual",
        "assertTrue",
        "change",
        "cli_process_context",
        "events",
        "events_path",
        "invoke_cli",
        "start_bound_chain",
        "state",
        "state_path"
      ],
      "globals": [
        "CLI",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "line": 4053,
      "end_line": 4145,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context",
        "events_path",
        "invoke_cli",
        "repo",
        "start_bound_chain",
        "state_path"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context",
        "events_path",
        "invoke_cli",
        "start_bound_chain",
        "state_path"
      ],
      "globals": [
        "CLI",
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
      "name": "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "line": 4147,
      "end_line": 4311,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertGreater",
        "assertIn",
        "assertIsNone",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context",
        "events",
        "invoke_cli",
        "repo",
        "start_bound_fast_chain",
        "state_path"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertGreater",
        "assertIn",
        "assertIsNone",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context",
        "events",
        "invoke_cli",
        "start_bound_fast_chain",
        "state_path"
      ],
      "globals": [
        "CLI",
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
      "name": "test_abort_refuses_terminal_chains_before_any_mutation",
      "line": 4313,
      "end_line": 4343,
      "decorators": [],
      "reads": [
        "assertEqual",
        "cli_process_context",
        "events_path",
        "invoke_cli",
        "repo",
        "start_bound_fast_chain",
        "state_path"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "cli_process_context",
        "events_path",
        "invoke_cli",
        "start_bound_fast_chain",
        "state_path"
      ],
      "globals": [
        "CLI",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_abort_refuses_landed_chain_and_keeps_its_landing",
      "line": 4345,
      "end_line": 4386,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIsNone",
        "cli_process_context",
        "events_path",
        "invoke_cli",
        "repo",
        "start_bound_fast_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIsNone",
        "cli_process_context",
        "events_path",
        "invoke_cli",
        "start_bound_fast_chain",
        "state"
      ],
      "globals": [
        "CLI",
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
      "name": "test_retrospective_abort_disposition_carries_the_decision_once",
      "line": 4388,
      "end_line": 4465,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertIsNone",
        "assertNotEqual",
        "assertNotIn",
        "assertTrue",
        "cli_process_context",
        "events",
        "events_path",
        "invoke_cli",
        "repo",
        "start_bound_fast_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertIsNone",
        "assertNotEqual",
        "assertNotIn",
        "assertTrue",
        "cli_process_context",
        "events",
        "events_path",
        "invoke_cli",
        "start_bound_fast_chain",
        "state"
      ],
      "globals": [
        "CLI",
        "RUNTIME",
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
      "name": "_quarantine_and_tombstone",
      "line": 4467,
      "end_line": 4480,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertTrue",
        "invoke_cli",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertTrue",
        "invoke_cli"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_journal_records",
      "line": 4482,
      "end_line": 4487,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "line": 4489,
      "end_line": 4606,
      "decorators": [],
      "reads": [
        "_journal_records",
        "_quarantine_and_tombstone",
        "assertEqual",
        "assertFalse",
        "assertGreater",
        "assertGreaterEqual",
        "assertNotEqual",
        "assertRaises",
        "assertTrue",
        "cli_process_context",
        "invoke_cli",
        "repo",
        "start_bound_fast_chain",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_journal_records",
        "_quarantine_and_tombstone",
        "assertEqual",
        "assertFalse",
        "assertGreater",
        "assertGreaterEqual",
        "assertNotEqual",
        "assertRaises",
        "assertTrue",
        "cli_process_context",
        "invoke_cli",
        "start_bound_fast_chain",
        "subTest"
      ],
      "globals": [
        "CLI",
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
      "name": "test_tombstone_disposition_refuses_a_nonexistent_run_before_any_lock",
      "line": 4608,
      "end_line": 4626,
      "decorators": [],
      "reads": [
        "_quarantine_and_tombstone",
        "assertEqual",
        "assertFalse",
        "invoke_cli",
        "repo",
        "start_bound_fast_chain"
      ],
      "writes": [],
      "calls": [
        "_quarantine_and_tombstone",
        "assertEqual",
        "assertFalse",
        "invoke_cli",
        "start_bound_fast_chain"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_abort_disposition_run_id_must_name_a_readable_chains_bound_run",
      "line": 4628,
      "end_line": 4651,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIn",
        "events",
        "invoke_cli",
        "repo",
        "start_bound_fast_chain"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIn",
        "events",
        "invoke_cli",
        "start_bound_fast_chain"
      ],
      "globals": [
        "RUNTIME",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "line": 4653,
      "end_line": 4733,
      "decorators": [],
      "reads": [
        "_journal_records",
        "_quarantine_and_tombstone",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "cli_process_context",
        "invoke_cli",
        "repo",
        "start_bound_fast_chain",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_journal_records",
        "_quarantine_and_tombstone",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "cli_process_context",
        "invoke_cli",
        "start_bound_fast_chain",
        "subTest"
      ],
      "globals": [
        "CLI",
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
      "name": "test_abort_disposition_refuses_every_ineligible_chain",
      "line": 4735,
      "end_line": 4749,
      "decorators": [],
      "reads": [
        "assertEqual",
        "events_path",
        "invoke_cli",
        "start_bound_fast_chain"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "events_path",
        "invoke_cli",
        "start_bound_fast_chain"
      ],
      "globals": [
        "CLI"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_abort_disposition_preconditions_are_independently_load_bearing",
      "line": 4751,
      "end_line": 4783,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIsNone",
        "assertIsNotNone",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIsNone",
        "assertIsNotNone",
        "subTest"
      ],
      "globals": [
        "CLI"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_abort_disposition_reaches_a_dead_in_place_chain",
      "line": 4785,
      "end_line": 4811,
      "decorators": [],
      "reads": [
        "assertEqual",
        "events",
        "invoke_cli",
        "start_bound_fast_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "events",
        "invoke_cli",
        "start_bound_fast_chain",
        "state"
      ],
      "globals": [
        "CLI",
        "RUNTIME",
        "datetime",
        "mock",
        "patch_engine"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_abort_disposition_is_exempt_from_the_iteration_cap",
      "line": 4813,
      "end_line": 4846,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertRaises",
        "cli_process_context",
        "invoke_cli",
        "repo",
        "start_bound_fast_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertRaises",
        "cli_process_context",
        "invoke_cli",
        "start_bound_fast_chain",
        "state"
      ],
      "globals": [
        "CLI",
        "RUNTIME",
        "mock",
        "patch_engine"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_abort_disposition_requires_a_chain_id_and_a_readable_journal",
      "line": 4848,
      "end_line": 4866,
      "decorators": [],
      "reads": [
        "assertEqual",
        "events_path",
        "invoke_cli",
        "start_bound_fast_chain"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "events_path",
        "invoke_cli",
        "start_bound_fast_chain"
      ],
      "globals": [
        "CLI",
        "RUNTIME",
        "mock"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_abort_disposition_refuses_a_live_bound_chain",
      "line": 4868,
      "end_line": 4876,
      "decorators": [],
      "reads": [
        "assertEqual",
        "events_path",
        "invoke_cli",
        "start_bound_fast_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "events_path",
        "invoke_cli",
        "start_bound_fast_chain",
        "state"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_abort_disposition_refuses_an_unbound_aborted_chain",
      "line": 4878,
      "end_line": 4889,
      "decorators": [],
      "reads": [
        "assertEqual",
        "change",
        "events_path",
        "invoke_cli"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "change",
        "events_path",
        "invoke_cli"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_task_finish_inspects_only_the_finishing_tasks_chains",
      "line": 4891,
      "end_line": 4954,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertRaisesRegex",
        "change",
        "cli_process_context",
        "git",
        "invoke_cli",
        "repo",
        "start_bound_chain"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertRaisesRegex",
        "change",
        "cli_process_context",
        "git",
        "invoke_cli",
        "start_bound_chain"
      ],
      "globals": [
        "CLI",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_operator_tombstone_admits_absent_chain_and_refuses_healthy_chain",
      "line": 4956,
      "end_line": 5007,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "change",
        "invoke_cli",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "change",
        "invoke_cli"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_tombstone_publication_recovers_only_authenticated_temp_alias",
      "line": 5009,
      "end_line": 5049,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertTrue",
        "invoke_cli",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertTrue",
        "invoke_cli"
      ],
      "globals": [
        "os"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_tombstone_publication_retries_prelink_and_postunlink_failures",
      "line": 5051,
      "end_line": 5115,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertNotIn",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertNotIn",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context"
      ],
      "globals": [
        "CLI",
        "mock",
        "os",
        "stat"
      ],
      "nested_defs": [
        "fail_directory_fsync"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "line": 5117,
      "end_line": 5165,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertIsNotNone",
        "assertNotEqual",
        "assertRaisesRegex",
        "cli_process_context",
        "events_path",
        "repo",
        "start_bound_chain",
        "state_path"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertIsNotNone",
        "assertNotEqual",
        "assertRaisesRegex",
        "cli_process_context",
        "events_path",
        "start_bound_chain",
        "state_path"
      ],
      "globals": [
        "CLI",
        "json"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_failed_ingest_proof_captures_but_never_references_or_mutates_journal",
      "line": 5167,
      "end_line": 5235,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "git",
        "invoke_cli",
        "open_run_and_task",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "git",
        "invoke_cli",
        "open_run_and_task"
      ],
      "globals": [
        "CLI",
        "hashlib",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_event_carrier_survives_drain_crash_and_replays_once",
      "line": 5237,
      "end_line": 5357,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIsInstance",
        "assertIsNone",
        "assertNotIn",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context",
        "events",
        "repo",
        "start_bound_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIsInstance",
        "assertIsNone",
        "assertNotIn",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context",
        "events",
        "start_bound_chain",
        "state"
      ],
      "globals": [
        "CLI",
        "copy",
        "hashlib",
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
      "name": "assert_commit_identity_drain_crash_replays_once",
      "line": 5359,
      "end_line": 5472,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIsInstance",
        "assertIsNone",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context",
        "events",
        "repo",
        "start_bound_fast_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIsInstance",
        "assertIsNone",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context",
        "events",
        "start_bound_fast_chain",
        "state"
      ],
      "globals": [
        "CLI",
        "mock"
      ],
      "nested_defs": [
        "crash_identity_drain",
        "append_then_crash"
      ],
      "nonlocal_names": [
        "crashed"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_commit_identity_carrier_pre_drain_crash_replays_once",
      "line": 5474,
      "end_line": 5475,
      "decorators": [],
      "reads": [
        "assert_commit_identity_drain_crash_replays_once"
      ],
      "writes": [],
      "calls": [
        "assert_commit_identity_drain_crash_replays_once"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_commit_identity_journal_append_crash_replays_once",
      "line": 5477,
      "end_line": 5478,
      "decorators": [],
      "reads": [
        "assert_commit_identity_drain_crash_replays_once"
      ],
      "writes": [],
      "calls": [
        "assert_commit_identity_drain_crash_replays_once"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_commit_identity_receipt_append_crash_replays_once",
      "line": 5480,
      "end_line": 5481,
      "decorators": [],
      "reads": [
        "assert_commit_identity_drain_crash_replays_once"
      ],
      "writes": [],
      "calls": [
        "assert_commit_identity_drain_crash_replays_once"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
      "line": 5483,
      "end_line": 5629,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context",
        "repo",
        "start_bound_fast_chain",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertRaisesRegex",
        "assertTrue",
        "cli_process_context",
        "start_bound_fast_chain",
        "subTest"
      ],
      "globals": [
        "CLI",
        "copy",
        "hashlib",
        "json",
        "key",
        "mock"
      ],
      "nested_defs": [
        "append_journal_then_crash"
      ],
      "nonlocal_names": [
        "crashed"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_receipted_commit_produced_crash_recovers_one_landing",
      "line": 5631,
      "end_line": 5749,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIsNone",
        "assertRaisesRegex",
        "cli_process_context",
        "events",
        "git",
        "invoke_cli",
        "repo",
        "start_bound_fast_chain",
        "state"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIsNone",
        "assertRaisesRegex",
        "cli_process_context",
        "events",
        "git",
        "invoke_cli",
        "start_bound_fast_chain",
        "state"
      ],
      "globals": [
        "CLI",
        "json",
        "mock"
      ],
      "nested_defs": [
        "persist_then_crash"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    }
  ],
  "edges": [
    [
      "_quarantine_and_tombstone",
      "@state:assertEqual"
    ],
    [
      "_quarantine_and_tombstone",
      "@state:assertTrue"
    ],
    [
      "_quarantine_and_tombstone",
      "@state:repo"
    ],
    [
      "_quarantine_and_tombstone",
      "invoke_cli"
    ],
    [
      "assert_commit_identity_drain_crash_replays_once",
      "@state:assertEqual"
    ],
    [
      "assert_commit_identity_drain_crash_replays_once",
      "@state:assertIsInstance"
    ],
    [
      "assert_commit_identity_drain_crash_replays_once",
      "@state:assertIsNone"
    ],
    [
      "assert_commit_identity_drain_crash_replays_once",
      "@state:assertRaisesRegex"
    ],
    [
      "assert_commit_identity_drain_crash_replays_once",
      "@state:assertTrue"
    ],
    [
      "assert_commit_identity_drain_crash_replays_once",
      "@state:events"
    ],
    [
      "assert_commit_identity_drain_crash_replays_once",
      "@state:repo"
    ],
    [
      "assert_commit_identity_drain_crash_replays_once",
      "@state:state"
    ],
    [
      "assert_commit_identity_drain_crash_replays_once",
      "cli_process_context"
    ],
    [
      "assert_commit_identity_drain_crash_replays_once",
      "start_bound_fast_chain"
    ],
    [
      "cli_process_context",
      "@state:helpers"
    ],
    [
      "cli_process_context",
      "revision9_environment"
    ],
    [
      "configure_changelog_gate",
      "@state:git"
    ],
    [
      "configure_changelog_gate",
      "@state:repo"
    ],
    [
      "invoke_cli",
      "@state:repo"
    ],
    [
      "invoke_cli",
      "invoke_cli_at"
    ],
    [
      "invoke_cli_at",
      "@state:assertEqual"
    ],
    [
      "invoke_cli_at",
      "cli_process_context"
    ],
    [
      "open_run_and_task",
      "@state:assertTrue"
    ],
    [
      "open_run_and_task",
      "@state:git"
    ],
    [
      "open_run_and_task",
      "@state:repo"
    ],
    [
      "open_run_and_task",
      "cli_process_context"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:assertEqual"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:assertFalse"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:assertIn"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:assertIsNone"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:assertNotIn"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:change"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:events"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:events_path"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:git"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:repo"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:state"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:state_path"
    ],
    [
      "prepare_unbound_fast_ingest",
      "@state:wait_for_review_completion"
    ],
    [
      "prepare_unbound_fast_ingest",
      "cli_process_context"
    ],
    [
      "prepare_unbound_fast_ingest",
      "invoke_cli"
    ],
    [
      "prepare_unbound_fast_ingest",
      "open_run_and_task"
    ],
    [
      "prepare_unbound_fast_ingest",
      "selected_commit_ingest_event_digests"
    ],
    [
      "revision9_environment",
      "@state:environment"
    ],
    [
      "start_bound_chain",
      "@state:assertEqual"
    ],
    [
      "start_bound_chain",
      "@state:assertIsInstance"
    ],
    [
      "start_bound_chain",
      "@state:assertTrue"
    ],
    [
      "start_bound_chain",
      "@state:change"
    ],
    [
      "start_bound_chain",
      "invoke_cli"
    ],
    [
      "start_bound_chain",
      "open_run_and_task"
    ],
    [
      "start_bound_fast_chain",
      "@state:assertEqual"
    ],
    [
      "start_bound_fast_chain",
      "@state:change"
    ],
    [
      "start_bound_fast_chain",
      "@state:state"
    ],
    [
      "start_bound_fast_chain",
      "invoke_cli"
    ],
    [
      "start_bound_fast_chain",
      "open_run_and_task"
    ],
    [
      "start_bound_multicell_stack_chain",
      "@state:assertEqual"
    ],
    [
      "start_bound_multicell_stack_chain",
      "@state:assertGreaterEqual"
    ],
    [
      "start_bound_multicell_stack_chain",
      "@state:change"
    ],
    [
      "start_bound_multicell_stack_chain",
      "@state:git"
    ],
    [
      "start_bound_multicell_stack_chain",
      "@state:repo"
    ],
    [
      "start_bound_multicell_stack_chain",
      "invoke_cli"
    ],
    [
      "start_bound_multicell_stack_chain",
      "open_run_and_task"
    ],
    [
      "test_abort_disposition_is_exempt_from_the_iteration_cap",
      "@state:assertEqual"
    ],
    [
      "test_abort_disposition_is_exempt_from_the_iteration_cap",
      "@state:assertRaises"
    ],
    [
      "test_abort_disposition_is_exempt_from_the_iteration_cap",
      "@state:repo"
    ],
    [
      "test_abort_disposition_is_exempt_from_the_iteration_cap",
      "@state:state"
    ],
    [
      "test_abort_disposition_is_exempt_from_the_iteration_cap",
      "cli_process_context"
    ],
    [
      "test_abort_disposition_is_exempt_from_the_iteration_cap",
      "invoke_cli"
    ],
    [
      "test_abort_disposition_is_exempt_from_the_iteration_cap",
      "start_bound_fast_chain"
    ],
    [
      "test_abort_disposition_preconditions_are_independently_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_abort_disposition_preconditions_are_independently_load_bearing",
      "@state:assertIsNone"
    ],
    [
      "test_abort_disposition_preconditions_are_independently_load_bearing",
      "@state:assertIsNotNone"
    ],
    [
      "test_abort_disposition_preconditions_are_independently_load_bearing",
      "@state:subTest"
    ],
    [
      "test_abort_disposition_reaches_a_dead_in_place_chain",
      "@state:assertEqual"
    ],
    [
      "test_abort_disposition_reaches_a_dead_in_place_chain",
      "@state:events"
    ],
    [
      "test_abort_disposition_reaches_a_dead_in_place_chain",
      "@state:state"
    ],
    [
      "test_abort_disposition_reaches_a_dead_in_place_chain",
      "invoke_cli"
    ],
    [
      "test_abort_disposition_reaches_a_dead_in_place_chain",
      "start_bound_fast_chain"
    ],
    [
      "test_abort_disposition_refuses_a_live_bound_chain",
      "@state:assertEqual"
    ],
    [
      "test_abort_disposition_refuses_a_live_bound_chain",
      "@state:events_path"
    ],
    [
      "test_abort_disposition_refuses_a_live_bound_chain",
      "@state:state"
    ],
    [
      "test_abort_disposition_refuses_a_live_bound_chain",
      "invoke_cli"
    ],
    [
      "test_abort_disposition_refuses_a_live_bound_chain",
      "start_bound_fast_chain"
    ],
    [
      "test_abort_disposition_refuses_an_unbound_aborted_chain",
      "@state:assertEqual"
    ],
    [
      "test_abort_disposition_refuses_an_unbound_aborted_chain",
      "@state:change"
    ],
    [
      "test_abort_disposition_refuses_an_unbound_aborted_chain",
      "@state:events_path"
    ],
    [
      "test_abort_disposition_refuses_an_unbound_aborted_chain",
      "invoke_cli"
    ],
    [
      "test_abort_disposition_refuses_every_ineligible_chain",
      "@state:assertEqual"
    ],
    [
      "test_abort_disposition_refuses_every_ineligible_chain",
      "@state:events_path"
    ],
    [
      "test_abort_disposition_refuses_every_ineligible_chain",
      "invoke_cli"
    ],
    [
      "test_abort_disposition_refuses_every_ineligible_chain",
      "start_bound_fast_chain"
    ],
    [
      "test_abort_disposition_requires_a_chain_id_and_a_readable_journal",
      "@state:assertEqual"
    ],
    [
      "test_abort_disposition_requires_a_chain_id_and_a_readable_journal",
      "@state:events_path"
    ],
    [
      "test_abort_disposition_requires_a_chain_id_and_a_readable_journal",
      "invoke_cli"
    ],
    [
      "test_abort_disposition_requires_a_chain_id_and_a_readable_journal",
      "start_bound_fast_chain"
    ],
    [
      "test_abort_disposition_run_id_must_name_a_readable_chains_bound_run",
      "@state:assertEqual"
    ],
    [
      "test_abort_disposition_run_id_must_name_a_readable_chains_bound_run",
      "@state:assertIn"
    ],
    [
      "test_abort_disposition_run_id_must_name_a_readable_chains_bound_run",
      "@state:events"
    ],
    [
      "test_abort_disposition_run_id_must_name_a_readable_chains_bound_run",
      "@state:repo"
    ],
    [
      "test_abort_disposition_run_id_must_name_a_readable_chains_bound_run",
      "invoke_cli"
    ],
    [
      "test_abort_disposition_run_id_must_name_a_readable_chains_bound_run",
      "start_bound_fast_chain"
    ],
    [
      "test_abort_refuses_landed_chain_and_keeps_its_landing",
      "@state:assertEqual"
    ],
    [
      "test_abort_refuses_landed_chain_and_keeps_its_landing",
      "@state:assertIsNone"
    ],
    [
      "test_abort_refuses_landed_chain_and_keeps_its_landing",
      "@state:events_path"
    ],
    [
      "test_abort_refuses_landed_chain_and_keeps_its_landing",
      "@state:repo"
    ],
    [
      "test_abort_refuses_landed_chain_and_keeps_its_landing",
      "@state:state"
    ],
    [
      "test_abort_refuses_landed_chain_and_keeps_its_landing",
      "cli_process_context"
    ],
    [
      "test_abort_refuses_landed_chain_and_keeps_its_landing",
      "invoke_cli"
    ],
    [
      "test_abort_refuses_landed_chain_and_keeps_its_landing",
      "start_bound_fast_chain"
    ],
    [
      "test_abort_refuses_terminal_chains_before_any_mutation",
      "@state:assertEqual"
    ],
    [
      "test_abort_refuses_terminal_chains_before_any_mutation",
      "@state:events_path"
    ],
    [
      "test_abort_refuses_terminal_chains_before_any_mutation",
      "@state:repo"
    ],
    [
      "test_abort_refuses_terminal_chains_before_any_mutation",
      "@state:state_path"
    ],
    [
      "test_abort_refuses_terminal_chains_before_any_mutation",
      "cli_process_context"
    ],
    [
      "test_abort_refuses_terminal_chains_before_any_mutation",
      "invoke_cli"
    ],
    [
      "test_abort_refuses_terminal_chains_before_any_mutation",
      "start_bound_fast_chain"
    ],
    [
      "test_bound_changelog_output_is_committed_policy_machinery",
      "@state:assertEqual"
    ],
    [
      "test_bound_changelog_output_is_committed_policy_machinery",
      "@state:assertIn"
    ],
    [
      "test_bound_changelog_output_is_committed_policy_machinery",
      "@state:assertTrue"
    ],
    [
      "test_bound_changelog_output_is_committed_policy_machinery",
      "@state:state"
    ],
    [
      "test_bound_changelog_output_is_committed_policy_machinery",
      "configure_changelog_gate"
    ],
    [
      "test_bound_changelog_output_is_committed_policy_machinery",
      "invoke_cli"
    ],
    [
      "test_bound_changelog_output_is_committed_policy_machinery",
      "start_bound_chain"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "@state:assertEqual"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "@state:assertFalse"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "@state:assertNotEqual"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "@state:assertNotIn"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "@state:change"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "@state:events"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "@state:gate_lines"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "@state:helpers"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "@state:repo"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "@state:state"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "cli_process_context"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "invoke_cli"
    ],
    [
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "start_bound_multicell_stack_chain"
    ],
    [
      "test_bound_multicell_stack_journal_deferral_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_bound_multicell_stack_journal_deferral_is_load_bearing",
      "@state:assertIn"
    ],
    [
      "test_bound_multicell_stack_journal_deferral_is_load_bearing",
      "@state:assertNotIn"
    ],
    [
      "test_bound_multicell_stack_journal_deferral_is_load_bearing",
      "@state:gate_lines"
    ],
    [
      "test_bound_multicell_stack_journal_deferral_is_load_bearing",
      "@state:state"
    ],
    [
      "test_bound_multicell_stack_journal_deferral_is_load_bearing",
      "invoke_cli"
    ],
    [
      "test_bound_multicell_stack_journal_deferral_is_load_bearing",
      "start_bound_multicell_stack_chain"
    ],
    [
      "test_bound_multicell_stack_journals_one_completed_batch",
      "@state:assertEqual"
    ],
    [
      "test_bound_multicell_stack_journals_one_completed_batch",
      "@state:events"
    ],
    [
      "test_bound_multicell_stack_journals_one_completed_batch",
      "@state:events_path"
    ],
    [
      "test_bound_multicell_stack_journals_one_completed_batch",
      "@state:gate_lines"
    ],
    [
      "test_bound_multicell_stack_journals_one_completed_batch",
      "@state:gate_log"
    ],
    [
      "test_bound_multicell_stack_journals_one_completed_batch",
      "@state:repo"
    ],
    [
      "test_bound_multicell_stack_journals_one_completed_batch",
      "@state:state"
    ],
    [
      "test_bound_multicell_stack_journals_one_completed_batch",
      "@state:state_path"
    ],
    [
      "test_bound_multicell_stack_journals_one_completed_batch",
      "cli_process_context"
    ],
    [
      "test_bound_multicell_stack_journals_one_completed_batch",
      "invoke_cli"
    ],
    [
      "test_bound_multicell_stack_journals_one_completed_batch",
      "start_bound_multicell_stack_chain"
    ],
    [
      "test_bound_non_changelog_output_still_names_out_of_scope_path",
      "@state:assertEqual"
    ],
    [
      "test_bound_non_changelog_output_still_names_out_of_scope_path",
      "@state:assertIn"
    ],
    [
      "test_bound_non_changelog_output_still_names_out_of_scope_path",
      "@state:change"
    ],
    [
      "test_bound_non_changelog_output_still_names_out_of_scope_path",
      "configure_changelog_gate"
    ],
    [
      "test_bound_non_changelog_output_still_names_out_of_scope_path",
      "invoke_cli"
    ],
    [
      "test_bound_non_changelog_output_still_names_out_of_scope_path",
      "open_run_and_task"
    ],
    [
      "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "@state:assertEqual"
    ],
    [
      "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "@state:assertFalse"
    ],
    [
      "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "@state:assertIsNotNone"
    ],
    [
      "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "@state:assertNotEqual"
    ],
    [
      "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "@state:assertRaisesRegex"
    ],
    [
      "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "@state:events_path"
    ],
    [
      "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "@state:repo"
    ],
    [
      "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "@state:state_path"
    ],
    [
      "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "cli_process_context"
    ],
    [
      "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "start_bound_chain"
    ],
    [
      "test_bound_start_persists_exact_immutable_binding",
      "@state:assertEqual"
    ],
    [
      "test_bound_start_persists_exact_immutable_binding",
      "@state:assertIs"
    ],
    [
      "test_bound_start_persists_exact_immutable_binding",
      "@state:assertIsNone"
    ],
    [
      "test_bound_start_persists_exact_immutable_binding",
      "@state:events"
    ],
    [
      "test_bound_start_persists_exact_immutable_binding",
      "@state:repo"
    ],
    [
      "test_bound_start_persists_exact_immutable_binding",
      "@state:state"
    ],
    [
      "test_bound_start_persists_exact_immutable_binding",
      "start_bound_chain"
    ],
    [
      "test_captured_commit_and_merge_sources_reopen_from_the_run_root",
      "@state:assertEqual"
    ],
    [
      "test_captured_commit_and_merge_sources_reopen_from_the_run_root",
      "@state:assertRaisesRegex"
    ],
    [
      "test_captured_commit_and_merge_sources_reopen_from_the_run_root",
      "@state:repo"
    ],
    [
      "test_captured_commit_and_merge_sources_reopen_from_the_run_root",
      "@state:subTest"
    ],
    [
      "test_captured_commit_and_merge_sources_reopen_from_the_run_root",
      "cli_process_context"
    ],
    [
      "test_captured_commit_and_merge_sources_reopen_from_the_run_root",
      "open_run_and_task"
    ],
    [
      "test_captured_source_substitution_before_builder_keeps_exact_diagnostic",
      "@state:assertEqual"
    ],
    [
      "test_captured_source_substitution_before_builder_keeps_exact_diagnostic",
      "@state:assertFalse"
    ],
    [
      "test_captured_source_substitution_before_builder_keeps_exact_diagnostic",
      "@state:assertTrue"
    ],
    [
      "test_captured_source_substitution_before_builder_keeps_exact_diagnostic",
      "invoke_cli"
    ],
    [
      "test_captured_source_substitution_before_builder_keeps_exact_diagnostic",
      "prepare_unbound_fast_ingest"
    ],
    [
      "test_captured_source_substitution_before_intent_refuses_without_append",
      "@state:assertEqual"
    ],
    [
      "test_captured_source_substitution_before_intent_refuses_without_append",
      "@state:assertFalse"
    ],
    [
      "test_captured_source_substitution_before_intent_refuses_without_append",
      "@state:assertTrue"
    ],
    [
      "test_captured_source_substitution_before_intent_refuses_without_append",
      "invoke_cli"
    ],
    [
      "test_captured_source_substitution_before_intent_refuses_without_append",
      "prepare_unbound_fast_ingest"
    ],
    [
      "test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
      "@state:assertEqual"
    ],
    [
      "test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
      "@state:assertFalse"
    ],
    [
      "test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
      "@state:assertRaises"
    ],
    [
      "test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
      "@state:assertRaisesRegex"
    ],
    [
      "test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
      "@state:assertTrue"
    ],
    [
      "test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
      "@state:repo"
    ],
    [
      "test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
      "@state:subTest"
    ],
    [
      "test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
      "cli_process_context"
    ],
    [
      "test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
      "start_bound_fast_chain"
    ],
    [
      "test_commit_activation_rejects_event_one_rebinding_before_replay",
      "@state:assertEqual"
    ],
    [
      "test_commit_activation_rejects_event_one_rebinding_before_replay",
      "@state:assertIsInstance"
    ],
    [
      "test_commit_activation_rejects_event_one_rebinding_before_replay",
      "@state:assertRaises"
    ],
    [
      "test_commit_activation_rejects_event_one_rebinding_before_replay",
      "@state:change"
    ],
    [
      "test_commit_activation_rejects_event_one_rebinding_before_replay",
      "@state:repo"
    ],
    [
      "test_commit_activation_rejects_event_one_rebinding_before_replay",
      "@state:state"
    ],
    [
      "test_commit_activation_rejects_event_one_rebinding_before_replay",
      "invoke_cli"
    ],
    [
      "test_commit_activation_rejects_event_one_rebinding_before_replay",
      "open_run_and_task"
    ],
    [
      "test_commit_identity_carrier_pre_drain_crash_replays_once",
      "assert_commit_identity_drain_crash_replays_once"
    ],
    [
      "test_commit_identity_journal_append_crash_replays_once",
      "assert_commit_identity_drain_crash_replays_once"
    ],
    [
      "test_commit_identity_receipt_append_crash_replays_once",
      "assert_commit_identity_drain_crash_replays_once"
    ],
    [
      "test_each_ingest_proof_control_refuses_at_its_named_boundary",
      "@state:assertEqual"
    ],
    [
      "test_each_ingest_proof_control_refuses_at_its_named_boundary",
      "@state:assertFalse"
    ],
    [
      "test_each_ingest_proof_control_refuses_at_its_named_boundary",
      "@state:assertRaises"
    ],
    [
      "test_each_ingest_proof_control_refuses_at_its_named_boundary",
      "@state:assertTrue"
    ],
    [
      "test_each_ingest_proof_control_refuses_at_its_named_boundary",
      "@state:repo"
    ],
    [
      "test_each_ingest_proof_control_refuses_at_its_named_boundary",
      "@state:subTest"
    ],
    [
      "test_each_ingest_proof_control_refuses_at_its_named_boundary",
      "prepare_unbound_fast_ingest"
    ],
    [
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "@state:assertEqual"
    ],
    [
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "@state:assertIsInstance"
    ],
    [
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "@state:assertIsNone"
    ],
    [
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "@state:assertNotIn"
    ],
    [
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "@state:assertRaisesRegex"
    ],
    [
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "@state:assertTrue"
    ],
    [
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "@state:events"
    ],
    [
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "@state:repo"
    ],
    [
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "@state:state"
    ],
    [
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "cli_process_context"
    ],
    [
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "start_bound_chain"
    ],
    [
      "test_existing_chain_batch_lock_skips_creation_only_validation",
      "@state:assertEqual"
    ],
    [
      "test_existing_chain_batch_lock_skips_creation_only_validation",
      "@state:repo"
    ],
    [
      "test_existing_chain_batch_lock_skips_creation_only_validation",
      "cli_process_context"
    ],
    [
      "test_existing_chain_batch_lock_skips_creation_only_validation",
      "open_run_and_task"
    ],
    [
      "test_existing_locked_bound_start_preserves_foreign_owner_behavior",
      "@state:assertEqual"
    ],
    [
      "test_existing_locked_bound_start_preserves_foreign_owner_behavior",
      "@state:assertTrue"
    ],
    [
      "test_existing_locked_bound_start_preserves_foreign_owner_behavior",
      "@state:change"
    ],
    [
      "test_existing_locked_bound_start_preserves_foreign_owner_behavior",
      "@state:repo"
    ],
    [
      "test_existing_locked_bound_start_preserves_foreign_owner_behavior",
      "invoke_cli"
    ],
    [
      "test_existing_locked_bound_start_preserves_foreign_owner_behavior",
      "open_run_and_task"
    ],
    [
      "test_existing_locked_bound_start_succeeds_without_session_pid",
      "@state:assertEqual"
    ],
    [
      "test_existing_locked_bound_start_succeeds_without_session_pid",
      "@state:assertTrue"
    ],
    [
      "test_existing_locked_bound_start_succeeds_without_session_pid",
      "@state:change"
    ],
    [
      "test_existing_locked_bound_start_succeeds_without_session_pid",
      "@state:helpers"
    ],
    [
      "test_existing_locked_bound_start_succeeds_without_session_pid",
      "@state:repo"
    ],
    [
      "test_existing_locked_bound_start_succeeds_without_session_pid",
      "open_run_and_task"
    ],
    [
      "test_existing_locked_bound_start_succeeds_without_session_pid",
      "revision9_environment"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "@state:assertEqual"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "@state:assertFalse"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "@state:assertGreater"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "@state:assertIn"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "@state:assertIsNone"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "@state:assertRaisesRegex"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "@state:assertTrue"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "@state:events"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "@state:repo"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "@state:state_path"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "cli_process_context"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "invoke_cli"
    ],
    [
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "start_bound_fast_chain"
    ],
    [
      "test_failed_ingest_proof_captures_but_never_references_or_mutates_journal",
      "@state:assertEqual"
    ],
    [
      "test_failed_ingest_proof_captures_but_never_references_or_mutates_journal",
      "@state:assertFalse"
    ],
    [
      "test_failed_ingest_proof_captures_but_never_references_or_mutates_journal",
      "@state:assertNotIn"
    ],
    [
      "test_failed_ingest_proof_captures_but_never_references_or_mutates_journal",
      "@state:git"
    ],
    [
      "test_failed_ingest_proof_captures_but_never_references_or_mutates_journal",
      "@state:repo"
    ],
    [
      "test_failed_ingest_proof_captures_but_never_references_or_mutates_journal",
      "invoke_cli"
    ],
    [
      "test_failed_ingest_proof_captures_but_never_references_or_mutates_journal",
      "open_run_and_task"
    ],
    [
      "test_fast_mechanical_skip_is_rejected_at_current_gates_proof",
      "@state:assertEqual"
    ],
    [
      "test_fast_mechanical_skip_is_rejected_at_current_gates_proof",
      "@state:assertFalse"
    ],
    [
      "test_fast_mechanical_skip_is_rejected_at_current_gates_proof",
      "@state:assertRaises"
    ],
    [
      "test_fast_mechanical_skip_is_rejected_at_current_gates_proof",
      "@state:repo"
    ],
    [
      "test_fast_mechanical_skip_is_rejected_at_current_gates_proof",
      "prepare_unbound_fast_ingest"
    ],
    [
      "test_fresh_key_cannot_replay_typed_verification_or_decision_binding",
      "@state:assertEqual"
    ],
    [
      "test_fresh_key_cannot_replay_typed_verification_or_decision_binding",
      "@state:assertFalse"
    ],
    [
      "test_fresh_key_cannot_replay_typed_verification_or_decision_binding",
      "@state:assertRaises"
    ],
    [
      "test_fresh_key_cannot_replay_typed_verification_or_decision_binding",
      "@state:repo"
    ],
    [
      "test_fresh_key_cannot_replay_typed_verification_or_decision_binding",
      "@state:subTest"
    ],
    [
      "test_fresh_key_cannot_replay_typed_verification_or_decision_binding",
      "cli_process_context"
    ],
    [
      "test_fresh_key_cannot_replay_typed_verification_or_decision_binding",
      "open_run_and_task"
    ],
    [
      "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "@state:assertEqual"
    ],
    [
      "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "@state:assertFalse"
    ],
    [
      "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "@state:assertRaisesRegex"
    ],
    [
      "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "@state:assertTrue"
    ],
    [
      "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "@state:events_path"
    ],
    [
      "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "@state:repo"
    ],
    [
      "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "@state:state_path"
    ],
    [
      "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "cli_process_context"
    ],
    [
      "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "invoke_cli"
    ],
    [
      "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "start_bound_chain"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "@state:assertEqual"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "@state:assertNotEqual"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "@state:assertTrue"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "@state:change"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "@state:events"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "@state:events_path"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "@state:repo"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "@state:state"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "@state:state_path"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "cli_process_context"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "invoke_cli"
    ],
    [
      "test_historical_receipted_binding_replays_after_restage",
      "start_bound_chain"
    ],
    [
      "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "@state:assertEqual"
    ],
    [
      "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "@state:assertFalse"
    ],
    [
      "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "@state:assertIsInstance"
    ],
    [
      "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "@state:assertNotEqual"
    ],
    [
      "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "@state:change"
    ],
    [
      "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "@state:events"
    ],
    [
      "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "@state:repo"
    ],
    [
      "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "@state:state"
    ],
    [
      "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "invoke_cli"
    ],
    [
      "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "open_run_and_task"
    ],
    [
      "test_legacy_first_use_chain_receipt_bootstrap_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_legacy_first_use_chain_receipt_bootstrap_is_load_bearing",
      "@state:assertFalse"
    ],
    [
      "test_legacy_first_use_chain_receipt_bootstrap_is_load_bearing",
      "@state:assertIsNone"
    ],
    [
      "test_legacy_first_use_chain_receipt_bootstrap_is_load_bearing",
      "@state:change"
    ],
    [
      "test_legacy_first_use_chain_receipt_bootstrap_is_load_bearing",
      "@state:repo"
    ],
    [
      "test_legacy_first_use_chain_receipt_bootstrap_is_load_bearing",
      "@state:state"
    ],
    [
      "test_legacy_first_use_chain_receipt_bootstrap_is_load_bearing",
      "invoke_cli"
    ],
    [
      "test_legacy_first_use_chain_receipt_bootstrap_is_load_bearing",
      "open_run_and_task"
    ],
    [
      "test_legacy_run_ingest_allocation_projection_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_legacy_run_ingest_allocation_projection_is_load_bearing",
      "@state:assertFalse"
    ],
    [
      "test_legacy_run_ingest_allocation_projection_is_load_bearing",
      "@state:assertGreaterEqual"
    ],
    [
      "test_legacy_run_ingest_allocation_projection_is_load_bearing",
      "@state:repo"
    ],
    [
      "test_legacy_run_ingest_allocation_projection_is_load_bearing",
      "cli_process_context"
    ],
    [
      "test_legacy_run_ingest_allocation_projection_is_load_bearing",
      "prepare_unbound_fast_ingest"
    ],
    [
      "test_legacy_run_ingest_first_typed_use_activates_once_and_is_receipted",
      "@state:assertEqual"
    ],
    [
      "test_legacy_run_ingest_first_typed_use_activates_once_and_is_receipted",
      "@state:assertFalse"
    ],
    [
      "test_legacy_run_ingest_first_typed_use_activates_once_and_is_receipted",
      "@state:assertTrue"
    ],
    [
      "test_legacy_run_ingest_first_typed_use_activates_once_and_is_receipted",
      "invoke_cli"
    ],
    [
      "test_legacy_run_ingest_first_typed_use_activates_once_and_is_receipted",
      "normalized_journal_records"
    ],
    [
      "test_legacy_run_ingest_first_typed_use_activates_once_and_is_receipted",
      "prepare_unbound_fast_ingest"
    ],
    [
      "test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive",
      "@state:assertEqual"
    ],
    [
      "test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive",
      "@state:assertFalse"
    ],
    [
      "test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive",
      "@state:assertTrue"
    ],
    [
      "test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive",
      "@state:git"
    ],
    [
      "test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive",
      "@state:repo"
    ],
    [
      "test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive",
      "@state:temp_root"
    ],
    [
      "test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive",
      "cli_process_context"
    ],
    [
      "test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive",
      "invoke_cli_at"
    ],
    [
      "test_lockless_bound_start_creation_control_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_lockless_bound_start_creation_control_is_load_bearing",
      "@state:assertFalse"
    ],
    [
      "test_lockless_bound_start_creation_control_is_load_bearing",
      "@state:change"
    ],
    [
      "test_lockless_bound_start_creation_control_is_load_bearing",
      "@state:git"
    ],
    [
      "test_lockless_bound_start_creation_control_is_load_bearing",
      "@state:repo"
    ],
    [
      "test_lockless_bound_start_creation_control_is_load_bearing",
      "invoke_cli"
    ],
    [
      "test_lockless_bound_start_creation_control_is_load_bearing",
      "open_run_and_task"
    ],
    [
      "test_lockless_bound_start_halt_precedes_stable_lock_creation",
      "@state:assertEqual"
    ],
    [
      "test_lockless_bound_start_halt_precedes_stable_lock_creation",
      "@state:assertFalse"
    ],
    [
      "test_lockless_bound_start_halt_precedes_stable_lock_creation",
      "@state:change"
    ],
    [
      "test_lockless_bound_start_halt_precedes_stable_lock_creation",
      "@state:git"
    ],
    [
      "test_lockless_bound_start_halt_precedes_stable_lock_creation",
      "@state:helpers"
    ],
    [
      "test_lockless_bound_start_halt_precedes_stable_lock_creation",
      "@state:repo"
    ],
    [
      "test_lockless_bound_start_halt_precedes_stable_lock_creation",
      "invoke_cli"
    ],
    [
      "test_lockless_bound_start_halt_precedes_stable_lock_creation",
      "open_run_and_task"
    ],
    [
      "test_lockless_bound_start_refuses_foreign_owner_without_creating_lock",
      "@state:assertEqual"
    ],
    [
      "test_lockless_bound_start_refuses_foreign_owner_without_creating_lock",
      "@state:assertFalse"
    ],
    [
      "test_lockless_bound_start_refuses_foreign_owner_without_creating_lock",
      "@state:change"
    ],
    [
      "test_lockless_bound_start_refuses_foreign_owner_without_creating_lock",
      "@state:git"
    ],
    [
      "test_lockless_bound_start_refuses_foreign_owner_without_creating_lock",
      "@state:repo"
    ],
    [
      "test_lockless_bound_start_refuses_foreign_owner_without_creating_lock",
      "invoke_cli"
    ],
    [
      "test_lockless_bound_start_refuses_foreign_owner_without_creating_lock",
      "open_run_and_task"
    ],
    [
      "test_lockless_bound_start_refuses_nonexistent_run_without_creating_it",
      "@state:assertEqual"
    ],
    [
      "test_lockless_bound_start_refuses_nonexistent_run_without_creating_it",
      "@state:assertFalse"
    ],
    [
      "test_lockless_bound_start_refuses_nonexistent_run_without_creating_it",
      "@state:change"
    ],
    [
      "test_lockless_bound_start_refuses_nonexistent_run_without_creating_it",
      "@state:git"
    ],
    [
      "test_lockless_bound_start_refuses_nonexistent_run_without_creating_it",
      "@state:repo"
    ],
    [
      "test_lockless_bound_start_refuses_nonexistent_run_without_creating_it",
      "invoke_cli"
    ],
    [
      "test_lockless_bound_start_refuses_other_worktree_without_creating_lock",
      "@state:assertEqual"
    ],
    [
      "test_lockless_bound_start_refuses_other_worktree_without_creating_lock",
      "@state:assertFalse"
    ],
    [
      "test_lockless_bound_start_refuses_other_worktree_without_creating_lock",
      "@state:git"
    ],
    [
      "test_lockless_bound_start_refuses_other_worktree_without_creating_lock",
      "@state:git_at"
    ],
    [
      "test_lockless_bound_start_refuses_other_worktree_without_creating_lock",
      "@state:repo"
    ],
    [
      "test_lockless_bound_start_refuses_other_worktree_without_creating_lock",
      "@state:temp_root"
    ],
    [
      "test_lockless_bound_start_refuses_other_worktree_without_creating_lock",
      "invoke_cli_at"
    ],
    [
      "test_lockless_bound_start_refuses_other_worktree_without_creating_lock",
      "open_run_and_task"
    ],
    [
      "test_lockless_chain_batch_creation_revalidates_in_lock_order",
      "@state:assertEqual"
    ],
    [
      "test_lockless_chain_batch_creation_revalidates_in_lock_order",
      "@state:assertTrue"
    ],
    [
      "test_lockless_chain_batch_creation_revalidates_in_lock_order",
      "@state:repo"
    ],
    [
      "test_lockless_chain_batch_creation_revalidates_in_lock_order",
      "cli_process_context"
    ],
    [
      "test_lockless_chain_batch_creation_revalidates_in_lock_order",
      "open_run_and_task"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "@state:assertEqual"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "@state:assertFalse"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "@state:assertGreaterEqual"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "@state:assertIsNone"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "@state:assertTrue"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "@state:change"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "@state:repo"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "@state:state"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "@state:wait_for_review_completion"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "cli_process_context"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "invoke_cli"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "normalized_journal_records"
    ],
    [
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
      "open_run_and_task"
    ],
    [
      "test_lockless_merge_start_binding_creates_stable_batch_lock",
      "@state:assertEqual"
    ],
    [
      "test_lockless_merge_start_binding_creates_stable_batch_lock",
      "@state:assertTrue"
    ],
    [
      "test_lockless_merge_start_binding_creates_stable_batch_lock",
      "@state:repo"
    ],
    [
      "test_lockless_merge_start_binding_creates_stable_batch_lock",
      "cli_process_context"
    ],
    [
      "test_lockless_merge_start_binding_creates_stable_batch_lock",
      "open_run_and_task"
    ],
    [
      "test_lockless_read_only_binding_validator_does_not_create_batch_lock",
      "@state:assertEqual"
    ],
    [
      "test_lockless_read_only_binding_validator_does_not_create_batch_lock",
      "@state:assertFalse"
    ],
    [
      "test_lockless_read_only_binding_validator_does_not_create_batch_lock",
      "@state:assertRaises"
    ],
    [
      "test_lockless_read_only_binding_validator_does_not_create_batch_lock",
      "@state:repo"
    ],
    [
      "test_lockless_read_only_binding_validator_does_not_create_batch_lock",
      "cli_process_context"
    ],
    [
      "test_lockless_read_only_binding_validator_does_not_create_batch_lock",
      "open_run_and_task"
    ],
    [
      "test_operator_tombstone_admits_absent_chain_and_refuses_healthy_chain",
      "@state:assertEqual"
    ],
    [
      "test_operator_tombstone_admits_absent_chain_and_refuses_healthy_chain",
      "@state:assertFalse"
    ],
    [
      "test_operator_tombstone_admits_absent_chain_and_refuses_healthy_chain",
      "@state:assertIn"
    ],
    [
      "test_operator_tombstone_admits_absent_chain_and_refuses_healthy_chain",
      "@state:change"
    ],
    [
      "test_operator_tombstone_admits_absent_chain_and_refuses_healthy_chain",
      "@state:repo"
    ],
    [
      "test_operator_tombstone_admits_absent_chain_and_refuses_healthy_chain",
      "invoke_cli"
    ],
    [
      "test_real_unbound_fast_chain_ingests_and_receipted_retry_skips_reproof",
      "@state:assertEqual"
    ],
    [
      "test_real_unbound_fast_chain_ingests_and_receipted_retry_skips_reproof",
      "@state:assertFalse"
    ],
    [
      "test_real_unbound_fast_chain_ingests_and_receipted_retry_skips_reproof",
      "@state:assertIn"
    ],
    [
      "test_real_unbound_fast_chain_ingests_and_receipted_retry_skips_reproof",
      "@state:assertTrue"
    ],
    [
      "test_real_unbound_fast_chain_ingests_and_receipted_retry_skips_reproof",
      "invoke_cli"
    ],
    [
      "test_real_unbound_fast_chain_ingests_and_receipted_retry_skips_reproof",
      "normalized_journal_records"
    ],
    [
      "test_real_unbound_fast_chain_ingests_and_receipted_retry_skips_reproof",
      "prepare_unbound_fast_ingest"
    ],
    [
      "test_real_unbound_multicell_stack_ingest_keeps_every_head_record",
      "@state:assertEqual"
    ],
    [
      "test_real_unbound_multicell_stack_ingest_keeps_every_head_record",
      "@state:repo"
    ],
    [
      "test_real_unbound_multicell_stack_ingest_keeps_every_head_record",
      "invoke_cli"
    ],
    [
      "test_real_unbound_multicell_stack_ingest_keeps_every_head_record",
      "normalized_journal_records"
    ],
    [
      "test_real_unbound_multicell_stack_ingest_keeps_every_head_record",
      "prepare_unbound_fast_ingest"
    ],
    [
      "test_receipted_commit_produced_crash_recovers_one_landing",
      "@state:assertEqual"
    ],
    [
      "test_receipted_commit_produced_crash_recovers_one_landing",
      "@state:assertIsNone"
    ],
    [
      "test_receipted_commit_produced_crash_recovers_one_landing",
      "@state:assertRaisesRegex"
    ],
    [
      "test_receipted_commit_produced_crash_recovers_one_landing",
      "@state:events"
    ],
    [
      "test_receipted_commit_produced_crash_recovers_one_landing",
      "@state:git"
    ],
    [
      "test_receipted_commit_produced_crash_recovers_one_landing",
      "@state:repo"
    ],
    [
      "test_receipted_commit_produced_crash_recovers_one_landing",
      "@state:state"
    ],
    [
      "test_receipted_commit_produced_crash_recovers_one_landing",
      "cli_process_context"
    ],
    [
      "test_receipted_commit_produced_crash_recovers_one_landing",
      "invoke_cli"
    ],
    [
      "test_receipted_commit_produced_crash_recovers_one_landing",
      "start_bound_fast_chain"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "@state:assertEqual"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "@state:assertFalse"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "@state:assertIsNone"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "@state:assertNotEqual"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "@state:assertNotIn"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "@state:assertTrue"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "@state:events"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "@state:events_path"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "@state:repo"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "@state:state"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "cli_process_context"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "invoke_cli"
    ],
    [
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "start_bound_fast_chain"
    ],
    [
      "test_start_lock_disappearance_never_recreates_before_halt",
      "@state:assertEqual"
    ],
    [
      "test_start_lock_disappearance_never_recreates_before_halt",
      "@state:assertFalse"
    ],
    [
      "test_start_lock_disappearance_never_recreates_before_halt",
      "@state:assertTrue"
    ],
    [
      "test_start_lock_disappearance_never_recreates_before_halt",
      "@state:change"
    ],
    [
      "test_start_lock_disappearance_never_recreates_before_halt",
      "@state:git"
    ],
    [
      "test_start_lock_disappearance_never_recreates_before_halt",
      "@state:helpers"
    ],
    [
      "test_start_lock_disappearance_never_recreates_before_halt",
      "@state:repo"
    ],
    [
      "test_start_lock_disappearance_never_recreates_before_halt",
      "invoke_cli"
    ],
    [
      "test_start_lock_disappearance_never_recreates_before_halt",
      "open_run_and_task"
    ],
    [
      "test_task_finish_inspects_only_the_finishing_tasks_chains",
      "@state:assertEqual"
    ],
    [
      "test_task_finish_inspects_only_the_finishing_tasks_chains",
      "@state:assertRaisesRegex"
    ],
    [
      "test_task_finish_inspects_only_the_finishing_tasks_chains",
      "@state:change"
    ],
    [
      "test_task_finish_inspects_only_the_finishing_tasks_chains",
      "@state:git"
    ],
    [
      "test_task_finish_inspects_only_the_finishing_tasks_chains",
      "@state:repo"
    ],
    [
      "test_task_finish_inspects_only_the_finishing_tasks_chains",
      "cli_process_context"
    ],
    [
      "test_task_finish_inspects_only_the_finishing_tasks_chains",
      "invoke_cli"
    ],
    [
      "test_task_finish_inspects_only_the_finishing_tasks_chains",
      "start_bound_chain"
    ],
    [
      "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "@state:assertRaises"
    ],
    [
      "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "@state:assertTrue"
    ],
    [
      "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "@state:repo"
    ],
    [
      "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "@state:subTest"
    ],
    [
      "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "_journal_records"
    ],
    [
      "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "_quarantine_and_tombstone"
    ],
    [
      "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "cli_process_context"
    ],
    [
      "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "invoke_cli"
    ],
    [
      "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "start_bound_fast_chain"
    ],
    [
      "test_tombstone_disposition_refuses_a_nonexistent_run_before_any_lock",
      "@state:assertEqual"
    ],
    [
      "test_tombstone_disposition_refuses_a_nonexistent_run_before_any_lock",
      "@state:assertFalse"
    ],
    [
      "test_tombstone_disposition_refuses_a_nonexistent_run_before_any_lock",
      "@state:repo"
    ],
    [
      "test_tombstone_disposition_refuses_a_nonexistent_run_before_any_lock",
      "_quarantine_and_tombstone"
    ],
    [
      "test_tombstone_disposition_refuses_a_nonexistent_run_before_any_lock",
      "invoke_cli"
    ],
    [
      "test_tombstone_disposition_refuses_a_nonexistent_run_before_any_lock",
      "start_bound_fast_chain"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "@state:assertEqual"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "@state:assertFalse"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "@state:assertGreater"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "@state:assertGreaterEqual"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "@state:assertNotEqual"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "@state:assertRaises"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "@state:assertTrue"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "@state:repo"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "@state:subTest"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "_journal_records"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "_quarantine_and_tombstone"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "cli_process_context"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "invoke_cli"
    ],
    [
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "start_bound_fast_chain"
    ],
    [
      "test_tombstone_publication_recovers_only_authenticated_temp_alias",
      "@state:assertEqual"
    ],
    [
      "test_tombstone_publication_recovers_only_authenticated_temp_alias",
      "@state:assertFalse"
    ],
    [
      "test_tombstone_publication_recovers_only_authenticated_temp_alias",
      "@state:assertIn"
    ],
    [
      "test_tombstone_publication_recovers_only_authenticated_temp_alias",
      "@state:assertTrue"
    ],
    [
      "test_tombstone_publication_recovers_only_authenticated_temp_alias",
      "@state:repo"
    ],
    [
      "test_tombstone_publication_recovers_only_authenticated_temp_alias",
      "invoke_cli"
    ],
    [
      "test_tombstone_publication_retries_prelink_and_postunlink_failures",
      "@state:assertEqual"
    ],
    [
      "test_tombstone_publication_retries_prelink_and_postunlink_failures",
      "@state:assertFalse"
    ],
    [
      "test_tombstone_publication_retries_prelink_and_postunlink_failures",
      "@state:assertIn"
    ],
    [
      "test_tombstone_publication_retries_prelink_and_postunlink_failures",
      "@state:assertNotIn"
    ],
    [
      "test_tombstone_publication_retries_prelink_and_postunlink_failures",
      "@state:assertRaisesRegex"
    ],
    [
      "test_tombstone_publication_retries_prelink_and_postunlink_failures",
      "@state:assertTrue"
    ],
    [
      "test_tombstone_publication_retries_prelink_and_postunlink_failures",
      "@state:repo"
    ],
    [
      "test_tombstone_publication_retries_prelink_and_postunlink_failures",
      "cli_process_context"
    ]
  ],
  "clusters": [
    [
      "revision9_environment",
      "test_existing_locked_bound_start_succeeds_without_session_pid"
    ],
    [
      "invoke_cli_at",
      "test_lockless_bound_start_refuses_other_worktree_without_creating_lock",
      "test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive"
    ],
    [
      "start_bound_chain",
      "configure_changelog_gate",
      "test_bound_changelog_output_is_committed_policy_machinery",
      "test_bound_non_changelog_output_still_names_out_of_scope_path",
      "test_captured_commit_and_merge_sources_reopen_from_the_run_root",
      "test_each_ingest_proof_control_refuses_at_its_named_boundary",
      "test_fast_mechanical_skip_is_rejected_at_current_gates_proof",
      "test_legacy_first_use_chain_receipt_bootstrap_is_load_bearing",
      "test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
      "test_commit_activation_rejects_event_one_rebinding_before_replay",
      "test_lockless_read_only_binding_validator_does_not_create_batch_lock",
      "test_bound_start_persists_exact_immutable_binding",
      "test_fresh_key_cannot_replay_typed_verification_or_decision_binding",
      "test_historical_receipted_binding_replays_after_restage",
      "test_frozen_abort_writes_explicit_tombstone_without_replay",
      "test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
      "test_abort_refuses_terminal_chains_before_any_mutation",
      "test_abort_refuses_landed_chain_and_keeps_its_landing",
      "test_retrospective_abort_disposition_carries_the_decision_once",
      "_quarantine_and_tombstone",
      "_journal_records",
      "test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
      "test_tombstone_disposition_refuses_a_nonexistent_run_before_any_lock",
      "test_abort_disposition_run_id_must_name_a_readable_chains_bound_run",
      "test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
      "test_abort_disposition_refuses_every_ineligible_chain",
      "test_abort_disposition_preconditions_are_independently_load_bearing",
      "test_abort_disposition_is_exempt_from_the_iteration_cap",
      "test_abort_disposition_requires_a_chain_id_and_a_readable_journal",
      "test_abort_disposition_refuses_a_live_bound_chain",
      "test_abort_disposition_refuses_an_unbound_aborted_chain",
      "test_task_finish_inspects_only_the_finishing_tasks_chains",
      "test_operator_tombstone_admits_absent_chain_and_refuses_healthy_chain",
      "test_tombstone_publication_recovers_only_authenticated_temp_alias",
      "test_tombstone_publication_retries_prelink_and_postunlink_failures",
      "test_bound_replay_refuses_noncanonical_event_without_state_repair",
      "test_event_carrier_survives_drain_crash_and_replays_once",
      "assert_commit_identity_drain_crash_replays_once",
      "test_commit_identity_carrier_pre_drain_crash_replays_once",
      "test_commit_identity_journal_append_crash_replays_once",
      "test_commit_identity_receipt_append_crash_replays_once",
      "test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
      "test_receipted_commit_produced_crash_recovers_one_landing"
    ],
    [
      "start_bound_multicell_stack_chain",
      "test_bound_multicell_stack_journals_one_completed_batch",
      "test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
      "test_bound_multicell_stack_journal_deferral_is_load_bearing",
      "test_legacy_run_ingest_allocation_projection_is_load_bearing",
      "test_failed_ingest_proof_captures_but_never_references_or_mutates_journal"
    ],
    [
      "selected_commit_ingest_event_digests",
      "normalized_journal_records",
      "prepare_unbound_fast_ingest",
      "test_real_unbound_fast_chain_ingests_and_receipted_retry_skips_reproof",
      "test_real_unbound_multicell_stack_ingest_keeps_every_head_record",
      "test_legacy_run_ingest_first_typed_use_activates_once_and_is_receipted",
      "test_captured_source_substitution_before_intent_refuses_without_append",
      "test_captured_source_substitution_before_builder_keeps_exact_diagnostic",
      "test_lockless_legacy_bound_chain_activates_and_lands_cleanly"
    ],
    [
      "test_lockless_bound_start_refuses_nonexistent_run_without_creating_it"
    ],
    [
      "test_lockless_bound_start_halt_precedes_stable_lock_creation",
      "test_start_lock_disappearance_never_recreates_before_halt"
    ],
    [
      "test_lockless_bound_start_refuses_foreign_owner_without_creating_lock"
    ],
    [
      "test_lockless_bound_start_creation_control_is_load_bearing"
    ],
    [
      "test_lockless_chain_batch_creation_revalidates_in_lock_order"
    ],
    [
      "test_existing_chain_batch_lock_skips_creation_only_validation"
    ],
    [
      "test_existing_locked_bound_start_preserves_foreign_owner_behavior"
    ],
    [
      "test_lockless_merge_start_binding_creates_stable_batch_lock"
    ],
    [
      "test_abort_disposition_reaches_a_dead_in_place_chain"
    ],
    [
      "invoke_cli"
    ],
    [
      "cli_process_context"
    ],
    [
      "open_run_and_task"
    ],
    [
      "start_bound_fast_chain"
    ]
  ],
  "hubs": [
    "@state:assertEqual",
    "@state:repo",
    "invoke_cli",
    "@state:assertFalse",
    "cli_process_context",
    "@state:assertTrue",
    "open_run_and_task",
    "@state:change",
    "@state:state",
    "start_bound_fast_chain",
    "@state:git",
    "@state:events"
  ],
  "prerequisites": [
    {
      "name": "ROOT",
      "line": 24,
      "users": [
        {
          "method": "Revision9BoundCLIIntegrationTests.cli_process_context",
          "line": 1259
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_existing_locked_bound_start_succeeds_without_session_pid",
          "line": 3590
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "ENVELOPE_KEYS",
      "line": 26,
      "users": [
        {
          "method": "Revision9BoundCLIIntegrationTests.invoke_cli_at",
          "line": 1274
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "CLI",
      "line": 44,
      "users": [
        {
          "method": "Revision9BoundCLIIntegrationTests.invoke_cli_at",
          "line": 1274
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.open_run_and_task",
          "line": 1291
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_bound_multicell_stack_journals_one_completed_batch",
          "line": 1469
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_bound_multicell_stack_failure_journals_failed_cell_and_stops",
          "line": 1616
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.selected_commit_ingest_event_digests",
          "line": 1979
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.prepare_unbound_fast_ingest",
          "line": 2055
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_real_unbound_fast_chain_ingests_and_receipted_retry_skips_reproof",
          "line": 2314
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_real_unbound_multicell_stack_ingest_keeps_every_head_record",
          "line": 2429
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_legacy_run_ingest_first_typed_use_activates_once_and_is_receipted",
          "line": 2536
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_legacy_run_ingest_allocation_projection_is_load_bearing",
          "line": 2587
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_captured_commit_and_merge_sources_reopen_from_the_run_root",
          "line": 2645
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_captured_source_substitution_before_intent_refuses_without_append",
          "line": 2696
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_captured_source_substitution_before_builder_keeps_exact_diagnostic",
          "line": 2742
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_each_ingest_proof_control_refuses_at_its_named_boundary",
          "line": 2789
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_fast_mechanical_skip_is_rejected_at_current_gates_proof",
          "line": 2851
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
          "line": 2892
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_bound_start_halt_precedes_stable_lock_creation",
          "line": 3051
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_start_lock_disappearance_never_recreates_before_halt",
          "line": 3101
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_legacy_first_use_chain_receipt_bootstrap_is_load_bearing",
          "line": 3154
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_legacy_first_use_chain_prevalidation_is_load_bearing_in_memory",
          "line": 3229
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_commit_activation_rejects_event_one_rebinding_before_replay",
          "line": 3289
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_bound_start_refuses_foreign_owner_without_creating_lock",
          "line": 3340
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_bound_start_refuses_other_worktree_without_creating_lock",
          "line": 3385
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_bound_start_creation_control_is_load_bearing",
          "line": 3421
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_chain_batch_creation_revalidates_in_lock_order",
          "line": 3462
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_existing_chain_batch_lock_skips_creation_only_validation",
          "line": 3548
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_existing_locked_bound_start_succeeds_without_session_pid",
          "line": 3590
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_existing_locked_bound_start_preserves_foreign_owner_behavior",
          "line": 3630
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_merge_start_binding_creates_stable_batch_lock",
          "line": 3661
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_read_only_binding_validator_does_not_create_batch_lock",
          "line": 3695
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_bound_start_persists_exact_immutable_binding",
          "line": 3731
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_fresh_key_cannot_replay_typed_verification_or_decision_binding",
          "line": 3752
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive",
          "line": 3867
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_historical_receipted_binding_replays_after_restage",
          "line": 3988
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_frozen_abort_writes_explicit_tombstone_without_replay",
          "line": 4053
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
          "line": 4147
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_refuses_terminal_chains_before_any_mutation",
          "line": 4313
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_refuses_landed_chain_and_keeps_its_landing",
          "line": 4345
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_retrospective_abort_disposition_carries_the_decision_once",
          "line": 4388
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
          "line": 4489
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
          "line": 4653
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_disposition_refuses_every_ineligible_chain",
          "line": 4735
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_disposition_preconditions_are_independently_load_bearing",
          "line": 4751
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_disposition_reaches_a_dead_in_place_chain",
          "line": 4785
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_disposition_is_exempt_from_the_iteration_cap",
          "line": 4813
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_disposition_requires_a_chain_id_and_a_readable_journal",
          "line": 4848
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_task_finish_inspects_only_the_finishing_tasks_chains",
          "line": 4891
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_tombstone_publication_retries_prelink_and_postunlink_failures",
          "line": 5051
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_bound_replay_refuses_noncanonical_event_without_state_repair",
          "line": 5117
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_failed_ingest_proof_captures_but_never_references_or_mutates_journal",
          "line": 5167
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_event_carrier_survives_drain_crash_and_replays_once",
          "line": 5237
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.assert_commit_identity_drain_crash_replays_once",
          "line": 5359
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
          "line": 5483
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_receipted_commit_produced_crash_recovers_one_landing",
          "line": 5631
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "CORE",
      "line": 45,
      "users": [
        {
          "method": "Revision9BoundCLIIntegrationTests.test_commit_activation_rejects_event_one_rebinding_before_replay",
          "line": 3289
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_chain_batch_creation_revalidates_in_lock_order",
          "line": 3462
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_existing_chain_batch_lock_skips_creation_only_validation",
          "line": 3548
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_merge_start_binding_creates_stable_batch_lock",
          "line": 3661
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_read_only_binding_validator_does_not_create_batch_lock",
          "line": 3695
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "RUNTIME",
      "line": 46,
      "users": [
        {
          "method": "Revision9BoundCLIIntegrationTests.cli_process_context",
          "line": 1259
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.prepare_unbound_fast_ingest",
          "line": 2055
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_existing_locked_bound_start_succeeds_without_session_pid",
          "line": 3590
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_retrospective_abort_disposition_carries_the_decision_once",
          "line": 4388
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_disposition_run_id_must_name_a_readable_chains_bound_run",
          "line": 4628
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_disposition_reaches_a_dead_in_place_chain",
          "line": 4785
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_disposition_is_exempt_from_the_iteration_cap",
          "line": 4813
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_disposition_requires_a_chain_id_and_a_readable_journal",
          "line": 4848
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "CLI_FIXTURE_SUPPORT",
      "line": 49,
      "users": [
        {
          "method": "Revision9BoundCLIIntegrationTests.configure_changelog_gate",
          "line": 1414
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.start_bound_multicell_stack_chain",
          "line": 1424
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "key",
      "line": 54,
      "users": [
        {
          "method": "Revision9BoundCLIIntegrationTests.open_run_and_task",
          "line": 1291
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.prepare_unbound_fast_ingest",
          "line": 2055
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_legacy_bound_chain_activates_and_lands_cleanly",
          "line": 2892
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_commit_activation_rejects_event_one_rebinding_before_replay",
          "line": 3289
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_merge_start_binding_creates_stable_batch_lock",
          "line": 3661
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_lockless_read_only_binding_validator_does_not_create_batch_lock",
          "line": 3695
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_fresh_key_cannot_replay_typed_verification_or_decision_binding",
          "line": 3752
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive",
          "line": 3867
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_frozen_abort_writes_explicit_tombstone_without_replay",
          "line": 4053
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition",
          "line": 4147
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_refuses_terminal_chains_before_any_mutation",
          "line": 4313
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_abort_refuses_landed_chain_and_keeps_its_landing",
          "line": 4345
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_retrospective_abort_disposition_carries_the_decision_once",
          "line": 4388
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed",
          "line": 4489
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing",
          "line": 4653
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_task_finish_inspects_only_the_finishing_tasks_chains",
          "line": 4891
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_failed_ingest_proof_captures_but_never_references_or_mutates_journal",
          "line": 5167
        },
        {
          "method": "Revision9BoundCLIIntegrationTests.test_chain_receipt_replay_reader_is_read_only_and_fail_closed",
          "line": 5483
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    }
  ],
  "census": [],
  "census_complete": false
}
