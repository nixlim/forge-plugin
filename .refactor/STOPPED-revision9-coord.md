# STOPPED: lane A (session 4, bead forge-plugin-6g67), 2026-09-23 13:30 (relaunch of 12:55 under the isort ruling)

Condition: docs/analysis/refactor-overnight-brief-2026-09-23.md section 8 item 3 (a Gate 1 shard failing once with
`/proc/loadavg` under 24 at start: load 4.18 at launch, 4..10 throughout) and item 4 (the only disposition inside the
repository is an edit to a test outside the target file and its new siblings).

## The finding

The wave-close Gate 1 cell (`.refactor/gate1-revision9-coord-wave-close.txt`, head 9b7599a, run WITHOUT `PYTHONPATH`
as CI and the merge chain run it) fails on exactly one test in shard 2/4:
`tests/test_migration.py` line 96, `LegacyRuntimeNameCarveOutTests`, the test that inventories every tracked and
untracked-unignored file (`git ls-files -z --cached --others --exclude-standard`) and asserts that the legacy runtime
name (the 8-letter lower-case string on its line 116; not spelled here because this file would then be one more
violation) appears only in `UPSTREAM`, `scripts/forge/migrate-upstream.py`, `tests/test_migration.py`, `docs/design/**`
and `docs/specs/**`. Shards 1, 3 and 4 pass (414, 389 and 502 tests; shard 2 ran 603 with the one failure and one
skip). Every family module imports and runs standalone without `PYTHONPATH`, so the 02:25 finding (critique B1) is
resolved by the ruling; this is a different mechanism.

The violations are 31 evidence files of this branch, all under `.refactor/`, none under `tests/` (reproduced at HEAD
with `python3 -m unittest tests.test_migration.LegacyRuntimeNameCarveOutTests`; zero violations at BASE 69bc28d):

- the 16 test-ID snapshots `tests-revision9-coord-*.json` (`collect_tests.py snapshot --start tests`): the collector
  records every test ID under `tests/`, and the carve-out test's own method name contains the string;
- the 15 body snapshots `before-revision9-coord.json`, `revision9-coord-c00-before-attempt1.json`,
  `revision9-coord-<label>-before.json` (`snapshot_bodies.py snapshot tests`): the oracle records every body under
  `tests/`, including the carve-out test's, which contains the string as a bytes literal;
- plus, once committed, the Gate 1 log itself (`gate1-revision9-coord-wave-close.txt`, which quotes the failing test's
  name). It is committed verbatim as the evidence of this stop.

So the mechanism is inherent to the recipe, not to a move: any `tests`-scoped ID or body snapshot the brief requires
(section 3 items 6 and 7, section 6) carries the string. Lane B's branches (`refactor/split-test-revision8-coordination`,
`refactor/split-test-revision9-cli-surfaces`) freeze the same `tests`-scoped snapshots and will fail the same test at
their Gate 1; the lane-B beads carry a heads-up comment. The merge-engine session did not hit it because its snapshots
were scoped to `scripts/forge/forge_cli/app`.

Candidate dispositions, none inside this session's authority (recorded, not applied):

- (a) one line in `tests/test_migration.py`: add `.refactor/` to `allowed_prefixes` (evidence records are verbatim
  copies of test source, the same class of content the test already allows for itself). It is an edit to a test
  outside the target file (brief section 8 item 4) and `tests/**` is not a control path, so it needs the operator's
  direction, not a review gate. If ruled: a config-class prep commit on this branch, then Gate 1 re-run at wave close.
- (b) untrack the snapshots: contradicts "every evidence file goes under tracked `.refactor/`" and does not help
  anyway, because the test also scans untracked files unless they are git-ignored; git-ignoring `.refactor/*-before.json`
  and `.refactor/tests-*.json` would hide the record the reviewers adjudicate against.
- (c) re-scope the snapshots (`snapshot_bodies.py` accepts several paths, so a body snapshot of only the touched
  files is possible; the ID collector has no path filter and refuses `--top .` / `--preset package`): would need the
  whole wave re-extracted from fresh HEAD under a scope the brief does not define, and would still leave the ID
  snapshots as violations.
- (d) any other operator ruling (for example an encoding of the evidence files the test does not read).

## What passed before the stop

Branch `refactor/split-test-revision9-coordination` at **9b7599a** (18 commits on 69bc28d, all per-cluster gates PASS):

- 40ea8c1 freeze, cc0bfd7 temporary ruff globs, 455e436 hand-written constants module (unchanged from the 02:25 run);
- 212ccc7 the isort ruling (`[tool.ruff.lint.isort] known-local-folder`), STOPPED file of 02:25 removed, Gate 1 script
  without `PYTHONPATH`, c00 dry run re-run under the ruling: identical to the measure run but the header order, 806 lines;
