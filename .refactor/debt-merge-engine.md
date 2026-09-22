# Debt report: MergeEngine decompose (bead forge-plugin-37fr, branch refactor/split-merge-engine)

Measured at finalize with `python3 $D/quality.py scripts/forge/forge_cli/app/_merge_engine.py
scripts/forge/forge_cli/app/_engine_*.py --debt .refactor/merge-engine-debt.json`
(limits from `.refactor-quality.json`: module target 500, ceiling 1,000, function target 150, class target
30, max parameters 6). Code lines as `scripts/check_file_length.py` counts them.

## Result

- `app/_merge_engine.py`: 10,302 -> **224** code lines (7 defs: `__init__`, `store` property, `_load`, `_halt`,
  `_wrong_state`, `_epoch_transition`, `_tail_event_digest`; 86 class-body bindings). Its `.refactor-baseline.json`
  entry (10302) is deleted at finalize.
- Tier 1: 29 clusters -> 27 `app/_engine_*.py` seam modules, 86 methods moved verbatim (function shape,
  `--annotate-self`).
- Tier 2 (second wave, operator rule 2026-09-22): 9 declared range extractions (e01-e05, e07-e10) into three
  `app/_engine_*_steps.py` sibling modules (e01, e02, e05) or in-module helpers; e06 not applied (rope drops the
  live-out `next_state`).
- 31 modules in `app/` after the wave; 28 under target, **3 between target and ceiling**, 0 over ceiling.

## Modules between 500 and 1,000 (provisional `.refactor-baseline.json` entries, pinned at finalize)

| module | code lines | entry (P2 -> finalize) | reason | follow-up |
|---|---|---|---|---|
| `_engine_recover_conflict.py` | 830 | 830 -> 830 | one method, `_recover_conflict_locked` (843 source lines, 11 nested defs, 5 of them `nonlocal state`); every remaining range has two outputs or calls `mark_foreign` | forge-plugin-c4l4 (two-output ranges), forge-plugin-g8kf (closure state object) |
| `_engine_recover.py` | 584 | 621 -> 584 | one method, `recover` (578 lines after e01); the five remaining ranges each have two outputs (A+B alone would bring the module under 500 with `--dest`) | forge-plugin-c4l4 |
| `_engine_lock.py` | 578 | 591 -> 578 | one contextmanager, `_recording_common_lock` (545 lines after e02): five annotated closures (`lifecycle_classification` 349, `classify_reserved_fence` 148) plus a `yield`; hoisting refused for every annotated closure | forge-plugin-g8kf |

## Functions over 150 lines (24; relocation does not change function length, extraction shortened five)

| function | module | lines | tier-2 status | follow-up |
|---|---|---|---|---|
| `_recover_conflict_locked` | `_engine_recover_conflict.py` | 843 | no eligible range | c4l4 / g8kf |
| `recover` | `_engine_recover.py` | 578 (was 616) | e01 applied; A/B/D/E/F two-output | c4l4 |
| `_recording_common_lock` | `_engine_lock.py` | 545 (was 559) | e02 applied; rest is closures + yield | g8kf |
| `_run_remote_observation` | `_engine_observe_remote.py` | 458 (was 495) | e05 applied; e06 rope live-out drop; A two-output | c4l4 |
| `cleanup_chain` | `_engine_cleanup.py` | 436 (was 453) | e10 applied; A/C two-output | c4l4 |
| `_run_bootstrap_generation_composite` | `_engine_bootstrap.py` | 374 (was 412) | e07, e08 applied; B raise-terminated | c4l4 |
| `_run_epoch_suite` | `_engine_epoch_suite.py` | 358 (was 382) | e09 applied; B/C two-output | c4l4 |
| `lifecycle_classification` (closure) | `_engine_lock.py` | 349 | annotated closure, 7 params | g8kf |
| `abort` | `_engine_abort.py` | 257 | A/B/C two-output | c4l4 |
| `_run_integrated_rebase_observation_locked` | `_engine_epoch_rebase.py` | 236 | not inventoried this session | c4l4 |
| `_run_conflict_observation_locked` | `_engine_conflict_observation.py` | 235 | not inventoried | c4l4 |
| `_recover_classifying_bootstrap_v12_locked` | `_engine_recover_bootstrap.py` | 216 | not inventoried | c4l4 |
| `_run_epoch_push` | `_engine_epoch_push.py` | 213 | not inventoried | c4l4 |
| `_complete_epoch_fetch_locked` | `_engine_epoch_fetch.py` | 213 | not inventoried | c4l4 |
| `_recover_rebase_observation_locked` | `_engine_rebase_recovery.py` | 207 | not inventoried | c4l4 |
| `_run_carried_successor_ancestry` | `_engine_epoch_ancestry.py` | 205 (was 264) | e03, e04 applied; B two-output | c4l4 |
| `_run_candidate_observation_locked` | `_engine_observation.py` | 199 | not inventoried | c4l4 |
| `classify_continue_result` (closure) | `_engine_recover_conflict.py` | 169 | annotated closure, `nonlocal state`, 8 params | g8kf |
| `_run_cleanup_child` | `_engine_cleanup_child.py` | 167 | not inventoried | c4l4 |
| `start_chain` | `_engine_start_chain.py` | 160 | not inventoried | c4l4 |
| `_attempted_release_preconditions_locked` | `_engine_abort.py` | 157 | not inventoried | c4l4 |
| `review_attach` | `_engine_review_verdict.py` | 155 | not inventoried | c4l4 |
| `review_disposition` | `_engine_review_verdict.py` | 154 | not inventoried | c4l4 |
| `_run_epoch_rebase` | `_engine_epoch_rebase.py` | 154 | not inventoried | c4l4 |

