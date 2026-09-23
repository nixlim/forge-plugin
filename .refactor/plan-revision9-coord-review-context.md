# Split plan: tests/test_revision9_coordination.py — class `Revision9BuilderBatchTests` (decompose mode, class shape)

Lane A, session 4, bead forge-plugin-6g67. Planner: split-planner (Fable). Written against inventory `.refactor/inventory-revision9-coord-builder.json` / `-sizes.md` (class_inventory.py at **69bc28d**, class lines 199..8973) and the ID freeze `.refactor/tests-revision9-coord-before.json` (namespace preset, 1,908 IDs per collector, 144 in the focused set). **Line numbers below are inventory (69bc28d) lines.** After 455e436 the preamble is 22 lines shorter (subtract 22); after the c00 mixin commit the helper bodies are gone too, so re-derive lines from the current tree, never from this file. Sizes are `check_file_length.py` code lines (non-blank, non-comment) as the sizes inventory measured them per def.

## 0. Summary

| item | value |
|---|---|
| **Status** | Lane stopped 2026-09-23 before c00 on critique B1 (see `.refactor/STOPPED-revision9-coord.md`); branch head 455e436; relaunch resumes at the provisional-baseline config commit, then c00 via the driver, once the operator has ruled on B1. |
| **Operator decision required before c01 (critique B1)** | Mechanism: `--format-imports` (isort) writes the third-party `from codex_orchestrator import ...` above the first-party `from tests._revision9_coord_*` lines in every family module, and `scripts/` is on `sys.path` only after some module has run `sys.path.insert(0, str(ROOT / "scripts"))` — a family module imported first in a process without `PYTHONPATH` therefore fails at import. Evidence: critique B1 items 1–5 (attempt-1 header order at `dryrun-revision9-coord-c00-mixin-attempt1.txt:1791-1816`; only four test modules bootstrap `scripts/` today; the committed Gate 1 cell shards `sorted(glob("tests/test_*.py"))` round-robin and the simulation puts `test_revision9_coordination_activation_scan` / `_batch_builder` first in shards 2 and 3 with no bootstrapper ahead ⇒ `ModuleNotFoundError: codex_orchestrator` ⇒ `GATE: FAIL`; CI `forge-ci.yml` and the main-clone merge chain run that cell without `PYTHONPATH`; this lane's `gate1-revision9-coord.sh:6` exports `PYTHONPATH` and `REFACTOR_TEST_CMD` discovers the source module first, so in-session gates stay green); `env -u PYTHONPATH python3 -c "import codex_orchestrator"` → `ModuleNotFoundError`. Candidate dispositions, verbatim from the critique, **not chosen here**: (a) config-only: `[tool.ruff.lint.isort] known-local-folder = ["codex_orchestrator", "codex_orch_tools", "forge_cli"]`, which sinks those imports below the first-party `tests.*` block so the constants module bootstraps first; measured cost of the whole-repo re-sort exactly one new `I001` at `tests/test_commitment_paths.py:20`; must land **before c01** (it changes the headers the mover writes) and re-sorts the c00 header if c00 already landed; (b) a `sys.path` bootstrap line per family module = a second hand-written commit (brief §8 item 4); (c) any other operator ruling (e.g. a `PYTHONPATH` export in the Gate 1 cell / CI = control-class change). c00 is unaffected by the choice except for the header re-sort under (a) (806 code lines either way; (b) would add 2–3 lines per family module and require re-measuring the family entries). |
| baseline | 69bc28d (= main); branch `refactor/split-test-revision9-coordination`; prep commits 40ea8c1 (freeze), cc0bfd7 (ruff globs), 455e436 (constants module, hand-written) — all done, not re-planned |
| c00 (re-planned here, §2b) | **18 shared helpers** -> `tests/_revision9_coord_support.py`, mixin `Revision9BuilderBatchSupport`, mixin shape, **791 helper code lines, 806 measured with header** (attempt 1 with all 38 measured 1,623 > ceiling and was reverted; head is still 455e436). The other 20 helpers travel with the single family that uses them, in the same class-shape `--methods` (helpers first). |
| this plan | **12 scenario families**, class shape, one commit each, sequential from the merged head; **108 tests moved** (6,661 test code lines) plus **20 family-private helpers** (808 code lines incl. decorators); **1 test stays** (`unittest.skipUnless`); **0 helpers stay** |
| shape / tier / mode | `--shape class --target-class <Family>Tests --test-only --id-map ... --format-imports --import-root "$PWD"`; tier 1 relocation; gate `--test-mode mapping` |
| modules over 1,000 | **0** (largest estimate 909: `legacy_activation`; mixin 806 measured) |
| modules under 500 | **2** (`cli_diagnostics` ~240: the inspection cluster; `chain_drain` ~436: its only thematic neighbour, `terminal_builder`, would exceed the ceiling once private helpers are counted; reasons in §2) |
| refusals expected | **none** for the 108 tests and 38 helpers (all `ok` or `wrap` — `wrap` = decorated helper, accepted in mixin and class shapes; no test calls a test; every private helper calls only same-family or mixin helpers; every mixin helper calls only mixin helpers; class body has no non-def statements; no destination exists; no family class name appears in the source). The 109th test is not listed anywhere, so it produces no refusal. |
| focused test count | 144 before and after **every** family (`REFACTOR_TEST_CMD = python3 -m unittest discover -s tests -p 'test_revision9_coordination*.py'`; the pattern picks up every `tests/test_revision9_coordination_<family>.py`, never `tests/_revision9_coord_*.py`) |
| source after the wave | ~4,900 code lines (>1,000): keeps `Revision9FixtureTests`, `Revision9BindingTests`, `Revision9MergeTransitionGrammarTests`, the shell of `Revision9BuilderBatchTests` with the one skipUnless test, and `if __name__ == "__main__"` -> baseline entry stays (re-measured downward at finalize) plus a follow-up naming the two remaining classes (§6) |

## 1. Delete first (dead code, with evidence)

None. `vulture` is absent (preflight: optional radon/vulture absent); the inventory has no method with zero readers that is not a collected test; every helper has at least one caller after c00 (`inventory-revision9-coord-builder-sizes.md`, helper call lists). Nothing is deleted in this wave: the brief forbids body, decorator and assertion edits.

## 2. Family rules applied (from brief §4 "Planning rules the critic enforces")

- Families start from the inventory's 37 clusters after hub peeling (hubs: `assertEqual`, `api_environment`, `run_dir`, `_new_repo`, `assertRaisesRegex`, `assertFalse`, `assertTrue`, `start_task`, `subTest`, `repo`, `_open_legacy_run`, `open_run`). Cluster 1 (28 tests, 1,910 lines) and cluster 13 (30 tests, 1,774 lines) are each split along scenario themes visible in the test names and the non-hub helpers they share; the 22 singleton clusters and the 2- and 4-test clusters are merged into the thematically nearest family. The §3 table gives, per test, its inventory cluster so the critic can see every merge and every split.
- Every module is estimated at test lines + private-helper lines (decorator lines included) + 22 header lines (`from __future__`, `import unittest`, 6–12 import lines, the class line). The 10 families between target and ceiling land in 531..909; none can reach 1,000 (the mover adds only header lines, never body lines).
- `cli_diagnostics` (4 tests, ~240) is under 500 **on purpose**: the brief asks for a small, thematically clean first (inspection) cluster; it is the complete CLI/diagnostic-surface scenario (the only readers of `ORCH_TOOLS` and `redirect_stdout`, and two of the four `command` callers) and it exercises, on a 4-test diff the operator can read by hand, the three mover behaviours the later families depend on: copying an aliased import (`import codex_orch_tools as ORCH_TOOLS`), removing an aliased `# noqa: E402` import from the source when its last reader leaves, and trimming a name out of a multi-name `from contextlib import ...`. No other family has a thematic claim on these four tests.
- `chain_drain` (6 tests + 1 private helper, ~436) is under 500 because of the ceiling, not by choice: merged with `terminal_builder` (its only thematic neighbour, same cluster 13 via `_terminal_control_repo`/`_write_bound_chain_state`) the module would carry 894 test lines + 163 private-helper lines + header ≈ 1,090 > 1,000. The split keeps each side one scenario (drain authorization vs. terminal dispositions) and makes `_terminal_control_repo` (12 lines) a shared mixin helper.
- No test is placed for size balance alone; each family section states its theme and which helpers it inherits. Helpers never move again: they are all on the mixin after c00 and are inherited through the copied bases `(Revision9BuilderBatchSupport, unittest.TestCase)`.
- Execution order: c01 = the inspection family, then c02..c12 in source order of each family's first test (a family may contain tests from far apart in the source; order is by first member). Source order is not required by the brief; risk order is.

## 2b. Helper allocation (c00 mixin vs. family-private vs. source)

Rule (bead): a helper whose transitive test users span two or more families, `setUp`, and every helper a mixin helper calls -> the **one mixin** `Revision9BuilderBatchSupport` (`tests/_revision9_coord_support.py`, mixin shape, commit c00, listed first in every family's bases). A helper whose transitive test users all lie in one family -> that family's sibling class, moved in the same class-shape call, listed before the tests. A helper used only by the skipUnless test -> source (none exist). A helper with no test users -> source, dead-code candidate (none exist). Computed from the inventory call graph (`inventory-revision9-coord-builder.json`, helper->helper edges followed transitively; cross-checked against `inventory-revision9-coord-helpers.md`). Mixin closure: after the first pass no mixin helper called a private helper, so nothing had to be lifted.

| helper | lines (decorators) | calls helpers | test users | families of its users | destination |
|---|---|---|---|---|---|
| `setUp` | 6 | `_new_repo` | 0 | — (`setUp`, framework-called) | **mixin** (c00) |
| `_new_repo` | 29 | — | 75 | `c02-batch_builder`, `c03-scope_change`, `c04-gap_repair`, `c05-staging_crashes`, `c06-chain_drain`, `c07-terminal_builder`, `c08-legacy_activation`, `c10-activation_scan`, `c11-activation_outbox`, `c12-ledger_recovery` | **mixin** (c00) |
| `api_environment` | 3 ['contextmanager'] | — | 103 | `c01-cli_diagnostics`, `c02-batch_builder`, `c03-scope_change`, `c04-gap_repair`, `c05-staging_crashes`, `c06-chain_drain`, `c07-terminal_builder`, `c08-legacy_activation`, `c09-receipted_chain`, `c10-activation_scan`, `c11-activation_outbox`, `c12-ledger_recovery` | **mixin** (c00) |
| `run_dir` | 2 | — | 91 | `c01-cli_diagnostics`, `c02-batch_builder`, `c03-scope_change`, `c04-gap_repair`, `c05-staging_crashes`, `c06-chain_drain`, `c07-terminal_builder`, `c08-legacy_activation`, `c09-receipted_chain`, `c10-activation_scan`, `c11-activation_outbox`, `c12-ledger_recovery` | **mixin** (c00) |
| `open_run` | 9 | — | 47 | `c02-batch_builder`, `c03-scope_change`, `c04-gap_repair`, `c05-staging_crashes`, `c06-chain_drain`, `c07-terminal_builder`, `c08-legacy_activation`, `c11-activation_outbox` | **mixin** (c00) |
| `start_task` | 10 | — | 53 | `c02-batch_builder`, `c04-gap_repair`, `c05-staging_crashes`, `c06-chain_drain`, `c07-terminal_builder`, `c08-legacy_activation`, `c10-activation_scan`, `c11-activation_outbox`, `c12-ledger_recovery` | **mixin** (c00) |
| `_leave_complete_intent` | 37 | `open_run`, `run_dir`, `start_task` | 5 | `c02-batch_builder`, `c04-gap_repair`, `c05-staging_crashes` | **mixin** (c00) |
| `_leave_base_intent` | 16 | `open_run`, `run_dir`, `start_task` | 3 | `c02-batch_builder` | family `c02-batch_builder` (private, on `Revision9BatchBuilderTests`) |
| `_leave_scope_receipt_gap` | 69 | `open_run`, `run_dir` | 5 | `c04-gap_repair` | family `c04-gap_repair` (private, on `Revision9GapRepairTests`) |
| `_leave_two_record_receipt_gap` | 45 | `_write_landed_intent_for_last_receipt`, `open_run`, `run_dir`, `start_task` | 2 | `c04-gap_repair` | family `c04-gap_repair` (private, on `Revision9GapRepairTests`) |
| `_write_landed_intent_for_last_receipt` | 29 | — | 10 | `c04-gap_repair`, `c11-activation_outbox`, `c12-ledger_recovery` | **mixin** (c00) |
| `_write_bound_chain_state` | 240 | — | 26 | `c06-chain_drain`, `c07-terminal_builder`, `c09-receipted_chain`, `c10-activation_scan`, `c11-activation_outbox` | **mixin** (c00) |
| `_chain_drain_case` | 40 | `_terminal_control_repo`, `_write_bound_chain_state` | 4 | `c06-chain_drain` | family `c06-chain_drain` (private, on `Revision9ChainDrainTests`) |
| `_chain_drain_authorizer` | 93 | `run_dir` | 6 | `c06-chain_drain`, `c11-activation_outbox` | **mixin** (c00) |
| `_append_test_landing` | 4 | `_append_test_decision` | 4 | `c07-terminal_builder` | family `c07-terminal_builder` (private, on `Revision9TerminalBuilderTests`) |
| `_append_test_decision` | 46 | — | 4 | `c07-terminal_builder` | family `c07-terminal_builder` (private, on `Revision9TerminalBuilderTests`) |
| `_terminal_control_repo` | 12 | `_new_repo`, `open_run`, `start_task` | 10 | `c06-chain_drain`, `c07-terminal_builder` | **mixin** (c00) |
| `_abort_bound_chain_fixture` | 38 | — | 1 | `c07-terminal_builder` | family `c07-terminal_builder` (private, on `Revision9TerminalBuilderTests`) |
| `_self_event_fixture` | 35 | — | 2 | `c07-terminal_builder` | family `c07-terminal_builder` (private, on `Revision9TerminalBuilderTests`) |
| `_open_legacy_run` | 35 | — | 48 | `c04-gap_repair`, `c08-legacy_activation`, `c09-receipted_chain`, `c10-activation_scan`, `c11-activation_outbox`, `c12-ledger_recovery` | **mixin** (c00) |
| `_activation_markers` | 8 ['staticmethod'] | — | 8 | `c04-gap_repair`, `c08-legacy_activation`, `c11-activation_outbox`, `c12-ledger_recovery` | **mixin** (c00) |
| `_run_file_bytes` | 6 ['staticmethod'] | — | 22 | `c04-gap_repair`, `c08-legacy_activation`, `c11-activation_outbox`, `c12-ledger_recovery` | **mixin** (c00) |
| `_plant_unreplayable_unrelated_chain` | 14 | — | 2 | `c10-activation_scan` | family `c10-activation_scan` (private, on `Revision9ActivationScanTests`) |
| `_pad_valid_json_over_cap` | 5 ['staticmethod'] | — | 3 | `c10-activation_scan` | family `c10-activation_scan` (private, on `Revision9ActivationScanTests`) |
| `_guard_activation_artifact_read_budget` | 46 ['contextmanager'] | — | 5 | `c10-activation_scan` | family `c10-activation_scan` (private, on `Revision9ActivationScanTests`) |
| `_assert_first_batch_artifact_substitution_refuses` | 60 | `_new_repo`, `_open_legacy_run`, `api_environment`, `run_dir`, `start_task` | 2 | `c08-legacy_activation` | family `c08-legacy_activation` (private, on `Revision9LegacyActivationTests`) |
| `_activation_outbox_case` | 87 | `_new_repo`, `_open_legacy_run`, `_write_bound_chain_state`, `run_dir` | 4 | `c11-activation_outbox` | family `c11-activation_outbox` (private, on `Revision9ActivationOutboxTests`) |
| `_compete_with_activation_outbox` | 17 | — | 2 | `c11-activation_outbox` | family `c11-activation_outbox` (private, on `Revision9ActivationOutboxTests`) |
| `_invoke_raw_lifecycle` | 25 | `run_dir` | 4 | `c10-activation_scan`, `c11-activation_outbox`, `c12-ledger_recovery` | **mixin** (c00) |
| `_bound_chain_outbox` | 29 | — | 5 | `c09-receipted_chain` | family `c09-receipted_chain` (private, on `Revision9ReceiptedChainTests`) |
| `_acknowledge_bound_chain` | 47 | — | 5 | `c09-receipted_chain` | family `c09-receipted_chain` (private, on `Revision9ReceiptedChainTests`) |
| `_legacy_receipted_chain_case` | 80 | `_acknowledge_bound_chain`, `_bound_chain_outbox`, `_open_legacy_run`, `_write_bound_chain_state` | 5 | `c09-receipted_chain` | family `c09-receipted_chain` (private, on `Revision9ReceiptedChainTests`) |
| `_rewrite_commit_events` | 25 | — | 2 | `c09-receipted_chain` | family `c09-receipted_chain` (private, on `Revision9ReceiptedChainTests`) |
| `_restore_prefix_wedge_fixture` | 37 | `_new_repo`, `run_dir` | 1 | `c12-ledger_recovery` | family `c12-ledger_recovery` (private, on `Revision9LedgerRecoveryTests`) |
| `_seed_unactivated_stale_ledger` | 66 | `_open_legacy_run`, `run_dir` | 4 | `c12-ledger_recovery` | family `c12-ledger_recovery` (private, on `Revision9LedgerRecoveryTests`) |
| `_seed_gh17_wedge` | 157 | `_open_legacy_run`, `_write_landed_intent_for_last_receipt`, `run_dir` | 8 | `c04-gap_repair`, `c11-activation_outbox`, `c12-ledger_recovery` | **mixin** (c00) |
| `_assert_gh17_recovered` | 77 | `_activation_markers` | 4 | `c04-gap_repair`, `c12-ledger_recovery` | **mixin** (c00) |
| `command` | 10 | — | 4 | `c01-cli_diagnostics`, `c03-scope_change` | **mixin** (c00) |

**Mixin (c00):** 18 helpers, **791 code lines** including 3 decorator lines (`api_environment` contextmanager; `_activation_markers`, `_run_file_bytes` staticmethod), **806 measured with header** (`.refactor/dryrun-revision9-coord-c00-mixin-measure.txt`; the other two decorated helpers are `activation_scan`-private). Not reachable under 500 by any honest partition: `_write_bound_chain_state` (240) is read by 5 families, the six hub helpers (59) by 8–12 families each, `_chain_drain_authorizer` (93) by 2, `_seed_gh17_wedge`/`_assert_gh17_recovered` (234) by 3 and 2 families whose tests are named after repair receipts and the GH#17 wedge respectively; moving the 3 gap_repair/activation_outbox readers of the GH#17 helpers into `ledger_recovery` would take that module to ≈1,335 and would drag `_leave_two_record_receipt_gap` into the mixin. So the mixin is a between-target-and-ceiling module with a debt row (§6, §8).
- mixin methods csv (inventory order): `setUp,_new_repo,api_environment,run_dir,open_run,start_task,_leave_complete_intent,_write_landed_intent_for_last_receipt,_write_bound_chain_state,_chain_drain_authorizer,_terminal_control_repo,_open_legacy_run,_activation_markers,_run_file_bytes,_invoke_raw_lifecycle,_seed_gh17_wedge,_assert_gh17_recovered,command`
- c00 argv (mixin shape; identity mode):
  ```
  python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision9_coordination.py --class Revision9BuilderBatchTests \
    --methods setUp,_new_repo,api_environment,run_dir,open_run,start_task,_leave_complete_intent,_write_landed_intent_for_last_receipt,_write_bound_chain_state,_chain_drain_authorizer,_terminal_control_repo,_open_legacy_run,_activation_markers,_run_file_bytes,_invoke_raw_lifecycle,_seed_gh17_wedge,_assert_gh17_recovered,command \
    --dest tests/_revision9_coord_support.py --shape mixin --target-class Revision9BuilderBatchSupport --test-only \
    --test-snapshot .refactor/tests-revision9-coord-c00-mixin.json --format-imports --manifest .refactor/mixin-revision9-coord.json
  ```
  driver: `bash .refactor/revision9-coord-cluster.sh c00-mixin mixin tests/_revision9_coord_support.py Revision9BuilderBatchSupport "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["mixin"]["methods_csv"])')" "refactor(tests): move the 18 shared helpers of Revision9BuilderBatchTests to tests/_revision9_coord_support.py (mixin shape, tier 1)"` — gate `--test-mode identity`; then `env -u PYTHONPATH python3 -m unittest tests.test_revision9_coordination` once (brief §4 item 3).
- expected mixin header (from the helpers' globals plus decorators): `from __future__ import annotations`; stdlib `base64, copy, io, json, os, subprocess, sys, tempfile` (`hashlib` and `shutil` no longer: their helper readers are family-private); `from contextlib import contextmanager, redirect_stderr`; `from pathlib import Path`; `from unittest import mock`; `from codex_orchestrator import batch, builders, journal`; `from tests._revision9_coord_constants import TOOLS, key` (the attempt-1 header minus the four fixture constants, which now travel with `activation_scan` and `ledger_recovery`). Globals actually read: `Path`, `TOOLS`, `base64`, `batch`, `builders`, `copy`, `io`, `journal`, `json`, `key`, `mock`, `os`, `redirect_stderr`, `subprocess`, `sys`, `tempfile` plus the `contextmanager` decorator.
- source after c00: `remove_imports` = `TOOLS` only (attempt 1 also removed `PREFIX_WEDGE_FIXTURE`, `PREFIX_WEDGE_FIXTURE_SHA256`, `UNREPLAYABLE_CHAIN_FIXTURE`, `UNREPLAYABLE_CHAIN_FIXTURE_SHA256`; with this allocation those four stay until c10/c12).
- **Family-private helpers (20, 808 lines):** defined on the sibling class of exactly one family and inheritable by nobody else (risk R16). Per family: `batch_builder`: `_leave_base_intent`; `gap_repair`: `_leave_scope_receipt_gap`, `_leave_two_record_receipt_gap`; `chain_drain`: `_chain_drain_case`; `terminal_builder`: `_append_test_landing`, `_append_test_decision`, `_abort_bound_chain_fixture`, `_self_event_fixture`; `legacy_activation`: `_assert_first_batch_artifact_substitution_refuses`; `receipted_chain`: `_bound_chain_outbox`, `_acknowledge_bound_chain`, `_legacy_receipted_chain_case`, `_rewrite_commit_events`; `activation_scan`: `_plant_unreplayable_unrelated_chain`, `_pad_valid_json_over_cap`, `_guard_activation_artifact_read_budget`; `activation_outbox`: `_activation_outbox_case`, `_compete_with_activation_outbox`; `ledger_recovery`: `_restore_prefix_wedge_fixture`, `_seed_unactivated_stale_ledger`.
- **Source-retained helpers:** none. **Dead-code candidates:** none (every helper has ≥1 test user; `setUp` is framework-called).

## 3. Target modules

### 3.0 Common to every family (the driver `.refactor/revision9-coord-cluster.sh` implements exactly this)

- Precondition: c00 committed with exactly the §2b mixin method list (the class header reads `class Revision9BuilderBatchTests(Revision9BuilderBatchSupport, unittest.TestCase)`; the class body contains only `def`s: the 109 tests and the 20 family-private helpers). Before c00 every class-shape dry run is refused with `sibling class would lose calls to remaining methods` (designed order check); after c00 the same check passes for every family because each family's tests and private helpers call only (a) methods in the same `--methods` list or (b) mixin methods, which are no longer methods of the source class. Tracked tree clean; destination absent; manifest path absent.
- Fresh snapshots first: `python3 $D/collect_tests.py snapshot --start tests --out .refactor/tests-revision9-coord-<label>.json` and `python3 $S/snapshot_bodies.py snapshot tests --out .refactor/revision9-coord-<label>-before.json` (scope exactly the gate's `--pkg tests`).
- Id map: built by `.refactor/revision9-coord-idmap.py <fresh snapshot> test_revision9_coordination_<family> <Family>Tests .refactor/idmap-revision9-coord-<family>.json <methods csv>` from the **fresh** snapshot (the script keeps only `test_`-prefixed names, so the private helpers in the csv never enter the map) (old IDs must be members of that snapshot: `collect_tests.compare` refuses keys outside `before['ids']`). Shape, verified against the freeze's real spellings:
  ```json
  {"unittest": {"test_revision9_coordination.Revision9BuilderBatchTests.<t>": "test_revision9_coordination_<family>.<Family>Tests.<t>"},
   "pytest":   {"tests/test_revision9_coordination.py::Revision9BuilderBatchTests::<t>": "tests/test_revision9_coordination_<family>.py::<Family>Tests::<t>"}}
  ```
  Exactly the family's tests (never its helpers) in both collectors, one entry per test per collector (unittest IDs start with the module stem, not `tests.`, per the namespace preset; pytest IDs carry the `tests/` path). `settings.pinned` and `shards` are empty in the freeze, so no pinned ID or shard membership exists to preserve; `compare` still requires injective values and an exact multiset match after the move.
- Mover, dry run then apply (identical argv plus `--apply`):
  ```
  python3 $D/move_methods.py --project . --import-root "$PWD" --source tests/test_revision9_coordination.py \
    --class Revision9BuilderBatchTests --methods <csv> --dest tests/test_revision9_coordination_<family>.py \
    --shape class --target-class <Family>Tests --test-only --test-snapshot .refactor/tests-revision9-coord-<label>.json \
    --id-map .refactor/idmap-revision9-coord-<family>.json --format-imports --manifest .refactor/family-revision9-coord-<family>.json
  ```
  `--import-root "$PWD"` is mandatory (brief §11 item 2). `--format-imports` on both runs (ruff `I` rules; the temporary glob excludes `I001` by design).
- Expected diff per family: the listed `def`s deleted from the source class (nothing else in the source body changes); the source's import block loses only the names in the §5 removal schedule; the destination is a new module with the header imports listed in the family section, then `class <Family>Tests(Revision9BuilderBatchSupport, unittest.TestCase):` holding the tests **in the requested order** = csv order (`moved.sort(key=methods.index)`, move_methods.py:398), and every csv is in source order with the private helpers interleaved among the tests exactly as in the source — re-ordering a csv would silently re-order the module. Bodies, docstrings, decorators (`staticmethod`, `contextmanager`) and fixture strings verbatim. No `__all__`, no docstring on the class, and **no `if __name__ == "__main__": unittest.main()` block** (the mover never emits one; unlike every existing module in `tests/`; harmless for both collectors — one handover line so finalize does not read it as a loss).
- Gate: `bash $S/verify.sh --pkg tests --snapshot <bodies> --manifest <manifest> --strict-bodies --test-snapshot <ids> --test-mode mapping`, then the repository guard `git ls-files -z "*.py" | xargs -0 python3 scripts/check_file_length.py <dest>`, then `git diff --stat HEAD -- scripts docs/specs .forge` empty. Commit on PASS only. Test count printed by the gate's test step: **144**.
- Commit subject: `refactor(tests): move the <family> scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_<family>.py (class shape, tier 1)`.
- Tier: 1 (relocation). Refusals expected: none (see §0). Stop conditions: brief §8 (a gate failing twice on one family; any non-collection test failure; any ID compare failure).

### 3.1 Family overview

| # | label | module | class | tests | private helpers | test lines + helper lines = code lines | est. module code lines | inventory clusters merged |
|---|---|---|---|---|---|---|---|---|
| 1 | `c01-cli_diagnostics` | `tests/test_revision9_coordination_cli_diagnostics.py` | `Revision9CliDiagnosticsTests` | 4 | 0 | 218 + 0 = 218 | 240 | 1 |
| 2 | `c02-batch_builder` | `tests/test_revision9_coordination_batch_builder.py` | `Revision9BatchBuilderTests` | 13 | 1 | 547 + 16 = 563 | 585 | 1, 2, 3, 4, 5, 6, 10, 11 |
| 3 | `c03-scope_change` | `tests/test_revision9_coordination_scope_change.py` | `Revision9ScopeChangeTests` | 6 | 0 | 509 + 0 = 509 | 531 | 1, 7, 8 |
| 4 | `c04-gap_repair` | `tests/test_revision9_coordination_gap_repair.py` | `Revision9GapRepairTests` | 9 | 2 | 636 + 114 = 750 | 772 | 1, 9 |
| 5 | `c05-staging_crashes` | `tests/test_revision9_coordination_staging_crashes.py` | `Revision9StagingCrashTests` | 10 | 0 | 526 + 0 = 526 | 548 | 1, 12, 13, 15, 16, 17, 18, 19 |
| 6 | `c06-chain_drain` | `tests/test_revision9_coordination_chain_drain.py` | `Revision9ChainDrainTests` | 6 | 1 | 374 + 40 = 414 | 436 | 1, 13, 20 |
| 7 | `c07-terminal_builder` | `tests/test_revision9_coordination_terminal_builder.py` | `Revision9TerminalBuilderTests` | 9 | 4 | 520 + 123 = 643 | 665 | 13, 21, 22 |
| 8 | `c08-legacy_activation` | `tests/test_revision9_coordination_legacy_activation.py` | `Revision9LegacyActivationTests` | 11 | 1 | 827 + 60 = 887 | 909 | 13, 14, 23, 24 |
| 9 | `c09-receipted_chain` | `tests/test_revision9_coordination_receipted_chain.py` | `Revision9ReceiptedChainTests` | 5 | 4 | 603 + 181 = 784 | 806 | 1, 13, 25 |
| 10 | `c10-activation_scan` | `tests/test_revision9_coordination_activation_scan.py` | `Revision9ActivationScanTests` | 11 | 3 | 532 + 67 = 599 | 621 | 13, 26, 27 |
| 11 | `c11-activation_outbox` | `tests/test_revision9_coordination_activation_outbox.py` | `Revision9ActivationOutboxTests` | 12 | 2 | 674 + 104 = 778 | 800 | 1, 13, 23, 28, 29, 31 |
| 12 | `c12-ledger_recovery` | `tests/test_revision9_coordination_ledger_recovery.py` | `Revision9LedgerRecoveryTests` | 12 | 2 | 695 + 103 = 798 | 820 | 1, 13, 14, 23, 30 |
| | | | **total** | **108** | **20** | **6,661 + 808 = 7,469** | | |
| c00 | `c00-mixin` | `tests/_revision9_coord_support.py` | `Revision9BuilderBatchSupport` (mixin) | 0 | 18 shared | 791 | 806 (measured) | — |

### 3.2 c01 — `cli_diagnostics` -> `tests/test_revision9_coordination_cli_diagnostics.py`, class `Revision9CliDiagnosticsTests`

- theme: CLI open-notice and diagnostic surfaces: the legacy-open notice is stderr-only (in-process ORCH_TOOLS entry with absent/broken stderr) and the typed open, singleton and idempotency-key diagnostics through the `command` subprocess helper.
- tests (4, source order = requested order), with inventory line/size/cluster:
  - `test_legacy_open_without_stderr_never_falls_back_to_stdout` L6679-6719 41 lines (cluster 1)
  - `test_legacy_open_broken_stderr_never_changes_durable_success` L6721-6768 46 lines (cluster 1)
  - `test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet` L8835-8942 106 lines (cluster 1)
  - `test_cli_singleton_and_idempotency_key_diagnostics` L8944-8971 25 lines (cluster 1)
- private helpers: none (every helper this family calls is shared, hence on the mixin)
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `test_legacy_open_without_stderr_never_falls_back_to_stdout,test_legacy_open_broken_stderr_never_changes_durable_success,test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet,test_cli_singleton_and_idempotency_key_diagnostics`
- code lines: tests **218** + private helpers **0** = **218**; estimated module code lines: **240**; under 500: no baseline entry
- mixin helpers inherited (direct or transitive): `api_environment`, `command`, `run_dir`
- module globals read by the bodies (inventory `globals`): `ORCH_TOOLS`, `Path`, `io`, `journal`, `json`, `key`, `mock`, `redirect_stdout`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import io`
  - `import json`
  - `import unittest`
  - `from contextlib import redirect_stdout`
  - `from pathlib import Path`
  - `from unittest import mock`
  - `import codex_orch_tools as ORCH_TOOLS`
  - `from codex_orchestrator import journal`
  - `from tests._revision9_coord_constants import key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: none
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 1
- note: first family on purpose (inspection): 4 tests, one aliased third-party import to copy (`ORCH_TOOLS`), and the first source-side removals (`import codex_orch_tools as ORCH_TOOLS  # noqa: E402` whole statement; `redirect_stdout` out of the contextlib import). The operator reads this diff by hand before c02.
- note: the other two `command` callers are here.
- dry run / apply / gate: §3.0 with `<label>=c01-cli_diagnostics`, `<family>=cli_diagnostics`, `<Family>Tests=Revision9CliDiagnosticsTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c01-cli_diagnostics class tests/test_revision9_coordination_cli_diagnostics.py Revision9CliDiagnosticsTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["cli_diagnostics"]["methods_csv"])')" "refactor(tests): move the cli_diagnostics scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_cli_diagnostics.py (class shape, tier 1)"`
- id map: 4 unittest + 4 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_legacy_open_without_stderr_never_falls_back_to_stdout` -> `test_revision9_coordination_cli_diagnostics.Revision9CliDiagnosticsTests.test_legacy_open_without_stderr_never_falls_back_to_stdout`.
- expected refusals: none.

### 3.3 c02 — `batch_builder` -> `tests/test_revision9_coordination_batch_builder.py`, class `Revision9BatchBuilderTests`

- theme: Typed batch builder contract: round-trip IDs/receipts/idempotency, request schema and digest, torn intent and receipt recovery, ledger consistency freezes, midflight intent fences, and the in-memory load-bearing builder/batch controls.
- tests (13, source order = requested order), with inventory line/size/cluster:
  - `test_typed_builder_round_trip_ids_receipts_and_idempotency` L266-393 125 lines (cluster 1)
  - `test_exact_prefix_and_torn_receipt_recovery` L453-481 29 lines (cluster 1)
  - `test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only` L483-509 26 lines (cluster 1)
  - `test_torn_intent_never_becomes_authoritative` L511-542 32 lines (cluster 2)
  - `test_self_consistent_intent_substitution_after_prepare_is_refused` L544-585 40 lines (cluster 3)
  - `test_activated_missing_stable_lock_or_receipt_ledger_diverges` L587-609 23 lines (cluster 4)
  - `test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze` L611-644 34 lines (cluster 5)
  - `test_intent_without_journal_and_reentrant_pending_read_refuse_exactly` L646-673 27 lines (cluster 2)
  - `test_midflight_intent_hardlink_fifo_and_foreign_uid_fences` L675-707 33 lines (cluster 1)
  - `test_batch_controls_are_load_bearing` L709-777 63 lines (cluster 1)
  - `test_builder_validation_controls_are_detected_in_memory` L779-826 46 lines (cluster 6)
  - `test_typed_task_scope_refusal_names_offending_pathspec` L1935-1950 16 lines (cluster 10)
  - `test_builder_request_schema_and_digest_are_exact` L1952-2005 53 lines (cluster 11)
- private helpers (1, 16 code lines incl. decorator lines; defined on `Revision9BatchBuilderTests`, inherited by nobody — see §2b), moved in the same call, in source order among the tests:
  - `_leave_base_intent` L434-451 16 lines; calls: `open_run` (mixin), `run_dir` (mixin), `start_task` (mixin); test users: 3
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `test_typed_builder_round_trip_ids_receipts_and_idempotency,_leave_base_intent,test_exact_prefix_and_torn_receipt_recovery,test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only,test_torn_intent_never_becomes_authoritative,test_self_consistent_intent_substitution_after_prepare_is_refused,test_activated_missing_stable_lock_or_receipt_ledger_diverges,test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze,test_intent_without_journal_and_reentrant_pending_read_refuse_exactly,test_midflight_intent_hardlink_fifo_and_foreign_uid_fences,test_batch_controls_are_load_bearing,test_builder_validation_controls_are_detected_in_memory,test_typed_task_scope_refusal_names_offending_pathspec,test_builder_request_schema_and_digest_are_exact`
- code lines: tests **547** + private helpers **16** = **563**; estimated module code lines: **585**; provisional baseline entry: **630**
- mixin helpers inherited (direct or transitive): `_leave_complete_intent`, `_new_repo`, `api_environment`, `open_run`, `run_dir`, `start_task`
- module globals read by the bodies (inventory `globals`): `Path`, `base64`, `batch`, `builders`, `copy`, `journal`, `json`, `key`, `mock`, `nullcontext`, `os`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import base64`
  - `import copy`
  - `import json`
  - `import os`
  - `import unittest`
  - `from contextlib import nullcontext`
  - `from pathlib import Path`
  - `from unittest import mock`
  - `from codex_orchestrator import batch, builders, journal`
  - `from tests._revision9_coord_constants import key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: 4 (`test_torn_intent_never_becomes_authoritative`, `test_activated_missing_stable_lock_or_receipt_ledger_diverges`, `test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze`, `test_midflight_intent_hardlink_fifo_and_foreign_uid_fences`)
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 1
- dry run / apply / gate: §3.0 with `<label>=c02-batch_builder`, `<family>=batch_builder`, `<Family>Tests=Revision9BatchBuilderTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c02-batch_builder class tests/test_revision9_coordination_batch_builder.py Revision9BatchBuilderTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["batch_builder"]["methods_csv"])')" "refactor(tests): move the batch_builder scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_batch_builder.py (class shape, tier 1)"`
- id map: 13 unittest + 13 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_typed_builder_round_trip_ids_receipts_and_idempotency` -> `test_revision9_coordination_batch_builder.Revision9BatchBuilderTests.test_typed_builder_round_trip_ids_receipts_and_idempotency`.
- expected refusals: none.

### 3.4 c03 — `scope_change` -> `tests/test_revision9_coordination_scope_change.py`, class `Revision9ScopeChangeTests`

- theme: Activated-run readmission and scope change: typed readmit sequences keep receipts contiguous, scope-change recovery of intent and receipted registry publication, superset/conflict rechecks, and the multi-process admission-vs-scope-change race (the `program = r'''...'''` fixture script, the only ROOT reader).
- tests (6, source order = requested order), with inventory line/size/cluster:
  - `test_activated_scope_readmission_uses_typed_builder` L828-906 76 lines (cluster 1)
  - `test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume` L908-981 72 lines (cluster 1)
  - `test_scope_change_recovers_intent_and_receipted_registry_publication` L983-1065 81 lines (cluster 7)
  - `test_scope_change_recovery_refuses_unproved_replace_and_disabled_control` L1067-1154 87 lines (cluster 8)
  - `test_activated_scope_change_rechecks_superset_containment_and_conflicts` L1436-1510 74 lines (cluster 1)
  - `test_concurrent_admission_and_scope_change_remain_disjoint` L1512-1636 119 lines (cluster 1)
- private helpers: none (every helper this family calls is shared, hence on the mixin)
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `test_activated_scope_readmission_uses_typed_builder,test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume,test_scope_change_recovers_intent_and_receipted_registry_publication,test_scope_change_recovery_refuses_unproved_replace_and_disabled_control,test_activated_scope_change_rechecks_superset_containment_and_conflicts,test_concurrent_admission_and_scope_change_remain_disjoint`
- code lines: tests **509** + private helpers **0** = **509**; estimated module code lines: **531**; provisional baseline entry: **580**
- mixin helpers inherited (direct or transitive): `_new_repo`, `api_environment`, `command`, `open_run`, `run_dir`
- module globals read by the bodies (inventory `globals`): `Path`, `ROOT`, `batch`, `builders`, `contextmanager`, `journal`, `json`, `key`, `mock`, `subprocess`, `sys`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import json`
  - `import subprocess`
  - `import sys`
  - `import unittest`
  - `from contextlib import contextmanager`
  - `from pathlib import Path`
  - `from unittest import mock`
  - `from codex_orchestrator import batch, builders, journal`
  - `from tests._revision9_coord_constants import ROOT, key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: 3 (`test_scope_change_recovers_intent_and_receipted_registry_publication`, `test_scope_change_recovery_refuses_unproved_replace_and_disabled_control`, `test_activated_scope_change_rechecks_superset_containment_and_conflicts`)
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 1
- note: `test_concurrent_admission_and_scope_change_remain_disjoint` contains the `program = r'''...'''` fixture script (inventory L1534-1587; a raw string, kept verbatim; its inner `sys.path.insert`/`from codex_orchestrator import` lines are string content, invisible to the AST import analysis) and is the **only ROOT reader** (`str(ROOT / "scripts")` as a subprocess argument): the destination imports `ROOT` from `tests._revision9_coord_constants`; the source keeps `ROOT` for its own `sys.path.insert`.
- note: two of the four `command` callers are here (`test_activated_scope_readmission_uses_typed_builder`, `test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume`).
- dry run / apply / gate: §3.0 with `<label>=c03-scope_change`, `<family>=scope_change`, `<Family>Tests=Revision9ScopeChangeTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c03-scope_change class tests/test_revision9_coordination_scope_change.py Revision9ScopeChangeTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["scope_change"]["methods_csv"])')" "refactor(tests): move the scope_change scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_scope_change.py (class shape, tier 1)"`
- id map: 6 unittest + 6 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_activated_scope_readmission_uses_typed_builder` -> `test_revision9_coordination_scope_change.Revision9ScopeChangeTests.test_activated_scope_readmission_uses_typed_builder`.
- expected refusals: none.

### 3.5 c04 — `gap_repair` -> `tests/test_revision9_coordination_gap_repair.py`, class `Revision9GapRepairTests`

- theme: Batch gap repair and repair receipts: refusal of leading/trailing/ambiguous gaps, one-n-record and proven-readmission gap repair, rederivation of repair receipts (including every n-record repair member on the GH#17 wedge) and the independently load-bearing repair controls.
- tests (9, source order = requested order), with inventory line/size/cluster:
  - `test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps` L1156-1231 73 lines (cluster 1)
  - `test_batch_recover_repairs_one_n_record_gap` L1233-1311 76 lines (cluster 1)
  - `test_batch_gap_repair_controls_are_independently_load_bearing` L1313-1356 44 lines (cluster 1)
  - `test_repair_receipt_is_rederived_on_every_load` L1358-1386 29 lines (cluster 9)
  - `test_torn_repair_receipt_resumes_only_its_derived_suffix` L1388-1434 44 lines (cluster 9)
  - `test_batch_recover_repairs_proven_readmission_gap_and_stale_intent` L1786-1830 45 lines (cluster 9)
  - `test_batch_gap_repair_refuses_unproved_bytes_and_intent` L1832-1933 101 lines (cluster 9)
  - `test_repair_receipt_n_record_members_rederived` L8287-8407 119 lines (cluster 1)
  - `test_stable_reader_rederives_every_n_record_repair_member` L8409-8515 105 lines (cluster 1)
- private helpers (2, 114 code lines incl. decorator lines; defined on `Revision9GapRepairTests`, inherited by nobody — see §2b), moved in the same call, in source order among the tests:
  - `_leave_scope_receipt_gap` L1638-1708 69 lines; calls: `open_run` (mixin), `run_dir` (mixin); test users: 5
  - `_leave_two_record_receipt_gap` L1710-1754 45 lines; calls: `_write_landed_intent_for_last_receipt` (mixin), `open_run` (mixin), `run_dir` (mixin), `start_task` (mixin); test users: 2
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps,test_batch_recover_repairs_one_n_record_gap,test_batch_gap_repair_controls_are_independently_load_bearing,test_repair_receipt_is_rederived_on_every_load,test_torn_repair_receipt_resumes_only_its_derived_suffix,_leave_scope_receipt_gap,_leave_two_record_receipt_gap,test_batch_recover_repairs_proven_readmission_gap_and_stale_intent,test_batch_gap_repair_refuses_unproved_bytes_and_intent,test_repair_receipt_n_record_members_rederived,test_stable_reader_rederives_every_n_record_repair_member`
- code lines: tests **636** + private helpers **114** = **750**; estimated module code lines: **772**; provisional baseline entry: **820**
- mixin helpers inherited (direct or transitive): `_activation_markers`, `_assert_gh17_recovered`, `_leave_complete_intent`, `_new_repo`, `_open_legacy_run`, `_run_file_bytes`, `_seed_gh17_wedge`, `_write_landed_intent_for_last_receipt`, `api_environment`, `open_run`, `run_dir`, `start_task`
- module globals read by the bodies (inventory `globals`): `base64`, `batch`, `builders`, `journal`, `json`, `key`, `mock`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import base64`
  - `import json`
  - `import unittest`
  - `from unittest import mock`
  - `from codex_orchestrator import batch, builders, journal`
  - `from tests._revision9_coord_constants import key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: 5 (`test_batch_gap_repair_controls_are_independently_load_bearing`, `test_repair_receipt_is_rederived_on_every_load`, `test_batch_gap_repair_refuses_unproved_bytes_and_intent`, `test_repair_receipt_n_record_members_rederived`, `test_stable_reader_rederives_every_n_record_repair_member`)
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 2
- note: the two GH#17 n-record repair-member tests (L8287, L8409) sit 6,400 lines away from the other seven in the source; the family is nonetheless one scenario (repair receipts), and `test_batch_gap_repair_controls_are_independently_load_bearing` already seeds the GH#17 wedge.
- dry run / apply / gate: §3.0 with `<label>=c04-gap_repair`, `<family>=gap_repair`, `<Family>Tests=Revision9GapRepairTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c04-gap_repair class tests/test_revision9_coordination_gap_repair.py Revision9GapRepairTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["gap_repair"]["methods_csv"])')" "refactor(tests): move the gap_repair scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_gap_repair.py (class shape, tier 1)"`
- id map: 9 unittest + 9 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps` -> `test_revision9_coordination_gap_repair.Revision9GapRepairTests.test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps`.
- expected refusals: none.

### 3.6 c05 — `staging_crashes` -> `tests/test_revision9_coordination_staging_crashes.py`, class `Revision9StagingCrashTests`

- theme: Run-open publication atomicity and the batch/intent staging crash matrix: a crash at every phase leaves no visible run, no duplicate receipt and no lost bytes; foreign or substituted intent stages are quarantined, never adopted; hostile transaction nodes freeze.
- tests (10, source order = requested order), with inventory line/size/cluster:
  - `test_run_open_is_hidden_until_atomic_publication` L2007-2042 34 lines (cluster 12)
  - `test_run_open_prepublication_crashes_leave_no_visible_run` L2044-2077 32 lines (cluster 13)
  - `test_run_open_durable_receipt_survives_registry_failure_and_retry` L2079-2114 34 lines (cluster 1)
  - `test_fr019_failure_phase_order_preserves_earlier_bytes` L2197-2258 60 lines (cluster 15)
  - `test_batch_crashes_recover_stored_bytes_without_duplicate_receipt` L2260-2326 62 lines (cluster 13)
  - `test_prepublication_intent_stage_crashes_retry_without_authority` L2328-2410 81 lines (cluster 16)
  - `test_foreign_request_intent_stage_is_not_deleted` L2412-2428 17 lines (cluster 17)
  - `test_intent_source_name_substitution_never_survives_canonical` L2430-2498 67 lines (cluster 18)
  - `test_intent_quarantine_preserves_a_second_canonical_swap` L2500-2588 85 lines (cluster 19)
  - `test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze` L2648-2704 54 lines (cluster 1)
- private helpers: none (every helper this family calls is shared, hence on the mixin)
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `test_run_open_is_hidden_until_atomic_publication,test_run_open_prepublication_crashes_leave_no_visible_run,test_run_open_durable_receipt_survives_registry_failure_and_retry,test_fr019_failure_phase_order_preserves_earlier_bytes,test_batch_crashes_recover_stored_bytes_without_duplicate_receipt,test_prepublication_intent_stage_crashes_retry_without_authority,test_foreign_request_intent_stage_is_not_deleted,test_intent_source_name_substitution_never_survives_canonical,test_intent_quarantine_preserves_a_second_canonical_swap,test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze`
- code lines: tests **526** + private helpers **0** = **526**; estimated module code lines: **548**; provisional baseline entry: **590**
- mixin helpers inherited (direct or transitive): `_leave_complete_intent`, `_new_repo`, `api_environment`, `open_run`, `run_dir`, `start_task`
- module globals read by the bodies (inventory `globals`): `Path`, `batch`, `builders`, `journal`, `json`, `key`, `mock`, `os`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import json`
  - `import os`
  - `import unittest`
  - `from pathlib import Path`
  - `from unittest import mock`
  - `from codex_orchestrator import batch, builders, journal`
  - `from tests._revision9_coord_constants import key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: 4 (`test_run_open_prepublication_crashes_leave_no_visible_run`, `test_batch_crashes_recover_stored_bytes_without_duplicate_receipt`, `test_prepublication_intent_stage_crashes_retry_without_authority`, `test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze`)
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 8
- note: the skipUnless test `test_run_open_process_death_keeps_staging_invisible_and_retryable` (L2117-2195) sits in the middle of this region and **stays on the source class**; it is not in this csv.
- dry run / apply / gate: §3.0 with `<label>=c05-staging_crashes`, `<family>=staging_crashes`, `<Family>Tests=Revision9StagingCrashTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c05-staging_crashes class tests/test_revision9_coordination_staging_crashes.py Revision9StagingCrashTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["staging_crashes"]["methods_csv"])')" "refactor(tests): move the staging_crashes scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_staging_crashes.py (class shape, tier 1)"`
- id map: 10 unittest + 10 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_run_open_is_hidden_until_atomic_publication` -> `test_revision9_coordination_staging_crashes.Revision9StagingCrashTests.test_run_open_is_hidden_until_atomic_publication`.
- expected refusals: none.

### 3.7 c06 — `chain_drain` -> `tests/test_revision9_coordination_chain_drain.py`, class `Revision9ChainDrainTests`

- theme: Bound-chain drain authorization: valid authorizer paths (new and repeated), authorized-pending and lost-response retry, exact field bindings, the load-bearing authorization controls, the no-capability refusal of raw drain records, and ingest's registered proof-complete authority.
- tests (6, source order = requested order), with inventory line/size/cluster:
  - `test_chain_drain_raw_records_without_capability_refuses` L2590-2646 57 lines (cluster 20)
  - `test_chain_drain_valid_authorizer_new_and_repeated_paths` L3098-3132 35 lines (cluster 13)
  - `test_chain_drain_authorized_pending_and_lost_response_retry` L3134-3196 61 lines (cluster 13)
  - `test_chain_drain_authorization_exact_field_bindings` L3198-3277 80 lines (cluster 13)
  - `test_chain_drain_authorization_controls_are_load_bearing` L3279-3330 52 lines (cluster 13)
  - `test_ingest_requires_registered_proof_complete_authority` L3332-3423 89 lines (cluster 1)
- private helpers (1, 40 code lines incl. decorator lines; defined on `Revision9ChainDrainTests`, inherited by nobody — see §2b), moved in the same call, in source order among the tests:
  - `_chain_drain_case` L2960-2999 40 lines; calls: `_terminal_control_repo` (mixin), `_write_bound_chain_state` (mixin); test users: 4
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `test_chain_drain_raw_records_without_capability_refuses,_chain_drain_case,test_chain_drain_valid_authorizer_new_and_repeated_paths,test_chain_drain_authorized_pending_and_lost_response_retry,test_chain_drain_authorization_exact_field_bindings,test_chain_drain_authorization_controls_are_load_bearing,test_ingest_requires_registered_proof_complete_authority`
- code lines: tests **374** + private helpers **40** = **414**; estimated module code lines: **436**; under 500: no baseline entry
- mixin helpers inherited (direct or transitive): `_chain_drain_authorizer`, `_new_repo`, `_terminal_control_repo`, `_write_bound_chain_state`, `api_environment`, `open_run`, `run_dir`, `start_task`
- module globals read by the bodies (inventory `globals`): `batch`, `builders`, `copy`, `journal`, `json`, `key`, `mock`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import copy`
  - `import json`
  - `import unittest`
  - `from unittest import mock`
  - `from codex_orchestrator import batch, builders, journal`
  - `from tests._revision9_coord_constants import key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: 4 (`test_chain_drain_authorized_pending_and_lost_response_retry`, `test_chain_drain_authorization_exact_field_bindings`, `test_chain_drain_authorization_controls_are_load_bearing`, `test_ingest_requires_registered_proof_complete_authority`)
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 2
- note: under 500 by the ceiling rule (§2): merging with `terminal_builder` would reach ≈1,090 once both sides' private helpers are counted. `_chain_drain_case` (private) calls `_terminal_control_repo` and `_write_bound_chain_state`, both on the mixin.
- dry run / apply / gate: §3.0 with `<label>=c06-chain_drain`, `<family>=chain_drain`, `<Family>Tests=Revision9ChainDrainTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c06-chain_drain class tests/test_revision9_coordination_chain_drain.py Revision9ChainDrainTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["chain_drain"]["methods_csv"])')" "refactor(tests): move the chain_drain scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_chain_drain.py (class shape, tier 1)"`
- id map: 6 unittest + 6 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_chain_drain_raw_records_without_capability_refuses` -> `test_revision9_coordination_chain_drain.Revision9ChainDrainTests.test_chain_drain_raw_records_without_capability_refuses`.
- expected refusals: none.

### 3.8 c07 — `terminal_builder` -> `tests/test_revision9_coordination_terminal_builder.py`, class `Revision9TerminalBuilderTests`

- theme: The terminal builder on a bound chain: pending-outbox/missing-landing guards, authenticated abort disposition and its self-event admission controls, explicit-absent and exact-captured chain tombstones (then quarantine), every terminal chain control load-bearing, and the chain-root swap guard after enumeration.
- tests (9, source order = requested order), with inventory line/size/cluster:
  - `test_terminal_builder_guards_pending_outbox_and_missing_landing` L3490-3526 36 lines (cluster 13)
  - `test_terminal_builder_accepts_authenticated_abort_disposition` L3567-3675 93 lines (cluster 13)
  - `test_terminal_abort_disposition_fails_closed_on_shape` L3677-3697 21 lines (cluster 21)
  - `test_abort_disposition_self_event_admission_controls_are_load_bearing` L3735-3765 26 lines (cluster 22)
  - `test_abort_disposition_self_event_source_fact_requires_aborted_unchanged_prior` L3767-3803 32 lines (cluster 22)
  - `test_terminal_builder_accepts_only_explicit_absent_chain_tombstone` L3805-3882 73 lines (cluster 13)
  - `test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine` L3884-3975 86 lines (cluster 13)
  - `test_each_terminal_chain_control_is_load_bearing` L3977-4089 106 lines (cluster 13)
  - `test_terminal_guard_refuses_chain_root_swap_after_enumeration` L4091-4139 47 lines (cluster 13)
- private helpers (4, 123 code lines incl. decorator lines; defined on `Revision9TerminalBuilderTests`, inherited by nobody — see §2b), moved in the same call, in source order among the tests:
  - `_append_test_landing` L3425-3428 4 lines; calls: `_append_test_decision` (same family); test users: 4
  - `_append_test_decision` L3430-3475 46 lines; calls: no helper; test users: 4
  - `_abort_bound_chain_fixture` L3528-3565 38 lines; calls: no helper; test users: 1
  - `_self_event_fixture` L3699-3733 35 lines; calls: no helper; test users: 2
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `_append_test_landing,_append_test_decision,test_terminal_builder_guards_pending_outbox_and_missing_landing,_abort_bound_chain_fixture,test_terminal_builder_accepts_authenticated_abort_disposition,test_terminal_abort_disposition_fails_closed_on_shape,_self_event_fixture,test_abort_disposition_self_event_admission_controls_are_load_bearing,test_abort_disposition_self_event_source_fact_requires_aborted_unchanged_prior,test_terminal_builder_accepts_only_explicit_absent_chain_tombstone,test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine,test_each_terminal_chain_control_is_load_bearing,test_terminal_guard_refuses_chain_root_swap_after_enumeration`
- code lines: tests **520** + private helpers **123** = **643**; estimated module code lines: **665**; provisional baseline entry: **710**
- mixin helpers inherited (direct or transitive): `_new_repo`, `_terminal_control_repo`, `_write_bound_chain_state`, `api_environment`, `open_run`, `run_dir`, `start_task`
- module globals read by the bodies (inventory `globals`): `Path`, `builders`, `contextmanager`, `copy`, `journal`, `json`, `key`, `mock`, `os`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import copy`
  - `import json`
  - `import os`
  - `import unittest`
  - `from contextlib import contextmanager`
  - `from pathlib import Path`
  - `from unittest import mock`
  - `from codex_orchestrator import builders, journal`
  - `from tests._revision9_coord_constants import key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: none
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 3
- note: `_append_test_landing` (private, 4 lines) calls `_append_test_decision` (private, same family) — the one private-to-private call in the wave; both are in this csv, so the mover's remaining-methods check passes.
- dry run / apply / gate: §3.0 with `<label>=c07-terminal_builder`, `<family>=terminal_builder`, `<Family>Tests=Revision9TerminalBuilderTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c07-terminal_builder class tests/test_revision9_coordination_terminal_builder.py Revision9TerminalBuilderTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["terminal_builder"]["methods_csv"])')" "refactor(tests): move the terminal_builder scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_terminal_builder.py (class shape, tier 1)"`
- id map: 9 unittest + 9 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_terminal_builder_guards_pending_outbox_and_missing_landing` -> `test_revision9_coordination_terminal_builder.Revision9TerminalBuilderTests.test_terminal_builder_guards_pending_outbox_and_missing_landing`.
- expected refusals: none.

### 3.9 c08 — `legacy_activation` -> `tests/test_revision9_coordination_legacy_activation.py`, class `Revision9LegacyActivationTests`

- theme: Legacy run activation on first typed use: first-batch artifact substitution refusals, id-only legacy openings, persisted activation candidates and allocation refusals, the atomic first typed use and its crash matrix, byte-golden typed-open artifacts, and global reconciliation deferring torn adopted coverage.
- tests (11, source order = requested order), with inventory line/size/cluster:
  - `test_batch_lock_create_open_substitution_refuses` L4333-4336 4 lines (cluster 24)
  - `test_first_receipt_ledger_create_open_substitution_refuses` L4338-4341 4 lines (cluster 24)
  - `test_first_receipt_ledger_post_create_substitution_refuses` L4343-4405 60 lines (cluster 23)
  - `test_id_only_legacy_opening_activates_with_matching_marker_run_id` L5918-5959 40 lines (cluster 14)
  - `test_persisted_activation_candidate_requires_allocated_id_and_contract` L5961-6058 97 lines (cluster 23)
  - `test_activation_allocation_refuses_unicode_and_oversized_suffixes` L6060-6115 55 lines (cluster 23)
  - `test_removed_batch_lock_after_activation_is_not_recreated` L6117-6141 23 lines (cluster 23)
  - `test_legacy_first_typed_use_atomically_activates` L6896-6989 90 lines (cluster 23)
  - `test_legacy_activation_crash_matrix` L6991-7159 165 lines (cluster 13)
  - `test_typed_opened_run_bytes_are_unchanged` L7161-7360 193 lines (cluster 23)
  - `test_global_reconciliation_defers_torn_adopted_coverage` L7362-7463 96 lines (cluster 23)
- private helpers (1, 60 code lines incl. decorator lines; defined on `Revision9LegacyActivationTests`, inherited by nobody — see §2b), moved in the same call, in source order among the tests:
  - `_assert_first_batch_artifact_substitution_refuses` L4269-4331 60 lines; calls: `_new_repo` (mixin), `_open_legacy_run` (mixin), `api_environment` (mixin), `run_dir` (mixin), `start_task` (mixin); test users: 2
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `_assert_first_batch_artifact_substitution_refuses,test_batch_lock_create_open_substitution_refuses,test_first_receipt_ledger_create_open_substitution_refuses,test_first_receipt_ledger_post_create_substitution_refuses,test_id_only_legacy_opening_activates_with_matching_marker_run_id,test_persisted_activation_candidate_requires_allocated_id_and_contract,test_activation_allocation_refuses_unicode_and_oversized_suffixes,test_removed_batch_lock_after_activation_is_not_recreated,test_legacy_first_typed_use_atomically_activates,test_legacy_activation_crash_matrix,test_typed_opened_run_bytes_are_unchanged,test_global_reconciliation_defers_torn_adopted_coverage`
- code lines: tests **827** + private helpers **60** = **887**; estimated module code lines: **909**; provisional baseline entry: **950**
- mixin helpers inherited (direct or transitive): `_activation_markers`, `_new_repo`, `_open_legacy_run`, `_run_file_bytes`, `api_environment`, `open_run`, `run_dir`, `start_task`
- module globals read by the bodies (inventory `globals`): `batch`, `builders`, `journal`, `json`, `key`, `mock`, `os`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import json`
  - `import os`
  - `import unittest`
  - `from unittest import mock`
  - `from codex_orchestrator import batch, builders, journal`
  - `from tests._revision9_coord_constants import key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: 4 (`test_persisted_activation_candidate_requires_allocated_id_and_contract`, `test_activation_allocation_refuses_unicode_and_oversized_suffixes`, `test_legacy_activation_crash_matrix`, `test_global_reconciliation_defers_torn_adopted_coverage`)
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 4
- note: `test_batch_lock_create_open_substitution_refuses` and `test_first_receipt_ledger_create_open_substitution_refuses` are 4-line wrappers around `_assert_first_batch_artifact_substitution_refuses` (mixin).
- dry run / apply / gate: §3.0 with `<label>=c08-legacy_activation`, `<family>=legacy_activation`, `<Family>Tests=Revision9LegacyActivationTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c08-legacy_activation class tests/test_revision9_coordination_legacy_activation.py Revision9LegacyActivationTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["legacy_activation"]["methods_csv"])')" "refactor(tests): move the legacy_activation scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_legacy_activation.py (class shape, tier 1)"`
- id map: 11 unittest + 11 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_batch_lock_create_open_substitution_refuses` -> `test_revision9_coordination_legacy_activation.Revision9LegacyActivationTests.test_batch_lock_create_open_substitution_refuses`.
- expected refusals: none.

### 3.10 c09 — `receipted_chain` -> `tests/test_revision9_coordination_receipted_chain.py`, class `Revision9ReceiptedChainTests`

- theme: Legacy receipted-chain cases (`_legacy_receipted_chain_case`): commit-sibling receipt request, carried-binding and snapshot-recheck authentication against chain_core, and the activation scan's lock discipline around an external receipted sibling chain (skip, never cross-acquire run locks under concurrency).
- tests (5, source order = requested order), with inventory line/size/cluster:
  - `test_commit_sibling_receipt_request_authentication_is_load_bearing` L4725-4863 136 lines (cluster 25)
  - `test_commit_sibling_carried_binding_authentication_is_load_bearing` L4865-5023 158 lines (cluster 25)
  - `test_commit_sibling_receipt_snapshot_recheck_is_load_bearing` L5025-5123 97 lines (cluster 13)
  - `test_activation_scan_skips_external_sibling_chain_and_run_lock` L5694-5784 87 lines (cluster 1)
  - `test_concurrent_legacy_activation_never_cross_acquires_run_locks` L5786-5916 125 lines (cluster 1)
- private helpers (4, 181 code lines incl. decorator lines; defined on `Revision9ReceiptedChainTests`, inherited by nobody — see §2b), moved in the same call, in source order among the tests:
  - `_bound_chain_outbox` L4540-4568 29 lines; calls: no helper; test users: 5
  - `_acknowledge_bound_chain` L4570-4616 47 lines; calls: no helper; test users: 5
  - `_legacy_receipted_chain_case` L4618-4697 80 lines; calls: `_acknowledge_bound_chain` (same family), `_bound_chain_outbox` (same family), `_open_legacy_run` (mixin), `_write_bound_chain_state` (mixin); test users: 5
  - `_rewrite_commit_events` L4699-4723 25 lines; calls: no helper; test users: 2
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `_bound_chain_outbox,_acknowledge_bound_chain,_legacy_receipted_chain_case,_rewrite_commit_events,test_commit_sibling_receipt_request_authentication_is_load_bearing,test_commit_sibling_carried_binding_authentication_is_load_bearing,test_commit_sibling_receipt_snapshot_recheck_is_load_bearing,test_activation_scan_skips_external_sibling_chain_and_run_lock,test_concurrent_legacy_activation_never_cross_acquires_run_locks`
- code lines: tests **603** + private helpers **181** = **784**; estimated module code lines: **806**; provisional baseline entry: **850**
- mixin helpers inherited (direct or transitive): `_open_legacy_run`, `_write_bound_chain_state`, `api_environment`, `run_dir`
- module globals read by the bodies (inventory `globals`): `CHAIN_CORE`, `Path`, `batch`, `builders`, `contextmanager`, `copy`, `journal`, `json`, `key`, `mock`, `os`, `subprocess`, `threading`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import copy`
  - `import json`
  - `import os`
  - `import subprocess`
  - `import threading`
  - `import unittest`
  - `from contextlib import contextmanager`
  - `from pathlib import Path`
  - `from unittest import mock`
  - `from codex_orchestrator import batch, builders, journal`
  - `from forge_cli import chain_core as CHAIN_CORE`
  - `from tests._revision9_coord_constants import key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: none
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 3
- note: only readers of `CHAIN_CORE` (`from forge_cli import chain_core as CHAIN_CORE  # noqa: E402`) and `threading`; both statements leave the source in this commit. `test_concurrent_legacy_activation_never_cross_acquires_run_locks` starts real threads (`threading.Barrier`, `threading.Thread`) — a timing-sensitive test; a failure here under host load is a stop, not a repoint (brief §8 item 3).
- dry run / apply / gate: §3.0 with `<label>=c09-receipted_chain`, `<family>=receipted_chain`, `<Family>Tests=Revision9ReceiptedChainTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c09-receipted_chain class tests/test_revision9_coordination_receipted_chain.py Revision9ReceiptedChainTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["receipted_chain"]["methods_csv"])')" "refactor(tests): move the receipted_chain scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_receipted_chain.py (class shape, tier 1)"`
- id map: 5 unittest + 5 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_commit_sibling_receipt_request_authentication_is_load_bearing` -> `test_revision9_coordination_receipted_chain.Revision9ReceiptedChainTests.test_commit_sibling_receipt_request_authentication_is_load_bearing`.
- expected refusals: none.

### 3.11 c10 — `activation_scan` -> `tests/test_revision9_coordination_activation_scan.py`, class `Revision9ActivationScanTests`

- theme: Activation scan bounds: unreplayable/unrelated chains are tolerated, oversized state and event artifacts hit byte caps (warn for unrelated, refuse for bound), bounded-path memory errors convert, scan-only caps pass to replay, and chains created between scans are ignored or refused.
- tests (11, source order = requested order), with inventory line/size/cluster:
  - `test_activation_scan_tolerates_unreplayable_unrelated_chain` L5125-5172 46 lines (cluster 13)
  - `test_activation_scan_warns_and_continues_on_oversized_unrelated_state` L5174-5224 49 lines (cluster 13)
  - `test_activation_scan_refuses_oversized_state_bound_to_this_run` L5226-5268 41 lines (cluster 13)
  - `test_activation_state_byte_cap_is_load_bearing_in_memory` L5270-5304 33 lines (cluster 13)
  - `test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one` L5306-5355 48 lines (cluster 13)
  - `test_activation_events_byte_cap_is_load_bearing_in_memory` L5357-5394 36 lines (cluster 13)
  - `test_activation_scan_converts_bounded_path_memory_errors` L5396-5434 36 lines (cluster 13)
  - `test_activation_replay_passes_scan_only_state_and_event_caps` L5436-5516 78 lines (cluster 13)
  - `test_activation_scan_unrelated_tolerance_is_load_bearing` L5518-5537 18 lines (cluster 13)
  - `test_activation_scan_ignores_unrelated_chain_created_between_scans` L5539-5589 48 lines (cluster 26)
  - `test_activation_scan_bound_chain_created_between_scans_refuses` L5591-5692 99 lines (cluster 27)
- private helpers (3, 67 code lines incl. decorator lines; defined on `Revision9ActivationScanTests`, inherited by nobody — see §2b), moved in the same call, in source order among the tests:
  - `_plant_unreplayable_unrelated_chain` L4195-4208 14 lines; calls: no helper; test users: 2
  - `_pad_valid_json_over_cap` L4211-4215 5 lines ['staticmethod']; calls: no helper; test users: 3
  - `_guard_activation_artifact_read_budget` L4218-4267 46 lines ['contextmanager']; calls: no helper; test users: 5
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `_plant_unreplayable_unrelated_chain,_pad_valid_json_over_cap,_guard_activation_artifact_read_budget,test_activation_scan_tolerates_unreplayable_unrelated_chain,test_activation_scan_warns_and_continues_on_oversized_unrelated_state,test_activation_scan_refuses_oversized_state_bound_to_this_run,test_activation_state_byte_cap_is_load_bearing_in_memory,test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one,test_activation_events_byte_cap_is_load_bearing_in_memory,test_activation_scan_converts_bounded_path_memory_errors,test_activation_replay_passes_scan_only_state_and_event_caps,test_activation_scan_unrelated_tolerance_is_load_bearing,test_activation_scan_ignores_unrelated_chain_created_between_scans,test_activation_scan_bound_chain_created_between_scans_refuses`
- code lines: tests **532** + private helpers **67** = **599**; estimated module code lines: **621**; provisional baseline entry: **670**
- mixin helpers inherited (direct or transitive): `_invoke_raw_lifecycle`, `_new_repo`, `_open_legacy_run`, `_write_bound_chain_state`, `api_environment`, `run_dir`, `start_task`
- module globals read by the bodies (inventory `globals`): `UNREPLAYABLE_CHAIN_FIXTURE`, `UNREPLAYABLE_CHAIN_FIXTURE_SHA256`, `UNREPLAYABLE_CHAIN_ID`, `builders`, `contextmanager`, `hashlib`, `io`, `journal`, `key`, `mock`, `nullcontext`, `os`, `patch_chain_core`, `redirect_stderr`, `shutil`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import hashlib`
  - `import io`
  - `import os`
  - `import shutil`
  - `import unittest`
  - `from contextlib import contextmanager, nullcontext, redirect_stderr`
  - `from unittest import mock`
  - `from codex_orchestrator import builders, journal`
  - `from tests._cli_loader import patch_chain_core`
  - `from tests._revision9_coord_constants import UNREPLAYABLE_CHAIN_FIXTURE, UNREPLAYABLE_CHAIN_FIXTURE_SHA256, UNREPLAYABLE_CHAIN_ID, key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: 2 (`test_activation_scan_tolerates_unreplayable_unrelated_chain`, `test_activation_scan_bound_chain_created_between_scans_refuses`)
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 3
- note: only reader of `UNREPLAYABLE_CHAIN_ID` (`test_activation_scan_tolerates_unreplayable_unrelated_chain`) — the name leaves the source's `from tests._revision9_coord_constants import (...)` list here; `io`/`redirect_stderr`/`nullcontext` also leave the source here (last readers).
- dry run / apply / gate: §3.0 with `<label>=c10-activation_scan`, `<family>=activation_scan`, `<Family>Tests=Revision9ActivationScanTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c10-activation_scan class tests/test_revision9_coordination_activation_scan.py Revision9ActivationScanTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["activation_scan"]["methods_csv"])')" "refactor(tests): move the activation_scan scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_activation_scan.py (class shape, tier 1)"`
- id map: 11 unittest + 11 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_activation_scan_tolerates_unreplayable_unrelated_chain` -> `test_revision9_coordination_activation_scan.Revision9ActivationScanTests.test_activation_scan_tolerates_unreplayable_unrelated_chain`.
- expected refusals: none.

### 3.12 c11 — `activation_outbox` -> `tests/test_revision9_coordination_activation_outbox.py`, class `Revision9ActivationOutboxTests`

- theme: Activated-writer guards: the activation outbox reserves first use and drains the exact batch, raw append/lifecycle/open paths are blocked or ordered by the guards (lock order, validation before reservation, writer contract), first-use intents block the outbox before publication, and the internal typed flag cannot bypass activated builders.
- tests (12, source order = requested order), with inventory line/size/cluster:
  - `test_activation_outbox_blocks_raw_append_byte_exactly_then_drains` L6143-6244 97 lines (cluster 13)
  - `test_activation_outbox_lifecycle_guard_is_load_bearing` L6246-6284 37 lines (cluster 13)
  - `test_legacy_raw_guard_intent_conditions_are_load_bearing` L6286-6322 35 lines (cluster 23)
  - `test_raw_lifecycle_validation_precedes_batch_reservation` L6324-6380 54 lines (cluster 13)
  - `test_raw_lifecycle_lock_order_is_load_bearing` L6382-6522 134 lines (cluster 28)
  - `test_published_first_use_intent_blocks_outbox_before_publication` L6524-6577 50 lines (cluster 29)
  - `test_staged_first_use_intent_blocks_outbox_before_publication` L6579-6608 29 lines (cluster 23)
  - `test_raw_open_cannot_supply_writer_contract_before_any_mutation` L6610-6646 37 lines (cluster 13)
  - `test_raw_open_writer_contract_refusal_is_load_bearing` L6648-6677 29 lines (cluster 1)
  - `test_activation_outbox_reserves_first_use_then_drains_exact_batch` L6770-6851 81 lines (cluster 13)
  - `test_activation_outbox_missing_events_or_tampered_state_refuses_first_use` L6853-6894 40 lines (cluster 13)
  - `test_internal_typed_flag_cannot_bypass_activated_batch_builders` L8771-8822 51 lines (cluster 31)
- private helpers (2, 104 code lines incl. decorator lines; defined on `Revision9ActivationOutboxTests`, inherited by nobody — see §2b), moved in the same call, in source order among the tests:
  - `_activation_outbox_case` L4407-4494 87 lines; calls: `_new_repo` (mixin), `_open_legacy_run` (mixin), `_write_bound_chain_state` (mixin), `run_dir` (mixin); test users: 4
  - `_compete_with_activation_outbox` L4496-4512 17 lines; calls: no helper; test users: 2
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `_activation_outbox_case,_compete_with_activation_outbox,test_activation_outbox_blocks_raw_append_byte_exactly_then_drains,test_activation_outbox_lifecycle_guard_is_load_bearing,test_legacy_raw_guard_intent_conditions_are_load_bearing,test_raw_lifecycle_validation_precedes_batch_reservation,test_raw_lifecycle_lock_order_is_load_bearing,test_published_first_use_intent_blocks_outbox_before_publication,test_staged_first_use_intent_blocks_outbox_before_publication,test_raw_open_cannot_supply_writer_contract_before_any_mutation,test_raw_open_writer_contract_refusal_is_load_bearing,test_activation_outbox_reserves_first_use_then_drains_exact_batch,test_activation_outbox_missing_events_or_tampered_state_refuses_first_use,test_internal_typed_flag_cannot_bypass_activated_batch_builders`
- code lines: tests **674** + private helpers **104** = **778**; estimated module code lines: **800**; provisional baseline entry: **850**
- mixin helpers inherited (direct or transitive): `_activation_markers`, `_chain_drain_authorizer`, `_invoke_raw_lifecycle`, `_new_repo`, `_open_legacy_run`, `_run_file_bytes`, `_seed_gh17_wedge`, `_write_bound_chain_state`, `_write_landed_intent_for_last_receipt`, `api_environment`, `open_run`, `run_dir`, `start_task`
- module globals read by the bodies (inventory `globals`): `batch`, `builders`, `contextmanager`, `copy`, `journal`, `json`, `key`, `mock`, `patch_chain_core`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import copy`
  - `import json`
  - `import unittest`
  - `from contextlib import contextmanager`
  - `from unittest import mock`
  - `from codex_orchestrator import batch, builders, journal`
  - `from tests._cli_loader import patch_chain_core`
  - `from tests._revision9_coord_constants import key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: 7 (`test_activation_outbox_blocks_raw_append_byte_exactly_then_drains`, `test_activation_outbox_lifecycle_guard_is_load_bearing`, `test_legacy_raw_guard_intent_conditions_are_load_bearing`, `test_raw_lifecycle_validation_precedes_batch_reservation`, `test_raw_lifecycle_lock_order_is_load_bearing`, `test_raw_open_cannot_supply_writer_contract_before_any_mutation`, `test_activation_outbox_missing_events_or_tampered_state_refuses_first_use`)
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 2
- note: last reader of `patch_chain_core` (`from tests._cli_loader import patch_chain_core  # noqa: E402`, whole statement leaves) and of `contextmanager` (the contextlib import line disappears entirely from the source in this commit).
- dry run / apply / gate: §3.0 with `<label>=c11-activation_outbox`, `<family>=activation_outbox`, `<Family>Tests=Revision9ActivationOutboxTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c11-activation_outbox class tests/test_revision9_coordination_activation_outbox.py Revision9ActivationOutboxTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["activation_outbox"]["methods_csv"])')" "refactor(tests): move the activation_outbox scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_activation_outbox.py (class shape, tier 1)"`
- id map: 12 unittest + 12 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_activation_outbox_blocks_raw_append_byte_exactly_then_drains` -> `test_revision9_coordination_activation_outbox.Revision9ActivationOutboxTests.test_activation_outbox_blocks_raw_append_byte_exactly_then_drains`.
- expected refusals: none.

### 3.13 c12 — `ledger_recovery` -> `tests/test_revision9_coordination_ledger_recovery.py`, class `Revision9LedgerRecoveryTests`

- theme: Recovery of wedged and stale ledgers: the pre-fix golden prefix-wedge fixture, unactivated stale ledgers (refusal, retire-then-successor, raw close, EOF guard), the GH#17 wedge shape (recovery without reapplication, foreign gap run id, activation crash matrix, writer activation controls) and retired-successor close recovery.
- tests (12, source order = requested order), with inventory line/size/cluster:
  - `test_pre_fix_golden_wedge_recovers_and_continues` L7504-7639 129 lines (cluster 30)
  - `test_unactivated_stale_ledger_has_legible_refusal_and_raw_append` L7710-7766 55 lines (cluster 23)
  - `test_unactivated_stale_ledger_retire_then_typed_successor` L7768-7796 28 lines (cluster 23)
  - `test_unactivated_stale_ledger_raw_close_succeeds` L7798-7815 18 lines (cluster 13)
  - `test_unactivated_stale_ledger_eof_guard_is_load_bearing` L7817-7844 28 lines (cluster 23)
  - `test_gh17_shape_recovers_without_reapplication` L8088-8145 56 lines (cluster 1)
  - `test_gh17_shape_refuses_explicit_foreign_gap_run_id` L8147-8167 21 lines (cluster 1)
  - `test_recovery_activation_crash_matrix` L8169-8285 112 lines (cluster 1)
  - `test_writer_activation_controls_are_independently_load_bearing` L8517-8567 51 lines (cluster 1)
  - `test_retired_successor_close_intent_recovers_and_releases_registry` L8569-8607 39 lines (cluster 14)
  - `test_retired_successor_close_recovers_every_stored_suffix_prefix` L8609-8689 81 lines (cluster 14)
  - `test_retired_successor_recovery_rejects_other_run_mutation` L8691-8769 77 lines (cluster 23)
- private helpers (2, 103 code lines incl. decorator lines; defined on `Revision9LedgerRecoveryTests`, inherited by nobody — see §2b), moved in the same call, in source order among the tests:
  - `_restore_prefix_wedge_fixture` L7465-7502 37 lines; calls: `_new_repo` (mixin), `run_dir` (mixin); test users: 1
  - `_seed_unactivated_stale_ledger` L7641-7708 66 lines; calls: `_open_legacy_run` (mixin), `run_dir` (mixin); test users: 4
- methods csv (every moved method, helpers and tests together, in **source order** — the mover writes the sibling class in this order): `_restore_prefix_wedge_fixture,test_pre_fix_golden_wedge_recovers_and_continues,_seed_unactivated_stale_ledger,test_unactivated_stale_ledger_has_legible_refusal_and_raw_append,test_unactivated_stale_ledger_retire_then_typed_successor,test_unactivated_stale_ledger_raw_close_succeeds,test_unactivated_stale_ledger_eof_guard_is_load_bearing,test_gh17_shape_recovers_without_reapplication,test_gh17_shape_refuses_explicit_foreign_gap_run_id,test_recovery_activation_crash_matrix,test_writer_activation_controls_are_independently_load_bearing,test_retired_successor_close_intent_recovers_and_releases_registry,test_retired_successor_close_recovers_every_stored_suffix_prefix,test_retired_successor_recovery_rejects_other_run_mutation`
- code lines: tests **695** + private helpers **103** = **798**; estimated module code lines: **820**; provisional baseline entry: **870**
- mixin helpers inherited (direct or transitive): `_activation_markers`, `_assert_gh17_recovered`, `_invoke_raw_lifecycle`, `_new_repo`, `_open_legacy_run`, `_run_file_bytes`, `_seed_gh17_wedge`, `_write_landed_intent_for_last_receipt`, `api_environment`, `run_dir`, `start_task`
- module globals read by the bodies (inventory `globals`): `PREFIX_WEDGE_FIXTURE`, `PREFIX_WEDGE_FIXTURE_SHA256`, `Path`, `base64`, `batch`, `builders`, `hashlib`, `journal`, `json`, `key`, `mock`, `os`
- expected destination header (mover-computed from those globals plus the copied bases; isort-ordered by `--format-imports`; the dry-run manifest `imports[dest]` is the record):
  - `from __future__ import annotations`
  - `import base64`
  - `import hashlib`
  - `import json`
  - `import os`
  - `import unittest`
  - `from pathlib import Path`
  - `from unittest import mock`
  - `from codex_orchestrator import batch, builders, journal`
  - `from tests._revision9_coord_constants import PREFIX_WEDGE_FIXTURE, PREFIX_WEDGE_FIXTURE_SHA256, key`
  - `from tests._revision9_coord_support import Revision9BuilderBatchSupport`
- subTest users: 3 (`test_recovery_activation_crash_matrix`, `test_writer_activation_controls_are_independently_load_bearing`, `test_retired_successor_close_recovers_every_stored_suffix_prefix`)
- nested `def`s inside bodies (moved verbatim by LibCST; `nonlocal` included): 3
- note: last reader of `base64` (leaves the source here). `test_pre_fix_golden_wedge_recovers_and_continues` reads `hashlib`; the source keeps `hashlib` (two readers in the other classes).
- dry run / apply / gate: §3.0 with `<label>=c12-ledger_recovery`, `<family>=ledger_recovery`, `<Family>Tests=Revision9LedgerRecoveryTests`; driver line:
  `bash .refactor/revision9-coord-cluster.sh c12-ledger_recovery class tests/test_revision9_coordination_ledger_recovery.py Revision9LedgerRecoveryTests "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["families"]["ledger_recovery"]["methods_csv"])')" "refactor(tests): move the ledger_recovery scenario family of Revision9BuilderBatchTests to tests/test_revision9_coordination_ledger_recovery.py (class shape, tier 1)"`
- id map: 12 unittest + 12 pytest entries; first entry `test_revision9_coordination.Revision9BuilderBatchTests.test_pre_fix_golden_wedge_recovers_and_continues` -> `test_revision9_coordination_ledger_recovery.Revision9LedgerRecoveryTests.test_pre_fix_golden_wedge_recovers_and_continues`.
- expected refusals: none.

### 3.14 Stays in `tests/test_revision9_coordination.py`

| symbol | reason |
|---|---|
| `Revision9BuilderBatchTests.test_run_open_process_death_keeps_staging_invisible_and_retryable` (L2117-2195, 75 lines) | inventory verdict **unsupported: unknown decorator** (`@unittest.skipUnless(hasattr(os, "fork"), ...)`); the mover refuses it, so it is listed in no family and stays on the source class, which keeps its post-c00 header and inherits `setUp` and every helper from the mixin. It keeps reading `builders`, `journal`, `json`, `key`, `mock`, `os` from the source module, so none of those imports can be pruned by the wave. Say so in the handover. |
| `Revision9FixtureTests` (L43-176 at HEAD), `Revision9BindingTests` (L8952-11078 at HEAD, 2,125 physical lines), `Revision9MergeTransitionGrammarTests` (L11079-13857 at HEAD, 2,777 physical lines) | never in this class's scope; separate class-shape targets of the same bead **after** this wave closes green (brief §5): run `class_inventory.py` on each then and plan separately. |
| module preamble (imports, `from tests._revision9_coord_constants import (...)`, `sys.path.insert`, `if __name__ == "__main__"`) | shell; only the §5 import removals touch it. |
| helpers | **none stay**: every helper has at least one test user among the 108 (§2b); the skipUnless test's helpers (`_new_repo`, `api_environment`, `run_dir`) are shared and go to the mixin; no helper is used only by it; no helper has zero users (no dead-code candidates). |

## 4. State ownership table

| state | owner module | users |
|---|---|---|
| `self.temporary`, `self.env`, `self.repo`, `self.head` (instance attributes written by `setUp`/`_new_repo`) | `tests/_revision9_coord_support.py` (mixin, after c00) | every family (inherited `setUp`); no family module defines class-level state (the mover refuses class-body statements in class shape; there are none) |
| module constants `ROOT, TOOLS, FIXTURES, PREFIX_WEDGE_FIXTURE, UNREPLAYABLE_CHAIN_ID, UNREPLAYABLE_CHAIN_FIXTURE, JOURNAL_FIXTURE_SHA256, OUTPUT_FIXTURE_SHA256, PREFIX_WEDGE_FIXTURE_SHA256, UNREPLAYABLE_CHAIN_FIXTURE_SHA256, key` | `tests/_revision9_coord_constants.py` (455e436) | families import only what their bodies read: `key` (9 families), `ROOT` (scope_change), `UNREPLAYABLE_CHAIN_ID` (activation_scan); the rest are read by the mixin and by the source's other classes |
| `sys.path.insert(0, str(ROOT / "scripts"))` | executed by `tests/_revision9_coord_constants.py` on import and by the source module | see risk R2 |
| no mutable module-level assignment and no `global` statement exist in the class or the families (inventory `writes`: only the four instance attributes above) | — | — |

## 5. Waves and the source-import removal schedule

Class shape is strictly sequential (one source file, one commit per family, fresh snapshot each time); there is no parallel wave. Wave 0 = c00 (mixin of the 18 shared helpers, §2b). Wave 1 = c01..c12 in this order:

| order | label | first test line | why here |
|---|---|---|---|
| 1 | `c01-cli_diagnostics` | L6679 | inspection cluster (small, clean, exercises aliased-import copy and removal) |
| 2 | `c02-batch_builder` | L266 | source order (first family carrying a private helper: `_leave_base_intent`) |
| 3 | `c03-scope_change` | L828 | source order |
| 4 | `c04-gap_repair` | L1156 | source order |
| 5 | `c05-staging_crashes` | L2007 | source order |
| 6 | `c06-chain_drain` | L2590 | source order |
| 7 | `c07-terminal_builder` | L3490 | source order |
| 8 | `c08-legacy_activation` | L4333 | source order |
| 9 | `c09-receipted_chain` | L4725 | source order |
| 10 | `c10-activation_scan` | L5125 | source order |
| 11 | `c11-activation_outbox` | L6143 | source order |
| 12 | `c12-ledger_recovery` | L7504 | source order |

`remove_imports` is sequence-dependent and absent from the manifest when empty. Names whose **only** readers are in this class (counted at HEAD outside lines 177..8951: each appears once, on its import line; the five preamble constants below were proven class-only by c00 attempt 1, which removed them) leave the source in the commit of their last-reader unit (mixin c00 or a family; helper readers now count for the unit the helper moves with). A missed removal is an `F401` in the source (not ignored there) and fails ruff; an extra removal breaks a remaining body. Everything else the families import (`json`, `os`, `copy`, `hashlib`, `subprocess`, `sys`, `Path`, `mock`, `batch`, `builders`, `journal`, `key`, `ROOT`, `unittest`) keeps readers in the other three classes or the preamble and must **not** be removed. Checked for the private helpers' own globals: `_restore_prefix_wedge_fixture` reads `hashlib`, `shutil` (with `ledger_recovery`), `_assert_first_batch_artifact_substitution_refuses`/`_activation_outbox_case` read `subprocess`/`os`/`copy` — every one of those names keeps a reader outside the class (`hashlib` 2, `shutil` 1, `subprocess` 2, `copy`, `os`, `tempfile` in `Revision9FixtureTests`/`Revision9BindingTests`), so no private helper is the last reader of any source import; the table below is complete. One name survives only through the retained test: `os` has **no** reader outside `Revision9BuilderBatchTests` — it stays because the skipUnless test (decorator `hasattr(os, "fork")` and body) stays; if that test ever moves, `import os` becomes `F401`.

| source import name | statement in the source | reader units (c00 mixin / families) | removed in |
|---|---|---|---|
| `TOOLS` | constants import (name only) | `c00-mixin` | `c00-mixin` |
| `ORCH_TOOLS` | `import codex_orch_tools as ORCH_TOOLS  # noqa: E402` (whole statement) | `c01-cli_diagnostics` | `c01-cli_diagnostics` |
| `redirect_stdout` | `from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout` (name only) | `c01-cli_diagnostics` | `c01-cli_diagnostics` |
| `threading` | `import threading` (whole statement) | `c09-receipted_chain` | `c09-receipted_chain` |
| `CHAIN_CORE` | `from forge_cli import chain_core as CHAIN_CORE  # noqa: E402` (whole statement) | `c09-receipted_chain` | `c09-receipted_chain` |
| `io` | `import io` (whole statement) | `c00-mixin`, `c01-cli_diagnostics`, `c10-activation_scan` | `c10-activation_scan` |
| `redirect_stderr` | contextlib import (name only) | `c00-mixin`, `c10-activation_scan` | `c10-activation_scan` |
| `nullcontext` | contextlib import (name only) | `c02-batch_builder`, `c10-activation_scan` | `c10-activation_scan` |
| `UNREPLAYABLE_CHAIN_ID` | `from tests._revision9_coord_constants import (...)` (name only; `FIXTURES`, `JOURNAL_FIXTURE_SHA256`, `OUTPUT_FIXTURE_SHA256`, `ROOT`, `key` stay) | `c10-activation_scan` | `c10-activation_scan` |
| `UNREPLAYABLE_CHAIN_FIXTURE` | constants import (name only) | `c10-activation_scan` | `c10-activation_scan` |
| `UNREPLAYABLE_CHAIN_FIXTURE_SHA256` | constants import (name only) | `c10-activation_scan` | `c10-activation_scan` |
| `patch_chain_core` | `from tests._cli_loader import patch_chain_core  # noqa: E402` (whole statement) | `c10-activation_scan`, `c11-activation_outbox` | `c11-activation_outbox` |
| `contextmanager` | contextlib import — the last name, so the whole statement goes | `c03-scope_change`, `c07-terminal_builder`, `c09-receipted_chain`, `c11-activation_outbox` | `c11-activation_outbox` |
| `base64` | `import base64` (whole statement) | `c00-mixin`, `c02-batch_builder`, `c04-gap_repair`, `c12-ledger_recovery` | `c12-ledger_recovery` |
| `PREFIX_WEDGE_FIXTURE` | constants import (name only) | `c12-ledger_recovery` | `c12-ledger_recovery` |
| `PREFIX_WEDGE_FIXTURE_SHA256` | constants import (name only) | `c12-ledger_recovery` | `c12-ledger_recovery` |

