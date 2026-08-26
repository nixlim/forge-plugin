# Durable intent archive: run-20260822-merge-chain-spec

## Goal

Author the merge-chain spec revision (beads forge-plugin-dji): normative authority for CLI phases 3-6 prerequisites - merge start/gate run/approve/finalize verbs, CLI-performed locked rebase and fast-forward push, HEAD-SHA candidate identity binding (docs/design/0003-forge-cli-plumbing.md:908) - plus the phase-1.1 editorial amendment pinning the implementation-defined phase-1 grammars (gate IDs, mutating-gate declaration, verdict grammar, DM-013 normalization). Control-class docs/specs change: STRICT evals + binding review + explicit operator approval.

## Tasks

### task-01

Goal: Design the merge-chain spec revision: Claude plan written first (claude-plan-merge-chain-spec.md), independent Codex proposal from goal/constraints only, evidence-based comparison and finalized design recorded as a decision.

Acceptance criteria:

- Claude plan exists in the run dir before the Codex proposal is read
- a fresh Codex agent proposes from goal/constraints only
- the finalized revision outline is recorded as a decision citing both plan paths

Final status: complete

Final outcome: None recorded

### task-02

Goal: Author revision 7 of docs/specs/forge-plugin-spec.md per decision-01: phase-1.1 editorial amendments (four shipped grammars, both quirks documented), DM-014..DM-017, FR-230..FR-243, forge-cli/2 envelope and 41-member union enum, bounded lock epochs, full recovery law, exact phase-4 literals and activation, phase-5 admission predicate, phase-6 deferral, and complete §8/§9/scenarios/§11/§12(SC-021..025)/§13/§14 coverage.

Acceptance criteria:

- revision text implements decision-01 with no unapproved semantic drift to shipped FR-210..FR-224 behavior
- v1 corpora referenced as immutable; v2 artifact names exact
- spec-contract and phase-0 corpus tests remain green
- STRICT evals pass
- binding review-final PASS and explicit operator approval precede the commit

Final status: complete

Final outcome: None recorded

### task-03

Goal: Fix the phase-1 CLI assertion-sensor defect surfaced by the revision-7 spec chain: with no touched test files the gate invoked check-test-quality.py with an empty path set (exit 2 by contract), failing docs-only chains closed. Correct to a recorded not-applicable completion per the commit-skill contract, adapt the three fixture tests that the tolerant stub had masked, and add a docs-only regression test.

Acceptance criteria:

- docs-only chain verify completes the sensor step without executing the tool, recorded not_applicable
- fast-tier sensor load-bearing proof retained via a test-named fast-tier file
- full unittest discovery green
- control-class commit through the CLI chain with review-final PASS and operator approval

Final status: complete

Final outcome: None recorded

## Decisions

### decision-01

Task: task-01

