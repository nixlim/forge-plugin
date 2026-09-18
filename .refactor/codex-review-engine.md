VERDICT: REJECT
CONFIDENCE: high
BLOCKING:
- scripts/forge/forge_cli/engine/__init__.py:29 — Exported controls became detached snapshot bindings: assigning `engine.REVIEW_MASTER_WINDOW_BYTES = 1` leaves `_review_master_window_count(10) == 1` because `_review_transport.py:3` still holds `65536`; the old shared module global produced `10`. `CODEX_EXECUTABLE` has the same regression, which the new package-wide test patcher masks. (evidence: direct Python probes; tests/test_cli_loader.py:95-98)
- scripts/forge/forge_cli/engine/__init__.py:35 — Exported `_ARCHIVE_MODULE` no longer reflects its own cache operation: after `loaded = engine._archive_module()`, `engine._ARCHIVE_MODULE is loaded` is false while `_archive._ARCHIVE_MODULE is loaded` is true. It remains in `__all__`. (evidence: direct Python probe; _archive.py:19-47,406-409)
- scripts/forge/forge_cli/engine/_finalize.py:23 — The `TYPE_CHECKING`-only `Engine` import breaks runtime annotation resolution: `typing.get_type_hints(FinalizeContext)` now raises `NameError`; `_peek_selected_chain` and `_command_run_lock_id` also fail, while all three resolve against the base module. (evidence: current/base isolated Python probes)
- scripts/forge/forge_cli/engine/__init__.py:12 — Twenty-one previously importable original-path bindings were dropped, including `OUTPUT_SCHEMA`, `Policy`, `REGION_ORDER`, `Revision9ReasonCode`, `threading`, `argparse`, and `dataclasses`; explicit imports now fail. (evidence: base/current `vars()` comparison; `from forge_cli.engine import OUTPUT_SCHEMA` raises `ImportError`)
- scripts/forge/forge_cli/engine/__init__.py:69 — The journal seam assignment did not move with its function into `_journal.py` as planned. It now executes after `_engine` and every other submodule initialize, instead of immediately after the builder definition, changing initialization order and contradicting Risk 3. (evidence: `rg -n '_build_chain_journal_records\\s*=' scripts/forge/forge_cli/engine` returns only this line)
- scripts/forge/forge_cli/chain_core/_commit_chain.py:1076 — An unplanned `chain_core` seam-marker move changes reload behavior: deleting the markers and reloading `forge_cli.chain_core` formerly restored them; HEAD leaves the cached submodule unexecuted and `register_coordination_seams()` raises `RuntimeError: merge transition reducer registration conflict`. (evidence: `git diff` plus direct `importlib.reload` reproduction)
ADVISORY:
- `.refactor-baseline.json:13` raises grandfathered `_commit_chain.py` from 1840 to 1847, contrary to AGENTS.md:5 and the plan; CHANGELOG.md:15 explicitly said this move was deferred because that file may not grow.
- All moved functions/classes now expose internal `__module__` paths, changing introspection and new pickle paths; root `engine.__annotations__` also changed from six entries to `{}`.
- docs/specs/forge-plugin-spec.md:117-118 incorrectly says `_journal.py` binds the seam and unused imports are not rebound, while still referring to the nonexistent `engine.py` launcher adapter.
- The E0 plan says 62 patch sites, but AST census found 64; all 64 were converted. The new fixture also creates `CODEX_EXECUTABLE` on every submodule rather than only existing binders.
CHECKED:
- 1. AST declaration census found 223/223 unique declarations, no dropped or duplicate owners, and all 222 moved declarations re-exported once.
- 2. Exact source/AST comparison found only the authorized E1 `_merge_bootstrap_child_argv` edit; the post-E1 oracle reports 881 bodies unchanged.
- 3. State initializer ASTs and identities are unique, but runtime probes exposed detached root controls, stale archive state, and the relocated journal side effect.
- 4. Runtime import graph has no SCC or function-local imports; only the two guarded `_engine` back-edges exist, and they cause the annotation failures above.
- 5. `__all__` remains identical at 191 names and all declared re-exports resolve, but explicit-import, root-rebinding, metadata, and pickle surfaces changed.
- 6. Audited all 75 changed files; ruff, file-length, import-linter, loader, byte-pin, and bootstrap checks passed. Full temporary-directory suites were unavailable in the read-only sandbox.
---
codex_thread: 01a0b29b-1a22-77e0-8602-18a75ac92c74
model: gpt-5.6-sol  effort: ultra
