# MergeEngine tier 2 (declared extraction) proposal

Date: 2026-09-22 · branch `refactor/split-merge-engine` (tier 1 complete, 86 methods moved) ·
tooling: refactor-python 0.1.2 `skills/decompose/scripts` (`D=/home/agents/foundry-of-zero/refactor-python/skills/decompose/scripts`) ·
rope 1.14.0 · `max_parameters` 6 (`.refactor/merge-engine-sim-quality.json`).

Nothing below has been run against the tree: no `extract_ranges.py` invocation (not even dry-run),
no `.py` edited. Inputs are the nine inventories `.refactor/merge-engine-fninv-<name>.json`.

## Method and tool findings

- `function_inventory.py <module> --function <bare name>` worked for all nine (exit 0); the
  qualified `MergeEngine.<name>` form was not needed (the functions are module-level now).
- The inventory's `blocks` are blank-line/comment-separated runs of *top-level* statements, so
  for these bodies it yields one or two giant blocks (e.g. `recover` 24–630 with three returns).
  Statement-level windows below were computed by a scratchpad scanner (`scan.py`, not in the
  tree) that enumerates every consecutive-statement window of every block (top-level body and
  nested `if`/`for`/`with`/`try` bodies, recursively; closure bodies excluded), applies the
  `extract_ranges.py` refusal set verbatim (lines 106–108: Return/Yield/YieldFrom/Await/
  Nonlocal/Global/FunctionDef/AsyncFunctionDef/ClassDef anywhere in the range; break/continue
  whose loop is outside), and infers inputs (names read in range that are parameters or were
  assigned earlier in the function; module globals and builtins excluded) and outputs (names
  assigned in range and read textually later, inside a closure, or elsewhere in an enclosing
  loop). Rope's inference is authoritative; these are conservative estimates. Windows under 8
  source lines were ignored.
- **Closure-state hazard (scanner-added rule, not in the tool):** a range that calls a closure
  which either writes `nonlocal X` while the range reads/writes `X`, or reads free `X` while the
  range rebinds `X`, would silently change semantics after extraction (the closure keeps
  operating on the outer function's cell; the helper's local copy diverges). Such windows are
  listed as HAZARD, never FEASIBLE. Affects `_recover_conflict_locked` (`mark_foreign`),
  `cleanup_chain` (`fail_step`), `_run_bootstrap_generation_composite` (`failed_result`).
- **Hoisting is unavailable for every closure in these nine functions.** All 44 nested defs
  carry parameter or return annotations, and `manifest_oracle.py` line 227 refuses a hoist when
  `nested.returns or any(a.annotation …)`. Most are also passed as callbacks (escape) or write
  `nonlocal state`. They are tier 3 material (bead forge-plugin-g8kf), listed per function.
- **An in-module extract never shrinks the module.** `extract_ranges.py` appends the helper to
  the same file when `--dest` is omitted (net ≈ +4 lines: def, signature, return, blank). The
  three over-500 modules only drop if the helper lands in a separate destination:
  `--dest scripts/forge/forge_cli/app/_engine_<x>_steps.py --import-root scripts/forge`
  (the tier 1 driver used `--import-root scripts/forge`; `read_sources` accepts a missing
  destination as empty text). `_engine_observe_remote` is at 495 code lines: three in-module
  extracts would push it over 500, so it needs `--dest` too if more than one is taken.
- **rope refuses an `elif` clause as a region** (scratchpad check on rope 1.14.0:
  "Extracted piece should contain complete statements"); the clause *body* extracts fine. The
  `recover` 440–570 window is therefore not usable as-is (see §2).
- **rope output caveat:** in one synthetic scratchpad case (a parameter rebound inside an
  `elif` body whose sibling `else` also rebinds it) rope 1.14.0 emitted a bare call and dropped
  the live-out. Standard shapes returned the expected assignment. Every dry-run diff must be
  checked against the outputs column below before `--apply`.
- Ranges use the baseline's inclusive line numbers (`selection()` requires the range to start
  and end exactly on whole statements). After each `--apply` the function shifts, so a second
  extract in the same function must be re-inventoried first; the argv below is valid only
  against the current tree (`f5ac5b3` + working tree).
- Docstring lines are excluded from first-statement windows (`recover` L22, `cleanup_chain`
  L14, `_run_carried_successor_ancestry` L42, `_run_bootstrap_generation_composite` L80).
