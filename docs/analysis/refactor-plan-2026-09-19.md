# Refactor plan — 2026-09-19

Status: **historical protocol record, not authority.** This note records the operator-directed
working protocol of the 2026-09-19..22 decomposition sessions (Engine, MergeEngine). Two of its
rules were session-scoped operator directions that deviate from the committed repository rules
and were accepted as such at reintegration (review finding OPS-03 on `657f6c1`): authoring the
refactor branch with the Forge plugin disabled, and admitting 500–1,000-line modules through
provisional `.refactor-baseline.json` entries. Neither is a standing permission. Wherever this
note conflicts with `AGENTS.md` / `CLAUDE.md` — every commit through the Forge commit chain,
no Python file over 500 code lines, baseline entries grandfathered-only — the committed rules
govern, and every branch this protocol produced was reintegrated through the Forge
worktree-merge chain with its four gates.

Point of reference for the decomposition sessions that work through
`refactoring-candidates-2026-09-19.md`. Measured on main 7e40590. One session per target,
one branch per session, one Forge reintegration per branch. Beads carry the per-target
instructions; this document carries the shared protocol and the order. The beads are
chained as dependencies in plan order, so `bd ready` surfaces the next session; sweep-1
(forge-plugin-i5od) is deliberately unchained because it may run in parallel with session 2.

Plugin: `~/foundry-of-zero/refactor-python`, tag 0.1.2.
Loaded with `claude --plugin-dir ~/foundry-of-zero/refactor-python`
on this machine. Its hooks (a SessionStart notice and a PostToolUse file-length check) are
session-scoped by `--plugin-dir`; nothing is installed into this repository and nothing needs
removing afterwards.

## 1. Targets and sizes

Two numbers, both in code lines as `scripts/check_file_length.py` counts them:

- **Target 500** per module. The planner plans to it. This is the repository budget.
- **Ceiling 1,000** for any module a session creates. A module between 500 and 1,000 needs
  a provisional entry in `.refactor-baseline.json` (the repository guard still enforces 500)
  and a row in the session's debt report with a reason and a follow-up bead. A plan that
  creates a module over 1,000 is rejected at critique.
- Functions over 150 lines and classes over 30 methods stay listed as candidates in the
  debt report even when their module fits.

Configured in `.refactor-quality.json` (tracked; commit it with session 1):

```json
{"module_target": 500, "module_ceiling": 1000, "function_target": 150, "class_target": 30,
 "max_parameters": 6, "plain_decorators": ["_serialize_worktree_command"]}
```

`plain_decorators` declares the project's own function-wrapper decorator so that Engine's
18 verb methods are movable; a function-shape move re-applies it in the class binding.

## 2. Session protocol

### Start checklist (the session runs these, the bead tells it to)

`$S` below is the `scripts/` directory of the refactor-python plugin's `split-module` skill
(locally `~/foundry-of-zero/refactor-python/skills/split-module/scripts`). The mint script named
in step 5 lives under `.codex-orchestrator/runs/`, which is per-clone (`info/exclude`) — the
checklist is reproducible only on a machine that holds that run directory.

1. `cat .claude/settings.local.json` shows `"forge@forge": false`. If not, set it and note it
   for the end checklist. No `/forge:*` skills, chains, markers or approvals during the session.
2. `git status` clean on `main` at the tip named in the bead; `git switch -c refactor/<name>`.
3. `bash $S/preflight.sh --decompose` reports no missing REQUIRED tool (LibCST, rope, ruff, mypy, pytest).
4. `.refactor-quality.json` present with the values above.
5. Environment exported in the launching shell (they die with the shell, nothing to remove):
   `REFACTOR_TEST_CMD="python3 -m unittest <focused modules from the bead>"`,
   `REFACTOR_MINT_CMD="python3 .codex-orchestrator/runs/run-20260906-95e4-phase3/evidence/mint.py"`,
   `PYTHONPATH=scripts:scripts/forge`, `MYPYPATH=scripts:scripts/forge`,
   `TMPDIR=/dev/shm/forge-gate`, `FORGE_SESSION_PID` unset.
