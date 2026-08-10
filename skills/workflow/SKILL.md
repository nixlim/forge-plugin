---
name: forge-workflow
description: Run the full Codex orchestration workflow end to end.
---

# Workflow

Use this skill for one complete run. This skill owns the lifecycle from planning through the final
report. Use `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/SKILL.md` for each focused Codex-agent
execution, review, or verification cycle.

## Run Initialization

<!-- forge: modified from upstream — enforce the single-active-run successor rule -->
Before opening a run, inspect every `.codex-orchestrator/runs/*/journal.jsonl` in the target
repository. If any journal lacks a `run_closed` entry, refuse to open the new run and name each
open run. Proceed only when the user explicitly designates the new run as a successor run; record
that designation and the predecessor run ID in the new `run_started.goal`. Never infer successor
status merely because an earlier run exists.

From the target Git worktree, exclude run data locally before creating it:

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

Use only this local exclude; do not edit the tracked `.gitignore`. Record the concise original goal,
`REPO`, full starting HEAD, attached branch when the branch output is nonempty, and exact status
lines as `goal`, `repo`, `repo_head`, optional `repo_branch`, and `repo_status` in `run_started`.
Do not create the run unless both exclude checks succeed. Initially dirty paths are pre-existing
user work; if planned work overlaps them, use an isolated clean worktree or get user direction
rather than claiming those changes.

## Forge Governance Doctrine

<!-- forge: modified from upstream — weave durable governance into the orchestration lifecycle -->

- **Journal integrity (FR-120).** Record every full SHA from observed command output such as
  `git rev-parse HEAD`, never from memory. Correct an error by appending a later entry that names
  the correction; never rewrite history. Execution IDs are strings shaped `execution-NN`. The
  fields `acceptance`, `files`, `repo_status`, `basis`, `evidence`, `caveats`, `files_changed`,
  `risks`, and `follow_ups` are arrays, including when empty or containing one item.
- **Verification integrity (FR-121–FR-123).** After any defect fix, the affected end-to-end
  verification must pass twice consecutively before task completion, recorded as two separate
  `verification` entries. Re-measure any timing or benchmark result obtained during detected
  machine instability before recording it as a passing verification; note sleep gaps or load
  spikes in an `observation`. Leak and quality checks must use the real canonical answer plus a
  positive control—a planted known-present string the check must find—never an invented
  substitute.
- **Independent planning (FR-124).** For every consequential or hard-to-reverse choice, Claude
  writes its own plan into the run directory before reading any Codex proposal for that choice.
  Compare both with evidence and reference both document paths from the resulting
  `decision.basis` array.
- **Input and authority (FR-125–FR-126).** Apply
  `${CLAUDE_PLUGIN_ROOT}/rules/untrusted-input.md` and
  `${CLAUDE_PLUGIN_ROOT}/rules/risk-authority.md` without restating or weakening them.
- **Bounded parallelism (FR-130).** Never exceed 10 concurrent Codex executions per run; use the
  orchestrate skill's ownership, worktree, and serialization rules. The twice-consecutive
  verification rule above applies in every focused execution as well.

## Full Workflow

1. Inspect the repository and user context to understand the goal and relevant constraints.
2. Perform Run Initialization, create `.codex-orchestrator/runs/<run-id>/journal.jsonl`, and append
   `run_started` with the concise original goal, absolute repository path, captured Git baseline,
   plugin ref, and available Claude and Codex versions.
3. Claude turns the goal into a concrete plan with expected deliverables, acceptance criteria,
   risks, and verification paths.
4. Ask Codex to review Claude's plan when a second opinion materially reduces risk; record that
   review as a task and focused agent cycle. For a consequential or hard-to-reverse design choice,
   first write Claude's own plan into the run directory without reading a Codex proposal. Only
   then ask a fresh Codex agent to propose an approach from only the goal, constraints, and
   acceptance criteria. Claude compares the results using evidence rather than agent count,
   references both plan paths in `decision.basis`, and finalizes the plan.
<!-- forge: modified from upstream — overlapping ownership always serializes (FR-130) -->
5. Split the finalized plan into active `task` entries with goals, acceptance criteria, and
   allowed/owned `files`. Serialize every overlap in files, contracts, or shared resources;
   isolated worktrees support concurrent tasks only when their ownership is disjoint.
<!-- forge: modified from upstream — fail closed at the run-lifecycle launch boundary (FR-033/092) -->
6. For each task, use the orchestrate skill to assign a fresh Codex implementer, capture its
   prompt, events, and handoff, and independently verify the result. Never resume an implementer;
   only the same reviewer may be resumed for a targeted confirmation round under the orchestrate
   contract. Immediately before every new execution launch, require this checkpoint to exit 0:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh"
```

   If it reports a halt, launch no new work, perform no reintegration, report the sentinel, and
   wait. Agents never create, delete, or bypass halt sentinels without explicit user direction.
   Repeat focused fix or review cycles as needed.
7. Record only consequential resolutions or user dependencies as `decision`. Append a terminal
   `task` entry only after its acceptance criteria have been evaluated.
8. When every task is terminal, re-read the complete journal and inspect the final repository state
   and diff.

<!-- forge: modified from upstream — use the Level B gates profile before and after closure -->
9. Run the pre-close gates check. This pass is advisory: the passed-close gate-presence check cannot
   fire before a `run_closed` entry exists.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" validate --gates \
  .codex-orchestrator/runs/<run-id>
```

10. Resolve omissions that can be corrected by appending, and inspect every non-passing
    verification. Never rewrite journal history. If a duplicate identity or another structural
    conflict cannot be corrected by appending, retain the run and start a successor as defined by
    the orchestration contract. Otherwise append one final `run_closed` entry with
    `judgment: passed|blocked`, unresolved risks, and follow-ups; its `validation` field embeds the
    pre-close payload verbatim. An absent `profile: "gates"` in that payload means the gated close
    was skipped.
11. After `run_closed`, run the post-close gates check:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" validate --gates \
  .codex-orchestrator/runs/<run-id>
```

    The post-close pass must exit 0 before invoking
    `${CLAUDE_PLUGIN_ROOT}/skills/report/SKILL.md` to create `report.md` once.
    The report skill refuses to write `report.md` while the post-close `validate --gates` reports issues.

The canonical close sequence is `validate --gates → run_closed → validate --gates → report.md`.
Claude still decides the semantic judgment, while gated validation enforces the recorded gate
conditions required for a clean accepted close. The final report never repairs or rewrites journal
history.