Expected `remove_imports[source]` (sequential): c00 `TOOLS` (the mixin carries `command`; `io`, `redirect_stderr`, `base64` stay because families still read them — unlike attempt 1, c00 no longer removes `PREFIX_WEDGE_*`/`UNREPLAYABLE_CHAIN_FIXTURE*`) · c01 `ORCH_TOOLS`, `redirect_stdout` · c02..c08 none · c09 `threading`, `CHAIN_CORE` · c10 `io`, `redirect_stderr`, `nullcontext`, `UNREPLAYABLE_CHAIN_ID`, `UNREPLAYABLE_CHAIN_FIXTURE`, `UNREPLAYABLE_CHAIN_FIXTURE_SHA256` · c11 `patch_chain_core`, `contextmanager` (the source's `api_environment` decorator left with c00, so nothing else reads it) · c12 `base64`, `PREFIX_WEDGE_FIXTURE`, `PREFIX_WEDGE_FIXTURE_SHA256`. The dry-run manifest is authoritative; a deviation from this table is a finding to investigate before apply, not a reason to edit an import by hand.

## 6. Provisional `.refactor-baseline.json` entries (config-only commit **before c00**; brief §4 item 1)

`check_file_length.py:check` consults the baseline only for paths that exist and fails only on `n > allowed`, so entries for not-yet-created files are inert and a file created at or under its entry passes. The commit lands **before c00** because `scripts/check_file_length.py` defaults to **500** when `REFACTOR_MAX_LINES` is unset and `.pre-commit-config.yaml` invokes it with only `--baseline .refactor-baseline.json` (no `--max`), so on main every new module over 500 needs its entry before the commit that creates it — the mixin (806) included. The mixin value is **measured**: the re-planned c00 dry run `.refactor/dryrun-revision9-coord-c00-mixin-measure.txt` (`DRY RUN: verified; no files written`; `remove_imports[source] == ["TOOLS"]`; destination header exactly the §2b prediction; 806 code lines = 791 helper lines + 15 header lines) is the c00 record-to-be: the driver's c00 dry run must reproduce it. The ten family values = estimate (§3.1) + 40 lines of margin, rounded up to the next 10, because class-shape dry runs are refused until c00 lands; the calibrated header cost is 15 lines (c00), so the `+22` estimates are conservative. **Preferred:** once c00 is committed, dry-run all 11 families in one pass (dry runs write nothing; families are independent, so destination sizes do not depend on order), count the code lines of each `+++ tests/test_revision9_coordination_<family>.py` hunk, and commit those measured values instead. Finalize replaces whichever values were used with the measured sizes of the committed modules (shrink-only) and re-measures the source entry downward. Under B1 disposition (b) every family entry (and 806) must be re-measured after the bootstrap commit.

```
"tests/_revision9_coord_support.py": 806,
"tests/test_revision9_coordination_batch_builder.py": 630,
"tests/test_revision9_coordination_scope_change.py": 580,
"tests/test_revision9_coordination_gap_repair.py": 820,
"tests/test_revision9_coordination_staging_crashes.py": 590,
"tests/test_revision9_coordination_terminal_builder.py": 710,
"tests/test_revision9_coordination_legacy_activation.py": 950,
"tests/test_revision9_coordination_receipted_chain.py": 850,
"tests/test_revision9_coordination_activation_scan.py": 670,
"tests/test_revision9_coordination_activation_outbox.py": 850,
"tests/test_revision9_coordination_ledger_recovery.py": 870,
```

The mixin (806 measured) is between target and ceiling: a debt row (`quality.py --debt`: reason "18 helpers shared by two or more scenario families of one 109-test class; `_write_bound_chain_state` alone is 240 lines and is read by 5 families", follow-up: the handover bead). `tests/test_revision9_coordination.py` keeps its entry (13222) during the wave — it only shrinks — and gets the measured value at finalize.

Expected source after the wave: 13,222 (base) − ~38 preamble lines moved by 455e436 − 1,599 helper lines (791 in c00, 808 with the families) − 6,661 test lines − ~16 import lines ≈ **4,900 code lines**, i.e. still over 1,000 because `Revision9BindingTests` (2,125 physical lines) and `Revision9MergeTransitionGrammarTests` (2,777 physical lines) remain. Per brief §5 those two classes are the next targets of this session (inventory each, then a separate class-shape plan), started only if this wave closed green and the clock allows (§8 item 7). The handover names them and the measured source size either way.

## 7. Re-exports required in `__init__.py`

None. `tests/` is a namespace directory (no `__init__.py`); nothing imports `Revision9BuilderBatchTests` or any test by name (`grep -rn Revision9BuilderBatchTests tests scripts` finds only the class statement; inventory census: 0 sites, `census_complete: false` treated as empty per brief §5). `__all__` does not exist in these files and must not be created.

## 8. Quality / debt report (`quality.py` expectations)

- Module target 500 / ceiling 1,000 (`.refactor-quality.json`): 10 family modules and the mixin land between target and ceiling -> each needs a debt row (`.refactor/debt-revision9-coord.json`, the brief §7 spelling: reason "scenario family of a 109-test class; 500..1,000 per brief §4", follow-up: the finalize measurement and the handover bead); `cli_diagnostics` and `chain_drain` are under target; the mixin is between target and ceiling (§6). Nothing is over the ceiling.
- Function target 150: three tests exceed it unchanged by relocation — `test_typed_opened_run_bytes_are_unchanged` 193 (legacy_activation), `test_legacy_activation_crash_matrix` 165 (legacy_activation), `test_commit_sibling_carried_binding_authentication_is_load_bearing` 158 (receipted_chain); the mixin's `_write_bound_chain_state` 240 and `_seed_gh17_wedge` 157 likewise. They are extraction candidates for a later tier-2 pass on the destination modules, never a cluster edit (brief: no body edits).
- Class method target 30: after the wave the largest family class has 13 tests + 1 helper (`batch_builder`) or 9 + 4 (`terminal_builder`); the mixin has 18 methods (under target).
- Parameters ≤ 6: no test takes parameters; helpers unchanged.
- Cohesion: every family shares a scenario and at least one non-hub helper or module global (§3 sections); the only tests with no calls beyond hubs (`test_builder_request_schema_and_digest_are_exact`, `test_terminal_abort_disposition_fails_closed_on_shape`) are placed by subject (builder request schema -> batch_builder; abort disposition shape -> `terminal_builder`, next to the other abort-disposition tests).
- Ruff: the temporary glob `tests/test_revision9_coordination_*.py` (cc0bfd7) covers the relocated complexity codes without `I001`. Finalize replaces it with measured per-module entries; expected per module: a subset of `B023, B905, C901, E501, E702, E731, F841, PLR0912, PLR0913, PLR0915, PLR1702, UP012` (PLR0904 cannot trip: no family has more than 20 tests). No family module gets `E402`, `F401` or `I001`.

## 9. Risks the reviewer must check

- **R1 id-map 1:1 and injectivity.** For every family: `len(map.unittest) == len(map.pytest) == len(tests)`; keys are members of the fresh snapshot; values are distinct and spelled `test_revision9_coordination_<family>.<Family>Tests.<t>` / `tests/test_revision9_coordination_<family>.py::<Family>Tests::<t>`; after apply the collectors report exactly the mapped IDs (gate `test-identities` PASS in `mapping` mode) and 1,908 IDs per collector overall. The driver's generator refuses a test missing from the snapshot in either collector.
- **R2 family-module import bootstrap — operator decision (critique B1), see the §0 row.** Mechanism: `--format-imports` orders the third-party `from codex_orchestrator import ...` / `import codex_orch_tools as ORCH_TOOLS` / `from forge_cli import ...` lines **before** the first-party `from tests._revision9_coord_*` lines, and a family module has no `sys.path.insert` of its own (verified on the c00 attempt-1 and measure dry-run headers, which have the same ordering). Not a handover note: the committed Gate 1 cell (run without `PYTHONPATH` by CI and by the main-clone merge chain) would fail on shards whose first import is a family module — the repository's test gate would be red on main while every in-session gate (PYTHONPATH exported by `gate1-revision9-coord.sh`; `REFACTOR_TEST_CMD` discovers the source module first, `.` < `_`) stays green. That is a brief §8 item-4 condition, escalated in the §0 row with the evidence and the three candidate dispositions; c00 may proceed, c01 may not until the operator rules. Two measurements to attach for the ruling: `env -u PYTHONPATH python3 -m unittest tests.test_revision9_coordination_cli_diagnostics` at the post-c01 tip (predicted `ModuleNotFoundError`) and one run of `gate1-revision9-coord.sh` with its `PYTHONPATH` export removed. `tests/_revision9_coord_support.py` is unaffected: it is only ever imported after the constants module.
- **R3 aliased and `# noqa: E402` import removal in the source.** c01 removes `import codex_orch_tools as ORCH_TOOLS  # noqa: E402` (whole statement), c09 `from forge_cli import chain_core as CHAIN_CORE  # noqa: E402` and `import threading`, c11 `from tests._cli_loader import patch_chain_core  # noqa: E402` (its c10 reader `activation_scan` moves first, so c10 removes nothing of it). Check the c01 dry-run diff by hand: the statement (with its trailing comment) is gone, `import codex_orch_tools` does not survive un-aliased, and `ruff check tests/test_revision9_coordination.py` shows no `F401`. The §5 table is the expected schedule; the manifests are the record.
- **R4 aliased import copying into destinations.** c01 needs `import codex_orch_tools as ORCH_TOOLS`, c09 `from forge_cli import chain_core as CHAIN_CORE`, c10 **and** c11 `from tests._cli_loader import patch_chain_core` in the destination header exactly as the source spells them (without the `# noqa: E402`, which the destination does not need). Verify in `imports[dest]` of each dry-run manifest.
- **R5 tests reading module globals other than the 11 constants.** Union over all families (inventory `globals`): `batch, builders, journal` (codex_orchestrator), `ORCH_TOOLS`, `CHAIN_CORE`, `patch_chain_core`, `mock`, `json`, `os`, `Path`, `copy`, `subprocess`, `sys`, `base64`, `io`, `hashlib`, `threading`, `contextmanager`, `nullcontext`, `redirect_stderr`, `redirect_stdout`, plus constants `key`, `ROOT`, `UNREPLAYABLE_CHAIN_ID`. Per-family lists are in §3; none is a mutable global, none is written.
- **R6 test calling another test.** None: inventory `calls` of every test contains only helpers (checked programmatically, 108/108); so no family can lose a call and no cross-family dependency exists. `_append_test_landing`/`_append_test_decision` are helpers despite the name (not `test_`-prefixed; on the mixin after c00).
- **R7 reflection on the class.** `grep` of the class body (HEAD lines 177..8951) for `self.__class__`, `type(self)`, `__module__`, `__qualname__`, `__name__`, `__file__`, `getattr(self`, `setattr(self`: **0 hits**. (The one `__name__` hit in the file, HEAD L8221, is inside `Revision9BindingTests`, out of scope.) `FORGE_SESSION_PID`/`os.getpid()` in `setUp` is process identity, not class identity.
- **R8 fixture-script strings.** Exactly one `program = r'''...'''` block, inside `test_concurrent_admission_and_scope_change_remain_disjoint` (inventory L1534-1587; scope_change, c03). It is a raw string passed to `python3 -c`; the mover keeps it byte-identical (`--strict-bodies`). No other triple-quoted raw string or `textwrap` block exists in the class.
- **R9 subTest.** 36 tests use `self.subTest` (listed per family in §3); subTest IDs are not collected IDs, so the map is unaffected, and the gate's `Ran 144 tests` count is unchanged.
- **R10 the skipUnless test.** `test_run_open_process_death_keeps_staging_invisible_and_retryable` must remain on `Revision9BuilderBatchTests` in the source, with the class header `(Revision9BuilderBatchSupport, unittest.TestCase)`; after c12 the class body is that single test. It is counted among the 144 and must stay collected under its original ID.
- **R11 sizes.** Per-family estimates in §3.1 are test lines + private-helper lines + 22 (calibrated by c00: the real header cost 15); the critic's rule is a hard 1,000. The largest, `legacy_activation`, is 909 (provisional entry 950). Verify each destination with `python3 scripts/check_file_length.py <dest>` after apply (the driver does) and compare with the provisional entry.
- **R12 order and freshness.** Each family's `--test-snapshot` must be the snapshot taken at the merged head immediately before its dry run (the id-map keys must exist in it). Never reuse `tests-revision9-coord-before.json` or c00's snapshot for a family; the driver names each `tests-revision9-coord-<label>.json`.
- **R13 thread/timing sensitivity.** `test_concurrent_legacy_activation_never_cross_acquires_run_locks` (threads with a 5 s barrier) and `test_concurrent_admission_and_scope_change_remain_disjoint` (two subprocesses on a filesystem barrier) are load-sensitive. Brief §6/§8: a failure that is not a collection or import error is a stop; one re-run of the gate from fresh HEAD is allowed.
- **R15 helper methods in a class-shape `--test-only` move (VERIFIED).** Probe by the orchestrator at 455e436: a class-shape `--test-only` dry run with `--methods _append_test_decision,test_builder_request_schema_and_digest_are_exact` (a call-free helper plus a call-free test, so the pre-c00 order check did not fire) returned `DRY RUN: verified; no files written`; the sibling class carries the helper as an ordinary method above the test and the id map covering only the test was accepted. Evidence: `.refactor/probe-revision9-coord-helper-in-class-dryrun.txt`, `.refactor/probe-revision9-coord-helper-in-class-idmap.json` (the probe destination was never written). Each family's dry-run manifest is the record for its own helper set; decorated private helpers (`_guard_activation_artifact_read_budget` contextmanager, `_pad_valid_json_over_cap` staticmethod, both `activation_scan`) rely on the same verbatim-decorator path the mixin shape used in c00 attempt 1.
- **R16 family-private helpers are not inheritable.** A helper moved with a family is defined on that family's sibling class only; no other family can call it (by construction none does today: §2b users column). Any later re-grouping that moves a test to another family must also re-move (or lift to the mixin) every private helper it calls — a new plan, not an ad-hoc edit. The one private-to-private call is `_append_test_landing` -> `_append_test_decision` (both `terminal_builder`).
- **R17 mixin closure.** Every mixin helper's helper calls resolve to mixin helpers (checked programmatically: `_seed_gh17_wedge` -> `_open_legacy_run`, `_write_landed_intent_for_last_receipt`, `run_dir`; `_assert_gh17_recovered` -> `_activation_markers`; `_chain_drain_authorizer`/`_invoke_raw_lifecycle` -> `run_dir`; `_terminal_control_repo` -> `_new_repo`, `open_run`, `start_task`; `_leave_complete_intent` -> `open_run`, `run_dir`, `start_task`; `setUp` -> `_new_repo`). No mixin method calls a family-private helper, so the mixin never depends on a sibling. The mover does not check this for mixin shape; the reviewer does, against the c00 manifest's method list, which must equal §2b exactly.
- **R18 c00 method list is load-bearing.** If c00 moves a helper that §2b marks private (or omits a shared one), a later family dry run refuses with `sibling class would lose calls to remaining methods` (omitted shared helper) or a family module silently inherits a helper it was meant to own (extra helper; harmless at runtime but the sizes and the allocation record diverge). Compare `.refactor/mixin-revision9-coord.json` `methods` with `families-revision9-coord.json` `mixin.methods` before c01.
- **R14 no production change.** `git diff --stat BASE..HEAD -- scripts docs/specs .forge` must be empty after every commit (driver check). The families touch only `tests/test_revision9_coordination.py`, the new module and `.refactor/`.

## 10. Summary table

| order | family | module | class | tests | private helpers | est. code lines |
|---|---|---|---|---|---|---|
| c00 | mixin | `tests/_revision9_coord_support.py` | `Revision9BuilderBatchSupport` | 0 | 18 shared (791 lines) | 806 (measured) |
| 1 | `cli_diagnostics` | `tests/test_revision9_coordination_cli_diagnostics.py` | `Revision9CliDiagnosticsTests` | 4 | 0 (0 lines) | 240 |
| 2 | `batch_builder` | `tests/test_revision9_coordination_batch_builder.py` | `Revision9BatchBuilderTests` | 13 | 1 (16 lines) | 585 |
| 3 | `scope_change` | `tests/test_revision9_coordination_scope_change.py` | `Revision9ScopeChangeTests` | 6 | 0 (0 lines) | 531 |
| 4 | `gap_repair` | `tests/test_revision9_coordination_gap_repair.py` | `Revision9GapRepairTests` | 9 | 2 (114 lines) | 772 |
| 5 | `staging_crashes` | `tests/test_revision9_coordination_staging_crashes.py` | `Revision9StagingCrashTests` | 10 | 0 (0 lines) | 548 |
| 6 | `chain_drain` | `tests/test_revision9_coordination_chain_drain.py` | `Revision9ChainDrainTests` | 6 | 1 (40 lines) | 436 |
| 7 | `terminal_builder` | `tests/test_revision9_coordination_terminal_builder.py` | `Revision9TerminalBuilderTests` | 9 | 4 (123 lines) | 665 |
| 8 | `legacy_activation` | `tests/test_revision9_coordination_legacy_activation.py` | `Revision9LegacyActivationTests` | 11 | 1 (60 lines) | 909 |
| 9 | `receipted_chain` | `tests/test_revision9_coordination_receipted_chain.py` | `Revision9ReceiptedChainTests` | 5 | 4 (181 lines) | 806 |
| 10 | `activation_scan` | `tests/test_revision9_coordination_activation_scan.py` | `Revision9ActivationScanTests` | 11 | 3 (67 lines) | 621 |
| 11 | `activation_outbox` | `tests/test_revision9_coordination_activation_outbox.py` | `Revision9ActivationOutboxTests` | 12 | 2 (104 lines) | 800 |
| 12 | `ledger_recovery` | `tests/test_revision9_coordination_ledger_recovery.py` | `Revision9LedgerRecoveryTests` | 12 | 2 (103 lines) | 820 |
| — | stays | `tests/test_revision9_coordination.py` | `Revision9BuilderBatchTests` | 1 (skipUnless) | 0 | source ≈4,900 after the wave |

Machine-readable copy of the families (order, csv, expected headers, helpers, sizes): `.refactor/families-revision9-coord.json`.

# Reviewer context from the overnight brief 2026-09-23 (operator rulings and allowed deviations)

## Brief section 4 item 1 (config-only prep, including the operator rulings of 11:30 and 14:10)
1. **Config-only prep, before any move** (session-2 lesson): pyproject.toml
   `[tool.ruff.lint.per-file-ignores]` gains two temporary globs, `"tests/test_<stem>_*.py"` and
   `"tests/_<name>_*.py"`, whose list is the source file's current entry (pyproject lines 242,
   244, 245) MINUS `I001`; plus provisional `.refactor-baseline.json` entries for every planned
   module over 500 (added once the plan is approved, still before the first family cluster).
   **Operator ruling 2026-09-23 11:30 on both lanes' stop finding (import bootstrap order):** the
   same config-only prep, in a commit that precedes the mixin commit, adds

   ```toml
   [tool.ruff.lint.isort]
   known-local-folder = ["codex_orchestrator", "codex_orch_tools", "forge_cli", "commitment_paths"]
   ```

   Measured on the whole repository (`ruff check --select I scripts tests system/fr223`): zero new
   findings; a generated header then places `from tests._<name>_constants import ...` above the
   `codex_orchestrator` / `codex_orch_tools` / `forge_cli` imports, so the constants module's
   `sys.path` line runs first and every family module imports standalone without PYTHONPATH.
   The driver keeps lane B's standalone-import check per module. That commit also removes the
   lane's `STOPPED-<name>.md` (superseded by this ruling) and is the only place this ruling is
   applied; the mixin dry run is re-run under it with the same argv before the apply.
   **Operator ruling 2026-09-23 14:10 on both lanes' wave-close stop (legacy-name carve-out):**
   `tests/test_migration.py` `LegacyRuntimeNameCarveOutTests` scans every tracked file for the
   legacy runtime name, and the brief's `tests`-scoped ID and body snapshots under `.refactor/`
   quote that test's own name and fixtures. Ruling: one config-class prep commit per lane adds
   `".refactor/"` to that test's `allowed_prefixes` tuple (the evidence files are verbatim copies of
   test source the test already allows for itself), removes the wave-close `STOPPED-<name>.md`,
   and is followed by the wave-close Gate 1 re-run. This is the one permitted edit to a test
   outside the target file. The separate question of the evidence directory shipping with plugin
   installs is bead forge-plugin-xlt7 (see section 10), not a lane matter.
   Without the glob the gate's `ruff check tests` fails on the first family module that
   inherits a PLR0904/PLR0915 finding. Finalize replaces the globs with measured per-module
   entries and deletes them.