6. Baseline green: the focused set passes on the untouched branch; the gate-1 cell (4 shards)
   was green on the named main tip.
7. Read: beads memory `refactor-session-operating-notes-2026-09-13`, `app-split-handoff-2026-09-18`;
   the plugin's `skills/decompose/SKILL.md` and `references/operations.md` (or `split-module`
   for pure-move targets); the target bead.

### During

- Freeze (bodies, test ids where tests are touched, type baseline), inventory, plan, critique,
  then one cluster at a time, sequential per source file. Dry run, then `--apply`, always with
  `--format-imports` (this repository enforces isort); function-shape method moves also pass
  `--annotate-self` and stop on NEW or LOST mypy keys.
- Per-cluster snapshot scope must equal the gate's `--pkg` path. Keep all evidence under
  tracked `.refactor/` with unique names.
- Never include Ruff `I001` in destination per-file ignores or globs; temporary globs for
  relocated complexity codes are replaced by measured per-module entries at finalize.
- Never hand-edit a body. A refusal is a planning result: re-plan or report, never bypass.
- Tier 1 (relocation) and tier 2 (declared extraction) never share a commit. Tier 3 is not
  in this plan.
- FR-230: production subjects are byte-pinned. Add every new module under a subject package
  to the manifest, run `verify.sh --mint` at wave close and finalize, commit the manifest,
  `tests/fixtures/fr230-results/*.json` and the byte pin with the wave. Keep the digest tests
  out of the focused per-cluster set.
- Layout pins (patch targets, `__globals__` identity, plain assignments in fixtures) are
  repointed in the same commit as the move under the operator's standing permission.
  Behaviour tests are never edited. Class-patch sites keep working under function-shape
  bindings and need no repoint; confirm with the census output.
- `__all__` verbatim from baseline to finalize. CHANGELOG: one entry per branch.

### End checklist

1. Finalize: measured `.refactor-baseline.json` (old entry gone or shrunk, provisional
   entries only for modules the plan marked over target), `lint-imports` contract, spec
   line 117 wording if a package layout changed, re-mint, gate-1 cell twice consecutively.
2. Codex review detached, then the Fable reviewer adjudicates; consensus round on disagreement.
3. Debt report: every module between 500 and 1,000, every function over 150 lines, every
   class over 30 methods, each with reason and follow-up bead.
4. Handover bead in the style of forge-plugin-90b0: branch, tip SHA, old-to-new path map,
   every non-move edit, expected gates, debt report. Push the branch. Reintegration is a
   separate Forge session.
5. Restore `.claude/settings.local.json` to `"forge@forge": true`. Remove the run's
   worktrees and branches. The exported environment ends with the shell.

## 3. Order

