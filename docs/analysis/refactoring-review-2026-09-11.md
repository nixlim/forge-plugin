# Refactoring and simplification analysis — forge-plugin

*An analysis for operator review. The recommendations in §4 are proposals, not designs.*

Date: 2026-09-11 · Branch `main` · HEAD `2d2faa60378959d83bd5cad4e56a85390b912da1`
Scope: read-only structural analysis — `git log`, AST/grep scripts, unittest *loading* (not
execution) for shard counts, and a timed sample of seven test modules. Every number and line
citation was re-derived at this HEAD with the appendix commands (revision 4 re-measured the
co-change, shard and spec-form figures after the iteration-3 review: A8, A10). That review's
unresolved design objections are carried verbatim in §7.

Lenses: the ponytail decision ladder (`github.com/DietrichGebert/ponytail`, `AGENTS.md`,
`skills/ponytail/SKILL.md`) and the eight lenses of `rules/review-constitution.md`. Ponytail's
own ceiling applies throughout: "never simplify away input validation, error handling,
security … or explicitly requested features" — here, the fail-closed gates.

## 1. Executive summary

Three structural facts explain the concentration the operator measured:

1. **The FR-230 manifest pins 16 files by byte digest into one preimage** (`subject_candidate`,
   `tests/test_fr230_phase3_manifest.py:221`). Any byte change in any of the 11 production or
   5 test subjects invalidates 5 result fixtures + the manifest + the byte-pin test. Measured
   (A10): the manifest and the five fixtures are lockstep — all 22 manifest commits (of
   110) carry all five — and 4 of the 22 changed nothing but digests. The byte-pin test
   `tests/test_fr223_v2_byte_pins.py` is *not* lockstep: it joined 17 of the 22 (§2.2). HEAD
   itself is an example: a 19-line `policy.py` diff (16+/3−) re-minted all seven.
2. **Two packages hold one state machine.** `_merge_transition_valid` exists twice
   (`scripts/forge/forge_cli/chain_core.py:3741`, 1,984 lines, cyclomatic 897;
   `scripts/codex_orchestrator/builders.py:5505`, 601 lines), the first composing over the
   second, and the packages import each other (`builders.py:2714-2716` ↔ `runtime.py:74`).
   The co-change is real but not lockstep (A10): 24 commits touch at least one of
   `chain_core`, `builders`, `journal` and the 13,883-line `test_revision9_coordination.py`;
   only 3 touch all four. The `codex_orchestrator` trio pairs at 8 commits each; `chain_core`
   pairs with each of them in only 3–4 (§2.2).
3. **The spec is one 863 KB file whose §7 is 54 % merge/CLI prose by bytes**, and 17
   `spec.split(...)` string pins in `tests/test_docs_contract.py` tie tests to its exact
   wording. It appears in 32 % of commits; the changelog in 40 %.

Top three recommendations (proposal level): (R1) script the FR-230 mint as a one-command,
evidence-preserving tool over the *unchanged* 16-subject set — narrowing is rejected; (R2)
split the spec into per-area authority files under `docs/specs/` with the current file as
index; (R3) split the shared test modules and the `MergeEngine`/`chain_core` giants along
existing seams, keeping every refusal literal byte-identical per raise site (R7 is the
*proposed* proof; its closure is open, §7 INC-11).

## 2. Measurements

### 2.1 Size and shape

Method (A1): lines = `wc -l`; functions = every `def` under `ast.walk`; cyclomatic = 1 +
`if/for/while/except/with/ifexp`, + 1 per comprehension and its `if` clauses, + (n−1) per
n-operand `BoolOp`. The guard payload is lines 15–4922 of the 4,945-line `commit-guard.sh`
(heredoc opened at line 14, closed at 4923).

| Module | Lines | Funcs | Classes | Longest function (lines @ line no.) | Max cyclomatic |
|---|---:|---:|---:|---|---:|
| `scripts/forge/forge_cli/chain_core.py` | 20,455 | 346 | 24 | `_merge_transition_valid` 1,984 @3741 | 897 (same) |
| `scripts/forge/forge_cli/engine.py` | 12,155 | 235 | 14 | `_run_fresh_reviewer_evals` 362 @9653 | 86 (same) |
| `scripts/forge/forge_cli/app.py` | 11,524 | 160 | 2 | `MergeEngine._recover_conflict_locked` 843 @9133 | 170 (same) |
| `scripts/codex_orchestrator/builders.py` | 9,948 | 164 | 0 | `_commit_transition_valid` 813 @3188 | 431 (same) |
| `scripts/codex_orchestrator/journal.py` | 9,052 | 216 | 22 | `open_run` 764 @6267 | 179 (same) |
| `scripts/forge/archive-run.py` | 5,305 | 124 | 14 | `render_archive` 407 @4035 | 74 (same) |
| `scripts/forge/commit-guard.sh` (Python payload) | 4,908 | 143 | 8 | `main` 297 @4610 | 60 (`_repo_context_resolution` @2897) |
| `scripts/codex_orchestrator/batch.py` | 4,875 | 104 | 3 | `drain_chain_batch` 255 @4487 | 60 (`_repair_receipt_gap_locked` @1406) |
| `scripts/forge/forge_cli/fresh_evals.py` | 3,259 | 89 | 13 | `validate_manifest` 275 @2758 | 120 (same) |
| `scripts/forge/fr223_eval.py` | 1,385 | 33 | 2 | `_validate_probe_evidence` 145 @891 | 74 (same) |
| `scripts/forge/forge_cli/candidate.py` | 1,326 | 42 | 8 | `_run_bounded` 97 @187 | 31 (same) |
| `scripts/forge/risk_tier.py` | 806 | 29 | 4 | `classify` 123 @633 | 46 (same) |
| `scripts/forge/forge_cli/runtime.py` | 466 | 10 | 1 | `run_bounded` 292 @137 | 81 (same) |
| `scripts/forge/forge_cli/policy.py` | 450 | 14 | 2 | `_parse_regions_with_trigger_defect` 65 @149 | 16 (`_parse_invariants` @337) |
| `scripts/forge/forge_cli/envelope.py` | 274 | 6 | 5 | `__init__` 43 @177 | 15 |

Shape facts that matter more:

- `app.py` has 12 top-level definitions; `MergeEngine` spans lines 940–11,513 (10,574
  lines, 93 methods, 57 nested defs). Its five largest methods — `_recover_conflict_locked`
  (843 @9133), `recover` (616 @10321), `_recording_common_lock` (559 @1243),
  `_run_remote_observation` (495 @6589), `cleanup_chain` (453 @10938) — are five concerns.
- Name-cluster line share (top-level defs/classes whose name contains the token; overlapping):
  `chain_core.py` `merge` 8,337, `chain` 4,649, `ingest` 2,143, `lock` 1,489, `recover` 1,160;
  `builders.py` `merge` 3,262, `commit` 1,660; `journal.py` `run` 2,209, `registry` 856,
  `owner` 724 — latent modules.
- Cyclic import graph across packages: `builders.py:2714-2716` lazily imports
  `forge_cli.candidate/fresh_evals/policy`; `runtime.py:74` imports
  `codex_orchestrator.batch/builders/journal`; `chain_core.py:616,9721` import `chain_paths`.
  `commitment_paths.py` and `chain_paths.py` are the only true leaves.
- `fcntl.flock` sites: `journal.py` 11, `chain_core.py` 4, `batch`/`builders`/`archive-run`/
  `learn-proposals-locked` 2 each; `O_EXCL` creates in 12 files.
- Distinct `forge: …` diagnostic literals (quote-aware extractor, A7): `scripts/` **485** at
  751 sites (412 Python incl. the guard payload); `skills/**` cells 26 (23 not in `scripts/`);
  `hooks/` 0; 508 distinct / 786 sites overall. Sites per file: `app.py` 167, `engine.py` 147,
  `archive-run.py` 114, `journal.py` 99. Only 73 of the 415 literals ≥ 45 characters appear
  verbatim in the spec: ~82 % are code-only contracts.

Duplicated concepts (same name or same job in more than one module):