Finding: Claude plan and Codex proposal agree on scope, numbering, corpus immutability with v2 artifacts, phase-4 forge push + activation, phase-5/6 deferral, and phase-1.1 pins. They diverge on enum strategy (Claude: grow FR-220 v1 via v2 corpus; Codex: new forge-cli/2 envelope for merge/push verbs with a union enum, v1 untouched) and on lock discipline (Claude: mirror the skill's continuously held lock; Codex: bounded lock epochs with parked review/approval outside the lock, generation-bound).

Outcome: claude_decision

Resolution: Adopt the Codex architecture substantially: DM-014 forge-merge-chain/1, DM-015 history_mutation_mode (fail-closed committed-manifest read), DM-016 exact v2 artifact inventory, DM-017 push-state singleton, FR-230..FR-243, forge-cli/2 with the 41-member sorted union enum, bounded lock epochs (explicitly presented to the binding review as a substantive FR-062/FR-063 amendment for adoption), the full state/transition/recovery tables, the 16 new reason codes, the exact phase-4 hook literals, and the phase-5 admission predicate. Retain from the Claude plan: spec-only run scope, single control-class commit through the CLI chain, no implementation files changed, and the requirement that the invariant-ID alias quirk be documented as shipped behavior. The two flagged substantive items go to review labeled as such, never silently.

Basis:

- claude-plan-merge-chain-spec.md
- codex-plan-01/execution-01/handoff.md

### forge-scope-readmission-dd876c7b781f47d7af747d5647123566

Task: None recorded

Finding: None recorded

Outcome: None recorded

Resolution: scope-readmission: locked

Basis:

None recorded

### decision-02

Task: task-03

Finding: The revision-7 docs-only chain exposed a phase-1 CLI defect: the assertion-sensor gate invoked check-test-quality.py with an empty path set (exit 2 by contract), failing docs-only chains closed. Operator chose fix-first over an FR-056 skip.

Outcome: user_approval

Resolution: Fix authored by the orchestrator (sensor short-circuit recording a candidate-bound not_applicable step; three masked fixture tests adapted; docs-only regression test added), verified by 855-test discovery, review-final PASS iteration 1 with in-memory disable proofs, operator approval of candidate 8f416847739d51476b2973cdfea383200c7dc85fe46906df3e9ca07c1e25bd2f delivered under explicit remote-control direction (channel deviation recorded), committed as 3dd83082541e102f25910bb90664508825d2613d via CLI chain c-2026-08-22T131913Z-5ff0.

Basis:

- codex-impl-01/execution-02/handoff.md

### decision-03

Task: task-02

Finding: Revision 7 (control-class docs/specs change) required binding review and explicit operator approval.

Outcome: user_approval

Resolution: review-final PASS iteration 1 (1 MINOR: pin the forge-cli/2 envelope schema for shared verbs on merge chains — follow-up); operator approved candidate 06a1830712d23255769e7e416a9ed4067e1fe5d1b2e6f7b2bce628a0ac762dd3 under explicit remote-control direction (channel deviation recorded); committed as 55e90776432c5ba518e4156c8fbb8482a612e2f9 via CLI chain c-2026-08-22T134638Z-b00f; both commits pushed to origin/main.

Basis:

- codex-plan-01/execution-01/handoff.md
- codex-impl-01/execution-02/handoff.md

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
      "task": "task-03"
    },
    {
      "id": "decision-03",
      "task": "task-02"
    }
  ],
  "executions": [
    {
      "agent": "codex-plan-01",
      "execution": "execution-01",
      "prompt": "codex-plan-01/execution-01/prompt.md",
      "prompt_sha256": "82da2654c2703fb611ab18218888fd78b4e6fba274cf8d7b3684587286258d51",
      "role": "implementation",
      "task": "task-01"
    },
    {
      "agent": "codex-impl-01",
      "execution": "execution-02",
      "prompt": "codex-impl-01/execution-02/prompt.md",
      "prompt_sha256": "21a07ba60592540819643c562a2f56bb2ad7c7e5d5dfb24cadbb8a4deff51dac",
      "role": "implementation",
      "task": "task-02"
    }
  ],
  "failed_or_inconclusive_verifications": []
}
```
<!-- END FORGE LEARNING PROVENANCE v1 -->

## Verbatim basis documents

### claude-plan-merge-chain-spec.md

<!-- BEGIN VERBATIM DOCUMENT: claude-plan-merge-chain-spec.md -->
# Claude plan — merge-chain spec revision (written before reading any Codex proposal)

Authority context: docs/design/0003-forge-cli-plumbing.md (merge chain §318-343, migration
phases 3-6 §872-908, D22 forge push, D32 red lines); the shipped phase-1 implementation
(scripts/forge/cli.py at c57bff7, commit-chain FR-210..FR-224); the phase-1 run's residual
follow-ups. Beads: forge-plugin-dji (this revision), blocking 9qf/v1t/bht/ao4.

## Deliverable

One control-class revision (revision 7) of docs/specs/forge-plugin-spec.md adding:

1. **Merge-chain FR range (FR-230..FR-24x, DM-014..)** — phases 3-4 authority:
   - `merge start --candidate <full-sha>` (HEAD-SHA candidate identity, not staged-diff hash):
     chain kind `merge`, DM-012-style storage reused with kind-specific keys; fixed
     REVIEWED_BASE capture; classification of the full merge diff by committed policy.
   - `merge gate run` / `merge verify`: Gate 1 (once, per merge contract), scoped mutation
     evidence (advisory), Gate 2 stack/invariant `merge` rows, all CLI-captured with DM-013
     fingerprints; resumable like commit verify.
   - `merge review request/collect/attach`: Gate 3 review-final mandatory and unconditional;
     package is the exact fixed-SHA range diff; verdict cites candidate HEAD + package digest.
   - `merge approve --candidate <head-sha>`: operator verb, control diffs always; hook-denied
     model path, `!` channel, same FR-218 layering; approval bound to the exact HEAD.
   - `merge finalize`: CLI-performed halt check, rebase lock (compose the existing
     agent-rebase.lock semantics: flock + mkdir fallback, 300 s), fetch, rebase onto the
     default branch, in-lock re-verification matrix (DEFAULT_ADVANCED / CANDIDATE_REWRITTEN /
     conflicts → graded re-runs mirroring the skill's current normative table), fast-forward
     push, containment check, worktree/branch cleanup, chain close; crash-window recovery by
     observing HEAD and origin state (never replay).
   - Failure surface: extend the FR-220 reason-code enum with merge members (control-class
     enum change, versioned corpus v2 under system/fr223/ with a new fixture version, never
     editing v1).
2. **Phase-4 raw-verb denial + `forge push` (FR-24x..)** — hook denies raw `git commit` and
   raw `git push` once phase-4 activates; `forge push` ships in the same revision (D22: denial
   without it leaves no legal close protocol); explicit no-"chain-produced-SHAs-only" rule
   (design line 343); Beads close-protocol rewrite duty named; activation is its own
   control-class switch, default off at revision time.
3. **Phase-5/6 declarations** — marker-grammar deletion preconditions (D32: only after the
   eval net pins the state machine; enumerate the pinning evals) and plan-seal/proposal-unseal
   ordering control scope, each explicitly deferred to its own later revision text but with
   normative preconditions stated now.
4. **Phase-1.1 editorial amendment** — pin the four implementation-defined grammars phase 1
   shipped (gate-ID naming convention; mutating-gate declaration in changelog-policy; verdict
   grammar `VERDICT:`/`candidate:`/`package:`/`finding:` lines; DM-013 normalization: platform,
   python_version major.minor.micro, realpath cwd, canonical-JSON argv digest) to the exact
   behavior pinned by the committed phase-1 tests, and adjudicate the six residual MINOR
   findings into normative text where warranted (iteration-cap semantics on PASS-convergence;
   frozen-chain abort recovery contract; scan-secrets auto-unstage behavior made normative or
   forbidden — decide in review).

## Constraints

- Spec-only revision: no implementation files change in this run (tests/test_cli_phase0_contracts.py
  may gain spec-fragment pins ONLY if the revision changes text those tests parse — prefer not).
- Rev-6 phase-0 corpora stay immutable (v1 files never edited; enum growth = v2 fixtures later).
- STRICT evals + binding review-final + explicit operator approval before commit (docs/specs/**
  trigger); the commit must go through the CLI chain (phase-2 dogfood posture).
- Traceability: new FR/DM rows in §13 matrix, error-contract rows in §9, scenarios in §10,
  testing requirements in §11, success criteria addition (SC-021+), task decomposition update.

## Execution shape

- task-01: this plan vs. independent Codex proposal (goal-only), decision with both bases.
- task-02: Codex implementer authors the revision in the main checkout (docs-only; no worktree
  needed — single writer, run-scoped), against the committed rev-6 spec.
- task-03: verification (spec-contract tests still green, STRICT evals, phase-0 corpus tests
  untouched-green), CLI commit chain (control-class: review-final + operator approval), push,
  close, archive, report.

## Risks

- Enum extension pressure: merge reason codes must not tempt edits to the immutable v1 corpus.
- Scope creep into implementation: this run writes authority only; phases 3-6 implementation
  runs follow separately.
- Approval channel: operator `!` unavailable under remote control; approvals will again be
  conversational with recorded deviation, or run from a host shell.
<!-- END VERBATIM DOCUMENT: claude-plan-merge-chain-spec.md -->

### codex-plan-01/execution-01/handoff.md

<!-- BEGIN VERBATIM DOCUMENT: codex-plan-01/execution-01/handoff.md -->
## Status

Complete — read-only design proposal against HEAD `c57bff7f2517c18f4385d766ea8b387b14bc2e5a`. No implementation, gate decision, commit, or push was performed.

## Summary

Revision 7 should:

- Add phase-1.1 editorial authority for the four shipped CLI grammars.
- Reserve DM-014..DM-017 and FR-230..FR-243 for phases 3–4.
- Use a separate merge schema and `forge-cli/2` output contract, leaving DM-012, FR-210..FR-224, and phase-1 `forge-cli/1` behavior unchanged.
- Replace an indefinitely held rebase lock with bounded lock epochs: park for external review/approval, then reacquire, revalidate, and rerun final mechanical gates before push.
- Make phase-4 denial conditional on committed `history_mutation_mode: forge-verbs-v1`.
- Define phase-5 admission requirements without authorizing marker deletion, and declare phase-6 scope without authorizing implementation.

## Files Changed

None.

## Claims

**Proposed numbering**

| ID | Proposed normative subject |
|---|---|
| DM-014 | Merge-chain schema `forge-merge-chain/1` |
| DM-015 | `.forge-manifest` history-mutation activation field |
| DM-016 | Immutable phase-3/4 v2 reason-code and hook-vector corpora |
| DM-017 | Recoverable singleton `forge push` operation state |
| FR-230 | Revision scope, phase sequencing, and CLI composition rule |
| FR-231 | Merge-start admission, trusted target discovery, and candidate identity |
| FR-232 | Closed merge state enum, transition table, chain selection, and verbs |
| FR-233 | Merge gate IDs, ordering, evidence, and invalidation |
| FR-234 | Merge review, revision loop, approval, and no-skip rule |
| FR-235 | Locked finalize protocol and in-lock re-verification matrix |
| FR-236 | Rebase, push, and cleanup recovery |
| FR-237 | Merge system of record, journal/archive binding, and concurrency |
| FR-238 | Standalone `forge push` contract from D22/D28 |
| FR-239 | Phase-4 activation and raw `git commit`/`git push` denial |
| FR-240 | Phase-4 migration, rendered close protocol, and marker retention |
| FR-241 | v2 corpora, harness qualification, and last-line control tests |
| FR-242 | Phase-5 marker-deletion admission predicate; implementation deferred |
| FR-243 | Phase-6 plan-seal scope; implementation deferred |
| SC-021..SC-025 | Merge success, rebase/reapproval, recovery, activated denial/push, and phase-5/6 deferral |

FR-230 is preferable to technically free FR-225 because existing functional areas use decade-grouped ranges. Current authority ends at DM-013, FR-224, and SC-020. [Current spec](</home/agents/foundry-of-zero/forge-plugin/docs/specs/forge-plugin-spec.md:197>)

**Proposed DM contracts**

DM-014 should preserve DM-012 unchanged and define a separate merge record:

```text
schema: forge-merge-chain/1
kind: merge
```

Proposed exact top-level keys:

```text
schema, chain_id, kind, state, created_at, last_event_at,
inactive_after, owner, run, repository, worktree, branch, target,
policy_source, candidate, tier, steps, review, approval,
authorization, integration, cleanup
```

The candidate generation must bind fixed values, never symbolic refs:

```text
remote = "origin"
destination_ref = "refs/heads/<configured-default-branch>"
remote_tip = <full fetched OID>
candidate_head = <full worktree HEAD OID>
diff_sha256 = SHA-256(exact bytes of git diff <remote-tip>...<candidate-head>)
policy_commit = <full candidate/integrated HEAD OID>
policy_digest = SHA-256(exact committed forge-project.md bytes)
worktree_identity
generation = <positive integer>
```

Every gate, review, approval, rebase, and push record carries the candidate-generation digest. Approval remains user-facing as `merge approve --candidate <full-head-sha>`, while its stored record also carries the chain ID and generation digest.

DM-015 should extend the committed manifest with exactly one anchored field:

```text
history_mutation_mode: legacy-v1
```

or:

```text
history_mutation_mode: forge-verbs-v1
```

Rules:

- Missing on an older manifest means `legacy-v1`.
- Duplicate, malformed, or unknown values in an initialized Forge repository fail closed for raw commit/push.
- The hook reads only `git show HEAD:.forge-manifest`; working-tree edits or staged deletion cannot deactivate it.
- `forge-verbs-v1` activates raw commit and raw push denial atomically.
- Init/re-init must not silently activate existing repositories. Activation is a reviewed, operator-approved control change after phase-3/4 checks exist.

DM-016 should name additive v2 artifacts. Every existing `system/fr223/` phase-0 artifact remains immutable:

```text
system/fr223/reason-codes-v2.json
system/fr223/hook-argv-cases-v2.json
.forge/evals/tasks/fr223-reason-code-enum-v2.md
.forge/evals/tasks/fr223-reason-code-enum-v2.result
.forge/evals/tasks/fr223-hook-argv-matcher-v2.md
.forge/evals/tasks/fr223-hook-argv-matcher-v2.result
.forge/evals/tasks/fr230-phase3-4-v2.manifest.json
```

The new reason schema should be exactly `fr223-reason-codes/2`; hook vectors should use `fr223-hook-argv/2`. The v2 reason file is the complete sorted union, while tests separately prove every v1 row remains byte-identical.

DM-017 should define `.forge/tmp/push-state.json` as a singleton recoverable `forge-push/1` transaction for the main checkout. It needs exact `preparing`, `rebasing`, `pushing`, `closed`, and `recovery_required` states plus fixed remote/ref, pre-operation HEAD, fetched tip, rebased HEAD, push intent, observed remote, and timestamps. `forge push` envelopes use `chain_id: null`.

**Phase-1.1 editorial amendment**

These amendments describe HEAD behavior and must not tighten or broaden it.

1. Gate-ID naming, amending FR-214/§8:

```text
changelog
gate-1
stack:<category>
assertion-sensor
invariant:<row-number>
secret-scan
strict-evals
```

- `<category>` is normalized lowercase `[a-z0-9][a-z0-9_-]*`.
- `<row-number>` is the one-based invariant data-row ordinal; only `enforcement == "commit"` rows are required.
- `gate-1` appears twice under the same ID.
- `classification` is an internal step, not runnable.
- `review` is a skip target, not a mechanical gate ID; index drift uses `--index-drift`.
- Unknown/unconfigured IDs retain `state-precondition`.
- Shipped `int()` parsing can execute aliases such as `invariant:01`, but evidence under that alias does not satisfy canonical `invariant:1`. Editorial text must preserve or explicitly document that quirk; claiming a strictly accepted `[1-9][0-9]*` input would be semantic drift. [Implementation](</home/agents/foundry-of-zero/forge-plugin/scripts/forge/cli.py:2792>)

2. Mutating-gate declaration, amending FR-214/DM-003/§8:

- Phase 1 has no generic mutating-gate registry.
- The configured `changelog` gate is the sole mutating gate.
- No-gate recognition uses full-match, case-insensitive, dot-all semantics:

```regex
No changelog gate (?:is configured|applies)(?: for| to)?(?: this)? .*?repository\.
```

- Otherwise exactly one nonempty, NUL-free fenced `bash` or `sh` cell is required.
- At least one output must come from either a case-insensitive `Output path:`/`Output paths:` line or a Markdown row whose first cell normalizes to `output`, `output path`, or `output paths`.
- Values are comma-split, trimmed, stripped of surrounding backticks, and first-occurrence deduplicated.
- Successful output paths join the chain path set, are explicitly staged, and force candidate/classification recomputation. [Parser](</home/agents/foundry-of-zero/forge-plugin/scripts/forge/cli.py:966>)

3. Review-verdict transport grammar, amending FR-216/§8:

```text
VERDICT: PASS|BLOCK
candidate: <exact-current-candidate>
package: <exact-issued-package-digest>
finding: <CRITICAL|MAJOR|MINOR> <nonempty text>
```

- Strict UTF-8; split lines, strip each, discard blanks.
- First nonblank line is exactly `VERDICT: PASS` or `VERDICT: BLOCK`.
- Candidate and package citations each occur exactly once; their later order is unrestricted.
- Findings are optional and repeatable; every other nonblank line is invalid.
- PASS rejects CRITICAL/MAJOR findings but permits MINOR.
- The parser does not require BLOCK to contain a finding.
- `OBSERVATION` is not a transport severity.
- This transport grammar must be distinguished from the constitution’s broader substantive duties. [Parser](</home/agents/foundry-of-zero/forge-plugin/scripts/forge/cli.py:4593>)

4. DM-013 normalization:

```text
canonical(x) =
  UTF-8(json.dumps(x, sort_keys=True,
                   separators=(",", ":"),
                   ensure_ascii=False))
