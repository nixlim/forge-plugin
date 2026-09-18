VERDICT: REJECT
CONFIDENCE: high
BLOCKING:
- scripts/forge/forge_cli/app/__init__.py:37 — Re-exports are snapshot bindings: rebinding public `forge_cli.app.dispatch` no longer changes what `main()` invokes at `_dispatch.py:296`. The new `patch_app` helper compensates only tests; ordinary callers changed behavior. (evidence: base-vs-HEAD execution printed `old_main_reads_root_rebinding True` and `new_main_reads_root_rebinding False`; the diff replaces raw root patches with `patch_app`)
- scripts/forge/forge_cli/app/__init__.py:18 — The root drops 35 previously importable bindings, including `Policy`, `Outcome`, `Path`, `engine`, `runtime`, and `chain_core`. (evidence: `vars()` census found 53 non-dunder names before versus 23 after; `PYTHONPATH=scripts:scripts/forge python3 -c 'from forge_cli.app import Policy'` now raises `ImportError`)
ADVISORY:
- scripts/forge/forge_cli/app/_mutation_journal.py:4 — Import-start order changed from `chain_core → runtime` to `runtime → chain_core`; runtime initializes a cache and lock. Fresh imports pass, but initialization order is not preserved.
- scripts/forge/forge_cli/app/_dispatch.py:4 — Unused imports of `prepare_merge_admission` and `_observe_current_merge_candidate` add bindings and dependency edges omitted by the plan.
- Moved callables now expose owner-submodule `__module__` values, changing introspection and newly emitted pickle references.
- Commit `d788d70` added the provisional size baseline before wave 0, not at wave-0 close as planned; unrelated test baselines were also tightened.
- CHANGELOG.md:13 states 11,525 historical lines; the base file has 11,524.
- Tempfile-dependent suites could not run in the read-only sandbox; failures were environmental `FileNotFoundError`s.
CHECKED:
- 1. AST census found exactly the same 18 declarations, each occurring once with all 17 moved names re-exported.
- 2. Compared complete source spans for every declaration; all 18 were byte-identical, including the entire `MergeEngine` class.
- 3. Audited state ownership and import order; constants have one owner, but root snapshot rebinding and initialization-order changes were confirmed.
- 4. Found no new local/lazy imports or abstractions; `lint-imports --no-cache` kept all five contracts with zero cycles.
- 5. Verified unchanged `__all__`, callable signatures, methods, and help bytes; runtime namespace and rebinding probes exposed the two blockers above.
- 6. Reviewed all 31 changed files and history; six E0 patches match the plan, while ruff, file-length, loader, manifest, and byte-pin checks passed.
---
codex_thread: 01a0b571-c486-74a3-889a-7296be03ac6c
model: gpt-5.6-sol  effort: ultra