- Line figures: "code" = non-blank, non-comment lines, the `check_file_length.py` metric.
  Module counts were re-measured on the current tree (recover_conflict 830, recover 621,
  lock 591, observe_remote 495, bootstrap 479, cleanup 438, abort 419, epoch_suite 392,
  epoch_ancestry 286). "Removed from function" = range code lines minus one call line
  (a tuple-returning call may wrap to 2–4 lines after formatting).

## Summary

| function | module (code) | fn src/code | clean feasible windows | best candidate (code removed) | proposed set (code removed) | module after, with `--dest` | <500? |
|---|---|---|---|---|---|---|---|
| `_recover_conflict_locked` | `_engine_recover_conflict` (830) | 843/820 | 57 (max 30) | 60–89 (29) | 3 ranges, 71 | ≈759 | **no** — tier 3 (g8kf) |
| `recover` | `_engine_recover` (621) | 616/612 | 153 | 307–378 (71) | 3 ranges, 161 (6 ranges, 261) | ≈460 (≈360) | **yes** |
| `_recording_common_lock` | `_engine_lock` (591) | 559/546 | 1 (15 lines) | 590–604 (14) | 1 range, 14 | ≈577 | **no** — tier 3 (g8kf) |
| `_run_remote_observation` | `_engine_observe_remote` (495) | 495/485 | 82 | 324–367 (43) | 3 ranges, 99 | ≈396 (in-module: >500 after 2nd) | already <500 |
| `cleanup_chain` | `_engine_cleanup` (438) | 453/430 | 42 | 72–90 (18) | 3 ranges, 47 | n/a (in-module +12) | already <500 |
| `_run_bootstrap_generation_composite` | `_engine_bootstrap` (479) | 412/395 | 29 | 450–473 (23) | 3 ranges, 54 | n/a (in-module 491) | already <500 |
| `_run_epoch_suite` | `_engine_epoch_suite` (392) | 382/379 | 43 | 144–168 (24) | 3 ranges, 63 | n/a | already <500 |
| `_run_carried_successor_ancestry` | `_engine_epoch_ancestry` (286) | 264/260 | 29 | 119–163 (44) | 3 ranges, 74 | n/a | already <500 |
| `abort` | `_engine_abort` (419) | 257/257 | 236 | 110–260 (150) | 1 range, 150 (alt. 161–242, 81) | n/a | already <500 |

Only `_engine_recover` reaches the 500 budget through tier 2. `_engine_recover_conflict` and
`_engine_lock` cannot: their bodies flow through `nonlocal state` closures (`mark_foreign`,
`classify_continue_result`, `persist_*`) or are one `@contextmanager` whose top level is five
annotated closures plus a `yield`-bearing `try`. Both stay debt rows for forge-plugin-g8kf.

Argv convention used below (`$D` as above; run from the repo root; add `--apply` only after
the dry-run diff and manifest are reviewed):

```
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/<module>.py --function <name> \
  --start N --end M --name <helper> --format-imports \
  --manifest .refactor/merge-engine-t2-<name>-<helper>.json [--dest <module>_steps.py --import-root scripts/forge]
```

---

## 1. `_recover_conflict_locked` — `app/_engine_recover_conflict.py` L15–857 (843 src / 820 code)

Params: `self, state, lease, lock, paths, continue_rebase, abort_rebase`. Whole body refused
(FunctionDef + Nonlocal + Return). 11 nested defs, 5 of them `nonlocal state`. 57 hazard-free
feasible windows, none over 30 code lines.

| # | block | lines | code | removed | inputs | outputs | helper | verdict |
|---|---|---|---|---|---|---|---|---|
| A | top-level | 60–89 | 30 | 29 | `abort_rebase, continuation_marker, prior_conflict, prior_intent` (4) | `abort_result_pending, continuation_phase` (2) | `_conflict_continuation_phase` | FEASIBLE |
| B | `if continuation_phase is None:` body (L414) | 415–437 | 23 | 22 | `conflict, lease, lock, selected_paths, self, state` (6) | `observation, state` (2) | `_observe_authorized_conflict_paths` | FEASIBLE (exactly 6) |
| C | top-level | 836–856 | 21 | 20 | `lease, self, state, updated` (4; `updated` is a textual carry-over from L554–577 — rope may drop it) | `state, updated` (2) | `_persist_reverifying_integration` | FEASIBLE |
| — | `if continuation_phase is None:` body | 415–470 | 56 | — | 10 (`conflict, conflict_digest, identity, lease, lock, mark_foreign, refuse_changed_conflict, selected_paths, self, state`) | `stage_intent, state` | — | RE-PLAN (10 params) + HAZARD (`mark_foreign`) |
| — | `if continuation_phase == "stage-result":` body (L529) | 554–577 / 530–546 | 24 / 17 | — | 6 / 5 | 2 / 1 | — | HAZARD: calls `mark_foreign` (`nonlocal state`) while reading `state` |
| — | top-level 29–45, 111–127 | 17 each | — | 1 / 4 | 2 / 2 | `_conflict_pending_flags`, `_conflict_rebase_identity` | FEASIBLE, small (optional 4th/5th) |

