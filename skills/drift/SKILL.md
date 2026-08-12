---
name: drift
description: Sense mechanical and semantic governance drift and write a durable periodic report.
---

# Drift

Use this skill only when an operator invokes `/forge:drift`. It combines the no-LLM mechanical
checker with one fresh, read-only semantic review. Hooks and scheduled CI only nudge or run the
mechanical checker; they never launch this skill or any model.

## 1. Run the Mechanical Checker

From the target repository root, run:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/forge/drift-check.sh"
```

Capture stdout byte-for-byte and capture the exit status without suppressing it. The only semantic
input is that stdout document: validate it as the FR-161 drift summary schema v1, including
`schema_version: 1`, before reviewing anything. Never read, derive, repair, or supplement the
semantic input from `.forge/tmp/telemetry-latest.csv`; even an intervening Stop hook overwrite of
that CSV cannot influence this review. The same-date `.forge/tmp/drift/<date>.json` is a transient
byte-identical copy for operators, not a second input.

- Exit 0 is a mechanically clean summary and proceeds to semantic review.
- Exit 1 is a schema-valid drift-present summary and also proceeds to semantic review.
- Exit 2 is a mechanical failure. Confirm stdout is the corresponding schema-valid outcome, print
  exactly `forge: drift mechanical check failed` to stderr, and stop before semantic review,
  report creation, commits, or block changes.

Any invalid JSON, wrong schema version, missing field, or mismatch between the process status and
the literal outcome object is a mechanical failure and follows the exit-2 path. Do not reinterpret
or manufacture a summary.

## 2. Run the Periodic Semantic Review

Launch one fresh reviewer in read-only mode. Apply the complete
`${CLAUDE_PLUGIN_ROOT}/rules/review-constitution.md` baseline plus the `review-periodic` profile
version 1.0. The reviewer may inspect the current repository and committed history as evidence, but
must receive the validated schema-v1 JSON as its only current mechanical and telemetry input.
For this D9 surface, the more specific FR-162 output contract replaces the constitution's generic
prose finding format: every mechanical and semantic finding is an object with exactly `check`,
`code`, `evidence`, `severity`, and `summary`. `severity` is exactly `CRITICAL`, `MAJOR`, or `MINOR`;
an `OBSERVATION` is not a drift finding. Preserve each schema-valid object in the report and never
upgrade or downgrade its severity to affect blocking.

Compare trends with the immediately preceding UTC calendar quarter. Find candidates from the
committed tree and read them from committed objects; do not trust worktree copies. For example,
enumerate with `git ls-tree -r --name-only HEAD -- .forge/history/drift` and read each candidate with
`git show "HEAD:<path>"`. Ignore malformed, working-tree-only, and other-quarter reports, then select
the valid preceding-quarter report with the greatest `generated_at`. Record the candidate inventory,
selection rules, selected report path and commit, exclusions with reasons, or that no eligible
baseline exists. Never read prior-quarter counters from `events.jsonl` or the Stop-hook CSV. Compare
the JSON's fast-path share with that baseline; growth without a committed `risk-tiers` allowlist
change in the comparison window is a semantic drift finding.

## 3. Write One Durable Report

Choose a UTC timestamp and reserve exactly one collision-free path shaped
`.forge/history/drift/YYYY-MM-DDTHHMMSSZ.md`; if it exists in either the worktree, index, or
committed tree, try `-02`, `-03`, and so on without overwriting. Create no more than one report for
this invocation. Never overwrite, amend, prune, rename, or delete an earlier drift report.

The Markdown report must include:

- the UTC generated timestamp and collision-free report path;
- mechanical checker exit status and the complete schema-v1 JSON, byte-for-byte in a fenced block;
- telemetry window, counters, and decision totals copied only from that JSON;
- semantic reviewer identity and candidate, `review-periodic` profile/version, repository HEAD,
  policy SHA copied from the JSON, and evidence scope;
- prior-quarter candidate inventory, selection/exclusions, and committed baseline references;
- every mechanical and semantic finding in FR-162's exact five-key object shape and the reviewer
  verdict;
- a disposition for every finding, including explicit operator approval for any consciously
  dispositioned finding above `MINOR`; and
- a concise CRITICAL summary used for the block, or an explicit statement that no CRITICAL finding
  exists.

Stage only the new report and commit it through the ordinary `/forge:commit` five-step chain. A
failed, refused, or unverified commit leaves the report uncommitted and stops the skill. Do not
claim completion and do not create or modify `.forge/tmp/drift-block` until `git cat-file -e
"HEAD:<report-path>"` proves that exact report is committed.

## 4. Apply CRITICAL-Only Run Blocking

If and only if at least one semantic finding has literal severity `CRITICAL`, atomically write
`.forge/tmp/drift-block` after the durable report commit is verified. Its content must include the
UTC timestamp, concise CRITICAL summary, and committed report path. Refuse to overwrite an existing
block; report the collision for operator action. The block is ignored transient state and must
never be staged or committed.

`MAJOR` and `MINOR` findings are advisory and must not block commits, merges, or run opening, and
must not create or modify the block. Only an operator clears an existing `.forge/tmp/drift-block`
after reading the named report. Forge agents never clear, bypass, or replace it, including during
cleanup. This is a run-open refusal, not halt semantics: never create or clear `AGENT_HALT` because
of drift.

Report the mechanical outcome, semantic verdict and severity counts, durable committed report path,
and whether the pre-existing or newly written operator-cleared block is present.
