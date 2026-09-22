# Plan critique: MergeEngine decompose (plan-merge-engine.md) — plan-critic, 2026-09-22

Reviewed at branch refactor/split-merge-engine d3946d7 (main d885f97 + P0 6ee38b6 + P1 d3946d7). Read-only on the
project tree except this file. Independent evidence came from a throwaway clone of the project at d3946d7
(`.../scratchpad/critic-merge-engine`, removed when done) with P0b and P2 reproduced as local commits, and a worktree of
that clone at the planner's sim tip 7faa07f (fetched read-only from `sim-merge-engine`, which was not modified).
Plugin refactor-python 0.1.2 (db96360).

VERDICT: REVISE (the plan is sound; three items must be resolved before c01 is committed — two of them are operator
nods the plan already asks for, one is an evidence-commit defect)

BLOCKING:
- B1. UP037 / P0b is real and blocks c01 as the branch stands. Reproduced independently: c01 applied on d3946d7
  (P0 glob without UP037) -> `ruff check` 4x UP037 (`_engine_final_mode.py:26,45,83,143`, `self: "MergeEngine"`),
  and `verify.sh --fast` -> `GATE: FAIL` (ruff-lint). Same tree plus a one-token P0b (`"UP037"` appended to the
  `app/_engine_*.py` glob) and P2 -> `PASS compile, ruff-lint, file-length, types, import-contracts,
  bodies-unchanged` / `GATE: PASS`. Minimal: the code list is `select` = E,F,I,B,UP,C90,PLR… (pyproject.toml:28);
  ruff has no UP037 setting other than ignoring it, a `# noqa` or unquoting is a signature edit the oracle rejects
  (planner's probe), and a repo-wide ignore would be broader. I AGREE WITH OPTION A: one config-only P0b commit,
  scoped to the glob only, with UP037 kept per module at finalize (§5 lists it in all 27 entries — re-measured, below),
  optional (C) quote-stripping later as its own declared commit. It changes the brief's "minus I001" definition of
  the glob and adds a code `_merge_engine.py` does not carry, so it needs the operator's explicit nod BEFORE c01.
  I001 is correctly absent from the glob and from every proposed `_engine_*` entry.
- B2. P2 must be committed before c16 (the plan says so) — and needs the operator's nod as a new grandfathered
  entry set. Confirmed from both copies of `check_file_length.py` (project `scripts/` and the plugin copy
  `verify.sh` runs with `"$PKG"` only and the cwd default `.refactor-baseline.json`): `check()` iterates files found
  on disk and consults the baseline by `os.path.normpath` key only for those, so an entry for a missing file is
  inert; the only failure for a listed file is `n > allowed`, so a file created at exactly its entry passes. No
  stale-entry check exists. The pre-commit `max-file-length` hook and CI `guardrails.yml` use the same script with
  `--baseline .refactor-baseline.json`. The three values equal the recounted destination sizes 591/621/830.
- B3. The planner's evidence helpers will fail the pre-commit hook when committed. `ruff check
  .refactor/merge-engine-sim-tool-*.py` under the project config: 65 findings (58 E501 at line-length 100,
  3 I001, 2 E741 `l`, 1 E401, 1 B007) in driver/probes/reader_check/types_delta; `.refactor/` is not in
  `extend-exclude`, and `.git/hooks/pre-commit` runs `ruff-check` on staged `*.py`. Fix before staging: wrap the
  lines and fix the imports in those four helpers (they are evidence tooling, not moved code). Do not add a
  per-file-ignore, do not commit with `--no-verify`. The tracked precedents `.refactor/types_delta.py` and
  `.refactor/add_fr230_subjects_engine_verbs.py` are clean.

ADVISORY:
- A1. Completeness and order verified mechanically from `merge-engine-inventory.json` against the 29 plan argv
  lines and `merge-engine-sim-clusters.json`: 93 methods = 86 moved + 7 stay, no duplicate, none missing, every
  cluster's `--methods` list in ascending source-line order, every argv carries `--shape function --annotate-self
  --format-imports`, all 29 dry-run evidence files say `DRY RUN: verified; no files written` and match the plan's
  argv. Inventory: 78 ok + 15 wrap (12 staticmethod, 1 classmethod, 1 property, 1 contextlib.contextmanager),
  `reasons`/`mangled` empty for all 93. No module-level state and no `global` (plan §3), so state ownership is
  `__init__` on the shell only. Cross-cluster `self.` calls are not flagged (function shape resolves them through the
  class attribute in any order).
- A2. Shared destinations: on the final sim tree all 27 `_engine_*` modules carry exactly one top-level
  `if TYPE_CHECKING:` block, all 27 byte-identical (`from forge_cli.app._merge_engine import MergeEngine`);
  c03/c17 reused it. c03/c17 must be dry-run only after c01/c15 are committed (manifest baseline digests the
  existing destination) — the plan says so.
- A3. Sizes recounted with `scripts/check_file_length.py`'s `code_lines` on the sim tip: all 27 destinations and the
  shell (224) equal plan §4 exactly; 0 over 1,000; exactly three over 500 (591/621/830). Full-repo length check on
  the sim tip with P2: `ok: 221 files within budget`.
- A4. Type gate re-run (`type_baseline.py check --pkg scripts/forge/forge_cli`, `PYTHONPATH`/`MYPYPATH` =
  `scripts:scripts/forge`, `FORGE_SESSION_PID`/`REFACTOR_TYPE_CMD` unset): sim tip `types ok: 234 error(s), all
  grandfathered (0 fixed since baseline)`, and the same at c01 560cc17, c03 41ce352 (classmethod; `cls:
  "type[MergeEngine]"`, i.e. annotate-self types `cls` correctly), c07 ce6a5e3 (`store` reader: 5 `self.store`
  reads), c16 9bb4fca (contextmanager, 11 `self.store` reads), c17 883604d, c20 6927b6e. Also PASS on my own c01
  apply. The planner's per-cluster NEW=0/GONE=0 lines (29/29) agree. 75 receiver annotations = 74 `self` + 1 `cls`.
- A5. Census (9 class-level sites, all tests/test_cli_merge_integration.py 1160/5097/5110/5249/5312/5401/5415/5424/
  6568): dispositions correct. `_push_classification` stays a `staticmethod` in the class dict (unbound call yields
  the plain function, as before); `patch.object(CLI.MergeEngine, '_complete_epoch_fetch_locked')` and the
  `_head_contained` tripwire replace and restore the class-dict object whatever it is; `autospec=True` on
  `_run_carried_successor_ancestry` introspects a plain function whose first parameter is `self` both before and
  after (a `def` in the class body was also a plain function). `_recording_common_lock`: nothing in scripts/ or
  tests/ reads `__wrapped__`, `inspect.getsource`, `__qualname__`, `__module__`, `get_type_hints`/`eval_str` or pickles
  it; the only test mention (test_cli_loader.py:308) is a string sample for the patch-sweep classifier. Planner's
  probes re-run on the sim tip: 12/12 PASS.
  NOT in the census: ~60 instance-level `mock.patch.object(engine, "<moved name>", ...)` sites (e.g.
  integration 455 `_run_carried_successor_ancestry`, 3201 `_prepare_git_no_lazy_fetch_qualification`, 4089/4287
  `_final_history_mutation_mode`, 744 `_read_only_recovery_flag_state`; lifecycle 49/4214/4630/4650 …). They are
  unaffected (an instance attribute shadows any class attribute and is deleted on exit) and all live in the four
  merge test modules of the focused set. Say so in the handover instead of "9 sites" alone; `census_complete: false`
  is the inventory's honest flag.
- A6. Import hygiene on the sim tip: reader check (planner tool) -> 0 through-module readers of the 19 pruned
  names; independent `git grep _merge_engine` outside the app package finds only config, the FR-230 manifest,
  `app/__init__.py:36` and `app/_dispatch.py:4` (both import `MergeEngine` only). `patch_app` is package-root +
  pkgutil enumeration (tests/_cli_loader.py:76-139), not a through-module reader, and new submodules are enumerated
  automatically. `git diff d885f97 7faa07f` touches no file under tests/ and not `app/__init__.py` (so `__all__` is
  verbatim). AST: no `_engine_*` imports `_merge_engine` or another `_engine_*` at runtime; each module imports first
  in a fresh interpreter. `lint-imports`: `Contracts: 5 kept, 0 broken`. The pruned-name check is per cluster in
  the brief: the manifest JSON (which the planner's tool reads) exists only after `--apply`, so before each apply
  take the names from the dry-run's printed manifest `remove_imports` and grep them (the union is already known to
  be clean; this is procedure, not a new risk).
- A7. Finalize layer row re-probed independently on the sim tip (row inserted between `_merge_engine` and the
  bottom row): `lint-imports` rc=0, `5 kept, 0 broken`. Control: with `exclude_type_checking_imports = false` both
  `forge_cli.engine layers` and `forge_cli.app layers` BREAK — the session option is load-bearing and the row is
  genuinely enforced.
- A8. Finalize ruff entries re-measured on the sim tip with the glob removed and the shell entry emptied: all 27
  per-module code sets and the shell's `E501, I001, UP035` equal §5 exactly; the union is the P0 list + UP037.
- A9. c01 real-gate items the sim's `--fast` gate did not cover (measured on my c01 apply): FR-230
  `tests.test_fr230_phase3_manifest` fails 3 tests (generation / real-pass-results) from c01 until the wave-close
  mint, as expected; `tests.test_fr223_v2_byte_pins` and `tests.test_repo_conformance` pass at c01. Keep digest tests
  out of REFACTOR_TEST_CMD (the plan does). No intermediate cluster SHA is a reintegration candidate. Note the project's
  P1 already re-minted (fixtures + byte pin differ from the sim's P1, which did not mint); the sim's forge_cli tree and
  type baseline are identical to the project's, so no gate number changes.
- A10. CHANGELOG: P0's entry says "Two prep commits precede the moves"; with P0b and P2 there are four. Amend at
  finalize and also record there (and in the debt report) the reflection changes the session-1 Codex review
  flagged: moved functions' `__module__` becomes `forge_cli.app._engine_<x>`, `__qualname__` loses `MergeEngine.`,
  bound methods are no longer picklable by qualified name, and the receiver annotation is the string `"MergeEngine"`
  (autospec/`inspect.signature` show `self: "'MergeEngine'"`; nothing in the repo evaluates it).
- A11. Mover output style the operator will see at c01: one blank line between top-level functions in the
  destination (E302 is preview-only and not selected, so ruff passes); the three bindings after `__init__` have no
  blank line; the header is `--format-imports` sorted (`from typing import TYPE_CHECKING, Any, Mapping`, `from
  forge_cli import chain_core, engine, runtime`), so the plan's "destination imports" list (manifest order) is not the
  literal header. None of this may be tidied in tier 1.
- A12. §7 per-cluster focused set (operator decision; shape comment only). The shape is sound but probably
  unnecessary: `.refactor/merge-engine-timing/summary.txt` already measures the seven modules individually —
  loader 1.4 s, store 0.7 s, adapters 27 s, lifecycle 105 s, integration 148 s, shard1 166 s, shard2 131 s — run
  concurrently, all rc=0. A REFACTOR_TEST_CMD that runs the same seven modules as parallel processes (fail-closed
  like the Gate 1 cell: every process exit 0 and a `Ran N tests` summary) keeps the FULL set per cluster at ~3 min
  wall (~1.5 h over 29) instead of choosing a subset. If a subset is chosen anyway, the census/instance-patch
  clusters (c01, c03, c15, c17, c18, c19, c20, c23, c27, c29) and the over-500 ones need the integration modules;
  lifecycle covers c04-c06, c10-c11. Evidence of one concurrent pass is not evidence of no cross-process
  interference: if the parallel form is adopted, run it twice on the untouched branch first.
- A13. Dead-code candidates (§1) correctly not deleted; `_head_contained` correctly kept (tripwire needs the
  attribute). quality.py still exits 1 after the wave (24 functions > 150) — the tier-2 checkpoint is mandatory, as
  the plan says. Debt rows for the three over-500 modules are present with `tracking`.

c01 specifics:
- Order correct: 33-43 (staticmethod), 45-62, 64-100, 6201-6259, 6261-6305, 6871-6872 (staticmethod). My dry run
  in the clean clone with the plan's exact argv is BYTE-IDENTICAL to `.refactor/dryrun-merge-engine-c01-final_mode.txt`
  (`diff` exit 0); source digest `3e51b4cc…2fd63` = project d3946d7 = manifest `baseline`.
- Expected bindings (at apply, in my clone): `_merge_engine.py:32-34` `_final_mode_unavailable =
  staticmethod(_engine_final_mode._final_mode_unavailable)`, `_prepare_git_no_lazy_fetch_qualification = …`,
  `_prepare_bootstrap_git_no_lazy_fetch_qualification = …` (directly after `__init__`, no blank line);
  `:6134-6135` `_final_history_mutation_mode`, `_park_invalid_final_history_mode`; `:6699`
  `_current_merge_authority = staticmethod(…)`. Source import `from . import _engine_final_mode` at line 21.
  `remove_imports`: none (absent from the manifest). `type_checking_imports`: `from forge_cli.app._merge_engine
  import MergeEngine`.
- Destination header (11 lines): `from __future__ import annotations` / `import copy` / `from pathlib import Path` /
  `from typing import TYPE_CHECKING, Any, Mapping` / `from forge_cli import chain_core, engine, runtime` /
  `from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Refusal, V2ReasonCode` / `if TYPE_CHECKING:`
  block. Sizes 177 / 10138.
- Post-apply checks the session should run and show the operator: `MergeEngine.__dict__` types for
  `_final_mode_unavailable` and `_current_merge_authority` are `staticmethod` and `_recover_can_reach_final_mode`
  (still a real classmethod here) reaches `cls._current_merge_authority` (verified: staticmethod, staticmethod,
  classmethod; `MergeEngine._current_merge_authority({})` callable unbound); `__module__` of the moved functions
  is `forge_cli.app._engine_final_mode`; the instance attribute write `self._git_no_lazy_fetch_qualification = …`
  in the moved `_prepare_*` functions type-checks (types NEW 0/GONE 0); `ruff` shows no F401 in `_merge_engine.py`.
- Gate: snapshot AFTER committing P0b and P2 (`snapshot_bodies.py snapshot scripts/forge/forge_cli --out
  .refactor/merge-engine-c01-before.json`), full `verify.sh` (not `--fast`) in the stated env, types delta file,
  then the commit = `_merge_engine.py`, `_engine_final_mode.py`, `.refactor/merge-engine-final_mode.json`,
  `.refactor/merge-engine-c01-before.json`, `.refactor/types-delta-merge-engine-final_mode.txt`, gate log.
  Focused set (the plan's seven modules) on my c01 apply: `Ran 247 tests in 619.505s` / `OK`, rc=0 — same 247 as the
  untouched-branch baseline.
