# Monitoring Routed Agents

`forge launch collect` is the lifecycle authority for typed implementer and plan executions;
eligible stream-backed typed launches may also be watched observationally. For reviewer prose
sessions, use the bundled tools for compact status snapshots; they parse event streams locally, so
do not copy raw logs into Claude's context unless a focused inspection is needed.

## Launching And Collecting Executions

<!-- forge: modified from upstream — routed launch artifacts and provider stream monitoring -->

### Typed Implementer And Plan Launches

Below, `forge` is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py"`, the same alias the commit
skill uses. `<repo>` is the absolute repository root, and every path argument is absolute. A
successful start receipt reads `launch started for execution-NN`; its `next_required_step` is the
exact collect command to run next.

`forge launch` owns implementer and plan launches; the commands, the outcome table, and the prompt
layout are canonical in
[Forge Execution Preparation And Launch](../SKILL.md#forge-execution-preparation-and-launch).

Forge creates the next numbered typed execution under its named routed agent. Read its artifacts as
follows:

- `prompt.md` is the exact stdin bytes.
- `events.jsonl` and `stderr.log` are the provider streams, capped at 16 MiB and 1 MiB.
- `launch.json` is the owner-only `forge-launch-marker/1`.
- `identity.json` and `completion.json` hold the wrapper identity and terminal completion;
  `completion.json` appearing is the wake signal.
- `handoff.md` is the redacted final message.
- `pid` is the legacy three-line sidecar, informational only.

For Codex, `prompt.md` and stdin start with the applicable plugin role template, followed by the
committed `agent-project-context`, optional committed gotchas, and the concrete task assignment.
For Claude, the applicable committed role body is passed only through the exact FR-245 argv flag
and is not part of `prompt.md`; Claude `prompt.md` and stdin start with the exact bytes
`\n--- committed agent-project-context ---\n`, followed by the same committed context, gotchas, and
task assignment. Both committed inputs come from the recorded absolute worktree at its committed
HEAD; never use working-tree prose or a rendered agent definition.

The generated owner record includes the absolute worktree, full HEAD, actual provider/model/effort,
prompt/events/handoff paths, `mode: detached`, `launch_marker`, and the route trio `sandbox`,
`route_source`, and `route_sha256`, copied from that role's frozen run snapshot; do not reconstruct
or omit it. Never write `unrecorded` for a new snapshot-backed run. A reviewer-specific prose record
written outside the typed lane may omit the trio; if it carries any of `sandbox`, `route_source`, or
`route_sha256`, it must carry all three, equal to that role's frozen run snapshot in
`run_started.route`, which Forge accepts only when the launched provider, model, and effort equal
that frozen route.

Every committed implementer and plan role template already requires this six-heading handoff; do
not restate it in the brief. After collect, confirm that `handoff.md` carries these headings in
order, and record a missing heading as a verification finding:

```markdown
## Status

## Summary

## Files Changed

## Claims / Findings

## Commands Reported

## Caveats / Blockers
```

Extract the last completed agent message from events only when normal handoff capture failed. Never
resume an implementation session; start every corrected or follow-up implementer or plan task as a
fresh typed execution.

Run-level monitoring follows typed Codex and typed Claude launches only when their owner record
names a stream-JSON `events` file. Subagent-mode Claude records have no events file and are not
monitor targets. For eligible typed launches, monitor notifications are observational: `forge
launch collect` and `forge launch cancel` remain the only lifecycle authorities.

### Reviewer-Only Confirmation Outside The Typed Lane

The sole sanctioned resume is a targeted confirmation round for the same reviewer. The session
prepares it by hand, so follow FR-036 exactly: create the reviewer's next execution directory,
write `prompt.md` (committed context and optional gotchas read from the preceding execution's
recorded worktree at its current `HEAD`), create an empty `events.jsonl`, append the `execution`
entry with the recorded `session_id`, then launch. Immediately before launch, require
`bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh"` to exit 0; on a halt, launch nothing,
report the sentinel, and wait. Never use `--ephemeral` or a harness-managed background task. The
resume command has no `-C`; the working directory comes from the resumed session:

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
Inspect its current HEAD and branch for the new entry. The prior `head` is a snapshot, so do not
check out or reset to it merely because the worktree advanced.

## Agent State And Monitor

<!-- forge: modified from upstream — bounded re-arm and explicit ambiguity protocols -->

Use `state` for a compact reviewer-session snapshot:

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

Run-level monitoring may follow the eligible typed streams described above, but stale or unknown
notifications never determine a typed execution's lifecycle; collect does. The ambiguity protocol
below applies only to reviewer prose sessions.

While any reviewer prose session is in flight, re-arm the monitor no later than 60 minutes after
the last arm or exit: stale and unknown targets are terminal to one monitor invocation and are no
longer being watched. Between monitor cycles, run
`bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh"`. A halt forbids new work and
reintegration; report it and wait.

Treat `codex_agent_stale` as ambiguous. Before appending any `execution_result`, check the events
file mtime, read PID and PGID from the execution's three-line `pid` file, verify them with `ps`, and
inspect the handoff and worktree. For example:

```bash
execution_pid="$(sed -n '1p' /absolute/path/to/execution-01/pid)"
execution_pgid="$(sed -n '2p' /absolute/path/to/execution-01/pid)"
ps -p "$execution_pid" -o pid=,pgid=,stat=,etime=,command=
```

Compare the observed PGID with `execution_pgid`. Never conclude failure from staleness alone. If
the group is alive, append no result and re-arm the monitor. After a machine-sleep gap whose
wall-clock jump exceeds the stale threshold, run `state` for every in-flight reviewer target before
trusting any stale notification emitted across the gap.

For `codex_agent_unknown`, inspect the actual event vocabulary:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" \
  state --dump-event-types <session-id> --file /absolute/path/to/execution-01/events.jsonl
```

Do not infer agent status from a low-confidence parse. Surface the format incompatibility and
observed event types to the user.

## Operational Rules

### Long-Running Commands (FR-034 Generalised)

Run any non-provider command whose runtime can exceed a session's patience (full test suites, long
builds, multi-minute verification) detached in its own process group rather than as a
harness-registered background shell, which the session layer may reap: `set -m` (or `setsid`),
`nohup <command> &`, `disown`, with every redirect target a literal absolute path (FR-035), and
watch the output file rather than the shell. This was observed twice in one run: background
test-suite invocations were killed mid-run while detached executions continued. Implementer and
plan providers are launched only by `forge launch`, and reviewer launches follow `review.md`.

Never re-run an identical launch after an unexplained death. Check first whether the death was
specific to the harness-registered wrapper or to the work itself: a detached sibling that is still
alive answers the question immediately.

### Reading Silence Correctly

A monitor timeout is not a signal. Monitor windows are bounded (an hour is typical); an expired
window means the watcher's clock ran out, never that the work stopped. Re-arm and continue.

For a typed execution, a `still running` collect refusal is the liveness answer. For a reviewer
prose session, judge liveness on process state plus event mtime together, and treat a second
consecutive long gap with no suite completion as worth investigating rather than the first.

Do not run a full suite concurrently with a review subagent or another suite. Contention stretches
runtimes far enough to trip timing-sensitive assertions, producing failures that do not reproduce
when re-measured alone. FR-122 requires the re-measurement; this is the usual cause.

### Command-Shape Constraints

Two constraints come from tooling outside Forge and otherwise cost a cycle each:

- A command guard may refuse a shell redirect whose target is known only after expansion because it
  cannot prove what would be truncated. Write redirect targets as literal absolute paths (FR-035),
  and put computed paths or long prose in a script file invoked by absolute path.
- A provider safety classifier may terminate an execution whose brief describes defensive
  hardening in terms of the manipulation it prevents. Describe the guarantee to enforce, not the
  exploit to demonstrate.
