# Consensus round: revision9 cli-surfaces test-split reviews (2026-09-23)

Reviewed source tip: `ea0698b` (BASE main `69bc28d`), branch `refactor/split-test-revision9-cli-surfaces`.
Codex (gpt-5.6-sol, effort ultra, thread `01a0cf38-0e9c-7b31-af4f-35fac0742f57`): REJECT with 1 BLOCKING + 3
ADVISORY (`codex-review-revision9-cli.md`). Fable refactor-reviewer: APPROVE, no blocking; B1 CONFIRMED as fact and
REFUTED as blocking, A1..A3 CONFIRMED as advisory (`fable-review-revision9-cli.md`). One follow-up on the Codex
thread for the disputed finding:

| finding | Codex answer | record |
|---|---|---|
| B1 the driver commits with plain `git commit` outside the Forge commit chain; 16 intermediate commits carry no same-candidate CHANGELOG entry | AGREE: advisory ("a disclosed lane-protocol property, not an unauthorized bypass": the operator brief prescribes the Forge-off clone, plain commits, one branch-level changelog entry at finalize and reintegration through the Forge worktree-merge chain; the plan's own protocol records the same; sessions 1 and 2 and lane B1 were adjudicated the same way; `git log 69bc28d..ea0698b -- CHANGELOG.md` shows the finalize entry) | `consensus-revision9-cli-B1.md` |

Advisories, all accepted and recorded in the handover bead: A1 eight names (`ROOT`, `CLI_PATH`, `ENGINE`,
`patch_chain_core`, `datetime`, `os`, `stat`, `warnings`) are no longer importable from the source module (no
importer at BASE or HEAD; test-module namespaces are not an API; same class of finding as lane B1's B3); A2 the
finalize Gate 1 logs were untracked at review time (tracked by the records commit that follows this file; runs 2
and 3 are the consecutive 1,908-test passes, run 1 errored one real-time test at load 3.5 and the three tests that
failed across the wave-close and finalize runs pass standalone on the tip); A3 the plan names
`mixin-revision9-cli.json` where the driver wrote `mixin-revision9-cli-mixin.json`, and the finalize commit message
says eight cluster records where the JSON holds six (mixin + five families): both are documentation slips, corrected
here, not in the plan (no rewrite of committed evidence).

Outcome: both reviewers agree there is no blocking finding on `ea0698b` (Codex: B1 AGREE advisory; Fable: APPROVE). The review-records commit that follows this file tracks every artifact named above; the source tree is identical to `ea0698b`.
