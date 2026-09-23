# Critique: `.refactor/plan-revision9-coord.md` (decompose mode, class shape, lane A / bead forge-plugin-6g67)

Critic: plan-critic (Opus 5), 2026-09-23, branch `refactor/split-test-revision9-coordination` @ 455e436.
Inputs: the plan and `.refactor/families-revision9-coord.json`; inventories
`inventory-revision9-coord-builder{,-sizes}.json`; `tests-revision9-coord-1.json`;
`revision9-coord-cluster.sh`, `revision9-coord-idmap.py`, `gate1-revision9-coord.sh`;
attempt-1 evidence `dryrun-/gate-revision9-coord-c00-mixin-attempt1.txt`; the mover, `verify.sh`,
`collect_tests.py`; brief 2026-09-23 §4/§5/§8/§11. No test run, no `--apply`, no dry run executed.

**VERDICT: REVISE** — one blocking item (B1) that needs an operator disposition before c01, one
major evidence gap (M1) that is free to close now, and three plan-text contradictions (M2–M4)
that would read as "unexpected deviation" (a stop trigger) at dry-run inspection time.

---

## Verified clean (recomputed independently; do not re-litigate)

| check | result |
|---|---|
| Completeness | 147 inventory methods = 109 tests + 38 helpers; every symbol placed exactly once; 108 tests in 12 families, 1 (`test_run_open_process_death_keeps_staging_invisible_and_retryable`) unplaced (the `skipUnless` refusal), 18 helpers mixin + 20 family-private; 0 duplicates, 0 orphans. |
| Helper allocation | transitive closure over `calls` (methods only): every family-private helper's transitive test users lie in exactly its own family (0 exceptions); no mixin helper calls a non-mixin method (0); every non-`setUp` mixin helper is reached by tests of ≥2 families; `setUp` is the only helper with 0 test users. |
| Order / refusal safety | the mover's class-shape check is `calls ∩ (remaining class methods)` (move_methods.py:326). For all 12 families the moved set's **transitive** closure contains no method outside the csv ∪ mixin ⇒ no `sibling class would lose calls to remaining methods` at any turn. No method is referenced without being called (0 non-call `reads` of a sibling method), no name mangling, no `getattr/setattr(self`, no `self.__class__`/`type(self)`/`__qualname__` in the class; the only string literal equal to a method name is `mock.patch.object(journal, "open_run", …)` at HEAD L7214 — a module attribute, not the class method. |
| skipUnless test | closure = `_new_repo`, `api_environment`, `run_dir` — all three on the mixin ⇒ the retained shell inherits everything it needs. |
| Id maps | generator spelling matches the freeze exactly: all 108 old unittest IDs (`test_revision9_coordination.Revision9BuilderBatchTests.<t>`) and all 108 old pytest IDs (`tests/test_revision9_coordination.py::…`) are members of `tests-revision9-coord-1.json`; 108 distinct new IDs per collector, no collision with any existing ID; `settings.pinned` and `shards` empty (nothing to preserve); focused unittest set = 144 before, 144 after (mixin module is not discovered, family stems are). Generator filters non-`test_` names, so private helpers never enter a map. `compare` (collect_tests.py:95-118) enforces injectivity + multiset equality. |
| Naming | mixin module `tests/_revision9_coord_support.py` matches no discovery pattern and `Revision9BuilderBatchSupport` matches no `Test*` class pattern (`validate_support`); 12 family stems match `test_revision9_coordination*.py` (REFACTOR_TEST_CMD), `tests/test_revision9_coordination_*.py` (ruff glob, pyproject:246) and `tests/test_*.py` (Gate 1); all 12 class names end in `Tests`, are pairwise distinct and appear nowhere in `tests/` or `scripts/`. |
| Bases | `move_methods.py:405-407` copies `source_class.bases` verbatim for class shape ⇒ after c00 every sibling is `(Revision9BuilderBatchSupport, unittest.TestCase)`, exactly as planned. One mixin, no production base class. |
| Headers | destination import sets equal the computed global sets for all 12 families and the mixin (exact match, no missing, no extra), except A1 below. Mixin globals recomputed = plan's list verbatim. |
| Import-removal schedule (§5) | recomputed last-reader per imported name from the per-method `globals` × placement × execution order, plus readers outside the class: **all 16 rows match**, and no other source import becomes unused (`dt`, `hashlib`, `shutil`, `subprocess`, `sys`, `tempfile`, `copy`, `Path`, `json`, `mock`, `batch`, `builders`, `journal`, `key`, `ROOT`, `unittest` keep readers). No name with a `# noqa: E402` loses only part of its statement (all three aliased ones leave whole), so no noqa comment is orphaned. |
| Sizes | csv line sums reproduce the plan exactly (decorator lines included: mixin 788+3=791, activation_scan 597+2=599, total 7,467+2=7,469). Largest family estimate 909 (`legacy_activation`; header-exact recompute 896); **0 modules ≥1,000**. The estimate method is calibrated: attempt 1 predicted 1,599 helper lines + 24 header = measured 1,623 exactly (`gate-…-attempt1.txt`). Provisional baseline values (§6) all exceed their estimates by ≥40. `cli_diagnostics` 240 and `chain_drain` 436 under target — reasons given and the `chain_drain`+`terminal_builder` merge arithmetic checks out (414+643+header ≈ 1,079 > 1,000). |
| Clusters | per-family "inventory clusters merged" column reproduces exactly from `clusters` for all 12 rows. |
| Quality limits | `.refactor-quality.json` class_target 30: largest family class 14 methods, mixin 18; max_parameters 6: no test takes parameters; function_target 150 exceedances (5) are named and left unchanged. |
| Scope | tier 1 relocation only; one destination per commit; no rename, no body/docstring/decorator edit, no `__all__`, no production path (driver enforces `git diff --stat HEAD -- scripts docs/specs .forge` empty); §2b helper table's 38 "test users" counts all reproduce. |

