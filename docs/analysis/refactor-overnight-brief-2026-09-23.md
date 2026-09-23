# Overnight brief 2026-09-23: unattended test-file decompositions (sessions 8, 6, 4)

> Tracked 2026-09-23 as the operator-issued brief **exactly as issued**; historical record, not a live
> instruction set (the lanes it briefed have pushed their branches). Three notes from the review that tracked
> it are recorded here rather than edited into the text: (a) the separate-clone design of section 1 is not
> reflected by the setup and checklist paths given elsewhere (sections 1 and 3 still name the Forge-enabled
> main clone) — anyone reusing this protocol substitutes the refactor clone paths and checks that clone's
> settings; (b) the `rm -rf $TMPDIR` step in the section "7. Finalize, reviews, handover (one per session)" trusts an unresolved environment value — a reuse validates an
> exact lane-specific path and deletes that literal target; (c) the scheduling statement in section 0 and the chain-J
> note in the morning checklist cite `docs/analysis/model-routing-implementation-plan-2026-09-22.md`, a working document
> that is not tracked in this tree — the committed authority for those chains is
> `docs/analysis/model-routing-design-2026-09-20.md` sections 10-12 and the beads epic `forge-plugin-4g68`.

Status: **session brief, operator-issued 2026-09-23, for Fable sessions running the
refactor-python plugin 0.1.3 in forge-plugin worktrees while the operator is away.** The shared
protocol is docs/analysis/refactor-plan-2026-09-19.md; where this brief narrows it (unattended
stop rules, worktree layout, concurrency guards, the three plugin deviations in section 11) this
brief wins for these three sessions only. Where it conflicts with AGENTS.md / CLAUDE.md the
committed rules govern.

## 0. What this batch is and why

Three test-file splits from the plan's order, chosen because nothing in the model-routing chains
(docs/analysis/model-routing-implementation-plan-2026-09-22.md) edits them before chain J, and
because none is an FR-230 subject, so there is no mint and no byte pin to chase:

| Lane | Session | Bead | Target (code lines at 69bc28d) | Big class | Focused set at 69bc28d |
|---|---|---|---|---|---|
| A | 4 | forge-plugin-6g67 | tests/test_revision9_coordination.py (13,222) | Revision9BuilderBatchTests, 147 methods (109 tests, 38 helpers) | 144 tests, 22 s |
| B1 | 8 | forge-plugin-25ms | tests/test_revision8_coordination.py (4,905) | Revision8CoordinationTests, 112 methods (81 tests, 31 helpers) | 81 tests, 35..46 s |
| B2 | 6 | forge-plugin-kzu0 | tests/test_revision9_cli_surfaces.py (5,456) | Revision9BoundCLIIntegrationTests, 77 methods (62 tests, 15 helpers) | 85 tests, 109 s |

Two Fable sessions run at once: lane A does session 4; lane B does session 8 and, when its
handover bead exists, session 6 in a fresh worktree from the same main tip. At most two refactor
worktrees exist at any time, and never more than one Gate 1 cell runs on the host (section 6).

Operator decisions recorded here (the sessions cite this brief instead of asking):

1. The bead dependency edges 6g67 -> 37fr (closed), pot9 -> 6g67, kzu0 -> pot9, tyud -> kzu0,
   25ms -> tyud are ordering suggestions from 2026-09-19. For this batch 6g67, 25ms and kzu0 are
   released to run now and in parallel. Do not edit the dependency graph; note the release in the
   first bead comment.
2. Dropped from the batch, do not start them: the archive-run.py façade half of sweep-1 (the
   split-module inventory at 69bc28d shows 171 top-level symbols, one dominant component of 119 of
   124 defs after 12 hubs, a `global` statement, and the plugin has no façade mode; that needs a
   planner and an operator, not an unattended night), sessions 5 and 7 (FR-230 test subjects,
   id-identical mixin shape, re-mint), fresh_evals.py, chain_core, sweep-2, sweep-3.
3. Each session stops at a pushed branch plus a handover bead. Reintegration through the Forge
   worktree-merge chain is the operator's, in the morning, in the order the handover beads
   were closed (B1, then B2, then A, smallest first so routing's V chain is not stuck behind the
   13k-line merge).
