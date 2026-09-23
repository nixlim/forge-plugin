# Fable review: revision9 cli-surfaces test split (lane B2, bead forge-plugin-kzu0)

Reviewer: Claude Fable 5.1 (refactor-reviewer), independent of the author session. Worktree
`/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s6`, branch `refactor/split-test-revision9-cli-surfaces`.
BASE `69bc28d` (= main). Reviewed tip = HEAD = `ea0698b` (finalize). Every command ran from the s6 worktree with
`TMPDIR=/dev/shm/refactor-s6 PYTHONPATH=scripts:scripts/forge`; the six replays ran in throwaway worktrees
`/dev/shm/refactor-s6/review-<sha7>` (added with `--detach`, removed with `--force`; `git worktree list` is back to
the four lane worktrees). Nothing was written except this file. Own check was completed before the Codex file
(`.refactor/codex-review-revision9-cli.md`, landed 19:28) was read; `.refactor/consensus-revision8.md` (lane B1)
was read after the own check.

## 1. Command table

| # | check | command (from s6) | outcome |
|---|---|---|---|
| 1 | scope | `git diff --stat 69bc28d..HEAD -- . ':!.refactor'` | 12 files: `.refactor-baseline.json`, `CHANGELOG.md`, `pyproject.toml`, `tests/test_migration.py` (+1/-1), the source (-4537/+~10), 7 new `tests/` modules. Nothing else. |
| 2 | no production diff | `git diff --stat 69bc28d..HEAD -- scripts docs/specs .forge \| wc -l` | **0** |
| 3 | finalize changes no body | `snapshot_bodies.py compare .refactor/revision9-cli-finalize-before.json tests` | `2890 before, 2890 after, missing=0 added=0 changed=0`, exit 0. `git show --stat ea0698b`: only `.refactor-baseline.json`, `pyproject.toml`, `CHANGELOG.md` + 7 evidence files under `.refactor/`. |
| 4 | whole-branch body compare vs BASE freeze | `snapshot_bodies.py compare .refactor/before-revision9-cli.json tests` (no manifest) | MISSING = exactly the 77 `Revision9BoundCLIIntegrationTests.*` methods; ADDED = the same 77 under `Revision9CliSupport` (15) / five `Revision9CliSurfaces*Tests` (20/17/10/6/9) + the 6 new class entries; CHANGED = 3: `LegacyRuntimeNameCarveOutTests` and `.test_shipped_files_limit_opencode_to_migration_carve_out` (the 14:10 ruling), `Revision9BoundCLIIntegrationTests` (the `pass` shell). Nothing unexplained. |
| 5 | manifest replay, mixin `ce6eb08` | worktree at sha; `snapshot_bodies.py compare <snap> tests --manifest .refactor/mixin-revision9-cli-mixin.json --strict`; `collect_tests.py compare <ids> --start tests --mode identity --manifest <same>` | `manifest oracle: PASS (tier 1)`; `test IDs and shard memberships: PASS`. Evidence files present in the commit. |
| 6 | replay, dispositions `c424d79` | same, `--mode mapping`, `family-revision9-cli-dispositions.json` | PASS / PASS |
| 7 | replay, start_locks `e31e727` | same, `family-revision9-cli-start_locks.json` | PASS / PASS |
| 8 | replay, replay `e9a0250` | same, `family-revision9-cli-replay.json` | PASS / PASS |
| 9 | replay, multicell_stack `7596909` | same, `family-revision9-cli-multicell_stack.json` | PASS / PASS |
| 10 | replay, ingest `e03515d` | same, `family-revision9-cli-ingest.json` | PASS / PASS |
| 11 | final sources = reviewed mover outputs | `git diff --quiet <sha> HEAD -- <dest>` for ce6eb08/support, c424d79/dispositions, e31e727/start_locks, e9a0250/replay, 7596909/multicell_stack, e03515d/ingest, e03515d/source, b4d3c4f/constants, a30d535/test_migration | **SAME** for all 9 pairs (no post-mover edit to any moved file). |
| 12 | whole-branch test IDs at HEAD | `collect_tests.py snapshot --start tests --out /dev/shm/refactor-s6/ids-head.json`; python: (freeze IDs − 62 idmap keys) ∪ 62 idmap values == HEAD IDs | unittest 1908/1908, pytest 1908/1908, `expected==head: True`, unexpected `[]`, missing `[]`, settings equal, `shards {}` / `pinned` none; 62 old-class IDs at BASE, 0 at HEAD. |
| 13 | class headers | `grep -n '^class '` on the 6 new modules + source | five families `class Revision9CliSurfaces<F>Tests(Revision9CliSupport, CLI_FIXTURE_SUPPORT.ForgeCLIFixture):`; mixin `class Revision9CliSupport:`; source `class Revision9BoundCLIIntegrationTests(Revision9CliSupport, CLI_FIXTURE_SUPPORT.ForgeCLIFixture):` + `pass` (1221..1222), `__main__` guard at 1225 kept. |
| 14 | import blocks (top ~30 lines of each new module) | `awk 'NR<=32'` ×7 + source preamble | every family imports `CLI_FIXTURE_SUPPORT` from `tests._revision9_cli_constants` and `Revision9CliSupport` from `tests._revision9_cli_support`; only stdlib + `tests.*` imports; no function-local imports (grep empty); no module-level state outside the constants module (the verbatim `ROOT/CLI_PATH/ENVELOPE_KEYS/CLI/CORE/RUNTIME/ENGINE/CANDIDATE/CLI_FIXTURE_SUPPORT`); no `sys.path.insert` anywhere in the 3 support/source files (0 at BASE too, so the B1 "duplicated sys.path" class does not arise here); no `__all__`. |
| 15 | bare-PYTHONPATH import proof | `env -u PYTHONPATH python3 -c 'import tests.<m>'` ×8 (7 new + source) | all 8 **IMPORT OK** |
| 16 | loader sweep | `python3 -m unittest tests.test_cli_loader` at HEAD | `Ran 14 tests … OK` |
| 17 | constants commit `b4d3c4f` | `git show b4d3c4f -- tests`; python diff of source lines 24..55 at `b4d3c4f^` vs the constants body (loader import un-wrapped) | body == removed span **verbatim and in order** (only the ruff `I` wrap of the loader import differs); constants header = `from __future__`, `import hashlib`, `from pathlib import Path`; source: 25 lines removed, exactly 1 added (`from tests._revision9_cli_constants import CANDIDATE, CLI, CLI_FIXTURE_SUPPORT, CORE, ENVELOPE_KEYS, ROOT, RUNTIME, key`), the loader import kept. The two `load_script` names are called only in the constants module at HEAD (git grep) as they were only in the source at BASE. |
| 18 | config prep `a30d535` | `git show a30d535 -- pyproject.toml tests .refactor-baseline.json` | exactly: `[tool.ruff.lint.isort] known-local-folder = [...]` (+comment), the two temporary globs, `allowed_prefixes += ".refactor/"`. Isort hunk `+` lines byte-equal to lane B1 `cc99cc8`; migration hunk byte-equal to B1 `4977efc`; `tests/test_migration.py` at HEAD identical to B1 tip `94df0b8`. |
| 19 | C2 `451cf2f` | `git show 451cf2f` | six `.refactor-baseline.json` entries 674/976/578/602/678/812, nothing else. |
| 20 | per-family source import pruning | `git diff <sha>^ <sha> -- source \| grep -E '^[-+](from \|import \|class )'` ×6 | ce6eb08: `+from tests._revision9_cli_support import Revision9CliSupport`, class header gains the mixin; c424d79: `-import datetime`, `-import stat`; e31e727: constants import loses `ROOT`; e9a0250: none; 7596909: none; e03515d: `-import os`, `-import warnings`, loader import loses `patch_chain_core`. **Exactly** plan §3 / decompose-records / review-context item 3. |
| 21 | dead names in the retained preamble | reference counts BASE vs HEAD | `load_script` 3→1, `package_module` 5→1 (dead by the relocation, disclosed; `F401` kept in the measured entry); `ModuleType` 1→1 and `importlib` 1→1 were already dead at BASE (not a mover miss). `ruff --isolated --select F821,F811` on all 8 modules: clean (no undefined name from the pruning). |
| 22 | descriptors / hooks | grep in the mixin | `@contextlib.contextmanager` (`cli_process_context`, :27) and `@staticmethod` (`normalized_journal_records`, :305) preserved; 15 methods; no `setUp/tearDown/setUpClass/environment/state/change/repo/git/events/helpers` defined on the mixin, so MRO order `(mixin, ForgeCLIFixture)` shadows exactly what the subclass shadowed at BASE. |
| 23 | census / reflection callers | `grep -rn Revision9BoundCLIIntegrationTests\|Revision9CliSupport\|test_revision9_cli_surfaces` (excl. .git/.refactor) | class name: 1 code hit (the shell) + CHANGELOG/docs prose; module name: config only (`pyproject.toml`, `.refactor-baseline.json`, `.claude/settings.local.json` pattern) + prose; no importer of the module in any tracked file at BASE or HEAD (`git grep` at both revisions). |
| 24 | finalize measured entries | `python3 -m ruff check` on the 8 modules + `test_migration.py`; CLAUDE.md finish command | `All checks passed!`; `ruff check scripts tests system/fr223` clean; `check_file_length.py` `ok: 239 files within budget`; `lint-imports` `5 kept, 0 broken`. Measured sizes 1229/674/34/966/803/666/588/570 == the baseline entries and the debt report. |
| 25 | Gate 1 logs | grep of the 5 logs | wave-close run 1 at `e03515d` (load 17.6): 2 FAIL in `tests.test_cli_common_lock` and `tests.test_cli_merge_integration` (untouched by the branch: `git diff --stat` = 0 lines); run 2 (load 2.6): 4/4 OK. Finalize at `ea0698b`: run 1 ERROR `test_cli_merge_integration…test_inactive_authorized_attempt_observes_without_starting_an_epoch` (untouched module), runs 2 and 3: 4/4 OK, 1908 tests each; standalone rerun of the 3 flaky tests `OK`. Disclosed in the debt report and review context. |
| 26 | Codex adjudication | see §4 | reproduced B1, A1, A2, A3 |

