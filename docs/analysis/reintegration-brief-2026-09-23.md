# Reintegration brief 2026-09-23: the three test-split branches (sessions 8, 6, 4)

> Tracked 2026-09-23 as the operator-issued brief **exactly as issued**; historical record of the protocol the
> main-clone Forge session followed that evening, not a live instruction set. Notes from the execution are recorded
> here rather than edited into the text: (a) branch 2 (`refactor/split-test-revision9-cli-surfaces`) was not on
> `origin` when branches 1 and 3 landed, so the order run was 1 then 3, with the spec Revision 15 chain landing in
> between; (b) both branches were rebased onto the current `origin/main` *before* the pre-lock gates (the V1
> precedent), so each locked rebase was a pure fast-forward and no in-lock re-run was needed; (c) one finding the
> section-2 dry merge could not anticipate: the isort `known-local-folder` ruling re-sorts an import block in
> `tests/test_vocab_readers.py`, a module 0.6.13 added after the ruling was measured at `69bc28d` — the fix rode
> with branch 1 as its own commit through the Forge commit chain (disclosed in the branch's changelog entry), so the
> section-2 sentence "a finding here means a wrong resolution" has this one exception; (d) the section-1 step-6
> progress-log rows for both branches land together in one docs chain after branch 3, not one per branch.

For the Forge session in the MAIN clone `/home/agents/foundry-of-zero/forge-plugin` (Forge ON,
Fable, plugin 0.6.12 or later). Precedents: forge-plugin-ah1a (MergeEngine, 657f6c1) and
forge-plugin-r80b (Engine, d885f97); the shared protocol is docs/analysis/refactor-plan-2026-09-19.md
section 2 and the handover beads below. This brief adds only what is specific to landing three
sibling branches that share a base.

## 0. What lands, in this order

| # | Handover bead | Branch | Reviewed source tip | Branch tip (review records) | Session bead |
|---|---|---|---|---|---|
| 1 | forge-plugin-4p7p | refactor/split-test-revision8-coordination | 97d4d60 | 94df0b8 | forge-plugin-25ms |
| 2 | forge-plugin-l4f4 | refactor/split-test-revision9-cli-surfaces | ea0698b | cb2a37b | forge-plugin-kzu0 |
| 3 | forge-plugin-kyt1 | refactor/split-test-revision9-coordination | f20b8e8 | fee6e07 | forge-plugin-6g67 |

All three are linear on BASE 69bc28d, authored in a separate clone with Forge disabled under
docs/analysis/refactor-overnight-brief-2026-09-23.md, reviewed by Codex (gpt-5.6-sol) and the
plugin's Fable reviewer with consensus rounds recorded under `.refactor/*<name>*`. None changes a
production file, a spec sentence or an FR-230 subject: `git diff --stat 69bc28d..<tip> -- scripts
docs/specs .forge` is empty on each. Read each handover bead in full before its merge; the
"NON-MOVE EDITS TO DISCLOSE" list on the bead is the Gate 3 review context for that branch.

`origin/main` has moved since BASE: 679c651 (release 0.6.13, the routing vocabulary chain V).
Its changes touch `pyproject.toml` (version line only), `CHANGELOG.md` (the `[Unreleased]` body
moved under `## [0.6.13]`, leaving an empty `[Unreleased]`), production and test files none of
the three branches touch. So every one of the three rebases rewrites the candidate
(`CANDIDATE_REWRITTEN=1`) and the first one already conflicts in `CHANGELOG.md`.

## 1. Per branch: the same six steps

1. In the main clone: `git fetch origin`, then
   `git worktree add .worktrees/<branch-stem> -b <branch> origin/<branch>` (the same layout the
   ah1a and r80b sessions used; `.worktrees/` is git-excluded). `cd` there. Precondition: the
   worktree is clean and `git rev-parse HEAD` equals the branch tip in the table.
2. Run `/forge:worktree-merge` from that worktree exactly as the skill says (policy from
   `git show HEAD:forge-project.md`, cells as `bash -c <cell> forge`, session identity CLAUDE_PID,
   never export FORGE_SESSION_PID, detach long verbs with `nohup setsid`, no backticks or
   dollar-parens in commit messages, zsh no-match globs abort a whole `&&` chain so wrap launches
   in `bash -c`, the lock-owning shell must outlive tool calls: a detached keeper holding the
   release FIFO writer, the wrapper waits for EOF after the release frame).
3. Expected tier and gates (from the beads): `tests/**` is not a control path; `pyproject.toml`,
   `.refactor-baseline.json` and `CHANGELOG.md` are config; no reviewer-facing eval trigger fires
   (tests/fixtures untouched, skills/hooks/docs/specs untouched). Gate 1 is the full 4-shard
   discovery WITHOUT PYTHONPATH exactly as the committed cell runs it (the main clone's local
   settings set none; every new module bootstraps `scripts/` through its `tests._<name>_constants`
   module under the isort ruling). Expect more than 1,908 tests now that 0.6.13 added its own.
   Gate 2 includes `tests.test_repo_conformance` (every evidence file under `.refactor/` matches a
   file category) and `tests.test_migration` (the `.refactor/` carve-out landed on each branch).
4. The locked rebase onto `origin/main` WILL stop on conflicts. Resolve only the named paths,
   stage each explicitly, `git rebase --continue 8<&- 9>&-`, keep the lock, and record that
   conflicts were resolved (the skill then makes Gate 3 mandatory on the post-rebase candidate
   over `INTEGRATED_BASE...INTEGRATED_HEAD`, and Gate 4 must name the new SHA). Resolution rules,
   section 2. Never resolve by dropping a lane's entry, never edit anything outside the
   conflicted hunks, never create a merge commit.
5. Gate 4: present the integrated full SHA and wait for the operator's approval naming it; the
   operator is present for these merges. Push is the skill's `HEAD:main` fast-forward inside the
   lock. After the push: verify `origin/main` equals the pushed SHA.
6. Close-out for that branch: comment and close the handover bead and the session bead with the
   merged SHA and the old-to-new SHA map of the rewritten candidate (the review records name the
   pre-rebase tips; the map keeps them citable); append the bead's PROGRESS-LOG ROW to
   docs/analysis/refactor-plan-2026-09-19.md section 5 and land that docs-only change through
   `/forge:commit` (standard tier) before starting the next branch, so the next rebase sees it;
   remove the main-clone worktree `.worktrees/<branch-stem>`; leave the remote branch in place
   (operator call, as for the earlier sessions). The lane worktrees in the refactor clone are
   removed by the operator afterwards:
   `git -C /home/agents/foundry-of-zero/forge-plugin-refactor worktree remove ../forge-plugin-refactor-wt/<lane>`.

Then the next branch from step 1, against the new `origin/main`.

## 2. Conflict resolution rules (measured 18:15 with a dry merge of branches 1 and 3)

The three branches overlap on exactly four files: `CHANGELOG.md`, `pyproject.toml`,
`.refactor-baseline.json`, `tests/test_migration.py`. Git merges the last two cleanly (disjoint
baseline keys; the carve-out is the identical one-line hunk on all three). The first two conflict:

- **CHANGELOG.md.** Each branch wrote its one entry under `## [Unreleased]` when that section
  held the MergeEngine entry; main has since moved that entry under `## [0.6.13]`. Resolution:
  the lane's entry goes under the now-empty `## [Unreleased]` `### Changed` heading, above
  `## [0.6.13]`; nothing under `[0.6.13]` changes; a later lane's entry is appended below the
  earlier lane's under the same heading. The changelog gate is satisfied by the added entry.
- **pyproject.toml.** Branch 1 adds `[tool.ruff.lint.isort] known-local-folder = [...]` (the
  11:30 ruling) and its per-module `per-file-ignores` entries; branches 2 and 3 add the SAME
  isort section text and their own entries. Resolution: exactly ONE isort section with the
  four-name list `["codex_orchestrator", "codex_orch_tools", "forge_cli", "commitment_paths"]`;
  the union of all lanes' per-file-ignores entries, each lane's source-file entry as that lane
  shrank it, entries kept in the file's existing sorted order; the `version` line as on main.
  After resolving, before continuing the rebase, `ruff check scripts tests system/fr223` must
  be clean and `python3 scripts/check_file_length.py` must report every file within budget; a
  finding here means a wrong resolution, not a new lint problem.
- **.refactor-baseline.json** and **tests/test_migration.py**: expect no conflict; if git reports
  one, the resolution is the union of entries and the single carve-out tuple
  `("docs/design/", "docs/specs/", ".refactor/")`.

If any conflict appears outside these four files, abort the rebase, release the lock, leave the
worktree, and report it: it means a branch is not what its bead says.

## 3. What Gate 3 should know (per branch, from the beads)

- Branch 1 (revision8): Codex REJECT 4 blocking + 3 advisory; consensus: B2 AGREE advisory (direct
  execution of a test module is not a supported surface; 30 BASE modules already fail it), B3 and
  B4 RETRACT, B1 REFUTED by the Fable reviewer; Fable APPROVE. Non-move edits: hand-written
  `tests/_revision8_constants.py`, isort ruling, carve-out ruling, temporary globs replaced by
  measured entries, provisional baseline entries pinned. Debt bead forge-plugin-7pzp (eight
  modules 500..1,000, the mixin at 31 methods, the empty source shell, the shell's I001 entry).
- Branch 2 (revision9 cli-surfaces): Codex REJECT 1 blocking + 3 advisory; consensus: B1 AGREE
  advisory (the driver's plain commits outside the Forge chain and the single finalize CHANGELOG
  entry are the lane protocol, same adjudication as sessions 1, 2 and lane B1); Fable APPROVE.
  Non-move edits: hand-written `tests/_revision9_cli_constants.py` (the loader block: CLI, CORE,
  RUNTIME, ENGINE, CANDIDATE, CLI_FIXTURE_SUPPORT, key), config prep a30d535 carrying both rulings
  as the same hunks lane B1 carries, globs replaced, baseline pinned. 15 helpers in the mixin
  `tests/_revision9_cli_support.py` (674), 62 tests in five modules 570..966; source 5,456 to
  1,229 (the eight retained classes; over the ceiling by scope, pinned). Debt bead forge-plugin-by61.
- Branch 3 (revision9 coordination): Codex REJECT 2 blocking, both AGREE-downgraded in consensus
  (duplicated sys.path insert prescribed by the brief; import removals from a module with zero
  importers); Fable APPROVE. Non-move edits: hand-written `tests/_revision9_coord_constants.py`,
  isort ruling, carve-out ruling, globs replaced, baseline pinned. The `unittest.skipUnless` test
  stays on the source class; Binding and MergeTransitionGrammar classes remain in the source
  (forge-plugin-z50i). Debt bead forge-plugin-z50i.
- Common to all three: every mover call used `--import-root "$PWD"` so destination imports read
  `from tests._<name>_... import`; every family module was proven to import standalone without
  PYTHONPATH; the evidence directory shipping with plugin installs is forge-plugin-xlt7 and not a
  merge input.

## 4. Stop conditions

A gate failing after one rerun; a conflict outside the four files; a Gate 3 BLOCK the reviewer
does not withdraw with evidence; a lock the session cannot obtain (report the holder hint, never
delete the lock directory); any mismatch between a bead's tip and `origin/<branch>`. On a stop:
leave the worktree and branch intact, release the lock by exiting the owning shell, comment the
handover bead with the gate output, and report. Never force-push, never rewrite `origin/<branch>`,
never delete a remote branch.