4. Every "ask the operator" in the plan, the skill and the session-2 brief becomes "stop" here
   (section 8). There is nobody to ask. Never bypass, never widen, never hand-edit a body.

## 1. Setup per lane (operator, before launch)

**Layout (corrected twice: 01:25 after lane A's first stop, 11:30 for daytime).** Plugin enablement
for a git worktree is read from the repository's MAIN checkout's `.claude/settings.local.json`, not
from the worktree's own file (verified 01:24: `claude plugin disable forge@forge --scope local` run
inside a worktree wrote to the main checkout's file). So the switch is per repository, and the
refactor lanes now live in a SEPARATE CLONE of the same GitHub remote:
`/home/agents/foundry-of-zero/forge-plugin-refactor` (Forge off in its local settings, which its
own `info/exclude` hides) with one worktree per lane under
`/home/agents/foundry-of-zero/forge-plugin-refactor-wt/<lane>`. The main clone
`/home/agents/foundry-of-zero/forge-plugin` has Forge ON again for the routing and reintegration
sessions; the lanes never touch it except through `bd -C` (its beads) and by reading this brief
and the plan by absolute path. Branches are pushed to origin from the clone and reintegrated from
the main clone exactly as sessions 1 and 2 were. Each lane worktree's own
`.claude/settings.local.json` carries the env block below. The harness does not pass `TMPDIR`
from that block into the shell: every command that runs tests or gates exports
`TMPDIR=/dev/shm/refactor-<lane>` itself. `REFACTOR_TYPE_CMD` points the gate's type step at the
production package (section 11, item 3).

```bash
# lane A (session 4)
cd /home/agents/foundry-of-zero/forge-plugin
git worktree add /home/agents/foundry-of-zero/forge-plugin-wt/s4 -b refactor/split-test-revision9-coordination main
mkdir -p /home/agents/foundry-of-zero/forge-plugin-wt/s4/.claude /dev/shm/refactor-s4
cat > /home/agents/foundry-of-zero/forge-plugin-wt/s4/.claude/settings.local.json <<'JSON'
{"enabledPlugins": {"forge@forge": false},
 "env": {"TMPDIR": "/dev/shm/refactor-s4", "PYTHONPATH": "scripts:scripts/forge", "MYPYPATH": "scripts:scripts/forge",
         "REFACTOR_MAX_LINES": "1000",
         "REFACTOR_TYPE_CMD": "mypy --no-error-summary --no-color-output --show-error-codes --hide-error-context scripts/forge/forge_cli",
         "REFACTOR_TEST_CMD": "python3 -m unittest discover -s tests -p 'test_revision9_coordination*.py'"}}
JSON
cd /home/agents/foundry-of-zero/forge-plugin-wt/s4 && tmux new -d -s refactor-s4 \
  "claude --plugin-dir /home/agents/foundry-of-zero/refactor-python --dangerously-skip-permissions \
   'Read /home/agents/foundry-of-zero/forge-plugin/docs/analysis/refactor-overnight-brief-2026-09-23.md and run lane A (session 4, bead forge-plugin-6g67) to its handover bead. Unattended: stop conditions in section 8.'"
```

```bash
# lane B (session 8 first; the session itself creates the s6 worktree afterwards, section 9)
cd /home/agents/foundry-of-zero/forge-plugin
git worktree add /home/agents/foundry-of-zero/forge-plugin-wt/s8 -b refactor/split-test-revision8-coordination main
mkdir -p /home/agents/foundry-of-zero/forge-plugin-wt/s8/.claude /dev/shm/refactor-s8
cat > /home/agents/foundry-of-zero/forge-plugin-wt/s8/.claude/settings.local.json <<'JSON'
{"enabledPlugins": {"forge@forge": false},
 "env": {"TMPDIR": "/dev/shm/refactor-s8", "PYTHONPATH": "scripts:scripts/forge", "MYPYPATH": "scripts:scripts/forge",
         "REFACTOR_MAX_LINES": "1000",
         "REFACTOR_TYPE_CMD": "mypy --no-error-summary --no-color-output --show-error-codes --hide-error-context scripts/forge/forge_cli",
         "REFACTOR_TEST_CMD": "python3 -m unittest discover -s tests -p 'test_revision8*.py'"}}
JSON
cd /home/agents/foundry-of-zero/forge-plugin-wt/s8 && tmux new -d -s refactor-s8 \
  "claude --plugin-dir /home/agents/foundry-of-zero/refactor-python --dangerously-skip-permissions \
   'Read /home/agents/foundry-of-zero/forge-plugin/docs/analysis/refactor-overnight-brief-2026-09-23.md and run lane B (session 8, bead forge-plugin-25ms, then session 6, bead forge-plugin-kzu0) to their handover beads. Unattended: stop conditions in section 8.'"
```

Main clone facts at issue time: main = origin/main = 69bc28d; refactor-python is on branch
plugin-0.1.3 at d265b57 (plugin.json version 0.1.3); codex-cli 0.155.1 authenticated;
`bd` resolves the main clone's `.beads` from any worktree (verified with `bd context`); a
`git worktree add ... main` plus the settings file leaves `git status` empty (verified).
The main clone carries staged, uncommitted routing docs; the worktrees branch from the `main`
ref and do not see them. Nothing in this brief touches the main clone's working tree.

## 2. Read first, in this order

1. `bd show <your bead>` including comments; docs/analysis/refactor-plan-2026-09-19.md sections
   2, 3 and 5 (the progress log rows for sessions 1 and 2 carry the lessons).
2. `bd recall refactor-session-operating-notes-2026-09-13`, `bd recall app-split-handoff-2026-09-18`,
   `bd recall merge-engine-split-handoff-2026-09-22` (if present).
3. The plugin's skills/decompose/SKILL.md and references/operations.md, in particular the
   "For test shapes" and "Real test files often define shared constants" paragraphs; then
   skills/split-module/SKILL.md phases 0, 1, 6 and 7 and its "Rules that override everything".
4. docs/analysis/refactor-session-2-brief.md for the voice and the finalize/review shape
   (historical; its FR-230 and annotate-self rules do not apply to test-only sessions).
5. .refactor/plan-merge-engine.md and .refactor/critique-merge-engine.md as the planning
   evidence format. Section 11 of this brief before planning: it lists what was verified
   tonight and the three deviations you are allowed.

## 3. Start checklist (run each, print each result; any failure is a stop)

1. `pwd` is your lane's worktree; `git branch --show-current` is your lane's branch; `git log -1`
   is 69bc28d or a later main tip (record it as BASE in `.refactor/`).
2. `cat /home/agents/foundry-of-zero/forge-plugin/.claude/settings.local.json` (the MAIN clone's
   file) shows `"forge@forge": false`; no `forge:*` skill is listed in this session; `env | grep -E
   'PYTHONPATH|MYPYPATH|REFACTOR_'` shows the five values and you export `TMPDIR` yourself;
   `FORGE_SESSION_PID` is unset. No `/forge:*` skill, chain, marker or approval in this session.
   A plain commit works because the Forge commit guard is that plugin's hook. If a `forge:*`
   skill is listed anyway, stop before the first commit (section 8).
3. `bash $S/preflight.sh --decompose` reports no missing REQUIRED tool
   ($S = /home/agents/foundry-of-zero/refactor-python/skills/split-module/scripts,
   $D = /home/agents/foundry-of-zero/refactor-python/skills/decompose/scripts).
4. `.refactor-quality.json` present (module_target 500, module_ceiling 1000, function_target 150,
   class_target 30, max_parameters 6). `.refactor-baseline.json` has your source file's entry.
5. Baseline green: `$REFACTOR_TEST_CMD` passes on the untouched branch and collects the expected
   count (lane A 144, B1 81, B2 85). Record the wall time. (`discover -t . -s tests` is refused
   by unittest because `tests/` has no `__init__.py`; the `-s tests` form is the one that works.)
6. Test-ID freeze: `python3 $D/collect_tests.py snapshot --start tests --out .refactor/tests-<name>-before.json`.
   The auto preset resolves to the namespace layout (top = `tests`, IDs like
   `test_revision8_coordination.Revision8CoordinationTests.test_x`; 1,908 unittest and 1,908
   pytest IDs at 69bc28d, about 5 s). `--top .` and `--preset package` are refused for the same
   reason as item 5; do not try to force them. Never change the preset between snapshots.
7. Source freeze for the manifest oracle: `python3 $S/snapshot_bodies.py snapshot tests --out
   .refactor/before-<name>.json` (2,906 bodies, 4 s). The gate `--pkg` for a test-only session
   is `tests`; the oracle refuses a manifest whose touched files lie outside the compared scope,
   so every per-cluster snapshot and compare uses `tests` too.
8. Gate dry run on the clean tree: `bash $S/verify.sh --pkg tests --snapshot .refactor/before-<name>.json
   --strict-bodies --fast` prints PASS for compile, ruff-lint, file-length, types,
   import-contracts and bodies-unchanged (5 s at 69bc28d with the env of section 1).
9. Commit the freeze evidence as the branch's first commit.

`<name>` is `revision8`, `revision9-cli` or `revision9-coord`. Every evidence file goes under
tracked `.refactor/` with a unique name carrying `<name>`; the movers refuse evidence paths
outside the project, and nothing in `$TMPDIR` or the scratchpad is evidence.

## 4. The shape recipe (identical for the three targets)

Four kinds of commits, in this order, each its own commit and (from the third on) its own
manifest:

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
2. **Preamble prerequisites into a constants module** (the inventory names them, section 5).
   `rope_move.py` cannot do this here (section 11, item 1), so this is the one hand-written
   preparation commit of the session: create `tests/_<name>_constants.py` containing the
   named top-level statements verbatim (same text, same order, keeping `ROOT =
   Path(__file__).resolve().parents[1]`, which resolves to the same repo root from that path),
   the imports they need, and a copy of the source's `sys.path.insert(0, str(ROOT / "scripts"))`
   line when the source has one (so the support module's copied `codex_orchestrator` import
   resolves without PYTHONPATH); delete those statements from the source and add one line
   `from tests._<name>_constants import <names>` at the position of the first removed statement
   (before the source's own `sys.path.insert`, so `ROOT` is bound for it). No other line of the
   source changes. Verify: `ruff check` clean on both files, `$REFACTOR_TEST_CMD` green, and
   `git diff` shows only removed statements plus the one import. Re-collect IDs (identity
   compare against the freeze) and re-freeze the source snapshot after this commit.
3. **Helpers into a support mixin**. `python3 $D/move_methods.py --project . --import-root "$PWD"
   --source tests/<file> --class <BigClass> --methods <setUp plus every non-test_ helper>
   --dest tests/_<name>_support.py --shape mixin --target-class <Name>Support --test-only
   --test-snapshot .refactor/tests-<name>-<n>.json --format-imports --manifest
   .refactor/mixin-<name>.json`, dry run (inspect the diff: the source gains
   `from tests._<name>_support import <Name>Support` and the class header becomes
   `class <BigClass>(<Name>Support, <original bases>)`; the destination gains the helpers
   verbatim, the imports they own, and `from tests._<name>_constants import ...`), then
   `--apply`. `--import-root "$PWD"` is required (section 11, item 2): with the default the
   mover writes a bare `from _<name>_support import`, which the Gate 1 cell cannot import.
   The mixin's name must not contain `Test`; decorated helpers (`property`, `contextmanager`,
   `staticmethod`) travel verbatim in this shape. The mixin cannot live in the constants module
   (section 11, item 4). Gate with `--test-mode identity`. After the commit also run
   `env -u PYTHONPATH python3 -m unittest tests.<module>` once: it proves the `sys.path` line
   in the constants module does its job.
4. **Scenario families in class shape**, one commit per family: `python3 $D/move_methods.py
   --project . --import-root "$PWD" --source tests/<file> --class <BigClass> --methods <tests of
   the family> --dest tests/test_<stem>_<family>.py --shape class --target-class <Family>Tests
   --test-only --test-snapshot <ids> --id-map .refactor/idmap-<name>-<family>.json
   --format-imports --manifest .refactor/family-<name>-<family>.json`. The id map is a JSON
   object `{"unittest": {old: new}, "pytest": {old: new}}` covering exactly the moved tests in
   both collectors (old IDs from the current snapshot; new IDs substitute the module and class).
   The sibling class copies the source class's bases (support mixin first, then the original
   base), so the helpers are inherited; a dry run before the mixin commit is refused with
   "sibling class would lose calls to remaining methods", which is the designed order check.
   New modules are named `tests/test_revision8_<family>.py`,
   `tests/test_revision9_coordination_<family>.py`, `tests/test_revision9_cli_surfaces_<family>.py`
   so the lane's `REFACTOR_TEST_CMD` pattern, the ruff glob and the Gate 1 cell's
   `tests/test_*.py` glob all pick them up; class names end in `Tests` like the source so pytest
   collects them too (both collectors must map 1:1). Gate with `--test-mode mapping`.

