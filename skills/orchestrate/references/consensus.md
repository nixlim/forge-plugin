# Consensus And Decisions

Use a `decision` only for a consequential disagreement, accepted risk, resolution, or required user
action. Do not record routine agreement. Use [the orchestration
contract](../../../docs/orchestration-contract.md) for journal fields.

Allowed outcomes:

- `consensus`: Claude and the relevant Codex agent converge after inspecting evidence.
- `claude_decision`: Claude chooses and records the rationale and residual risk.
- `user_action_required`: progress or acceptance requires an explicit user choice or external
  action.

## Resolve A Disagreement

<!-- forge: modified from upstream — implementation follow-ups always use fresh sessions (FR-033) -->

1. State the disputed finding and cite Claude's observation.
2. For an implementation follow-up, launch a fresh named implementer and native session. Only a
   targeted reviewer-confirmation round may resume that same reviewer session; do not request
   another broad review.
3. Inspect the response, repository state, and relevant checks.
4. If a fix is chosen, assign and verify it before completing the task.
5. Record a decision only when the result affects implementation, acceptance, risk, or user action.

Choose by acceptance fit, direct evidence, risk, simplicity, and reversibility—not agent count.
Record the finding, resolution, basis, and risk without erasing failed verifications. Use
`claude_decision` when Claude can proceed within existing authority; record the rejected alternative
and residual risk. Use `user_action_required` when authority or required information is missing;
unresolved required user action normally closes the run as blocked.
