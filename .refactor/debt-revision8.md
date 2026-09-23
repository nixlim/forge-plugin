# Debt report: revision8 test split (bead forge-plugin-25ms, branch refactor/split-test-revision8-coordination)

Measured at finalize with `python3 $D/quality.py tests/test_revision8_coordination.py
tests/_revision8_constants.py tests/_revision8_support.py tests/test_revision8_*.py --debt
.refactor/debt-revision8.json` (output `.refactor/quality-revision8.json`; limits from
`.refactor-quality.json`: module target 500, ceiling 1,000, function target 150, class target 30,
max parameters 6). Code lines as `scripts/check_file_length.py` counts them. The tool exits 1 because
of the candidates it lists (one class over 30 methods, three functions over 150 lines); every
over-target module carries a reason and the follow-up bead forge-plugin-7pzp.

## Result

- `tests/test_revision8_coordination.py`: 4,905 -> **10** code lines (docstring-only shell of
  `Revision8CoordinationTests(Revision8Support, unittest.TestCase)`, its `sys.path` bootstrap and
  `__main__`); collects 0 tests (`python3 -m unittest tests.test_revision8_coordination` exits 5,
  "NO TESTS RAN"; the Gate 1 cell groups modules per shard and passes). Its baseline entry (4905) and
  pyproject entry are gone; the shell keeps a measured `I001` entry (the mover left no blank line
  after the future import; not hand-edited). Deletion is an operator call: forge-plugin-7pzp.
- `tests/_revision8_constants.py`: 6 code lines (hand-written prep 42980e7: `ROOT`, `TOOLS`,
  `RECORDED_AT` verbatim plus the `sys.path` bootstrap).
- 31 helpers -> `tests/_revision8_support.py` (mixin shape); 81 tests -> seven class-shape families.
- 10 modules after the wave: 2 under target, **8 between target and ceiling**, 0 over ceiling.

## Modules between 500 and 1,000 (provisional entries at C2 -> measured at finalize)

| module | code lines | entry (C2 -> finalize) | reason | follow-up |
|---|---|---|---|---|
| `tests/_revision8_support.py` | 539 | 539 -> 539 | the 31 helpers as one mixin (class over class_target 30); helper fan-in is high (each family uses 10..18), so the split is by role, not by family | forge-plugin-7pzp |
| `tests/test_revision8_orphan_identity.py` | 809 | 819 -> 809 | 17 tests, scenario family in the brief's 500..1,000 band | forge-plugin-7pzp |
| `tests/test_revision8_append_schema.py` | 712 | 724 -> 712 | 10 tests, same band | forge-plugin-7pzp |
| `tests/test_revision8_registry_races.py` | 618 | 628 -> 618 | 12 tests, same band | forge-plugin-7pzp |
| `tests/test_revision8_precedence.py` | 609 | 617 -> 609 | 16 tests, same band | forge-plugin-7pzp |
| `tests/test_revision8_rollback.py` | 583 | 593 -> 583 | 9 tests, same band | forge-plugin-7pzp |
| `tests/test_revision8_interruptions.py` | 566 | 576 -> 566 | 3 tests of 166..205 code lines each; no seam under 500 keeps two together | forge-plugin-7pzp |
| `tests/test_revision8_successors.py` | 533 | 540 -> 533 | 14 tests, same band | forge-plugin-7pzp |

## Functions over 150 lines (3; relocation does not change function length, moved verbatim)

| function | module | lines (physical / code) | follow-up |
|---|---|---|---|
| `test_postsyscall_baseexception_restores_registry_and_owner_begin_paths` | `test_revision8_interruptions.py` | 201 / 185 | forge-plugin-7pzp (noted; test bodies are not split) |
| `test_postsyscall_baseexception_during_rollback_retains_coherent_candidate` | `test_revision8_interruptions.py` | 221 / 205 | same |
| `test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent` | `test_revision8_interruptions.py` | 177 / 166 | same |

## Ruff per-file ignores (measured per module with the temporary globs removed)

`_revision8_support.py` PLR0904 PLR0915 UP012; `append_schema` PLR0915; `coordination` (shell) I001;
`interruptions` C901 PLR0915 UP012; `orphan_identity` B023 C901 PLR0912 PLR0915 PLR1702 UP012;
`precedence` B023 PLR1702 UP012; `registry_races` B023 PLR0915 UP012; `rollback` B023 UP012;
`successors` and `_revision8_constants.py` clean (no entry). Every code was in the source's
grandfathered list; no `I001` in any destination entry.
