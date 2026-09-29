---
name: forge-orchestrate
description: Forge's focused cycle for one task inside an open Forge orchestration run. Launch a fresh routed implementer or planner with forge launch, wait for it and collect or cancel it with forge launch collect and forge launch cancel, run an isolated first-pass or confirmation reviewer, and verify the handoff against the repository. Use this skill, not the upstream codex-orchestrator orchestrate skill, whenever a Forge-governed repository (one with forge-project.md) needs an implementer, planner, first-pass review, or execution check during a workflow run, even if the request only says "have Codex do task-03", "check on the implementer", or "re-review that fix".
---

# Forge Focused Orchestration

Claude coordinates and verifies focused agent work. Forge launches scoped implementer and planner
work through the run's frozen provider routes. Prefer a fresh implementer as the first mover for
bounded coding tasks.

Use this skill for one focused agent cycle inside an orchestration run. The workflow skill owns
planning, run initialization, task decomposition, closure, and reporting. Return to it when the
focused phase is complete.

## Forge Role Routing And Control Plane

<!-- forge: modified from upstream — role routing and control-class launch values (FR-030) -->

| Actor | Responsibility | Journal role | Committed default | Launch owner |
|---|---|---|---|---|
| Claude main session | Orchestrator/verifier; owns the journal, worktrees, gate chain, and all reintegration | n/a | host session | host session |
| Fresh routed implementer | Scoped implementation in its assigned worktree | `implementer` | Codex `gpt-5.6-sol` / `ultra` / `workspace-write` | `forge launch --role implementer` |
| Fresh Codex first-pass reviewer | Independent, non-editing review of the supplied target | `review-cheap` | Codex `gpt-5.6-sol` / `high` / `read-only` | session, by the procedure in `references/review.md` |
| Fresh routed planner | Bounded implementation planning for one run task; runs only, never a chain-bound planning pass | `plan` | Codex `gpt-5.6-sol` / `high` / `read-only` | `forge launch --role plan` |
| Binding final reviewer | Candidate-bound final review | `review-final` | project-configured route | Forge review engine (`forge review request` / `forge review collect`); interactive only in `/forge:worktree-merge` |

For typed implementer and plan executions, provider, model, effort, and sandbox come from the run's
frozen resolved route and the exact FR-245 provider profile; never hand-substitute provider flags
for those roles. The reviewer-specific procedure in `references/review.md` is the only place the
session writes provider flags, and it uses the committed `review-cheap` values shown there. The
`model` and `effort` in every journal `execution` entry are the values actually passed at launch.
Changing any committed model, effort, or sandbox default or provider-profile value is a
control-class change; do not silently substitute a cheaper model, lower effort, or broader sandbox.

## Forge Isolation And Prompt Construction

<!-- forge: modified from upstream — worktree and reviewer isolation plus prompts (FR-031/032/037) -->

Every implementer gets a dedicated git worktree. Put this sentence verbatim in every implementer
brief, because the brief is the only prompt text the session controls and the Claude implementer
body grants commits only when the assignment permits them: "You may commit inside this worktree.
You must NEVER push, never touch any branch other than your own, and never run destructive git
commands." The orchestrator alone performs reintegration.

Resolve `<worktree>` to the same absolute execution worktree that Forge will record and use for the
launch. For implementer and plan, write the concrete assignment (goal, acceptance criteria,
constraints, owned files, the sentence above for an implementer, and the required handoff) to a
brief file: an absolute path to a regular file you own (not a symlink), UTF-8 without NUL bytes, at
most 1 MiB. Keep it outside the target worktree, for example in the session scratchpad, because
collect reports every untracked worktree path in `files_changed`; `forge launch` preserves its bytes
in `prompt.md`. The provider split is exact: for Codex, `prompt.md` and stdin start with the
applicable plugin role template; for
Claude, the applicable committed role body is passed only through the exact FR-245 argv flag and is
not part of `prompt.md`. Claude `prompt.md` and stdin start with the exact bytes
`\n--- committed agent-project-context ---\n`. The remaining prompt components keep this order:

1. The applicable plugin role template for Codex:
   `${CLAUDE_PLUGIN_ROOT}/system/codex/prompts/implementer.md` or
   `${CLAUDE_PLUGIN_ROOT}/system/codex/prompts/plan.md`. The reviewer-specific path uses
   `${CLAUDE_PLUGIN_ROOT}/system/codex/prompts/review-cheap.md`.
1. Only the `agent-project-context` managed region extracted from the committed bytes returned by
   `git -C <worktree> show HEAD:forge-project.md`.
1. When it exists in that same committed `HEAD`, the exact committed bytes returned by
   `git -C <worktree> show HEAD:.forge/history/gotchas.md`. Test presence with
   `git -C <worktree> cat-file -e HEAD:.forge/history/gotchas.md`; omit this component only when the
   object is absent, and stop the launch on any other read failure.
