{
  "name": "Revision9BindingTests",
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
      "line": 247,
      "end_line": 251,
      "decorators": [],
      "reads": [
        "addCleanup",
        "repo",
        "temporary"
      ],
      "writes": [
        "repo",
        "temporary"
      ],
      "calls": [
        "addCleanup"
      ],
      "globals": [
        "Path",
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
      "name": "binding",
      "line": 253,
      "end_line": 271,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
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
      "name": "_write_commit_gate_binding_chain",
      "line": 273,
      "end_line": 523,
      "decorators": [],
      "reads": [
        "repo"
      ],
      "writes": [],
      "calls": [],
      "globals": [
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
      "name": "_write_commit_decision_cycle_chain",
      "line": 525,
      "end_line": 883,
      "decorators": [],
      "reads": [
        "_write_commit_gate_binding_chain",
        "repo"
      ],
      "writes": [],
      "calls": [
        "_write_commit_gate_binding_chain"
      ],
      "globals": [
        "copy",
        "journal",
        "json",
        "key"
      ],
      "nested_defs": [
        "next_at",
        "append_event",
        "prepare_approval",
        "restage"
      ],
      "nonlocal_names": [
        "minute",
        "previous",
        "state"
      ],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_resolver_rejects_stale_and_result_mismatched_gate_bindings",
      "line": 885,
      "end_line": 939,
      "decorators": [],
      "reads": [
        "_write_commit_gate_binding_chain",
        "assertEqual",
        "assertRaisesRegex",
        "repo",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_write_commit_gate_binding_chain",
        "assertEqual",
        "assertRaisesRegex",
        "subTest"
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
      "name": "test_resolver_rejects_recreated_approval_and_skip_facts",
      "line": 941,
      "end_line": 995,
      "decorators": [],
      "reads": [
        "_write_commit_decision_cycle_chain",
        "assertEqual",
        "assertRaisesRegex",
        "repo",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_write_commit_decision_cycle_chain",
        "assertEqual",
        "assertRaisesRegex",
        "subTest"
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
      "name": "test_resolver_rejects_candidate_cycles_retaining_decision_facts",
      "line": 997,
      "end_line": 1025,
      "decorators": [],
      "reads": [
        "_write_commit_decision_cycle_chain",
        "assertRaisesRegex",
        "repo",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_write_commit_decision_cycle_chain",
        "assertRaisesRegex",
        "subTest"
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
      "name": "test_dm001_exact_shape_candidate_and_review_vectors",
      "line": 1027,
      "end_line": 1116,
      "decorators": [],
      "reads": [
        "assertFalse",
        "assertTrue",
        "binding"
      ],
      "writes": [],
      "calls": [
        "assertFalse",
        "assertTrue",
        "binding"
      ],
      "globals": [
        "copy",
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
      "name": "test_commit_candidate_binding_reconstructs_v2_without_relabeling_history",
      "line": 1118,
      "end_line": 1192,
      "decorators": [],
      "reads": [
        "assertEqual",
        "assertIsNone",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "assertIsNone",
        "subTest"
      ],
      "globals": [
        "builders",
        "copy",
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
      "name": "test_commit_identity_binding_projects_existing_verification_type",
      "line": 1194,
      "end_line": 1303,
      "decorators": [],
      "reads": [
        "assertFalse",
        "assertIsNotNone",
        "assertTrue",
        "binding"
      ],
      "writes": [],
      "calls": [
        "assertFalse",
        "assertIsNotNone",
        "assertTrue",
        "binding"
      ],
      "globals": [
        "builders",
        "copy",
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
      "name": "test_binding_currentness_rejects_superseded_gate_facts",
      "line": 1305,
      "end_line": 1509,
      "decorators": [],
      "reads": [
        "assertFalse",
        "assertTrue",
        "binding"
      ],
      "writes": [],
      "calls": [
        "assertFalse",
        "assertTrue",
        "binding"
      ],
      "globals": [
        "builders",
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
      "name": "test_binding_currentness_rejects_superseded_review_tuple",
      "line": 1511,
      "end_line": 1577,
      "decorators": [],
      "reads": [
        "assertFalse",
        "assertTrue",
        "binding"
      ],
      "writes": [],
      "calls": [
        "assertFalse",
        "assertTrue",
        "binding"
      ],
      "globals": [
        "builders",
        "copy",
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
      "name": "correlation_records",
      "line": 1579,
      "end_line": 1622,
      "decorators": [],
      "reads": [
        "binding"
      ],
      "writes": [],
      "calls": [
        "binding"
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
      "name": "issue_for",
      "line": 1624,
      "end_line": 1627,
      "decorators": [],
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
      "verdict": "ok"
    },
    {
      "name": "test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task",
      "line": 1629,
      "end_line": 1684,
      "decorators": [],
      "reads": [
        "assertEqual",
        "binding",
        "correlation_records",
        "issue_for"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "binding",
        "correlation_records",
        "issue_for"
      ],
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
      "name": "_relined",
      "line": 1686,
      "end_line": 1689,
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
      "name": "_superseded_set",
      "line": 1691,
      "end_line": 1721,
      "decorators": [],
      "reads": [
        "binding"
      ],
      "writes": [],
      "calls": [
        "binding"
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
      "name": "_with_control_removed",
      "line": 1723,
      "end_line": 1727,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
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
      "name": "test_fr021_superseded_candidate_records_are_retired",
      "line": 1729,
      "end_line": 1916,
      "decorators": [],
      "reads": [
        "_relined",
        "_superseded_set",
        "_with_control_removed",
        "assertEqual",
        "assertIn",
        "binding",
        "correlation_records",
        "issue_for"
      ],
      "writes": [],
      "calls": [
        "_relined",
        "_superseded_set",
        "_with_control_removed",
        "assertEqual",
        "assertIn",
        "binding",
        "correlation_records",
        "issue_for"
      ],
      "globals": [
        "copy",
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
      "name": "test_fr021_precedence_rule_scopes_to_the_landed_candidate",
      "line": 1918,
      "end_line": 1973,
      "decorators": [],
      "reads": [
        "_relined",
        "_superseded_set",
        "_with_control_removed",
        "assertEqual",
        "assertTrue",
        "binding",
        "correlation_records",
        "issue_for"
      ],
      "writes": [],
      "calls": [
        "_relined",
        "_superseded_set",
        "_with_control_removed",
        "assertEqual",
        "assertTrue",
        "binding",
        "correlation_records",
        "issue_for"
      ],
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
      "name": "test_fr021_post_landing_result_moves_no_boundary",
      "line": 1975,
      "end_line": 2069,
      "decorators": [],
      "reads": [
        "_relined",
        "_with_control_removed",
        "assertEqual",
        "assertTrue",
        "correlation_records",
        "issue_for"
      ],
      "writes": [],
      "calls": [
        "_relined",
        "_with_control_removed",
        "assertEqual",
        "assertTrue",
        "correlation_records",
        "issue_for"
      ],
      "globals": [
        "copy",
        "journal"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_fr021_four_exact_correlation_issues_and_disabled_control",
      "line": 2071,
      "end_line": 2108,
      "decorators": [],
      "reads": [
        "assertEqual",
        "binding",
        "correlation_records",
        "issue_for"
      ],
      "writes": [],
      "calls": [
        "assertEqual",
        "binding",
        "correlation_records",
        "issue_for"
      ],
      "globals": [
        "copy",
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
      "name": "_semantic_state",
      "line": 2110,
      "end_line": 2174,
      "decorators": [],
      "reads": [
        "repo"
      ],
      "writes": [],
      "calls": [],
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
      "name": "_write_semantic_chain",
      "line": 2176,
      "end_line": 2317,
      "decorators": [],
      "reads": [
        "_semantic_state",
        "binding",
        "repo"
      ],
      "writes": [],
      "calls": [
        "_semantic_state",
        "binding"
      ],
      "globals": [
        "copy",
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
      "name": "test_commit_and_merge_replay_reject_invented_self_consistent_transitions",
      "line": 2319,
      "end_line": 2341,
      "decorators": [],
      "reads": [
        "_write_semantic_chain",
        "assertRaisesRegex",
        "repo",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_write_semantic_chain",
        "assertRaisesRegex",
        "subTest"
      ],
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
      "name": "test_commit_and_merge_replay_reject_digest_valid_candidate_rollback",
      "line": 2343,
      "end_line": 2370,
      "decorators": [],
      "reads": [
        "_write_semantic_chain",
        "assertRaisesRegex",
        "repo",
        "subTest",
        "temporary"
      ],
      "writes": [
        "repo"
      ],
      "calls": [
        "_write_semantic_chain",
        "assertRaisesRegex",
        "subTest"
      ],
      "globals": [
        "Path",
        "builders",
        "journal",
        "subprocess"
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
      "_semantic_state",
      "@state:repo"
    ],
    [
      "_superseded_set",
      "binding"
    ],
    [
      "_write_commit_decision_cycle_chain",
      "@state:repo"
    ],
    [
      "_write_commit_decision_cycle_chain",
      "_write_commit_gate_binding_chain"
    ],
    [
      "_write_commit_gate_binding_chain",
      "@state:repo"
    ],
    [
      "_write_semantic_chain",
      "@state:repo"
    ],
    [
      "_write_semantic_chain",
      "_semantic_state"
    ],
    [
      "_write_semantic_chain",
      "binding"
    ],
    [
      "correlation_records",
      "binding"
    ],
    [
      "setUp",
      "@state:addCleanup"
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
      "test_binding_currentness_rejects_superseded_gate_facts",
      "@state:assertFalse"
    ],
    [
      "test_binding_currentness_rejects_superseded_gate_facts",
      "@state:assertTrue"
    ],
    [
      "test_binding_currentness_rejects_superseded_gate_facts",
      "binding"
    ],
    [
      "test_binding_currentness_rejects_superseded_review_tuple",
      "@state:assertFalse"
    ],
    [
      "test_binding_currentness_rejects_superseded_review_tuple",
      "@state:assertTrue"
    ],
    [
      "test_binding_currentness_rejects_superseded_review_tuple",
      "binding"
    ],
    [
      "test_commit_and_merge_replay_reject_digest_valid_candidate_rollback",
      "@state:assertRaisesRegex"
    ],
    [
      "test_commit_and_merge_replay_reject_digest_valid_candidate_rollback",
      "@state:repo"
    ],
    [
      "test_commit_and_merge_replay_reject_digest_valid_candidate_rollback",
      "@state:subTest"
    ],
    [
      "test_commit_and_merge_replay_reject_digest_valid_candidate_rollback",
      "@state:temporary"
    ],
    [
      "test_commit_and_merge_replay_reject_digest_valid_candidate_rollback",
      "_write_semantic_chain"
    ],
    [
      "test_commit_and_merge_replay_reject_invented_self_consistent_transitions",
      "@state:assertRaisesRegex"
    ],
    [
      "test_commit_and_merge_replay_reject_invented_self_consistent_transitions",
      "@state:repo"
    ],
    [
      "test_commit_and_merge_replay_reject_invented_self_consistent_transitions",
      "@state:subTest"
    ],
    [
      "test_commit_and_merge_replay_reject_invented_self_consistent_transitions",
      "_write_semantic_chain"
    ],
    [
      "test_commit_candidate_binding_reconstructs_v2_without_relabeling_history",
      "@state:assertEqual"
    ],
    [
      "test_commit_candidate_binding_reconstructs_v2_without_relabeling_history",
      "@state:assertIsNone"
    ],
    [
      "test_commit_candidate_binding_reconstructs_v2_without_relabeling_history",
      "@state:subTest"
    ],
    [
      "test_commit_identity_binding_projects_existing_verification_type",
      "@state:assertFalse"
    ],
    [
      "test_commit_identity_binding_projects_existing_verification_type",
      "@state:assertIsNotNone"
    ],
    [
      "test_commit_identity_binding_projects_existing_verification_type",
      "@state:assertTrue"
    ],
    [
      "test_commit_identity_binding_projects_existing_verification_type",
      "binding"
    ],
    [
      "test_dm001_exact_shape_candidate_and_review_vectors",
      "@state:assertFalse"
    ],
    [
      "test_dm001_exact_shape_candidate_and_review_vectors",
      "@state:assertTrue"
    ],
    [
      "test_dm001_exact_shape_candidate_and_review_vectors",
      "binding"
    ],
    [
      "test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task",
      "@state:assertEqual"
    ],
    [
      "test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task",
      "binding"
    ],
    [
      "test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task",
      "correlation_records"
    ],
    [
      "test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task",
      "issue_for"
    ],
    [
      "test_fr021_four_exact_correlation_issues_and_disabled_control",
      "@state:assertEqual"
    ],
    [
      "test_fr021_four_exact_correlation_issues_and_disabled_control",
      "binding"
    ],
    [
      "test_fr021_four_exact_correlation_issues_and_disabled_control",
      "correlation_records"
    ],
    [
      "test_fr021_four_exact_correlation_issues_and_disabled_control",
      "issue_for"
    ],
    [
      "test_fr021_post_landing_result_moves_no_boundary",
      "@state:assertEqual"
    ],
    [
      "test_fr021_post_landing_result_moves_no_boundary",
      "@state:assertTrue"
    ],
    [
      "test_fr021_post_landing_result_moves_no_boundary",
      "_relined"
    ],
    [
      "test_fr021_post_landing_result_moves_no_boundary",
      "_with_control_removed"
    ],
    [
      "test_fr021_post_landing_result_moves_no_boundary",
      "correlation_records"
    ],
    [
      "test_fr021_post_landing_result_moves_no_boundary",
      "issue_for"
    ],
    [
      "test_fr021_precedence_rule_scopes_to_the_landed_candidate",
      "@state:assertEqual"
    ],
    [
      "test_fr021_precedence_rule_scopes_to_the_landed_candidate",
      "@state:assertTrue"
    ],
    [
      "test_fr021_precedence_rule_scopes_to_the_landed_candidate",
      "_relined"
    ],
    [
      "test_fr021_precedence_rule_scopes_to_the_landed_candidate",
      "_superseded_set"
    ],
    [
      "test_fr021_precedence_rule_scopes_to_the_landed_candidate",
      "_with_control_removed"
    ],
    [
      "test_fr021_precedence_rule_scopes_to_the_landed_candidate",
      "binding"
    ],
    [
      "test_fr021_precedence_rule_scopes_to_the_landed_candidate",
      "correlation_records"
    ],
    [
      "test_fr021_precedence_rule_scopes_to_the_landed_candidate",
      "issue_for"
    ],
    [
      "test_fr021_superseded_candidate_records_are_retired",
      "@state:assertEqual"
    ],
    [
      "test_fr021_superseded_candidate_records_are_retired",
      "@state:assertIn"
    ],
    [
      "test_fr021_superseded_candidate_records_are_retired",
      "_relined"
    ],
    [
      "test_fr021_superseded_candidate_records_are_retired",
      "_superseded_set"
    ],
    [
      "test_fr021_superseded_candidate_records_are_retired",
      "_with_control_removed"
    ],
    [
      "test_fr021_superseded_candidate_records_are_retired",
      "binding"
    ],
    [
      "test_fr021_superseded_candidate_records_are_retired",
      "correlation_records"
    ],
    [
      "test_fr021_superseded_candidate_records_are_retired",
      "issue_for"
    ],
    [
      "test_resolver_rejects_candidate_cycles_retaining_decision_facts",
      "@state:assertRaisesRegex"
    ],
    [
      "test_resolver_rejects_candidate_cycles_retaining_decision_facts",
      "@state:repo"
    ],
    [
      "test_resolver_rejects_candidate_cycles_retaining_decision_facts",
      "@state:subTest"
    ],
    [
      "test_resolver_rejects_candidate_cycles_retaining_decision_facts",
      "_write_commit_decision_cycle_chain"
    ],
    [
      "test_resolver_rejects_recreated_approval_and_skip_facts",
      "@state:assertEqual"
    ],
    [
      "test_resolver_rejects_recreated_approval_and_skip_facts",
      "@state:assertRaisesRegex"
    ],
    [
      "test_resolver_rejects_recreated_approval_and_skip_facts",
      "@state:repo"
    ],
    [
      "test_resolver_rejects_recreated_approval_and_skip_facts",
      "@state:subTest"
    ],
    [
      "test_resolver_rejects_recreated_approval_and_skip_facts",
      "_write_commit_decision_cycle_chain"
    ],
    [
      "test_resolver_rejects_stale_and_result_mismatched_gate_bindings",
      "@state:assertEqual"
    ],
    [
      "test_resolver_rejects_stale_and_result_mismatched_gate_bindings",
      "@state:assertRaisesRegex"
    ],
    [
      "test_resolver_rejects_stale_and_result_mismatched_gate_bindings",
      "@state:repo"
    ],
    [
      "test_resolver_rejects_stale_and_result_mismatched_gate_bindings",
      "@state:subTest"
    ],
    [
      "test_resolver_rejects_stale_and_result_mismatched_gate_bindings",
      "_write_commit_gate_binding_chain"
    ]
  ],
  "clusters": [
    [
      "setUp",
      "_semantic_state",
      "_write_semantic_chain",
      "test_commit_and_merge_replay_reject_invented_self_consistent_transitions",
      "test_commit_and_merge_replay_reject_digest_valid_candidate_rollback"
    ],
    [
      "_write_commit_gate_binding_chain",
      "_write_commit_decision_cycle_chain",
      "test_resolver_rejects_stale_and_result_mismatched_gate_bindings",
      "test_resolver_rejects_recreated_approval_and_skip_facts",
      "test_resolver_rejects_candidate_cycles_retaining_decision_facts"
    ],
    [
      "test_dm001_exact_shape_candidate_and_review_vectors",
      "test_commit_identity_binding_projects_existing_verification_type",
      "test_binding_currentness_rejects_superseded_gate_facts",
      "test_binding_currentness_rejects_superseded_review_tuple"
    ],
    [
      "test_commit_candidate_binding_reconstructs_v2_without_relabeling_history"
    ],
    [
      "test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task"
    ],
    [
      "_relined",
      "_superseded_set",
      "_with_control_removed",
      "test_fr021_superseded_candidate_records_are_retired",
      "test_fr021_precedence_rule_scopes_to_the_landed_candidate",
      "test_fr021_post_landing_result_moves_no_boundary"
    ],
    [
      "test_fr021_four_exact_correlation_issues_and_disabled_control"
    ],
    [
      "binding"
    ],
    [
      "correlation_records"
    ],
    [
      "issue_for"
    ]
  ],
  "hubs": [
    "binding",
    "@state:repo",
    "@state:assertEqual",
    "@state:assertTrue",
    "@state:subTest",
    "correlation_records",
    "issue_for",
    "@state:assertRaisesRegex"
  ],
  "prerequisites": [],
  "census": [],
  "census_complete": false
}
