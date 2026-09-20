# Class inventory: Engine (scripts/forge/forge_cli/engine/_engine.py)

Measured on branch refactor/split-engine-class at 5480091 (tree identical to main 7e40590).
Quality config: .refactor-quality.json (module_target 500, module_ceiling 1000, function_target 150, class_target 30, max_parameters 6, plain_decorators [_serialize_worktree_command]).

## Methods (41; verdicts: ok=20, wrap=21, other=0)

| method | lines | span | verdict | decorators | calls | reads self.* | globals |
|---|---|---|---|---|---|---|---|
| __init__ | 2 | 34-35 | ok |  |  |  |  |
| _require_tombstone_control | 8 | 38-45 | wrap | staticmethod |  |  | FrozenError, REVISION9_OUTPUT_SCHEMA, chain_core, runtime |
| _tombstone_outcome | 16 | 47-62 | ok |  |  |  | Outcome, REVISION9_OUTPUT_SCHEMA, V2ReasonCode |
| operator_tombstone | 48 | 65-112 | wrap | _serialize_worktree_command | _require_tombstone_control, _tombstone_outcome | _require_tombstone_control, _tombstone_outcome, ctx | FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode |
| journal_batch_recover | 23 | 114-136 | ok |  |  | ctx | Outcome, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode, chain_core, runtime |
| journal_ingest_chain | 116 | 138-253 | ok |  |  | ctx | Outcome, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode, _install_ingest_sources, _read_ingest_sources, chain_core, runtime |
| _chains_for_worktree | 17 | 255-271 | ok |  |  | ctx | FrozenError, sys |
| select | 44 | 273-316 | ok |  | _chains_for_worktree | _chains_for_worktree, ctx | FrozenError, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal, TERMINAL_STATES |
| _live_chain | 5 | 318-322 | ok |  | _chains_for_worktree | _chains_for_worktree | TERMINAL_STATES |
| _record_head_moved | 20 | 324-343 | ok |  |  | ctx | chain_core |
| _preflight | 112 | 345-456 | ok |  | _record_head_moved | _record_head_moved, ctx | ReasonCode, Refusal, TERMINAL_STATES, TERMINAL_TOUCH_VERBS, _adopt_out_of_band_candidate, _archive_metadata, _archive_recheck, _run_halt, candidate_module, chain_core, runtime |
| status | 123 | 459-581 | wrap | _serialize_worktree_command | _record_head_moved, _recover_committing, _release_lock, _require_tombstone_control, _tombstone_outcome, next_step, select | _record_head_moved, _recover_committing, _release_lock, _require_tombstone_control, _tombstone_outcome, ctx, next_step, select | FINALIZE_CHECKS, FinalizeContext, FrozenError, ReasonCode, Refusal, TERMINAL_STATES, _adopt_out_of_band_candidate, _run_halt, _success, chain_core, runtime |
| next_step | 33 | 583-615 | ok |  |  |  | TERMINAL_STATES, chain_core |
| start | 134 | 618-751 | wrap | _serialize_worktree_command | _live_chain, _preflight, next_step | _live_chain, _preflight, ctx, next_step | FrozenError, PolicyError, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal, _archive_contamination_refusal, _archive_recheck, _new_state, _prepare_archive_candidate, _prove_run_task_binding, _run_classification, _run_halt, _stage_paths, _success, chain_core, chain_id_now, parse_policy |
| classify | 32 | 754-785 | wrap | _serialize_worktree_command | _preflight, _wrong_state, next_step, select | _preflight, _wrong_state, ctx, next_step, select | ReasonCode, Refusal, _run_classification, _success, chain_core |
| restage | 88 | 788-875 | wrap | _serialize_worktree_command | _preflight, _wrong_state, next_step, select | _preflight, _wrong_state, ctx, next_step, select | ReasonCode, Refusal, V2ReasonCode, _archive_metadata, _invalidate_candidate_evidence, _run_classification, _stage_paths, _success, _transition_state, chain_core, sha256_bytes |
| abort | 95 | 878-972 | wrap | _serialize_worktree_command | _preflight, _require_tombstone_control, _tombstone_outcome, _wrong_state, select | _preflight, _require_tombstone_control, _tombstone_outcome, _wrong_state, ctx, select | FrozenError, Mapping, REVISION9_OUTPUT_SCHEMA, Refusal, TERMINAL_STATES, V2ReasonCode, _run_halt, _success, _transition_state, chain_core |
| abort_disposition | 68 | 975-1042 | wrap | _serialize_worktree_command | _preflight, _tombstone_abort_disposition, _wrong_state, select | _preflight, _tombstone_abort_disposition, _wrong_state, ctx, select | Mapping, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode, _success, abort_disposition_refusal, runtime |
| _tombstone_abort_disposition | 115 | 1044-1158 | ok |  |  | ctx | Mapping, Outcome, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode, chain_core, copy, runtime |
| _wrong_state | 14 | 1160-1173 | ok |  | next_step | next_step | ReasonCode, Refusal |
| rebase | 147 | 1176-1322 | wrap | _serialize_worktree_command | _preflight, _wrong_state, next_step, select | _preflight, _wrong_state, ctx, next_step, select | PolicyError, ReasonCode, Refusal, TERMINAL_STATES, V2ReasonCode, _archive_metadata, _authorization_problem, _invalidate_candidate_evidence, _run_classification, _stage_paths, _success, _transition_state, chain_core, copy, parse_policy, sha256_bytes |
| _pending_mutating_gate | 5 | 1324-1328 | ok |  |  | ctx | chain_core |
| _resolve_gate | 72 | 1330-1401 | ok |  |  | ctx | ReasonCode, Refusal, _current_test_paths, chain_core, sys |
| _run_fresh_reviewer_evals | 362 | 1403-1764 | ok |  |  | ctx | FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, FrozenError, Mapping, ReasonCode, Refusal, _FreshEvalArtifactIO, _FreshEvalControlAbort, _fresh_eval_evaluation, _fresh_eval_invalid_refusal, _next_incomplete, _record_fresh_eval_terminal, _success, _validated_fresh_reviewer_manifest, candidate_module, chain_core, copy, fresh_eval_module, re, secrets, sha256_bytes, time |
| gate_run | 279 | 1767-2045 | wrap | _serialize_worktree_command | _emit_decision, _pending_mutating_gate, _preflight, _resolve_gate, _run_fresh_reviewer_evals, _wrong_state, scan_secrets, select | _emit_decision, _pending_mutating_gate, _preflight, _resolve_gate, _run_fresh_reviewer_evals, _wrong_state, ctx, scan_secrets, select | ReasonCode, Refusal, V2ReasonCode, _adopt_out_of_band_candidate, _archive_metadata, _candidate_snapshot, _current_test_paths, _install_candidate_snapshot, _invalidate_candidate_evidence, _record_process_step, _run_classification, _success, _transition_state, _void_mismatched_gate_one_pair, candidate_module, chain_core, fresh_eval_module, hashlib, os, runtime, secrets, sys |
| scan_secrets | 80 | 2048-2127 | wrap | _serialize_worktree_command | _preflight, _wrong_state, select | _preflight, _wrong_state, ctx, select | FrozenError, ReasonCode, Refusal, _adopt_out_of_band_candidate, _candidate_review_diff, _evidence_record, _success, chain_core, scan_added_secrets, sha256_bytes, time |
| verify | 110 | 2130-2239 | wrap | _serialize_worktree_command | _preflight, _wrong_state, gate_run, next_step, select | _preflight, _wrong_state, ctx, gate_run, next_step, select | ReasonCode, Refusal, _classification_argv, _classification_environment, _issue_authorization, _mechanical_complete, _next_incomplete, _record_process_step, _success, _transition_state, chain_core, runtime |
| _profiles_for_path | 33 | 2242-2274 | wrap | staticmethod |  |  | Path, re |
| _review_package | 118 | 2276-2393 | ok |  | _profiles_for_path | _profiles_for_path, ctx | Path, REVIEW_INSTRUCTION, ReasonCode, Refusal, _candidate_review_diff, _fresh_eval_invalid_refusal, _fresh_reviewer_evidence_package, chain_core, fresh_eval_module, sha256_bytes |
| review_request | 277 | 2396-2672 | wrap | _serialize_worktree_command | _preflight, _review_package, _wrong_state, next_step, select | _preflight, _review_package, _wrong_state, ctx, next_step, select | CODEX_EXECUTABLE, Path, REVIEW_LAUNCHER_CODE, REVIEW_MASTER_WINDOW_BYTES, ReasonCode, Refusal, _mechanical_complete, _pid_is_running, _review_master_pointer_prompt, _review_master_transport, _review_master_window_count, _review_package_is_oversized, _success, _write_artifact, chain_core, os, secrets, sha256_bytes, stat, subprocess, sys |
| _parse_verdict | 35 | 2675-2709 | wrap | staticmethod |  |  | re |
| _apply_verdict | 81 | 2711-2791 | ok |  | _emit_decision, next_step | _emit_decision, ctx, next_step | ReasonCode, Refusal, _issue_authorization, _success, _transition_state, chain_core |
| review_collect | 177 | 2794-2970 | wrap | _serialize_worktree_command | _apply_verdict, _parse_verdict, _preflight, _wrong_state, select | _apply_verdict, _parse_verdict, _preflight, _wrong_state, ctx, select | ReasonCode, Refusal, _pid_is_running, _read_bound_artifact, chain_core, json, runtime, sha256_bytes |
| review_attach | 89 | 2973-3061 | wrap | _serialize_worktree_command | _apply_verdict, _parse_verdict, _preflight, _wrong_state, select | _apply_verdict, _parse_verdict, _preflight, _wrong_state, ctx, select | Path, ReasonCode, Refusal, _read_bound_artifact, _write_artifact, chain_core, os, runtime, stat |
| review_disposition | 66 | 3064-3129 | wrap | _serialize_worktree_command | _preflight, _wrong_state, next_step, select | _preflight, _wrong_state, ctx, next_step, select | ReasonCode, Refusal, _success, chain_core |
| approve | 48 | 3132-3179 | wrap | _serialize_worktree_command | _preflight, _wrong_state, next_step, select | _preflight, _wrong_state, ctx, next_step, select | ReasonCode, Refusal, _issue_authorization, _success, _verify_operator_harness, chain_core |
| skip | 97 | 3182-3278 | wrap | _serialize_worktree_command | _emit_decision, _preflight, _wrong_state, next_step, select | _emit_decision, _preflight, _wrong_state, ctx, next_step, select | FrozenError, ReasonCode, Refusal, _fresh_reviewer_block_claimed, _issue_authorization, _success, _transition_state, chain_core |
| _emit_decision | 33 | 3280-3312 | ok |  |  | ctx | runtime, sys |
| finalize | 240 | 3315-3554 | wrap | _serialize_worktree_command | _emit_decision, _record_head_moved, _recover_committing, _release_lock, _wrong_state, select | _emit_decision, _record_head_moved, _recover_committing, _release_lock, _wrong_state, ctx, select | FINALIZE_CHECKS, FinalizeContext, FrozenError, ReasonCode, Refusal, _archive_recheck, _classification_argv, _classification_environment, _produced_mismatch_outcome, _record_process_step, _record_produced_identity, _success, _transition_state, chain_core, commit_message_bytes, os, re, runtime, sha256_bytes |
| _release_lock | 16 | 3556-3571 | ok |  |  | ctx | os, runtime |
| _recover_committing | 138 | 3573-3710 | ok |  | _emit_decision, _release_lock, next_step | _emit_decision, _release_lock, ctx, next_step | FINALIZE_CHECKS, FinalizeContext, FrozenError, PRODUCED_COMMIT_CHECKS, _authorization_problem, _produced_mismatch_outcome, _record_produced_identity, _success, _transition_state, chain_core, os |

