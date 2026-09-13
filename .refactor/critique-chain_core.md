# Plan critique: scripts/forge/forge_cli/chain_core.py (round 1)

Reviewer: refactor-python:plan-critic (Opus 5), 2026-09-13. Verdict: **REVISE**.
Plan reviewed: `.refactor/plan-chain_core.md` as written by the split-planner (36 targets, 17 waves).
Independent measurement by the orchestrator confirmed B1 (208 sites / 43 names / 11 files).

## Blocking

**B1. Patch-target analysis wrong.** The plan found one name patched on `chain_core`; the real count is
43 names across 208 `mock.patch.object(CORE|CHAIN_CORE|CLI.chain_core, "<name>")` sites in 11 test
files (multi-line calls). 42 of the 43 have at least one intra-module caller, so a patch on the package
root stops reaching them once the caller lives in a submodule (each submodule binds its own copy via
`from forge_cli.chain_core._x import name`). Only `run_fenced_command` (83 sites) is called purely from
outside the package. The loader's conformance sweep (`_moved_shim_patch_offenders`) is not tripped by
either fix shape. **Resolution taken:** commit 6502849 adds `patch_chain_core(name, ...)` to
`tests/_cli_loader.py` (patches the root and every package submodule binding the name with one object)
and rewrites all 208 sites; no per-wave retargeting.

**B2. Three function-local imports are body edits.** `snapshot_bodies.py` counts an added import inside
a function as CHANGED; `verify.sh` never forwards `--allow-changed`, and the final gate is
`--strict-bodies`. Tarjan SCC over all 813 intra-module edges: exactly three non-trivial SCCs —
SCC-1 the activation trio (already co-located in `_activation.py`); SCC-2 {ChainStore, CommandContext,
_chain_batch_lock, _fresh_reviewer_evals_required, _ingest_proof_verifier, _policy_for_state,
_required_steps, _verify_and_build_ingest_records, register_coordination_seams}; SCC-3 {ChainLease,
CommonRebaseLock, MergeChainStore, _clear_reserved_fence, _lease_exclusion_is_current,
_lease_reclaim_authority_is_current, _reconcile_merge_projection_for_lease_reclaim,
_recovery_classification_receipt_valid, acquire_chain_lease}. TYPE_CHECKING is unavailable (runtime
constructions). **Resolution directed:** co-locate each SCC in one target (no body edit); the later
body-edit split is a separate follow-up commit.

**B3. Package conversion missing.** The plan never schedules `git mv chain_core.py chain_core/__init__.py`
and wave 17 "deletes chain_core.py"; a package directory shadows the module file, so waves 0-16 as
written fail at wave 0. **Resolution directed:** explicit Phase 3 step before wave 0; drop the deletion.

**B4. Unplanned control-class changes.** (a) `docs/specs/forge-plugin-spec.md:117` enumerates the
package files and becomes false after the split; `docs/specs/**` requires operator approval. (b) Risk 4
told extractors to append new over-budget files to `.refactor-baseline.json`; that is an operator
decision, one finalize-wave edit. **Resolution directed:** both become named finalize work items.

**B5. Six over-budget targets are splittable with no body edit** (`_chain_state`, `_merge_epoch`,
`_merge_scope`, `_merge_recovery`, `_merge_cleanup`, `_activation` minus the recursive trio); the
genuinely single-symbol cases are `_merge_transition` (1984-line function), `_storage` (1090-line
class), `_merge_store` (819-line class), `_ingest_merge`, `_chain_store`, `_ingest_commit`,
`_common_lock_acquire`.

## Advisory

- Verified sound: all 316 symbols placed once; nothing invented; target graph acyclic once the three
  flagged edges are removed; all 34 mutable module-level names owned by `_state.py` (wave 0) ahead of
  users; no `global`; `__all__` is 298 committed names with zero dangling entries; the 18 top-level names
  outside `__all__` are covered by the plan's extra re-exports (9 are read externally); the
  `[tool.importlinter]` layers contract is satisfied by a package; nothing keys off `__module__`,
  `__file__` or `repr` of chain_core, so no diagnostic byte can move.
- Wave 0 has an intra-wave edge (`_core` -> `_state`): label it two sequential steps in one worktree.
- Wave ordering is genuinely forced (longest path 17 hops), but single-cluster waves (5, 6, 9, 10, 11,
  14, 16) can be chained in one worktree to cut merge rounds from ~18 to ~10.
- `_activation` lists `_chain_activation_ownership_summary` before `_resolve_chain_activation_snapshot`
  (mutual recursion; order label inaccurate).
- Fact corrections: seam-marker loop is lines 9389-9397 (not 9388-9395) and leaves a module global
  `_seam` that must live in `_seams.py`; the `chain_core/**` ruff per-file-ignores entry is already
  committed (`pyproject.toml:65`).
- Only scope creep: rewriting the module docstring for the package root; a pure move keeps it verbatim.
