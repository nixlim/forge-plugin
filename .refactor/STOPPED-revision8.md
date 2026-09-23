# STOPPED: lane B (session 8, bead forge-plugin-25ms), 2026-09-23 13:40 CEST (third run, after the 12:55 relaunch under the isort ruling)

Condition: brief section 8 item 3 (a Gate 1 shard failed once with `/proc/loadavg` 5.04 at start,
i.e. under 24, and the failure is deterministic, not a collection or import error) and item 4
(the only remedy is an edit to a test outside the target file and its new siblings). The stop is
taken at wave close, AFTER the whole wave landed green: the isort ruling, the mixin and all seven
families are committed and every per-cluster gate passed. Finalize, the two finalize Gate 1 runs,
the reviews and the handover bead were not started. Session 6 (bead forge-plugin-kzu0) is not
started (section 8 item 6).

## The finding

The wave-close Gate 1 cell (`.refactor/gate1-revision8-wave-close.txt`, head 3982972, start
2026-09-23T11:06:16Z load 5.04, end 11:14:03Z) ran 4 shards: 1/4 OK (447 tests), 3/4 OK (432),
4/4 OK (501), **2/4 FAILED (528 tests, failures=1)**:

    FAIL: test_shipped_files_limit_opencode_to_migration_carve_out
          (tests.test_migration.LegacyRuntimeNameCarveOutTests)
    AssertionError: legacy runtime name appears outside migration carve-out:
      ['.refactor/before-revision8-1.json', '.refactor/before-revision8.json',
       '.refactor/revision8-<cluster>-before.json' x8, '.refactor/tests-revision8-before.json',
       '.refactor/tests-revision8-<cluster>.json' x8]   (19 files)

`tests/test_migration.py:96-135` lists every tracked and untracked-not-ignored file
(`git ls-files --cached --others --exclude-standard`) and fails if the byte string `opencode`
appears in any file outside `UPSTREAM`, `scripts/forge/migrate-upstream.py`, the test itself,
`docs/design/` and `docs/specs/`. The brief's evidence protocol (section 3 items 6..7, section 6)
snapshots the whole `tests/` tree for every cluster: the body snapshot (`snapshot_bodies.py
snapshot tests`) carries the bodies of `tests/test_migration.py`, whose fixtures spell
`.opencode/...`, and the ID snapshot (`collect_tests.py snapshot --start tests`) carries the ID
`test_shipped_files_limit_opencode_to_migration_carve_out` itself. Both are tracked under
`.refactor/` by the brief's own rule ("every evidence file goes under tracked `.refactor/`"), and
the reviewer replays them against the manifests, so they cannot be untracked or rewritten.

- Present since the freeze commit `f80e262` (`before-revision8.json`, `tests-revision8-before.json`);
  every per-cluster commit added one body and one ID snapshot. The lane gates do not run
  `tests/test_migration.py` (`REFACTOR_TEST_CMD` = `discover -p 'test_revision8*.py'`), so the
  first full run to see it was wave close.
- Reproduced standalone: `python3 -m unittest tests.test_migration.LegacyRuntimeNameCarveOutTests`
  -> FAILED (failures=1) in 0.5 s; passes at BASE 69bc28d (no `.refactor/` file on main carries the
  string). Not load-related; a bisect would only re-find it.
- The gate log itself and this file quote the failure and are the 20th and 21st such files.
- **Applies to all three lanes of the brief**, not only B1: every test-tree body and ID snapshot
  carries the string. Lane A (s4, tip 38f7319 at 13:35) has no `gate1-revision9-*` log yet and will
  fail the same way at its wave close; lane B2 would too.

## Remedy measured for the operator (none taken)

| option | change | measured | rule status |
|---|---|---|---|
| A | `tests/test_migration.py:110` `allowed_prefixes` gains `".refactor/"` | violations 20 -> **0** (same inventory logic run on a copy; nothing edited) | one-line edit to a test outside the target: section 8 item 4, operator decision. `.refactor/` is planning and gate evidence, not a shipped runtime surface, which is the carve-out's stated purpose |
| B | untrack the 17 snapshot JSONs (gitignore) | would pass | contradicts the brief's evidence rule and removes the reviewer's replay inputs; not recommended |
| C | move the snapshots under `docs/design/` | would pass | abuses a carve-out meant for design documents; not recommended |

Whichever the operator picks lands as one commit on this branch ahead of finalize (option A is
docs/test-class in the file-category sense but still a test edit, so it is disclosed to both
reviewers and in the handover as the session's one non-target test edit); then wave close is
re-run (Gate 1 once), and the plan continues: finalize, Gate 1 twice, Codex + Fable reviews,
handover. The decision is the same for lanes A and B2, so one ruling serves all three.

## State left behind (all green, nothing reverted)

Branch `refactor/split-test-revision8-coordination` from BASE 69bc28d, pushed at this commit.
Commits since the 02:25 stop tip b0eec81, in order:

- cc99cc8 the operator's isort ruling (`[tool.ruff.lint.isort] known-local-folder = [codex_orchestrator,
  codex_orch_tools, forge_cli, commitment_paths]`; ruff --select I repo-wide clean, CLAUDE.md finish
  command clean, gate --fast PASS; removed the 02:25 STOPPED file)
- c8a4662 mixin dry run regenerated under it (only the header order changed: constants first)
- a1defe4 C1 mixin: 31 helpers -> `tests/_revision8_support.py` (539 code lines), gate PASS
  (--test-mode identity), focused 81 OK, `env -u PYTHONPATH` unittest and standalone import OK
- 5be2e31 C2 provisional size-baseline entries (539/724/617/593/628/576/819/540), guard clean at 500
- 6099c5a orphan_identity (17 tests, 809 code lines), c27ca9f append_schema (10, 712),
  872314e registry_races (12, 618), f38b2d4 precedence (16, 609), d3b84bb rollback (9, 583),
  1e26031 interruptions (3, 566), 3982972 successors (14, 533): each gate PASS (manifest oracle
  --strict-bodies, ruff, file-length, types, lint-imports, ID compare --mode mapping, focused 81
  OK), repository guard OK, `env -u PYTHONPATH python3 -m unittest tests.<module>` OK and the
  standalone `import tests.<module>` OK; source now 10 code lines (docstring-only shell, kept)
- this commit: STOPPED record, the wave-close Gate 1 log, `.refactor/decompose-records-revision8.json`
  (the eight cluster records: commit, snapshot, manifest, id map, sizes)

`git diff --stat 69bc28d..HEAD -- scripts docs/specs .forge` is empty; no production file changed;
no mint; no body edit. Untracked: nothing. `$TMPDIR` (/dev/shm/refactor-s8) left in place.

## Next step I would have taken

With the operator's option committed: `flock /dev/shm/refactor-gate1.lock bash
.refactor/gate1-revision8.sh wave-close-2` under the load guard (expect 4/4 OK; shard 2's only
failure was this test), then finalize (measured baseline entries from decompose-records, the
temporary ruff globs replaced by measured per-module entries via `ruff check` per module with the
globs and `pyproject.toml:242` removed, `quality.py` with `.refactor/debt-revision8.json`
(follow-up bead forge-plugin-7pzp already created: mixin split by role, shell deletion), the
CHANGELOG entry), Gate 1 twice, `codex_review.sh --base 69bc28d --plan .refactor/plan-revision8.md`,
the refactor-reviewer agent, consensus, the handover bead, push, `bd remember`; then session 6 in s6.
