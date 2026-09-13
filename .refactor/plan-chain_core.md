# Split plan: scripts/forge/forge_cli/chain_core.py -> scripts/forge/forge_cli/chain_core/

Revision 2 (after plan-critic REVISE). Inputs: `.refactor/inventory.md/.json` (12 hubs), `inventory-hubs20/40/60` (hub peeling never breaks the dominant component), spec line 117 vocabulary, commit 6502849 (`tests/_cli_loader.patch_chain_core`). Method: a mechanical package conversion first (no code moved), then Wave 0 peels state + hubs into `_state.py`/`_core.py`; the remaining targets are the label-propagation communities, each split along its own hub and each tiny community merged into a neighbour. Symbol-level Tarjan SCC over all 813 edges finds exactly three non-trivial SCCs (activation trio; SCC-2 around `ChainStore`/`register_coordination_seams`; SCC-3 around `MergeChainStore`/`CommonRebaseLock`/`ChainLease`); every member of an SCC is placed in one target, so the target graph is acyclic with NO ignored edges and NO function-local imports and NO body edits. 37 target modules result; the 3-8 target guideline cannot hold for a 20,456-line module whose largest symbols are 1,984 / 1,090 / 819 lines.

Conventions for the extractor: every target is `scripts/forge/forge_cli/chain_core/<target>.py`; the source of every move is `scripts/forge/forge_cli/chain_core/__init__.py` (after the package conversion below), which keeps `__all__` verbatim plus re-exports; intra-package imports are absolute (`from forge_cli.chain_core._core import canonical_bytes`); external imports (`runtime`, `candidate_module`, `fresh_eval_module`, envelope, policy, stdlib) are copied per target as needed; every module keeps `from __future__ import annotations`. Runtime controls stay read by attribute through `forge_cli.runtime`. No function or class body is edited, ever, in this split (the snapshot oracle `snapshot_bodies.py` enforces it).

### Pre-wave step P: package conversion (sequential, one extractor, own commit)
- `git mv scripts/forge/forge_cli/chain_core.py scripts/forge/forge_cli/chain_core/__init__.py`; nothing else changes (a package directory would shadow the module file, so this must land before any wave). The module docstring (lines 1-8) stays verbatim. Run the gate; commit `refactor(chain_core): convert module to package (no code moved)`. From here on `chain_core/__init__.py` is the source module for every wave and shrinks to `__all__` + re-exports by wave 16.

## Delete first (dead code, with evidence)

- Nothing is deleted in this split. `radon` and `vulture` are not installed; the inventory's fan-in analysis finds two symbols with no reference anywhere in the repository outside `chain_core.py` (grep over `tests/`, `scripts/`, `docs/`): `_candidate_binding_for_state_with_candidate_v2` (line 9553, 9 lines) and `_binding_shape_valid_with_candidate_v2` (line 9563, 9 lines). Both are in `__all__` and forwarded by the `scripts/forge/cli.py` shim, so removing them changes the exported attribute set the spec (line 117) says the split must not change. Decision: keep both in `_candidate_v2.py`; file a follow-up bead to remove them with a spec/`__all__` change of their own.
- `__all__` (line 20156, 300 lines) is 'used by nobody' inside the module but is the shim contract; it stays in `__init__.py`.

## Target modules

Code lines are non-blank, non-comment lines of the moved symbols (docstrings included); `scripts/check_file_length.py` will count slightly fewer. OVER BUDGET targets exceed 500 either because they hold one unsplittable symbol or one SCC; extractors do NOT touch `.refactor-baseline.json` (see Risk 4).

### _state.py — Every module-level constant, frozen set, compiled regex, control tuple and the three worktree-lock dicts, plus their sole accessor `_exclusive_descriptor_lock`; imports only `forge_cli.runtime` (for `FENCED_CHILD_DRAIN_CAP_BYTES`).
- symbols (dependency order): SCHEMA, KIND, FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES, STATE_KEYS, EVENT_KEYS, MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS, MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK, INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME, COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS, CHAIN_ID_RE, SHA256_RE, COMMIT_RE, RUN_ID_RE, CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS, _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS, _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY, _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
- owns state: SCHEMA, KIND, FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES, STATE_KEYS, EVENT_KEYS, MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS, MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK, INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME, COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS, CHAIN_ID_RE, SHA256_RE, COMMIT_RE, RUN_ID_RE, CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS, _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS, _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY, _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
- estimated code lines: 477
- imports from package: none (leaf)
- wave: 0
- cycle risks and resolution: none: leaf. `FENCED_CHILD_DRAIN_CAP_BYTES = runtime.OUTPUT_CAP_BYTES + 1` is evaluated at import as today; `_WORKTREE_LOCKS_GUARD = threading.Lock()` is created here exactly once.

### _core.py — Hub utilities shared by every other target: canonical bytes/time helpers, the five `_require_*_control` gates, the `_valid_*` predicates, the common-lock/lease/fence exception and record dataclasses, deadline/probe helpers, `merge_gate_intent_digest`, `_merge_refusal`, `_forge_command` and the storage-path helpers.
- symbols (dependency order): canonical_bytes, _chain_storage_root, _validated_commitment_path, _parsed_run_captured_path, _require_ingest_proof, iso_z, parse_time, _require_merge_store_control, _require_merge_adapter_control, _require_merge_integration_control, _require_common_lock_control, CommonLockBoundaryCrash, PublishedLockRecord, CommonLockInspection, CommonLockUnavailable, CommonLockReleaseFailure, ChainLeaseUnavailable, FencedChildSurvived, _valid_utc_second, _valid_positive_int, _valid_nonnegative_int, _valid_host, _valid_nonce, _valid_nullable_chain, _write_all, _PublicationCleanupFailure, _process_probe, _group_probe, _sleep_with_deadline, _require_deadline_open, FencedProcessResult, merge_gate_intent_digest, _forge_command, MergeRunTaskSnapshot, _merge_refusal, _valid_sorted_unique_strings
- owns state: none
- estimated code lines: 388
- imports from package: _state
- wave: 0
- cycle risks and resolution: none: depends on `_state` only (intra-wave-0 edge `_core -> _state`, hence two sequential steps). `merge_gate_intent_digest` is placed here (not with the fenced runner) because `_merge_recovery_lifecycle` needs it.

### _candidate_v2.py — The seven candidate-v2 binding predicates (`candidate_is_v2`, `_binding_*_with_candidate_v2`, `_commit_transition_valid_with_candidate_v2`, ...).
- symbols (dependency order): candidate_is_v2, _candidate_binding_for_state_with_candidate_v2, _binding_shape_valid_with_candidate_v2, _event_batch_records_with_candidate_v2, _binding_matches_source_fact_with_candidate_v2, _binding_is_current_with_candidate_v2, _commit_transition_valid_with_candidate_v2
- owns state: none
- estimated code lines: 96
- imports from package: none (leaf)
- wave: 1
- cycle risks and resolution: none: leaf. `_commit_transition_valid_with_candidate_v2` is read by `getattr(chain_core, ...)` in scripts/forge/archive-run.py:1656 and must be re-exported although absent from `__all__`.

### _receipt_snapshot.py — Receipt-run snapshot lock/dataclass and `_ChainReceiptSnapshotVerifier` used by merge replay and chain activation.
- symbols (dependency order): _ReceiptRunSnapshot, _chain_receipt_snapshot_lock, _receipt_run_snapshot, _ChainReceiptSnapshotVerifier
- owns state: none
- estimated code lines: 208
- imports from package: none (leaf)
- wave: 1
- cycle risks and resolution: none: leaf. Kept apart from `_activation` so `_merge_replay` can use the verifier while `_activation` uses `_merge_replay`.

### _merge_plan.py — Merge gate-plan facts: plan position, carried gate steps, generation digests, current-authority and plan-transition validation.
- symbols (dependency order): _merge_plan_position_fact, _merge_carried_gate_steps, _merge_gate_step_generation_digests, _merge_current_authority_valid, _merge_remote_only_equality_proof, _merge_carry_payload_valid, _merge_plan_transition_valid
- owns state: none
- estimated code lines: 271
- imports from package: _state
- wave: 1
- cycle risks and resolution: none: depends on `_state` only.

### _bootstrap_observation.py — Bootstrap fetch-observation record and transition validation.
- symbols (dependency order): _bootstrap_fetch_observation_record_valid, _bootstrap_fetch_observation_transition_valid
- owns state: none
- estimated code lines: 169
- imports from package: _core, _state
- wave: 1
- cycle risks and resolution: none: depends on `_core`, `_state`.

### _chain_state.py — Commit-chain state validation: `validate_state`.
- symbols (dependency order): validate_state
- owns state: none
- estimated code lines: 427
- imports from package: _core, _state
- wave: 1
- cycle risks and resolution: none: depends on `_core`, `_state`.

### _fenced_child.py — Fenced child mechanics: blocked-child spawn with ack pipe, waitpid/terminate/stop, bounded output collection.
- symbols (dependency order): _BlockedFenceChild, _pipe_cloexec, _read_child_ack, _waitpid_nohang, _wait_for_child_exit, _spawn_blocked_fence_child, _terminate_fenced_group, _stop_unstarted_child, _collect_fenced_child
- owns state: none
- estimated code lines: 442
- imports from package: _core, _state
- wave: 1
- cycle risks and resolution: none: depends on `_core`, `_state`.

