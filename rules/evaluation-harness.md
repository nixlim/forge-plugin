# Evaluation Harness

<!-- forge: modified from upstream — condensed and re-rooted to plugin scripts and .forge state -->

Changes to AI controls—including prompts, agents, the review constitution and profiles,
model/effort routing, guardrails, permissions, and provider versions—must pass an offline
evaluation suite before rollout. The harness is a control regression test, not optional evidence.

Golden fixtures and committed `.result` baselines live under `.forge/evals/tasks/`. Transient plans,
logs, and results belong under `.forge/tmp/`. Run
`${CLAUDE_PLUGIN_ROOT}/scripts/forge/run-evals.sh`. Run it with `STRICT=1` whenever a control-class
change touches agent prompt templates, the review constitution, model/effort/sandbox routing,
execpolicy rules, or a Codex or Claude model/provider version; pending results then fail closed.
Fixtures declare `id`, `category`, `agent`, and `expected_verdict`. Valid verdicts are PASS, BLOCK,
and FLAG, but a review agent cannot use FLAG as its expected verdict.

Exit 0 means no regression; exit 1 means a regression or strict-mode pending result; exit 2 means
a malformed or empty suite. An empty suite never satisfies the gate. A nonzero result, missing
runner, malformed fixture, or unexplained baseline change blocks rollout and is escalated. New
real-world failure patterns should become golden fixtures, and baseline changes require the same
independent review and approval as other control changes.

<!-- forge: added — fail-closed fixture growth and provenance contract (FR-102) -->

Prefer journal-derived fixtures when growing the suite: preserve the exact recorded agent prompt
as the fixture Input, declare the expected verdict, and record provenance containing both the
orchestration run ID and the agent execution ID. Fixtures and committed `.result` baselines are
append-only evidence: never overwrite either one, and never edit a result merely to make the gate
pass. A changed expectation requires a new independently reviewed fixture and baseline.