## 2. Findings

```
VERDICT: APPROVE
CODEX_VERDICT: REJECT (1 BLOCKING, 3 ADVISORY; confidence high)
BLOCKING:
- none. Every hunk outside .refactor/ is a manifest-covered move, a mover import repair, a class-header
  change, the disclosed hand-written verbatim relocation (b4d3c4f), config (a30d535, 451cf2f, ea0698b),
  or the CHANGELOG entry. All six cluster records replay PASS/PASS at their commits; the final sources
  are byte-identical to the mover outputs; IDs are 1908/1908 per collector with exactly the 62 mapped;
  no production diff; the finalize commit changes no body.
ADVISORY:
- .refactor/revision9-cli-run-cluster.py:278 — the driver commits with raw `git commit -q -F -` and
  only the finalize commit ea0698b carries the CHANGELOG entry (Codex B1, facts CONFIRMED, blocking
  classification REFUTED, see §4). This is the lane process the operator's brief prescribes
  (brief §1: lanes run in the Forge-off clone; §6: per-cluster driver "commit only on PASS";
  §1 line 68: "Reintegrate in the order B1, B2, A through the worktree-merge chain from the main
  clone") and is identical to lane B1 (revision8-run-cluster.py:269, 25 intermediate commits without
  an entry, Codex did not raise it there, consensus: no blocking) and to the earlier merge-engine
  lane in this same evidence directory. It changes nothing in the reviewed tree. The orchestrator
  should carry the fact to the operator for the reintegration decision (gated-approval class) rather
  than treat it as a split defect; if the operator wants per-commit changelog compliance on main, a
  `commit skip changelog` record or a squash at reintegration are the remedies, not a re-split.
- tests/test_revision9_cli_surfaces.py:20-22 — the module no longer binds ROOT, CLI_PATH, ENGINE,
  patch_chain_core, datetime, os, stat, warnings (Codex A1, CONFIRMED). No importer exists at BASE or
  HEAD (`git grep` both revisions); `tests` is not a declared package API; lane B1 consensus B3 settled
  the same class ("relocated test-module names have no importer"). Not a behavior change.
- .refactor/gate1-revision9-cli-finalize-run{1,2,3}.txt and -flake-standalone.txt are untracked at
  review time (Codex A2, CONFIRMED). Track them in the review-records commit that follows, as lane B1
  did (its A3). Run 1's single ERROR is in an untouched module and is disclosed.
- .refactor/plan-revision9-cli.md:176 and :179 name `.refactor/mixin-revision9-cli.json`; the driver's
  `paths_for` (line 96-98) writes the label-suffixed `.refactor/mixin-revision9-cli-mixin.json`, which
  is what the record, the commit ce6eb08 and my replay use (same convention as B1's
  `mixin-revision8-mixin.json`). The finalize commit message says "the eight cluster records"; the
  JSON holds six (Codex A3, CONFIRMED). Evidence-text drift only; the records file is the authority
  and it replays clean. Fix the two strings in the records commit.
- review-context item 1 says "load_script/package_module cache in sys.modules so each loaded module
  is still created once": `load_script` (tests/_cli_loader.py:35-44) does not cache — it always
  executes the file and registers it; `load_cached` is the caching variant. The "created once"
  property holds anyway because the two `load_script` calls live only in
  `tests/_revision9_cli_constants.py` (git grep) and Python imports that module once; identical to
  BASE where the same two calls lived only in the source module. Wording precision only.
- tests/test_revision9_cli_surfaces.py keeps `import importlib.util` and `ModuleType` which were
  already dead at BASE (1 reference each = the import line), plus `load_script`/`package_module`
  made dead by b4d3c4f. All covered by the measured `F401` entry; deleting them is a body edit
  outside this lane (plan §5, debt report). No action for this review.
- Gate 1 history: two load-shaped flakes at wave close (load 17.6) and one at finalize run 1, all in
  `tests/test_cli_common_lock` / `tests/test_cli_merge_integration`, untouched by the branch; the
  consecutive passing pair is runs 2 and 3 on ea0698b. Disclosed; the timing-fragility of those two
  modules is pre-existing and not this lane's debt.
CODEX_FINDINGS:
- CONFIRMED (fact) / REFUTED (as blocking) — B1 driver raw `git commit`, 16 applicable commits without
  a same-candidate CHANGELOG entry, no skip recorded. Evidence: .refactor/revision9-cli-run-cluster.py:278
  `subprocess.run(["git", "commit", "-q", "-F", "-"], ...)`; my per-commit census over
  `git rev-list --reverse 69bc28d..HEAD` shows changelog=0 for all 17 commits before ea0698b and
  changelog=1 for ea0698b. Refuting the blocking classification: (a) zero effect on the reviewed tree
  or on behavior; (b) the operator's brief §1/§6 directs Forge-off lanes with driver-issued commits and
  reintegration through the worktree-merge chain from the main clone, whose gates are derived from the
  candidate range `REVIEWED_BASE...CANDIDATE_HEAD` (skills/worktree-merge/SKILL.md:95-108), not per
  intermediate commit; (c) the plan (§5 C2 paragraph) and CHANGELOG disclose that the lane's single
  entry lands at finalize; (d) the same pattern on lane B1 (revision8-run-cluster.py:269; 25 entry-less
  commits) was reviewed by Codex today without this finding and closed with no blocking in
  consensus-revision8.md. The authority question belongs to the operator at reintegration.
- CONFIRMED — A1 source module no longer exposes ROOT, CLI_PATH, ENGINE, patch_chain_core, datetime, os,
  stat, warnings. Evidence: `env -u PYTHONPATH python3 -c 'from tests.test_revision9_cli_surfaces import
  ROOT'` fails at HEAD for all eight names; `git grep` at 69bc28d and HEAD finds no importer of the module
  in any tracked .py/.sh/.toml/.json. Advisory, as Codex classified it.