| Concept | Definitions |
|---|---|
| merge grammar | `_merge_transition_valid` `builders.py:5505` (601 lines) / `chain_core.py:3741` (1,984) |
| merge helpers | `_merge_payload_delta` `builders.py:4792` (138) / `chain_core.py:888` (99); `_merge_current_gate_facts` `builders.py:1719` (47) / `chain_core.py:7676` (46); `_merge_required_gate_ids` `builders.py:1768` / `archive-run.py:2115` |
| primitives | `_write_all` `batch.py:213`, `chain_core.py:13830`, `fresh_evals.py:1285`; `_directory_open_flags`, `_utc_now`, `_sha256` each in `journal.py` and `fresh_evals.py` |
| git / subprocess wrappers (7) | `archive-run.run_git` @996, `risk_tier.run_git` @108, `candidate._git` @290, `candidate._run_bounded` @187, `chain_core.Repository.git` @9679, `runtime.run_bounded` @137, `drift-check.sh` |
| path containment (6) | `journal-patterns.confined_regular_file` @82, `learn-proposals.contained_existing_directory` @311, `commitment_paths.resolve_contained_path` @555 / `surface_path_is_contained` @642, `audit-commitments.confined_relative_path` @482, `journal.pathspec_contained` @1645 |

### 2.2 Churn and co-change (`git log --since=2026-08-15 --name-only 2d2faa6`)

110 commits (13 archive-only). Files per commit excluding `.forge/history/**`: median 3,
mean 6.9, p90 18, max 43.

| File | Commits | Share |
|---|---:|---:|
| `CHANGELOG.md` | 44 | 40 % |
| `docs/specs/forge-plugin-spec.md` | 35 | 32 % |
| `.forge/evals/tasks/fr230-phase3-4-v2.manifest.json` + each of 5 `tests/fixtures/fr230-results/*.json` | 22 | 20 % |
| `scripts/forge/cli.py` | 20 | 18 % |
| `scripts/codex_orchestrator/journal.py`, `tests/test_fr223_v2_byte_pins.py` | 18 each | 16 % |
| `tests/test_revision9_cli_surfaces.py` | 15 | 14 % |
| `tests/test_revision9_coordination.py` | 11 | 10 % |
| `scripts/codex_orchestrator/builders.py` | 10 | 9 % |
| `commit-guard.sh`, `test_docs_contract.py`, `forge-project.md` | 7 each | 6 % |
| `chain_core.py`, `engine.py` | 6 each | 5 % |
| `app.py` | 4 | 4 % |
| `batch.py` | 3 | 3 % |

Co-change (A10; "commits containing the whole set"):

| File set | Commits | Note |
|---|---:|---|
| spec + `CHANGELOG.md` | 23 | |
| manifest + each fixture; manifest + all five fixtures | 22 / 22 | lockstep: a six-file clique with no exception |
| manifest + five fixtures + `test_fr223_v2_byte_pins.py` | 17 | pin total 18; absent from the four digest-only "rebind" commits and creation commit `924d7c9`; once without the manifest (`20c15a7`, the one subject change shipped without a mint) |
| any of `chain_core.py` (6), `builders.py` (10), `journal.py` (18), `test_revision9_coordination.py` (11) | 24 | all four together **3** (`c164e6d`, `e7813cc`, `41da640`) |
| pairs | 8 / 8 / 8 / 4 / 3 / 3 | `builders`↔`journal`, `builders`↔coordination, `journal`↔coordination, `chain_core`↔`builders`, `chain_core`↔`journal`, `chain_core`↔coordination |
| `scripts/` commits (50) also touching the spec / the manifest | 20 / 17 | 40 % / 34 % |

