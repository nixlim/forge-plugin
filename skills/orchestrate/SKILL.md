---
name: forge-orchestrate
description: Run a focused Codex-agent execution, monitoring, review, or verification phase.
---

# Claude-Codex Orchestration

Claude coordinates and verifies focused agent work. Codex handles scoped implementation and review
through its native CLI. Prefer Codex as the first mover for bounded coding tasks.

Use this skill for one focused agent cycle inside an orchestration run. The workflow skill owns
planning, run initialization, task decomposition, closure, and reporting. Return to it when the
focused phase is complete.

## Forge Role Routing And Control Plane

<!-- forge: modified from upstream — role routing and control-class launch values (FR-030) -->

| Actor | Responsibility | Journal role | Model | Effort | Sandbox |
|---|---|---|---|---|---|
| Claude main session | Orchestrator/verifier; owns the journal, worktrees, gate chain, and all reintegration | n/a | host session | host session | host session |
| Fresh Codex implementer | Scoped implementation in its assigned worktree | `implementation` | `gpt-5.6-sol` | `ultra` | `workspace-write` |
| Fresh Codex first-pass reviewer | Independent, non-editing review of the supplied target | `review` | `gpt-5.6-sol` | `high` | `read-only` |
| Claude subagent `review-final` | Binding final review | n/a | project-configured | project-configured | orchestrator tree |

The `model` and `effort` in every journal `execution` entry are the values actually passed at
launch. Changing any model, effort, or sandbox value is a control-class change; do not silently
substitute a cheaper model, lower effort, or broader sandbox.

## Forge Isolation And Prompt Construction

<!-- forge: modified from upstream — worktree and reviewer isolation plus prompts (FR-031/032/037) -->

Every implementer gets a dedicated git worktree. Include this sentence verbatim in its prompt:
"You may commit inside this worktree. You must NEVER push, never touch any branch other than your
own, and never run destructive git commands." The orchestrator alone performs reintegration.

Build each Codex prompt at launch, in this order:

1. The applicable plugin role template:
   `${CLAUDE_PLUGIN_ROOT}/system/codex/prompts/implementer.md` or
   `${CLAUDE_PLUGIN_ROOT}/system/codex/prompts/review-cheap.md`.
1. Only the `agent-project-context` managed region from `forge-project.md`.
1. The concrete task assignment, with its goal, acceptance criteria, constraints, owned files,
   and required handoff.

Render the concrete values, then save those exact bytes as `prompt.md` before appending the
journal `execution` entry. Handoffs retain the upstream six-heading contract shown below.

A first-pass reviewer is always a fresh agent and native session launched with `-s read-only`.
Its prompt contains the goal, acceptance criteria, constraints, and exact target SHA. It must
contain none of the implementer's handoff, claimed test results, earlier review verdicts, or the
orchestrator's tentative conclusion. Inspect the review target directly; do not use those excluded
claims as prompt context.

## Forge Execution Preparation And Launch

<!-- forge: modified from upstream — ordered detached Codex launch mechanics (FR-033..037/092) -->

Before each new execution, run the halt checkpoint. If it reports a global or scoped halt, launch
no new work, perform no reintegration, report the sentinel to the user, and wait. Agents must not
create, delete, or bypass halt sentinels without explicit user direction.

Prepare each execution in this exact order:

1. Create the next numbered `execution-NN` directory.
1. Assemble and write `prompt.md` as described above.
1. Create an empty `events.jsonl`.
1. Append the journal `execution` entry, including the absolute worktree, full HEAD, branch, role,
   actual model and effort, and prompt/events/handoff paths.
1. Launch the process.

The events file therefore exists before either the journal or monitor refers to it, and the
journal entry always precedes the process launch. Fresh launches use this exact command pattern:

```text
codex exec --json --output-last-message <handoff> -s <sandbox> -c approval_policy=never -c model="<role model>" -c model_reasoning_effort="<role effort>" -C <worktree> - < prompt.md > events.jsonl
```

Substitute the role table values without changing the option shape. All shell redirect targets
must be literal absolute paths: never put `$VAR`, `~`, or a relative path in redirect position.
The following is the required detached form for a fresh implementer:

```bash
set -m
nohup codex exec --json \
  --output-last-message /absolute/path/to/execution-01/handoff.md \
  -s workspace-write \
  -c approval_policy=never \
  -c model="gpt-5.6-sol" \
  -c model_reasoning_effort="ultra" \
  -C /absolute/path/to/implementer-worktree \
  - \
  < /absolute/path/to/execution-01/prompt.md \
  > /absolute/path/to/execution-01/events.jsonl &
launch_pid=$!
disown "$launch_pid"
launch_pgid="$(ps -o pgid= -p "$launch_pid" | tr -d ' ')"
{
  printf '%s\n' "$launch_pid"
  printf '%s\n' "$launch_pgid"
  date -u '+%Y-%m-%dT%H:%M:%SZ'
} > /absolute/path/to/execution-01/pid
```

Use the identical preparation and detachment mechanics for a reviewer, substituting its
`gpt-5.6-sol`, `high`, and `read-only` role-table values.

`set -m` gives the background launch its own process group. `setsid` is an acceptable equivalent
where available, but the launch still uses `nohup ... &` and `disown`. Never use `--ephemeral`,
and never use a harness-managed background task. Immediately after launch, verify that `pid` has
exactly three lines (PID, PGID, UTC ISO-8601 launch timestamp) before arming the monitor.

Never resume an implementation session: every implementer task gets a fresh named agent and fresh
native session. The sole sanctioned resume is a targeted confirmation round by the same reviewer.
Create the reviewer's next `execution-NN` directory, follow the same prepare/journal ordering, and
use its recorded `session_id` with `codex exec ... resume <session_id> -`. Do not pass `-C` on a
resume; the resumed session inherits its working directory. The resumed command still records its
events and handoff under the new execution directory, uses literal absolute redirect paths, and
runs detached with a new three-line `pid` sidecar.

