# Split plan: scripts/forge/forge_cli/engine.py -> scripts/forge/forge_cli/engine/

Inputs: `.refactor/inventory-engine.md/.json` (223 symbols, 295 edges, 12 hubs auto-peeled), symbol-level Tarjan SCC over all 295 edges, `.refactor/plan-chain_core.md` (conventions and precedent, commit 6502849 for the loader patch helper), spec line 117/278/280/285, `policy.py` `REVIEWER_EVAL_TRIGGER_TABLE`. `radon`/`vulture` are not installed.

Method: the same mechanical package conversion as chain_core, then Wave 0 peels constants (`_state.py`) and Wave 1 the hub helpers (`_core.py`); the remaining targets are the inventory's connected components / label-propagation communities, each named by responsibility, each tiny community merged into a neighbour and each >400-line component split along its own hub. Tarjan finds exactly ONE non-trivial SCC (`Engine` -> `FINALIZE_CHECKS` -> `_finalize_*` -> `FinalizeContext` -> `Engine`); the closing edge `FinalizeContext.engine: Engine` is a dataclass field annotation only (line 515, module has `from __future__ import annotations`), so it is a `TYPE_CHECKING` import; three quoted `"Engine"` annotations in the `_command_lock` symbols (lines 4362, 4383, 4515 — `ast.Constant`, so absent from the inventory's `ast.Name` edge list) get the same guard; the target graph is acyclic with no ignored runtime edge, no function-local import, and exactly ONE body edit (pre-wave step E1 below, forced by `__file__` depth). 28 targets result (`Engine` alone is 3,678 lines; the 3-8 target guideline cannot hold for a 12,178-line module).

Conventions for the extractor (identical to the chain_core split): every target is `scripts/forge/forge_cli/engine/<target>.py`; the source of every move is `scripts/forge/forge_cli/engine/__init__.py` (after step E2), which keeps `__all__` verbatim plus re-exports; intra-package imports are absolute (`from forge_cli.engine._core import _run_halt`); external imports (`chain_core`, `runtime`, `candidate_module`, `fresh_eval_module`, envelope, policy, stdlib) are copied per target as needed; every module keeps `from __future__ import annotations`; runtime controls stay read by attribute through `forge_cli.runtime`; `chain_core` names stay read by attribute through `forge_cli.chain_core`. No function or class body is edited after step E1 (`snapshot_bodies.py` oracle taken AFTER E1, before E2). Extractors never edit `.refactor-baseline.json`, `pyproject.toml`, `forge-project.md`, `policy.py`, or the spec.

## Delete first (dead code, with evidence)

- Nothing is deleted in this split. Two module-level state objects are dead: `_CHAIN_CAPABILITY_LOCK` (line 109) and `_CHAIN_CAPABILITIES` (line 112) are referenced by nobody in `engine.py`, `app.py`, `chain_core/`, `scripts/`, or `tests/` (the live capability registry is `batch._FORGE_CLI_CHAIN_CAPABILITIES` in `chain_core/_commit_chain.py:1096`). Both are in `__all__` and forwarded by the `scripts/forge/cli.py` shim `__getattr__`, so removing them changes the exported attribute set the spec (line 117) says the split must not change. Decision: move both to `_state.py`; file a follow-up bead to delete them with an `__all__` change of their own.
- `_MERGE_INITIAL_INTEGRATION` (line 7188) is "used by nobody" in-module but read by `app.py` (`engine._MERGE_INITIAL_INTEGRATION`); it is live. `_DERIVE_MERGE_SCOPE`, `_MERGE_BOOTSTRAP_CHILD_SOURCE`, `_MERGE_CANDIDATE_IDENTITY_FIELDS` are live (default-arg sentinel, child source, identity fields).
- `__all__` (line 11985, 193 lines) stays in `__init__.py`; it is the shim contract.

## Target modules

Code lines are non-blank, non-comment lines of the moved symbols (docstrings included), before the import header (~10-25 lines each). Targets flagged OVER BUDGET hold one unsplittable symbol.

### _state.py — Module-level constants and process state: state/verb sets, `STATE_TRANSITIONS`, TTL, the two `_REQUIRED_*_CONTROLS` with public aliases, the dead capability registry, `CODEX_EXECUTABLE`, fresh-eval request schema/keys, review transport limits and refusal/mismatch strings, `REVIEW_INSTRUCTION`, `REVIEW_LAUNCHER_CODE`, `GLOBAL_OPTIONS_HELP`, `ARCHIVE_CONTAMINATION`, `SECRET_RULES`/`PLACEHOLDER_RE`, `ABORT_DISPOSITION_PRECONDITIONS`, the merge identity fields, the bootstrap child source, the `_DERIVE_MERGE_SCOPE` sentinel and `_MERGE_INITIAL_INTEGRATION`.
- symbols (dependency order): TERMINAL_STATES, TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS, TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES, CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, _FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS, REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION, SECRET_RULES, PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION
- owns state: all 28 names above
- estimated code lines: 280
- imports from package: none (leaf); stdlib `re`, `threading`, `typing.Any` only
- wave: 0
- cycle risks and resolution: none: leaf. `_CHAIN_CAPABILITY_LOCK = threading.Lock()` and `PLACEHOLDER_RE = re.compile(...)` are created here exactly once. `_DERIVE_MERGE_SCOPE = object()` is an identity sentinel compared with `is` in `bind_merge_candidate_generation` (lines 6901, 6903); one object, imported by name, identity preserved. The two comment lines above `REVIEW_DIRECT_PACKAGE_MAX_BYTES`/`REVIEW_MASTER_WINDOW_BYTES` (lines 141-147) move with them.
- fallback seam (orchestrator-only): review strings (`REVIEW_INSTRUCTION`, `REVIEW_LAUNCHER_CODE`, 159 lines) vs everything else

### _core.py — Hub helpers shared by many targets: the three tiny chain helpers, `_transition_state`, `_require_merge_lifecycle_control`, `inspect_common_lock`, the three archive refusal/metadata helpers, `_commit_start_binding_refusal`, evidence fingerprint/record and `_record_process_step`, bound-artifact read/write, `_fresh_eval_invalid_refusal`, `_run_halt`, and the four merge admission/scope dataclasses.
- symbols (dependency order): commit_message_bytes, chain_id_now, promoted_tier, _transition_state, _require_merge_lifecycle_control, inspect_common_lock, _commit_start_binding_refusal, _archive_refusal, _archive_contamination_refusal, _archive_metadata, _env_fingerprint, _evidence_record, _write_artifact, _read_bound_artifact, _fresh_eval_invalid_refusal, _record_process_step, _run_halt, MergeAdmission, MergeScopeResult, MergeCandidateGeneration, MergeBootstrapClassification
- owns state: none
- estimated code lines: 385
- imports from package: _state (STATE_TRANSITIONS, MERGE_LIFECYCLE_CONTROLS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS, ARCHIVE_CONTAMINATION)
- wave: 1
- cycle risks and resolution: none: depends on `_state` only. `inspect_common_lock` (9 lines, leaf) is placed here rather than with `_command_lock` so `_merge_epoch` (its other user via `_merge_process_unresolved`) needs no wave-2 dependency. `_run_halt`, `_mechanical_complete` and `CODEX_EXECUTABLE` are test patch targets: see Risk 1.
- fallback seam (orchestrator-only): dataclasses + refusal helpers vs artifact/evidence helpers (`_write_artifact`, `_read_bound_artifact`, `_env_fingerprint`, `_evidence_record`, `_record_process_step`)

### _journal.py — Ingest-source capture and the chain journal-record builder, including the import-time `runtime._build_chain_journal_records` seam binding.
- symbols (dependency order): _read_ingest_sources, _install_ingest_sources, _capture_ingest_inputs, _binding_for_commit_event, _passed_stack_cell_is_intermediate, _build_chain_journal_records
- owns state: none (but performs the one import-time side effect: line 1786 `runtime._build_chain_journal_records = _build_chain_journal_records`, moved verbatim with its two comment lines directly after the `def`, see Risk 3)
- estimated code lines: 440 (+ header ~15 = ~455; under 500, over the 400 guideline)
- imports from package: none (leaf)
- wave: 2
- cycle risks and resolution: none: leaf. `_passed_stack_cell_is_intermediate` is a test patch target (Risk 1).
- fallback seam (orchestrator-only, if the file exceeds 500 code lines with its header): `_ingest_sources.py` (`_read_ingest_sources`, `_install_ingest_sources`, `_capture_ingest_inputs`, 79 lines) vs journal records

### _parser.py — Argument-parser construction: `ContractArgumentParser`, global-option extraction, the merge-lifecycle subparser, `build_parser`, and raw top-level command detection.
- symbols (dependency order): ContractArgumentParser, _extract_global_options, _attach_merge_lifecycle_parser, build_parser, _raw_top_level_command
- owns state: none
- estimated code lines: 291
- imports from package: _core (_require_merge_lifecycle_control), _state (GLOBAL_OPTIONS_HELP)
- wave: 2
- cycle risks and resolution: none. `build_parser` is read by `app.py` as `engine.build_parser`; spec line 117 pins `--help` bytes: `GLOBAL_OPTIONS_HELP` moves verbatim.
- fallback seam: `_extract_global_options` + `_raw_top_level_command` vs parser builders

### _cli_options.py — Verb-argument post-processing and outcome rendering: `_message_from_args`, the Revision-9 cross-option validator, `render`.
- symbols (dependency order): _message_from_args, _validate_revision9_cross_options, render
- owns state: none
- estimated code lines: 150
- imports from package: none (leaf)
- wave: 2
- cycle risks and resolution: none: leaf. `render` writes to `sys.stdout` and reads `chain_core.canonical_bytes` by attribute.
- fallback seam: none needed