`cli.py`'s 20 commits come from the
four-phase `cli split` refactor (`54527e9`, `1400915`, `3ce1a50`, `c55c312`) and the phase-3
slices — it is a 131-line forwarding shim (FR-210's sole entry point).

Since the manifest was created (`924d7c9`, 2026-09-03): 36 commits, **21 mints (58 %)**; one
subject-changing commit (`20c15a7`) shipped without a mint. Four mints (`eb30c6a`, `419598b`,
`99c85db`, `6f9b9a1`, all titled "evidence: rebind the slice-7 manifest and result fixtures…")
changed no subject — hand-mint error correction. Subjects most often inside mints: `cli.py` 7,
`chain_core.py` 6, `engine.py` 6, `test_cli_merge_lifecycle.py` 5, `commit-guard.sh` 5.

### 2.3 Spec shape (`docs/specs/forge-plugin-spec.md`, unchanged since c164e6d)

3,267 lines, 111,278 words, 862,791 bytes; 13 `##` sections, 142 `###`; 161 distinct FR ids;
185 data rows in §9 Error Contract (1892–2087); 92 `### Scenario:` headings (2088–3037); §8
typed-verb and durable-chain-fact tables (1485–1891). §7 (719–1484) has 24 `###` blocks,
388,185 bytes: FR-230..243 = 308 lines / 144,532 bytes, FR-210..224 = 118 / 63,244; the two
CLI blocks are 207,776 bytes (54 %). Revision markers: Rev-9
×42, Rev-10 ×34, Rev-13 ×30, Rev-12 ×17, Rev-11 ×12. Durable references to the spec path
outside `docs/specs`, `.forge/`, `.codex-orchestrator/` and this report: 29 files (A3). The
path is a contract; the contents need not be.

### 2.4 Test suite shape

66 modules; 1,914 `def test_` methods by grep; 1,891 test cases when *loaded* by
`unittest.TestLoader` (A10 — `load_tests` hooks and `test_*` helpers explain the gap). Largest:

| Module | Lines | Tests | Notes |
|---|---:|---:|---|
| `test_revision9_coordination.py` | 13,883 | 144 | `Revision9BuilderBatchTests` alone is lines 197–8973 (8,777 lines, 109 tests, 38 helper methods) |
| `test_cli_merge_integration.py` | 8,017 | 82 | `MergeIntegrationEpochTests` lines 44–7962 (7,919 lines); longest test 376 lines; its `load_tests` (line 8007) keeps only index residue 0 (28 tests) under this module name and hands residues 1–2 (27 each) to `test_cli_merge_integration_shard{1,2}.py` |
| `test_cli_merge_lifecycle.py` | 5,412 | 115 | 9 classes; 10 `sys.executable` subprocess sites |
| `test_revision8_coordination.py` | 5,253 | 81 | one class, 31 helper methods |
| `test_revision9_cli_surfaces.py` | 5,114 | 80 | `Revision9BoundCLIIntegrationTests` 3,849 lines |
| `test_commit_guard.py` | 3,039 | 84 | `setUp` (line 53) runs `git init` (103) and `copytree`s `scripts/forge` into mutant roots (155, 164–165) |
| `test_docs_contract.py` | 1,705 | 39 | 130 `assertIn`, 618 string literals ≥ 20 chars, 17 `spec.split(` pins, 6 `*_survives_mutation` tests |

What makes it slow (a sample of seven, not the full suite; one module at a time on this
12-CPU host, A4):

| Module | Tests | Wall | Why |
|---|---:|---:|---|
| `test_version` | 1 | 0.1 s | in-process |
| `test_cli_policy_fences` | 32 | 0.2 s | in-process parser |
| `test_docs_contract` | 39 | 0.6 s | reads files, no subprocess |
| `test_fr230_phase3_manifest` | 12 | 24.5 s | `live_result_test_passes` (line 465) re-runs subject tests as `python -m unittest <id>` subprocesses, once per PASS slot |
| `test_commit_guard` | 84 | 65.3 s | fresh git repo + `copytree` per test; each case execs the 4.9k-line guard as a child |
| `test_cli_merge_lifecycle` | 115 | 100.4 s | 10 `sys.executable` launch sites; full CLI child per lifecycle step |
| `test_revision9_coordination` | 144 | 15.2 s | the largest *file* is cheap: in-process builders/batch calls |

Within this sample of seven, file size does not drive runtime: the 13.9k-line module costs
~0.1 s/test, the subprocess-heavy modules 0.8–0.9 s/test. The other 59 modules were not
timed; the ten child-spawning modules A4 lists are *candidates* for the full pass's cost by
`subprocess.` density, not a measured share. Counted drivers: 33
modules run `git init`; `subprocess.` appears 42× in `test_governance_scripts`, 32× in
`test_commit_guard`, 28× in `test_candidate_identity`; 3 modules use `setUpClass` versus 33
with per-test `setUp`.

The gate-1 cell in `forge-project.md` (line 121) shards with `min(4, cpu)` and assigns modules
round-robin by *index* — as FR-149's Revision-13 amendment (spec line 872) prescribes. Replayed
at this HEAD on 12 CPUs (A10; revision 3's 516/559/445/394 was a wrong partition and is
superseded):

| Shard | Modules | Loaded tests | Heavy modules drawn |
|---|---:|---:|---|
| 1 | 17 | 516 | `test_cli_merge_lifecycle` (115) |
| 2 | 17 | 482 | `test_cli_merge_integration` (residue 0, 28), `test_governance_scripts`, `test_learn_proposals`, `test_worktree_merge_skill` |
| 3 | 16 | 472 | `test_commit_guard`, `test_fr230_phase3_manifest`, `test_revision9_coordination`, `test_candidate_identity`, `test_cli_merge_integration_shard1` |
| 4 | 16 | 421 | `test_cli_merge_integration_shard2`, `test_revision8_coordination`, `test_migration`, `test_fr223_v2_byte_pins` |

1,891 loaded tests — balanced by count, not by cost.

### 2.5 Pinning blast radius

Three layers pin the same surfaces:

1. **Byte pins.** `test_fr223_v2_byte_pins.py:38` sha256-checks 7 artifacts including the
   manifest; `test_fr230_phase3_manifest.py:221` hashes all 16 subjects (`subjects.production`
   ×11: `cli.py`, `commit-guard.sh`, 9 `forge_cli/*.py`; `subjects.tests` ×5) into one
   `subject_candidate_sha256` that every PASS fixture must carry. Radius of one whitespace change
   in `forge_cli/__init__.py`: 7 files re-minted, 1 changelog line, a binding review (both
   fixture locations are control-class).
2. **Literal pins.** `test_docs_contract.py:1027` (`test_run_open_refusal_source_literal_inventory`)
   asserts *occurrence counts* of literals in `journal.py` (1050:
   `literals.count(shared_refusal) == 9`); `assert_guard_denylist_spec_contract` (352) slices
   the spec at `- **FR-095**` and requires 17 phrases verbatim. The FR-220/221 corpora under
   `system/fr223/` (v1–v3, immutable by DM-016) pin denial strings and argv shapes.
3. **Spec prose.** §9's 185 rows and 92 scenarios restate a subset (~18 %) of the 485 code
   diagnostics.

No script performs the mint (`grep -rl fr230 scripts skills hooks system` is empty): the
manifest and fixtures are hand-edited — the four "rebind" commits are the evidence.

## 3. Diagnosis

### 3.1 What the structure does well

| Strength | Evidence | Consequence for this report |
|---|---|---|
| Fail-closed is real and testable: every gate is a refusal-first path with an exact literal; "disable the control in memory and confirm the test fails" is practised | `*_survives_mutation` in `test_docs_contract.py`; `mutant_guard` roots in `test_commit_guard.py:153` | nothing below weakens it |
| Evidence-bound: candidate identity binds tree/parent/message; manifests chain by `previous_manifest_sha256`; results carry the subject digest *and* are re-executed live | `resolve_live_result`, `test_fr230_phase3_manifest.py:496-546` | the pinning is right; only its *operation* (hand-minting) is wrong |
| The split already started: `cli split` phases created `forge_cli/` and one test loader so "later split phases retarget the import mechanics in one place" | bead forge-plugin-95e; `tests/_cli_loader.py` (`load_cli`, `package_module`) | R3–R4 continue that work |

### 3.2 By constitution lens (applied to the architecture, not a diff)

| Lens | Finding | Evidence |
|---|---|---|
| AMB-01 (term defined once) | "Merge transition validity" is defined twice with different signatures: `(event, prior, current, context)` in `builders.py:5505` and `(builders, event, prior, current, *, context, history)` in `chain_core.py:3741`. A reader cannot know which is authority without reading both. | §2.1 |
| AMB-08 (control vs data plane) | `MergeEngine` mixes lock acquisition (`_recording_common_lock`), remote observation, bootstrap, epoch execution, recovery and cleanup in one class. | `app.py:940-11513` |
| INC-03 (state machine complete) | The merge state machine is complete but only in code: cyclomatic 897 in one function is un-reviewable as a transition table, though §8/DM-014 describe it as one. | `chain_core.py:3741` |
| INC-11 (tooling layer in inventory) | The re-mint is a required step of every subject change but has no tool, no skill step, and no spec row naming the procedure. | §2.5 |
| CON-01/CON-08 | Three `_write_all`, two `_utc_now`, two `_sha256`, seven git wrappers, six containment helpers — same concept, different names and edge behaviour. | §2.1 |
| CON-02 (bidirectional traceability) | 485 diagnostics vs 73 spec-verbatim prefixes: the spec cannot be the authority for literals it does not contain, yet the review triggers treat it as such. | §2.1 |
| FEA-03 (reproducible tests) | 33 modules build real git repos; `test_fr230_phase3_manifest` spawns nested unittest processes; host-dependent failures were observed on 2026-09-11 (memory obs 9597). | §2.4 |
| COR-08 (module boundaries) | Package cycle `forge_cli` ↔ `codex_orchestrator`; `builders.py` reaches into `forge_cli.candidate/fresh_evals/policy` lazily to dodge the import cycle. | `builders.py:2714` |
| CPX-03 (layers justified) | Validation is stacked four deep for one write: `chain_core` grammar → `builders` grammar → `journal` record validation → `batch` intent/receipt. Each layer re-derives digests (`sha256(` sites: batch 48, fresh_evals 28, builders 23, journal 19). | §2.1 |
| CPX-06 (test infra ≤ code) | `Revision9BuilderBatchTests` carries 38 helper methods and 8.8k lines; `test_fr230_phase3_manifest` re-implements bounded process-group execution (lines 278–464) that `runtime.run_bounded` already provides. | §2.4–2.5 |
| SEC / OPS | No architectural finding. Bounded reads, process groups and exact diagnostics are consistently present. The duplication is a maintenance cost, not a hole. | — |

### 3.3 By ponytail principle

| Principle | Application here |
|---|---|
| Rung 1, YAGNI — "does this need to exist?" | The *hand mint* does not: four of 21 mints existed only to correct earlier hand mints. The 16-file subject set does — R1 shows the five PASS slots are merge-engine tests, so the merge modules are exactly the subjects the evidence is about |
| Rung 2, reuse what is here | `runtime.run_bounded` should be the one git/subprocess wrapper; the tests' `bounded_process_output` and six other wrappers are re-implementations; `commitment_paths` already owns containment; the mint tool should call the validator's own `subject_candidate`, `result_evidence`, `live_result_test_passes` |
| "Deletion over addition; fewest files" | Splitting files *adds* files; the justification is measured contention (§2.2), not taste. Where a split does not reduce co-change it is not recommended (`batch.py` stays) |
| "Bug fix = root cause, grep every caller" | The four "rebind" commits are symptom patches; the root cause is a 16-file digest recomputed by hand |
| "Mark deliberate ceilings with a `ponytail:` comment" | Adopt the convention (the repo already uses `# forge: modified from upstream —` markers, 17 in `journal.py`) |
| Not lazy about trust-boundary validation and error handling | Every refusal literal and gate ordering below is a "must not change" |

## 4. Recommendations (ranked, proposal level)

Every recommendation below is a proposal, not a design. Each requires its own design, a spec
amendment where it touches `docs/specs/**` authority (R2, R6.1, any DM-016 subject-inventory
change), and a DVRR review of that design before any implementation candidate is opened; the
steps and tables sketch *what* would change and *why*, not *how*. Where the commit-chain
review of this document objected to a sketch's depth, the objection is quoted unresolved in
§7 "Open review findings" and the affected sentence is marked *proposed*.

Each item: change · principle · effect · risk to fail-closed behaviour · size · must-not-change.

### R1 — Script the FR-230 mint as an evidence-preserving tool; keep the 16 subjects (S)

**What the manifest proves.** For each of the five generation-1 PASS slots the validator
requires a fixture bound to the digest of all 16 subjects *as in the tree under test*, naming
the exact slot test, byte-identical to `result_evidence()`, and re-executes that test live:

| Check | `tests/test_fr230_phase3_manifest.py` |
|---|---|
| preimage over all 16 subjects | `subject_candidate` 221–246 |
| fixture digest == current candidate | `validate_manifest` 552; slot loop 732–806; candidate compare 788 |
| command == the slot's exact test id | `PHASE3_RESULT_TESTS` 92–113, `PHASE4_RESULT_TESTS` 121–134; compare 795–805 |
| fixture bytes == `result_evidence()` | 249; `resolve_live_result` 496–546 |
| live re-run of the test | `live_result_test_passes` 465 |
| generation 2 may not change subjects / prior PASS rows | 728; 813–824 |

| PASS slot | Subject test (class, line) | Behaviour proved | Production subjects exercised |
|---|---|---|---|
| `merge-transition` | `test_cli_merge_lifecycle.MergeLifecycleStartTests` (838) | ownership + generation published before success | `app.py`, `chain_core.py`, `engine.py`, `runtime.py`, `cli.py` |
| `cleanup` | `test_cli_merge_integration.MergeIntegrationEpochTests` (866) | full epoch push + non-force cleanup | same, incl. `MergeEngine.cleanup_chain` |
| `recovery` | same class (1210) | recovery resumes the single fetch intent | same, incl. `recover`/`_recover_conflict_locked` |
| `re-verification-matrix` | same class (5220) | remote-only successor carried then pushed in a new epoch | same |
| `merge-last-line` | same class (6632) | each bounded epoch control is load-bearing | same |

`chain_core.py`, `app.py`, `engine.py` and the two merge test modules are therefore the code
the five PASS slots certify. **Narrowing the subject set is rejected.** Removing them would
(i) leave every PASS slot's evidence acceptable after a merge-engine change — the digest at
line 788 would no longer move, leaving only the live re-run at 465; (ii) be forbidden at
generation 2 (line 728); (iii) be a DM-016/FR-241 subject-binding change (spec 653, 1460)
needing STRICT evals, binding review and operator approval. The binding *is* the control.

**Change.** Add `scripts/forge/fr230-mint.py` (stdlib, control-class):

| Step | Behaviour | Why |
|---|---|---|
| 1 | reuse one definition of `subject_candidate`, `result_evidence`, `live_result_test_passes`, `PHASE3_RESULT_TESTS`/`PHASE3_RESULT_IDS` — *proposed* as an import from the test module; where that definition should live is open (§7 COR-08) | rung 2 — one definition of the preimage and the fixture bytes |
| 2 | recompute the candidate; if it equals the committed fixtures' digest, exit 0 "no mint needed", write nothing | idempotent |
| 3 | print the *per-subject* digest delta against the subjects' bytes at the last manifest-touching commit (`git log -1 --format=%H -- <manifest>`, `git show <sha>:<path>`) | the reviewer sees which of the 16 files caused the mint |
| 4 | re-run **all five** PASS slot tests through `live_result_test_passes`; any failure → exit 1, nothing written | never carries a PASS forward — a fixture claiming a run that did not happen against this candidate is the fiction spec line 1928 refuses |
| 2b | refuse (exit 1, nothing written) when a production file exists but is absent from `subjects.production`, naming the path — *proposed*; the scan sketched here (`scripts/forge/forge_cli/*.py`, `scripts/forge/commit_guard.py`) is not a closed inventory of every subject R4/R5 propose (§7 COR-05) | intended to close the silent-narrowing path of R4/R5 (see R4 risk); the validator itself does not check this (test lines 641–678 accept any sorted unique `scripts/` list) |
| 5 | rewrite the five fixtures byte-identically to `result_evidence()`; patch only the five `result_sha256` values in the generation-1 manifest (generation stays 1, `previous_manifest_sha256` stays `null`, `pending-phase-4` rows untouched); refuse if the committed manifest's `generation` ≠ 1 | generation 2 is reserved for phase 4 (lines 728, 813–824), not for re-mints |
| 6 | **recompute the sha256 of the rewritten manifest bytes and rewrite the pin at `tests/test_fr223_v2_byte_pins.py:25–27`** (key `.forge/evals/tasks/fr230-phase3-4-v2.manifest.json`, the only manifest-derived digest that test holds — its other six pins are fr223 corpora untouched by a mint, and the five fixtures are pinned only through the manifest's `result_sha256`). Steps 5 and 6 are *proposed* as one transaction — all bytes computed in memory before any write; the crash-safety of the multi-file write is an open design item (§7 FEA-05) | `test_all_seven_artifacts_match_the_generation_contract` (line 38) hashes the generation-1 manifest bytes against that pin (line 54); a mint that skips this step fails that test in gate 1 (`tests.test_fr223_v2_byte_pins`, shard 4 at this HEAD) and the chain refuses the candidate — the exact error the four hand-mint "rebind" commits corrected |
| 7 | print the eight paths to stage: manifest, 5 fixtures, `tests/test_fr223_v2_byte_pins.py`, `CHANGELOG.md` | explicit-path staging |
| 8 | focused tests: (a) patch `live_result_test_passes` → `False`, assert nothing written and exit 1; (b) patch the step-6 pin rewrite to a no-op, assert the tool refuses before writing the manifest; one-line step in `skills/commit/SKILL.md`: "if a subject changed, run `fr230-mint.py` before `verify`" | disable-in-memory proofs; INC-11 |

**Principle.** Ponytail rung 1 (delete the hand procedure) and rung 2; INC-11; CPX-06.
**Effect.** Mint frequency does not fall (subject churn is real: 21/36); mint *cost* falls
from hand-editing seven hex digests to one command plus a machine diff; the four digest-only
correction commits (11 % of post-creation commits) need not recur.
**Risk.** Low, not zero. The tool adds no acceptance path: the unchanged validator still
re-derives the candidate and re-runs every slot, and the byte-pin test still hashes the
manifest, so wrong tool output is refused at gate 1. Residual: a fixture written for a test
not run — addressed by step 4 and the step-8 mutation tests. Open in §7: import direction
(COR-08), step-2b inventory closure (COR-05), multi-file write (FEA-05). Control-class:
focused tests, full discovery, binding review.
**Must not change.** The 16-subject set, `subject_candidate` preimage, `pending-phase-4`
rule, eight-slot inventory, corpora immutability, the fictional-PASS refusal rows (spec
1927–1928), `validate_manifest` itself.

### R2 — Split the spec into per-area authority files with the current file as index (M)

**Change.** Keep `docs/specs/forge-plugin-spec.md` at its path (29 durable references) holding
§§1–6, §§11–14 and an index; move each §7 FR block with *its* §8 tables, §9 rows and scenarios
into `docs/specs/areas/<block>.md` (24 blocks; start with the two that are 54 % of §7:
`fr-210-224-commit-chain.md`, `fr-230-243-merge-push.md`). Add one conformance test
(`tests/test_repo_conformance.py` already owns routing/inventory checks) with three
assertions — a check, not a build step:

| Assertion | Recognition rule | Measured at HEAD (single file) |
|---|---|---|
| the index lists every `areas/*.md` file and nothing else | directory listing vs index table | — |
| every FR id has exactly one **normative definition marker** across the set | a line matching `^- \*\*FR-\d{3}\*\* \((MUST\|SHOULD\|MAY)\)` | 161 markers for 161 distinct ids, all in §7 (lines 723–1474); zero ids defined twice or never |
| every amendment/clarification line names an id defined in the *same* area file | **not yet specified** — the recognizer must cover every normative amendment form found at HEAD (A8 list, below) before any split; a `Revision-`-prefixed regex alone matches 39 of the 56 amendment lines | 56 `amendment to **FR-` lines (31 ids, lines 735–1464); 6 `clarification to **FR-` lines |

Amendment and clarification forms measured at HEAD (A8). The recognizer must cover every one
of them before authority files are split (§7 INC-12); revision 3's 54/30/7 counts were wrong.

| Form | Lines | Shape |
|---|---:|---|
| `Revision-N [<qualifier>] amendment to **FR-nnn**` | 39 | single ids, id lists (`**FR-a**, **FR-b**, and **FR-c**`), ranges (`**FR-a..FR-b**`) |
| `Candidate-bound fresh reviewer evaluation [<qualifier>] amendment to **FR-nnn**` | 17 | no revision prefix; includes the multi-id `operator-skip amendment` (1090) |
| `… clarification to **FR-nnn**` | 6 | `Revision-N …` ×3 (1181, 1317, 1419); `Candidate-bound … temporal` (1183); `Candidate-tree execution` (916); `Fresh-reviewer output-cap` (973) |
| inline amendment inside a definition marker, ids unbolded | 1 | FR-235: "substantive amendment to FR-062/FR-063" (1319) |
| `- Revision-11 standing clarifications:` (revision history, not FR-targeted) | 1 | 3087 |


References stay unconstrained: the 161 ids occur 1,327 times (`FR-236` ×47, `FR-019` ×43;
`FR-230` ×15 = one definition at 1179, one clarification at 1181, thirteen references).
"Appears exactly once" fails at HEAD before any split; "defined exactly once" passes at HEAD
and fails when a split duplicates or drops a definition.
**Principle.** CON-02 traceability; ponytail rung 2 (the `docs/specs/**` trigger already
covers the directory — no new gate).
**Effect.** A task touching FR-235 locking no longer conflicts with one touching FR-095; a
reviewer loads ~50 KB instead of 863 KB; spec appearance in commits should fall from 32 %.
**Risk.** Low for semantics, medium for pins: the 17 `spec.split(` sites in
`test_docs_contract.py` (e.g. line 353 `spec.split("- **FR-095**")`) and the `policy.py`/
`fr223_eval.py`/`audit-commitments.py` path references must be re-pointed in the same
candidate. The file is not one concern — its own §14 lists 27 decomposition tasks by FR
range. Any single-file rendering goes to `.forge/tmp`, never to the tree.
**Must not change.** The path `docs/specs/forge-plugin-spec.md` as the entry authority; RFC-2119
wording; FR numbering; the §9 literal text.

### R3 — Split the shared test modules along their existing class seams (S)

**Change.**

| Module | Split along | Shared helpers go to |
|---|---|---|
| `test_revision9_coordination.py` | its four classes (`Revision9FixtureTests` @63, `Revision9BuilderBatchTests` @197, `Revision9BindingTests` @8976, `Revision9MergeTransitionGrammarTests` @11103), then `Revision9BuilderBatchTests` by typed verb (run-open/readmit, task, execution, verification/decision, ingest, close — the §8 table is the map) | `tests/_revision9_support.py` (38 helper methods, `JOURNAL_FIXTURE_SHA256` line 36) |
| `test_docs_contract.py` | `test_skill_contracts.py` (`documentation_paths()` scans, line 27), `test_spec_contracts.py` (`assert_*_spec_contract` family, 352/387/494), `test_guard_denylist_contract.py`, `test_journal_literal_inventory.py` | — |
| `test_cli_merge_integration.py` | by epoch scenario, **except the six pinned tests**: `MergeIntegrationEpochTests` (line 44) stays in this file under its name holding `test_full_epoch_push_and_nonforce_cleanup` (866), `test_recovery_resumes_the_single_fetch_intent` (1210), `test_remote_only_successor_is_carried_then_pushed_in_a_new_epoch` (5220), `test_each_bounded_epoch_control_is_load_bearing` (6632) and the two reserved phase-4 ids `test_transient_known_push_failure_retries_after_fresh_old_tip` (2087), `test_invalid_final_mode_control_is_load_bearing_at_push_boundary` (4259); the other 76 of its 82 tests move to `test_cli_merge_epoch_{push,recovery,matrix,controls}.py` | existing `MergeAdapterFixture` |

**Pinned test ids.** Eight dotted `module.Class.method` ids are contract — the filename alone
is insufficient — so the split moves the *unpinned* 76 and never renames the six.

| Fact | Where |
|---|---|
| 5 phase-3 + 3 phase-4 ids | `PHASE3_RESULT_TESTS` `test_fr230_phase3_manifest.py:92–113`, `PHASE4_RESULT_TESTS` 121–134 |
| compared verbatim to each fixture's `command` (`["python3","-m","unittest",<id>]`), re-run live by id | 795–805; 465; all five `tests/fixtures/fr230-results/*.json` |
| homes | 6 in `MergeIntegrationEpochTests`; 1 in `test_cli_merge_lifecycle.MergeLifecycleStartTests` (838; class 1 of 9, line 190); 1 in `test_fr223_v2_hook.V2HookExecutionTests` (385) |
| authorized rename path (not recommended) | generation-1 re-mint of all five fixtures with new `command` arrays + edit of `PHASE3/4_RESULT_TESTS` (control-class `tests/fixtures/**`, binding review); must land before generation 2, which may not change a prior PASS binding (813–820) — afterwards a new lineage (spec 1462). The spec names none of the ids (grep: 0): no spec amendment |
**Principle.** Ponytail rung 2; CPX-06; constitution axiom 4 (per-verb files trace to §8 rows).
**Effect.** Disjoint ownership: a journal-verb task owns one ~1.5k-line file and its review
reads that file, not 13.9k lines — a review-surface win, not a runtime win (§2.4).
**Risk.** Zero to production semantics. `subjects.tests` names `test_cli_merge_lifecycle.py`
and `test_cli_merge_integration.py`; the validator freezes that list at generation 2 (line
728), so both paths stay, and moving the 76 unpinned tests changes their bytes → one scripted
mint (R1). Whether the sibling modules must *also* become subjects is **open** (§7 CON-06);
so is the module's `load_tests` residue partition (§2.4), which a split changes.
**Must not change.** The eight pinned dotted ids, assertion text, fixture `command` arrays,
the `*_survives_mutation` tests, the `literals.count(...)` pins (R7 is additive).

### R4 — Module boundaries for `chain_core` / `engine` / `app` / `builders` / `journal` (L, in slices)

**Change.** Continue the `cli split` phases:

| Slice | Move | Seam evidence |
|---|---|---|
| 1 | `app.py`: `MergeEngine` → `forge_cli/merge/{admission,lock,bootstrap,epoch,observation,recovery,cleanup}.py`; `app.py` keeps `dispatch` (273), `main` (424), deferred-mutation helpers (83–270) | `prepare_merge_admission` @543, `_recording_common_lock` @1243, `_run_bootstrap_generation_composite` @2500, `_run_epoch_suite` @6126, `_run_remote_observation` @6589, `recover` @10321 / `_recover_conflict_locked` @9133, `cleanup_chain` @10938 |
| 2 | `chain_core.py` → `merge_grammar.py` (the 8,337-line `merge` cluster incl. `_merge_transition_valid`), `locks.py`, `ingest.py`, `recovery.py`; chain state/records stay | `_verify_and_build_merge_ingest_records` @7928, `_verify_and_build_ingest_records` @8518 |
| 3 | one owner for the merge grammar: `builders._merge_transition_valid` (Revision-9 base) and `chain_core._merge_transition_valid` (Revision-10 strict composition) become one leaf module with two named layers imported by both packages; delete the duplicated `_merge_payload_delta` / `_merge_current_gate_facts` | §2.1 duplicates table |
| 4 | `journal.py` kept as a façade (FR-003, spec line 725, pins the vendored path); `run*` (2,209 lines, `open_run`), `registry*`, `owner*` → `codex_orchestrator/journal_{runs,registry,owner}.py` with `# forge: modified from upstream —` markers | §2.1 clusters |
| 5 | leaf `scripts/forge/forge_common.py` for `_write_all`, `_utc_now`, `_sha256`, `_directory_open_flags`, bounded reads; containment points at `commitment_paths`; `builders.py:2714` lazy imports become top-level | breaks the package cycle |

**DM-016 subject inventory is part of every slice.** The inventory is the manifest's
`subjects.production` array (11 paths); the spec fixes its grammar (line 653) and requires for
"every changed or added production subject" a current `strict-evals` binding (line 117); the
validator accepts any such list (test 641–678) and freezes it only at generation 2 (726–728).
Each slice that creates a control module adds its path *in the same candidate*:

| Slice | Subject additions | What `subject_candidate_sha256` covers during the move |
|---|---|---|
| 1 | `forge_cli/merge/{admission,lock,bootstrap,epoch,observation,recovery,cleanup}.py` | the move changes `app.py` bytes → one mint; without the addition, every later edit to a `merge/*.py` file leaves the digest — and all five PASS fixtures — unchanged: the evidence silently narrows to the shrunken `app.py` |
| 2 | `forge_cli/{merge_grammar,locks,ingest,recovery}.py` | same mechanism via `chain_core.py` |
| 3 | the single grammar leaf module | same; `builders.py` is not a subject today (Q1) |
| 4 | none — `codex_orchestrator/*` is outside the inventory today | nothing currently covered narrows; Q1 asks whether it should widen |
| 5 | `scripts/forge/forge_common.py` | it will hold `_write_all`/`_sha256` used by subjects; a bug there changes no subject byte unless it is one |

Each addition = generation-1 manifest edit (control-class `.forge/evals/tasks/**`) +
spec-117 strict-evals binding + re-mint of all five fixtures (the preimage gains a path) +
R1 step 6 pin rewrite: one R1 run per slice under binding review. R1 step 2b is *proposed* to
turn an omitted addition into a refusal; as sketched its scan does not cover `forge_common.py`
or later guard submodules, so the inventory it checks is not yet closed (§7 COR-05).

**Principle.** COR-08, CPX-03, ponytail rung 2 — each slice is a *move*, not a rewrite.
**Effect.** Lock, recovery and grammar tasks can run in three worktrees; the review surface
per change is one 1–3k-line module instead of a 20k one.
**Risk.** Medium: moved controls are patched in tests by canonical name (`package_module`),
so every `mock.patch.object(CHAIN_CORE, ...)` must retarget — `_cli_loader.py`'s docstring
anticipates this. Each slice moves subject bytes and adds subjects → one R1 mint per slice.
The `reviewer-routing` and `model-provider-version` eval triggers name `forge_cli/engine.py`
(spec 278/280, `forge-project.md`) — update them in the same candidate.
**Must not change.** Any `"forge: …"` literal or its raise-site multiplicity (R7 is the
proposed check), lock ordering, event names, the `next required step:` output contract
(FR-220, spec line 1110).

### R5 — Lift the guard's Python out of the shell heredoc (S)

**Change.** Move lines 15–4922 of `commit-guard.sh` to `scripts/forge/commit_guard.py`
(non-executable); the wrapper keeps its 13-line head and 22-line tail (4924–4945) and passes
the file instead of fd 3, retaining the bootstrap-failure literal and exit 2. The same candidate adds `commit_guard.py` to `subjects.production` beside
`commit-guard.sh` (still a subject as the pinned hook path): otherwise the PASS fixtures'
digest would track a 35-line wrapper and lose 4,908 lines of guard control — R4's narrowing,
closed the same way (manifest edit, spec-117 binding, one R1 run with the step-6 pin rewrite,
and the step-2b refusal once its inventory covers guard submodules — §7 COR-05). Then split
the payload by its prefix clusters (`shell*/case*/executable*` lexer; `guard_denied*`;
`resolve_*`/`_repo_context_*`; `main`), each new module a subject addition.
**Principle.** Ponytail rung 3 (the heredoc, `read -d ''`, fd-3 plumbing and `compile(source,
"<forge-commit-guard>")` at line 4934 are hand-rolled module loading); CPX-07.
**Effect.** AST tooling, coverage, the gate-1 assertion sensor and mutation fallback can see
the guard; `test_commit_guard.py:196`'s `source.split("<<'PY' || true\n")` extraction goes
away; per-test `copytree` of `scripts/forge` (line 155) can copy two files.
**Risk.** The hook path `scripts/forge/commit-guard.sh` is pinned by `hooks/hooks.json:9`, the
fr223 corpora and FR-090/FR-095 — it stays. Neither the spec (no "heredoc"/"python_code";
"self-contained" at 1110 concerns diagnostics) nor `skills/commit/SKILL.md` records a reason
for embedding (Q3). Two-file loading adds one failure mode (payload missing) that must map to
the existing bootstrap refusal — a one-line test.
**Must not change.** Denial literals, reason codes, argv classification, `umask 077` (line 9),
exit codes, `FORGE_COMMIT_GUARD_SCRIPT_DIR` handoff (line 4930).

### R6 — Test-suite speed without new infrastructure (S–M)

**6.1 Shards are spec-fixed, not policy-fixed.** FR-149's Revision-13 sharded-cell amendment
(spec line 872) normatively states that this repository's `gate1-test-command` partitions
modules "round-robin over `min(4, cpu)` shards". Both the constant and the assignment rule are
specification authority: raising the count to `min(8, cpu)` *or* cost-balanced assignment is
a `docs/specs/**` amendment (STRICT evals + binding review + explicit operator approval) *and
then* a `forge-project.md` cell change (policy/parser contract tests + binding review).
Nothing here may be a policy-only edit; renaming modules to game the index assignment is not
proposed. Within the spec as written the only levers are 6.2–6.4.

| Item | Change | Constraint |
|---|---|---|
| 6.2 stop testing tests in tests | `test_fr230_phase3_manifest`'s live re-run of five subject tests (24.5 s) is FR-241's own currency proof; R1 keeps it. If FR-241 may be amended (Q4), run the five in one `unittest` child instead of five | FR-241 amendment = spec change |
| 6.3 shared repos | `test_commit_guard` (65 s / 84 tests) builds a git repo and copies `scripts/forge` per test; a `setUpClass` base repo plus per-test `git worktree add` or `copytree` of only the guard file cuts most of it | mutant roots stay per-test |
| 6.4 one bounded runner | replace the test-local `bounded_process_output` and the seven production wrappers with `runtime.run_bounded` | rung 2; timeouts/caps unchanged |

**Principle.** CPX-10: optimise measured bottlenecks — the subprocess-per-test modules.
**Risk.** None to gates for 6.2–6.4; 6.1 is a control change that keeps the cell's
fail-closed rules (empty module set, missing summary, non-zero exit, 1200 s bound) verbatim.

### R7 — Diagnostic inventory with per-literal, per-site multiplicity (S)

**Change.** A generated-and-checked table `tests/fixtures/diagnostics-inventory.tsv`
(control-class), one row per distinct `"forge: …"` literal:
`<literal>\t<total count>\t<sorted occurrence list>`, each occurrence
`<file>:<qualified enclosing def>` with `×n` for repeats. Produced by a **quote-aware
extractor** (A7), not a grep — the c164e6d double-quote grep cannot see a single-quoted shell
literal and missed five sites. A7 is an uncommitted scratch script; its closure is *claimed,
not proved* (§7 INC-11):

| Extractor rule | Covers | Evidence at HEAD |
|---|---|---|
| Python `ast` over every `.py` and the guard payload (lines 15–4922 parsed as a module): `Constant` str; `JoinedStr` rendered with `{<expr>}` placeholders; a `BinOp(+)` chain headed by a `forge:` literal rendered as one row; `.format`/`%` receivers are `Constant` nodes and need no special case | double- and single-quoted, implicit adjacent-literal concatenation across lines (`ast` folds it: 32 `forge:` constants span more than one source line), f-strings (159 sites), trailing `\n` | 412 distinct Python literals; 0 `+`-concatenated, 0 `.format`, 0 `%` at HEAD — the rules exist for the planted set, not for current code |
| shell tokenizer over `.sh`, `#!` scripts and the `bash`/`sh` fences of `skills/**/*.md`: single quotes (no escapes), double quotes (backslash escapes; `$(…)` kept opaque), backslash-newline continuation, adjacent segments joined into one word; a word whose text starts with `forge: ` is a row, so `printf '%s\n' 'forge: …'`, `printf 'forge: %s\n'`, `echo "forge: …"` and `"forge: "$var" …"` need no per-command rules | both quote styles, continuation lines, concatenated words | 81 shell sites in `scripts/` (75 double-quoted, 6 single-quoted); 35 sites in `skills/**` cells; 0 in `hooks/` |
| previously missed | `scripts/forge/configure-dcg.sh:13,18,27,33,35` (4 distinct literals: `forge: dcg not found — no project allowlist change`, `forge: dcg allowlist update failed` ×2, `forge: dcg allowlist already contains core.git:branch-force-delete for this project`, `forge: dcg allowlisted core.git:branch-force-delete for this project`; 27 and 33 follow a `printf '%s\n' \` continuation) and `check-halt.sh:345` (single-quoted, also on a continuation line; visible to the grep only because its double-quoted twin sits at line 230) | — |

Totals: `scripts/` 751 sites / 485 distinct (vs 418); with `skills/**` 786 / 508. Example row
at HEAD for the literal pinned at `test_docs_contract.py:1050`:

| literal | count | occurrences |
|---|---:|---|
| `forge: journal append refused — activated writer requires typed builder` | 9 | `journal.py:_append_owned_record_reserved`, `journal.py:_append_run_record_reserved`, `journal.py:_prevalidate_legacy_lifecycle×2`, `journal.py:_prevalidate_raw_append`, `journal.py:close_run`, `journal.py:readmit_run×2`, `journal.py:retire_run` |

A conformance test regenerates the table in memory and asserts byte-equality with the
committed file. Deleting one of the nine guarded sites changes the count *and* the occurrence
list, so the check fails where set membership would not. The `literals.count(...) == 9` pins
stay; the table is additive.
**Closure as a checked property (proposed).** R7 is intended as the preservation proof for
R4/R5, so the proposal tests the extractor against a planted set
`tests/fixtures/diagnostics-planted/{planted.py,planted.sh,planted.md}` with a hand-written
expected TSV. §7 INC-11 objects that planted *known* forms cannot prove closure and that the
function-level key misses a delete-and-replace within one function; both are open.

| Planted form | Test |
|---|---|
| shell: single-quoted; double-quoted; `printf '%s\n' \` + literal on the continuation line; `printf 'forge: %s\n'`; `echo 'forge: …'`; `"forge: "$var" suffix"` word concatenation; a `bash` fence in `planted.md` | extractor output over the planted set == expected rows, exactly |
| Python: single- and double-quoted; `'forge: ' + tail`; f-string; `.format`; `%`; implicit multi-line adjacent literals; the same forms inside a heredoc-embedded `<<'PY'` payload | same |
| disable-in-memory | patch out the single-quote branch, then the continuation rule, then the `+`-chain rule; assert the planted test fails each time |
**How a legitimate change updates it.** The candidate regenerates and stages the file; the
reviewer reads the diff. A *move* (R4/R5) changes only an occurrence's `<file>:` prefix and
leaves `count` unchanged — each slice's literal-preservation evidence. A count change or new
literal is a control-class refusal-surface edit reviewed against FR-220/§9. Line numbers are excluded from the key.
**Principle.** AMB-01 / CON-05 (one definition), CPX-10.
**Effect.** R4's moves gain a literal- and site-preservation check (a proof only if INC-11
is resolved); new refusals are reviewed as a one-row diff. **Risk.** None; additive to the count
pins and mutation-style tests.

## 5. Suggested sequencing (small, independently reviewable, DVRR-compatible)

| Step | Candidate | Class | Gate path | Unblocks |
|---|---|---|---|---|
| 0 | R7 committed extractor + planted set + inventory + conformance test (closure open, §7 INC-11) | `tests/fixtures/**` control + `tests/**` | binding review | R4, R5 literal/site-preservation check |
| 1 | R1 `fr230-mint.py` (steps 1–8, incl. the byte-pin rewrite and the subject-inventory refusal) + focused mutation tests + skill note in `skills/commit/SKILL.md` | `scripts/forge/**`, `skills/**` control | focused tests + full discovery + binding review | ends hand mints immediately |
| 2 | R3 test-module splits (one module per candidate; 4–6 candidates; the two merge-module candidates keep the eight pinned ids and mint via R1) | `tests/**` (+ mint files) | standard / binding where fixtures move | R4 |
| 3 | R5 guard payload lift + `commit_guard.py` subject addition + mint | `scripts/forge/**`, `hooks`, `.forge/evals/tasks/**` | affected focused tests + full discovery, binding review, strict-evals binding (spec 117) | R5 sub-splits |
| 4 | R6.1 FR-149 amendment (shard count and/or assignment rule), then the matching `forge-project.md` cell edit | `docs/specs/**` then `forge-project.md` | STRICT evals + binding review + explicit operator approval; then policy/parser contract tests + binding review | measurable gate-1 wall time |
| 5 | R4 slices 5 → 1 → 2 → 3 → 4, one worktree each (leaf first, then app, then chain_core, then the single grammar owner, then journal); slices 1, 2, 3 and 5 each carry their `subjects.production` addition, strict-evals binding and R1 mint | control (+ `.forge/evals/tasks/**`; `docs/specs/**` only if Q1 widens the inventory to `codex_orchestrator`) | full discovery ×2 after last fix + binding review (+ STRICT evals + operator approval where the spec moves) | parallel ownership |
| 6 | R2 spec split, two area files first (FR-210..224, FR-230..243), then the rest | `docs/specs/**` | STRICT evals + binding review + explicit operator approval | spec contention |
| 7 | R6.2–6.4 | mixed | standard | |

Every step is intended as a pure move or an additive check — none changes a refusal
literal, raise-site count, lock order, exit code, or gate pass condition — subject to §7.

## 6. Open questions for the operator

1. **DM-016 subject width — wider, not narrower?** The five PASS slots exercise
   `codex_orchestrator` (`runtime.py:74` imports `batch`, `builders`, `journal`) yet the
   subject set stops at `forge_cli/`. Should the list grow to what the slot tests execute (R4
   slice 4's `journal_*.py` would then be additions too)? R4/R5's additions are required
   regardless (R4 table).
2. **Spec as one file.** Do external consumers (omnipus-cloud-agent, GH citations) rely on
   line-number citations into the single file? R2 preserves the path, not line numbers.
3. **Guard embedding.** Deliberate tamper-surface decision or first-implementation artefact?
   The spec records no rationale; R5 depends on the answer.
4. **Live re-runs in FR-241.** Is "result currency" satisfied by a mint-time run plus one
   combined live child, or must the validator re-execute each of the five subjects in its own
   process on every gate-1 pass?
5. **FR-149 shard rule.** Is amending FR-149's Revision-13 sentence (`min(4, cpu)`,
   round-robin) in scope for 0.7.0? Until then R6.1 cannot proceed.
6. **Priority.** If only one of R1/R2/R4 fits 0.7.0, the measurements favour R1 (largest
   ceremony per commit, smallest change), then R4 (largest ownership gain).

## Appendix — how the numbers were produced (all at 2d2faa6)

| Id | Figure(s) | Command / method |
|---|---|---|
| A1 | §2.1 table, shape facts | `python3 - <<'PY'` over `scripts/forge/forge_cli/*.py`, `scripts/codex_orchestrator/*.py`, `scripts/forge/*.py` and the guard payload (`commit-guard.sh` lines between the `<<'PY'` opener and the bare `PY` terminator): `ast.parse`; lines = `wc -l`; funcs = `ast.walk` `FunctionDef`/`AsyncFunctionDef`; cyclomatic as defined in §2.1; clusters = sum of spans of top-level defs/classes whose lower-cased name contains the token; duplicates = top-level function names present in >1 module |
| A2 | §2.2 | `git log --since=2026-08-15 --format='COMMIT %h %s' --name-only 2d2faa6`, per-commit file sets minus `.forge/history/**`; co-change = pairwise membership; mint stats over commits newer than `924d7c9`; subject set read from the manifest's `subjects` |
| A3 | §2.3 | `wc -lwc docs/specs/forge-plugin-spec.md`; `grep -c '^## '`, `'^### '`; `grep -oE 'FR-[0-9]{3}' \| sort -u \| wc -l`; §9 rows = lines starting `\|` in 1892–2087 minus header and separator; scenarios = `^### Scenario:` in 2088–3037; block bytes = UTF-8 length of each §7 `###` block; references = `grep -rl docs/specs/forge-plugin-spec.md` excluding `.git .forge .codex-orchestrator .worktrees docs/specs` → `forge-project.md`, `AGENTS.md`, `README.md`, `skills/workflow/SKILL.md`, `system/template/forge-project.md`, `system/fr223/hook-argv-cases-v1.json`, `policy.py`, `fr223_eval.py`, `audit-commitments.py`, 15 `tests/test_*.py`, 5 `docs/**` files |
| A4 | §2.4 | `ls tests/test_*.py \| wc -l`; `grep -c '^\s*def test_'`; `grep -c 'subprocess\.'`, `'sys.executable'`; `grep -lE '"init"\|git init'`; `grep -l 'def setUpClass'` / `'def setUp('`; class spans via `ast`; shard assignment = the gate-1 cell's own `index % min(4, cpu)` rule replayed over the sorted module list on this 12-CPU host; timings = `subprocess.run([sys.executable, "-m", "unittest", "tests.<module>"])` around `time.perf_counter`, one module at a time, host otherwise busy; the ten child-spawning modules = `test_cli_merge_lifecycle`, `test_cli_merge_integration`, `test_commit_guard`, `test_governance_scripts`, `test_candidate_identity`, `test_learn_proposals`, `test_revision8_coordination`, `test_migration`, `test_fr230_phase3_manifest`, `test_worktree_merge_skill` |
| A5 | §2.1 literals, §2.5, R7 | superseded grep kept for the delta only: `grep -rhoE '"forge: [^"]{8,}' scripts/ \| sort -u \| wc -l` (418); current figures come from A7; spec overlap = 45-character prefix `in` spec text over literals ≥ 45 characters (415 in `scripts/`, 73 hit); per-site table = `ast.walk` of `journal.py` recording `(lineno, enclosing def)` for each `Constant` equal to the pinned literal |
| A7 | §2.1 literals, R7 | quote-aware extractor (scratch script, ~120 lines, stdlib): every regular file under `scripts/`, `hooks/`, `skills/`; `.py` → `ast.parse`, rows from `Constant` str, `JoinedStr` (placeholders `{unparse(expr)}`), `BinOp(+)` chains headed by a `forge:` literal; `commit-guard.sh` → payload between the `<<'PY'` line and the bare `PY` line parsed as Python, head/tail tokenized as shell; `.sh`/`#!` files and `bash`/`sh` fences in `.md` → character tokenizer (single quotes, double quotes with `\` escapes and opaque `$(…)`, `\`-newline continuation, word = adjacent segments; row iff word starts with `forge: `); `.json` → every string value. Totals 786 sites / 508 distinct; per-kind 493 `Constant` + 151 f-string in `.py`, 26 guard-payload (18 + 8), 81 shell (75 double-quoted incl. 2 bare-word concatenations, 6 single-quoted), 35 markdown-cell. Old-vs-new delta computed as prefix match after quote stripping; the 61 sub-eight-character literals and the five `configure-dcg.sh` sites account for the 418 → 485 gap apart from escape rendering |
| A8 | R2 | `re` over the spec: definition markers `^- \*\*FR-\d{3}\*\* \((MUST\|SHOULD\|MAY)\)` → 161 lines (723–1474); all `FR-\d{3}` tokens → 1,327 (145 ids > 1, 16 once). Re-measured for revision 4: `grep -c 'amendment to \*\*FR-'` → 56 (lines 735–1464, 31 distinct ids); `grep -cE '^Revision-[0-9]+ .*amendment to \*\*FR-'` → 39; the 17 non-matching lines all begin `Candidate-bound fresh reviewer evaluation`; `grep -c 'clarification to \*\*FR-'` → 6 (`grep -ci clarification` → 9, the other three being the intent line 6, the inline FR-235 sentence 1319 and the revision-history line 3087); `grep -c 'Revision-'` → 147; forms enumerated by `grep -n 'amendment to \*\*FR-' \| sed 's/[0-9]\+/N/g' \| cut -c1-70 \| sort \| uniq -c` |
| A9 | R3 | `grep -n` of the eight `RESULT_TESTS` method names and `^class` in the three pinned modules; `python3 -c` over `tests/fixtures/fr230-results/*.json` printing `command`; `grep -c` of the ids in the spec → 0 |
| A10 | §1, §2.2, §2.4 (revision-4 re-measurement) | Co-change: the A2 `git log --since=2026-08-15 --format='COMMIT %h %s' --name-only 2d2faa6` stream parsed into per-commit path sets (`.forge/history/**` dropped); for a file set S, "co-change" = number of commits whose set ⊇ S. Results: manifest 22; manifest ∪ each fixture 22; manifest ∪ all five fixtures 22; ∪ `tests/test_fr223_v2_byte_pins.py` 17 (pin total 18; pin without manifest = `20c15a7`; manifest+fixtures without pin = `eb30c6a`, `419598b`, `99c85db`, `6f9b9a1`, `924d7c9`); digest-only commits = manifest commits whose non-history paths ⊆ {manifest, 5 fixtures, pin, `CHANGELOG.md`} → the four "rebind" commits; four-module set {`chain_core.py`, `builders.py`, `journal.py`, `test_revision9_coordination.py`}: any 24, all 3 (`c164e6d`, `e7813cc`, `41da640`), singles 6/10/18/11, pairs as in §2.2; HEAD diff `git show --stat HEAD -- scripts/forge/forge_cli/policy.py` → 16 insertions, 3 deletions. Shards: the gate-1 cell's own partition replayed — `modules = sorted(Path(p).stem for p in glob("tests/test_*.py"))`, `shards = min(4, os.cpu_count())` (12 → 4), group *s* = modules with `index % 4 == s`; test counts = `unittest.TestLoader().loadTestsFromName(f"tests.{m}").countTestCases()` per module with the repository root on `sys.path` (load only; nothing executed) → 17/17/16/16 modules, 516/482/472/421 tests, 1,891 total; `test_cli_merge_integration` loads 28 because its `load_tests` (line 8007) returns `merge_integration_shard_suite(0)` |
| A6 | Line citations | every `file:line` above was located by `grep -n` or `ast` at this HEAD (`git rev-parse HEAD` = `2d2faa60378959d83bd5cad4e56a85390b912da1`); `git diff --stat c164e6d 2d2faa6` lists the 18 files that moved since the superseded draft (`fresh_evals.py` 3,248 → 3,259 lines; `test_docs_contract.py` 1,655 → 1,705) |

## 7. Open review findings (commit-chain review, iterations 1–3, unresolved by design)

Recorded verbatim and left unresolved by the operator's ruling (this document is an analysis;
each finding belongs to its recommendation's design phase). Quoted line numbers are the
reviewer's, against revision 3; the passage each refers to is named, with its current line.

- iteration 3 [CON-06]: "Lines 372–376 exclude the 76 moved merge tests from subjects.tests, silently narrowing evidence binding despite R1's stated prohibition on narrowing. Add every moved subject file or obtain approval for an explicit subject-model change."
  Passage: R3 → **Risk** paragraph (line 399). Carried as an open item for the recommendation's design phase.
- iteration 3 [COR-05]: "Lines 296 and 409–412 claim R1 step 2b prevents omitted R4/R5 subjects, but its scan covers only forge_cli/*.py and commit_guard.py—not forge_common.py or later guard submodules. Define and test a closed inventory covering every proposed production subject."
  Passage: R1 change table, step 2b (line 314); R4 → paragraph after the "Subject additions" table (line 433). Carried as an open item for the recommendation's design phase.
- iteration 3 [FEA-05]: "Lines 297–300 require seven files to be written 'together, or nothing,' which ordinary filesystem operations cannot guarantee across crashes. Specify staged temporary files, confinement and symlink checks, fsync/rename ordering, rollback or recovery, and failure tests."
  Passage: R1 change table, step 6 (line 316). Carried as an open item for the recommendation's design phase.
- iteration 3 [COR-08]: "Line 292 makes a production governance script import implementation from tests/test_fr230_phase3_manifest.py. That reverses the module boundary and may fail when tests are unavailable or outside script-path imports. Move shared evidence logic into a production leaf module."
  Passage: R1 change table, step 1 (line 310). Carried as an open item for the recommendation's design phase.
- iteration 3 [INC-11]: "Lines 479–520 call R7 a closed, site-preservation proof, but A7 is an unavailable scratch script and planted known forms cannot prove extractor closure. The function-level occurrence key also cannot detect deletion and replacement within the same function. Commit a reproducible extractor and strengthen the key."
  Passage: R7 (lines 496–541) and appendix A7 (line 587). Carried as an open item for the recommendation's design phase.
- iteration 3 [INC-12]: "Lines 324–328 propose an incomplete R2 conformance recognizer. At HEAD there are 56 direct FR amendment lines, only 39 matching the proposed Revision-prefixed regex, and 6—not 7—clarification lines. Cover every normative amendment form before splitting authority files."
  Passage: R2 conformance-assertion table, third row (line 347), and the "Amendment and clarification forms" table (line 349). Carried as an open item for the recommendation's design phase.

### Iteration 4 (added after the fourth commit-chain review; carried as open items)

- iteration 4 [COR-05]: "treats non-equivalent subprocess wrappers as interchangeable; runtime.run_bounded merges output and returns flags, while candidate, archive, and drift wrappers preserve distinct streams, errors, limits, environments, and exit mappings, contradicting the claimed unchanged semantics and zero gate risk." Passage: R6 (bounded runner consolidation). Carried as an open item for the recommendation's design phase.
- iteration 4 [COR-08]: "claims slice 5 breaks the package cycle, but making builders imports of forge_cli top-level leaves runtime.py's reverse import of codex_orchestrator intact; extracting common primitives does not remove either dependency direction." Passage: R4 slice 5 (forge_common leaf). Carried as an open item for the recommendation's design phase.
- iteration 4 [INC-01]: "claims the extracted guard preserves the exact bootstrap refusal, but direct Python-file loading introduces unreadable, syntax, and import failures that can emit interpreter diagnostics before the shell fallback; specify and test exact fail-closed handling for every loader failure." Passage: R5 (guard payload lift). Carried as an open item for the recommendation's design phase.