### _ingest_capture.py — Ingest input reading and evidence capture: `_read_ingest_input`, blob/run/record capture, captured-path resolution, step/secret-scan currency, `_prove_ingest_live_chain`.
- symbols (dependency order): _read_ingest_input, _capture_ingest_blob, _capture_run_evidence, _capture_ingest_record_evidence, _ingest_captured_paths, _ingest_step_is_current, _ingest_secret_scan_is_current, _prove_ingest_live_chain
- owns state: none
- estimated code lines: 482
- imports from package: _core, _state
- wave: 1
- cycle risks and resolution: none: depends on `_core`, `_state`.

### _lock_records.py — FR-235 published-record primitives: owner/fence/recovery/lease record validators, owned-record read/create/publish/revalidate/unlink helpers, lock-directory open, `_inspect_common_lock_fd`.
- symbols (dependency order): _validate_owner_record, _validate_fence_record, _validate_recovery_record, _validate_chain_lease_record, _read_owned_record_at, _same_published_record, _open_lock_directory, _opaque_path_evidence_at, _inspect_common_lock_fd, _create_private_record_at, _publish_no_replace_link, _revalidate_record_at, _unlink_revalidated_record_at, _record_at_if_present
- owns state: none
- estimated code lines: 471
- imports from package: _core, _state
- wave: 1
- cycle risks and resolution: `_open_owned_directory` and `RecoveryReservation` are in `_lock_owner` (they reference `ChainStore._owned_directory`, which would put `_commit_chain` under the merge-validation stack).

### _merge_cleanup_intent.py — Merge cleanup intent: expected subject/argv, intent validity, unmatched intent, retry proof, intent transition, git-mutation intent detection, cleanup evidence history/summary and the recovery-intent leaf helpers.
- symbols (dependency order): _recovery_event_intent, _recovery_cleanup_intent, _merge_cleanup_expected_subject, _merge_cleanup_expected_argv, _merge_cleanup_intent_valid, _merge_cleanup_evidence_history, _merge_cleanup_history_summary, _merge_cleanup_unmatched_intent, _merge_cleanup_retry_proof_valid, _merge_cleanup_intent_transition_valid, _merge_history_has_git_mutation_intent
- owns state: none
- estimated code lines: 486
- imports from package: _core, _state
- wave: 1
- cycle risks and resolution: `_recovery_event_intent`/`_recovery_cleanup_intent` (leaves) are placed here so the recovery modules depend on cleanup and not vice-versa. The history pair rides here because `_merge_cleanup_intent_transition_valid` uses `_merge_cleanup_history_summary` while `_merge_cleanup_step_result_valid` uses `_merge_cleanup_intent_valid` (intent -> result -> intent otherwise); so `_merge_cleanup_result` depends on this module, not vice-versa. Depends on `_core`, `_state`.

### _merge_events.py — Merge event reduction (`reduce_merge_event`, outbox, payload delta) and merge-state shape/epoch/gate-plan/Revision-9 compatibility checks.
- symbols (dependency order): _merge_event_outbox, _merge_payload_delta, reduce_merge_event, _merge_gate_plan_valid, _merge_epoch_valid, _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view, _merge_state_shape_valid, _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar
- owns state: none
- estimated code lines: 480
- imports from package: _core, _state
- wave: 1
- cycle risks and resolution: `_merge_ingest_transition_valid` is NOT here (it calls `_merge_transition_valid`); it lives in `_merge_transition`.

### _merge_rebase.py — Merge rebase action/result classification, containment, contained-attempt lookup, inactive post-attempt recovery readiness, remote-observation argv builders, `_parse_registered_worktrees`.
- symbols (dependency order): _parse_registered_worktrees, _merge_rebase_action, _merge_rebase_result_classification, _merge_containment, _merge_old_tip_all_false, _merge_latest_contained_attempt, _merge_inactive_post_attempt_recovery_ready, _remote_observation_heads, _remote_observation_fetch_argv, _remote_containment_argv
- owns state: none
- estimated code lines: 285
- imports from package: _core, _state
- wave: 1
- cycle risks and resolution: none.

### _repository.py — The `Repository` git-context wrapper and `_committed_changelog_output_paths`.
- symbols (dependency order): Repository, _committed_changelog_output_paths
- owns state: none
- estimated code lines: 170
- imports from package: _core, _state
- wave: 1
- cycle risks and resolution: none.

### _merge_cleanup_observation.py — Merge cleanup process observation: output/completion, branch observation, worktree inventory, FETCH_HEAD bytes, `_merge_cleanup_observation_valid`.
- symbols (dependency order): _merge_cleanup_process_output, _merge_cleanup_process_complete, _merge_cleanup_branch_observation, _merge_cleanup_worktree_inventory, _merge_cleanup_fetch_head_bytes, _merge_cleanup_observation_valid
- owns state: none
- estimated code lines: 308
- imports from package: _merge_rebase, _state
- wave: 2
- cycle risks and resolution: depends on `_merge_rebase` (`_parse_registered_worktrees`), `_state`.

### _merge_release.py — Merge release preconditions (`_merge_release_preconditions_valid`, `_merge_attempted_release_preconditions_valid`).
- symbols (dependency order): _merge_attempted_release_preconditions_valid, _merge_release_preconditions_valid
- owns state: none
- estimated code lines: 235
- imports from package: _core, _merge_cleanup_intent, _merge_events, _merge_rebase, _state
- wave: 2
- cycle risks and resolution: `_merge_attempted_release_preconditions_valid` is placed here (calls `reduce_merge_event` and `_merge_containment`). Depends on `_merge_cleanup_intent` (`_merge_cleanup_history_summary`, `_merge_history_has_git_mutation_intent`), `_merge_events`, `_merge_rebase`, `_core`, `_state`.

### _merge_scope_binding.py — Merge scope request/fetch-binding validation, scope environment contract, scope and full-patch argv builders, the scope binding validator.
- symbols (dependency order): _merge_scope_environment_contract, _validate_merge_scope_request, _merge_retained_inflight, _validate_merge_scope_fetch_binding, _merge_scope_binding_names, _merge_full_patch_argv, _merge_scope_argv, _merge_scope_binding_validator
- owns state: none
- estimated code lines: 411
- imports from package: _core, _lock_records, _state
- wave: 2
- cycle risks and resolution: depends on `_lock_records` (`_validate_fence_record`), `_core` (`FencedProcessResult`, `PublishedLockRecord`), `_state`.

### _remote_observation.py — Remote-observation progress validation/transition, containment evidence, replayed-completion detection.
- symbols (dependency order): _remote_containment_evidence_valid, _remote_observation_progress_valid, _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed, _replayed_remote_observation_completed
- owns state: none
- estimated code lines: 359
- imports from package: _core, _merge_rebase, _state
- wave: 2
- cycle risks and resolution: depends on `_merge_rebase` (`_remote_containment_argv`), `_core`, `_state`.

### _merge_candidate_observation.py — Merge candidate-observation step specs/names, binding, record/transition validation and evidence extraction.
- symbols (dependency order): _merge_candidate_observation_step_specs, _merge_candidate_observation_step_names, _merge_candidate_observation_binding, _merge_candidate_observation_record_valid, _merge_candidate_observation_transition_valid, _merge_candidate_observation_evidence, _merge_candidate_observation_evidence_valid
- owns state: none
- estimated code lines: 483
- imports from package: _core, _merge_scope_binding, _state
- wave: 3
- cycle risks and resolution: depends on `_merge_scope_binding` (`_merge_scope_argv`, `_merge_full_patch_argv`), `_core`, `_state`.

### _merge_cleanup_result.py — Merge cleanup process/step result validation, results validity and result transition.
- symbols (dependency order): _merge_cleanup_process_result_valid, _merge_cleanup_step_result_valid, _merge_cleanup_results_valid, _merge_cleanup_result_transition_valid
- owns state: none
- estimated code lines: 171
- imports from package: _core, _merge_cleanup_intent, _merge_cleanup_observation, _state
- wave: 3
- cycle risks and resolution: depends on `_merge_cleanup_observation`, `_core`, `_state`.

### _merge_scope.py — Merge scope proof, scope event binding and scope transition validation.
- symbols (dependency order): _validate_merge_scope_proof, _merge_scope_event_binding_valid, _merge_scope_transition_valid
- owns state: none
- estimated code lines: 239
- imports from package: _core, _merge_scope_binding, _state
- wave: 3
- cycle risks and resolution: depends on `_merge_scope_binding`, `_lock_records`, `_core`, `_state`.

### _merge_epoch.py — Epoch fetch-observation record/passed/intent-digest and epoch ancestry validation.
- symbols (dependency order): _epoch_fetch_observation_record_valid, _epoch_fetch_observation_passed, _epoch_ancestry_record_valid, _epoch_fetch_result_intent_digest
- owns state: none
- estimated code lines: 396
- imports from package: _core, _merge_candidate_observation, _merge_rebase, _state
- wave: 4
- cycle risks and resolution: depends on `_merge_candidate_observation`, `_merge_rebase`, `_core`, `_state`.

