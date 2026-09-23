# Split plan: tests/test_revision9_coordination.py — class `Revision9BindingTests` (decompose mode, class shape)

Lane A, session 4, bead forge-plugin-6g67 (second class of the same bead; the `Revision9BuilderBatchTests` wave closed green at 9b7599a). Planner: split-planner (Fable). Written against `.refactor/inventory-revision9-coord-binding.json` / `.md` (class_inventory.py at **9b7599a**, class lines **246..2370**, bases `unittest.TestCase`, no class-body statements, 26 methods all verdict `ok`) and the latest ID snapshot `.refactor/tests-revision9-coord-c12-ledger_recovery.json` (namespace preset, 1,908 IDs per collector, 15 of them under `Revision9BindingTests`, `settings.pinned` and `shards` empty). **All line numbers below are HEAD 9b7599a lines**; after c00b the two mixin bodies are gone (subtract 26 physical lines from everything after L271), so re-derive lines from the current tree, never from this file. Sizes are `scripts/check_file_length.py` code lines (non-blank, non-comment; `code_lines()` at check_file_length.py:37-45), measured per `def` with python over the HEAD file: **15 tests = 1,121**, **11 helpers = 901**, class line 1, class total **2,023**; source module today **4,931**.

## 0. Summary

| item | value |
|---|---|
| **Status** | Plan only; no dry run, no apply, no gate executed by the planner. The orchestrator copies the driver and id-map generator (§3.0), lands the two prep commits (§6), then runs c00b, c01b, c02b, c03b through the driver from the merged head, then the wave-close Gate 1. |
| baseline | 9b7599a (branch `refactor/split-test-revision9-coordination`; already carries the constants module 455e436, the ruff globs cc0bfd7, the isort ruling 212ccc7 and the `Revision9BuilderBatchTests` wave 63dd6b8..9b7599a). Prerequisites: **none** (`key` and the other constants already live in `tests/_revision9_coord_constants.py`, imported by the source at L16-21). Census: 0 external sites (`census_complete: false` treated as empty per brief §5; `grep -rn Revision9BindingTests tests scripts pyproject.toml` finds only the class statement at L246). |
| c00b (§2b) | **2 shared helpers** `setUp`, `binding` -> `tests/_revision9_coord_binding_support.py`, mixin `Revision9BindingSupport`, mixin shape, `--test-only`, identity mode; **24 helper code lines, ~31 with header** (no baseline entry: far under 500). The other 9 helpers (877 lines) are private to exactly one family each and travel in that family's class-shape `--methods` list. |
| this plan | **3 scenario families**, class shape, one commit each, sequential from the merged head; **15 tests moved** (1,121 test code lines) plus **9 family-private helpers** (877 code lines); **0 tests stay**, **0 helpers stay**; the source keeps an empty `pass` shell of the class (§3.5). |
| why 3 families, not 2 | family payload = 1,121 + 877 = **1,998** code lines before headers; two modules at the 1,000 ceiling cannot hold 1,998 + 2 headers (≥ 2,014). Three is the minimum; each lands in 544..752 (§3.1). |
| shape / tier / mode | `--shape class --target-class Revision9<Family>Tests --test-only --id-map ... --format-imports --import-root "$PWD"`; tier 1 relocation; gate `--test-mode mapping`. No `--annotate-self` (that flag is for function-shape moves in the type-gated production package; nothing here is a function-shape move and `tests/` is outside the type gate). |
| modules over 1,000 | **0** (largest estimate 752: `binding_replay`). |
| modules under 500 | **0 families**; the mixin (~31) is a support module, not a family, and is as small as honest allocation permits (§2b). |
| refusals expected | **none**: all 26 methods `ok`; no decorators; no test calls a test; every private helper's transitive test users lie in one family (checked programmatically, §2b); the mixin helpers call no class method (`binding` calls nothing; `setUp` calls only `addCleanup`); no destination exists; no family class name appears anywhere in `tests/` or `scripts/`. |
| focused test count | **144** before and after every commit (`REFACTOR_TEST_CMD = python3 -m unittest discover -s tests -p 'test_revision9_coordination*.py'` picks up `tests/test_revision9_coordination_binding_<family>.py`, never `tests/_revision9_coord_binding_support.py`); 1,908 per collector overall. |
| source after the wave | ≈ **2,909** code lines (4,931 − 2,023 class lines + 1 class line kept + 1 `pass` + 1 support import − 1 `import subprocess`), still over 1,000 because `Revision9FixtureTests` (L28-161), the `Revision9BuilderBatchTests` shell (L162-245, one skipUnless test) and `Revision9MergeTransitionGrammarTests` (L2373-5150) remain; the grammar class is the next target (inventory `.refactor/inventory-revision9-coord-grammar.json` already taken). |

## 1. Delete first (dead code, with evidence)

None. `vulture`/`radon` absent (as in the first wave). Every helper has ≥ 1 test user in the transitive call closure (§2b: `setUp` is framework-called; `binding` 11 users; `issue_for` 5; `correlation_records` 5; `_relined`/`_with_control_removed` 3; `_write_commit_gate_binding_chain` 3; `_write_commit_decision_cycle_chain`/`_superseded_set`/`_semantic_state`/`_write_semantic_chain` 2). No body, docstring, decorator or assertion edit anywhere in this wave.

## 2. Family rules applied (from brief §4 "Planning rules the critic enforces")

