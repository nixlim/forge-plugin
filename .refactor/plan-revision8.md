# Decompose plan: `Revision8CoordinationTests` in `tests/test_revision8_coordination.py` (test class: mixin + class shape) — revision 2

Revised at branch `refactor/split-test-revision8-coordination` tip `4d4d7c9` (BASE main `69bc28d`) after `.refactor/critique-revision8.md` (VERDICT: REVISE; findings 1, 3, 4, 5, 6 and the advisories applied; the partition, names, classes and ID maps are unchanged — the critic verified them 81/81, injective, no collisions). Plugin refactor-python 0.1.3. Inputs: `.refactor/inventory-revision8-1.json` (regenerated against the current source after `42980e7`; 112 methods = 81 `test_*` + 31 helpers; 109 ok, 3 wrap; `prerequisites: []`; the first inventory `.refactor/inventory-revision8.json` was pre-constants and every span was +2/+3 — critique finding 1), the verified mixin dry run `.refactor/dryrun-revision8-mixin.txt`, the ID freeze `.refactor/tests-revision8-before.json` (81 IDs per collector for this class; `preset: auto` resolving to the namespace spellings), the constants prep `42980e7`, the ruff-glob prep `c8cf01a`, the driver `.refactor/revision8-run-cluster.py`. No file outside `.refactor/` was written; no `--apply` was run. Machine twin: `.refactor/plan-revision8.json`; ID maps: `.refactor/idmap-revision8-<family>.json` (7 files, 81 entries per collector).

## 0. STOP / operator decisions (read first)

**The session STOPS before commit 1.** The orchestrator has ruled that a repository-wide isort setting is outside the brief's enumerated config prep (per-file-ignore globs and baseline entries), so item 1 below is an operator decision, not a session decision; nothing is committed beyond this plan until it is taken. Items 2 and 3 are resolved in-brief and need no input. The partition is complete and checked (§2), no class-shape refusal is expected (§6), and every planned module lands in the 500..1,000 band (max 819).

### 0.1 Decision record for the operator — generated headers import `codex_orchestrator` before the `tests.*` block

**Defect (measured, reproduced independently by the critic).** The mover's mandatory `--format-imports` is `ruff check --select I --fix` (move_methods.py:244-254) under the committed `pyproject.toml`, where `codex_orchestrator` (a `scripts/`-resident top-level module, unresolvable under `src = ['.']`) sorts as third-party and therefore *above* the first-party `tests.*` block. The verified mixin header (`.refactor/dryrun-revision8-mixin.txt` lines 599..616) already shows it: `from codex_orchestrator import batch, journal` then `from tests._revision8_constants import RECORDED_AT, TOOLS`. Every family header gets the same order. Consequences:

- `env -u PYTHONPATH python3 -c 'from codex_orchestrator import journal'` (repo root) -> `ModuleNotFoundError`; with `import tests._revision8_constants` first -> ok. The constants module's `sys.path.insert` is what resolves it, and in the generated order it runs too late.
- `tests/_revision8_support.py` is itself unimportable standalone without `PYTHONPATH`; C1's gate does not catch it because the *source* imports constants (line 18) before support (line 19).
- `orphan_identity` — first in the commit order — reads no constant (`globals = {journal, json, mock, os, threading}`), so its header has **no** `tests._revision8_constants` import at all; its only route to `scripts/` on `sys.path` is transitive through the mixin, which has the defect. C3's gate is where the wave would stop.
- Gate 1 shard simulation (host `cpu_count` 12 -> 4 shards, round-robin over sorted `tests/test_*.py` stems, each shard's modules imported in order without `PYTHONPATH`, module level only, then `import codex_orchestrator`):

  ```
  A) after the split, source file KEPT (75 modules):
     shard 1: RESOLVES  (first family orphan_identity, 14 modules of prefix)
     shard 2: FAILS     (first family append_schema,   13 modules of prefix)
     shard 3: RESOLVES  (first family registry_races,  14 modules of prefix; holds the source)
     shard 4: FAILS     (first family interruptions,   13 modules of prefix)
  B) source file DELETED at finalize (74 modules):
     shard 1: RESOLVES  (first family precedence)
     shard 2: FAILS     (first family append_schema)
     shard 3: FAILS     (first family interruptions)
     shard 4: FAILS     (first family orphan_identity)
  ```

  Shards that resolve do so by accident (an unrelated earlier module in the bucket inserts `scripts`); any added or removed test module reshuffles the buckets.
- `PYTHONPATH=scripts:scripts/forge` exists only in this worktree's machine-local `.claude/settings.local.json`; CI runs the Gate 1 cell (`.github/workflows/forge-ci.yml:27-52`) with **no** `PYTHONPATH` (its `sys.path.insert` is in-process in the driver and does not reach the subprocess); the only CI `PYTHONPATH` is `guardrails.yml:24`, scoped to `lint-imports`.

**Options (all side effects measured with ruff 0.16.7 over `scripts tests system/fr223`; header orders verified on stdin copies, no file written):**

| option | change | new findings repo-wide | header order produced | status |
|---|---|---|---|---|
| A | `[tool.ruff.lint.isort] known-local-folder = ["codex_orchestrator"]` | **1** — `I001` at `tests/test_commitment_paths.py:20` (fix = one blank line inserted at 21) | `tests.*` then `codex_orchestrator` (mixin and families) | needs an edit to a test outside the target and its siblings (brief §8 item 4) |
| A' | A + `no-lines-before = ["local-folder"]` | **1** — identical finding, identical fix | same | same objection |
| A'' | custom section `sections = {orch = ["codex_orchestrator"]}` + `section-order = [..., "first-party", "orch", "local-folder"]` | **1** — identical finding | same | same objection |
| **A'''** | `known-local-folder = ["codex_orchestrator", "commitment_paths"]` | **0** — `All checks passed!` | mixin: `from tests._revision8_constants import RECORDED_AT, TOOLS` then `from codex_orchestrator import batch, journal`; family: `from tests._cli_loader / tests._revision8_*` then `from codex_orchestrator import journal` | config-only, `pyproject.toml` only, edits no test and no production file; `pyproject.toml` is `config`, not `control`, in `forge-project.md`; a repo-wide isort setting is outside the brief's enumeration — **operator's call** |
| B | plugin: the mover carries the source's `sys.path.insert` preamble and `# noqa: E402` pattern into the destination | n/a | correct by construction | out of scope tonight; bead in the refactor-python repo; stops the wave |
| C | rely on `PYTHONPATH` | n/a | unchanged (defective) | refuted: shard simulation above and CI `forge-ci.yml` running the Gate 1 cell without `PYTHONPATH` |
| D | `tests/_revision8_constants.py` re-exports `batch`/`journal` after its `sys.path.insert`, so the mover copies `from tests._revision8_constants import journal` and the order becomes irrelevant | n/a | correct by construction | needs the hand-written constants commit `42980e7` amended **and** a hand edit of the source's import line (brief §8 item 4 twice); cleaner long-term shape, not tonight |

**Whichever option the operator picks, the config commit MUST precede C1** so the mixin header is generated under it (otherwise C1 must be reverted and re-run), and the C1 dry run must be re-run under it with the same argv (the evidence file is regenerated; the manifest oracle's `normalise_header` sorts the flattened imports, so the verdict and manifest are unchanged). The config commit is gated on both `verify.sh`'s `ruff check tests` and CLAUDE.md's finish command `ruff check scripts tests system/fr223 && git ls-files -z "*.py" | xargs -0 python3 scripts/check_file_length.py && PYTHONPATH=scripts:scripts/forge lint-imports`, since it is the one commit whose blast radius is the whole repository. What makes it legal is that **no test outside the target file and its new siblings is edited** (A''' only). Disclose it in the handover and to both reviewers as a fourth measured deviation alongside brief §11's three.