### _command_lock.py — Per-worktree command serialization and chain selection: new-state construction, run/task binding proof, chain/abort-state peeking, run-lock id, abort-disposition refusal, and the `_serialize_worktree_command` decorator applied at `Engine` class-body time.
- symbols (dependency order): _new_state, _prove_run_task_binding, _peek_chain_state, _peek_raw_abort_state, _peek_selected_chain, _command_run_lock_id, abort_disposition_refusal, _serialize_worktree_command
- owns state: none
- estimated code lines: 322
- imports from package: _core (_commit_start_binding_refusal, _run_halt), _state (TERMINAL_STATES, ABORT_DISPOSITION_PRECONDITIONS); plus `if TYPE_CHECKING: from forge_cli.engine._engine import Engine` for the three quoted `"Engine"` annotations: `_peek_selected_chain` (`engine: "Engine"`, line 4362), `_command_run_lock_id` (line 4383) and the inner `wrapped(self: "Engine", ...)` of `_serialize_worktree_command` (line 4515).
- wave: 2
- cycle risks and resolution: one annotation-only edge to `Engine`, invisible to the inventory (quoted annotations are strings, not `ast.Name` references): `grep -n '"Engine"' scripts/forge/forge_cli/engine.py` returns exactly lines 4362, 4383 and 4515, all three in this cluster; no other target has one. Ruff reports F821 for a quoted `"Engine"` with no binding, F821 is not in the `engine.py` per-file-ignores that E2 copies to `engine/*.py` (`pyproject.toml:110`), and mypy would add a new undefined-name key against the type baseline. Resolution: the same guarded import `_finalize.py` gets (Risk 5); no runtime edge `_command_lock -> _engine`. `_engine` does not exist from wave 2 until wave 5: the "module does not exist yet" allowance stated in the wave-4 finalize cluster applies to `_command_lock` from wave 2 through wave 5 (orchestrator decision, same mechanism). `_serialize_worktree_command` is used as a decorator inside `class Engine` (14 methods), so it MUST be importable before `_engine.py` executes: wave 2 < wave 5. It reads `method.__name__` (lines 4517-4559), unaffected by the move.
- fallback seam: peek/lock-id helpers vs `_new_state` + `_prove_run_task_binding` + `abort_disposition_refusal`

### _archive.py — The archive surface: lazy `archive-run.py` module loading (with its cache and lock), tree-clean/NUL path helpers, archive candidate parent/read/render/prepare, and the archive recheck.
- symbols (dependency order): _ARCHIVE_MODULE, _ARCHIVE_MODULE_LOCK, _archive_module, _nul_git_paths, _archive_close_tree_clean, _archive_parent_descriptor, _read_archive_candidate_at, _read_archive_candidate, _render_archive_bytes, _prepare_archive_candidate, _archive_recheck
- owns state: _ARCHIVE_MODULE, _ARCHIVE_MODULE_LOCK
- estimated code lines: 369
- imports from package: _core (_archive_refusal, _archive_contamination_refusal), _state (ARCHIVE_RECHECK_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS)
- wave: 2
- cycle risks and resolution: none. `_archive_module` declares `global _ARCHIVE_MODULE` (line 1938): a `global` rebinds the global of the DEFINING module, so `_ARCHIVE_MODULE` and `_ARCHIVE_MODULE_LOCK` must live in this file with `_archive_module` (they do). The `__init__.py` re-export of `_ARCHIVE_MODULE` is a snapshot of the import-time value (`None`) and never reflects the cache; nothing in the repo reads it (attribute parity only; Risk 6). `_render_archive_bytes`, `_read_archive_candidate`, `ARCHIVE_RECHECK_CONTROLS` are test patch targets (Risk 1).
- fallback seam: `_archive_module` + candidate read/parent helpers vs render/prepare/recheck

### _review_transport.py — FR-216 Revision-10 review package transport: oversize predicate, complete-package refusal, master window count/transport/pointer prompt, master identity/leaf/digest/window readers, and the verified window iterator.
- symbols (dependency order): _review_package_is_oversized, _review_complete_package_refusal, _review_master_window_count, _review_master_transport, _review_master_pointer_prompt, _review_master_identity, _review_master_leaf_is_valid, _read_review_master_digest, _read_review_master_window, _assert_review_master_stable, _iter_verified_master_package_windows, iter_verified_master_package_windows
- owns state: none
- estimated code lines: 232
- imports from package: _state (REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL)
- wave: 2
- cycle risks and resolution: none. The receipt string `"reader=forge_cli.engine.iter_verified_master_package_windows"` (line 2471, asserted by two tests) is a literal and stays byte-identical; `iter_verified_master_package_windows` is re-exported on the package so the dotted name stays true. `REVIEW_MASTER_WINDOW_BYTES` is patched by 5 tests (Risk 1).
- fallback seam: transport/pointer side vs master reader side

### _fresh_eval.py — Fresh reviewer eval request/artifact mechanics: the artifact IO dataclass, control abort, request enumeration, per-step request lookup, evaluation, and the validated manifest.
- symbols (dependency order): _FreshEvalArtifactIO, _FreshEvalControlAbort, _fresh_eval_requests, _fresh_eval_request_for_step, _fresh_eval_evaluation, _validated_fresh_reviewer_manifest
- owns state: none
- estimated code lines: 294
- imports from package: _core (_read_bound_artifact, _write_artifact, _run_halt), _state (FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, _FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS)
- wave: 2
- cycle risks and resolution: none. `_validated_fresh_reviewer_manifest` (fan-in 5) is deliberately NOT a `_core` hub: its dependents (`_finalize`, `_fresh_eval_evidence`, `_gate_checks`, `Engine`) all sit in later waves.
- fallback seam: `_FreshEvalArtifactIO` alone vs the functions

### _fresh_eval_evidence.py — Fresh reviewer evidence package assembly and terminal-step recording.
- symbols (dependency order): _fresh_reviewer_evidence_package, _record_fresh_eval_terminal
- owns state: none
- estimated code lines: 196
- imports from package: _core (_read_bound_artifact, _record_process_step, _transition_state), _fresh_eval (_FreshEvalArtifactIO, _validated_fresh_reviewer_manifest)
- wave: 3
- cycle risks and resolution: none.
- fallback seam: one function each

### _classification.py — Classification child run: argv/environment construction and `_run_classification`.
- symbols (dependency order): _classification_argv, _classification_environment, _run_classification
- owns state: none
- estimated code lines: 180
- imports from package: _core (_env_fingerprint, _record_process_step, _transition_state, promoted_tier)
- wave: 2
- cycle risks and resolution: none.
- fallback seam: none needed

### _candidate_ops.py — Candidate snapshot operations: evidence invalidation, patch ref, snapshot/install, review diff, out-of-band adoption, and `_stage_paths`.
- symbols (dependency order): _invalidate_candidate_evidence, _candidate_patch_ref, _candidate_snapshot, _install_candidate_snapshot, _candidate_review_diff, _adopt_out_of_band_candidate, _stage_paths
- owns state: none
- estimated code lines: 229
- imports from package: _core (_read_bound_artifact, _write_artifact, _transition_state), _classification (_run_classification)
- wave: 3
- cycle risks and resolution: none.
- fallback seam: snapshot helpers vs `_adopt_out_of_band_candidate` + `_stage_paths`

### _gate_checks.py — Gate completeness predicates and the added-secret scan: current test paths, gate-one pair voiding, fresh-reviewer pass/block claims, mechanical-complete/next-incomplete, `SecretFinding` and `scan_added_secrets`.
- symbols (dependency order): _current_test_paths, _void_mismatched_gate_one_pair, _fresh_reviewer_pass_claimed, _fresh_reviewer_block_claimed, _mechanical_complete, _next_incomplete, SecretFinding, scan_added_secrets
- owns state: none
- estimated code lines: 211
- imports from package: _core (_fresh_eval_invalid_refusal), _fresh_eval (_validated_fresh_reviewer_manifest), _state (SECRET_RULES, PLACEHOLDER_RE)
- wave: 3
- cycle risks and resolution: none. The secret-scan trio (61 lines) is a tiny community merged here rather than given its own file. `_mechanical_complete` is a test patch target (Risk 1).
- fallback seam: `_secrets.py` (SecretFinding, scan_added_secrets) vs gate predicates

### _approval.py — Approval and operator authorization: success outcome, authorization issue/problem, pid liveness, and operator-harness verification.
- symbols (dependency order): _success, _issue_authorization, _pid_is_running, _authorization_problem, _verify_operator_harness
- owns state: none
- estimated code lines: 194
- imports from package: _archive (_archive_recheck), _core (_archive_metadata, _transition_state, _record_process_step), _state (TOKEN_TTL_SECONDS)
- wave: 3
- cycle risks and resolution: none.
- fallback seam: none needed