- CONFIRMED — A2 finalize Gate 1 logs untracked. Evidence: `git status --short .refactor | grep gate1`
  lists `?? gate1-revision9-cli-finalize-run1/2/3.txt` and `-flake-standalone.txt`; runs 2 and 3 read
  `head=ea0698b`, 4/4 shards OK, 426+671+409+402 = 1908 tests. Advisory; tracked by the records commit.
- CONFIRMED — A3 plan :176/:179 name `mixin-revision9-cli.json`, the tree has only
  `mixin-revision9-cli-mixin.json` (`ls .refactor | grep ^mixin-revision9`); finalize message line 10
  says "the eight cluster records", `decompose-records-revision9-cli.json` has 6 objects. Advisory.
DISPUTED:
- ".refactor/revision9-cli-run-cluster.py:278 — The new driver invokes raw `git commit`, bypassing the
  mandatory Forge commit chain. Its six move commits—and ten other intermediate candidates—touch
  Python/config/JSON without the same-candidate changelog entry required by `forge-project.md:149`; no
  skip is recorded, so the fail-closed history is invalid. (evidence: `git rev-list --reverse
  69bc28d..e03515d` plus `git diff-tree --no-commit-id --name-only -r <sha>` found 16 applicable commits
  and none containing `CHANGELOG.md`)" — facts agreed; disputed as BLOCKING for the reasons in
  CODEX_FINDINGS (brief-prescribed lane process, candidate-range merge gates, B1 precedent, no tree or
  behavior effect); disposition is the operator's at reintegration.
