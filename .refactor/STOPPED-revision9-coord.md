# STOPPED: lane A (session 4, bead forge-plugin-6g67), 2026-09-23 02:25 (relaunched run, started 01:27)

Condition: docs/analysis/refactor-overnight-brief-2026-09-23.md section 8 item 4 (an item that needs a repository
config decision or a second hand-written commit), raised as the plan critic's blocking finding B1
(`.refactor/critique-revision9-coord.md`, verdict REVISE). Section 8 item 5 also applies (a reviewer BLOCK that a
consensus round cannot resolve to advisory with evidence: the finding reproduces).

## The finding

Every class-shape family module the recipe produces (`tests/test_revision9_coordination_<family>.py`, and equally
lane B's `tests/test_revision8_<family>.py` / `tests/test_revision9_cli_surfaces_<family>.py`) gets its header from the
mover with `--format-imports` (isort): the third-party `from codex_orchestrator import batch, builders, journal`
(and `import codex_orch_tools as ORCH_TOOLS`, `from forge_cli import chain_core as CHAIN_CORE`) sorts ABOVE the
first-party `from tests._revision9_coord_constants import ...`. Only the constants module (and the source module)
put `scripts/` on `sys.path`; a family module has no `sys.path` line of its own. So a family module imported first
in a fresh process fails:

```
$ env -u PYTHONPATH python3 -c "import codex_orchestrator"
ModuleNotFoundError: No module named 'codex_orchestrator'
```

The committed Gate 1 cell (forge-project.md) runs `python3 -m unittest tests.<stem> ...` over four round-robin shards
of `sorted(glob("tests/test_*.py"))`, each a fresh process, and unittest imports the listed modules in order.
Simulation of the post-split list (80 modules, 4 shards; `.refactor/STOPPED-revision9-coord.md` command below):

```
shard 1: 20 modules; families 3; first-unbootstrapped-need=None
shard 2: 20 modules; families 3; first-unbootstrapped-need=test_audit_commitments   (pre-existing module; passes today)
shard 3: 20 modules; families 3; first-unbootstrapped-need=test_revision9_coordination_activation_scan
   preceding: ['test_monitor', 'test_repo_conformance', 'test_revision9_archive']
shard 4: 20 modules; families 3; first-unbootstrapped-need=test_revision9_coordination_batch_builder
   preceding: ['test_mutation_runner', 'test_report_skill', 'test_revision9_cli_surfaces']
```

Shards 3 and 4 would import a family module with no bootstrapping module ahead of them: `ModuleNotFoundError`,
shard exit 1, `GATE: FAIL`. That cell runs WITHOUT `PYTHONPATH` in CI (`.github/workflows/forge-ci.yml`, no env
block on the Gate 1 step) and in the Forge merge chain from the main clone (its `.claude/settings.local.json` sets
only `DISCORD_STATE_DIR` and `TMPDIR`). The lane's own gates hide it: `REFACTOR_TEST_CMD`'s discover imports the
source module first (`.` sorts before `_`), which bootstraps the whole process, and `.refactor/gate1-revision9-coord.sh`
exports `PYTHONPATH=scripts:scripts/forge` (copied from the merge-engine session's script). A branch whose every
in-session gate is green but whose merge gate is red must not be handed over with the mechanism filed as a note.

Candidate dispositions, none inside the session's authority (recorded, not applied):

- (a) config-only: `[tool.ruff.lint.isort] known-local-folder = ["codex_orchestrator", "codex_orch_tools", "forge_cli"]`
  in pyproject.toml sinks those imports below the first-party `tests.*` block, so the constants module bootstraps
  first. Measured without editing any file (`ruff check tests scripts --config "lint.isort.known-local-folder = [...]"`):
  exactly one new I001, `tests/test_commitment_paths.py:20` (fixable). It is a repository-wide lint policy change and
  changes every destination header the mover writes, so it must land before c01 (and re-sorts the c00 header if c00
  has landed).
- (b) a `sys.path` bootstrap line per family module: a second hand-written commit beyond the constants module
  (section 8 item 4).
- (c) any other operator ruling (e.g. exporting PYTHONPATH in the Gate 1 cell is a control-file change).

## What passed before the stop

Branch `refactor/split-test-revision9-coordination` at **455e436** (three commits on 69bc28d):
- 40ea8c1 freeze evidence (BASE record, ID snapshot 1908/1908, body snapshot 2906, focused set 144 OK, gate dry run PASS);
- cc0bfd7 temporary ruff globs (config-only prep);
- 455e436 the hand-written constants module `tests/_revision9_coord_constants.py` (ruff clean, focused 144 OK, ID
  identity compare PASS, imports with PYTHONPATH unset).

Mixin attempt 1 (all 38 helpers) verified and applied, then FAILED only the gate's file-length step at 1,623 code
lines (ceiling 1,000); reverted (evidence `*-attempt1.*`). Re-planned per the bead's rule: 18 helpers shared across
families in the mixin (measured 806 code lines by dry run, `.refactor/dryrun-revision9-coord-c00-mixin-measure.txt`),
20 family-private helpers travel with their family; the mover's acceptance of helpers in a class-shape move is
verified (`.refactor/probe-revision9-coord-helper-in-class-dryrun.txt`). Plan: `.refactor/plan-revision9-coord.md`
(12 families, 108 tests, largest 909 code lines, `bound_chain` split into `chain_drain` + `terminal_builder`; the
skipUnless test stays on the source class) with `.refactor/families-revision9-coord.json`; critique:
`.refactor/critique-revision9-coord.md` (everything except B1 verified clean; M1-M4 and A1-A9 applied to the plan
text after the verdict). Driver `.refactor/revision9-coord-cluster.sh`, id-map generator
`.refactor/revision9-coord-idmap.py`, Gate 1 script `.refactor/gate1-revision9-coord.sh` are ready.

The commands and outputs (this run): focused baseline `Ran 144 tests in 17.357s OK` (18 s wall, load 19..26);
gate dry run PASS x6 steps (5 s); mixin attempt-1 gate: PASS compile, ruff-lint, types, import-contracts,
bodies-unchanged, test-identities, tests; FAIL file-length (`tests/_revision9_coord_support.py: 1623 code lines >
budget 1000`).

Shard simulation command (read-only, run from the worktree):

```
python3 - <<'PY'
import glob, json, pathlib, re, os
fam=json.load(open('.refactor/families-revision9-coord.json'))
new=[f"tests/test_revision9_coordination_{n.split('-',1)[1]}.py" for n in fam['order']]
mods=sorted(pathlib.Path(p).stem for p in glob.glob("tests/test_*.py")+new)
shards=max(1,min(4,os.cpu_count() or 1))
groups=[[m for i,m in enumerate(mods) if i%shards==k] for k in range(shards)]
def bootstraps(stem):
    p=pathlib.Path('tests')/f'{stem}.py'
    if not p.exists(): return False
    s=p.read_text()
    return bool(re.search(r'sys\.path\.insert\(0,\s*str\(ROOT\s*/\s*"scripts"\)\)', s)) or 'tests._revision9_coord_constants' in s
def needs(stem):
    p=pathlib.Path('tests')/f'{stem}.py'
    return (not p.exists()) or ('codex_orchestrator' in p.read_text() and not bootstraps(stem))
for k,g in enumerate(groups,1):
    boot=False; fail=None
    for m in g:
        if needs(m) and not boot: fail=m; break
        if bootstraps(m): boot=True
    print(k, len(g), fail)
PY
```

## State left behind

- Branch at 455e436 plus this stop commit (planning evidence, critique, driver, scripts, attempt-1 and probe
  evidence, this file); pushed to origin. Tracked tree clean; no production file, no spec sentence, no mint.
- `git diff --stat 69bc28d..HEAD -- scripts docs/specs .forge` is empty.
- Worktree `forge-plugin-wt/s4` and its `.claude/settings.local.json` left in place; `/dev/shm/refactor-s4` left
  (small; freeze copies only). No nested worktrees, no run branches. Planner and critic agents finished.
- Bead forge-plugin-6g67: comment with this text; not closed. No handover bead created. Beads forge-plugin-25ms and
  forge-plugin-kzu0 (lane B) carry a heads-up comment: the same mechanism applies to their family modules.

## Next step I would have taken (for the relaunch, after the operator rules on B1)

1. If (a): the config-only commit adding the isort setting and the one-line I001 fix in
   `tests/test_commitment_paths.py` (a config-driven mechanical edit, `ruff --fix`), gated by `ruff check tests scripts`
   and the focused set; then the provisional `.refactor-baseline.json` config commit (`tests/_revision9_coord_support.py`
   806 and the ten family entries of plan §6); then c00 through the driver:
   `bash .refactor/revision9-coord-cluster.sh c00-mixin mixin tests/_revision9_coord_support.py Revision9BuilderBatchSupport "$(python3 -c 'import json;print(json.load(open(".refactor/families-revision9-coord.json"))["mixin"]["methods_csv"])')" "refactor(tests): move the 18 shared helpers of Revision9BuilderBatchTests to tests/_revision9_coord_support.py (mixin shape, tier 1)"`
   followed by `env -u PYTHONPATH python3 -m unittest tests.test_revision9_coordination`; then c01..c12 with the
   driver lines in plan §3.x; after c01, one Gate 1 run with the PYTHONPATH export removed from the gate script (the
   critic's second measurement) to prove the disposition; wave close, finalize, reviews, handover per brief §7.
2. If (b): the same, with the operator's bootstrap line added to each family module in the commit the operator
   directs (it is a hand edit of a destination header; the manifest oracle will report it unless it is a separate,
   declared commit).