## Brief section 11 (verified tonight, and the three allowed deviations)
## 11. Verified tonight, and the three allowed deviations

Lane A's first run stopped at its first commit because the worktree-local `"forge@forge": false`
did not disable the plugin; section 1 records the corrected layout. Both lanes' second runs
stopped at 02:25 on the import bootstrap order of generated headers (their `STOPPED-*.md` and
critiques hold the shard simulations); section 4 item 1 records the operator's ruling.
Dry-run on a throwaway worktree of 69bc28d (removed afterwards; nothing committed anywhere):
the worktree plus settings file leaves git status empty; the focused discover commands collect
81/85/144 tests; the ID and body snapshots take 5 s and 4 s; `verify.sh --pkg tests ... --fast`
passes every step with the section-1 env; the mixin move of all 31 lane-B1 helpers verifies
clean once the constants module exists; the class-shape dry run before the mixin commit refuses
as designed. Three plugin behaviours do not fit this repository's namespace `tests/` layout;
each has a bounded workaround here and a follow-up in the plugin repo:

1. **rope_move.py fails on the `Path(__file__)`-derived constants** (`ROOT`, `TOOLS`:
   `AttributeError: 'NoneType' object has no attribute 'group'` with `--project tests`; a silent
   no-op with `--project .`). The constants module is therefore hand-written (section 4, item 2)
   under the plan's "layout-only preparation commit" clause; it is disclosed to both reviewers
   and in the handover as the session's one hand-written commit.
