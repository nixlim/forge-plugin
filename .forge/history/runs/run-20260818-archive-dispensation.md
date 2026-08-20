# Durable intent archive: run-20260818-archive-dispensation

## Goal

Two-part archive-integrity workstream: (1) prevention - append-time enforcement that journal records cite only paths within the run directory or repository, plus the corresponding spec FRs including the CLI-chain journaling rule; (2) cure - an operator-directed dispensation mechanism letting closed, otherwise-unarchivable runs (out-of-root citations; pre-D13 dialects with no appendable declaration) validate and archive with visible degraded sections, never silently.

## Tasks

### task-01

Goal: Spec revision 5: FR-017 append-time citation-root enforcement, FR-018 operator-directed closed-run dispensation, FR-016/FR-170/FR-210 amendments, error rows, scenarios, traceability, test obligations.

Acceptance criteria:

- FR-017 and FR-018 match the run plan with no invented policy
- strict no-flag behavior specified byte-identical to current behavior
- every new tolerance/enforcement leg carries a disable-detection test obligation
- STRICT evals, review-final PASS bound to the staged-diff SHA-256, and operator approval naming that SHA precede the commit

Final status: complete

Final outcome: None recorded

### task-02

Goal: Implement FR-017: journal-append/run-open/run-close refuse records citing paths outside the run directory or repository, reusing the commitment_paths tokenizer, with the exact diagnostic and focused disable-detection tests.

Acceptance criteria:

- out-of-root citation in any checked field refuses with the exact diagnostic and writes nothing
- in-root relative citations append unchanged; absolute citations refused outright; resolve-then-contain symlink semantics
- tokenizer and containment shared with the audit (no second predicate)
- a focused test fails when the enforcement is disabled in memory
- full discovery passes twice consecutively after the last fix

Final status: complete

Final outcome: None recorded

### task-03

Goal: Implement FR-018: validate --gates --closed-legacy-compat and audit/archive --dispense-citation flags with visible degraded sections, strict-path parity, and per-leg disable-detection tests.

Acceptance criteria:

- closed pre-D13-style journal validates ok:true under the flag with the activation warning; without the flag byte-identical strict
- audit degrades exactly the named citations to a visible Dispensed Citations section; non-dispensed citations still fail(5)
- archive renders the dispensed section and records the flags under provenance
- focused tests fail when each dispensation leg is disabled in memory
- full discovery passes twice consecutively after the last fix

Final status: complete

Final outcome: None recorded

## Decisions

### decision-01

Task: task-02

Finding: Merge Gate 1 initially FAILED (1 failure, 2 errors) because the orchestrator ran full discovery concurrently with the scoped-mutation runner and Gate 2 suites in the same worktree, and the failure was masked as passed because PIPESTATUS was read through the background-task wrapper (check-11, corrected by check-13).

Outcome: claude_decision

Resolution: Two clean consecutive serial re-runs (check-14, check-15) establish the candidate passes; check-11 is void as evidence. Standing lessons: gate suites are never run concurrently with other executions in the same checkout, and gate pass/fail is read from the suite's own output tail, never a wrapper exit code.

Basis:

- check-13
- check-14
- check-15

### forge-scope-readmission-784fed6e424847d5883e09a870cf005f

Task: None recorded

Finding: None recorded

Outcome: None recorded

Resolution: scope-readmission: locked

Basis:

None recorded

### decision-02

Task: task-03

Finding: Codex implementation capacity is unavailable until 2026-08-20T05:31 (provider usage limit), stalling the Codex-implementer path for FR-018.

Outcome: claude_decision

Resolution: Claude implements FR-018 directly in the already-created worktree (untouched by the failed execution), preserving separation of duties: the binding reviewer remains a distinct review-final subagent, and the change is control-class so no review-cheap (Codex) leg is required by policy. Serial-only suite execution per decision-01. The operator is informed in-session.

Basis:

- codex-impl-02/execution-06/events.jsonl
- check-16

### forge-scope-readmission-0804b01542f4473786cb57eb77b211dc

Task: None recorded

Finding: None recorded

Outcome: None recorded

Resolution: scope-readmission: locked

Basis:

None recorded

## Learning provenance

