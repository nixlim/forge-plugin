# Plan critique: `.refactor/plan-revision8.md` / `.refactor/plan-revision8.json`

Critic: plan-critic agent, 2026-09-23, worktree `/home/agents/foundry-of-zero/forge-plugin-wt/s8`,
branch `refactor/split-test-revision8-coordination` tip `0c05015`, BASE main `69bc28d`.
Everything below was reproduced independently in this worktree (read-only) or on stdin copies;
no `--apply`, no file outside `.refactor/critique-revision8.md` written.

VERDICT: REVISE

## BLOCKING

1. **The inventory's line numbers are stale by 2 (pre-constants-commit coordinates), so every
   per-method line citation in plan §3/§7 is wrong and every family size estimate undercounts by
   one code line per test.**
   `.refactor/inventory-revision8.json` was generated against the source as it was at `e7813cc`
   (before `42980e7` removed the preamble constants), not against HEAD. Proof:
   `inventory-revision8.json` `setUp.line = 31`, but `tests/test_revision8_coordination.py:29` is
   `def setUp(self) -> None:` and line 31 is `self.addCleanup(...)`;
   `git show e7813cc:tests/test_revision8_coordination.py` has `def setUp` at line 31.
   Offset histogram over all 112 methods (start, end): `{(2,2): 109, (3,2): 3}` — +2 for every
   method, +3 on the start of the three decorated helpers.
   Consequence: the plan's counts were taken over the window `[def+2 .. end+2]` of the *current*
   file, which drops the `def` line and the first body line and picks up the following blank plus
   the next `def`. Net **-1 code line per undecorated method, -2 per decorated one**.
   Independent confirmation: the true (AST-derived) helper total is **524** code lines, which is
   exactly the method-body code-line count of the verified mixin dry run
   (`.refactor/dryrun-revision8-mixin.txt` destination hunk, 539 total minus a 15-line header);
   the inventory-derived figure is 490.
   Corrected family sizes (AST spans in the current file, `check_file_length.code_lines` rule):

   | family | plan est_total | true method lines | true + 20 header |
   |---|---|---|---|
   | append_schema | 714 | 704 | **724** |
   | precedence | 601 | 597 | **617** |
   | rollback | 584 | 573 | **593** |
   | registry_races | 616 | 608 | **628** |
   | interruptions | 573 | 556 | **576** |
   | orphan_identity | 802 | 799 | **819** |
   | successors | 525 | 520 | **540** |
   | `_revision8_support.py` | 539 (measured) | 524 + 15 header | 539 (correct) |

   The sizing *conclusion* survives (0 over 1,000, all 7 in the 500..1,000 band, max 819), but
   **`.refactor/plan-revision8.json.provisional_baseline` and plan §5 C2 are every one of them
   9..17 lines too low.** `check_file_length.py` treats a baseline entry as a ceiling
   (`"grandfathered at {allowed} code lines but grew to {n}"`), so committing C2 with those
   numbers makes **every family gate fail** at the `file-length` step of `verify.sh`.
   Fix in one pass: (a) restate §3's per-test `line..end_line` tables in current-file
   coordinates (subtract 2), (b) replace the C2 numbers with the `true + 20` column above, or
   keep §0.2's "measure from the dry runs" but delete the estimate block from the JSON twin so no
   one commits it verbatim. Also correct §7's three debt lines: the true spans are
   `test_postsyscall_baseexception_restores_registry_and_owner_begin_paths` **3233..3433**
   (201 phys / **185** code), `..._during_rollback_retains_coherent_candidate` **3435..3655**
   (221 / **205**), `test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent`
   **3657..3833** (177 / **166**).
   (§3 line tables were computed from the stale inventory while §6's grep evidence — decorators
   at 65/69/101, the `nonlocal` line list — is in *current* coordinates. Two coordinate systems
   in one plan is itself a defect; §6's list is correct, §3's is not.)