Planning rules the critic enforces (a plan that breaks one is rejected, not ruled over):

- Families are the inventory's clusters after hub peeling, merged to 500..1,000 code lines per
  module and named after the scenario (the bead: "planner names them"). A plan with any module
  over 1,000 is rejected at critique: split the family.
- The source module keeps: the classes that were never in scope (lane B2: eight classes;
  lane A: Revision9FixtureTests, Revision9BindingTests 2,125 lines and
  Revision9MergeTransitionGrammarTests 2,777 lines are separate classes and separate targets of
  the same session if the plan reaches them; section 5), the shell of the big class with
  whatever the mover refuses (lane A: the one `unittest.skipUnless`-decorated test, verdict
  "unsupported: unknown decorator", stays in the source class), and `if __name__ == "__main__"`
  if present.
- Every mover call has `--format-imports` (the repository enforces isort). No `I001` in any
  destination per-file ignore.
- Never hand-edit a body, a docstring, a decorator or an assertion. The only hand-written
  commit is item 2 above. Layout pins would be repointed in the same commit as a move under
  the operator's standing permission, but the census found none on these three files (0 sites),
  so any test failure that is not a collection or import error is a stop, not a repoint.
- No production file changes in these sessions. `git diff --stat BASE..HEAD -- scripts docs/specs
  .forge` must be empty at every commit. Therefore no mint, no byte pin, no spec sentence.