<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->
```json
{
  "decisions": [
    {
      "id": "decision-01",
      "task": "task-02"
    },
    {
      "id": "decision-02",
      "task": "task-03"
    }
  ],
  "executions": [
    {
      "agent": "claude-review-final-01",
      "execution": "execution-01",
      "prompt": "claude-review-final-01/execution-01/prompt.md",
      "prompt_sha256": "b5d019cd111d699124842fc25fa3c896bb81aa0d15b42e55d57d8e06cdefc6f8",
      "role": "review",
      "task": "task-01"
    },
    {
      "agent": "claude-review-final-02",
      "execution": "execution-02",
      "prompt": "claude-review-final-02/execution-02/prompt.md",
      "prompt_sha256": "c4699385f6334317cfdb13e0bb277c37ced792955d1b6ee4c3e95fc1c67296ab",
      "role": "review",
      "task": "task-01"
    },
    {
      "agent": "codex-impl-01",
      "execution": "execution-03",
      "prompt": "codex-impl-01/execution-03/prompt.md",
      "prompt_sha256": "d8a3b625bd4e60fe076674c4458c647b72d7528c526c0d7b92ddeff30a0dc873",
      "role": "implementation",
      "task": "task-02"
    },
    {
      "agent": "claude-review-final-03",
      "execution": "execution-04",
      "prompt": "claude-review-final-03/execution-04/prompt.md",
      "prompt_sha256": "54aaaf2b66d6e61bcfa784b2ca23fcc5f0c3b5f548cbc43af8aacc3585107116",
      "role": "review",
      "task": "task-02"
    },
    {
      "agent": "claude-review-final-04",
      "execution": "execution-05",
      "prompt": "claude-review-final-04/execution-05/prompt.md",
      "prompt_sha256": "527774f6fdfd1b8d0eaa5c743e907c81c11effc60114665bb48f9ef65b1e287d",
      "role": "review",
      "task": "task-02"
    },
    {
      "agent": "codex-impl-02",
      "execution": "execution-06",
      "prompt": "codex-impl-02/execution-06/prompt.md",
      "prompt_sha256": "917c45f57e105f1e0d1c8bcd7f62c8306a8354f4c3863762041073cf4dc982ff",
      "role": "implementation",
      "task": "task-03"
    },
    {
      "agent": "claude-review-final-05",
      "execution": "execution-07",
      "prompt": "claude-review-final-05/execution-07/prompt.md",
      "prompt_sha256": "0bce115835fe782fc5ba7e7ef04f1b33da4252bb6e09195dfc2d86a8b8d4d59d",
      "role": "review",
      "task": "task-03"
    }
  ],
  "failed_or_inconclusive_verifications": [
    {
      "criterion": "gate-3: review-final verdict",
      "id": "check-03",
      "observation": "BLOCK; 4 CRITICAL/MAJOR findings; severities CRITICAL=1,MAJOR=3,MINOR=3; reviewer review-final; iteration 1 of 8.",
      "result": "failed",
      "task": "task-01"
    },
    {
      "criterion": "gate-1: project tests",
      "id": "check-13",
      "observation": "CORRECTION of check-11: the merge Gate 1 run actually FAILED (failures=1, errors=2, skipped=3, 721 tests); check-11 recorded passed because the orchestrator's exit-code capture read PIPESTATUS through a background wrapper and reported 0. The failing run executed concurrently with the scoped-mutation runner and Gate 2 suites in the same worktree; investigating whether the failures are real defects or concurrency artifacts. A clean serial re-run follows; check-11's passed result must not be treated as gate evidence.",
      "result": "failed",
      "task": "task-02"
    }
  ]
}
```
<!-- END FORGE LEARNING PROVENANCE v1 -->

## Verbatim basis documents

### codex-impl-02/execution-06/events.jsonl

<!-- BEGIN VERBATIM DOCUMENT: codex-impl-02/execution-06/events.jsonl -->
{"type":"thread.started","thread_id":"01a0150e-0365-7a33-b84b-748b4a7ce5ad"}
{"type":"turn.started"}
{"type":"error","message":"You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at Aug 20th, 2026 5:31 AM."}
{"type":"turn.failed","error":{"message":"You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at Aug 20th, 2026 5:31 AM."}}
<!-- END VERBATIM DOCUMENT: codex-impl-02/execution-06/events.jsonl -->

## Gate evidence