2. **Plan §0.1 option A, exactly as written, triggers brief §8 stop condition 4 — and there is a
   measured variant that does not.**
   Reproduced verbatim: `ruff check --select I scripts tests system/fr223` → `All checks passed!`;
   with `--config 'lint.isort.known-local-folder=["codex_orchestrator"]'` → exactly **one** new
   `I001` at `tests/test_commitment_paths.py:20`, fix = insert one blank line between
   `import commitment_paths` and `from codex_orchestrator import batch, journal` (layout only, no
   reorder). The plan's own remedy ("that blank line ... belongs in the same config commit with
   the operator's nod") is **an edit to a test outside the target file and its new siblings**,
   which brief §8 item 4 names as a stop; and there is no operator tonight (task framing +
   brief §8). Leaving the `I001` is not an option either: `verify.sh` runs
   `ruff check "$PKG"` with `PKG=tests` (verify.sh:62), so the finding fails every per-cluster
   gate, and `ruff check scripts tests system/fr223` is CLAUDE.md's finish command.
   **A' does not help** (measured): adding
   `--config 'lint.isort.no-lines-before=["local-folder"]'` — confirmed applied via
   `--show-settings` (`linter.isort.no_lines_before = [known { type = local_folder }]`) — leaves
   the **same single `I001` at the same line with the same fix**. It changes no other file.
   **A'' does not help**: a custom section (`lint.isort.sections={"orch"=["codex_orchestrator"]}`
   with `section-order=[...,"first-party","orch","local-folder"]`) produces the identical single
   `I001` at `tests/test_commitment_paths.py:20`.
   **A''' has zero measured side effects**:
   `ruff check --select I --config 'lint.isort.known-local-folder=["codex_orchestrator","commitment_paths"]' scripts tests system/fr223`
   → `All checks passed!` (both third-party-looking `scripts/`-resident top-level modules land in
   the same section; ruff's default `force-sort-within-sections=false` keeps the straight
   `import commitment_paths` before the `from codex_orchestrator import ...`, i.e. the file's
   existing layout). And it produces the order the plan needs, verified on stdin copies:
   family header → `... from tests._cli_loader / from tests._revision8_constants` **then**
   `from codex_orchestrator import journal`; mixin header (the real dry-run header, re-linted) →
   `from tests._revision8_constants import RECORDED_AT, TOOLS` **then**
   `from codex_orchestrator import batch, journal`.
   The plan must replace option A with A''' (or justify A and accept the stop). It must also
   state that "no test outside the target file and its siblings is edited" is what makes the
   config commit legal.

3. **"preferably before commit 1" is wrong: the isort config MUST land before C1, because
   `orphan_identity` — the first family in the commit order — imports no constants module.**
   Inventory globals for f6 are `{journal, json, mock, os, threading}`; it is the only family
   without `RECORDED_AT`/`TOOLS`, and it is `family_order[0]`. Its generated header will therefore
   be `... import unittest / from tests._revision8_support import Revision8Support /
   from codex_orchestrator import journal` with **no** `tests._revision8_constants` import, so its
   `sys.path` insert can only come transitively from `tests/_revision8_support.py`. The mixin's
   *verified* header today (`.refactor/dryrun-revision8-mixin.txt`, destination hunk) is
   `from codex_orchestrator import batch, journal` **before**
   `from tests._revision8_constants import RECORDED_AT, TOOLS`, i.e. `tests/_revision8_support.py`
   is itself unimportable without `PYTHONPATH`. If C1 is committed first and the config lands
   afterwards, C1 must be reverted and re-run. Note also that the driver's own bare-`PYTHONPATH`
   proof for the mixin label runs `python3 -m unittest tests.test_revision8_coordination`
   (`.refactor/revision8-run-cluster.py:207-211`, `SRC_MODULE` when `label == "mixin"`), which
   passes because the *source* imports constants on line 18 before support on line 19 — so C1's
   gate does **not** catch the latent defect; C3's does, and then the wave stops.
   Fix: make §5 order `C-config (A''') → C1 mixin → C2 baseline → C3..C9`, and re-run the C1 dry
   run afterwards (the plan already says the manifest oracle's `normalise_header` accepts the
   regrouping, so the verdict is unchanged — but the evidence file must be regenerated).