1. The concrete task assignment, with its goal, acceptance criteria, constraints, owned files,
   and required handoff.

The region and gotchas MUST NOT come from working-tree state, another checkout, or a rendered agent
definition. The typed lane renders the concrete values, saves those exact assembled bytes as
`prompt.md`, and appends its owner record in the required order. Do not assemble or save that prompt
by hand. Handoffs retain the upstream six-heading contract shown below.

A first-pass reviewer is always a fresh agent and native session launched with `-s read-only`.
Its prompt contains the goal, acceptance criteria, constraints, and exact target SHA. It must
contain none of the implementer's handoff, claimed test results, earlier review verdicts, or the
orchestrator's tentative conclusion. Inspect the review target directly; do not use those excluded
claims as prompt context.

## Forge Execution Preparation And Launch

<!-- forge: modified from upstream — typed routed launch lifecycle (FR-033..037/092/245) -->

### Typed Implementer And Plan Launches

Implementer and plan executions are engine-launched. Invoke only the typed lane with the absolute
repository, run, worktree, and owner-controlled brief:

Below, `forge` is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py"`, the same alias the commit
skill uses. `<repo>` is the absolute repository root, and every path argument is absolute. The
successful start receipt reads `launch started for execution-NN`; its `next_required_step` is the
exact collect command to run next.

```text
forge launch --repo <repo> --run-id <run-id> --role implementer --task <task-id> --worktree <absolute-worktree> --brief <absolute-brief>
forge launch --repo <repo> --run-id <run-id> --role plan --task <task-id> --worktree <absolute-worktree> --brief <absolute-brief>
```

The lane runs the halt checkpoint first. If it reports a global or scoped halt, launch no new work,
perform no reintegration, report the sentinel to the user, and wait. Agents must not create, delete,
or bypass halt sentinels without explicit user direction. Forge then performs the task, registered
worktree, committed HEAD, initialization, brief, frozen-route, executable, version-floor, and
in-flight checks. An implementer worktree must be a dedicated linked worktree.

The typed lane performs the owner sequence; the session does not reproduce it:

1. Create the agent directory when absent and the owner-only `execution-NN` directory.
1. Assemble and save `prompt.md`, then create the empty `events.jsonl`.
1. Write and fsync `launch.json`.
1. Append the journal `execution` owner record.
1. Launch the process through the isolated wrapper.

The generated owner record includes the absolute worktree, full HEAD, actual provider/model/effort,
prompt/events/handoff paths, `mode: detached`, `launch_marker`, and the route trio `sandbox`,
`route_source`, and `route_sha256`, copied from that role's frozen run snapshot; do not reconstruct
or omit it. Never write `unrecorded` for a new snapshot-backed run. A reviewer-specific prose record
written outside the typed lane may omit the trio; if it carries any of `sandbox`, `route_source`, or
`route_sha256`, it must carry all three, equal to that role's frozen run snapshot in
`run_started.route`, which Forge accepts only when the launched provider, model, and effort equal
that frozen route.

The old implementer/plan recipe is retired. Do not use or reconstruct
`codex exec --json --output-last-message`, `-c model="<role model>"`,
`-c model_reasoning_effort="<role effort>"`, `set -m`, `nohup codex exec`, or
`disown "$launch_pid"` for these roles. Forge owns provider argv, detachment, process identity, and
the legacy PID sidecar's exactly three lines. Do not assemble provider argv or substitute provider
flags.

Read the returned `execution-NN` and `next_required_step`. Collect only through:

```text
forge launch collect --repo <repo> --run-id <run-id> --execution <execution-NN>
```

A still-launching or still-running refusal is nonterminal: append no result, do not relaunch, and
retry collection later. Collection validates the launch marker, prompt, route, worktree, identity,
and completion before writing at most one terminal `execution_result`; repeated collection is
idempotent. If collect reports `wrapper-dead / child-alive`, or an owned execution must be stopped,
use:

```text
forge launch cancel --repo <repo> --run-id <run-id> --execution <execution-NN>
```

Cancel proves the recorded process-group identity, terminates only that owned group, publishes
`cancelled` or `wrapper-lost`, and finishes through collect. It is not a pause or continuation
operation.

The typed launch lane supports only fresh `implementer` and `plan` starts. It accepts no reviewer
role, session id, resume, continuation, or attach operation. `launch collect` records completion and
`launch cancel` terminates and collects; neither continues a provider session. A failed or corrected
implementer or plan task therefore uses a new `forge launch` execution and attempt. Reviewer
confirmation rounds remain on the reviewer-specific path in `references/review.md`; do not route
them through `forge launch`. The typed lane has no `stale` transition.