### _merge_recovery_lifecycle.py — Merge recovery lifecycle classification (`_classify_merge_recovery_lifecycle`) and its evidence/inflight/cleanup-result helpers.
- symbols (dependency order): _published_recovery_evidence_valid, _recovery_value_carries_inflight, _recovery_cleanup_result_matches, _classify_merge_recovery_lifecycle
- owns state: none
- estimated code lines: 380
- imports from package: _core, _merge_cleanup_intent, _merge_cleanup_result, _merge_epoch, _state
- wave: 5
- cycle risks and resolution: depends on `_merge_epoch`, `_merge_cleanup_intent`, `_merge_cleanup_result`, `_core` (`merge_gate_intent_digest`), `_state`.

### _merge_recovery_proof.py — Merge recovery-proof transition validation, epoch fetch-observation predecessor check, recovered-absent rebase intent digest.
- symbols (dependency order): _merge_recovery_proof_transition_valid, _epoch_fetch_observation_predecessor_valid, _recovered_absent_rebase_intent_digest
- owns state: none
- estimated code lines: 272
- imports from package: _core, _lock_records, _merge_candidate_observation, _merge_rebase, _merge_recovery_lifecycle, _state
- wave: 6
- cycle risks and resolution: depends on `_merge_candidate_observation`, `_merge_rebase`, `_lock_records`, `_core`, `_state`.

### _merge_transition.py — The merge transition validator `_merge_transition_valid` (1,984 lines, one function) and its ingest wrapper `_merge_ingest_transition_valid`.
- symbols (dependency order): _merge_transition_valid, _merge_ingest_transition_valid
- owns state: none
- estimated code lines: 1985  (OVER BUDGET)
- imports from package: _bootstrap_observation, _core, _merge_candidate_observation, _merge_cleanup_intent, _merge_cleanup_result, _merge_epoch, _merge_events, _merge_plan, _merge_rebase, _merge_recovery_proof, _merge_release, _merge_scope, _remote_observation, _state
- wave: 7
- cycle risks and resolution: OVER BUDGET by construction (single function; body untouched). Depends on every `_merge_*` target below it.

### _ingest_merge.py — Merge-chain ingest verifier `_verify_and_build_merge_ingest_records` and its record helpers (ingest binding, gate event fact, current gate facts, record templates, allocation records).
- symbols (dependency order): _merge_ingest_binding, _merge_gate_event_fact, _merge_current_gate_facts, _merge_ingest_record_templates, _ingest_allocation_records, _verify_and_build_merge_ingest_records
- owns state: none
- estimated code lines: 838  (OVER BUDGET)
- imports from package: _core, _ingest_capture, _merge_plan, _merge_transition, _repository, _state
- wave: 8
- cycle risks and resolution: OVER BUDGET (588-line function). Depends on `_merge_transition`, `_merge_plan`, `_ingest_capture`, `_repository`, `_core`, `_state`.

### _merge_replay.py — Merge-chain replay: `validate_merge_state`, `MergeReplayResult`, `_replay_merge_event_bytes`.
- symbols (dependency order): validate_merge_state, MergeReplayResult, _replay_merge_event_bytes
- owns state: none
- estimated code lines: 339
- imports from package: _core, _merge_events, _merge_transition, _receipt_snapshot, _state
- wave: 8
- cycle risks and resolution: depends on `_receipt_snapshot`, `_merge_transition`, `_merge_events`, `_core`, `_state`.

### _activation.py — Chain activation snapshot resolution: `_ChainActivationSnapshot` and the mutually recursive trio `_resolve_chain_activation_snapshot` / `_chain_activation_ownership_summary` / `_validate_chain_activation_lineage` (SCC-1).
- symbols (dependency order): _ChainActivationSnapshot, _resolve_chain_activation_snapshot, _chain_activation_ownership_summary, _validate_chain_activation_lineage
- owns state: none
- estimated code lines: 532  (OVER BUDGET)
- imports from package: _core, _merge_events, _merge_replay, _receipt_snapshot, _state
- wave: 9
- cycle risks and resolution: OVER BUDGET: the trio is one SCC and must stay together; order inside the module is source order (Python resolves the mutual calls at call time). Depends on `_merge_replay`, `_receipt_snapshot`, `_merge_events`, `_core`, `_state`.

### _storage.py — `_ChainStoragePrimitives`, the shared storage base class of both stores (1,090 lines, one class).
- symbols (dependency order): _ChainStoragePrimitives
- owns state: none
- estimated code lines: 1046  (OVER BUDGET)
- imports from package: _chain_state, _core, _merge_replay, _state
- wave: 9
- cycle risks and resolution: OVER BUDGET by construction (single class; body untouched). Depends on `_merge_replay`, `_chain_state`, `_core`, `_state` (`_exclusive_descriptor_lock`).

### _activation_outbox.py — Chain activation projection, pending-activation-outbox scan (`_require_no_pending_chain_activation_outbox`) and the merge activation preamble.
- symbols (dependency order): _resolve_chain_activation_projection, _require_no_pending_chain_activation_outbox, _prepare_merge_activation_preamble
- owns state: none
- estimated code lines: 213
- imports from package: _activation, _receipt_snapshot
- wave: 10
- cycle risks and resolution: depends on `_activation`, `_receipt_snapshot`.

### _chain_batch.py — Chain-batch carrier prevalidation, the Revision-9 chain-batch authorizer, chain-batch target validation, coordination refusal mapping and `_drain_chain_batch_capability`.
- symbols (dependency order): _prevalidate_chain_batch_carrier, _authorize_chain_batch, _coordination_refusal, _validate_chain_batch_target, _drain_chain_batch_capability
- owns state: none
- estimated code lines: 494
- imports from package: _activation, _core
- wave: 10
- cycle risks and resolution: depends on `_activation`, `_core`.

### _commit_chain.py — Commit-chain storage and everything knotted to it in SCC-2: `ChainStore` (+ `_validate_bound_chain_state`), `CommandContext`/`CLIOptions`/`_policy_for_state` and the gate helpers, the commit ingest verifier `_verify_and_build_ingest_records`, and the Revision-9 seam registration (`register_coordination_seams`, `register_activation_reservation_seam`, `_ingest_proof_verifier`, `_chain_batch_lock`) with the seam-marker loop (source lines 9389-9397, leaves the module global `_seam`) placed verbatim after the last of the four marked callables.
- symbols (dependency order): CLIOptions, register_activation_reservation_seam, _validate_bound_chain_state, _user_skip, _gate_one_complete, _latest_current_pass, _gate_satisfied, _verify_and_build_ingest_records, _ingest_proof_verifier, register_coordination_seams, _chain_batch_lock, ChainStore, CommandContext, _policy_for_state, _fresh_reviewer_evals_required, _required_steps
- owns state: none
- estimated code lines: 1784  (OVER BUDGET)
- imports from package: _activation_outbox, _candidate_v2, _chain_batch, _chain_state, _core, _ingest_capture, _ingest_merge, _merge_events, _repository, _state, _storage
- wave: 11
- cycle risks and resolution: OVER BUDGET (1,784 code lines): SCC-2 = {ChainStore, CommandContext, _chain_batch_lock, _fresh_reviewer_evals_required, _ingest_proof_verifier, _policy_for_state, _required_steps, _verify_and_build_ingest_records, register_coordination_seams} is a genuine symbol-level cycle (ChainStore -> register_coordination_seams -> _ingest_proof_verifier -> _verify_and_build_ingest_records -> CommandContext -> ChainStore) and must be co-located; no body is edited. Depends on `_storage`, `_chain_batch`, `_activation_outbox`, `_ingest_merge`, `_ingest_capture`, `_candidate_v2`, `_chain_state`, `_repository`, `_merge_events`, `_core`, `_state`. See Follow-up for the later body-edit split.

### _lock_owner.py — Portable owner and recovery-reservation records: `RecoveryReservation`, `_open_owned_directory`, owner record creation, portable owner publish/release, reservation publish/evidence/clear, `_recovery_record`.
- symbols (dependency order): _open_owned_directory, RecoveryReservation, _new_owner_record, _fence_matches_owner, _release_portable_identity, _publish_portable_owner, _publish_recovery_reservation, _reservation_evidence, _clear_owned_reservation, _recovery_record
- owns state: none
- estimated code lines: 461
- imports from package: _commit_chain, _core, _lock_records, _state
- wave: 12
- cycle risks and resolution: `_open_owned_directory` calls `ChainStore._owned_directory` (staticmethod inherited from `_ChainStoragePrimitives`); keep verbatim and import `ChainStore` from `_commit_chain`. Depends on `_commit_chain`, `_lock_records`, `_core`, `_state`.

### _lock_recovery.py — Stale portable-owner recovery helpers: fence death proof, recovery-proof recorder/persistence, fence read for recovery, common fence presence, `_recover_stale_portable_owner`.
- symbols (dependency order): _fence_death_proof, _require_recovery_proof_recorder, _persist_recovery_proof, _read_fence_for_recovery, _common_fence_path_present, _recover_stale_portable_owner
- owns state: none
- estimated code lines: 167
- imports from package: _core, _lock_owner, _lock_records, _state
- wave: 13
- cycle risks and resolution: `_clear_reserved_fence` and `_recovery_classification_receipt_valid` are NOT here: they belong to SCC-3 and live in `_merge_chain`. Depends on `_lock_owner`, `_lock_records`, `_core`, `_state`.