| # | Target | Bead | Tool and shape | Notes |
|---|---|---|---|---|
| 1 | `forge_cli/engine/_engine.py` (3,574; Engine, 41 methods) | forge-plugin-321p | decompose, function shape, manual phases (not the workflow) | First real decompose run; the operator watches the first cluster through gate and merge. |
| 2 | `forge_cli/app/_merge_engine.py` (10,302; MergeEngine, 93 methods) | forge-plugin-37fr | decompose workflow, function shape, seven seams, then tier 2 on the eight methods over 250 lines | Depends on 1. Largest context and parallel-editing win. Operator decision 2026-09-22: first code commit is the type-only prep fix of `_recording_common_lock` (`Iterable` to `Iterator`, mypy 241 to 234, details on the bead); the `store` property stays on the class. |
| 3 | sweep-1: `fresh_evals.py`, `archive-run.py` façade, `batch.py` if not vendored | forge-plugin-i5od | split-module (pure moves) | May run in parallel with 2 in a second worktree; reintegrations stay sequential. |
| 4 | `tests/test_revision9_coordination.py` (13,222) | forge-plugin-6g67 | decompose, class shape (ids unpinned), preamble prep first | Largest test file. |
| 5 | `tests/test_cli_merge_integration.py` (7,332) | forge-plugin-pot9 | decompose, mixin shape (shard suite, FR-230 test subject) | Ids and shard membership must be identical. |
| 6 | `tests/test_revision9_cli_surfaces.py` (5,456) | forge-plugin-kzu0 | decompose, class shape | |
| 7 | `tests/test_cli_merge_lifecycle.py` (4,946) | forge-plugin-tyud | decompose, mixin shape (FR-230 test subject) | |
| 8 | `tests/test_revision8_coordination.py` (4,905) | forge-plugin-25ms | decompose, class shape | |
| 9 | `chain_core/_merge_transition.py` (2,020; one 1,984-line function) | forge-plugin-jizz, deferred P4 | tier 3 context-record refactor, not in the queue | Measured 2026-09-19: the block is one data pipeline (a 717-line run has 13 inputs and 31 live outputs; only 1 of 15 large statements fits six parameters). Verified extraction would produce 15-to-26-parameter helpers. Stays as tracked debt; the plugin now supports ranges inside nested blocks, so small extracts remain possible when the seam is right. |
| 10 | `chain_core/_commit_chain.py`, `_merge_chain.py` | forge-plugin-4j7 | tier 2 late-binding edit per the chain_core plan, then split-module | Previously deferred; follows session 8. |
| 11 | sweep-2: the 14 production files between 576 and 1,275 lines | forge-plugin-3p4o | split-module | Routine. |
| 12 | sweep-3: the remaining 27 test files between 633 and 2,635 lines | forge-plugin-u3b2 | decompose class shape, batched by fixture family | Routine. |

Out of scope: vendored `codex_orchestrator` files per the 2026-09-19 direction (`builders.py`
and `batch.py` are forge-authored and wait on that call), shell scripts (epic 8mf covers the
guard), docs, and any tier 3 design change (MergeEngine state objects are forge-plugin-g8kf, P4).

## 4. Cost reference

Engine split (12.2k lines, 28 clusters): about 14 h wall including one restart, about 3M
subagent tokens. App split (11.2k lines, 5 clusters): 96 min of waves plus finalize and
reviews. Expect session 1 near the app figure and session 2 near the engine figure.

## 5. Progress log

