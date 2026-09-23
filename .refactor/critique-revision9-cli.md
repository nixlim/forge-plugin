# Plan critique: `.refactor/plan-revision9-cli.md` / `.refactor/plan-revision9-cli.json`

Target: `Revision9BoundCLIIntegrationTests` in `tests/test_revision9_cli_surfaces.py` (lane B2,
bead forge-plugin-kzu0). Reviewed at worktree `s6`, branch `refactor/split-test-revision9-cli-surfaces`
tip `eacf52c` (plan commit), source at the post-constants head. Every command below was run from
`/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s6` with `TMPDIR=/dev/shm/refactor-s6`;
nothing outside `.refactor/critique-revision9-cli.md` was written (the mover simulations ran
entirely in memory and into `/dev/shm/refactor-s6/sim*`).

VERDICT: REVISE

One blocking finding, and it is a documentation/expectation fix, not a design change: the plan
tells the executor and the per-commit reviewer that the source diff of each family touches only
the class range and that "the source keeps every import". The mover's `repair_source_imports`
provably deletes six import bindings across three of the five family commits. Under brief §8 an
unexpected source diff is a stop, so as written the plan manufactures up to three false stops (or,
worse, trains the reviewer to wave a preamble diff through). Everything else — sizes, partition,
id maps, schema, base-expression resolution, refusals, bootstrap, ruff, shards — reproduces exactly.

## BLOCKING

### 1. §7 ("The source keeps every import") and §8 item 7 ("the source diff of each family touches only 1224..5719") are false: three family commits also rewrite the preamble imports

The mover repairs newly-unused source imports as part of the same operation (`move_methods.py:418`
-> `repair_source_imports`), independently of the `F401` per-file ignore. Simulating the five
family moves sequentially from the post-C1 source (the real execution order `family_order`), the
source import block changes at three of the five steps:

```
$ PYTHONPATH=$D:scripts:scripts/forge python3 - <<'PY'   # M.plan() per family, in-memory, sim2 tree
--- dispositions: source import lines changed: -['import datetime', 'import stat'] +[]
--- start_locks: source import lines changed: -['from tests._revision9_cli_constants import CANDIDATE, CLI, CLI_FIXTURE_SUPPORT, CORE, ENVELOPE_KEYS, ROOT, RUNTIME, key'] +['from tests._revision9_cli_constants import CANDIDATE, CLI, CLI_FIXTURE_SUPPORT, CORE, ENVELOPE_KEYS, RUNTIME, key']
--- replay: source import lines changed: -[] +[]
--- multicell_stack: source import lines changed: -[] +[]
--- ingest: source import lines changed: -['import os', 'import warnings', 'from tests._cli_loader import load_script, package_module, patch_chain_core, patch_engine'] +['from tests._cli_loader import load_script, package_module, patch_engine']
```

The repairs are *correct* — the final source has zero remaining references to the dropped names
(`os.` 0, `stat.` 0, `datetime` 0, `warnings` 0, `patch_chain_core` 0, `ROOT` 0 hits) — and they
are inside the manifest operation, so `verify.sh --strict-bodies` passes. The defect is only in
what the plan tells the human: C1 indeed drops nothing (verified: post-C1 `imports removed: []`,
`imports added: ['from tests._revision9_cli_support import Revision9CliSupport']`), and the plan
generalised that to the families.

Fix in one pass:
- §7 (line 218): replace "The source keeps every import (the eight other classes read them; F401
  is in its ignore list regardless)" with "the mover repairs newly-unused source imports per
  family (measured list below); `F401` is irrelevant to that repair".
- §8 item 7: replace "the source diff of each family touches only 1224..5719 lines" with "touches
  the class range plus, for `dispositions`/`start_locks`/`ingest` only, the preamble import lines
  listed in §3" and add the three measured deletions (above) to those families' entries in §3 and
  to `plan-revision9-cli.json` (a `source_imports_dropped` field alongside `module_globals_used`).
