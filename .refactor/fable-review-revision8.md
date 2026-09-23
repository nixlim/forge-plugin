# Fable review: revision8 test split (branch refactor/split-test-revision8-coordination, BASE 69bc28d, reviewed tip 97d4d60)

Reviewer: Claude Fable 5.1 (split reviewer, decompose mode), 2026-09-23, worktree
/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s8. Read-only; no file written except this
one. Own check completed before .refactor/codex-review-revision8.md was read.

## Commands run (TMPDIR=/dev/shm/refactor-s8, PYTHONPATH=scripts:scripts/forge unless `env -u`)

| # | Command | Outcome |
|---|---|---|
| 1 | `git diff --stat 69bc28d..HEAD -- scripts docs/specs .forge` | empty: no production diff |
| 2 | `git diff --stat 69bc28d..HEAD -- . ':!.refactor'` | 14 files: 10 under tests/, pyproject.toml, .refactor-baseline.json, CHANGELOG.md, tests/test_migration.py |
| 3 | `git show --stat` for all 25 commits in range | every commit touches only its declared paths (evidence-only, config-only, one mover pair, or the disclosed hand-written/migration edits) |
| 4 | `git show 42980e7 -- tests/test_revision8_coordination.py tests/_revision8_constants.py` | source: ROOT/TOOLS/RECORDED_AT removed + one import added; constants module = the 3 statements verbatim + sys.path bootstrap copy |
| 5 | `git show 4977efc -- tests/test_migration.py` | exactly one line: allowed_prefixes gains ".refactor/" |
| 6 | `git show cc99cc8 / c8cf01a / 5be2e31` | isort known-local-folder (4 packages) / temporary ruff globs / provisional baseline = plan §5 C2 numbers |
| 7 | `snapshot_bodies.py compare .refactor/revision8-finalize-before.json tests` | 2892 before, 2892 after, missing=0 added=0 changed=0 |
| 8 | 8x `git worktree add --detach <record.commit>` -> `snapshot_bodies.py compare <record.snapshot> tests --manifest <record.manifest> --strict` + `collect_tests.py compare <record.test_snapshot> --mode identity|mapping --manifest <record.manifest>` -> `git worktree remove --force` | all 8 (mixin a1defe4 identity; orphan_identity 6099c5a, append_schema c27ca9f, registry_races 872314e, precedence f38b2d4, rollback d3b84bb, interruptions 1e26031, successors 3982972 mapping): `manifest oracle: PASS (tier 1)`, `test IDs and shard memberships: PASS`; artefacts unchanged since their commits |
| 9 | `git diff --quiet <mover-sha> HEAD -- <dest>` for 10 files | all HEAD sources identical to the reviewed mover outputs (shell identical since 3982972; constants since 42980e7) |
| 10 | `+` lines written into the source by each of the 8 mover commits | only import-line rewrites (`journal`-only import at a1defe4, `ROOT`-only at 3982972) and the class-header change |
| 11 | `cat tests/test_revision8_coordination.py`; `scripts/check_file_length.py` on it | 10 code lines, docstring-only shell; `class Revision8CoordinationTests(Revision8Support, unittest.TestCase):` |
| 12 | `grep -n "^class "` across new modules | `class Revision8Support:` + 7x `class Revision8<Family>Tests(Revision8Support, unittest.TestCase):` |
| 13 | `head -22` of each new module | header order `tests._revision8_constants` (where read) -> `tests._revision8_support` -> `codex_orchestrator` in every module; no function-local imports; no `= {}`/`= []`/`Client()`; no `__all__`; sys.path.insert only in constants and the shell |
| 14 | `env -u PYTHONPATH python3 -c 'import tests.<m>'` x 10 modules | all OK |
| 15 | `collect_tests.py snapshot --start tests` at HEAD; union of the 7 id maps applied to .refactor/tests-revision8-before.json | unittest and pytest 1908 -> 1908, 81 mapped, mapped == head: True; settings blocks identical |
| 16 | `python3 -m unittest` on the 7 family modules; on the shell | Ran 81 tests OK (baseline log: 81 OK); shell Ran 0 tests, rc 5 |
| 17 | `ruff check scripts tests system/fr223`; `ruff check --select I ...`; `git ls-files -z "*.py" | xargs -0 python3 scripts/check_file_length.py`; `lint-imports` | all pass (241 files within budget; 5 contracts kept) |
| 18 | census grep for `Revision8CoordinationTests` / `test_revision8_coordination` outside .refactor | pyproject I001 entry, CHANGELOG prose, docs/analysis/*.md, .forge/history/*.md only; zero importers at BASE or HEAD |
| 19 | tails of .refactor/gate1-revision8-wave-close-2.txt, -finalize-run1.txt, -finalize-run2.txt | each 4/4 shards exit 0 OK (447/528/432/501 tests), gate1_rc=0 |
| 20 | Gate-1-partition shard-import simulation, `env -u PYTHONPATH` (75 modules, 4 shards, same round-robin as the cell) | 4/4 rc 0 (shard 3 holds the shell + registry_races) |
| 21 | Codex reproduction probes (listed below) | see CODEX_FINDINGS |

Probe results for command 21:
- sys.path delta after `import tests.test_revision8_coordination` (env -u PYTHONPATH): tip `[scripts, scripts/forge, scripts]`; BASE worktree `[scripts/forge, scripts]`; `scripts/forge` is inserted by scripts/codex_orchestrator/journal.py:28.
- `comm -12 <(ls scripts) <(ls scripts/forge)` -> `__pycache__` only (no shared top-level module name).
- `env -u PYTHONPATH python3 tests/test_revision8_coordination.py` -> ModuleNotFoundError: No module named 'tests', rc 1; BASE blob via runpy with stubbed unittest.main -> "reached unittest.main"; BASE worktree `python3 tests/test_revision9_cli_surfaces.py` -> same ModuleNotFoundError.
- `git grep -l "^from tests\." 69bc28d -- tests | wc -l` -> 31.
- `git grep "from tests.test_revision8_coordination\|import test_revision8_coordination"` at 69bc28d and at HEAD -> no matches.
- grep for `patch("tests.` / `patch.dict(...globals` / `globals()[` over revision8 modules -> empty; patch histogram HEAD: 70 `mock.patch.object(`, 2 `mock.patch.object(journal`, 3 `mock.patch.dict(os.environ`; BASE identical for `.object`.
- `cat -n .refactor/gate1-revision8.sh` -> line 9 exports PYTHONPATH; lines 15-19 echo `gate1_rc=$?` with no exit propagation.
- `env -u PYTHONPATH python3 -m unittest tests.test_revision8_coordination` -> rc 5.
- `git status --short` -> `??` for gate1-revision8-finalize-run1.txt and -run2.txt; wave-close and wave-close-2 tracked.

## Report

```
VERDICT: APPROVE
CODEX_VERDICT: REJECT (confidence high; thread 01a0ce80-5296-7a53-af2c-ec33d7b35173)
BLOCKING:
- none
ADVISORY:
- tests/test_revision8_coordination.py:8 - the shell's own `sys.path.insert(0, ROOT/"scripts")` is redundant after tests/_revision8_constants.py:7 (imported on line 5): importing the shell leaves `scripts` on sys.path twice and ahead of `scripts/forge` (inserted by scripts/codex_orchestrator/journal.py:28). Harmless: no top-level name exists under both `scripts/` and `scripts/forge/`, so no import resolves differently, and a duplicate sys.path entry is a no-op; brief section 4 item 2 mandates both lines; it disappears with the shell (forge-plugin-7pzp). (Codex B1, downgraded.)
- tests/test_revision8_coordination.py:5 and tests/test_revision8_<family>.py - direct script execution (`python3 tests/<file>.py`) fails with `ModuleNotFoundError: tests`, where the baseline file reached `unittest.main()`. This is the `from tests._revision8_...` import form mandated by brief section 11 item 2 (`--import-root "$PWD"`); 31 test files at 69bc28d already import `from tests.` and fail identically; Gate 1 and CI run `python3 -m unittest tests.<module>`; no gate, CI job or skill runs a revision8 file directly; the shell collects 0 tests anyway. Record in the handover. (Codex B2, downgraded.)
- .refactor/gate1-revision8.sh:9,15-19 - the Gate 1 wrapper exports PYTHONPATH and always exits 0 (it only echoes `gate1_rc`). The logs remain auditable (`gate1_rc=0`, per-shard `exit 0 OK`) but do not prove bare-PYTHONPATH import; the per-module standalone proofs (row 14) and the shard-import simulation (row 20) cover that. Evidence tooling only. (Codex A1.)
- .refactor/plan-revision8.md:54 says the empty shell's unittest invocation exits 0; `python3 -m unittest tests.test_revision8_coordination` exits 5 (NO TESTS RAN), as debt-revision8.md already states. Doc nit. (Codex A2.)
- .refactor/gate1-revision8-finalize-run1.txt and -run2.txt are untracked at review time, so 69bc28d..97d4d60 does not contain the two logs attesting its own tip. Expected chicken-and-egg; they must ride in the handover/evidence commit. (Codex A3.)
CODEX_FINDINGS:
- REFUTED (as a behavior change) - B1 "inserts `scripts` twice and reverses import precedence relative to `scripts/forge`" - raw observation reproduced (BASE `[scripts/forge, scripts]`, tip `[scripts, scripts/forge, scripts]`), but `comm -12 <(ls scripts) <(ls scripts/forge)` yields only `__pycache__`: no module name exists under both roots, so the order cannot change which module any import resolves to, and a duplicate entry is a no-op. The copied bootstrap line is the disclosed, brief-mandated deviation. Kept as ADVISORY.
- CONFIRMED (fact), BLOCKING severity disputed -> ADVISORY - B2 "direct execution now fails before reaching unittest.main()" - reproduced: tip rc 1 with ModuleNotFoundError; baseline blob via runpy reached a stubbed unittest.main. Not blocking: the import form is the operator-approved deviation (brief section 11 item 2); 31 sibling test files at BASE already behave the same (verified on tests/test_revision9_cli_surfaces.py at 69bc28d); no gate, CI job, skill or test invokes any tests/test_revision8* file directly.
- REFUTED - B3 "relocated names were not re-exported, breaking imports of TOOLS, RECORDED_AT, batch, journal" - `git grep` at 69bc28d and at HEAD finds zero importers of tests.test_revision8_coordination anywhere; the only non-evidence references are pyproject's I001 entry and prose. A test module's namespace is not a public API, the plan has no re-exports-required list for a test-shape decompose, and package-root re-export rules do not apply to this review per its instructions.
- REFUTED - B4 "rebinding a family constant no longer affects inherited helpers" - the split binding is real but unexercised: no revision8 test patches a module global by string path (grep for `patch("tests.`, `patch.dict(...globals`, `globals()[` is empty); every patch is `mock.patch.object(<shared object>, ...)` (72, same histogram as BASE) or `mock.patch.dict(os.environ, ...)`; RECORDED_AT/TOOLS/ROOT are immutable constants nobody rebinds. Focused 81 OK and 3x Gate 1 4/4 confirm. This is the standard consequence of any mixin decompose that copies imports, not a defect of this split.
- CONFIRMED - A1 gate1-revision8.sh injects PYTHONPATH (line 9) and exits 0 regardless of gate1_rc (lines 15-19; `set -u` only). Evidence tooling; compensated by rows 14 and 20. ADVISORY.
- CONFIRMED - A2 plan section 0.3 "exit 0" vs actual exit 5 for the shell under `python3 -m unittest`. ADVISORY.
- CONFIRMED - A3 the two finalize Gate 1 logs are untracked (`git status --short` shows `??`). ADVISORY.
DISPUTED:
- "tests/_revision8_constants.py:7 and tests/test_revision8_coordination.py:8 - importing the retained module inserts `scripts` twice and reverses import precedence relative to `scripts/forge`; baseline inserted it once (evidence: clean-process probes printed `BASE_PATH_INSERTIONS 1`, `TIP_PATH_INSERTIONS 2`, with paths `[scripts/forge, scripts]` versus `[scripts, scripts/forge, scripts]`)"
- "tests/test_revision8_coordination.py:5 - direct execution now fails before reaching the retained `unittest.main()` because `tests.*` is imported before the repository root is available (evidence: `env -u PYTHONPATH python3 tests/test_revision8_coordination.py` exits 1 with `ModuleNotFoundError`; executing the baseline blob reached a stubbed `unittest.main`)" - fact confirmed; BLOCKING severity disputed
- "tests/test_revision8_coordination.py:5 - relocated names were not re-exported, breaking imports of `TOOLS`, `RECORDED_AT`, `batch`, `journal`, and other prior module symbols (evidence: `from tests.test_revision8_coordination import TOOLS, RECORDED_AT, journal` raises `ImportError`; namespace census shrank from 21 to 6 non-dunder names)"
- "tests/_revision8_support.py:15 and tests/test_revision8_successors.py:12 - the former single globals owner is split across support and family modules; rebinding a family constant no longer affects inherited helpers (evidence: probe reported `BASE_SHARED_GLOBALS True`, with patched helper output, versus `TIP_SHARED_GLOBALS False`, with the helper retaining the original value)"
ALLOWED_CHANGED: none
```
