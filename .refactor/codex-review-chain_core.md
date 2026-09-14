VERDICT: REJECT
CONFIDENCE: high
BLOCKING:
- scripts/forge/forge_cli/chain_core/__init__.py:674 — `__all__` grew from 298 to 306 names, changing star imports and the CLI shim’s forwarding API, despite the verbatim requirement. (evidence: AST comparison found the original list plus eight appended private names)
- scripts/forge/forge_cli/chain_core/__init__.py:12 — 44 previously importable attributes disappeared, including `os`, `Path`, `runtime`, `FrozenError`, and `sha256_bytes`; the test suite was edited to avoid `CORE.os`. (evidence: namespace comparison against `git show e4a6846:.../chain_core.py`; `git diff` changes `CORE.os` to bare `os` at tests/test_revision9_cli_surfaces.py:3130)
- scripts/forge/forge_cli/chain_core/_core.py:5 — package-root rebindings no longer affect moved functions’ globals. Rebinding exported `COMMON_LOCK_CONTROLS` to empty raised `FrozenError` before, but HEAD silently accepted the control. (evidence: identical baseline/HEAD runtime probe printed `baseline FrozenError` and `HEAD NO_ERROR`; tests/test_revision9_ingest_negatives.py:592 retargets `vars(CORE)` to `_commit_chain`)
- forge-project.md:86 — unrelated policy behavior was added: `*.js` now belongs to the config category and triggers the changelog gate at line 178. (evidence: `git diff e4a6846..HEAD -- forge-project.md`)
- .refactor-baseline.json:11 — `chain_core/__init__.py` is grandfathered at 19,308 code lines while currently containing 665, weakening the size guard by 18,643 lines and exceeding the plan’s seven-file baseline. (evidence: the default checker passes; without the baseline it reports `665 code lines > budget 500`)
ADVISORY:
- `_state.py` reverses the original declaration order; observable initialization changed from runtime-cap → regexes → lock to lock → regexes → runtime-cap.
- The seam-marker loop remains executable root logic at `__init__.py:367`, rather than moving to `_commit_chain.py` as planned.
- The graph is acyclic, but planned leaves have blanket imports and `_fenced_process.py:13` adds the forbidden same-wave dependency on `_common_lock`.
- All 242 moved definitions now expose submodule `__module__` identities, changing introspection and new pickle paths.
- Wave 17 is absent: the spec still names `chain_core.py`, and no intra-package import-linter contract exists.
- Commit `9dac802` was not the planned move-only package conversion; it also changed the manifest, result fixtures, and byte pin.
CHECKED:
- 1 — AST inventory found 242 functions/classes and 75 assignment targets before and after, with no dropped or duplicated declarations.
- 2 — Direct source comparison found all 242 definitions identical; the strict snapshot oracle reported `881 before, 881 after, missing=0 added=0 changed=0`.
- 3 — Mutable lock state is instantiated once, but root/global rebinding behavior and `_state.py` initialization order changed.
- 4 — Static analysis found no import SCC, no new abstraction, and exactly the four pre-existing local imports; extra and same-wave imports deviate from the plan.
- 5 — All 315 planned symbols resolve from the root, but runtime namespace comparison found 44 removed attributes and eight `__all__` additions.
- 6 — The 65-file diff includes test-body and control-policy changes beyond moves/imports/re-exports; ruff, file-length, import-linter, and 299 focused tests passed, while full discovery was unavailable because one test writes to read-only `/tmp`.
---
codex_thread: 01a0a015-b9f3-7072-9abd-4d4a29f96082
model: gpt-5.6-sol  effort: ultra