---

## BLOCKING

**B1. R2 is not a handover note: the split makes the project's own Gate 1 cell fail outside this
worktree, and the lane's gate script hides it.**

Facts, each verified:

1. `--format-imports` (isort) puts the third-party `from codex_orchestrator import …` **above** the
   first-party `from tests._revision9_coord_constants import …`. Evidence: the c00 attempt-1 dry
   run, `dryrun-revision9-coord-c00-mixin-attempt1.txt:1791-1816` (destination header order).
2. `scripts/` is on `sys.path` only because some module ran
   `sys.path.insert(0, str(ROOT / "scripts"))`. `env -u PYTHONPATH python3 -c "import
   codex_orchestrator"` → `ModuleNotFoundError`. Exactly four test modules bootstrap it today
   (`test_commitment_paths`, `test_revision8_coordination`, `test_run_coordination`,
   `test_revision9_coordination`); `tests/_cli_loader.py` inserts `scripts/forge` only, and only
   when `package_module()` is called. `tests/_revision9_coord_constants.py` does bootstrap — which
   is why **c00 is safe** (the source imports the constants module before the support module) and
   why every *family* module is not (its first non-stdlib import is `codex_orchestrator`).
3. The committed Gate 1 cell (`forge-project.md`) runs `python3 -m unittest tests.<stem> …` over
   `min(4, cpu)` round-robin shards of `sorted(glob("tests/test_*.py"))`. Simulating the
   post-split module list (80 modules, 4 shards): shard 0 gets `test_revision9_coordination`
   before its first family; shard 1 is saved by `test_revision8_coordination` (which lane B1 is
   splitting tonight — that accident disappears); **shards 2 and 3 import
   `test_revision9_coordination_activation_scan` / `…_batch_builder` with no bootstrapper ahead of
   them** ⇒ `ModuleNotFoundError: codex_orchestrator` ⇒ shard exit 1 ⇒ `GATE: FAIL`.