- §2 "Stays in ..." (line 150): the retained preamble after C7 is
  `from tests._cli_loader import load_script, package_module, patch_engine` and
  `from tests._revision9_cli_constants import CANDIDATE, CLI, CLI_FIXTURE_SUPPORT, CORE, ENVELOPE_KEYS, RUNTIME, key`
  (no `patch_chain_core`, no `ROOT`), minus `datetime`, `os`, `stat`, `warnings`.

## ADVISORY

1. **The driver runs the repository guard with the lane's relaxed ceiling.** `ENV` sets
   `REFACTOR_MAX_LINES=1000` (driver line 42) for *all* steps, including
   `python3 scripts/check_file_length.py tests` (driver line 202), so that step cannot catch a
   missing C2 baseline entry — a 966-line family module would pass locally at 1000 and fail CI's
   500-default guardrail later. A low entry still fails (baseline takes precedence), which is the
   case the plan worries about. Suggest running that one step with the variable unset
   (`bare = dict(ENV); bare.pop("REFACTOR_MAX_LINES")`), or state in §0.1 that the 500-default
   proof is deferred to the CLAUDE.md finish command at finalize.
2. **The C2 mixin entry has zero slack.** `674` equals the measured size exactly (reproduced
   below), so any drift in the applied mixin fails C2's guard. Harmless as ordered (C2 runs after
   C1, when the file exists), but the executor should re-measure with the driver's own
   `code_lines()` instead of trusting the literal.
3. **C2's owner and gate chain are unstated.** C1 and C3..C7 are driver-issued commits; C2
   (`.refactor-baseline.json`) is hand-made. Say who commits it and under which chain, and note
   (as lane B1 did) that the driver's commits carry no `CHANGELOG.md` entry because the lane's
   changelog entry lands in the finalize commit. No new authority is claimed by this plan; the
   driver's direct `git commit` follows brief §6 and the B1 precedent.
4. **Stale line citations.** §2/§3/§8 cite "driver line 205" for the loader sweep (actual: 207),
   "driver lines 152-155" for the id-map mismatch refusal (actual: 154-157) and
   "`revision9-cli-run-cluster.py:192-221`" for the gate (actual: 192-227). The *content* of every
   citation is correct; only the numbers drift. Same class as revision8 critique finding 1 — cheap
   to fix, and it is the field the next reviewer checks first.