| Gate | Check | Candidate | Result | Reviewer verdict | Iteration |
|---|---|---|---|---|---|
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-2: stack validations, invariants, and STRICT evals | python3 -m unittest tests.test_repo_conformance; STRICT=1 bash run-evals.sh | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final subagent over staged diff 1374d6e196ad476931d2b987ecf7d15b7cfcafc081200dcca72f6b397ee30c7a | 1374d6e196ad476931d2b987ecf7d15b7cfcafc081200dcca72f6b397ee30c7a | failed | BLOCK | 1 |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final subagent over staged diff f5441de360fe02668851e09a4752b563d524b050c15317bd65f54968ce3f151c | f5441de360fe02668851e09a4752b563d524b050c15317bd65f54968ce3f151c | passed | PASS | 2 |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-2: stack validations, invariants, sensor, and STRICT evals | python3 -m unittest tests.test_repo_conformance; check-test-quality.py; STRICT=1 run-evals.sh | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final subagent over staged diff 8f1f2bb204d5166ace5ba50a1d29a72e3541e56448d4061c84e634ee202a66ac | 8f1f2bb204d5166ace5ba50a1d29a72e3541e56448d4061c84e634ee202a66ac | passed | PASS | 1 |
| gate-3: review-final verdict | review-final confirmation round over staged diff 8f1f2bb204d5166ace5ba50a1d29a72e3541e56448d4061c84e634ee202a66ac | 8f1f2bb204d5166ace5ba50a1d29a72e3541e56448d4061c84e634ee202a66ac | passed | PASS | 2 |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-2: stack validations and merge invariants | python3 -m unittest tests.test_repo_conformance; check-test-quality.py | None recorded | passed | None recorded | None recorded |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | failed | None recorded | None recorded |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final subagent over git diff f3f8fa3b5dec00103c4771dc606fa3a3f90cfe81...d9f705fa441c0c597d82eb59a8fbd69343ffd803 | d9f705fa441c0c597d82eb59a8fbd69343ffd803 | passed | PASS | 1 |
| gate-2: locked rebase reintegration and fast-forward push | git rebase origin/main; git push origin HEAD:main | None recorded | passed | None recorded | None recorded |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final subagent over staged diff afb9c2d08b38ea823eb77132134377a0b7e5cdfcec92a77b5e5986a413545417 | afb9c2d08b38ea823eb77132134377a0b7e5cdfcec92a77b5e5986a413545417 | passed | PASS | 1 |
| gate-3: review-final verdict | review-final confirmation round over staged diff afb9c2d08b38ea823eb77132134377a0b7e5cdfcec92a77b5e5986a413545417 | afb9c2d08b38ea823eb77132134377a0b7e5cdfcec92a77b5e5986a413545417 | passed | PASS | 2 |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-2: stack validations and merge invariants | python3 -m unittest tests.test_repo_conformance; check-test-quality.py | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final merge-composition review over git diff d9f705fa441c0c597d82eb59a8fbd69343ffd803...9ac712d0edf9c1549df4b2fce1305005556b72e2 | 9ac712d0edf9c1549df4b2fce1305005556b72e2 | passed | PASS | 1 |
| gate-2: locked rebase reintegration and fast-forward push | git rebase origin/main; git push origin HEAD:main | None recorded | passed | None recorded | None recorded |

## Historical Routing Findings

- journal line 7: agent 'claude-review-final-01' recorded model/effort ('claude-fable-5', 'high'); expected model/effort ('fable', 'high') from f3f8fa3b5dec00103c4771dc606fa3a3f90cfe81:agents/review-final.md
- journal line 10: agent 'claude-review-final-02' recorded model/effort ('claude-fable-5', 'high'); expected model/effort ('fable', 'high') from f3f8fa3b5dec00103c4771dc606fa3a3f90cfe81:agents/review-final.md
- journal line 21: agent 'claude-review-final-03' recorded model/effort ('claude-fable-5', 'high'); expected model/effort ('fable', 'high') from a3c2c1766cb29ad245245de4b5df7e9b7906dbe1:agents/review-final.md
- journal line 28: agent 'claude-review-final-04' recorded model/effort ('claude-fable-5', 'high'); expected model/effort ('fable', 'high') from d9f705fa441c0c597d82eb59a8fbd69343ffd803:agents/review-final.md
- journal line 46: agent 'claude-review-final-05' recorded model/effort ('claude-fable-5', 'high'); expected model/effort ('fable', 'high') from d9f705fa441c0c597d82eb59a8fbd69343ffd803:agents/review-final.md

## Residual Risks

- The FR-018 dispensation for run-20260818-cli-spec is implemented and smoke-proven against the real journal but not yet exercised for its committed archive; it awaits explicit operator direction naming that run (FR-018(c)).
- MINOR review follow-ups deferred: mechanical append/audit coextensiveness pin, shared containment predicate extraction, dedicated no-flag parity test strengthening, one untested refusal branch, revision-5 wording notes (pipeline-vs-audit attribution; existence/branch-fallback clause).

## Follow-ups

- Dispensed archive of run-20260818-cli-spec on explicit operator direction.
- Archive pre-D13 runs 20260808/20260811 from their origin machine using validate --closed-legacy-compat once operator-directed there.
- CLI phase-0 precondition evals (FR-223), then phase-1 cli.py implementation.
- Remaining beads: forge-plugin-3bh, xqb, 479, afq, 1k9; learning-shape investigations.

## Provenance

Run ID: run-20260818-archive-dispensation

Starting HEAD: f3f8fa3b5dec00103c4771dc606fa3a3f90cfe81