Set A+B+C removes 71 code lines → module ≈759 with `--dest`. Not enough; recommend deferring
this function entirely to tier 3 unless the operator wants the three small extracts as
groundwork. No feasible range exists for the 400+ lines between L129 and L835 because every
continuation branch calls `mark_foreign()`/`classify_continue_result()` (both `nonlocal state`).

```
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_recover_conflict.py --function _recover_conflict_locked --start 60 --end 89 --name _conflict_continuation_phase --format-imports --manifest .refactor/merge-engine-t2-_recover_conflict_locked-_conflict_continuation_phase.json --dest scripts/forge/forge_cli/app/_engine_recover_conflict_steps.py --import-root scripts/forge
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_recover_conflict.py --function _recover_conflict_locked --start 415 --end 437 --name _observe_authorized_conflict_paths --format-imports --manifest .refactor/merge-engine-t2-_recover_conflict_locked-_observe_authorized_conflict_paths.json --dest scripts/forge/forge_cli/app/_engine_recover_conflict_steps.py --import-root scripts/forge
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_recover_conflict.py --function _recover_conflict_locked --start 836 --end 856 --name _persist_reverifying_integration --format-imports --manifest .refactor/merge-engine-t2-_recover_conflict_locked-_persist_reverifying_integration.json --dest scripts/forge/forge_cli/app/_engine_recover_conflict_steps.py --import-root scripts/forge
```
(Re-inventory after each apply; the second and third `--start/--end` shift.)

Nested defs (all refused for hoist by annotation; none qualify):

| closure | line | lines | positional | free (captured) | nonlocal writes | direct calls | other blockers |
|---|---|---|---|---|---|---|---|
| `mark_foreign` | 158 | 3 | 0 | 3 | `state` | 10 | called from another nested scope |
| `refuse_changed_conflict` | 162 | 11 | 0 | 1 (`state`) | — | 7 | — |
| `phase_intent_valid` | 174 | 16 | 1 | 4 | — | 2 | — |
| `exact_stage_success` | 191 | 16 | 1 | 0 | — | 2 | — (would qualify if un-annotated) |
| `classify_continue_result` | 208 | 169 | 0 | 8 | `state` | 2 | 8 params > 6 |
| `stage_intent_current` | 473 | 14 | 0 | 5 | — | 0 | passed as callback (escapes) |
| `persist_stage` | 488 | 25 | 1 | 4 | `state` | 0 | escapes |
| `rebase_intent_current` | 619 | 15 | 0 | 5 | — | 0 | escapes |
| `persist_continue` | 635 | 43 | 1 | 4 | `state` | 0 | escapes |
| `abort_intent_current` | 721 | 15 | 0 | 5 | — | 0 | escapes |
| `persist_abort` | 737 | 43 | 1 | 4 | `state` | 0 | escapes |

## 2. `recover` — `app/_engine_recover.py` L15–630 (616 src / 612 code)

Params: `self, paths, continue_rebase, abort_rebase`. No nested defs. Whole body refused only
by its three returns (L68, L154, L623). 153 clean windows. This is the one function where
tier 2 pays: the state-dispatch `elif` chain (L291–570) decomposes branch by branch.

