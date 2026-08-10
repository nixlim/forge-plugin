# Commit Locking

<!-- forge: modified from upstream — condensed and re-rooted to plugin scripts and .forge state -->

All sessions and worktrees for a repository share `.forge/tmp/commit-lock`. The lock contains
`<PID> <TIMESTAMP>` and is acquired atomically. Export the stable owner PID as
`FORGE_SESSION_PID`; shell subprocess PIDs must not become separate owners.

## Protocol

1. Run `${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh commit`.
2. Run `${CLAUDE_PLUGIN_ROOT}/scripts/forge/acquire-commit-lock.sh` before the commit workflow's
   mutation phase. If another live PID owns the lock, poll every 2 seconds for at most 300 seconds.
3. If the recorded PID is dead, treat the lock as stale, record the takeover, remove it safely,
   and retry atomic acquisition. Malformed ownership data fails closed.
4. Hold the lock across staged-diff hash re-verification and the entire commit attempt. Do not hold
   it across the preceding adversarial review loop.
5. Always run `${CLAUDE_PLUGIN_ROOT}/scripts/forge/release-commit-lock.sh` on success, failure, or
   interruption. Release is owner-only and idempotent; a non-owner must not delete the lock.

Timeout, ownership mismatch, halt detection, staging drift, or an unverifiable stale owner stops
the commit. Manual lock removal requires explicit operator direction unless the acquisition script
has proven the recorded PID dead.