### _finalize.py — The finalize pipeline: `FinalizeContext`, `ProducedCommitContext`, the four produced-commit checks and `PRODUCED_COMMIT_CHECKS`, produced-identity finalize/record/mismatch, the seven `_finalize_*` steps and `FINALIZE_CHECKS`.
- symbols (dependency order): FinalizeContext, ProducedCommitContext, _produced_head_moved, _produced_single_parent, _produced_exact_tree, _produced_exact_message, PRODUCED_COMMIT_CHECKS, _finalize_produced_identity, _record_produced_identity, _produced_mismatch_outcome, _finalize_halt, _finalize_lock, _finalize_candidate, _finalize_evidence, _finalize_fresh_reviewer_evals, _finalize_ttl, _finalize_tree_drift, FINALIZE_CHECKS
- owns state: PRODUCED_COMMIT_CHECKS, FINALIZE_CHECKS (tuples of function references; they must follow the functions they name, hence they live here, not in `_state`)
- estimated code lines: 359
- imports from package: _approval (_authorization_problem), _core (_write_artifact, _archive_metadata, _run_halt, _fresh_eval_invalid_refusal), _fresh_eval (_validated_fresh_reviewer_manifest), _gate_checks (_mechanical_complete, _next_incomplete), _state (PRODUCED_COMMIT_MISMATCH); plus `if TYPE_CHECKING: from forge_cli.engine._engine import Engine` for the `FinalizeContext.engine: Engine` field.
- wave: 4
- cycle risks and resolution: the only SCC in the module (`Engine` <-> finalize pipeline) closes through `FinalizeContext.engine: Engine`, a dataclass field annotation never evaluated at runtime under `from __future__ import annotations` (dataclasses only string-match `ClassVar`/`InitVar`). Resolution: `TYPE_CHECKING`-only import of `Engine` in this file; no runtime edge `_finalize -> _engine`. Ruff F821 is satisfied by the guarded import; the intra-package import-linter contract sets `exclude_type_checking_imports = true` (Risk 5). `_record_produced_identity` is a test patch target (Risk 1).
- fallback seam: produced-identity side (contexts, checks, `_finalize_produced_identity`, `_record_produced_identity`, `_produced_mismatch_outcome`) vs the `_finalize_*` steps + `FINALIZE_CHECKS`

### _merge_candidate.py — Merge candidate admission helpers: nonmovement counter reset, candidate tuple materialize/retain-or-advance, scope request/proof, released predecessor, recorded tip resolution.
- symbols (dependency order): _reset_merge_nonmovement_counter, _materialize_merge_candidate_tuple, _retain_or_advance_merge_candidate, _merge_scope_request, _merge_scope_proof, _merge_released_predecessor, _resolve_recorded_merge_tip
- owns state: none
- estimated code lines: 337
- imports from package: _core (MergeAdmission, MergeScopeResult), _state (_MERGE_CANDIDATE_IDENTITY_FIELDS)
- wave: 2
- cycle risks and resolution: none. `_merge_released_predecessor` (216 lines, leaf, fan-in 0, read by `app.py`) is merged here because a one-function module would be a tiny community.
- fallback seam: `_merge_released_predecessor` alone vs the rest

### _merge_worktree.py — Merge worktree and git metadata observation: plugin manifest/history-mutation parsing, absolute git path, registered worktrees, worktree status, git metadata and owned-rebase metadata, loud recovery mode, cleanup process record and remote-fetch observation.
- symbols (dependency order): _merge_cleanup_process_record, _read_merge_git_metadata, _merge_cleanup_remote_fetch_observation, _parse_plugin_manifest, _parse_history_mutation_mode, _absolute_git_path, _registered_worktrees, _merge_worktree_status, _merge_owned_rebase_metadata, _require_loud_merge_recovery_mode
- owns state: none
- estimated code lines: 302
- imports from package: none (leaf)
- wave: 2
- cycle risks and resolution: none: leaf. `_merge_worktree_status` is a test patch target (Risk 1).
- fallback seam: cleanup/metadata helpers vs manifest/worktree helpers

### _merge_conflict.py — Merge conflict observation: canonical conflict paths, non-conflict index/status bytes, conflict/post-add observation, conflict record and matcher, rebase-result-failed predicate.
- symbols (dependency order): _merge_conflict_path_is_canonical, _parse_merge_conflict_paths, _normalize_merge_conflict_paths, _merge_nonconflict_index_bytes, _merge_nonconflict_status_bytes, _observe_merge_conflict, _observe_merge_post_add, _merge_conflict_record, _merge_conflict_record_matches, _merge_rebase_result_failed
- owns state: none
- estimated code lines: 162
- imports from package: none (leaf)
- wave: 2
- cycle risks and resolution: none: leaf.
- fallback seam: none needed

### _merge_rebase_integrated.py — Rebase-integrated proof: branch reflog proof, integrated observation binding, operation-metadata-absent predicate, and the integrated predicate.
- symbols (dependency order): _merge_branch_reflog_proves_integrated, _merge_rebase_integrated_observation_binding, _merge_rebase_operation_metadata_absent, _merge_rebase_integrated_predicate
- owns state: none
- estimated code lines: 240
- imports from package: none (leaf)
- wave: 2
- cycle risks and resolution: none: leaf.
- fallback seam: none needed

### _merge_scope_derive.py — Merge scope environment and derivation: scope environment, git no-lazy-fetch qualification (dataclass, digest, executable qualification, qualify/require), sidecar fence discovery, name-status/scope output parsing, `_derive_merge_scope`.
- symbols (dependency order): _merge_scope_environment, _GitNoLazyFetchQualification, _git_environment_digest, _git_executable_qualification, _qualify_git_no_lazy_fetch, _require_git_no_lazy_fetch_qualification, _discover_merge_scope_fence_from_sidecar, _parse_merge_name_status_output, _parse_merge_scope_output, _derive_merge_scope
- owns state: none
- estimated code lines: 351
- imports from package: _core (MergeAdmission, MergeScopeResult)
- wave: 2
- cycle risks and resolution: none. `_derive_merge_scope` (5 patch sites), `_git_executable_qualification`, `_qualify_git_no_lazy_fetch` are test patch targets (Risk 1).
- fallback seam: git qualification (first six) vs scope parsing/derivation

### _merge_scope_binding.py — Merge scope binding lifecycle: child result, inspection dataclass, temporary unlink, classify (at/current), resume, publish.
- symbols (dependency order): _merge_scope_child_result, MergeScopeBindingInspection, _unlink_merge_scope_temporary_at, _classify_merge_scope_binding_at, _classify_merge_scope_binding, _resume_merge_scope_binding, _publish_merge_scope_binding
- owns state: none
- estimated code lines: 388
- imports from package: none (leaf)
- wave: 2
- cycle risks and resolution: none: leaf. `_publish_merge_scope_binding`, `_classify_merge_scope_binding`, `_unlink_merge_scope_temporary_at` are test patch targets (Risk 1).
- fallback seam: `_publish_merge_scope_binding` (173 lines) alone vs the rest

### _merge_bootstrap_child.py — Revision-12 merge bootstrap child protocol: the child `main` and the parent-side argv builder.
- symbols (dependency order): _merge_bootstrap_child_main, _merge_bootstrap_child_argv
- owns state: none
- estimated code lines: 216
- imports from package: _core (MergeAdmission), _merge_scope_derive (_git_environment_digest, _parse_merge_name_status_output), _state (_MERGE_BOOTSTRAP_CHILD_SOURCE)
- wave: 3
- cycle risks and resolution: none. HAZARD resolved before the split: `_merge_bootstrap_child_argv` line 6361 computes the re-exec target as `Path(__file__).resolve().parents[1] / "cli.py"`; from `engine/<anything>.py` that resolves to the non-existent `forge_cli/cli.py`. Pre-wave step E1 replaces that one expression with `Path(runtime.__file__).resolve().parents[1] / "cli.py"` (`runtime.py` sits in `forge_cli/`, so its `parents[1]` is `scripts/forge/` from any depth; `runtime.SCRIPT_DIR` was rejected because five fixtures patch it to a helpers/ directory without a cli.py), so the symbol is depth-independent when it moves (Risk 2).
- fallback seam: one function each

### _merge_bootstrap_result.py — Decoding of the bootstrap child result.
- symbols (dependency order): _decode_merge_bootstrap_result
- owns state: none
- estimated code lines: 189
- imports from package: none (leaf)
- wave: 2
- cycle risks and resolution: none: leaf; a single 196-line function (3 patch sites, Risk 1).
- fallback seam: none available

### _merge_epoch.py — Merge run directory and epoch facts: run directory, merge artifact read/write, gate suite/current, event and epoch-fetch digests, inactive/attempt/started-child/active-epoch predicates, unresolved process, `_MergeEpochBudget`, epoch suite, remote observation intent.
- symbols (dependency order): _merge_run_directory, _write_merge_artifact, _read_merge_artifact, _merge_gate_suite, _merge_gate_current, _merge_event_digest, _merge_epoch_fetch_observation_digest, _merge_inactive, _merge_has_attempt, _merge_inactive_epoch_has_no_started_child, _require_active_merge_epoch, _merge_process_unresolved, _MergeEpochBudget, _merge_epoch_suite, _remote_observation_intent
- owns state: none
- estimated code lines: 352
- imports from package: _core (_write_artifact, _read_bound_artifact, inspect_common_lock)
- wave: 2
- cycle risks and resolution: none. `_merge_process_unresolved`, `_require_active_merge_epoch`, `_merge_epoch_suite`, `_merge_run_directory`, `_read_merge_artifact`, `_write_merge_artifact` are test patch targets (Risk 1).
- fallback seam: artifact/gate/digest helpers vs epoch predicates + budget

### _merge_claim.py — Merge claim publication: record validation, owner directory, claim identity, read/publish/remove, publication failure, unpublished-claim-absent.
- symbols (dependency order): _validate_merge_claim_record, _merge_owner_directory, _merge_claim_identity, _read_merge_claim, _publish_merge_claim, _merge_publication_failure, _remove_merge_claim, _merge_unpublished_claim_absent
- owns state: none
- estimated code lines: 271
- imports from package: _core (_require_merge_lifecycle_control)
- wave: 2
- cycle risks and resolution: none. `_publish_merge_claim`, `_remove_merge_claim` are test patch targets (Risk 1).
- fallback seam: `_merge_publication_failure` (103 lines) alone vs the rest

### _merge_candidate_observation.py — Candidate observation outputs and parsing.
- symbols (dependency order): _merge_candidate_observation_outputs, _parse_merge_candidate_observation
- owns state: none
- estimated code lines: 288
- imports from package: _merge_worktree (_parse_plugin_manifest)
- wave: 3
- cycle risks and resolution: none.
- fallback seam: none available (one 265-line function)

