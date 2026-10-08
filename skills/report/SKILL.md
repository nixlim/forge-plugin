---
name: forge-report
description: Author a final run report from local execution logs, observed repository state, and chain evidence.
---

# Report

Use this skill after the orchestration work is finished. Return to
`${CLAUDE_PLUGIN_ROOT}/skills/workflow/SKILL.md` if checks or implementation remain.

## Sources

Read the complete `journal.jsonl`, the exact prompts and handoffs, observed repository changes,
and the relevant `.forge/chains/` state, events, gate outputs, review verdicts, approvals, and
landing evidence. A `run_closed` record describes the reported outcome; it is not a judgment or
permission check. `validate` checks record structure only:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" validate \
  .codex-orchestrator/runs/<run-id>
```

Report validation issues honestly. Do not edit the journal to make the report look complete.
Ground each claim in the right source: Git for delivered changes, observed checks and chain
records for gates and approvals, prompt for assignment, handoff for agent claims, and the journal
for chronology and decisions. Use raw events to resolve ambiguity. Surface missing or conflicting
facts rather than infer a passing check.

Treat a handoff as a claim until it has been checked against the repository and observed results.

## Required Report Structure

Write the local `report.md` with exactly these five top-level sections in order. Replace an
existing final report only when asked to correct or regenerate it.

```markdown
# Report

## Summary

## Changes

## Orchestration Graph

## Consensus

## Final Results
```

### Summary

State the original intent, delivered result, and main reason for that result. Name unresolved work.

### Changes

Compare final repository state with the observed starting Git baseline. Connect material changes
to tasks and agents where the evidence supports it. Do not attribute initially dirty paths
without evidence or treat an agent's files-changed claim as mechanical attribution.

### Orchestration Graph

Create a readable Mermaid `flowchart TD` from execution and decision chronology. Include Claude
and Codex agents, material checks, review and fix loops, and delivered outcomes. Name each agent's
task, recorded model and effort, main result, and observed completion status. Mark reconstructed
facts `inferred`; never infer a passing check, verdict, or terminal execution status.

### Consensus

Summarize consequential `decision` entries, user actions, accepted risks, and unresolved outcomes.
Say when no decision was required.

### Final Results

Use these subsections in order:

```markdown
### Gate Result

### Risks / Follow-ups
```

Under `Gate Result`, report each required gate and its actual outcome from chain evidence or the
merge skill's observed commands. Include candidate identity, any in-lock reruns, review verdict,
approval, pushed SHA, and cleanup outcome where applicable. A journal reference alone cannot
establish a gate result.

Under `Risks / Follow-ups`, list failed or missing checks, blocked work, user actions, accepted
risks, and concrete next steps. State the ruling or request the run implemented and list every
mechanism, field, verb or literal the change added beyond that text; an addition the ruling did
not name is a follow-up even when every gate passed. Write `None recorded.` if nothing remains. Include available tool
versions as one compact `Run metadata` bullet when observed; omit unavailable values.

## Final Check

Confirm that the five required sections appear once and in order, the graph is readable, and
material claims match Git, observed checks, and chain evidence. Reconcile numeric totals with the
underlying records or handoffs.
