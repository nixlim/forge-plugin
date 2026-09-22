# Decompose plan: `MergeEngine` in `scripts/forge/forge_cli/app/_merge_engine.py` (function shape, tier 1)

Mode: **decompose** (class -> `app/_engine_*.py` modules), production class, **function shape**, **tier 1 only**,
every move with `--annotate-self --format-imports`. Bead forge-plugin-37fr, branch `refactor/split-merge-engine`.
Tool roots: `$D=/home/agents/foundry-of-zero/refactor-python/skills/decompose/scripts`,
`$S=/home/agents/foundry-of-zero/refactor-python/skills/split-module/scripts` (plugin refactor-python 0.1.2).
All evidence is tracked under `.refactor/` (`merge-engine-*`, `dryrun-merge-engine-*`); nothing lives in scratch.

## 0. STOP / operator decisions (read first)

**No refusal and no nonzero type delta.** All 29 dry runs verify, all 29 sim gates pass, and every cluster measures
mypy **NEW 0 / GONE 0**. Nothing below is a mover refusal. There is, however, one finding that blocks the c01 gate as
the prep commits currently stand:

1. **BLOCKING for c01 — the P0 glob is missing `UP037`.** `--annotate-self` writes the receiver as a *string*
   annotation (`self: "MergeEngine"`, by contract: operations.md "New annotations are string constants with or without
   `from __future__ import annotations`"). Every destination inherits `from __future__ import annotations` from the
   source, so ruff `UP037` (quoted-annotation; `UP` is selected project-wide, `pyproject.toml:28`) fires once per
   annotated function. `UP037` is **not** in the `_merge_engine.py` list, so "that list minus `I001`" does not cover it.
   - Reproduced: with P0 exactly as specified the c01 gate is `FAIL ruff-lint` (4x `UP037`) while compile, file-length,
     types, import-contracts and bodies-unchanged all PASS -> `.refactor/merge-engine-sim-finding-up037-c01-gate.txt`.
   - It cannot be fixed inside a tier-1 commit: `ruff --fix` rewrites the signature and the manifest oracle then reports
     `decompose oracle: FAIL: undeclared structural change` (control on the unfixed tree: PASS) ->
     `.refactor/merge-engine-sim-up037-probe.txt`. (A first attempt at that probe without `--isolated` was invalid —
     the glob suppressed the fix — and is noted as such in the file.)
   - **The project branch already carries P0 as `6ee38b6` without `UP037`.** Options, operator's call:
     **(A, recommended)** one more config-only commit **P0b** adding `"UP037"` to the `_engine_*.py` glob before c01.
     It is mover-generated, not a relocated defect, and it is the one code in the glob that `_merge_engine.py` does not
     carry — so it is a slightly larger "never add to that list" exception than P0 itself and needs an explicit nod.
     At finalize every per-module entry keeps `UP037` (§5 table) unless (C) is done.
     **(B)** plugin change (emit an unquoted annotation when the destination defers annotations, oracle to match):
     out of this session's hands, blocks the wave.
     **(C)** follow-up after the wave: a separate, declared non-tier-1 commit that strips the quotes
     (signature-only, 75 annotations = 86 moved methods minus the 11 moved staticmethods, which get no receiver) and then deletes `UP037` everywhere. Compatible with (A).
   - The whole sim below ran with (A) as a separate, labelled sim commit (`d951143`); every other number in this plan
     is measured on that basis.
2. **P2 (size baseline) — default works, confirm.** Three destinations exceed 500 by construction (each is one method):
   `_engine_lock.py` 591, `_engine_recover.py` 621, `_engine_recover_conflict.py` 830. None exceeds 1,000. See §4 P2.
3. **Per-cluster focused set is over the brief's ten-minute threshold.** Untouched-branch baseline: 247 tests in
   634.215 s (`.refactor/merge-engine-baseline-focused.txt`). 29 clusters x ~10.5 min is ~5 h of tests alone. The brief
   says to propose a smaller per-cluster set in that case; I have **not** measured per-module timings, so I propose the
   shape only (§7) and leave the split to the session/operator.
4. **Count correction.** The brief speaks of "eight methods over 250 lines"; `quality.py` on the sim tree counts
   **nine** moved methods over 250 (and a tenth function, the nested closure `lifecycle_classification`, 349). §5.
5. **Dead-code candidates are NOT deleted by this plan** (§1): deletion is not a tier-1 move.

## 1. Delete first (dead code, with evidence) — candidates only, none executed

Tier 1 relocates; it does not delete. These four methods have **no caller anywhere** and are listed for a follow-up
bead, not for this wave. Evidence: inventory `calls` has no edge into them; `grep -rn "\b<name>\b" scripts tests docs
skills system` finds only the `def` line in `_merge_engine.py`; the module contains no `getattr(self`, `type(self).`,
`self.__class__` or `MergeEngine.` dynamic dispatch (one `cls.` use, `cls._current_merge_authority`, line 135).

| method | lines | moved in | note |
|---|---|---|---|
| `_record_bootstrap_failure` | 1424–1465 | c08 | no caller |
| `_resolved_fetch_tip` (`staticmethod`) | 1500–1522 | c09 | no caller |
| `_restore_bootstrap_fetch_observation_locked` | 938–954 | c15 | no caller |
| `_parse_remote_observation` (`staticmethod`) | 5593–5621 | c17 | no caller |

**Not dead despite having no caller:** `_head_contained` (5664–5670). Census site 9 patches it with
`side_effect=AssertionError("cleanup used unfenced merge-base")` as a tripwire proving `cleanup_chain` does *not* call
it; `mock.patch.object` needs the attribute to exist. It moves with a binding (c17).

`vulture`/`radon` were not run: the inventory graph plus the repo-wide grep above is the evidence.

## 2. Summary

| item | value |
|---|---|
| baseline | `d885f97` (= `main`), then prep commits P0, P1, P2 (+ P0b if option A) |
| source | `scripts/forge/forge_cli/app/_merge_engine.py`: **10,302** code lines (`scripts/check_file_length.py` count; grandfathered at 10302) |
| class | `MergeEngine`, 93 methods (78 `ok` + 15 `wrap`: 12 `staticmethod`, 1 `classmethod`, 1 `property`, 1 `contextlib.contextmanager`; 0 unsupported), no bases/metaclass/slots, one class statement (the docstring) |
| prerequisites | none (inventory `prerequisites: []`; the module has no top-level def or assignment besides the class, so no "globals need an independent owner" refusal is possible) |
| shape / tier | function shape, `--annotate-self`, **tier 1 only**, `--strict-bodies` |
| result | **29 clusters -> 27 new modules** (two modules are filled by two clusters each); **86 methods moved, 7 stay**; shell `_merge_engine.py` ends at **224** code lines |
| modules over 500 | **3** (591 / 621 / 830), each a single method; **0 over 1,000** |
| refusals | **none** (29/29 `DRY RUN: verified; no files written`) |
| type delta | **NEW 0 / GONE 0 in every cluster** and on the final tree (234 = the P1 baseline) |
| sim gate | 29/29 `GATE: PASS` with `verify.sh --fast` (compile, ruff, file-length, types, lint-imports, manifest oracle `--strict-bodies`) |
| `--retain-module-api` | needed by **no** cluster (0 through-module readers of the 19 pruned names) |

**Sequential-simulation evidence (not the project tree).** The clusters were applied in plan order, one commit each,
in a throwaway `git clone` at `d885f97` under
`/dev/shm/forge-gate/claude-1000/-home-agents-foundry-of-zero-forge-plugin/14e60ebd-baaa-4b34-86f1-b6d1f63af6c3/scratchpad/sim-merge-engine`
on top of sim commits P0 `750e1eb`, P1 `888b256`, P2 `3d37a7e`, P0b `d951143`. The project tree received only evidence
files. The sim's post-P1 source hashes to `3e51b4cc…fd63`, **identical to the project working tree's post-P1 source**
(checked with `sha256sum`), which is the `baseline` digest recorded in the c01 dry-run manifest — so the extractor's
c01 dry run should reproduce the diff and manifest of `.refactor/dryrun-merge-engine-c01-final_mode.txt` (same source
digest, same argv). I did not dry-run in the project tree (off limits), so that equality is expected, not observed.
Per-cluster numbers below are measured there; the extractor's own dry run at apply time is the manifest of record.

Evidence files (all under `.refactor/`):
`dryrun-merge-engine-cNN-<cluster>.txt` x29 (argv, full diff, manifest incl. `remove_imports`, exit code) ·
`merge-engine-sim-results.json` (per cluster: sizes, bindings, imports, removals, gate tail, types line, sim SHA) ·
`merge-engine-sim-types-delta.txt` (NEW/GONE per cluster) · `merge-engine-sim-final.txt` (final ruff, length,
lint-imports, types, per-module ruff codes with the glob disabled, quality, probes, reader check) ·
`merge-engine-sim-focused.txt` (focused tests on the final sim tree) · `merge-engine-sim-driver.txt` ·
`merge-engine-sim-finding-up037-c01-gate.txt` · `merge-engine-sim-up037-probe.txt` · `merge-engine-sim-shell-ruff.txt` ·
`merge-engine-sim-quality.json` · `merge-engine-debt-proposed.json` · `merge-engine-sim-clusters.json` ·
`merge-engine-sim-tool-*.{py,sh}` (the driver, probes, reader check, type-delta helper, final checks — re-runnable).
**Deliberately NOT copied:** the sim's manifests `merge-engine-<cluster>.json` and snapshots
`merge-engine-cNN-before.json` — a pre-existing manifest makes the real `--apply` refuse ("refuses existing manifest
outputs"). A collision check against all 58 planned names came back empty.

## 3. Stays in `_merge_engine.py` (7 defs; shell measured at 224 code lines)

| method | lines | decorator | reason |
|---|---|---|---|
| `__init__` | 26–30 | — | constructor; owns both instance attributes `self.ctx` and `self._git_no_lazy_fetch_qualification` (the two `@state:` hubs). Operator rule. |
| `store` | 209–216 | `property` | operator decision: moved as `property(...)` its uses become `Any` under mypy even with `--annotate-self`. |
| `_load` | 218–238 | — | hub, fan-in 13; the chain-state loader every verb starts with. |
| `_halt` | 270–285 | — | hub, fan-in 10. |
| `_wrong_state` | 3341–3351 | `staticmethod` | hub, fan-in 13. |
| `_epoch_transition` | 4276–4301 | — | hub, fan-in 27: the single state-transition primitive. |
| `_tail_event_digest` | 4303–4315 | — | hub, fan-in 16. |

Why these five small hubs stay rather than forming an `_engine_core.py`: together they are 87 code lines — the class's
state-access kernel (load, halt, wrong-state refusal, epoch transition, tail digest) that *every* moved module reaches
through `self.`. A five-function, ~100-line module would be below the 150-line floor, and keeping them as real methods
leaves the shell a readable definition of what a `MergeEngine` *is* rather than 93 bare bindings. The shell ends at
224, far under 500, so the size rule is not what decides this. Note `store` is read by 48 of the 93 methods, about 45 of
which move: they read a real property through the annotated `self`, and every one of those clusters still measures
NEW 0 / GONE 0 — the regrouping the lead anticipated for `self.store` readers turned out not to be needed.

The sixth small hub, `_admission_from_candidate_observation` (53 lines, fan-in 4), **moves** (c07): it is admission
logic with a natural family, not a state primitive. The four large hubs move as the lead directed:
`_recording_common_lock` (c16), `_run_remote_observation` (c18), `_run_candidate_observation_locked` (c15),
`_preflight_lifecycle` (c04).

Under function shape every `self.x(...)` resolves through the class attribute whether `x` is a `def` or a binding, in
any commit order. **The critic must not flag cross-cluster `self.` calls**; the sim gated the mechanism from c01 on.

### State ownership

The module has **no module-level assignment and no `global` statement** (grep: none), so there is no module state to
place. The only state is the two instance attributes, both owned by `__init__`, which stays on the shell:

| state | owner | writers | readers |
|---|---|---|---|
| `self.ctx` | `__init__` (shell) | `__init__` only | 36 methods across the shell and most modules |
| `self._git_no_lazy_fetch_qualification` | `__init__` (shell) | `__init__`; `_prepare_git_no_lazy_fetch_qualification`, `_prepare_bootstrap_git_no_lazy_fetch_qualification` (c01); `recover` (c28); `finalize` (c29) | `_final_history_mutation_mode` (c01), `refresh` (c07), `start_chain` (c08), `_run_bootstrap_generation_composite` (c09) |

Writes from moved functions go through `self: "MergeEngine"`, so mypy checks them against the declaration in
`__init__` (c01, c28 and c29 each measure NEW 0 / GONE 0). No re-export is needed in `app/__init__.py`: it imports
only `MergeEngine`, stays byte-identical (probe 11), and no `_engine_*` name enters `__all__`.

Shell header after the wave (sim): `from __future__ import annotations`; `import contextlib` (still read by the
`contextlib.contextmanager(...)` binding); `from pathlib import Path`; `from typing import Any, Mapping`;
`from forge_cli import chain_core, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA,
ReasonCode, Refusal, V2ReasonCode`; then 27 `from . import _engine_<x>` lines in cluster order. `ruff` passes on it at
every step with `F401` *not* ignored there, i.e. no missed removal.

## 4. Prep commits, then clusters in execution order

### P0 — config only (already on the branch as `6ee38b6`)
`"scripts/forge/forge_cli/app/_engine_*.py" = [` the `_merge_engine.py` list minus `I001` `]`. Temporary; finalize
replaces it with the measured per-module entries of §5 and deletes it. Measured: the union of codes the 27 modules trip
with the glob disabled is **exactly** this list plus `UP037` — no glob code is unused, no other code appears.

### P0b — config only, **operator decision 1** (recommended)
Add `"UP037"` to that glob. Message: config-only, mover-generated quoted receiver annotations, temporary until finalize.

### P1 — type only (in progress in the project tree; reproduced in the sim)
`Iterable` -> `Iterator` at line 14 and in the return annotation at line 332; nothing else; no line shifts.
Sim: `types ok: 234 error(s) … (7 fixed since baseline)`, NEW 0; baseline ratcheted 241 -> 234. All per-cluster deltas
in this plan are against that 234 baseline. (`Iterator` is later pruned from the shell by c16, its last reader.)

### P2 — config only: provisional `.refactor-baseline.json` entries (**operator decision 2**, default works)
```
"scripts/forge/forge_cli/app/_engine_lock.py": 591,
"scripts/forge/forge_cli/app/_engine_recover.py": 621,
"scripts/forge/forge_cli/app/_engine_recover_conflict.py": 830,
```
inserted before the `_merge_engine.py` entry. How the tool treats it (read from `check_file_length.py:check`, both the
project copy and the plugin copy `verify.sh` runs): files are enumerated from disk and the baseline is only consulted
for a path that exists, so **entries for files that do not exist yet are inert** (sim: `ok: 6 files within budget`
right after P2); the only failure condition for a listed file is `n > allowed`, so a file created at exactly its entry
passes (sim: c16 at 591, c26 at 830, c28 at 621 all `PASS file-length`). "May shrink, never grow" would also tolerate a
module that reaches its size over several clusters, but that case **does not arise**: each of the three is created by
exactly one cluster. Nothing else reads the baseline (`.pre-commit-config.yaml`, `guardrails.yml`, one unit test with
its own temp file). Precedent: the app split committed the provisional `_merge_engine.py` entry before its extractor.
Without P2, c16/c26/c28 fail `file-length` inside `verify.sh`. The `_merge_engine.py` entry (10302) needs no change
during the wave (it only shrinks); finalize deletes it (224 < 500).

### Common to every cluster
- One commit per cluster, sequential, each on top of the previous commit. Commit P0b/P2 and each cluster **before** the
  next dry run: apply refuses a stale/uncommitted HEAD and a pre-existing manifest path.
- Before apply: `python3 $S/snapshot_bodies.py snapshot scripts/forge/forge_cli --out .refactor/merge-engine-cNN-before.json`
  — scope **exactly** `scripts/forge/forge_cli` (the gate's `--pkg`). Including `tests` makes the oracle fail with
  "unmanifested file added or removed" (session-1 critique, blocking finding 1).
- Gate environment, verbatim, from the repo root (session-1 critique, blocking finding 2 — without it the `types` step
  reports 3 bogus `import-untyped` errors and the gate FAILs):
  `env -u FORGE_SESSION_PID -u REFACTOR_TYPE_CMD PYTHONPATH=scripts:scripts/forge MYPYPATH=scripts:scripts/forge TMPDIR=/dev/shm/forge-gate PATH="$HOME/.local/bin:$PATH" bash $S/verify.sh …`
  (`REFACTOR_TEST_CMD` / `REFACTOR_MINT_CMD` come from the launching shell.)
- Type gate: `type_baseline.py check` prints only a GONE *count*; record keys per cluster in
  `.refactor/types-delta-merge-engine-<cluster>.txt` (the sim helper `merge-engine-sim-tool-types_delta.py` prints NEW
  and GONE keys using the plugin's own `run_checker`/`key`). Stop on any NEW or GONE. Never `--update` after P1.
- `remove_imports` is sequence-dependent and **absent from the manifest when empty**; the values below are sequential.
  A missed removal is an `F401` in `_merge_engine.py` (not ignored there) and fails ruff; an extra removal breaks a
  remaining body and fails mypy/tests. Never add `F401`/`F821` to an ignore list.
- Expected per-cluster diff: deleted `def`s in the class, bindings inserted at the same positions, at most one
  `from . import _engine_<x>` line, import-line shrinkage in `_merge_engine.py`, the new/extended destination, plus
  `.refactor/merge-engine-<cluster>.json` and `.refactor/merge-engine-cNN-before.json`. Do not tidy binding order.
- CHANGELOG: one entry for the branch (shared protocol, `docs/analysis/refactor-plan-2026-09-19.md:79`).
- Expected refusals: **none**. Inventory `reasons: []` and `mangled: []` for all 93; no setter/deleter, no stacked or
  undeclared decorator, no `super`/`__class__`, no global still defined in the source, no destination name clash, and
  the two shared-destination clusters reuse an *identical* `if TYPE_CHECKING:` block (a different block would refuse).

### Cluster overview (all values measured in the sim)

| # | cluster | destination | methods | dest code lines after | `_merge_engine.py` after | mypy NEW / GONE | sim gate |
|---|---|---|---|---|---|---|---|
| c01 | `final_mode` | `_engine_final_mode.py` | 6 | **177** | 10138 | 0 / 0 | PASS |
| c02 | `gate` | `_engine_gate.py` | 5 | **396** | 9762 | 0 / 0 | PASS |
| c03 | `final_mode_recover` | `_engine_final_mode.py` (existing, from c01) | 2 | **312** | 9634 | 0 / 0 | PASS |
| c04 | `lifecycle` | `_engine_lifecycle.py` | 5 | **318** | 9331 | 0 / 0 | PASS |
| c05 | `review_request` | `_engine_review_request.py` | 3 | **231** | 9113 | 0 / 0 | PASS |
| c06 | `review_verdict` | `_engine_review_verdict.py` | 2 | **315** | 8811 | 0 / 0 | PASS |
| c07 | `refresh` | `_engine_refresh.py` | 4 | **291** | 8536 | 0 / 0 | PASS |
| c08 | `start_chain` | `_engine_start_chain.py` | 6 | **454** | 8100 | 0 / 0 | PASS |
| c09 | `bootstrap` | `_engine_bootstrap.py` | 4 | **479** | 7632 | 0 / 0 | PASS |
| c10 | `release_aborted` | `_engine_release_aborted.py` | 3 | **321** | 7324 | 0 / 0 | PASS |
| c11 | `abort` | `_engine_abort.py` | 2 | **419** | 6917 | 0 / 0 | PASS |
| c12 | `release_pending` | `_engine_release_pending.py` | 3 | **277** | 6651 | 0 / 0 | PASS |
| c13 | `cleanup_child` | `_engine_cleanup_child.py` | 3 | **311** | 6354 | 0 / 0 | PASS |
| c14 | `cleanup` | `_engine_cleanup.py` | 1 | **438** | 5926 | 0 / 0 | PASS |
| c15 | `observation` | `_engine_observation.py` | 4 | **264** | 5675 | 0 / 0 | PASS |
| c16 | `lock` | `_engine_lock.py` | 2 | **591** | 5095 | 0 / 0 | PASS |
| c17 | `observation_parse` | `_engine_observation.py` (existing, from c15) | 3 | **338** | 5022 | 0 / 0 | PASS |
| c18 | `observe_remote` | `_engine_observe_remote.py` | 1 | **495** | 4539 | 0 / 0 | PASS |
| c19 | `epoch_fetch` | `_engine_epoch_fetch.py` | 6 | **446** | 4109 | 0 / 0 | PASS |
| c20 | `epoch_ancestry` | `_engine_epoch_ancestry.py` | 2 | **286** | 3834 | 0 / 0 | PASS |
| c21 | `epoch_rebase` | `_engine_epoch_rebase.py` | 3 | **449** | 3399 | 0 / 0 | PASS |
| c22 | `epoch_suite` | `_engine_epoch_suite.py` | 1 | **392** | 3019 | 0 / 0 | PASS |
| c23 | `epoch_push` | `_engine_epoch_push.py` | 2 | **251** | 2780 | 0 / 0 | PASS |
| c24 | `rebase_recovery` | `_engine_rebase_recovery.py` | 3 | **356** | 2439 | 0 / 0 | PASS |
| c25 | `conflict_observation` | `_engine_conflict_observation.py` | 1 | **240** | 2211 | 0 / 0 | PASS |
| c26 | `recover_conflict` | `_engine_recover_conflict.py` | 1 | **830** | 1391 | 0 / 0 | PASS |
| c27 | `recover_bootstrap` | `_engine_recover_bootstrap.py` | 4 | **397** | 1006 | 0 / 0 | PASS |
| c28 | `recover` | `_engine_recover.py` | 1 | **621** | 396 | 0 / 0 | PASS |
| c29 | `finalize` | `_engine_finalize.py` | 3 | **183** | 224 | 0 / 0 | PASS |

### c01 — `final_mode`

- destination: `scripts/forge/forge_cli/app/_engine_final_mode.py` — git no-lazy-fetch qualification and the final intended-HEAD history-mode family.
- methods (source order): `_final_mode_unavailable` (33–43, `staticmethod`), `_prepare_git_no_lazy_fetch_qualification` (45–62), `_prepare_bootstrap_git_no_lazy_fetch_qualification` (64–100), `_final_history_mutation_mode` (6201–6259), `_park_invalid_final_history_mode` (6261–6305), `_current_merge_authority` (6871–6872, `staticmethod`)
- why this grouping: First on purpose; the operator inspects this one by hand. `_final_mode_unavailable` (staticmethod) is called only by `_prepare_git_no_lazy_fetch_qualification` and `_final_history_mutation_mode`, both here. The two `_prepare_*_qualification` methods are twins and two of the five writers of `self._git_no_lazy_fetch_qualification` (the others: `__init__` on the shell, `recover` c28, `finalize` c29). `_final_history_mutation_mode` / `_park_invalid_final_history_mode` are called only by `_run_epoch_push` (c23), which reaches them through the class bindings. `_current_merge_authority` (staticmethod, 2 lines) is the authority predicate the final-mode decisions use (callers: `_recover_can_reach_final_mode` c03 same module, `_run_epoch_push` c23, `_finish_recovered_epoch_locked` c29). Representative and low risk: 2 `staticmethod` bindings + 4 plain bindings, no census site, 177 code lines, no nested defs, exercises typing-import copying (`Any`, `Mapping` merged with the generated `TYPE_CHECKING`), and exercises an instance-attribute WRITE through the annotated `self` (type-checked, NEW 0 / GONE 0). Its callers `recover`, `finalize`, `start_chain`, `refresh`, `_run_epoch_push` are all still real methods at this point, so cross-cluster `self.` resolution through bindings is gated in the very first cluster.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _final_mode_unavailable,_prepare_git_no_lazy_fetch_qualification,_prepare_bootstrap_git_no_lazy_fetch_qualification,_final_history_mutation_mode,_park_invalid_final_history_mode,_current_merge_authority --dest scripts/forge/forge_cli/app/_engine_final_mode.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-final_mode.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _final_mode_unavailable = staticmethod(_engine_final_mode._final_mode_unavailable)
  _prepare_git_no_lazy_fetch_qualification = _engine_final_mode._prepare_git_no_lazy_fetch_qualification
  _prepare_bootstrap_git_no_lazy_fetch_qualification = _engine_final_mode._prepare_bootstrap_git_no_lazy_fetch_qualification
  _final_history_mutation_mode = _engine_final_mode._final_history_mutation_mode
  _park_invalid_final_history_mode = _engine_final_mode._park_invalid_final_history_mode
  _current_merge_authority = staticmethod(_engine_final_mode._current_merge_authority)
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_final_mode`; `remove_imports` (sequential): none
- size (measured in the sim): destination **177** code lines; `_merge_engine.py` after: **10138**
- census: none of the 9 sites names these methods -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c01-final_mode.txt` (sim commit `560cc17`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c01-before.json --manifest .refactor/merge-engine-final_mode.json --strict-bodies`
- commit: `refactor(app): move final_mode methods to _engine_final_mode.py (tier 1, function shape)`

### c02 — `gate`

- destination: `scripts/forge/forge_cli/app/_engine_gate.py` — gate execution: gate resolution, scoped mutation, gate-result recording, and the `gate_run` / `verify` verbs.
- methods (source order): `_resolve_gate` (3353–3421), `_run_scoped_mutation` (3423–3507), `_record_gate_result` (3509–3570), `gate_run` (3572–3701), `verify` (3703–3738)
- why this grouping: `_run_scoped_mutation` and `_record_gate_result` are called only by `gate_run`; `verify` calls `self.gate_run`. `_resolve_gate` is called by `gate_run` and by `_run_epoch_suite` (c22) -> second on purpose: an early cross-cluster `self.` call INTO a moved method from a still-real method, and calls OUT of moved bodies to shell hubs (`_load`, `_halt`, `_wrong_state`) and to `_preflight_lifecycle` (real until c04, a binding after).
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _resolve_gate,_run_scoped_mutation,_record_gate_result,gate_run,verify --dest scripts/forge/forge_cli/app/_engine_gate.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-gate.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _resolve_gate = _engine_gate._resolve_gate
  _run_scoped_mutation = _engine_gate._run_scoped_mutation
  _record_gate_result = _engine_gate._record_gate_result
  gate_run = _engine_gate.gate_run
  verify = _engine_gate.verify
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `import re`; `import secrets`; `import sys`; `from pathlib import Path`; `from typing import Any, Mapping, Sequence`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.app._candidate_observation import _observe_current_merge_candidate`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, V2ReasonCode`; `from forge_cli.policy import Policy, sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_gate`; `remove_imports` (sequential): none
- size (measured in the sim): destination **396** code lines; `_merge_engine.py` after: **9762**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c02-gate.txt` (sim commit `adf8ea7`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c02-before.json --manifest .refactor/merge-engine-gate.json --strict-bodies`
- commit: `refactor(app): move gate methods to _engine_gate.py (tier 1, function shape)`

### c03 — `final_mode_recover`

- destination: `scripts/forge/forge_cli/app/_engine_final_mode.py` (**existing module**, created by c01) — (same module as c01) recover-side reachability of the final mode and the read-only recovery flag state.
- methods (source order): `_recover_can_reach_final_mode` (103–206, `classmethod`), `_read_only_recovery_flag_state` (240–268)
- why this grouping: Second cluster INTO AN EXISTING DESTINATION and the only `classmethod` in the class, placed early so both mechanisms are gated by c03. `_recover_can_reach_final_mode` (classmethod, calls `cls._current_merge_authority`, moved in c01) decides whether recovery can reach the final mode: same family as c01. `_read_only_recovery_flag_state` is the other read-only `recover` preflight (sole caller `recover`). Kept out of c01 so the operator's first cluster carries no classmethod binding. The mover reuses the identical `if TYPE_CHECKING:` block and merges the new imports into the existing header (verified in the sim: `DRY RUN: verified`, oracle PASS).
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _recover_can_reach_final_mode,_read_only_recovery_flag_state --dest scripts/forge/forge_cli/app/_engine_final_mode.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-final_mode_recover.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _recover_can_reach_final_mode = classmethod(_engine_final_mode._recover_can_reach_final_mode)
  _read_only_recovery_flag_state = _engine_final_mode._read_only_recovery_flag_state
  ```
- destination imports NEWLY ADDED by this cluster (manifest `imports[dest]`; the mover merges them into the existing header and reuses the identical `if TYPE_CHECKING:` block): `from forge_cli.envelope import ReasonCode`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: none added (`from . import _engine_final_mode` already present from c01); `remove_imports` (sequential): none
- size (measured in the sim): destination **312** code lines; `_merge_engine.py` after: **9634**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c03-final_mode_recover.txt` (sim commit `41ce352`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c03-before.json --manifest .refactor/merge-engine-final_mode_recover.json --strict-bodies`
- commit: `refactor(app): move final_mode_recover methods to _engine_final_mode.py (tier 1, function shape)`

### c04 — `lifecycle`

- destination: `scripts/forge/forge_cli/app/_engine_lifecycle.py` — lifecycle preflight and the simple lifecycle verbs (`start`, `bind_candidate`, `approve`, `status`).
- methods (source order): `start` (1156–1170), `bind_candidate` (1172–1184), `_preflight_lifecycle` (1186–1285), `approve` (2575–2709), `status` (3291–3338)
- why this grouping: `_preflight_lifecycle` (hub, fan-in 10, 100 lines) is the shared preflight of every lifecycle verb; under function shape its ten callers keep resolving it through the class binding. `start` / `bind_candidate` are thin adapters with no intra-class edge (external callers only: `start` from `_dispatch.py:164` and tests, `bind_candidate` from tests only); `approve` and `status` are the two remaining verbs whose only intra-class edges are shell hubs plus `_preflight_lifecycle`. Seed-forced, hub-only singletons grouped by role (as session 1's `decision` cluster was): four modules of 13-135 lines would defeat the module target.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods start,bind_candidate,_preflight_lifecycle,approve,status --dest scripts/forge/forge_cli/app/_engine_lifecycle.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-lifecycle.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  start = _engine_lifecycle.start
  bind_candidate = _engine_lifecycle.bind_candidate
  _preflight_lifecycle = _engine_lifecycle._preflight_lifecycle
  approve = _engine_lifecycle.approve
  status = _engine_lifecycle.status
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, engine`; `from forge_cli.app._admission import prepare_merge_admission`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, V2ReasonCode`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_lifecycle`; `remove_imports` (sequential): none
- size (measured in the sim): destination **318** code lines; `_merge_engine.py` after: **9331**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c04-lifecycle.txt` (sim commit `78d7dd5`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c04-before.json --manifest .refactor/merge-engine-lifecycle.json --strict-bodies`
- commit: `refactor(app): move lifecycle methods to _engine_lifecycle.py (tier 1, function shape)`

### c05 — `review_request`

- destination: `scripts/forge/forge_cli/app/_engine_review_request.py` — review package construction and the review request/collect verbs.
- methods (source order): `_review_package` (3740–3836), `review_request` (3838–3951), `review_collect` (3953–3963)
- why this grouping: `_review_package` is called only by `review_request`. `review_collect` (11 lines) always refuses in the merge family and points the caller to `review attach`; it shares nothing but shell hubs and `_preflight_lifecycle` with either review module and is placed here, in the smaller of the two, as a judgment call (it would fit c06 equally: 315 + ~11). The two review modules are not merged: 231 + 315 > 500.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _review_package,review_request,review_collect --dest scripts/forge/forge_cli/app/_engine_review_request.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-review_request.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _review_package = _engine_review_request._review_package
  review_request = _engine_review_request.review_request
  review_collect = _engine_review_request.review_collect
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from typing import Any, Mapping, Sequence`; `from forge_cli import chain_core, engine`; `from forge_cli.app._candidate_observation import _observe_current_merge_candidate`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, V2ReasonCode`; `from forge_cli.policy import Policy, sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_review_request`; `remove_imports` (sequential): none
- size (measured in the sim): destination **231** code lines; `_merge_engine.py` after: **9113**
- census: none -> no repoint. `_review_package` calls `engine.Engine._profiles_for_path` (the session-1 staticmethod binding) through the `engine` package import, unchanged.
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c05-review_request.txt` (sim commit `239074e`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c05-before.json --manifest .refactor/merge-engine-review_request.json --strict-bodies`
- commit: `refactor(app): move review_request methods to _engine_review_request.py (tier 1, function shape)`

### c06 — `review_verdict`

- destination: `scripts/forge/forge_cli/app/_engine_review_verdict.py` — verdict intake verbs: `review_attach` and `review_disposition`.
- methods (source order): `review_attach` (3965–4119), `review_disposition` (4121–4274, 1 nested)
- why this grouping: The two verdict-side review verbs; both are over the 150-line function target (tier-2 candidates), share only shell hubs and `_preflight_lifecycle`. `review_disposition` carries one nested def, which travels verbatim.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods review_attach,review_disposition --dest scripts/forge/forge_cli/app/_engine_review_verdict.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-review_verdict.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  review_attach = _engine_review_verdict.review_attach
  review_disposition = _engine_review_verdict.review_disposition
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `import stat`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.app._candidate_observation import _observe_current_merge_candidate`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, V2ReasonCode`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_review_verdict`; `remove_imports` (sequential): `stat`
- size (measured in the sim): destination **315** code lines; `_merge_engine.py` after: **8811**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c06-review_verdict.txt` (sim commit `8cb3461`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c06-before.json --manifest .refactor/merge-engine-review_verdict.json --strict-bodies`
- commit: `refactor(app): move review_verdict methods to _engine_review_verdict.py (tier 1, function shape)`

### c07 — `refresh`

- destination: `scripts/forge/forge_cli/app/_engine_refresh.py` — admission derivation from a candidate observation and the `refresh` verb.
- methods (source order): `_admission_from_candidate_observation` (2291–2343), `_admission_for_refresh` (2345–2398), `_refresh_iteration` (2400–2448), `refresh` (2450–2573)
- why this grouping: `_admission_for_refresh` and `_refresh_iteration` are called by `refresh` (and `_admission_for_refresh` by `_recover_classifying_bootstrap_v12_locked`, c27, via `self.`). `_admission_from_candidate_observation` is a hub (fan-in 4: here, `_run_epoch_suite` c22, `_run_remote_observation` c18, `_materialize_rebase_success_locked` c24) but it is 53 lines of admission logic, not a state primitive: it moves with its family rather than staying on the shell.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _admission_from_candidate_observation,_admission_for_refresh,_refresh_iteration,refresh --dest scripts/forge/forge_cli/app/_engine_refresh.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-refresh.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _admission_from_candidate_observation = _engine_refresh._admission_from_candidate_observation
  _admission_for_refresh = _engine_refresh._admission_for_refresh
  _refresh_iteration = _engine_refresh._refresh_iteration
  refresh = _engine_refresh.refresh
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import dataclasses`; `import secrets`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, engine`; `from forge_cli.app._admission import prepare_merge_admission`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, V2ReasonCode`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_refresh`; `remove_imports` (sequential): `dataclasses`
- size (measured in the sim): destination **291** code lines; `_merge_engine.py` after: **8536**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c07-refresh.txt` (sim commit `ce6a5e3`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c07-before.json --manifest .refactor/merge-engine-refresh.json --strict-bodies`
- commit: `refactor(app): move refresh methods to _engine_refresh.py (tier 1, function shape)`

### c08 — `start_chain`

- destination: `scripts/forge/forge_cli/app/_engine_start_chain.py` — chain creation: slot claim, chain-id allocation, initial state, bootstrap classification completion, and the `start_chain` verb.
- methods (source order): `_claim_slot` (1287–1354), `_allocate_chain_id` (1356–1367), `_initial_merge_state` (1369–1422), `_record_bootstrap_failure` (1424–1465), `_complete_bootstrap_classification` (2021–2127), `start_chain` (2130–2289)
- why this grouping: `_claim_slot`, `_allocate_chain_id`, `_initial_merge_state` are called only by `start_chain`. `_complete_bootstrap_classification` is called by `start_chain` (here), `refresh` (c07) and `recover` (c28). `_record_bootstrap_failure` has no caller anywhere (see Delete-first candidates) and is bootstrap-start bookkeeping: it travels with this family, not deleted.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _claim_slot,_allocate_chain_id,_initial_merge_state,_record_bootstrap_failure,_complete_bootstrap_classification,start_chain --dest scripts/forge/forge_cli/app/_engine_start_chain.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-start_chain.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _claim_slot = _engine_start_chain._claim_slot
  _allocate_chain_id = _engine_start_chain._allocate_chain_id
  _initial_merge_state = _engine_start_chain._initial_merge_state
  _record_bootstrap_failure = _engine_start_chain._record_bootstrap_failure
  _complete_bootstrap_classification = _engine_start_chain._complete_bootstrap_classification
  start_chain = _engine_start_chain.start_chain
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `import secrets`; `import socket`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, engine`; `from forge_cli.app._admission import prepare_merge_admission`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_start_chain`; `remove_imports` (sequential): `prepare_merge_admission`, `socket`
- size (measured in the sim): destination **454** code lines; `_merge_engine.py` after: **8100**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c08-start_chain.txt` (sim commit `2efc671`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c08-before.json --manifest .refactor/merge-engine-start_chain.json --strict-bodies`
- commit: `refactor(app): move start_chain methods to _engine_start_chain.py (tier 1, function shape)`

### c09 — `bootstrap`

- destination: `scripts/forge/forge_cli/app/_engine_bootstrap.py` — bootstrap generation: fetch argv, fetch-tip resolution and the composite bootstrap generation.
- methods (source order): `_bootstrap_fetch_argv` (1468–1497, `staticmethod`), `_resolved_fetch_tip` (1500–1522, `staticmethod`), `_run_bootstrap_generation_composite` (1583–1994, 4 nested), `_run_bootstrap_generation` (1996–2019)
- why this grouping: `_run_bootstrap_generation` is a 24-line wrapper whose only callee is `_run_bootstrap_generation_composite` (412 lines, 4 nested defs; the bead's `bootstrap` seam), which calls `_bootstrap_fetch_argv` (staticmethod). `_resolved_fetch_tip` (staticmethod, no caller anywhere) is the bootstrap fetch-tip resolver and sits with its family. 479 measured: the largest module that stays under target; nothing else may be added here.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _bootstrap_fetch_argv,_resolved_fetch_tip,_run_bootstrap_generation_composite,_run_bootstrap_generation --dest scripts/forge/forge_cli/app/_engine_bootstrap.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-bootstrap.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _bootstrap_fetch_argv = staticmethod(_engine_bootstrap._bootstrap_fetch_argv)
  _resolved_fetch_tip = staticmethod(_engine_bootstrap._resolved_fetch_tip)
  _run_bootstrap_generation_composite = _engine_bootstrap._run_bootstrap_generation_composite
  _run_bootstrap_generation = _engine_bootstrap._run_bootstrap_generation
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_bootstrap`; `remove_imports` (sequential): none
- size (measured in the sim): destination **479** code lines; `_merge_engine.py` after: **7632**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c09-bootstrap.txt` (sim commit `23900c8`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c09-before.json --manifest .refactor/merge-engine-bootstrap.json --strict-bodies`
- commit: `refactor(app): move bootstrap methods to _engine_bootstrap.py (tier 1, function shape)`

### c10 — `release_aborted`

- destination: `scripts/forge/forge_cli/app/_engine_release_aborted.py` — release to `aborted`: unlocked and locked release paths and the scope-exceeded release.
- methods (source order): `_release_to_aborted` (2711–2840), `_release_to_aborted_locked` (2842–2961), `_release_scope_exceeded` (2963–3031)
- why this grouping: `_release_scope_exceeded` calls `_release_to_aborted`; `_release_to_aborted_locked` is its locked twin (callers `abort` c11, `_recover_classifying_bootstrap_v12_locked` c27). The callers of `_release_to_aborted` and `_release_scope_exceeded` (`_run_bootstrap_generation_composite` c09, `_complete_bootstrap_classification` c08) have already moved and reach them via `self.` from another module: the first cluster with module-to-module calls through the class. `_release_to_aborted_locked`'s callers (`abort` c11, v12 recovery c27) are still real methods at this point.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _release_to_aborted,_release_to_aborted_locked,_release_scope_exceeded --dest scripts/forge/forge_cli/app/_engine_release_aborted.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-release_aborted.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _release_to_aborted = _engine_release_aborted._release_to_aborted
  _release_to_aborted_locked = _engine_release_aborted._release_to_aborted_locked
  _release_scope_exceeded = _engine_release_aborted._release_scope_exceeded
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_release_aborted`; `remove_imports` (sequential): none
- size (measured in the sim): destination **321** code lines; `_merge_engine.py` after: **7324**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c10-release_aborted.txt` (sim commit `7039024`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c10-before.json --manifest .refactor/merge-engine-release_aborted.json --strict-bodies`
- commit: `refactor(app): move release_aborted methods to _engine_release_aborted.py (tier 1, function shape)`

### c11 — `abort`

- destination: `scripts/forge/forge_cli/app/_engine_abort.py` — the `abort` verb and the attempted-release precondition proof it needs.
- methods (source order): `abort` (3033–3289), `_attempted_release_preconditions_locked` (7064–7220)
- why this grouping: `_attempted_release_preconditions_locked` is called by `abort` (here) and `_release_historical_landing_locked` (c12). `abort` + preconditions measure 419; adding `_release_historical_landing_locked` (90 code lines) would exceed 500, so it goes to c12.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods abort,_attempted_release_preconditions_locked --dest scripts/forge/forge_cli/app/_engine_abort.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-abort.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  abort = _engine_abort.abort
  _attempted_release_preconditions_locked = _engine_abort._attempted_release_preconditions_locked
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, engine`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, V2ReasonCode`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_abort`; `remove_imports` (sequential): none
- size (measured in the sim): destination **419** code lines; `_merge_engine.py` after: **6917**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c11-abort.txt` (sim commit `415b089`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c11-before.json --manifest .refactor/merge-engine-abort.json --strict-bodies`
- commit: `refactor(app): move abort methods to _engine_abort.py (tier 1, function shape)`

### c12 — `release_pending`

- destination: `scripts/forge/forge_cli/app/_engine_release_pending.py` — pending-release completion/resumption and the historical-landing release.
- methods (source order): `_complete_pending_release_locked` (6874–6998), `_resume_pending_release` (7000–7062), `_release_historical_landing_locked` (7222–7311)
- why this grouping: `_resume_pending_release` calls `_complete_pending_release_locked`; both are called by `recover` and `cleanup_chain`. `_release_historical_landing_locked` (callers `abort`, `recover`) is the third release-completion path and shares the `_epoch_transition` + release-record seam.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _complete_pending_release_locked,_resume_pending_release,_release_historical_landing_locked --dest scripts/forge/forge_cli/app/_engine_release_pending.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-release_pending.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _complete_pending_release_locked = _engine_release_pending._complete_pending_release_locked
  _resume_pending_release = _engine_release_pending._resume_pending_release
  _release_historical_landing_locked = _engine_release_pending._release_historical_landing_locked
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `from typing import Any, Mapping`; `from forge_cli import chain_core, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, V2ReasonCode`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_release_pending`; `remove_imports` (sequential): none
- size (measured in the sim): destination **277** code lines; `_merge_engine.py` after: **6651**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c12-release_pending.txt` (sim commit `65cfe78`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c12-before.json --manifest .refactor/merge-engine-release_pending.json --strict-bodies`
- commit: `refactor(app): move release_pending methods to _engine_release_pending.py (tier 1, function shape)`

### c13 — `cleanup_child`

- destination: `scripts/forge/forge_cli/app/_engine_cleanup_child.py` — cleanup child execution, its result recording and the release to `closed`.
- methods (source order): `_release_to_closed_locked` (6556–6666), `_cleanup_result_locked` (6668–6700), `_run_cleanup_child` (6702–6868, 2 nested)
- why this grouping: `_cleanup_result_locked` is called only by `_run_cleanup_child`; `_run_cleanup_child` and `_release_to_closed_locked` are called only by `cleanup_chain` (c14). Split from c14 because `cleanup_chain` alone measures 438 (bead seam `cleanup` = these two modules).
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _release_to_closed_locked,_cleanup_result_locked,_run_cleanup_child --dest scripts/forge/forge_cli/app/_engine_cleanup_child.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-cleanup_child.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _release_to_closed_locked = _engine_cleanup_child._release_to_closed_locked
  _cleanup_result_locked = _engine_cleanup_child._cleanup_result_locked
  _run_cleanup_child = _engine_cleanup_child._run_cleanup_child
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `import secrets`; `from typing import Any, Callable, Mapping, Sequence`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_cleanup_child`; `remove_imports` (sequential): none
- size (measured in the sim): destination **311** code lines; `_merge_engine.py` after: **6354**
- census: none -> no repoint (the `_head_contained` tripwire patch wraps `engine.cleanup_chain()`, it does not name these methods)
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c13-cleanup_child.txt` (sim commit `6e276cb`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c13-before.json --manifest .refactor/merge-engine-cleanup_child.json --strict-bodies`
- commit: `refactor(app): move cleanup_child methods to _engine_cleanup_child.py (tier 1, function shape)`

### c14 — `cleanup`

- destination: `scripts/forge/forge_cli/app/_engine_cleanup.py` — the `cleanup_chain` verb.
- methods (source order): `cleanup_chain` (10021–10473, 9 nested)
- why this grouping: Singleton: 453 lines with 9 nested defs (the largest closure population after `_recover_conflict_locked`); tier-2 candidate. Own module so the later extraction has a home and the module stays under target.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods cleanup_chain --dest scripts/forge/forge_cli/app/_engine_cleanup.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-cleanup.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  cleanup_chain = _engine_cleanup.cleanup_chain
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import os`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, engine`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, V2ReasonCode`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_cleanup`; `remove_imports` (sequential): none
- size (measured in the sim): destination **438** code lines; `_merge_engine.py` after: **5926**
- census: none names it directly; the `_head_contained` tripwire test (site 9) drives `engine.cleanup_chain()` -> covered by the focused set
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c14-cleanup.txt` (sim commit `d7972b3`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c14-before.json --manifest .refactor/merge-engine-cleanup.json --strict-bodies`
- commit: `refactor(app): move cleanup methods to _engine_cleanup.py (tier 1, function shape)`

### c15 — `observation`

- destination: `scripts/forge/forge_cli/app/_engine_observation.py` — observation primitives: candidate-observation transition, intent restore and the locked candidate observation.
- methods (source order): `_candidate_observation_transition` (886–913), `_restore_candidate_observation_intent_locked` (915–936), `_restore_bootstrap_fetch_observation_locked` (938–954), `_run_candidate_observation_locked` (956–1154, 3 nested)
- why this grouping: `_candidate_observation_transition` is called only by the other three; `_restore_candidate_observation_intent_locked` by `_run_candidate_observation_locked` and `recover`. `_run_candidate_observation_locked` is a hub (fan-in 8, 199 lines, 3 nested defs) and moves (function shape: callers resolve through the binding). `_restore_bootstrap_fetch_observation_locked` has no caller anywhere (Delete-first candidate) and belongs to this family by its only callee.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _candidate_observation_transition,_restore_candidate_observation_intent_locked,_restore_bootstrap_fetch_observation_locked,_run_candidate_observation_locked --dest scripts/forge/forge_cli/app/_engine_observation.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-observation.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _candidate_observation_transition = _engine_observation._candidate_observation_transition
  _restore_candidate_observation_intent_locked = _engine_observation._restore_candidate_observation_intent_locked
  _restore_bootstrap_fetch_observation_locked = _engine_observation._restore_bootstrap_fetch_observation_locked
  _run_candidate_observation_locked = _engine_observation._run_candidate_observation_locked
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import base64`; `import copy`; `from typing import Any, Mapping`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_observation`; `remove_imports` (sequential): `base64`
- size (measured in the sim): destination **264** code lines; `_merge_engine.py` after: **5675**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c15-observation.txt` (sim commit `9cb88a8`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c15-before.json --manifest .refactor/merge-engine-observation.json --strict-bodies`
- commit: `refactor(app): move observation methods to _engine_observation.py (tier 1, function shape)`

### c16 — `lock`

- destination: `scripts/forge/forge_cli/app/_engine_lock.py` — the recording common-rebase lock context manager and its release-failure recorder.
- methods (source order): `_record_common_release_failure` (287–323), `_recording_common_lock` (326–884, `contextlib.contextmanager`, 5 nested)
- why this grouping: The bead's `lock` seam. `_record_common_release_failure` is called only by `_recording_common_lock`. The only `contextlib.contextmanager` binding in the class, 559 lines, 5 nested defs with `nonlocal`: placed after fifteen gated precedents. Its six callers use `with self._recording_common_lock(...)`: four are already moved (`refresh` c07, `start_chain` c08, `abort` c11, `cleanup_chain` c14), two are still real methods (`recover`, `finalize`). OVER TARGET by construction (591 measured; the method alone is 546): provisional baseline entry + debt row.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _record_common_release_failure,_recording_common_lock --dest scripts/forge/forge_cli/app/_engine_lock.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-lock.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _record_common_release_failure = _engine_lock._record_common_release_failure
  _recording_common_lock = contextlib.contextmanager(_engine_lock._recording_common_lock)
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from pathlib import Path`; `from typing import Any, Iterator, Mapping`; `from forge_cli import chain_core, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_lock`; `remove_imports` (sequential): `Iterator`
- size (measured in the sim): destination **591** code lines; `_merge_engine.py` after: **5095**
- census: none of the 9 sites; contextmanager probe in §6
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c16-lock.txt` (sim commit `9bb4fca`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c16-before.json --manifest .refactor/merge-engine-lock.json --strict-bodies`
- commit: `refactor(app): move lock methods to _engine_lock.py (tier 1, function shape)`

### c17 — `observation_parse`

- destination: `scripts/forge/forge_cli/app/_engine_observation.py` (**existing module**, created by c15) — (same module as c15) remote-observation parsers and the head-containment helper.
- methods (source order): `_parse_remote_observation` (5593–5621, `staticmethod`), `_parse_fetched_remote_observation` (5624–5661, `staticmethod`), `_head_contained` (5664–5670, `staticmethod`)
- why this grouping: Three staticmethods of the observation seam. `_parse_fetched_remote_observation` is called only by `_run_remote_observation`, which measures 495 alone (c18) and therefore cannot take them; the honest neighbour under the 500 target is the observation-primitives module (264 -> 338 measured). `_parse_remote_observation` has no caller anywhere (Delete-first candidate). `_head_contained` has no caller either but MUST keep existing as a class attribute: census site 9 patches it as a tripwire.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _parse_remote_observation,_parse_fetched_remote_observation,_head_contained --dest scripts/forge/forge_cli/app/_engine_observation.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-observation_parse.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _parse_remote_observation = staticmethod(_engine_observation._parse_remote_observation)
  _parse_fetched_remote_observation = staticmethod(_engine_observation._parse_fetched_remote_observation)
  _head_contained = staticmethod(_engine_observation._head_contained)
  ```
- destination imports NEWLY ADDED by this cluster (manifest `imports[dest]`; the mover merges them into the existing header and reuses the identical `if TYPE_CHECKING:` block): `from pathlib import Path`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: none added (`from . import _engine_observation` already present from c15); `remove_imports` (sequential): none
- size (measured in the sim): destination **338** code lines; `_merge_engine.py` after: **5022**
- census: site 9 `mock.patch.object(CLI.MergeEngine, '_head_contained', side_effect=AssertionError(...))` -> no repoint: patch.object replaces the class attribute (a `staticmethod(...)` binding) and restores the same object (probe 5)
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c17-observation_parse.txt` (sim commit `883604d`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c17-before.json --manifest .refactor/merge-engine-observation_parse.json --strict-bodies`
- commit: `refactor(app): move observation_parse methods to _engine_observation.py (tier 1, function shape)`

### c18 — `observe_remote`

- destination: `scripts/forge/forge_cli/app/_engine_observe_remote.py` — the remote observation run.
- methods (source order): `_run_remote_observation` (5672–6166, 4 nested)
- why this grouping: Singleton hub (fan-in 5, 495 lines, 4 nested defs); 495 measured with its header, i.e. exactly fits alone. Tier-2 candidate.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _run_remote_observation --dest scripts/forge/forge_cli/app/_engine_observe_remote.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-observe_remote.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _run_remote_observation = _engine_observe_remote._run_remote_observation
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_observe_remote`; `remove_imports` (sequential): none
- size (measured in the sim): destination **495** code lines; `_merge_engine.py` after: **4539**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c18-observe_remote.txt` (sim commit `d0178fb`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c18-before.json --manifest .refactor/merge-engine-observe_remote.json --strict-bodies`
- commit: `refactor(app): move observe_remote methods to _engine_observe_remote.py (tier 1, function shape)`

### c19 — `epoch_fetch`

- destination: `scripts/forge/forge_cli/app/_engine_epoch_fetch.py` — epoch start and epoch fetch: sealed plan, begin, fetch argv, fetch-tip resolution, fetch run and locked completion.
- methods (source order): `_sealed_plan` (4318–4332, `staticmethod`), `_begin_epoch` (4334–4393), `_epoch_fetch_argv` (4396–4407, `staticmethod`), `_resolved_epoch_fetch_tip` (4430–4450, `staticmethod`), `_run_epoch_fetch` (4717–4838, 2 nested), `_complete_epoch_fetch_locked` (4840–5052)
- why this grouping: `_epoch_fetch_argv` (static) is called only by `_run_epoch_fetch`; `_resolved_epoch_fetch_tip` (static) only by `_complete_epoch_fetch_locked`; `_run_epoch_fetch` calls `_complete_epoch_fetch_locked`. `_sealed_plan` (static) is called by `_begin_epoch`, `_complete_epoch_fetch_locked` (both here) and `_materialize_rebase_success_locked` (c24). Census-touched: after eighteen gated precedents.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _sealed_plan,_begin_epoch,_epoch_fetch_argv,_resolved_epoch_fetch_tip,_run_epoch_fetch,_complete_epoch_fetch_locked --dest scripts/forge/forge_cli/app/_engine_epoch_fetch.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-epoch_fetch.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _sealed_plan = staticmethod(_engine_epoch_fetch._sealed_plan)
  _begin_epoch = _engine_epoch_fetch._begin_epoch
  _epoch_fetch_argv = staticmethod(_engine_epoch_fetch._epoch_fetch_argv)
  _resolved_epoch_fetch_tip = staticmethod(_engine_epoch_fetch._resolved_epoch_fetch_tip)
  _run_epoch_fetch = _engine_epoch_fetch._run_epoch_fetch
  _complete_epoch_fetch_locked = _engine_epoch_fetch._complete_epoch_fetch_locked
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `import secrets`; `from pathlib import Path`; `from typing import Any, Mapping, Sequence`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.app._candidate_observation import _observe_current_merge_candidate`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode`; `from forge_cli.policy import Policy, sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_epoch_fetch`; `remove_imports` (sequential): `Policy`
- size (measured in the sim): destination **446** code lines; `_merge_engine.py` after: **4109**
- census: sites 4-6 `mock.patch.object(CLI.MergeEngine, '_complete_epoch_fetch_locked', side_effect=...)` x3 -> no repoint: the class attribute is replaced and restored whether it is a def or a binding; callers use `self._complete_epoch_fetch_locked(...)` (probe 1)
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c19-epoch_fetch.txt` (sim commit `b20d693`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c19-before.json --manifest .refactor/merge-engine-epoch_fetch.json --strict-bodies`
- commit: `refactor(app): move epoch_fetch methods to _engine_epoch_fetch.py (tier 1, function shape)`

### c20 — `epoch_ancestry`

- destination: `scripts/forge/forge_cli/app/_engine_epoch_ancestry.py` — carried-successor ancestry proof and the epoch replay context it reads.
- methods (source order): `_epoch_replay_context` (4409–4427), `_run_carried_successor_ancestry` (4452–4715, 2 nested)
- why this grouping: `_run_carried_successor_ancestry` (264 lines, 2 nested defs, tier-2 candidate) is called only by `_complete_epoch_fetch_locked`; `_epoch_replay_context` by it and by `_complete_epoch_fetch_locked`. Split from c19 because 446 + 286 (both measured) > 500.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _epoch_replay_context,_run_carried_successor_ancestry --dest scripts/forge/forge_cli/app/_engine_epoch_ancestry.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-epoch_ancestry.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _epoch_replay_context = _engine_epoch_ancestry._epoch_replay_context
  _run_carried_successor_ancestry = _engine_epoch_ancestry._run_carried_successor_ancestry
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_epoch_ancestry`; `remove_imports` (sequential): none
- size (measured in the sim): destination **286** code lines; `_merge_engine.py` after: **3834**
- census: sites 7-8: unbound read `CLI.MergeEngine._run_carried_successor_ancestry` and `mock.patch.object(..., autospec=True, side_effect=kill_after_result)` -> no repoint: the unbound read returns the moved plain function (first parameter `self`), autospec introspects that function's signature, and the instance call passes `self` (probe 3)
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c20-epoch_ancestry.txt` (sim commit `6927b6e`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c20-before.json --manifest .refactor/merge-engine-epoch_ancestry.json --strict-bodies`
- commit: `refactor(app): move epoch_ancestry methods to _engine_epoch_ancestry.py (tier 1, function shape)`

### c21 — `epoch_rebase`

- destination: `scripts/forge/forge_cli/app/_engine_epoch_rebase.py` — epoch rebase and the integrated-rebase observation it drives.
- methods (source order): `_run_epoch_rebase` (5054–5207, 2 nested), `_restore_integrated_rebase_observation_intent_locked` (7337–7396), `_run_integrated_rebase_observation_locked` (7398–7633, 4 nested)
- why this grouping: `_restore_integrated_rebase_observation_intent_locked` is called by `_run_integrated_rebase_observation_locked` (here) and `_recover_rebase_observation_locked` (c24); `_run_epoch_rebase` is the epoch step that produces the observation (it calls `_recover_rebase_observation_locked`, c24, via `self.`). 449 measured.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _run_epoch_rebase,_restore_integrated_rebase_observation_intent_locked,_run_integrated_rebase_observation_locked --dest scripts/forge/forge_cli/app/_engine_epoch_rebase.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-epoch_rebase.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _run_epoch_rebase = _engine_epoch_rebase._run_epoch_rebase
  _restore_integrated_rebase_observation_intent_locked = _engine_epoch_rebase._restore_integrated_rebase_observation_intent_locked
  _run_integrated_rebase_observation_locked = _engine_epoch_rebase._run_integrated_rebase_observation_locked
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `from pathlib import Path`; `from typing import Any, Mapping, Sequence`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_epoch_rebase`; `remove_imports` (sequential): none
- size (measured in the sim): destination **449** code lines; `_merge_engine.py` after: **3399**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c21-epoch_rebase.txt` (sim commit `e81f466`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c21-before.json --manifest .refactor/merge-engine-epoch_rebase.json --strict-bodies`
- commit: `refactor(app): move epoch_rebase methods to _engine_epoch_rebase.py (tier 1, function shape)`

### c22 — `epoch_suite`

- destination: `scripts/forge/forge_cli/app/_engine_epoch_suite.py` — the epoch gate suite.
- methods (source order): `_run_epoch_suite` (5209–5590, 2 nested)
- why this grouping: Singleton: 382 lines, 2 nested defs, tier-2 candidate; calls `_resolve_gate` (c02), `_admission_from_candidate_observation` (c07), `_run_candidate_observation_locked` (c15) via `self.`.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _run_epoch_suite --dest scripts/forge/forge_cli/app/_engine_epoch_suite.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-epoch_suite.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _run_epoch_suite = _engine_epoch_suite._run_epoch_suite
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `import re`; `import sys`; `from typing import Any, Callable, Mapping`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.app._candidate_observation import _observe_current_merge_candidate`; `from forge_cli.app._mutation_journal import _persist_deferred_mutation_result`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_epoch_suite`; `remove_imports` (sequential): `Callable`, `_persist_deferred_mutation_result`, `re`, `sys`
- size (measured in the sim): destination **392** code lines; `_merge_engine.py` after: **3019**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c22-epoch_suite.txt` (sim commit `0034920`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c22-before.json --manifest .refactor/merge-engine-epoch_suite.json --strict-bodies`
- commit: `refactor(app): move epoch_suite methods to _engine_epoch_suite.py (tier 1, function shape)`

### c23 — `epoch_push`

- destination: `scripts/forge/forge_cli/app/_engine_epoch_push.py` — push classification and the epoch push.
- methods (source order): `_push_classification` (6169–6199, `staticmethod`), `_run_epoch_push` (6307–6519, 2 nested)
- why this grouping: `_push_classification` (staticmethod) is called only by `_run_epoch_push`. Census-touched staticmethod: after twenty-two gated precedents.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _push_classification,_run_epoch_push --dest scripts/forge/forge_cli/app/_engine_epoch_push.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-epoch_push.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _push_classification = staticmethod(_engine_epoch_push._push_classification)
  _run_epoch_push = _engine_epoch_push._run_epoch_push
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.app._candidate_observation import _observe_current_merge_candidate`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, V2ReasonCode`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_epoch_push`; `remove_imports` (sequential): none
- size (measured in the sim): destination **251** code lines; `_merge_engine.py` after: **2780**
- census: sites 1-3: unbound calls `CLI.MergeEngine._push_classification(result, destination)` -> no repoint: `MergeEngine.__dict__['_push_classification']` is `staticmethod(<function>)`, class-level access yields the plain function exactly as the in-class `@staticmethod` did (probe 2)
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c23-epoch_push.txt` (sim commit `70daa11`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c23-before.json --manifest .refactor/merge-engine-epoch_push.json --strict-bodies`
- commit: `refactor(app): move epoch_push methods to _engine_epoch_push.py (tier 1, function shape)`

### c24 — `rebase_recovery`

- destination: `scripts/forge/forge_cli/app/_engine_rebase_recovery.py` — rebase-observation recovery: foreign-git recording, rebase success materialization and the rebase-observation recovery step.
- methods (source order): `_record_foreign_git_locked` (7313–7335), `_materialize_rebase_success_locked` (7635–7750), `_recover_rebase_observation_locked` (7752–7958)
- why this grouping: `_materialize_rebase_success_locked` is called by `_recover_rebase_observation_locked` (here) and `_recover_conflict_locked` (c26). `_record_foreign_git_locked` (23 lines; callers here, c19, c26, `recover`) is the foreign-git recorder of the recovery family. Part of the bead's `recovery` seam, split by size.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _record_foreign_git_locked,_materialize_rebase_success_locked,_recover_rebase_observation_locked --dest scripts/forge/forge_cli/app/_engine_rebase_recovery.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-rebase_recovery.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _record_foreign_git_locked = _engine_rebase_recovery._record_foreign_git_locked
  _materialize_rebase_success_locked = _engine_rebase_recovery._materialize_rebase_success_locked
  _recover_rebase_observation_locked = _engine_rebase_recovery._recover_rebase_observation_locked
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, engine`; `from forge_cli.app._candidate_observation import _observe_current_merge_candidate`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_rebase_recovery`; `remove_imports` (sequential): none
- size (measured in the sim): destination **356** code lines; `_merge_engine.py` after: **2439**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c24-rebase_recovery.txt` (sim commit `61b743c`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c24-before.json --manifest .refactor/merge-engine-rebase_recovery.json --strict-bodies`
- commit: `refactor(app): move rebase_recovery methods to _engine_rebase_recovery.py (tier 1, function shape)`

### c25 — `conflict_observation`

- destination: `scripts/forge/forge_cli/app/_engine_conflict_observation.py` — the conflict observation run.
- methods (source order): `_run_conflict_observation_locked` (7980–8214, 3 nested)
- why this grouping: Singleton: 235 lines, 3 nested defs (tier-2 candidate); callers `_recover_rebase_observation_locked` (c24) and `_recover_conflict_locked` (c26). Not merged with c24 (356 + 240 measured > 500) nor with c15/c17 (338 + 240 measured > 500).
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _run_conflict_observation_locked --dest scripts/forge/forge_cli/app/_engine_conflict_observation.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-conflict_observation.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _run_conflict_observation_locked = _engine_conflict_observation._run_conflict_observation_locked
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `import secrets`; `from pathlib import Path`; `from typing import Any, Mapping, Sequence`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.envelope import FrozenError, Refusal`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_conflict_observation`; `remove_imports` (sequential): `secrets`
- size (measured in the sim): destination **240** code lines; `_merge_engine.py` after: **2211**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c25-conflict_observation.txt` (sim commit `ec92f1f`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c25-before.json --manifest .refactor/merge-engine-conflict_observation.json --strict-bodies`
- commit: `refactor(app): move conflict_observation methods to _engine_conflict_observation.py (tier 1, function shape)`

### c26 — `recover_conflict`

- destination: `scripts/forge/forge_cli/app/_engine_recover_conflict.py` — locked conflict recovery.
- methods (source order): `_recover_conflict_locked` (8216–9058, 11 nested)
- why this grouping: Singleton, the largest method in the class: 843 lines, 11 nested defs. 830 measured: OVER TARGET by construction, under the 1,000 ceiling; provisional baseline entry + debt row; first tier-2 candidate.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _recover_conflict_locked --dest scripts/forge/forge_cli/app/_engine_recover_conflict.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-recover_conflict.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _recover_conflict_locked = _engine_recover_conflict._recover_conflict_locked
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `import os`; `from pathlib import Path`; `from typing import Any, Mapping, Sequence`; `from forge_cli import chain_core, runtime, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode`; `from forge_cli.policy import sha256_bytes`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_recover_conflict`; `remove_imports` (sequential): `os`, `runtime`, `sha256_bytes`
- size (measured in the sim): destination **830** code lines; `_merge_engine.py` after: **1391**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c26-recover_conflict.txt` (sim commit `9ae138d`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c26-before.json --manifest .refactor/merge-engine-recover_conflict.json --strict-bodies`
- commit: `refactor(app): move recover_conflict methods to _engine_recover_conflict.py (tier 1, function shape)`

### c27 — `recover_bootstrap`

- destination: `scripts/forge/forge_cli/app/_engine_recover_bootstrap.py` — recovery of a chain parked in bootstrap classification.
- methods (source order): `_recover_merge_bootstrap_scope_binding` (1524–1581), `_bootstrap_pending_classification_inputs_locked` (9060–9168), `_recover_classifying_bootstrap_v12_locked` (9170–9385, 1 nested), `_recover_classifying_bootstrap_locked` (9387–9401)
- why this grouping: `_recover_classifying_bootstrap_locked` (15 lines) delegates to `_recover_classifying_bootstrap_v12_locked` (216 lines, 1 nested def), which calls `_recover_merge_bootstrap_scope_binding` and `_bootstrap_pending_classification_inputs_locked` (each called only from here).
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _recover_merge_bootstrap_scope_binding,_bootstrap_pending_classification_inputs_locked,_recover_classifying_bootstrap_v12_locked,_recover_classifying_bootstrap_locked --dest scripts/forge/forge_cli/app/_engine_recover_bootstrap.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-recover_bootstrap.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _recover_merge_bootstrap_scope_binding = _engine_recover_bootstrap._recover_merge_bootstrap_scope_binding
  _bootstrap_pending_classification_inputs_locked = _engine_recover_bootstrap._bootstrap_pending_classification_inputs_locked
  _recover_classifying_bootstrap_v12_locked = _engine_recover_bootstrap._recover_classifying_bootstrap_v12_locked
  _recover_classifying_bootstrap_locked = _engine_recover_bootstrap._recover_classifying_bootstrap_locked
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from typing import Any, Mapping`; `from forge_cli import chain_core, engine`; `from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, V2ReasonCode`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_recover_bootstrap`; `remove_imports` (sequential): none
- size (measured in the sim): destination **397** code lines; `_merge_engine.py` after: **1006**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c27-recover_bootstrap.txt` (sim commit `82a8196`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c27-before.json --manifest .refactor/merge-engine-recover_bootstrap.json --strict-bodies`
- commit: `refactor(app): move recover_bootstrap methods to _engine_recover_bootstrap.py (tier 1, function shape)`

### c28 — `recover`

- destination: `scripts/forge/forge_cli/app/_engine_recover.py` — the `recover` verb.
- methods (source order): `recover` (9404–10019)
- why this grouping: Singleton: 616 lines, 26 intra-class callees. 621 measured: OVER TARGET by construction; provisional baseline entry + debt row; tier-2 candidate. By c28 every one of its 26 intra-class callees is a binding except the shell hubs it uses and `_finish_recovered_epoch_locked` (c29, still a real method).
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods recover --dest scripts/forge/forge_cli/app/_engine_recover.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-recover.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  recover = _engine_recover.recover
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from pathlib import Path`; `from typing import Mapping, Sequence`; `from forge_cli import chain_core, engine`; `from forge_cli.app._candidate_observation import _observe_current_merge_candidate`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, V2ReasonCode`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_recover`; `remove_imports` (sequential): `Sequence`
- size (measured in the sim): destination **621** code lines; `_merge_engine.py` after: **396**
- census: none names it; sites 4-8 drive `engine.recover()` with a patched callee -> covered by the focused set
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c28-recover.txt` (sim commit `0300265`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c28-before.json --manifest .refactor/merge-engine-recover.json --strict-bodies`
- commit: `refactor(app): move recover methods to _engine_recover.py (tier 1, function shape)`

### c29 — `finalize`

- destination: `scripts/forge/forge_cli/app/_engine_finalize.py` — the `finalize` verb and the two epoch-closing helpers.
- methods (source order): `_park_integrated_review` (6521–6554), `_finish_recovered_epoch_locked` (7960–7978), `finalize` (10475–10596)
- why this grouping: `_park_integrated_review` is called by `finalize` and `_finish_recovered_epoch_locked`; `_finish_recovered_epoch_locked` (19 lines, caller `recover`) is the recover-side twin of `finalize`'s suite -> observe -> push tail. Last on purpose: of `finalize`'s fourteen intra-class callees, three are shell hubs (`_load`, `_halt`, `_wrong_state`), one is in this cluster, and the other ten are bindings created by earlier clusters.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/app/_merge_engine.py --class MergeEngine --methods _park_integrated_review,_finish_recovered_epoch_locked,finalize --dest scripts/forge/forge_cli/app/_engine_finalize.py --import-root scripts/forge --shape function --annotate-self --format-imports --manifest .refactor/merge-engine-finalize.json`
- apply: same argv + `--apply`
- expected class bindings (from the sim apply; identical to the dry-run diff):
  ```
  _park_integrated_review = _engine_finalize._park_integrated_review
  _finish_recovered_epoch_locked = _engine_finalize._finish_recovered_epoch_locked
  finalize = _engine_finalize.finalize
  ```
- destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, engine`; `from forge_cli.app._candidate_observation import _observe_current_merge_candidate`; `from forge_cli.envelope import Outcome, V2ReasonCode`; `from typing import TYPE_CHECKING`; type-only: `from forge_cli.app._merge_engine import MergeEngine`
- source imports: `from . import _engine_finalize`; `remove_imports` (sequential): `Outcome`, `_observe_current_merge_candidate`, `copy`
- size (measured in the sim): destination **183** code lines; `_merge_engine.py` after: **224**
- census: none -> no repoint
- refusals: none (`DRY RUN: verified; no files written`). mypy delta (sim, vs the P1 baseline 234): **NEW 0 / GONE 0**
- evidence: `.refactor/dryrun-merge-engine-c29-finalize.txt` (sim commit `a0e86fc`)
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/merge-engine-c29-before.json --manifest .refactor/merge-engine-finalize.json --strict-bodies`
- commit: `refactor(app): move finalize methods to _engine_finalize.py (tier 1, function shape)`

### Wave close (after c29; not a cluster)

- **FR-230 subjects.** `scripts/forge/forge_cli/app/_merge_engine.py` is an existing production subject in
  `.forge/evals/tasks/fr230-phase3-4-v2.manifest.json` (line 55, inside the sorted `app/` block, lines 51–56). Add these
  **27** paths to `subjects.production`, keeping the `app/` block sorted, then mint via `REFACTOR_MINT_CMD`
  (`verify.sh --mint`) before the digest tests — **never inside a cluster commit**. Model the edit on
  `.refactor/add_fr230_subjects_engine_verbs.py` (assert the block is sorted, merge, assert no duplicate, show the diff
  before `--write`). I did **not** mint in the sim: mint writes `.forge/evals/**`, `tests/fixtures/fr230-results/**` and
  the byte-pin test, which is neither cheap nor side-effect free.
  ```
  "scripts/forge/forge_cli/app/_engine_abort.py",
  "scripts/forge/forge_cli/app/_engine_bootstrap.py",
  "scripts/forge/forge_cli/app/_engine_cleanup.py",
  "scripts/forge/forge_cli/app/_engine_cleanup_child.py",
  "scripts/forge/forge_cli/app/_engine_conflict_observation.py",
  "scripts/forge/forge_cli/app/_engine_epoch_ancestry.py",
  "scripts/forge/forge_cli/app/_engine_epoch_fetch.py",
  "scripts/forge/forge_cli/app/_engine_epoch_push.py",
  "scripts/forge/forge_cli/app/_engine_epoch_rebase.py",
  "scripts/forge/forge_cli/app/_engine_epoch_suite.py",
  "scripts/forge/forge_cli/app/_engine_final_mode.py",
  "scripts/forge/forge_cli/app/_engine_finalize.py",
  "scripts/forge/forge_cli/app/_engine_gate.py",
  "scripts/forge/forge_cli/app/_engine_lifecycle.py",
  "scripts/forge/forge_cli/app/_engine_lock.py",
  "scripts/forge/forge_cli/app/_engine_observation.py",
  "scripts/forge/forge_cli/app/_engine_observe_remote.py",
  "scripts/forge/forge_cli/app/_engine_rebase_recovery.py",
  "scripts/forge/forge_cli/app/_engine_recover.py",
  "scripts/forge/forge_cli/app/_engine_recover_bootstrap.py",
  "scripts/forge/forge_cli/app/_engine_recover_conflict.py",
  "scripts/forge/forge_cli/app/_engine_refresh.py",
  "scripts/forge/forge_cli/app/_engine_release_aborted.py",
  "scripts/forge/forge_cli/app/_engine_release_pending.py",
  "scripts/forge/forge_cli/app/_engine_review_request.py",
  "scripts/forge/forge_cli/app/_engine_review_verdict.py",
  "scripts/forge/forge_cli/app/_engine_start_chain.py",
  ```
- **Import contract.** `lint-imports` passes **unchanged** at every one of the 29 sim commits and on the final tree
  (`Contracts: 5 kept, 0 broken`): a layers contract ignores unlisted modules, `exclude_type_checking_imports = true`
  is already set session-wide (`pyproject.toml:234`, from session 1), and no `_engine_*` module imports `_merge_engine`
  at runtime or another `_engine_*` (probe 10, AST-based; probe 12 imports each module first in a fresh interpreter).
  Finalize should add one row to `forge_cli.app layers` between `"_merge_engine"` and
  `"_admission | _candidate_observation | _mutation_journal"` (12 of the 27 modules import that bottom row, so the new
  row must sit above it). With `|` the siblings become *enforced* independent. Probed in a separate worktree of the
  final sim tree: `Contracts: 5 kept, 0 broken` (`.refactor/merge-engine-sim-layer-probe.txt`; the exit code was not
  captured there — zsh `pipestatus` — so rely on the Contracts line). Row:
  ```
  "_engine_abort | _engine_bootstrap | _engine_cleanup | _engine_cleanup_child | _engine_conflict_observation | _engine_epoch_ancestry | _engine_epoch_fetch | _engine_epoch_push | _engine_epoch_rebase | _engine_epoch_suite | _engine_final_mode | _engine_finalize | _engine_gate | _engine_lifecycle | _engine_lock | _engine_observation | _engine_observe_remote | _engine_rebase_recovery | _engine_recover | _engine_recover_bootstrap | _engine_recover_conflict | _engine_refresh | _engine_release_aborted | _engine_release_pending | _engine_review_request | _engine_review_verdict | _engine_start_chain",
  ```
- **`pyproject.toml` finalize.** Replace the glob with the 27 measured per-module entries of §5 and delete it; shrink
  the `_merge_engine.py` entry to the measured `["E501", "I001", "UP035"]` (`.refactor/merge-engine-sim-shell-ruff.txt`;
  `E501` stays because 13 binding lines exceed the limit). `UP037` appears in **all 27** entries unless option (C) of
  §0.1 is taken first.
- **`.refactor-baseline.json` finalize.** Delete the `_merge_engine.py` entry (224 < 500); keep the three P2 entries
  at their measured values (they equal the final sizes) until tier 2 shrinks them.
- Spec line 117 (`docs/specs/forge-plugin-spec.md`) says the `app/` modules are "exactly the … production subjects
  listed in" the FR-230 manifest and then enumerates five submodules by role. Adding the 27 subjects keeps the
  "exactly" claim true; whether the role list needs an `_engine_*` clause is a gated `docs/specs/**` decision for
  finalize, not this plan.
- Re-run the seeded inventory and `quality.py` on the final tree for the handover report.

## 5. Quality and debt report

Code lines as `check_file_length.py` counts them, measured on the final sim tree. Function sizes from `quality.py`
(`end_lineno - lineno + 1`, unchanged by relocation). Ruff codes measured with the P0 glob temporarily removed
(`.refactor/merge-engine-sim-final.txt`); their union is exactly the P0 list plus `UP037`.

| module | code lines | vs target 500 / ceiling 1000 | functions over 150 (tier-2 candidates; nested closures marked) | ruff codes tripped with the glob disabled (finalize entry) |
|---|---|---|---|---|
| `_merge_engine.py` (shell) | 224 | under target; **delete its `.refactor-baseline.json` entry at finalize** | — (7 defs, 86 bindings) | `E501`, `I001`, `UP035` (drops 12 of its 15 codes) |
| `_engine_abort.py` | 419 | under target | `abort` 257, `_attempted_release_preconditions_locked` 157 | `B905`, `C901`, `E501`, `PLR0912`, `PLR0915`, `PLR1702`, `UP035`, `UP037` |
| `_engine_bootstrap.py` | 479 | under target | `_run_bootstrap_generation_composite` 412 | `C901`, `PLR0913`, `PLR0915`, `UP035`, `UP037` |
| `_engine_cleanup.py` | 438 | under target | `cleanup_chain` 453 | `C901`, `F841`, `PLR0912`, `PLR0915`, `PLR1702`, `UP035`, `UP037` |
| `_engine_cleanup_child.py` | 311 | under target | `_run_cleanup_child` 167 | `PLR0913`, `UP035`, `UP037` |
| `_engine_conflict_observation.py` | 240 | under target | `_run_conflict_observation_locked` 235 | `B023`, `C901`, `PLR0911`, `PLR0915`, `UP035`, `UP037` |
| `_engine_epoch_ancestry.py` | 286 | under target | `_run_carried_successor_ancestry` 264 | `C901`, `PLR0915`, `UP035`, `UP037` |
| `_engine_epoch_fetch.py` | 446 | under target | `_complete_epoch_fetch_locked` 213 | `C901`, `PLR0912`, `PLR0915`, `UP035`, `UP037` |
| `_engine_epoch_push.py` | 251 | under target | `_run_epoch_push` 213 | `C901`, `E501`, `PLR0915`, `UP035`, `UP037` |
| `_engine_epoch_rebase.py` | 449 | under target | `_run_integrated_rebase_observation_locked` 236, `_run_epoch_rebase` 154 | `C901`, `E501`, `PLR0911`, `PLR0915`, `UP035`, `UP037` |
| `_engine_epoch_suite.py` | 392 | under target | `_run_epoch_suite` 382 | `B023`, `C901`, `E731`, `PLR0912`, `PLR0915`, `PLR1702`, `UP035`, `UP037` |
| `_engine_final_mode.py` | 312 | under target | — | `C901`, `PLR0911`, `PLR0912`, `UP035`, `UP037` |
| `_engine_finalize.py` | 183 | under target | — | `E501`, `UP035`, `UP037` |
| `_engine_gate.py` | 396 | under target | — | `PLR0913`, `UP035`, `UP037` |
| `_engine_lifecycle.py` | 318 | under target | — | `C901`, `E501`, `PLR0912`, `PLR0915`, `UP035`, `UP037` |
| `_engine_lock.py` | 591 | **over target, under ceiling: baseline entry + debt row** | `_recording_common_lock` 559, `lifecycle_classification` 349 (nested) | `C901`, `PLR0912`, `PLR0915`, `UP035`, `UP037` |
| `_engine_observation.py` | 338 | under target | `_run_candidate_observation_locked` 199 | `B023`, `PLR0911`, `PLR0913`, `UP012`, `UP035`, `UP037` |
| `_engine_observe_remote.py` | 495 | under target | `_run_remote_observation` 495 | `B023`, `B905`, `C901`, `PLR0912`, `PLR0913`, `PLR0915`, `PLR1702`, `UP035`, `UP037` |
| `_engine_rebase_recovery.py` | 356 | under target | `_recover_rebase_observation_locked` 207 | `C901`, `PLR0911`, `PLR0912`, `PLR0913`, `PLR0915`, `UP035`, `UP037` |
| `_engine_recover.py` | 621 | **over target, under ceiling: baseline entry + debt row** | `recover` 616 | `C901`, `E501`, `PLR0912`, `PLR0915`, `PLR1702`, `UP035`, `UP037` |
| `_engine_recover_bootstrap.py` | 397 | under target | `_recover_classifying_bootstrap_v12_locked` 216 | `UP035`, `UP037` |
| `_engine_recover_conflict.py` | 830 | **over target, under ceiling: baseline entry + debt row** | `_recover_conflict_locked` 843, `classify_continue_result` 169 (nested) | `B904`, `C901`, `E501`, `F841`, `PLR0911`, `PLR0912`, `PLR0913`, `PLR0915`, `UP035`, `UP037` |
| `_engine_refresh.py` | 291 | under target | — | `F841`, `UP035`, `UP037` |
| `_engine_release_aborted.py` | 321 | under target | — | `UP035`, `UP037` |
| `_engine_release_pending.py` | 277 | under target | — | `C901`, `PLR0912`, `UP035`, `UP037` |
| `_engine_review_request.py` | 231 | under target | — | `UP012`, `UP035`, `UP037` |
| `_engine_review_verdict.py` | 315 | under target | `review_attach` 155, `review_disposition` 154 | `C901`, `E501`, `PLR0912`, `PLR0915`, `UP035`, `UP037` |
| `_engine_start_chain.py` | 454 | under target | `start_chain` 160 | `UP035`, `UP037` |

**Debt rows (modules between target and ceiling)** — proposed file `.refactor/merge-engine-debt-proposed.json`,
accepted by `quality.py` (`tracking` populated for all three):

| module | code lines | reason | follow-up |
|---|---|---|---|
| `_engine_lock.py` | 591 | `_recording_common_lock` alone is 546 code lines (5 nested defs, one of them 349 lines); tier 1 cannot shrink a body | tier 2: this bead's tier-2 checkpoint; tier 3: forge-plugin-g8kf |
| `_engine_recover.py` | 621 | `recover` alone is 612 code lines | same |
| `_engine_recover_conflict.py` | 830 | `_recover_conflict_locked` alone is 820 code lines (11 nested defs) | same; first tier-2 candidate |

**No module exceeds 1,000** (`over_ceiling: false` for all 33 app modules).

**`quality.py` still exits 1 after the wave, and that is expected, not a pass.** Its exit is
`over_ceiling or bool(candidates) or untracked debt` (`quality.py:67`); with the debt file the third term is satisfied,
but 24 functions over the 150-line target remain and relocation cannot shorten them. The skill's wording is
"an extraction candidate, never an accepted final plan": the brief's **tier-2 checkpoint after wave close is
mandatory**, not optional. (Two further candidates, `_admission.prepare_merge_admission` 198 and
`_candidate_observation._observe_current_merge_candidate` 195, pre-date this bead and are not its debt.)

**Functions over 150 lines — tier-2 candidates with their destination module** (22 moved methods plus
nested closures; never in a cluster commit; `extract_ranges.py` against the *destination* module once its cluster is
merged; more than six parameters means re-plan, not a state object):

1. `_engine_recover_conflict._recover_conflict_locked` — 843 lines
2. `_engine_recover.recover` — 616 lines
3. `_engine_lock._recording_common_lock` — 559 lines
4. `_engine_observe_remote._run_remote_observation` — 495 lines
5. `_engine_cleanup.cleanup_chain` — 453 lines
6. `_engine_bootstrap._run_bootstrap_generation_composite` — 412 lines
7. `_engine_epoch_suite._run_epoch_suite` — 382 lines
8. `_engine_lock.lifecycle_classification` — 349 lines (nested closure; `extract_ranges.py --nested` hoist candidate, subject to its no-`nonlocal`-write rule)
9. `_engine_epoch_ancestry._run_carried_successor_ancestry` — 264 lines
10. `_engine_abort.abort` — 257 lines
11. `_engine_epoch_rebase._run_integrated_rebase_observation_locked` — 236 lines
12. `_engine_conflict_observation._run_conflict_observation_locked` — 235 lines
13. `_engine_recover_bootstrap._recover_classifying_bootstrap_v12_locked` — 216 lines
14. `_engine_epoch_push._run_epoch_push` — 213 lines
15. `_engine_epoch_fetch._complete_epoch_fetch_locked` — 213 lines
16. `_engine_rebase_recovery._recover_rebase_observation_locked` — 207 lines
17. `_engine_observation._run_candidate_observation_locked` — 199 lines
18. `_engine_recover_conflict.classify_continue_result` — 169 lines (nested closure; `extract_ranges.py --nested` hoist candidate, subject to its no-`nonlocal`-write rule)
19. `_engine_cleanup_child._run_cleanup_child` — 167 lines
20. `_engine_start_chain.start_chain` — 160 lines
21. `_engine_abort._attempted_release_preconditions_locked` — 157 lines
22. `_engine_review_verdict.review_attach` — 155 lines
23. `_engine_review_verdict.review_disposition` — 154 lines
24. `_engine_epoch_rebase._run_epoch_rebase` — 154 lines

**Over 250 lines:** `_recover_conflict_locked` 843, `recover` 616, `_recording_common_lock` 559, `_run_remote_observation` 495, `cleanup_chain` 453, `_run_bootstrap_generation_composite` 412, `_run_epoch_suite` 382, `lifecycle_classification` 349 (nested), `_run_carried_successor_ancestry` 264, `abort` 257 — that is **9 moved methods**, not the eight the brief mentions
(the ninth and eighth, `abort` 257 and `_run_carried_successor_ancestry` 264, sit just over the line; `_run_integrated_rebase_observation_locked` 236 and `_run_conflict_observation_locked` 235 just under it).

**Class size.** `MergeEngine` has 93 defs today (far over `class_target` 30). After the wave: **7 defs + 86
bindings**. `quality.py` counts only `def` statements in the class body, so the class leaves the candidate list
(sim: `_merge_engine.py` `candidates: []`). Parameter counts are unchanged by relocation; the `PLR0913` findings in §5
are pre-existing and grandfathered.

**Cohesion, stated honestly.** c04 (`lifecycle`) groups four verbs that share only shell hubs and
`_preflight_lifecycle` — seed-forced, hub-only singletons grouped by role, as session 1's `decision` cluster was.
c17 puts the remote-observation parsers beside the *candidate*-observation primitives because their true neighbour
`_run_remote_observation` fills its module alone at 495; the alternative is a fourth over-500 module (568 measured).
Six modules are single-method (c14, c18, c22, c25, c26, c28) and c16 is effectively one: each is one method of 235–843
lines, which is the tier-2 problem showing through, not a seam choice.

## 6. Risks the critic must check

1. **UP037 / P0b (§0.1).** Verify the reproduction (`…-finding-up037-c01-gate.txt`), that the fix is oracle-rejected
   (`…-up037-probe.txt`), and that P0b adds exactly one code. Confirm no `I001` anywhere in the glob or the finalize
   entries (it would silence `--format-imports`). Note the operator rule text says "minus I001" and nothing about
   adding — P0b needs an explicit nod.
2. **Census dispositions are probes, not prose** (`.refactor/merge-engine-sim-final.txt`, 12/12 PASS; tool:
   `merge-engine-sim-tool-probes.py`): (1) `patch.object` round trip on `_complete_epoch_fetch_locked` with the
   side-effect reached through an instance; (2) `_push_classification` is `staticmethod` in the class dict and a plain
   function on class *and* instance access; (3) autospec patch + unbound read of `_run_carried_successor_ancestry`,
   `self` passed, original restored; (4) `_recording_common_lock` is a function whose `__wrapped__` is a generator
   function in `forge_cli.app._engine_lock`, `__name__` preserved, return annotation `Iterator[...]`; (5) the
   `_head_contained` tripwire fires and the same `staticmethod` object is restored; (6) classmethod bound to the class;
   (7) `store`/`__init__` still defined in `_merge_engine`; (8) all 93 names in `MergeEngine.__dict__`; (9) 7 defs + 86
   bindings; (10)/(12) no runtime cycle; (11) `app/__init__.py` byte-identical to `d885f97`, so `__all__` is verbatim.
   `census_complete` is `false` by design (dynamic lookups unresolved); the module has no `getattr(self…)` dispatch.
3. **Reflection metadata changes** (operations.md). `__module__` becomes `forge_cli.app._engine_<x>`; `__qualname__`
   loses the `MergeEngine.` prefix (probe 4 shows `qualname=_recording_common_lock`). Autospec sees the first parameter
   annotated `'MergeEngine'` (a string). Check no focused test asserts on `__qualname__`/`__module__` of these methods
   and nothing pickles them (session-1 Codex review raised pickling; state it in the debt/changelog this time).
4. **Import pruning / external API.** 19 names are pruned from `_merge_engine.py` over 11 clusters (`Callable`,
   `Iterator`, `Outcome`, `Policy`, `Sequence`, `_observe_current_merge_candidate`, `_persist_deferred_mutation_result`,
   `base64`, `copy`, `dataclasses`, `os`, `prepare_merge_admission`, `re`, `runtime`, `secrets`, `sha256_bytes`,
   `socket`, `stat`, `sys`). Through-module readers: **0**. Apart from config, the FR-230 manifest and the spec, the only
   code naming the module path is `app/__init__.py:36` and `app/_dispatch.py:4` (both import only `MergeEngine`) plus the
   27 new `TYPE_CHECKING` imports; there is no string patch target, `sys.modules` lookup or `importlib` call on it. `CLI.<name>` reads resolve
   through `cli.py`'s own imports and the façade, which takes only `MergeEngine` from `_merge_engine`. The 4
   `patch_app`/`patch_engine`/`patch_chain_core` sites naming a pruned name are **excluded by construction**: they patch
   the package root plus every submodule that binds the name via `pkgutil`, never through `_merge_engine`; the new
   modules bind those names by value and are enumerated automatically. Tool: `merge-engine-sim-tool-reader_check.py`.
   -> no cluster takes `--retain-module-api`.
5. **`_PackagePatch` semantics after pruning.** A patched control that `_merge_engine.py` no longer binds is simply
   not patched *there* — correct, since no remaining shell body reads it — and is patched in each `_engine_*` that
   binds it. `tests.test_cli_loader` is in the focused set; it passed on the final sim tree.
6. **Shared destinations (c03 into c01's module, c17 into c15's).** Verified in the sim: identical `TYPE_CHECKING`
   block reused, new imports merged, oracle PASS, size guard PASS. The manifest `baseline` then records the *existing*
   destination's digest, so c03/c17 must be dry-run only after c01/c15 are **committed**.
7. **Type ratchet is keyed by (code, message), not file.** Grandfathered `_merge_engine.py` errors travel with their
   bodies; measured NEW 0 / GONE 0 x29. `--annotate-self` is what prevents the session-1 "lost checks" effect: drop
   the flag on any cluster and GONE goes nonzero. A `import-untyped codex_orchestrator` x3 result means the gate
   environment was not applied — rerun with it; never "fix" it in a cluster commit.
8. **Body-verbatim proof.** `--strict-bodies` + manifest oracle; comments/blank lines are preserved by LibCST but not
   proven by the AST oracle, docstrings are. 16 moved methods carry nested defs (up to 11 in
   `_recover_conflict_locked`), 12 of them with `nonlocal`: they travel inside the unchanged method — check one
   (`cleanup_chain`, 9 nested) by eye in its dry-run diff.
9. **Binding placement.** Bindings land where each `def` was, so the shell interleaves 7 real methods with 86
   bindings, the first four directly after `__init__` with no blank line. Harmless; do not tidy in tier 1.
10. **File-length guard.** `verify.sh` runs the plugin copy of `check_file_length.py`, which reads
    `.refactor-baseline.json` from cwd: run from the repo root. P2 must be committed before c16.
11. **Full-suite state between c01 and the mint.** `_merge_engine.py` is an *existing* FR-230 subject whose bytes change
    in every cluster, so its digest pins (`tests/test_fr223_v2_byte_pins.py`, `tests/test_fr230_phase3_manifest.py`) are
    expected to fail from c01 until the mint — expected from the lead's brief and session-1 precedent; **not run in the
    sim**. No intermediate cluster SHA is a reintegration candidate. The wave-close mint touches `.forge/evals/tasks/**` and
    `tests/fixtures/**` (control class).
12. **What the sim did not do.** It ran `verify.sh --fast` per cluster (no tests) and the focused set **once**, on the
    final tree; it did not mint, did not run full discovery, and did not dry-run in the project tree.

## 7. Test expectations

- Production function shape: **no test-ID mapping, no test snapshot, no `--test-only`**; the test surface is
  untouched and `collect_tests.py` is not part of this wave. No repoint is expected: no tracked test names the
  `_merge_engine` module path, none lists the `app/` directory against the FR-230 manifest, and
  `tests/test_repo_conformance.py` does not mention `forge_cli` (all three checked with grep, not by running them).
  Behaviour tests are never edited.
- Focused set (`REFACTOR_TEST_CMD`): `python3 -m unittest tests.test_cli_merge_adapters tests.test_cli_merge_store
  tests.test_cli_merge_lifecycle tests.test_cli_merge_integration tests.test_cli_merge_integration_shard1
  tests.test_cli_merge_integration_shard2 tests.test_cli_loader`.
  Untouched branch: `Ran 247 tests in 634.215s` / `OK`. **Final sim tree (all 29 clusters):** `Ran 247 tests in 622.450s` / `OK` (exit 0, wall 623 s, sim HEAD `7faa07f`) — test count
  identical to the 247 the untouched branch collects. Log tail: `.refactor/merge-engine-sim-focused.txt`.
- **Per-cluster set (operator decision 3).** At ~10.5 min the full focused set costs ~5 h over 29 clusters. Proposed
  shape, timings unmeasured: a short per-cluster set that always contains `tests.test_cli_loader` plus the merge module
  that drives the verbs just moved, with the full seven-module set at c01 (the operator's inspection cluster), at the
  census-touched clusters c17, c19, c20, c23, at the three over-500 clusters c16, c26, c28, and at wave close. The
  session should time the seven modules individually before fixing the split; I did not, to keep the one permitted
  long run exactly the specified command.
- Digest / byte-pin tests (FR-230 subjects, `test_repo_conformance` inventory) run **only at wave close** after the
  mint; they are expected to fail between c01 and the mint and stay out of the per-cluster command.
- Full unittest discovery (project Gate 1 cell) at wave close and at finalize, twice consecutively after the last fix.

## 8. Operator decisions applied (session, 2026-09-22, after critique `.refactor/critique-merge-engine.md`)

- **§0.1 / critique B1 (UP037):** option A taken as **P0b `e814491`** (config-only, `"UP037"` appended to the
  `app/_engine_*.py` glob). Operator direction differs from §5 at finalize: UP037 is **not** carried into the measured
  per-module entries; instead `ruff check --select UP037 --fix` runs over the new `app/_engine_*.py` modules as one
  mechanical non-move commit before the re-mint and the final gates, listed in the handover next to the prep commits,
  with the delta recorded in the debt report.
- **§4 P2 / critique B2:** taken as **P2 `09f8275`** (config-only): provisional `.refactor-baseline.json` entries
  `_engine_lock.py` 591, `_engine_recover.py` 621, `_engine_recover_conflict.py` 830, plus the matching debt rows in
  `.refactor/merge-engine-debt.json`. At finalize each entry is pinned to its measured size or deleted if tier 2
  brings the module under 500.
- **§7 / critique A12 (per-cluster test set):** per-cluster `REFACTOR_TEST_CMD` =
  `python3 -m unittest tests.test_cli_merge_adapters tests.test_cli_merge_lifecycle tests.test_cli_merge_store tests.test_cli_loader`
  (set by the driver `.refactor/merge-engine-run-cluster.py`). The full seven-module set runs as four parallel
  unittest processes, fail-closed (`.refactor/merge-engine-full-set.sh`, every process exit 0 and a final `OK`):
  at c01 (operator inspection), after every fifth cluster (c05, c10, c15, c20, c25), after every cluster that moves a
  method named in a census or `test_cli_loader` patch site (c16 `_recording_common_lock`, c17 `_head_contained`,
  c19 `_complete_epoch_fetch_locked`, c20 `_run_carried_successor_ancestry`, c23 `_push_classification`,
  c29 `finalize`), at wave close and at finalize. A failing checkpoint is bisected over at most five commits by
  re-running the full set at each. Proven twice on the untouched branch first
  (`.refactor/fullset-merge-engine-baseline.txt`, critique A12).
- **Critique B3:** the four `merge-engine-sim-tool-*.py` helpers were lint-cleaned (wrapping and renames only, no
  behaviour change) before the evidence commit.
- The prep-commit sequence on the branch is therefore P0 `6ee38b6`, P1 `d3946d7`, P0b `e814491`, P2 `09f8275`;
  the CHANGELOG entry (written at P0, "two prep commits") is corrected at finalize (critique A9).