### _merge_candidate_generation.py — Merge candidate generation binding: scope from candidate observation and `bind_merge_candidate_generation`.
- symbols (dependency order): _merge_scope_from_candidate_observation, bind_merge_candidate_generation
- owns state: none
- estimated code lines: 378
- imports from package: _core (MergeAdmission, MergeScopeResult, MergeCandidateGeneration), _merge_candidate_observation (_merge_candidate_observation_outputs, _parse_merge_candidate_observation), _merge_scope_derive (_derive_merge_scope, _parse_merge_scope_output), _merge_worktree (_merge_worktree_status), _state (_DERIVE_MERGE_SCOPE)
- wave: 4
- cycle risks and resolution: none. `_DERIVE_MERGE_SCOPE` is the default of the `scope_result` parameter (line 6762): it must be bound (imported) before the `def` executes — it is, from `_state`.
- fallback seam: none available (one 313-line function)

### _engine.py — The `Engine` class (41 methods: tombstone, journal ingest/recover, select/status/start/classify/restage/abort/abort-disposition/rebase, gate run, secret scan, verify, review request/collect/attach/disposition, approve, skip, finalize, recovery). OVER BUDGET.
- symbols (dependency order): Engine
- owns state: none
- estimated code lines: 3544 (OVER BUDGET: one unsplittable class; baseline entry in the finalize wave under operator direction, Risk 4)
- imports from package: _approval, _archive, _candidate_ops, _classification, _command_lock (`_serialize_worktree_command` at class-body time), _core, _finalize, _fresh_eval, _fresh_eval_evidence, _gate_checks, _journal, _review_transport, _state — 61 names, listed by the inventory edge list for `Engine`.
- wave: 5
- cycle risks and resolution: none at runtime; `_finalize` reaches `Engine` only under `TYPE_CHECKING`. `Engine` reads `chain_core.register_coordination_seams`, `runtime._coordination_modules`, etc. by attribute (unchanged). Follow-up (not this split): split `Engine` into verb mixins — a class-structure change needing its own review.
- fallback seam: none (no body edits)

### __init__.py — stays: `__all__` (verbatim, 193 lines), the module docstring (updated only in the finalize wave), and one `from forge_cli.engine.<owner> import <name> as <name>` per moved symbol (222 lines); ~420 code lines after the finalize wave. Reason `__all__` stays: the `scripts/forge/cli.py` shim forwards exactly this list through `__getattr__` (cli.py:90).

## State ownership table

| state | owner module | users |
|---|---|---|
| `TERMINAL_STATES` | `_state.py` | `Engine`, `_peek_selected_chain` |
| `TERMINAL_TOUCH_VERBS` | `_state.py` | `Engine` (+ 2 test patch sites) |
| `STATE_TRANSITIONS` | `_state.py` | `_transition_state` |
| `TOKEN_TTL_SECONDS` | `_state.py` | `_authorization_problem`, `_issue_authorization` |
| `_REQUIRED_MERGE_LIFECYCLE_CONTROLS` | `_state.py` | `MERGE_LIFECYCLE_CONTROLS`, `_require_merge_lifecycle_control` |
| `MERGE_LIFECYCLE_CONTROLS` | `_state.py` | `_require_merge_lifecycle_control` (+ 1 test patch site) |
| `_REQUIRED_ARCHIVE_RECHECK_CONTROLS` | `_state.py` | `ARCHIVE_RECHECK_CONTROLS`, `_archive_recheck` |
| `ARCHIVE_RECHECK_CONTROLS` | `_state.py` | `_archive_recheck` (+ 1 test patch site) |
| `_CHAIN_CAPABILITY_LOCK` | `_state.py` | nobody (dead; kept for `__all__`) |
| `_CHAIN_CAPABILITIES` | `_state.py` | nobody (dead; kept for `__all__`) |
| `_ARCHIVE_MODULE` | `_archive.py` | `_archive_module` (rebinds it via `global`) |
| `_ARCHIVE_MODULE_LOCK` | `_archive.py` | `_archive_module` |
| `CODEX_EXECUTABLE` | `_state.py` | `Engine` (+ 8 test patch sites) |
| `FRESH_REVIEWER_EVAL_REQUEST_SCHEMA` | `_state.py` | `Engine`, `_fresh_eval_evaluation` |
| `_FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS` | `_state.py` | `_fresh_eval_evaluation` |
| `REVIEW_DIRECT_PACKAGE_MAX_BYTES` | `_state.py` | `_review_package_is_oversized` (+ app.py read) |
| `REVIEW_MASTER_WINDOW_BYTES` | `_state.py` | `Engine`, `_iter_verified_master_package_windows`, `_review_master_transport`, `_review_master_window_count` (+ 5 test patch sites, app.py read) |
| `REVIEW_COMPLETE_PACKAGE_REFUSAL` | `_state.py` | `_review_complete_package_refusal`, `_review_master_pointer_prompt` |
| `PRODUCED_COMMIT_MISMATCH` | `_state.py` | `_produced_mismatch_outcome` |
| `REVIEW_INSTRUCTION` | `_state.py` | `Engine` |
| `REVIEW_LAUNCHER_CODE` | `_state.py` | `Engine` |
| `GLOBAL_OPTIONS_HELP` | `_state.py` | `build_parser` |
| `ARCHIVE_CONTAMINATION` | `_state.py` | `_archive_contamination_refusal` |
| `SECRET_RULES` | `_state.py` | `scan_added_secrets` |
| `PLACEHOLDER_RE` | `_state.py` | `scan_added_secrets` |
| `ABORT_DISPOSITION_PRECONDITIONS` | `_state.py` | `abort_disposition_refusal` |
| `_MERGE_CANDIDATE_IDENTITY_FIELDS` | `_state.py` | `_retain_or_advance_merge_candidate` |
| `_MERGE_BOOTSTRAP_CHILD_SOURCE` | `_state.py` | `_merge_bootstrap_child_argv` |
| `_DERIVE_MERGE_SCOPE` | `_state.py` | `bind_merge_candidate_generation` (default arg + `is` checks) |
| `_MERGE_INITIAL_INTEGRATION` | `_state.py` | nobody in-module; `app.py` reads `engine._MERGE_INITIAL_INTEGRATION` |
| `PRODUCED_COMMIT_CHECKS` | `_finalize.py` | `Engine`, `_finalize_produced_identity` |
| `FINALIZE_CHECKS` | `_finalize.py` | `Engine` |
| `__all__` | `__init__.py` | `scripts/forge/cli.py` `__getattr__` |
| (side effect) `runtime._build_chain_journal_records = _build_chain_journal_records` | `_journal.py` | `chain_core` (reads the seam by attribute at call time); tests patch it on `forge_cli.runtime` |
| `global _ARCHIVE_MODULE` (in `_archive_module`) | `_archive.py` | same module as the state it rebinds |

Every owner is in a wave strictly before (or equal to, same file) every user's wave.

## Waves

Wave membership = closure over the target graph (all 295 edges minus the one `TYPE_CHECKING` edge): a target is in wave N when every target it imports is in a wave < N (asserted by the generator script; no edge joins two members of the same wave; `_core -> _state` is why `_state` (wave 0) and `_core` (wave 1) are two single-cluster waves, never side by side). A wave starts only after the previous wave is merged. The orchestrator runs the pre-wave steps E0, E1, E2 and the finalize wave (wave 6) by hand; `.refactor/plan-engine.json` `waves` covers only the rope extraction clusters (waves 0-5, one JSON entry per plan wave, same numbering). Each extractor: move the listed symbols from `engine/__init__.py` (rope `move` or verbatim cut) into the target, add the imports the target needs from earlier-wave modules, add `from forge_cli.engine.<target> import <name> as <name>` to `__init__.py` for every moved name, run the gate (including `snapshot_bodies.py`: bodies byte-identical to the post-E1 snapshot; `patch_engine` sweep from step E0).

Size rule: if any non-flagged target exceeds 500 code lines including its header after extraction, the orchestrator (never an extractor) splits it on the seam named in that target's section before the wave is merged. Flagged (OVER BUDGET): `_engine.py` only.

