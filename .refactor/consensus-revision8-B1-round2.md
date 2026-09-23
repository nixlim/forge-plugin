Evidence:

- Clean-process measurements reproduced the delta:

```text
                    scripts count   len(forge.__path__)   iter_importers("forge.forge_cli")
69bc28d bare              1                  1                         1
69bc28d PYTHONPATH        2                  2                         2
97d4d60 bare              2                  2                         2
97d4d60 PYTHONPATH        3                  3                         3
```

I ran the tip using `import tests.test_revision8_coordination`; for baseline I compiled the file from `git show 69bc28d:tests/test_revision8_coordination.py`. Production `scripts/` is unchanged across the range.

- The extra insertion comes from `tests/_revision8_constants.py:7` plus retained `tests/test_revision8_coordination.py:8`. Baseline had one insertion at line 21.
- `git grep` shows four baseline modules already inserted the same path:

```text
tests/test_commitment_paths.py:17
tests/test_revision8_coordination.py:21
tests/test_revision9_coordination.py:32
tests/test_run_coordination.py:19
```

Baseline Gate 1 placed `test_commitment_paths` and `test_revision9_coordination` together; importing those two produced `scripts_count=2` and `len(forge.__path__)=2`.

- This consumer search returned no `import forge`, `forge.__path__`, or `iter_importers` usage at either revision:

```sh
git grep -n -E 'import forge|from forge|forge\.__path__|iter_importers\(' \
  <rev> -- . ':(exclude).refactor/**'
```

The only `pkgutil.iter_modules` sites are `tests/_cli_loader.py:82` and embedded code at `tests/test_cli_chain.py:87`; both enumerate `forge_cli` packages.

- The top-level import-name intersection between `scripts/` and `scripts/forge/` is empty, so the changed ordering resolves no repository module differently.
- `.refactor/debt-revision8.md:13-20` records the retained shell/bootstrap and follow-up `forge-plugin-7pzp`.

One correction: `.github/workflows/guardrails.yml:24` scopes that `PYTHONPATH` to `lint-imports`; CI Gate 1 itself is bare (`.github/workflows/forge-ci.yml:27-45`). This does not change the conclusion.

**AGREE — advisory.** The multiplicity delta is observable, so I would not retract it entirely. But it is pre-existing in kind, disclosed, tracked for cleanup, and has no repository observer or resolution effect; it is not blocking.