Evidence:

- `env -u PYTHONPATH python3 tests/test_revision8_coordination.py` fails at `tests/test_revision8_coordination.py:5` with `ModuleNotFoundError: No module named 'tests'`.
- The same command against unchanged `tests/test_revision9_cli_surfaces.py` fails identically at line 41 despite its `unittest.main()` at line 5752.
- `git grep ... tests/test_revision8_coordination.py` found no script, hook, workflow, or document executing that file directly at either revision.
- The supported paths use module imports: `README.md:267` documents discovery; `forge-project.md:117-125` constructs `tests.<module>` and runs `python -m unittest`; `.refactor/revision8-run-cluster.py:205-216` tests module execution and package import.
- One direct-file consumer exists: `skills/workflow/SKILL.md:249` and `scripts/forge/audit-commitments.py:870-877` execute `tests/test_repo_conformance.py`. However, that file is a purpose-built CLI with `main(argv)` at `tests/test_repo_conformance.py:1096-1109`; it does not establish direct execution as a contract for ordinary unittest modules.
- At `69bc28d`, 30 test modules already combined a top-level `from tests...` import with a `__main__` guard, so that guard alone does not demonstrate supported direct execution.

AGREE — B2 should be downgraded to advisory. The execution difference is real, and the retained but unreachable `__main__` is confusing quality debt, but no repository consumer or documented contract makes direct execution of `test_revision8_coordination.py` a supported surface.