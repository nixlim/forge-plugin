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