- `__all__` does not exist in these files; do not create one. CHANGELOG: one `[Unreleased]`
  entry per branch at finalize, in the style of the MergeEngine entry, shorter, naming the
  hand-written constants commit and the `--import-root` deviation.

## 5. Per-target facts (class_inventory.py at 69bc28d, tonight)

**Lane B1, Revision8CoordinationTests** (tests/test_revision8_coordination.py, lines 28..end,
one class): 112 methods, 109 ok, 3 wrap (`runs_root` and `registry_path` properties,
`api_environment` contextmanager: they move in the helper mixin, not function shape).
Prerequisites: `ROOT` (line 18), `TOOLS` (line 19, 2 users) and `RECORDED_AT` (line 25, 25
users); the source keeps reading `ROOT` for its own `sys.path.insert`. Verified tonight on a
throwaway worktree: with `tests/_revision8_constants.py` holding those three statements and the
source importing them, the mixin dry run of all 31 helpers verifies clean; the destination
header is `from codex_orchestrator import batch, journal` plus `from tests._revision8_constants
import RECORDED_AT, TOOLS`, and the source drops `stat`, `tempfile`, `contextmanager` and the
`batch` import whose last readers moved. Hubs: open_run, run_dir, api_environment,
coordination_snapshot, opening_record, journal_path (all helpers). 31 helpers: setUp, runs_root,
registry_path, run_dir, journal_path, write_record, command, api_environment, opening_record,
task_record, execution_record, execution_result_record, verification_record, decision_record,
closure_record, create_citation_files, open_run, append_record, readmit, retire, close,
coordination_snapshot, write_registry, prime_registry_lock, prime_batch_lock,
assert_absent_registry_node_collision, valid_candidate, assert_invalid_candidate,
assert_valid_candidate, plant_run_state, proven_dead_pid. Clusters after peeling: 19, sizes
52/20/18/7 and singletons; expect 5 to 7 families of 81 tests. Census complete = false with 0
sites: no external reference to the class; treat the census as empty.