### Pre-wave (sequential, one worktree, three commits, all BEFORE wave 0)
- step E0 (tests only, precedent commit 6502849): add `patch_engine(name, ...)` to `tests/_cli_loader.py` — patches `forge_cli.engine` (the package root, or the module before E2) and every `forge_cli.engine.*` submodule that binds the name with the same object, restoring on exit, refusing names the root does not bind (mirror `_ChainCorePatch`/`_engine_modules()` with `pkgutil.iter_modules`). Rewrite every `mock.patch.object(ENGINE, "<name>", ...)` / `mock.patch("forge_cli.engine.<name>", ...)` site to it: 28 distinct names at ~70 sites in `tests/test_cli_loader.py`, `test_revision9_archive.py`, `test_revision9_cli_surfaces.py`, `test_revision9_ingest_negatives.py`, `test_revision9_matrix.py`, `test_revision9_terminal_races.py`, `test_revision10_review_transport.py`, `test_cli_merge_lifecycle.py`, `test_cli_merge_integration.py`, `test_cli_merge_adapters.py`, `test_cli_chain_finalize.py`, `test_fresh_reviewer_cli.py`. Names: CODEX_EXECUTABLE, REVIEW_MASTER_WINDOW_BYTES, TERMINAL_TOUCH_VERBS, ARCHIVE_RECHECK_CONTROLS, MERGE_LIFECYCLE_CONTROLS, _run_halt, _mechanical_complete, _review_package_is_oversized, _record_produced_identity, _passed_stack_cell_is_intermediate, _render_archive_bytes, _read_archive_candidate, _derive_merge_scope, _publish_merge_claim, _remove_merge_claim, _merge_process_unresolved, _publish_merge_scope_binding, _classify_merge_scope_binding, _unlink_merge_scope_temporary_at, _decode_merge_bootstrap_result, _git_executable_qualification, _qualify_git_no_lazy_fetch, _read_merge_artifact, _write_merge_artifact, _require_active_merge_epoch, _merge_epoch_suite, _merge_run_directory, _merge_worktree_status. Extend the `_moved_shim_patch_offenders` sweep in `tests/test_cli_loader.py` so a raw `patch.object(ENGINE, ...)` fails the loader test. Commit `test(engine): patch engine controls through one loader helper`. (Patches on `Engine` INSTANCES — `patch.object(engine, "_halt"|"_load"|"_review_package")` where `engine` is an instance — are not module patches and stay as they are.)
- step E1 (ONE body edit, own commit, control-class path): in `_merge_bootstrap_child_argv` (line 6361) replace `str(Path(__file__).resolve().parents[1] / "cli.py")` with `str(Path(runtime.__file__).resolve().parents[1] / "cli.py")` and update the two-line comment above it; add a focused test asserting `_merge_bootstrap_child_argv(...)[3] == str(Path(runtime.__file__).resolve().parents[1] / "cli.py") == str(ROOT / "scripts/forge/cli.py"), with runtime.SCRIPT_DIR both unpatched and patched (fixtures in test_cli_merge_adapters, test_revision9_matrix, test_revision9_archive, test_revision9_cli_surfaces and test_revision9_terminal_races patch SCRIPT_DIR to a helpers/ directory without a cli.py, so a SCRIPT_DIR-based target breaks them; the gate on the SCRIPT_DIR variant failed test_cli_merge_adapters.test_disposition_slot_allows_minor_then_exactly_one_above_minor with "merge start refused — fixed target fetch failed")`. Then take the body snapshot (`snapshot_bodies.py` -> `.refactor/before.json`). Commit `refactor(engine): resolve the bootstrap re-exec target through runtime.SCRIPT_DIR`.
- step E2 (package conversion, own commit): `git mv scripts/forge/forge_cli/engine.py scripts/forge/forge_cli/engine/__init__.py`; re-key `.refactor-baseline.json` from `scripts/forge/forge_cli/engine.py` to `scripts/forge/forge_cli/engine/__init__.py` with the SAME number (11412; may shrink, never grow); add the `pyproject.toml` per-file-ignores entry `"scripts/forge/forge_cli/engine/*.py"` with the current engine.py rule list (narrow per module in the finalize wave, as chain_core did) and keep the `engine.py` entry until the finalize wave removes it; nothing else changes. Run the gate; commit `refactor(engine): convert module to package (no code moved)`. From here on `engine/__init__.py` is the source module for every wave. Reviewer: `git ls-files scripts/forge/forge_cli/engine.py` is empty from E2 on.

### Wave 0 (single cluster)
- cluster "state": target=_state.py symbols=[TERMINAL_STATES, TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS, TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES, CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, _FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS, REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION, SECRET_RULES, PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION]
### Wave 1 (single cluster, after wave 0 merged; `_core` imports `_state`)
- cluster "core": target=_core.py symbols=[commit_message_bytes, chain_id_now, promoted_tier, _transition_state, _require_merge_lifecycle_control, inspect_common_lock, _commit_start_binding_refusal, _archive_refusal, _archive_contamination_refusal, _archive_metadata, _env_fingerprint, _evidence_record, _write_artifact, _read_bound_artifact, _fresh_eval_invalid_refusal, _record_process_step, _run_halt, MergeAdmission, MergeScopeResult, MergeCandidateGeneration, MergeBootstrapClassification]

### Wave 2 (parallel, after wave 1 merged; every cluster imports only `_state`/`_core` or nothing)
- cluster "journal": target=_journal.py symbols=[_read_ingest_sources, _install_ingest_sources, _capture_ingest_inputs, _binding_for_commit_event, _passed_stack_cell_is_intermediate, _build_chain_journal_records] (+ the line-1786 seam statement, verbatim, after the last def)
- cluster "parser": target=_parser.py symbols=[ContractArgumentParser, _extract_global_options, _attach_merge_lifecycle_parser, build_parser, _raw_top_level_command]
- cluster "cli options": target=_cli_options.py symbols=[_message_from_args, _validate_revision9_cross_options, render]
- cluster "command lock": target=_command_lock.py symbols=[_new_state, _prove_run_task_binding, _peek_chain_state, _peek_raw_abort_state, _peek_selected_chain, _command_run_lock_id, abort_disposition_refusal, _serialize_worktree_command] (+ `if TYPE_CHECKING: from forge_cli.engine._engine import Engine` for the three quoted `"Engine"` annotations at lines 4362/4383/4515; `_engine` does not exist until wave 5 — the same "module does not exist yet" allowance as the wave-4 finalize cluster, waves 2 through 5)
- cluster "archive": target=_archive.py symbols=[_ARCHIVE_MODULE, _ARCHIVE_MODULE_LOCK, _archive_module, _nul_git_paths, _archive_close_tree_clean, _archive_parent_descriptor, _read_archive_candidate_at, _read_archive_candidate, _render_archive_bytes, _prepare_archive_candidate, _archive_recheck]
- cluster "review transport": target=_review_transport.py symbols=[_review_package_is_oversized, _review_complete_package_refusal, _review_master_window_count, _review_master_transport, _review_master_pointer_prompt, _review_master_identity, _review_master_leaf_is_valid, _read_review_master_digest, _read_review_master_window, _assert_review_master_stable, _iter_verified_master_package_windows, iter_verified_master_package_windows]
- cluster "fresh eval": target=_fresh_eval.py symbols=[_FreshEvalArtifactIO, _FreshEvalControlAbort, _fresh_eval_requests, _fresh_eval_request_for_step, _fresh_eval_evaluation, _validated_fresh_reviewer_manifest]
- cluster "classification": target=_classification.py symbols=[_classification_argv, _classification_environment, _run_classification]
- cluster "merge candidate": target=_merge_candidate.py symbols=[_reset_merge_nonmovement_counter, _materialize_merge_candidate_tuple, _retain_or_advance_merge_candidate, _merge_scope_request, _merge_scope_proof, _merge_released_predecessor, _resolve_recorded_merge_tip]
- cluster "merge worktree": target=_merge_worktree.py symbols=[_merge_cleanup_process_record, _read_merge_git_metadata, _merge_cleanup_remote_fetch_observation, _parse_plugin_manifest, _parse_history_mutation_mode, _absolute_git_path, _registered_worktrees, _merge_worktree_status, _merge_owned_rebase_metadata, _require_loud_merge_recovery_mode]
- cluster "merge conflict": target=_merge_conflict.py symbols=[_merge_conflict_path_is_canonical, _parse_merge_conflict_paths, _normalize_merge_conflict_paths, _merge_nonconflict_index_bytes, _merge_nonconflict_status_bytes, _observe_merge_conflict, _observe_merge_post_add, _merge_conflict_record, _merge_conflict_record_matches, _merge_rebase_result_failed]
- cluster "merge rebase integrated": target=_merge_rebase_integrated.py symbols=[_merge_branch_reflog_proves_integrated, _merge_rebase_integrated_observation_binding, _merge_rebase_operation_metadata_absent, _merge_rebase_integrated_predicate]
- cluster "merge scope derive": target=_merge_scope_derive.py symbols=[_merge_scope_environment, _GitNoLazyFetchQualification, _git_environment_digest, _git_executable_qualification, _qualify_git_no_lazy_fetch, _require_git_no_lazy_fetch_qualification, _discover_merge_scope_fence_from_sidecar, _parse_merge_name_status_output, _parse_merge_scope_output, _derive_merge_scope]
- cluster "merge scope binding": target=_merge_scope_binding.py symbols=[_merge_scope_child_result, MergeScopeBindingInspection, _unlink_merge_scope_temporary_at, _classify_merge_scope_binding_at, _classify_merge_scope_binding, _resume_merge_scope_binding, _publish_merge_scope_binding]
- cluster "merge bootstrap result": target=_merge_bootstrap_result.py symbols=[_decode_merge_bootstrap_result]
- cluster "merge epoch": target=_merge_epoch.py symbols=[_merge_run_directory, _write_merge_artifact, _read_merge_artifact, _merge_gate_suite, _merge_gate_current, _merge_event_digest, _merge_epoch_fetch_observation_digest, _merge_inactive, _merge_has_attempt, _merge_inactive_epoch_has_no_started_child, _require_active_merge_epoch, _merge_process_unresolved, _MergeEpochBudget, _merge_epoch_suite, _remote_observation_intent]
- cluster "merge claim": target=_merge_claim.py symbols=[_validate_merge_claim_record, _merge_owner_directory, _merge_claim_identity, _read_merge_claim, _publish_merge_claim, _merge_publication_failure, _remove_merge_claim, _merge_unpublished_claim_absent]

### Wave 3 (parallel, after wave 2 merged)
- cluster "fresh eval evidence": target=_fresh_eval_evidence.py symbols=[_fresh_reviewer_evidence_package, _record_fresh_eval_terminal]
- cluster "candidate ops": target=_candidate_ops.py symbols=[_invalidate_candidate_evidence, _candidate_patch_ref, _candidate_snapshot, _install_candidate_snapshot, _candidate_review_diff, _adopt_out_of_band_candidate, _stage_paths]
- cluster "gate checks": target=_gate_checks.py symbols=[_current_test_paths, _void_mismatched_gate_one_pair, _fresh_reviewer_pass_claimed, _fresh_reviewer_block_claimed, _mechanical_complete, _next_incomplete, SecretFinding, scan_added_secrets]
- cluster "approval": target=_approval.py symbols=[_success, _issue_authorization, _pid_is_running, _authorization_problem, _verify_operator_harness]
- cluster "merge bootstrap child": target=_merge_bootstrap_child.py symbols=[_merge_bootstrap_child_main, _merge_bootstrap_child_argv]
- cluster "merge candidate observation": target=_merge_candidate_observation.py symbols=[_merge_candidate_observation_outputs, _parse_merge_candidate_observation]