### _merge_chain.py — Merge-chain storage and everything knotted to it in SCC-3: `MergeChainStore` (+ journal-record builder, `_new_merge_record_is_current`, `_prove_merge_run_task_binding`), the common-lock arbiter handle `CommonRebaseLock`, chain leases (`ChainLease`, lease checks, `_reconcile_merge_projection_for_lease_reclaim`, `acquire_chain_lease`) and the reserved-fence clearing pair `_clear_reserved_fence` / `_recovery_classification_receipt_valid`.
- symbols (dependency order): _build_merge_chain_journal_records, _new_merge_record_is_current, _prove_merge_run_task_binding, _repository_recovery_reservation_present, MergeChainStore, _recovery_classification_receipt_valid, CommonRebaseLock, _clear_reserved_fence, ChainLease, _lease_exclusion_is_current, _lease_reclaim_authority_is_current, _reconcile_merge_projection_for_lease_reclaim, acquire_chain_lease
- owns state: none
- estimated code lines: 1845  (OVER BUDGET)
- imports from package: _activation_outbox, _chain_batch, _commit_chain, _core, _ingest_merge, _lock_owner, _lock_records, _lock_recovery, _merge_events, _merge_replay, _merge_transition, _state, _storage
- wave: 14
- cycle risks and resolution: OVER BUDGET (1,845 code lines): SCC-3 = {ChainLease, CommonRebaseLock, MergeChainStore, _clear_reserved_fence, _lease_exclusion_is_current, _lease_reclaim_authority_is_current, _reconcile_merge_projection_for_lease_reclaim, _recovery_classification_receipt_valid, acquire_chain_lease} is a genuine cycle (CommonRebaseLock -> _clear_reserved_fence -> _recovery_classification_receipt_valid -> MergeChainStore -> acquire_chain_lease -> _reconcile... -> CommonRebaseLock) and must be co-located; no body is edited. `_repository_recovery_reservation_present` rides along (used only by `acquire_chain_lease`). Depends on `_lock_recovery`, `_lock_owner`, `_lock_records`, `_commit_chain`, `_chain_batch`, `_activation_outbox`, `_ingest_merge`, `_merge_replay`, `_merge_transition`, `_merge_events`, `_storage`, `_core`, `_state`. See Follow-up.

### _common_lock.py — Common-lock acquisition and holding: `_acquire_secondary_flock`, `acquire_common_lock` (544 lines), `hold_common_lock`.
- symbols (dependency order): _acquire_secondary_flock, acquire_common_lock, hold_common_lock
- owns state: none
- estimated code lines: 707  (OVER BUDGET)
- imports from package: _core, _lock_owner, _lock_records, _lock_recovery, _merge_chain, _repository, _state
- wave: 15
- cycle risks and resolution: OVER BUDGET (544-line function). Depends on `_merge_chain` (`CommonRebaseLock`, `_clear_reserved_fence`, `_recovery_classification_receipt_valid`), `_lock_recovery`, `_lock_owner`, `_lock_records`, `_repository`, `_core`, `_state`.

### _fenced_process.py — The fenced process runner: `_publish_fence` and `run_fenced_command`.
- symbols (dependency order): _publish_fence, run_fenced_command
- owns state: none
- estimated code lines: 420
- imports from package: _core, _fenced_child, _lock_records, _merge_chain, _state
- wave: 15
- cycle risks and resolution: depends on `_merge_chain` (`CommonRebaseLock`), `_fenced_child`, `_lock_records`, `_core`, `_state`.

### __init__.py — package root: `__all__` verbatim, the original module docstring verbatim, and re-exports; no logic.
- symbols (dependency order): __all__ (plus the re-export lines)
- owns state: none (all module-level state lives in `_state.py`)
- estimated code lines: ~300 (`__all__`) + ~330 re-export lines
- cycle risks and resolution: no submodule may import from `forge_cli.chain_core` (the package root); the extractor's verify step must grep each target for `from forge_cli.chain_core import` / `from forge_cli import chain_core` and fail if found.

### stays in __init__.py (reason)
- `__all__` only (shim contract). Every other one of the 315 symbols is placed above; the module docstring stays verbatim (docs-only content, not a symbol).

## State ownership table

| state | owner module | users |
|---|---|---|
| `STATES` | `_state.py` | `validate_state` |
| `STATE_KEYS` | `_state.py` | `validate_state` |
| `EVENT_KEYS` | `_state.py` | `ChainStore`, `_ChainStoragePrimitives`, `_verify_and_build_ingest_records` |
| `MERGE_STATE_KEYS` | `_state.py` | `_merge_recovery_proof_transition_valid`, `_merge_transition_valid`, `_replay_merge_event_bytes`, `validate_merge_state` |
| `_MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES` | `_state.py` | `_merge_transition_valid` |
| `_MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES` | `_state.py` | `_merge_inactive_post_attempt_recovery_ready` |
| `MERGE_EVENT_KEYS` | `_state.py` | `_ChainStoragePrimitives`, `_replay_merge_event_bytes` |
| `MERGE_EVENT_NAMES` | `_state.py` | `MergeChainStore`, `_replay_merge_event_bytes`, `validate_merge_state` |
| `MERGE_CONSEQUENTIAL_EVENTS` | `_state.py` | `_build_merge_chain_journal_records` |
| `TIER_RANK` | `_state.py` | `_merge_candidate_observation_binding`, `_merge_candidate_observation_record_valid`, `_merge_candidate_observation_step_specs`, `_verify_and_build_ingest_records` |
| `COMMON_LOCK_OWNER_KINDS` | `_state.py` | `_validate_owner_record` |
| `COMMON_LOCK_OPERATIONS` | `_state.py` | `_validate_owner_record` |
| `COMMON_LOCK_FENCE_OPERATIONS` | `_state.py` | `_validate_fence_record`, `run_fenced_command` |
| `COMMON_LOCK_RECOVERY_KINDS` | `_state.py` | `_validate_recovery_record` |
| `_COMMON_LOCK_OWNER_KEYS` | `_state.py` | `_validate_owner_record` |
| `_COMMON_LOCK_FENCE_KEYS` | `_state.py` | `_validate_fence_record` |
| `_COMMON_LOCK_RECOVERY_KEYS` | `_state.py` | `_validate_recovery_record` |
| `_CHAIN_LEASE_KEYS` | `_state.py` | `_validate_chain_lease_record` |
| `_REQUIRED_COMMON_LOCK_CONTROLS` | `_state.py` | `COMMON_LOCK_CONTROLS`, `_require_common_lock_control` |
| `CHAIN_ID_RE` | `_state.py` | `RecoveryReservation`, `_ChainStoragePrimitives`, `_valid_nullable_chain`, `_validate_chain_lease_record`, `_validate_fence_record`, `_validate_merge_scope_fetch_binding`, `_validate_owner_record`, `acquire_chain_lease`, `merge_gate_intent_digest`, `validate_merge_state`, `validate_state` |
| `SHA256_RE` | `_state.py` | `_ChainStoragePrimitives`, `_bootstrap_fetch_observation_record_valid`, `_classify_merge_recovery_lifecycle`, `_epoch_ancestry_record_valid`, `_epoch_fetch_observation_record_valid`, `_epoch_fetch_result_intent_digest`, `_ingest_captured_paths`, `_merge_candidate_observation_binding`, `_merge_candidate_observation_record_valid`, `_merge_carried_gate_steps`, `_merge_cleanup_intent_valid`, `_merge_cleanup_observation_valid`, `_merge_cleanup_process_result_valid`, `_merge_current_authority_valid`, `_merge_epoch_valid`, `_merge_event_outbox`, `_merge_gate_plan_valid`, `_merge_gate_step_generation_digests`, `_merge_inactive_post_attempt_recovery_ready`, `_merge_plan_transition_valid`, `_merge_rebase_action`, `_merge_rebase_result_classification`, `_merge_scope_transition_valid`, `_merge_transition_valid`, `_published_recovery_evidence_valid`, `_recovery_classification_receipt_valid`, `_remote_containment_evidence_valid`, `_remote_observation_progress_valid`, `_replay_merge_event_bytes`, `_validate_fence_record`, `_validate_merge_scope_fetch_binding`, `_validate_merge_scope_proof`, `_validate_recovery_record`, `_verify_and_build_ingest_records`, `_verify_and_build_merge_ingest_records`, `merge_gate_intent_digest`, `run_fenced_command`, `validate_state` |
| `COMMIT_RE` | `_state.py` | `Repository`, `_bootstrap_fetch_observation_record_valid`, `_epoch_fetch_result_intent_digest`, `_merge_bootstrap_classification_pending`, `_merge_candidate_observation_binding`, `_merge_candidate_observation_step_specs`, `_merge_cleanup_branch_observation`, `_merge_cleanup_expected_subject`, `_merge_cleanup_fetch_head_bytes`, `_merge_cleanup_worktree_inventory`, `_merge_latest_contained_attempt`, `_remote_observation_progress_valid`, `_validate_merge_scope_fetch_binding`, `_verify_and_build_ingest_records`, `_verify_and_build_merge_ingest_records`, `validate_state` |
| `RUN_ID_RE` | `_state.py` | `validate_state` |
| `CHAIN_TOMBSTONE_KEYS` | `_state.py` | `_ChainStoragePrimitives` |
| `_REQUIRED_MERGE_STORE_CONTROLS` | `_state.py` | `MERGE_STORE_CONTROLS`, `_require_merge_store_control` |
| `_REQUIRED_MERGE_ADAPTER_CONTROLS` | `_state.py` | `MERGE_ADAPTER_CONTROLS`, `_require_merge_adapter_control` |
| `_REQUIRED_MERGE_INTEGRATION_CONTROLS` | `_state.py` | `MERGE_INTEGRATION_CONTROLS`, `_require_merge_integration_control` |
| `_REQUIRED_INGEST_PROOF_CONTROLS` | `_state.py` | `INGEST_PROOF_CONTROLS`, `_require_ingest_proof`, `_verify_and_build_ingest_records` |
| `_WORKTREE_LOCKS_GUARD` | `_state.py` | `_exclusive_descriptor_lock` |
| `_WORKTREE_LOCKS` | `_state.py` | `_exclusive_descriptor_lock` |
| `_WORKTREE_LOCK_STATE` | `_state.py` | `_exclusive_descriptor_lock` |
| `_MERGE_CLEANUP_FENCE_OPERATIONS` | `_state.py` | `_merge_cleanup_intent_valid` |
| `_MERGE_SCOPE_UNSET` | `_state.py` | `_merge_scope_environment_contract` |
| `_MERGE_SCOPE_OVERLAY` | `_state.py` | `_merge_scope_environment_contract` |
| `__all__` | `__init__.py` | scripts/forge/cli.py `__getattr__` (shim forwarding) |
| `_seam` (loop variable left by the seam-marker loop, lines 9389-9397) | `_commit_chain.py` | nobody; re-exported for attribute parity |

