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

<!-- forge: modified from upstream — atomically admit disjoint owned runs through the D13 registry -->
Before `run_started`, declare a nonempty intended repository file scope made only of positive,
repository-relative Git pathspecs. Exclude transient Forge and run state (`.forge/**`,
`.codex-orchestrator/**`, and `.worktrees/**`). Export one stable long-lived session identity with
`export FORGE_SESSION_PID=$$`; every run coordination and journal append in this shell must retain
that same value.

Open the run only through `${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py run-open`, passing
`--repo "$REPO"`, `--run-id <run-id>`, one `--scope <pathspec>` for every declared pathspec, and a
`--record-json` file containing the proposed `run_started` object. The command atomically creates
the owner sidecar with `run_started`, reconciles `.forge/tmp/run-registry.json`, and admits this run
when its scope is disjoint from every open run. It prints one exact
`forge: new run refused — scope overlap between <new-run-id> and open run <open-run-id>` line for
each conflict in bytewise run-ID order. Missing, malformed, ambiguous, or unregistered open-run
state refuses exactly `forge: new run refused — run registry unavailable`. Never bypass either
refusal by manually creating a run directory or appending a journal line.

Disjoint open runs may proceed concurrently. Scope remains fixed for the run. Before adding a task,
ensure every `task.files` pathspec is contained by its admitted run scope; widen it first, under the
same registry lock, with `run-readmit --repo "$REPO" --run-id <run-id> --scope <pathspec> ...`.
Append every later record only with `journal-append --repo "$REPO" --run-id <run-id>
--record-json <file>`, which proves the current PID/host owner before every write. A different live
owner, or a missing/malformed owner after `run_started`, is a hard refusal and leaves the journal
byte-identical.

If immutable journal damage requires a successor, never rewrite journal history: retain the run,
stop all mutation, and use `run-retire --repo "$REPO" --run-id <predecessor>` first. Then start the
user-designated successor with `run-open ... --successor-of <predecessor>`. Scope reuse is legal
only after that locked, non-mutating retirement and never over a foreign live predecessor owner.

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
2. Perform Run Initialization and use `run-open` to atomically create ownership plus `run_started`
   with the concise original goal, absolute repository path, captured Git baseline, plugin ref,
   available Claude and Codex versions, and the declared admitted scope.
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
   admitted-scope-contained `files`; append them through `journal-append`. Serialize every overlap
   in files, contracts, or shared resources;
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
7. Record only consequential resolutions or user dependencies as `decision`. Use
   `journal-append` for every record; append a terminal `task` only after its acceptance criteria
   have been evaluated.
   When correcting a journal citation, preserve the original entry and append an owned `decision`
   whose `resolution` begins exactly `citation-correction:`. Put one directive per following line:
   `<decision-id> basis[<n>]: <corrected-path>` or
   `<verification-id> observation: <cited> -> <corrected-path>`. The latest correction for the
   same citation applies; never rewrite the cited entry.
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
    the orchestration contract and locked retirement above. Otherwise use `run-close --repo
    "$REPO" --run-id <run-id> --record-json <file>` to append one final `run_closed` entry with
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

## Machine Moves Are Run Boundaries

The run journal, owner sidecar, and run registry never travel through Git; only the committed
archive under `.forge/history/runs/` does. Treat a machine or session-host move as a run boundary:
close and archive every open run before moving, recording unfinished work as honest `follow_ups`
in `run_closed`, and let the successor machine open a fresh run against the committed archive. On
a fresh clone, never resume another machine's run — open a new one. On a synced filesystem, close
the run on its origin machine first; appends from any other host refuse as foreign ownership, and
only an explicit operator-authorized owner re-stamp may transfer a live run.

When close corrections are themselves appends, order them so the journal stays closable: append
every missing terminal `execution_result` first, then a fresh passing verification for each of
gate-1, gate-2, and gate-3 (a later terminal result moves the gate-ordering anchor past every
earlier gate verification), and only then `run_closed`. A run closed in the wrong order cannot be
repaired by appending.

## Post-Report Best-Effort Learning

Only after Step 13 has finished and the archive commit plus `report.md` outcome are final, make one
best-effort invocation of `${CLAUDE_PLUGIN_ROOT}/skills/learn/SKILL.md` (`/forge:learn`). This
advisory pass is outside the canonical close sequence above and never runs inside the archive
commit. Its failure or refusal must not reopen, block, delay, or change the completed close or
report outcome. Leave every candidate or gotcha proposal unstaged and uncommitted for a separate
ordinary commit.
