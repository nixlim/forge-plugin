# Fable refactor-reviewer record: test_revision9_coordination split (lane A, session 4, bead forge-plugin-6g67)

Reviewer: refactor-python `refactor-reviewer` agent (claude-fable-5-1, read-only), spawned by the session orchestrator
2026-09-23 after the two finalize Gate 1 runs. Range 69bc28d..f20b8e8 (reviewed tip f20b8e8). Independent review first
(Codex verdict absent at that time), then the adjudication round against `.refactor/codex-review-revision9-coord.md`.
Both messages are reproduced verbatim below.

## Independent review (13:52 UTC)

```
VERDICT: APPROVE
CODEX_VERDICT: pending — .refactor/codex-review-revision9-coord.md absent at review time (the .jsonl has 34 lines, no .md verdict); send the path for the adjudication round
BLOCKING:
- none
ADVISORY:
- .refactor/decompose-records-revision9-coord.json:4 (every "commit" field) — records the PRE-AMEND SHAs (91f32c5, c46bb8c, 4bd6736, ed265c0, d3d137a, 28de543, d8d8111, 18c4dfd, 05e1290, 39e08fc, 74ce1c9, d4a36fa, 38f7319); `git merge-base --is-ancestor <sha> f20b8e8` → NO for all 13. Each shares parent and subject with its branch commit (63dd6b8, 40383f3, ba41883, 666ab3b, e9cac07, 09c4b74, e01d101, 744293d, 3c47c51, cbac4a4, 4d416d1, db63ca7, 9b7599a) and `git diff --name-only <recorded> <branch>` touches only the records file and the driver log — tests/, pyproject.toml, .refactor-baseline.json identical. The driver documents the amend; objects are reachable and I ran the oracle at them. Bookkeeping only; the handover should name the amended SHAs as the record (or a docs commit should rewrite the records file).
- .refactor/gate-revision9-coord-c*.txt — verify.sh writes `Ran 144 tests` to .refactor-gate.log (not retained), so the driver's `grep '^Ran '` on the gate file recorded nothing; the committed per-cluster record holds only PASS/FAIL lines. The 144 count is proven independently below; no evidence gap, but the plan's "gate prints 144" is not in the record.
- .refactor/gate1-revision9-coord-finalize-run{1,2}.txt are untracked at f20b8e8 (post-date the finalize commit); committed Gate 1 evidence at the tip is wave-close (pre-ruling FAIL) and wave-close-2 (PASS). Both finalize runs read 4/4 shards exit 0, 414+603+389+502 = 1,908 tests; they should ride in the review-record commit.
- tests/test_revision9_coordination.py:16-21 — the mover re-wrote the constants import with the closing paren on the last-name line (`key)`). Cosmetic; `ruff check tests` clean, I001 already in the source's grandfathered entry at 69bc28d. No action.
CODEX_FINDINGS:
- pending
DISPUTED:
- none
ALLOWED_CHANGED: LegacyRuntimeNameCarveOutTests, LegacyRuntimeNameCarveOutTests.test_shipped_files_limit_opencode_to_migration_carve_out, Revision9BuilderBatchTests
```

ALLOWED_CHANGED rationale: the first two are the operator-ruled one-element tuple change in 73eee2b
(`allowed_prefixes = ("docs/design/", "docs/specs/", ".refactor/")`, the only hunk in tests/test_migration.py); the third
is the moved class itself (146 methods left, header gained the mixin base). The 146 MISSING / 159 ADDED lines from
`snapshot_bodies.py compare .refactor/before-revision9-coord.json tests` are the 38 helpers + 108 tests re-homed under 13
new qualnames plus the 13 new class entries (159 = 146 + 13); `key` and the 10 constants are not flagged because their
bodies are AST-identical at the new path.

Independent review of 69bc28d..f20b8e8 (21 linear commits): `git diff --stat -- scripts docs/specs .forge` empty; outside
tests/ only pyproject.toml, .refactor-baseline.json, CHANGELOG.md and .refactor/ changed. IDs: `collect_tests.py snapshot
--start tests` at HEAD gives 1,908/1,908 (unittest/pytest) as in the freeze; exactly 108 gone and 108 new per collector,
equal to the union of the 12 id-map keys/values (injective, one class per family, no duplicates, no pinned IDs or shards);
the skipUnless test is still collected on `Revision9BuilderBatchTests` in both collectors. Bodies: all 147 methods of the
class at 69bc28d located exactly once at f20b8e8 (18 mixin, 128 family, 1 retained), `ast.dump` with decorators and
dedented source segments equal for every one; `key()` and the 10 constants AST-identical in `_revision9_coord_constants.py`;
455e436 removes exactly those 11 statements and adds one import; the other three classes and the source's module-level
statements are AST-identical; 0 unread source imports; removals match plan §5 and the manifests. Oracle: per cluster,
detached worktree at the recorded commit, `snapshot_bodies.py compare --strict --manifest` → PASS (tier 1) ×13 and
`collect_tests.py compare --mode identity|mapping` → PASS ×13; every manifest tier 1, test_only, methods equal to the
planned csv in order, id maps 4/13/6/9/10/6/9/11/5/11/12/12. Headers: mixin has no base and only 18 defs; all family
classes and the source class read `(Revision9BuilderBatchSupport, unittest.TestCase)`; family bodies are defs only;
private helpers on exactly the §2b family; every `self.<attr>` resolves (R16/R17). Imports: `tests._revision9_coord_*`
precede the scripts/ packages in all 13 new modules; `ruff check tests` and `--select I` clean; no local imports, module
state, `__all__` or side effects beyond the constants module and source; every new module imports first in a fresh
process without PYTHONPATH; focused discover → Ran 144 tests OK. Census: no by-name reference to the old or new classes
outside the 13 mixin imports; 0 reflection hits. Finalize: per-file-ignores equal the measured ruff codes (no glob, no
I001/E402/F401 on new modules, source entry a 6-code subset); every baseline pin equals the measured size (source 4931,
mixin 806, families 521–896; 230/424 unpinned); 246 files within budget; 12 debt rows with reasons and follow-up
forge-plugin-z50i; one CHANGELOG line. Logs: c00..c12 GATE: PASS, 12 standalone OK, Gate 1 wave-close-2/finalize-run1/run2
4/4 shards OK (1,908). Advisory only: records file names pre-amend SHAs (trees identical in tests/); finalize Gate 1 logs
untracked at the tip.

