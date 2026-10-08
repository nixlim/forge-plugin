---
name: forge-workflow
description: Forge's end-to-end owner workflow for planning, routed execution, verification, reintegration, and reporting in a governed repository.
---

# Workflow

Use this skill for one complete run. The [orchestrate skill](../orchestrate/SKILL.md) owns each
focused agent cycle; commit and merge skills own their candidate-bound gates. The run journal is a
local append-only log of executions and decisions. It does not authorize a gate, commit, merge,
approval, launch, or close. Read [the orchestration contract](../../docs/orchestration-contract.md)
before recording or interpreting it.

## Run Initialization

<!-- forge: run-open refusal for operator-cleared CRITICAL drift (FR-163) -->
Resolve the target repository root and check for the operator-cleared drift block before opening
any run:

```bash
REPO="$(git rev-parse --show-toplevel)" || exit 1
if [ -e "$REPO/.forge/tmp/drift-block" ]; then
  printf '%s\n' \
    'forge: new run refused — CRITICAL drift block present at .forge/tmp/drift-block; operator clearance required' \
    >&2
  exit 1
fi
```

This refusal applies to every new run. Only an operator may manually delete the block after
reading the durable drift report. Forge agents and cleanup never delete or bypass it. This is a
run-open refusal, not an `AGENT_HALT` sentinel.

Exclude local run data before creating it:

```bash
REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"
EXCLUDE_FILE="$(git rev-parse --git-path info/exclude)"
grep -qxF '/.codex-orchestrator/' "$EXCLUDE_FILE" ||
  printf '\n/.codex-orchestrator/\n' >> "$EXCLUDE_FILE"
grep -qxF '/.codex-orchestrator/' "$EXCLUDE_FILE"
git check-ignore -q .codex-orchestrator/.ignore-check
git rev-parse HEAD
git branch --show-current
git status --short --untracked-files=all
```

Use only this local exclude; do not edit the tracked `.gitignore`. If planned work overlaps
pre-existing user changes, isolate the work or get user direction.

Open the run through the plain writer:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" run-open \
  --repo "$REPO" --run-id <run-id> --intent <concise-original-goal> --actor <actor>