- 2da3f4e provisional `.refactor-baseline.json` entries (mixin 806 measured, ten families at estimate + margin);
- 63dd6b8 c00: 18 shared helpers -> `tests/_revision9_coord_support.py` (mixin `Revision9BuilderBatchSupport`, 806 code
  lines, identity mode, `remove_imports = [TOOLS]`, method list == plan §2b); `env -u PYTHONPATH python3 -m unittest
  tests.test_revision9_coordination` 144 OK;
- a2f86cb pre-check: all twelve family dry runs verify at the c00 head, every destination under its provisional entry,
  every header places the `tests._revision9_coord_*` imports above the `codex_orchestrator` ones; driver gains the
  standalone no-`PYTHONPATH` step;
- 40383f3 c01 .. 9b7599a c12: the twelve scenario families, class shape, mapping mode, each with gate PASS on all eight
  steps, repository file-length guard OK, production paths untouched, and `env -u PYTHONPATH python3 -m unittest
  tests.test_revision9_coordination_<family>` OK (`.refactor/standalone-revision9-coord-*.txt`). `remove_imports` per
  family == plan §5 for all twelve. Measured module code lines: cli_diagnostics 230, batch_builder 576, scope_change 521,
  gap_repair 760, staging_crashes 536, chain_drain 424, terminal_builder 655, legacy_activation 896, receipted_chain 799,
  activation_scan 618, activation_outbox 790, ledger_recovery 810; source 4,931 (from 13,222). 108 tests moved out and
  in per collector (1,908 IDs before and after); the `unittest.skipUnless` test stays on the source class as planned.
- `ruff check scripts tests system/fr223` clean, `check_file_length.py` clean (246 files), `lint-imports` 5 kept,
  `git diff --stat 69bc28d..HEAD -- scripts docs/specs .forge` empty. No production file, no spec sentence, no mint.

Post-wave inventories (brief section 5, the other two classes), run but NOT started:

- `Revision9BindingTests` (`.refactor/inventory-revision9-coord-binding.{json,md}`): 26 methods all `ok`, 15 tests
  (1,121 code lines), 11 helpers (901); plannable under the recipe. Planner output (split-planner, not yet
  critiqued, nothing moved): `.refactor/plan-revision9-coord-binding.md` / `families-revision9-coord-binding.json`:
  mixin `Revision9BindingSupport` (`setUp`, `binding`; 24 code lines) plus three families `binding_shape` (5 tests,
  544), `binding_resolver` (3 tests + 2 private helpers, 729), `binding_replay` (7 tests + 7 private helpers, 752);
  only `import subprocess` leaves the source; the class ends fully emptied (`pass` body) — a handover item.
- `Revision9MergeTransitionGrammarTests` (`.refactor/inventory-revision9-coord-grammar.{json,md}`): 27 methods, 17 tests
  (2,295 code lines), 10 helpers (384); the class body holds three constants (`CHAIN_ID`, `BASE_AT`, `NEXT_AT`, lines
  2374..2376 at HEAD) and the two hub helpers `_state` / `_transition` use `BASE_AT` / `NEXT_AT` as parameter defaults,
  verdict `unsupported: class-dependent default, annotation, or decorator`. Nearly every test calls them, so no family
  can leave the class without them and they cannot move: not plannable within the brief's rules (it would need a hand
  edit hoisting the constants to module level). Follow-up bead material, not a stop by itself.

## Next step I would have taken (for the relaunch, after the operator rules)

1. Under (a): the one-line carve-out commit (`chore(tests): ...`, prefixed as config-class prep), then
   `flock /dev/shm/refactor-gate1.lock bash .refactor/gate1-revision9-coord.sh wave-close-2` under the load guard
   (expected: four shards OK), then finalize per brief section 7 (measured baseline entries, per-module ruff entries
   replacing the two globs, `quality.py --debt`, CHANGELOG entry naming the constants commit, the `--import-root`
   deviation and the isort ruling, decompose records), Gate 1 twice, Codex review + refactor-reviewer, handover bead.
2. Optionally before finalize, if the clock allows: critique and execute the binding plan (c00b mixin + its families
   through a parameterised copy of the driver); the grammar class goes to the follow-up bead with the finding above.

## State left behind

- Branch at 9b7599a plus this stop commit (Gate 1 log, inventories, planner output, this file); pushed to origin.
  Tracked tree clean; no nested worktrees, no run branches. Worktree `forge-plugin-refactor-wt/s4` and its
  `.claude/settings.local.json` left in place; `/dev/shm/refactor-s4` left (driver outputs and a scratch ID snapshot).
- Bead forge-plugin-6g67: comment with this text; not closed. No handover bead created.
