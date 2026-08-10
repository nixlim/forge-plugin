# Control Integrity

<!-- forge: modified from upstream — condensed for plugin delivery and aligned to plugin control surfaces -->

A gate satisfied by reducing its strength is a failure, not a pass. Fix the product or the
legitimate defect in the control; never redefine success to obtain a green result.

## Protected controls

Tests, golden fixtures, coverage thresholds, validation commands, review doctrine, routing,
authority rules, hooks, halt/lock mechanisms, and evaluation baselines are controls. Within this
plugin, `skills/`, `hooks/`, `scripts/`, `rules/`, `agents/`, `.claude-plugin/`, and `system/` are
control-class surfaces.

A constitution or per-artefact profile change must bump `Profile set version`, pass the offline
evaluation suite, receive an independent PASS from `review-final`, and obtain explicit human
approval before rollout.

## Prohibited gaming

Do not delete, skip, relax, or narrow a failing test; rewrite a golden answer to bless incorrect
output; exclude relevant code from coverage; suppress a scanner, analyzer, or policy rule; weaken
review prompts, severity, routing, tool limits, or required gates; conceal a control change through
renaming or change splitting; or let an implementer approve or disposition its own major finding.

Control changes require evaluation and an independent reviewer. The implementer and binding
reviewer are separate roles. Suspected or detected gate gaming is a CRITICAL finding: return
BLOCK, preserve the evidence, escalate to the user, and stop commit, rollout, and reintegration.
