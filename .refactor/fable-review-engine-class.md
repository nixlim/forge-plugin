# Fable adjudicating review: Engine decompose (refactor-reviewer, 2026-09-20)

Reviewed: main 7e40590 .. 813246a (finalized tip) on refactor/split-engine-class. Read-only. Own check
first (oracle replays in detached worktrees, header/binding inspection, census and descriptor probes),
then the Codex review `.refactor/codex-review-engine-class.md` finding by finding.

VERDICT: APPROVE
CODEX_VERDICT: REJECT (3 BLOCKING, 4 ADVISORY; gpt-5.6-sol, confidence high)

BLOCKING:
- none. No hunk changes behavior or an API that anything in the repo uses.

ADVISORY:
- engine/_engine.py:28 — the 18 class functions wrapped by `_serialize_worktree_command` no longer pickle
  (they did at 7e40590). `Engine` instances, bound methods and the class still pickle. operations.md
  discloses this kind of change for function shape. Nothing in the repo pickles them: the only
  multiprocessing users (tests/test_d13_concurrency.py, tests/test_revision9_terminal_races.py) use
  `get_context("fork")` with module-level targets. Not in the debt report or CHANGELOG: add to the handover.
- pyproject.toml:124 @5025042 — the temporary glob carried PLR0904, which plan §3 P0 and §5.1 exclude. No
  effect (class-level rule, no class in any verb module). The word "operator" appears in neither 78d9610's
  nor 5025042's commit message, so the operator direction for that deviation is not recorded there; the
  operator should confirm it at the terminal at reintegration.
- plan-engine-class.md:109,417 — the plan requires one CHANGELOG line per cluster commit; only 78d9610,
  5025042 and 813246a touch CHANGELOG. The session protocol (docs/analysis/refactor-plan-2026-09-19.md:73)
  says "CHANGELOG: one entry per branch" and forge@forge was false. The plan was never amended to match.
- debt-engine-class.md:30 — mypy 251 -> 241, 0 new; ten checks lost to untyped `self`; the critic predicted
  exactly 10; follow-up bead forge-plugin-psvo is OPEN.
- All nine _verbs_*.py files lack a terminal newline. Adding one is not an AST or body edit (oracle still
  passes) but is a byte edit to FR-230 subjects: own commit, re-mint (5 fixtures, manifest, byte pin),
  gates and both reviews rerun on the new tip. W292 is not selected, so no gate requires it.

CODEX_FINDINGS:
- B1 pickling — CONFIRMED as fact (0/18 at HEAD, 18/18 at baseline), REFUTED as blocking: no pickle,
  copyreg or spawn consumer in scripts/, hooks/ or tests/; instances, bound methods and the class still
  pickle; the operation contract names the change as expected.
- B2 PLR0904 in the glob — CONFIRMED as fact, REFUTED as blocking: class-level rule, no class in the nine
  modules; ruff with all per-file entries stripped shows no PLR0904 in any verb module; measured codes
  equal the final entries for all 10 files; each verb file has one commit and no later change. Authority
  for the plan deviation UNVERIFIABLE by the reviewer.
- B3 changelog per commit — CONFIRMED as fact, REFUTED as blocking: changes no behavior or API; the Forge
  commit chain was disabled; reintegration evaluates the branch as a whole; precedent on main: 2 of the 18
  app-split commits touch CHANGELOG and merged with gates PASS. Skip authority UNVERIFIABLE by the reviewer.
- A1 mypy 251 -> 241 — CONFIRMED (NEW 0, GONE 10).
- A2 `_engine` lost 71 imported globals (29 non-underscore) — CONFIRMED, advisory only: declared in the
  manifests' `remove_imports`; the only external readers of `_engine` are two TYPE_CHECKING imports of
  `Engine`; package root and `__all__` unchanged; patch_engine covers every submodule binding a name.
- A3 5480091 not tree-identical to 7e40590 — CONFIRMED: only .refactor-quality.json (+2 lines); sources
  identical; `_serialize_worktree_command` is a plain functools.wraps wrapper, so `plain_decorators` is
  accurate; the plan's "tree identical" wording is loose but harmless.
- A4 terminal newlines / whitespace — CONFIRMED: nine verb modules end without a newline; `git diff --check`
  hits are only in .refactor dry-run, gate1 and types-delta logs.

FINDINGS CODEX MISSED (all advisory): the pickling / `__qualname__` change is absent from the debt report
and CHANGELOG; the operator direction for the glob codes is not recorded in the commit messages; plan §3
and §5.11 were never amended to the one-entry-per-branch protocol.

DISPUTED (to the consensus round): B1, B2, B3 as blocking.

ALLOWED_CHANGED: none