ALLOWED_CHANGED: LegacyRuntimeNameCarveOutTests, LegacyRuntimeNameCarveOutTests.test_shipped_files_limit_opencode_to_migration_carve_out, Revision9BoundCLIIntegrationTests
```

## 3. What I did not find (checked explicitly)

- No mixed-tier commit: every mover manifest replays `PASS (tier 1)`; no tier-3 change anywhere.
- No class-wide waiver: the finalize `pyproject.toml` entries are per-module measured lists (the two
  temporary globs are gone), and the six size-baseline entries are the measured sizes.
- No debt without reason/follow-up: every over-target module in `.refactor/debt-revision9-cli.md` carries a
  reason and forge-plugin-by61; the four >150-line functions are moved/retained verbatim.
- No import cycle, no function-local import, no duplicated module-level state, no import-time side
  effect added: the only side effects (`load_script`/`package_module` calls) moved verbatim and in order
  from the source preamble into the constants module, executed once by Python's import cache, exactly as
  at BASE.
- No hand edit after the mover: all nine `git diff --quiet <commit> HEAD -- <file>` pairs are SAME.
- No reflection/registry caller of the class or module: census 0 code sites besides the shell line.

## 4. Codex adjudication notes

Codex's CHECKED items 1-6 agree with my independent measurements (77 methods placed once and partitioned
15/20/17/10/6/9; bodies and descriptors identical; single shared identity of CLI/fixture/constants; no
cycle; 1908 IDs per collector with 62 injective mappings; six manifests replayed; ruff, default-500 guard,
five import contracts pass; no production file changed). The sole divergence is the classification of the
commit-chain finding, recorded under DISPUTED for the consensus round.
