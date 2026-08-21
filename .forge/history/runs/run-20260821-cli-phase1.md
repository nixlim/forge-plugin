# Durable intent archive: run-20260821-cli-phase1

## Goal

Implement CLI phase 1 - the Forge CLI commit-chain slice (beads forge-plugin-vjj): scripts/forge/cli.py per spec FR-210..FR-224 / DM-012..DM-013, FR-221 hook dual-accept in commit-guard, /.forge/chains/ gitignore entry per DM-007, un-skip both phase-1 red-line contract-test legs, full test/eval/review gates with control-class operator approval.

## Tasks

### task-01

Goal: Design the CLI phase-1 implementation: Claude plan written first (claude-plan-cli-phase1.md), independent Codex proposal, evidence-based comparison and finalized design recorded as a decision.

Acceptance criteria:

- Claude plan exists in the run dir before the Codex proposal is read
- a fresh Codex agent proposes from goal/constraints only
- the finalized design is recorded as a decision citing both plan paths

Final status: complete

Final outcome: None recorded

### task-02

Goal: Implement scripts/forge/cli.py - the complete FR-210..FR-220 commit-chain engine (DM-012 storage with append-first digest-chained events and replay, FR-211 transition table, FR-212 candidate identity/invalidation, FR-213 head-moved handling, FR-214/FR-215 resumable verify and per-tier gate running with DM-013 fingerprints, FR-216 review verbs, FR-217/FR-218 operator verbs and approval, FR-219 two-phase finalize with three-case crash recovery and injectable FINALIZE_CHECKS registry, FR-220 envelope with the closed 25-member reason enum) plus the full unit-test surface for the spec §11 Forge CLI commit chain items.

Acceptance criteria:

- scripts/forge/cli.py exists, stdlib-only, Python>=3.10
- every §11 unit item for the CLI chain has a test: transition-edge refusals, candidate binding/TTL/consumed token, restage and out-of-band invalidation with classification rerun, head_moved graded disposition, verify resumability and passed-verify no-op, mutating-gate precedence, fingerprint-pair voiding, per-tier structure, finalize crash-window recovery with every non-recovery verb refusing in committing, every internal finalize check independently disableable in memory with a focused failing test, single --json envelope, output-contract conformance
- both phase-1 red-line legs in tests/test_cli_phase0_contracts.py execute with the reason-code leg passing and the matcher leg red per decision-02
- full unittest discovery green except the matcher leg per decision-02

Final status: complete

Final outcome: None recorded

### task-03

Goal: FR-221 hook integration in scripts/forge/commit-guard.sh (dual-accept chain-or-marker commit authorization, CLI-invocation argv matcher bound to the committed 112-case corpus, exact operator-verb denial literals, index-mutating verb denial for non-owning sessions) plus the DM-007 /.forge/chains/ gitignore entry in .gitignore, scripts/forge/install.sh, and system/template/gitignore-block.txt, plus the §11 phase-1 integration tests.

Acceptance criteria:

- every FR-090 denial literal and DM-006 marker behavior byte-identical
- hook dual-accept end-to-end: chain-authorized commit admitted, marker-authorized commit admitted, model-issued commit approve/skip denied with the two exact FR-221 literals
- foreign index-mutating git verbs denied while a live chain exists
- /.forge/chains/ ignored in repo, installer block, and template
- full unittest discovery passes in the worktree

Final status: complete

Final outcome: None recorded

### task-04

Goal: Package verification and reintegration: orchestrator-observed full-suite twice consecutively, STRICT evals, red-line legs, SC-019 fixture demonstration, control-class commit through /forge:commit with binding review-final and operator approval, reintegration through /forge:worktree-merge.

Acceptance criteria:

- gate-1 passes twice consecutively orchestrator-observed after the last fix
- STRICT evals pass
- binding review-final PASS bound to the staged-diff SHA-256
- explicit operator approval naming the candidate
- fast-forward push of the approved candidate

Final status: complete

Final outcome: None recorded

## Decisions

### decision-01

Task: task-01

Finding: Claude plan and Codex proposal agree on storage (DM-012 verbatim), composition boundaries, dual-accept hook posture, literal 25-member reason enum, and the finalize disable-in-memory registry. They diverge on whether implementation must wait for spec amendments covering gate-ID grammar, mutating-gate declaration, secret-scan contract, session identity, verdict grammar, and DM-013 normalization; and on whether the hook's chain-side acceptance is incoherent because finalize's child git commit bypasses PreToolUse.

Outcome: claude_decision

Resolution: Proceed without a prior spec amendment, adopting the Codex architectural sharpenings (event digest chaining, injectable FINALIZE_CHECKS registry, single output adapter, three-case finalize recovery, optimistic concurrency). Adjudications: (1) gate IDs are an implementation naming convention over committed policy tables the spec already designates (gate1-test-command, stack-validations categories, invariants rows, sensor, secret scan, STRICT evals) - defining names is not new authority; (2) no mutating gate is configured in this repository (changelog-policy: none), so the mutating-gate ordering machinery is implemented against test fixtures and its policy grammar is documented as a candidate spec-revision follow-up; (3) no tested standalone secret scanner exists, so scan secrets is new CLI-owned code with planted-positive-control tests - FR-210 forbids reimplementing tested controls, and no tested executable is being reimplemented; (4) session identity for the index-verb denial uses the harness-provided channel with re-hash as spec-designated backstop and FR-218-style honest-limits documentation; (5) the finalize child git commit never traverses PreToolUse, which is consistent with FR-221: the hook's chain-side acceptance targets model-issued git commit while a chain is authorized, and a raw commit that matches the bound candidate converges through the FR-219 recovery path to the same closed chain - no incoherence; (6) verdict grammar and DM-013 normalization are implementation-defined, pinned by tests, and adjudicated by the binding control-class review, with a phase-1.1 editorial spec amendment filed as follow-up. Implementation proceeds in the isolated worktree .worktrees/forge/cli-phase1 as serialized tasks with a single control-class package commit at the end (phase-0 precedent 3f70810), recorded here as the checkpoint-consolidation decision.