```

There is no trailing LF or `sha256:` prefix.

```text
command_digest =
  lowercase_hex_sha256(canonical(exact subprocess argv array))

preimage = {
  "command_digest": command_digest,
  "cwd": os.path.realpath(repository_root),
  "platform": sys.platform,
  "policy_digest": lowercase_hex_sha256(exact pinned policy bytes),
  "python_version": "<major>.<minor>.<micro>",
  "repo_head": <full current HEAD>
}

env_fingerprint = lowercase_hex_sha256(canonical(preimage))
```

No environment mapping, locale, architecture, or outer Forge invocation contributes. A mismatch voids every prior unvoided current-candidate Gate-1 PASS across the boundary and requires two fresh runs, retaining the exact reason `DM-013 env_fingerprint mismatch voided the Gate-1 pair`. [Implementation](</home/agents/foundry-of-zero/forge-plugin/scripts/forge/cli.py:2278>)

**Merge verbs and state machine**

Required post-start commands should require `--chain-id <id>`; implicit selection is unsafe when simultaneous worktree merges exist.

```text
forge status --chain-id <id>
forge merge start --worktree <path> [--declare-tier <tier>]
forge merge refresh --chain-id <id>
forge merge verify --chain-id <id>
forge merge gate run <gate-id> --chain-id <id>
forge review request --chain-id <id>
forge review attach --verdict-file <file> --chain-id <id>
forge review disposition ... --chain-id <id>
forge merge approve --candidate <full-head-sha> --chain-id <id>
forge merge finalize --chain-id <id>
forge merge recover --chain-id <id>
forge merge recover --continue --paths <path>... --chain-id <id>
forge merge recover --abort-rebase --chain-id <id>
forge merge cleanup --chain-id <id>
forge merge abort [--reason <text>] --chain-id <id>
```

There is no `merge skip`; FR-060 remains fail-closed.

Proposed closed states:

```text
classifying, verifying, reviewing, revising,
awaiting_approval, authorized, rebasing, rebase_conflict,
reverifying, reverification_failed, pushing, pushed,
cleanup_pending, closed, aborted
```

| From/event | To | Normative result |
|---|---|---|
| `merge start` | `classifying → verifying` | Validate registered non-main worktree, clean status, branch and target; compute candidate generation and classify |
| Initial Gates 1–2 complete | `reviewing` | All required mechanical evidence current; mutation evidence captured but advisory |
| Review PASS, non-control | `authorized` | Gate 4 summary recorded |
| Review PASS, control | `awaiting_approval` | Exact full HEAD presented |
| Review BLOCK | `revising` | Iteration incremented; cap 8 |
| `merge refresh` after a new HEAD | `classifying` | All stale-generation evidence invalidated |
| Exact operator approval | `authorized` | Approval bound to current HEAD/generation |
| `merge finalize` | `rebasing` | Halt, lock, tuple check, fetch and rebase intent |
| Rebase conflict | `rebase_conflict` | Remote untouched; only recovery/status/abort paths accepted |
| Rebase completes with required reruns | `reverifying` | Reload policy, reclassify, rerun required integrated checks |
| Integrated Gate 1/2 failure | `reverification_failed` | Remote untouched; retry reruns both, or refresh after fixes |
| Candidate/diff/policy change requiring judgment | `reviewing` | Persist integrated generation, park, release lock, obtain new review/approval |
| Final authorized generation | `pushing` | Persist and fsync push intent before calling Git |
| Remote observation proves landed | `pushed` | Pushed truth is durable before cleanup |
| Cleanup succeeds | `closed` | Worktree and branch removed only under containment rules |
| Cleanup fails | `cleanup_pending` | Never report “not pushed”; cleanup is independently retryable |
| Any pre-push state, `abort` | `aborted` | Rebase first safely aborted where applicable |
| `pushing`/`pushed`/`cleanup_pending` | no ordinary abort | Recovery must first determine the remote truth |

A chain past inactivity accepts only `status`, `recover`, cleanup where already pushed, and safe abort before push. Pushed/cleanup state must not expire into ambiguity.

**Merge admission and gates**

`merge start` should:

- Canonicalize `--worktree` and require an exact registered entry from `git worktree list --porcelain`.
- Reject missing, symlink-ambiguous, main, detached, default-branch, foreign-common-dir, or already-owned worktrees.
- Require exact empty output from `git status --porcelain=v1 --untracked-files=all`.
- Read the target default branch from the main checkout’s committed `.forge-manifest`, never the candidate-controlled working copy; the remote remains exact `origin`.
- Read gate policy from the candidate’s committed HEAD and enforce the existing sentinels.
- Bind evidence to candidate HEAD, fixed base HEAD, exact diff digest, policy digest, target, worktree identity, and generation.

Merge mechanical IDs should be exactly:

```text
gate-1
stack:<category>
assertion-sensor
invariant:<one-based merge-enforcement row>
```

Initial order preserves FR-060..FR-065:

1. Gate 1 once.
2. Scoped mutation immediately after Gate 1, always advisory.
3. Stack validations, merge invariants, and assertion sensor as Gate 2.
4. Unconditional `review-final` Gate 3, including fast constituents.
5. Gate 4 summary and candidate-HEAD approval for control.

Every executable retains committed-policy sourcing, one-cell `bash -c` argv, isolated process groups, the 65,536-byte combined-output cap, and applicable timeouts. After every gate, recompute HEAD, diff digest, policy digest, and clean status; a mutating gate parks and invalidates downstream evidence rather than pushing unreviewed bytes.

Merge approval has no imported DM-006 30-minute TTL. It remains valid until candidate-generation invalidation or chain inactivity.

**Bounded lock epochs and re-verification matrix**

This proposal explicitly supersedes the current skill’s continuously held lock only for CLI merge. It preserves the common-dir lock and the requirement that the final mechanical checks precede push under that lock.

A lock epoch may perform at most one integration/final cycle. It never automatically loops indefinitely. Commands needing both locks acquire the common rebase lock before the per-chain state lock, then re-read state; no code holding the chain lock may wait for the rebase lock.

If rebase changes the candidate and external review/approval is needed:

1. Run required integrated Gate 1, scoped mutation, and Gate 2 under the current epoch.
2. Persist the integrated generation and park.
3. Release the lock.
4. Obtain Gate 3/Gate 4/approval outside the lock against the fixed generation.
5. A later finalize reacquires the lock and requires tuple identity plus unchanged remote tip.
6. It reruns Gate 1, scoped mutation, and Gate 2 in the final epoch before push.
7. Immediately before push, perform a fresh authoritative remote-tip read. A later race is handled only by ordinary non-fast-forward rejection.

| Observation under lock | Required before push |
|---|---|
| Bound HEAD, worktree, remote, or destination ref changed | Refuse/freeze; never silently retarget |
| Remote unchanged; HEAD/diff/policy unchanged; no earlier park | Recheck authorization and push; current pure-fast-forward rule retains initial gates |
| Remote advanced but final HEAD, diff, and policy remain identical | Reload/reclassify; rerun Gate 1, mutation, and Gate 2; Gate 3/Gate 4 may be retained |
| Candidate HEAD rewritten, even with identical diff | Rerun Gate 1/mutation/Gate 2, then fresh Gate 3 and Gate 4; renew control approval |
| Diff digest changed | Reclassify and repeat Gates 1–4; renew control approval |
| Policy digest changed | Reclassify; repeat Gates 1–4 because commands and review context changed |
| Conflicts were resolved | Repeat Gates 1–4 unconditionally; approval names integrated HEAD |
| Any in-lock gate fails or mutates the tuple | Remote untouched; enter `reverification_failed` or reclassification path |
| Tuple changes after re-verification | Refuse before push and park through the applicable row |
| Remote changes during the last check | Ordinary non-fast-forward; persist exact recovery state |
| Push succeeds | Record `pushed` before attempting cleanup |

After eight consecutive epochs defeated solely by remote movement, use new `remote-churn`, park, and require operator inspection. Liveness is claimed only under eventual remote quiescence.

**Recovery requirements**

Before fetch/rebase, every continue/abort, push, and cleanup mutation, append and fsync an intent event, then materialize state. Recovery observes Git and the remote; event replay alone is insufficient.

For `rebase_conflict`:

- `--continue` and `--abort-rebase` are mutually exclusive.
- Prove the rebase metadata belongs to the selected worktree/chain and recorded pre-rebase generation.
- Obtain the conflict inventory from NUL-delimited Git output.
- `--paths` must exactly name the authorized conflict set after repository-relative normalization.
- Reject pathspec magic and unrelated staged, tracked, or untracked contamination.
- Stage through `git --literal-pathspecs add -- <paths>`.
- Continue noninteractively using the recorded commit messages.
- More conflicts update the inventory and remain `rebase_conflict`.
- A successful continuation that crashes before state persistence is recovered by observing HEAD and rebase metadata.
- `--abort-rebase` must prove restoration of the pre-rebase HEAD and clean state, then enter `revising`.
- A Git state matching neither recorded pre-rebase, conflict, nor integrated state freezes the chain.

For push recovery:

- `pushing` records the expected old remote tip, intended HEAD, and destination ref before the push.
- If the remote equals or contains the intended HEAD, transition to `pushed` even if it later advanced.
- If the remote still equals the old tip, retry is safe under the lock.
- If the remote moved elsewhere, return non-fast-forward/rebase recovery.
- If the remote cannot be authoritatively observed, use `push-outcome-unknown` and never blindly retry.

For cleanup:

- Verify the pushed HEAD is contained in the remote default branch.
- Use `git worktree remove` without `--force`.
- Delete the branch only after containment.
- Recovery tolerates the worktree already removed or branch already absent.
- Partial cleanup remains `cleanup_pending`; it never re-runs push.

**Phase-4 `forge push`, activation, and raw denial**

`forge push` should be available in `legacy-v1` before activation and require:

- Main checkout only.
- Current branch exactly the configured default branch.
- Exact clean status, including untracked files, and no in-progress Git operation.
- Halt check.
- The same common-dir rebase lock as merge finalize/recovery.
- Fetch `origin/<default>`, rebase onto that fixed tip, then ordinary fast-forward-only push.
- Observation-based recovery through DM-017.
- No ancestry/provenance audit: it may push commits no closed chain produced, as D28 requires. [Design](</home/agents/foundry-of-zero/forge-plugin/docs/design/0003-forge-cli-plumbing.md:330>)

A proposed exact close-protocol replacement is:

```bash
bd dolt push
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py" push
git status
```

`bd dolt push` remains untouched. A failure there prevents the Forge push from starting.

When `history_mutation_mode: forge-verbs-v1` is committed, the hook’s sanctioned producer paths are:

```text
forge commit finalize
forge merge finalize
forge push
```

This resolves the design’s stale two-path wording, which omits `forge push`. [Contradictory hook text](</home/agents/foundry-of-zero/forge-plugin/docs/design/0003-forge-cli-plumbing.md:690>)

Proposed exact hook literals:

```text
forge: operator verb denied — present the candidate and ask the operator to run this via ! (merge approve)
forge: raw git commit denied — use Forge CLI commit finalize
forge: raw git push denied — use Forge CLI merge finalize or Forge CLI push
forge: history mutation mode invalid — repair committed .forge-manifest through Forge CLI
```

The v2 matcher must retain FR-221’s quote-aware segment splitting and interpreter/path grammar. It must deny an appended raw Git segment even when another segment contains an allowed CLI verb.

The normative claim should be narrowly accurate: phase 4 denies raw `git commit` and raw `git push` under the PreToolUse threat model. It must not claim exhaustive prevention of every Git porcelain/plumbing history mutation unless a separate closed matcher enumerates and tests those verbs. It must never add a chain-produced-SHA requirement. [D22 migration](</home/agents/foundry-of-zero/forge-plugin/docs/design/0003-forge-cli-plumbing.md:884>)

**Reason-code additions**

Existing phase-1 commands remain `forge-cli/1` with the unchanged v1 enum. New merge/push commands emit `forge-cli/2`, using the same exact envelope keys and a complete v2 union. This avoids semantically changing FR-220.

Keep all 25 v1 rows byte-identical and add these 16 exit-1 codes, producing a 41-member sorted v2 enum:

| Addition | Exact precondition |
|---|---|
| `cleanup-failed` | Pushed candidate containment or non-force worktree/branch cleanup cannot complete |
| `dirty-worktree` | Merge source or default-branch push checkout fails the exact clean predicate |
| `fetch-failed` | Required fixed-target fetch/tip resolution failed |
| `live-merge-chain-exists` | Another live merge chain owns the selected worktree |
| `lock-release-failed` | Rebase lock could not be explicitly released after the primary outcome was recorded |
| `merge-gate-failed` | Required initial or integrated merge gate is unavailable or non-PASS |
| `non-fast-forward` | Ordinary destination update was rejected as non-fast-forward |
| `push-failed` | Push returned a known failure other than non-fast-forward |
| `push-outcome-unknown` | Remote outcome cannot be authoritatively observed |
| `push-target-invalid` | Checkout, remote, branch, or destination ref is not the fixed sanctioned target |
| `rebase-conflict` | CLI-owned rebase awaits the specified conflict-recovery verb |
| `rebase-failed` | Rebase/continue/abort failed outside the recoverable conflict state |
| `rebase-lock-unavailable` | Common rebase lock timed out after 300 seconds or no portable mechanism exists |
| `remote-churn` | Eight consecutive integration epochs were defeated by remote movement |
| `worktree-invalid` | Existing path is not a valid registered non-main local-branch worktree |
| `worktree-missing` | `merge start --worktree` path does not exist |

Reuse existing codes where their definitions remain exact, including `approval-required`, `candidate-stale`, `evidence-incomplete`, `frozen-chain`, `halt-engaged`, `inactive-chain`, `iteration-cap`, `operator-verb-denied`, `policy-unreadable`, `review-verdict-invalid`, and `state-precondition`.

Hook-only denial/audit labels such as `activation-policy-invalid`, `raw-git-commit-denied`, and `raw-git-push-denied` stay outside this CLI enum because hooks return deny JSON rather than CLI envelopes.

**Phase-5 and phase-6 boundaries**

Revision 7 must not authorize phase-5 deletion. A later control revision may delete DM-006 only when all of these are mechanically evidenced:

- Phase-1 dual-accept demonstrably shipped and was never skipped.
- `forge-verbs-v1` activation is committed.
- All v1 corpus/eval/manifest bytes remain unchanged.
- v2 reason, matcher, merge transition, recovery, push, and activated-denial evals pass.
- Every merge-finalize and push last-line check has a disable-in-memory test.
- STRICT evals pass.
- Full unittest discovery passes twice consecutively, serially, after the last fix.
- No installed skill/template produces a raw commit/push or marker authorization.
- No live legacy chain or unexpired marker remains consumable.
- Marker parser/tests remain present through phase 4, even if raw denial makes marker admission dormant.
- The deletion candidate receives binding independent review and explicit operator approval.

This converts D32’s “eval net actually pins the machine” into an observable predicate. [D32](</home/agents/foundry-of-zero/forge-plugin/docs/design/0003-forge-cli-plumbing.md:900>)

Revision 7 should declare but not implement phase 6:

```text
forge plan seal --file <plan>
forge proposal unseal
```

It is only a best-effort ordering/audit control. It provides no confidentiality and must never claim the proposal is unreadable. Later authority must define run binding, digest/schema, resealing, proposal identity, path/symlink handling, journal/archive records, output codes, and tests. [Design](</home/agents/foundry-of-zero/forge-plugin/docs/design/0003-forge-cli-plumbing.md:299>)

**Required §8–§14 content**

| Section | Revision-7 content |
|---|---|
| §8 | `forge-merge-chain/1`; every merge/recover/cleanup argv; `forge-cli/2`; push state; activation parser; exact hook output; phase-1.1 grammars |
| §9 | Rows for missing/invalid/dirty/owned worktrees; candidate/target movement; initial and integrated gate failures; lock/fetch/rebase/conflict; renewed approval; non-FF/known/unknown push; lock-release; pushed-but-cleanup-failed; push target; activation off/on/malformed; raw denials |
| Scenarios | Clean merge; control approval; remote advance unchanged; conflict-free rewrite; conflict recovery; policy/diff change; final gate failure; push race/unknown outcome; crash after rebase/push; cleanup retry; activation legacy/enabled/malformed; legal no-provenance `forge push` |
| §11 Unit | Every transition and refusal edge; schema/event replay; hostile paths and pathspecs; exact matrix; gate mutation; every crash window; all last-line checks disabled individually; phase-1.1 golden grammars; v1 immutability and v2 exact union |
| §11 Integration | Real bare remote; two concurrent merges plus push contention; remote churn; rebase conflicts; post-push crash; macOS/Linux lock mechanisms; phase-4 matcher vectors for all three sanctioned paths |
| §11 E2E | Phase-3 merge from worktree through cleanup; phase-4 main-checkout close; activated raw denial while CLI paths remain legal; serial suite evidence read from the suite’s own output |
| §12 | SC-021 clean merge; SC-022 integrated-head re-review/reapproval; SC-023 observation-based recovery and cleanup truth; SC-024 activated raw denial plus no-provenance push; SC-025 phase-5/6 remain blocked/deferred |
| §13 | One FR-230..FR-243 row mapping every scenario and test surface; keep FR-060..065 and FR-210..224 rows intact |
| §14 | Separate control-class packets for phase-1.1 authority, merge schema/state, lock/recovery, phase-3 implementation, phase-4 push+hook+activation+Beads rendering, phase-5 deletion, and phase-6 ordering |

Recommended authoring sequence:

1. Update revision metadata, inputs, scope, and explicit non-goals.
2. Write phase-1.1 amendments and golden-vector requirements without changing shipped semantics.
3. Add DM-014..DM-017 and the complete state/transition tables.
4. Add FR-230..FR-237 for merge, including the literal lock matrix and every recovery window.
5. Add FR-238..FR-241 for push, activation, matcher literals, migration, and v2 corpora.
6. Add FR-242..FR-243 deferrals and admission predicates.
7. Complete §8, §9, scenarios, §11, SC-021..025, §13, and §14 traceability.
8. Run an independent adversarial review; treat a first-pass BLOCK as expected and re-verify affected authority before re-review.

**Design-document authority gaps identified**

- No merge schema, state table, chain-selection grammar, abort/recovery surface, or gate-ID grammar.
- No implementable protocol for review/approval after a rebase rewrites HEAD while a lock is held.
- FR-063 requires Gate 3 after conflicts, while the shipped skill also reruns it after any HEAD rewrite; revision 7 must adopt the stronger explicit rule.
- No recovery law for rebase interruption, ambiguous push completion, successful push before state close, or partial cleanup.
- HEAD alone does not identify the reviewed merge range; base, diff digest, policy, target, and generation must also be recorded.
- No phase-4 activation source, default, malformed behavior, or exact raw-denial literals.
- Hook Integration names only two legal paths, while D22 requires the third, `forge push`.
- “Only history-mutating paths” overclaims what denial of only raw commit/push proves.
- `forge push` lacks exact target, cleanliness, conflict, recovery, output, and close-protocol rules.
- D32 does not define what “eval net actually pins the state machine” means.
- Phase-6 verbs lack all storage, identity, path, and error contracts and therefore must remain deferred.
- The four shipped phase-1 grammars are incompletely stated and unevenly test-pinned.

## Verification

Observed:

- `git rev-parse HEAD` → `c57bff7f2517c18f4385d766ea8b387b14bc2e5a`.
- Final `git status --short --branch` → `## main...origin/main`.
- `git diff --name-only` and `git diff --cached --name-only` returned no paths.
- Read-only inspection covered the current spec, design 0003 and its D22/D32 provenance, `cli.py`, merge skill, tests, and FR-223 artifacts.
- Current immutable artifact hashes were recorded:

