# Operator Halt

<!-- forge: modified from upstream — condensed and re-rooted to plugin scripts and state -->

The operator can stop all Forge activity with `AGENT_HALT` at the main-checkout root, or stop a
scope with `AGENT_HALT_<scope>` such as `AGENT_HALT_commit`. The global sentinel applies to every
session and worktree. Only the operator or user may clear a sentinel; agents must never create,
delete, move, ignore, or bypass one without explicit user direction.

Before new work, subagent launch, commit, push, reintegration, or any irreversible/external action,
run `${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh` with the relevant scope. Long-running loops
also check between iterations. The check resolves the shared main checkout and appends detections
to `.forge/tmp/halt-audit.log`.

When halted, stop starting new work; safely finish or abandon the current atomic step; do not
commit, push, or reintegrate; report the sentinel and scope to the user; and wait for the operator
to clear it. A check failure is never skipped or treated as approval.
