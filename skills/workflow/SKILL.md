---
name: forge-workflow
description: Run the full Codex orchestration workflow end to end.
---

# Workflow

Use this skill for one complete run. This skill owns the lifecycle from planning through the final
report. Use `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/SKILL.md` for each focused Codex-agent
execution, review, or verification cycle.

## Run Initialization

<!-- forge: run-open refusal for operator-cleared CRITICAL drift (FR-163) -->
Before inspecting journals or applying the successor-run exception, resolve the target repository
root and check for the operator-cleared drift block:

```bash
REPO="$(git rev-parse --show-toplevel)" || exit 1
if [ -e "$REPO/.forge/tmp/drift-block" ]; then
  printf '%s\n' \
    'forge: new run refused — CRITICAL drift block present at .forge/tmp/drift-block; operator clearance required' \
    >&2
  exit 1
fi
```

This refusal applies to every new run, including a user-designated successor. After `/forge:drift`
creates `.forge/tmp/drift-block`, only an operator may manually delete it after reading the named
durable report. Forge agents and cleanup never delete, bypass, or replace it. This file is a
run-open refusal, not an `AGENT_HALT` sentinel; agents never create or clear `AGENT_HALT` for drift.

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
11. After `run_closed`, run the post-close gates check and persist its exact JSON stdout for the
    archive renderer. Do not reconstruct that payload from the journal or from memory:

```bash
RUN_DIR=".codex-orchestrator/runs/<run-id>"
POST_CLOSE_VALIDATION_FILE="$RUN_DIR/post-close-validation.json"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" validate --gates \
  "$RUN_DIR" > "$POST_CLOSE_VALIDATION_FILE"
```

    The post-close pass must exit 0. Immediately after that successful command, before archive
    generation or any other repository operation, capture the closed implementation commit from
    command output:

```bash
CLOSING_HEAD="$(git rev-parse HEAD)" || exit 1
test -n "$CLOSING_HEAD" || exit 1
```

12. Create and commit the durable archive before invoking the report skill. First prove the index
    and tracked and untracked worktree are clean with `git status --short --untracked-files=all`;
    require its stdout to be empty. Also require both `git diff --quiet` and
    `git diff --cached --quiet` to succeed. If any proof fails, refuse with exactly:

```text
forge: archive refused — close tree contains unrelated changes
```

    Before the commitment audit, run the forge-plugin repository's routing-conformance audit when
    the target is the forge-plugin source repository. This is a repository dogfood control, not an
    installed-project requirement: ordinary target repositories do not ship
    `tests/test_repo_conformance.py`. Identify the source repository by the tracked conformance
    program and its authority files and run the check from its root. Current agent-definition and
    `system/codex/agents/*.toml` routing must conform to the committed specification. A current
    mismatch, or a recorded execution whose provider, role, recorded HEAD, or authority at that HEAD
    cannot be resolved and parsed, is repairable or unauditable and therefore remains fail closed on
    the command's nonzero exit. A fully resolved historical model/effort mismatch is immutable
    journal evidence, not a refusal: the command exits zero and names every mismatch under
    `## Historical Routing Findings`, including its journal line, agent, recorded value, expected
    value, and recorded-HEAD authority. Never suppress or reclassify those findings:

```bash
REPO="$(git rev-parse --show-toplevel)" || exit 1
cd "$REPO" || exit 1
if git ls-files --error-unmatch \
  tests/test_repo_conformance.py .claude-plugin/plugin.json \
  docs/specs/forge-plugin-spec.md >/dev/null 2>&1; then
  python3 tests/test_repo_conformance.py --run-dir "$RUN_DIR" || exit 1
fi
```

    Run the commitment audit before archive generation. For the forge-plugin source repository the
    commitment audit reruns that same routing-conformance command as defense in depth and prepends
    its exact `## Historical Routing Findings` section to the audit output. Its stdout is the sole
    source for the archive's routing findings, residual-risk, and follow-up sections; a nonzero exit
    is fail closed, so do not create an archive and therefore do not write a report:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/audit-commitments.py" --run-dir "$RUN_DIR"
```

    Then invoke the renderer from the repository root using only the closing SHA and post-close
    result captured directly above. The renderer independently reruns the commitment audit and
    embeds that exact output, preserving the order direct routing conformance → commitment audit →
    archive and making every historical routing finding part of the committed archive:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/archive-run.py" \
  --run-dir "$RUN_DIR" \
  --closing-head "$CLOSING_HEAD" \
  --post-close-validation "$POST_CLOSE_VALIDATION_FILE"
```

    Require stdout to name exactly `.forge/history/runs/<run-id>.md`. Prove with
    `git status --short --untracked-files=all` and `git diff --cached --name-only` that the archive
    is the only changed or staged path. Any other path uses the same exact archive refusal above.
    Commit exactly that one archive through `${CLAUDE_PLUGIN_ROOT}/skills/commit/SKILL.md`
    (`/forge:commit`) as a docs-class change; never stage another path or bypass the commit chain.
    Require the commit to succeed before proceeding.
13. Only after the archive commit, invoke `${CLAUDE_PLUGIN_ROOT}/skills/report/SKILL.md` to create
    `report.md` once. The report skill reruns the post-close gate validation and verifies the archive
    is committed and clean before treating the run as delivered.

The report skill refuses to write `report.md` while the post-close `validate --gates` reports issues.
The canonical close sequence is
`validate --gates → run_closed → validate --gates → archive → report.md`.
Claude still decides the semantic judgment, while gated validation enforces the recorded gate
conditions required for a clean accepted close. The final report never repairs or rewrites journal
history.