Basis:

- claude-plan-cli-phase1.md
- codex-plan-01/execution-01/handoff.md

### decision-02

Task: task-02

Finding: The phase-1 matcher red-line leg activates the moment scripts/forge/cli.py exists but asserts against the commit-guard matcher that task-03 delivers, so task-02 cannot reach a fully green discovery run alone.

Outcome: claude_decision

Resolution: Execute task-02 (cli.py plus unit tests) before task-03 (hook integration); amend task-02 acceptance to: full unittest discovery green except test_phase1_hook_consumes_committed_matcher_vectors, which task-03 must turn green; final twice-consecutive full-suite verification remains a task-04 obligation over the complete package.

Basis:

- codex-plan-01/execution-01/handoff.md
- claude-plan-cli-phase1.md

### decision-03

Task: task-04

Finding: Control-class phase-1 candidate 10cb6e2526622687df0bd6705e59b8cec6a57033aa0105953a9f5c061d5a3106 passed review-final (iteration 1, 0 CRITICAL/MAJOR, 3 MINOR, 2 OBSERVATION) and required operator approval.

Outcome: user_approval

Resolution: Operator explicitly approved the exact candidate SHA-256 at 2026-08-21T21:47Z, within the 30-minute freshness window of the 21:46:22Z PASS; committed as b3493a2890f079abcfad2a25edbffd10a5dda56f on forge/cli-phase1 via the five-step chain (halt, lock, marker validation by the PreToolUse guard, hash re-verification, release). The three MINOR findings (iteration-cap over-refusal on PASS-converged control chains, frozen-chain abort remediation dead-end, scan-secrets auto-unstage spec silence) are recorded as residual risk for follow-up.

Basis:

- codex-impl-01/execution-02/handoff.md
- codex-impl-02/execution-03/handoff.md

### decision-04

Task: task-04

Finding: Merge Gate 4 required operator approval for the control-class range 51e1187e8b6e282bd70e5822c7d60c33be388199...b3493a2890f079abcfad2a25edbffd10a5dda56f.

Outcome: user_approval

Resolution: Operator explicitly approved candidate HEAD b3493a2890f079abcfad2a25edbffd10a5dda56f; locked rebase was a no-op fast-forward (DEFAULT_ADVANCED=0, CANDIDATE_REWRITTEN=0), pushed to origin/main, containment verified, worktree .worktrees/forge/cli-phase1 removed and branch forge/cli-phase1 deleted, local main fast-forwarded. Residual MINOR findings carried to follow-ups: iteration-cap over-refusal on PASS-converged control chains; frozen-chain abort remediation dead-end; scan-secrets auto-unstage spec silence; corpus integration test leaking guard_deny events into live telemetry; stash-list over-denial; --json help-path envelope bypass.

Basis:

- codex-impl-01/execution-02/handoff.md
- codex-impl-02/execution-03/handoff.md

## Learning provenance

<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->
```json
{
  "decisions": [
    {
      "id": "decision-01",
      "task": "task-01"
    },
    {
      "id": "decision-02",
      "task": "task-02"
    },
    {
      "id": "decision-03",
      "task": "task-04"
    },
    {
      "id": "decision-04",
      "task": "task-04"
    }
  ],
  "executions": [
    {
      "agent": "codex-plan-01",
      "execution": "execution-01",
      "prompt": "codex-plan-01/execution-01/prompt.md",
      "prompt_sha256": "c16a12b509b24911f54d7ba4e93fbd296bf94b065a600c1027c1ae1c08ae702a",
      "role": "implementation",
      "task": "task-01"
    },
    {
      "agent": "codex-impl-01",
      "execution": "execution-02",
      "prompt": "codex-impl-01/execution-02/prompt.md",
      "prompt_sha256": "d57cf32525245283f6cf1f244f715e2a2e8641b191a129accd0dde1f625b2a0e",
      "role": "implementation",
      "task": "task-02"
    },
    {
      "agent": "codex-impl-02",
      "execution": "execution-03",
      "prompt": "codex-impl-02/execution-03/prompt.md",
      "prompt_sha256": "6c5b74282e7ecee8ce15a1560602913e23bfacf50b1500fc9e578214039f42ea",
      "role": "implementation",
      "task": "task-03"
    }
  ],
  "failed_or_inconclusive_verifications": [
    {
      "criterion": "gate-1: project tests",
      "id": "check-02",
      "observation": "Ran 840 tests; FAILED (failures=1, skipped=3); sole failure test_phase1_hook_consumes_committed_matcher_vectors, red by decision-02 until task-03; reason-code red-line leg executes and passes; orchestrator-observed.",
      "result": "failed",
      "task": "task-02"
    }
  ]
}
```
<!-- END FORGE LEARNING PROVENANCE v1 -->

## Verbatim basis documents

### claude-plan-cli-phase1.md

<!-- BEGIN VERBATIM DOCUMENT: claude-plan-cli-phase1.md -->
# Claude plan — CLI phase 1 (written before reading any Codex proposal)

Authority: docs/specs/forge-plugin-spec.md revision 6, FR-210..FR-224, DM-012..DM-013;
docs/design/0003-forge-cli-plumbing.md phases 0-2. Beads issue forge-plugin-vjj.

## Deliverables

1. `scripts/forge/cli.py` — stdlib-only Python ≥ 3.10, the commit-chain state machine
   (FR-211 states exactly: classifying, verifying, reviewing, revising, awaiting_approval,
   authorized, committing, closed, aborted), invoked as
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py" <verb>`.
2. FR-221 dual-accept in `scripts/forge/commit-guard.sh`: chain-authorized `git commit`
   acceptance alongside the byte-identical DM-006 marker path; CLI-invocation argv matcher
   (grammar pinned by the committed phase-0 corpus `system/fr223/hook-argv-cases-v1.json`);
   model-issued `commit approve`/`commit skip` denial with the two exact FR-221 literals;
   index-mutating git verb denial for sessions that do not own the live chain.
