Evidence:

- [_core.py:5](/home/agents/foundry-of-zero/forge-plugin/scripts/forge/forge_cli/chain_core/_core.py:5) imports `_REQUIRED_COMMON_LOCK_CONTROLS` by value; [_require_common_lock_control at line 141](/home/agents/foundry-of-zero/forge-plugin/scripts/forge/forge_cli/chain_core/_core.py:141) therefore reads that submodule binding.
- Runtime probe produced:

```text
baseline_root_rebind=ValueError
head_root_rebind=NO_ERROR
head_helper_patch=ValueError
helper_restored=True
```

- [tests/_cli_loader.py:101](/home/agents/foundry-of-zero/forge-plugin/tests/_cli_loader.py:101) patches the root and every binding submodule; lines 119–121 restore them in reverse order.
- [.refactor/plan-chain_core.md:568](/home/agents/foundry-of-zero/forge-plugin/.refactor/plan-chain_core.md:568) explicitly prescribes this test-layer solution.
- AST and `rg` scans found no production assignments or `setattr` operations targeting `chain_core` root attributes. The only direct root patch outside the helper is [test_cli_loader.py:221](/home/agents/foundry-of-zero/forge-plugin/tests/test_cli_loader.py:221), which tests shim forwarding rather than internal interception.
- [forge-plugin-spec.md:117](/home/agents/foundry-of-zero/forge-plugin/docs/specs/forge-plugin-spec.md:117) designates `forge_cli.runtime` as the canonical patchable-control module.
- [test_revision9_ingest_negatives.py:592](/home/agents/foundry-of-zero/forge-plugin/tests/test_revision9_ingest_negatives.py:592) correctly asserts the moved function’s actual defining globals.

AGREE — the rebinding difference is real, but blocking severity is unsupported. It was anticipated by the split plan, covered by a restoring test helper, and has no production consumer. Retain it as advisory because raw package-root monkeypatch semantics are observably different.