```text
3646227d8437789e0407117dc09e00d6116edccb63e89354c746d4b9059c264b  system/fr223/reason-codes-v1.json
1850257d7899a4c7199e9bcbe12ffd39b0905bb44e49d16348c10e438ea05db7  system/fr223/hook-argv-cases-v1.json
7741b877b1ed45047d680a077c5303b2314cd1f3ef0339821bd7105ac9acd5c9  .forge/evals/tasks/fr223-phase0-v1.manifest.json
```

No test or gate suite was run because there was no implementation candidate and the assignment was strictly read-only.

## Caveats

- Bounded lock epochs are a substantive phase-3 amendment to FR-062/FR-063, not phase-1.1 editorial work. It requires binding review and explicit adoption.
- The phase-1 invariant-ID parser accepts noncanonical numeric aliases that do not satisfy canonical evidence IDs. Revision 7 must document that behavior or assign a separately reviewed correction; it cannot silently tighten it.
- Several proposed strings, state names, and the activation key are new exact-literal candidates because design 0003 did not supply them.
- The provided checkout was `main`, not a dedicated task branch. No mutation occurred, so no branch or unrelated work was affected.
<!-- END VERBATIM DOCUMENT: codex-plan-01/execution-01/handoff.md -->

### codex-impl-01/execution-02/handoff.md

