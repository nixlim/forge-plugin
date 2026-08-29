# Durable intent archive: run-20260829-phase0-recovery

## Goal

Operator-approved phase-0 legacy archive recovery: record the revision-9 legacy-archive-recovery decision for run-20260821-phase0-evals at recovered closing HEAD f64164b4f8695b745c7a4d85d09cc295aa6d3846 and commit its archive through the legacy archive mode.

## Tasks

None recorded

## Decisions

### decision-01

Task: None recorded

Finding: The phase-0 run closed before revision 9 and lacks a contemporaneous FR-172 capture; its archive requires the legacy recovery mode with a per-instance operator decision naming the recovered closing HEAD, held in an activated run.

Outcome: operator_approval

Resolution: legacy-archive-recovery: run-20260821-phase0-evals recovered closing HEAD f64164b4f8695b745c7a4d85d09cc295aa6d3846; operator approved the phase-0 legacy archive recovery on 2026-08-29 under explicit remote-control direction (deviation recorded), grounded in the target journal's check-18 passing STRICT recheck at that HEAD

Basis:

None recorded

### decision-02

Task: None recorded

Finding: Fresh-shell transient identity violated the DM-010 stable-identity contract; stale same-host takeover applied by the live harness identity.

Outcome: claude_decision

Resolution: DM-010 ownership takeover audit: the run was opened under a transient shell PID that died between tool calls; ownership taken over by the stable live session identity 472225 (the harness process), which all subsequent coordination for this session uses.

Basis:

None recorded

## Learning provenance

<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->
```json
{
  "decisions": [],
  "executions": [],
  "failed_or_inconclusive_verifications": []
}
```
<!-- END FORGE LEARNING PROVENANCE v1 -->

## Verbatim basis documents

None recorded

## Gate evidence

| Gate | Check | Candidate | Result | Reviewer verdict | Iteration | Binding source | Binding status |
|---|---|---|---|---|---|---|---|
| None recorded | None recorded | None recorded | None recorded | None recorded | None recorded | None recorded | None recorded |

## Binding discrepancies

None recorded

## Chain evidence

None recorded

## Historical Routing Findings

None recorded

## Residual Risks

None recorded

## Follow-ups

- None - single-purpose recovery run complete

## Provenance

Run ID: run-20260829-phase0-recovery

Starting HEAD: fd64d6f321cd509503a941401e69d84b677a13bc

Closing HEAD: 59ca57db3778dc7dc7c67b2aed79f5c8773ebc35

### Pre-close validation payload embedded in `run_closed`

```json
{
  "issues": [],
  "non_passing_verifications": [],
  "ok": true,
  "profile": "gates",
  "warnings": []
}
```

### Post-close validation result

```json
{
  "issues": [],
  "non_passing_verifications": [],
  "ok": true,
  "profile": "gates",
  "warnings": []
}
```
