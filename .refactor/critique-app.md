# Plan critique: scripts/forge/forge_cli/app.py

Reviewer: an Opus 5 critic run by the orchestrator with the refactor-python plan-critic instructions.
Plan reviewed: `.refactor/plan-app.md` / `.refactor/plan-app.json` (5 targets + root) at tip 713a81c,
with the E0 test edits present uncommitted in the working tree. Every check below was rerun
mechanically (AST walks over `app.py` and `tests/`, `git show HEAD:` for the pre-E0 census, the
plugin's `verify.sh`/`check_file_length.py`, the engine commit history).

## Round 1 — REVISE (2026-09-18)

Blocking:

- **B1. Wave-1 extractor gate cannot pass as sequenced.** `_merge_engine.py` lands at 10,282 code
  lines (measured over lines 940-11513; +~35 header). The extractor gate is
  `verify.sh --strict-bodies`, whose `file-length` step runs `check_file_length.py` against
  `.refactor-baseline.json` (verify.sh:36), and the extractor brief forbids touching
  `.refactor-baseline.json` (workflow RULES, plan line 7). The plan puts the provisional entry
  "in this wave's re-mint commit" (plan lines 48, 102, 126) — i.e. AFTER the extractor's gate, so
  the wave-1 extraction fails deterministically (10,3xx > 500, no baseline key), and the Opus
  retry fails the same way. The engine split solved this by committing the provisional entry
  BEFORE the extraction: e8f6e30 (`provisional size-baseline entry for the planned over-budget
  engine/_engine.py`, 3700) precedes 7263e40 (`extract engine -> _engine.py`, "3588 code lines
  under the provisional 3700 entry"), then e23ac60 re-pinned the measured count. Fix (one pass):
  add an orchestrator commit at the wave-0 close (or fold it into E2) that adds
  `"scripts/forge/forge_cli/app/_merge_engine.py": <ceiling ≥ 10,320, e.g. 10400>` under the
  recorded forge-plugin-hcuo ruling; the finalize wave re-pins it to the measured count
  (plan line 109 already says so). Update plan lines 48/102/126 and `plan-app.json` wave-1 notes.

Advisory (round 1):

- A1. Wrong line cite, right claim: the local `main = chain_core.Repository(...)` in
  `_observe_current_merge_candidate` is at line 831, not 796 (796 is `V2ReasonCode.WORKTREE_INVALID,`).
  Line 596 is correct. Both inventory `-> main` edges are confirmed local-shadowed by AST
  (Store before Load inside the function); no real cross-cluster edge exists.
- A2. `nonlocal` count: 22 statements (21 `nonlocal state`, 1 `nonlocal state, progress`), not 10;
  all inside `MergeEngine` methods, no `global` anywhere — conclusion unchanged.
- A3. E0 is already applied in the working tree (uncommitted; 5 files, +120/−17): exactly the six
  sites the pre-E0 AST census finds at HEAD (adapters 997/1043, integration 7726, lifecycle
  5157/5178/5294 — all `mock.patch.object(APP, ...)`, 4 names), plus the loader helper and the sweep.
  `tests.test_cli_loader` = 14 OK; ruff clean; `test_cli_loader.py` is now 447 code lines (53 of
  headroom for the follow-up `patch_package` fold). It must be committed before E2 as the plan says.
  Five `CLI.MergeEngine` patches confirmed as class-attribute patches (`_complete_epoch_fetch_locked`
  ×3, `_run_carried_successor_ancestry`, `_head_contained`) — untouched by the move. No string-target
  `mock.patch("forge_cli.app...")`, no `APP.x = `/`setattr(APP, ...)` in `tests/`.
- A4. "Wave 0 (parallel: ...)" — every cluster rewrites `app/__init__.py` (same import block; spans
  543-740 and 743-937 are separated by two blank lines, which a 3-way merge would conflict on). The
  workflow already forces sequential for wave 0 (`sequential = ... || w === 0`); align the plan
  heading to "sequential, one worktree, one commit per cluster" so an extractor never assumes
  parallel worktrees.
- A5. Root attribute reads outside `__all__` are more than the one cited: `tests/test_cli_merge_adapters.py`
  1112/1122/1165/1211/1394 (`APP._persist_deferred_mutation_result`), 1192
  (`APP._MUTATION_JOURNAL_SIDEBAND_PREFIX`), 1220 (`APP._MUTATION_PERSISTENCE_ADVISORY`), and
  `tests/test_mutation_runner.py:1542`. All are covered by the 17-name re-export rule; list them in
  the state-ownership table so the finalize reviewer checks them. `APP.os` appears only as sample
  text inside the sweep test (test_cli_loader.py:306), not as a live read.
- A6. `.refactor/rope-ignore.txt` already names `forge_cli.app` (rewritten in the freeze commit
  713a81c); the E2 clause "update ... if its comment names the file" is a no-op.
- A7. Re-export form: the engine root uses relative `from ._engine import Engine as Engine`
  (36 such lines) and the workflow's wave-close step writes `from .<target> import A as A`, while the
  plan prescribes absolute `from forge_cli.app.<owner> import ...`. Either satisfies the layers
  contract; pick one (the workflow/engine form) so the finalize check "docstring + `__future__` +
  17 re-exports + `__all__`" is a literal match.

Verified with no finding (evidence): 18 inventory symbols assigned exactly once (17 moved + `__all__`
stays); module-level node kinds = {Docstring 1, Import 12, ImportFrom 10, Assign 6 (all `ast.Name`
targets), ClassDef 2, FunctionDef 10} — nothing rope cannot move; the only `ast.Constant` strings
naming a moved symbol are the seven `__all__` entries (11517-11523), no quoted annotation of
`MergeEngine` or any moved name; per-target external import lists reproduce my AST free-name
derivation exactly (incl. `_dispatch` needing both `engine` and `_engine_module`; `Collection`,
`MutableMapping` unused everywhere and correctly dropped); cross-cluster edges are exactly
`MergeEngine -> {_persist_deferred_mutation_result, prepare_merge_admission,
_observe_current_merge_candidate}` and `{_route_shared_chain_engine, _merge_command_engine} ->
MergeEngine`, so waves 0→1→2 are forward-only and wave-0 clusters share no edge; `MergeEngine` has
no bases, no class-body assignment, decorators = staticmethod 12 / classmethod 1 / property 1 /
contextlib.contextmanager 1; the sole non-constant default is `()`; code-line estimates match
(176/195/193/10,282/289); only `scripts/forge/cli.py:76` imports `forge_cli.app` (nothing under
engine/, chain_core/, codex_orchestrator/, system/); proposed `forge_cli.app layers` contract is
acyclic and the root `forge_cli layers` contract is unaffected; `type-baseline.json` keys are
path-free; `before-app.json` is keyed by qualname; control surfaces naming `app.py` are exactly
pyproject.toml:60, .refactor-baseline.json:9, the FR-230 manifest line 51, spec line 117, and the
loader docstrings — no trigger row in forge-project.md, system/**, policy.py, rules/, agents/,
skills/ names it, and no test pins the spec sentence; `__all__` (7 names) all resolve on the root
after the re-exports and `cli.py` needs no change. No rename, body edit, or new abstraction anywhere
in the plan; E0 is the only non-move and is test-only.

## Round 2 — APPROVE (2026-09-18)

Every round-1 item verified against the revised `plan-app.md` / `plan-app.json`:

- **B1 fixed.** New "Wave-0 close" section (plan lines 102-103): orchestrator commit
  `refactor(app): provisional size-baseline entry for the planned over-budget app/_merge_engine.py`
  adds `"scripts/forge/forge_cli/app/_merge_engine.py": 10400` after the wave-0 re-mint and
  BEFORE wave 1; the wave-1 heading (105), the cluster line (106), Risk 3 (130) and the JSON wave-1
  notes (line 48) all say the extractor's gate passes because the entry already exists; the finalize
  wave (113) re-pins to the measured count. Mechanically confirmed that `check_file_length.py`
  accepts a baseline key for a not-yet-existing file: with the 10400 key injected into a copy of the
  baseline, `git ls-files -z '*.py' | xargs -0 check_file_length.py --baseline <copy>` exits 0
  ("ok: 178 files within budget"). 10,320 < 10400 leaves headroom for the header.
- **A1 fixed.** Lines 5 and 42 and JSON line 38 cite 831 (596 unchanged).
- **A2 fixed.** Lines 51 and 77: 22 `nonlocal` statements (21 `nonlocal state`, 1 `nonlocal state,
  progress`). One stale "10 `nonlocal state` closures" remains in the Follow-up section (line 140) —
  cosmetic, outside the split's scope.
- **A3 recorded.** Line 86 states E0 is already applied in the working tree at 713a81c (uncommitted;
  14 loader tests OK, ruff clean) and stays a pre-wave commit before E2.
- **A4 fixed.** Wave 0 heading (97) is now "sequential ... one commit per cluster", matching the
  workflow's forced-sequential branch for `w === 0`.
- **A5 fixed.** State-ownership rows (70-72) and the re-export rule (124) list every root read:
  `test_mutation_runner.py:1542`, `test_cli_merge_adapters.py:1112,1122,1165,1211,1394` (+ patch site
  1043), `:1192`, `:1220`.
- **A6 fixed.** E2 (95) now says rope-ignore already names `forge_cli.app` since 713a81c; the
  "update if" clause is gone.
- **A7 fixed.** Line 7: root re-exports are RELATIVE `from .<owner> import <name> as <name>` (engine
  root / workflow form); intra-submodule imports absolute (`from forge_cli.app._merge_engine import
  MergeEngine`); the per-extractor step (81), the re-export rule (124) and the JSON wave-0 notes
  (22) use the relative form. JSON wave-1/wave-2 "Imports from package" stay absolute — consistent.

No new finding. Remaining advisories: the line-140 "10 `nonlocal state`" remnant (follow-up text
only); the final `__init__.py` code-line count (~32) and `_merge_engine.py` measured count (~10,320)
are estimates to be measured in the finalize wave, as the plan already says.