### Wave 4 (parallel, after wave 3 merged)
- cluster "finalize": target=_finalize.py symbols=[FinalizeContext, ProducedCommitContext, _produced_head_moved, _produced_single_parent, _produced_exact_tree, _produced_exact_message, PRODUCED_COMMIT_CHECKS, _finalize_produced_identity, _record_produced_identity, _produced_mismatch_outcome, _finalize_halt, _finalize_lock, _finalize_candidate, _finalize_evidence, _finalize_fresh_reviewer_evals, _finalize_ttl, _finalize_tree_drift, FINALIZE_CHECKS] (+ `if TYPE_CHECKING: from forge_cli.engine._engine import Engine`; `_engine` does not exist yet in wave 4 — the guarded import is never executed, and ruff/mypy resolve it once wave 5 lands; if the type checker in the gate rejects the forward module, keep the guarded import and let the orchestrator (never the extractor) accept the one new `import-not-found` key for `forge_cli.engine._engine` in `type_baseline.py check` until wave 5 lands — the "module does not exist yet" allowance; it covers `_command_lock` (wave 2) and `_finalize` (wave 4) alike and is withdrawn in the wave-5 gate)
- cluster "merge candidate generation": target=_merge_candidate_generation.py symbols=[_merge_scope_from_candidate_observation, bind_merge_candidate_generation]

### Wave 5 (single cluster, after wave 4 merged)
- cluster "engine": target=_engine.py symbols=[Engine]

### Wave 6 (finalize; orchestrator, by hand, control-class, binding review + explicit operator approval)
- `engine/__init__.py`: docstring updated to describe the package (mirroring the chain_core wording); verify it is `__all__` + re-exports only; no unused imports re-bound.
- `.refactor-baseline.json`: shrink `scripts/forge/forge_cli/engine/__init__.py` to its final count (or delete if <= 500); add `scripts/forge/forge_cli/engine/_engine.py` (about 3560) under explicit operator direction.
- `pyproject.toml`: delete the `scripts/forge/forge_cli/engine.py` per-file-ignores entry; narrow the `engine/*.py` entry per module from `ruff check`; add a `forge_cli.engine layers` import-linter contract (`containers = ["forge_cli.engine"]`, layers in wave order top-down: `_engine`; `_finalize | _merge_candidate_generation`; `_fresh_eval_evidence | _candidate_ops | _gate_checks | _approval | _merge_bootstrap_child | _merge_candidate_observation`; the 17 wave-2 modules with `|`; `_core`; `_state`) with `exclude_type_checking_imports = true` (that setting, not `ignore_imports`, is what excludes the two `TYPE_CHECKING`-only upward edges `_finalize -> _engine` and `_command_lock -> _engine`) and the same three `runtime -> codex_orchestrator` ignores.
- Trigger path (spec-bound): replace the literal `scripts/forge/forge_cli/engine.py` with `scripts/forge/forge_cli/engine/**` in `docs/specs/forge-plugin-spec.md` lines 278, 280, 285 (and the line-117 package description), `scripts/forge/forge_cli/policy.py` `REVIEWER_EVAL_TRIGGER_TABLE` (lines 71, 75), `forge-project.md`, `system/template/forge-project.md`, `AGENTS.md` (368, 370), `.forge/evals/tasks/fr230-phase3-4-v2.manifest.json` line 99 (production subject), and the fixture copies in `tests/test_cli_chain.py` (145, 147, 709, 773), `tests/test_cli_chain_finalize.py` (90, 92), `tests/test_cli_policy_fences.py` (80, 82), `tests/test_drift_check.py` (29, 31), `tests/test_fresh_eval_policy.py` (255, 288, 289, 321, 322). See Risk 7 (OPERATOR DECISION): under Option A the table already names both paths when this wave runs and this wave only removes the old literal (Option A step 8); under Option B this wave makes the whole change.
- CHANGELOG entry; STRICT evals (spec/skills/agents triggers) and `tests.test_repo_conformance`; full gate-1 twice.

## Re-exports required in __init__.py

`__all__` (191 names; keep the literal verbatim, order unchanged) — every name must be importable as `forge_cli.engine.<name>` after the split because `scripts/forge/cli.py:90` forwards exactly this list through `__getattr__`, `app.py` reads ~95 of them as `engine.<name>` / `_engine_module.<name>`, and `tests/_cli_loader.package_module("engine")` reaches the package root:

`ABORT_DISPOSITION_PRECONDITIONS`, `ARCHIVE_CONTAMINATION`, `ARCHIVE_RECHECK_CONTROLS`, `CODEX_EXECUTABLE`, `ContractArgumentParser`, `Engine`, `FINALIZE_CHECKS`, `FRESH_REVIEWER_EVAL_REQUEST_SCHEMA`, `FinalizeContext`, `GLOBAL_OPTIONS_HELP`, `MERGE_LIFECYCLE_CONTROLS`, `MergeAdmission`, `MergeBootstrapClassification`, `MergeCandidateGeneration`, `MergeScopeBindingInspection`, `MergeScopeResult`, `PLACEHOLDER_RE`, `PRODUCED_COMMIT_CHECKS`, `PRODUCED_COMMIT_MISMATCH`, `REVIEW_COMPLETE_PACKAGE_REFUSAL`, `REVIEW_DIRECT_PACKAGE_MAX_BYTES`, `REVIEW_INSTRUCTION`, `REVIEW_LAUNCHER_CODE`, `REVIEW_MASTER_WINDOW_BYTES`, `SECRET_RULES`, `STATE_TRANSITIONS`, `SecretFinding`, `TERMINAL_STATES`, `TERMINAL_TOUCH_VERBS`, `TOKEN_TTL_SECONDS`, `_ARCHIVE_MODULE`, `_ARCHIVE_MODULE_LOCK`, `_CHAIN_CAPABILITIES`, `_CHAIN_CAPABILITY_LOCK`, `_DERIVE_MERGE_SCOPE`, `_GitNoLazyFetchQualification`, `_MERGE_BOOTSTRAP_CHILD_SOURCE`, `_MERGE_CANDIDATE_IDENTITY_FIELDS`, `_MERGE_INITIAL_INTEGRATION`, `_MergeEpochBudget`, `_REQUIRED_ARCHIVE_RECHECK_CONTROLS`, `_REQUIRED_MERGE_LIFECYCLE_CONTROLS`, `_absolute_git_path`, `_adopt_out_of_band_candidate`, `_archive_close_tree_clean`, `_archive_contamination_refusal`, `_archive_metadata`, `_archive_module`, `_archive_parent_descriptor`, `_archive_recheck`, `_archive_refusal`, `_attach_merge_lifecycle_parser`, `_authorization_problem`, `_binding_for_commit_event`, `_build_chain_journal_records`, `_capture_ingest_inputs`, `_classification_argv`, `_classification_environment`, `_classify_merge_scope_binding`, `_classify_merge_scope_binding_at`, `_command_run_lock_id`, `_current_test_paths`, `_decode_merge_bootstrap_result`, `_derive_merge_scope`, `_discover_merge_scope_fence_from_sidecar`, `_env_fingerprint`, `_evidence_record`, `_extract_global_options`, `_finalize_candidate`, `_finalize_evidence`, `_finalize_fresh_reviewer_evals`, `_finalize_halt`, `_finalize_lock`, `_finalize_produced_identity`, `_finalize_tree_drift`, `_finalize_ttl`, `_git_environment_digest`, `_git_executable_qualification`, `_install_ingest_sources`, `_invalidate_candidate_evidence`, `_install_candidate_snapshot`, `_issue_authorization`, `_materialize_merge_candidate_tuple`, `_mechanical_complete`, `_merge_bootstrap_child_argv`, `_merge_bootstrap_child_main`, `_merge_branch_reflog_proves_integrated`, `_merge_candidate_observation_outputs`, `_merge_claim_identity`, `_merge_cleanup_process_record`, `_merge_cleanup_remote_fetch_observation`, `_merge_conflict_path_is_canonical`, `_merge_conflict_record`, `_merge_conflict_record_matches`, `_merge_epoch_fetch_observation_digest`, `_merge_epoch_suite`, `_merge_event_digest`, `_merge_gate_current`, `_merge_gate_suite`, `_merge_has_attempt`, `_merge_inactive`, `_merge_inactive_epoch_has_no_started_child`, `_merge_nonconflict_index_bytes`, `_merge_nonconflict_status_bytes`, `_merge_owned_rebase_metadata`, `_merge_owner_directory`, `_merge_process_unresolved`, `_merge_publication_failure`, `_merge_rebase_integrated_observation_binding`, `_merge_rebase_integrated_predicate`, `_merge_rebase_operation_metadata_absent`, `_merge_rebase_result_failed`, `_merge_released_predecessor`, `_merge_run_directory`, `_merge_scope_child_result`, `_merge_scope_environment`, `_merge_scope_from_candidate_observation`, `_merge_scope_proof`, `_merge_scope_request`, `_merge_unpublished_claim_absent`, `_merge_worktree_status`, `_message_from_args`, `_new_state`, `_next_incomplete`, `_normalize_merge_conflict_paths`, `_nul_git_paths`, `_observe_merge_conflict`, `_observe_merge_post_add`, `_parse_history_mutation_mode`, `_parse_merge_candidate_observation`, `_parse_merge_conflict_paths`, `_parse_merge_name_status_output`, `_parse_merge_scope_output`, `_parse_plugin_manifest`, `_peek_chain_state`, `_peek_raw_abort_state`, `_peek_selected_chain`, `_pid_is_running`, `_prepare_archive_candidate`, `_prove_run_task_binding`, `_publish_merge_claim`, `_publish_merge_scope_binding`, `_qualify_git_no_lazy_fetch`, `_raw_top_level_command`, `_read_archive_candidate`, `_read_archive_candidate_at`, `_read_bound_artifact`, `_read_ingest_sources`, `_read_merge_artifact`, `_read_merge_claim`, `_read_merge_git_metadata`, `_read_review_master_window`, `_record_process_step`, `_registered_worktrees`, `_remote_observation_intent`, `_review_master_transport`, `_review_master_window_count`, `_review_package_is_oversized`, `_remove_merge_claim`, `_render_archive_bytes`, `_require_active_merge_epoch`, `_require_git_no_lazy_fetch_qualification`, `_require_loud_merge_recovery_mode`, `_require_merge_lifecycle_control`, `_reset_merge_nonmovement_counter`, `_resolve_recorded_merge_tip`, `_resume_merge_scope_binding`, `_retain_or_advance_merge_candidate`, `_run_classification`, `_run_halt`, `_serialize_worktree_command`, `_stage_paths`, `_success`, `_transition_state`, `_unlink_merge_scope_temporary_at`, `_validate_merge_claim_record`, `_validate_revision9_cross_options`, `_verify_operator_harness`, `_void_mismatched_gate_one_pair`, `_write_artifact`, `_write_merge_artifact`, `abort_disposition_refusal`, `bind_merge_candidate_generation`, `build_parser`, `chain_id_now`, `commit_message_bytes`, `inspect_common_lock`, `iter_verified_master_package_windows`, `promoted_tier`, `render`, `scan_added_secrets`