| # | block | lines | code | removed | inputs | outputs | helper | verdict |
|---|---|---|---|---|---|---|---|---|
| A | `elif current["state"] == "pushing":` body (L306) | 307–378 | 72 | 71 | `budget, containment, current, fresh_observation_digest, prior_observation_digest, self` (6) | `action, current` (2) | `_recover_pushing_locked` | FEASIBLE (exactly 6) |
| B | `with acquire_chain_lease(` body (L127) | 168–220 | 53 | 52 | `current, inactive_replay, self` (3) | `current, interrupted_candidate_observation` (2) | `_recover_inactive_candidate_observation` | FEASIBLE |
| C | top-level | 584–622 | 39 | 38 | `action, current` (2) | `next_steps` (1) | `_recover_next_steps` | FEASIBLE |
| D | top-level (after docstring) | 24–64 | 38 | 37 | `abort_rebase, continue_rebase, paths, self` (4) | `resumed_release, state` (2) | `_recover_preconditions` | FEASIBLE (4th) |
| E | top-level | 82–114 | 33 | 32 | `abort_rebase, continue_rebase, self, state` (4) | `binding, inactive_replay` (2) | `_recover_pending_claim_replay` | FEASIBLE (5th) |
| F | `elif … == "reverification_failed":` body (L388) | 389–420 | 32 | 31 | `budget, current, self` (3) | `action, current` (2) | `_recover_reverification_failed_locked` | FEASIBLE (6th) |
| — | `elif … == "rebase_conflict":` orelse (L425) | 440–570 | 131 | — | 4 | 2 | — | REFUSED-BY-RULE: the range is an `elif` clause, not a statement; rope 1.14.0 refuses ("complete statements") |
| — | `elif … == "rebasing":` body (L440) | 441–535 | 95 | — | `budget, current, self` (3) | 4 (`action, current, fetched_tip, unchanged`) | `_recover_rebasing_locked` | RE-PLAN: outputs 4 > 2 by textual liveness. `fetched_tip`/`unchanged` are only read in the unreachable sibling `elif` L536–570, so the true live-outs are `action, current`; rope will still emit the 4-tuple. Operator call: accept a 4-tuple, or take the L465 branch pieces (471–481, 11 lines) instead |
| — | `elif … == "classifying":` orelse (L291) | 306–570 | 265 | — | 11 | 2 | — | RE-PLAN (11 params) and `elif` clause |

Set A+B+C removes 161 code lines → module ≈460 with `--dest`; all six remove 261 → ≈360.
A, B, C, D, E, F are pairwise non-overlapping. Apply order suggestion: C, A, F, B, E, D
(bottom-up so earlier line numbers stay valid longer; still re-inventory after each apply).

```
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_recover.py --function recover --start 584 --end 622 --name _recover_next_steps --format-imports --manifest .refactor/merge-engine-t2-recover-_recover_next_steps.json --dest scripts/forge/forge_cli/app/_engine_recover_steps.py --import-root scripts/forge
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_recover.py --function recover --start 307 --end 378 --name _recover_pushing_locked --format-imports --manifest .refactor/merge-engine-t2-recover-_recover_pushing_locked.json --dest scripts/forge/forge_cli/app/_engine_recover_steps.py --import-root scripts/forge
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_recover.py --function recover --start 389 --end 420 --name _recover_reverification_failed_locked --format-imports --manifest .refactor/merge-engine-t2-recover-_recover_reverification_failed_locked.json --dest scripts/forge/forge_cli/app/_engine_recover_steps.py --import-root scripts/forge
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_recover.py --function recover --start 168 --end 220 --name _recover_inactive_candidate_observation --format-imports --manifest .refactor/merge-engine-t2-recover-_recover_inactive_candidate_observation.json --dest scripts/forge/forge_cli/app/_engine_recover_steps.py --import-root scripts/forge
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_recover.py --function recover --start 82 --end 114 --name _recover_pending_claim_replay --format-imports --manifest .refactor/merge-engine-t2-recover-_recover_pending_claim_replay.json --dest scripts/forge/forge_cli/app/_engine_recover_steps.py --import-root scripts/forge
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_recover.py --function recover --start 24 --end 64 --name _recover_preconditions --format-imports --manifest .refactor/merge-engine-t2-recover-_recover_preconditions.json --dest scripts/forge/forge_cli/app/_engine_recover_steps.py --import-root scripts/forge
```
(Line numbers above are all baseline; each command after the first must be re-derived from a
fresh inventory. The `_engine_recover_steps.py` destination is a new module; it needs a
`.refactor-baseline.json`/pyproject glob decision like the tier 1 destinations.)

Nested defs: none.

## 3. `_recording_common_lock` — `app/_engine_lock.py` L52–610 (559 src / 546 code)

Params: `self, common_dir, chain_id, operation`. `@contextmanager`. Top level is five annotated
closures (L59–588), one `lock = acquire_common_lock(...)` assignment (L590–604) and a
`try:`/`yield`/`finally` (L605–610). The `yield` and the closures refuse everything else.

| # | block | lines | code | removed | inputs | outputs | helper | verdict |
|---|---|---|---|---|---|---|---|---|
| A | top-level | 590–604 | 15 | 14 | `chain_id, classify_reserved_fence, common_dir, operation, unexpected_split_recovery_proof` (5; two are closures passed as callbacks) | `lock` (1) | `_acquire_recording_common_lock` | FEASIBLE but cosmetic |