| Date | Session | Branch | Tip | Outcome |
|---|---|---|---|---|
| 2026-09-20 | 1 Engine class (forge-plugin-321p) | refactor/split-engine-class | bc85f57 (reviewed tip 813246a) | Nine tier-1 function-shape clusters; `_engine.py` 3,574 -> 324; verb modules 275..458; every gate PASS, gate-1 x2 PASS; Codex REJECT downgraded to advisories in consensus, Fable APPROVE; mypy baseline 251 -> 241 (10 lost self-typed checks, forge-plugin-psvo); tier-2 candidates forge-plugin-stfj; terminal newlines forge-plugin-6rcp; handover forge-plugin-r80b; reintegrated through the Forge worktree-merge chain as `d885f97` (2026-09-21, r80b closed). Protocol corrections for later sessions: export PYTHONPATH and MYPYPATH (scripts:scripts/forge) with the gate; snapshot scope = the gate's --pkg; never put I001 in a destination ruff glob; keep evidence under `.refactor/` (the scratchpad is pruned after 3 h). |
| 2026-09-22 | 2 MergeEngine class (forge-plugin-37fr) | refactor/split-merge-engine | 657f6c1 (reviewed source tip eb1cc9e) | 29 tier-1 function-shape clusters (`--annotate-self`) + a second wave of 9 tier-2 declared extractions under the operator's one-output rule (e06 not applied: rope drops a live-out); `_merge_engine.py` 10,302 -> 224; 27 seam modules 183..830 + 3 `_steps` siblings; three modules 500-1,000 pinned (830/584/578); every gate PASS, mypy NEW 0 / GONE 0 throughout, gate-1 x2 PASS (1908); Codex REJECT downgraded to advisory in consensus (B3 after the full-set bisect), Fable APPROVE; follow-ups forge-plugin-c4l4 (tier-2 remainder), forge-plugin-g8kf (tier 3); handover forge-plugin-ah1a; reintegrated through the Forge worktree-merge chain as `657f6c1` (2026-09-22, ah1a closed). Lessons: UP037 fires on `--annotate-self` receivers under the future import (temporary glob, then one mechanical unquote commit at finalize); provisional size entries BEFORE the over-500 cluster; parallel seven-module set (~3 min) with a four-module per-cluster set; a `--dest` extract shifts later ranges by one line; compare rope's inferred outputs to the plan before apply; never run gate-1 concurrently with a mint; evidence files must match a file category (no .log/.done); host load can fail the real-time integration tests (bisect with the full set per the rule). |
| 2026-09-23 | 8 revision8 tests (forge-plugin-25ms) | refactor/split-test-revision8-coordination | 1342a8e on main (origin tip 94df0b8, reviewed source tip 97d4d60, rebased 07d919e) | Test-shape decompose: 31 helpers -> mixin `tests/_revision8_support.py` (539), 81 tests -> seven class-shape scenario modules 533..809 with id maps; source 4,905 -> 10 (empty shell kept); one hand-written constants commit; two operator rulings (isort `known-local-folder` for the `scripts/`-resident packages; `.refactor/` carved out of the legacy-runtime-name scan); every gate PASS, gate-1 x2 PASS (1908); Codex REJECT resolved to advisory in consensus (B1 in round 2), Fable APPROVE; follow-up forge-plugin-7pzp; handover forge-plugin-4p7p. Reintegration 2026-09-23 17:59Z (main-clone Forge session): rebased onto 75cf81a before the gates (CHANGELOG conflict only), plus one commit re-sorting `tests/test_vocab_readers.py` under the isort ruling (a 0.6.13 module the ruling was not measured against); merge Gate 1 PASS 1926 tests, Gate 2 PASS, review-final PASS with 4 MINORs (7pzp, xlt7), operator approval, pure fast-forward push. Lessons: the tests/ body and ID snapshots trip test_migration's carve-out scan (ruled, applies to every test-file split); the mover's isort header order needs known-local-folder for sys.path-bootstrapped packages, and the ruling must be re-measured against any module main gained since the lane froze; a docstring-only shell module exits 5 under a per-module unittest run; run $REFACTOR_TEST_CMD through bash -c under zsh. |
| 2026-09-23 | 4 test_revision9_coordination (forge-plugin-6g67) | refactor/split-test-revision9-coordination | c289699 on main (origin tip fee6e07, reviewed tip f20b8e8, rebased 372538d then c289699) | Decompose class shape: 18 shared helpers -> `tests/_revision9_coord_support.py` mixin (806) and 108 tests + 20 private helpers -> 12 scenario modules 230..896; source 13,222 -> 4,931 (Binding and MergeTransitionGrammar classes remain, forge-plugin-z50i); one hand-written constants commit; every gate PASS, gate-1 x3 PASS (1,908, no PYTHONPATH); Codex REJECT downgraded to advisory in consensus, Fable APPROVE; two operator rulings (isort known-local-folder for scripts/ packages; .refactor/ carve-out in tests/test_migration.py); handover forge-plugin-kyt1. Reintegration 2026-09-23 19:49Z (main-clone Forge session): rebased onto 1342a8e (pyproject and CHANGELOG conflicts per the reintegration brief section 2), gates PASS and review-final PASS on 372538d, then main moved to 6fa8670 (spec Revision 15) so the chain restarted: rebased without conflicts, merge Gate 1 PASS 1932 tests, Gate 2 PASS, review-final PASS iteration 2 with 2 MINORs (changelog prose fixed in the 0.6.14 release commit b533fd5; duplicate sys.path insert -> z50i), operator approval, pure fast-forward push. Lessons: a generated header must import the sys.path-bootstrapping module first (isort known-local-folder); tests-scoped ID/body snapshots quote every test name and body, so any repository test that scans shipped files for a string trips on them; run Gate 1 without PYTHONPATH; the driver's amend must not write the pre-amend SHA into the records file; rebasing onto the current main before the pre-lock gates keeps the locked rebase a pure fast-forward. |