## Hubs (peeled before clustering)

- @state:ctx
- select
- _preflight
- _wrong_state
- next_step
- _emit_decision

## Clusters after hub peeling

1. (2 lines) __init__
2. (704 lines) _require_tombstone_control, _tombstone_outcome, operator_tombstone, _record_head_moved, status, abort, finalize, _release_lock, _recover_committing
3. (23 lines) journal_batch_recover
4. (116 lines) journal_ingest_chain
5. (156 lines) _chains_for_worktree, _live_chain, start
6. (32 lines) classify
7. (88 lines) restage
8. (183 lines) abort_disposition, _tombstone_abort_disposition
9. (147 lines) rebase
10. (908 lines) _pending_mutating_gate, _resolve_gate, _run_fresh_reviewer_evals, gate_run, scan_secrets, verify
11. (428 lines) _profiles_for_path, _review_package, review_request
12. (382 lines) _parse_verdict, _apply_verdict, review_collect, review_attach
13. (66 lines) review_disposition
14. (48 lines) approve
15. (97 lines) skip
16. (44 lines) select
17. (112 lines) _preflight
18. (14 lines) _wrong_state
19. (33 lines) next_step
20. (33 lines) _emit_decision

## Prerequisites

none

## Census (complete: False)

| path | line | kind | text |
|---|---|---|---|
| .codex-orchestrator/runs/run-20260910-release-0611/evidence/task-06/review-final-iter5-harness/head-guard/scripts/forge/forge_cli/app.py | 4666 | unbound-call | `engine.Engine._profiles_for_path(path)` |
| .codex-orchestrator/runs/run-20260910-release-0611/evidence/task-06/review-final-iter5-harness/head-guard/scripts/forge/forge_cli/app.py | 4969 | unbound-call | `engine.Engine._parse_verdict(data, str(state['candidate']['candidate_head']), str(request['package_digest']))` |
| scripts/forge/forge_cli/app/_merge_engine.py | 3749 | unbound-call | `engine.Engine._profiles_for_path(path)` |
| scripts/forge/forge_cli/app/_merge_engine.py | 4052 | unbound-call | `engine.Engine._parse_verdict(data, str(state['candidate']['candidate_head']), str(request['package_digest']))` |
| tests/test_cli_chain.py | 2736 | unbound-call | `module.Engine._profiles_for_path('scripts/inspector.py')` |
| tests/test_cli_chain_finalize.py | 251 | patch-or-reflection | `mock.patch.object(CLI.Engine, '_emit_decision', autospec=True)` |
| tests/test_cli_chain_finalize.py | 1267 | patch-or-reflection | `mock.patch.object(CLI.Engine, '_emit_decision', autospec=True)` |
| tests/test_cli_chain_finalize.py | 1341 | patch-or-reflection | `mock.patch.object(CLI.Engine, '_emit_decision', autospec=True)` |
| tests/test_cli_chain_finalize.py | 1667 | patch-or-reflection | `mock.patch.object(CLI.Engine, 'finalize', side_effect=refusal)` |
| tests/test_revision9_cli_surfaces.py | 5794 | patch-or-reflection | `inspect.getsource(CLI.Engine.gate_run)` |