### 0.2 Provisional `.refactor-baseline.json` entries (resolved in-brief)

Eight modules exceed 500 by construction: the mixin (539, measured from the dry run) and all seven families. C2 commits the **true + 20 upper bounds** below (method code lines over the regenerated inventory's spans, `check_file_length.code_lines` rule, plus the 20-line header allowance). A low entry fails every family gate at `verify.sh`'s file-length step (`grandfathered at N ... but grew to M`); a high one is inert until finalize replaces it with the measured size. The pre-commit hook honours `REFACTOR_MAX_LINES=1000` from the lane env, so C1 passes locally before C2; CI's guardrails job uses the 500 default plus the baseline, so all eight entries must exist before reintegration. C2 goes after C1 and before C3 (brief §4 item 1).

### 0.3 Source shell (resolved in-brief: **keep it**)

After C9 the source keeps `class Revision8CoordinationTests(Revision8Support, unittest.TestCase):` with its docstring only (`retained or [pass]`, move_methods.py:402), its remaining imports, `sys.path.insert`, and `if __name__ == "__main__"`. It collects cleanly (`Ran 0 tests`, exit 0; pytest `no tests ran`, no warning). Deleting the module is refuted by shard table B above: it re-partitions the Gate 1 buckets and three of four shards then fail the bare-`PYTHONPATH` import unless the isort fix has landed. Deletion remains an operator call, recorded at handover as a follow-up; `.refactor-baseline.json:56` (4905; the file is 4903 now — inert, growth-only guard) and `pyproject.toml:242` are dropped at finalize either way.

### 0.4 Family count is seven (brief: "expect 5 to 7")

Every family is a scenario the class docstring names (append, orphan, identity, successor-DAG) or an adjacent contract block (precedence/literals, rollback, registry races, interruptions). `interruptions` has 3 tests but 556 code lines (185/205/166 each, §7): no seam under 500 keeps two together. No family is under 500.

## 1. Delete first (dead code, with evidence)

None. `vulture` is not installed; every one of the 31 helpers appears in `calls` of at least one test or helper (from `edges`); dead-code deletion is not a test-shape move.

## 2. Summary

| item | value |
|---|---|
| baseline | `69bc28d` (= `main`); prep `c8cf01a` (ruff globs), `42980e7` (constants module, hand-written); evidence `d4c9b36`, `79795b2`, `9c465ca`, `0c05015`, `4d4d7c9` |
| source | `tests/test_revision8_coordination.py`: **4,903** code lines (grandfathered at 4905), 5,251 lines; class at line 26, `setUp` at 29; `__main__` at 5250 |
| class | `Revision8CoordinationTests(unittest.TestCase)`, 112 methods = 31 helpers + 81 tests; 109 ok, 3 wrap (`runs_root`, `registry_path` properties; `api_environment` contextmanager — helpers, all in the mixin); 0 unsupported; class body = docstring only; no metaclass, slots, or decorators on tests |
| prerequisites | `[]` in the regenerated inventory (`TOOLS`, `RECORDED_AT` relocated by `42980e7`; the source keeps `ROOT` for its own `sys.path.insert`) |
| hubs (post-peel, inventory-revision8-1) | `open_run`, `run_dir`, `api_environment`, `coordination_snapshot`, `opening_record`, `journal_path` (+ `@state:` assert/repo/subTest) — all helpers, all in the mixin |
| clusters | 19 after peeling; test membership 43 / 13 / 14 / 4 + 7 singletons — the 43-test cluster is split by scenario (§3) |
| result | **C-config (operator) + C1 mixin + C2 baseline + C3..C9 families**; 81/81 tests move; source shell kept |
| sizes | mixin **539** (measured); families **724 / 617 / 593 / 628 / 576 / 819 / 540** (true method lines + 20); **0 over 1,000; 8 over 500** |
| test-ID gates | C1 `--test-mode identity`; each family `--test-mode mapping` with `.refactor/idmap-revision8-<family>.json` |
| refusals | none expected (§6); class-shape dry runs are refused by design until C1 is merged |
| census | `census_complete=false`, 0 sites. Reproduced in this worktree: `grep -rln Revision8CoordinationTests . --exclude-dir=.git` -> only the source and `.refactor/*` artifacts: **0 code sites, 0 docs hits**; the file name is named only by the config lines `pyproject.toml:242` and `.refactor-baseline.json:56` (both dropped at finalize) and, as historical prose recording past sizes/commands, by `docs/analysis/*.md` (3 files) and `.forge/history/runs/run-20260826-coordination-hardening.md` — nothing to repoint |

**Partition check (mechanical, over `inventory-revision8-1.json`; reproduced verbatim):**

```
PARTITION CHECK (inventory-revision8-1.json): inventory tests=81 placed=81 unique=81 duplicates=[] missing=[] extra=[] sum_code_lines=4357
```

4,357 = the 81 tests' code lines; with the helpers' 521 (+3 decorator lines the inventory spans exclude = 524, the mixin dry run's body count) and the 25-line header, that is the 4,903-line source. Header overhead is assumed at **20** code lines per family (upper estimate): the measured mixin header is 15 through its class line; a family header is `from __future__ import annotations`, the 4..9 stdlib imports the family owns (§3), `from codex_orchestrator import journal`, `from tests._revision8_constants import ...` (where read), `from tests._revision8_support import Revision8Support`, and the class line; the sibling body is built from the moved methods only (move_methods.py:406), so no docstring is copied.

## 3. Target modules

| # | family | module | class | tests | method code lines | upper bound (+20) = baseline entry | helpers used |
|---|---|---|---|---|---|---|---|
| f1 | `append_schema` | `tests/test_revision8_append_schema.py` | `Revision8AppendSchemaTests` | 10 | 704 | **724** | 17 |
| f2 | `precedence` | `tests/test_revision8_precedence.py` | `Revision8PrecedenceTests` | 16 | 597 | **617** | 18 |
| f3 | `rollback` | `tests/test_revision8_rollback.py` | `Revision8RollbackTests` | 9 | 573 | **593** | 11 |
| f4 | `registry_races` | `tests/test_revision8_registry_races.py` | `Revision8RegistryRacesTests` | 12 | 608 | **628** | 11 |
| f5 | `interruptions` | `tests/test_revision8_interruptions.py` | `Revision8InterruptionsTests` | 3 | 556 | **576** | 10 |
| f6 | `orphan_identity` | `tests/test_revision8_orphan_identity.py` | `Revision8OrphanIdentityTests` | 17 | 799 | **819** | 14 |
| f7 | `successors` | `tests/test_revision8_successors.py` | `Revision8SuccessorsTests` | 14 | 520 | **540** | 16 |

Class names: `grep -rn '^class .*Tests' tests/` finds no `Revision8*` class other than the source class; none of the seven names or eight module paths exists under `tests/`. All seven end in `Tests`; `Revision8Support` matches neither collector's class pattern and `_revision8_support.py` matches neither file pattern.

### f1 — `append_schema` -> `tests/test_revision8_append_schema.py` / `Revision8AppendSchemaTests`

- scenario: Record append schema: the seven strict record types, per-type first-required-field diagnostics, FR-019 candidate boundaries (strings, enums, arrays, nested, inheritance/handoff/extensions), first-failure examples and the envelope literal, array-index and sparse-history append refusals.
- tests (10, ascending source order, current-file `line..end_line` (code lines)): `test_all_seven_strict_minimum_record_types_append` 588..623 (34), `test_per_type_first_required_field_diagnostics_are_exact` 625..684 (59), `test_fr019_common_and_required_string_boundaries` 686..828 (142), `test_fr019_format_enum_repository_and_scope_boundaries` 830..955 (123), `test_fr019_all_arrays_and_nested_validation_boundaries` 957..1075 (117), `test_fr019_inheritance_events_handoff_optionals_and_extensions` 1077..1194 (113), `test_first_failure_examples_and_envelope_literal_are_exact` 1196..1230 (34), `test_array_members_fail_at_the_first_ascending_index` 1232..1251 (18), `test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes` 1253..1282 (29), `test_sparse_history_reads_unchanged_but_same_new_shape_refuses` 1284..1321 (35)
- helpers used (inventory `calls` ∩ helpers, all inherited from `Revision8Support`): `append_record`, `assert_invalid_candidate`, `assert_valid_candidate`, `close`, `closure_record`, `coordination_snapshot`, `create_citation_files`, `decision_record`, `execution_record`, `execution_result_record`, `journal_path`, `open_run`, `opening_record`, `run_dir`, `task_record`, `valid_candidate`, `verification_record`
- module globals the methods read (the mover copies these imports): `RECORDED_AT`, `journal`, `json`, `mock`
- size: **724** upper bound = 704 (methods, true) + 20 (header); this is the C2 baseline entry
- fallback seam (if the measured size lands over the ceiling): split into `append` (590..1323 minus the four fr019 tests: 6 tests, 203 lines) and `candidates` (the four test_fr019_* tests, 688..1196: 491 lines) — the fr019 tests use only valid_candidate/assert_*_candidate.
- dry run (from the merged head after C1 and C2; `--test-snapshot` = the ID snapshot re-collected at that head — identity-equal to `.refactor/tests-revision8-before.json` until the first family lands; the driver regenerates the id map and refuses a mismatch with the pre-written file):
  ```
  TMPDIR=/dev/shm/refactor-s8 python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision8_coordination.py --class Revision8CoordinationTests --methods test_all_seven_strict_minimum_record_types_append,test_per_type_first_required_field_diagnostics_are_exact,test_fr019_common_and_required_string_boundaries,test_fr019_format_enum_repository_and_scope_boundaries,test_fr019_all_arrays_and_nested_validation_boundaries,test_fr019_inheritance_events_handoff_optionals_and_extensions,test_first_failure_examples_and_envelope_literal_are_exact,test_array_members_fail_at_the_first_ascending_index,test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes,test_sparse_history_reads_unchanged_but_same_new_shape_refuses --dest tests/test_revision8_append_schema.py --shape class --target-class Revision8AppendSchemaTests --test-only --test-snapshot <ids-snapshot-at-merged-head> --id-map .refactor/idmap-revision8-append_schema.json --format-imports --manifest .refactor/family-revision8-append_schema.json
  ```
- apply: same argv + `--apply`
- gate (matches `.refactor/revision8-run-cluster.py:191-215` exactly): `bash $S/verify.sh --pkg tests --snapshot <body-snapshot-at-merged-head> --manifest .refactor/family-revision8-append_schema.json --strict-bodies --test-snapshot <ids-snapshot-at-merged-head> --test-mode mapping` (no `--fast`; `GATE: PASS` required), then `python3 scripts/check_file_length.py tests`, then the bare-`PYTHONPATH` proofs `env -u PYTHONPATH python3 -m unittest tests.test_revision8_append_schema` and `env -u PYTHONPATH python3 -c 'import tests.test_revision8_append_schema'` (standalone import, i.e. first in a Gate 1 shard)
- id map: `.refactor/idmap-revision8-append_schema.json` (10 entries per collector). Example: unittest `test_revision8_coordination.Revision8CoordinationTests.test_all_seven_strict_minimum_record_types_append` -> `test_revision8_append_schema.Revision8AppendSchemaTests.test_all_seven_strict_minimum_record_types_append`; pytest `tests/test_revision8_coordination.py::Revision8CoordinationTests::test_all_seven_strict_minimum_record_types_append` -> `tests/test_revision8_append_schema.py::Revision8AppendSchemaTests::test_all_seven_strict_minimum_record_types_append`
- commit: `refactor(tests): move the append schema scenarios of Revision8CoordinationTests to tests/test_revision8_append_schema.py (class shape)`

### f2 — `precedence` -> `tests/test_revision8_precedence.py` / `Revision8PrecedenceTests`

- scenario: Refusal precedence and exact literals: which check wins (candidate schema vs stale-owner takeover, foreign/engine-lifecycle owner classification vs schema, citation controls vs session identity), session-PID identity across shells, operation-specific invalid-id/missing-run/repository-unavailable/scope literals, lock/registry-update/rollback failure literals.
- tests (16, ascending source order, current-file `line..end_line` (code lines)): `test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes` 1323..1351 (27), `test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes` 1353..1377 (23), `test_foreign_owner_classification_precedes_candidate_schema` 1379..1398 (18), `test_engine_lifecycle_owner_classification_precedes_schema` 1400..1443 (43), `test_engine_lifecycle_envelope_is_built_before_session_identity` 1445..1493 (46), `test_citation_controls_precede_current_session_identity_refusals` 1495..1534 (39), `test_current_session_identity_literals_are_exact_and_nonmutating` 1536..1573 (38), `test_citation_controls_precede_recorded_owner_classification` 1575..1650 (75), `test_new_write_validator_control_is_load_bearing` 1652..1669 (16), `test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry` 1671..1697 (27), `test_invalid_session_pid_literal_is_retained` 1699..1709 (11), `test_live_session_identity_is_stable_across_fresh_cli_shells` 1711..1741 (29), `test_operation_specific_invalid_id_and_missing_run_literals` 1743..1775 (32), `test_operation_specific_repository_unavailable_literals` 1777..1853 (77), `test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct` 1855..1908 (50), `test_lock_registry_update_and_rollback_failure_literals_are_exact` 1910..1957 (46)
- helpers used (inventory `calls` ∩ helpers, all inherited from `Revision8Support`): `api_environment`, `append_record`, `close`, `closure_record`, `command`, `coordination_snapshot`, `decision_record`, `execution_record`, `journal_path`, `open_run`, `opening_record`, `prime_batch_lock`, `proven_dead_pid`, `readmit`, `retire`, `run_dir`, `verification_record`, `write_record`
- module globals the methods read (the mover copies these imports): `RECORDED_AT`, `copy`, `journal`, `json`, `mock`, `os`, `socket`, `sys`
- size: **617** upper bound = 597 (methods, true) + 20 (header); this is the C2 baseline entry
- fallback seam (if the measured size lands over the ceiling): split at the source seam 1652/1654: `owner_precedence` (1325..1652, 8 tests, 301 lines) and `session_literals` (1654..1959, 8 tests, 280 lines).
- dry run (from the merged head after C1 and C2; `--test-snapshot` = the ID snapshot re-collected at that head — identity-equal to `.refactor/tests-revision8-before.json` until the first family lands; the driver regenerates the id map and refuses a mismatch with the pre-written file):
  ```
  TMPDIR=/dev/shm/refactor-s8 python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision8_coordination.py --class Revision8CoordinationTests --methods test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes,test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes,test_foreign_owner_classification_precedes_candidate_schema,test_engine_lifecycle_owner_classification_precedes_schema,test_engine_lifecycle_envelope_is_built_before_session_identity,test_citation_controls_precede_current_session_identity_refusals,test_current_session_identity_literals_are_exact_and_nonmutating,test_citation_controls_precede_recorded_owner_classification,test_new_write_validator_control_is_load_bearing,test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry,test_invalid_session_pid_literal_is_retained,test_live_session_identity_is_stable_across_fresh_cli_shells,test_operation_specific_invalid_id_and_missing_run_literals,test_operation_specific_repository_unavailable_literals,test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct,test_lock_registry_update_and_rollback_failure_literals_are_exact --dest tests/test_revision8_precedence.py --shape class --target-class Revision8PrecedenceTests --test-only --test-snapshot <ids-snapshot-at-merged-head> --id-map .refactor/idmap-revision8-precedence.json --format-imports --manifest .refactor/family-revision8-precedence.json
  ```
- apply: same argv + `--apply`
- gate (matches `.refactor/revision8-run-cluster.py:191-215` exactly): `bash $S/verify.sh --pkg tests --snapshot <body-snapshot-at-merged-head> --manifest .refactor/family-revision8-precedence.json --strict-bodies --test-snapshot <ids-snapshot-at-merged-head> --test-mode mapping` (no `--fast`; `GATE: PASS` required), then `python3 scripts/check_file_length.py tests`, then the bare-`PYTHONPATH` proofs `env -u PYTHONPATH python3 -m unittest tests.test_revision8_precedence` and `env -u PYTHONPATH python3 -c 'import tests.test_revision8_precedence'` (standalone import, i.e. first in a Gate 1 shard)
- id map: `.refactor/idmap-revision8-precedence.json` (16 entries per collector). Example: unittest `test_revision8_coordination.Revision8CoordinationTests.test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes` -> `test_revision8_precedence.Revision8PrecedenceTests.test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes`; pytest `tests/test_revision8_coordination.py::Revision8CoordinationTests::test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes` -> `tests/test_revision8_precedence.py::Revision8PrecedenceTests::test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes`
- commit: `refactor(tests): move the precedence scenarios of Revision8CoordinationTests to tests/test_revision8_precedence.py (class shape)`

### f3 — `rollback` -> `tests/test_revision8_rollback.py` / `Revision8RollbackTests`

- scenario: Post-publication and stale-owner transaction rollback: append registry drift after fsync, post-publication faults restore every lifecycle transaction (existing and initially-absent registry), registry restoration failure retains the published run, canonical name stays present across link/exchange/unlink, stale-owner append/lifecycle failures restore owner and journal bytes, owner-restoration identity conflict preserves the foreign owner, restoration cleanup only after final proof.
- tests (9, ascending source order, current-file `line..end_line` (code lines)): `test_ordinary_append_registry_drift_after_fsync_rolls_back_append` 2028..2065 (35), `test_postpublication_fault_restores_every_lifecycle_transaction` 2231..2303 (69), `test_initially_absent_registry_is_removed_after_postpublication_fault` 2305..2339 (32), `test_registry_restoration_failure_retains_published_run_and_journal` 2341..2407 (63), `test_existing_registry_publication_keeps_canonical_name_present` 2409..2520 (107), `test_stale_owner_append_failure_restores_owner_and_journal` 2522..2576 (52), `test_stale_owner_lifecycle_failure_restores_all_transaction_bytes` 2578..2660 (79), `test_owner_restoration_identity_conflict_preserves_foreign_owner` 2662..2740 (75), `test_registry_restoration_cleanup_occurs_only_after_final_proof` 3835..3899 (61)
- helpers used (inventory `calls` ∩ helpers, all inherited from `Revision8Support`): `api_environment`, `closure_record`, `coordination_snapshot`, `decision_record`, `journal_path`, `open_run`, `opening_record`, `prime_batch_lock`, `prime_registry_lock`, `proven_dead_pid`, `run_dir`
- module globals the methods read (the mover copies these imports): `RECORDED_AT`, `journal`, `json`, `mock`, `os`, `socket`
- size: **593** upper bound = 573 (methods, true) + 20 (header); this is the C2 baseline entry
- fallback seam (if the measured size lands over the ceiling): split `stale_owner_rollback` (2524, 2580, 2664: 203 lines) from `publication_rollback` (the rest, 361 lines).
- dry run (from the merged head after C1 and C2; `--test-snapshot` = the ID snapshot re-collected at that head — identity-equal to `.refactor/tests-revision8-before.json` until the first family lands; the driver regenerates the id map and refuses a mismatch with the pre-written file):
  ```
  TMPDIR=/dev/shm/refactor-s8 python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision8_coordination.py --class Revision8CoordinationTests --methods test_ordinary_append_registry_drift_after_fsync_rolls_back_append,test_postpublication_fault_restores_every_lifecycle_transaction,test_initially_absent_registry_is_removed_after_postpublication_fault,test_registry_restoration_failure_retains_published_run_and_journal,test_existing_registry_publication_keeps_canonical_name_present,test_stale_owner_append_failure_restores_owner_and_journal,test_stale_owner_lifecycle_failure_restores_all_transaction_bytes,test_owner_restoration_identity_conflict_preserves_foreign_owner,test_registry_restoration_cleanup_occurs_only_after_final_proof --dest tests/test_revision8_rollback.py --shape class --target-class Revision8RollbackTests --test-only --test-snapshot <ids-snapshot-at-merged-head> --id-map .refactor/idmap-revision8-rollback.json --format-imports --manifest .refactor/family-revision8-rollback.json
  ```
- apply: same argv + `--apply`
- gate (matches `.refactor/revision8-run-cluster.py:191-215` exactly): `bash $S/verify.sh --pkg tests --snapshot <body-snapshot-at-merged-head> --manifest .refactor/family-revision8-rollback.json --strict-bodies --test-snapshot <ids-snapshot-at-merged-head> --test-mode mapping` (no `--fast`; `GATE: PASS` required), then `python3 scripts/check_file_length.py tests`, then the bare-`PYTHONPATH` proofs `env -u PYTHONPATH python3 -m unittest tests.test_revision8_rollback` and `env -u PYTHONPATH python3 -c 'import tests.test_revision8_rollback'` (standalone import, i.e. first in a Gate 1 shard)
- id map: `.refactor/idmap-revision8-rollback.json` (9 entries per collector). Example: unittest `test_revision8_coordination.Revision8CoordinationTests.test_ordinary_append_registry_drift_after_fsync_rolls_back_append` -> `test_revision8_rollback.Revision8RollbackTests.test_ordinary_append_registry_drift_after_fsync_rolls_back_append`; pytest `tests/test_revision8_coordination.py::Revision8CoordinationTests::test_ordinary_append_registry_drift_after_fsync_rolls_back_append` -> `tests/test_revision8_rollback.py::Revision8RollbackTests::test_ordinary_append_registry_drift_after_fsync_rolls_back_append`
- commit: `refactor(tests): move the rollback scenarios of Revision8CoordinationTests to tests/test_revision8_rollback.py (class shape)`

### f4 — `registry_races` -> `tests/test_revision8_registry_races.py` / `Revision8RegistryRacesTests`

- scenario: Registry node identity under hostile concurrent change: stat-to-open and parent/lock-epoch swaps stay generic, exchange and link races never clobber a foreign canonical, absent-registry node collisions (directory, symlink, broken symlink, unreadable file) preserve the foreign node, exact staged registry/owner prelinks are recognized, post-exchange foreign canonicals are preserved for registry and owner.
- tests (12, ascending source order, current-file `line..end_line` (code lines)): `test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating` 2074..2150 (74), `test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting` 2152..2229 (75), `test_registry_exchange_race_restores_foreign_canonical_without_publish` 2742..2808 (64), `test_absent_registry_link_race_never_clobbers_foreign_canonical` 2810..2872 (60), `test_absent_registry_directory_collision_preserves_foreign_node` 2874..2875 (2), `test_absent_registry_symlink_collision_preserves_foreign_node` 2877..2878 (2), `test_absent_registry_broken_symlink_collision_preserves_foreign_node` 2880..2883 (4), `test_absent_registry_unreadable_file_collision_preserves_foreign_node` 2885..2888 (4), `test_exact_staged_registry_prelink_is_recognized_as_published` 2890..2960 (68), `test_exact_staged_registry_prelink_rolls_back_after_validation_failure` 2962..3021 (57), `test_exact_staged_owner_prelink_is_recognized_as_adopted` 3023..3081 (56), `test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner` 3083..3231 (142)
- helpers used (inventory `calls` ∩ helpers, all inherited from `Revision8Support`): `api_environment`, `assert_absent_registry_node_collision`, `coordination_snapshot`, `decision_record`, `journal_path`, `open_run`, `opening_record`, `prime_batch_lock`, `prime_registry_lock`, `proven_dead_pid`, `run_dir`
- module globals the methods read (the mover copies these imports): `RECORDED_AT`, `journal`, `json`, `mock`, `os`, `socket`
- size: **628** upper bound = 608 (methods, true) + 20 (header); this is the C2 baseline entry
- fallback seam (if the measured size lands over the ceiling): split `registry_swaps` (2076, 2154, 2744, 2812: 269 lines) from `registry_prelinks` (the four collisions + 2892, 2964, 3025, 3085: 327 lines).
- dry run (from the merged head after C1 and C2; `--test-snapshot` = the ID snapshot re-collected at that head — identity-equal to `.refactor/tests-revision8-before.json` until the first family lands; the driver regenerates the id map and refuses a mismatch with the pre-written file):
  ```
  TMPDIR=/dev/shm/refactor-s8 python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision8_coordination.py --class Revision8CoordinationTests --methods test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating,test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting,test_registry_exchange_race_restores_foreign_canonical_without_publish,test_absent_registry_link_race_never_clobbers_foreign_canonical,test_absent_registry_directory_collision_preserves_foreign_node,test_absent_registry_symlink_collision_preserves_foreign_node,test_absent_registry_broken_symlink_collision_preserves_foreign_node,test_absent_registry_unreadable_file_collision_preserves_foreign_node,test_exact_staged_registry_prelink_is_recognized_as_published,test_exact_staged_registry_prelink_rolls_back_after_validation_failure,test_exact_staged_owner_prelink_is_recognized_as_adopted,test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner --dest tests/test_revision8_registry_races.py --shape class --target-class Revision8RegistryRacesTests --test-only --test-snapshot <ids-snapshot-at-merged-head> --id-map .refactor/idmap-revision8-registry_races.json --format-imports --manifest .refactor/family-revision8-registry_races.json
  ```
- apply: same argv + `--apply`
- gate (matches `.refactor/revision8-run-cluster.py:191-215` exactly): `bash $S/verify.sh --pkg tests --snapshot <body-snapshot-at-merged-head> --manifest .refactor/family-revision8-registry_races.json --strict-bodies --test-snapshot <ids-snapshot-at-merged-head> --test-mode mapping` (no `--fast`; `GATE: PASS` required), then `python3 scripts/check_file_length.py tests`, then the bare-`PYTHONPATH` proofs `env -u PYTHONPATH python3 -m unittest tests.test_revision8_registry_races` and `env -u PYTHONPATH python3 -c 'import tests.test_revision8_registry_races'` (standalone import, i.e. first in a Gate 1 shard)
- id map: `.refactor/idmap-revision8-registry_races.json` (12 entries per collector). Example: unittest `test_revision8_coordination.Revision8CoordinationTests.test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating` -> `test_revision8_registry_races.Revision8RegistryRacesTests.test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating`; pytest `tests/test_revision8_coordination.py::Revision8CoordinationTests::test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating` -> `tests/test_revision8_registry_races.py::Revision8RegistryRacesTests::test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating`
- commit: `refactor(tests): move the registry races scenarios of Revision8CoordinationTests to tests/test_revision8_registry_races.py (class shape)`

### f5 — `interruptions` -> `tests/test_revision8_interruptions.py` / `Revision8InterruptionsTests`

- scenario: BaseException injected after each publication/rollback syscall restores registry and owner begin paths and keeps the candidate coherent; post-restoration read and lock failures keep registry and journal coherent.
- tests (3, ascending source order, current-file `line..end_line` (code lines)): `test_postsyscall_baseexception_restores_registry_and_owner_begin_paths` 3233..3433 (185), `test_postsyscall_baseexception_during_rollback_retains_coherent_candidate` 3435..3655 (205), `test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent` 3657..3833 (166)
- helpers used (inventory `calls` ∩ helpers, all inherited from `Revision8Support`): `api_environment`, `coordination_snapshot`, `decision_record`, `journal_path`, `open_run`, `opening_record`, `prime_batch_lock`, `prime_registry_lock`, `proven_dead_pid`, `run_dir`
- module globals the methods read (the mover copies these imports): `RECORDED_AT`, `journal`, `json`, `mock`, `os`, `socket`
- size: **576** upper bound = 556 (methods, true) + 20 (header); this is the C2 baseline entry
- fallback seam (if the measured size lands over the ceiling): one test per module if ever needed (184/204/165 lines each); no seam under 500 exists that keeps two of them together — a real scenario boundary, so leave as is.
- dry run (from the merged head after C1 and C2; `--test-snapshot` = the ID snapshot re-collected at that head — identity-equal to `.refactor/tests-revision8-before.json` until the first family lands; the driver regenerates the id map and refuses a mismatch with the pre-written file):
  ```
  TMPDIR=/dev/shm/refactor-s8 python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision8_coordination.py --class Revision8CoordinationTests --methods test_postsyscall_baseexception_restores_registry_and_owner_begin_paths,test_postsyscall_baseexception_during_rollback_retains_coherent_candidate,test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent --dest tests/test_revision8_interruptions.py --shape class --target-class Revision8InterruptionsTests --test-only --test-snapshot <ids-snapshot-at-merged-head> --id-map .refactor/idmap-revision8-interruptions.json --format-imports --manifest .refactor/family-revision8-interruptions.json
  ```
- apply: same argv + `--apply`
- gate (matches `.refactor/revision8-run-cluster.py:191-215` exactly): `bash $S/verify.sh --pkg tests --snapshot <body-snapshot-at-merged-head> --manifest .refactor/family-revision8-interruptions.json --strict-bodies --test-snapshot <ids-snapshot-at-merged-head> --test-mode mapping` (no `--fast`; `GATE: PASS` required), then `python3 scripts/check_file_length.py tests`, then the bare-`PYTHONPATH` proofs `env -u PYTHONPATH python3 -m unittest tests.test_revision8_interruptions` and `env -u PYTHONPATH python3 -c 'import tests.test_revision8_interruptions'` (standalone import, i.e. first in a Gate 1 shard)
- id map: `.refactor/idmap-revision8-interruptions.json` (3 entries per collector). Example: unittest `test_revision8_coordination.Revision8CoordinationTests.test_postsyscall_baseexception_restores_registry_and_owner_begin_paths` -> `test_revision8_interruptions.Revision8InterruptionsTests.test_postsyscall_baseexception_restores_registry_and_owner_begin_paths`; pytest `tests/test_revision8_coordination.py::Revision8CoordinationTests::test_postsyscall_baseexception_restores_registry_and_owner_begin_paths` -> `tests/test_revision8_interruptions.py::Revision8InterruptionsTests::test_postsyscall_baseexception_restores_registry_and_owner_begin_paths`
- commit: `refactor(tests): move the interruptions scenarios of Revision8CoordinationTests to tests/test_revision8_interruptions.py (class shape)`

### f6 — `orphan_identity` -> `tests/test_revision8_orphan_identity.py` / `Revision8OrphanIdentityTests`

- scenario: runs_root orphan/placeholder classification and node-identity swaps: malformed/registered-missing registry stays generic, empty placeholders are silent, same-id state after final classification is never overwritten, orphan kinds and the classifier control, runs_root inode swap, claimed candidate child, cleanup identity replacements, placeholder mutation/inode/type replacement at publication, run-directory and journal identity swaps roll back the original, post-scan journal target swaps are never followed.
- tests (17, ascending source order, current-file `line..end_line` (code lines)): `test_post_scan_journal_target_swaps_are_generic_and_never_followed` 1959..2026 (65), `test_malformed_registry_remains_generic` 2067..2072 (6), `test_registered_missing_journal_remains_generic` 3901..3912 (10), `test_empty_placeholder_is_silent_for_all_unrelated_coordination` 3914..3962 (45), `test_empty_placeholder_targeted_validate_and_monitor_remain_unchanged` 3964..4006 (41), `test_same_id_state_created_after_final_classification_is_never_overwritten` 4008..4106 (96), `test_nonempty_ownerless_orphan_names_validated_repo_relative_path` 4108..4124 (15), `test_non_dot_regular_file_in_runs_root_is_silently_ignored` 4126..4135 (8), `test_ambiguous_orphan_kinds_remain_generic_and_nonmutating` 4137..4240 (100), `test_orphan_classifier_control_is_load_bearing` 4242..4261 (19), `test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty` 4686..4750 (62), `test_claimed_candidate_child_is_preserved_but_never_published` 4752..4798 (44), `test_cleanup_identity_replacements_preserve_foreign_state_and_fail` 4800..4889 (87), `test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate` 4891..4945 (51), `test_placeholder_inode_and_type_replacement_at_publication_are_generic` 4947..5029 (80), `test_run_directory_identity_swap_at_publication_rolls_back_original` 5031..5066 (33), `test_journal_identity_swap_at_publication_rolls_back_bound_original` 5068..5107 (37)
- helpers used (inventory `calls` ∩ helpers, all inherited from `Revision8Support`): `api_environment`, `append_record`, `close`, `command`, `coordination_snapshot`, `decision_record`, `journal_path`, `open_run`, `opening_record`, `prime_registry_lock`, `readmit`, `retire`, `run_dir`, `write_registry`
- module globals the methods read (the mover copies these imports): `journal`, `json`, `mock`, `os`, `threading`
- size: **819** upper bound = 799 (methods, true) + 20 (header); this is the C2 baseline entry
- fallback seam (if the measured size lands over the ceiling): split `orphans` (2069, 3903, 3916..4263: 9 tests, 331 lines) from `identity_swaps` (1961, 4688..5109: 8 tests, 451 lines) — the seam is the source gap 4263/4265 plus the two early tests.
- dry run (from the merged head after C1 and C2; `--test-snapshot` = the ID snapshot re-collected at that head — identity-equal to `.refactor/tests-revision8-before.json` until the first family lands; the driver regenerates the id map and refuses a mismatch with the pre-written file):
  ```
  TMPDIR=/dev/shm/refactor-s8 python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision8_coordination.py --class Revision8CoordinationTests --methods test_post_scan_journal_target_swaps_are_generic_and_never_followed,test_malformed_registry_remains_generic,test_registered_missing_journal_remains_generic,test_empty_placeholder_is_silent_for_all_unrelated_coordination,test_empty_placeholder_targeted_validate_and_monitor_remain_unchanged,test_same_id_state_created_after_final_classification_is_never_overwritten,test_nonempty_ownerless_orphan_names_validated_repo_relative_path,test_non_dot_regular_file_in_runs_root_is_silently_ignored,test_ambiguous_orphan_kinds_remain_generic_and_nonmutating,test_orphan_classifier_control_is_load_bearing,test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty,test_claimed_candidate_child_is_preserved_but_never_published,test_cleanup_identity_replacements_preserve_foreign_state_and_fail,test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate,test_placeholder_inode_and_type_replacement_at_publication_are_generic,test_run_directory_identity_swap_at_publication_rolls_back_original,test_journal_identity_swap_at_publication_rolls_back_bound_original --dest tests/test_revision8_orphan_identity.py --shape class --target-class Revision8OrphanIdentityTests --test-only --test-snapshot <ids-snapshot-at-merged-head> --id-map .refactor/idmap-revision8-orphan_identity.json --format-imports --manifest .refactor/family-revision8-orphan_identity.json
  ```
- apply: same argv + `--apply`
- gate (matches `.refactor/revision8-run-cluster.py:191-215` exactly): `bash $S/verify.sh --pkg tests --snapshot <body-snapshot-at-merged-head> --manifest .refactor/family-revision8-orphan_identity.json --strict-bodies --test-snapshot <ids-snapshot-at-merged-head> --test-mode mapping` (no `--fast`; `GATE: PASS` required), then `python3 scripts/check_file_length.py tests`, then the bare-`PYTHONPATH` proofs `env -u PYTHONPATH python3 -m unittest tests.test_revision8_orphan_identity` and `env -u PYTHONPATH python3 -c 'import tests.test_revision8_orphan_identity'` (standalone import, i.e. first in a Gate 1 shard)
- id map: `.refactor/idmap-revision8-orphan_identity.json` (17 entries per collector). Example: unittest `test_revision8_coordination.Revision8CoordinationTests.test_post_scan_journal_target_swaps_are_generic_and_never_followed` -> `test_revision8_orphan_identity.Revision8OrphanIdentityTests.test_post_scan_journal_target_swaps_are_generic_and_never_followed`; pytest `tests/test_revision8_coordination.py::Revision8CoordinationTests::test_post_scan_journal_target_swaps_are_generic_and_never_followed` -> `tests/test_revision8_orphan_identity.py::Revision8OrphanIdentityTests::test_post_scan_journal_target_swaps_are_generic_and_never_followed`
- commit: `refactor(tests): move the orphan identity scenarios of Revision8CoordinationTests to tests/test_revision8_orphan_identity.py (class shape)`

### f7 — `successors` -> `tests/test_revision8_successors.py` / `Revision8SuccessorsTests`

- scenario: Successor DAG: transfer control, ancestry transfer/release/readmission, refusal literals for retired/overlap/disjoint scope, persisted dangling/cyclic/disjoint edges stay generic, legacy successor close without valid judgment, byte-sorted mixed conflicts, concurrent successor and ordinary admission serialize atomically, only a retired successor may close and release ancestry, close rollback and release-control-disabled keep the reservation, historical fork releases the shared ancestor only after both branches close.
- tests (14, ascending source order, current-file `line..end_line` (code lines)): `test_successor_transfer_control_is_load_bearing` 4263..4286 (23), `test_successor_chain_transfers_ancestry_releases_and_readmits` 4288..4365 (73), `test_successor_readmission_may_leave_ancestor_scope_but_keeps_it_reserved` 4367..4406 (38), `test_successor_refusal_literals_for_retired_overlap_and_disjoint_scope` 4408..4427 (19), `test_persisted_dangling_successor_edge_is_generic_and_nonmutating` 4429..4445 (15), `test_persisted_successor_cycle_is_generic_and_nonmutating` 4447..4470 (22), `test_persisted_disjoint_successor_edge_is_generic_and_nonmutating` 4472..4489 (16), `test_legacy_successor_close_without_valid_judgment_cannot_release_scope` 4491..4539 (47), `test_mixed_open_and_retired_conflicts_are_byte_sorted` 4541..4562 (20), `test_concurrent_successor_and_ordinary_admission_serialize_atomically` 4564..4684 (120), `test_only_a_retired_successor_may_close_and_release_ancestry` 5109..5133 (22), `test_close_rollback_preserves_effective_ancestral_reservation` 5135..5168 (32), `test_release_control_disabled_keeps_retired_ancestry_reserved` 5170..5201 (31), `test_historical_fork_releases_shared_ancestor_only_after_both_branches_close` 5203..5247 (42)
- helpers used (inventory `calls` ∩ helpers, all inherited from `Revision8Support`): `api_environment`, `close`, `closure_record`, `command`, `coordination_snapshot`, `journal_path`, `open_run`, `opening_record`, `plant_run_state`, `prime_batch_lock`, `prime_registry_lock`, `readmit`, `retire`, `run_dir`, `write_record`, `write_registry`
- module globals the methods read (the mover copies these imports): `RECORDED_AT`, `TOOLS`, `journal`, `json`, `mock`, `os`, `socket`, `subprocess`, `sys`, `time`
- size: **540** upper bound = 520 (methods, true) + 20 (header); this is the C2 baseline entry
- fallback seam (if the measured size lands over the ceiling): split at the source gap 4686/5111: `successor_admission` (4265..4686, 10 tests, 383 lines) and `successor_release` (5111..5249, 4 tests, 122 lines) — only if needed; the second half is small.
- dry run (from the merged head after C1 and C2; `--test-snapshot` = the ID snapshot re-collected at that head — identity-equal to `.refactor/tests-revision8-before.json` until the first family lands; the driver regenerates the id map and refuses a mismatch with the pre-written file):
  ```
  TMPDIR=/dev/shm/refactor-s8 python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision8_coordination.py --class Revision8CoordinationTests --methods test_successor_transfer_control_is_load_bearing,test_successor_chain_transfers_ancestry_releases_and_readmits,test_successor_readmission_may_leave_ancestor_scope_but_keeps_it_reserved,test_successor_refusal_literals_for_retired_overlap_and_disjoint_scope,test_persisted_dangling_successor_edge_is_generic_and_nonmutating,test_persisted_successor_cycle_is_generic_and_nonmutating,test_persisted_disjoint_successor_edge_is_generic_and_nonmutating,test_legacy_successor_close_without_valid_judgment_cannot_release_scope,test_mixed_open_and_retired_conflicts_are_byte_sorted,test_concurrent_successor_and_ordinary_admission_serialize_atomically,test_only_a_retired_successor_may_close_and_release_ancestry,test_close_rollback_preserves_effective_ancestral_reservation,test_release_control_disabled_keeps_retired_ancestry_reserved,test_historical_fork_releases_shared_ancestor_only_after_both_branches_close --dest tests/test_revision8_successors.py --shape class --target-class Revision8SuccessorsTests --test-only --test-snapshot <ids-snapshot-at-merged-head> --id-map .refactor/idmap-revision8-successors.json --format-imports --manifest .refactor/family-revision8-successors.json
  ```
- apply: same argv + `--apply`
- gate (matches `.refactor/revision8-run-cluster.py:191-215` exactly): `bash $S/verify.sh --pkg tests --snapshot <body-snapshot-at-merged-head> --manifest .refactor/family-revision8-successors.json --strict-bodies --test-snapshot <ids-snapshot-at-merged-head> --test-mode mapping` (no `--fast`; `GATE: PASS` required), then `python3 scripts/check_file_length.py tests`, then the bare-`PYTHONPATH` proofs `env -u PYTHONPATH python3 -m unittest tests.test_revision8_successors` and `env -u PYTHONPATH python3 -c 'import tests.test_revision8_successors'` (standalone import, i.e. first in a Gate 1 shard)
- id map: `.refactor/idmap-revision8-successors.json` (14 entries per collector). Example: unittest `test_revision8_coordination.Revision8CoordinationTests.test_successor_transfer_control_is_load_bearing` -> `test_revision8_successors.Revision8SuccessorsTests.test_successor_transfer_control_is_load_bearing`; pytest `tests/test_revision8_coordination.py::Revision8CoordinationTests::test_successor_transfer_control_is_load_bearing` -> `tests/test_revision8_successors.py::Revision8SuccessorsTests::test_successor_transfer_control_is_load_bearing`
- commit: `refactor(tests): move the successors scenarios of Revision8CoordinationTests to tests/test_revision8_successors.py (class shape)`

### Stays in `tests/test_revision8_coordination.py` (default: keep, §0.3)

The module header (`from __future__`, the stdlib imports the shell still needs, `from tests._revision8_constants import ...` pruned to the names still read, `from tests._revision8_support import Revision8Support`, `sys.path.insert(0, str(ROOT / "scripts"))`, `from codex_orchestrator import journal  # noqa: E402` if a reader remains), the class shell with its docstring only, and `if __name__ == "__main__": unittest.main()`. No method stays: 31 helpers -> mixin, 81 tests -> families. Expected shell: ~25 code lines.

## 4. State ownership

| state | owner | writers | readers |
|---|---|---|---|
| `self.temporary`, `self.root`, `self.repo`, `self.head`, `self.env` | `setUp` (mixin) | `setUp` only | helpers and tests via inheritance |
| `self._record_number` | `setUp` (mixin) | `setUp`, `write_record` (mixin) | `write_record` |
| `self._readmit_number` | `setUp` (mixin) | `setUp`, `readmit` (mixin) | `readmit` |
| module-level state | none (constants `ROOT`, `TOOLS`, `RECORDED_AT` are immutable and live in `tests/_revision8_constants.py`); no `global` statement | — | — |

No test writes instance state (`writes` empty for all 81); class-body state is the docstring only, so `sibling class extraction requires class state to live in a shared support base` cannot fire.

## 5. Commits in execution order

### C-config — config only, **operator decision (§0.1)**, before C1

Recommended content if the operator takes A''': `pyproject.toml` gains `[tool.ruff.lint.isort]` / `known-local-folder = ["codex_orchestrator", "commitment_paths"]` and nothing else. Gated on `verify.sh`'s `ruff check tests` **and** CLAUDE.md's `ruff check scripts tests system/fr223 && git ls-files -z "*.py" | xargs -0 python3 scripts/check_file_length.py && PYTHONPATH=scripts:scripts/forge lint-imports` (measured: 0 new findings). Edits no test and no production file. Then re-run the C1 dry run.

### C1 — mixin (FIXED argv; dry run verified `.refactor/dryrun-revision8-mixin.txt` line 1262 under the committed config; to be re-run under C-config)

```
TMPDIR=/dev/shm/refactor-s8 python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision8_coordination.py --class Revision8CoordinationTests --methods setUp,runs_root,registry_path,run_dir,journal_path,write_record,command,api_environment,opening_record,task_record,execution_record,execution_result_record,verification_record,decision_record,closure_record,create_citation_files,open_run,append_record,readmit,retire,close,coordination_snapshot,write_registry,prime_registry_lock,prime_batch_lock,assert_absent_registry_node_collision,valid_candidate,assert_invalid_candidate,assert_valid_candidate,plant_run_state,proven_dead_pid --dest tests/_revision8_support.py --shape mixin --target-class Revision8Support --test-only --test-snapshot .refactor/tests-revision8-before.json --format-imports --manifest .refactor/mixin-revision8.json
```

- apply: same argv + `--apply`; gate: `bash $S/verify.sh --pkg tests --snapshot <body-snapshot> --manifest .refactor/mixin-revision8.json --strict-bodies --test-snapshot <ids-snapshot> --test-mode identity`, then `python3 scripts/check_file_length.py tests` (passes under the lane's `REFACTOR_MAX_LINES=1000` before C2), then `env -u PYTHONPATH python3 -m unittest tests.test_revision8_coordination` (brief §4 item 3) **and** `env -u PYTHONPATH python3 -c 'import tests._revision8_support'` (the standalone proof; fails under the committed config, passes under A''').
- expected diff (from the dry run): source drops `stat`, `tempfile`, `contextmanager`, `batch`; class header becomes `class Revision8CoordinationTests(Revision8Support, unittest.TestCase):`; destination `tests/_revision8_support.py` = 579 lines / **539 code lines**, 31 methods verbatim with their decorators; header imports `copy, json, os, socket, stat, subprocess, sys, tempfile, contextmanager, Path, mock`, `from tests._revision8_constants import RECORDED_AT, TOOLS`, `from codex_orchestrator import batch, journal` (in that order under A'''; reversed under the committed config).
- before C1, diff the `settings` block of a fresh `collect_tests.py snapshot --start tests` against the freeze (`start tests / top tests / preset auto / pattern test*.py / pytest true`) so the per-cluster compare diffs IDs, not settings.

### C2 — config only: provisional `.refactor-baseline.json` entries (§0.2)

```json
{
 "tests/_revision8_support.py": 539,
 "tests/test_revision8_append_schema.py": 724,
 "tests/test_revision8_precedence.py": 617,
 "tests/test_revision8_rollback.py": 593,
 "tests/test_revision8_registry_races.py": 628,
 "tests/test_revision8_interruptions.py": 576,
 "tests/test_revision8_orphan_identity.py": 819,
 "tests/test_revision8_successors.py": 540
}
```

### C3..C9 — families, in this order

Largest first so the source shrinks fastest; any order is valid (every helper is inherited from the mixin; `tests calling other tests: []`). Each family's dry run is produced **from the merged head**; body and ID snapshots are re-taken after each merge.

1. C3 `orphan_identity` -> `tests/test_revision8_orphan_identity.py` (17 tests, upper bound 819); source after (est.): 3565 code lines
2. C4 `append_schema` -> `tests/test_revision8_append_schema.py` (10 tests, upper bound 724); source after (est.): 2861 code lines
3. C5 `registry_races` -> `tests/test_revision8_registry_races.py` (12 tests, upper bound 628); source after (est.): 2253 code lines
4. C6 `precedence` -> `tests/test_revision8_precedence.py` (16 tests, upper bound 617); source after (est.): 1656 code lines
5. C7 `rollback` -> `tests/test_revision8_rollback.py` (9 tests, upper bound 593); source after (est.): 1083 code lines
6. C8 `interruptions` -> `tests/test_revision8_interruptions.py` (3 tests, upper bound 576); source after (est.): 527 code lines
7. C9 `successors` -> `tests/test_revision8_successors.py` (14 tests, upper bound 540); source after (est.): 7 code lines

Gate 1 shard membership after the split (4 shards, source kept): shard 1 `orphan_identity`, `successors`; shard 2 `append_schema`, `precedence`; shard 3 `registry_races` (with the source); shard 4 `interruptions`, `rollback` (§0.1 table A).

## 6. Expected refusals and the constructs checked

- **None expected for any family once C1 is merged.** Class-body non-def statements = docstring only -> pass (move_methods.py:324); no test calls a test and no helper remains after C1 -> pass (:326). Before C1 every family dry run is refused with `sibling class would lose calls to remaining methods` (designed order check).
- Decorators: `@` in lines 28..5251 only at 65 (`@property`), 69 (`@property`), 101 (`@contextmanager`) — helpers, all in C1. No test is decorated; no `skipUnless`.
- `nonlocal`: **28** occurrences, all inside closures nested in method bodies (line 385 in the helper `assert_absent_registry_node_collision`, C1; 27 in test bodies: 1981, 2094, 2170, 2760, 2827, 3115, 3178, 3253, 3299, 3344, 3397, 3451, 3496, 3560, 3620, 3674, 3683, 3752, 3762, 3849, 4029, 4709, 4767, 4824, 4965, 5043, 5081). They bind the enclosing method's locals and travel verbatim; every such test is `ok`.
- Nested defs: 42 nested `def`/`class` (two local `class InjectedInterruption(BaseException)` at 3236 and 3438); all inside bodies, verbatim.
- `super()`, `__class__`, `type(self)`, name mangling (`mangled: []` for all 112), or the literal `Revision8CoordinationTests` inside a body: none (the only hit is the class line 26).
- `subTest` is used widely; fine in class shape.
- `TOOLS` is read by one test (`test_concurrent_successor_and_ordinary_admission_serialize_atomically`, 4564..4684) and `RECORDED_AT` by 25; the mover copies `from tests._revision8_constants import ...` into each family that needs them (`orphan_identity` needs neither — see §0.1).
- `threading`/`time` are read only by tests (`orphan_identity`, `successors`); the source keeps them until their last reader moves.

## 7. Quality and debt report

- tests/_revision8_support.py holds 31 methods (> class_target 30) — accepted: one support mixin per class (brief section 4); follow-up bead: to be created at handover (split by role: record factories / lifecycle drivers / registry-lock primers)
- tests/_revision8_support.py 539 code lines (> module_target 500) — provisional baseline entry; same follow-up bead
- every family module over module_target 500 (upper bounds 540..819) — provisional baseline entries; 500..1000 is the brief's band; finalize replaces with measured sizes
- test_postsyscall_baseexception_restores_registry_and_owner_begin_paths 3233..3433 (201 lines, 185 code) — function-length debt, moved verbatim (interruptions)
- test_postsyscall_baseexception_during_rollback_retains_coherent_candidate 3435..3655 (221 lines, 205 code) — function-length debt, moved verbatim (interruptions)
- test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent 3657..3833 (177 lines, 166 code) — function-length debt, moved verbatim (interruptions)
- tests/test_revision8_coordination.py keeps an empty class shell (docstring only) plus __main__ — default keep (see source_shell); .refactor-baseline.json:56 (4905, file now 4903, inert) and pyproject.toml:242 dropped at finalize
- Helper fan-in is high by design (each family uses 10..18 of the 31 helpers); the mixin cannot be split along family lines without duplicating factories — the follow-up splits it by role.

## 8. Risks the critic must check

1. §0.1: the operator's option; that C-config precedes C1; that the C1 dry run is regenerated under it; the two ruff gates on the config commit.
2. Sizes: recount each family from its dry run at apply time; any family over 1,000 takes its listed fallback seam (none expected: max 819). C2 must carry exactly the upper bounds in §5 (a low entry fails the family gate).
3. ID maps: 81 keys per collector across seven files, injective, disjoint, spelled as in the freeze (`preset: auto` -> namespace spellings); `shards: {}`, `pinned: {}`.
4. Item D (§0.1) would be a second hand-written commit plus a hand edit of the source header: not tonight, but the cleaner long-term shape; B is the plugin fix (bead in refactor-python).
5. After C9 the source collects 0 tests; `REFACTOR_TEST_CMD` (`discover -p 'test_revision8*.py'`) still collects it — not a failure. Do not introduce a pytest-only per-module gate (bare `pytest` on an empty collection exits 5).
6. Family modules inherit the temporary glob `tests/test_revision8_*.py` (no `I001`, no `E402` — under A''' the `codex_orchestrator` import sits in the header block with no preceding statement); finalize replaces the globs with measured per-module entries and deletes `pyproject.toml:242`.

## 9. Test expectations

- C1: `collect_tests.py compare <ids> --mode identity` -> identical 1,908 IDs per collector.
- each family: `--mode mapping --manifest .refactor/family-revision8-<family>.json` -> exactly the family's N IDs remapped per collector, all others identical, counts exact; `REFACTOR_TEST_CMD` = 81 tests green; both bare-`PYTHONPATH` proofs green.
- after C9: the seven modules collect 81 tests; the source collects 0.
