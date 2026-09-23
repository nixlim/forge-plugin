Evidence:

- [tests/_revision8_constants.py:7](/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s8/tests/_revision8_constants.py:7) inserts `scripts`; [journal.py:26](/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s8/scripts/codex_orchestrator/journal.py:26) inserts `scripts/forge`; then [test_revision8_coordination.py:8](/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s8/tests/test_revision8_coordination.py:8) inserts `scripts` again.
- `git ls-files scripts/forge/__init__.py` returned nothing, so `forge` is an importable namespace package.
- Clean-process probes produced:

```text
BASE forge.__path__ = ['.../scripts/forge']
TIP  forge.__path__ = ['.../scripts/forge', '.../scripts/forge']
```

- `pkgutil.iter_importers("forge.forge_cli")` returned one `FileFinder` at baseline and two at the tip.
- With `PYTHONPATH=scripts:scripts/forge`, the difference remains: baseline `forge.__path__` has two entries; tip has three.
- I confirmed the ordinary top-level-name intersection is empty and found no repository consumer importing `forge` or counting/removing `sys.path` entries. Thus ordinary imports resolve to the same files, but the namespace-package attribute and importer enumeration differ.
- The CI claim is inaccurate: [forge-ci.yml:27](/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s8/.github/workflows/forge-ci.yml:27) does not set `PYTHONPATH`; line 38 changes only the parent runner’s `sys.path`. The plan states this explicitly at [.refactor/plan-revision8.md:32](/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s8/.refactor/plan-revision8.md:32).

DISAGREE. The duplication was intentional and its practical impact is narrow, but intent and green gates do not make it behaviorally identical. `forge.__path__` and standard-library importer enumeration are concrete module behaviors that changed, satisfying the requested counterexample.