4. **The plan's per-family gate command drops `--strict-bodies`, which brief §6 requires.**
   §3 (every family, e.g. plan-revision8.md:68) reads
   `bash $S/verify.sh --pkg tests --snapshot <..> --manifest <..> --test-snapshot <..> --test-mode mapping --fast`.
   Brief §6: "`bash $S/verify.sh --pkg tests --snapshot <that> --manifest <manifest>
   --strict-bodies --test-snapshot <ids> --test-mode identity|mapping`". The committed driver
   gets it right (`.refactor/revision8-run-cluster.py:191-196` passes `--strict-bodies` and no
   `--fast`), so this is plan text that contradicts the artifact the session will actually run —
   fix the plan text, not the driver. (`--fast` only skips the `tests` step, verify.sh:88-92, so
   the plan's "then the lane's `REFACTOR_TEST_CMD`" is equivalent in coverage but not in gate
   record.)

5. **Three decisions are handed to an operator who is not there; under brief §8 each is a stop,
   so as written the plan cannot be executed past C1.** §0.1 ("Options, operator's call"),
   §0.2 ("confirm the entries and their timing"), §0.4 ("Whether finalize deletes the shell ... is
   an operator decision"). The plan must resolve all three in-brief or declare the stop:
   - §0.1 → option A''' above (config-only, zero side effects, no edit outside `pyproject.toml`).
   - §0.2 → commit C2 with the `true + 20` upper bounds (a high entry is inert; §0.2 already says
     so), no operator input needed.
   - §0.4 → **keep the shell**. Deleting the source module is not merely "an operator decision",
     it is actively harmful: the Gate 1 cell's round-robin over sorted `tests/test_*.py` stems is
     membership-sensitive, and removing `test_revision8_coordination` re-partitions all four
     shards (see the simulation below): 3 of 4 shards then fail instead of 2. Record the deletion
     question in the handover as a follow-up bead.

6. **The census claim in §2 is false as stated.** §2 says the grep "outside the source finds only
   prose in `docs/analysis/*.md` (3 files) and config lines". Reproduced here:
   `grep -rln "Revision8CoordinationTests" . --exclude-dir=.git` returns
   `tests/test_revision8_coordination.py` plus `.refactor/*` artifacts and **nothing under
   `docs/`**. The two config lines are real (`.refactor-baseline.json:56` = 4905,
   `pyproject.toml:242`). The conclusion ("no code reference, nothing to repoint") is correct and
   stronger than claimed, but a plan that cites evidence it did not reproduce in this tree is not
   auditable — restate it from this worktree.

## The shard simulation (independent reproduction)

`os.cpu_count()` on this host is **12**, so `shards = max(1, min(4, 12)) = 4`. Sorted
`tests/test_*.py` stems today: 68 modules; with the seven planned family modules: 75.
Round-robin membership matches plan §5 line 226 exactly:

```
shard 1 (19 mods): orphan_identity, successors
shard 2 (19 mods): append_schema, precedence
shard 3 (19 mods): registry_races          <- also holds test_revision8_coordination
shard 4 (18 mods): interruptions, rollback
```

For each shard I imported, in argv order and with `env -u PYTHONPATH`, every module preceding the
shard's first family module, then attempted `import codex_orchestrator`:

```
A) after the split, source file KEPT (75 modules):
   shard 1: RESOLVES  (first family orphan_identity, 14 modules of prefix)
   shard 2: FAILS     (first family append_schema,   13 modules of prefix)
   shard 3: RESOLVES  (first family registry_races,  14 modules of prefix)
   shard 4: FAILS     (first family interruptions,   13 modules of prefix)
B) after finalize DELETES the source file (74 modules):
   shard 1: RESOLVES  (first family precedence)
   shard 2: FAILS     (first family append_schema)
   shard 3: FAILS     (first family interruptions)
   shard 4: FAILS     (first family orphan_identity)
```

No prefix module failed to import in any case. Plan §0.1(c) is confirmed (shards 2 and 4 fail);
case (B) is **new** and is the argument that §0.4 must default to keeping the shell.
Note that shards 1 and 3 "resolve" only by accident — an unrelated earlier module in the same
round-robin bucket happens to insert `scripts` on `sys.path`. Any future test module added or
removed reshuffles the buckets. Option C (rely on `PYTHONPATH`) is therefore correctly rejected,
and for a second reason the plan does not give: **CI runs the Gate 1 cell**
(`.github/workflows/forge-ci.yml:27-52`, the committed `gate1` policy cell executed through
`run_bounded`) and sets **no** `PYTHONPATH` — its `sys.path.insert(0, "scripts/forge")` is
in-process in the driver and does not reach the subprocess environment. `PYTHONPATH` exists only
in `.claude/settings.local.json` of **this worktree** (`PYTHONPATH=scripts:scripts/forge`,
machine-local, excluded via `.git/info/exclude`); the main clone's
`/home/agents/foundry-of-zero/forge-plugin/.claude/settings.local.json` sets only
`DISCORD_STATE_DIR` and `TMPDIR`; `~/.claude/settings.json` sets only
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`; and the only `PYTHONPATH` in CI is
`guardrails.yml:24`, scoped to `lint-imports`.

Direct reproduction of §0.1(b), from the repo root:
`env -u PYTHONPATH python3 -c 'from codex_orchestrator import journal'` →
`ModuleNotFoundError: No module named 'codex_orchestrator'`;
`env -u PYTHONPATH python3 -c 'import tests._revision8_constants; from codex_orchestrator import journal'` → ok.

## Side-effect measurements (ruff 0.16.7, repo-wide `scripts tests system/fr223`)

| option | config | new findings |
|---|---|---|
| baseline | (committed pyproject) | `All checks passed!` |
| A | `lint.isort.known-local-folder=["codex_orchestrator"]` | **1** — `I001` at `tests/test_commitment_paths.py:20`; fix = insert one blank line at 21 |
| A' | A + `lint.isort.no-lines-before=["local-folder"]` | **1** — identical finding, identical fix, no other file touched (override confirmed live via `--show-settings`) |
| A'' | `lint.isort.sections={"orch"=["codex_orchestrator"]}` + `section-order=[future, standard-library, third-party, first-party, orch, local-folder]` | **1** — identical finding |
| **A'''** | `lint.isort.known-local-folder=["codex_orchestrator","commitment_paths"]` | **0** — `All checks passed!` |

Header order produced on stdin copies (no file written):
- committed config: `from codex_orchestrator import journal` **first**, `tests.*` after — the defect.
- A''': `from tests._cli_loader ... / from tests._revision8_constants ...` then
  `from codex_orchestrator import journal`; the real mixin dry-run header re-linted under A'''
  becomes `from tests._revision8_constants import RECORDED_AT, TOOLS` then
  `from codex_orchestrator import batch, journal`.

## What checks out (no finding)

- **Partition.** 81 inventory `test_*` methods, 81 placed, 81 unique, 0 duplicates, 0 missing,
  0 extra. Every family's `methods` equals its `methods_arg.split(",")` and is in **ascending
  source order**. `tests` counts match list lengths (10/16/9/12/3/17/14). The 31 mixin methods are
  exactly the 31 non-`test_` methods, also in source order. No family exceeds 30 tests.
- **Names.** All seven classes end in `Tests`; none of the seven class names and neither
  `Revision8Support` nor any of the eight module paths exists anywhere under `tests/`
  (`tests/_*.py` today: `_cli_loader.py`, `_fresh_eval_support.py`, `_revision8_constants.py`).
  `Revision8Support` contains no `Test`, lives in `_revision8_support.py` which matches neither
  the unittest `test*.py` pattern nor the lane's `test_revision8*.py`.
- **ID maps.** All seven `.refactor/idmap-revision8-<family>.json` have exactly
  `{"unittest","pytest"}`, N entries each matching the family's method count, 81 old IDs per
  collector in total, **injective**, **disjoint**, and every old ID present verbatim in
  `.refactor/tests-revision8-before.json` (1,908 IDs per collector, 81 for this class). Every new
  ID equals `<dest stem>.<class>.<test>` / `<dest path>::<class>::<test>`. The freeze has
  `shards: {}` and `pinned: {}` — no pinned IDs, no shard preservation to check. (Nit: the freeze
  records `settings.preset = "auto"`, not `"namespace"` as plan §8 item 3 and the task brief say;
  the *spellings* are the namespace ones, so nothing breaks.)
- **Refusal hazards (`move_methods.py`).** Class body non-`def` statements = the docstring only
  (`inventory.statements`), so `sibling class extraction requires class state to live in a shared
  support base` (move_methods.py:324) cannot fire. `tests calling other tests` = `{}` verified
  from `edges`/`calls`, and after C1 no helper remains in the class, so
  `sibling class would lose calls to remaining methods` (:326) cannot fire post-C1 (and *does*
  fire pre-C1, as designed). `mangled` is empty for all 112 methods; no `super()`, `__class__`,
  `type(self)` or literal `Revision8CoordinationTests` inside any body. Decorators exist only at
  `tests/test_revision8_coordination.py:65,69,101` (`@property`,`@property`,`@contextmanager`) —
  all on helpers, all in C1, and mixin shape carries them verbatim. No metaclass, no `__slots__`,
  no class decorator (:288). The class is a test class (:290). Destination files are new, so no
  name clash (:334) and no `target class clashes with source` (:344). The sibling copies
  `source_class.bases` (move_methods.py:407) = `(Revision8Support, unittest.TestCase)` after C1,
  and `dependency_imports(..., extra_names={names in cls.bases})` (:345-348) guarantees both
  `import unittest` and `from tests._revision8_support import Revision8Support` are emitted — the
  bases do resolve in each sibling.
- **`--format-imports` is `ruff check --select I --fix`** — move_methods.py:244-254, as the plan
  says, and it raises `Refusal('import formatting failed: ...')` rather than silently skipping.
- **Per-family `module_globals_used` and `helpers_used` are exactly right** — recomputed as
  `union(globals)` and `union(calls) ∩ helpers` over each family's methods; 7/7 match.
- **State.** No module-level mutable assignment and no `global` remains in the source after
  `42980e7` (header is imports + one `sys.path.insert` call). No test writes instance state
  (`writes` empty for all 81). `_record_number`/`_readmit_number` are owned by `setUp` and written
  only by `write_record`/`readmit`, all four in C1 — owner moves before every user.
- **Empty shell after C9.** A `unittest.TestCase` subclass with only a docstring plus
  `if __name__ == "__main__"` collects cleanly: `python3 -m unittest discover` → `Ran 0 tests` /
  `NO TESTS RAN`, exit 0; `pytest -q` → `no tests ran`, **no warning** (pytest never applies its
  `python_classes = ["Test"]` pattern to `TestCase` subclasses — which is also why the seven
  `Revision8*Tests` classes are collected by pytest despite not starting with `Test`).
  Caveat: bare `pytest` on a directory that collects nothing exits **5**; that is not how the lane
  or Gate 1 invokes it, but do not introduce a pytest-only per-module gate.
- **Temporary ruff globs (`c8cf01a`).** `"tests/test_revision8_*.py"` and
  `"tests/_revision8_*.py"` carry `["B023","C901","PLR0904","PLR0912","PLR0915","PLR1702","UP012"]`
  — the source entry minus `I001`, as brief §4 item 1 requires. They cover every planned
  destination; ruff unions per-file-ignore patterns, so `tests/test_revision8_coordination.py`
  keeps its own `I001` via `pyproject.toml:242`. No `E501`/`E402` is ignored, and none is needed:
  the source has no long lines under these rules and, under A''', the generated headers put the
  `codex_orchestrator` import in the header block with no preceding statement, so no `E402`.
- **Driver (`.refactor/revision8-run-cluster.py`, `0c05015`) against plan JSON and brief §6.**
  It reads `.refactor/plan-revision8.json` (`mixin.methods`, `families[].{name,methods,module,
  class}`) — schema matches. It does preflight (clean tracked tree, absent evidence paths, absent
  destination), re-collects IDs, **regenerates the id map and refuses a mismatch with the
  planner's pre-written file** (good: the planner's maps are checked, not trusted), dry-runs,
  freezes `snapshot_bodies.py snapshot tests`, applies, runs `verify.sh --strict-bodies` without
  `--fast`, runs the repository's own `scripts/check_file_length.py tests`, runs the
  bare-`PYTHONPATH` import proof, records `commit/snapshot/manifest/test_snapshot/id_map` in
  `.refactor/decompose-records-revision8.json`, and commits only on PASS. That is brief §6's list.
  It does **not** run the Gate 1 cell or take the host lock — correct, those are wave-close/finalize.
- **Commit order.** `family_order = [orphan_identity, append_schema, registry_races, precedence,
  rollback, interruptions, successors]` is monotonically decreasing in size and valid: no test
  calls another test, and every helper is inherited from the mixin, so the families are mutually
  independent. One target per commit, one tier-1 manifest per commit, `max_outputs = 1` per mover
  call — satisfied.
- **Fallback seams.** Every family lists one; none is needed (max corrected size 819 < 1,000).
  `interruptions` at 3 tests / 556 lines is correctly justified: its three tests are 185/205/166
  code lines, so no seam under 500 keeps two together.
- **Scope creep.** Apart from finding 2 (the `tests/test_commitment_paths.py` blank line), the
  plan proposes no rename, no new abstraction, no body edit and no second hand-written commit.
  §1 "delete first: none" is right.

## ADVISORY

- §6 says "`nonlocal`: 29 occurrences"; `grep -c nonlocal tests/test_revision8_coordination.py`
  is **28**, and the 28 line numbers the plan lists are correct (385 in a helper + 27 in test
  bodies). Cosmetic, but it is a counted claim.
- §2 "`hubs (post-peel)`" and "clusters: 19 after peeling" are taken verbatim from the stale
  inventory; harmless, but they inherit the same provenance problem as finding 1.
- Option **D** (make `tests/_revision8_constants.py` re-export `batch`/`journal` after its
  `sys.path.insert`, so the mover copies `from tests._revision8_constants import journal` into each
  family and the ordering becomes irrelevant) is technically sound and needs no `pyproject.toml`
  change — but it requires amending the already-committed hand-written constants commit `42980e7`
  **and** hand-editing the source's import line so the mover re-binds `journal`. That is a second
  hand-written commit and a hand edit to the target file's header outside the mover, i.e. brief
  §8 item 4 twice over. Do not take it tonight; record it as the cleaner long-term shape.
- Option **B** (teach the mover to carry the source's `sys.path.insert` preamble and the
  `# noqa: E402` pattern into the destination) is the correct plugin fix and should be a bead in
  the refactor-python repo; it is out of this session's hands and would stop the wave tonight.
- The driver's `collect_tests.py snapshot --start tests --out ...` passes no preset/pattern flags.
  The freeze was taken with `{"start":"tests","top":"tests","preset":"auto","pattern":"test*.py",
  "pytest":true}`; if any of those are not the tool defaults, the per-cluster compare will diff on
  settings rather than IDs. Cheap to confirm once before C1 by diffing the `settings` block of a
  fresh snapshot against `.refactor/tests-revision8-before.json`.
- `.refactor-baseline.json:56` grandfathers the source at **4905** while it is now **4903** code
  lines; the guard only forbids growth, so this is inert, but finalize should drop the line rather
  than update it.
- Debt correctly declared and tracked: mixin 31 methods > `class_target` 30; mixin 539 >
  `module_target` 500; seven families over 500; three tests over 150 code lines; the source shell.
  All are baseline/follow-up items, none is a new violation introduced by the move. The plan
  should name the follow-up bead ID for the mixin split rather than "follow-up bead".
- Both `verify.sh`'s `ruff check tests` and CLAUDE.md's finish command
  `ruff check scripts tests system/fr223` must be green; state in §5 that the config commit is
  gated on both, since it is the one commit whose blast radius is the whole repository.

## Recommendation for an unattended session tonight

Fix findings 1 and 4..6 as plan text (they are one editing pass and change no artifact), then
open the wave with a **config-only prep commit that adds
`[tool.ruff.lint.isort] known-local-folder = ["codex_orchestrator", "commitment_paths"]` to
`pyproject.toml` and nothing else** — option A''' — *before* C1, and re-run the C1 dry run under
it. That commit is the same class of change brief §4 item 1 already mandates for this session
(config-only, `pyproject.toml`, before any move; `pyproject.toml` is `config`, not `control`, in
`forge-project.md`'s category table, so no binding review is triggered), it is measured to
introduce **zero** new findings anywhere in `scripts tests system/fr223`, it edits no test and no
production file, and it realises the intent the brief itself states in §4 item 2 — "so the support
module's copied `codex_orchestrator` import resolves without PYTHONPATH" — which the mover's
mandatory `--format-imports` pass silently defeats. Disclose it in the handover and to both
reviewers as a fourth, measured deviation alongside the three in brief §11, exactly as the
hand-written constants commit was disclosed. If the session judges that a repo-wide isort
setting is *not* within brief §4 item 1's enumeration (per-file-ignore globs and baseline entries
only), then no in-brief fix exists, option A costs an out-of-scope test edit (§8 item 4), option C
is refuted by the shard simulation and by CI, and options B and D are stops — in that case commit
**nothing beyond C1**, write `.refactor/STOPPED-revision8.md` with the shard table and the four
option measurements above, and hand over. Do not commit C2 with the current baseline numbers
under either branch, and do not delete the source shell at finalize without the operator.
