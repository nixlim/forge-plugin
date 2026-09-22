{
  "name": "Revision8CoordinationTests",
  "bases": [
    "unittest.TestCase"
  ],
  "metaclass": [],
  "decorators": [],
  "statements": [
    "'Revision-8 append, orphan, identity, and successor-DAG contracts.'"
  ],
  "slots": false,
  "methods": [
    {
      "name": "setUp",
      "line": 31,
      "end_line": 65,
      "decorators": [],
      "reads": [
        "addCleanup",
        "env",
        "repo",
        "root",
        "temporary"
      ],
      "writes": [
        "_readmit_number",
        "_record_number",
        "env",
        "head",
        "repo",
        "root",
        "temporary"
      ],
      "calls": [
        "addCleanup"
      ],
      "globals": [
        "Path",
        "os",
        "subprocess",
        "tempfile"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "runs_root",
      "line": 68,
      "end_line": 69,
      "decorators": [
        "property"
      ],
      "reads": [
        "repo"
      ],
      "writes": [],
      "calls": [],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "wrap",
      "note": "A function-shape move uses property(...), making its uses Any under mypy even with --annotate-self; prefer leaving this property on the class unless it is large."
    },
    {
      "name": "registry_path",
      "line": 72,
      "end_line": 73,
      "decorators": [
        "property"
      ],
      "reads": [
        "repo"
      ],
      "writes": [],
      "calls": [],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "wrap",
      "note": "A function-shape move uses property(...), making its uses Any under mypy even with --annotate-self; prefer leaving this property on the class unless it is large."
    },
    {
      "name": "run_dir",
      "line": 75,
      "end_line": 76,
      "decorators": [],
      "reads": [
        "runs_root"
      ],
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
      "name": "journal_path",
      "line": 78,
      "end_line": 79,
      "decorators": [],
      "reads": [
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "run_dir"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "write_record",
      "line": 81,
      "end_line": 85,
      "decorators": [],
      "reads": [
        "_record_number",
        "root"
      ],
      "writes": [
        "_record_number"
      ],
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
      "name": "command",
      "line": 87,
      "end_line": 101,
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
      "name": "api_environment",
      "line": 104,
      "end_line": 106,
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
      "name": "opening_record",
      "line": 108,
      "end_line": 120,
      "decorators": [],
      "reads": [
        "head",
        "repo"
      ],
      "writes": [],
      "calls": [],
      "globals": [
        "RECORDED_AT"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "task_record",
      "line": 122,
      "end_line": 133,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "RECORDED_AT"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "execution_record",
      "line": 135,
      "end_line": 155,
      "decorators": [],
      "reads": [
        "head",
        "repo"
      ],
      "writes": [],
      "calls": [],
      "globals": [
        "RECORDED_AT"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "execution_result_record",
      "line": 157,
      "end_line": 171,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "RECORDED_AT"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "verification_record",
      "line": 173,
      "end_line": 187,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "RECORDED_AT"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "decision_record",
      "line": 189,
      "end_line": 198,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "RECORDED_AT"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "closure_record",
      "line": 200,
      "end_line": 219,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "RECORDED_AT"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "create_citation_files",
      "line": 221,
      "end_line": 227,
      "decorators": [],
      "reads": [
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "run_dir"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "open_run",
      "line": 229,
      "end_line": 250,
      "decorators": [],
      "reads": [
        "command",
        "opening_record",
        "repo",
        "write_record"
      ],
      "writes": [],
      "calls": [
        "command",
        "opening_record",
        "write_record"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "append_record",
      "line": 252,
      "end_line": 268,
      "decorators": [],
      "reads": [
        "command",
        "repo",
        "write_record"
      ],
      "writes": [],
      "calls": [
        "command",
        "write_record"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "readmit",
      "line": 270,
      "end_line": 291,
      "decorators": [],
      "reads": [
        "_readmit_number",
        "command",
        "repo"
      ],
      "writes": [
        "_readmit_number"
      ],
      "calls": [
        "command"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "retire",
      "line": 293,
      "end_line": 303,
      "decorators": [],
      "reads": [
        "command",
        "repo"
      ],
      "writes": [],
      "calls": [
        "command"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "close",
      "line": 305,
      "end_line": 323,
      "decorators": [],
      "reads": [
        "closure_record",
        "command",
        "repo",
        "write_record"
      ],
      "writes": [],
      "calls": [
        "closure_record",
        "command",
        "write_record"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "coordination_snapshot",
      "line": 325,
      "end_line": 341,
      "decorators": [],
      "reads": [
        "repo"
      ],
      "writes": [],
      "calls": [],
      "globals": [
        "os",
        "stat"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "write_registry",
      "line": 343,
      "end_line": 355,
      "decorators": [],
      "reads": [
        "registry_path"
      ],
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
      "name": "prime_registry_lock",
      "line": 357,
      "end_line": 360,
      "decorators": [],
      "reads": [
        "repo"
      ],
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
      "name": "prime_batch_lock",
      "line": 362,
      "end_line": 366,
      "decorators": [],
      "reads": [
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "run_dir"
      ],
      "globals": [
        "batch"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "assert_absent_registry_node_collision",
      "line": 368,
      "end_line": 483,
      "decorators": [],
      "reads": [
        "addCleanup",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "fail",
        "opening_record",
        "prime_registry_lock",
        "registry_path",
        "repo",
        "root",
        "run_dir",
        "runs_root"
      ],
      "writes": [],
      "calls": [
        "addCleanup",
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "fail",
        "opening_record",
        "prime_registry_lock",
        "run_dir"
      ],
      "globals": [
        "Path",
        "journal",
        "mock",
        "os",
        "stat"
      ],
      "nested_defs": [
        "install_foreign_then_link"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "valid_candidate",
      "line": 485,
      "end_line": 499,
      "decorators": [],
      "reads": [
        "closure_record",
        "decision_record",
        "execution_record",
        "execution_result_record",
        "opening_record",
        "task_record",
        "verification_record"
      ],
      "writes": [],
      "calls": [
        "opening_record"
      ],
      "globals": [
        "copy"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "assert_invalid_candidate",
      "line": 501,
      "end_line": 520,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertRaises",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertRaises"
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
      "name": "assert_valid_candidate",
      "line": 522,
      "end_line": 536,
      "decorators": [],
      "reads": [
        "assertIs",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertIs"
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
      "name": "plant_run_state",
      "line": 538,
      "end_line": 573,
      "decorators": [],
      "reads": [
        "journal_path",
        "opening_record",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "journal_path",
        "opening_record",
        "run_dir"
      ],
      "globals": [
        "RECORDED_AT",
        "journal",
        "json",
        "os",
        "socket"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "proven_dead_pid",
      "line": 575,
      "end_line": 588,
      "decorators": [],
      "reads": [
        "assertIsNotNone",
        "fail"
      ],
      "writes": [],
      "calls": [
        "assertIsNotNone",
        "fail"
      ],
      "globals": [
        "os",
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
      "name": "test_all_seven_strict_minimum_record_types_append",
      "line": 590,
      "end_line": 625,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "close",
        "create_citation_files",
        "decision_record",
        "execution_record",
        "execution_result_record",
        "journal_path",
        "open_run",
        "subTest",
        "task_record",
        "verification_record"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "close",
        "create_citation_files",
        "decision_record",
        "execution_record",
        "execution_result_record",
        "journal_path",
        "open_run",
        "subTest",
        "task_record",
        "verification_record"
      ],
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
      "name": "test_per_type_first_required_field_diagnostics_are_exact",
      "line": 627,
      "end_line": 686,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "assertFalse",
        "close",
        "closure_record",
        "coordination_snapshot",
        "create_citation_files",
        "decision_record",
        "execution_record",
        "execution_result_record",
        "open_run",
        "opening_record",
        "run_dir",
        "subTest",
        "task_record",
        "verification_record"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "assertFalse",
        "close",
        "closure_record",
        "coordination_snapshot",
        "create_citation_files",
        "decision_record",
        "execution_record",
        "execution_result_record",
        "open_run",
        "opening_record",
        "run_dir",
        "subTest",
        "task_record",
        "verification_record"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_fr019_common_and_required_string_boundaries",
      "line": 688,
      "end_line": 830,
      "decorators": [],
      "reads": [
        "assert_invalid_candidate",
        "subTest",
        "valid_candidate"
      ],
      "writes": [],
      "calls": [
        "assert_invalid_candidate",
        "subTest",
        "valid_candidate"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_fr019_format_enum_repository_and_scope_boundaries",
      "line": 832,
      "end_line": 957,
      "decorators": [],
      "reads": [
        "assert_invalid_candidate",
        "assert_valid_candidate",
        "root",
        "subTest",
        "valid_candidate"
      ],
      "writes": [],
      "calls": [
        "assert_invalid_candidate",
        "assert_valid_candidate",
        "subTest",
        "valid_candidate"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_fr019_all_arrays_and_nested_validation_boundaries",
      "line": 959,
      "end_line": 1077,
      "decorators": [],
      "reads": [
        "assert_invalid_candidate",
        "assert_valid_candidate",
        "subTest",
        "valid_candidate"
      ],
      "writes": [],
      "calls": [
        "assert_invalid_candidate",
        "assert_valid_candidate",
        "subTest",
        "valid_candidate"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_fr019_inheritance_events_handoff_optionals_and_extensions",
      "line": 1079,
      "end_line": 1196,
      "decorators": [],
      "reads": [
        "assert_invalid_candidate",
        "assert_valid_candidate",
        "subTest",
        "task_record",
        "valid_candidate"
      ],
      "writes": [],
      "calls": [
        "assert_invalid_candidate",
        "assert_valid_candidate",
        "subTest",
        "task_record",
        "valid_candidate"
      ],
      "globals": [
        "RECORDED_AT"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_first_failure_examples_and_envelope_literal_are_exact",
      "line": 1198,
      "end_line": 1232,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "assertNotIn",
        "coordination_snapshot",
        "create_citation_files",
        "execution_record",
        "open_run",
        "subTest",
        "task_record",
        "verification_record"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "assertNotIn",
        "coordination_snapshot",
        "create_citation_files",
        "execution_record",
        "open_run",
        "subTest",
        "task_record",
        "verification_record"
      ],
      "globals": [
        "RECORDED_AT"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_array_members_fail_at_the_first_ascending_index",
      "line": 1234,
      "end_line": 1253,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "assertNotIn",
        "coordination_snapshot",
        "open_run",
        "task_record"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "assertNotIn",
        "coordination_snapshot",
        "open_run",
        "task_record"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes",
      "line": 1255,
      "end_line": 1284,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "coordination_snapshot",
        "open_run",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "coordination_snapshot",
        "open_run",
        "subTest"
      ],
      "globals": [
        "RECORDED_AT",
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_sparse_history_reads_unchanged_but_same_new_shape_refuses",
      "line": 1286,
      "end_line": 1323,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "assertIsInstance",
        "coordination_snapshot",
        "journal_path",
        "open_run",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "assertIsInstance",
        "coordination_snapshot",
        "journal_path",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "RECORDED_AT",
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
      "name": "test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes",
      "line": 1325,
      "end_line": 1353,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "assertTrue",
        "coordination_snapshot",
        "decision_record",
        "open_run",
        "proven_dead_pid",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "assertTrue",
        "coordination_snapshot",
        "decision_record",
        "open_run",
        "proven_dead_pid",
        "run_dir"
      ],
      "globals": [
        "RECORDED_AT",
        "socket"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "line": 1355,
      "end_line": 1379,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "coordination_snapshot",
        "decision_record",
        "open_run",
        "proven_dead_pid",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "coordination_snapshot",
        "decision_record",
        "open_run",
        "proven_dead_pid",
        "run_dir"
      ],
      "globals": [
        "RECORDED_AT",
        "journal",
        "socket"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_foreign_owner_classification_precedes_candidate_schema",
      "line": 1381,
      "end_line": 1400,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "coordination_snapshot",
        "decision_record",
        "open_run",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "coordination_snapshot",
        "decision_record",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "RECORDED_AT",
        "socket"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_engine_lifecycle_owner_classification_precedes_schema",
      "line": 1402,
      "end_line": 1445,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "coordination_snapshot",
        "open_run",
        "repo",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "coordination_snapshot",
        "open_run",
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
      "name": "test_engine_lifecycle_envelope_is_built_before_session_identity",
      "line": 1447,
      "end_line": 1495,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIsInstance",
        "assertRaises",
        "coordination_snapshot",
        "env",
        "open_run",
        "repo",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIsInstance",
        "assertRaises",
        "coordination_snapshot",
        "open_run",
        "subTest"
      ],
      "globals": [
        "copy",
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "refuse_generated_envelope"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_citation_controls_precede_current_session_identity_refusals",
      "line": 1497,
      "end_line": 1536,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertRaises",
        "coordination_snapshot",
        "decision_record",
        "env",
        "execution_record",
        "open_run",
        "proven_dead_pid",
        "repo",
        "root",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertRaises",
        "coordination_snapshot",
        "decision_record",
        "execution_record",
        "open_run",
        "proven_dead_pid",
        "subTest"
      ],
      "globals": [
        "journal",
        "mock",
        "os",
        "sys"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_current_session_identity_literals_are_exact_and_nonmutating",
      "line": 1538,
      "end_line": 1575,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertRaises",
        "coordination_snapshot",
        "decision_record",
        "env",
        "open_run",
        "proven_dead_pid",
        "repo",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertRaises",
        "coordination_snapshot",
        "decision_record",
        "open_run",
        "proven_dead_pid",
        "subTest"
      ],
      "globals": [
        "journal",
        "mock",
        "os",
        "sys"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_citation_controls_precede_recorded_owner_classification",
      "line": 1577,
      "end_line": 1652,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "coordination_snapshot",
        "decision_record",
        "open_run",
        "repo",
        "root",
        "run_dir",
        "subTest",
        "verification_record"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "coordination_snapshot",
        "decision_record",
        "open_run",
        "run_dir",
        "subTest",
        "verification_record"
      ],
      "globals": [
        "RECORDED_AT",
        "journal",
        "socket"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_new_write_validator_control_is_load_bearing",
      "line": 1654,
      "end_line": 1671,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "journal_path",
        "open_run",
        "repo"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "journal_path",
        "open_run"
      ],
      "globals": [
        "RECORDED_AT",
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
      "name": "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "line": 1673,
      "end_line": 1699,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "assertFalse",
        "close",
        "coordination_snapshot",
        "decision_record",
        "env",
        "open_run",
        "proven_dead_pid",
        "readmit",
        "retire",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "assertFalse",
        "close",
        "coordination_snapshot",
        "decision_record",
        "open_run",
        "proven_dead_pid",
        "readmit",
        "retire",
        "run_dir",
        "subTest"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_invalid_session_pid_literal_is_retained",
      "line": 1701,
      "end_line": 1711,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "env",
        "open_run",
        "repo"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "open_run"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_live_session_identity_is_stable_across_fresh_cli_shells",
      "line": 1713,
      "end_line": 1743,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "assertTrue",
        "command",
        "decision_record",
        "open_run",
        "readmit",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "assertTrue",
        "command",
        "decision_record",
        "open_run",
        "readmit",
        "run_dir"
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
      "name": "test_operation_specific_invalid_id_and_missing_run_literals",
      "line": 1745,
      "end_line": 1777,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "assertNotIn",
        "close",
        "decision_record",
        "open_run",
        "opening_record",
        "readmit",
        "retire",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "assertNotIn",
        "close",
        "decision_record",
        "open_run",
        "opening_record",
        "readmit",
        "retire",
        "subTest"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_operation_specific_repository_unavailable_literals",
      "line": 1779,
      "end_line": 1855,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertNotIn",
        "closure_record",
        "command",
        "decision_record",
        "opening_record",
        "root",
        "subTest",
        "write_record"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertNotIn",
        "closure_record",
        "command",
        "decision_record",
        "opening_record",
        "subTest",
        "write_record"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct",
      "line": 1857,
      "end_line": 1910,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "close",
        "decision_record",
        "journal_path",
        "open_run",
        "readmit",
        "retire",
        "root"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "close",
        "decision_record",
        "journal_path",
        "open_run",
        "readmit",
        "retire"
      ],
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
      "name": "test_lock_registry_update_and_rollback_failure_literals_are_exact",
      "line": 1912,
      "end_line": 1959,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertNotIn",
        "assertRaises",
        "coordination_snapshot",
        "open_run",
        "opening_record",
        "prime_batch_lock",
        "repo"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertNotIn",
        "assertRaises",
        "coordination_snapshot",
        "open_run",
        "opening_record",
        "prime_batch_lock"
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
      "name": "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "line": 1961,
      "end_line": 2028,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "decision_record",
        "journal_path",
        "open_run",
        "registry_path",
        "repo",
        "root",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "decision_record",
        "journal_path",
        "open_run",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "mutate_after_scan"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_ordinary_append_registry_drift_after_fsync_rolls_back_append",
      "line": 2030,
      "end_line": 2067,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertGreater",
        "assertRaises",
        "decision_record",
        "journal_path",
        "open_run",
        "registry_path",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertGreater",
        "assertRaises",
        "decision_record",
        "journal_path",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "journal",
        "json",
        "mock"
      ],
      "nested_defs": [
        "append_then_drift"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_malformed_registry_remains_generic",
      "line": 2069,
      "end_line": 2074,
      "decorators": [],
      "reads": [
        "assertEqual",
        "open_run",
        "registry_path"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "open_run"
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
      "name": "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "line": 2076,
      "end_line": 2152,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "opening_record",
        "registry_path",
        "repo",
        "root",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "opening_record",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "swap_before_open"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "line": 2154,
      "end_line": 2231,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "coordination_snapshot",
        "journal_path",
        "open_run",
        "prime_batch_lock",
        "registry_path",
        "repo",
        "root",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "coordination_snapshot",
        "journal_path",
        "open_run",
        "prime_batch_lock",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "swap_after_validation"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_postpublication_fault_restores_every_lifecycle_transaction",
      "line": 2233,
      "end_line": 2305,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotEqual",
        "assertRaises",
        "closure_record",
        "coordination_snapshot",
        "open_run",
        "opening_record",
        "prime_batch_lock",
        "registry_path",
        "repo",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotEqual",
        "assertRaises",
        "closure_record",
        "coordination_snapshot",
        "open_run",
        "opening_record",
        "prime_batch_lock",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "journal",
        "mock"
      ],
      "nested_defs": [
        "refuse_after_publication"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_initially_absent_registry_is_removed_after_postpublication_fault",
      "line": 2307,
      "end_line": 2341,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "coordination_snapshot",
        "opening_record",
        "prime_registry_lock",
        "registry_path",
        "repo",
        "run_dir",
        "runs_root"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "coordination_snapshot",
        "opening_record",
        "prime_registry_lock",
        "run_dir"
      ],
      "globals": [
        "journal",
        "json",
        "mock"
      ],
      "nested_defs": [
        "refuse_after_publication"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_registry_restoration_failure_retains_published_run_and_journal",
      "line": 2343,
      "end_line": 2409,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertIn",
        "assertNotEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "opening_record",
        "registry_path",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertIn",
        "assertNotEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "opening_record",
        "run_dir"
      ],
      "globals": [
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
      "name": "test_existing_registry_publication_keeps_canonical_name_present",
      "line": 2411,
      "end_line": 2522,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "assertTrue",
        "open_run",
        "registry_path",
        "repo"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "assertTrue",
        "open_run"
      ],
      "globals": [
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "observe_link",
        "observe_exchange",
        "observe_unlink"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_stale_owner_append_failure_restores_owner_and_journal",
      "line": 2524,
      "end_line": 2578,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "assertRaises",
        "assertTrue",
        "decision_record",
        "open_run",
        "proven_dead_pid",
        "registry_path",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "assertRaises",
        "assertTrue",
        "decision_record",
        "open_run",
        "proven_dead_pid",
        "run_dir"
      ],
      "globals": [
        "RECORDED_AT",
        "journal",
        "mock",
        "os",
        "socket"
      ],
      "nested_defs": [
        "append_then_drift"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "line": 2580,
      "end_line": 2662,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "assertRaises",
        "closure_record",
        "coordination_snapshot",
        "open_run",
        "prime_batch_lock",
        "proven_dead_pid",
        "registry_path",
        "repo",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertNotEqual",
        "assertRaises",
        "closure_record",
        "coordination_snapshot",
        "open_run",
        "prime_batch_lock",
        "proven_dead_pid",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "RECORDED_AT",
        "journal",
        "mock",
        "socket"
      ],
      "nested_defs": [
        "validate_then_refuse"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "line": 2664,
      "end_line": 2742,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertIsInstance",
        "assertIsNotNone",
        "assertRaises",
        "assertTrue",
        "decision_record",
        "open_run",
        "proven_dead_pid",
        "registry_path",
        "repo",
        "root",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertIsInstance",
        "assertIsNotNone",
        "assertRaises",
        "assertTrue",
        "decision_record",
        "open_run",
        "proven_dead_pid",
        "run_dir"
      ],
      "globals": [
        "RECORDED_AT",
        "journal",
        "mock",
        "os",
        "socket"
      ],
      "nested_defs": [
        "append_then_drift",
        "replace_owner_then_rollback"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "line": 2744,
      "end_line": 2810,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "opening_record",
        "registry_path",
        "repo",
        "root",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "opening_record",
        "run_dir"
      ],
      "globals": [
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "install_foreign_then_exchange"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_absent_registry_link_race_never_clobbers_foreign_canonical",
      "line": 2812,
      "end_line": 2874,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "opening_record",
        "prime_registry_lock",
        "registry_path",
        "repo",
        "run_dir",
        "runs_root"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "opening_record",
        "prime_registry_lock",
        "run_dir"
      ],
      "globals": [
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "install_foreign_then_link"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_absent_registry_directory_collision_preserves_foreign_node",
      "line": 2876,
      "end_line": 2877,
      "decorators": [],
      "reads": [
        "assert_absent_registry_node_collision"
      ],
      "writes": [],
      "calls": [
        "assert_absent_registry_node_collision"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_absent_registry_symlink_collision_preserves_foreign_node",
      "line": 2879,
      "end_line": 2880,
      "decorators": [],
      "reads": [
        "assert_absent_registry_node_collision"
      ],
      "writes": [],
      "calls": [
        "assert_absent_registry_node_collision"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_absent_registry_broken_symlink_collision_preserves_foreign_node",
      "line": 2882,
      "end_line": 2885,
      "decorators": [],
      "reads": [
        "assert_absent_registry_node_collision"
      ],
      "writes": [],
      "calls": [
        "assert_absent_registry_node_collision"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_absent_registry_unreadable_file_collision_preserves_foreign_node",
      "line": 2887,
      "end_line": 2890,
      "decorators": [],
      "reads": [
        "assert_absent_registry_node_collision"
      ],
      "writes": [],
      "calls": [
        "assert_absent_registry_node_collision"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_exact_staged_registry_prelink_is_recognized_as_published",
      "line": 2892,
      "end_line": 2962,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertTrue",
        "journal_path",
        "opening_record",
        "prime_registry_lock",
        "registry_path",
        "repo",
        "run_dir",
        "runs_root"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertTrue",
        "journal_path",
        "opening_record",
        "prime_registry_lock",
        "run_dir"
      ],
      "globals": [
        "journal",
        "json",
        "mock",
        "os"
      ],
      "nested_defs": [
        "prelink_exact_candidate"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_exact_staged_registry_prelink_rolls_back_after_validation_failure",
      "line": 2964,
      "end_line": 3023,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "coordination_snapshot",
        "opening_record",
        "prime_registry_lock",
        "registry_path",
        "repo",
        "run_dir",
        "runs_root"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "coordination_snapshot",
        "opening_record",
        "prime_registry_lock",
        "run_dir"
      ],
      "globals": [
        "journal",
        "mock"
      ],
      "nested_defs": [
        "prelink_exact_candidate"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "line": 3025,
      "end_line": 3083,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertTrue",
        "decision_record",
        "journal_path",
        "prime_registry_lock",
        "registry_path",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertTrue",
        "decision_record",
        "journal_path",
        "prime_registry_lock",
        "run_dir"
      ],
      "globals": [
        "journal",
        "json",
        "mock",
        "os",
        "socket"
      ],
      "nested_defs": [
        "prelink_exact_owner"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "line": 3085,
      "end_line": 3233,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertIn",
        "assertRaises",
        "assertTrue",
        "decision_record",
        "journal_path",
        "open_run",
        "opening_record",
        "proven_dead_pid",
        "registry_path",
        "repo",
        "root",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertIn",
        "assertRaises",
        "assertTrue",
        "decision_record",
        "journal_path",
        "open_run",
        "opening_record",
        "proven_dead_pid",
        "run_dir"
      ],
      "globals": [
        "RECORDED_AT",
        "journal",
        "json",
        "mock",
        "os",
        "socket"
      ],
      "nested_defs": [
        "race_owner_after_exchange",
        "race_registry_after_exchange"
      ],
      "nonlocal_names": [
        "owner_raced",
        "registry_raced"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "line": 3235,
      "end_line": 3435,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "coordination_snapshot",
        "decision_record",
        "journal_path",
        "open_run",
        "opening_record",
        "prime_batch_lock",
        "prime_registry_lock",
        "proven_dead_pid",
        "registry_path",
        "repo",
        "run_dir",
        "runs_root"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "coordination_snapshot",
        "decision_record",
        "journal_path",
        "open_run",
        "opening_record",
        "prime_batch_lock",
        "prime_registry_lock",
        "proven_dead_pid",
        "run_dir"
      ],
      "globals": [
        "RECORDED_AT",
        "journal",
        "json",
        "mock",
        "os",
        "socket"
      ],
      "nested_defs": [
        "interrupt_absent_registry_link",
        "interrupt_registry_exchange",
        "interrupt_owner_exchange",
        "interrupt_missing_owner_link"
      ],
      "nonlocal_names": [
        "absent_linked",
        "owner_exchanged",
        "owner_linked",
        "registry_exchanged"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "line": 3437,
      "end_line": 3657,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "decision_record",
        "journal_path",
        "opening_record",
        "prime_registry_lock",
        "proven_dead_pid",
        "registry_path",
        "repo",
        "run_dir",
        "runs_root"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "decision_record",
        "journal_path",
        "opening_record",
        "prime_registry_lock",
        "proven_dead_pid",
        "run_dir"
      ],
      "globals": [
        "RECORDED_AT",
        "journal",
        "json",
        "mock",
        "os",
        "socket"
      ],
      "nested_defs": [
        "interrupt_absent_registry_rollback",
        "interrupt_existing_registry_rollback",
        "interrupt_owner_rollback",
        "interrupt_missing_owner_rollback"
      ],
      "nonlocal_names": [
        "absent_moved",
        "existing_restored",
        "missing_moved",
        "owner_restored"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent",
      "line": 3659,
      "end_line": 3835,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "opening_record",
        "prime_registry_lock",
        "registry_path",
        "repo",
        "runs_root"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "opening_record",
        "prime_registry_lock"
      ],
      "globals": [
        "journal",
        "json",
        "mock"
      ],
      "nested_defs": [
        "observe_absent_restore",
        "fail_absent_read",
        "observe_absent_cleanup",
        "observe_existing_restore",
        "fail_existing_lock",
        "observe_existing_cleanup"
      ],
      "nonlocal_names": [
        "absent_failed",
        "absent_restored",
        "existing_failed",
        "existing_restored"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_registry_restoration_cleanup_occurs_only_after_final_proof",
      "line": 3837,
      "end_line": 3901,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "coordination_snapshot",
        "open_run",
        "opening_record",
        "registry_path",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "coordination_snapshot",
        "open_run",
        "opening_record",
        "run_dir"
      ],
      "globals": [
        "journal",
        "mock"
      ],
      "nested_defs": [
        "validate_then_mark",
        "require_proof_before_cleanup"
      ],
      "nonlocal_names": [
        "proof_complete",
        "proof_started"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_registered_missing_journal_remains_generic",
      "line": 3903,
      "end_line": 3914,
      "decorators": [],
      "reads": [
        "assertEqual",
        "coordination_snapshot",
        "open_run",
        "repo",
        "run_dir",
        "write_registry"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "coordination_snapshot",
        "open_run",
        "run_dir",
        "write_registry"
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
      "name": "test_empty_placeholder_is_silent_for_all_unrelated_coordination",
      "line": 3916,
      "end_line": 3964,
      "decorators": [],
      "reads": [
        "append_record",
        "assertEqual",
        "assertNotIn",
        "close",
        "decision_record",
        "open_run",
        "readmit",
        "registry_path",
        "retire",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "append_record",
        "assertEqual",
        "assertNotIn",
        "close",
        "decision_record",
        "open_run",
        "readmit",
        "retire",
        "run_dir"
      ],
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
      "name": "test_empty_placeholder_targeted_validate_and_monitor_remain_unchanged",
      "line": 3966,
      "end_line": 4008,
      "decorators": [],
      "reads": [
        "assertEqual",
        "command",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "command",
        "run_dir"
      ],
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
      "name": "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "line": 4010,
      "end_line": 4108,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "opening_record",
        "registry_path",
        "repo",
        "root",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "opening_record",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "create_same_id_state"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_nonempty_ownerless_orphan_names_validated_repo_relative_path",
      "line": 4110,
      "end_line": 4126,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "coordination_snapshot",
        "open_run",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "coordination_snapshot",
        "open_run",
        "run_dir"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_non_dot_regular_file_in_runs_root_is_silently_ignored",
      "line": 4128,
      "end_line": 4137,
      "decorators": [],
      "reads": [
        "assertEqual",
        "open_run",
        "runs_root"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "open_run"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_ambiguous_orphan_kinds_remain_generic_and_nonmutating",
      "line": 4139,
      "end_line": 4242,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "open_run",
        "registry_path",
        "root",
        "run_dir",
        "runs_root",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "open_run",
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
      "name": "test_orphan_classifier_control_is_load_bearing",
      "line": 4244,
      "end_line": 4263,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "coordination_snapshot",
        "open_run",
        "opening_record",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "coordination_snapshot",
        "open_run",
        "opening_record",
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
      "name": "test_successor_transfer_control_is_load_bearing",
      "line": 4265,
      "end_line": 4288,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "coordination_snapshot",
        "open_run",
        "opening_record",
        "repo",
        "retire",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "coordination_snapshot",
        "open_run",
        "opening_record",
        "retire",
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
      "name": "test_successor_chain_transfers_ancestry_releases_and_readmits",
      "line": 4290,
      "end_line": 4367,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "command",
        "open_run",
        "readmit",
        "repo",
        "retire",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "command",
        "open_run",
        "readmit",
        "retire",
        "run_dir"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_successor_readmission_may_leave_ancestor_scope_but_keeps_it_reserved",
      "line": 4369,
      "end_line": 4408,
      "decorators": [],
      "reads": [
        "assertEqual",
        "open_run",
        "readmit",
        "registry_path",
        "retire"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "open_run",
        "readmit",
        "retire"
      ],
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
      "name": "test_successor_refusal_literals_for_retired_overlap_and_disjoint_scope",
      "line": 4410,
      "end_line": 4429,
      "decorators": [],
      "reads": [
        "assertEqual",
        "open_run",
        "retire"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "open_run",
        "retire"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_persisted_dangling_successor_edge_is_generic_and_nonmutating",
      "line": 4431,
      "end_line": 4447,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "open_run",
        "plant_run_state",
        "prime_registry_lock",
        "run_dir",
        "write_registry"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "open_run",
        "plant_run_state",
        "prime_registry_lock",
        "run_dir",
        "write_registry"
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
      "name": "test_persisted_successor_cycle_is_generic_and_nonmutating",
      "line": 4449,
      "end_line": 4472,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "open_run",
        "plant_run_state",
        "prime_registry_lock",
        "run_dir",
        "write_registry"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "open_run",
        "plant_run_state",
        "prime_registry_lock",
        "run_dir",
        "write_registry"
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
      "name": "test_persisted_disjoint_successor_edge_is_generic_and_nonmutating",
      "line": 4474,
      "end_line": 4491,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "open_run",
        "plant_run_state",
        "prime_registry_lock",
        "run_dir",
        "write_registry"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "open_run",
        "plant_run_state",
        "prime_registry_lock",
        "run_dir",
        "write_registry"
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
      "name": "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "line": 4493,
      "end_line": 4541,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "journal_path",
        "open_run",
        "opening_record",
        "plant_run_state",
        "prime_registry_lock",
        "run_dir",
        "subTest",
        "write_registry"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "journal_path",
        "open_run",
        "opening_record",
        "plant_run_state",
        "prime_registry_lock",
        "run_dir",
        "subTest",
        "write_registry"
      ],
      "globals": [
        "RECORDED_AT",
        "journal",
        "json",
        "os",
        "socket"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_mixed_open_and_retired_conflicts_are_byte_sorted",
      "line": 4543,
      "end_line": 4564,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "open_run",
        "retire",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "coordination_snapshot",
        "open_run",
        "retire",
        "run_dir"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "line": 4566,
      "end_line": 4686,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertTrue",
        "env",
        "open_run",
        "opening_record",
        "registry_path",
        "repo",
        "retire",
        "root",
        "run_dir",
        "write_record"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertFalse",
        "assertIn",
        "assertTrue",
        "open_run",
        "opening_record",
        "retire",
        "run_dir",
        "write_record"
      ],
      "globals": [
        "TOOLS",
        "json",
        "subprocess",
        "sys",
        "time"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "line": 4688,
      "end_line": 4752,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "coordination_snapshot",
        "open_run",
        "opening_record",
        "prime_registry_lock",
        "registry_path",
        "repo",
        "root",
        "runs_root",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "assertTrue",
        "coordination_snapshot",
        "open_run",
        "opening_record",
        "prime_registry_lock",
        "subTest"
      ],
      "globals": [
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "bind_then_swap"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_claimed_candidate_child_is_preserved_but_never_published",
      "line": 4754,
      "end_line": 4800,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertRaises",
        "assertTrue",
        "open_run",
        "opening_record",
        "registry_path",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotIn",
        "assertRaises",
        "assertTrue",
        "open_run",
        "opening_record",
        "run_dir"
      ],
      "globals": [
        "journal",
        "json",
        "mock"
      ],
      "nested_defs": [
        "inject_then_validate"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "line": 4802,
      "end_line": 4891,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertIn",
        "assertNotIn",
        "assertRaises",
        "assertTrue",
        "open_run",
        "opening_record",
        "registry_path",
        "repo",
        "root",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertIn",
        "assertNotIn",
        "assertRaises",
        "assertTrue",
        "open_run",
        "opening_record",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "journal",
        "json",
        "mock",
        "os"
      ],
      "nested_defs": [
        "replace_before_cleanup"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate",
      "line": 4893,
      "end_line": 4947,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "journal_path",
        "open_run",
        "opening_record",
        "registry_path",
        "repo",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "journal_path",
        "open_run",
        "opening_record",
        "run_dir"
      ],
      "globals": [
        "journal",
        "mock",
        "threading"
      ],
      "nested_defs": [
        "mutate_placeholder",
        "barrier_revalidate"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "line": 4949,
      "end_line": 5031,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "opening_record",
        "registry_path",
        "repo",
        "root",
        "run_dir",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertNotEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "opening_record",
        "run_dir",
        "subTest"
      ],
      "globals": [
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "replace_observed_placeholder"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_run_directory_identity_swap_at_publication_rolls_back_original",
      "line": 5033,
      "end_line": 5068,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "registry_path",
        "repo",
        "root",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "swap_run_directory"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_journal_identity_swap_at_publication_rolls_back_bound_original",
      "line": 5070,
      "end_line": 5109,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "registry_path",
        "repo",
        "root",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "assertTrue",
        "journal_path",
        "open_run",
        "run_dir"
      ],
      "globals": [
        "journal",
        "mock",
        "os"
      ],
      "nested_defs": [
        "swap_journal"
      ],
      "nonlocal_names": [
        "triggered"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_only_a_retired_successor_may_close_and_release_ancestry",
      "line": 5111,
      "end_line": 5135,
      "decorators": [],
      "reads": [
        "assertEqual",
        "close",
        "coordination_snapshot",
        "open_run",
        "retire"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "close",
        "coordination_snapshot",
        "open_run",
        "retire"
      ],
      "globals": [],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_close_rollback_preserves_effective_ancestral_reservation",
      "line": 5137,
      "end_line": 5170,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "closure_record",
        "coordination_snapshot",
        "open_run",
        "prime_batch_lock",
        "repo",
        "retire"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertRaises",
        "closure_record",
        "coordination_snapshot",
        "open_run",
        "prime_batch_lock",
        "retire"
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
      "name": "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "line": 5172,
      "end_line": 5203,
      "decorators": [],
      "reads": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "closure_record",
        "open_run",
        "opening_record",
        "repo",
        "retire",
        "run_dir"
      ],
      "writes": [],
      "calls": [
        "api_environment",
        "assertEqual",
        "assertFalse",
        "assertRaises",
        "closure_record",
        "open_run",
        "opening_record",
        "retire",
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
      "name": "test_historical_fork_releases_shared_ancestor_only_after_both_branches_close",
      "line": 5205,
      "end_line": 5249,
      "decorators": [],
      "reads": [
        "assertEqual",
        "close",
        "open_run",
        "opening_record",
        "retire",
        "run_dir",
        "write_registry"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "close",
        "open_run",
        "opening_record",
        "retire",
        "run_dir",
        "write_registry"
      ],
      "globals": [
        "RECORDED_AT",
        "json",
        "os",
        "socket"
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
      "api_environment",
      "@state:env"
    ],
    [
      "append_record",
      "@state:repo"
    ],
    [
      "append_record",
      "command"
    ],
    [
      "append_record",
      "write_record"
    ],
    [
      "assert_absent_registry_node_collision",
      "@state:addCleanup"
    ],
    [
      "assert_absent_registry_node_collision",
      "@state:assertEqual"
    ],
    [
      "assert_absent_registry_node_collision",
      "@state:assertFalse"
    ],
    [
      "assert_absent_registry_node_collision",
      "@state:assertRaises"
    ],
    [
      "assert_absent_registry_node_collision",
      "@state:assertTrue"
    ],
    [
      "assert_absent_registry_node_collision",
      "@state:fail"
    ],
    [
      "assert_absent_registry_node_collision",
      "@state:repo"
    ],
    [
      "assert_absent_registry_node_collision",
      "@state:root"
    ],
    [
      "assert_absent_registry_node_collision",
      "api_environment"
    ],
    [
      "assert_absent_registry_node_collision",
      "opening_record"
    ],
    [
      "assert_absent_registry_node_collision",
      "prime_registry_lock"
    ],
    [
      "assert_absent_registry_node_collision",
      "run_dir"
    ],
    [
      "assert_invalid_candidate",
      "@state:assertEqual"
    ],
    [
      "assert_invalid_candidate",
      "@state:assertRaises"
    ],
    [
      "assert_invalid_candidate",
      "@state:repo"
    ],
    [
      "assert_valid_candidate",
      "@state:assertIs"
    ],
    [
      "assert_valid_candidate",
      "@state:repo"
    ],
    [
      "close",
      "@state:repo"
    ],
    [
      "close",
      "closure_record"
    ],
    [
      "close",
      "command"
    ],
    [
      "close",
      "write_record"
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
      "coordination_snapshot",
      "@state:repo"
    ],
    [
      "create_citation_files",
      "run_dir"
    ],
    [
      "execution_record",
      "@state:head"
    ],
    [
      "execution_record",
      "@state:repo"
    ],
    [
      "journal_path",
      "run_dir"
    ],
    [
      "open_run",
      "@state:repo"
    ],
    [
      "open_run",
      "command"
    ],
    [
      "open_run",
      "opening_record"
    ],
    [
      "open_run",
      "write_record"
    ],
    [
      "opening_record",
      "@state:head"
    ],
    [
      "opening_record",
      "@state:repo"
    ],
    [
      "plant_run_state",
      "journal_path"
    ],
    [
      "plant_run_state",
      "opening_record"
    ],
    [
      "plant_run_state",
      "run_dir"
    ],
    [
      "prime_batch_lock",
      "run_dir"
    ],
    [
      "prime_registry_lock",
      "@state:repo"
    ],
    [
      "proven_dead_pid",
      "@state:assertIsNotNone"
    ],
    [
      "proven_dead_pid",
      "@state:fail"
    ],
    [
      "readmit",
      "@state:_readmit_number"
    ],
    [
      "readmit",
      "@state:repo"
    ],
    [
      "readmit",
      "command"
    ],
    [
      "registry_path",
      "@state:repo"
    ],
    [
      "retire",
      "@state:repo"
    ],
    [
      "retire",
      "command"
    ],
    [
      "runs_root",
      "@state:repo"
    ],
    [
      "setUp",
      "@state:_readmit_number"
    ],
    [
      "setUp",
      "@state:_record_number"
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
      "@state:root"
    ],
    [
      "setUp",
      "@state:temporary"
    ],
    [
      "test_absent_registry_broken_symlink_collision_preserves_foreign_node",
      "assert_absent_registry_node_collision"
    ],
    [
      "test_absent_registry_directory_collision_preserves_foreign_node",
      "assert_absent_registry_node_collision"
    ],
    [
      "test_absent_registry_link_race_never_clobbers_foreign_canonical",
      "@state:assertEqual"
    ],
    [
      "test_absent_registry_link_race_never_clobbers_foreign_canonical",
      "@state:assertFalse"
    ],
    [
      "test_absent_registry_link_race_never_clobbers_foreign_canonical",
      "@state:assertRaises"
    ],
    [
      "test_absent_registry_link_race_never_clobbers_foreign_canonical",
      "@state:assertTrue"
    ],
    [
      "test_absent_registry_link_race_never_clobbers_foreign_canonical",
      "@state:repo"
    ],
    [
      "test_absent_registry_link_race_never_clobbers_foreign_canonical",
      "api_environment"
    ],
    [
      "test_absent_registry_link_race_never_clobbers_foreign_canonical",
      "opening_record"
    ],
    [
      "test_absent_registry_link_race_never_clobbers_foreign_canonical",
      "prime_registry_lock"
    ],
    [
      "test_absent_registry_link_race_never_clobbers_foreign_canonical",
      "run_dir"
    ],
    [
      "test_absent_registry_symlink_collision_preserves_foreign_node",
      "assert_absent_registry_node_collision"
    ],
    [
      "test_absent_registry_unreadable_file_collision_preserves_foreign_node",
      "assert_absent_registry_node_collision"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "@state:assertEqual"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "@state:subTest"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "append_record"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "close"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "create_citation_files"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "decision_record"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "execution_record"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "execution_result_record"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "journal_path"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "open_run"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "task_record"
    ],
    [
      "test_all_seven_strict_minimum_record_types_append",
      "verification_record"
    ],
    [
      "test_ambiguous_orphan_kinds_remain_generic_and_nonmutating",
      "@state:assertEqual"
    ],
    [
      "test_ambiguous_orphan_kinds_remain_generic_and_nonmutating",
      "@state:assertFalse"
    ],
    [
      "test_ambiguous_orphan_kinds_remain_generic_and_nonmutating",
      "@state:root"
    ],
    [
      "test_ambiguous_orphan_kinds_remain_generic_and_nonmutating",
      "@state:subTest"
    ],
    [
      "test_ambiguous_orphan_kinds_remain_generic_and_nonmutating",
      "coordination_snapshot"
    ],
    [
      "test_ambiguous_orphan_kinds_remain_generic_and_nonmutating",
      "open_run"
    ],
    [
      "test_ambiguous_orphan_kinds_remain_generic_and_nonmutating",
      "run_dir"
    ],
    [
      "test_array_members_fail_at_the_first_ascending_index",
      "@state:assertEqual"
    ],
    [
      "test_array_members_fail_at_the_first_ascending_index",
      "@state:assertNotIn"
    ],
    [
      "test_array_members_fail_at_the_first_ascending_index",
      "append_record"
    ],
    [
      "test_array_members_fail_at_the_first_ascending_index",
      "coordination_snapshot"
    ],
    [
      "test_array_members_fail_at_the_first_ascending_index",
      "open_run"
    ],
    [
      "test_array_members_fail_at_the_first_ascending_index",
      "task_record"
    ],
    [
      "test_citation_controls_precede_current_session_identity_refusals",
      "@state:assertEqual"
    ],
    [
      "test_citation_controls_precede_current_session_identity_refusals",
      "@state:assertRaises"
    ],
    [
      "test_citation_controls_precede_current_session_identity_refusals",
      "@state:env"
    ],
    [
      "test_citation_controls_precede_current_session_identity_refusals",
      "@state:repo"
    ],
    [
      "test_citation_controls_precede_current_session_identity_refusals",
      "@state:root"
    ],
    [
      "test_citation_controls_precede_current_session_identity_refusals",
      "@state:subTest"
    ],
    [
      "test_citation_controls_precede_current_session_identity_refusals",
      "coordination_snapshot"
    ],
    [
      "test_citation_controls_precede_current_session_identity_refusals",
      "decision_record"
    ],
    [
      "test_citation_controls_precede_current_session_identity_refusals",
      "execution_record"
    ],
    [
      "test_citation_controls_precede_current_session_identity_refusals",
      "open_run"
    ],
    [
      "test_citation_controls_precede_current_session_identity_refusals",
      "proven_dead_pid"
    ],
    [
      "test_citation_controls_precede_recorded_owner_classification",
      "@state:assertEqual"
    ],
    [
      "test_citation_controls_precede_recorded_owner_classification",
      "@state:assertRaises"
    ],
    [
      "test_citation_controls_precede_recorded_owner_classification",
      "@state:repo"
    ],
    [
      "test_citation_controls_precede_recorded_owner_classification",
      "@state:root"
    ],
    [
      "test_citation_controls_precede_recorded_owner_classification",
      "@state:subTest"
    ],
    [
      "test_citation_controls_precede_recorded_owner_classification",
      "api_environment"
    ],
    [
      "test_citation_controls_precede_recorded_owner_classification",
      "coordination_snapshot"
    ],
    [
      "test_citation_controls_precede_recorded_owner_classification",
      "decision_record"
    ],
    [
      "test_citation_controls_precede_recorded_owner_classification",
      "open_run"
    ],
    [
      "test_citation_controls_precede_recorded_owner_classification",
      "run_dir"
    ],
    [
      "test_citation_controls_precede_recorded_owner_classification",
      "verification_record"
    ],
    [
      "test_claimed_candidate_child_is_preserved_but_never_published",
      "@state:assertEqual"
    ],
    [
      "test_claimed_candidate_child_is_preserved_but_never_published",
      "@state:assertFalse"
    ],
    [
      "test_claimed_candidate_child_is_preserved_but_never_published",
      "@state:assertNotIn"
    ],
    [
      "test_claimed_candidate_child_is_preserved_but_never_published",
      "@state:assertRaises"
    ],
    [
      "test_claimed_candidate_child_is_preserved_but_never_published",
      "@state:assertTrue"
    ],
    [
      "test_claimed_candidate_child_is_preserved_but_never_published",
      "@state:repo"
    ],
    [
      "test_claimed_candidate_child_is_preserved_but_never_published",
      "api_environment"
    ],
    [
      "test_claimed_candidate_child_is_preserved_but_never_published",
      "open_run"
    ],
    [
      "test_claimed_candidate_child_is_preserved_but_never_published",
      "opening_record"
    ],
    [
      "test_claimed_candidate_child_is_preserved_but_never_published",
      "run_dir"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "@state:assertEqual"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "@state:assertIn"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "@state:assertNotIn"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "@state:assertRaises"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "@state:assertTrue"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "@state:repo"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "@state:root"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "@state:subTest"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "api_environment"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "open_run"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "opening_record"
    ],
    [
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "run_dir"
    ],
    [
      "test_close_rollback_preserves_effective_ancestral_reservation",
      "@state:assertEqual"
    ],
    [
      "test_close_rollback_preserves_effective_ancestral_reservation",
      "@state:assertRaises"
    ],
    [
      "test_close_rollback_preserves_effective_ancestral_reservation",
      "@state:repo"
    ],
    [
      "test_close_rollback_preserves_effective_ancestral_reservation",
      "api_environment"
    ],
    [
      "test_close_rollback_preserves_effective_ancestral_reservation",
      "closure_record"
    ],
    [
      "test_close_rollback_preserves_effective_ancestral_reservation",
      "coordination_snapshot"
    ],
    [
      "test_close_rollback_preserves_effective_ancestral_reservation",
      "open_run"
    ],
    [
      "test_close_rollback_preserves_effective_ancestral_reservation",
      "prime_batch_lock"
    ],
    [
      "test_close_rollback_preserves_effective_ancestral_reservation",
      "retire"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "@state:assertEqual"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "@state:assertFalse"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "@state:assertIn"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "@state:assertTrue"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "@state:env"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "@state:repo"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "@state:root"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "open_run"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "opening_record"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "retire"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "run_dir"
    ],
    [
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "write_record"
    ],
    [
      "test_current_session_identity_literals_are_exact_and_nonmutating",
      "@state:assertEqual"
    ],
    [
      "test_current_session_identity_literals_are_exact_and_nonmutating",
      "@state:assertRaises"
    ],
    [
      "test_current_session_identity_literals_are_exact_and_nonmutating",
      "@state:env"
    ],
    [
      "test_current_session_identity_literals_are_exact_and_nonmutating",
      "@state:repo"
    ],
    [
      "test_current_session_identity_literals_are_exact_and_nonmutating",
      "@state:subTest"
    ],
    [
      "test_current_session_identity_literals_are_exact_and_nonmutating",
      "coordination_snapshot"
    ],
    [
      "test_current_session_identity_literals_are_exact_and_nonmutating",
      "decision_record"
    ],
    [
      "test_current_session_identity_literals_are_exact_and_nonmutating",
      "open_run"
    ],
    [
      "test_current_session_identity_literals_are_exact_and_nonmutating",
      "proven_dead_pid"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "@state:assertEqual"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "@state:assertFalse"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "@state:env"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "@state:subTest"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "append_record"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "close"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "coordination_snapshot"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "decision_record"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "open_run"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "proven_dead_pid"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "readmit"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "retire"
    ],
    [
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "run_dir"
    ],
    [
      "test_empty_placeholder_is_silent_for_all_unrelated_coordination",
      "@state:assertEqual"
    ],
    [
      "test_empty_placeholder_is_silent_for_all_unrelated_coordination",
      "@state:assertNotIn"
    ],
    [
      "test_empty_placeholder_is_silent_for_all_unrelated_coordination",
      "append_record"
    ],
    [
      "test_empty_placeholder_is_silent_for_all_unrelated_coordination",
      "close"
    ],
    [
      "test_empty_placeholder_is_silent_for_all_unrelated_coordination",
      "decision_record"
    ],
    [
      "test_empty_placeholder_is_silent_for_all_unrelated_coordination",
      "open_run"
    ],
    [
      "test_empty_placeholder_is_silent_for_all_unrelated_coordination",
      "readmit"
    ],
    [
      "test_empty_placeholder_is_silent_for_all_unrelated_coordination",
      "retire"
    ],
    [
      "test_empty_placeholder_is_silent_for_all_unrelated_coordination",
      "run_dir"
    ],
    [
      "test_empty_placeholder_targeted_validate_and_monitor_remain_unchanged",
      "@state:assertEqual"
    ],
    [
      "test_empty_placeholder_targeted_validate_and_monitor_remain_unchanged",
      "@state:repo"
    ],
    [
      "test_empty_placeholder_targeted_validate_and_monitor_remain_unchanged",
      "command"
    ],
    [
      "test_empty_placeholder_targeted_validate_and_monitor_remain_unchanged",
      "run_dir"
    ],
    [
      "test_engine_lifecycle_envelope_is_built_before_session_identity",
      "@state:assertEqual"
    ],
    [
      "test_engine_lifecycle_envelope_is_built_before_session_identity",
      "@state:assertIsInstance"
    ],
    [
      "test_engine_lifecycle_envelope_is_built_before_session_identity",
      "@state:assertRaises"
    ],
    [
      "test_engine_lifecycle_envelope_is_built_before_session_identity",
      "@state:env"
    ],
    [
      "test_engine_lifecycle_envelope_is_built_before_session_identity",
      "@state:repo"
    ],
    [
      "test_engine_lifecycle_envelope_is_built_before_session_identity",
      "@state:subTest"
    ],
    [
      "test_engine_lifecycle_envelope_is_built_before_session_identity",
      "coordination_snapshot"
    ],
    [
      "test_engine_lifecycle_envelope_is_built_before_session_identity",
      "open_run"
    ],
    [
      "test_engine_lifecycle_owner_classification_precedes_schema",
      "@state:assertEqual"
    ],
    [
      "test_engine_lifecycle_owner_classification_precedes_schema",
      "@state:assertRaises"
    ],
    [
      "test_engine_lifecycle_owner_classification_precedes_schema",
      "@state:repo"
    ],
    [
      "test_engine_lifecycle_owner_classification_precedes_schema",
      "@state:subTest"
    ],
    [
      "test_engine_lifecycle_owner_classification_precedes_schema",
      "api_environment"
    ],
    [
      "test_engine_lifecycle_owner_classification_precedes_schema",
      "coordination_snapshot"
    ],
    [
      "test_engine_lifecycle_owner_classification_precedes_schema",
      "open_run"
    ],
    [
      "test_engine_lifecycle_owner_classification_precedes_schema",
      "run_dir"
    ],
    [
      "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "@state:assertEqual"
    ],
    [
      "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "@state:assertFalse"
    ],
    [
      "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "@state:assertIn"
    ],
    [
      "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "@state:assertTrue"
    ],
    [
      "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "@state:repo"
    ],
    [
      "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "api_environment"
    ],
    [
      "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "decision_record"
    ],
    [
      "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "journal_path"
    ],
    [
      "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "prime_registry_lock"
    ],
    [
      "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "run_dir"
    ],
    [
      "test_exact_staged_registry_prelink_is_recognized_as_published",
      "@state:assertEqual"
    ],
    [
      "test_exact_staged_registry_prelink_is_recognized_as_published",
      "@state:assertTrue"
    ],
    [
      "test_exact_staged_registry_prelink_is_recognized_as_published",
      "@state:repo"
    ],
    [
      "test_exact_staged_registry_prelink_is_recognized_as_published",
      "api_environment"
    ],
    [
      "test_exact_staged_registry_prelink_is_recognized_as_published",
      "journal_path"
    ],
    [
      "test_exact_staged_registry_prelink_is_recognized_as_published",
      "opening_record"
    ],
    [
      "test_exact_staged_registry_prelink_is_recognized_as_published",
      "prime_registry_lock"
    ],
    [
      "test_exact_staged_registry_prelink_is_recognized_as_published",
      "run_dir"
    ],
    [
      "test_exact_staged_registry_prelink_rolls_back_after_validation_failure",
      "@state:assertEqual"
    ],
    [
      "test_exact_staged_registry_prelink_rolls_back_after_validation_failure",
      "@state:assertFalse"
    ],
    [
      "test_exact_staged_registry_prelink_rolls_back_after_validation_failure",
      "@state:assertRaises"
    ],
    [
      "test_exact_staged_registry_prelink_rolls_back_after_validation_failure",
      "@state:repo"
    ],
    [
      "test_exact_staged_registry_prelink_rolls_back_after_validation_failure",
      "api_environment"
    ],
    [
      "test_exact_staged_registry_prelink_rolls_back_after_validation_failure",
      "coordination_snapshot"
    ],
    [
      "test_exact_staged_registry_prelink_rolls_back_after_validation_failure",
      "opening_record"
    ],
    [
      "test_exact_staged_registry_prelink_rolls_back_after_validation_failure",
      "prime_registry_lock"
    ],
    [
      "test_exact_staged_registry_prelink_rolls_back_after_validation_failure",
      "run_dir"
    ],
    [
      "test_existing_registry_publication_keeps_canonical_name_present",
      "@state:assertEqual"
    ],
    [
      "test_existing_registry_publication_keeps_canonical_name_present",
      "@state:assertNotEqual"
    ],
    [
      "test_existing_registry_publication_keeps_canonical_name_present",
      "@state:assertTrue"
    ],
    [
      "test_existing_registry_publication_keeps_canonical_name_present",
      "@state:repo"
    ],
    [
      "test_existing_registry_publication_keeps_canonical_name_present",
      "api_environment"
    ],
    [
      "test_existing_registry_publication_keeps_canonical_name_present",
      "open_run"
    ],
    [
      "test_first_failure_examples_and_envelope_literal_are_exact",
      "@state:assertEqual"
    ],
    [
      "test_first_failure_examples_and_envelope_literal_are_exact",
      "@state:assertNotIn"
    ],
    [
      "test_first_failure_examples_and_envelope_literal_are_exact",
      "@state:subTest"
    ],
    [
      "test_first_failure_examples_and_envelope_literal_are_exact",
      "append_record"
    ],
    [
      "test_first_failure_examples_and_envelope_literal_are_exact",
      "coordination_snapshot"
    ],
    [
      "test_first_failure_examples_and_envelope_literal_are_exact",
      "create_citation_files"
    ],
    [
      "test_first_failure_examples_and_envelope_literal_are_exact",
      "execution_record"
    ],
    [
      "test_first_failure_examples_and_envelope_literal_are_exact",
      "open_run"
    ],
    [
      "test_first_failure_examples_and_envelope_literal_are_exact",
      "task_record"
    ],
    [
      "test_first_failure_examples_and_envelope_literal_are_exact",
      "verification_record"
    ],
    [
      "test_foreign_owner_classification_precedes_candidate_schema",
      "@state:assertEqual"
    ],
    [
      "test_foreign_owner_classification_precedes_candidate_schema",
      "append_record"
    ],
    [
      "test_foreign_owner_classification_precedes_candidate_schema",
      "coordination_snapshot"
    ],
    [
      "test_foreign_owner_classification_precedes_candidate_schema",
      "decision_record"
    ],
    [
      "test_foreign_owner_classification_precedes_candidate_schema",
      "open_run"
    ],
    [
      "test_foreign_owner_classification_precedes_candidate_schema",
      "run_dir"
    ],
    [
      "test_fr019_all_arrays_and_nested_validation_boundaries",
      "@state:subTest"
    ],
    [
      "test_fr019_all_arrays_and_nested_validation_boundaries",
      "assert_invalid_candidate"
    ],
    [
      "test_fr019_all_arrays_and_nested_validation_boundaries",
      "assert_valid_candidate"
    ],
    [
      "test_fr019_all_arrays_and_nested_validation_boundaries",
      "valid_candidate"
    ],
    [
      "test_fr019_common_and_required_string_boundaries",
      "@state:subTest"
    ],
    [
      "test_fr019_common_and_required_string_boundaries",
      "assert_invalid_candidate"
    ],
    [
      "test_fr019_common_and_required_string_boundaries",
      "valid_candidate"
    ],
    [
      "test_fr019_format_enum_repository_and_scope_boundaries",
      "@state:root"
    ],
    [
      "test_fr019_format_enum_repository_and_scope_boundaries",
      "@state:subTest"
    ],
    [
      "test_fr019_format_enum_repository_and_scope_boundaries",
      "assert_invalid_candidate"
    ],
    [
      "test_fr019_format_enum_repository_and_scope_boundaries",
      "assert_valid_candidate"
    ],
    [
      "test_fr019_format_enum_repository_and_scope_boundaries",
      "valid_candidate"
    ],
    [
      "test_fr019_inheritance_events_handoff_optionals_and_extensions",
      "@state:subTest"
    ],
    [
      "test_fr019_inheritance_events_handoff_optionals_and_extensions",
      "assert_invalid_candidate"
    ],
    [
      "test_fr019_inheritance_events_handoff_optionals_and_extensions",
      "assert_valid_candidate"
    ],
    [
      "test_fr019_inheritance_events_handoff_optionals_and_extensions",
      "task_record"
    ],
    [
      "test_fr019_inheritance_events_handoff_optionals_and_extensions",
      "valid_candidate"
    ],
    [
      "test_historical_fork_releases_shared_ancestor_only_after_both_branches_close",
      "@state:assertEqual"
    ],
    [
      "test_historical_fork_releases_shared_ancestor_only_after_both_branches_close",
      "close"
    ],
    [
      "test_historical_fork_releases_shared_ancestor_only_after_both_branches_close",
      "open_run"
    ],
    [
      "test_historical_fork_releases_shared_ancestor_only_after_both_branches_close",
      "opening_record"
    ],
    [
      "test_historical_fork_releases_shared_ancestor_only_after_both_branches_close",
      "retire"
    ],
    [
      "test_historical_fork_releases_shared_ancestor_only_after_both_branches_close",
      "run_dir"
    ],
    [
      "test_historical_fork_releases_shared_ancestor_only_after_both_branches_close",
      "write_registry"
    ],
    [
      "test_initially_absent_registry_is_removed_after_postpublication_fault",
      "@state:assertEqual"
    ],
    [
      "test_initially_absent_registry_is_removed_after_postpublication_fault",
      "@state:assertFalse"
    ],
    [
      "test_initially_absent_registry_is_removed_after_postpublication_fault",
      "@state:assertRaises"
    ],
    [
      "test_initially_absent_registry_is_removed_after_postpublication_fault",
      "@state:repo"
    ],
    [
      "test_initially_absent_registry_is_removed_after_postpublication_fault",
      "api_environment"
    ],
    [
      "test_initially_absent_registry_is_removed_after_postpublication_fault",
      "coordination_snapshot"
    ],
    [
      "test_initially_absent_registry_is_removed_after_postpublication_fault",
      "opening_record"
    ],
    [
      "test_initially_absent_registry_is_removed_after_postpublication_fault",
      "prime_registry_lock"
    ],
    [
      "test_initially_absent_registry_is_removed_after_postpublication_fault",
      "run_dir"
    ],
    [
      "test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes",
      "@state:assertEqual"
    ],
    [
      "test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes",
      "@state:assertTrue"
    ],
    [
      "test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes",
      "append_record"
    ],
    [
      "test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes",
      "coordination_snapshot"
    ],
    [
      "test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes",
      "decision_record"
    ],
    [
      "test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes",
      "open_run"
    ],
    [
      "test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes",
      "proven_dead_pid"
    ],
    [
      "test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes",
      "run_dir"
    ],
    [
      "test_invalid_session_pid_literal_is_retained",
      "@state:assertEqual"
    ],
    [
      "test_invalid_session_pid_literal_is_retained",
      "@state:assertFalse"
    ],
    [
      "test_invalid_session_pid_literal_is_retained",
      "@state:env"
    ],
    [
      "test_invalid_session_pid_literal_is_retained",
      "@state:repo"
    ],
    [
      "test_invalid_session_pid_literal_is_retained",
      "open_run"
    ],
    [
      "test_journal_identity_swap_at_publication_rolls_back_bound_original",
      "@state:assertEqual"
    ],
    [
      "test_journal_identity_swap_at_publication_rolls_back_bound_original",
      "@state:assertRaises"
    ],
    [
      "test_journal_identity_swap_at_publication_rolls_back_bound_original",
      "@state:assertTrue"
    ],
    [
      "test_journal_identity_swap_at_publication_rolls_back_bound_original",
      "@state:repo"
    ],
    [
      "test_journal_identity_swap_at_publication_rolls_back_bound_original",
      "@state:root"
    ],
    [
      "test_journal_identity_swap_at_publication_rolls_back_bound_original",
      "api_environment"
    ],
    [
      "test_journal_identity_swap_at_publication_rolls_back_bound_original",
      "journal_path"
    ],
    [
      "test_journal_identity_swap_at_publication_rolls_back_bound_original",
      "open_run"
    ],
    [
      "test_journal_identity_swap_at_publication_rolls_back_bound_original",
      "run_dir"
    ],
    [
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "@state:assertEqual"
    ],
    [
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "@state:assertFalse"
    ],
    [
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "@state:subTest"
    ],
    [
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "coordination_snapshot"
    ],
    [
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "journal_path"
    ],
    [
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "open_run"
    ],
    [
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "opening_record"
    ],
    [
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "plant_run_state"
    ],
    [
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "prime_registry_lock"
    ],
    [
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "run_dir"
    ],
    [
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
      "write_registry"
    ],
    [
      "test_live_session_identity_is_stable_across_fresh_cli_shells",
      "@state:assertEqual"
    ],
    [
      "test_live_session_identity_is_stable_across_fresh_cli_shells",
      "@state:assertTrue"
    ],
    [
      "test_live_session_identity_is_stable_across_fresh_cli_shells",
      "@state:repo"
    ],
    [
      "test_live_session_identity_is_stable_across_fresh_cli_shells",
      "append_record"
    ],
    [
      "test_live_session_identity_is_stable_across_fresh_cli_shells",
      "command"
    ],
    [
      "test_live_session_identity_is_stable_across_fresh_cli_shells",
      "decision_record"
    ],
    [
      "test_live_session_identity_is_stable_across_fresh_cli_shells",
      "open_run"
    ],
    [
      "test_live_session_identity_is_stable_across_fresh_cli_shells",
      "readmit"
    ],
    [
      "test_live_session_identity_is_stable_across_fresh_cli_shells",
      "run_dir"
    ],
    [
      "test_lock_registry_update_and_rollback_failure_literals_are_exact",
      "@state:assertEqual"
    ],
    [
      "test_lock_registry_update_and_rollback_failure_literals_are_exact",
      "@state:assertNotIn"
    ],
    [
      "test_lock_registry_update_and_rollback_failure_literals_are_exact",
      "@state:assertRaises"
    ],
    [
      "test_lock_registry_update_and_rollback_failure_literals_are_exact",
      "@state:repo"
    ],
    [
      "test_lock_registry_update_and_rollback_failure_literals_are_exact",
      "api_environment"
    ],
    [
      "test_lock_registry_update_and_rollback_failure_literals_are_exact",
      "coordination_snapshot"
    ],
    [
      "test_lock_registry_update_and_rollback_failure_literals_are_exact",
      "open_run"
    ],
    [
      "test_lock_registry_update_and_rollback_failure_literals_are_exact",
      "opening_record"
    ],
    [
      "test_lock_registry_update_and_rollback_failure_literals_are_exact",
      "prime_batch_lock"
    ],
    [
      "test_malformed_registry_remains_generic",
      "@state:assertEqual"
    ],
    [
      "test_malformed_registry_remains_generic",
      "open_run"
    ],
    [
      "test_mixed_open_and_retired_conflicts_are_byte_sorted",
      "@state:assertEqual"
    ],
    [
      "test_mixed_open_and_retired_conflicts_are_byte_sorted",
      "@state:assertFalse"
    ],
    [
      "test_mixed_open_and_retired_conflicts_are_byte_sorted",
      "coordination_snapshot"
    ],
    [
      "test_mixed_open_and_retired_conflicts_are_byte_sorted",
      "open_run"
    ],
    [
      "test_mixed_open_and_retired_conflicts_are_byte_sorted",
      "retire"
    ],
    [
      "test_mixed_open_and_retired_conflicts_are_byte_sorted",
      "run_dir"
    ],
    [
      "test_new_write_validator_control_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_new_write_validator_control_is_load_bearing",
      "@state:assertNotEqual"
    ],
    [
      "test_new_write_validator_control_is_load_bearing",
      "@state:repo"
    ],
    [
      "test_new_write_validator_control_is_load_bearing",
      "api_environment"
    ],
    [
      "test_new_write_validator_control_is_load_bearing",
      "journal_path"
    ],
    [
      "test_new_write_validator_control_is_load_bearing",
      "open_run"
    ],
    [
      "test_non_dot_regular_file_in_runs_root_is_silently_ignored",
      "@state:assertEqual"
    ],
    [
      "test_non_dot_regular_file_in_runs_root_is_silently_ignored",
      "open_run"
    ],
    [
      "test_nonempty_ownerless_orphan_names_validated_repo_relative_path",
      "@state:assertEqual"
    ],
    [
      "test_nonempty_ownerless_orphan_names_validated_repo_relative_path",
      "@state:assertFalse"
    ],
    [
      "test_nonempty_ownerless_orphan_names_validated_repo_relative_path",
      "@state:assertTrue"
    ],
    [
      "test_nonempty_ownerless_orphan_names_validated_repo_relative_path",
      "coordination_snapshot"
    ],
    [
      "test_nonempty_ownerless_orphan_names_validated_repo_relative_path",
      "open_run"
    ],
    [
      "test_nonempty_ownerless_orphan_names_validated_repo_relative_path",
      "run_dir"
    ],
    [
      "test_only_a_retired_successor_may_close_and_release_ancestry",
      "@state:assertEqual"
    ],
    [
      "test_only_a_retired_successor_may_close_and_release_ancestry",
      "close"
    ],
    [
      "test_only_a_retired_successor_may_close_and_release_ancestry",
      "coordination_snapshot"
    ],
    [
      "test_only_a_retired_successor_may_close_and_release_ancestry",
      "open_run"
    ],
    [
      "test_only_a_retired_successor_may_close_and_release_ancestry",
      "retire"
    ],
    [
      "test_operation_specific_invalid_id_and_missing_run_literals",
      "@state:assertEqual"
    ],
    [
      "test_operation_specific_invalid_id_and_missing_run_literals",
      "@state:assertNotIn"
    ],
    [
      "test_operation_specific_invalid_id_and_missing_run_literals",
      "@state:subTest"
    ],
    [
      "test_operation_specific_invalid_id_and_missing_run_literals",
      "append_record"
    ],
    [
      "test_operation_specific_invalid_id_and_missing_run_literals",
      "close"
    ],
    [
      "test_operation_specific_invalid_id_and_missing_run_literals",
      "decision_record"
    ],
    [
      "test_operation_specific_invalid_id_and_missing_run_literals",
      "open_run"
    ],
    [
      "test_operation_specific_invalid_id_and_missing_run_literals",
      "opening_record"
    ],
    [
      "test_operation_specific_invalid_id_and_missing_run_literals",
      "readmit"
    ],
    [
      "test_operation_specific_invalid_id_and_missing_run_literals",
      "retire"
    ],
    [
      "test_operation_specific_repository_unavailable_literals",
      "@state:assertEqual"
    ],
    [
      "test_operation_specific_repository_unavailable_literals",
      "@state:assertNotIn"
    ],
    [
      "test_operation_specific_repository_unavailable_literals",
      "@state:root"
    ],
    [
      "test_operation_specific_repository_unavailable_literals",
      "@state:subTest"
    ],
    [
      "test_operation_specific_repository_unavailable_literals",
      "closure_record"
    ],
    [
      "test_operation_specific_repository_unavailable_literals",
      "command"
    ],
    [
      "test_operation_specific_repository_unavailable_literals",
      "decision_record"
    ],
    [
      "test_operation_specific_repository_unavailable_literals",
      "opening_record"
    ],
    [
      "test_operation_specific_repository_unavailable_literals",
      "write_record"
    ],
    [
      "test_ordinary_append_registry_drift_after_fsync_rolls_back_append",
      "@state:assertEqual"
    ],
    [
      "test_ordinary_append_registry_drift_after_fsync_rolls_back_append",
      "@state:assertGreater"
    ],
    [
      "test_ordinary_append_registry_drift_after_fsync_rolls_back_append",
      "@state:assertRaises"
    ],
    [
      "test_ordinary_append_registry_drift_after_fsync_rolls_back_append",
      "@state:repo"
    ],
    [
      "test_ordinary_append_registry_drift_after_fsync_rolls_back_append",
      "api_environment"
    ],
    [
      "test_ordinary_append_registry_drift_after_fsync_rolls_back_append",
      "decision_record"
    ],
    [
      "test_ordinary_append_registry_drift_after_fsync_rolls_back_append",
      "journal_path"
    ],
    [
      "test_ordinary_append_registry_drift_after_fsync_rolls_back_append",
      "open_run"
    ],
    [
      "test_ordinary_append_registry_drift_after_fsync_rolls_back_append",
      "run_dir"
    ],
    [
      "test_orphan_classifier_control_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_orphan_classifier_control_is_load_bearing",
      "@state:assertRaises"
    ],
    [
      "test_orphan_classifier_control_is_load_bearing",
      "@state:repo"
    ],
    [
      "test_orphan_classifier_control_is_load_bearing",
      "api_environment"
    ],
    [
      "test_orphan_classifier_control_is_load_bearing",
      "coordination_snapshot"
    ],
    [
      "test_orphan_classifier_control_is_load_bearing",
      "open_run"
    ],
    [
      "test_orphan_classifier_control_is_load_bearing",
      "opening_record"
    ],
    [
      "test_orphan_classifier_control_is_load_bearing",
      "run_dir"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "@state:assertEqual"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "@state:assertIsInstance"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "@state:assertIsNotNone"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "@state:assertRaises"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "@state:assertTrue"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "@state:repo"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "@state:root"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "api_environment"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "decision_record"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "open_run"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "proven_dead_pid"
    ],
    [
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "run_dir"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "@state:assertEqual"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "@state:assertFalse"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "@state:subTest"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "append_record"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "close"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "closure_record"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "coordination_snapshot"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "create_citation_files"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "decision_record"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "execution_record"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "execution_result_record"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "open_run"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "opening_record"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "run_dir"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "task_record"
    ],
    [
      "test_per_type_first_required_field_diagnostics_are_exact",
      "verification_record"
    ],
    [
      "test_persisted_dangling_successor_edge_is_generic_and_nonmutating",
      "@state:assertEqual"
    ],
    [
      "test_persisted_dangling_successor_edge_is_generic_and_nonmutating",
      "@state:assertFalse"
    ],
    [
      "test_persisted_dangling_successor_edge_is_generic_and_nonmutating",
      "coordination_snapshot"
    ],
    [
      "test_persisted_dangling_successor_edge_is_generic_and_nonmutating",
      "open_run"
    ],
    [
      "test_persisted_dangling_successor_edge_is_generic_and_nonmutating",
      "plant_run_state"
    ],
    [
      "test_persisted_dangling_successor_edge_is_generic_and_nonmutating",
      "prime_registry_lock"
    ],
    [
      "test_persisted_dangling_successor_edge_is_generic_and_nonmutating",
      "run_dir"
    ],
    [
      "test_persisted_dangling_successor_edge_is_generic_and_nonmutating",
      "write_registry"
    ],
    [
      "test_persisted_disjoint_successor_edge_is_generic_and_nonmutating",
      "@state:assertEqual"
    ],
    [
      "test_persisted_disjoint_successor_edge_is_generic_and_nonmutating",
      "@state:assertFalse"
    ],
    [
      "test_persisted_disjoint_successor_edge_is_generic_and_nonmutating",
      "coordination_snapshot"
    ],
    [
      "test_persisted_disjoint_successor_edge_is_generic_and_nonmutating",
      "open_run"
    ],
    [
      "test_persisted_disjoint_successor_edge_is_generic_and_nonmutating",
      "plant_run_state"
    ],
    [
      "test_persisted_disjoint_successor_edge_is_generic_and_nonmutating",
      "prime_registry_lock"
    ],
    [
      "test_persisted_disjoint_successor_edge_is_generic_and_nonmutating",
      "run_dir"
    ],
    [
      "test_persisted_disjoint_successor_edge_is_generic_and_nonmutating",
      "write_registry"
    ],
    [
      "test_persisted_successor_cycle_is_generic_and_nonmutating",
      "@state:assertEqual"
    ],
    [
      "test_persisted_successor_cycle_is_generic_and_nonmutating",
      "@state:assertFalse"
    ],
    [
      "test_persisted_successor_cycle_is_generic_and_nonmutating",
      "coordination_snapshot"
    ],
    [
      "test_persisted_successor_cycle_is_generic_and_nonmutating",
      "open_run"
    ],
    [
      "test_persisted_successor_cycle_is_generic_and_nonmutating",
      "plant_run_state"
    ],
    [
      "test_persisted_successor_cycle_is_generic_and_nonmutating",
      "prime_registry_lock"
    ],
    [
      "test_persisted_successor_cycle_is_generic_and_nonmutating",
      "run_dir"
    ],
    [
      "test_persisted_successor_cycle_is_generic_and_nonmutating",
      "write_registry"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "@state:assertEqual"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "@state:assertFalse"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "@state:assertNotEqual"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "@state:assertRaises"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "@state:assertTrue"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "@state:repo"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "@state:root"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "@state:subTest"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "api_environment"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "journal_path"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "open_run"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "opening_record"
    ],
    [
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "run_dir"
    ],
    [
      "test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate",
      "@state:assertEqual"
    ],
    [
      "test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate",
      "@state:assertFalse"
    ],
    [
      "test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate",
      "@state:assertRaises"
    ],
    [
      "test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate",
      "@state:repo"
    ],
    [
      "test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate",
      "api_environment"
    ],
    [
      "test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate",
      "journal_path"
    ],
    [
      "test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate",
      "open_run"
    ],
    [
      "test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate",
      "opening_record"
    ],
    [
      "test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate",
      "run_dir"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "@state:assertEqual"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "@state:assertFalse"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "@state:assertRaises"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "@state:assertTrue"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "@state:repo"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "@state:root"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "@state:subTest"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "api_environment"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "decision_record"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "journal_path"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "open_run"
    ],
    [
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "run_dir"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "@state:assertEqual"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "@state:assertIn"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "@state:assertRaises"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "@state:assertTrue"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "@state:repo"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "@state:root"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "api_environment"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "decision_record"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "journal_path"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "open_run"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "opening_record"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "proven_dead_pid"
    ],
    [
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "run_dir"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "@state:assertEqual"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "@state:assertFalse"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "@state:assertNotEqual"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "@state:assertRaises"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "@state:repo"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "@state:subTest"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "api_environment"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "closure_record"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "coordination_snapshot"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "open_run"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "opening_record"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "prime_batch_lock"
    ],
    [
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "run_dir"
    ],
    [
      "test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent",
      "@state:assertEqual"
    ],
    [
      "test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent",
      "@state:assertRaises"
    ],
    [
      "test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent",
      "@state:assertTrue"
    ],
    [
      "test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent",
      "@state:repo"
    ],
    [
      "test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent",
      "api_environment"
    ],
    [
      "test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent",
      "journal_path"
    ],
    [
      "test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent",
      "opening_record"
    ],
    [
      "test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent",
      "prime_registry_lock"
    ],
    [
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "@state:assertEqual"
    ],
    [
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "@state:assertRaises"
    ],
    [
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "@state:assertTrue"
    ],
    [
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "@state:repo"
    ],
    [
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "api_environment"
    ],
    [
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "decision_record"
    ],
    [
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "journal_path"
    ],
    [
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "opening_record"
    ],
    [
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "prime_registry_lock"
    ],
    [
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "proven_dead_pid"
    ],
    [
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
      "run_dir"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "@state:assertEqual"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "@state:assertFalse"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "@state:assertRaises"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "@state:assertTrue"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "@state:repo"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "api_environment"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "coordination_snapshot"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "decision_record"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "journal_path"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "open_run"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "opening_record"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "prime_batch_lock"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "prime_registry_lock"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "proven_dead_pid"
    ],
    [
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "run_dir"
    ],
    [
      "test_registered_missing_journal_remains_generic",
      "@state:assertEqual"
    ],
    [
      "test_registered_missing_journal_remains_generic",
      "@state:repo"
    ],
    [
      "test_registered_missing_journal_remains_generic",
      "coordination_snapshot"
    ],
    [
      "test_registered_missing_journal_remains_generic",
      "open_run"
    ],
    [
      "test_registered_missing_journal_remains_generic",
      "run_dir"
    ],
    [
      "test_registered_missing_journal_remains_generic",
      "write_registry"
    ],
    [
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "@state:assertEqual"
    ],
    [
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "@state:assertFalse"
    ],
    [
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "@state:assertRaises"
    ],
    [
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "@state:assertTrue"
    ],
    [
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "@state:repo"
    ],
    [
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "@state:root"
    ],
    [
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "api_environment"
    ],
    [
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "journal_path"
    ],
    [
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "open_run"
    ],
    [
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "opening_record"
    ],
    [
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "run_dir"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "@state:assertEqual"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "@state:assertRaises"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "@state:assertTrue"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "@state:repo"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "@state:root"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "@state:subTest"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "api_environment"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "coordination_snapshot"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "journal_path"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "open_run"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "prime_batch_lock"
    ],
    [
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "run_dir"
    ],
    [
      "test_registry_restoration_cleanup_occurs_only_after_final_proof",
      "@state:assertEqual"
    ],
    [
      "test_registry_restoration_cleanup_occurs_only_after_final_proof",
      "@state:assertFalse"
    ],
    [
      "test_registry_restoration_cleanup_occurs_only_after_final_proof",
      "@state:assertRaises"
    ],
    [
      "test_registry_restoration_cleanup_occurs_only_after_final_proof",
      "@state:assertTrue"
    ],
    [
      "test_registry_restoration_cleanup_occurs_only_after_final_proof",
      "@state:repo"
    ],
    [
      "test_registry_restoration_cleanup_occurs_only_after_final_proof",
      "api_environment"
    ],
    [
      "test_registry_restoration_cleanup_occurs_only_after_final_proof",
      "coordination_snapshot"
    ],
    [
      "test_registry_restoration_cleanup_occurs_only_after_final_proof",
      "open_run"
    ],
    [
      "test_registry_restoration_cleanup_occurs_only_after_final_proof",
      "opening_record"
    ],
    [
      "test_registry_restoration_cleanup_occurs_only_after_final_proof",
      "run_dir"
    ],
    [
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "@state:assertEqual"
    ],
    [
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "@state:assertIn"
    ],
    [
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "@state:assertNotEqual"
    ],
    [
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "@state:assertRaises"
    ],
    [
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "@state:assertTrue"
    ],
    [
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "@state:repo"
    ],
    [
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "api_environment"
    ],
    [
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "journal_path"
    ],
    [
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "open_run"
    ],
    [
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "opening_record"
    ],
    [
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "run_dir"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "@state:assertEqual"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "@state:assertFalse"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "@state:assertRaises"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "@state:assertTrue"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "@state:repo"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "@state:root"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "@state:subTest"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "api_environment"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "journal_path"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "open_run"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "opening_record"
    ],
    [
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "run_dir"
    ],
    [
      "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "@state:assertEqual"
    ],
    [
      "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "@state:assertFalse"
    ],
    [
      "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "@state:assertRaises"
    ],
    [
      "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "@state:repo"
    ],
    [
      "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "api_environment"
    ],
    [
      "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "closure_record"
    ],
    [
      "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "open_run"
    ],
    [
      "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "opening_record"
    ],
    [
      "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "retire"
    ],
    [
      "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "run_dir"
    ],
    [
      "test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes",
      "@state:assertEqual"
    ],
    [
      "test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes",
      "@state:subTest"
    ],
    [
      "test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes",
      "append_record"
    ],
    [
      "test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes",
      "coordination_snapshot"
    ],
    [
      "test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes",
      "open_run"
    ],
    [
      "test_run_directory_identity_swap_at_publication_rolls_back_original",
      "@state:assertEqual"
    ],
    [
      "test_run_directory_identity_swap_at_publication_rolls_back_original",
      "@state:assertRaises"
    ],
    [
      "test_run_directory_identity_swap_at_publication_rolls_back_original",
      "@state:assertTrue"
    ],
    [
      "test_run_directory_identity_swap_at_publication_rolls_back_original",
      "@state:repo"
    ],
    [
      "test_run_directory_identity_swap_at_publication_rolls_back_original",
      "@state:root"
    ],
    [
      "test_run_directory_identity_swap_at_publication_rolls_back_original",
      "api_environment"
    ],
    [
      "test_run_directory_identity_swap_at_publication_rolls_back_original",
      "journal_path"
    ],
    [
      "test_run_directory_identity_swap_at_publication_rolls_back_original",
      "open_run"
    ],
    [
      "test_run_directory_identity_swap_at_publication_rolls_back_original",
      "run_dir"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "@state:assertEqual"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "@state:assertFalse"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "@state:assertRaises"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "@state:assertTrue"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "@state:repo"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "@state:root"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "@state:subTest"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "api_environment"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "coordination_snapshot"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "open_run"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "opening_record"
    ],
    [
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "prime_registry_lock"
    ],
    [
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "@state:assertEqual"
    ],
    [
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "@state:assertRaises"
    ],
    [
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "@state:assertTrue"
    ],
    [
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "@state:repo"
    ],
    [
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "@state:root"
    ],
    [
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "@state:subTest"
    ],
    [
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "api_environment"
    ],
    [
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "journal_path"
    ],
    [
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "open_run"
    ],
    [
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "opening_record"
    ],
    [
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "run_dir"
    ],
    [
      "test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct",
      "@state:assertEqual"
    ],
    [
      "test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct",
      "@state:root"
    ],
    [
      "test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct",
      "append_record"
    ],
    [
      "test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct",
      "close"
    ],
    [
      "test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct",
      "decision_record"
    ],
    [
      "test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct",
      "journal_path"
    ],
    [
      "test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct",
      "open_run"
    ],
    [
      "test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct",
      "readmit"
    ],
    [
      "test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct",
      "retire"
    ],
    [
      "test_sparse_history_reads_unchanged_but_same_new_shape_refuses",
      "@state:assertEqual"
    ],
    [
      "test_sparse_history_reads_unchanged_but_same_new_shape_refuses",
      "@state:assertIsInstance"
    ],
    [
      "test_sparse_history_reads_unchanged_but_same_new_shape_refuses",
      "append_record"
    ],
    [
      "test_sparse_history_reads_unchanged_but_same_new_shape_refuses",
      "coordination_snapshot"
    ],
    [
      "test_sparse_history_reads_unchanged_but_same_new_shape_refuses",
      "journal_path"
    ],
    [
      "test_sparse_history_reads_unchanged_but_same_new_shape_refuses",
      "open_run"
    ],
    [
      "test_sparse_history_reads_unchanged_but_same_new_shape_refuses",
      "run_dir"
    ],
    [
      "test_stale_owner_append_failure_restores_owner_and_journal",
      "@state:assertEqual"
    ],
    [
      "test_stale_owner_append_failure_restores_owner_and_journal",
      "@state:assertNotEqual"
    ],
    [
      "test_stale_owner_append_failure_restores_owner_and_journal",
      "@state:assertRaises"
    ],
    [
      "test_stale_owner_append_failure_restores_owner_and_journal",
      "@state:assertTrue"
    ],
    [
      "test_stale_owner_append_failure_restores_owner_and_journal",
      "@state:repo"
    ],
    [
      "test_stale_owner_append_failure_restores_owner_and_journal",
      "api_environment"
    ],
    [
      "test_stale_owner_append_failure_restores_owner_and_journal",
      "decision_record"
    ],
    [
      "test_stale_owner_append_failure_restores_owner_and_journal",
      "open_run"
    ],
    [
      "test_stale_owner_append_failure_restores_owner_and_journal",
      "proven_dead_pid"
    ],
    [
      "test_stale_owner_append_failure_restores_owner_and_journal",
      "run_dir"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "@state:assertEqual"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "@state:assertNotEqual"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "@state:assertRaises"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "@state:repo"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "@state:subTest"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "api_environment"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "closure_record"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "coordination_snapshot"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "open_run"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "prime_batch_lock"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "proven_dead_pid"
    ],
    [
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "run_dir"
    ],
    [
      "test_successor_chain_transfers_ancestry_releases_and_readmits",
      "@state:assertEqual"
    ],
    [
      "test_successor_chain_transfers_ancestry_releases_and_readmits",
      "@state:assertFalse"
    ],
    [
      "test_successor_chain_transfers_ancestry_releases_and_readmits",
      "@state:repo"
    ],
    [
      "test_successor_chain_transfers_ancestry_releases_and_readmits",
      "command"
    ],
    [
      "test_successor_chain_transfers_ancestry_releases_and_readmits",
      "open_run"
    ],
    [
      "test_successor_chain_transfers_ancestry_releases_and_readmits",
      "readmit"
    ],
    [
      "test_successor_chain_transfers_ancestry_releases_and_readmits",
      "retire"
    ],
    [
      "test_successor_chain_transfers_ancestry_releases_and_readmits",
      "run_dir"
    ],
    [
      "test_successor_readmission_may_leave_ancestor_scope_but_keeps_it_reserved",
      "@state:assertEqual"
    ],
    [
      "test_successor_readmission_may_leave_ancestor_scope_but_keeps_it_reserved",
      "open_run"
    ],
    [
      "test_successor_readmission_may_leave_ancestor_scope_but_keeps_it_reserved",
      "readmit"
    ],
    [
      "test_successor_readmission_may_leave_ancestor_scope_but_keeps_it_reserved",
      "retire"
    ],
    [
      "test_successor_refusal_literals_for_retired_overlap_and_disjoint_scope",
      "@state:assertEqual"
    ],
    [
      "test_successor_refusal_literals_for_retired_overlap_and_disjoint_scope",
      "open_run"
    ],
    [
      "test_successor_refusal_literals_for_retired_overlap_and_disjoint_scope",
      "retire"
    ],
    [
      "test_successor_transfer_control_is_load_bearing",
      "@state:assertEqual"
    ],
    [
      "test_successor_transfer_control_is_load_bearing",
      "@state:assertFalse"
    ],
    [
      "test_successor_transfer_control_is_load_bearing",
      "@state:assertRaises"
    ],
    [
      "test_successor_transfer_control_is_load_bearing",
      "@state:repo"
    ],
    [
      "test_successor_transfer_control_is_load_bearing",
      "api_environment"
    ],
    [
      "test_successor_transfer_control_is_load_bearing",
      "coordination_snapshot"
    ],
    [
      "test_successor_transfer_control_is_load_bearing",
      "open_run"
    ],
    [
      "test_successor_transfer_control_is_load_bearing",
      "opening_record"
    ],
    [
      "test_successor_transfer_control_is_load_bearing",
      "retire"
    ],
    [
      "test_successor_transfer_control_is_load_bearing",
      "run_dir"
    ],
    [
      "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "@state:assertEqual"
    ],
    [
      "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "@state:assertRaises"
    ],
    [
      "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "@state:assertTrue"
    ],
    [
      "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "@state:repo"
    ],
    [
      "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "api_environment"
    ],
    [
      "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "coordination_snapshot"
    ],
    [
      "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "decision_record"
    ],
    [
      "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "open_run"
    ],
    [
      "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "proven_dead_pid"
    ],
    [
      "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "run_dir"
    ],
    [
      "valid_candidate",
      "opening_record"
    ],
    [
      "write_record",
      "@state:_record_number"
    ],
    [
      "write_record",
      "@state:root"
    ]
  ],
  "clusters": [
    [
      "setUp",
      "write_record",
      "command",
      "closure_record",
      "append_record",
      "readmit",
      "retire",
      "close",
      "prime_batch_lock",
      "test_array_members_fail_at_the_first_ascending_index",
      "test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes",
      "test_sparse_history_reads_unchanged_but_same_new_shape_refuses",
      "test_foreign_owner_classification_precedes_candidate_schema",
      "test_engine_lifecycle_envelope_is_built_before_session_identity",
      "test_new_write_validator_control_is_load_bearing",
      "test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry",
      "test_invalid_session_pid_literal_is_retained",
      "test_live_session_identity_is_stable_across_fresh_cli_shells",
      "test_operation_specific_invalid_id_and_missing_run_literals",
      "test_operation_specific_repository_unavailable_literals",
      "test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct",
      "test_lock_registry_update_and_rollback_failure_literals_are_exact",
      "test_post_scan_journal_target_swaps_are_generic_and_never_followed",
      "test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating",
      "test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting",
      "test_postpublication_fault_restores_every_lifecycle_transaction",
      "test_registry_restoration_failure_retains_published_run_and_journal",
      "test_existing_registry_publication_keeps_canonical_name_present",
      "test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
      "test_registry_exchange_race_restores_foreign_canonical_without_publish",
      "test_exact_staged_owner_prelink_is_recognized_as_adopted",
      "test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
      "test_empty_placeholder_is_silent_for_all_unrelated_coordination",
      "test_empty_placeholder_targeted_validate_and_monitor_remain_unchanged",
      "test_same_id_state_created_after_final_classification_is_never_overwritten",
      "test_ambiguous_orphan_kinds_remain_generic_and_nonmutating",
      "test_successor_transfer_control_is_load_bearing",
      "test_successor_chain_transfers_ancestry_releases_and_readmits",
      "test_successor_readmission_may_leave_ancestor_scope_but_keeps_it_reserved",
      "test_successor_refusal_literals_for_retired_overlap_and_disjoint_scope",
      "test_mixed_open_and_retired_conflicts_are_byte_sorted",
      "test_concurrent_successor_and_ordinary_admission_serialize_atomically",
      "test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty",
      "test_claimed_candidate_child_is_preserved_but_never_published",
      "test_cleanup_identity_replacements_preserve_foreign_state_and_fail",
      "test_placeholder_inode_and_type_replacement_at_publication_are_generic",
      "test_run_directory_identity_swap_at_publication_rolls_back_original",
      "test_journal_identity_swap_at_publication_rolls_back_bound_original",
      "test_only_a_retired_successor_may_close_and_release_ancestry",
      "test_close_rollback_preserves_effective_ancestral_reservation",
      "test_release_control_disabled_keeps_retired_ancestry_reserved",
      "test_historical_fork_releases_shared_ancestor_only_after_both_branches_close"
    ],
    [
      "runs_root"
    ],
    [
      "registry_path"
    ],
    [
      "task_record",
      "execution_record",
      "execution_result_record",
      "verification_record",
      "decision_record",
      "create_citation_files",
      "proven_dead_pid",
      "test_all_seven_strict_minimum_record_types_append",
      "test_per_type_first_required_field_diagnostics_are_exact",
      "test_first_failure_examples_and_envelope_literal_are_exact",
      "test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes",
      "test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
      "test_citation_controls_precede_current_session_identity_refusals",
      "test_current_session_identity_literals_are_exact_and_nonmutating",
      "test_citation_controls_precede_recorded_owner_classification",
      "test_ordinary_append_registry_drift_after_fsync_rolls_back_append",
      "test_stale_owner_append_failure_restores_owner_and_journal",
      "test_owner_restoration_identity_conflict_preserves_foreign_owner",
      "test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
      "test_postsyscall_baseexception_during_rollback_retains_coherent_candidate"
    ],
    [
      "write_registry",
      "prime_registry_lock",
      "assert_absent_registry_node_collision",
      "plant_run_state",
      "test_initially_absent_registry_is_removed_after_postpublication_fault",
      "test_absent_registry_link_race_never_clobbers_foreign_canonical",
      "test_absent_registry_directory_collision_preserves_foreign_node",
      "test_absent_registry_symlink_collision_preserves_foreign_node",
      "test_absent_registry_broken_symlink_collision_preserves_foreign_node",
      "test_absent_registry_unreadable_file_collision_preserves_foreign_node",
      "test_exact_staged_registry_prelink_is_recognized_as_published",
      "test_exact_staged_registry_prelink_rolls_back_after_validation_failure",
      "test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent",
      "test_registered_missing_journal_remains_generic",
      "test_persisted_dangling_successor_edge_is_generic_and_nonmutating",
      "test_persisted_successor_cycle_is_generic_and_nonmutating",
      "test_persisted_disjoint_successor_edge_is_generic_and_nonmutating",
      "test_legacy_successor_close_without_valid_judgment_cannot_release_scope"
    ],
    [
      "valid_candidate",
      "assert_invalid_candidate",
      "assert_valid_candidate",
      "test_fr019_common_and_required_string_boundaries",
      "test_fr019_format_enum_repository_and_scope_boundaries",
      "test_fr019_all_arrays_and_nested_validation_boundaries",
      "test_fr019_inheritance_events_handoff_optionals_and_extensions"
    ],
    [
      "test_engine_lifecycle_owner_classification_precedes_schema"
    ],
    [
      "test_malformed_registry_remains_generic"
    ],
    [
      "test_registry_restoration_cleanup_occurs_only_after_final_proof"
    ],
    [
      "test_nonempty_ownerless_orphan_names_validated_repo_relative_path"
    ],
    [
      "test_non_dot_regular_file_in_runs_root_is_silently_ignored"
    ],
    [
      "test_orphan_classifier_control_is_load_bearing"
    ],
    [
      "test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate"
    ],
    [
      "open_run"
    ],
    [
      "run_dir"
    ],
    [
      "api_environment"
    ],
    [
      "coordination_snapshot"
    ],
    [
      "opening_record"
    ],
    [
      "journal_path"
    ]
  ],
  "hubs": [
    "@state:assertEqual",
    "open_run",
    "@state:repo",
    "run_dir",
    "api_environment",
    "@state:assertRaises",
    "coordination_snapshot",
    "opening_record",
    "@state:assertFalse",
    "@state:assertTrue",
    "@state:subTest",
    "journal_path"
  ],
  "prerequisites": [
    {
      "name": "TOOLS",
      "line": 19,
      "users": [
        {
          "method": "Revision8CoordinationTests.command",
          "line": 87
        },
        {
          "method": "Revision8CoordinationTests.test_concurrent_successor_and_ordinary_admission_serialize_atomically",
          "line": 4566
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    },
    {
      "name": "RECORDED_AT",
      "line": 25,
      "users": [
        {
          "method": "Revision8CoordinationTests.opening_record",
          "line": 108
        },
        {
          "method": "Revision8CoordinationTests.task_record",
          "line": 122
        },
        {
          "method": "Revision8CoordinationTests.execution_record",
          "line": 135
        },
        {
          "method": "Revision8CoordinationTests.execution_result_record",
          "line": 157
        },
        {
          "method": "Revision8CoordinationTests.verification_record",
          "line": 173
        },
        {
          "method": "Revision8CoordinationTests.decision_record",
          "line": 189
        },
        {
          "method": "Revision8CoordinationTests.closure_record",
          "line": 200
        },
        {
          "method": "Revision8CoordinationTests.plant_run_state",
          "line": 538
        },
        {
          "method": "Revision8CoordinationTests.test_fr019_inheritance_events_handoff_optionals_and_extensions",
          "line": 1079
        },
        {
          "method": "Revision8CoordinationTests.test_first_failure_examples_and_envelope_literal_are_exact",
          "line": 1198
        },
        {
          "method": "Revision8CoordinationTests.test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes",
          "line": 1255
        },
        {
          "method": "Revision8CoordinationTests.test_sparse_history_reads_unchanged_but_same_new_shape_refuses",
          "line": 1286
        },
        {
          "method": "Revision8CoordinationTests.test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes",
          "line": 1325
        },
        {
          "method": "Revision8CoordinationTests.test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes",
          "line": 1355
        },
        {
          "method": "Revision8CoordinationTests.test_foreign_owner_classification_precedes_candidate_schema",
          "line": 1381
        },
        {
          "method": "Revision8CoordinationTests.test_citation_controls_precede_recorded_owner_classification",
          "line": 1577
        },
        {
          "method": "Revision8CoordinationTests.test_new_write_validator_control_is_load_bearing",
          "line": 1654
        },
        {
          "method": "Revision8CoordinationTests.test_stale_owner_append_failure_restores_owner_and_journal",
          "line": 2524
        },
        {
          "method": "Revision8CoordinationTests.test_stale_owner_lifecycle_failure_restores_all_transaction_bytes",
          "line": 2580
        },
        {
          "method": "Revision8CoordinationTests.test_owner_restoration_identity_conflict_preserves_foreign_owner",
          "line": 2664
        },
        {
          "method": "Revision8CoordinationTests.test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner",
          "line": 3085
        },
        {
          "method": "Revision8CoordinationTests.test_postsyscall_baseexception_restores_registry_and_owner_begin_paths",
          "line": 3235
        },
        {
          "method": "Revision8CoordinationTests.test_postsyscall_baseexception_during_rollback_retains_coherent_candidate",
          "line": 3437
        },
        {
          "method": "Revision8CoordinationTests.test_legacy_successor_close_without_valid_judgment_cannot_release_scope",
          "line": 4493
        },
        {
          "method": "Revision8CoordinationTests.test_historical_fork_releases_shared_ancestor_only_after_both_branches_close",
          "line": 5205
        }
      ],
      "action": "relocate to a non-discovered support module before method extraction"
    }
  ],
  "census": [],
  "census_complete": false
}