No other feasible range: everything else is inside the closures (FunctionDef refusal) or the
`yield`-bearing `try`. Module stays ≈577. **Tier 3 / forge-plugin-g8kf material**: the 349-line
`lifecycle_classification` and 148-line `classify_reserved_fence` need to become module-level
functions with explicit `self`/`chain_id` parameters — a signature rewrite, not a tier 2 hoist.

```
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_lock.py --function _recording_common_lock --start 590 --end 604 --name _acquire_recording_common_lock --format-imports --manifest .refactor/merge-engine-t2-_recording_common_lock-_acquire_recording_common_lock.json --dest scripts/forge/forge_cli/app/_engine_lock_steps.py --import-root scripts/forge
```

Nested defs (all annotated → hoist refused; none qualify):

| closure | line | lines | positional | free | nonlocal writes | direct calls | other blockers |
|---|---|---|---|---|---|---|---|
| `event_intent` | 59 | 12 | 1 | 0 | — | 4 | called from another nested scope (would otherwise qualify) |
| `carries_fence_digest` | 72 | 13 | 2 | 1 (itself) | — | 5 | recursive; called from another nested scope |
| `lifecycle_classification` | 86 | 349 | 3 | 4 (`carries_fence_digest, chain_id, event_intent, self`) | — | 1 | 7 params > 6 → RE-PLAN; called from `classify_reserved_fence` |
| `classify_reserved_fence` | 436 | 148 | 2 | 2 (`lifecycle_classification, self`) | — | 0 | passed as callback to `acquire_common_lock` (escapes) |
| `unexpected_split_recovery_proof` | 585 | 4 | 1 | 0 | — | 0 | passed as callback (escapes) |

## 4. `_run_remote_observation` — `app/_engine_observe_remote.py` L15–509 (495 src / 485 code)

Params: `self, state, lock, lease, phase, budget, budget_member, allow_inactive_observation`.
Four closures (`intent_current`, `persist`, `containment_current`, `persist_containment`), the
last two `nonlocal state`/`progress`; all passed as callbacks. 82 clean windows. Module is
already under 500; extraction is optional. If more than one range is taken, use `--dest`
(495 + 2×4 > 500 in-module).

| # | block | lines | code | removed | inputs | outputs | helper | verdict |
|---|---|---|---|---|---|---|---|---|
| A | `if exists is True and oid is not None:` body (L323) | 324–367 | 44 | 43 | `lease, lock, next_integration, oid, self, state` (6) | `carried_generation, state` (2) | `_observe_landed_candidate_generation` | FEASIBLE (exactly 6) |
| B | top-level | 471–508 | 38 | 37 | `carried_generation, lease, next_integration, next_state, self, state` (6) | `state` (1) | `_persist_remote_observation_delta` | FEASIBLE (exactly 6) |
| C | `elif exists is True and oid == …expected_old_tip:` body (L424) | 437–456 | 20 | 19 | `classification, count, next_integration, prior_count` (4) | `next_state` (1) | `_classify_nonmovement_observation` | FEASIBLE |
| — | top-level | 293–508 | 216 | — | 13 | 2 | — | RE-PLAN (13 params): the whole post-fetch classification pipeline |
| — | top-level 26–44, 127–143 | 19 / 17 | — | 5 / 3 | 2 / 2 | `_remote_observation_intent`, `_remote_observation_progress` | FEASIBLE, small |

```
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_observe_remote.py --function _run_remote_observation --start 324 --end 367 --name _observe_landed_candidate_generation --format-imports --manifest .refactor/merge-engine-t2-_run_remote_observation-_observe_landed_candidate_generation.json --dest scripts/forge/forge_cli/app/_engine_observe_remote_steps.py --import-root scripts/forge
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_observe_remote.py --function _run_remote_observation --start 471 --end 508 --name _persist_remote_observation_delta --format-imports --manifest .refactor/merge-engine-t2-_run_remote_observation-_persist_remote_observation_delta.json --dest scripts/forge/forge_cli/app/_engine_observe_remote_steps.py --import-root scripts/forge
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_observe_remote.py --function _run_remote_observation --start 437 --end 456 --name _classify_nonmovement_observation --format-imports --manifest .refactor/merge-engine-t2-_run_remote_observation-_classify_nonmovement_observation.json --dest scripts/forge/forge_cli/app/_engine_observe_remote_steps.py --import-root scripts/forge
```

Nested defs: `intent_current` L54 (6 lines, free 4), `persist` L64 (39, free 5, `nonlocal state`),
`containment_current` L176 (8, free 4), `persist_containment` L185 (43, free 7, `nonlocal state,
progress`, 8 params > 6). All annotated, all passed as callbacks → none qualify.

