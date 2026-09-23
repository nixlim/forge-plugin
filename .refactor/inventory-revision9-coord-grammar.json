{
  "name": "Revision9MergeTransitionGrammarTests",
  "bases": [
    "unittest.TestCase"
  ],
  "metaclass": [],
  "decorators": [],
  "statements": [
    "CHAIN_ID = 'c-2026-08-28T120000Z-cafe'",
    "BASE_AT = '2026-08-28T12:00:00Z'",
    "NEXT_AT = '2026-08-28T12:01:00Z'"
  ],
  "slots": false,
  "methods": [
    {
      "name": "setUp",
      "line": 2378,
      "end_line": 2402,
      "decorators": [],
      "reads": [
        "addCleanup",
        "common_dir",
        "git_dir",
        "temporary",
        "worktree_path"
      ],
      "writes": [
        "candidate_head",
        "claim_path",
        "common_dir",
        "git_dir",
        "policy_digest",
        "remote_tip",
        "repository",
        "temporary",
        "worktree_path"
      ],
      "calls": [
        "addCleanup"
      ],
      "globals": [
        "Path",
        "journal",
        "key",
        "tempfile"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_candidate",
      "line": 2404,
      "end_line": 2433,
      "decorators": [],
      "reads": [
        "candidate_head",
        "common_dir",
        "git_dir",
        "policy_digest",
        "remote_tip",
        "worktree_path"
      ],
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
      "name": "_state",
      "line": 2435,
      "end_line": 2513,
      "decorators": [],
      "reads": [
        "BASE_AT",
        "CHAIN_ID",
        "_candidate",
        "claim_path",
        "common_dir",
        "git_dir",
        "policy_digest",
        "repository",
        "worktree_path"
      ],
      "writes": [],
      "calls": [
        "_candidate"
      ],
      "globals": [
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [
        "class-dependent default, annotation, or decorator"
      ],
      "verdict": "unsupported"
    },
    {
      "name": "_deadline",
      "line": 2515,
      "end_line": 2524,
      "decorators": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "globals": [
        "builders",
        "dt"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "_with_current_merge_authority",
      "line": 2526,
      "end_line": 2588,
      "decorators": [],
      "reads": [
        "BASE_AT",
        "CHAIN_ID"
      ],
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
      "name": "_transition",
      "line": 2590,
      "end_line": 2629,
      "decorators": [],
      "reads": [
        "CHAIN_ID",
        "_deadline"
      ],
      "writes": [],
      "calls": [
        "_deadline"
      ],
      "globals": [
        "copy",
        "key"
      ],
      "nested_defs": [],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [
        "class-dependent default, annotation, or decorator"
      ],
      "verdict": "unsupported"
    },
    {
      "name": "_initial",
      "line": 2631,
      "end_line": 2650,
      "decorators": [],
      "reads": [
        "BASE_AT",
        "CHAIN_ID",
        "_state"
      ],
      "writes": [],
      "calls": [
        "_state"
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
      "name": "_push_state",
      "line": 2652,
      "end_line": 2677,
      "decorators": [],
      "reads": [
        "BASE_AT",
        "_state",
        "candidate_head",
        "remote_tip"
      ],
      "writes": [],
      "calls": [
        "_state"
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
      "name": "_push_observed",
      "line": 2679,
      "end_line": 2751,
      "decorators": [],
      "reads": [
        "CHAIN_ID",
        "NEXT_AT",
        "_push_state",
        "_transition",
        "candidate_head",
        "remote_tip"
      ],
      "writes": [],
      "calls": [
        "_push_state",
        "_transition"
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
      "name": "_push_context",
      "line": 2753,
      "end_line": 2770,
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
      "name": "test_scalar_edge_table_is_closed_for_all_28_events",
      "line": 2772,
      "end_line": 2890,
      "decorators": [],
      "reads": [
        "_state",
        "assertEqual",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_state",
        "assertEqual",
        "subTest"
      ],
      "globals": [
        "builders",
        "copy"
      ],
      "nested_defs": [
        "pairs"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_epoch_identity_is_event_bound_and_cannot_clear_before_park",
      "line": 2892,
      "end_line": 3042,
      "decorators": [],
      "reads": [
        "NEXT_AT",
        "_push_state",
        "_state",
        "_transition",
        "_with_current_merge_authority",
        "assertFalse",
        "assertTrue"
      ],
      "writes": [],
      "calls": [
        "_push_state",
        "_state",
        "_transition",
        "_with_current_merge_authority",
        "assertFalse",
        "assertTrue"
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
      "name": "test_inactive_cleanup_replays_only_after_current_pushed_truth",
      "line": 3044,
      "end_line": 3129,
      "decorators": [],
      "reads": [
        "NEXT_AT",
        "_push_observed",
        "_state",
        "_transition",
        "assertFalse",
        "assertTrue",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_push_observed",
        "_state",
        "_transition",
        "assertFalse",
        "assertTrue",
        "subTest"
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
      "name": "test_condition_edge_table_and_forbidden_top_level_fields_are_closed",
      "line": 3131,
      "end_line": 3283,
      "decorators": [],
      "reads": [
        "_state",
        "assertEqual",
        "assertTrue",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_state",
        "assertEqual",
        "assertTrue",
        "subTest"
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
      "name": "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "line": 3285,
      "end_line": 3318,
      "decorators": [],
      "reads": [
        "CHAIN_ID",
        "_candidate",
        "_initial",
        "_state",
        "_transition",
        "assertFalse",
        "assertTrue",
        "common_dir",
        "git_dir",
        "temporary"
      ],
      "writes": [],
      "calls": [
        "_candidate",
        "_initial",
        "_state",
        "_transition",
        "assertFalse",
        "assertTrue"
      ],
      "globals": [
        "Path",
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
      "name": "test_gate_review_and_approval_require_exact_fact_changes",
      "line": 3320,
      "end_line": 3538,
      "decorators": [],
      "reads": [
        "CHAIN_ID",
        "_state",
        "_transition",
        "_with_current_merge_authority",
        "assertFalse",
        "assertTrue",
        "candidate_head"
      ],
      "writes": [],
      "calls": [
        "_state",
        "_transition",
        "_with_current_merge_authority",
        "assertFalse",
        "assertTrue"
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
      "name": "test_complete_tuple_closes_gate_review_and_iteration_bypasses",
      "line": 3540,
      "end_line": 3780,
      "decorators": [],
      "reads": [
        "NEXT_AT",
        "_state",
        "_transition",
        "assertFalse",
        "assertTrue",
        "candidate_head"
      ],
      "writes": [],
      "calls": [
        "_state",
        "_transition",
        "assertFalse",
        "assertTrue"
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
      "name": "test_refresh_retains_iteration_and_eighth_block_closes_loop",
      "line": 3782,
      "end_line": 3977,
      "decorators": [],
      "reads": [
        "NEXT_AT",
        "_state",
        "_transition",
        "assertFalse",
        "assertTrue",
        "candidate_head"
      ],
      "writes": [],
      "calls": [
        "_state",
        "_transition",
        "assertFalse",
        "assertTrue"
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
      "name": "test_disposition_cosign_and_remote_churn_approval_are_exact",
      "line": 3979,
      "end_line": 4095,
      "decorators": [],
      "reads": [
        "CHAIN_ID",
        "NEXT_AT",
        "_state",
        "_transition",
        "_with_current_merge_authority",
        "assertFalse",
        "assertTrue",
        "candidate_head"
      ],
      "writes": [],
      "calls": [
        "_state",
        "_transition",
        "_with_current_merge_authority",
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
      "name": "test_bootstrap_and_push_evidence_cannot_be_fabricated",
      "line": 4097,
      "end_line": 4193,
      "decorators": [],
      "reads": [
        "NEXT_AT",
        "_push_context",
        "_push_state",
        "_state",
        "_transition",
        "assertFalse",
        "candidate_head",
        "remote_tip"
      ],
      "writes": [],
      "calls": [
        "_push_context",
        "_push_state",
        "_state",
        "_transition",
        "assertFalse"
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
      "name": "test_push_observation_phase_and_classification_are_context_bound",
      "line": 4195,
      "end_line": 4371,
      "decorators": [],
      "reads": [
        "BASE_AT",
        "CHAIN_ID",
        "NEXT_AT",
        "_push_context",
        "_push_observed",
        "_push_state",
        "_state",
        "_transition",
        "assertFalse",
        "assertTrue",
        "candidate_head",
        "remote_tip",
        "subTest"
      ],
      "writes": [],
      "calls": [
        "_push_context",
        "_push_observed",
        "_push_state",
        "_state",
        "_transition",
        "assertFalse",
        "assertTrue",
        "subTest"
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
      "name": "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once",
      "line": 4373,
      "end_line": 4535,
      "decorators": [],
      "reads": [
        "BASE_AT",
        "CHAIN_ID",
        "NEXT_AT",
        "_state",
        "_transition",
        "_with_current_merge_authority",
        "assertFalse",
        "assertTrue",
        "candidate_head",
        "remote_tip"
      ],
      "writes": [],
      "calls": [
        "_state",
        "_transition",
        "_with_current_merge_authority",
        "assertFalse",
        "assertTrue"
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
      "name": "test_claim_release_and_terminal_links_are_replay_context_bound",
      "line": 4537,
      "end_line": 4773,
      "decorators": [],
      "reads": [
        "_state",
        "_transition",
        "assertFalse",
        "assertIsInstance",
        "assertTrue",
        "claim_path",
        "common_dir",
        "git_dir",
        "worktree_path"
      ],
      "writes": [],
      "calls": [
        "_state",
        "_transition",
        "assertFalse",
        "assertIsInstance",
        "assertTrue"
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
      "name": "test_slot_lineage_rejects_missing_cycle_fork_and_snapshot_substitution",
      "line": 4775,
      "end_line": 4914,
      "decorators": [],
      "reads": [
        "CHAIN_ID",
        "_state",
        "assertRaises",
        "repository"
      ],
      "writes": [],
      "calls": [
        "_state",
        "assertRaises"
      ],
      "globals": [
        "Path",
        "builders",
        "copy",
        "journal",
        "key",
        "mock"
      ],
      "nested_defs": [
        "summary",
        "exercise",
        "replay",
        "read_events",
        "read_state"
      ],
      "nonlocal_names": [],
      "mangled": [],
      "reasons": [],
      "verdict": "ok"
    },
    {
      "name": "test_condition_cleanup_and_inactive_results_require_exact_evidence",
      "line": 4916,
      "end_line": 4980,
      "decorators": [],
      "reads": [
        "_state",
        "_transition",
        "assertFalse"
      ],
      "writes": [],
      "calls": [
        "_state",
        "_transition",
        "assertFalse"
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
      "name": "test_outbox_is_required_iff_an_ordinary_record_is_derived",
      "line": 4982,
      "end_line": 5091,
      "decorators": [],
      "reads": [
        "CHAIN_ID",
        "_push_context",
        "_push_observed",
        "_push_state",
        "_transition",
        "assertFalse",
        "assertTrue"
      ],
      "writes": [],
      "calls": [
        "_push_context",
        "_push_observed",
        "_push_state",
        "_transition",
        "assertFalse",
        "assertTrue"
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
      "name": "test_fractional_deadline_is_sticky_and_never_rearmed",
      "line": 5093,
      "end_line": 5149,
      "decorators": [],
      "reads": [
        "_state",
        "_transition",
        "assertEqual",
        "assertFalse",
        "assertTrue",
        "candidate_head"
      ],
      "writes": [],
      "calls": [
        "_state",
        "_transition",
        "assertEqual",
        "assertFalse",
        "assertTrue"
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
    }
  ],
  "edges": [
    [
      "_candidate",
      "@state:candidate_head"
    ],
    [
      "_candidate",
      "@state:common_dir"
    ],
    [
      "_candidate",
      "@state:git_dir"
    ],
    [
      "_candidate",
      "@state:policy_digest"
    ],
    [
      "_candidate",
      "@state:remote_tip"
    ],
    [
      "_candidate",
      "@state:worktree_path"
    ],
    [
      "_initial",
      "@state:BASE_AT"
    ],
    [
      "_initial",
      "@state:CHAIN_ID"
    ],
    [
      "_initial",
      "_state"
    ],
    [
      "_push_observed",
      "@state:CHAIN_ID"
    ],
    [
      "_push_observed",
      "@state:NEXT_AT"
    ],
    [
      "_push_observed",
      "@state:candidate_head"
    ],
    [
      "_push_observed",
      "@state:remote_tip"
    ],
    [
      "_push_observed",
      "_push_state"
    ],
    [
      "_push_observed",
      "_transition"
    ],
    [
      "_push_state",
      "@state:BASE_AT"
    ],
    [
      "_push_state",
      "@state:candidate_head"
    ],
    [
      "_push_state",
      "@state:remote_tip"
    ],
    [
      "_push_state",
      "_state"
    ],
    [
      "_state",
      "@state:BASE_AT"
    ],
    [
      "_state",
      "@state:CHAIN_ID"
    ],
    [
      "_state",
      "@state:claim_path"
    ],
    [
      "_state",
      "@state:common_dir"
    ],
    [
      "_state",
      "@state:git_dir"
    ],
    [
      "_state",
      "@state:policy_digest"
    ],
    [
      "_state",
      "@state:repository"
    ],
    [
      "_state",
      "@state:worktree_path"
    ],
    [
      "_state",
      "_candidate"
    ],
    [
      "_transition",
      "@state:CHAIN_ID"
    ],
    [
      "_transition",
      "_deadline"
    ],
    [
      "_with_current_merge_authority",
      "@state:BASE_AT"
    ],
    [
      "_with_current_merge_authority",
      "@state:CHAIN_ID"
    ],
    [
      "setUp",
      "@state:addCleanup"
    ],
    [
      "setUp",
      "@state:candidate_head"
    ],
    [
      "setUp",
      "@state:claim_path"
    ],
    [
      "setUp",
      "@state:common_dir"
    ],
    [
      "setUp",
      "@state:git_dir"
    ],
    [
      "setUp",
      "@state:policy_digest"
    ],
    [
      "setUp",
      "@state:remote_tip"
    ],
    [
      "setUp",
      "@state:repository"
    ],
    [
      "setUp",
      "@state:temporary"
    ],
    [
      "setUp",
      "@state:worktree_path"
    ],
    [
      "test_bootstrap_and_push_evidence_cannot_be_fabricated",
      "@state:NEXT_AT"
    ],
    [
      "test_bootstrap_and_push_evidence_cannot_be_fabricated",
      "@state:assertFalse"
    ],
    [
      "test_bootstrap_and_push_evidence_cannot_be_fabricated",
      "@state:candidate_head"
    ],
    [
      "test_bootstrap_and_push_evidence_cannot_be_fabricated",
      "@state:remote_tip"
    ],
    [
      "test_bootstrap_and_push_evidence_cannot_be_fabricated",
      "_push_context"
    ],
    [
      "test_bootstrap_and_push_evidence_cannot_be_fabricated",
      "_push_state"
    ],
    [
      "test_bootstrap_and_push_evidence_cannot_be_fabricated",
      "_state"
    ],
    [
      "test_bootstrap_and_push_evidence_cannot_be_fabricated",
      "_transition"
    ],
    [
      "test_claim_release_and_terminal_links_are_replay_context_bound",
      "@state:assertFalse"
    ],
    [
      "test_claim_release_and_terminal_links_are_replay_context_bound",
      "@state:assertIsInstance"
    ],
    [
      "test_claim_release_and_terminal_links_are_replay_context_bound",
      "@state:assertTrue"
    ],
    [
      "test_claim_release_and_terminal_links_are_replay_context_bound",
      "@state:claim_path"
    ],
    [
      "test_claim_release_and_terminal_links_are_replay_context_bound",
      "@state:common_dir"
    ],
    [
      "test_claim_release_and_terminal_links_are_replay_context_bound",
      "@state:git_dir"
    ],
    [
      "test_claim_release_and_terminal_links_are_replay_context_bound",
      "@state:worktree_path"
    ],
    [
      "test_claim_release_and_terminal_links_are_replay_context_bound",
      "_state"
    ],
    [
      "test_claim_release_and_terminal_links_are_replay_context_bound",
      "_transition"
    ],
    [
      "test_complete_tuple_closes_gate_review_and_iteration_bypasses",
      "@state:NEXT_AT"
    ],
    [
      "test_complete_tuple_closes_gate_review_and_iteration_bypasses",
      "@state:assertFalse"
    ],
    [
      "test_complete_tuple_closes_gate_review_and_iteration_bypasses",
      "@state:assertTrue"
    ],
    [
      "test_complete_tuple_closes_gate_review_and_iteration_bypasses",
      "@state:candidate_head"
    ],
    [
      "test_complete_tuple_closes_gate_review_and_iteration_bypasses",
      "_state"
    ],
    [
      "test_complete_tuple_closes_gate_review_and_iteration_bypasses",
      "_transition"
    ],
    [
      "test_condition_cleanup_and_inactive_results_require_exact_evidence",
      "@state:assertFalse"
    ],
    [
      "test_condition_cleanup_and_inactive_results_require_exact_evidence",
      "_state"
    ],
    [
      "test_condition_cleanup_and_inactive_results_require_exact_evidence",
      "_transition"
    ],
    [
      "test_condition_edge_table_and_forbidden_top_level_fields_are_closed",
      "@state:assertEqual"
    ],
    [
      "test_condition_edge_table_and_forbidden_top_level_fields_are_closed",
      "@state:assertTrue"
    ],
    [
      "test_condition_edge_table_and_forbidden_top_level_fields_are_closed",
      "@state:subTest"
    ],
    [
      "test_condition_edge_table_and_forbidden_top_level_fields_are_closed",
      "_state"
    ],
    [
      "test_disposition_cosign_and_remote_churn_approval_are_exact",
      "@state:CHAIN_ID"
    ],
    [
      "test_disposition_cosign_and_remote_churn_approval_are_exact",
      "@state:NEXT_AT"
    ],
    [
      "test_disposition_cosign_and_remote_churn_approval_are_exact",
      "@state:assertFalse"
    ],
    [
      "test_disposition_cosign_and_remote_churn_approval_are_exact",
      "@state:assertTrue"
    ],
    [
      "test_disposition_cosign_and_remote_churn_approval_are_exact",
      "@state:candidate_head"
    ],
    [
      "test_disposition_cosign_and_remote_churn_approval_are_exact",
      "_state"
    ],
    [
      "test_disposition_cosign_and_remote_churn_approval_are_exact",
      "_transition"
    ],
    [
      "test_disposition_cosign_and_remote_churn_approval_are_exact",
      "_with_current_merge_authority"
    ],
    [
      "test_epoch_identity_is_event_bound_and_cannot_clear_before_park",
      "@state:NEXT_AT"
    ],
    [
      "test_epoch_identity_is_event_bound_and_cannot_clear_before_park",
      "@state:assertFalse"
    ],
    [
      "test_epoch_identity_is_event_bound_and_cannot_clear_before_park",
      "@state:assertTrue"
    ],
    [
      "test_epoch_identity_is_event_bound_and_cannot_clear_before_park",
      "_push_state"
    ],
    [
      "test_epoch_identity_is_event_bound_and_cannot_clear_before_park",
      "_state"
    ],
    [
      "test_epoch_identity_is_event_bound_and_cannot_clear_before_park",
      "_transition"
    ],
    [
      "test_epoch_identity_is_event_bound_and_cannot_clear_before_park",
      "_with_current_merge_authority"
    ],
    [
      "test_fractional_deadline_is_sticky_and_never_rearmed",
      "@state:assertEqual"
    ],
    [
      "test_fractional_deadline_is_sticky_and_never_rearmed",
      "@state:assertFalse"
    ],
    [
      "test_fractional_deadline_is_sticky_and_never_rearmed",
      "@state:assertTrue"
    ],
    [
      "test_fractional_deadline_is_sticky_and_never_rearmed",
      "@state:candidate_head"
    ],
    [
      "test_fractional_deadline_is_sticky_and_never_rearmed",
      "_state"
    ],
    [
      "test_fractional_deadline_is_sticky_and_never_rearmed",
      "_transition"
    ],
    [
      "test_gate_review_and_approval_require_exact_fact_changes",
      "@state:CHAIN_ID"
    ],
    [
      "test_gate_review_and_approval_require_exact_fact_changes",
      "@state:assertFalse"
    ],
    [
      "test_gate_review_and_approval_require_exact_fact_changes",
      "@state:assertTrue"
    ],
    [
      "test_gate_review_and_approval_require_exact_fact_changes",
      "@state:candidate_head"
    ],
    [
      "test_gate_review_and_approval_require_exact_fact_changes",
      "_state"
    ],
    [
      "test_gate_review_and_approval_require_exact_fact_changes",
      "_transition"
    ],
    [
      "test_gate_review_and_approval_require_exact_fact_changes",
      "_with_current_merge_authority"
    ],
    [
      "test_inactive_cleanup_replays_only_after_current_pushed_truth",
      "@state:NEXT_AT"
    ],
    [
      "test_inactive_cleanup_replays_only_after_current_pushed_truth",
      "@state:assertFalse"
    ],
    [
      "test_inactive_cleanup_replays_only_after_current_pushed_truth",
      "@state:assertTrue"
    ],
    [
      "test_inactive_cleanup_replays_only_after_current_pushed_truth",
      "@state:subTest"
    ],
    [
      "test_inactive_cleanup_replays_only_after_current_pushed_truth",
      "_push_observed"
    ],
    [
      "test_inactive_cleanup_replays_only_after_current_pushed_truth",
      "_state"
    ],
    [
      "test_inactive_cleanup_replays_only_after_current_pushed_truth",
      "_transition"
    ],
    [
      "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "@state:CHAIN_ID"
    ],
    [
      "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "@state:assertFalse"
    ],
    [
      "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "@state:assertTrue"
    ],
    [
      "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "@state:common_dir"
    ],
    [
      "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "@state:git_dir"
    ],
    [
      "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "@state:temporary"
    ],
    [
      "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "_candidate"
    ],
    [
      "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "_initial"
    ],
    [
      "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "_state"
    ],
    [
      "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "_transition"
    ],
    [
      "test_outbox_is_required_iff_an_ordinary_record_is_derived",
      "@state:CHAIN_ID"
    ],
    [
      "test_outbox_is_required_iff_an_ordinary_record_is_derived",
      "@state:assertFalse"
    ],
    [
      "test_outbox_is_required_iff_an_ordinary_record_is_derived",
      "@state:assertTrue"
    ],
    [
      "test_outbox_is_required_iff_an_ordinary_record_is_derived",
      "_push_context"
    ],
    [
      "test_outbox_is_required_iff_an_ordinary_record_is_derived",
      "_push_observed"
    ],
    [
      "test_outbox_is_required_iff_an_ordinary_record_is_derived",
      "_push_state"
    ],
    [
      "test_outbox_is_required_iff_an_ordinary_record_is_derived",
      "_transition"
    ],
    [
      "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once",
      "@state:BASE_AT"
    ],
    [
      "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once",
      "@state:CHAIN_ID"
    ],
    [
      "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once",
      "@state:NEXT_AT"
    ],
    [
      "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once",
      "@state:assertFalse"
    ],
    [
      "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once",
      "@state:assertTrue"
    ],
    [
      "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once",
      "@state:candidate_head"
    ],
    [
      "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once",
      "@state:remote_tip"
    ],
    [
      "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once",
      "_state"
    ],
    [
      "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once",
      "_transition"
    ],
    [
      "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once",
      "_with_current_merge_authority"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "@state:BASE_AT"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "@state:CHAIN_ID"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "@state:NEXT_AT"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "@state:assertFalse"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "@state:assertTrue"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "@state:candidate_head"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "@state:remote_tip"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "@state:subTest"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "_push_context"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "_push_observed"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "_push_state"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "_state"
    ],
    [
      "test_push_observation_phase_and_classification_are_context_bound",
      "_transition"
    ],
    [
      "test_refresh_retains_iteration_and_eighth_block_closes_loop",
      "@state:NEXT_AT"
    ],
    [
      "test_refresh_retains_iteration_and_eighth_block_closes_loop",
      "@state:assertFalse"
    ],
    [
      "test_refresh_retains_iteration_and_eighth_block_closes_loop",
      "@state:assertTrue"
    ],
    [
      "test_refresh_retains_iteration_and_eighth_block_closes_loop",
      "@state:candidate_head"
    ],
    [
      "test_refresh_retains_iteration_and_eighth_block_closes_loop",
      "_state"
    ],
    [
      "test_refresh_retains_iteration_and_eighth_block_closes_loop",
      "_transition"
    ],
    [
      "test_scalar_edge_table_is_closed_for_all_28_events",
      "@state:assertEqual"
    ],
    [
      "test_scalar_edge_table_is_closed_for_all_28_events",
      "@state:subTest"
    ],
    [
      "test_scalar_edge_table_is_closed_for_all_28_events",
      "_state"
    ],
    [
      "test_slot_lineage_rejects_missing_cycle_fork_and_snapshot_substitution",
      "@state:CHAIN_ID"
    ],
    [
      "test_slot_lineage_rejects_missing_cycle_fork_and_snapshot_substitution",
      "@state:assertRaises"
    ],
    [
      "test_slot_lineage_rejects_missing_cycle_fork_and_snapshot_substitution",
      "@state:repository"
    ],
    [
      "test_slot_lineage_rejects_missing_cycle_fork_and_snapshot_substitution",
      "_state"
    ]
  ],
  "clusters": [
    [
      "setUp",
      "_candidate",
      "_initial",
      "test_initial_nested_shapes_and_candidate_coherence_are_enforced",
      "test_claim_release_and_terminal_links_are_replay_context_bound",
      "test_slot_lineage_rejects_missing_cycle_fork_and_snapshot_substitution"
    ],
    [
      "_deadline"
    ],
    [
      "_with_current_merge_authority",
      "test_epoch_identity_is_event_bound_and_cannot_clear_before_park",
      "test_gate_review_and_approval_require_exact_fact_changes",
      "test_disposition_cosign_and_remote_churn_approval_are_exact",
      "test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once"
    ],
    [
      "_push_observed",
      "_push_context",
      "test_scalar_edge_table_is_closed_for_all_28_events",
      "test_inactive_cleanup_replays_only_after_current_pushed_truth",
      "test_condition_edge_table_and_forbidden_top_level_fields_are_closed",
      "test_bootstrap_and_push_evidence_cannot_be_fabricated",
      "test_push_observation_phase_and_classification_are_context_bound",
      "test_outbox_is_required_iff_an_ordinary_record_is_derived",
      "test_fractional_deadline_is_sticky_and_never_rearmed"
    ],
    [
      "test_complete_tuple_closes_gate_review_and_iteration_bypasses"
    ],
    [
      "test_refresh_retains_iteration_and_eighth_block_closes_loop"
    ],
    [
      "test_condition_cleanup_and_inactive_results_require_exact_evidence"
    ],
    [
      "_state"
    ],
    [
      "_transition"
    ],
    [
      "_push_state"
    ]
  ],
  "hubs": [
    "_state",
    "_transition",
    "@state:assertFalse",
    "@state:assertTrue",
    "@state:CHAIN_ID",
    "@state:candidate_head",
    "@state:NEXT_AT",
    "@state:remote_tip",
    "@state:BASE_AT",
    "_push_state",
    "@state:common_dir",
    "@state:git_dir"
  ],
  "prerequisites": [],
  "census": [],
  "census_complete": false
}