**Lane B2, Revision9BoundCLIIntegrationTests** (tests/test_revision9_cli_surfaces.py lines
1254..5755, base `CLI_FIXTURE_SUPPORT.ForgeCLIFixture`; eight other classes stay): 77 methods, 75 ok,
2 wrap (`cli_process_context` contextlib.contextmanager, `normalized_journal_records`
staticmethod). Prerequisites: `ROOT` 24, `ENVELOPE_KEYS` 26, `CLI` 44 (54 users), `CORE` 45,
`RUNTIME` 46, `CLI_FIXTURE_SUPPORT` 49, `key` 54 (18 users); `CLI_PATH` 25, `ENGINE` 47 and
`CANDIDATE` 48 are siblings of the same preamble and move with it so the constants module owns
the whole loader block, including its `from tests._cli_loader import load_script, package_module,
patch_chain_core, patch_engine` line (the source keeps that import too if it still uses
`patch_*`). The loader sweep tests.test_cli_loader must stay green after the relocation, so add
`python3 -m unittest tests.test_cli_loader` to this lane's per-cluster run. 15 helpers:
revision9_environment, cli_process_context, invoke_cli, invoke_cli_at, open_run_and_task,
start_bound_chain, start_bound_fast_chain, configure_changelog_gate,
start_bound_multicell_stack_chain, selected_commit_ingest_event_digests,
normalized_journal_records, prepare_unbound_fast_ingest, _quarantine_and_tombstone,
_journal_records, assert_commit_identity_drain_crash_replays_once. Clusters: 18, sizes 43/9/6/3
and singletons; expect 4 to 6 families of 62 tests. The base class is a runtime-loaded attribute
(`CLI_FIXTURE_SUPPORT.ForgeCLIFixture`); the sibling classes copy that base expression, which
resolves because the constants module is imported first. Verify on the first family's dry run.

