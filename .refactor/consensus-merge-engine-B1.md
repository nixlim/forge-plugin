Evidence:

- `git grep -n -E '\b(get_type_hints|get_annotations|ForwardRef|eval_str|__annotations__)\b' -- scripts tests hooks skills system` returned no matches.
- `tests/test_cli_merge_integration.py:5423-5429` uses `autospec=True`; the probe script passes this case. Plain `inspect.signature()` also succeeds.
- `operations.md:58-75` requires a `TYPE_CHECKING`-only class import and states it is never evaluated at runtime to avoid a cycle.
- `scripts/forge/forge_cli/app/_merge_engine.py:8-37` imports seam modules before defining `MergeEngine`, confirming that a reverse runtime import would create the cycle the contract avoids.
- `.refactor/probe-merge-engine-get-type-hints.txt:1-3` confirms 75 failures and zero readers.
- Current handover edits disclose the limitation in `.refactor/debt-merge-engine.md:74-81` and `CHANGELOG.md:13`. These disclosures are presently uncommitted additions after `eb1cc9e`; the reviewed commit only implied the limitation generally.

AGREE — downgrade to advisory. The reflection delta is real, but I found no consumer, normal signature/autospec behavior remains intact, and the `TYPE_CHECKING` arrangement is intentional under the `--annotate-self` contract.