## Edges

- __init__ -> @state:ctx
- _apply_verdict -> @state:ctx
- _apply_verdict -> _emit_decision
- _apply_verdict -> next_step
- _chains_for_worktree -> @state:ctx
- _emit_decision -> @state:ctx
- _live_chain -> _chains_for_worktree
- _pending_mutating_gate -> @state:ctx
- _preflight -> @state:ctx
- _preflight -> _record_head_moved
- _record_head_moved -> @state:ctx
- _recover_committing -> @state:ctx
- _recover_committing -> _emit_decision
- _recover_committing -> _release_lock
- _recover_committing -> next_step
- _release_lock -> @state:ctx
- _resolve_gate -> @state:ctx
- _review_package -> @state:ctx
- _review_package -> _profiles_for_path
- _run_fresh_reviewer_evals -> @state:ctx
- _tombstone_abort_disposition -> @state:ctx
- _wrong_state -> next_step
- abort -> @state:ctx
- abort -> _preflight
- abort -> _require_tombstone_control
- abort -> _tombstone_outcome
- abort -> _wrong_state
- abort -> select
- abort_disposition -> @state:ctx
- abort_disposition -> _preflight
- abort_disposition -> _tombstone_abort_disposition
- abort_disposition -> _wrong_state
- abort_disposition -> select
- approve -> @state:ctx
- approve -> _preflight
- approve -> _wrong_state
- approve -> next_step
- approve -> select
- classify -> @state:ctx
- classify -> _preflight
- classify -> _wrong_state
- classify -> next_step
- classify -> select
- finalize -> @state:ctx
- finalize -> _emit_decision
- finalize -> _record_head_moved
- finalize -> _recover_committing
- finalize -> _release_lock
- finalize -> _wrong_state
- finalize -> select
- gate_run -> @state:ctx
- gate_run -> _emit_decision
- gate_run -> _pending_mutating_gate
- gate_run -> _preflight
- gate_run -> _resolve_gate
- gate_run -> _run_fresh_reviewer_evals
- gate_run -> _wrong_state
- gate_run -> scan_secrets
- gate_run -> select
- journal_batch_recover -> @state:ctx
- journal_ingest_chain -> @state:ctx
- operator_tombstone -> @state:ctx
- operator_tombstone -> _require_tombstone_control
- operator_tombstone -> _tombstone_outcome
- rebase -> @state:ctx
- rebase -> _preflight
- rebase -> _wrong_state
- rebase -> next_step
- rebase -> select
- restage -> @state:ctx
- restage -> _preflight
- restage -> _wrong_state
- restage -> next_step
- restage -> select
- review_attach -> @state:ctx
- review_attach -> _apply_verdict
- review_attach -> _parse_verdict
- review_attach -> _preflight
- review_attach -> _wrong_state
- review_attach -> select
- review_collect -> @state:ctx
- review_collect -> _apply_verdict
- review_collect -> _parse_verdict
- review_collect -> _preflight
- review_collect -> _wrong_state
- review_collect -> select
- review_disposition -> @state:ctx
- review_disposition -> _preflight
- review_disposition -> _wrong_state
- review_disposition -> next_step
- review_disposition -> select
- review_request -> @state:ctx
- review_request -> _preflight
- review_request -> _review_package
- review_request -> _wrong_state
- review_request -> next_step
- review_request -> select
- scan_secrets -> @state:ctx
- scan_secrets -> _preflight
- scan_secrets -> _wrong_state
- scan_secrets -> select
- select -> @state:ctx
- select -> _chains_for_worktree
- skip -> @state:ctx
- skip -> _emit_decision
- skip -> _preflight
- skip -> _wrong_state
- skip -> next_step
- skip -> select
- start -> @state:ctx
- start -> _live_chain
- start -> _preflight
- start -> next_step
- status -> @state:ctx
- status -> _record_head_moved
- status -> _recover_committing
- status -> _release_lock
- status -> _require_tombstone_control
- status -> _tombstone_outcome
- status -> next_step
- status -> select
- verify -> @state:ctx
- verify -> _preflight
- verify -> _wrong_state
- verify -> gate_run
- verify -> next_step
- verify -> select