- Families start from the inventory's **10 clusters after hub peeling** (hubs: `binding`, `correlation_records`, `issue_for`, `@state:repo`, `@state:assertEqual`, `@state:assertTrue`, `@state:subTest`, `@state:assertRaisesRegex`): cluster 1 = `setUp` + the semantic pair (2 tests + 2 helpers), cluster 2 = the resolver trio + its 2 chain writers, cluster 3 = the four shape/currentness tests, clusters 4/5/7 = singletons (`test_commit_candidate_binding_reconstructs_v2_without_relabeling_history`, `test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task`, `test_fr021_four_exact_correlation_issues_and_disabled_control`), cluster 6 = the three FR-021 `2mu` tests + 3 helpers, clusters 8/9/10 = the peeled hubs `binding`, `correlation_records`, `issue_for`. The §3 per-test table names each test's cluster so the critic can see every merge; there is **no split** of any cluster (cluster 1 loses only `setUp`, which goes to the mixin by rule).
- Merges: cluster 4 -> cluster 3 (`binding_shape`: the v2 reconstruction test exercises `builders._candidate_binding_for_state` like `test_commit_identity_binding_projects_existing_verification_type` next to it in the source; it calls no helper, so placement is by subject). Clusters 5, 6, 7, 9, 10 -> one FR-021 correlation group (all five tests call `correlation_records` + `issue_for`; 486 lines). Cluster 1 minus `setUp` (256 lines) -> merged with that group into `binding_replay` (742): both halves are replay-time checks over recorded facts (`journal._check_binding_correlation` over a run's records; `builders.resolve_binding` replaying a chain's events), both build their records with the mixin's `binding`, and the FR-021 group alone (486 + 9 header = 495) would be a family under 500 — the merge removes the only under-target candidate instead of justifying it.
- Rejected alternative for the semantic pair: joining `binding_resolver` (same API under test, `builders.resolve_binding` + `assertRaisesRegex(journal.CoordinationRefusal, ...)` + `subTest`) would make that module 720 + 256 + 9 = **985** — 15 lines under the hard ceiling, and its provisional baseline entry (+40) would itself exceed 1,000. Not planned; recorded so the critic does not re-derive it.
- Every module is estimated at test lines + private-helper lines + the exact header the mover will write (§3 lists it per family; the first wave's c00 measured the header model exact: 15 predicted = 15 measured, and family headers cost 12..22 lines there only because they had more imports). Nothing can reach 1,000 (the mover adds only header lines).
- Execution order: c01b = the family with no private helpers (`binding_shape`; the cleanest first diff: five tests, the inherited `binding` only), then c02b and c03b in source order of each family's first test. Order does not affect refusals (§3.0).
- Helpers never move twice: `setUp` and `binding` go to the mixin at c00b and are inherited through the copied bases `(Revision9BindingSupport, unittest.TestCase)`; the 9 private helpers move once, with their family.

## 2b. Helper allocation (c00b mixin vs. family-private vs. source)

Rule (bead): a helper whose transitive test users span two or more families, plus `setUp`, plus every helper a mixin helper calls -> the **one mixin** `Revision9BindingSupport` (`tests/_revision9_coord_binding_support.py`, mixin shape, commit c00b, listed first in every family's bases). A helper whose transitive test users all lie in one family -> that family's sibling class, moved in the same class-shape call in source order. Computed from the inventory `calls` graph followed transitively (python over `inventory-revision9-coord-binding.json`; the same script generated `families-revision9-coord-binding.json` and asserts the property for every private helper). Mixin closure: `binding` calls no method and `setUp` calls only `addCleanup`, so nothing had to be lifted.

| helper | HEAD lines | code lines | calls helpers | test users | families of its users | destination |
|---|---|---|---|---|---|---|
| `setUp` | L247-251 | 5 | — | 0 (framework-called) | — | **mixin** (c00b) |
| `binding` | L253-271 | 19 | — | 11 | `binding_shape` (4), `binding_replay` (7) | **mixin** (c00b) |
| `_write_commit_gate_binding_chain` | L273-523 | 242 | — | 3 (directly 1, via `_write_commit_decision_cycle_chain` 2) | `binding_resolver` | family `binding_resolver` (private) |
| `_write_commit_decision_cycle_chain` | L525-883 | 342 | `_write_commit_gate_binding_chain` | 2 | `binding_resolver` | family `binding_resolver` (private) |
| `correlation_records` | L1579-1622 | 44 | `binding` | 5 | `binding_replay` | family `binding_replay` (private) |
| `issue_for` | L1624-1627 | 4 | — | 5 | `binding_replay` | family `binding_replay` (private) |
| `_relined` | L1686-1689 | 4 | — | 3 | `binding_replay` | family `binding_replay` (private) |
| `_superseded_set` | L1691-1721 | 31 | `binding` | 2 | `binding_replay` | family `binding_replay` (private) |
| `_with_control_removed` | L1723-1727 | 5 | — | 3 | `binding_replay` | family `binding_replay` (private) |
| `_semantic_state` | L2110-2174 | 65 | — | 2 (via `_write_semantic_chain`) | `binding_replay` | family `binding_replay` (private) |
| `_write_semantic_chain` | L2176-2317 | 140 | `_semantic_state`, `binding` | 2 | `binding_replay` | family `binding_replay` (private) |

**Mixin (c00b):** 2 helpers, **24 code lines**, ~31 with header. The two big writers (242 + 342) are used only by the three resolver tests, so they are private to `binding_resolver` and the mixin does not carry them — this is what keeps the mixin at 24 instead of ~610. `binding` cannot be private: its 11 users are 464 lines of `binding_shape` and 742 lines of `binding_replay`, which no single module under 1,000 can hold.
- mixin methods csv (source order): `setUp,binding`
- c00b argv (mixin shape; identity mode):
  ```
  python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision9_coordination.py --class Revision9BindingTests \
    --methods setUp,binding --dest tests/_revision9_coord_binding_support.py --shape mixin --target-class Revision9BindingSupport --test-only \
    --test-snapshot .refactor/tests-revision9-coord-binding-c00b-mixin.json --format-imports --manifest .refactor/mixin-revision9-coord-binding.json
  ```
  driver line: `bash .refactor/revision9-coord-binding-cluster.sh c00b-mixin mixin tests/_revision9_coord_binding_support.py Revision9BindingSupport "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord-binding.json"))["mixin"]["methods_csv"])')" "refactor(tests): move setUp and the shared binding helper of Revision9BindingTests to tests/_revision9_coord_binding_support.py (mixin shape, tier 1)"` — gate `--test-mode identity`; then `env -u PYTHONPATH python3 -m unittest tests.test_revision9_coordination` once (brief §4 item 3; the driver's standalone step also runs `tests._revision9_coord_binding_support`, which imports and collects nothing, `Ran 0 tests`).
- expected mixin header (helpers' globals `Path, subprocess, tempfile` from `setUp`; `journal, key` from `binding`; no decorators; no `import unittest` because a mixin has no bases): `from __future__ import annotations` / `import subprocess` / `import tempfile` / `from pathlib import Path` / `from tests._revision9_coord_constants import key` / `from codex_orchestrator import journal` / `class Revision9BindingSupport:` = 7 lines + 24 = **31**. The constants import precedes the `codex_orchestrator` import (isort ruling 212ccc7), so the module bootstraps `scripts/` by itself.
- source after c00b: gains `from tests._revision9_coord_binding_support import Revision9BindingSupport` (inserted with the other `from tests.` imports, as c00 inserted its line at the same spot: `dryrun-revision9-coord-c00-mixin.txt:14`), class header becomes `class Revision9BindingTests(Revision9BindingSupport, unittest.TestCase):`; `remove_imports` **absent** (`subprocess` keeps its reader at L2347; `tempfile` keeps L30 and L2379; `Path` many).
- **Family-private helpers (9, 877 lines):** `binding_resolver`: `_write_commit_gate_binding_chain`, `_write_commit_decision_cycle_chain`; `binding_replay`: `correlation_records`, `issue_for`, `_relined`, `_superseded_set`, `_with_control_removed`, `_semantic_state`, `_write_semantic_chain`; `binding_shape`: none. Private-to-private calls: `_write_commit_decision_cycle_chain` -> `_write_commit_gate_binding_chain` (both `binding_resolver`); `_write_semantic_chain` -> `_semantic_state` (both `binding_replay`). Private-to-mixin calls: `correlation_records`, `_superseded_set`, `_write_semantic_chain` -> `binding`.
- **Source-retained helpers:** none. **Dead-code candidates:** none.

## 3. Target modules

### 3.0 Common to every family (the driver `.refactor/revision9-coord-binding-cluster.sh` implements exactly this)

- **Driver and id-map generator** — mechanical copies of the first wave's, made by the orchestrator before the prep commit (tested by the planner on scratch copies: `bash -n` clean; the id-map copy compiled and produced 5 + 5 entries for `binding_shape` from `tests-revision9-coord-c12-ledger_recovery.json`):
  ```
  sed -e 's/revision9-coord-/revision9-coord-binding-/g' \
      -e 's/mixin-revision9-coord\.json/mixin-revision9-coord-binding.json/' \
      -e 's/decompose-records-revision9-coord\.json/decompose-records-revision9-coord-binding.json/g' \
      -e 's/^CLASS=Revision9BuilderBatchTests$/CLASS=Revision9BindingTests/' \
      -e 's|"$idmap" "$methods" \|\||"$idmap" "$methods" "$CLASS" \|\||' \
      -e 's/Per-cluster driver for the test_revision9_coordination split/Per-cluster driver for the Revision9BindingTests split of test_revision9_coordination/' \
      .refactor/revision9-coord-cluster.sh > .refactor/revision9-coord-binding-cluster.sh
  sed -e 's/^snapshot_path, stem, cls, out_path, tests_csv = sys.argv\[1:6\]$/snapshot_path, stem, cls, out_path, tests_csv, old_class = sys.argv[1:7]/' \
      -e 's/^old_class = "Revision9BuilderBatchTests"$/# old_class comes from argv[6] (Revision9BindingTests for the binding wave)/' \
      -e 's/usage: revision9-coord-idmap.py <snapshot.json> <family-stem> <FamilyClass> <out.json> <test,...>/usage: revision9-coord-binding-idmap.py <snapshot.json> <family-stem> <FamilyClass> <out.json> <test,...> <OldClass>/' \
      -e 's/for one family of the test_revision9_coordination split/for one family of the Revision9BindingTests split of test_revision9_coordination/' \
      .refactor/revision9-coord-idmap.py > .refactor/revision9-coord-binding-idmap.py
  ```
  Resulting driver differences (the whole diff, verified): header comment/usage; `CLASS=Revision9BindingTests`; `REC=$R/decompose-records-revision9-coord-binding.json`; `log="$R/driver-revision9-coord-binding-$label.txt"`; `ids="$R/tests-revision9-coord-binding-$label.json"`; `bodies="$R/revision9-coord-binding-$label-before.json"`; manifests `$R/mixin-revision9-coord-binding.json` / `$R/family-revision9-coord-binding-${label#*-}.json`; `idmap="$R/idmap-revision9-coord-binding-${label#*-}.json"` built by `python3 "$R/revision9-coord-binding-idmap.py" "$ids" "$stem" "$cls" "$idmap" "$methods" "$CLASS"`; evidence `dryrun-`/`apply-`/`gate-`/`standalone-revision9-coord-binding-$label.txt`; both record snippets read `.refactor/decompose-records-revision9-coord-binding.json`; the commit-message `Gate:` line names the `-binding-` gate file. Everything else (env exports incl. `REFACTOR_MAX_LINES=1000` and `REFACTOR_TEST_CMD`, clean-tree check, snapshots, dry run, apply, `verify.sh`, file-length guard, production-path check, standalone-import check, record, commit, amend) is unchanged. The id-map generator keeps its filter to `test_`-prefixed names, so private helpers in a csv never enter a map, and still refuses a test missing from the snapshot in either collector.
- Precondition: c00b committed with exactly `setUp,binding` (the class header reads `class Revision9BindingTests(Revision9BindingSupport, unittest.TestCase)`; the class body contains only `def`s: 15 tests and 9 private helpers). Before c00b a class-shape dry run of `binding_shape` or `binding_replay` is refused with `sibling class would lose calls to remaining methods` (`binding` still a class method; move_methods.py:326); after c00b every family passes that check because its members call only methods in the same csv or mixin methods, whichever order the families run in. Tracked tree clean; destination absent; manifest path absent.
- Fresh snapshots first: `python3 $D/collect_tests.py snapshot --start tests --out .refactor/tests-revision9-coord-binding-<label>.json` and `python3 $S/snapshot_bodies.py snapshot tests --out .refactor/revision9-coord-binding-<label>-before.json`.
- Id map: `.refactor/revision9-coord-binding-idmap.py <fresh snapshot> test_revision9_coordination_<family> Revision9<Family>Tests .refactor/idmap-revision9-coord-binding-<family>.json <methods csv> Revision9BindingTests`. Shape (spellings verified against the c12 snapshot, which holds all 15 old IDs in both collectors):
  ```json
  {"unittest": {"test_revision9_coordination.Revision9BindingTests.<t>": "test_revision9_coordination_<family>.Revision9<Family>Tests.<t>"},
   "pytest":   {"tests/test_revision9_coordination.py::Revision9BindingTests::<t>": "tests/test_revision9_coordination_<family>.py::Revision9<Family>Tests::<t>"}}
  ```
  Exactly the family's tests in both collectors; `settings.pinned` and `shards` are empty, so no pinned ID or shard membership exists to preserve; `compare` still requires injective values and an exact multiset match.
- Mover, dry run then apply (identical argv plus `--apply`):
  ```
  python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision9_coordination.py \
    --class Revision9BindingTests --methods <csv> --dest tests/test_revision9_coordination_<family>.py \
    --shape class --target-class Revision9<Family>Tests --test-only --test-snapshot .refactor/tests-revision9-coord-binding-<label>.json \
    --id-map .refactor/idmap-revision9-coord-binding-<family>.json --format-imports --manifest .refactor/family-revision9-coord-binding-<family>.json
  ```
- Expected diff per family: the listed `def`s deleted from the source class (nothing else in the source body changes); the source import block loses only what §5 schedules (`import subprocess` at c03b, nothing else); the destination is a new module with the header listed in the family section, then `class Revision9<Family>Tests(Revision9BindingSupport, unittest.TestCase):` holding the methods **in csv order** (`moved.sort(key=methods.index)`, move_methods.py:398; every csv below is in source order). Bodies, docstrings (7 method docstrings, all in `binding_replay` and `binding_resolver`), nested `def`s with their `nonlocal` statements, verbatim. No `__all__`, no class docstring, no `if __name__ == "__main__"` block (the mover never emits one; handover line as in the first wave).
- Header order under the isort ruling: stdlib, then the first-party `tests.*` block, then the local-folder `codex_orchestrator` block. Inside the `tests.*` block `tests._revision9_coord_binding_support` sorts **before** `tests._revision9_coord_constants` (unlike the first wave, where `_constants` came before `_support`); the bootstrap still holds because the support module's own header imports the constants module before `codex_orchestrator` (§2b). The driver's standalone step proves it per module.
- Gate: `bash $S/verify.sh --pkg tests --snapshot <bodies> --manifest <manifest> --strict-bodies --test-snapshot <ids> --test-mode mapping`, the repository guard, the production-path check, the standalone import. Commit on PASS only. Test count printed by the gate's test step: **144**.
- Commit subject: `refactor(tests): move the <family> scenario family of Revision9BindingTests to tests/test_revision9_coordination_<family>.py (class shape, tier 1)`.
- Tier: 1 (relocation). Refusals expected: none. Stop conditions: brief §8.

### 3.1 Family overview

| # | label | module | class | tests | private helpers | test lines + helper lines = code lines | header lines | est. module code lines | inventory clusters merged |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `c01b-binding_shape` | `tests/test_revision9_coordination_binding_shape.py` | `Revision9BindingShapeTests` | 5 | 0 | 536 + 0 = 536 | 8 | **544** | 3, 4 |
| 2 | `c02b-binding_resolver` | `tests/test_revision9_coordination_binding_resolver.py` | `Revision9BindingResolverTests` | 3 | 2 | 136 + 584 = 720 | 9 | **729** | 2 |
| 3 | `c03b-binding_replay` | `tests/test_revision9_coordination_binding_replay.py` | `Revision9BindingReplayTests` | 7 | 7 | 449 + 293 = 742 | 10 | **752** | 1 (minus `setUp`), 5, 6, 7, 9, 10 |
| | | | **total** | **15** | **9** | **1,121 + 877 = 1,998** | | | |
| c00b | `c00b-mixin` | `tests/_revision9_coord_binding_support.py` | `Revision9BindingSupport` (mixin) | 0 | 2 shared (24) | 24 | 7 | **31** | 1 (`setUp`), 8 |

"header lines" = import statements + the class line, exactly as listed per family (the c00 calibration of the first wave: predicted = measured).

Per-test table (HEAD lines, code lines, inventory cluster, family):

| test | HEAD lines | code | cluster | family |
|---|---|---|---|---|
| `test_resolver_rejects_stale_and_result_mismatched_gate_bindings` | L885-939 | 53 | 2 | `binding_resolver` |
| `test_resolver_rejects_recreated_approval_and_skip_facts` | L941-995 | 54 | 2 | `binding_resolver` |
| `test_resolver_rejects_candidate_cycles_retaining_decision_facts` | L997-1025 | 29 | 2 | `binding_resolver` |
| `test_dm001_exact_shape_candidate_and_review_vectors` | L1027-1116 | 86 | 3 | `binding_shape` |
| `test_commit_candidate_binding_reconstructs_v2_without_relabeling_history` | L1118-1192 | 72 | 4 | `binding_shape` |
| `test_commit_identity_binding_projects_existing_verification_type` | L1194-1303 | 109 | 3 | `binding_shape` |
| `test_binding_currentness_rejects_superseded_gate_facts` | L1305-1509 | 202 | 3 | `binding_shape` |
| `test_binding_currentness_rejects_superseded_review_tuple` | L1511-1577 | 67 | 3 | `binding_shape` |
| `test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task` | L1629-1684 | 51 | 5 | `binding_replay` |
| `test_fr021_superseded_candidate_records_are_retired` | L1729-1916 | 172 | 6 | `binding_replay` |
| `test_fr021_precedence_rule_scopes_to_the_landed_candidate` | L1918-1973 | 53 | 6 | `binding_replay` |
| `test_fr021_post_landing_result_moves_no_boundary` | L1975-2069 | 89 | 6 | `binding_replay` |
| `test_fr021_four_exact_correlation_issues_and_disabled_control` | L2071-2108 | 33 | 7 | `binding_replay` |
| `test_commit_and_merge_replay_reject_invented_self_consistent_transitions` | L2319-2341 | 23 | 1 | `binding_replay` |
| `test_commit_and_merge_replay_reject_digest_valid_candidate_rollback` | L2343-2370 | 28 | 1 | `binding_replay` |

### 3.2 c01b — `binding_shape` -> `tests/test_revision9_coordination_binding_shape.py`, class `Revision9BindingShapeTests`

- theme: binding shape and currentness vectors — the DM-001 exact-shape candidate/review vectors, the commit-candidate v2 reconstruction without relabeling history, the identity binding projecting an existing verification type, and binding currentness rejecting superseded gate facts and a superseded review tuple (`journal._binding_shape_valid`, `builders._binding_is_current`, `builders._candidate_binding_for_state`, `builders.tombstone_abort_binding`, `journal._git_tree_candidate_authorization_id`).
- tests (5, source order = requested order): `test_dm001_exact_shape_candidate_and_review_vectors` L1027-1116 86 (cluster 3); `test_commit_candidate_binding_reconstructs_v2_without_relabeling_history` L1118-1192 72 (cluster 4); `test_commit_identity_binding_projects_existing_verification_type` L1194-1303 109 (cluster 3); `test_binding_currentness_rejects_superseded_gate_facts` L1305-1509 202 (cluster 3); `test_binding_currentness_rejects_superseded_review_tuple` L1511-1577 67 (cluster 3).
- private helpers: none.
- methods csv (source order): `test_dm001_exact_shape_candidate_and_review_vectors,test_commit_candidate_binding_reconstructs_v2_without_relabeling_history,test_commit_identity_binding_projects_existing_verification_type,test_binding_currentness_rejects_superseded_gate_facts,test_binding_currentness_rejects_superseded_review_tuple`
- code lines: tests **536** + private helpers **0** = **536**; header 8; estimated module code lines **544**; provisional baseline entry **590** (§6).
- mixin helpers inherited: `binding` (4 tests; the v2 test calls no helper), `setUp`.
- module globals read by the bodies (inventory `globals`, union): `builders`, `copy`, `journal`, `key`, `mock`.
- expected destination header (the dry-run manifest `imports[dest]` is the record): `from __future__ import annotations` / `import copy` / `import unittest` / `from unittest import mock` / `from tests._revision9_coord_binding_support import Revision9BindingSupport` / `from tests._revision9_coord_constants import key` / `from codex_orchestrator import builders, journal`.
- subTest users: `test_commit_candidate_binding_reconstructs_v2_without_relabeling_history`. Nested defs: none. `mock.patch.object(journal, "BINDING_CANDIDATE_KINDS", ...)` at L1111 patches a module attribute, not a class method.
- source `remove_imports`: none (§5).
- driver line: `bash .refactor/revision9-coord-binding-cluster.sh c01b-binding_shape class tests/test_revision9_coordination_binding_shape.py Revision9BindingShapeTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord-binding.json"))["families"]["binding_shape"]["methods_csv"])')" "refactor(tests): move the binding_shape scenario family of Revision9BindingTests to tests/test_revision9_coordination_binding_shape.py (class shape, tier 1)"`
- id map: 5 unittest + 5 pytest entries; first entry `test_revision9_coordination.Revision9BindingTests.test_dm001_exact_shape_candidate_and_review_vectors` -> `test_revision9_coordination_binding_shape.Revision9BindingShapeTests.test_dm001_exact_shape_candidate_and_review_vectors`.
- note: first family on purpose — no private helpers, so the diff is five deleted tests, one new module, and the inherited `binding`; the operator reads it by hand before c02b.
- expected refusals: none.

### 3.3 c02b — `binding_resolver` -> `tests/test_revision9_coordination_binding_resolver.py`, class `Revision9BindingResolverTests`

- theme: `builders.resolve_binding` refusals over receipted commit-chain histories — stale and result-mismatched gate bindings, recreated approval and skip facts, candidate cycles retaining decision facts — with the two chain writers that build those histories.
- tests (3, source order): `test_resolver_rejects_stale_and_result_mismatched_gate_bindings` L885-939 53 (cluster 2); `test_resolver_rejects_recreated_approval_and_skip_facts` L941-995 54 (cluster 2); `test_resolver_rejects_candidate_cycles_retaining_decision_facts` L997-1025 29 (cluster 2).
- private helpers (2, source order, both before the tests): `_write_commit_gate_binding_chain` L273-523 242 (nested `append_event`, `nonlocal previous`; docstring); `_write_commit_decision_cycle_chain` L525-883 342 (calls `_write_commit_gate_binding_chain`; nested `next_at`/`append_event`/`prepare_approval`/`restage` with `nonlocal minute`/`previous`/`state`; docstring).
- methods csv (source order): `_write_commit_gate_binding_chain,_write_commit_decision_cycle_chain,test_resolver_rejects_stale_and_result_mismatched_gate_bindings,test_resolver_rejects_recreated_approval_and_skip_facts,test_resolver_rejects_candidate_cycles_retaining_decision_facts`
- code lines: tests **136** + private helpers **584** = **720**; header 9; estimated module code lines **729**; provisional baseline entry **770** (§6).
- mixin helpers inherited: `setUp` only (no test or helper here calls `binding`).
- module globals read (union): `builders`, `copy`, `journal`, `json`, `key`, `mock`.
- expected destination header: `from __future__ import annotations` / `import copy` / `import json` / `import unittest` / `from unittest import mock` / `from tests._revision9_coord_binding_support import Revision9BindingSupport` / `from tests._revision9_coord_constants import key` / `from codex_orchestrator import builders, journal`.
- subTest users: all three tests. `mock.patch.object(builders, "_verify_receipted_batch")` (L911, L954, L1002) patches a module attribute.
- source `remove_imports`: none (`json` keeps 5 readers outside the class, §5).
- driver line: `bash .refactor/revision9-coord-binding-cluster.sh c02b-binding_resolver class tests/test_revision9_coordination_binding_resolver.py Revision9BindingResolverTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord-binding.json"))["families"]["binding_resolver"]["methods_csv"])')" "refactor(tests): move the binding_resolver scenario family of Revision9BindingTests to tests/test_revision9_coordination_binding_resolver.py (class shape, tier 1)"`
- id map: 3 unittest + 3 pytest entries; first entry `test_revision9_coordination.Revision9BindingTests.test_resolver_rejects_stale_and_result_mismatched_gate_bindings` -> `test_revision9_coordination_binding_resolver.Revision9BindingResolverTests.test_resolver_rejects_stale_and_result_mismatched_gate_bindings`.
- note: the two helpers are 81 % of the module; they are read by no other family (§2b), so they are private by the rule, not by choice. The private-to-private call `_write_commit_decision_cycle_chain` -> `_write_commit_gate_binding_chain` stays inside the csv, so the order check passes.
- expected refusals: none.

### 3.4 c03b — `binding_replay` -> `tests/test_revision9_coordination_binding_replay.py`, class `Revision9BindingReplayTests`

- theme: replay-time binding checks over a run's records and a chain's events — the FR-021 binding-correlation issues (`journal._check_binding_correlation` via `issue_for` over `correlation_records`: abort retirement, superseded candidate sets, the precedence rule, post-landing results, the four exact issues and the disabled `BINDING_CORRELATION_CONTROLS` control) and the commit/merge chain-replay refusals of invented self-consistent transitions and digest-valid candidate rollback (`_semantic_state`, `_write_semantic_chain`, `builders.resolve_binding`).
- tests (7, source order): `test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task` L1629-1684 51 (cluster 5); `test_fr021_superseded_candidate_records_are_retired` L1729-1916 172 (cluster 6); `test_fr021_precedence_rule_scopes_to_the_landed_candidate` L1918-1973 53 (cluster 6); `test_fr021_post_landing_result_moves_no_boundary` L1975-2069 89 (cluster 6); `test_fr021_four_exact_correlation_issues_and_disabled_control` L2071-2108 33 (cluster 7); `test_commit_and_merge_replay_reject_invented_self_consistent_transitions` L2319-2341 23 (cluster 1); `test_commit_and_merge_replay_reject_digest_valid_candidate_rollback` L2343-2370 28 (cluster 1).
- private helpers (7, source order, interleaved): `correlation_records` L1579-1622 44 (cluster 9; calls `binding`); `issue_for` L1624-1627 4 (cluster 10); `_relined` L1686-1689 4 (cluster 6); `_superseded_set` L1691-1721 31 (cluster 6; calls `binding`); `_with_control_removed` L1723-1727 5 (cluster 6; returns `mock.patch.object(journal, "BINDING_CORRELATION_CONTROLS", ...)`); `_semantic_state` L2110-2174 65 (cluster 1); `_write_semantic_chain` L2176-2317 140 (cluster 1; calls `_semantic_state`, `binding`).
- methods csv (source order): `correlation_records,issue_for,test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task,_relined,_superseded_set,_with_control_removed,test_fr021_superseded_candidate_records_are_retired,test_fr021_precedence_rule_scopes_to_the_landed_candidate,test_fr021_post_landing_result_moves_no_boundary,test_fr021_four_exact_correlation_issues_and_disabled_control,_semantic_state,_write_semantic_chain,test_commit_and_merge_replay_reject_invented_self_consistent_transitions,test_commit_and_merge_replay_reject_digest_valid_candidate_rollback`
- code lines: tests **449** + private helpers **293** = **742**; header 10; estimated module code lines **752**; provisional baseline entry **800** (§6).
- mixin helpers inherited: `binding` (5 tests directly, plus via `correlation_records`/`_superseded_set`/`_write_semantic_chain`), `setUp`.
- module globals read (union of tests and private helpers): `Path`, `builders`, `copy`, `journal`, `key`, `mock`, `subprocess`.
- expected destination header: `from __future__ import annotations` / `import copy` / `import subprocess` / `import unittest` / `from pathlib import Path` / `from unittest import mock` / `from tests._revision9_coord_binding_support import Revision9BindingSupport` / `from tests._revision9_coord_constants import key` / `from codex_orchestrator import builders, journal`.
- subTest users: the two `test_commit_and_merge_replay_*` tests. Docstrings: the four FR-021 tests at L1630, L1730, L1919, L1976 and `_superseded_set` at L1692 (verbatim; the other two of the class's seven are the resolver writers' at L281 and L533). Nested defs: none. State: `test_commit_and_merge_replay_reject_digest_valid_candidate_rollback` re-assigns `self.repo` to a second `git init` repo under `self.temporary` (L2344-2349) — instance state, unchanged by relocation.
- source `remove_imports`: **`subprocess`** — its two readers were `setUp` (left at c00b) and this family's rollback test (L2347); no reader outside the class (§5). Expected manifest: `remove_imports[source] == ["subprocess"]`.
- driver line: `bash .refactor/revision9-coord-binding-cluster.sh c03b-binding_replay class tests/test_revision9_coordination_binding_replay.py Revision9BindingReplayTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord-binding.json"))["families"]["binding_replay"]["methods_csv"])')" "refactor(tests): move the binding_replay scenario family of Revision9BindingTests to tests/test_revision9_coordination_binding_replay.py (class shape, tier 1)"`
- id map: 7 unittest + 7 pytest entries; first entry `test_revision9_coordination.Revision9BindingTests.test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task` -> `test_revision9_coordination_binding_replay.Revision9BindingReplayTests.test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task`.
- note: last family, the only one with a source-side import removal and the one that empties the class (§3.5).
- expected refusals: none.

### 3.5 Stays in `tests/test_revision9_coordination.py`

| symbol | reason |
|---|---|
| `class Revision9BindingTests(Revision9BindingSupport, unittest.TestCase): pass` (the shell) | After c03b every method has left. The mover keeps the class statement and writes a `pass` body (`move_methods.py:402-403`: `body=retained or [cst.parse_statement('pass\n')]`); it never deletes a class. The shell has no tests (no ID in either collector; `Ran 144` unchanged), keeps reading `Revision9BindingSupport` and `unittest` (so the support import is not `F401`), and trips no selected ruff rule (`select = E, F, I, B, UP, C90, PLR0904/0911/0912/0913/0915/1702`; no `PIE790`). Removing the shell and its support import would be a hand edit of the source — **not** part of this wave (brief §4: the constants module is the only hand-written commit); name it in the handover as finalize/operator work. |
| `Revision9FixtureTests` (L28-161), the `Revision9BuilderBatchTests` shell (L162-245, one skipUnless test), `Revision9MergeTransitionGrammarTests` (L2373-5150) | never in this class's scope; the grammar class is the next class-shape target of the bead (inventory `.refactor/inventory-revision9-coord-grammar.json` at HEAD, planned separately after this wave closes green). |
| module preamble (imports L1-25, `sys.path.insert`, `if __name__ == "__main__"` L5152-5153) | shell; only the §5 import removal (`subprocess` at c03b) and the c00b support-import insertion touch it. |
| tests / helpers | **none stay**: 15/15 tests and 11/11 helpers are placed (§2b, §3.1). |

## 4. State ownership table

| state | owner module | users |
|---|---|---|
| `self.temporary`, `self.repo` (instance attributes written by `setUp` L248-250; `addCleanup(self.temporary.cleanup)`) | `tests/_revision9_coord_binding_support.py` (mixin, after c00b) | every family (inherited `setUp`); `binding_replay`'s rollback test re-assigns `self.repo` per subTest (L2344-2349) |
| module constant `key` (and `FIXTURES`, `JOURNAL_FIXTURE_SHA256`, `OUTPUT_FIXTURE_SHA256`, `ROOT`, unread by this class) | `tests/_revision9_coord_constants.py` (455e436) | the mixin (`binding`) and all three families import `key`; nothing else from the constants module is read by this class |
| `sys.path.insert(0, str(ROOT / "scripts"))` | executed by `tests/_revision9_coord_constants.py` on import and by the source module | families and mixin bootstrap through the constants module (§3.0 header-order note) |
| no mutable module-level assignment, no `global` statement, no class-body statement in the class or the families (inventory `writes`: only `repo`, `temporary`) | — | — |

## 5. Waves and the source-import removal schedule

Class shape is strictly sequential (one source file, one commit per family, fresh snapshot each time). Wave 0 = c00b (mixin `setUp,binding`). Wave 1 = c01b..c03b in this order:

| order | label | first member line | why here |
|---|---|---|---|
| 1 | `c01b-binding_shape` | L1027 | no private helpers: the inspection diff (5 tests, inherited `binding`) |
| 2 | `c02b-binding_resolver` | L273 | source order of the remaining two; carries the two 240+ line writers with `nonlocal` nested defs |
| 3 | `c03b-binding_replay` | L1579 | source order; the only source import removal (`subprocess`); empties the class (§3.5) |

Readers of every name the source imports, counted at HEAD **outside** L246-2370 with python (`(?<![\w.])name(?![\w])`, excluding the import statements themselves) and inside the class:

| source import name | statement | readers outside the class | readers inside the class (unit) | removed in |
|---|---|---|---|---|
| `subprocess` | `import subprocess` (L8) | **0** | 2: `setUp` L251 (c00b), `test_commit_and_merge_replay_reject_digest_valid_candidate_rollback` L2347 (c03b) | **c03b** |
| `tempfile` | `import tempfile` (L10) | 2 (L30 `Revision9FixtureTests.setUp`, L2379 `Revision9MergeTransitionGrammarTests.setUp`) | 1: `setUp` L248 (c00b) | never |
| `json` | `import json` (L5) | 5 (L40, L75, L76, ... Fixture/Grammar classes) | 2: `_write_commit_decision_cycle_chain` (c02b) | never |
| `copy` | `import copy` (L2) | 139 | 84 | never |
| `Path` | `from pathlib import Path` (L12) | 12 | 2 (c00b, c03b) | never |
| `mock` | `from unittest import mock` (L13) | 6 | 6 | never |
| `builders` / `journal` | `from codex_orchestrator import batch, builders, journal  # noqa: E402` (L25) | 116 / 34 | 27 / 78 | never |
| `batch` | same statement | 6 | 0 | never (not read by this class) |
| `key` | `from tests._revision9_coord_constants import (...)` (L16-21) | 74 | 54 | never |
| `FIXTURES`, `JOURNAL_FIXTURE_SHA256`, `OUTPUT_FIXTURE_SHA256`, `ROOT` | same statement | 3 / 1 / 1 / 1 | 0 | never |
| `dt`, `hashlib`, `os`, `shutil`, `sys`, `unittest`, `Revision9BuilderBatchSupport` | L3, L4, L6, L7, L9, L11, L22 | 1 / 2 / 15 / 1 / 1 / 5 / 1 | 0 (`unittest` 1: the class line) | never |

Expected `remove_imports[source]` (sequential): c00b **absent** · c01b **absent** · c02b **absent** · c03b **`["subprocess"]`**. A missed removal is an `F401` in the source (fails ruff); an extra removal breaks a remaining body. The dry-run manifest is authoritative; a deviation from this table is a finding to investigate before apply, not a reason to edit an import by hand. The source gains one import at c00b (`from tests._revision9_coord_binding_support import Revision9BindingSupport`) and loses none until c03b.

Wave close (after c03b): the Gate 1 cell once via `until [ "$(cut -d. -f1 /proc/loadavg)" -lt 24 ]; do sleep 120; done; flock /dev/shm/refactor-gate1.lock bash .refactor/gate1-revision9-coord.sh binding-wave-close` (the script runs without `PYTHONPATH`, brief §6).

## 6. Provisional `.refactor-baseline.json` entries (config-only commit **before c00b**; brief §4 item 1)

Two prep commits, both before c00b, in the first wave's form: (i) a docs/evidence commit adding this plan, `families-revision9-coord-binding.json`, `inventory-revision9-coord-binding.{json,md}`, `revision9-coord-binding-cluster.sh`, `revision9-coord-binding-idmap.py` (precedent: d6c3bc3, a2f86cb); (ii) the config-only baseline commit (precedent 2da3f4e, `chore(tests): provisional .refactor-baseline.json entries for the Revision9BindingTests split modules (config-only prep)`), needed because `scripts/check_file_length.py` defaults to 500 without `REFACTOR_MAX_LINES` and `.pre-commit-config.yaml` passes only `--baseline`, so on main every new module over 500 needs its entry before the commit that creates it. Entries for not-yet-created files are inert. No ruff change: the globs `tests/test_revision9_coordination_*.py` and `tests/_revision9_coord_*.py` (pyproject L254-255) already cover the three families and the mixin; the isort ruling (pyproject L47-48) is already applied. Values = estimate + 40, rounded up to the next 10 (the executed wave measured headers within 12..22 lines of the estimates and never above; here the header is listed line by line, so +40 is margin, not uncertainty):

```
"tests/test_revision9_coordination_binding_shape.py": 590,
"tests/test_revision9_coordination_binding_resolver.py": 770,
"tests/test_revision9_coordination_binding_replay.py": 800,
```

No entry for `tests/_revision9_coord_binding_support.py` (~31 lines). **Preferred, as the first-wave critique ruled:** once c00b is committed, dry-run all three families in one pass (dry runs write nothing; family sizes are order-independent), count the code lines of each `+++ tests/test_revision9_coordination_binding_<family>.py` hunk, and commit those measured values instead. Finalize replaces whichever values were used with the measured sizes (shrink-only) and re-measures the source entry (`tests/test_revision9_coordination.py`: 13222 today, ≈ 2,909 after this wave) downward.

## 7. Re-exports required in `__init__.py`

None. `tests/` is a namespace directory; nothing imports `Revision9BindingTests` or any of its methods by name (census 0; grep §0). `__all__` does not exist in these files and must not be created.

## 8. Quality / debt report (`quality.py` expectations, `.refactor-quality.json`: module 500/1,000, function 150, class 30, parameters 6)

- Module target/ceiling: all three families land between target and ceiling (544, 729, 752) -> a debt row each in `.refactor/debt-revision9-coord.json` (brief §7 spelling; reason "scenario family of a 15-test class; 500..1,000 per brief §4", follow-up: finalize measurement and the handover bead). The mixin (~31) is under target by design (support module). Nothing over the ceiling.
- Function target 150: four methods exceed it unchanged by relocation — `_write_commit_decision_cycle_chain` 342 and `_write_commit_gate_binding_chain` 242 (`binding_resolver`), `test_binding_currentness_rejects_superseded_gate_facts` 202 (`binding_shape`), `test_fr021_superseded_candidate_records_are_retired` 172 (`binding_replay`). Extraction candidates for a later tier-2 pass, never a cluster edit.
- Class method target 30: `binding_replay` 14 methods, `binding_resolver` 5, `binding_shape` 5, mixin 2.
- Parameters ≤ 6: `binding` 5 (`seed`, `candidate`, `review`, `chain_id` + self), `_write_commit_gate_binding_chain` 4, `_write_commit_decision_cycle_chain` 4, `_semantic_state` 3, `_write_semantic_chain` 3; no test takes parameters.
- Cohesion: every family shares a scenario and (except `binding_shape`, which shares the hub `binding` and the `builders._binding_*` API) at least one private helper; the one test with no helper calls (`test_commit_candidate_binding_reconstructs_v2_without_relabeling_history`) is placed by subject (§2).
- Ruff: the temporary globs cover the relocated complexity codes without `I001`; finalize replaces them with measured per-module entries (expected subsets of `B023, B905, C901, E501, E702, E731, F841, PLR0912, PLR0913, PLR0915, PLR1702, UP012`; `PLR0904` cannot trip). No family module gets `E402`, `F401` or `I001`.

## 9. Risks the reviewer must check

- **R1 id-map 1:1 and injectivity.** Per family `len(map.unittest) == len(map.pytest) == len(tests)` (5 / 3 / 7); keys are members of the fresh snapshot; values spelled `test_revision9_coordination_<family>.Revision9<Family>Tests.<t>` / `tests/test_revision9_coordination_<family>.py::Revision9<Family>Tests::<t>`; after apply the collectors report exactly the mapped IDs (gate `test-identities` PASS in `mapping` mode) and 1,908 IDs per collector. The parameterised generator refuses a test missing from the snapshot in either collector and receives the old class name as its 6th argument — a driver line that omits `"$CLASS"` fails at `sys.argv[1:7]` unpacking (`ValueError`), which the driver reports as `FAIL: id map`.
- **R2 driver/id-map copies.** Compare `.refactor/revision9-coord-binding-cluster.sh` against §3.0's diff list before c00b (`diff .refactor/revision9-coord-cluster.sh .refactor/revision9-coord-binding-cluster.sh` must show exactly those lines); a copy that still says `CLASS=Revision9BuilderBatchTests` is refused by the mover at c00b with `unknown method: setUp` (move_methods.py resolves `--methods` against the named class's own defs; the `Revision9BuilderBatchTests` body defines neither `setUp`, inherited from its mixin, nor `binding`, defined only at L253 of `Revision9BindingTests`), and a copy that still writes `mixin-revision9-coord.json` would collide with the first wave's tracked manifest.
- **R3 c00b method list is load-bearing.** If c00b moves anything beyond `setUp,binding`, a private helper becomes inherited by every family (allocation record diverges); if it omits `binding`, c01b and c03b are refused with `sibling class would lose calls to remaining methods`. Compare `mixin-revision9-coord-binding.json` `methods` with `families-revision9-coord-binding.json` `mixin.methods` before c01b.
- **R4 header order and bootstrap.** Unlike the first wave, `tests._revision9_coord_binding_support` sorts before `tests._revision9_coord_constants` in every family header. Bootstrap holds because the mixin module imports the constants module before `codex_orchestrator` (§2b header). Verify on the c00b dry run that the mixin header has `from tests._revision9_coord_constants import key` **above** `from codex_orchestrator import journal`; the driver's standalone step (`env -u PYTHONPATH -u MYPYPATH python3 -m unittest tests.<stem>`) is the per-module proof.
- **R5 the emptied class.** After c03b the source holds `class Revision9BindingTests(Revision9BindingSupport, unittest.TestCase):` + `pass` (§3.5). Check the c03b dry-run diff shows exactly that shell (no syntax error, no deleted class statement, support import retained), `ruff check tests/test_revision9_coordination.py` clean, and both collectors still count 144 focused / 1,908 total. The shell is a handover item, not a wave edit.
- **R6 source import removal.** Only c03b removes anything, and only `import subprocess` (§5). A c00b manifest with a `remove_imports` key, or a c03b manifest with anything other than `["subprocess"]`, is a deviation to investigate before apply.
- **R7 reflection on the class.** `grep` of L246-2370 for `self.__class__`, `type(self)`, `__module__`, `__qualname__`, `__name__`, `__file__`, `getattr(self`, `setattr(self`: **0 hits** (the only BRE match, `..._verification_type(self)` at L1194, is a method name containing the substring `type(self)`, checked by eye). No method name of this class appears as a string literal: the `"binding"` literals (L462, L717, L1603-1747, ...) are record field names and `mock.patch.object` targets are `builders._verify_receipted_batch`, `journal.BINDING_CANDIDATE_KINDS`, `journal.BINDING_CORRELATION_CONTROLS` — module attributes.
- **R8 fixture strings / threads.** No triple-quoted raw string, no `textwrap`, no `threading`, no `time.sleep` in the class. Two `subprocess.run(["git", "init", ...])` calls (L251 setUp, L2347) — deterministic, no timing sensitivity. `tempfile.TemporaryDirectory(prefix="forge-revision9-binding-")` in `setUp` moves with it.
- **R9 subTest.** 6 tests use `self.subTest` (3 resolver, 1 shape, 2 replay); subTest IDs are not collected IDs, so the maps are unaffected and `Ran 144` is unchanged.
- **R10 nested defs and `nonlocal`.** `_write_commit_gate_binding_chain` (1 nested def, `nonlocal previous`) and `_write_commit_decision_cycle_chain` (4 nested defs, `nonlocal minute/previous/state`) move verbatim by LibCST (`--strict-bodies` in the gate compares bodies byte-for-byte against the snapshot).
- **R11 sizes.** Largest estimate 752 (`binding_replay`), provisional entry 800; the rejected alternative (semantic pair into `binding_resolver`) would be 985 and is not planned. Verify each destination with `python3 scripts/check_file_length.py <dest>` after apply (the driver does) and compare with §3.1.
- **R12 order and freshness.** Each family's `--test-snapshot` is the snapshot taken at the merged head immediately before its dry run; never reuse a first-wave snapshot or c00b's for a family; the driver names each `tests-revision9-coord-binding-<label>.json`.
- **R13 private helpers are not inheritable.** A helper moved with a family is defined on that family's sibling class only; the private-to-private calls (`_write_commit_decision_cycle_chain` -> `_write_commit_gate_binding_chain`; `_write_semantic_chain` -> `_semantic_state`) stay within one csv each. Any later re-grouping must re-move the helpers too — a new plan, not an ad-hoc edit.
- **R14 no production change.** `git diff --stat 9b7599a..HEAD -- scripts docs/specs .forge` must be empty after every commit (driver check). The wave touches only `tests/test_revision9_coordination.py`, the four new modules, `.refactor-baseline.json` (prep) and `.refactor/`.
- **R15 name collisions.** `Revision9BindingSupport` contains no `Test`; `Revision9BindingShapeTests`, `Revision9BindingResolverTests`, `Revision9BindingReplayTests` end in `Tests`, are pairwise distinct, and appear nowhere in `tests/` or `scripts/` at HEAD; the three stems collide with none of the 12 existing `test_revision9_coordination_*` modules and match `test_revision9_coordination*.py` (REFACTOR_TEST_CMD), `tests/test_revision9_coordination_*.py` (ruff glob) and `tests/test_*.py` (Gate 1); the mixin stem matches `tests/_revision9_coord_*.py` (ruff) and no discovery pattern.
- **R16 two support mixins in one source.** After c00b the source imports both `Revision9BuilderBatchSupport` and `Revision9BindingSupport`; they share no method and no state, and each is a base of exactly one class. No MRO interaction.

## 10. Summary table

| order | family | module | class | tests | private helpers | est. code lines |
|---|---|---|---|---|---|---|
| c00b | mixin | `tests/_revision9_coord_binding_support.py` | `Revision9BindingSupport` | 0 | 2 shared (24 lines) | 31 |
| 1 | `binding_shape` | `tests/test_revision9_coordination_binding_shape.py` | `Revision9BindingShapeTests` | 5 | 0 (0 lines) | 544 |
| 2 | `binding_resolver` | `tests/test_revision9_coordination_binding_resolver.py` | `Revision9BindingResolverTests` | 3 | 2 (584 lines) | 729 |
| 3 | `binding_replay` | `tests/test_revision9_coordination_binding_replay.py` | `Revision9BindingReplayTests` | 7 | 7 (293 lines) | 752 |
| — | stays | `tests/test_revision9_coordination.py` | `Revision9BindingTests` (empty `pass` shell) | 0 | 0 | source ≈ 2,909 after the wave |

Machine-readable copy (order, csv in source order, expected headers, helpers, sizes, allocation): `.refactor/families-revision9-coord-binding.json`.