3. DM-007 `/.forge/chains/` gitignore entry in this repo's `.gitignore`, in
   `scripts/forge/install.sh`'s gitignore block, and in `system/template` where applicable.
4. Tests: unit coverage for every §11 "Forge CLI commit chain" item (transition-edge refusals,
   candidate binding/TTL/consumed token, restage and out-of-band invalidation, head_moved graded
   disposition, verify resumability, DM-013 fingerprint pair voiding, per-tier structure,
   finalize two-phase crash-window recovery, every internal finalize check independently
   disableable in memory with a focused failing test, `--json` single-envelope conformance,
   reason-code/output-contract conformance) plus §11 integration items (phase-0 evals precede
   phase-1 surface tests, hook dual-accept end-to-end, operator-verb denial, foreign
   index-verb denial, review launch/collect/attach citation checks). Both phase-1 red-line
   legs in tests/test_cli_phase0_contracts.py execute with no new skip condition and no
   corpus copy.

## Architecture decisions (candidate — subject to FR-124 comparison)

- **A1 storage**: DM-012 verbatim — `.forge/chains/<chain-id>.json` materialized state,
  `.forge/chains/<chain-id>.events.jsonl` append-only, artifacts under
  `.forge/chains/<chain-id>/`. Event written first, then state; startup divergence replayed
  from events; irresolvable divergence = exit-2 frozen. Finalize window exempt from replay:
  recovery observes HEAD per FR-219. chain_id `c-<UTC compact>-<4hex>`; schema `forge-chain/1`;
  exact DM-012 top-level key set.
- **A2 composition (FR-210)**: subprocess composition of check-halt.sh,
  acquire/release-commit-lock.sh, risk_tier.py (`--staged`, both for classification and the
  finalize-time fast eligibility recomputation), run-evals.sh, check-test-quality.py,
  emit-decision-event.py, and the committed-policy gate/invariant runners under FR-149
  discipline (one-cell `bash -c` argv, isolated process group, 64KiB cap, 1200s timeout).
  No reimplementation of halt/lock/classification. No extraction from commit-guard.sh in this
  phase: every composed control already exists as a tested standalone executable; the guard's
  embedded fast-recompute stays where its disable-in-memory tests point.
- **A3 secret scan**: no tested standalone executable exists today; the CLI's `scan secrets`
  implements the staged-patch pattern scan (added-line credential/key/token/private-key/env
  patterns) as new CLI-owned code with its own unit tests and a planted positive control.
- **A4 reason codes**: cli.py defines the FR-220 closed enum as a frozen table; the phase-1
  red-line test leg binds it (consumes, never copies) to `system/fr223/reason-codes-v1.json`
  and the spec text. Envelope: exact sorted-key JSON `{schema "forge-cli/1", ok, chain_id,
  state, reason_code, message, expected, observed, remediation, next_required_step,
  evidence_refs}`; human output ends with the exact `next required step:` line.
