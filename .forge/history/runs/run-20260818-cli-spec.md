# Durable intent archive: run-20260818-cli-spec

## Goal

Clear the FR-016 review debt by committing its binding-review record, then author the CLI-plumbing commit-slice spec revision (phases 0-2 of docs/design/0003-forge-cli-plumbing.md) in docs/specs/forge-plugin-spec.md through the control-class gate chain.

## Tasks

### task-01

Goal: Commit the FR-016 post-commit binding-review record, clearing the review debt for spec commit 90370cf.

Acceptance criteria:

- docs/design/research/2026-08-18-fr016-post-commit-binding-review.md contains the reviewer's file-delivered PASS report verbatim with disposition
- the record is committed through the full /forge:commit chain at the classifier's effective tier with a distinct reviewer
- gate-1, stack-validation, and invariant evidence recorded

Final status: complete

Final outcome: None recorded

### task-02

Goal: Author the CLI-plumbing commit-slice spec revision (phases 0-2 of docs/design/0003-forge-cli-plumbing.md, decisions D1-D34 as scoped by D21) in docs/specs/forge-plugin-spec.md.

Acceptance criteria:

- new FR range plus DM entries, envelope contract, error rows, scenarios, and traceability row cover the commit slice with no semantic drift from the reviewed design
- raw-verb denial, merge chain, marker deletion, and plan-seal are explicitly out of scope
- the FR-016 editorial amendments from the binding review (leg-7 warning cardinality, leg-8/FR-021 interaction note) are included
- STRICT evals pass, binding review-final PASS bound to the exact staged-diff SHA-256, and explicit operator approval naming that SHA precede the commit

Final status: complete

Final outcome: None recorded

## Decisions

### decision-01

Task: task-01

Finding: The review-cheap execution for task-01 was launched at 2026-08-17T23:09:57Z, before this run was admitted at 2026-08-17T23:12:47Z, so its execution entry is appended after launch instead of before.

Outcome: claude_decision

Resolution: Retain the in-flight read-only reviewer rather than killing and relaunching: its prompt, events, handoff, and pid sidecar are preserved at the recorded paths, the review input is the exact staged diff whose SHA-256 will bind the gate-3 verification, and the ordering anomaly is recorded here rather than repaired by rewriting.

Basis:

- docs/design/research/2026-08-18-fr016-post-commit-binding-review.md
- /tmp/claude-1000/-home-agents-foundry-of-zero-forge-plugin/edb48c72-0313-4b28-a4c5-618e93b42d6f/scratchpad/review-cheap-exec-01/pid

### decision-02

Task: task-02

Finding: The operator's first approval (2026-08-18T00:51:32Z) arrived 57 minutes after the review-final PASS (23:54:39Z), outside the 30-minute freshness window the chain requires between PASS and approval.

Outcome: user_action_required

Resolution: The chain refused the stale authorization path: lock released, marker deleted, no commit. The same reviewer re-verified the byte-identical candidate and HEAD and re-issued PASS at 00:52:11Z (confirmation round, check-11); the operator re-approved naming candidate 5f7d35ba within the fresh window, and finalize proceeded with the marker timestamped at the fresh PASS.

Basis:

- check-10
- check-11
- /tmp/claude-1000/-home-agents-foundry-of-zero-forge-plugin/edb48c72-0313-4b28-a4c5-618e93b42d6f/scratchpad/review-final-spec-verdict.md

### decision-03

Task: task-02

Finding: execution-04's prompt field recorded a descriptive string rather than a file path, so pre-close gated validation reported the referenced prompt file as nonexistent. The review-final reviewer was a Claude subagent launched through the Agent tool, which takes its prompt inline rather than from a prompt.md.

Outcome: claude_decision

Resolution: Repaired by materializing the referenced artifact rather than rewriting the journal: a file with exactly the recorded name now exists in the run directory containing the verbatim Agent-invocation prompt text and a provenance note that it was written post-launch. Future Claude-subagent review executions will write prompt.md before launch and record that path.

Basis:

- .codex-orchestrator/runs/run-20260818-cli-spec/(assembled in Agent tool invocation; candidate 5f7d35babb17c31da8d525c143cf90c4dcc2b471cb81b11f60b0bcd656bd810b bound in prompt)

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
      "task": "task-02"
    }
  ],
  "executions": [
    {
      "agent": "claude-review-final-01",
      "execution": "execution-04",
      "prompt": "(assembled in Agent tool invocation; candidate 5f7d35babb17c31da8d525c143cf90c4dcc2b471cb81b11f60b0bcd656bd810b bound in prompt)",
      "prompt_sha256": "c8a2a43a88937791c956f23c9bb696713c1b52ae8bcadc2d8e5817b760f1ce53",
      "role": "review",
      "task": "task-02"
    }
  ],
  "failed_or_inconclusive_verifications": [
    {
      "criterion": "gate-3: review-final verdict",
      "id": "check-03",
      "observation": "BLOCK; 3 CRITICAL/MAJOR findings; severities CRITICAL=0,MAJOR=3,MINOR=1; reviewer review-cheap; iteration 1 of 8.",
      "result": "failed",
      "task": "task-01"
    },
    {
      "criterion": "gate-3: review-final verdict",
      "id": "check-04",
      "observation": "BLOCK; 1 CRITICAL/MAJOR findings; severities CRITICAL=0,MAJOR=1,MINOR=0; reviewer review-cheap; iteration 2 of 8.",
      "result": "failed",
      "task": "task-01"
    }
  ]
}
```
<!-- END FORGE LEARNING PROVENANCE v1 -->

## Verbatim basis documents

### docs/design/research/2026-08-18-fr016-post-commit-binding-review.md

<!-- BEGIN VERBATIM DOCUMENT: docs/design/research/2026-08-18-fr016-post-commit-binding-review.md -->
# FR-016 Post-Commit Binding Review — 2026-08-18

This record clears the review debt carried in `docs/handover-2026-08-17.md` and the
`run-20260815-followups` archive's residual risks: the FR-016 spec amendment (commit
`90370cf80ddd2c6c9f8dde5386ef79b0aa6b5de8`, `docs/specs/forge-plugin-spec.md`) was
committed at session close under explicit operator direction with gate steps 2–4 skipped
after its review chain was twice voided (one reviewer died silently; HEAD then moved under
a second reviewer). Per this repository's trigger table, `docs/specs/**` requires STRICT
evals plus binding review plus operator approval; the binding-review leg was owed.

A fresh independent `review-final` agent (distinct from the amendment's author session)
reviewed the committed spec text at HEAD `b7acebda2f29ea81cc0d29ad598cbee42e751050`.

Provenance of the report below:

- Reviewer: the plugin `forge:review-final` agent definition (`agents/review-final.md`,
  model fable, read-only tools), spawned as subagent `fr016-review` by orchestrator
  session `edb48c72-0313-4b28-a4c5-618e93b42d6f` on host `v2202608347457500837`.
- Timeline (UTC, 2026-08-17): spawned ≈22:47; the reviewer's transcript held the complete
  report by 22:56:49 (its first idle notification); outbound messaging is disabled for
  `forge:review-final` agents by design, so the orchestrator directed file delivery, and
  the reviewer wrote its report to a session scratchpad file
  (`scratchpad/fr016-review-verdict.md`) by 23:00:01; a comms-check line
  `ack: SendMessage still disabled` was appended to that file by 23:03:32.
- Content binding: the verbatim report below is the delivered file minus that single
  trailing comms-check line. SHA-256 of the verbatim report bytes (file with the final
  line removed): `71a9539e8049de8c761c16819e9b94a8719683f4bfdbdf23feff3e2b6a21251e`.
  SHA-256 of the delivered file including the appended comms-check line:
  `a76329e2bf94f64cc274b981298e244af28444917f7e411bb5ea991b80b407df`.
- Journal: this record's commit is task-01 of run `run-20260818-cli-spec`, whose journal
  carries the gate verifications and the review-iteration history for this candidate.

---

# Binding Review — FR-016 Legacy Journal Compatibility Posture

Verdict: PASS
Iteration: 1
Reviewed commit: 90370cf80ddd2c6c9f8dde5386ef79b0aa6b5de8 at HEAD b7acebda2f29ea81cc0d29ad598cbee42e751050
Reviewer: review-final (binding), distinct from the amendment author.
Profile: review-specification composed with the review-coding verification method (constitution v1.1).
Project trigger fired: docs/specs/** => STRICT evals (re-executed fresh) + binding review (this document). The operator-approval leg remains with the operator.
Parts A–E: ALL COMPLETE.

## A. Spec-vs-implementation fidelity — verified by execution

Implementation located: scripts/codex_orchestrator/journal.py — constants lines 44–64
(LEGACY_COMPATIBILITY_DECLARATION_ID, LEGACY_COMPATIBILITY_RESOLUTION_PREFIX,
LEGACY_COMPATIBILITY_LEGS, LEGACY_EXECUTION_STATUS_MAP); _legacy_compatibility_declaration ~1124;
_legacy_allows ~1142; legs woven through validate_run, check_declared_file, check_gate_profile.
All ten spec-enumerated legs map 1:1 to the code's frozenset (observation, verification-pass,
string-evidence, execution-result-status, execution-task-mismatch, missing-execution-file,
duplicate-verification-id, missing-execution-result, empty-events, failed-gate-recheck).
LEGACY_EXECUTION_STATUS_MAP is exactly handoff-ready->complete, pass->complete, block->blocked.

Read-only in-process probes (tempdir journals, journal.py imported directly) confirmed:
- Declaration grammar: exact id + exact prefix + nonempty stripped justification; CR-embedded
  justification refused (no activation warning, strict issues remain). Wrong id/prefix and
  empty/whitespace justification pinned by test_legacy_compatibility_requires_the_exact_declaration_grammar.
- Present-but-malformed result NEVER rescued: result:"ok" + status:"pass" -> hard
  "line 3: verification result is not recognized: ok"; absent result + status:"pass" -> rescued
  with warning "interpreted verification result from status 'pass' with no result as 'passed'".
- Second declaration -> hard "line 4: duplicate decision id journal-dialect-compat", ok:false.
- At/after-declaration fully strict (_legacy_allows uses strict < declaration_line):
  post-declaration observation -> hard issue; run_closed with bad judgment -> hard
  "line 6: run_closed judgment must be passed or blocked".
- Undeclared journal byte-identical to strict: same issue text, zero warnings.
- Validator-assigned line numbers never taken from journal content: read_journal unconditionally
  overwrites any journal-supplied _line (journal.py:1084); spoofed _line:999/1 records still
  reported at their real lines.
- "(inline)" sentinel tolerated pre-declaration ("tolerated missing prompt file '(inline)'");
  existing non-file paths stay hard (test_legacy_missing_execution_file_leg_keeps_existing_non_files_hard).
- Raw records authoritative for lifecycle (starts/closures from raw records) and citation checks
  (_validate_citation_targets on raw records regardless of declaration).
- non_passing_verifications reporting unchanged by tolerance (strict/compat parity asserted by
  test_legacy_compatibility_normalizes_all_ten_legs_and_preserves_strict_parity).
- Task-mismatch leg requires both records pre-declaration AND both task IDs known
  (task_id in tasks and result_task in tasks); execution task authoritative (result["task"] rewritten);
  test_legacy_task_mismatch_never_conceals_an_unknown_task pins the floor.

No semantic drift found between the committed spec text and the committed implementation.

## B. Disable-detection tests — real, in-memory

tests/test_validation.py:158 assert_legacy_leg_is_load_bearing validates the same journal twice:
once with the shipped LEGACY_COMPATIBILITY_LEGS, once under
mock.patch.object(journal, "LEGACY_COMPATIBILITY_LEGS", enabled - {leg}),
asserting compat ok:true flips to ok:false with the exact strict issue resurfacing. This is a
genuine in-memory control-disable — _legacy_allows consults that frozenset on every application —
not a happy-path test. All TEN legs have dedicated tests (test_validation.py:1108–1204) plus an
events-variant disable test for missing-execution-file. All ten were executed (exceeds the
required two-leg spot check); the mechanism was inspected end-to-end.

## C. Commands executed and exit codes

| Command | Result | Exit |
|---|---|---|
| python3 -m unittest tests.test_validation tests.test_run_coordination tests.test_audit_commitments | 120 tests OK (2 env-dependent skips) | 0 |
| python3 -m unittest tests.test_repo_conformance tests.test_docs_contract tests.test_governance_content | 74 tests OK | 0 |
| python3 -m unittest discover -s tests  (full gate, single run) | 712 tests OK (skipped=3) | 0 |
| STRICT=1 bash scripts/forge/run-evals.sh | tasks=3 pass=3 fail=0 strict=1 — re-executed fresh; no reliance on recorded STRICT evidence | 0 |
| bash scripts/forge/run-evals.sh (non-strict, incidental) | 3/3 PASS | 0 |
| git rev-parse HEAD; git show 90370cf | diff/message inspected | 0 |
| Two read-only in-process probe scripts (semantic edges; duplicate-warning cardinality) | outputs as cited in A and Findings | 0 |

Note: the project completeness item "full discovery passes twice consecutively after the last
defect fix" binds after a defect fix; no fix occurred in this session — discovery ran once, green.

## Findings

[AMB-07] Severity: MINOR
Location: docs/specs/forge-plugin-spec.md, FR-016 ("each emitted per application plus one activation warning")
Finding: For leg 7 (duplicate verification IDs) the code emits ONE consolidated warning per
tolerated duplicate ID listing all occurrence lines, while strict mode emits one issue per
duplicate occurrence — the per-application cardinality claim is imprecise for this leg.
Evidence (executed): triple-duplicate probe — strict issues at lines 4 and 5; compat single warning
"line 4: legacy compatibility tolerated duplicate verification id dup; occurrences at lines 3, 4, 5";
activation warnings: 1; compat ok: true. No information or control strength lost.
Recommendation: future editorial pass — state that leg 7 warns once per tolerated ID with all
occurrence lines listed.

[INC-03] Severity: OBSERVATION
Location: docs/specs/forge-plugin-spec.md, FR-016 leg (8) / FR-021 interaction; journal.py:1248–1259
Finding: FR-016 is silent that leg 8's tolerance also prevents the FR-021 unterminated-mutation
gate veto for pre-declaration executions.
Evidence: code comment and veto logic in check_gate_profile honor the missing-execution-result leg;
pinned by test_legacy_unterminated_mutations_do_not_veto_gates_after_declaration. FR-021's literal
text presupposes each mutating execution has a terminal result, so compat behavior does not
contradict it, and strict mode remains stricter-than-spec in a journal already failing the baseline
missing-result check. No gate weakening.
Recommendation: add a clarifying clause in a future editorial spec pass.

[CON-02] Severity: OBSERVATION
Location: docs/specs/forge-plugin-spec.md traceability row FR-010..FR-016; tests/test_validation.py:1207; tests/test_run_coordination.py:203
Finding: The claimed "real legacy-prefix acceptance" integration surface exists
(test_real_palimpsest_reviewed_prefix_accounts_for_all_legacy_issues,
test_real_legacy_journals_admit_a_new_run) but skipUnless-skips in this checkout — the fixture
lives at ../palimpsest, absent here (the 3 skips in the full run).
Evidence: ls of ../palimpsest path -> No such file or directory; unittest -v shows the explicit skip.
Recommendation: none required — synthetic per-leg coverage runs unconditionally; optionally note the
sibling-checkout dependency where the surface is documented.

Gate-weakening check (D): the FR-011 exception sentence is keyed to "a journal bearing an FR-016
declaration"; undeclared byte-identity was verified by execution and is restated as a floor inside
FR-016 itself — it cannot be read as loosening undeclared-journal validation. Injection surface
(untrusted journal content supplies the declaration): exact-id + exact-prefix keying, single-line
CR/LF-forbidden justification (no warning-line splitting), spoofed _line ignored, tolerance
strictly narrowed to pre-declaration physical lines, and widening the tolerated set declared
control-class. Prose quality (E): the ten-item enumeration has no overlaps (empty events = leg 9
vs missing files = leg 6 are disjoint in code and text) and no exploitable gaps; the control-class
widening sentence is unambiguous. All 8 constitution lenses applied — Infeasibility and
Overcomplexity yielded no findings (the frozenset mechanism is minimal and is what enables the
disable tests); constitution completeness check and project completeness items done.

## Justification

The committed FR-016 text accurately describes the control it governs — every one of the ten
tolerance legs, the declaration grammar, the pre-declaration boundary, the exact status mappings,
the never-rescued malformed-result rule, and every hard floor was verified against
scripts/codex_orchestrator/journal.py by in-process execution rather than prose; all ten
disable-detection tests use a genuine in-memory control-disable and pass; the full 712-test gate
and STRICT evals were re-executed fresh against HEAD and are green; and the FR-011 exception
sentence demonstrably cannot loosen undeclared-journal validation. The findings are one MINOR
prose-cardinality imprecision and two documentation-completeness observations, none of which
misdescribes or weakens the control — with no CRITICAL or MAJOR findings, the amendment passes
under the constitution's verdict rules. This PASS clears the recorded review debt for commit
90370cf; the operator-approval leg of the docs/specs/** trigger remains with the operator.

---

## Disposition (orchestrator)

- Verdict: PASS at iteration 1; the binding-review leg owed for `90370cf` is supplied by
  this record.
- Finding [AMB-07] (MINOR, leg-7 warning cardinality). Stated plainly: this is a real
  divergence between FR-016's text and the implementation on warning cardinality — the
  spec says tolerated diagnostics are warned "each emitted per application", while for
  leg 7 the implementation emits one consolidated warning per tolerated duplicate ID
  listing all occurrence lines. The binding reviewer verified by execution that no
  information or control strength is lost (every occurrence line is reported; strict-mode
  issues are unaffected) and therefore classified it MINOR prose imprecision rather than a
  control defect. Resolution: the FR-016 sentence is amended to match the implemented
  cardinality as part of the next `docs/specs/**` revision (task-02 of
  `run-20260818-cli-spec`, the CLI commit-slice revision), which runs the full
  control-class chain — STRICT evals, binding `review-final`, and explicit operator
  approval. Until that amendment lands, this divergence is tracked here, not silently
  absorbed.
- Finding [INC-03] (OBSERVATION, leg-8/FR-021 interaction): editorial clarification,
  folded into the same `docs/specs/**` revision.
- Finding [CON-02] (OBSERVATION): environment-dependent skips are by design (`skipUnless`
  on the sibling palimpsest checkout); no action.
- The original commit's operator direction (recorded in the 90370cf commit message)
  supplied the operator-approval leg; this record supplies the previously voided
  binding-review leg.

## Commit-chain review history for this record

This record itself was committed at standard tier (the classifier's unknown-manifest floor
promoted it above the `docs/**` fast row). Its first-pass `review-cheap` iteration
returned BLOCK with findings COR-03 (the launch assignment supplied no immutable review
target — corrected: for commit reviews the immutable candidate identity is the staged-diff
SHA-256 per FR-052/DM-006, now stated in the assignment), COR-01 (the record's framing
claimed "no semantic drift" while its own [AMB-07] evidence shows the leg-7 cardinality
divergence — corrected in the [AMB-07] disposition above), CON-02 (unverifiable external
report provenance — corrected by the Provenance section above), and AMB-06 (imprecise
review timestamps — corrected in the same section). The revised record then re-entered
review; the accepted iteration's verdict is recorded in the run journal.
<!-- END VERBATIM DOCUMENT: docs/design/research/2026-08-18-fr016-post-commit-binding-review.md -->

## Gate evidence

| Gate | Check | Candidate | Result | Reviewer verdict | Iteration |
|---|---|---|---|---|---|
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-2: stack validations and commit invariants | python3 -m unittest tests.test_repo_conformance | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-cheap over staged diff 54b429eb6ed81632f36453c1eef1850d3f1f428059a930451e972930cf52955a | 54b429eb6ed81632f36453c1eef1850d3f1f428059a930451e972930cf52955a | failed | BLOCK | 1 |
| gate-3: review-final verdict | review-cheap over staged diff e0e0bd5608f35aaf52467294a02406e446623850129b759cd9cd2209b1b8e1ba | e0e0bd5608f35aaf52467294a02406e446623850129b759cd9cd2209b1b8e1ba | failed | BLOCK | 2 |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-cheap over staged diff e0e0bd5608f35aaf52467294a02406e446623850129b759cd9cd2209b1b8e1ba | e0e0bd5608f35aaf52467294a02406e446623850129b759cd9cd2209b1b8e1ba | passed | PASS | 3 |
| gate-1: project tests | python3 -m unittest discover -s tests | None recorded | passed | None recorded | None recorded |
| gate-2: stack validations, invariants, and STRICT evals | python3 -m unittest tests.test_repo_conformance; STRICT=1 bash run-evals.sh | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final subagent over staged diff 5f7d35babb17c31da8d525c143cf90c4dcc2b471cb81b11f60b0bcd656bd810b | 5f7d35babb17c31da8d525c143cf90c4dcc2b471cb81b11f60b0bcd656bd810b | passed | PASS | 1 |
| gate-3: review-final verdict | review-final confirmation round over staged diff 5f7d35babb17c31da8d525c143cf90c4dcc2b471cb81b11f60b0bcd656bd810b | 5f7d35babb17c31da8d525c143cf90c4dcc2b471cb81b11f60b0bcd656bd810b | passed | PASS | 2 |

## Historical Routing Findings

- journal line 22: agent 'claude-review-final-01' recorded model/effort ('claude-fable-5', 'high'); expected model/effort ('fable', 'high') from 9d22d5bef2881390616fad2fb1771b3cd3b909e5:agents/review-final.md

## Dispensed Citations

- /tmp/claude-1000/-home-agents-foundry-of-zero-forge-plugin/edb48c72-0313-4b28-a4c5-618e93b42d6f/scratchpad/review-cheap-exec-01/pid (decision decision-01 basis[1]) — reason: Operator-directed 2026-08-21: pre-FR-017 session cited scratchpad artifact paths; artifacts preserved in evidence-preserved/ inside the run directory.
- /tmp/claude-1000/-home-agents-foundry-of-zero-forge-plugin/edb48c72-0313-4b28-a4c5-618e93b42d6f/scratchpad/review-final-spec-verdict.md (decision decision-02 basis[2]) — reason: Operator-directed 2026-08-21: pre-FR-017 session cited scratchpad artifact paths; artifacts preserved in evidence-preserved/ inside the run directory.

## Residual Risks

- Five MINOR findings and six OBSERVATIONs from the revision-4 binding review are deferred obligations on the phase-1 implementation revision (FR-090 dual-accept cross-reference, event-emission ownership for CLI-finalized commits, review-skip transition, DM-012 archive-travel wording, layer-3 permission-bypass caveat, chain_id timestamp grammar, chain GC actor, validate-gates negative test).
- The gitignore-block template gains /.forge/chains/ only at phase 1; until then DM-007's spec text is ahead of the shipped template by design.

## Follow-ups

- Phase 0: author and commit the FR-223 precondition evals (!-bypass, CLI argv matcher, reason-code enum, !-channel temptation).
- Phase 1: implement scripts/forge/cli.py per FR-210..FR-224 with the dual-accept hook change, resolving the five MINOR review findings in the same control-class revision.
- Beads: forge-plugin-3bh gate1 targeted paths, forge-plugin-xqb stable machine identity, forge-plugin-479 codex byte-identity invariant, forge-plugin-afq drift-check self-locate, forge-plugin-1k9 release-protocol enforcement.
- Learning-shape investigations, findings-telemetry-void first.
- Record the review-final file-delivery protocol as a bead/bd-remember from a machine with beads installed.

## Provenance

Run ID: run-20260818-cli-spec

Starting HEAD: b7acebda2f29ea81cc0d29ad598cbee42e751050

Closing HEAD: 9d69cd98ff8f1611d27a7a7b64e77af3b0f09b02

### Operator-directed dispensation

- `--dispense-citation decision-01 basis[1]`
- `--dispense-citation decision-02 basis[2]`
- `--dispense-reason Operator-directed 2026-08-21: pre-FR-017 session cited scratchpad artifact paths; artifacts preserved in evidence-preserved/ inside the run directory.`

### Pre-close validation payload embedded in `run_closed`

```json
{
  "issues": [],
  "non_passing_verifications": [
    {
      "check": "review-cheap over staged diff 54b429eb6ed81632f36453c1eef1850d3f1f428059a930451e972930cf52955a",
      "criterion": "gate-3: review-final verdict",
      "id": "check-03",
      "observation": "BLOCK; 3 CRITICAL/MAJOR findings; severities CRITICAL=0,MAJOR=3,MINOR=1; reviewer review-cheap; iteration 1 of 8.",
      "result": "failed",
      "task": "task-01"
    },
    {
      "check": "review-cheap over staged diff e0e0bd5608f35aaf52467294a02406e446623850129b759cd9cd2209b1b8e1ba",
      "criterion": "gate-3: review-final verdict",
      "id": "check-04",
      "observation": "BLOCK; 1 CRITICAL/MAJOR findings; severities CRITICAL=0,MAJOR=1,MINOR=0; reviewer review-cheap; iteration 2 of 8.",
      "result": "failed",
      "task": "task-01"
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
      "check": "review-cheap over staged diff 54b429eb6ed81632f36453c1eef1850d3f1f428059a930451e972930cf52955a",
      "criterion": "gate-3: review-final verdict",
      "id": "check-03",
      "observation": "BLOCK; 3 CRITICAL/MAJOR findings; severities CRITICAL=0,MAJOR=3,MINOR=1; reviewer review-cheap; iteration 1 of 8.",
      "result": "failed",
      "task": "task-01"
    },
    {
      "check": "review-cheap over staged diff e0e0bd5608f35aaf52467294a02406e446623850129b759cd9cd2209b1b8e1ba",
      "criterion": "gate-3: review-final verdict",
      "id": "check-04",
      "observation": "BLOCK; 1 CRITICAL/MAJOR findings; severities CRITICAL=0,MAJOR=1,MINOR=0; reviewer review-cheap; iteration 2 of 8.",
      "result": "failed",
      "task": "task-01"
    }
  ],
  "ok": true,
  "profile": "gates",
  "warnings": []
}
```
