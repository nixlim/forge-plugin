# Review And Verification

Use [the orchestration contract](../../../docs/orchestration-contract.md) for journal fields.

## Verify Agent Work

<!-- forge: modified from upstream — corrections use fresh implementers, not resumed sessions -->

1. Read the handoff as claims.
1. Inspect the actual diff and changed files. Compare them with the task's declared `files`.
1. Evaluate every acceptance criterion with an observed check. Do not promote `Commands Reported`
   to a passing verification.
1. Record each criterion as a `verification`.
1. On implementation failure, preserve the record and launch a fresh named implementer and native
   session with the exact finding and observation. Only reviewer confirmation may resume that same
   reviewer session. Record the recheck separately.
1. Mark the task terminal only after all criteria are evaluated.

Base verification on repository state or observed output. Use handoffs and model findings to choose
what to inspect. Keep concise observations inline; use `evidence/` only for lengthy material worth
retaining.

## Independent Codex Review

<!-- forge: modified from upstream — fresh read-only review with isolated evidence (FR-032..034) -->

For the first independent review:

- Start a fresh named `codex-review-NN` agent and native session; never resume the implementation
  session.
- Provide the goal, acceptance criteria, constraints, and exact commit SHA.
- Do not provide the implementer handoff, claimed test results, earlier review verdicts, or Claude's
  tentative conclusion.
- Build the prompt through the canonical
  [prompt-construction contract](../SKILL.md#forge-isolation-and-prompt-construction), in exact
  order: `${CLAUDE_PLUGIN_ROOT}/system/codex/prompts/review-cheap.md`; the `agent-project-context`
  region from `git -C <worktree> show HEAD:forge-project.md`; the exact bytes from
  `git -C <worktree> show HEAD:.forge/history/gotchas.md` when present in that `HEAD`; and the
  isolated review assignment. `<worktree>` is the same review worktree recorded for the execution
  and passed to `-C`; never source either committed input from working-tree state or a rendered
  agent definition.
- In order, create the execution directory, save the exact prompt, create an empty `events.jsonl`,
  append the execution, and only then launch. Capture the event stream and exact handoff.

Immediately before launch, require the forge halt checkpoint to exit 0. Run the reviewer with
model `gpt-5.6-sol`, effort `high`, and sandbox `read-only` in a detached process group. All
redirect targets are literal absolute paths:

```bash
set -m
nohup codex exec --json \
  --output-last-message /absolute/path/to/run/codex-review-01/execution-01/handoff.md \
  -s read-only \
  -c approval_policy=never \
  -c model="gpt-5.6-sol" \
  -c model_reasoning_effort="high" \
  -C /absolute/path/to/review-worktree \
  - \
  < /absolute/path/to/run/codex-review-01/execution-01/prompt.md \
  > /absolute/path/to/run/codex-review-01/execution-01/events.jsonl &
launch_pid=$!
disown "$launch_pid"
launch_pgid="$(ps -o pgid= -p "$launch_pid" | tr -d ' ')"
{
  printf '%s\n' "$launch_pid"
  printf '%s\n' "$launch_pgid"
  date -u '+%Y-%m-%dT%H:%M:%SZ'
} > /absolute/path/to/run/codex-review-01/execution-01/pid
```

Write the exact commit SHA into `prompt.md` and instruct Codex to review that snapshot. Use plain
`codex exec`: the Codex CLI does not accept a stdin review prompt together with the `review`
subcommand's revision selectors. Prefer a worktree at the reviewed commit; reviewing a fixed SHA
does not require pausing unrelated work. Tell Codex not to edit and confirm the review worktree is
clean afterward. Tests that require writes belong to Claude's independent verification, not the
read-only review process.

Verify review findings against the repository. The only allowed resume is a targeted confirmation
round by this same reviewer: use its recorded `session_id`, the next execution directory, and no
`-C` flag, as shown in [`monitoring.md`](monitoring.md). Start a fresh reviewer for a distinct
unresolved question. Never resume an implementer.