## 5. `cleanup_chain` — `app/_engine_cleanup.py` L13–465 (453 src / 430 code)

Params: `self`. Nine closures (none `nonlocal`), six of them `observe_*` callbacks passed to
`_run_fenced_child`-style calls; `fail_step` reads free `current`. 42 clean windows; the
larger observation windows (157–174, 201–221) are HAZARD because they rebind `current` and
call `fail_step` (which reads the outer `current`).

| # | block | lines | code | removed | inputs | outputs | helper | verdict |
|---|---|---|---|---|---|---|---|---|
| A | `with acquire_chain_lease(` body (L47) | 72–90 | 19 | 18 | `current, self` (2) | `destination_ref, landed_head` (2) | `_cleanup_landing_targets` | FEASIBLE |
| B | `with acquire_chain_lease(` body | 443–460 | 18 | 17 | `cleanup_replay, current, self, summary` (4) | `current` (1) | `_cleanup_release_to_closed` | FEASIBLE |
| C | `with acquire_chain_lease(` body | 385–397 | 13 | 12 | `cleanup_replay, current, self, summary` (4) | `cleanup_replay, summary` (2) | `_cleanup_replay_summary` | FEASIBLE |
| — | `with` body | 157–174 / 201–221 | 18 / 20 | — | 6 / 6 | 2 / 2 | — | HAZARD: rebinds `current` then calls `fail_step` (free `current`) |
| — | top-level (after docstring) | 16–29 | 12 | — | `self` | `resumed_release, state` | `_cleanup_preconditions` | FEASIBLE, small |

```
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_cleanup.py --function cleanup_chain --start 72 --end 90 --name _cleanup_landing_targets --format-imports --manifest .refactor/merge-engine-t2-cleanup_chain-_cleanup_landing_targets.json
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_cleanup.py --function cleanup_chain --start 443 --end 460 --name _cleanup_release_to_closed --format-imports --manifest .refactor/merge-engine-t2-cleanup_chain-_cleanup_release_to_closed.json
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_cleanup.py --function cleanup_chain --start 385 --end 397 --name _cleanup_replay_summary --format-imports --manifest .refactor/merge-engine-t2-cleanup_chain-_cleanup_replay_summary.json
```

Nested defs (all annotated → refused; `child_complete` and `path_presence` have no free
variables and would qualify if un-annotated, but are called from other closures):

| closure | line | lines | positional | free | nonlocal writes | direct calls | other blockers |
|---|---|---|---|---|---|---|---|
| `child_complete` | 92 | 13 | 1 | 0 | — | 4 | called from another nested scope |
| `path_presence` | 106 | 8 | 1 | 0 | — | 2 | called from another nested scope |
| `fail_step` | 115 | 16 | 2 | 1 (`current`) | — | 6 | — |
| `observe_remote_fetch` | 141 | 15 | 1 | 3 | — | 0 | callback (escapes) |
| `observe_containment` | 184 | 16 | 1 | 3 | — | 0 | escapes |
| `observe_branch` | 246 | 18 | 1 | 1 | — | 0 | escapes |
| `observe_worktree` | 292 | 33 | 1 | 3 | — | 0 | escapes |
| `observe_worktree_removal` | 348 | 19 | 1 | 3 | — | 0 | escapes |
| `observe_branch_deletion` | 410 | 15 | 1 | 2 | — | 0 | escapes |

## 6. `_run_bootstrap_generation_composite` — `app/_engine_bootstrap.py` L68–479 (412 src / 395 code)

Params: `self, state, lock, admission, verb, remote_tip, attempt, generation_number,
operation_nonce`. Four closures; `failed_result` and `materialize_success` write `nonlocal
state`. 29 clean windows.

| # | block | lines | code | removed | inputs | outputs | helper | verdict |
|---|---|---|---|---|---|---|---|---|
| A | top-level | 450–473 | 24 | 23 | `proof, scope, self, state, verb` (5) | `state` (1) | `_refuse_exceeded_bootstrap_scope` | FEASIBLE |
| B | `except OSError as exc:` body (L352) | 369–385 | 17 | 16 | `exc, reason, scope_failure, self, state, verb` (6) | `refusal, state` (2, textual — the range ends in `raise refusal from exc`, so rope will append an unreachable `return`) | `_raise_bootstrap_fetch_refusal` | FEASIBLE (exactly 6; review the unreachable return) |
| C | `if not holder.get("complete"):` body (L411) | 413–428 | 16 | 15 | `composite_result, holder, reason, scope_failure, state, verb` (6) | `refusal` (1) | `_incomplete_bootstrap_refusal` | FEASIBLE (exactly 6) |
| — | `except OSError` body | 353–368 | 16 | — | `admission, exc, failed_result, holder` (4) | `reason, scope_failure` (2) | `_classify_bootstrap_fetch_failure` | FEASIBLE but calls `failed_result` (`nonlocal state`); the range itself never reads `state`, so no hazard — flag for review |
| — | top-level | 345–434 | 90 | — | 14 | 2 | — | RE-PLAN (14 params) + HAZARD (`failed_result`) |