## Class

`MergeEngine` had 93 `def`s (over `class_target` 30); after the wave the class body holds 7 `def`s and 86
bindings, so `quality.py` reports no class candidate. `__all__` of `app/__init__.py` is byte-identical.

## Tool artefacts accepted as debt (mechanical, not relocated defects)

- **UP037 quoted receiver annotations.** refactor-python 0.1.2 `--annotate-self` writes `self: "MergeEngine"` /
  `cls: "type[MergeEngine]"` as string constants although every seam module inherits
  `from __future__ import annotations`. Forgiven during the waves by the temporary glob (P0b `e814491`); at
  finalize removed by one mechanical non-move commit, `ruff check --select UP037 --fix` over `app/_engine_*.py`
  (75 annotations across 27 modules; the `TYPE_CHECKING` import of `MergeEngine` makes the bare name safe), so no
  measured per-module entry carries UP037.
- **Unannotated tier-2 helpers and long call lines.** rope emits the helper signature and the replacement call
  without annotations and on one line: the three `_engine_*_steps.py` modules and several in-module helpers trip
  `E501` (and `PLR0913` where a helper has six parameters). Carried in the measured per-module entries; the
  annotations are the same `self`-typing debt as forge-plugin-psvo.
- **Reflection changes** (operations.md; Codex review B1/A2, nothing in `scripts/` or `tests/` reads any of them —
  `.refactor/probe-merge-engine-get-type-hints.txt`): moved functions report `__module__ = forge_cli.app._engine_<x>`
  and lose the `MergeEngine.` `__qualname__` prefix; plain moved functions still pickle by their new qualified
  name, and the one new pickling failure is the `contextlib.contextmanager(...)` wrapper bound as
  `_recording_common_lock` (pickle fails for 2 of 93 attributes at the tip vs 1, the `store` property, at baseline);
  `typing.get_type_hints()` raises `NameError` for the 75 moved instance/class methods (baseline: 0 of 93) because
  the receiver annotation names `MergeEngine`, imported only under `TYPE_CHECKING` (never evaluated at runtime, by
  the `--annotate-self` contract); the UP037 commit only removed the quotes, it did not change resolvability.
  `from forge_cli.app._merge_engine import <pruned name>` no longer works for the 19 imports the mover pruned from
  the shell (private path; readers checked at every cluster).
- **Dead-code candidates, not deleted** (plan §1): `_record_bootstrap_failure`, `_resolved_fetch_tip`,
  `_restore_bootstrap_fetch_observation_locked`, `_parse_remote_observation` have no caller; `_head_contained` is a
  census tripwire and stays. Deletion is not a tier-1/2 move; listed for forge-plugin-c4l4's triage.

## Type baseline

`.refactor/type-baseline.json`: 241 -> 234 by the type-only prep commit (`d3946d7`, seven real fixes); every
cluster and every extraction measured NEW 0 / GONE 0 (`.refactor/types-delta-merge-engine-*.txt`), so the
finalize ratchet is a no-op at 234. The `store` property stays on the class shell so its readers keep their
types; unlike session 1 no `self`-typed checks were lost (`--annotate-self`).

## Test-set observation for later sessions

The parallel full set (`.refactor/merge-engine-full-set.sh`, seven modules in four processes) is 175-200 s wall
and passed at every checkpoint except once at e05, where two `prepare_older_only_attempts` integration tests
(real-time observation budgets) failed while the host load average was 16 on 12 cores; the same tree passed
both tests in isolation at every tier-2 commit and 7/7 on rerun. Treat a checkpoint failure under load as
"bisect, then rerun", as the operator's rule says, before suspecting a move.