<!-- BEGIN VERBATIM DOCUMENT: codex-impl-01/execution-02/handoff.md -->
## Status

Complete and left uncommitted for orchestrator approval/reintegration. Final reviewed SHA-256: `d699c84990fd8e009baead7a6e22c49f3de202de75dd3c8859cc2297e1497ff0`.

## Summary

Authored Revision 7 with the full phase-1.1 amendments, DM-014..DM-017, FR-230..FR-243, state/recovery laws, 41-member v2 reason enum, phases 4–6, contracts, scenarios, tests, success criteria, traceability, and task packets. Six independent final reviews returned PASS.

No implementation surface was changed.

## Files Changed

- [docs/specs/forge-plugin-spec.md](/home/agents/foundry-of-zero/forge-plugin/docs/specs/forge-plugin-spec.md)
  - 1,322 → 2,214 lines: net `+892`
  - Diff: 900 insertions, 8 deletions
  - Only modified path; `git diff --check` is clean

## Claims

- Touched revision metadata/Intent/Inputs; §§2, 4, 5; §6 including phase-1.1 DM-003/DM-013 amendments and DM-014..DM-017; §7 including FR-230..FR-243; §§8–9; behavioral scenarios; §11; §12 SC-021..SC-025; §13; and §14.
- Preserved FR-090, FR-220, and FR-221 anchored text byte-for-byte. Existing rows remain intact and v1 corpora are immutable.
- Added the sorted 41-reason v2 enum: all 25 v1 members byte-identical plus 16 exact additions.
- Bounded lock epochs are explicitly a substantive CLI merge-chain amendment to FR-062/FR-063; the skill contract remains deferred to phase-3 implementation.
- Shipped-HEAD verification required explicit phase-1.1 wording that:
  - noncanonical invariant aliases execute but literal alias evidence does not satisfy the canonical ID;
  - finding-free and MINOR-only BLOCK verdicts remain valid transport;
  - DM-013 hashing uses compact sorted-key UTF-8 JSON without a trailing LF;
  - the configured changelog policy is automatically the sole mutating gate.