**Lane A, Revision9BuilderBatchTests** (tests/test_revision9_coordination.py lines 199..8973):
147 methods, 141 ok, 5 wrap (api_environment contextmanager; _activation_markers,
_run_file_bytes, _pad_valid_json_over_cap staticmethods; _guard_activation_artifact_read_budget
contextmanager), 1 unsupported (`test_run_open_process_death_keeps_staging_invisible_and_retryable`,
line 2117, `unittest.skipUnless(...)`: stays on the source class, say so in the plan and the
handover). Prerequisites: `ROOT` 23, `TOOLS` 24, `PREFIX_WEDGE_FIXTURE` 26,
`UNREPLAYABLE_CHAIN_ID` 27, `UNREPLAYABLE_CHAIN_FIXTURE` 28, `PREFIX_WEDGE_FIXTURE_SHA256` 44,
`UNREPLAYABLE_CHAIN_FIXTURE_SHA256` 51, `key` 61 (75 users); `FIXTURES` 25,
`JOURNAL_FIXTURE_SHA256` 38 and `OUTPUT_FIXTURE_SHA256` 41 move with the block. The block around
lines 1536..1550 is a fixture script inside a string in a test body, not module-level code; the
mover keeps it verbatim. 38 helpers (setUp, _new_repo, api_environment, run_dir, open_run,
start_task, _leave_* x4, _write_* x2, _chain_drain_* x2, _append_test_* x2,
_terminal_control_repo, _abort_bound_chain_fixture, _self_event_fixture, _open_legacy_run,
_activation_markers, _run_file_bytes, _plant_unreplayable_unrelated_chain,
_pad_valid_json_over_cap, _guard_activation_artifact_read_budget,
_assert_first_batch_artifact_substitution_refuses, _activation_outbox_case,
_compete_with_activation_outbox, _invoke_raw_lifecycle, _bound_chain_outbox,
_acknowledge_bound_chain, _legacy_receipted_chain_case, _rewrite_commit_events,
_restore_prefix_wedge_fixture, _seed_unactivated_stale_ledger, _seed_gh17_wedge,
_assert_gh17_recovered, command). Clusters: 37, sizes 44/35/16/6/5/4/3/3/3 and singletons;
expect 9 to 12 families of 108 tests. The other two large classes in the file
(Revision9BindingTests 2,125 lines, Revision9MergeTransitionGrammarTests 2,777 lines) are in
scope for this bead as further class-shape targets after the builder-batch class is done; run
their inventories then, and only start them if the builder-batch wave closed green and the
clock allows (section 8, item 7). The source file must end under 1,000 code lines or carry a
provisional entry with a follow-up bead naming what remains.

