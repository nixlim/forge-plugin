# Plan critique: scripts/forge/forge_cli/engine.py

Reviewer: an Opus 5 critic run by the orchestrator with the refactor-python plan-critic instructions
(the plugin's plan-critic agent exhausted its 20-turn cap on the 63 KB plan without a verdict; the cap
is raised to 60 in the plugin source, commit d637cb2). Plan reviewed: `.refactor/plan-engine.md` as
written by the split-planner (28 targets), then its revision.

## Round 1 — REVISE (2026-09-17)

Blocking:

- **B1. Quoted `"Engine"` annotations in `_command_lock`.** `_peek_selected_chain` (engine.py:4362),
  `_command_run_lock_id` (4383) and the inner `wrapped(self: "Engine", ...)` of
  `_serialize_worktree_command` (4515) name `Engine` in string annotations; the inventory records only
  `ast.Name` edges, so the plan copied the gap and ruff F821 would fail the wave gate. Fix: the same
  `if TYPE_CHECKING: from forge_cli.engine._engine import Engine` guard `_finalize.py` gets, the
  "module does not exist yet" type-baseline allowance from wave 2, Risk 5 grep expects two guards.
- **B2. Trigger-table window (Risk 7).** After E2 no engine path matches the literal
  `scripts/forge/forge_cli/engine.py` in the `reviewer-routing` / `model-provider-version` rows. The
  critic asked for the table change to precede E2. Rewritten as Option A (land first on main) and
  Option B (accept the window; reintegration verification list). **Operator decision 2026-09-17:
  Option B**, on the grounds that Forge is disabled on the branch, no gate evaluates there, and the
  reintegration candidate both deletes `engine.py` and carries the repointed tables.
- **B3. `plan-engine.json` wave 0 listed `state` and `core` side by side** although `core` references
  `state`. Fix: `[state]`, `[core]`, then 17 / 6 / 2 / 1; prose states the orchestrator runs E0, E1,
  E2 and the finalize wave by hand.

Advisory (round 1): `_ARCHIVE_MODULE` root re-export reads `None` after the split (nothing reads it;
follow-up bead); E0 accepted and flagged (62 sites, not ~70); E1 accepted and flagged — five fixtures
patch `runtime.SCRIPT_DIR`, so a SCRIPT_DIR-based target is not value-identical under tests (confirmed
by the E1 gate: `test_cli_merge_adapters` failed; E1 now resolves the shim from `runtime.__file__`);
only `_engine.py` (3,678 lines) is over budget; `external_dependents` in the inventory is empty but all
222 moved names are re-exported; nothing beyond E0/E1 departs from a pure move.

## Round 2 — APPROVE (2026-09-17)

All three fixes verified mechanically: guard present in the cluster, wave entry and Risk 5; no other
quoted annotation exists (`grep -c '"Engine"'` = 3); 28 clusters, 223 symbols assigned once, no
intra-wave edge, only backward edge `FinalizeContext -> Engine` (annotation-only); Option B's
reintegration list is complete and executable. Advisory: state the exact site count (62 — applied);
make the JSON's scope explicit (the sentence under `## Waves` does); reword "minus the one
`TYPE_CHECKING` edge" (applied).

Unfinished: the final `__init__.py` code-line count is an estimate (measure in the finalize wave).
