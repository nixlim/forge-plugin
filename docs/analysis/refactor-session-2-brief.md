# Session 2 brief: MergeEngine split (bead forge-plugin-37fr)

Status: **historical session brief, not authority.** The session it briefed is complete
(reintegrated as `657f6c1`). Its provisional-baseline rule (500–1,000-line modules with a
`.refactor-baseline.json` entry and a debt row) was a session-scoped operator direction, not a
standing permission; where this brief conflicts with `AGENTS.md` / `CLAUDE.md` the committed
rules govern. See the status note at the head of `refactor-plan-2026-09-19.md`.

This brief was handed to SESSION 2 of docs/analysis/refactor-plan-2026-09-19.md (bead
forge-plugin-37fr, closed; the text below is preserved as issued and is no longer actionable):
splitting MergeEngine (scripts/forge/forge_cli/app/_merge_engine.py, 10,302 code lines, 93
methods) along its seams with the refactor-python plugin's `decompose` skill at tag 0.1.2,
function shape. Session 1 (Engine, bead forge-plugin-321p) is your template; this session is
three times its size, so follow its lessons exactly.

## Read first, in this order

1. `bd show forge-plugin-37fr` INCLUDING ALL COMMENTS. The comments carry the session-1 lessons,
   two operator decisions (the prep commit and the `store` property), and verified trial results.
2. docs/analysis/refactor-plan-2026-09-19.md (shared protocol, start and end checklists).
3. Beads memory: `bd recall engine-class-split-handoff-2026-09-20`,
   `bd recall refactor-session-operating-notes-2026-09-13`, `bd recall app-split-handoff-2026-09-18`.
4. The plugin's skills/decompose/SKILL.md and references/operations.md, and
   .refactor/plan-engine-class.md plus .refactor/critique-engine-class.md from session 1.

## Start checklist

Run the START CHECKLIST from the plan literally and print each result: Forge disabled in
.claude/settings.local.json ("forge@forge": false; restore it at the end), clean tree on main,
main tip SHA recorded, branch refactor/split-merge-engine created, `preflight.sh --decompose`
clean, plugin version 0.1.2 (`grep '"version"' <plugin>/.claude-plugin/plugin.json`),
.refactor-quality.json present, and these six variables visible in your shell: PYTHONPATH and
MYPYPATH (both `scripts:scripts/forge`), REFACTOR_TEST_CMD, REFACTOR_MINT_CMD,
TMPDIR=/dev/shm/forge-gate, and FORGE_SESSION_PID unset. The operator exported them before
launch; confirm, do not assume. Then the focused test set green on the untouched branch. Record
how long the focused set takes; if it is over ten minutes, propose a smaller per-cluster set
to the operator and keep the full set for wave close. If any item fails, stop and say so.

## Order of commits on the branch

1. Config-only prep: a temporary ruff per-file-ignores glob for
   scripts/forge/forge_cli/app/_engine_*.py whose code list is the current _merge_engine.py
   entry MINUS I001. Commit message says config-only, relocated grandfathering, temporary
   until finalize. Finalize replaces it with measured per-module entries and deletes the glob.
2. Type-only prep: the `_recording_common_lock` annotation fix exactly as the bead's
   2026-09-22 comment specifies (replace Iterable with Iterator in the import and in the
   return annotation, expect mypy 241 -> 234 with NEW 0 and GONE 7, update the type baseline,
   re-mint, its own commit). Any other delta: stop and report.
3. Tier 1 clusters, one commit each, pure mover output.

## Rules that override everything else

- Every move: move_methods.py with --annotate-self --format-imports, dry run then --apply,
  manifest under .refactor/ with a unique name. Every cluster passes verify.sh with its own
  fresh snapshot (scope = the gate's --pkg, scripts/forge/forge_cli, no tests directory) and
  its manifest before it is committed. All evidence lives under tracked .refactor/, never in
  a scratch directory.
- Type gate: stop on NEW or LOST mypy keys. With --annotate-self the expected delta per
  cluster is zero both ways. Record each cluster's delta in .refactor/types-delta-*.txt.
- Never hand-edit a function or class body. A refusal is a planning result: re-plan or report.
- Function shape only; no mixins, no new base class. The `store` property stays on the class
  shell; the inventory flags it with a note. __init__ and the two instance attributes stay too.
- Plan to 500 code lines per module. Modules between 500 and 1,000 need a provisional
  .refactor-baseline.json entry and a debt row; a plan with any module over 1,000 is rejected
  at critique, so split a seam in two rather than rule it over. The seven seams cover about
  5,600 lines; the planner must assign the remaining ~4,700 explicitly. Several clusters may
  share one destination module; 0.1.2 supports that.
- FR-230: every new app/_engine_*.py is a production subject. `verify.sh --mint` at wave close
  and finalize; commit manifest, fixtures and byte pin with the wave. Digest tests stay out of
  the focused per-cluster set.
- Census: the nine CLI.MergeEngine sites in tests/test_cli_merge_integration.py keep working
  under bindings; confirm from the census output, expect no repoint. Layout pins are repointed
  in the same commit as the move; behaviour tests are never edited. Before each apply, check
  that no import the mover prunes from _merge_engine.py is read or patched from outside
  through that module; if one is, use --retain-module-api for that cluster and say why.
- __all__ verbatim. Never commit to main, never force-push, never touch .forge/ (except via
  mint), .codex-orchestrator/, .worktrees/, .codegraph/.
- Do not read the whole module into your context; use the inventory and targeted reads.

## Cadence

Run the phases by hand through planning and critique, then pause and show the operator the
dry-run diff and manifest of the FIRST cluster and its gate result before committing it. After
approval, run the remaining tier 1 clusters unattended with a per-cluster driver as session 1
did, stopping only on the conditions below. Report after each phase in a few lines.

## Tier 2

After every tier 1 cluster is merged and the wave is closed, stop and give the operator a
checkpoint: module sizes, the debt report, and a tier 2 proposal for the eight methods over
250 lines using function_inventory.py block candidates and extract_ranges.py (nested ranges
are supported; rope refuses mid-range returns; more than six parameters means re-plan, not a
state object). The operator decides then whether tier 2 rides on this branch as a second wave,
in separate commits, or becomes a follow-up bead like forge-plugin-stfj. Tier 3 is out of
scope (bead forge-plugin-g8kf).

## End checklist

From the plan: finalize (glob replaced by measured per-module ruff entries, measured baseline,
lint-imports contract with exclude_type_checking_imports, spec line 117 wording if the layout
sentence changes, re-mint, gate-1 cell twice consecutively), Codex review detached then Fable
adjudication with a consensus round on disagreement, debt report, handover bead in the style
of forge-plugin-r80b (branch, tip, path map, every non-move edit including both prep commits,
expected gates), branch pushed, "forge@forge" restored to true, worktrees and run branches
removed, beads pushed, a row in the plan's progress log, and a beads memory with this
session's lessons.

## Stop and ask the operator when

A refusal you cannot plan around; any gate failing twice on the same cluster; any NEW or LOST
mypy key; any test that is not a layout pin failing; or anything that would require editing a
body or a file outside the app package, its import sites, pyproject's ruff entries and the
FR-230 evidence.