Closing HEAD: 9ac712d0edf9c1549df4b2fce1305005556b72e2

### Pre-close validation payload embedded in `run_closed`

```json
{
  "issues": [],
  "non_passing_verifications": [
    {
      "check": "review-final subagent over staged diff 1374d6e196ad476931d2b987ecf7d15b7cfcafc081200dcca72f6b397ee30c7a",
      "criterion": "gate-3: review-final verdict",
      "id": "check-03",
      "observation": "BLOCK; 4 CRITICAL/MAJOR findings; severities CRITICAL=1,MAJOR=3,MINOR=3; reviewer review-final; iteration 1 of 8.",
      "result": "failed",
      "task": "task-01"
    },
    {
      "check": "No mutation tool available for python — assertion-quality fallback only.",
      "criterion": "mutation: python",
      "id": "mutation-fdac94f1a20d489796c94a9e0eab2100",
      "observation": "tool=none; scope=python; outcome=declared-absence; scoped_files=[\"tests/test_run_coordination.py\"]; timeout=not-applicable",
      "result": "skipped",
      "task": "task-02"
    },
    {
      "check": "python3 -m unittest discover -s tests",
      "criterion": "gate-1: project tests",
      "id": "check-13",
      "observation": "CORRECTION of check-11: the merge Gate 1 run actually FAILED (failures=1, errors=2, skipped=3, 721 tests); check-11 recorded passed because the orchestrator's exit-code capture read PIPESTATUS through a background wrapper and reported 0. The failing run executed concurrently with the scoped-mutation runner and Gate 2 suites in the same worktree; investigating whether the failures are real defects or concurrency artifacts. A clean serial re-run follows; check-11's passed result must not be treated as gate evidence.",
      "result": "failed",
      "task": "task-02"
    },
    {
      "check": "No mutation tool available for python — assertion-quality fallback only.",
      "criterion": "mutation: python",
      "id": "mutation-87e8b8dd973b484b866b908924132f26",
      "observation": "tool=none; scope=python; outcome=declared-absence; scoped_files=[\"tests/test_archive_run.py\",\"tests/test_audit_commitments.py\",\"tests/test_validation.py\"]; timeout=not-applicable",
      "result": "skipped",
      "task": "task-03"
    }
  ],
  "ok": true,
  "profile": "gates",
  "warnings": [
    "execution codex-impl-02/execution-06 handoff is missing or empty"
  ]
}
```

### Post-close validation result

```json
{
  "issues": [],
  "non_passing_verifications": [
    {
      "check": "review-final subagent over staged diff 1374d6e196ad476931d2b987ecf7d15b7cfcafc081200dcca72f6b397ee30c7a",
      "criterion": "gate-3: review-final verdict",
      "id": "check-03",
      "observation": "BLOCK; 4 CRITICAL/MAJOR findings; severities CRITICAL=1,MAJOR=3,MINOR=3; reviewer review-final; iteration 1 of 8.",
      "result": "failed",
      "task": "task-01"
    },
    {
      "check": "No mutation tool available for python — assertion-quality fallback only.",
      "criterion": "mutation: python",
      "id": "mutation-fdac94f1a20d489796c94a9e0eab2100",
      "observation": "tool=none; scope=python; outcome=declared-absence; scoped_files=[\"tests/test_run_coordination.py\"]; timeout=not-applicable",
      "result": "skipped",
      "task": "task-02"
    },
    {
      "check": "python3 -m unittest discover -s tests",
      "criterion": "gate-1: project tests",
      "id": "check-13",
      "observation": "CORRECTION of check-11: the merge Gate 1 run actually FAILED (failures=1, errors=2, skipped=3, 721 tests); check-11 recorded passed because the orchestrator's exit-code capture read PIPESTATUS through a background wrapper and reported 0. The failing run executed concurrently with the scoped-mutation runner and Gate 2 suites in the same worktree; investigating whether the failures are real defects or concurrency artifacts. A clean serial re-run follows; check-11's passed result must not be treated as gate evidence.",
      "result": "failed",
      "task": "task-02"
    },
    {
      "check": "No mutation tool available for python — assertion-quality fallback only.",
      "criterion": "mutation: python",
      "id": "mutation-87e8b8dd973b484b866b908924132f26",
      "observation": "tool=none; scope=python; outcome=declared-absence; scoped_files=[\"tests/test_archive_run.py\",\"tests/test_audit_commitments.py\",\"tests/test_validation.py\"]; timeout=not-applicable",
      "result": "skipped",
      "task": "task-03"
    }
  ],
  "ok": true,
  "profile": "gates",
  "warnings": [
    "execution codex-impl-02/execution-06 handoff is missing or empty"
  ]
}
```
