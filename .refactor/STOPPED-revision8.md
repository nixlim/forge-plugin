# STOPPED: lane B (session 8, bead forge-plugin-25ms), 2026-09-23 (second run, after the 01:27 relaunch)

Condition: brief section 8 item 4. The first family commit (section 4 item 4) cannot be made
without one of: a repository-wide lint-configuration change in `pyproject.toml` that the brief's
enumerated config prep (section 4 item 1: per-file-ignore globs and size-baseline entries) does not
cover, an edit to a test outside the target file and its siblings, a second hand-written edit to
the constants commit, or a plugin change. Under decision 4 ("there is nobody to ask; never bypass,
never widen") that is a stop. The stop is taken BEFORE the mixin commit (section 4 item 3), because
the fix the operator picks changes the mixin's generated header too (details below); nothing of the
mover's output is on the branch. Session 6 (bead forge-plugin-kzu0) is not started (section 8 item 6).

## The finding (measured; planner section 0 item 1, critic finding 3, orchestrator reproduction)

`move_methods.py --format-imports` runs `ruff check --select I --fix` on every destination. Under
the project's isort settings `codex_orchestrator` (a package under `scripts/`, not resolvable
from `src = ["."]`) is third-party and `tests.*` is first-party, so every generated header reads

    from codex_orchestrator import batch, journal
    from tests._revision8_constants import RECORDED_AT, TOOLS

(`.refactor/dryrun-revision8-mixin.txt` lines 599..616). The constants module's copied
`sys.path.insert(0, str(ROOT / "scripts"))` therefore runs AFTER the `codex_orchestrator` import,
which defeats the brief's stated intent for that line ("so the support module's copied
codex_orchestrator import resolves without PYTHONPATH", section 4 item 2). Consequences:

- The mixin commit itself is importable only through the source module (it imports the constants
  module first); `env -u PYTHONPATH python3 -m unittest tests.test_revision8_coordination` would
  pass, `python3 -c "import tests._revision8_support"` would not.
- A family module imported first in a Gate 1 shard fails. Empirical shard check (this host,
  `os.cpu_count()=12` -> 4 shards, 68 existing + 7 planned module stems, each shard's prefix
  imported in argv order without PYTHONPATH, then `import codex_orchestrator`):

  | shard | first family module | result |
  |---|---|---|
  | 1 | test_revision8_orphan_identity | resolves (an earlier module inserted scripts/) |
  | 2 | test_revision8_append_schema | ModuleNotFoundError: codex_orchestrator |
  | 3 | test_revision8_registry_races | resolves |
  | 4 | test_revision8_interruptions | ModuleNotFoundError: codex_orchestrator |

  With the source shell deleted at finalize the critic measured shards 2, 3 and 4 failing.
- PYTHONPATH exists only in this worktree's git-excluded `.claude/settings.local.json`; the main
  clone's local settings, `~/.claude/settings.json` and CI do not set it, and
  `.github/workflows/forge-ci.yml:27-52` runs the committed Gate 1 cell without it. A reintegrated
  tree would fail CI and any Forge-session Gate 1 run on a 4-shard host. Option C (rely on
  PYTHONPATH) is therefore refuted, not merely discouraged.
- The four tests that import `codex_orchestrator` today (`test_commitment_paths`,
  `test_revision8_coordination`, `test_revision9_coordination`, `test_run_coordination`) all do
  their own `sys.path.insert` before a `# noqa: E402` import; the mover cannot reproduce that shape.

## Options for the operator (all measured, none taken)