## 6. Gates, concurrency and the host

- Per cluster: fresh `snapshot_bodies.py snapshot tests` before the apply; `bash $S/verify.sh
  --pkg tests --snapshot <that> --manifest <manifest> --strict-bodies --test-snapshot <ids>
  --test-mode identity|mapping` (its test step runs `$REFACTOR_TEST_CMD`; lane B2 runs
  `python3 -m unittest tests.test_cli_loader` as well); `python3 scripts/check_file_length.py`
  (the repository's own guard, reads the baseline); commit only on PASS; record `commit,
  snapshot, manifest` in `.refactor/decompose-records-<name>.json`.
- Wave close (after the last family) and finalize: the Gate 1 cell (4 shards, 1,908 tests at
  69bc28d, about 8 min alone) once at wave close and twice consecutively at finalize. Copy
  `.refactor/merge-engine-gate1.sh` to `.refactor/gate1-<name>.sh`, set its `TMPDIR` to the
  lane's, and run it under the host-wide lock and load guard:

  ```bash
  until [ "$(cut -d. -f1 /proc/loadavg)" -lt 24 ]; do sleep 120; done
  flock /dev/shm/refactor-gate1.lock bash .refactor/gate1-<name>.sh <label>
  ```

  The lock serialises Gate 1 across both lanes and any other session that adopts it; the load
  guard waits while the omnipus builds or a routing gate saturate the box (load was 15..120 on
  12 cores tonight; the session-2 lesson is that host load alone fails the real-time
  integration tests). A shard failure with the load under 24 is bisected once with the full
  set per the plan's rule; a second failure is a stop.
- Per-cluster driver: write `.refactor/<name>-cluster.sh` (freeze, dry run, apply, verify,
  file-length, commit) as sessions 1 and 2 did and run the families through it one at a time
  from the merged branch head. No Workflow tool run is needed: the planner and critic are the
  plugin's `split-planner` and `plan-critic` agents you spawn for the plan, the extraction is a
  shell loop, the reviews are step 7. If you do use workflows/decompose.js instead, its
  extractors run in nested worktrees; remove them before the handover.
- Nothing else runs in the worktree while a gate runs. No `pkill -f` of a pattern that appears
  in your own command line.

## 7. Finalize, reviews, handover (one per session)

1. Finalize commit: measured `.refactor-baseline.json` (source entry shrunk or gone, every new
   module over 500 pinned at its measured size, stale pins shrunk), the temporary ruff globs
   replaced by measured per-module entries (copy the source's list, then prune to what `ruff
   check` reports per module), `python3 $D/quality.py <all touched modules> --debt
   .refactor/debt-<name>.json`, the CHANGELOG entry, and `.refactor/decompose-records-<name>.json`.
   `python3 scripts/check_file_length.py` clean; `ruff check tests` clean.
2. Gate 1 cell twice on the finalized tip (section 6), logs under `.refactor/gate1-<name>-run{1,2}.txt`.
3. Codex review detached: `bash $S/codex_review.sh --base BASE --plan .refactor/plan-<name>.md
   --out .refactor/codex-review-<name>.md` under `nohup setsid`, poll the output file. Then spawn
   the plugin's `refactor-reviewer` agent to adjudicate against the manifests at their recorded
   commits; one consensus round on disagreement (`--followup <thread> "<finding>"`), recorded in
   `.refactor/consensus-<name>.md`. Both verdicts are committed as review records; a fix after a
   verdict re-runs step 2 and the reviews on the new tip. Both reviewers get section 11 of this
   brief as context for the hand-written constants commit.
4. Handover bead in the style of forge-plugin-ah1a and r80b: branch, tip SHA, BASE, old-to-new
   path map with per-module code lines, the id-map files, every non-move commit (freeze, config
   prep, constants, provisional baseline, finalize), expected gates for reintegration, debt rows,
   the reviewer verdicts, and the sentence "no production file changed; no mint". Title:
   `HANDOVER: reintegrate <branch> (reviewed tip <sha>) into main through Forge — for the forge
   session`, P1, `bd -C /home/agents/foundry-of-zero/forge-plugin create ...`; comment on the
   session bead with the same tip and close nothing.
5. `git push -u origin <branch>`; the plan's progress-log row is NOT written on this branch
   (the plan doc is on main; put the row text in the handover bead for the operator to land);
   `bd remember` a `<name>-split-handoff-2026-09-23` memory with the lessons.
6. Leave the lane worktree and its `.claude/settings.local.json` in place for the operator;
   remove any nested extractor worktrees and run branches; `rm -rf $TMPDIR`.

## 8. Unattended stop conditions

Stop means: finish nothing further, leave the branch at its last green commit (a failing apply
is reverted with `git checkout -- . && git clean -fd tests .refactor` back to HEAD, never
committed), write `.refactor/STOPPED-<name>.md` with the condition, the command, its output and
the next step you would have taken, commit it, push the branch, comment the session bead with
the same text, and end the session. Do not create the handover bead. Stop when:

1. A mover refusal you cannot plan around by re-clustering within this brief's rules.
2. Any gate failing twice on the same cluster (one re-extraction from fresh HEAD is allowed).
3. Any test that is not a collection or import error failing after a move; any ID compare
   failure; any Gate 1 shard failing twice, or once with `/proc/loadavg` under 24 at start.
4. Anything that would need a production file, a spec sentence, a mint, a body edit, a second
   hand-written commit beyond the constants module, a new base class other than the one support
   mixin per class, or an edit to a test outside the target file and its new siblings.
5. The Codex or Fable reviewer returns BLOCK or REJECT with a finding the consensus round does
   not resolve to advisory with evidence.
6. Lane B only: session 8 stopped, so session 6 is not started (one stop per lane).
7. Clock: if the wave has not closed 14 hours after the session started, close what is merged
   (wave close gate, finalize, reviews, handover naming the families left) rather than start
   another family. A handed-over partial split is worth more than an unfinished one.

## 9. Lane B chaining (session 8 then session 6)

After session 8's handover bead exists and its branch is pushed: from the main clone path, run
the lane setup for `s6` on branch `refactor/split-test-revision9-cli-surfaces` from the SAME
main ref as s8 (not from the s8 branch; the two branches stay independent so the operator can
reintegrate them in any order), with `TMPDIR=/dev/shm/refactor-s6`,
`REFACTOR_TEST_CMD="python3 -m unittest discover -s tests -p 'test_revision9_cli_surfaces*.py'"`
and the same `REFACTOR_TYPE_CMD`, `cd` there, and run sections 2 to 8 again for bead
forge-plugin-kzu0. Remove the s8 worktree only after the operator has reintegrated it.

## 10. Morning checklist (operator)

- Forge is ON in the main clone again (re-enabled 11:30); the lanes run in the separate clone
  (section 1), so nothing to flip.
- `git -C /home/agents/foundry-of-zero/forge-plugin-refactor worktree list`; per lane: the branch
  tip, a handover bead or a `STOPPED-<name>.md`.
- `bd list | grep HANDOVER` and `bd show` each; read the reviewer verdicts and the debt rows.
- Reintegrate in the order B1, B2, A through the worktree-merge chain from the main clone
  (Forge on there; nothing to flip). Each reintegration adds its progress-log row to the plan.
- Reintegration: `git fetch origin` in the main clone, then the worktree-merge chain on
  `origin/<branch>` as for sessions 1 and 2. Remove each lane worktree after its reintegration:
  `git -C /home/agents/foundry-of-zero/forge-plugin-refactor worktree remove ../forge-plugin-refactor-wt/<lane>`.
- Chain J of the routing plan edits journal builders that these tests exercise; land these three
  before J starts, or J rebases over new module paths.
- Plugin follow-ups from tonight's dry runs are in
  refactor-python/docs/plans/2026-09-23-plugin-0.1.4-followups.md.

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