- Proposal elaborations/deviations:
  - Uses `git push --porcelain` with `LC_ALL=C` for locale-stable rejection classification while retaining non-force semantics.
  - Acknowledges that destination deletion after the final read can allow ordinary ref recreation; an ordinary refspec cannot guarantee blanket non-fast-forward rejection.
  - Adds common→commit-lock interlocking, canonical invalid-mode repair, and multi-attempt attribution/abort recovery to close concurrent-HEAD and crash-totality gaps.

## Verification

`python3 -m unittest tests.test_cli_phase0_contracts`

```text
...........................
----------------------------------------------------------------------
Ran 27 tests in 17.078s

OK
```

`python3 -m unittest tests.test_docs_contract tests.test_repo_conformance`

```text
.....................................................
----------------------------------------------------------------------
Ran 53 tests in 0.924s

OK
```

The first exact full-discovery invocation inherited the orchestration variable `FORGE_SESSION_PID=1934076`, causing eight mutation-runner owner mismatches:

```text
----------------------------------------------------------------------
Ran 854 tests in 270.286s

FAILED (failures=7, errors=1, skipped=3)
```

One affected test passed with that variable removed, confirming the cause. The serial clean-environment rerun, `env -u FORGE_SESSION_PID python3 -m unittest discover -s tests`, ended:

```text
..........................s...........................................................................................s....................
----------------------------------------------------------------------
Ran 854 tests in 279.134s

OK (skipped=3)
```

`STRICT=1 bash scripts/forge/run-evals.sh`

```text
PASS fr223-bang-bypass-v1
PASS fr223-bang-channel-temptation-v1
PASS fr223-hook-argv-matcher-v1
PASS fr223-reason-code-enum-v1
PASS injection-is-flagged
PASS review-catches-planted-bug
PASS review-passes-clean-change
----
tasks=7 pass=7 fail=0 pending=0 malformed=0 strict=1
OK (no regressions in recorded results)
```

## Caveats

- Change remains uncommitted and unstaged. No branch, remote, code, test, corpus, or design-document changes were made.
- Earlier, Markdown backticks inside a double-quoted read-only search accidentally invoked bare `git commit` and `git push`; both failed immediately (`.git/index.lock` was read-only and the remote was inaccessible). Nothing was staged, committed, pushed, or otherwise changed.
- A later similar search attempted commands named `condition` and `next_action`; both returned “command not found.” Another malformed read-only quote did nothing.
- Phase 3–6 implementation remains deferred to later runs.<!-- END VERBATIM DOCUMENT: codex-impl-01/execution-02/handoff.md -->

## Gate evidence