Rules: `_state.py` is moved first (Wave 0 step 1, before any user). `_WORKTREE_LOCKS_GUARD`, `_WORKTREE_LOCKS`, `_WORKTREE_LOCK_STATE` are real mutable process state; their only accessor `_exclusive_descriptor_lock` moves with them so no other module touches the dicts. No `global` statements exist (grep). The 39 non-mutable constants (`SCHEMA`, `KIND`, `ZERO_DIGEST`, `COMMON_LOCK_*_NAME`, `_MERGE_CLEANUP_*_SCHEMA`, `_EPOCH_FETCH_OBSERVATION_SCHEMA`, `_MERGE_CANDIDATE_OBSERVATION_*_SCHEMA`, `_BOOTSTRAP_FETCH_OBSERVATION_SCHEMA`, `_MERGE_REMOTE_ONLY_IDENTITY_FIELDS`, ...) are also owned by `_state.py`; alias assignments (`COMMON_LOCK_CONTROLS = _REQUIRED_COMMON_LOCK_CONTROLS`, `MERGE_*_CONTROLS`, `INGEST_PROOF_CONTROLS`) stay adjacent to their source there.

## Waves

Wave membership = longest dependency path in the target graph over all 813 edges (no ignored edges). Within a wave (except wave 0) symbol sets are disjoint and no edge joins two members (asserted by the generator). A wave starts only after the previous wave is merged. Single-cluster waves may be chained as sequential steps in one worktree, in wave order, to cut merge rounds (marked below). Each extractor: move the listed symbols from `chain_core/__init__.py` (rope `move` or verbatim cut) into the target, add the imports the target needs from earlier-wave modules, add `from ._<target> import <name> as <name>` to `__init__.py` for every moved name, run the gate (including `snapshot_bodies.py`: bodies byte-identical).

### Wave 0 (two sequential steps in one worktree; `_core` imports `_state`)
- step 1, cluster "state": target=_state.py symbols=[SCHEMA, KIND, FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES, STATE_KEYS, EVENT_KEYS, MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS, MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK, INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME, COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS, CHAIN_ID_RE, SHA256_RE, COMMIT_RE, RUN_ID_RE, CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS, _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS, _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY, _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA]
- step 2, cluster "core hubs": target=_core.py symbols=[canonical_bytes, _chain_storage_root, _validated_commitment_path, _parsed_run_captured_path, _require_ingest_proof, iso_z, parse_time, _require_merge_store_control, _require_merge_adapter_control, _require_merge_integration_control, _require_common_lock_control, CommonLockBoundaryCrash, PublishedLockRecord, CommonLockInspection, CommonLockUnavailable, CommonLockReleaseFailure, ChainLeaseUnavailable, FencedChildSurvived, _valid_utc_second, _valid_positive_int, _valid_nonnegative_int, _valid_host, _valid_nonce, _valid_nullable_chain, _write_all, _PublicationCleanupFailure, _process_probe, _group_probe, _sleep_with_deadline, _require_deadline_open, FencedProcessResult, merge_gate_intent_digest, _forge_command, MergeRunTaskSnapshot, _merge_refusal, _valid_sorted_unique_strings]

### Wave 1 (parallel, after wave 0 merged)
- cluster "candidate v2": target=_candidate_v2.py symbols=[candidate_is_v2, _candidate_binding_for_state_with_candidate_v2, _binding_shape_valid_with_candidate_v2, _event_batch_records_with_candidate_v2, _binding_matches_source_fact_with_candidate_v2, _binding_is_current_with_candidate_v2, _commit_transition_valid_with_candidate_v2]
- cluster "receipt snapshot": target=_receipt_snapshot.py symbols=[_ReceiptRunSnapshot, _chain_receipt_snapshot_lock, _receipt_run_snapshot, _ChainReceiptSnapshotVerifier]
- cluster "merge plan": target=_merge_plan.py symbols=[_merge_plan_position_fact, _merge_carried_gate_steps, _merge_gate_step_generation_digests, _merge_current_authority_valid, _merge_remote_only_equality_proof, _merge_carry_payload_valid, _merge_plan_transition_valid]
- cluster "bootstrap observation": target=_bootstrap_observation.py symbols=[_bootstrap_fetch_observation_record_valid, _bootstrap_fetch_observation_transition_valid]
- cluster "chain state": target=_chain_state.py symbols=[validate_state]
- cluster "fenced child": target=_fenced_child.py symbols=[_BlockedFenceChild, _pipe_cloexec, _read_child_ack, _waitpid_nohang, _wait_for_child_exit, _spawn_blocked_fence_child, _terminate_fenced_group, _stop_unstarted_child, _collect_fenced_child]
- cluster "ingest capture": target=_ingest_capture.py symbols=[_read_ingest_input, _capture_ingest_blob, _capture_run_evidence, _capture_ingest_record_evidence, _ingest_captured_paths, _ingest_step_is_current, _ingest_secret_scan_is_current, _prove_ingest_live_chain]
- cluster "lock records": target=_lock_records.py symbols=[_validate_owner_record, _validate_fence_record, _validate_recovery_record, _validate_chain_lease_record, _read_owned_record_at, _same_published_record, _open_lock_directory, _opaque_path_evidence_at, _inspect_common_lock_fd, _create_private_record_at, _publish_no_replace_link, _revalidate_record_at, _unlink_revalidated_record_at, _record_at_if_present]
- cluster "merge cleanup intent": target=_merge_cleanup_intent.py symbols=[_recovery_event_intent, _recovery_cleanup_intent, _merge_cleanup_expected_subject, _merge_cleanup_expected_argv, _merge_cleanup_intent_valid, _merge_cleanup_evidence_history, _merge_cleanup_history_summary, _merge_cleanup_unmatched_intent, _merge_cleanup_retry_proof_valid, _merge_cleanup_intent_transition_valid, _merge_history_has_git_mutation_intent]
- cluster "merge events": target=_merge_events.py symbols=[_merge_event_outbox, _merge_payload_delta, reduce_merge_event, _merge_gate_plan_valid, _merge_epoch_valid, _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view, _merge_state_shape_valid, _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar]
- cluster "merge rebase": target=_merge_rebase.py symbols=[_parse_registered_worktrees, _merge_rebase_action, _merge_rebase_result_classification, _merge_containment, _merge_old_tip_all_false, _merge_latest_contained_attempt, _merge_inactive_post_attempt_recovery_ready, _remote_observation_heads, _remote_observation_fetch_argv, _remote_containment_argv]
- cluster "repository": target=_repository.py symbols=[Repository, _committed_changelog_output_paths]

### Wave 2 (parallel, after wave 1 merged)
- cluster "merge cleanup observation": target=_merge_cleanup_observation.py symbols=[_merge_cleanup_process_output, _merge_cleanup_process_complete, _merge_cleanup_branch_observation, _merge_cleanup_worktree_inventory, _merge_cleanup_fetch_head_bytes, _merge_cleanup_observation_valid]
- cluster "merge release": target=_merge_release.py symbols=[_merge_attempted_release_preconditions_valid, _merge_release_preconditions_valid]
- cluster "merge scope binding": target=_merge_scope_binding.py symbols=[_merge_scope_environment_contract, _validate_merge_scope_request, _merge_retained_inflight, _validate_merge_scope_fetch_binding, _merge_scope_binding_names, _merge_full_patch_argv, _merge_scope_argv, _merge_scope_binding_validator]
- cluster "remote observation": target=_remote_observation.py symbols=[_remote_containment_evidence_valid, _remote_observation_progress_valid, _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed, _replayed_remote_observation_completed]

