# Forge Operating Model

<!-- forge: modified from upstream — condensed for plugin delivery and re-rooted to plugin-local paths -->

Forge uses a fail-closed Decompose, Delegate, Verify, Review, Re-verify, Commit, and
Reintegrate (DVRR) operating model. Evidence, not an agent's confidence, advances work.

## Required sequence

1. **Decompose.** Define acceptance criteria, owned files, dependencies, risk, and the exact
   validation commands before implementation starts.
2. **Delegate and isolate.** Give parallel tasks disjoint file ownership or isolated worktrees.
   Serialize overlapping work. Never run more than 10 concurrent Codex executions in one run.
3. **Verify.** Run the target repository's configured gates in the orchestrator environment.
   Missing, malformed, skipped, or inconclusive evidence is a failure.
4. **Review.** Invoke `review-final` with
   `${CLAUDE_PLUGIN_ROOT}/rules/review-constitution.md`. Its PASS/BLOCK verdict is binding, and
   the reviewer remains independent and read-only.
5. **Revise.** Route a BLOCK and its findings to a fresh implementer, rerun Gates 1 and 2 in the
   orchestrator environment, rerun any other affected validation, and invoke a fresh-context
   review. After a defect fix, the affected end-to-end verification must pass twice consecutively
   as two separate verification records. Stop after eight review iterations; if no PASS exists,
   record every outstanding finding and why it remains, escalate to the user, and do not commit
   or merge.
6. **Commit.** Check the operator halt, acquire the shared commit lock, verify that the staged
   diff still matches the reviewed diff, commit only explicit paths, and release the lock on
   success or failure. Use `${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh`,
   `${CLAUDE_PLUGIN_ROOT}/scripts/forge/acquire-commit-lock.sh`, and
   `${CLAUDE_PLUGIN_ROOT}/scripts/forge/release-commit-lock.sh`.
7. **Reintegrate.** Stop the execution, save its handoff, inspect its diff, re-verify against the
   current integration baseline, and only then integrate. Never reintegrate while halted.

## Fail-closed and bounded operation

Repository-local transient state belongs under `.forge/tmp/`. Long-running loops check the
operator halt between iterations, retain enough evidence to resume safely, and use explicit
budgets. A failed tool, unavailable reviewer, missing gate, stale evidence, or exhausted budget
stops the transition and is surfaced; it never becomes an implicit pass.
