# Debt report: revision9 cli-surfaces test split (bead forge-plugin-kzu0, branch refactor/split-test-revision9-cli-surfaces)

Measured at finalize with `python3 $D/quality.py tests/test_revision9_cli_surfaces.py
tests/_revision9_cli_constants.py tests/_revision9_cli_support.py tests/test_revision9_cli_surfaces_*.py
--debt .refactor/debt-revision9-cli.json` (output `.refactor/quality-revision9-cli.json`; limits from
`.refactor-quality.json`: module target 500, ceiling 1,000, function target 150, class target 30, max
parameters 6). Code lines as `scripts/check_file_length.py` counts them. The tool exits 1 because of the
candidates it lists (four functions over 150 lines, all moved or retained verbatim); every over-target
module carries a reason and the follow-up bead forge-plugin-by61.

## Result

- `tests/test_revision9_cli_surfaces.py`: 5,456 -> **1,229** code lines. It keeps the eight classes that were
  never in this session's scope (`Revision9CLIParsingTests`, `Revision9CommitStateTests`,
  `Revision9CoordinationSeamTests`, `Revision9IngestProofControlTests`, `Revision9ArchiveRecheckTests`,
  `LegacyChainKeySetTests`, `GateEnvironmentScrubTests`, `GateEnvironmentScrubBehaviorTests`) and the
  `pass`-only shell `class Revision9BoundCLIIntegrationTests(Revision9CliSupport, CLI_FIXTURE_SUPPORT.ForgeCLIFixture)`.
  **Over the 1,000 ceiling by the session's scope**, carried by its baseline entry shrunk 5456 -> 1229
  (growth-only guard). Its measured ruff entry keeps `F401` because `load_script` and `package_module`
  are now dead names in the loader import line kept verbatim (no hand edit), `E501`/`PLR0915` from the
  retained classes, and `I001` (the two `tests.*` import lines the mover and the prep left unsorted
  relative to each other; not hand-edited). Follow-up forge-plugin-by61: a further class-shape session on
  the two largest remaining classes brings the file under 1,000; the empty shell is the operator's call.
- `tests/_revision9_cli_constants.py`: 34 code lines (hand-written prep b4d3c4f: the preamble loader block
  verbatim; measured ruff entry `E402` (the loader import after `ENVELOPE_KEYS`, verbatim order) and
  `F401` (`patch_chain_core`, `patch_engine` imported by the verbatim line, unused here)).
- 15 helpers -> `tests/_revision9_cli_support.py` (mixin shape, 674, 15 methods under class_target 30);
  62 tests -> five class-shape families.
- 8 modules after the wave: 1 under target (`_revision9_cli_constants.py`), **6 between target and
  ceiling**, **1 over ceiling** (the retained source, above).

## Modules between 500 and 1,000 (provisional entries at C2 -> measured at finalize)

| module | code lines | entry (C2 -> finalize) | reason | follow-up |
|---|---|---|---|---|
| `tests/_revision9_cli_support.py` | 674 | 674 -> 674 | the 15 helpers as one mixin; hubs (`invoke_cli`, `cli_process_context`, `open_run_and_task`, `start_bound_fast_chain`) used by every family | forge-plugin-by61 |
| `tests/test_revision9_cli_surfaces_dispositions.py` | 966 | 976 -> 966 | 20 tests, the brief's 500..1,000 band; fallback seam in the plan | forge-plugin-by61 |
| `tests/test_revision9_cli_surfaces_start_locks.py` | 803 | 812 -> 803 | 17 tests, same band | forge-plugin-by61 |
| `tests/test_revision9_cli_surfaces_replay.py` | 666 | 678 -> 666 | 10 tests, same band | forge-plugin-by61 |
| `tests/test_revision9_cli_surfaces_multicell_stack.py` | 588 | 602 -> 588 | 6 tests, same band | forge-plugin-by61 |
| `tests/test_revision9_cli_surfaces_ingest.py` | 570 | 578 -> 570 | 9 tests, same band | forge-plugin-by61 |

## Functions over 150 lines (4; relocation does not change function length)

| function | module | physical lines | status |
|---|---|---|---|
| `test_secret_scan_selection_is_exact_current_gate_two_authority` | `test_revision9_cli_surfaces.py` (retained class, out of scope) | 215 | pre-existing, untouched |
| `prepare_unbound_fast_ingest` | `_revision9_cli_support.py` | 258 | helper, moved verbatim |
| `test_bound_multicell_stack_failure_journals_failed_cell_and_stops` | `test_revision9_cli_surfaces_multicell_stack.py` | 274 | moved verbatim |
| `test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition` | `test_revision9_cli_surfaces_dispositions.py` | 165 | moved verbatim |

## Ruff per-file ignores (measured per module with the temporary globs removed)

`_revision9_cli_constants.py` E402 F401; `_revision9_cli_support.py` PLR0915; `test_revision9_cli_surfaces.py`
E501 F401 I001 PLR0915; `dispositions` E501 PLR0915 PLR1702; `ingest` B023 PLR0915; `multicell_stack` E501
PLR0915; `replay` PLR0915; `start_locks` E501 PLR0915. Every code was in the source's grandfathered list; no
`I001` in any destination entry (the retained source is not a destination).

## Gate 1 at wave close

The first wave-close cell at e03515d (load 17.6 at start) failed two timing-shaped tests in modules this
branch never touched (`tests.test_cli_common_lock.FencedProcessTests.test_timeout_and_output_cap_both_use_term_quarter_second_then_kill`:
SIGKILL escalation not observed; `tests.test_cli_merge_integration.MergeIntegrationEpochTests.test_cleanup_worktree_remove_pre_result_crash_is_observed`:
worktree still present); the one re-run allowed by brief section 6 passed 4/4 at load 2.6
(`gate1-revision9-cli-wave-close.txt`, `-wave-close-2.txt`). Disclosed to both reviewers and in the handover.