### Wave 3 (parallel, after wave 2 merged)
- cluster "merge candidate observation": target=_merge_candidate_observation.py symbols=[_merge_candidate_observation_step_specs, _merge_candidate_observation_step_names, _merge_candidate_observation_binding, _merge_candidate_observation_record_valid, _merge_candidate_observation_transition_valid, _merge_candidate_observation_evidence, _merge_candidate_observation_evidence_valid]
- cluster "merge cleanup result": target=_merge_cleanup_result.py symbols=[_merge_cleanup_process_result_valid, _merge_cleanup_step_result_valid, _merge_cleanup_results_valid, _merge_cleanup_result_transition_valid]
- cluster "merge scope": target=_merge_scope.py symbols=[_validate_merge_scope_proof, _merge_scope_event_binding_valid, _merge_scope_transition_valid]

### Wave 4 (single cluster; may be chained with adjacent single-cluster waves in one worktree, after wave 3 merged)
- cluster "merge epoch": target=_merge_epoch.py symbols=[_epoch_fetch_observation_record_valid, _epoch_fetch_observation_passed, _epoch_ancestry_record_valid, _epoch_fetch_result_intent_digest]

### Wave 5 (single cluster; may be chained with adjacent single-cluster waves in one worktree, after wave 4 merged)
- cluster "merge recovery lifecycle": target=_merge_recovery_lifecycle.py symbols=[_published_recovery_evidence_valid, _recovery_value_carries_inflight, _recovery_cleanup_result_matches, _classify_merge_recovery_lifecycle]

### Wave 6 (single cluster; may be chained with adjacent single-cluster waves in one worktree, after wave 5 merged)
- cluster "merge recovery proof": target=_merge_recovery_proof.py symbols=[_merge_recovery_proof_transition_valid, _epoch_fetch_observation_predecessor_valid, _recovered_absent_rebase_intent_digest]

### Wave 7 (single cluster; may be chained with adjacent single-cluster waves in one worktree, after wave 6 merged)
- cluster "merge transition": target=_merge_transition.py symbols=[_merge_transition_valid, _merge_ingest_transition_valid]

### Wave 8 (parallel, after wave 7 merged)
- cluster "ingest merge": target=_ingest_merge.py symbols=[_merge_ingest_binding, _merge_gate_event_fact, _merge_current_gate_facts, _merge_ingest_record_templates, _ingest_allocation_records, _verify_and_build_merge_ingest_records]
- cluster "merge replay": target=_merge_replay.py symbols=[validate_merge_state, MergeReplayResult, _replay_merge_event_bytes]

### Wave 9 (parallel, after wave 8 merged)
- cluster "activation": target=_activation.py symbols=[_ChainActivationSnapshot, _resolve_chain_activation_snapshot, _chain_activation_ownership_summary, _validate_chain_activation_lineage]
- cluster "storage": target=_storage.py symbols=[_ChainStoragePrimitives]

### Wave 10 (parallel, after wave 9 merged)
- cluster "activation outbox": target=_activation_outbox.py symbols=[_resolve_chain_activation_projection, _require_no_pending_chain_activation_outbox, _prepare_merge_activation_preamble]
- cluster "chain batch": target=_chain_batch.py symbols=[_prevalidate_chain_batch_carrier, _authorize_chain_batch, _coordination_refusal, _validate_chain_batch_target, _drain_chain_batch_capability]

### Wave 11 (single cluster; may be chained with adjacent single-cluster waves in one worktree, after wave 10 merged)
- cluster "commit chain": target=_commit_chain.py symbols=[CLIOptions, register_activation_reservation_seam, _validate_bound_chain_state, _user_skip, _gate_one_complete, _latest_current_pass, _gate_satisfied, _verify_and_build_ingest_records, _ingest_proof_verifier, register_coordination_seams, _chain_batch_lock, ChainStore, CommandContext, _policy_for_state, _fresh_reviewer_evals_required, _required_steps]

### Wave 12 (single cluster; may be chained with adjacent single-cluster waves in one worktree, after wave 11 merged)
- cluster "lock owner": target=_lock_owner.py symbols=[_open_owned_directory, RecoveryReservation, _new_owner_record, _fence_matches_owner, _release_portable_identity, _publish_portable_owner, _publish_recovery_reservation, _reservation_evidence, _clear_owned_reservation, _recovery_record]

### Wave 13 (single cluster; may be chained with adjacent single-cluster waves in one worktree, after wave 12 merged)
- cluster "lock recovery": target=_lock_recovery.py symbols=[_fence_death_proof, _require_recovery_proof_recorder, _persist_recovery_proof, _read_fence_for_recovery, _common_fence_path_present, _recover_stale_portable_owner]

### Wave 14 (single cluster; may be chained with adjacent single-cluster waves in one worktree, after wave 13 merged)
- cluster "merge chain": target=_merge_chain.py symbols=[_build_merge_chain_journal_records, _new_merge_record_is_current, _prove_merge_run_task_binding, _repository_recovery_reservation_present, MergeChainStore, _recovery_classification_receipt_valid, CommonRebaseLock, _clear_reserved_fence, ChainLease, _lease_exclusion_is_current, _lease_reclaim_authority_is_current, _reconcile_merge_projection_for_lease_reclaim, acquire_chain_lease]

### Wave 15 (parallel, after wave 14 merged)
- cluster "common lock": target=_common_lock.py symbols=[_acquire_secondary_flock, acquire_common_lock, hold_common_lock]
- cluster "fenced process": target=_fenced_process.py symbols=[_publish_fence, run_fenced_command]

### Wave 16 (sequential, one extractor, orchestrator + operator involvement): finalize
- `chain_core/__init__.py` now holds only the verbatim docstring, imports, re-exports and `__all__`; verify every name under Re-exports resolves (`python -c 'import forge_cli.chain_core as c; ...'`), run the full gate twice.
- Operator-approved spec update (control class `docs/specs/**`, same commit): in `docs/specs/forge-plugin-spec.md` line 117 the sentence fragment "`chain_core.py` (the fenced process runner, the FR-235 common-lock arbiter and chain leases, chain and merge-chain storage, merge state and transition validation, the ingest verifiers, and the Revision-9 seam-marker loop beside `register_coordination_seams`)" becomes false; replace `chain_core.py` with `chain_core/` (a package whose `__init__.py` keeps `__all__` and re-exports every historical attribute, with the listed responsibilities in its submodules). Requires binding review + explicit operator approval; the wave is blocked until both exist.
- Baseline recording (orchestrator, under explicit operator direction, once): add the OVER BUDGET files listed in Risk 4 to `.refactor-baseline.json`. Extractors never edit that file.
- Import-linter: add an intra-package `layers` contract in wave order (top `_fenced_process`/`_common_lock`, bottom `_state`) to `pyproject.toml` (config category, same commit); no `ignore_imports` are needed because there are no function-local imports.

## Re-exports required in __init__.py

`__all__` (298 names; keep the literal verbatim, order unchanged) — every name must be importable as `forge_cli.chain_core.<name>` after the split because `scripts/forge/cli.py` forwards exactly this list through `__getattr__` and `tests/_cli_loader.py` reaches the package by `forge_cli.<name>`:

`CHAIN_ID_RE`, `CHAIN_TOMBSTONE_EVENT`, `CHAIN_TOMBSTONE_KEYS`, `CHAIN_TOMBSTONE_SCHEMA`, `CLIOptions`, `COMMIT_RE`, `COMMON_LOCK_CONTROLS`, `COMMON_LOCK_DIRECTORY_NAME`, `COMMON_LOCK_FENCE_OPERATIONS`, `COMMON_LOCK_FLOCK_NAME`, `COMMON_LOCK_INFLIGHT_NAME`, `COMMON_LOCK_INTENT_NAME`, `COMMON_LOCK_OPERATIONS`, `COMMON_LOCK_OWNER_KINDS`, `COMMON_LOCK_OWNER_NAME`, `COMMON_LOCK_POLL_SECONDS`, `COMMON_LOCK_RECORD_CAP_BYTES`, `COMMON_LOCK_RECOVERY_KINDS`, `COMMON_LOCK_RECOVERY_NAME`, `COMMON_LOCK_TIMEOUT_SECONDS`, `ChainLease`, `ChainLeaseUnavailable`, `ChainStore`, `CommandContext`, `CommonLockBoundaryCrash`, `CommonLockInspection`, `CommonLockReleaseFailure`, `CommonLockUnavailable`, `CommonRebaseLock`, `EVENT_KEYS`, `FENCED_CHILD_ACK_TIMEOUT_SECONDS`, `FENCED_CHILD_DRAIN_CAP_BYTES`, `FENCED_CHILD_DRAIN_SECONDS`, `FENCED_CHILD_REAP_SECONDS`, `FENCED_CHILD_STOP_GRACE_SECONDS`, `FRESH_REVIEWER_EVALS_GATE`, `FRESH_REVIEWER_EVALS_REQUESTED_EVENT`, `FRESH_REVIEWER_EVALS_REQUESTS`, `FencedChildSurvived`, `FencedProcessResult`, `INACTIVE_SECONDS`, `INGEST_PROOF_CONTROLS`, `INGEST_PROOF_ORDER`, `KIND`, `MERGE_ADAPTER_CONTROLS`, `MERGE_CONSEQUENTIAL_EVENTS`, `MERGE_EVENT_KEYS`, `MERGE_EVENT_NAMES`, `MERGE_INTEGRATION_CONTROLS`, `MERGE_SCOPE_BINDING_CAP_BYTES`, `MERGE_STATE_KEYS`, `MERGE_STORE_CONTROLS`, `MergeChainStore`, `MergeReplayResult`, `MergeRunTaskSnapshot`, `PublishedLockRecord`, `RUN_ID_RE`, `RecoveryReservation`, `Repository`, `candidate_is_v2`, `_binding_is_current_with_candidate_v2`, `_binding_matches_source_fact_with_candidate_v2`, `_binding_shape_valid_with_candidate_v2`, `_candidate_binding_for_state_with_candidate_v2`, `_event_batch_records_with_candidate_v2`, `SCHEMA`, `SHA256_RE`, `STATES`, `STATE_KEYS`, `TIER_RANK`, `ZERO_DIGEST`, `_BOOTSTRAP_FETCH_OBSERVATION_SCHEMA`, `_BlockedFenceChild`, `_CHAIN_LEASE_KEYS`, `_COMMON_LOCK_FENCE_KEYS`, `_COMMON_LOCK_OWNER_KEYS`, `_COMMON_LOCK_RECOVERY_KEYS`, `_ChainStoragePrimitives`, `_EPOCH_FETCH_OBSERVATION_SCHEMA`, `_MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA`, `_MERGE_CANDIDATE_OBSERVATION_SCHEMA`, `_MERGE_CLEANUP_CLOSE_SCHEMA`, `_MERGE_CLEANUP_FENCE_OPERATIONS`, `_MERGE_CLEANUP_INTENT_SCHEMA`, `_MERGE_CLEANUP_RECOVERY_SCHEMA`, `_MERGE_CLEANUP_RESULT_SCHEMA`, `_MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES`, `_MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES`, `_MERGE_REMOTE_ONLY_IDENTITY_FIELDS`, `_MERGE_SCOPE_OVERLAY`, `_MERGE_SCOPE_UNSET`, `_PublicationCleanupFailure`, `_REQUIRED_COMMON_LOCK_CONTROLS`, `_REQUIRED_INGEST_PROOF_CONTROLS`, `_REQUIRED_MERGE_ADAPTER_CONTROLS`, `_REQUIRED_MERGE_INTEGRATION_CONTROLS`, `_REQUIRED_MERGE_STORE_CONTROLS`, `_WORKTREE_LOCKS`, `_WORKTREE_LOCKS_GUARD`, `_WORKTREE_LOCK_STATE`, `_acquire_secondary_flock`, `_authorize_chain_batch`, `_bootstrap_fetch_observation_record_valid`, `_bootstrap_fetch_observation_transition_valid`, `_build_merge_chain_journal_records`, `_capture_ingest_blob`, `_capture_ingest_record_evidence`, `_capture_run_evidence`, `_chain_storage_root`, `_classify_merge_recovery_lifecycle`, `_clear_owned_reservation`, `_clear_reserved_fence`, `_collect_fenced_child`, `_committed_changelog_output_paths`, `_common_fence_path_present`, `_coordination_refusal`, `_create_private_record_at`, `_drain_chain_batch_capability`, `_epoch_ancestry_record_valid`, `_epoch_fetch_observation_passed`, `_epoch_fetch_observation_predecessor_valid`, `_epoch_fetch_observation_record_valid`, `_epoch_fetch_result_intent_digest`, `_exclusive_descriptor_lock`, `_fence_death_proof`, `_fence_matches_owner`, `_forge_command`, `_fresh_reviewer_evals_required`, `_gate_one_complete`, `_gate_satisfied`, `_group_probe`, `_ingest_captured_paths`, `_ingest_proof_verifier`, `_ingest_secret_scan_is_current`, `_ingest_step_is_current`, `_inspect_common_lock_fd`, `_latest_current_pass`, `_lease_exclusion_is_current`, `_lease_reclaim_authority_is_current`, `_merge_attempted_release_preconditions_valid`, `_merge_bootstrap_classification_pending`, `_merge_candidate_observation_binding`, `_merge_candidate_observation_evidence`, `_merge_candidate_observation_evidence_valid`, `_merge_candidate_observation_record_valid`, `_merge_candidate_observation_step_names`, `_merge_candidate_observation_step_specs`, `_merge_candidate_observation_transition_valid`, `_merge_carried_gate_steps`, `_merge_carry_payload_valid`, `_merge_cleanup_branch_observation`, `_merge_cleanup_evidence_history`, `_merge_cleanup_expected_argv`, `_merge_cleanup_expected_subject`, `_merge_cleanup_fetch_head_bytes`, `_merge_cleanup_history_summary`, `_merge_cleanup_intent_transition_valid`, `_merge_cleanup_intent_valid`, `_merge_cleanup_observation_valid`, `_merge_cleanup_process_complete`, `_merge_cleanup_process_output`, `_merge_cleanup_process_result_valid`, `_merge_cleanup_result_transition_valid`, `_merge_cleanup_results_valid`, `_merge_cleanup_retry_proof_valid`, `_merge_cleanup_step_result_valid`, `_merge_cleanup_unmatched_intent`, `_merge_cleanup_worktree_inventory`, `_merge_containment`, `_merge_current_authority_valid`, `_merge_current_gate_facts`, `_merge_epoch_valid`, `_merge_event_outbox`, `_merge_full_patch_argv`, `_merge_gate_event_fact`, `_merge_gate_plan_valid`, `_merge_gate_step_generation_digests`, `_merge_history_has_git_mutation_intent`, `_merge_history_uses_additive_grammar`, `_merge_inactive_post_attempt_recovery_ready`, `_merge_ingest_binding`, `_merge_ingest_record_templates`, `_merge_ingest_state_shape_valid`, `_merge_ingest_transition_valid`, `_merge_latest_contained_attempt`, `_merge_old_tip_all_false`, `_merge_payload_delta`, `_merge_plan_position_fact`, `_merge_plan_transition_valid`, `_merge_rebase_action`, `_merge_rebase_result_classification`, `_merge_recovery_proof_transition_valid`, `_merge_refusal`, `_merge_release_preconditions_valid`, `_merge_remote_only_equality_proof`, `_merge_retained_inflight`, `_merge_revision9_compatibility_view`, `_merge_scope_argv`, `_merge_scope_binding_names`, `_merge_scope_binding_validator`, `_merge_scope_environment_contract`, `_merge_scope_event_binding_valid`, `_merge_scope_transition_valid`, `_merge_state_shape_valid`, `_merge_transition_valid`, `_new_merge_record_is_current`, `_new_owner_record`, `_opaque_path_evidence_at`, `_open_lock_directory`, `_open_owned_directory`, `_parse_registered_worktrees`, `_parsed_run_captured_path`, `_persist_recovery_proof`, `_pipe_cloexec`, `_policy_for_state`, `_process_probe`, `_prove_ingest_live_chain`, `_prove_merge_run_task_binding`, `_publish_fence`, `_publish_no_replace_link`, `_publish_portable_owner`, `_publish_recovery_reservation`, `_published_recovery_evidence_valid`, `_read_child_ack`, `_read_fence_for_recovery`, `_read_ingest_input`, `_read_owned_record_at`, `_reconcile_merge_projection_for_lease_reclaim`, `_record_at_if_present`, `_recover_stale_portable_owner`, `_recovered_absent_rebase_intent_digest`, `_recovery_classification_receipt_valid`, `_recovery_cleanup_intent`, `_recovery_cleanup_result_matches`, `_recovery_event_intent`, `_recovery_record`, `_recovery_value_carries_inflight`, `_release_portable_identity`, `_remote_containment_argv`, `_remote_containment_evidence_valid`, `_remote_observation_fetch_argv`, `_remote_observation_heads`, `_remote_observation_progress_matches_observed`, `_remote_observation_progress_transition_valid`, `_remote_observation_progress_valid`, `_replay_merge_event_bytes`, `_replayed_remote_observation_completed`, `_repository_recovery_reservation_present`, `_require_common_lock_control`, `_require_deadline_open`, `_require_ingest_proof`, `_require_merge_adapter_control`, `_require_merge_integration_control`, `_require_merge_store_control`, `_require_recovery_proof_recorder`, `_required_steps`, `_reservation_evidence`, `_revalidate_record_at`, `_same_published_record`, `_sleep_with_deadline`, `_spawn_blocked_fence_child`, `_stop_unstarted_child`, `_terminate_fenced_group`, `_unlink_revalidated_record_at`, `_user_skip`, `_valid_host`, `_valid_nonce`, `_valid_nonnegative_int`, `_valid_nullable_chain`, `_valid_positive_int`, `_valid_sorted_unique_strings`, `_valid_utc_second`, `_validate_bound_chain_state`, `_validate_chain_lease_record`, `_validate_fence_record`, `_validate_merge_scope_fetch_binding`, `_validate_merge_scope_proof`, `_validate_merge_scope_request`, `_validate_owner_record`, `_validate_recovery_record`, `_validated_commitment_path`, `_verify_and_build_ingest_records`, `_verify_and_build_merge_ingest_records`, `_wait_for_child_exit`, `_waitpid_nohang`, `_write_all`, `acquire_chain_lease`, `acquire_common_lock`, `canonical_bytes`, `hold_common_lock`, `iso_z`, `merge_gate_intent_digest`, `parse_time`, `reduce_merge_event`, `register_coordination_seams`, `run_fenced_command`, `validate_merge_state`, `validate_state`