4. That cell is run **without PYTHONPATH** by CI (`.github/workflows/forge-ci.yml`, no env block;
   the wrapper's `sys.path.insert` lives in the wrapper process, not the `bash -c` child) and by
   the Forge merge chain in the main clone, whose `.claude/settings.local.json` sets only
   `DISCORD_STATE_DIR` and `TMPDIR` — no PYTHONPATH.
5. This session will not see it: `.refactor/gate1-revision9-coord.sh:6` exports
   `PYTHONPATH=scripts:scripts/forge`, and `REFACTOR_TEST_CMD`'s `discover -p
   'test_revision9_coordination*.py'` imports the source module first (`.` < `_`), which
   bootstraps the path for the whole process. So every in-session gate is green on a branch whose
   merge gate is red. Under the Forge spine that is a gate passing because the environment was
   strengthened — it must not be carried to a handover as an advisory line.

The plan's R2 (§9, line 704) states the mechanism but rules it "expected, not a defect of the
move … record it in the handover, do not apply it mid-wave". That disposition is wrong for
(3)/(4): the defect is not "a family module cannot be imported standalone", it is "the
repository's test gate fails on main".

Required before c01 (c00 may proceed; it is safe):

- Reclassify R2 as a brief §8 item-4 condition (it needs either a repo config decision or a
  control-file change — neither is inside the session's authority) and **escalate to the operator
  with these two measurements attached**, rather than deciding it in-lane:
  - `env -u PYTHONPATH python3 -m unittest tests.test_revision9_coordination_cli_diagnostics`
    (predicted: `ModuleNotFoundError`), and
  - one run of `.refactor/gate1-revision9-coord.sh` with the PYTHONPATH export removed, at the
    post-c01 tip.
- Record, without applying, the three candidate dispositions so the operator can rule in one pass:
  (a) **config-only, cheapest**: `[tool.ruff.lint.isort] known-local-folder = ["codex_orchestrator",
  "codex_orch_tools", "forge_cli"]`, which sinks those imports below the first-party `tests.*`
  block so the constants module bootstraps first. Measured cost of the whole-repo re-sort:
  `ruff check tests scripts --select I001 --config "lint.isort.known-local-folder=[…]"` reports
  **exactly one** new finding, `tests/test_commitment_paths.py:20`. It is still a repo-wide lint
  policy change and it changes what every destination header looks like ⇒ operator call, and it
  must land **before c01** (it changes the headers the mover writes).
  (b) a `sys.path` bootstrap line per family module — a hand-written commit beyond the constants
  module ⇒ brief §8 item 4 stop.
  (c) a PYTHONPATH export in the Gate 1 cell / CI ⇒ control-class change ⇒ stop.
- If the operator cannot be reached: stop at c00 per brief §8 item 4 with
  `.refactor/STOPPED-revision9-coord.md` carrying the two measurements. A wave that lands 12
  modules and red-lights main's Gate 1 is worse than a wave that lands one mixin.

---

## MAJOR

**M1. The re-planned c00 has no dry run; attempt 1 verified a different method set.** Every later
family depends on c00's exact method list (the plan's own R18), on its header, and on
`remove_imports[source] == ["TOOLS"]`, and the §6 mixin baseline value is a guess (860) when the
measurement is free: mixin-shape dry runs are **not** refused pre-c00 (attempt 1 ran one), they
write nothing, and the plan itself says the measurement "is available now" (§6). Before the
config-only commit, run the §2b argv as a dry run and record:
`imports[dest]` (expect the 16 globals + `contextmanager` + `Revision9BuilderBatchSupport`-free
header), `remove_imports[source] == ["TOOLS"]` (attempt 1 also removed `PREFIX_WEDGE_*` /
`UNREPLAYABLE_CHAIN_FIXTURE*`; with 18 helpers they must stay), and the `+++
tests/_revision9_coord_support.py` code-line count (predicted 791 + ~22 = ~813). Put the measured
number in `.refactor-baseline.json` instead of 860. A manifest-verified c00 is also what licenses
the declared test-mixin base at all.

**M2. §9 R3/R4 contradict §5 and §3 on three aliased imports.** R3 assigns `CHAIN_CORE` and
`threading` to **c08** and `patch_chain_core` to **c10**; R4 assigns the `CHAIN_CORE` destination
header to **c08** and `patch_chain_core` to **c09/c10**. The correct, independently recomputed
schedule is §5's: `CHAIN_CORE` + `threading` are read only by `receipted_chain` ⇒ destination and
source removal at **c09**; `patch_chain_core` is read by `activation_scan` (c10) and
`activation_outbox` (c11) ⇒ destination header in both, source removal at **c11**. R3/R4 are the
lines the operator is told to check the dry-run diff against; as written they would report a
false deviation, which is a stop trigger. Fix the two risk rows to match §5.

**M3. Stale family name `bound_chain` in two places.** §9 R11: "The largest, `bound_chain`, is
916 (fallback split stated in its section)" — no such family exists in §3.1/§10, no section states
a fallback split, and the largest estimate is 909 (`legacy_activation`). §8 cohesion: "abort
disposition shape -> bound_chain" — `test_terminal_abort_disposition_fails_closed_on_shape` is in
c07 `terminal_builder`. Delete the stale name and restate R11 against the real maximum (909,
`legacy_activation`, provisional entry 950).

**M4. §6's heading and body disagree about when the config-only baseline commit lands, and the
stated reason is wrong.** Heading: "before **c01**"; body: "The mixin entry is needed **before
c00** (attempt 1 failed exactly here)". Attempt 1 failed at 1,623 > **1,000** (the gate ceiling),
not at a missing baseline entry — at ~813 the mixin passes both in-session checks with
`REFACTOR_MAX_LINES=1000` (verified present in this session's env). The entry is nevertheless
required, for a different reason the plan should state: `scripts/check_file_length.py` defaults to
**500** when `REFACTOR_MAX_LINES` is unset, and `.pre-commit-config.yaml` invokes it with only
`--baseline .refactor-baseline.json` — so on main every new module over 500 without an entry fails
the repository guard. Land the config-only commit **before c00** (it is free) and say why.

---

## MINOR / advisory

- **A1.** `activation_scan`'s expected header omits `from contextlib import contextmanager`. Its
  private helper `_guard_activation_artifact_read_budget` is `@contextmanager`-decorated, and
  `dependency_imports(..., include_decorators=shape != 'function')` (move_methods.py:84-101, 349)
  pulls decorator names into the destination imports. No size or schedule impact (it joins the
  existing `from contextlib import nullcontext, redirect_stderr` line; `contextmanager`'s last
  *body* reader is still c11), but the dry-run diff will not match the plan's line list.
- **A2.** §2b: the mixin's 791 includes **3** decorator lines (`api_environment`,
  `_activation_markers`, `_run_file_bytes`), not 5; the other two decorated helpers
  (`_pad_valid_json_over_cap`, `_guard_activation_artifact_read_budget`) are activation_scan's
  (597+2=599). Arithmetic elsewhere is right; only the sentence is wrong.
- **A3.** R10: "after **c11** the class body is that single test" — the last family is c12.
- **A4.** §5 prose claims `os` "keeps readers in the other three classes or the preamble".
  Recomputed: `os` has **no** reader outside `Revision9BuilderBatchTests`; it survives only
  because the `skipUnless` test stays (decorator `hasattr(os, "fork")` + body). The schedule is
  unaffected (`os` is never removed), but if that test ever moves, `import os` becomes F401.
- **A5.** §8 names the debt file `.refactor/revision9-coord-debt.json`; brief §7 spells
  `.refactor/debt-<name>.json` (`debt-revision9-coord.json`). Pick the brief's.
- **A6.** §6: "dry-run all **11** families" — there are 12 families (11 baseline entries = mixin +
  10 families over 500).
- **A7.** Driver hygiene (`.refactor/revision9-coord-cluster.sh`): it exports only
  `TMPDIR/PYTHONPATH/MYPYPATH` and inherits `REFACTOR_MAX_LINES` / `REFACTOR_TEST_CMD` from the
  session env. Re-run from a plain shell, `verify.sh` would silently fall back to budget 500 and
  to `pytest -q -x` over the whole repo. Export both explicitly. Also `git add` the per-cluster
  driver log and `.refactor/decompose-records-revision9-coord.json` (brief §3: evidence is tracked
  under `.refactor/`), and note that each cluster commits ~1 MB of snapshots (448 KB IDs + 613 KB
  bodies) — ~14 MB over the wave.
- **A8.** Destination modules get no `if __name__ == "__main__": unittest.main()` (the mover never
  emits one; move_methods.py:405-410), unlike every existing test module in `tests/`. Harmless for
  both collectors; worth one line in the handover so the finalize reviewer does not read it as a
  loss.
- **A9.** Rerun-order note for the executor: `moved.sort(key=methods.index)` (move_methods.py:398)
  means the sibling class is written in **csv order**, and every csv is in source order (verified
  for all 12 + the mixin) — so "source order" in §3 is accurate, and re-ordering a csv would
  silently re-order the module.

---

## Addendum, 02:15 — re-read after the planner's 01:58:31 consistency pass, plus the c00 measurement

Both files were re-read at their current state (`plan-revision9-coord.md` md5 968b4514…,
`families-revision9-coord.json` md5 ee9a3378…, both mtime 01:58:31); every check above was run
against those bytes, and the current JSON's `mixin_methods_csv`, per-family `private_helpers`,
source-ordered `methods_csv` and `allocation` map are the ones verified. **No finding changes**
— M2 (R3/R4 still say c08/c10), M3 (`bound_chain` still in R11 and §8), M4 (§6 heading vs body),
A2 ("5 decorator lines", §2b line 77), A3 (R10 "after c11"), A4, A5, A6 are all still present in
the current text.

**M1 is CLOSED by `.refactor/dryrun-revision9-coord-c00-mixin-measure.txt`.** Independently
checked, not taken on trust:

- `DRY RUN: verified; no files written`; 18 `def`s leave the source class; source header becomes
  `class Revision9BuilderBatchTests(Revision9BuilderBatchSupport, unittest.TestCase)`; the support
  import is inserted before the source's `sys.path.insert`.
- `remove_imports[source] == ["TOOLS"]` — exactly the §2b prediction, and none of attempt 1's
  four fixture constants.
- `imports[dest]` == the §2b predicted header to the name: `base64, copy, io, json, os,
  subprocess, sys, tempfile`, `from contextlib import contextmanager, redirect_stderr`, `Path`,
  `mock`, `from codex_orchestrator import batch, builders, journal`,
  `from tests._revision9_coord_constants import TOOLS, key`. No `hashlib`, no `shutil` (their
  readers are family-private) — the allocation's most load-bearing prediction, confirmed.
- Destination hunk: 851 emitted lines, **806 code lines** = 791 helper lines + 15 header lines
  (14 import statements + the class line). The `+22` header rule used across §3.1 is therefore
  conservative by 5–13 lines per module, not optimistic.

**Answer on the §6 mixin entry: yes — put it at the measured 806, not 860.** 860 is 54 lines of
ceiling headroom with no evidence behind it, which is exactly the untracked-debt shape a critique
should reject; the support module is written once at c00 and no later family move touches it (a
family move rewrites only the source and its own destination), so 806 is stable for the whole
wave and `check_file_length` only fails on `n > allowed`. Two conditions: (i) re-measure if
B1's disposition changes destination headers (disposition (a), the isort `known-local-folder`
change, re-orders but does not add lines ⇒ still 806; disposition (b), a bootstrap line per
module, would add 2–3 ⇒ 806 would fail and the entry must be re-measured after that commit);
(ii) finalize still re-measures shrink-only, per brief §7.

**Same argument for the ten family entries (advisory, now that the header model is calibrated
exactly by c00).** Predicted exact sizes (code lines + isort header at `line-length = 100`,
wrapping the one over-long constants import in `activation_scan` into 6 lines):

| module | exact prediction | §6 provisional | headroom |
|---|---|---|---|
| `_revision9_coord_support.py` | **806 (measured)** | 860 | 54 |
| batch_builder | 576 | 630 | 54 |
| scope_change | 521 | 580 | 59 |
| gap_repair | 759 | 820 | 61 |
| staging_crashes | 536 | 590 | 54 |
| terminal_builder | 655 | 710 | 55 |
| legacy_activation | 896 | 950 | 54 |
| receipted_chain | 799 | 850 | 51 |
| activation_scan | 617 (+1 if `contextmanager` needs its own line: it does not, 66 chars) | 670 | 53 |
| activation_outbox | 789 | 850 | 61 |
| ledger_recovery | 810 | 870 | 60 |
| (no entry) cli_diagnostics 230, chain_drain 423 | — | — | under 500 |

The plan's own "Preferred" path (§6: dry-run all families in one pass after c00 and commit the
measured values) is better than either list and costs nothing — take it, and drop the
+40-and-round rule from the text so the record shows measurements, not margins.
