# c01 tombstone — manifest evidence notes

- Base: P0 78d9610 (config-only ruff glob) on refactor/split-engine-class; Python tree identical to 5480091 / main 7e40590.
- Operator check before apply (2026-09-19): `abort_disposition_refusal` is the one import the move removes from
  `_engine.py`. Repo grep (scripts, tests, system, skills, hooks, docs): its only readers are three assertions in
  `tests/test_revision9_cli_surfaces.py` (4761, 4778, 4782) through `CLI.abort_disposition_refusal`, where `CLI` is
  the `scripts/forge/cli.py` shim; the engine package root re-exports the name directly from `._command_lock`
  (`engine/__init__.py:43`, `__all__` line 262). Nothing reads or patches it through `engine._engine` or any
  re-export of `_engine`, so the dry run is applied as shown, without `--retain-module-api`.
- Nested closure `refuse` inside `_tombstone_abort_disposition` travels verbatim (inventory nested_defs, no nonlocal).
- Gate env: PYTHONPATH=scripts:scripts/forge MYPYPATH=scripts:scripts/forge TMPDIR=/dev/shm/forge-gate,
  FORGE_SESSION_PID and REFACTOR_TYPE_CMD unset (critic blocking finding 2).