```
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_bootstrap.py --function _run_bootstrap_generation_composite --start 450 --end 473 --name _refuse_exceeded_bootstrap_scope --format-imports --manifest .refactor/merge-engine-t2-_run_bootstrap_generation_composite-_refuse_exceeded_bootstrap_scope.json
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_bootstrap.py --function _run_bootstrap_generation_composite --start 369 --end 385 --name _raise_bootstrap_fetch_refusal --format-imports --manifest .refactor/merge-engine-t2-_run_bootstrap_generation_composite-_raise_bootstrap_fetch_refusal.json
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_bootstrap.py --function _run_bootstrap_generation_composite --start 413 --end 428 --name _incomplete_bootstrap_refusal --format-imports --manifest .refactor/merge-engine-t2-_run_bootstrap_generation_composite-_incomplete_bootstrap_refusal.json
```

Nested defs: `intent_current` L97 (7 lines, free 3, callback), `failed_result` L105 (45, free 5,
`nonlocal state`), `materialize_success` L151 (115, free 6, `nonlocal state`, 9 params > 6),
`persist` L267 (77, free 9, 10 params > 6, callback). None qualify.

## 7. `_run_epoch_suite` — `app/_engine_epoch_suite.py` L18–399 (382 src / 379 code)

Params: `self, state, lock, lease, budget`. Two closures (`intent_current`, `persist` with 12
params). The gate loop is `while True:` at L60; the three candidates sit inside it (loop-carried
liveness was included; no `break`/`continue` inside the ranges).

| # | block | lines | code | removed | inputs | outputs | helper | verdict |
|---|---|---|---|---|---|---|---|---|
| A | `if gate_id.startswith("stack:"):` body (L134) | 144–168 | 25 | 24 | `cell_index, commands, details, gate_id, plan, state` (6) | `argv` (1) | `_stack_cell_argv` | FEASIBLE (exactly 6) |
| B | `if bound is not None:` body (L102) | 107–128 | 22 | 21 | `argv, bound_repository, bound_run_id, bound_task, candidate_base, state` (6) | `candidate_head, mutation_result_transform` (2) | `_bound_gate_argv` | FEASIBLE (exactly 6) |
| C | `while True:` body (L60) | 73–91 | 19 | 18 | `authorizing_digest, cursor, gate_id, member, plan, state` (6) | `intent_digest, mutation_result_transform` (2) | `_gate_intent_digest` | FEASIBLE (exactly 6) |
| — | `if` body (L300) | 353–388 | 36 | — | 7 | 2 | — | RE-PLAN (7 params) |
| — | `try:` body (L281) | 282–298 | 17 | — | 5 | 2 | `_observe_suite_candidate` | FEASIBLE, small |

```
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_epoch_suite.py --function _run_epoch_suite --start 144 --end 168 --name _stack_cell_argv --format-imports --manifest .refactor/merge-engine-t2-_run_epoch_suite-_stack_cell_argv.json
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_epoch_suite.py --function _run_epoch_suite --start 107 --end 128 --name _bound_gate_argv --format-imports --manifest .refactor/merge-engine-t2-_run_epoch_suite-_bound_gate_argv.json
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_epoch_suite.py --function _run_epoch_suite --start 73 --end 91 --name _gate_intent_digest --format-imports --manifest .refactor/merge-engine-t2-_run_epoch_suite-_gate_intent_digest.json
```

Nested defs: `intent_current` L171 (10 lines, free 4, callback), `persist` L182 (76, free 11,
`nonlocal state`, 12 params > 6, callback). Neither qualifies.

## 8. `_run_carried_successor_ancestry` — `app/_engine_epoch_ancestry.py` L33–296 (264 src / 260 code)

Params: `self, state, lock, lease, resume_intent, fetched_tip`. Two closures (`intent_current`,
`persist` with `nonlocal state`), both callbacks. 29 clean windows.