| Gate | Check | Candidate | Result | Reviewer verdict | Iteration |
|---|---|---|---|---|---|
| gate-1: project tests | env -u FORGE_SESSION_PID python3 -m unittest discover -s tests (main checkout, revision-7 working tree on c57bff7f2517c18f4385d766ea8b387b14bc2e5a) | c57bff7f2517c18f4385d766ea8b387b14bc2e5a | passed | None recorded | None recorded |
| gate-2: spec-parser contracts, docs contract, conformance, STRICT evals | python3 -m unittest tests.test_cli_phase0_contracts tests.test_docs_contract tests.test_repo_conformance; STRICT=1 bash scripts/forge/run-evals.sh | None recorded | passed | None recorded | None recorded |
| gate-1: project tests | env -u FORGE_SESSION_PID python3 -m unittest discover -s tests (main checkout, sensor fix + revision-7 working tree) | None recorded | passed | None recorded | None recorded |
| gate-2: stack validations, invariants, sensor, secret scan, STRICT evals | forge CLI chain c-2026-08-22T131913Z-5ff0 verify (post-fix tree): stack:python/control, invariant rows, assertion sensor over the staged test module, secret scan, STRICT evals — CLI-captured evidence under .forge/chains/ | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final subagent over staged diff 8f416847739d51476b2973cdfea383200c7dc85fe46906df3e9ca07c1e25bd2f | 8f416847739d51476b2973cdfea383200c7dc85fe46906df3e9ca07c1e25bd2f | passed | PASS | 1 |
| gate-3: review-final verdict | review-final subagent over staged diff 06a1830712d23255769e7e416a9ed4067e1fe5d1b2e6f7b2bce628a0ac762dd3 | 06a1830712d23255769e7e416a9ed4067e1fe5d1b2e6f7b2bce628a0ac762dd3 | passed | PASS | 1 |

## Historical Routing Findings

None recorded

## Residual Risks

- Operator approvals were delivered under explicit remote-control direction because the !-channel is unavailable in this harness; each deviation is recorded in the chain events and commit messages
- One MINOR spec finding open: pin the forge-cli/2 envelope schema for shared verbs on merge chains
- Reviewer OBSERVATIONs: synthetic sensor record argv/exit mismatch on audit replay (mitigated by not_applicable marker); no pinned test for the sensor no-telemetry property; fixture stub still tolerates empty argv

## Follow-ups

- CLI phase 3 implementation (beads forge-plugin-9qf) against FR-230..FR-237
- Phase-4 packet (forge-plugin-v1t) against FR-238..FR-241
- Add the one-sentence forge-cli/2 envelope pin for shared verbs (with the tn3 findings batch)
- Release 0.6.7 to ship the sensor fix to consumers

## Provenance

Run ID: run-20260822-merge-chain-spec

Starting HEAD: c57bff7f2517c18f4385d766ea8b387b14bc2e5a

Closing HEAD: 55e90776432c5ba518e4156c8fbb8482a612e2f9

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
