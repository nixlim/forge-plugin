# Plan critique: Engine decompose (plan-engine-class.md) — plan-critic, 2026-09-19

Reviewed at branch refactor/split-engine-class 5480091 (tree = main 7e40590). Read-only; no code applied.
Independent evidence: re-ran the c01 dry run (byte-identical to the planner's), inspected the planner's
sequential simulation clone through a temporary worktree (removed), ran the oracle on the simulated c01
commit against the real `.refactor/engine-c01-before.json` (PASS), ruff/length/compile/lint-imports there.

VERDICT: REVISE (both blocking findings applied to the plan by the session before c01; see §3 of the plan)

BLOCKING:
- Per-cluster snapshot argv in plan §3 included `tests`; verify.sh compares over `--pkg scripts/forge/forge_cli`
  only and `manifest_oracle.verify_scope` refuses when the snapshot file set differs from the compared set
  (reproduced: `decompose oracle: FAIL: unmanifested file added or removed`, rc=1). Fix: snapshot scope exactly
  `scripts/forge/forge_cli` (what `.refactor/engine-c01-before.json` records). APPLIED (plan line 89).
- Gate environment unspecified: with only REFACTOR_TEST_CMD exported, `type_baseline.py check` reports 3 NEW
  `import-untyped codex_orchestrator` errors (rc 1) → GATE: FAIL. With `PYTHONPATH=scripts:scripts/forge
  MYPYPATH=scripts:scripts/forge` it reports `types ok: 251 error(s), all grandfathered`. Plan text calling the
  failure benign is wrong: a FAIL step is a failed gate. Fix: state the gate env verbatim as the app split's
  `.refactor/split-app.workflow.js` GATE_ENV did. APPLIED (plan §3 common text; session reproduced both results).

ADVISORY:
- Completeness/order verified: 41 methods assigned exactly once (33 moved in 9 clusters + 8 stay); source order
  within every cluster; all non-hub cross-cluster edges resolve through class bindings whatever the commit order.
  `_chains_for_worktree` / `_record_head_moved` staying is justified by edges select→_chains_for_worktree and
  _preflight→_record_head_moved.
- Sizes independently recounted from dry-run destination text: 346/275/429/458/377/327/458/398/395, `_engine.py`
  324 — all match plan §4. quality.py on the sim tree: no debt; 5 functions > 150 remain tier-2 candidates.
  Bead forge-plugin-321p is the session bead: file a dedicated tier-2 follow-up bead at finalize so `follow_up`
  is real.
- c06 `decision`: "every seed forms one connected cluster" is label propagation honouring seeds, not
  connectivity; verify/review_disposition/approve/skip share no non-hub edge. Acceptable under the skill's rule
  (shared ctx, same hubs, `_issue_authorization` in 3 of 4) and four <110-line modules would be worse; call them
  "seed-forced, hub-only singletons" honestly. Plan line "398 + 114 > 500" conflates review_disposition (66)
  with approve; review_disposition alone would fit c08 (~464). No change required.
- Imports: every body global of every cluster is in its manifest `imports[dest]`; sequential `remove_imports`
  in the sim manifests match the plan's "sequential adds" for c04–c09 exactly. Self-detection holds (missed
  removal → F401 in `_engine.py`, not ignored; over-removal → F821/mypy + tests). Never add F401/F821 to an
  ignore list.
- Ruff on every intermediate sim commit: `_engine.py` clean under its entry; `_verbs_*` clean under the P0
  union, which is exactly the measured union (per-module codes match plan §4 line for line); I001 and PLR0904
  correctly omitted.
- P0 glob vs per-module entries: the glob is the cleaner route (one config-only commit; nine pure mover
  commits; precedent of both prior splits). Conditions: (a) it is the CLAUDE.md "never add to that list"
  exception → operator must approve P0 explicitly; (b) finalize replaces the glob with nine per-module entries
  (§4 codes), deletes the glob, drops PLR0904 from the `_engine.py` entry. The glob matches only files that do
  not yet exist, so it weakens nothing.
- Type-coverage regression (not a gate failure): moved functions have unannotated `self` → mypy treats it as
  Any, so `self.ctx.*` chains stop being checked. Sim ratchet: 241 errors, 0 new, 10 "fixed" — those are lost
  checks, not fixes. Record as debt with follow-up; `self: "Engine"` under TYPE_CHECKING is a header change →
  own reviewed commit, never inside a tier-1 cluster. Never run `type_baseline.py --update` in a cluster commit.
- Census confirmed by descriptors: `_serialize_worktree_command` uses functools.wraps and keys on
  `method.__name__` (unchanged); inspect.getsource unwraps via `__wrapped__`; staticmethod on the class yields
  the plain function for the two unbound sites; patch.object replaces the class attribute either way;
  MergeEngine is not a subclass; no `__qualname__`/`__module__` assertions in the focused tests; no pickling.
- Full-suite state between c01 and wave close: FR-230 byte pins fail until the nine subjects are added and
  minted; no intermediate cluster SHA is a reintegration candidate; the wave-close mint commit touches
  `.forge/evals/tasks/**` + `tests/fixtures/**` (control class → binding review + operator approval at
  reintegration). Decide at finalize whether spec line 117 needs a `_verbs_*` clause (docs/specs is gated).
- §5.7 expected per-cluster diff also contains `.refactor/engine-<x>.json`, `.refactor/engine-cNN-before.json`
  and one CHANGELOG line (`.refactor/` is tracked; the changelog gate treats `.refactor/*.json` as in-scope).
- Focused tests never hit `journal_batch_recover` (0) and barely `journal_ingest_chain` (5): add
  `tests.test_revision9_coordination` to REFACTOR_TEST_CMD for c02.
- Apply-time refusals still possible (common.py:117-131): stale/uncommitted HEAD → commit P0 and each cluster
  before the next dry-run+apply, snapshot after that commit; a pre-existing `.refactor/engine-<x>.json` refuses.
- lint-imports does not constrain unlisted `_verbs_*`; the real proof is `grep -c _engine engine/_verbs_*.py`
  = 0; the finalize layer row cannot be added before the modules exist.

c01 specifics:
- Order correct (lines 38, 47, 65, 878, 975, 1044). Independent dry run byte-identical to the planner's; oracle
  PASS on the simulated c01 commit against the real snapshot; ruff/length/compile/lint-imports pass there.
- Bindings land at two spots: three after `self.ctx = ctx` (no blank line; harmless), three after `restage`
  before `_wrong_state`. Do not tidy.
- Nested closure `refuse` inside `_tombstone_abort_disposition` travels verbatim — check it.
- `remove_imports` = only `abort_disposition_refusal`; destination header 12 lines; `_run_halt` /
  `_transition_state` on separate lines (isort `as` behaviour).
- Post-apply checks: `Engine.abort.__wrapped__.__name__ == 'abort'`; `Engine.__dict__['_require_tombstone_control']`
  is a staticmethod; `status` still reaches it via `self.`.
- Commit = P0-based; contains `_engine.py`, `_verbs_tombstone.py`, manifest, snapshot, CHANGELOG line.