| # | block | lines | code | removed | inputs | outputs | helper | verdict |
|---|---|---|---|---|---|---|---|---|
| A | `if source_intent.get("phase") == "result":` body (L118) | 119–163 | 45 | 44 | `replay_context, source_intent, state` (3) | `contained` (1) | `_replayed_ancestry_containment` | FEASIBLE |
| B | top-level | 198–213 | 16 | 15 | `ancestry_intent, lease, resume_intent, self, state` (5) | `ancestry_intent_digest, state` (2) | `_validate_ancestry_intent` | FEASIBLE |
| C | top-level | 280–295 | 16 | 15 | `result, state` (2) | `contained` (1) | `_durable_ancestry_containment` | FEASIBLE |
| — | top-level | 55–102 | 48 | — | 9 | 2 | — | RE-PLAN (9 params) |

```
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_epoch_ancestry.py --function _run_carried_successor_ancestry --start 119 --end 163 --name _replayed_ancestry_containment --format-imports --manifest .refactor/merge-engine-t2-_run_carried_successor_ancestry-_replayed_ancestry_containment.json
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_epoch_ancestry.py --function _run_carried_successor_ancestry --start 198 --end 213 --name _validate_ancestry_intent --format-imports --manifest .refactor/merge-engine-t2-_run_carried_successor_ancestry-_validate_ancestry_intent.json
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_epoch_ancestry.py --function _run_carried_successor_ancestry --start 280 --end 295 --name _durable_ancestry_containment --format-imports --manifest .refactor/merge-engine-t2-_run_carried_successor_ancestry-_durable_ancestry_containment.json
```

Nested defs: `intent_current` L215 (11 lines, free 5, callback), `persist` L227 (37, free 5,
`nonlocal state`, callback). Neither qualifies.

## 9. `abort` — `app/_engine_abort.py` L14–270 (257 src / 257 code)

Params: `self, reason`. No nested defs; the only refusal is the final `return` (L266–270), so
236 windows are clean. Two nested alternatives dominate; they overlap, so pick one (or apply B
first, re-inventory, then A on the shrunken `with`).

| # | block | lines | code | removed | inputs | outputs | helper | verdict |
|---|---|---|---|---|---|---|---|---|
| A | `with self.store._journal_outer(` body (L103) | 110–260 | 151 | 150 | `reason, self, state` (3) | `state, terminal_disposition` (2) | `_abort_under_lease` | FEASIBLE — the whole `with acquire_chain_lease(` block |
| B | `if engine._merge_has_attempt(current):` body (L160) | 161–242 | 82 | 81 | `current, current_containment, reason, self` (4) | `current, terminal_disposition` (2) | `_abort_attempted_landing` | FEASIBLE (nested inside A) |
| C | `if current_containment == "older":` body (L195) | 196–214 | 19 | 18 | `current, fresh_observation, self` (3) | `current, terminal_disposition` (2) | `_abort_older_containment` | FEASIBLE (nested inside B) |
| — | top-level | 52–99 | ≈48 | — | 7 (`attempted, containment, inactive, reason, self, state, worktree`) | 2 | `_abort_preconditions` | RE-PLAN (7 params) |
| — | top-level | 15–265 | 251 | — | 2 | 2 | — | feasible but a whole-body wrap; not meaningful |

```
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_abort.py --function abort --start 110 --end 260 --name _abort_under_lease --format-imports --manifest .refactor/merge-engine-t2-abort-_abort_under_lease.json
python3 $D/extract_ranges.py --source scripts/forge/forge_cli/app/_engine_abort.py --function abort --start 161 --end 242 --name _abort_attempted_landing --format-imports --manifest .refactor/merge-engine-t2-abort-_abort_attempted_landing.json
```

Nested defs: none.

---

## Recommendation

1. Tier 2 wave, if the operator takes one: `recover` (six extracts to
   `_engine_recover_steps.py`, module ≈360) is the only budget win; `abort` A and
   `_run_carried_successor_ancestry` A are the cleanest single extracts (3 inputs each, large
   cohesive branch bodies) and cost little. The rest are ≤25-line helpers with six parameters —
   legible but marginal; the operator may prefer to leave them.
2. `_engine_recover_conflict` (830) and `_engine_lock` (591) cannot reach 500 through tier 2;
   keep them as debt rows for forge-plugin-g8kf (explicit-state rewrite of the `nonlocal state`
   closures and of `lifecycle_classification`/`classify_reserved_fence`).
3. Before any `--apply`: dry-run each, compare rope's parameter list and return tuple with the
   inputs/outputs columns above, and confirm the manifest declares the same; a mismatch on
   outputs is the rope caveat above and is a stop.