```

The writer records `run_started` with the repository, intent, and actor. It does not reserve the
run, files, routes, or a session. Keep the run ID in the documented grammar; an invalid ID is
refused before a directory or file is created.

## Verification and planning doctrine

- After a defect fix, the affected end-to-end verification must pass twice consecutively before
  task completion. Retain both observed executions as evidence; this is independent of one
  candidate-bound Gate 1 check.
- Leak and quality checks must use the real canonical answer plus a positive control: a planted
  known-present string the check must find. Re-measure results obtained during detected machine
  instability.
- For every consequential or hard-to-reverse design choice, write the orchestrator's own plan in
  the run directory before reading any Codex proposal. Compare the plans with evidence and cite
  both documents as optional references on the resulting `decision` record.
- Apply `${CLAUDE_PLUGIN_ROOT}/rules/untrusted-input.md` and
  `${CLAUDE_PLUGIN_ROOT}/rules/risk-authority.md` without weakening either rule.

## Brief and design discipline

- A brief quotes the ruling or specification sentence it implements and never paraphrases it. When
  the brief and the specification disagree, the specification wins and the agent reports the
  disagreement instead of resolving it.
- A brief adds no mechanism, field, verb, literal, event member, module or helper that the ruling
  does not name, and never invites the agent to improve on the ruling. An agent that believes one
  is needed stops that part and reports it. A requirement that has grown past its ruling by an
  order of magnitude is cut before any code is written.
- A brief that changes existing code names a baseline commit and gives every touched file one
  disposition: keep, revert to the baseline, delete, or edit with the exact change. Its acceptance
  criterion is the baseline shape plus the named additions, measured with `git diff <baseline>
  --stat` and a trace from every added hunk to a quoted sentence.
- Kept diagnostics stay byte-identical. A retired literal leaves code, tests and prose in the same
  change; a deleted control loses its tests in the same change; a kept control keeps a focused
  test that fails when the control is disabled in memory.
- One rule for two verbs beats a mode flag, and shared helpers take no per-verb parameters. Never
  re-implement a tool the code already calls: do not parse Git pathspec syntax, match Git's stderr
  text, or predict what Git will stage; let Git act and observe the result with plumbing.
- A control that its own specification says can be evaded by construction is not specified.
  Measure the problem a mechanism would solve before adding it.
- When a ruling changes while a unit is open, patch every outstanding brief before the next
  launch; an agent otherwise re-reads the stale sentence.

## Full Workflow

1. Inspect the repository and user request. Write a plan with deliverables, acceptance criteria,
   risks, and verification commands. For a consequential choice, write your own plan before
   reading an agent proposal; compare both using evidence.
2. Break the plan into bounded tasks. Log each assignment with `journal task-start --repo "$REPO"
   --run-id <run-id> --task <task-id> --title <title> --scope <free-text-scope>`. Describe owned
   files in the task brief and serialize overlapping work. Isolated worktrees support parallel
   tasks when their files, contracts, and shared resources do not overlap. Limit a run to ten
   concurrent Codex executions.
3. Use [orchestrate](../orchestrate/SKILL.md) to launch each fresh implementer or planner with
   `forge launch` and collect with `forge launch collect`. Before each new launch, run:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh"
   ```

   On a halt, launch nothing, perform no reintegration, and report the sentinel. Agents never
   create, delete, or bypass halt sentinels without explicit user direction.
   For a reviewer session outside the typed launch lane, use `journal execution-start` before
   launch and `journal execution-result` after observing its outcome. Record the route actually
   used with `--sandbox <profile> --route-source <source> --route-sha256 <digest>`
   on both verbs; these entries do not determine process status or chain permission. Choose the next free
   `execution-NN` under the run's executions root and reserve it in `.execution-ids/` as the
   launcher does. For a typed launch, use the execution ID printed by `forge launch`.

   For a prose reviewer, with `REPO`, `RUN_ID`, `TASK_ID`, `WORKTREE`, the resolved route values,
   and observed `STATUS`, `EXIT_STATUS`, and existing `OUTPUT` set, run the following. Create the
   exact `prompt.md` and empty `events.jsonl` before the start record; append the result after
   the process ends. A reservation collision means choosing the next free ID.

   ```bash
   RUN_DIR="$REPO/.codex-orchestrator/runs/$RUN_ID"
   EXECUTION=execution-02
   mkdir -p "$RUN_DIR/.execution-ids"
   mkdir "$RUN_DIR/.execution-ids/$EXECUTION"
   STARTED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" journal execution-start \
     --repo "$REPO" --run-id "$RUN_ID" --task "$TASK_ID" --role review-final \
     --provider codex --model "$MODEL" --effort "$EFFORT" --worktree "$WORKTREE" \
     --sandbox "$SANDBOX" --route-source "$ROUTE_SOURCE" --route-sha256 "$ROUTE_SHA256" \
     --execution "$EXECUTION" --agent "$AGENT" --events "$EVENTS" --started-at "$STARTED_AT"
   ```

   After observing the process outcome, set `STATUS`, `EXIT_STATUS`, and `OUTPUT`, then append:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" journal execution-result \
     --repo "$REPO" --run-id "$RUN_ID" --task "$TASK_ID" --role review-final \
     --provider codex --model "$MODEL" --effort "$EFFORT" --worktree "$WORKTREE" \
     --sandbox "$SANDBOX" --route-source "$ROUTE_SOURCE" --route-sha256 "$ROUTE_SHA256" \
     --execution "$EXECUTION" --started-at "$STARTED_AT" --status "$STATUS" \
     --exit-status "$EXIT_STATUS" --output "$OUTPUT"
   ```
4. Inspect the handoff, actual diff, and required checks. Treat agent claims as claims. Record
   consequential resolutions with `journal decision-add --repo "$REPO" --run-id <run-id>
   --text <decision> --actor <actor>`. Describe task outcomes with `journal task-finish` using
   its task, title, scope, and status arguments. Task records are descriptive; evaluate acceptance
   against observed evidence.
5. Run `/forge:commit` for verified checkpoints and `/forge:worktree-merge` for reintegration.
   Their gate results, review verdicts, approval, and Git outcomes live in `.forge/chains/` or
   the merge skill's command evidence. Record relevant chain IDs or verdict paths as optional
   journal references, never as substitute authority. Preserve the merge skill's remote
   containment, clean-worktree, branch-tip, and guarded deletion proofs.
6. Inspect final repository state and unresolved work. Append a descriptive close:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" run-close \
     --repo "$REPO" --run-id <run-id> --outcome <free-text-outcome>
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" validate \
     .codex-orchestrator/runs/<run-id>
   ```

   `validate` checks JSON object structure only and returns `{ok, issues}`. A close is a fact in
   the log; later facts may still be appended. Validation does not decide delivery or permission.
7. Use [report](../report/SKILL.md) to write `report.md` from the journal, observed repository
   state, handoffs, and chain evidence. State failed checks, unresolved work, risks, and follow-ups
   plainly. Do not rewrite old journal lines to improve the report.

## Machine Moves

Run material is locally excluded from Git. Preserve the journal, execution artefacts, and
`.forge/chains/` evidence needed for an accurate report. A new machine may open a new run for
subsequent work; no owner sidecar, scope registry, successor protocol, or archive commit is
required by the journal writer.