## Adjudication round (14:05 UTC), against `.refactor/codex-review-revision9-coord.md`

CODEX_ADJUDICATION (Codex VERDICT: REJECT, thread 01a0ce81-0c72-7cd2-b38c-5ad8fa9753bd)

- REFUTED — B1 `tests/_revision9_coord_constants.py:27` duplicate `sys.path.insert` changes lookup precedence / import fails once the entry is removed. Probe (fresh process, `env -u PYTHONPATH python3 -c "import tests.test_revision9_coordination; print(sys.path.count(scripts))"`): tip 2 entries with `scripts` at `sys.path[0]`, baseline 1 (and 4 across the baseline suite: `_cli_loader`, `test_commitment_paths`, `test_revision8_coordination`, `test_run_coordination` already insert the same path; tip 5). Both entries are the same resolved string, so first-match resolution is unchanged and `scripts` is found no later than before. The failure needs a caller to delete the entry from `sys.path` after import — no test or script does. The second line is prescribed by the brief §4 item 2 / §11 item 1 ("a copy of the source's sys.path line"; source keeps its own). Not a behaviour change.
- REFUTED — B2 `tests/test_revision9_coordination.py:16` the source no longer exports `TOOLS`, `PREFIX_WEDGE_FIXTURE{,_SHA256}`, `UNREPLAYABLE_CHAIN_{ID,FIXTURE,FIXTURE_SHA256}`. Repo-wide grep (`tests scripts system hooks skills agents rules .github .claude-plugin`, plus every `*.py` outside `.git/.refactor`) for `from|import (tests.)?test_revision9_coordination` → 0 importers; the only mention outside the module family is the constants module docstring. The census gap is closed by that grep: `tests/` is a namespace directory of discovered modules, not an API, and no consumer of those six bindings exists. The names still live in `tests._revision9_coord_constants` and the source re-imports the five it reads.
- CONFIRMED as fact, no impact (advisory) — A1 `key.__module__` and its patch target changed. `key` is AST-identical; grep for `patch(...key|hashlib|TOOLS|PREFIX_WEDGE_*|UNREPLAYABLE_*)` in tests/ and scripts/ → 0 targets, and no module reads `test_revision9_coordination.key`. The rebinding scenario has no caller.
- CONFIRMED (advisory) — A2 no tracked c00 standalone source-module run: `.refactor/standalone-revision9-coord-c00*` absent, driver-c00 log has no standalone line (the driver's check began at c01). My probe at f20b8e8: `env -u PYTHONPATH python3 -m unittest tests.test_revision9_coordination` → Ran 36 tests, OK. Evidence gap only; behaviour proven.
- UNVERIFIABLE — A3 Codex's Gate 1 was sandbox-limited (`/tmp` not writable). A statement about Codex's environment, not the diff; the committed wave-close-2 and the finalize-run1/run2 logs show 4/4 shards exit 0, 1,908 tests, and my focused run passed 144/144.

DISPUTED (verbatim, for the consensus round):
- "tests/_revision9_coord_constants.py:27 — `scripts` is inserted into `sys.path` here and again at `tests/test_revision9_coordination.py:24`, changing lookup precedence and duplicating state. With the constants module cached and its entry removed, tip import fails at `tests/_revision9_coord_support.py:17`; baseline succeeds."
- "tests/test_revision9_coordination.py:16 — the original module no longer exports `TOOLS`, `PREFIX_WEDGE_FIXTURE{,_SHA256}`, or `UNREPLAYABLE_CHAIN_{ID,FIXTURE,FIXTURE_SHA256}`; direct imports now raise `ImportError`. The supporting census is explicitly incomplete."

Note: `.refactor/decompose-records-revision9-coord.json` now names the amended branch commits with `pre_amend_commit` fields — that closes my first advisory.

VERDICT: APPROVE (unchanged; neither Codex BLOCKING item survives reproduction, the two confirmed items are evidence-bookkeeping advisories with no behaviour effect)

## Orchestrator notes

- The first advisory is closed on this branch: the records file now carries the amended SHAs (`commit`) with the pre-amend
  SHAs kept as `pre_amend_commit`. The finalize Gate 1 logs and A2's standalone source-module run at the tip
  (`.refactor/standalone-revision9-coord-source-tip.txt`) ride in the review-record commit, as advised.
- The consensus round with Codex on the two disputed items is recorded in `.refactor/consensus-revision9-coord.md`.
