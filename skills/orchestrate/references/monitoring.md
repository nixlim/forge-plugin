# Monitoring Codex Agents

Use the bundled tools for compact status snapshots. They parse event streams locally; do not copy
raw logs into Claude's context unless a focused inspection is needed for an ambiguous or failed
agent.

## Headless Codex

<!-- forge: modified from upstream — ordered, routed, detached launches with PID evidence -->

Create the next numbered execution under its named agent:

```text
codex-impl-01/execution-01/
  prompt.md
  events.jsonl
  handoff.md
  pid
```

Prepare it in this order: create the execution directory; assemble and write `prompt.md`; create an
empty `events.jsonl`; append `execution`; launch. Follow the canonical
[prompt-construction contract](../SKILL.md#forge-isolation-and-prompt-construction): in exact order,
use the applicable plugin role template, the `agent-project-context` region from
`git -C <worktree> show HEAD:forge-project.md`, the exact bytes from
`git -C <worktree> show HEAD:.forge/history/gotchas.md` when that object is present, and the concrete
task assignment. Both committed inputs come from the same absolute `<worktree>` recorded below and
passed to `-C`; never use either working-tree file or a rendered agent definition. Save the
assembled prompt verbatim before the journal entry.

The entry records the absolute `worktree`, full `head`, attached `branch` when present, role, and
the actual model and effort passed at launch. Resolve the recorded Git values from the same path
passed to `-C`:

```bash
git -C <worktree> rev-parse --show-toplevel
git -C <worktree> rev-parse HEAD
git -C <worktree> branch --show-current
```

Immediately before launch, require
`bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh"` to exit 0. On halt, launch no new work,
perform no reintegration, report, and wait.

Fresh implementers use model `gpt-5.6-sol`, effort `ultra`, and sandbox `workspace-write`. Launch
in a detached process group. Redirect targets are literal absolute paths, not variables:

```bash
set -m
nohup codex exec --json \
  --output-last-message /absolute/path/to/run/codex-impl-01/execution-01/handoff.md \
  -s workspace-write \
  -c approval_policy=never \
  -c model="gpt-5.6-sol" \
  -c model_reasoning_effort="ultra" \
  -C /absolute/path/to/codex-impl-01-worktree \
  - \
  < /absolute/path/to/run/codex-impl-01/execution-01/prompt.md \
  > /absolute/path/to/run/codex-impl-01/execution-01/events.jsonl &
launch_pid=$!
disown "$launch_pid"
launch_pgid="$(ps -o pgid= -p "$launch_pid" | tr -d ' ')"
{
  printf '%s\n' "$launch_pid"
  printf '%s\n' "$launch_pgid"
  date -u '+%Y-%m-%dT%H:%M:%SZ'
} > /absolute/path/to/run/codex-impl-01/execution-01/pid
```

`set -m` may be replaced with `setsid` where available, but keep `nohup ... &` and `disown`.
Never use `--ephemeral` or a harness-managed background task. Before arming the monitor, ensure
`pid` contains exactly PID, PGID, and a UTC ISO-8601 launch timestamp on three lines.

Require Codex to end every execution with this concise handoff shape:

```markdown
## Status

## Summary

## Files Changed

## Claims / Findings

## Commands Reported

## Caveats / Blockers
```

Extract the last completed agent message from events only when normal handoff capture failed.

Never resume an implementation session. A new implementer task always gets a fresh named agent and
native session.

The sole sanctioned resume is a targeted confirmation round for the same reviewer. Use the next
execution directory for that reviewer and its recorded `session_id`. Prepare and journal it in the
same order, assembling committed context and optional gotchas from the preceding execution's
recorded worktree and its current `HEAD`, then launch it detached. The resume command has no `-C`;
the working directory comes from the resumed session:

```bash
set -m
nohup codex exec --json \
  --output-last-message /absolute/path/to/run/codex-review-01/execution-02/handoff.md \
  -s read-only \
  -c approval_policy=never \
  -c model="gpt-5.6-sol" \
  -c model_reasoning_effort="high" \
  resume <session-id> - \
  < /absolute/path/to/run/codex-review-01/execution-02/prompt.md \
  > /absolute/path/to/run/codex-review-01/execution-02/events.jsonl &
launch_pid=$!
disown "$launch_pid"
launch_pgid="$(ps -o pgid= -p "$launch_pid" | tr -d ' ')"
{
  printf '%s\n' "$launch_pid"
  printf '%s\n' "$launch_pgid"
  date -u '+%Y-%m-%dT%H:%M:%SZ'
} > /absolute/path/to/run/codex-review-01/execution-02/pid
```

Read the absolute `worktree` from the preceding execution and record it with the same `session_id`.
Inspect its current HEAD and branch for the new entry. The prior `head` is a snapshot, so do not check out or reset to it merely because the worktree advanced.

## Agent State And Monitor

<!-- forge: modified from upstream — bounded re-arm and explicit ambiguity protocols -->

Use `state` for a compact agent snapshot:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" state <session-id> \
  --file <events-jsonl> --json
```

After context loss, call `state` again. Do not persist parser positions in the journal.

Monitor an active run or explicit stream:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" monitor \
  --repo <repo> --run-id <run-id>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" monitor \
  --log <events-jsonl> --fail-on-agent-failure
```

Always select the target with `--run-id` plus its repository or with `--log`.

The monitor is read-only and emits completion, failure, unknown-format, missing-stream, or stale
notifications. While any execution is in flight, re-arm it no later than 60 minutes after the last
arm or exit: stale and unknown targets are terminal to one monitor invocation and are no longer
being watched. Between monitor cycles, run the halt checkpoint. A halt forbids new work and
reintegration; report it and wait.

Treat `codex_agent_stale` as ambiguous. Before appending any `execution_result`, check the events file mtime, read PID and PGID from the execution's three-line `pid` file and verify them with `ps`,
then inspect the handoff and worktree. For example:

```bash
execution_pid="$(sed -n '1p' /absolute/path/to/execution-01/pid)"
execution_pgid="$(sed -n '2p' /absolute/path/to/execution-01/pid)"
ps -p "$execution_pid" -o pid=,pgid=,stat=,etime=,command=
```

Compare the observed PGID with `execution_pgid`. Never conclude failure from staleness alone. If
the group is alive, append no result and re-arm the monitor. After a machine-sleep gap whose
wall-clock jump exceeds the stale threshold, run `state` for every in-flight target before trusting
any stale notification emitted across the gap.

For `codex_agent_unknown`, inspect the actual event vocabulary:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" \
  state --dump-event-types <session-id> --file /absolute/path/to/execution-01/events.jsonl
```

Do not infer agent status from a low-confidence parse. Surface the format incompatibility and
observed event types to the user.