## Forge Monitor Lifecycle And Ambiguity Protocol

<!-- forge: modified from upstream — bounded re-arm, ambiguity, sleep-gap, and halt (FR-040..043/092) -->

While a typed execution is in flight, observe it at least every 60 minutes and as soon as it can
have finished. The wrapper publishes `<run-dir>/<agent>/<execution-NN>/completion.json` when the
provider exits or hits its fixed timeout (implementer 14400 seconds, plan 1200 seconds), so wait
with a non-blocking poll for that file, bounded at 60 minutes, then run `forge launch collect`
whether or not it appeared. Before each observation run
`bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh"`; on a halt start no work and perform no
reintegration, but read-only collection of an already-launched execution remains allowed. Collect,
never a hand-written `execution_result`, is the lifecycle authority. Act on each result as follows:

| Result | Action |
|---|---|
| `launch collect: complete` or `launch collect: failed` | Terminal; the one result exists. Inspect `handoff.md` and the worktree. A failed task stays active; a retry is a new `forge launch`. |
| `is still launching; retry after the identity deadline` | Wait at least 60 seconds, then collect again. |
| `is still running` | Append nothing, do not relaunch, keep waiting. |
| `wrapper-dead / child-alive …; run launch cancel …` | Run the named `forge launch cancel`. |
| `identity-unproven … nothing was signalled` | Signal nothing yourself; report the listed PIDs to the user; collect again after they exit. |
| `pid sidecar unavailable …; run launch collect` | Run `forge launch collect`. |
| start refused: `still in flight in <worktree>` | One typed execution per worktree: collect or cancel that execution first. |
| any refusal naming `journal batch-recover` | Run the named recovery before anything else. |
| start refused: initialization, version floor, not logged in, or route | Stop and report the diagnostic verbatim; never switch provider or model. |

The legacy `codex_agent_stale`, `codex_agent_unknown`, and `state --dump-event-types` protocol
applies only to reviewer-specific prose sessions outside the typed lane. There, an events file mtime,
PID, PGID, and process-group check remain required; never conclude failure from staleness alone. A
machine-sleep gap still requires a fresh state observation before trusting an old notification. See
`references/monitoring.md` for that reviewer-only procedure.

## Durable Run

Keep run material under:

```text
.codex-orchestrator/runs/<run-id>/
  journal.jsonl
  <provider>-<role>-<NN>/execution-<NN>/
    prompt.md
    events.jsonl
    handoff.md
    pid
    stderr.log              # typed launches only
    launch.json             # typed launches only
    identity.json           # typed launches only
    completion.json         # typed launches only
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
4. Start a fresh implementer or planner only through `forge launch` (see Typed Implementer And Plan
   Launches). For an independent review, start a fresh agent and native session through
   `references/review.md`. Only a reviewer confirmation round may resume that same reviewer session.
5. Write the brief, then pass the absolute worktree and brief to `forge launch`. Forge resolves the
   full HEAD, saves the exact prompt and appends `execution` before launch; do not write
   `prompt.md`, `events.jsonl`, `launch.json`, `pid`, or the `execution` record yourself. The typed
   owner record carries no `branch` field; read it with `git -C <worktree> branch --show-current`
   when you need it.
6. Observe with `forge launch collect` without editing files owned by the active agent, following
   the wait and outcome rules in Forge Monitor Lifecycle And Ambiguity Protocol. Use
   `forge launch cancel` only when collect names it or the execution must be stopped.
7. When collect reports `launch collect: complete` or `launch collect: failed`, it has already
   written the one terminal `execution_result`. Inspect the exact `handoff.md` and the worktree;
   never append an `execution_result` for a typed execution by hand.
8. Evaluate acceptance criteria and record material checks as `verification`.
9. Record only consequential resolutions or user dependencies as `decision`.
10. After evaluating the criteria, append `complete` when they are satisfied, `failed` when they
    are conclusively unmet and no in-scope recovery remains, or `blocked` when a user or external
    dependency prevents completion or judgment. Otherwise keep the task `active` and return the
    unresolved work to the workflow.

Routine bounded work needs routed implementation plus main-session verification. Add a fresh
reviewer only for material risk or a distinct unresolved question; do not repeat identical reviews.

## Reference Map

Read only what the current phase needs:

- `references/monitoring.md`: before reading typed-launch artifacts on disk, and before launching,
  resuming, or monitoring any reviewer prose session (`state`, `monitor`, stale, unknown).
- `references/review.md`: before verifying a handoff or starting a first-pass reviewer, and to
  confirm that gate reviews are engine-launched.
- `references/consensus.md`: when Claude and an agent disagree or a decision outcome is recorded.
- `references/compute.md`: before running tasks in parallel or creating worktrees.