Rule: `__init__.py` re-exports ALL 222 moved top-level symbols (191 in `__all__` + 31 not) (`from forge_cli.engine.<owner> import <name> as <name>`), including the ones NOT in `__all__` that are read by attribute (a module attribute read bypasses `__all__`): the 31 names `ProducedCommitContext`, `_FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS`, `_FreshEvalArtifactIO`, `_FreshEvalControlAbort`, `_assert_review_master_stable`, `_candidate_patch_ref`, `_candidate_review_diff`, `_candidate_snapshot`, `_commit_start_binding_refusal`, `_fresh_eval_evaluation`, `_fresh_eval_invalid_refusal`, `_fresh_eval_request_for_step`, `_fresh_eval_requests`, `_fresh_reviewer_block_claimed`, `_fresh_reviewer_evidence_package`, `_fresh_reviewer_pass_claimed`, `_iter_verified_master_package_windows`, `_passed_stack_cell_is_intermediate`, `_produced_exact_message`, `_produced_exact_tree`, `_produced_head_moved`, `_produced_mismatch_outcome`, `_produced_single_parent`, `_read_review_master_digest`, `_record_fresh_eval_terminal`, `_record_produced_identity`, `_review_complete_package_refusal`, `_review_master_identity`, `_review_master_leaf_is_valid`, `_review_master_pointer_prompt`, `_validated_fresh_reviewer_manifest` (evidence: `_record_produced_identity`, `_passed_stack_cell_is_intermediate`, `_mechanical_complete`, `_review_package_is_oversized` are patched by tests though absent from `__all__`; `patch_engine` refuses names the root does not bind). `__all__` is not extended.

## Risks the reviewer must check