5. **§2 cluster histogram is off by one cluster.** Plan: "test membership 1 / 2 / 38 / 5 / 6 + 9
   singletons + 4 helper-only". Measured from `inventory-revision9-cli-1.json`: `(tests,total)` =
   `(38,43) (6,9) (5,6) (2,3) (2,2)` + 9 one-test clusters + 4 helper-only = 18 clusters, 62 tests
   (the plan's list sums to 61). The partition itself is exact (below), so this is evidence
   hygiene only.
6. **Post-wave source is 1,229 code lines, not ~1,233** (measured on the simulated final file).
   Still over the 1,000 ceiling, still inside the shrink-only grandfathered entry
   `.refactor-baseline.json` 5456 — the §0.2 disposition is unaffected; update the number and the
   §7 debt line.
7. **`load_script` / `package_module` are already dead in the source** (1 hit each in the final
   file — the import line itself). They survive the wave because no moved method read them. The
   finalize step that replaces `pyproject.toml:252` with measured findings must therefore keep
   `F401` for the source, or delete the two names in a separate, out-of-scope commit. Do not let
   "measured entries" silently become a body edit.
8. **Family cohesion is source-adjacency, not call-graph.** With all 15 helpers in the mixin there
   are zero edges between tests (`tests calling tests: []` — verified), so every partition is
   connected-by-construction and the scenario grouping is a naming choice, not a coupling claim.
   §8 item 8 already offers the two changelog-gate tests to `ingest`; either placement is fine and
   neither needs a re-plan.

## What checks out (independently reproduced)

1. **Completeness / partition.** Re-measured every method span from the *current* file's AST
   (decorator-inclusive) with the `scripts/check_file_length.py` rule (non-blank, non-comment):
   77 methods placed, 77 unique, `missing: []`, `extra: []`; family method lines
   956 / 792 / 658 / 582 / 558 (sum 3,546 = the plan's `partition_check`), mixin 655, class body
   4,202 at 1224..5719, file 5,432 — every number in §2/§3 exact. All 62 MD per-test spans
   `name line..end_line (code)` match the AST exactly (62 checked, 0 mismatches), as do the 62
   `method_lines` triples and the five `methods_arg` strings in the JSON.
2. **Sizes, measured end-to-end, not estimated.** Ran the real mover planner in memory
   (`move_methods.plan`, `--shape mixin` then `--shape class` per family from the post-C1 source,
   `--format-imports` on, `import_root` absolute):
   ```
   mixin dest code lines: 674            (== the C2 entry, == the committed dry run)
   dispositions     dest_code_lines= 966 baseline_entry=976 ok=True ceiling_ok=True
   start_locks      dest_code_lines= 803 baseline_entry=812 ok=True ceiling_ok=True
   replay           dest_code_lines= 666 baseline_entry=678 ok=True ceiling_ok=True
   multicell_stack  dest_code_lines= 588 baseline_entry=602 ok=True ceiling_ok=True
   ingest           dest_code_lines= 570 baseline_entry=578 ok=True ceiling_ok=True
   ```
   Every `provisional_baseline` entry is >= true + header (slack 8..12), none exceeds 1,000, and
   the tightest module (`dispositions`) lands 34 lines under the ceiling with a generated header
   of 11 code lines against the 44 the plan computes as the seam trigger. The `dispositions`
   fallback seam is real and arithmetically sound (the four tests at 4861..5085 are 208 code
   lines: 956-208=748, 658+208=866), but it is not needed.
3. **The runtime base resolves, mechanically.** `move_methods.py:347` passes
   `extra_names={Name ids of the source class bases}` into `dependency_imports`, and
   `:408` gives the sibling `bases=source_class.bases`. Simulation output:
   `extra_names: ['CLI_FIXTURE_SUPPORT', 'Revision9CliSupport']`, and every generated family
   header contains `from tests._revision9_cli_constants import CLI, CLI_FIXTURE_SUPPORT, ...` and
   `from tests._revision9_cli_support import Revision9CliSupport`, with the class line
   `class Revision9CliSurfaces<F>Tests(Revision9CliSupport, CLI_FIXTURE_SUPPORT.ForgeCLIFixture):`
   for all five. §2/§6/§8-item-4's "stop if the C3 header lacks CLI_FIXTURE_SUPPORT" is a correct
   guard that will not fire.
4. **No refusal fires after C1.** The class body has zero non-def statements (`statements: []`
   verified by AST), no test carries a decorator, no test calls a test, no test writes instance
   state, no unsupported verdict, the only two `wrap` verdicts are the two helpers that move in
   the mixin, `metaclass: []`, `slots: false`, `prerequisites: []`. All five family plans ran to
   completion in the simulation with no `Refusal`.
5. **ID maps.** 20/17/10/6/9 = 62 keys per collector, injective, pairwise disjoint, no target
   colliding with an existing ID, every key present in the freeze with the namespace spelling
   (`test_revision9_cli_surfaces.Revision9BoundCLIIntegrationTests.<m>` and
   `tests/test_revision9_cli_surfaces.py::Revision9BoundCLIIntegrationTests::<m>`), and **byte-equal
   to what the driver's `collect_ids` would generate** (`driver-equal=True` for all five). The 62
   keys cover exactly the 62 freeze IDs of the class.
6. **The freeze reproduces at HEAD.** `collect_tests.py snapshot --start tests` (the driver's exact
   invocation) -> `{'unittest': 1908, 'pytest': 1908}`, settings, patterns and both ID lists
   identical to `.refactor/tests-revision9-cli-before.json`. C1's identity compare will diff IDs,
   not settings — the §C1 precondition is met today.
7. **Plan JSON matches the driver schema.** `families[].name/module/class/methods`,
   `mixin.methods`, `family_order` all present; `load_cluster` finds each of the five labels and
   the mixin; `paths_for` labels line up with every evidence path quoted in §3/§5; the mixin
   `dryrun` path is correctly exempted from the "must not exist" preflight; `--id-map` is passed
   for class shape only.
8. **Names and paths.** No `Revision9CliSurfaces*` or `Revision9CliSupport` class exists anywhere
   under `tests/`; none of the five module paths nor `tests/_revision9_cli_support.py` exists; all
   five classes end in `Tests`, none contains the mixin name, the mixin name contains no `Test`
   and `_revision9_cli_support.py` matches no discovery pattern (`validate_support` will accept).
9. **Bootstrap / Gate 1 shard independence.** `env -u PYTHONPATH python3 -c 'import
   tests._revision9_cli_constants'` succeeds and binds `CLI_FIXTURE_SUPPORT`; the source file
   contains no `codex_orchestrator` import and no `sys.path.insert`; every generated family header
   is stdlib + `tests.*` only. Shard simulation over the post-split module set reproduces
   `gate_1_shards_after_split` exactly (73 modules, 4 shards: 1 = dispositions + start_locks,
   2 = ingest, 3 = multicell_stack, 4 = source + replay).
10. **Ruff under the committed config.** `ruff check tests` over the *simulated post-wave* tree
    (the five family modules, the mixin, and the reduced source, with the repo's `pyproject.toml`
    including the temporary globs and the `known-local-folder` isort ruling): `All checks passed!`
    — including `I001`, which the temporary globs deliberately do not ignore.
11. **Shell and untouched classes.** After the simulated C7 the source is
    `class Revision9BoundCLIIntegrationTests(Revision9CliSupport, CLI_FIXTURE_SUPPORT.ForgeCLIFixture): pass`
    with all nine classes intact in order and the `if __name__ == "__main__"` guard preserved;
    post-C1 source 4,778 code lines (== the plan's estimate), final 1,229.
12. **Contract items.** One destination per commit (`max_outputs` 1), tier 1 per manifest, a single
    declared test-mixin base backed by its verified manifest, no production base class, no
    pinned IDs to preserve (`pinned: {}`, `shards: {}`), census 0 code sites (the class name
    appears only at source line 1224 plus one prose row in
    `docs/analysis/refactoring-review-2026-09-11.md`), no state owner problem (`writes` empty for
    all 77 methods; the constants module is read-only), and no scope creep: §1 deletes nothing,
    every commit is mover output plus evidence, and the one hand-written commit (`b4d3c4f`) is
    already landed under brief §4 item 2.
13. **Loader sweep and per-cluster gate.** `tests.test_cli_loader` runs in every cluster gate
    (driver line 207), after `verify.sh --strict-bodies --test-mode identity|mapping` and the
    repository file-length guard, before the two bare-`PYTHONPATH` import proofs — exactly the
    order §3/§5 quote.

## Reproduction commands

```bash
cd /home/agents/foundry-of-zero/forge-plugin-refactor-wt/s6 && export TMPDIR=/dev/shm/refactor-s6
D=/home/agents/foundry-of-zero/refactor-python/skills/decompose/scripts

# 1. spans, partition, refusal facts, per-family helper/global sets   (checks 1, 4)
python3 - <<'PY'   # AST spans vs plan method_lines/MD spans; inventory decorators/calls/writes
PY

# 2. sizes and headers, produced by the real mover in memory           (checks 2, 3, 11)
PYTHONPATH=$D:scripts:scripts/forge python3 - <<'PY'   # M.plan(mixin) then M.plan(class) x5
PY

# 3. id maps vs freeze vs driver collect_ids                           (check 5)
python3 - <<'PY'
PY

# 4. freeze reproduction
PYTHONPATH=scripts:scripts/forge python3 $D/collect_tests.py snapshot --start tests --out /dev/shm/refactor-s6/ids-now.json

# 5. bootstrap proof
env -u PYTHONPATH python3 -c 'import tests._revision9_cli_constants as c; print(c.CLI_FIXTURE_SUPPORT)'

# 6. ruff over the simulated post-wave tree
(cd /dev/shm/refactor-s6/sim2 && python3 -m ruff check tests)
```

(The four heredocs are the scripts run during this review; their full output is quoted inline
above. They read the worktree and write only under `/dev/shm/refactor-s6/`.)