## Forge Monitor Lifecycle And Ambiguity Protocol

<!-- forge: modified from upstream — bounded re-arm, ambiguity, sleep-gap, and halt (FR-040..043/092) -->

While any execution remains in flight, re-arm the monitor no later than 60 minutes after its last
arm or exit. A stale or unknown target is terminal to that monitor invocation, so it has stopped
watching even though the underlying execution may still be running. Between every monitor cycle,
run the halt checkpoint. On halt, start no work and perform no reintegration; report and wait while
continuing only the read-only checks needed to understand already-launched executions.

Treat `codex_agent_stale` as ambiguous. Before appending any `execution_result`:

1. Check the `events.jsonl` mtime for progress after the notification.
1. Read PID and PGID from the execution's `pid` sidecar and use `ps` to check that PID and recorded
   process group rather than guessing from process names.
1. Inspect the handoff and the assigned worktree for completed or partial work.

Never conclude failure from staleness alone. If the process group remains alive, append no result
and re-arm the monitor within the same 60-minute bound. If a machine-sleep gap creates a wall-clock
jump beyond the stale threshold, first run `state` for every in-flight target before trusting any
stale notification emitted across that gap.

On `codex_agent_unknown`, run `state --dump-event-types` for that target. Do not infer whether the
agent is running, passed, or failed; surface the event-format incompatibility and observed types to
the user before deciding how to proceed.

## Durable Run

Keep run material under:

```text
.codex-orchestrator/runs/<run-id>/
  journal.jsonl
  <provider>-<role>-<NN>/execution-<NN>/
    prompt.md
    events.jsonl
    handoff.md
  evidence/                 # optional
  report.md                 # after the committed durable archive
```

The journal and execution material remain locally excluded working state. The workflow closes the
run by writing and committing the durable archive at `.forge/history/runs/<run-id>.md` before this
local `report.md` is written. `.forge/history/` is append-only committed repository documentation;
never ignore, overwrite, amend, delete, or prune an archive.

`journal.jsonl` is Claude's append-only orchestration journal. Read
`${CLAUDE_PLUGIN_ROOT}/docs/orchestration-contract.md` before creating or interpreting journal
entries; it owns record fields, authority, validation, and closure semantics.

Capture each execution's exact prompt, raw events when available, and exact handoff. Never
synthesize a log or rewrite a handoff. Keep small observations inline and create `evidence/` only
when material output must be retained.

## Forge Execution Doctrine

<!-- forge: modified from upstream — weave worktree isolation and bounded execution into focused cycles -->

- Parallel tasks require disjoint `files` ownership. Isolated worktrees enforce that boundary but
  never permit overlapping ownership to run concurrently. Serialize every overlap, including shared
  generated files and integration resources. At most 10 concurrent Codex executions may run in one
  orchestration run.
- Create each implementer worktree from the integration baseline with
  `git worktree add <dir> -b <branch>`. Do not integrate or remove it until its execution has
  stopped, its handoff has been saved, and Claude has inspected its diff.
- One session owns one worktree and must never adopt or reuse another session's tree. Helper Claude
  subagents, including `review-final`, share the orchestrator's worktree; they do not create or
  switch to a separate tree.
- Record SHAs only from observed command output, never memory, and append journal corrections
  instead of rewriting entries. Use string execution IDs shaped `execution-NN` and the array-field
  contract in `${CLAUDE_PLUGIN_ROOT}/skills/workflow/SKILL.md`.
- After any defect fix, the affected end-to-end verification must pass twice consecutively before
  task completion, with the two passes recorded as two separate `verification` entries.
- Apply `${CLAUDE_PLUGIN_ROOT}/rules/untrusted-input.md` and
  `${CLAUDE_PLUGIN_ROOT}/rules/risk-authority.md` for input handling and authority decisions.

## Focused Agent Cycle

1. Read the complete journal, current task, and relevant references before acting.
2. Confirm the task's acceptance criteria and allowed/owned `files`.
3. Compare active task files and shared resources before parallel work. Require disjoint ownership
   and serialize every overlap; use isolated worktrees for disjoint tasks without exceeding the
   run's execution cap.
4. Start a fresh named implementer and native session for implementation.
   For an independent review, start a fresh agent and native session. Only a reviewer confirmation
   round may resume that same reviewer session.
5. Resolve the execution's absolute worktree, full HEAD, and attached branch when present and
   include them in its record. Save the exact prompt and append `execution` before launch.
6. Monitor with the bundled tools without editing files owned by the active agent. Apply the
   bounded re-arm and ambiguity protocols above.
7. Save the exact handoff, inspect it and the repository, then append terminal
   `execution_result`.
8. Evaluate acceptance criteria and record material checks as `verification`.
9. Record only consequential resolutions or user dependencies as `decision`.
10. After evaluating the criteria, append `complete` when they are satisfied, `failed` when they
    are conclusively unmet and no in-scope recovery remains, or `blocked` when a user or external
    dependency prevents completion or judgment. Otherwise keep the task `active` and return the
    unresolved work to the workflow.

Routine bounded work needs Codex implementation plus Claude verification. Add a fresh reviewer only
for material risk or a distinct unresolved question; do not repeat identical reviews.

## Reference Map

Read only what the current phase needs:

- `references/monitoring.md`: execution capture, CLI monitoring, and handoffs.
- `references/review.md`: verification and independent review.
- `references/consensus.md`: consensus and decision outcomes.
- `references/compute.md`: parallel ownership, worktrees, and compute gating.