1. **Patch targets (resolved at the test layer in step E0, no per-wave retargeting).** 28 names are patched on the engine module at ~70 sites (list in step E0). After the split the caller of a patched name lives in a submodule that binds the name by `from ... import`, so a root-only `patch.object(ENGINE, ...)` would silently stop intercepting. `patch_engine` (mirror of `patch_chain_core`, commit 6502849) patches the root and every submodule binding the name. Reviewer: (a) after every wave, grep for `patch.object(ENGINE` / `patch("forge_cli.engine.` outside the helper and fail it (the extended `_moved_shim_patch_offenders` sweep does this); (b) the helper is a restoring context manager; (c) `runtime.*` seams (`runtime._build_chain_journal_records`, `CODEX_EXECUTABLE`-style controls that already live on `forge_cli.runtime`) are untouched; (d) `REVIEW_MASTER_WINDOW_BYTES` is patched by 5 tests and read by 4 functions in `_review_transport` + `Engine`: all must see the patched value (the helper covers it because each binding file imports the name).
2. **The ONE body edit (step E1) and the `__file__` depth.** `_merge_bootstrap_child_argv` re-execs `scripts/forge/cli.py` (the FR-221-pinned entry point) by `Path(__file__).resolve().parents[1]`; from any file under `engine/` that is `forge_cli/cli.py` (does not exist) and the merge bootstrap child would fail at `spec_from_file_location`. `Path(runtime.__file__).resolve().parents[1]` is the same directory (`runtime.py` sits in `forge_cli/`, one level below `scripts/forge/`), so E1 is value-identical today, depth-independent after E2, and unaffected by the fixtures that patch `runtime.SCRIPT_DIR` (a `runtime.SCRIPT_DIR`-based target was tried first and broke `test_cli_merge_adapters`). Reviewer: the E1 diff is exactly one expression plus its comment plus one new test; the body snapshot for the oracle is taken AFTER E1; `snapshot_bodies.py` shows byte-identical bodies for every later wave. Rejected alternative: a flat sibling layout (`forge_cli/_engine_*.py`) avoids E1 but still moves the trigger-guarded code out of `engine.py` (Risk 7) and pollutes `forge_cli/`.
3. **Import-time side effects, exactly once.** The only module-level statement that is not a def/assignment is line 1786 `runtime._build_chain_journal_records = _build_chain_journal_records` (with its two comment lines). It moves verbatim into `_journal.py` after the `def`, and `engine/__init__.py` imports `_journal` (via the re-export), so the seam is bound when `forge_cli.engine` is imported — exactly as the docstring and spec line 117 promise ("binds the journal-record builder onto the runtime seam at import"). Locks and compiled regexes (`_CHAIN_CAPABILITY_LOCK`, `PLACEHOLDER_RE` -> `_state`; `_ARCHIVE_MODULE_LOCK` -> `_archive`) are created once. Reviewer: `python -c 'import forge_cli.engine, forge_cli.runtime as r; assert r._build_chain_journal_records is forge_cli.engine._build_chain_journal_records'`; `tests/test_revision9_coordination.py` and the journal tests pass unchanged.
4. **File-size budget / baseline (orchestrator-only).** Expected OVER BUDGET new file: `engine/_engine.py` (~3,560 code lines; `Engine` is one class, 41 methods). `engine/__init__.py` is over budget from E2 until wave 5 (re-keyed baseline entry, shrinking every wave) and ~420 after the finalize wave. `_journal.py` (~455 with header) and `_core.py` (~400) are the closest to the line; their fallback seams are named. Extractors must NOT edit `.refactor-baseline.json`; the orchestrator records `_engine.py` once, in the finalize wave, under explicit operator direction, and the reviewer confirms no body was edited to fit.
5. **Cycle resolution is `TYPE_CHECKING`-only (two guarded files).** The single SCC closes through the `FinalizeContext.engine: Engine` annotation; in addition three quoted `"Engine"` annotations sit in `_command_lock` symbols (`_peek_selected_chain` 4362, `_command_run_lock_id` 4383, `wrapped(self: "Engine", ...)` 4515) — strings the inventory does not record, but F821 for ruff (not in the copied per-file-ignores) and a new undefined-name key for mypy without a binding. `_finalize.py` (wave 4) and `_command_lock.py` (wave 2) each get `if TYPE_CHECKING: from forge_cli.engine._engine import Engine`; nothing else in the package imports `_engine`. Reviewer: `grep -n '"Engine"' scripts/forge/forge_cli/engine.py` (before E2) returns exactly the three lines above, all in the command-lock cluster; `grep -rn "from forge_cli.engine._engine" scripts/forge/forge_cli/engine/` shows only `__init__.py` and the two guarded lines (`_finalize.py`, `_command_lock.py`); `ruff check scripts/forge/forge_cli/engine/` reports no F821; the new import-linter contract has `exclude_type_checking_imports = true`; `lint-imports` passes; `dataclasses.fields(FinalizeContext)[0].type == "Engine"` (a string, never evaluated).
6. **`global` state and attribute parity.** `_archive_module` rebinds `_ARCHIVE_MODULE` through `global` in `_archive.py`; the root re-export `forge_cli.engine._ARCHIVE_MODULE` is a snapshot (`None`) — nothing in the repo reads it, but any future test that asserts the cache through the root will be wrong; document it in the `__init__` docstring. After the finalize wave `set(n for n in dir(forge_cli.engine) if not n.startswith('__'))` must be a superset of the 223 original top-level names; `scripts/forge/cli.py` needs no change; spec line 117 says the split changes no verb, diagnostic, reason code, `--help` byte, or corpus: run the FR-223 corpora and `tests.test_repo_conformance`.
7. **Reviewer-facing eval trigger path (control-class) — OPERATOR DECISION between Option A and Option B; the plan does not pick.** `scripts/forge/forge_cli/engine.py` is a literal in the `reviewer-routing` and `model-provider-version` rows of the fixed reviewer-facing eval trigger table. The table is one canonical constant (`policy.py:63` `REVIEWER_EVAL_TRIGGER_TABLE`; lines 71 and 75 carry the literal) and `_parse_reviewer_eval_triggers` (`policy.py:369`) accepts a project's region only when byte-for-byte equal to it (spec line 283), so every copy changes in the same candidate. Sites: spec `docs/specs/forge-plugin-spec.md:278,280` (rows) and `:285` (prose naming `engine.py` as the chain-owned launcher adapter); `scripts/forge/forge_cli/policy.py:71,75`; rendered/installed copies `forge-project.md:350,352`, `system/template/forge-project.md:244,246`, `AGENTS.md:368,370`; verbatim fixture copies `tests/test_cli_chain.py:145,147`, `tests/test_cli_chain_finalize.py:90,92`, `tests/test_cli_policy_fences.py:80,82`, `tests/test_drift_check.py:29,31`; path-list/expectation fixtures `tests/test_fresh_eval_policy.py:255,288-289,321-322`; target paths the test creates and expects to trigger, `tests/test_cli_chain.py:709,773`. Keyed to the same path but not part of the table: `.forge/evals/tasks/fr230-phase3-4-v2.manifest.json:99` (FR-230 production subject, re-minted with `mint.py` in the finalize wave under either option) and `.refactor-baseline.json:19` / `pyproject.toml:110` (E2). After E2 the file no longer exists, so a change to `Engine.review_request`, `REVIEW_LAUNCHER_CODE` or `_fresh_eval_*` under `engine/` would no longer fire those triggers — a silent weakening wherever a gate evaluates the table.

   **Option A — land the trigger change first (before E2), so both paths are named and there is no window.** One gated-approval chain on `main`, run by the forge session through the Forge commit chain (the refactor session never commits to `main` and Forge is disabled on `refactor/split-engine`, operating note 2026-09-13); then rebase `refactor/split-engine` onto that `main` tip. E0 and E1 may precede the rebase; E2 may not. Steps:
   1. `docs/specs/forge-plugin-spec.md` lines 278 and 280: change each row's cell tail `scripts/forge/forge_cli/engine.py |` to `scripts/forge/forge_cli/engine.py, scripts/forge/forge_cli/engine/** |`; line 285: extend the sentence so it names `scripts/forge/forge_cli/engine.py` "and, once split, the `scripts/forge/forge_cli/engine/` package" as the chain-owned launcher adapter named by the fixed table.
   2. `scripts/forge/forge_cli/policy.py` lines 71 and 75: the same cell tail inside the `REVIEWER_EVAL_TRIGGER_TABLE` string fragments (keep the `|\n` layout; the constant must stay byte-equal to the spec rows).
   3. Same two rows in `forge-project.md:350,352`, `system/template/forge-project.md:244,246`, `AGENTS.md:368,370`.
   4. Fixtures that pin the table byte-for-byte, same two rows: `tests/test_cli_chain.py:145,147`, `tests/test_cli_chain_finalize.py:90,92`, `tests/test_cli_policy_fences.py:80,82`, `tests/test_drift_check.py:29,31`. `tests/test_fresh_eval_policy.py`: keep the `engine.py` cases at 255, 288-289, 321-322 (still true while both paths are named) and add `scripts/forge/forge_cli/engine/_engine.py` to the path list at 255 plus one expectation tuple per control (`reviewer-routing`, `model-provider-version`) matched through the `scripts/forge/forge_cli/engine/**` pattern. `tests/test_cli_chain.py:709,773` stay (the file still exists).
   5. `CHANGELOG.md` `[Unreleased]` entry; a bead for the change (blocked-by relation to the split bead's E2 step).
   6. Chain class and triggers: gated-approval on `main`; `docs/specs/**` -> STRICT evals + binding review + explicit operator approval bound to the reviewed candidate; `forge-project.md` -> policy/parser contract tests + binding review; `scripts/forge/**` -> focused tests (`tests.test_fresh_eval_policy`, `tests.test_cli_policy_fences`, `tests.test_drift_check`, `tests.test_commit_and_region_template`, `tests.test_cli_chain`, `tests.test_cli_chain_finalize`, `tests.test_docs_contract`, `tests.test_installer`, `tests.test_plugin_load`, `tests.test_repo_conformance`) + full gate-1 discovery. The `reviewer-routing` and `model-provider-version` STRICT evals fire on this candidate itself (it touches the spec and the table).
   7. Acceptance before E2, on the rebased branch: `git merge-base --is-ancestor <trigger-commit> HEAD` succeeds, and `PYTHONPATH=scripts/forge python3 -c 'from forge_cli.policy import REVIEWER_EVAL_TRIGGER_TABLE as T, _parse_reviewer_eval_triggers as p; t = dict(p(T)); assert "scripts/forge/forge_cli/engine/**" in t["reviewer-routing"] and "scripts/forge/forge_cli/engine/**" in t["model-provider-version"]'` passes.
   8. Finalize wave (wave 6) then removes the old literal: delete `scripts/forge/forge_cli/engine.py, ` from both rows in the same nine table-carrying files (spec 278/280, policy 71/75, `forge-project.md`, template, `AGENTS.md`, the four verbatim fixtures), rewrite spec line 285 to name only the package, retarget `tests/test_fresh_eval_policy.py` 255/288-289/321-322 and `tests/test_cli_chain.py` 709/773 to `scripts/forge/forge_cli/engine/_engine.py`, re-mint the FR-230 manifest (line 99). Every commit on `main` then names a path that exists at that commit; there is no window.

   **Option B — accept the window.** Nothing changes before E2; the finalize wave (wave 6) makes the whole trigger change in the reintegration candidate (Option A steps 1-4 with `scripts/forge/forge_cli/engine/**` replacing the literal outright, step 5, and the step-8 retargets). Why the window has no effect on the branch: Forge is disabled for this repository on the refactor branch by operator direction (2026-09-13, beads memory `refactor-session-operating-notes-2026-09-13`; `.claude/settings.local.json` sets `"forge@forge": false`), the branch takes plain git commits with no commit or merge chain, so between E2 and reintegration no gate evaluates `REVIEWER_EVAL_TRIGGER_TABLE` against any candidate and there is no eval the dormant literal could suppress; `main` keeps `engine.py` and its unchanged table until the reintegration lands, so `main` is never weakened; the window is opened and closed by the same candidate on `main`. What the reintegration chain (forge session; gated-approval; binding review + explicit operator approval; STRICT evals) must verify: (a) `git diff --name-status <main-tip>..<branch-tip>` contains `D scripts/forge/forge_cli/engine.py` — the deletion touches the literal still named by `main`'s table, so the `reviewer-routing` and `model-provider-version` STRICT evals fire on the reintegration candidate itself; the reviewer confirms in the chain record that both ran and passed; (b) the candidate's spec (278/280/285), `policy.py` (71/75), `forge-project.md`, `system/template/forge-project.md`, `AGENTS.md` and the four verbatim fixtures all carry `scripts/forge/forge_cli/engine/**` and none carries `scripts/forge/forge_cli/engine.py` (grep the nine table-carrying files plus `tests/test_fresh_eval_policy.py` and `tests/test_cli_chain.py` at the candidate tree: zero hits), `tests/test_fresh_eval_policy.py` and `tests/test_cli_chain.py` 709/773 are retargeted, and the FR-230 manifest is re-minted in the same candidate; (c) the Option A step-7 one-liner passes at the candidate tree and `tests.test_fresh_eval_policy`, `test_cli_policy_fences`, `test_cli_chain`, `test_cli_chain_finalize`, `test_drift_check`, `test_commit_and_region_template`, `test_docs_contract`, `test_installer`, `test_plugin_load`, `test_repo_conformance`, `test_fr230_phase3_manifest`, `test_fr223_v2_byte_pins` pass; (d) the finalized tree is fully gated: every file under `scripts/forge/forge_cli/engine/` (including `_engine.py`, `_review_transport.py`, `_fresh_eval*.py`, `_state.py` with `REVIEW_LAUNCHER_CODE`) matches `scripts/forge/forge_cli/engine/**` for both controls, so no engine surface sits outside the triggers after reintegration.

   Under either option the reviewer checks that `policy.py`'s table, the spec rows, the rendered copies and every fixture change in ONE candidate (byte equality is the acceptance rule), and that `python3 -m unittest tests.test_repo_conformance` passes.
8. **Decorator at class-body time.** `Engine` applies `@_serialize_worktree_command` to 14 methods; `_command_lock.py` (wave 2) must be importable before `_engine.py` executes — guaranteed by the wave order, but a wave-5 extractor that forgets the import gets a `NameError` at import, not at call. Reviewer: `python -c 'import forge_cli.engine'` in the wave-5 gate.
9. **`__init__` imports `chain_core`/`runtime` twice today** (lines 18/34 and 30/35, F811 grandfathered). Each target imports them once; the `__init__` header keeps only what the re-exports need. Reviewer: no unused import is re-bound on the root (the `engine.py` per-file-ignores entry, including F811, is deleted in the finalize wave and must not be needed by the package).
10. **Wave count and merge discipline.** Six extraction waves are dependency-forced (0: `_state`; 1: `_core`; 2: 17 parallel leaves; 3: 6; 4: 2; 5: `Engine`), then the finalize wave (6). Waves 0 and 1 are single clusters and are listed as separate entries in `plan-engine.json` so no driver runs `_core` beside `_state`. Do not merge multi-cluster waves: a target in wave N imports only wave < N modules, which is what keeps every extractor's diff free of judgment calls. Wave 2's 17 clusters may be batched into fewer worktrees in any grouping (they are mutually independent), but each cluster remains one commit.

## Follow-up (separate beads, not this split)

- Delete `_CHAIN_CAPABILITY_LOCK` and `_CHAIN_CAPABILITIES` from `_state.py` and `__all__` (dead; spec note).
- Split `Engine` (3,544 code lines) into verb mixins (`_ChainVerbs`, `_ReviewVerbs`, `_FinalizeVerbs`, ...) composed into `Engine`; a class-structure change with its own tests and review.
- Narrow the per-module ruff ignores for `engine/*.py` further as modules are cleaned.