Additionally re-export these 17 module symbols that are NOT in `__all__` but are read by attribute on the package (a module attribute read bypasses `__all__`): `_ReceiptRunSnapshot`, `_chain_receipt_snapshot_lock`, `_receipt_run_snapshot`, `_ChainReceiptSnapshotVerifier`, `_ChainActivationSnapshot`, `_resolve_chain_activation_snapshot`, `_resolve_chain_activation_projection`, `_chain_activation_ownership_summary`, `_validate_chain_activation_lineage`, `_require_no_pending_chain_activation_outbox`, `_prepare_merge_activation_preamble`, `_prevalidate_chain_batch_carrier`, `_ingest_allocation_records`, `register_activation_reservation_seam`, `_validate_chain_batch_target`, `_chain_batch_lock`, `_commit_transition_valid_with_candidate_v2`; plus the loop global `_seam` left by the seam-marker loop (attribute parity with the original module). Evidence: `scripts/forge/forge_cli/engine.py:4537` reads `chain_core._chain_batch_lock`; `scripts/forge/archive-run.py:1656` reads `getattr(chain_core, "_commit_transition_valid_with_candidate_v2", None)` and treats absence as a `structured_chain_mismatch`; `tests/test_revision9_coordination.py` binds `from forge_cli import chain_core as CHAIN_CORE` and reads private names; `tests/_cli_loader.patch_chain_core` patches the package root and every submodule binding the name, so the root must bind all of them. Rule: `__init__.py` re-exports all 315 top-level symbols + `_seam` (`from ._<owner> import <name> as <name>`), `__all__` is not extended.

## Follow-up (separate commit, not this split)

- `_commit_chain.py` (SCC-2, 1,784 code lines) can later be split into `_chain_store.py` / `_command_context.py` / `_ingest_commit.py` / `_seams.py` by ONE body edit: make `_ingest_proof_verifier` (or `register_coordination_seams`) reach `_verify_and_build_ingest_records` through a late-bound seam (e.g. a `forge_cli.runtime` attribute, mirroring `runtime._build_chain_journal_records`) instead of a direct call. That removes the only edge that closes SCC-2 (`register_coordination_seams -> _ingest_proof_verifier -> _verify_and_build_ingest_records -> CommandContext/ChainStore -> register_coordination_seams`). It is a behaviour-neutral but body-changing edit and needs its own tests and review.
- `_merge_chain.py` (SCC-3, 1,845 code lines) can later be split into `_common_lock.py` (`CommonRebaseLock`) / `_chain_lease.py` / `_merge_store.py` by ONE body edit in each of `_recovery_classification_receipt_valid` and `_reconcile_merge_projection_for_lease_reclaim`: take the merge store (or a store factory) as a parameter instead of constructing `MergeChainStore(...)` inline, with the two callers (`_clear_reserved_fence`, `acquire_chain_lease`) passing it. That removes both edges into `MergeChainStore` from the lock/lease side.
- `_activation.py` trio is mutually recursive by design; no split proposed.
- Remove `_candidate_binding_for_state_with_candidate_v2` and `_binding_shape_valid_with_candidate_v2` from `__all__` and the package (dead in-repo), with the corresponding spec note.

## Risks the reviewer must check

1. **Patch targets (resolved at the test layer, no per-wave retargeting).** 43 names are patched on the chain-core module at 208 sites (`patch.object(CORE|CHAIN_CORE|CLI.chain_core, "<name>", ...)`, many multi-line). Commit 6502849 on this branch added `patch_chain_core(name, ...)` to `tests/_cli_loader.py` — it patches `forge_cli.chain_core` (the package root) and every `forge_cli.chain_core.*` submodule that binds the name with the same object — and rewrote all 208 sites to it (209 call sites today). Therefore no wave needs a test retarget, and the split is indifferent to which file a control lands in. Reviewer: (a) grep for any new `patch.object(<chain_core alias>, ` outside the helper after each wave and fail it; (b) confirm the helper is a restoring context manager so a patched submodule global is restored after the test; (c) the `forge_cli.runtime` attribute seam is untouched. All other `chain_core.<name>` occurrences in engine/app/archive-run are attribute reads satisfied by re-exports.
2. **No function-local imports and no body edits.** The three cycles that would have required function-local imports are dissolved by co-locating each SCC (`_activation`, `_commit_chain`, `_merge_chain`). Reviewer: run `snapshot_bodies.py` before/after every wave (bodies byte-identical), and confirm no target contains an `import` statement inside a `def`/`class` that the original module did not already have at that place.
3. **Import-time side effects, exactly once.** The only module-level statements that are not defs/assignments are (a) the Revision-9 seam-marker loop at lines 9389-9397 (`for _seam in (reduce_merge_event, _authorize_chain_batch, _ingest_proof_verifier, _require_no_pending_chain_activation_outbox): setattr(_seam, "_forge_cli_revision9_seam", True)`), which moves verbatim into `_commit_chain.py` after the last of the four callables is bound (all four are importable there: `reduce_merge_event` from `_merge_events`, `_authorize_chain_batch` from `_chain_batch`, `_require_no_pending_chain_activation_outbox` from `_activation_outbox`, `_ingest_proof_verifier` local) and leaves the module global `_seam`; (b) `_WORKTREE_LOCKS_GUARD = threading.Lock()` and the compiled regexes -> `_state.py`; (c) `FENCED_CHILD_DRAIN_CAP_BYTES = runtime.OUTPUT_CAP_BYTES + 1` -> `_state.py`. `register_coordination_seams()` is NOT called at import time today (verified) and must not be after. Nothing in `chain_core` binds onto `forge_cli.runtime` at import (`runtime._build_chain_journal_records` is bound by `engine.py`; read here only inside bodies at lines 9242 and 12314). Reviewer: `python -c 'import forge_cli.chain_core as c; assert c.reduce_merge_event._forge_cli_revision9_seam and c._ingest_proof_verifier._forge_cli_revision9_seam'` passes; `tests/test_revision9_coordination.py` passes unchanged.
4. **File-size budget / baseline (orchestrator-only, finalize wave).** Expected OVER BUDGET new files (estimated code lines): `chain_core/_merge_transition.py` (1985), `chain_core/_merge_chain.py` (1845), `chain_core/_commit_chain.py` (1784), `chain_core/_storage.py` (1046), `chain_core/_ingest_merge.py` (838), `chain_core/_common_lock.py` (707), `chain_core/_activation.py` (532). Extractors must NOT edit `.refactor-baseline.json`; the orchestrator records these paths once, in the finalize wave, under explicit operator direction, and the reviewer confirms no body was edited to fit. The `scripts/forge/forge_cli/chain_core/**` ruff per-file-ignores entry is already committed (pyproject.toml line 65).
5. **`__all__` and attribute compatibility.** After the finalize wave, `set(n for n in dir(forge_cli.chain_core) if not n.startswith('__'))` must be a superset of the 315 original top-level names plus `_seam` (the loop global). `scripts/forge/cli.py` lines 74-89 need no change. Spec line 117 says the split changes no verb, diagnostic, reason code, `--help` byte or corpus: run the FR-223 corpora and `tests.test_repo_conformance`.
6. **Control-class changes bundled in the finalize wave:** the `docs/specs/forge-plugin-spec.md` line 117 sentence (Wave 16) and the `pyproject.toml` import-linter contract. Both require the binding review; the spec edit requires explicit operator approval bound to the reviewed candidate. No other wave touches a control-class path except `tests/**` re-export checks.
7. **`_open_owned_directory` references `ChainStore._owned_directory`** (a `@staticmethod` defined on `_ChainStoragePrimitives` at line 10742). Kept verbatim, which places `_lock_owner`, `_lock_recovery`, `_merge_chain`, `_common_lock`, `_fenced_process` above `_commit_chain`. Optional one-token follow-up (`_ChainStoragePrimitives._owned_directory`) is NOT part of this split.
8. **Dataclass fields with cross-module annotations** (`CommandContext.repo: Repository`, `.store: ChainStore`; `_reconcile_merge_projection_for_lease_reclaim(exclusion: CommonRebaseLock | RecoveryReservation, repair_with: ChainLease | None)`): resolved by normal imports or same-module placement; `from __future__ import annotations` must be preserved in every target.
9. **Package conversion ordering.** Step P must be its own commit before Wave 0; if a wave is started from the module file instead of `chain_core/__init__.py` the package directory shadows it and every import silently resolves to the wrong file. Reviewer: `git ls-files scripts/forge/forge_cli/chain_core.py` is empty from step P on.
10. **Wave count.** 16 waves are dependency-forced; single-cluster waves may be chained in one worktree in order. Do not merge multi-cluster waves: a target in wave N imports only wave <N modules, which is what keeps every extractor's diff free of judgment calls.
