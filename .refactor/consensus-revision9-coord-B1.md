Evidence:

- `docs/analysis/refactor-overnight-brief-2026-09-23.md:200-210` explicitly requires copying the source `sys.path.insert` into the constants module while retaining the source line.
- The two prescribed inserts are at [constants.py:27](/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s4/tests/_revision9_coord_constants.py:27) and [test_revision9_coordination.py:24](/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s4/tests/test_revision9_coordination.py:24).
- `git grep -n -E 'sys\.path\.(remove|pop|clear)|sys\.path *=|del +sys\.path' f20b8e8 -- tests scripts system` returned no matches.
- Baseline and tip probes resolved `codex_orchestrator` to the same `scripts/codex_orchestrator/__init__.py`.
- Importable top-level names under `scripts/` and `scripts/forge/` had no intersection.
- `env -u PYTHONPATH python3 -m unittest tests.test_revision9_coordination` passed: 36 tests.
- All 13 source/family modules imported successfully in separate processes without `PYTHONPATH`.

The duplicate remains observable in `sys.path`, but my failure required externally deleting an entry—no repository path does that. The changed precedence has no tracked module-name collision.

AGREE — downgrade BLOCKING 1 to ADVISORY because it is an explicitly authorized, disclosed state difference with no demonstrated repository behavior break.