| option | change | repo-wide side effect (`ruff check --select I scripts tests system/fr223`, baseline clean) | rule status |
|---|---|---|---|
| A | `[tool.ruff.lint.isort] known-local-folder = ["codex_orchestrator"]` | 1 new I001 at `tests/test_commitment_paths.py:20` (one blank line) | needs an out-of-scope test edit (section 8 item 4) |
| A' | A plus `no-lines-before = ["local-folder"]` | same single I001 | same |
| A'' | custom `sections` placed last | same single I001 | same |
| A''' | `known-local-folder = ["codex_orchestrator", "commitment_paths"]` | **none** (All checks passed); produces `tests.*` before `codex_orchestrator` in both the mixin and the family headers (critic, measured on stdin copies) | config-only, but a repo-wide import-section convention; not in the brief's enumeration; the UP037 glob of session 2 needed an explicit nod for less |
| B | plugin: the mover carries the source's `sys.path.insert` preamble and `# noqa: E402` pattern into the destination | n/a | refactor-python change, out of scope tonight (candidate for refactor-python/docs/plans/2026-09-23-plugin-0.1.4-followups.md) |
| C | rely on PYTHONPATH | n/a | refuted (shards 2 and 4; CI) |
| D | `tests/_revision8_constants.py` re-exports `batch` and `journal` after its `sys.path.insert`; the source imports them from there and drops its own `codex_orchestrator` line | none | amends the hand-written constants commit 42980e7 and hand-edits the source header: section 8 item 4 twice; cleanest long-term shape per the critic |

Whichever the operator picks, it MUST precede the mixin commit so that the mixin header is
generated under it, and the mixin dry run is re-run under it with the same argv.

## Command and output

    env -u PYTHONPATH python3 -c 'import importlib; [importlib.import_module("tests."+m) for m in <shard-2 prefix>]; import codex_orchestrator'
    -> ModuleNotFoundError: No module named 'codex_orchestrator'   (shards 2 and 4; shards 1 and 3 resolve)

    ruff check --select I --config 'lint.isort.known-local-folder=["codex_orchestrator"]' scripts tests system/fr223
    -> Found 1 error.   (tests/test_commitment_paths.py:20 I001)

## State left behind (all green, nothing reverted, nothing of the mover's output committed)

Branch `refactor/split-test-revision8-coordination` from BASE 69bc28d, pushed. Commits, in order:
f80e262 freeze evidence; c8cf01a temporary ruff globs (config-only prep, section 4 item 1);
42980e7 the hand-written constants module (section 4 item 2; ruff clean, focused 81 OK, ID identity
PASS); d4c9b36 first inventory; 79795b2 re-frozen body snapshot (`.refactor/before-revision8-1.json`,
gate --fast PASS); 9c465ca mixin dry-run evidence (verified, no files written); 0c05015 driver and
Gate 1 runner; 4d4d7c9 plan + 7 id maps; 5a24bf2 critique (REVISE) + regenerated inventory
(`inventory-revision8-1.json`, spans corrected); 2056725 the driver's standalone-import check;
27890f9 the revised plan; this file. `git diff --stat 69bc28d..HEAD -- scripts docs/specs .forge` is empty. The
provisional `.refactor-baseline.json` entries (section 4 item 1) were NOT committed: they are
gated on the plan's true+20 sizes and on the operator's option. The s6 worktree was not created.

Evidence to read in the morning: `.refactor/plan-revision8.md` (section 0 = the decision
record), `.refactor/critique-revision8.md` (shard simulation, side-effect measurements, what
checks out), `.refactor/inventory-revision8-1.md`, `.refactor/dryrun-revision8-mixin.txt`.

## Next step I would have taken

With the operator's option committed as a config-only prep commit ahead of the mixin: re-run the
mixin dry run under it (`.refactor/dryrun-revision8-mixin.txt` argv), commit the provisional
baseline entries at the plan's true+20 sizes (mixin 539; families 724/617/593/628/576/819/540),
then `python3 .refactor/revision8-run-cluster.py mixin`, then the seven families in the plan's
order through the same driver (each run proves the new module imports standalone without
PYTHONPATH), wave-close Gate 1 under the host lock, finalize, reviews, handover. Under option D the
constants commit is amended first and the source snapshot re-frozen before the mixin.