2. **The mover replaces `--import-root .` with the collector's top (`tests`)** and would write
   a bare `from _<name>_support import`, unimportable under the Gate 1 cell's
   `python3 -m unittest tests.<module>`. Pass `--import-root "$PWD"` on every mixin and class
   move; the import then reads `from tests._<name>_support import ...`, the form the file's
   existing `from tests._cli_loader import ...` already uses.
3. **verify.sh's type step cannot run mypy over `tests/`** ("Source file found twice under
   different module names", exit 2, whatever MYPYPATH). `REFACTOR_TYPE_CMD` in the worktree
   settings points it at `scripts/forge/forge_cli`, which these sessions must not change; the
   check runs in 4 s against the tracked baseline (234 grandfathered, 0 new) and the production
   diff check in section 4 covers the rest.

A fourth finding shapes the recipe rather than deviating from it: the mixin cannot be moved into
the module that defines the constants its helpers read (`destination import name clash`), hence
the separate `_<name>_constants.py` and `_<name>_support.py`.

## Post-plan facts
- Executed at commits 63dd6b8 (c00) and 40383f3..9b7599a (c01..c12); finalize f20b8e8 (reviewed tip); decompose records .refactor/decompose-records-revision9-coord.json; per-cluster manifests .refactor/mixin-revision9-coord.json and .refactor/family-revision9-coord-<family>.json with body snapshots .refactor/revision9-coord-<label>-before.json and id snapshots .refactor/tests-revision9-coord-<label>.json.
- The 12 families' measured sizes: cli_diagnostics 230, batch_builder 576, scope_change 521, gap_repair 760, staging_crashes 536, chain_drain 424, terminal_builder 655, legacy_activation 896, receipted_chain 799, activation_scan 618, activation_outbox 790, ledger_recovery 810; support mixin 806; source 4,931.
- Non-move commits: 40ea8c1 freeze, cc0bfd7 temporary ruff globs, 455e436 hand-written constants module, 212ccc7 isort ruling, 2da3f4e provisional baseline, a2f86cb pre-check evidence and driver, 73eee2b tests/test_migration.py carve-out ruling, f20b8e8 finalize; d6c3bc3 and 61518ad are stop records (evidence only).