- **A5 session ownership** (FR-221 index-verb denial): the chain file records at `start` the
  hook-relevant session identity (CLAUDE session env when present; else the FORGE_SESSION_PID
  form). The guard denies index-mutating git verbs (`add`, `restore --staged`, `reset`,
  `rm --cached`, `stash`) only when a live chain exists for the invoking worktree and the
  recorded identity does not match; absence of any recorded identity falls back to deny-only
  re-hash backstop semantics exactly as FR-221 scopes them ("only sessions running under the
  hook are bound").
- **A6 finalize checks**: each internal finalize check (evidence completeness, candidate byte
  identity, TTL, tree-vs-index drift, halt, lock) is a named, individually replaceable
  predicate in a registry structure so a test can disable exactly one in memory and prove the
  focused failure (FR-223 severity doctrine).
- **A7 fingerprints**: DM-013 `env_fingerprint` = SHA-256 of canonical sorted-key JSON
  `{command_digest, cwd, platform, policy_digest, python_version, repo_head}` attached to every
  gate/scan record; gate-1 twice-consecutive validity requires equal fingerprints.

## Execution shape

Serialized tasks in one isolated worktree (`.worktrees/forge/task-01-cli-phase1`, branch
`forge/task-01-cli-phase1` from current main), fresh Codex implementer per task, independent
verification by the orchestrator after each handoff, single control-class commit of the whole
phase-1 package at the end through /forge:commit (STRICT evals + review-final + operator
approval bound to the staged-diff SHA-256), then /forge:worktree-merge (Gate 4 operator
approval bound to the candidate HEAD). Precedent: the phase-0 package (3f70810) shipped the
same way. This consolidation is recorded as a decision.

- task-01: cli.py core — storage/event-log/replay, envelope + reason codes, state machine,
  `status`, `commit start`, `abort`, `restage`, `rebase`, `classify`; focused unit tests.
- task-02: evidence engine — `verify` (resumable), `gate run` (mutating-first ordering),
  `scan secrets`, DM-013 fingerprints, per-tier required-step tables; unit tests.
- task-03: judgment verbs — `review request/collect/attach/disposition`, approve/skip
  (operator posture), authorization token, `finalize` two-phase + crash-window recovery +
  disable-detection registry; unit tests.
- task-04: FR-221 guard dual-accept + matcher + denials; gitignore/install/template updates;
  integration tests; red-line legs green; full-suite + STRICT twice-consecutive.
- task-05: package verification, gate chain, commit, reintegration.

## Acceptance criteria (run-level)

- SC-019 demonstrable: a chain driven only by CLI verbs completes end to end on a fixture
  repo with every evidence record CLI-captured and candidate-bound; hook dual-accepts both
  authorization forms; control-class chains cannot commit without operator approval naming
  the exact candidate; disabling any single finalize check in memory fails its focused test.
- Both red-line legs execute and pass; no new skip condition; corpora consumed not copied.
- `python3 -m unittest discover -s tests` passes twice consecutively after the last fix.
- STRICT evals 7/7; FR-090/FR-220/FR-221 literals byte-identical.

## Risks

- Guard changes are the highest-blast-radius surface (existing byte-pinned literals and
  disable-in-memory tests must stay green while adding dual-accept and new denials).
- Session-identity mechanism for the index-verb denial has environmental variance; scoped
  deliberately narrow with re-hash as backstop.
- Harness tool-execution ceiling vs. gate-1 duration is why `verify` is resumable; tests must
  not depend on wall-clock.
<!-- END VERBATIM DOCUMENT: claude-plan-cli-phase1.md -->

### codex-plan-01/execution-01/handoff.md

<!-- BEGIN VERBATIM DOCUMENT: codex-plan-01/execution-01/handoff.md -->
## Status

Design proposal complete, read-only. No implementation or acceptance-gate PASS is claimed.

The design is conditionally viable, but implementation must remain blocked until the committed specification resolves several control-authority gaps—most critically the missing gate registry, secret-scan executable, authenticated session ownership, and the inability of the current hook to observe `finalize`’s child `git commit`.

## Summary

**Architecture**

- Add [cli.py](/home/agents/foundry-of-zero/forge-plugin/scripts/forge/cli.py) as a Python 3.10+ standard-library command dispatcher. Keep it non-executable and invoke it through the current Python interpreter.
- Store chains in the common checkout’s `/.forge/chains/`, lazily created with directory mode `0700` and files mode `0600`.
- Use DM-012’s exact top-level state keys. Put implementation details beneath their existing nested objects; do not add top-level keys without specification authority.
- Use append-first event sourcing:
  1. Acquire a short transaction lock.
  2. Verify the current state generation and event tail.
  3. Append and `fsync` one canonical event containing sequence, previous digest, full next-state snapshot, next digest, actor, time, and artifact references.
  4. Atomically replace and `fsync` the materialized state.
  5. Release the lock before running any long-lived gate or reviewer.
- Replay events whenever state and tail disagree. Malformed tails, digest conflicts, missing sequences, or irreconcilable replay freeze the chain; automation must never truncate or silently repair the event log.
- Long operations use optimistic concurrency: persist a launch event, run outside the lock, then reacquire and accept the result only if candidate, HEAD, policy, and generation remain compatible.
- Persist plain observed HEAD alongside every evidence item. DM-013’s fingerprint supplements this value; it does not replace it.

**State machine**

Use an explicit transition table rather than command-local conditionals:

- `start`: stage only explicit paths, create `classifying`, run the composed classifier, then enter `verifying`.
- `verifying`:
  - fast tier enters `authorized` only after every mechanical check and the independent fast-policy recomputation;
  - standard, hard, and control tiers enter `reviewing` after mechanical evidence is complete.
- `reviewing`:
  - PASS for standard/hard enters `authorized`;
  - PASS for control enters `awaiting_approval`;
  - BLOCK enters `revising` and increments the iteration counter.
- `revising`: explicit restaging creates a new candidate and returns to `classifying`; refuse beyond iteration eight.
- `awaiting_approval`: an operator approval bound to the exact candidate enters `authorized`.
- `authorized`: successful finalize progresses through `committing` to `closed`.
- `committing`: only status and recovery should be permitted.
- `closed` and `aborted`: status-only terminal states.

Every mutating command first validates repository context and composes the halt check. Unexpected HEAD movement records the old and new HEAD as an out-of-band change and blocks advancement until explicit rebase or abort. Index drift invalidates all evidence bound to the old candidate and returns the chain to classification. Tier changes are promotion-only.

**Finalize recovery window**

Before invoking Git, persist an intent containing the candidate digest, pre-commit HEAD, message digest, authorization token, and state `committing`.

Recovery then has three deterministic cases:

- HEAD still equals the pre-commit HEAD: return to `authorized` only if the token remains valid and unconsumed.
- HEAD is exactly one child of the pre-commit HEAD and its committed diff equals the candidate: record the commit, consume the token, and close idempotently.
- Any other history shape: retain `committing`, freeze the chain, and return exit 2 with `frozen-chain`.

The committed specification must define whether a failed `git commit` consumes the token and how `abort` behaves during `committing`.

**Composition boundaries**

The CLI should orchestrate, pin inputs, bound output, and translate results; it must not reproduce tested controls:

- `check-halt.sh commit`
- `acquire-commit-lock.sh` / `release-commit-lock.sh`
- `risk_tier.py --repo … --policy-sha … --staged`
- `run-evals.sh` with `STRICT=1`
- `check-test-quality.py`
- `emit-decision-event.py`, exactly once after the primary outcome

Three required controls lack suitable standalone interfaces:

- FR-154 fast-policy recomputation is embedded inside [commit-guard.sh](/home/agents/foundry-of-zero/forge-plugin/scripts/forge/commit-guard.sh).
- Invariant execution is embedded in a hook-oriented implementation.
- No tested staged-diff secret-scan executable exists.

These must be separate control-class extraction/interface tasks. Both the existing callers and the CLI must consume the shared implementations, with focused tests proving the old enforcement remains active. CLI-local copies would violate FR-210.

`check-test-quality.py` currently examines working-tree files. Exact-candidate use therefore requires either enforced tree/index equality or an approved staged-input extension.

**Hook integration**

Extend the existing hook parser with `classify_forge_cli_invocation(command)`, using its quote-aware command-cell splitter and the committed 112-case argv corpus directly. The accepted grammar must remain narrow: exact `env` with assignments, supported Python executable spellings, and the exact CLI path/verbs. Do not broaden it to `/usr/bin/env`, env options, arbitrary wrappers, Python flags, or bare assignments.

Hook behavior:

- Preserve every FR-090 denial and all DM-006 marker parsing, freshness, and hash behavior byte-for-byte.
- Commit authorization becomes `valid_marker OR valid_chain`, after the existing commit-stability checks.
- A valid marker must still authorize when chain data is corrupt; a valid chain must authorize when the marker is absent or invalid.
- Deny operator verbs with the exact literals:
  - `forge: operator verb denied — present the candidate and ask the operator to run this via ! (commit approve)`
  - `forge: operator verb denied — present the candidate and ask the operator to run this via ! (commit skip)`
- For a live chain, classify `git add`, `git restore --staged`, `git reset`, `git rm --cached`, and `git stash` as index writers. Permit only the authenticated owning session.
- First denied command segment wins; recognized non-operator CLI commands otherwise pass through.

An untrusted environment variable or CLI flag cannot establish ownership. The Claude hook input presently has no authenticated session identity, so foreign-session enforcement needs a normative harness-to-hook identity channel.

**Secret scan**

Introduce a shared staged-secret control only after its contract is committed and approved. It should:

- Pin repository, index identity, expected candidate digest, and HEAD.
- Rehash the exact staged diff before scanning.
- Compose the approved configured scanner/rules.
- Return canonical structured output with outcome, candidate digest, rule IDs, and locations—never secret values.
- Use exit 0 for clean, 1 for findings, and 2 for infrastructure failure.
- Cap captured output and store any transcript with mode `0600`.

The commit skill and CLI must call this same executable. Scanner rules, configuration discovery, redaction, diagnostics, and timeout behavior are not currently authoritative.

**DM-013 fingerprint**

Subject to a specification amendment pinning the precise inputs:

- `command_digest`: SHA-256 of canonical compact JSON containing the exact argv vector and only explicitly enumerated relevant environment overrides.
- `policy_digest`: SHA-256 of the exact raw committed `forge-project.md` bytes at the pinned repository HEAD.
- Fingerprint preimage:
  `{command_digest, cwd, platform, policy_digest, python_version, repo_head}`
- Encode with UTF-8, sorted keys, compact separators, `ensure_ascii=False`, and no trailing newline; SHA-256 that byte sequence.
- Persist both the preimage fields and resulting fingerprint in every evidence record.

The exact `platform`, Python-version representation, cwd normalization, and relevant environment allowlist must be made normative before implementation.

**Output contract**

Implement `ReasonCode` as a literal `str, Enum` containing all 25 committed values; do not dynamically construct it from the corpus.

Route every result through one output adapter:

- JSON mode emits exactly one sorted-key FR-220 object with the 11 required keys and schema `forge-cli/1`.
- Human mode ends with exactly one `next required step: …` line, except the specified closed-state form.
- `--verbose` sends bounded live activity to stderr so JSON stdout remains pure.
- Exit 0 is exclusive to `ok`; `frozen-chain` exits 2; all other reason codes exit 1.

**Disable-in-memory doctrine**

Define finalize’s six mandatory checks through an injectable `FINALIZE_CHECKS` registry:

1. Evidence completeness
2. Authorization TTL/token
3. Tree/index drift
4. Composed halt check
5. Composed lock acquisition
6. Candidate-byte verification under the lock

For each check, a focused test must:

- Arrange for only that check to reject.
- Assert the exact reason, remediation, next step, and that the Git commit spy was not invoked.
- Replace only that registry entry in memory with a passing function.
- Re-run the same scenario and prove the original refusal assertion now fails and the commit path becomes reachable.

Every newly extracted or introduced control needs an equivalent focused disable test.

**Serialized implementation tasks**

1. Amend committed authority: gate registry and mutating outputs; nested chain/event schema; explicit run context; authenticated session ownership; complete command/state/reason table; secret scanner; verdict/disposition/co-sign grammar; finalize token/recovery behavior; DM-013 normalization; artifact/archive ownership; JSON/verbose behavior; hook/finalize admission model.
2. Run STRICT evals, binding review, and obtain operator approval for that authority candidate.
3. Qualify the current hook/CLI argv corpus against the installed Claude major/minor and distribution.
4. Extract FR-154 recomputation and invariant execution into shared tested controls; add staged candidate support to test-quality if selected; create the shared secret scanner. Review and approve each control-class candidate separately.
5. Add `/.forge/chains/` to the root and template ignore blocks, extend installer postconditions/migration tests, and extend archive/run-context handling.
6. Implement the chain engine, literal reason enum, output adapter, verification scheduler, reviewer lifecycle, finalize/recovery, and all unit tests without landing a placeholder `cli.py`.
7. In the same atomic phase-1 candidate, update the hook classifier, dual acceptance, operator denial, and index ownership. Adding `cli.py` immediately activates both red-line tests.
8. Run focused tests, both red-line legs, SC-019, repository conformance, STRICT evals, and two consecutive serial full-discovery runs after the final fix. Read PASS from each suite’s own output tail.
9. Obtain independent binding review, apply any corrections, repeat affected checks and both full runs, then obtain operator approval. Reintegration remains the orchestrator’s responsibility.
10. Treat FR-224 skill dogfooding and zero-drift sensing as a subsequent phase-2 candidate.

## Files Changed

None. The worktree remained unmodified.

## Claims

- [cli.py](/home/agents/foundry-of-zero/forge-plugin/scripts/forge/cli.py) is absent at the assigned revision.
- Consequently, the two phase-1 corpus-consumption tests are currently skipped solely because that file does not exist. Adding it activates both legs; no new skip is permitted.
- The immutable hook corpus contains 112 matcher cases, and the reason-code corpus requires 25 literal enum values.
- The root [.gitignore](/home/agents/foundry-of-zero/forge-plugin/.gitignore) and [gitignore-block.txt](/home/agents/foundry-of-zero/forge-plugin/system/template/gitignore-block.txt) omit `/.forge/chains/`.
- [install.sh](/home/agents/foundry-of-zero/forge-plugin/install.sh) already reconciles the canonical template block, so updating that block upgrades existing installations on re-init. Its postconditions should additionally prove `.forge/chains` is effectively ignored.
- Chain creation can remain CLI-lazy; FR-080 does not require installation to precreate the directory.
- The current committed policy has no machine-readable stable gate IDs, mutating-gate declarations, or output paths sufficient to implement FR-214 without inventing authority.
- DM-012’s exact top-level schema provides no session/worktree owner or explicit run context.
- The hook sees the outer `python … cli.py commit finalize` invocation, not the CLI’s child `git commit`. Therefore, the specified chain-side hook admission cannot currently authorize or consume the internal commit, while authorizing a later raw `git commit` would bypass finalize and token consumption.
- Writable ignored chain state is not authenticated. If the threat model includes a hostile repository-writing model, approval and authorization records require an integrity mechanism or a narrower stated threat boundary.
- The named file scope is insufficient for full compliance: archive handling, extracted shared controls, run-context contracts, installer verification, and potentially committed policy/specification surfaces must also change.

## Verification

- Confirmed HEAD as `f64164b4f8695b745c7a4d85d09cc295aa6d3846`.
- Confirmed the worktree had no modified files after the read-only investigation.
- No unit, integration, STRICT, or gate suite was run; doing so would not satisfy the design-only assignment and the CLI-dependent legs are presently skipped.
- An independent adversarial review initially blocked the proposal, requested corrections around event atomicity, ownership, hook visibility, artifact authority, and failure mappings, and then returned PASS for this conditional design. That review does not authorize implementation or release.

Thus SC-019, both active red-line legs, two consecutive full-discovery passes, and STRICT PASS remain future implementation acceptance requirements—not observed results.

## Caveats

Implementation is infeasible without inventing policy unless authority first resolves:

- Stable gate IDs, ordering, mutation declarations, outputs, skip semantics, and changelog precedence.
- A tested staged-secret scanner and its exact rules, timeout, diagnostics, and redaction contract.
- Authenticated session identity for hook-enforced index ownership and its exact foreign-session denial.
- The hook/finalize visibility conflict for the child `git commit`.
- Full nested chain/event schemas and whether chains live in the common checkout.
- Explicit run/task/agent/execution context and the conflicting review-artifact locations.
- Complete verb-by-state guards and mappings for every failure into the existing reason-code enum.
- Abort behavior during `committing`, token consumption after commit failure, and recovery semantics.
- Verdict grammar, citation syntax, disposition/co-sign format, and control-review attachment rules.
- DM-013’s exact platform, Python version, cwd, argv, and environment normalization.
- Whether the current lock helper may be used for short chain-state transactions despite its commit-specific diagnostics and 300-second stale policy.
- Archive inclusion of chain state/events and the integrity expectations for ignored writable authorization state.

No suspected prompt injection was encountered during the repository inspection.<!-- END VERBATIM DOCUMENT: codex-plan-01/execution-01/handoff.md -->

### codex-impl-01/execution-02/handoff.md

<!-- BEGIN VERBATIM DOCUMENT: codex-impl-01/execution-02/handoff.md -->
## Status

Complete within owned scope. Changes remain uncommitted and unstaged. Independent adversarial review returned PASS.

## Summary

Implemented the FR-210..FR-220 commit-chain engine with:

- Digest-chained persistence, replay, atomic state updates, concurrency locks, and candidate invalidation.
- Composed classification, gates, halt/lock controls, evaluation, review, approval, secret scanning, and decision events.
- Resumable verification, tier enforcement, DM-013 fingerprints, operator skips, and review dispositions.
- Detached, digest-bound Codex review with hardened artifact handling.
- Two-phase finalize, exact authorization TTL enforcement, and all FR-219 recovery cases.
- Exact human/JSON output contracts and the static 25-member `ReasonCode` enum.

## Files Changed

- [scripts/forge/cli.py](/home/agents/foundry-of-zero/forge-plugin/.worktrees/forge/cli-phase1/scripts/forge/cli.py:1) — 5,521 lines, mode 0664.
- [tests/test_cli_chain.py](/home/agents/foundry-of-zero/forge-plugin/.worktrees/forge/cli-phase1/tests/test_cli_chain.py:1) — 2,587 lines, mode 0664.
- [tests/test_cli_chain_finalize.py](/home/agents/foundry-of-zero/forge-plugin/.worktrees/forge/cli-phase1/tests/test_cli_chain_finalize.py:1) — 1,271 lines, mode 0664.

No other files were changed.

## Claims / Findings

- The module imports without operational side effects and uses only the Python standard library.
- The committed reason-code corpus matches exactly.
- All 78 focused tests pass, including every injectable finalize check, concurrency, recovery, review substitution, transition, fingerprint, drift, and envelope case.
- Full discovery was repeated twice after the final fix; both runs had only the explicitly permitted hook matcher failure.
- Spec resolutions:
  - Followed the assignment’s binding CLI-owned secret-scanner decision, pinned by the positive-control test.
  - Used DM-012 `.forge/chains/` artifact storage; run-journal writing remains an explicit-`--run-id` stub.
  - Raw policy-byte continuity is checked before parsing, so malformed changed policy correctly ends the chain as `policy-changed`.
  - Per-artifact profile mappings are included in the actual detached-review prompt.
  - Production controls ignore `FORGE_CLI_*` environment overrides; tests inject module constants in-process.

## Commands Reported

- `python3 -m unittest tests.test_cli_chain tests.test_cli_chain_finalize`
  - Progressive clean runs: 67, 71, 77, then final 78 tests.
  - Final tail: `Ran 78 tests in 41.474s` / `OK`.
- `python3 -m unittest tests.test_cli_chain_finalize`
  - `Ran 29 tests in 2.526s` / `OK`.
- `python3 -m unittest tests.test_cli_chain`
  - Completed intermediate run: `Ran 31 tests in 34.231s` / `OK`.
- `python3 -m unittest tests.test_cli_phase0_contracts`
  - `Ran 27 tests in 1.404s` / `FAILED (failures=1)`.
  - Sole failure: `test_phase1_hook_consumes_committed_matcher_vectors`.
- `python3 -m unittest tests.test_cli_phase0_contracts.Phase1CorpusConsumptionTests.test_phase1_cli_consumes_committed_reason_code_corpus`
  - `Ran 1 test in 0.009s` / `OK`.
- `python3 -m unittest tests.test_repo_conformance`
  - `Ran 22 tests in 0.833s` / `OK`.
- `STRICT=1 bash scripts/forge/run-evals.sh`
  - `tasks=7 pass=7 fail=0 pending=0 malformed=0 strict=1`
  - `OK (no regressions in recorded results)`.
- `python3 -m unittest discover -s tests`, final run 1:
  - `Ran 840 tests in 238.965s`
  - `FAILED (failures=1, skipped=3)`, solely the hook matcher.
- Same discovery command, final run 2:
  - `Ran 840 tests in 241.294s`
  - Identical sole failure and skip count.
- Final `py_compile`, trailing-whitespace scan, and mode/status checks completed cleanly.

## Caveats / Blockers

- The sole remaining failure is the explicitly allowed `commit-guard.sh` matcher leg. Hook integration belongs to the next task and was not modified.
- Arbitrary raw external index mutations remain governed by the forthcoming FR-221 hook; this CLI serializes its own operations and rechecks candidate bytes immediately before intent.
- No files were staged, committed, or pushed.<!-- END VERBATIM DOCUMENT: codex-impl-01/execution-02/handoff.md -->

### codex-impl-02/execution-03/handoff.md

<!-- BEGIN VERBATIM DOCUMENT: codex-impl-02/execution-03/handoff.md -->
## Status

Complete. All acceptance gates passed. Changes remain uncommitted, unstaged, and unpushed.

## Summary

Implemented FR-221 hook classification and operator-verb denial, live-chain commit authorization, foreign-session index protection, DM-007 ignore surfaces, installer postconditions, and hermetic integration coverage.

## Files Changed

- [.gitignore](/home/agents/foundry-of-zero/forge-plugin/.worktrees/forge/cli-phase1/.gitignore:20)
- [scripts/forge/commit-guard.sh](/home/agents/foundry-of-zero/forge-plugin/.worktrees/forge/cli-phase1/scripts/forge/commit-guard.sh:288)
- [scripts/forge/install.sh](/home/agents/foundry-of-zero/forge-plugin/.worktrees/forge/cli-phase1/scripts/forge/install.sh:622)
- [system/template/gitignore-block.txt](/home/agents/foundry-of-zero/forge-plugin/.worktrees/forge/cli-phase1/system/template/gitignore-block.txt:3)
- [tests/test_cli_hook_integration.py](/home/agents/foundry-of-zero/forge-plugin/.worktrees/forge/cli-phase1/tests/test_cli_hook_integration.py:60)

## Claims / Findings

- All 112 FR-223 corpus cases pass both module-level classification and end-to-end hook execution.
- `commit approve` and `commit skip` produce their byte-exact denial reasons and one guard-denial event.
- Git commits are admitted independently by either a valid DM-006 marker or a valid live chain.
- Expired, consumed, future-issued, hash-mismatched, foreign-worktree, corrupt, oversized, or symlink-routed chain state cannot authorize.
- Foreign sessions are denied for the specified index-mutating verbs; owning, absent, terminal, inactive, and unidentified chains do not deny.
- Existing FR-090 diagnostics and marker recomputation behavior remain pinned by regression tests.
- Fresh install and re-init add exactly one `/.forge/chains/` rule, while history and eval candidates remain visible.
- Grammar decisions additionally pinned by tests:
  - `git restore -S` and combined forms such as `-SW` are treated as `--staged`.
  - Options appearing after `--` are treated as operands.
  - Classifier matching follows the committed `fr223_eval.py` oracle for literal `env`, recognized verbs, segment precedence, and final path components.
  - Chain reads use a defensive 1 MiB limit and reject unsafe intermediate symlinks.
- Independent read-only review initially found six issues; after corrections and load-bearing regression tests, its final result was `PASS`. Binding gate decisions remain with the orchestrator.

## Verification

- `bash -n scripts/forge/commit-guard.sh scripts/forge/install.sh` — silent exit 0 on both runs.
- `python3 -m unittest tests.test_cli_hook_integration`
  - `Ran 8 tests in 21.292s` — `OK`
  - `Ran 13 tests in 28.033s` — `OK`
  - `Ran 14 tests in 28.602s` — `OK`
  - Final repeat: `Ran 14 tests in 26.634s` — `OK`
- `python3 -m unittest tests.test_cli_phase0_contracts`
  - `Ran 27 tests in 16.232s` — `OK`
  - After fixes: `Ran 27 tests in 19.351s` — `OK`
- `python3 -m unittest tests.test_installer`
  - `Ran 29 tests in 5.211s` — `OK (skipped=1)`
- `python3 -m unittest tests.test_migration`
  - `Ran 34 tests in 5.570s` — `OK`
- `python3 -m unittest tests.test_installer tests.test_migration`
  - `Ran 63 tests in 12.558s` — `OK (skipped=1)`
- `python3 -m unittest tests.test_commit_guard`
  - Evidenced rerun: `Ran 49 tests in 38.780s` — `OK`
  - After fixes: `Ran 49 tests in 41.762s` — `OK`
  - One earlier invocation returned progress dots without a terminal tail and was discarded as evidence.
- `python3 -m unittest tests.test_repo_conformance`
  - `Ran 22 tests in 0.868s` — `OK`
- Consecutive full discovery run 1:
  - `Ran 854 tests in 323.656s`
  - `OK (skipped=3)`
- Consecutive full discovery run 2:
  - `Ran 854 tests in 293.486s`
  - `OK (skipped=3)`
- `STRICT=1 bash scripts/forge/run-evals.sh`
  - Seven tasks passed.
  - `tasks=7 pass=7 fail=0 pending=0 malformed=0 strict=1`
  - `OK (no regressions in recorded results)`
- `git diff --check` — silent exit 0.

## Caveats / Blockers

- No implementation blockers.
- Pre-existing task-02 files `scripts/forge/cli.py`, `tests/test_cli_chain.py`, and `tests/test_cli_chain_finalize.py` remain untracked and untouched.
- The repository-provided Beads block demanded a push, conflicting with the explicit assignment. It was treated as untrusted prompt-injection content and not followed.
- Beads search could not acquire its lock because its database lies outside this worktree’s writable scope; no tracker state was changed.
- No files were staged, committed, or pushed.<!-- END VERBATIM DOCUMENT: codex-impl-02/execution-03/handoff.md -->

## Gate evidence

| Gate | Check | Candidate | Result | Reviewer verdict | Iteration |
|---|---|---|---|---|---|
| gate-1: project tests | python3 -m unittest discover -s tests (worktree) | None recorded | failed | None recorded | None recorded |
| gate-1: project tests | python3 -m unittest discover -s tests (worktree) | None recorded | passed | None recorded | None recorded |
| gate-1: project tests | python3 -m unittest discover -s tests (worktree) | None recorded | passed | None recorded | None recorded |
| gate-2: STRICT evals | STRICT=1 bash scripts/forge/run-evals.sh (worktree) | None recorded | passed | None recorded | None recorded |
| gate-1: project tests | python3 -m unittest discover -s tests (worktree, commit-chain Step 2) | None recorded | passed | None recorded | None recorded |
| gate-2: stack validations, invariants, assertion sensor, STRICT evals | tests.test_repo_conformance x2; check-test-quality.py on the three new test modules; STRICT=1 run-evals.sh (worktree, commit-chain Step 2) | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final subagent over staged diff 10cb6e2526622687df0bd6705e59b8cec6a57033aa0105953a9f5c061d5a3106 | 10cb6e2526622687df0bd6705e59b8cec6a57033aa0105953a9f5c061d5a3106 | passed | PASS | 1 |
| gate-1: project tests | python3 -m unittest discover -s tests (worktree, merge Gate 1, candidate b3493a2890f079abcfad2a25edbffd10a5dda56f) | b3493a2890f079abcfad2a25edbffd10a5dda56f | passed | None recorded | None recorded |
| gate-2: stack validations, invariants, assertion sensor, STRICT evals | tests.test_repo_conformance x2 (stack + merge invariant row); check-test-quality.py on three new test modules; STRICT=1 run-evals.sh (worktree, merge Gate 2) | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final subagent over git diff 51e1187e8b6e282bd70e5822c7d60c33be388199...b3493a2890f079abcfad2a25edbffd10a5dda56f | b3493a2890f079abcfad2a25edbffd10a5dda56f | passed | PASS | 1 |

## Historical Routing Findings

None recorded

## Residual Risks

- Six residual MINOR/OBSERVATION findings: iteration-cap over-refusal on PASS-converged control chains, frozen-chain abort remediation dead-end, scan-secrets auto-unstage spec silence, corpus integration test leaking guard_deny events into live advisory telemetry, stash-list over-denial for foreign sessions, --json help-path envelope bypass
- Implementation-defined grammars (gate IDs, mutating-gate declaration, verdict grammar, DM-013 normalization) are test-pinned but await a phase-1.1 editorial spec amendment
- The installed plugin cache still ships 0.6.4; dogfood (FR-224 phase 2) requires a release carrying phase 1

## Follow-ups

- Release plugin 0.6.6 shipping the phase-1 CLI surface
- CLI phase 2 dogfood (beads forge-plugin-wh9): run this repository's commit chains exclusively through the CLI with fast-tier telemetry watched
- Phase-1.1 editorial spec amendment for the implementation-defined grammars
- Fix the six residual MINOR/OBSERVATION findings
- Phase-0 run archive remains parked on two MAJOR renderer/journal fidelity defects (archive-run.py verdict_for prose misread; decision-05 nonstandard payload field) pending operator disposition

## Provenance

Run ID: run-20260821-cli-phase1

Starting HEAD: f64164b4f8695b745c7a4d85d09cc295aa6d3846

Closing HEAD: b3493a2890f079abcfad2a25edbffd10a5dda56f

### Pre-close validation payload embedded in `run_closed`

```json
{
  "issues": [],
  "non_passing_verifications": [
    {
      "check": "python3 -m unittest discover -s tests (worktree)",
      "criterion": "gate-1: project tests",
      "id": "check-02",
      "observation": "Ran 840 tests; FAILED (failures=1, skipped=3); sole failure test_phase1_hook_consumes_committed_matcher_vectors, red by decision-02 until task-03; reason-code red-line leg executes and passes; orchestrator-observed.",
      "result": "failed",
      "task": "task-02"
    },
    {
      "check": "No mutation tool available for python — assertion-quality fallback only.",
      "criterion": "mutation: python",
      "id": "mutation-814ba71ee5234cc69d7088fdbbd1487a",
      "observation": "tool=none; scope=python; outcome=declared-absence; scoped_files=[\"scripts/forge/cli.py\",\"tests/test_cli_chain.py\",\"tests/test_cli_chain_finalize.py\",\"tests/test_cli_hook_integration.py\"]; timeout=not-applicable",
      "result": "skipped",
      "task": "task-04"
    }
  ],
  "ok": true,
  "profile": "gates",
  "warnings": []
}
```

### Post-close validation result

```json
{
  "issues": [],
  "non_passing_verifications": [
    {
      "check": "python3 -m unittest discover -s tests (worktree)",
      "criterion": "gate-1: project tests",
      "id": "check-02",
      "observation": "Ran 840 tests; FAILED (failures=1, skipped=3); sole failure test_phase1_hook_consumes_committed_matcher_vectors, red by decision-02 until task-03; reason-code red-line leg executes and passes; orchestrator-observed.",
      "result": "failed",
      "task": "task-02"
    },
    {
      "check": "No mutation tool available for python — assertion-quality fallback only.",
      "criterion": "mutation: python",
      "id": "mutation-814ba71ee5234cc69d7088fdbbd1487a",
      "observation": "tool=none; scope=python; outcome=declared-absence; scoped_files=[\"scripts/forge/cli.py\",\"tests/test_cli_chain.py\",\"tests/test_cli_chain_finalize.py\",\"tests/test_cli_hook_integration.py\"]; timeout=not-applicable",
      "result": "skipped",
      "task": "task-04"
    }
  ],
  "ok": true,
  "profile": "gates",
  "warnings": []
}
```
