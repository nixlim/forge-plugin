# Changelog

All notable changes to the Forge plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Release dates are the UTC dates of the release commits.

## [Unreleased]

### Fixed

- Recognize dollar-quoted git commit and push verbs (ANSI-C `$'...'` and locale `$"..."`) in the commit guard's action discovery; normalize dollar quotes before command segmentation so an escaped quote inside one no longer desynchronises top-level segmentation and hides a later git verb (the double-quoted command-substitution variant remains open as bead forge-plugin-er59); deny any command carrying a dollar quote the guard cannot normalize (NUL escapes, nonportable `\u`/`\U` escapes, invalid UTF-8, or an unterminated quote), in every repository kind and outside any repository, with the existing policy-malformed diagnostic (bead forge-plugin-752).

## [0.8.0] - 2026-10-08

### Added

- Operator-approved backfill archives (spec Revision 19 FR-172, GH#24, bead forge-plugin-i5k): a closed run whose closing HEAD is no longer the repository HEAD, including a blocked run that is still gate-clean, can now be archived through the inseparable pair `--backfill-closing-head <full-object-id>` and `--backfill-approval <approval-run-id>:<decision-id>`, accepted identically by `scripts/forge/archive-run.py` and `forge commit start --archive-run-id <run-id>` and mutually exclusive with `--closing-head` and the legacy pair; `forge commit start --archive-run-id` also gains `--closing-head`, accepted only when it equals the repository HEAD. The approval is an `operator_approval` decision in an open, activated run owned by the current session whose resolution names the target run, both heads and the judgment. The archive checks journal validity first, then approval binding (the first of the twelve ordered `BACKFILL_CONTROLS`), then the four gated-validation checks, then the remaining eleven controls (archive-HEAD binding, strict passed history, ancestry, landed-commit, basis-document stability and time-order proofs), each with its exact refusal, and records backfill and absent-worktree provenance; a backfill reason must be one nonempty line free of control characters and Unicode line terminators. The closing logic lives in the new non-executable module `scripts/forge/archive_closing.py`. Normal-mode archives are byte-identical, and every git pathspec the archive code builds from journal or repository data is now literal (retired again by Revision 22 within this release; see Removed).
- Worktree cleanup now waits for run archives (beads forge-plugin-i5k, forge-plugin-tf8, forge-plugin-qvu). The new read-only `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" worktree-check --repo <repo> --worktree <absolute-path>` exits 1 with `forge: worktree cleanup deferred — run <run-id> has no committed archive and depends on <worktree>` while a run without a committed archive (a blob at `HEAD:.forge/history/runs/<run-id>.md`) was opened from that worktree or cites evidence that physically resolves inside it, through any of the seven FR-017 journal citation surfaces, and 0 when nothing depends on it. Every other outcome, including an unexpected error, exits 2 with `forge: worktree check refused — unreadable input`: runs-root children are classified after run coordination's rules (a stray regular file or an empty placeholder directory is skipped; a directory holding a journal is scanned; other children refuse), every journal is fully validated before an archive releases it, and a run id or path with control characters or undecodable bytes is refused rather than printed. `/forge:worktree-merge` runs it after the push-containment proof and, on exit 1, keeps the worktree and branch and reports the cleanup as deferred without failing the merge; before removing anything it re-proves the branch tip and a clean worktree, never forces removal, and deletes the branch with `git update-ref -d` against the verified tip instead of `git branch -D`. `/forge:workflow` retries each deferred cleanup after the archive commit and the report, and says to copy worktree-resident evidence into `<run>/evidence/` first; a worktree a permanently unarchivable run depends on is released only by an operator-reserved cleanup recorded as an operator decision (retired again by Revision 22 within this release; see Removed).

### Changed

- Trailing whitespace left by U2 in two replay modules is removed; FR-230 evidence re-minted.
- The launch lane refuses to start when the launch-lane lock cannot be taken, as at 0.7.1; only the `execution_started` append stays best-effort (FR-034, FR-036). Found by the whole-stack review.
- Whole-stack review follow-ups: the commit guard no longer admits the retired `commit abort-disposition` verb; dead parameters and test plumbing are removed; a focused test refuses every FR-256 retired flag; FR-230 evidence is re-minted.
- Prose follow-ups from the whole-stack review: UPSTREAM records the learn loop, frozen-route launch binding and `commit abort-disposition` as retired by Revision 22; `docs/updating-forge.md` gains the Revision 22 breaking-upgrade note; `rules/evaluation-harness.md` and the README Evals section follow the amended FR-102; `forge-project.md` and `AGENTS.md` no longer describe durable run archives or archive-only chains; the `[Unreleased]` body names every retired surface under Removed.
- Skills carry the brief and review discipline from the Revision 22 post-mortem: `workflow` gains a "Brief and design discipline" section (quoted spec sentences, no mechanism the ruling does not name, baseline plus per-file dispositions, byte-identical kept diagnostics, no re-implementation of tools the code already calls, patch every brief when a ruling changes); `orchestrate` names the two independent review lenses (bloat and conformance; correctness and fail-closed), executed evidence with hypothesis labelling, and the rule that a fix which adds a branch, flag, helper or mechanism is a design signal; `commit` applies the same rule to its restage loop; `report` lists every mechanism added beyond the ruling as a follow-up.
- Revision 22 U5 (forge-plugin-x990.7): `commit restage --paths` accepts any path `commit start` accepts and records the superseded and new candidate identities with their exact tree delta; every gate and the review rerun after a restage and candidate-bound authority is void; the reviewer is told the prior candidate and the delta; `review request` for `review-final` refuses a route equal to the implementer route; classification derives from the full current candidate; review-side gotcha hydration is retired; `commit start`/`restage` render offending paths as escaped JSON literals and refuse an untracked git-ignored path with `named path does not exist`.
- Revision 22 spec amendment: FR-255 trimmed to fix-in-chain under `commit start`'s path rules with every gate rerun and the per-chain cap; gate carry-forward, cross-chain review-budget inheritance, `commit skip review-cap` and the restage `unsafe path` literal are removed before any implementing release.
- Revision 22 U6 (forge-plugin-x990.8): expand built-in control to `rules/**`, `agents/**`, `system/**`, `hooks/**`, `skills/**`, `.claude-plugin/**`, `docs/specs/**`, `.refactor/type-baseline.json`, and `scripts/forge/route_config.py`; separate control approval from the non-narrowable review-final floor for scripts, hooks and fixtures; require hard final review and STRICT integrity on the built-in floor; refuse skip-review for project trigger-path and hard-row candidates; deny the Gate 1 docs-class skip for docs paths matching a hard row; retain project control extensions, retire FR-247 provenance, update the canonical reviewer trigger table and history, and re-mint FR-230 evidence.
  Upgrade note: A malformed or invalid-pattern committed control row makes classification exit 2 for every candidate, including a commit that repairs `forge-project.md`. The operator must correct the policy through a separately authorized and independently reviewed recovery commit, then resume normal chains from the repaired committed policy; the mechanical refusal remains fail-closed.
- Revision 22 U4: make the journal an append-only execution and decision log with structural validation; remove retired coordination modules, batch verbs, gated journal validation, archive and run-authority prose, and the worktree cleanup guard while retaining Git cleanup proofs and chain-evidence reporting; launch and collect continue after journal I/O failure, while filesystem execution IDs and markers determine in-flight work.
  Upgrade note: collect or cancel every in-flight managed launch before upgrading; older uncollected launches lack `wrapper-config.json` and the worktree sidecar, so collect and cancel refuse them. The operator clears a stranded marker by hand after inspection.

- Revision 22 U3 (forge-plugin-x990.5): delete run archive and commitment-audit executables, helpers, fixtures, and tests; stop installing a run-archive directory; remove archive prerequisites from operational documentation and update the executable inventory while leaving existing history readable; clarify in FR-160 that tracked-file category coverage does not consume a journal or archive artefact as an input.
- Revision 22 U1 (forge-plugin-x990.3): remove journal-derived learning and its extractor, retain seven skills, and detach drift from journals, run archives, and learned artifacts while keeping summary schema version 1.
- Retire commit/merge journal permissions, ingest and archive chains, preserve authenticated legacy history with canonical/digest/state checks, authenticated commit landing windows and unbound bootstrap evidence, remove launch active-task preflight and route-snapshot refusals while retaining clean builder-refusal recovery, use non-reserved launch and chain-artifact reason codes and the diagnostic `forge: launch refused — owner record outcome is ambiguous` without retired batch-recovery advice, refuse retired --run-id/--task chain options after parsing, including separator placements before the complete verb, disable abbreviations on launch and leave invalid verbs to argparse, parse hidden commit/merge start task options only for the exact retired-option refusal, validate launch run IDs after parsing before filesystem access, update typed-run and commit-guard consumers, record the specification sentence authorizing subject re-mints, and retain strict DM-014 bootstrap refusals, reject scope requests and lone source-event carriers on new chains, remove dead merge controls and helpers, preserve native merge receipt/abort replay, safe CLI diagnostics and launch recovery files; type and name replay checks, and re-mint the FR-230 generation-1 manifest and result bindings for the final subject bytes.
- Spec Revision 22 (operator ruling of 2026-10-06, landed spec-first; epic bead forge-plugin-x990, unit x990.1) records the record-keeping simplification ahead of its code. The run journal becomes an append-only log of executions and decisions that never refuses a write on policy grounds and never gates a landing (FR-250..FR-252). Retired from the specification: the typed journal builders, batch transaction and owner refusals (FR-016..FR-019), the passed/blocked run-close judgment and `validate --gates` / `journal close-preflight` (FR-020..FR-025, FR-248..FR-249), journal-to-chain binding and gate-result ingest (`forge-journal-binding/1`, `forge-gate-binding/1`, `journal ingest-chain`, DM-001..DM-002), the run scope registry and successor runs (FR-014, FR-190..FR-194, DM-011), route freezing at run-open (the route is recorded per execution instead), committed run archives and the learn pipeline (FR-170..FR-174, FR-200..FR-205, `archive-run.py`, `audit-commitments.py`, `journal-patterns.py`, `/forge:learn`), and FR-247 task-completion provenance. Drift sensing stays and reads only gate output, chain evidence and committed text. The Revision-18 `run-bound-gate-one` rule retires with run binding, so every chain takes the docs-class Gate 1 skip (control, floor and trigger matches still excluded). The built-in `control` category no longer includes `scripts/**` or `tests/fixtures/**`, except `scripts/forge/route_config.py`, whose committed route defaults and sandbox table can weaken the review and stay control (FR-253); a new built-in, non-narrowable `review-final-floor` of `scripts/**`, `hooks/**`, `tests/fixtures/**` and every control path keeps binding `review-final` at commit and merge with no approval wait (FR-254). After a review BLOCK the revised candidate restages in the same chain under `commit start`'s path rules, and every gate reruns (FR-255). Already committed journals, bindings and archives are untouched and remain readable; the release implementing this will be breaking for callers of the retired verbs and skills (FR-256). FR-220's reason-code table, FR-221 and FR-210's verb sentence are byte-identical; the DM-016 Revision-10 manifest paragraph is amended by U2 to authorize in-place generation-1 re-mints; retired reason codes stay reserved and are never emitted. Retired text was removed rather than marked: the spec shrinks from 3,669 to about 2,800 lines. Spec-quoting tests were updated in the same unit (`test_spec_revision19` and `test_spec_revision21` deleted; `test_spec_revision15`, `test_spec_revision20`, `test_spec_typed_launch`, `test_docs_contract`, `test_route_vocab` re-pinned to the surviving text; `test_result_before_gate` and `test_ingest_refusal` deleted by U2 with their retired subjects, the gate-result ingest and journal-to-chain binding; new `tests/test_spec_revision22.py` pins FR-250..FR-256 with in-memory disable checks). The merge fetch sidecar keeps its `forge-run-scope-fetch-binding/2` shape with the three scope members null, by operator direction. FR-032 now requires the binding `review-final` route to differ from the implementer route in provider or model, refusing an equal route at `review request`; the committed defaults already satisfy it.
- Run archives now embed every chain event log compressed (spec Revision 21, bead forge-plugin-glqo): `scripts/forge/archive-run.py` writes each log as one xz stream (standard-library `lzma`, preset 6, CRC64 check) in unpadded base64url under `encoding=xz+base64url bytes=N encoded_bytes=E sha256=H` while the encoded payload is at most 2 MiB and the raw log at most 64 MiB, otherwise the unchanged digest-only `UNEMBEDDED` block, and refuses with `forge: archive refused — Python lzma module unavailable` (reason code `lzma-unavailable` through `forge-cli/2`) when the module is missing, with no fallback to the old encoding. The fail-closed decoder lives in the new non-executable module `scripts/forge/chain_evidence_codec.py` (64 MiB decompressor memory limit, declared length checked first, payload validation before importing `lzma`, one stream with exact length and digest); archives already committed with `encoding=base64url` still decode. Long runs that exceeded the 16 MiB archive cap now fit: logs repeat the full chain state in every event and compress by a factor of about 100 to 400 (retired again by Revision 22 within this release; see Removed).
- Spec Revision 21 (run run-20261004-backfill, landed spec-first; bead forge-plugin-glqo) records how run archives carry chain event logs from now on: each log is compressed as one `.xz` stream (standard-library `lzma`, preset 6, CRC64 check) and embedded as unpadded base64url under `encoding=xz+base64url bytes=N encoded_bytes=E sha256=H` whenever the encoded payload is at most 2 MiB and the raw log at most 64 MiB, otherwise as the unchanged digest-only `UNEMBEDDED` block. Decoders fail closed: a 64 MiB decompressor memory limit, the declared raw length checked before decoding, payload validation (including trailing bits) before importing `lzma`, one stream with exact length and digest, and exact refusals when the Python `lzma` module is missing (new reason code `lzma-unavailable`). Rerenders inside one chain stay byte-exact; `/forge:report` keeps its exact whole-archive rerender equality, so a compressor build change between an archive commit and a later report is a documented residual (bead forge-plugin-c2i8). The 16 MiB archive cap and its refusal are unchanged, and archives already committed with `encoding=base64url` stay valid. Measured on this host, the closed run that hit the cap would embed all 28 chain logs in about 0.6 MiB instead of 34 MiB. The renderer change follows as task TA; event-format slimming (bead forge-plugin-6f70), local retention and garbage collection stay deferred (retired again by Revision 22 within this release; see Removed).

### Removed

- Revision 22 (FR-256) retires the verbs and flags `validate --gates`, `journal close-preflight`, `run-readmit`, `run-retire`, `journal batch-recover`, `journal ingest-chain`, `chain outbox-drain`, `commit abort-disposition`, `journal verification-add`, `commit start --archive-run-id <run-id>` including its legacy/backfill flag pairs and `worktree-check`; the executables `archive-run.py`, `audit-commitments.py` and `journal-patterns.py`; their interpreter-loaded helper modules `archive_closing.py`, `chain_evidence_codec.py`, `commitment_paths.py`, `learn-proposals.py`, `learn-proposals-locked.py` and `route_provenance.py`; and `/forge:learn`. This release is breaking for their callers. Existing run directories, journals, bindings and committed archives stay untouched and readable (FR-256).

### Fixed

- Backfill and legacy archive approvals now replay the approval run's journal with the scope in force at each record, applying every scope readmission in order as the journal does (bead forge-plugin-ievf). Before, the replay checked every record against the run's opening scope, so an approval run that had readmitted scope and then journaled work on the new paths always refused with `forge: archive refused — backfill approval missing or mismatched` (retired again by Revision 22 within this release; see Removed).

### Release notes

- 0.8.0 is the Revision 22 record-keeping simplification (operator ruling of 2026-10-06; spec section 5A, FR-250..FR-256; epic bead forge-plugin-x990). The run journal is an append-only log of executions and decisions that never refuses a write on policy grounds and never gates a landing. The passed/blocked run close, journal-to-chain binding and gate ingest, the scope registry and successor runs, route freezing at run-open, committed run archives and the learn pipeline are retired; drift sensing stays, detached from the journal. The built-in control class narrows to the surfaces that can weaken a gate, and a built-in `review-final-floor` covers `scripts/**`, `hooks/**`, `tests/fixtures/**` and every control path. A review BLOCK is fixed inside its chain through `commit restage`, which reruns every gate on the new candidate. Gates, binding independent review, fail-closed behaviour and candidate-bound approval for control changes are unchanged. This release is breaking for callers of the surfaces listed under Removed.
- **Consumer actions.** Before updating, finish every managed launch with `launch collect` or `launch cancel`; afterwards both verbs refuse older uncollected launches (see the Revision 22 U4 upgrade note above). Remove the retired verbs, flags and executables from any scripts; the complete list is under Removed. A project `control` row that still lists `scripts/**` and `tests/fixtures/**` remains an honoured project extension; drop those two patterns from the row to take the narrowed built-in class and keep every other entry. A `.forge/local/routes.toml` that resolves `review-final` to the implementer's provider and model is refused at `review request`; route `review-final` to a different provider or model (the shipped defaults already do). Existing run directories, journals, bindings and committed archives stay untouched and readable. The 0.7.1 reviewer-facing eval-trigger table is kept in the superseded-table history, so a committed 0.7.1 policy still parses and `fresh-reviewer-evals` no longer refuses it as malformed.
- **Behaviour changes.** A candidate touching `scripts/**` or `tests/fixtures/**` is `hard` through the built-in floor: binding `review-final` with STRICT Recorded-baseline integrity where FR-103 applies, and no approval wait unless a control path is also touched. `commit skip review` is refused for a floor, trigger-path or hard-row candidate, and the docs-class Gate 1 skip is denied for a docs path matching a hard row. A malformed or invalid-pattern committed control row makes classification exit 2 for every candidate until a separately authorized and reviewed recovery commit repairs the policy. `run-close` records a free-text outcome and no judgment; `validate` checks envelope structure only and accepts unknown kinds; `journal execution-start` and `execution-result` record the route actually used and refuse no divergence from an earlier record; both verbs now require `--sandbox`, `--route-source` and `--route-sha256` (argparse exit 2 when absent) and accept any value. `forge launch` and `launch collect` continue after a journal I/O failure, while the launch lane still refuses to start when its single-writer lock cannot be taken. `commit restage --paths` accepts every path `commit start` accepts, records the superseded and new candidate identities with their tree delta, and voids every earlier gate result, review and authorization; the per-chain review-round cap is never reset by a restage, and a new chain starts at zero.
- **Known limitations.** The FR-032 distinctness check compares the resolved provider and model strings, so an alias or suffixed spelling of the implementer's model (`opus`, `claude-opus-5-5[1m]`) passes as different (bead forge-plugin-x990.12). Commit-chain replay verifies event digests but not event names or state transitions; this was already so for unbound chains and now applies to every chain (bead forge-plugin-x990.13). In an installed project, a candidate that triggers `fresh-reviewer-evals` still cannot pass it, because the suite reads `rules/review-constitution.md` from the candidate tree (GH#45, bead forge-plugin-8mbz).
- **Deferred work.** The specification keeps 11 deferral markers: nine Revision 20 markers (G40 x3, G42 x6) for amendments that shipped in 0.7.1, and two Revision 21 markers (TA x2) for the compressed chain-log archives, which Revision 22 retires within this release; all remain until a later cleanup removes them. Revision 22 follow-ups are tracked as beads forge-plugin-x990.10 (replay layer), forge-plugin-x990.11 (null-member merge scope sidecar) and the spec wording items under forge-plugin-x990.2.

## [0.7.1] - 2026-10-04

### Changed

- Spec Revision 20 (run run-20261003-archive, landed spec-first) records the authority for four consumer-reported fixes ahead of their code: commit approve from an installed, non-git plugin cache through a digest-chain verification helper that keeps the frozen FR-223 evaluator byte-identical (GH#40); upgrade chains whose base policy holds a released superseded reviewer-facing-eval-triggers table (0.6.11 to 0.6.14) pass fresh-reviewer-evals without a skip (GH#41); `install.sh` keeps a project spine block and foreign Codex hooks and collides instead of overwriting a foreign `.codex/config.toml` (GH#42); and citations of a run opened from a linked worktree resolve against the run directory, the recorded repository, then the layout-derived root, so such runs can be archived (GH#43). It also records that candidate checkout has refused absolute or escaping symlinks and gitlinks across the whole tree since 0.6.11. Each amendment whose code has not landed carries a deferral marker naming its implementing task.
- Spec Revision 19 (run run-20261003-archive, landed spec-first) records the archive-blocker authority ahead of its code: historical gate bindings an archive may render as not landing evidence (DM-001, FR-171), the operator-approved backfill archive with its proofs, provenance lines and blocked-run admission (FR-172, FR-170, FR-173), judgment and summary in archive provenance, a shared resolver for `run_started.repo` used by the journal writer, typed builders, typed-batch mismatch sites and commitment audit while other readers keep their own checks and messages (FR-019), and deferred worktree cleanup while an unarchived run depends on the worktree (FR-064, `codex_orch_tools.py worktree-check`). It also confirms archive-only chains without a changelog step (FR-214, FR-018), whose code already landed (bead forge-plugin-5wz). Each amendment whose code has not landed carries a deferral marker naming the task of this run that implements it, and a closing task of the same run removes those markers once the code has landed; the archive-only chain clauses carry no marker because their code is already in place. The rule that `/forge:report` rerenders an archive for equality only with the renderer revision that produced it is recorded but stays deferred under bead forge-plugin-c2i8; `/forge:report` behaviour does not change in this run.
- Plugin manifests no longer declare a version (GH#37, bead forge-plugin-6j08), so Claude Code keys the plugin cache by the installed commit SHA and updates, including `autoUpdate`, follow each commit on `main`; pin a `vX.Y.Z` tag for release-only updates.
- The rendered `AGENTS.md` Forge splice is re-rendered from `forge-project.md` (it had lagged by the `tests.test_version` line added to the docs-contract stack cell); nothing outside the splice markers changes and the executed policy is unchanged.

### Fixed

- Re-running `/forge:init` or updating the plugin no longer drops project text or project Codex hooks (GH#42, bead forge-plugin-ipth). `forge-project.md` gains one `FORGE:PROJECT-SPINE` block at the end of the DVRR spine whose contents are carried forward byte-for-byte; a legacy file whose text outside the regions differs from the template is preserved as `forge-project.md.forge-prev` and reported as a blocking collision for `/forge:init`, and the previous install date is kept. Before writing anything the installer now parses `.codex/hooks.json` and `.codex/config.toml` (strict UTF-8, at most 1 MiB, regular non-symlink files) and refuses malformed input with no change; hooks are merged so plugin-owned handlers refresh and foreign ones stay; a `config.toml` holding anything outside the plugin-owned keys is left untouched and the new template is written as `config.toml.forge-new`, which is also what happens when Python has no `tomllib`. This repository's own `forge-project.md` and `AGENTS.md` gain only the empty block.
- Runs whose run-bound chains were restaged can be archived again (bead forge-plugin-3bwn). The archive renderer used to refuse with `structured_chain_mismatch` whenever a journal-bound gate record was not current for its chain, which is routine after a `commit restage`, a gate re-run, or a chain abort. Only the renderer may now accept such a record, and only as replay-authenticated history: the chain must be terminal (landed, or aborted with a current carried `chain-abort` decision), and the chain-side and journal-side classes must agree. Accepted records render `BOUND — source-authenticated history; NOT LANDING EVIDENCE (<reason>; <binding-id>)` with the reason `superseded candidate`, `aborted chain`, `failed gate cleared by passing recheck` or `earlier run of the same step`. A record of a chain that ended in a carried abort, including a record that was current, renders as `aborted chain` history unless it is a superseded candidate, which keeps that reason by precedence. Append, ingest, terminal-guard and close-law currency are unchanged, and the archive's Candidate column now shows a v2 candidate's authorization id instead of `None recorded`.
- A run opened from a linked Git worktree can be audited and archived (GH#43, bead forge-plugin-n64p). Relative citations now resolve against the run directory, then the run's recorded repository, then the repository root derived from the run layout (where `.forge/chains/` and the run directories live), through one shared predicate used by append-time validation, `validate` and run close, the commitment audit and the archive's basis documents; before, the audit looked only in the run directory and the recorded worktree, so every chain-written citation of a worktree run was reported missing. Escaping citations still refuse at every leg; `validate` and run close now also refuse existing run-directory escapes; and under the legacy missing-file dispensation a missing citation whose spelling escapes the run is now a hard issue rather than a tolerated warning. Archive recovery resolves its recovery run beside the target run.
- Upgrading across a change of the reviewer-facing eval trigger table no longer needs an operator skip (GH#41, bead forge-plugin-1neg). When the committed base policy still holds the table a released plugin shipped (0.6.11 to 0.6.12, 0.6.13 or 0.6.14), `fresh-reviewer-evals` accepts it as authenticated base input and applies the current rows plus any pattern only the older table listed, keeping the base region's own digest in the evidence; the unreleased 2026-09-27 form and any edited table still refuse as malformed. FR-230 phase-3 evidence is re-minted for the changed `policy.py` subject.
- `commit approve` now works from an installed plugin (GH#40, bead forge-plugin-pcvy). Approval runs the FR-223 harness qualification through the new non-executable `scripts/forge/fr223_verify.py`: from a plugin root that is its own Git top level it runs the frozen `fr223_eval.py` exactly as before; from a marketplace cache, which is not a Git checkout, it checks the phase-0 manifest against its spec-pinned digest and the evaluator against its manifest entry, then runs those verified bytes with only the committed-spec read replaced by a strict read of the shipped spec file. A plugin root inside another work tree, or with a broken `.git`, refuses. Installed mode proves the cache is self-consistent, not that it is authentic; the frozen evaluator, its manifest, corpora and evidence are unchanged. FR-230 phase-3 evidence is re-minted for the changed `_approval.py` subject.
- A run opened from a git worktree can close from the main checkout after that worktree is removed (bead forge-plugin-h2z leg (a), GH#9). The journal writer and typed builders (`task-finish`, `run-close`, owner takeover, scope change) and the commitment audit for runs in the standard layout now resolve `run_started.repo` through one resolver, `scripts/codex_orchestrator/recorded_repository.py`: a pre-coordination journal still resolves to the state root; a present recorded path, including a subdirectory that `run-open` admitted, resolves to its checkout's toplevel when that checkout shares the caller's Git common directory, taken from the caller's own checkout so separate-git-dir repositories and submodules work; an absent path resolves to the state root only when it is a normalized absolute path strictly below `<state root>/.worktrees/` and the run directory sits at `<state root>/.codex-orchestrator/runs/<run-id>`; everything else refuses. At the four typed-batch mismatch sites a recorded repository that differs from `--repo` now refuses with `forge: journal append refused — recorded repository unavailable for run <run-id>` instead of `run registry unavailable`. Readers that keep their existing behaviour: the archive renderer and the approval proof still require a live recorded path; `_validate_chain_batch_target` keeps `forge: new run refused — run registry unavailable` when its resolved recorded repository differs from the caller's repository root; `_prevalidate_chain_batch_carrier` propagates the recorded-repository-unavailable diagnostic on resolution failure but keeps `forge: journal append refused — invalid journal record` for its combined successfully resolved mismatch; batch recovery compares the recorded string exactly where it compares at all; and the audit keeps its legacy resolution for an out-of-layout run directory (bead forge-plugin-9acq). The commitment audit now runs repository conformance from the resolved root instead of skipping it.
- Archive-only commit chains no longer schedule the changelog step (bead forge-plugin-5wz). With a configured changelog policy, `commit start --archive-run-id` chains used to dead-end at the changelog gate, which an archive chain refuses as a mutating gate, so every run-archive commit needed an operator `commit skip changelog`. Now `_required_steps` omits `changelog` when the chain carries validated archive staging (control `ARCHIVE_CHANGELOG_EXEMPTION`), and every verb, including the pending-mutating-gate check, derives from that same step list; ordinary chains keep their changelog gate first.
- The docs-class stack validation (the contract tests that run for a candidate whose only changed paths are documentation, because Gate 1 is skipped for it) now includes `tests.test_version`, and the policy pin that lists every test module reading repository prose now counts a `CHANGELOG.md` read as prose. Since the manifest version field was dropped, `tests.test_version` compares the `pyproject.toml` version with the newest `CHANGELOG.md` release heading; before this, a changelog-only candidate could move that heading without the comparison running (bead forge-plugin-7pvu).

### Release notes

- 0.7.1 carries four consumer-reported fixes: `commit approve` works from an installed plugin cache through `scripts/forge/fr223_verify.py` (GH#40); upgrade chains accept a released superseded reviewer-facing eval-trigger table without an operator skip (GH#41); re-init preserves the `FORGE:PROJECT-SPINE` block and foreign Codex hooks, writes `config.toml.forge-new` for a foreign `config.toml`, and preserves divergent legacy spine text as `forge-project.md.forge-prev`, which `/forge:init` reports as a blocking collision (GH#42); and runs opened from linked worktrees can be audited and archived (GH#43).
- **Consumer actions.** After updating, re-run `/forge:init`; with divergent legacy spine text, it writes `forge-project.md.forge-prev` and stops with a collision. Move any still-required project text from that sibling into the `FORGE:PROJECT-SPINE` block of `forge-project.md`, then remove the sibling and re-run `/forge:init`. If `/forge:init` reports `config.toml.forge-new`, then where `tomllib` is available, re-init completes only once `.codex/config.toml` holds only Forge-owned content, for example after adopting `config.toml.forge-new`; a config that keeps foreign content collides on every re-init. On Python 3.10, any existing config collides on every re-init. Archive-only chains no longer need `commit skip changelog`.
- **Behaviour changes.** Under the legacy missing-file dispensation, a missing citation whose spelling escapes the run is now a hard issue, and `validate` and run close now report an existing citation that escapes the run directory. On Python 3.10, which has no `tomllib`, a re-init reports a blocking `config.toml.forge-new` collision whenever `.codex/config.toml` already exists; a fresh install with no config still installs directly.
- **Deferred work.** The specification still carries 66 Revision 19 and Revision 20 deferral markers. The 15 Revision 20 markers—G40 ×3, G41 ×1, G42 ×7 and G43 ×4—and 18 Revision 19 markers for historical bindings (T1 ×9) and recorded-repository resolution (T5b ×9) describe amendments that ship in 0.7.1; those 33 markers remain until a later cleanup removes them. The other 33 markers identify work not included in this release: the backfill archive (T2a ×11), judgment and summary provenance (T3 ×7), the worktree cleanup guard (T6 ×8), and the `/forge:report` producing-renderer rerender rule (bead forge-plugin-c2i8 ×7).

## [0.7.0] - 2026-10-02

### Added

- Routing chain I (forge-plugin-4g68.12, operator rulings 2026-09-27 and 2026-09-28) adds typed engine launches for the `implementer` and `plan` roles: `forge launch` starts the resolved route (Codex or Claude) for an active run task as a detached, process-group-contained wrapper on E's lane, records a `forge-launch-marker/1` binding the attempt, argv, prompt, launcher and role body digests, and writes the journal `execution` record; `forge launch collect` writes the terminal `execution_result` exactly once from the wrapper's completion and handoff, with fail-closed recovery for launching, abandoned, wrapper-lost and identity-unproven attempts; `forge launch cancel` signals only a proven-owned group. Provider version floors move to the new stdlib leaf `scripts/forge/route_floor.py`, shared byte-for-byte by `launch` and `review request`; route evidence refuses executions whose route fields diverge from the run snapshot or are missing; `/forge:init` step 5 and the routes seed describe the typed launch; the FR-245 Claude implementer cell adds `--no-session-persistence` (keeping `acceptEdits` with Bash) and the plan cell drops `LS` and adds `--no-session-persistence`; the implementer profile timeout is 14400 seconds (review stays 2400); the three launch engine modules carry module and function docstrings and share their helpers through `_launch_lane.py`, and the orchestrate and workflow skills are rewritten for the typed lane; the chain-I deferral markers are removed from FR-034, FR-080, FR-245 and DM-018; FR-230 phase-3 evidence is re-minted with the three new engine modules as subjects.
- Claude stream monitoring (operator ruling 2026-09-28, with routing chain I): `codex_orch_tools.py monitor` no longer skips every execution whose event source is `claude`. A Claude execution with a stream-json events file, as written by `forge launch` for a Claude-routed implementer or planner, is summarised through the same status, notification, confidence and staleness model as a Codex exec stream (a final `result` event with `is_error` false completes it, `is_error` true fails it); Claude subagent records with no events file stay silently skipped, and other event sources stay errors. FR-012 records the upstream divergence.
- Route grammar (forge-plugin-772y, operator ruling 2026-09-27): the Claude effort set is `low | medium | high | xhigh | max`, amended in place in FR-244 and in `route_config.EFFORTS`; Codex effort is unchanged and `xhigh` stays refused for Codex in the routes file and the `run_started` route entry.
- Routing chain E (forge-plugin-4g68.11) makes `review request` launch the resolved `review-cheap` or `review-final` route, Codex or Claude, on both the commit and merge lanes as an engine-owned detached process: an isolated `-I` stdlib wrapper leads its own process group, records its identity before the reviewer starts, bounds and redacts streams and publishes its completion atomically, while identity claims and verb-side terminal completions use exclusive links; `review collect` is attempt-keyed and binds the verdict; the new `review cancel` terminates only a proven group and refuses when the group identity cannot be proven; `review attach` is retired for new requests by record shape; run-bound requests compare their route with the run snapshot. FR-246 and DM-018 lose their deferral markers, FR-246 defers the headless review for the legacy `/forge:worktree-merge` skill, the reviewer-facing trigger rows gain `route_evidence.py`, `route_provenance.py` and `route_floor.py`, and `engine/_review_lane_api.py` exposes the shared lane primitives for the typed launch verbs.
- Routing chain J (forge-plugin-4g68.10) adds frozen run-open route snapshots and best-effort orchestrator-model evidence, the execution `sandbox`/`route_source`/`route_sha256` trio with snapshot-divergence refusal, FR-247 completion provenance enforcement at `task-finish` and `run-close`, and `check_run` findings for developer-local routes, instruction-bounded implementers, orchestrator-owned completions, and same-model binding reviews; prose launches remain accepted and project as `route_source: unrecorded` until chain I.
- Routing chain L (forge-plugin-4g68.9) adds the stdlib-only `scripts/forge/route_config.py` leaf CLI with `init`, `show`, `check`, `resolve`, and `probe` verbs plus `system/local/routes.toml.seed`, and removes FR-244's implementation-deferral marker; its iteration-1 review fixes reject misplaced copies from the linked-worktree top level, use the new non-executable stdlib helper `scripts/forge/route_config_git.py` for bounded and ambient-Git-scrubbed calls, append the Git exclude line before the create-once refusal, and record both the probe contract and the review-final committed-default rule in FR-244; runs and launches do not read the developer-local file until routing chains J and I land.
- Routing chain B (forge-plugin-4g68.8) adds the Codex planner body and Claude implementer, planner, and first-pass-reviewer bodies, registers the read-only `gpt-5.6-sol`/`high` Codex plan agent, rewords review-cheap target identity to admit either a full commit SHA or an immutable staged-tree snapshot identified by tree OID, authorization ID, and review-diff digest (GH#34 / forge-plugin-o8uh), and pins the new surfaces in installer and repository-conformance coverage.

### Fixed

- Stage 1 follow-up for close preflight, run-bound Gate 1 and landed evidence (beads forge-plugin-diuy.1 and forge-plugin-diuy.2): `journal close-preflight` reports a lockless legacy or nonexistent run with the reader's own diagnostics instead of "pending or changed batch transaction", and stays non-blocking when the batch lock appears mid-read, validating from the single fenced snapshot it already read; the read-only chain-lock open is non-blocking and refuses a FIFO swap instead of hanging; a historical docs-class Gate 1 skip recorded on a run-bound chain no longer counts as a completed Gate 1 (unbound chains and ingest are unchanged); the journal-only line escapes control characters in the embedded first issue and caps it at 4,096 UTF-8 bytes; FR-248, FR-220 and FR-214 now state the bounded wait, the projected candidate, `journal_lines`, the expected pre-review verify issue and the unsuffixed no-op verify message. New direct tests pin each landed-candidate-evidence and landed-recheck-source sub-clause and the projected-chain exclusion from the terminal-chain guard. FR-230 phase-3 evidence is re-minted. Correction to the journal-only close-preflight entry below, under Changed: verify and the two review collect paths print the `close preflight (journal-only, projecting <chain-id>): ...` form.
- Stage 1 follow-up for the result-before-gate and ingest-refusal surfaces (beads forge-plugin-diuy.3 and forge-plugin-diuy.5): the spec now enumerates the sixteen ordered FR-210 proof names that a refused chain ingest may name, and a non-verbose refusal is pinned to carry no raise site; `commit restage` checks keyword-passed paths for overlap too; an `execution_result` whose status is missing, malformed or not terminal leaves the execution pending (as the close law treats it) instead of crashing, and an unexpected pending-result inspection failure on `commit start` or any of the five bound verbs refuses as `run-task-binding-invalid` (with exception class names under `--verbose` only) instead of exiting as a frozen chain with raw exception text; identifiers in the pending-result diagnostics and warnings are escaped onto one line, the remediation names the builder as `${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py`, and FR-249 states the real-end obligation as the operator's. The launch lock test asserts event order instead of a wall-clock bound, removing a CPU-load flake, and both repeat guards gained discriminating tests. `skills/orchestrate` and `skills/workflow` document the `execution-result-pending` refusal and the advisory close-projection warnings.
- Claude init check follow-ups (bead forge-plugin-wggs, the ig69 review-final MINORs): a redacted passed value that occurs inside the validated init `permissionMode` or a validated tool name (for example `AWS_PROFILE=default` against the plan profile's `default` mode) no longer fails the launch as `redaction damaged init.permissionMode`. The raw first init event is checked against the argv-derived expectation first, and only a value-only redaction, whole or partial, inside those two already-validated fields of that first event is exempt; later events with subtype `init` keep the damage rule; the persisted event still carries the redacted text, and key damage and every other extractor-field rule are unchanged. The `type`, `subtype` and list-typed `tools` init checks and the refusal of empty or duplicate `--tools` entries (now specified in FR-246) are pinned by tests with disable legs, and the redaction collision case is restored with a non-exempt name. FR-230 phase-3 evidence is re-minted.
- Assertion-quality sensor, Go and path labels (GH#36, beads forge-plugin-sqlb and forge-plugin-p0js): a Go test that asserts only through a same-file helper marked with `t.Helper()` was flagged as assertion-free. The sensor now resolves same-file helpers that call `Helper()` on a `*testing.T` or `testing.TB` parameter, transitively to eight hops, excluding qualified calls and method receivers, and credits a test only for helper calls inside its own brace-matched body, so a delegation-only helper defined after a test cannot satisfy it. Delegation is the only new way a test clears: the direct-assertion heuristic still scans the unchanged span from a test declaration to the next one, so over the Go 1.26.6 standard library the sensor reports no test that it did not report before (1,736 findings become 1,582: 146 cleared through same-file delegation and 8 string-embedded declarations that were never tests). One linear span pass over the Go source, with comments and string, raw-string and rune literals masked, finds the test and helper bodies, so a commented-out or string-embedded test declaration is no longer reported as a test, and Go findings now report the `func Test` line instead of the preceding blank line. A present test path whose label is not printable now fails with the FR-144 execution literal (exit 2) instead of crashing or printing raw bytes. Correction to the hermetic test git entry below: the commit-guard teardown waits on pending telemetry markers and on processes whose working directory is inside the scratch tree, uses the process group only for the deadline kill, and kills remaining workers when the 60-second hang guard expires.
- CI reliability P1 follow-ups (beads forge-plugin-eu83.16 and forge-plugin-eu83.18): the CI provider-stub audit failed open when its launch log was missing; `install-stubs` now records the log path in an installation marker, and `stub-audit` fails when stubs were installed but the log or marker is missing, unreadable, not a regular file, or names a different log. The `tests/test_git_env.py` disable legs, which run git unquieted on purpose, now drain the detached maintenance they start before their temporary directories are removed.
- Typed launch follow-ups from chain I's review-final (bead forge-plugin-wj3f): the orchestrate skill now states that a global `AGENT_HALT` refuses `forge launch`, `launch collect` and `launch cancel`, and that scoped halts are not consulted; `launch collect` refuses a worktree with a non-UTF-8 path name or more than 1 MiB of path listings with a remediation, instead of a permanent unavailable-facts refusal; a launch brief must be given as its canonical path and be an owner-owned regular file that is not world-writable and not group-writable unless the group is the owner's private group (the same rule as route paths); it is opened without following a leaf symlink and without blocking on a FIFO, and the opened descriptor's path must equal the checked canonical path, closing an ancestor-symlink swap between the check and the open (defined in FR-034). The FR-230 phase-3 evidence is re-minted. Correction to the chain I entry above: only FR-245 carried a chain-I deferral marker; FR-034, FR-080 and DM-018 were amended in place.
- CI reliability, hermetic test git and guard worker quiescence (beads forge-plugin-eu83.3 and forge-plugin-eu83.4, operator rulings 2026-09-29): git 2.55 on the CI runner starts detached `git maintenance run --auto` after commits, pushes and fetches in fixture repositories, which raced test cleanup and directory walks. The new `tests/_git_env.py` writes a quiet repository-local configuration (maintenance, gc and receive auto-gc off) that survives the `GIT_CONFIG_*` scrubbing production code performs, merges an idempotent `GIT_CONFIG_*` tail into test environments, and is adopted by the shared fixtures, with a ratchet that lists the files still to adopt. The new `tests/_worker_quiescence.py` makes `tests/test_commit_guard.py` wait for the commit guard's detached telemetry workers by process group, revalidated by PGID and start time, and fail loudly after a 60-second hang guard instead of deleting their directory under a live writer. Tests only. Correction to the FR-230 rerun entry below: the structured result records a bounded output tail, but the reported issue carries only the reason and elapsed seconds (bead forge-plugin-zybw).
- CI reliability, drift off the push path and CI observability (beads forge-plugin-eu83.1 and forge-plugin-eu83.7, operator rulings 2026-09-29): main forge-ci ran Gate 1 twice per push (the Gate 1 step, then the drift step's clean-tree Gate 1), which doubled exposure to every flaky test, and the drift step discarded the failing module's output, so six red builds were unattributable. forge-ci now runs Gate 1 once per push and gains `workflow_dispatch`; drift runs in the new `.github/workflows/forge-drift.yml` on its weekly schedule and on demand; and `scripts/forge/drift-check.sh` prints the failing Gate 1, Gate 2 or invariant module lines, the outcome kind and a bounded output tail to stderr on failure while its stdout stays the FR-161 JSON. The new `scripts/ci_diagnostics.py` adds an environment fingerprint, fail-loud `claude`/`codex` stubs first on `PATH` for the test steps with a final audit that fails the job if any stub ran (the real CLIs are installed off `PATH` for the version check), a diagnostic single-module rerun after a failure that labels it FLAKE-SUSPECT, REPRODUCIBLE or INCONCLUSIVE and can never turn the job green, and step-boundary process and temporary-space snapshots uploaded as artifacts. The one phase-0 test that reached the host `claude --version` is now hermetic.
- Changed-path derivations include rename sources (GH#35, bead forge-plugin-d8qp): porcelain `git diff --name-only` detects renames by default and reports only the destination, so merge candidate observation, unbound merge generation, the merge observation step program and the merge and legacy commit ingest proofs could miss the source path of a rename (a control path moved out of scope, for example). Every name-listing call now passes `--no-renames --no-ext-diff --no-textconv`, matching commit-time observation; patch and digest argv are unchanged.
- CI reliability, FR-230 live rerun and contention tests (beads forge-plugin-eu83.2 and forge-plugin-eu83.5, operator rulings 2026-09-29): the FR-230 phase-3 validator's live rerun of each bound test now reports why a rerun failed (`timed_out`, `output_exceeded`, `stream_failed`, `remaining_group_after_exit`, `cleanup_not_proven` or `returncode N`, with elapsed seconds and a bounded tail) instead of a bare `unresolved`, and its hang guard is 120 seconds (measured: 11.7 s unloaded, 45 s at 4x CPU oversubscription; the 40-second guard failed main CI on 109c565). The stale-lease recovery test and the fr223 distinct-action flood test no longer depend on sub-second scheduling or on the full production parse budget under contention; every assertion is kept and `PARSE_TIME_BUDGET_SECONDS` is unchanged. The FR-230 phase-3 evidence is re-minted.
- Small test and CI hardening (beads forge-plugin-yot4, forge-plugin-xfsd, forge-plugin-4yz0): the rename-listing contract test in `tests/test_worktree_merge_skill.py` is split into named helpers with the same mutants; the hermetic review guard builds a provider-free `PATH` and names the remediation when a provider CLI shares a directory with git; both CI workflows check out with `persist-credentials: false`, pinned by a stdlib regression test, so third-party install scripts no longer run with the token in `.git/config`; `default_acl_risk` gains a test for its refusal when `os.fstat` fails.
- Reviewer bodies end with the verdict block (bead forge-plugin-gv7b) and the chain-I-dependent prose is current (routing P task-02, bead forge-plugin-4g68.13): since the rk0x lane fix the engine extracts the verdict block from the end of the reviewer's final message and fails closed on anything after it, but `agents/review-final.md` put `Iteration:` beside the verdict and both review-cheap prompts ended with the six handoff headings. Every reviewer body now states that the verdict block is the final content, with `Iteration:` and all headings before it, states a fallback grammar matching the engine's verdict transport for callers that supply none, and the three runtime output-contract templates describe the verdict line without a copyable prefixed placeholder. The tracked installed copy `.codex/prompts/review-cheap.md` is synced with its template, and the new `tests/test_installed_prompt_sync.py` pins all nine verbatim Codex installer pairs byte-for-byte. README, OPERATIONS, UPSTREAM, the founding-decisions footnote, the review-final frontmatter note and the orchestrate review reference now describe typed `forge launch` for the implementer and plan roles and the reviewer-only manual path. The FR-230 phase-3 evidence is re-minted for the changed engine subjects.
- Commit drift preflight and index flags (bead forge-plugin-7hj9): `git diff` does not compare index entries flagged assume-unchanged or skip-worktree, so the engine's tree/index drift preflight could not see them, and the assertion-quality sensor could then read working-tree bytes that differ from the staged candidate (an assertion-free staged test passed behind an assume-unchanged flag; a skip-worktree entry with a deleted working file was skipped). The preflight now also lists the candidate paths with `git ls-files -v` and refuses every flagged entry with its path and the remediation (clear the flag, then restage); both git calls run with `core.fsmonitor=false` and literal pathspecs. The FR-230 phase-3 evidence is re-minted for the changed `chain_core/_repository.py` subject (five fixtures, manifest result digests and the manifest byte pin; generation stays 1).
- Route config ownership test fixtures (CI red since ap0g, 9be446b): the fixtures asserted the modes git itself creates for `.git/info`, `info/exclude` and `.forge`, but the GitHub runner's git template creates `info/exclude` at 0755, so 19 `tests.test_route_config` cases failed on CI while passing locally; the fixtures now set the intended modes explicitly, and the tests pass at umask 022 and 002 and with a 0755 exclude template. Production code is unchanged.
- Engine review lane scope and timeout (operator ruling 2026-09-28): since the Claude reviewer cells run with permission checks bypassed, the lane reviewer on routing chain P ran a full serial unittest discovery that Gate 1 had already run on the same candidate and was killed at the 1200-second review timeout, which collect records as a synthetic BLOCK. The engine prompt now derives a Gate 1 scope paragraph from the chain's current-candidate record: after a passed run it says full discovery passed on that exact candidate, cites the run's recorded output digest and tells the reviewer not to re-run discovery or the Gate 1 cell but to run focused modules and its own disable checks; after an operator or docs-class skip it states the recorded reason and leaves test choice to the reviewer; any other state refuses the review request with `forge: review request refused — no truthful current-candidate Gate 1 scope record` (FR-246). The FR-245 review profile timeout rises to 2400 seconds; the merge-gate and fresh-reviewer-evaluation timeouts are unchanged; FR-230 phase-3 evidence is re-minted.
- Route config under umask 002 (forge-plugin-ap0g): `init` and `probe` now refuse a route path only when a user other than the owner can write it. A group-writable route directory or `info/exclude` (such as `.forge`, `.forge/local`, `.forge/tmp`, `.git/info` and its `exclude`) is accepted when its group is the owner's private group, the owner and group are enumerable, and neither an access ACL nor, on the exclude parent, a default ACL is present; the predicate lives in `scripts/forge/route_config_git.py`. Other-writable, foreign-owned, shared-group, non-enumerable and ACL-bearing paths, and group-writable paths on platforms without `os.listxattr`, stay refused with unchanged diagnostics. Residual: a directory service that hides other members of the owner's group cannot be detected, and account lookups are synchronous and unbounded. The FR-244 routes-file rule is unchanged and the route_config fixtures pin umask 022.
- Hermetic review tests and CI provider CLIs (forge-plugin-wvnc, operator direction 2026-09-28): after routing chain E a review request launches the real reviewer executable, so `tests.test_fresh_reviewer_cli` failed on CI (no `claude` binary) and on a developer host could reach the real, authenticated CLI; the test now installs a fake Claude provider, patches the engine executable and asserts the launch, and `tests/test_review_lane_hermetic.py` guards the review path with `claude` and `codex` stripped from `PATH`. `forge-ci.yml` installs the pinned `@anthropic-ai/claude-code@2.1.283` and `@openai/codex@0.155.1` through a SHA-pinned `actions/setup-node` before Gate 1, with no credentials; tests stay hermetic.
- Engine review lane verdict transport and Claude reviewer permissions (forge-plugin-rk0x P0, forge-plugin-ig69; operator rulings 2026-09-28, landed by operator override): an engine-launched reviewer's final message is a full review record, but collect applied the verdict-first transport grammar to the whole message, so every real Claude review-final PASS became a synthetic BLOCK. Collect now extracts the single trailing verdict block (the last exact `VERDICT: PASS|BLOCK` line followed only by `candidate:`, `package:` and `finding:` lines) on both lanes and fails closed on zero or several exact verdict lines (a quoted one included), any other line beginning with `VERDICT:`, or any other trailing line; the raw message stays byte-identical evidence and a separate `verdict_transport_digest` binds the block, and the engine prompt states the required final-message format, including that no other line may begin with `VERDICT:` (FR-246). Both Claude reviewer cells now launch with `--dangerously-skip-permissions` and `--no-session-persistence`, and without the ignored `LS` tool: in the CLI's default mode `--permission-prompts none` denied every command it could not classify as read-only, including `python3 -m unittest`, so the execution-capable reviewer could not run tests, and each run persisted its unredacted transcript under `~/.claude/projects/` (FR-245); the no-write boundary stays instruction-bounded. FR-230 phase-3 evidence is re-minted.
- Activation replay cap (operator ruling 2026-09-27): the chain event-log cap that journal activation scans apply during binding replay rises from 8 MiB to 64 MiB, because routing chain E's landing chain grew an 8,433,733-byte event log (each event embeds a full state snapshot; bead forge-plugin-6f70) and every verb on that chain, including status, abort and tombstone, refused with `forge: journal append refused — invalid journal record`; the exact-cap and cap-plus-one boundary stays fail-closed.
- Assertion-quality sensor (forge-plugin-lhop, GH#33): a deleted touched test path prints `forge: deleted test path skipped: <path>` once and is not assessed, so a candidate that deletes tests no longer fails the sensor; absolute, option-shaped and non-printable absent labels, present non-files and unreadable inputs keep the FR-144 exit-2 failure literal, and deletions emit no assertion telemetry.
- Route evidence hardening (forge-plugin-wy8n): the session transcript behind `run_started.orchestrator_model` is opened with `O_NOFOLLOW` and `O_NONBLOCK` and must be a regular file, so a FIFO, directory or symlink at that path degrades to reason `unreadable` instead of hanging typed run-open; `validate_execution` loses its unreachable historical branch; and a missing canonical role is refused through the journal's structured refusal instead of an assert that `python -O` strips.
- Route evidence (forge-plugin-577d) validates transcript, `run_started.route` and `run_started.orchestrator_model` model ids with `route_vocab.MODEL_ID_RE`, the grammar the specification cites, instead of `route_config.MODEL_RE`; a test pins `route_config.MODEL_RE` to that grammar and proves every route_evidence site reads it, and the vocabulary reader tests (forge-plugin-4g68.16) assert the exact unknown Claude execution-role hard error beside the Codex one.
- Run scope and run-bound candidate validation (forge-plugin-dn9e) now admit the DM-007 committed `.forge/evals/` and `.forge/history/` subtrees while continuing to refuse transient roots and every other `.forge` child; the specification carries the Revision-16 FR-192/FR-014 amendment, and FR-230 phase-3 result evidence is re-minted for the changed `candidate.py` subject (five fixtures, manifest result digests, and the manifest byte pin; generation stays 1).
- Run-bound fresh reviewer evaluations (forge-plugin-4w5o) now keep the outer journal lock visible to worker-thread durability probes: the formerly thread-local active-lock registry is context-propagating and every fresh-evaluation worker runs under its own copied context. Unbound chains and single-threaded paths are unchanged; the FR-230 phase-3 result evidence is re-minted for the changed fresh_evals.py subject (five fixtures, manifest result digests and the manifest byte pin; generation stays 1).

### Changed

- Journal-only close-preflight line (diuy Stage 1 slice S8, spec Revision 18): run-bound `status` (its final chain-state message), a final successful `verify` and the two PASS-capable `review collect` paths now end their human message with `; ` and a labelled `close preflight (journal-only): ...` summary of the same projection `journal close-preflight` makes, without the terminal-chain guard (the line says so): the issue count and first issue, `no issue found; terminal chain guard not run`, `run is not open` for a closed run, or `unavailable` when it cannot be computed or a projected chain has no bound verification record. `review attach`, unbound outcomes, BLOCK outcomes and every exit status are unchanged, and the `journal close-preflight` JSON keeps its schema. The named control is `close-preflight-line`. The advisory close observations planned with it are deferred (bead forge-plugin-diuy.4).
- Result before gate, and close-projection warnings (diuy Stage 1 slices S6 and S7, bead forge-plugin-7154, spec Revision 18): in a run activated by `forge-journal-binding/1`, the commit-family run-bound verbs `commit start`, `commit restage`, `commit rebase`, `verify`, `gate run` and `review request` now refuse while an overlapping mutating execution of the run (the chain's task, or one whose files overlap the candidate) has no terminal `execution_result`, with reason `execution-result-pending` (the 55th `forge-cli/2` reason) and a remediation that names `forge launch collect` for a typed launch or the typed `execution-result` builder otherwise, with identifiers shell-quoted (FR-249); the existing missing-result legacy tolerance applies, restage paths are normalized before the overlap check, a failure of the inspection itself refuses as `run-task-binding-invalid`, and merge-family verbs are not hooked; a pending execution that does not overlap only prints a warning when the command proceeds, at most once per invocation, and never on a refused command. After a successful typed `execution-start`, `execution-result` or `task-finish`, and after typed `launch`, `launch collect` and `launch cancel`, stderr now warns when the run could no longer close as passed, computed from one shared-lock snapshot after the append against a pre-append baseline, waiting at most ten seconds for the lock and skipping the warning otherwise; a typed launch prints it only after the wrapper has spawned (close-projection-warning). The named controls are `result-before-gate` and `close-projection-warning`.
- Legible ingest refusal (diuy Stage 1 slice S3, bead forge-plugin-78l, spec Revision 18): when `journal ingest-chain` refuses because an ordered FR-210 proof fails, the diagnostic now names it as `forge: journal ingest refused — chain proof is invalid: proof <n> <name>: <observed>`, where the old literal is the exact prefix, `<n>` and `<name>` are the failing proof's position and FR-210 name (proof 0 for a failure before proof 1), and `<observed>` comes from a closed five-member vocabulary. Under `--verbose` only, the structured observation adds a scripts-relative `module path:line` raise site and exception class names, never an exception message. The logic lives in the new stdlib-only `scripts/codex_orchestrator/ingest_refusal.py` as the named control `proof-named`; progress from an earlier verifier pass never leaks into a later refusal. Once all sixteen proofs have passed, in both the commit and the merge verifier, any later consistency refusal keeps the bare literal instead of being attributed to a proof.
- A failed gate is cleared only by a pass on its own or a landed candidate (diuy Stage 1 slice S5, spec Revision 18): in a run activated by `forge-journal-binding/1`, a later passing verification now clears a failed Gate 1, Gate 2 or Gate 3 record under FR-022 only when it has the identical criterion, a valid binding that is not retired (no bound `chain-abort` decision for its own task and chain, tombstone dispositions included, and not superseded), and the failed record's own chain and candidate or those of a bound `chain-landing` decision; an unbound failure is cleared only by a pass on a landed candidate. Before, any later identical-criterion pass counted, including one on an aborted chain. Failed records are never retired, the diagnostic and legacy tolerance are unchanged, and the rule is the named control `landed-recheck-source`; over the recorded run journals only run-20260923-route-v2 gains two issues.
- Run-close legibility and run-bound Gate 1 for docs-class candidates (diuy Stage 1 slices S1 and S2, bead forge-plugin-8f0x, spec Revision 18): the new read-only `journal close-preflight --repo <repo> --run-id <run-id> [--chain <chain-id>]` verb projects a passed close through the same close law as `run-close` (run-close validation and the gate profile, the terminal-chain guard and FR-247, optionally with one chain's landing, approval and task completion projected) and prints one bounded JSON object; it takes only shared locks, opens existing chain locks without creating them, and never writes (FR-248). A refused passed `run-close` now keeps its old literal as the exact prefix and adds the first validation issue and `(+N more; run journal close-preflight)`, and a blocked close prints the would-be passed-close issues as capped stderr notices without changing stdout. A run-bound docs-class candidate now runs Gate 1 instead of recording the Revision-17 skip, so a docs-only landing can close a run as passed; unbound candidates and ingested chains keep the recorded skip.
- Passed run close counts only the landed candidate's gate evidence (diuy Stage 1 slice S4, spec Revision 18): in a run activated by `forge-journal-binding/1`, a passing Gate 1, Gate 2 or Gate 3 verification now satisfies the FR-021 run-level requirement only when its binding is valid, it is not retired (no bound `chain-abort` decision, tombstone dispositions included, exists for its own task and chain, and it is not superseded), and its chain and candidate are those of a bound `chain-landing` decision of the run. Before, any passing gate record after the last mutating execution counted, including one on an aborted chain. The rule lives in the new `scripts/codex_orchestrator/landed_evidence.py` as the named control `landed-candidate-evidence`, and binding correlation now uses the same task-scoped retirement. Legacy runs, diagnostics and the zero-mutating-execution exemption are unchanged; over the recorded run journals, only run-20260927-route-f projects two more issues.
- Reviewer and launch wrapper hardening (forge-plugin-ig69 items 4-7; operator rulings 2026-09-29): the provider wrapper no longer redacts the non-credential values `USER`, `LANG`, `LC_ALL` and `TERM`, so reviewer verdicts and implementer handoffs keep `agents/**` paths verbatim instead of `<redacted:USER>/...`; every other passed value, including `HOME`, `TMPDIR`, `PATH` and every credential-class name, stays redacted in raw and JSON-escaped form (FR-245, FR-246). The measured Claude Code floor rises to 2.1.283, whose `--effort` help lists `xhigh`, and FR-245 records the accepted gap that effort is not observable in the Claude stream. The ignored `LS` tool is removed from the review-final, review-cheap and plan tool lists and from the route probe (FR-111). A Claude stream whose first event is not the `system`/`init` event, or whose init `permissionMode` or `tools` set differs from the value derived from the digest-bound argv, now stops the child through the early-stop path and completes as `claude init mismatch`, which the review lane turns into a synthetic BLOCK and launch collect maps to a failed result; the argv derivation refuses duplicate, missing, empty or option-shaped `--permission-mode` and `--tools` values and a bypass flag combined with an explicit permission mode (FR-246). FR-230 phase-3 evidence is re-minted.
- Python code-line budget (operator direction 2026-09-28): the per-file budget rises from 500 to 1000 code lines because the 500-line limit was distorting code quality; `scripts/check_file_length.py` defaults to 1000 (`REFACTOR_MAX_LINES` and `--max` still override), `CLAUDE.md`, `AGENTS.md` and the `pyproject.toml` guardrails comment say so, and the 42 `.refactor-baseline.json` grandfather entries now within budget are removed while files above 1000 stay grandfathered. The ruff complexity limits are unchanged, and skill files were never subject to the line budget.
- Review-lane prose (routing chain P task-01, forge-plugin-4g68.13; also forge-plugin-uvh6 and the skill half of forge-plugin-d8qp, GH#35; operator rulings 2026-09-27): `/forge:commit` Step 4 selects `review-cheap` for standard and `review-final` for hard candidates, launched only by the engine lane (`forge review request` then `forge review collect`) on the persisted chain, with iteration accounting that counts one bound verdict (including a synthetic BLOCK) per iteration; without a persisted chain the skill completes only fast candidates. `/forge:worktree-merge` keeps its interactive review-final under the FR-246 deferral, lists changed paths with `--no-renames --no-ext-diff --no-textconv` so a rename reports both paths, and notes deleted test paths in the Gate 2 sensor. The orchestrate review reference, `OPERATIONS.md` and design note 0003 describe the engine-launched gate reviews; `tests/test_review_lane_prose.py` pins the prose with disable legs.
- Reviewer-facing eval triggers (operator rulings 2026-09-27, policy task E0 of routing chain E, run-20260927-route-e): the `reviewer-routing` and `model-provider-version` rows now name `scripts/forge/route_config.py`, `route_config_git.py`, `route_config_probe.py` and `route_vocab.py`, in the specification table (with a dated amendment sentence), `forge-project.md`, the rendered template and `policy.py`, so any change to route resolution triggers fresh reviewer evaluations; the FR-230 phase-3 evidence is re-minted for `policy.py`.
- Revision 17 follow-ups (forge-plugin-9a5k): `OPERATIONS.md` describes Gate 1 once per candidate; the `AGENTS.md` region mirror matches `forge-project.md`; an unreadable `/proc/pressure/cpu` counts as no pressure signal so the Gate 1 cell proceeds instead of failing; `.refactor/type-baseline.json` is control class with its own trigger row.
- Host policy (operator direction 2026-09-27): Codex implementer executions share one host-wide pool of 8 across forge-plugin and omnipus-ai, taken through `sem-run impl --slots 8`, replacing the prose cap of 4 in the `agent-project-context` region of `forge-project.md`.
- Governance (Revision 17): Gate 1 runs once per candidate and not for docs-class candidates, whose skip is
  recorded under the `gate-1` ID with reason `docs-class candidate` (FR-214/FR-215/DM-013; the pair-voiding rule
  and `_void_mismatched_gate_one_pair` are retired); the Gate 1 cell is a duration-balanced work queue over
  `min(8, cpu)` workers that takes the host gate slot and waits out CPU pressure (bead forge-plugin-pwy, revised);
  a review PASS is bound to the candidate, not to a 30-minute clock (bead forge-plugin-er3, GH#21); mypy runs as
  a python stack validation against the tracked `.refactor/type-baseline.json`, re-minted at 640b5dd with the
  cell's exact invocation (keys normalize embedded line references and counts ratchet per key); a
  docs-contract stack validation runs the prose-contract modules for any candidate touching a docs-class
  path, so the docs-class skip never lands untested prose; `CHANGELOG.md` joins the fast tier; the host concurrency cap is recorded in
  `agent-project-context`; the gate-evidence predicates move from `chain_core/_commit_chain.py` to
  `chain_core/_gate_evidence.py`; the journal builders' replay copy of the Gate-1 rule follows the same
  single-observation semantics; the FR-230 phase-3 result evidence is re-minted for the changed engine and
  chain_core subjects and the new `_gate_evidence.py` subject (five fixtures, manifest result digests, and
  the manifest byte pin; generation stays 1). Riding along because the new Gate 1 cell exposes it on every
  run (bead forge-plugin-hwbt): `route_config_probe._write_brief` tolerates a broken pipe on close and
  `route_config_git.run_git` closes its pipes through a `with` block; both hunks are verbatim from routing
  chain J's staged candidate so its lift stays conflict-free.

### Release notes

- 0.7.0 is the per-developer model routing release. Each clone may opt in to its own `.forge/local/routes.toml` (provider, model and effort for the implementer, review-cheap, review-final and plan roles); without it the committed defaults apply. New typed `forge launch`, `launch collect` and `launch cancel` verbs start the resolved Codex or Claude route as a detached, process-group-contained wrapper, and `review request` launches review-cheap or review-final on either provider through the engine review lane. `review attach` is retired for every new request; `review collect` is the remedy.
- Spec Revision 18 makes a passed run close stricter and more legible: only the landed candidate's gate evidence counts (FR-021) and a failure clears only on its own or a landed candidate (FR-022); the new read-only `journal close-preflight` verb projects a passed close; a run-bound docs-class candidate now runs Gate 1, so a docs-only landing can close a run as passed; and the commit-family gating verbs refuse with `execution-result-pending` (the 55th `forge-cli/2` reason) while an overlapping mutating execution has no terminal result.
- **Consumer actions.** Claude Code 2.1.283 or newer and Codex CLI 0.155.0 or newer are required and enforced by `/forge:init`, `review request` and `launch`; review-final needs an authenticated `claude` CLI on `PATH`. After updating, run `/forge:init`, or run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/route_config.py" init --repo "$PWD"` and then `probe --repo "$PWD"` from the repository root, to opt in to routes. New journal execution writes still refuse the legacy vocabulary spellings listed under 0.6.14 below (for example `--role implementation`); move launchers to the canonical ids first.
- **Downgrade.** 0.6.14 cannot collect a 0.7.0 review. Finish each chain on the version that requested its review, and roll back only when no chain is reviewing and no run opened under 0.7.0 is still open.
- **Plugin cache.** Several commits shipped under the 0.6.14 version string, so a 0.6.14 plugin cache may hold older bytes than its install record claims (GH#37). The 0.7.0 string refreshes it. By operator ruling of 2026-10-02 (bead forge-plugin-6j08, option B), the first commit after this release drops the manifest version field so that plugin caches and updates track commits; releases are then identified by the `CHANGELOG.md` heading, the `pyproject.toml` version and an annotated `vX.Y.Z` tag, which consumers may pin for release-only updates.

## [0.6.14] - 2026-09-24

### Changed

- New journal execution writes refuse the legacy role spellings `implementation`, `implement`, `review`, and `reviewer`; provider `codex-cli`; event sources `codex`, `agent-tool`, and literal `*/events.jsonl` paths; sandbox-as-mode values `read-only` and `workspace-write`; and noncanonical mode `orchestrator-inline`. Writers now use the canonical route vocabulary and the optional `sandbox` field, while historical readers retain compatibility.
- Specification Revision 15 defines the deferred per-clone routes file, eight provider/role profiles, headless review-final lane, route/task provenance, and mirrored routing trigger policy; every new FR/DM retains its chain-specific implementation-deferral marker.
- Refactor (tests): `tests/test_revision8_coordination.py` (4,905 code lines, one class `Revision8CoordinationTests` with 112 methods) is decomposed with the refactor-python `decompose` skill (0.1.3) in test shape (bead forge-plugin-25ms, plan `.refactor/plan-revision8.md`): the 31 helpers move verbatim into the support mixin `tests/_revision8_support.py` (539 code lines) and the 81 tests into seven scenario modules in class shape, `tests/test_revision8_{orphan_identity 809, append_schema 712, registry_races 618, precedence 609, rollback 583, interruptions 566, successors 533}.py`, each class inheriting the mixin, with both collectors' test IDs mapped 1:1 (`.refactor/idmap-revision8-*.json`); the source keeps a docstring-only shell that collects no test. One hand-written preparation commit precedes the moves (the preamble constants `ROOT`, `TOOLS`, `RECORDED_AT` relocated verbatim into `tests/_revision8_constants.py`, which also carries the `sys.path` bootstrap so every new module imports standalone without `PYTHONPATH`), and every mover call passes `--import-root "$PWD"` so the generated imports read `from tests._revision8_...` (the plugin's default writes a bare module name the Gate 1 cell cannot import). Two operator-ruled config changes ride with it: `pyproject.toml` gains `[tool.ruff.lint.isort] known-local-folder` for the `scripts/`-resident packages (`codex_orchestrator`, `codex_orch_tools`, `forge_cli`, `commitment_paths`), so a generated header imports the bootstrapping constants module before them (zero new isort findings repository-wide), and `tests/test_migration.py`'s legacy-runtime-name scan carves out `.refactor/` (the tracked test-tree snapshots carry that test's own name; evidence shipping is bead forge-plugin-xlt7). The temporary ruff globs are replaced by measured per-module entries and the eight new modules are pinned in `.refactor-baseline.json` at their measured sizes; no production file changed, no mint. At reintegration the isort ruling re-sorts one import block in `tests/test_vocab_readers.py` (added by 0.6.13 after the split was measured); that is the only file outside the split the branch edits. Follow-up: forge-plugin-7pzp (split the mixin by role; decide the empty shell).
- Refactor (tests): the `Revision9BuilderBatchTests` class in `tests/test_revision9_coordination.py` (13,222 code lines; 147 methods, 109 tests) is decomposed with the refactor-python `decompose` skill (0.1.3) in class shape (bead forge-plugin-6g67, plan `.refactor/plan-revision9-coord.md`): 18 helpers shared by two or more scenario families move verbatim to the mixin `Revision9BuilderBatchSupport` in `tests/_revision9_coord_support.py` (806 code lines) and 108 tests plus 20 family-private helpers move verbatim (LibCST mover, manifest-verified AST oracle, `--strict-bodies`, one commit per family, test IDs mapped 1:1 in both collectors) to twelve sibling modules `tests/test_revision9_coordination_<family>.py` — cli_diagnostics 230, batch_builder 576, scope_change 521, gap_repair 760, staging_crashes 536, chain_drain 424, terminal_builder 655, legacy_activation 896, receipted_chain 799, activation_scan 618, activation_outbox 790, ledger_recovery 810 — whose classes inherit the mixin; the source keeps the other three classes and the one `unittest.skipUnless` test the mover refuses (4,931 code lines; `Revision9BindingTests` and `Revision9MergeTransitionGrammarTests` are follow-up forge-plugin-z50i). Non-move commits: one hand-written preparation commit moves the module's preamble constants and `key()` verbatim to `tests/_revision9_coord_constants.py` (the plugin's rope mover cannot relocate `Path(__file__)`-derived constants); every mover call passes `--import-root "$PWD"` so destination imports read `from tests._revision9_coord_...` (the plugin's default writes a bare name the Gate 1 cell cannot import); the branch relies on the `[tool.ruff.lint.isort] known-local-folder` ruling and the `.refactor/` carve-out in `tests/test_migration.py` already landed with the revision8 split above (both operator rulings of 2026-09-23; the ruling makes a generated header import the constants module, which puts `scripts/` on `sys.path`, before `codex_orchestrator`, so each new module imports standalone without `PYTHONPATH`); the temporary ruff globs for the new modules are replaced at finalize by measured per-module entries, the source entry shrinks to the six codes it still trips, and the size baseline pins the source and the eleven modules over 500 at their measured sizes. No body, docstring, decorator or assertion changed; no production file changed; no mint.

### Release notes

- 0.6.14 is the routing plan's vocabulary **writers** release (chain V2): new journal `execution` records must carry the canonical ids — `role` implementer | review-cheap | review-final | plan | monitoring, `provider` codex | claude, `event_source` exec | claude, `mode` headless | detached | subagent | teammate, optional `sandbox` workspace-write | read-only | instruction-bounded. The typed builders refuse a legacy spelling on a new write with a diagnostic naming the canonical id. Refused values: `implementation`, `implement`, `review`, `reviewer`, provider `codex-cli`/`openai`, `event_source` `codex`/`agent-tool`/a literal `events.jsonl` path/`manual`, mode `orchestrator-inline`, and `read-only`/`workspace-write` used as a mode; of these, the peer corpus (152 executions, counted 2026-09-22) carries `implementation` x68, `(claude, implementation)` x29, `agent-tool` x27 and `orchestrator-inline` x1, while `openai` and `manual` were never mapped spellings and occurred only as this repository's own test-fixture literals. Historical records are never rewritten and keep reading through the 0.6.13 map; downgrade below 0.6.13 after 0.6.14 records exist is not supported.
- Consumers whose launchers still pass legacy spellings (for example `--role implementation`) must move to the canonical ids before adopting 0.6.14; 0.6.13 readers accept both, so the order of the two upgrades does not matter.
- Also ships spec Revision 15 (FR-244..247, DM-018: per-developer routes file, provider profiles, headless review-final lane, task-completion provenance — authority only, implementation deferred to the 0.7.0 chains) and the revision8/revision9 test-file decompositions (no behaviour change).

## [0.6.13] - 2026-09-23

### Changed

- Historical route readers now accept legacy and canonical role, provider, and event-source vocabulary through one shared normalizer.
- Refactor (app): the `MergeEngine` class in `scripts/forge/forge_cli/app/_merge_engine.py` (10,302 code lines, 93 methods) is decomposed with the refactor-python `decompose` skill (0.1.2) in function shape (bead forge-plugin-37fr): 86 method bodies move verbatim to 27 `app/_engine_*.py` seam modules and the class keeps same-named class-body bindings, so every `MergeEngine.<name>` attribute, patch target, verb, diagnostic and reason code is unchanged; the shell ends at 224 code lines. A second wave then extracts nine declared statement ranges (rope, oracle-checked) into three `app/_engine_*_steps.py` siblings and in-module helpers. Four config/type prep commits precede the moves (a temporary `app/_engine_*.py` ruff glob replaced at finalize by measured per-module entries; the `_recording_common_lock` return annotation corrected from `Iterable` to `Iterator`, type baseline 241 to 234; provisional size-baseline entries for the three single-method modules over 500, pinned at finalize to 830/584/578), and one mechanical non-move commit unquotes the mover's string receiver annotations. Consequences for reflection, none of which the repository reads: moved functions report `__module__` under their seam module and lose the `MergeEngine.` `__qualname__` prefix (plain moved functions still pickle by their new qualified name; the one new pickling failure is the `contextlib.contextmanager(...)` wrapper bound as `_recording_common_lock`, 2 of 93 attributes failing at the tip against 1, the `store` property, at baseline), and `typing.get_type_hints()` raises `NameError` on the 75 moved instance/class methods because their receiver annotation names `MergeEngine`, which the seam modules import only under `TYPE_CHECKING`. The 30 new modules are FR-230 production subjects (manifest, fixtures and byte pin re-minted); `app/__init__.py` and `__all__` are byte-identical; no test edits. Follow-ups: forge-plugin-c4l4 (remaining tier-2 ranges), forge-plugin-g8kf (closure state object).
- Refactor (engine): the `Engine` class in `scripts/forge/forge_cli/engine/_engine.py` (3,574 code lines, 41 methods) is decomposed with the refactor-python `decompose` skill in function shape (bead forge-plugin-321p, plan `.refactor/plan-engine-class.md`): 33 verb-method bodies move verbatim (LibCST, manifest-verified AST oracle, `--strict-bodies`, one tier-1 cluster per commit) into nine modules — `_verbs_tombstone.py` (346 code lines), `_verbs_status.py` (275), `_verbs_lifecycle.py` (429), `_verbs_gate.py` (458), `_verbs_gate_evals.py` (377), `_verbs_decision.py` (327), `_verbs_review_request.py` (458), `_verbs_review_collect.py` (398), `_verbs_finalize.py` (395) — and `_engine.py` keeps the class shell (324 code lines: `__init__`, the hubs `select`, `_preflight`, `_wrong_state`, `next_step`, `_emit_decision`, the two helpers they call, and one `name = _verbs_<x>.name` binding per moved method, re-wrapped with `staticmethod` or `_serialize_worktree_command` exactly as before), so `Engine.<verb>` lookups, unbound `Engine._profiles_for_path`/`_parse_verdict` calls, `patch.object(Engine, ...)` and `inspect.getsource(Engine.gate_run)` are unchanged; no body, verb, diagnostic or reason-code byte changes; the engine package root and its `__all__` are byte-identical. The nine modules are FR-230 production subjects (re-minted); `pyproject.toml` gains one measured ruff per-file-ignores entry per verb module (the temporary `_verbs_*.py` glob that carried `_engine.py`'s grandfathered codes during the moves is gone), the `_engine.py` entry shrinks to the five codes it still trips, a `forge_cli.engine layers` row places the verb modules under `_engine`, the `_engine.py` size-baseline entry (3574) is deleted, and the mypy ratchet drops 251 -> 241 (ten grandfathered checks inside moved bodies no longer fire because a moved function's `self` is untyped; tracked as debt with a follow-up bead).
- Refactor: `scripts/forge/forge_cli/app.py` (11,524 lines) becomes the `forge_cli.app` package — a root `__init__.py` with the verbatim `__all__` and re-exports plus five submodules moved by rope under the AST body oracle (bead forge-plugin-hcuo, plan `.refactor/plan-app.md`): `_mutation_journal.py`, `_admission.py`, `_candidate_observation.py`, `_merge_engine.py` (the `MergeEngine` class, the one new over-budget size-baseline entry at its measured count under the operator ruling on that bead; its class split is a follow-up) and `_dispatch.py`. One non-move edit rides with it: tests patch app-layer controls through one `patch_app` loader helper (E0; the loader sweep rejects raw module patches on app aliases). No body, verb, diagnostic, reason code or `--help` byte changes; the spec's package sentence, the FR-230 production subjects (re-minted), per-module ruff ignores and a `forge_cli.app layers` import-linter contract follow.
- Refactor: `scripts/forge/forge_cli/engine.py` (12,178 lines) becomes the `forge_cli.engine` package — a root `__init__.py` with the verbatim `__all__` and re-exports plus 29 submodules moved by rope under the AST body oracle (bead forge-plugin-2fc, plan `.refactor/plan-engine.md`). Two non-move edits ride with it: the merge bootstrap child resolves `scripts/forge/cli.py` from `runtime.py`'s location instead of its own file depth (E1, with a focused test), and tests patch engine controls through one `patch_engine` loader helper (E0; the hermetic chain fixture assigns the codex executable on every engine module that binds it). The reviewer-facing eval trigger table names `scripts/forge/forge_cli/engine/**` in place of `engine.py` in the spec, the policy constant, the rendered project files and the fixtures; the Revision-9 seam-marker loop moves from the `chain_core` package root to `_commit_chain.py` beside `register_coordination_seams` (bead forge-plugin-4j7, finding CON-02; its grandfathered size entry rises 1840 -> 1847 by operator direction of 2026-09-17); the FR-230 production subjects are the engine package files, re-minted; the size baseline is re-pinned at measured sizes (`engine/_engine.py`, the `Engine` class, is the one new over-budget entry), the ruff per-file ignores are narrowed per engine module, and an import-linter layers contract locks the package's wave order.
- Test isolation (beads forge-plugin-0eq, forge-plugin-ehn): `tests/test_audit_commitments.py` writes its disabled-control mutants of `audit-commitments.py` under a private temp directory (pinning the script's plugin root) instead of beside the real script, so a parallel Gate 1 shard copying the tracked `scripts/` tree no longer races on a vanishing sibling; `tests/test_mutation_runner.py` sets `FORGE_SESSION_PID` to the test process for the runner child instead of inheriting the caller's value, so an exported session identity no longer fails ten tests with a foreign-live-owner refusal.
- chain_core split follow-ups (bead forge-plugin-r0b; review-final findings at reintegration): `scripts/forge/forge_cli/chain_core/_state.py` declares its constants in the historical module order again (bodies unchanged; FR-230 manifest, result fixtures and the v2 byte pin re-minted for the changed production subject); the spec's package sentence names the submodules by the FR-230 manifest's production-subject list instead of the planning document; `pyproject.toml` per-file-ignores drop the dead `chain_core.py` entry and the blanket `chain_core/**` glob in favour of one entry per submodule listing only the codes it trips, and `scripts/check_file_length.py` is cleaned to the full rule set (its entry removed) and gains a focused unittest (`tests/test_check_file_length.py`: hook and plain-mode exit codes, the exact guard diagnostic, and an in-memory control-disable leg); `import-linter==2.15` is pinned beside ruff in the guardrails workflow and the pre-commit setup line. Disclosure: the 0.6.12 reintegration's `.claude/settings.json` also carries `worktree.baseRef: head` and `enabledPlugins: codex-orchestrator@codex-orchestrator` (operator-approved at Gate 4 on 2026-09-14; the plugin entry dangles on a clone without that marketplace). Deferred to the `_commit_chain` split (bead forge-plugin-4j7): moving the Revision-9 seam-marker loop out of the package root, because the grandfathered `_commit_chain.py` may not grow.
- Reviewer-facing eval fixture `review-passes-clean-change` is brought up to the conventions it claims to follow (first fresh-reviewer-evals run since the chain_core split's guardrails landed): its test imports are in the order the ruff I001 gate requires and its diff carries the `CHANGELOG.md` entry the changelog policy requires for added Python files; expected verdict unchanged (PASS). Landed as its own commit because a candidate may not rewrite an established fixture that judges it (bead forge-plugin-r0b).
- Refactor (chain_core): `scripts/forge/forge_cli/chain_core.py` (about 19,300 code lines) is now the package `scripts/forge/forge_cli/chain_core/`: 45 submodules hold the 315 moved symbols with every function and class body unchanged (strict AST oracle 881/881), and the root `__init__.py` keeps the verbatim `__all__` and re-exports every symbol the module defined, so `forge_cli.chain_core.<name>` and the CLI shim's forwarding are unchanged. Unused imports are no longer bound on the package root; test patches of moved controls go through `tests/_cli_loader.patch_chain_core`, which patches every submodule binding the name. The spec's package sentence, the size baseline (eight over-budget chain_core files recorded at measured size) and a `forge_cli.chain_core layers` import-linter contract follow (bead forge-plugin-deb; follow-ups in forge-plugin-r0b and forge-plugin-4j7).
- File categories: `*.js` now belongs to the `config` category (and the changelog gate's code-suffix list), so a tracked JavaScript file such as the chain_core split's Workflow script `.refactor/split-chain-core.workflow.js` matches a category and `tests.test_repo_conformance` file-category coverage passes (bead forge-plugin-g9i).
- Review evidence for the chain_core split is tracked under `.refactor/`: the Codex review transcripts (`codex-review.jsonl`, `codex-review-chain_core.jsonl`, thread `01a0a015-b9f3-7072-9abd-4d4a29f96082`) and their verdict summaries (`codex-review.md`, `codex-review-chain_core.md`), cited by the handback on bead forge-plugin-deb. Evidence only; no runtime surface changes.

### Deprecated

- Legacy route vocabulary on NEW journal `execution` records: 0.6.14 will refuse, with an exact diagnostic, `role` values other than `implementer | review-cheap | review-final | plan | monitoring` (legacy `implementation`, `implement`, `review`, `reviewer`), `provider` values other than `codex | claude` (legacy `codex-cli`; `openai` was never a mapped spelling and stays refused), `event_source` values other than `exec | claude` (legacy `codex`, `agent-tool`, and the literal `…/events.jsonl` path form), and `mode` values other than `headless | detached | subagent | teammate` (`orchestrator-inline` was never mapped and stays refused). Existing records are never rewritten and keep reading through the 0.6.13 map.

### Release notes

- 0.6.13 is the routing plan's vocabulary **readers** release (chain V1): `scripts/forge/route_vocab.py` gives every journal reader one legacy/canonical map for `role`, `provider` and `event_source`; writers are unchanged, so records written by 0.6.12 and by 0.6.13 read identically.
- Also ships (no behaviour change): the Engine and MergeEngine class decompositions, the app, chain_core and engine package splits, the chain_core split follow-ups and the reviewer-eval fixture repair — each itemised under Changed above.

## [0.6.12] - 2026-09-13

### Changed

- Run-bound commit chains no longer freeze at a multi-cell stack gate (GH#23). A stack-validations region with two or more fenced cells recorded one bound journal verification per cell while the replay validator required the whole batch, so `verify` returned `frozen-chain — carried binding fact is stale` after the first cell. The engine now emits one passed bound verification per completed batch, sourced from the final cell; a failed cell still records its failure immediately and stops the batch. Per-cell chain facts, the currentness predicate and non-run-bound chains are unchanged. FR-230 evidence re-minted.

## [0.6.11] - 2026-09-11

### Changed

- Stack-validations grammar legibility (bead forge-plugin-28y, GH#12(f), GH#19): a
  committed Stack Validations region that is present but holds no fenced shell cell
  (the prose shape `/forge:init` 0.6.x emitted) now refuses with its own literal naming
  the region and the required grammar instead of the sentinel's `not configured — run
  /forge:init`; the same literal surfaces on the fresh-reviewer-evals applicability
  reparse; `/forge:init` pins one fenced `bash`/`sh` cell per detected stack category
  and runs an isolated parser-only self-check with the same grammar so it cannot leave
  a prose region behind. Executable policy stays fenced; prose is not accepted. Spec:
  DM-003, FR-061, FR-080, refusal matrix. FR-230 evidence re-minted (policy and
  fresh-evals subjects).
- Legacy-run opening legibility (beads forge-plugin-khu, forge-plugin-2ev; GH#14/#18
  carve-out sharing GH#17's root): a `run-open --record-json` record that carries any
  caller-authored `writer_contract` now refuses before any repository access with one
  legible literal naming the typed `run-open` remedy (the shared activated-writer
  literal is unchanged at its other sites); a contract-less raw open still opens a
  legacy run and prints exactly one stderr notice that its first typed mutation will
  activate it in place; the spec's FR-019 and §8 `run-open` row name the typed form
  as canonical and the record-JSON form as legacy/migration-only, with the refusal in
  the matrix and the docs-contract inventory.
- Chain start on a lock-less legacy run (bead forge-plugin-ayk, review-final MINOR on
  the GH#17 chain): a run-bound `commit start` for a legacy run written by 0.6.10 (no
  `.journal-batch.lock`) refused with the frozen-chain divergence literal; the engine
  and chain store now validate the run, repository and owner with the existing
  predicates, create and acquire the stable batch lock, and revalidate under the
  batch → registry → journal order; nonexistent, foreign-owned or wrong-repository
  runs still refuse without creating a lock; read-only validators stay non-creating;
  run-bound `merge start` uses the same validated creation. The first chain-outbox
  drain then activates a never-typed legacy run in place through the Revision-14
  machinery (activation marker, receipt ledger at the journal origin), so verify,
  review, finalize and later typed mutations proceed; a refused drain leaves the
  chain, its events and the run journal byte-identical with no pending outbox; the
  activation-lineage scan keeps receipt and carried-binding authentication for
  commit-chain siblings. The legacy-open notice is emitted by the raw CLI surface
  only. FR-230 evidence re-minted (engine, chain-store and merge-adapter subjects).
- CI red at e7813cc (bead forge-plugin-eh2): the golden pre-fix wedge recovery test
  resolved the fixture's recorded host repository path through the terminal chain guard,
  so it errored on the GitHub runner where that path does not exist; the test now maps
  the archived chain authority to the restored temporary repository and fails loudly if
  the recorded host path is ever resolved. Fixture bytes and recovery assertions are
  unchanged.
- Mixed-mode journal wedge (bead forge-plugin-kk5, GH#17, GH#18; operator rulings:
  fix the bug with no new verb, and activate in place): a run opened in legacy mode
  and adopted by typed verbs is now ACTIVATED on its first typed use by an appended,
  authenticated `writer-contract-activated` decision written atomically with the
  adopting batch (allocated `decision-NN`, reserved resolution literal,
  `writer_contract`, `receipt_origin_size`/`receipt_origin_sha256`); both activation
  predicates recognise opening or decision activation; receipt-chain validation is
  anchored on the authenticated adoption origin; raw lifecycle writers (append,
  readmit, close, retire) share the first-use guard against a pending
  activation-bearing outbox; `journal batch-recover` repairs one interior
  N-record receipt gap with a single spanning repair receipt, reconciles a spent
  intent without re-applying it, activates a pre-fix legacy-adopted ledger, and
  accepts legacy-written gap records that carry no `run_id` — proven against a
  golden fixture written by the pre-fix code; retrospective ingest can be a legacy
  run's first typed use (shared decision-numbering projection); the scoped-mutation
  runner persists through the typed receipted writer with a deterministic
  idempotency key, never a raw fallback, with an advisory diagnostic on refusal,
  and the merge adapter passes owner identity to the runner while scrubbing it
  from the mutation child; the archive renderer and commitment audit classify
  adopted runs through the shared classifier and render the activation decision
  as lifecycle metadata; the workflow skill documents the typed `run-open` as
  canonical. The first-use reservation scan replays only chains bound to the
  current run, warns and skips unreplayable unrelated history, and byte-bounds
  every chain read (state 1 MiB, events 8 MiB, event-one 64 KiB); the raw
  lifecycle guard refuses only on a pending first-use intent or an
  activation-bearing outbox, so raw `run retire`/`run close` of an unactivated
  legacy run with a stale receipt ledger still work and retire → successor stays
  open; typed first use on such a run refuses with a new legible literal
  (`legacy receipt ledger does not reach journal EOF`) naming the remedy; global
  reconciliation no longer refuses unrelated `run-open` while an adopted run is
  mid-batch or torn. Spec: DM-001, DM-012, FR-011, FR-016, FR-019 (multi-record
  repair, stale-ledger refusal), FR-120, FR-142, §8, refusal matrix, SC-027
  (Revision 14). Disable-in-memory registries `WRITER_ACTIVATION_CONTROLS`,
  `BATCH_GAP_REPAIR_CONTROLS` (`legacy-record-membership`, `multi-record-gap`),
  `MUTATION_JOURNAL_CONTROLS`.
- Guard hook latency (bead forge-plugin-kc9, CI red at 18bbe01): the PreToolUse guard
  now resolves the committed guard-denied-commands rules before direct-invocation
  parsing and runs the Bash-accurate lexer only when denied rules exist, removing
  the per-segment lexing cost that pushed the 2,000-segment flood test past the
  10-second budget on slower CI runners. Hook outcomes, literals, precedence,
  the budget, and the configured-rule path are unchanged; new flood tests pin the
  filled-empty (zero lexer calls), configured (one call, match), and malformed
  (lexer-independent denial) policies.
- Fresh-reviewer events ceiling (first live fresh-evals run, this chain): the
  reviewer child's retained `events.jsonl` stream gets its own 8 MiB ceiling —
  live reviewers' search-command output routinely exceeded the old 64 KiB cap,
  killing judgments before the verdict was written — while `verdict.txt` and
  `completion.json` stay at 65,536 bytes and breach of any ceiling still
  terminates the process group fail-closed (spec FR-149 fresh-reviewer
  amendment + `fresh_evals.py`, with live-shaped regression tests).
- Guard denied-commands region (bead forge-plugin-x0h part 2, operator-requested):
  a new committed `guard-denied-commands` policy region lets the operator list
  additional command shapes the PreToolUse guard refuses outright — matched by
  prefix tokens against the parsed direct invocation under FR-149 committed
  sourcing, denying with `forge: operator-denied command — <reason>`; a
  malformed region fails closed, an absent region changes nothing, and the
  documented coverage is honestly the parser's direct-invocation scope
  (mistake prevention for cooperative agents, not tamper-proofing). The
  region-inventory sweep also fixed the drift checker and chain-test
  inventories and added the manifest entries missed earlier, including the
  reviewer-facing-eval-triggers line absent from `.forge-manifest`.
- Targeted fresh-execution evals (bead forge-plugin-7p4, external-review
  finding 5, operator option c): the recorded eval runner is honestly relabeled
  recorded-baseline integrity, and a new fresh-reviewer-evals chain gate runs
  real reviewer judgments on the nine review-role fixtures — in-session against
  a materialized copy of the exact candidate tree, compared by verdict, bound
  to the forge-commit-candidate/2 identity in a forge-fresh-reviewer-evals/1
  manifest under the chain directory — whenever the staged candidate matches
  the new committed reviewer-facing-eval-triggers policy region (a fixed
  plugin-owned table); trigger-region structural failures surface as the
  gate's INVALID exit-2 envelope, the TUI and orchestrator-oracle fixtures are
  explicitly dispositioned subject-specific-baseline-only, tests use a
  scripted-reviewer seam (no live model), and the bounded runner now kills and
  reaps the complete child process group on any post-launch exception.
- Immutable commit-candidate boundary (beads forge-plugin-w86 and forge-plugin-kmj,
  external-review findings 2 and 3): commit authorization now binds a
  `forge-commit-candidate/2` identity — a domain-separated SHA-256 over the
  repository object format and the `git write-tree` tree OID — with the intended
  parent and an exact message digest carried in commit intent; finalize verifies
  the produced commit's single parent, tree, and message BEFORE consuming
  authorization or recording a landing, freezing the chain fail-closed under the
  existing `frozen-chain` reason on mismatch, and crash recovery uses the same
  raw-object verifier. Staged-path enumeration, the review patch, and the secret
  scan render tree-to-tree from immutable objects under pinned, config-proof git
  invocation (gitlinks always visible), with bounded 16 MiB artifacts; the
  review-evidence diff keeps its own digest but is no longer authorization. The
  DM-006 marker gains a versioned five-line grammar (legacy markers are stale
  cleanup only, never authorization), all guard comparisons move to the
  authorization id with every public denial literal preserved, the journal
  accepts the `git-tree-candidate-v2` binding kind alongside readable historical
  bindings, and the replay grammar admits `commit_identity_checked`. Both
  external-review reproductions (pre-commit-hook index rewrite; ignoreSubmodules
  plus staged gitlink) are pinned as regression tests with disable-in-memory
  registries; spec amendment across DM-001/DM-006/DM-012/FR-210..223 including
  the deferred guard-breadth and reviewer-posture honesty wordings.
- Documentation honesty batch (external-review findings 1, 6, and 8; beads
  forge-plugin-x0h part 1, ryt, bfg, 9xb, x68): the README states the commit
  guard's real coverage (direct git invocations at the tool-use boundary,
  cooperative-agent assumption, wrappers intentionally out of scope); provider
  diversity is described as reducing correlated mistakes, not eliminating
  them; the binding Claude reviewer is described as instruction-bounded and
  execution-capable (deliberately keeping Bash for execution evidence) in
  contrast to the OS-sandboxed Codex first-pass reviewer; prose-contract tests
  and the release e2e are labeled as instruction-presence checks and scripted
  plumbing integration; platform claims are scoped to CI evidence; the
  standard MIT LICENSE is added per the operator's licensing decision and the
  README licence section fixed; stale README figures corrected; the AGENTS.md
  splice re-rendered byte-equal to committed policy; and the `docs` file
  category now classifies the root `LICENSE` file.
- Oversized review packages (bead forge-plugin-8lu, revision-10 FR-216/FR-170..174
  amendments): review packaging for commit, merge, and archive candidates now uses
  the single-master-package transport above a 786,432-byte threshold — the launch
  carries the authoritative package path, byte length, and lowercase SHA-256 with
  deterministic 65,536-byte window arithmetic instead of embedded bytes, the reader
  verifies identity and digest before the first and after the last window, and any
  mismatch refuses with the exact amendment literal; at or under the threshold the
  packaging is byte-identical to before, and the previous outright refusal for
  oversized merge packages upgrades to the same transport.
- CLI split phase 3 (bead forge-plugin-95e.4): the remaining 183 top-level
  names move verbatim into `scripts/forge/forge_cli/engine.py` (the commit-chain
  engine, parser construction, and helpers, including the journal-record-builder
  runtime binding) and `app.py` (`MergeEngine`, shared routing, argument parsing,
  dispatch, and main);
  `scripts/forge/cli.py` is now a 131-line forwarding shim, and the Revision-9
  seam-marker loop moves beside `register_coordination_seams` in
  `chain_core.py`. No verb, diagnostic, reason code, or `--help` byte changes.
- Gate 1 wall time (bead forge-plugin-pwy): the committed `gate1-test-command`
  cell now fans full unittest discovery out over `min(4, cpu)` shards inside the
  one `bash -c` cell, fail-closed on any failing shard, empty module set, or
  shard without a unittest summary, with per-shard output tails kept under the
  65,536-byte cap (tails sliced in bytes before decoding); the same 1,514 tests
  run in about 320 to 390 s instead of about 1,060 s on an eight-core host, and
  CI's gate-1 step runs the committed cell through the repository's FR-149
  runner (`forge_cli.runtime.run_bounded`: process group, output cap, 1,200 s
  bound), after its drift-check rerun had timed out at that bound on the
  slower runner. FR-149 gains a Revision-13 amendment authorising
  in-cell parallel workers under the cell's process group and output cap.
- CLI split phase 2b (bead forge-plugin-95e.3): the fenced process runner, the
  FR-235 common-lock arbiter and chain leases, chain and merge-chain storage,
  merge state and transition validation, and the ingest verifiers (288
  definitions) move verbatim into `scripts/forge/forge_cli/chain_core.py`; the
  shim reads them by attribute and forwards reads of those names, the
  journal-record builder stays in the shim and is bound onto a late-bound
  `forge_cli.runtime` seam that chain_core calls, the remaining test patch
  sites for `run_fenced_command` and the record builder target the canonical
  modules, and the FR-230 manifest subject set covers `chain_core.py`. The shim
  is now about 21k lines. No verb, diagnostic, reason code, or `--help` byte
  changes.
- CLI split phase 2a (bead forge-plugin-95e.3): `scripts/forge/forge_cli/runtime.py`
  is the one canonical module for the patchable controls (`utc_now`,
  `run_bounded`, `MERGE_LIFECYCLE_ACTIVE`, `REVISION9_STATE_CONTROLS`,
  `SCRIPT_DIR`/`PLUGIN_ROOT`, the coordination-module loader, and
  `_fast_mechanical_skips`); the shim reads them by attribute and forwards
  reads of those names, so a single `mock.patch.object(forge_cli.runtime, ...)`
  disables a control everywhere and the affected test patch sites now target
  that module. The FR-230 manifest subject set covers `runtime.py`. No verb,
  diagnostic, reason code, or `--help` byte changes.
- CLI split phase 1 (bead forge-plugin-95e.2): the response envelope (reason
  codes, `Refusal`, `FrozenError`, `Outcome`, output schemas) and the
  committed-policy parser move verbatim from `scripts/forge/cli.py` into the
  interpreter-loaded package `scripts/forge/forge_cli/` (`envelope.py`,
  `policy.py`); the shim re-imports every moved name by an explicit list so all
  module attributes, verbs, diagnostics, reason codes, and `--help` bytes are
  unchanged, and the policy-fence tests now patch the fence helpers on the
  canonical package module. The FR-230 phase-3 manifest's production subject
  set now covers the package modules beside `cli.py` and `commit-guard.sh`, so
  a change to a moved definition changes the subject candidate exactly as a
  shim edit does. The transition-table and ingest-verifier clusters stay in the
  shim for now: their closures reach patched controls and the coordination
  cache, so they move with the runtime module in later phases.
- CLI split phase 0 (bead forge-plugin-95e.1): every test module now loads
  `scripts/forge/cli.py` through one shared loader, `tests/_cli_loader.py`
  (`load_cli`, `load_script`, and the memoizing `load_cached`), with identical
  fresh-module semantics so per-module `mock.patch.object(CLI, ...)` isolation
  is unchanged; a loader contract test pins the shim path, the independent
  globals, and that no test module keeps a private loader. Spec §5 records
  `scripts/forge/forge_cli/` as the interpreter-loaded package the CLI is being
  split into, outside the executable-script inventory, with `cli.py` remaining
  the sole invoked entry point. No runtime behaviour changes.
- `/forge:worktree-merge` now takes its reintegration lock as FR-235's portable
  Git-common-dir arbiter through the Forge CLI wrapper `common-lock hold
  --owner-kind push --operation push`, waiting for the wrapper's readiness
  record before any rebase step and releasing with the exact `release` frame
  after the push; the skill-issued `flock --timeout 300` and `mkdir` mutex at
  `agent-rebase.lockdir` are retired because they diverged from, and collided
  with, the arbiter namespace every CLI merge and push entrant uses. The
  wrapper must not inherit the shell's release-pipe descriptor, the readiness
  wait ends as soon as the wrapper exits, every in-lock fenced command carries
  `8<&- 9>&-` so no child inherits the lock pipes, the post-push wrapper wait is
  bounded, the kernel `flock` layer is described by the wrapper's real predicate
  (Python's `fcntl.flock`, not the `flock` binary), a dead owner
  left by a killed holder is operator-cleared, and executable tests run the
  skill's exact fenced bytes against the wrapper (acquire/release, early exit,
  dead-owner refusal, and a descriptor disable proof). The init skill's lock
  report and the spec's macOS scenario now describe the arbiter instead of the
  retired `mkdir` fallback (spec revision 13 FR-062 amendment; bead
  forge-plugin-9qf.7, the slice-1 consumer cutover decision-02 of
  run-20260829-cli-phase3 deferred).

### Fixed

- FR-221 sentence shape restored (hotfix for the 41da640 amendment): the
  denial-literal sentence returns to the exact "with exactly `…(commit
  approve)` or `…(commit skip)` as the deny reason" phrasing that the phase-0
  contracts extractor pins against committed HEAD; the literals themselves
  never changed. The extractor reads HEAD by design, so the regression was
  invisible to every pre-commit gate and appeared only in post-landing CI.
- Bounded runner group termination (bead forge-plugin-8u4, external-review
  finding 4): `_kill_process_group` now proves process-group death — after
  SIGTERM and the full 0.25 s grace it probes the group and escalates SIGKILL
  to the group regardless of leader state, so a TERM-resistant descendant can
  no longer outlive a reported timeout; only ESRCH proves absence, existing
  fallbacks are preserved, and the regression is pinned by a real
  TERM-ignoring-descendant test with a disable-in-memory proof.
- Commitment audit, second matcher refinement (task-04 of the archive-unblockers
  run): a compound whose longest known-task-id prefix is a real task and whose
  tail is purely alphabetic ("task-09-bound" with task-09 known) resolves to the
  known id instead of failing the audit as an unresolved reference; unknown
  prefixes, digit-bearing tails, and partial-prefix forms stay flagged, with a
  disable-in-memory proof.
- Archive rendering of an operator-tombstoned chain (bead forge-plugin-cyg):
  when a journal-bound chain's artifacts are absent but a valid
  forge-chain-tombstone/1 record exists, the archive captures the tombstone's
  exact bytes as the chain's terminal artifact, renders bound records as
  explicitly not replay-authenticated with a `tombstoned_chain`
  non-authoritative discrepancy row, authenticates the tombstone-sourced
  chain-abort decision by carried-record equality, and keeps every fail-closed
  edge (missing or malformed tombstones refuse; real artifacts win; rerender
  determinism and the archive recheck cover the tombstone file) — with the
  Revision-13 spec amendment. Unblocks the run-20260829-cli-phase3 archive.
- Commitment audit (bead forge-plugin-a57, external-review follow-on): the
  unknown-task matcher treats a `task-<suffix>` compound in decision resolution
  prose as an unresolved reference only when the suffix begins with a digit, so
  ordinary English compounds ("task-binding", "task-level") no longer fail the
  audit closed and permanently block a run's archive; numeric references
  (`task-99`), known-id resolution, and the record task-field validation keep
  their fail-closed behavior, each pinned by new focused tests including a
  disable-in-memory proof.
- `commit abort-disposition --run-id <run> --chain-id <chain>` now dispositions
  an operator-tombstoned run-bound chain (a chain that froze and was sealed
  under Revision 11 without ever landing): it appends one `chain-abort`
  decision whose binding is sourced from the canonical tombstone digest and
  whose basis is the tombstone path, admitted on an already-terminal task and
  exempt from the terminal-task ordering, so the gate records the frozen chain
  drained are retired from FR-021 correlation and the run can close `passed`.
  The terminal guards authenticate that single decision against the tombstone
  and refuse a landing beside it, a second abort, or a candidate mismatch; every
  refusal appends nothing (spec revision 13 DM-001/FR-021/FR-210/FR-222 amendment;
  bead forge-plugin-11a).
- FR-021 journal-only correlation no longer refuses a `passed` close for a
  task whose chain drained gate sets for candidates it later restaged (any
  BLOCK-then-restage cycle): records bound to a superseded candidate are
  retired from the landing correlation and the precedence rule exactly as an
  abort retires a whole chain, the precedence rule scopes to the landed
  candidate's evidence, and a terminal execution result appended after its
  task's last landing for an execution recorded before that landing moves
  neither the run-level nor the per-task mutating boundary. Both rules are
  named controls (`superseded-candidate`, `post-landing-result`) with disable
  proofs; a landing followed by a different candidate on its own chain, an
  execution started after the landing, and records bound to a chain that
  neither landed, aborted with a decision, nor was superseded keep the
  refusals (spec revision 13 FR-021 amendment; bead forge-plugin-2mu).
- Retrospective chain abort disposition: `commit abort-disposition` on a
  run-bound chain that was aborted before revision 13 (its abort carried no
  decision) appends one `abort_disposition_recorded` self-event carrying the
  `chain-abort` decision through the ordinary outbox and receipt path, so the
  terminal guards, FR-021 correlation, and the archive see it exactly as a
  current abort; the verb refuses every other chain and any retry (spec
  revision 13, FR-210/FR-211/FR-222 amendments; bead forge-plugin-rtj).
- Journal validation: `validate` and the run-close validation now resolve a
  relative citation against the run directory first and the run's
  layout-derived repository root second, matching FR-017's append-time
  ordering, so gate evidence drained by run-bound chains (repository-relative
  `.forge/chains/…` paths) validates without a hand-made mirror, and the
  archive's pre-close recompute passes the real run's root into its temp
  mirror so a passed close stays archivable; absolute citations, symlink
  escapes, and citations absent from both roots keep the upstream diagnostic
  (spec revision 13, FR-011 amendment; bead forge-plugin-7t0).
- Commit guard: a leading shell assignment (`VAR=value python3
  scripts/forge/cli.py commit approve …`) no longer bypasses the operator-verb
  denial; the CLI invocation matcher skips assignment words before and after
  an `env` prefix like the git matcher does. The v1 corpus row that pinned
  the bypass is superseded, not edited, by the new `fr223-hook-argv/3`
  generation (twelve additive rows, one supersession member, eval fixture
  with a live-recorded baseline, v3 manifest), so v1 and v2 bytes stay
  immutable (spec revision 13, DM-016 and FR-221 amendments; bead
  forge-plugin-di8).
- Journal-visible chain abort: `commit abort` on a run-bound chain that
  holds a staged candidate and never landed now drains one `chain-abort`
  decision through the outbox, a fourth closed decision outcome. The terminal
  guard behind `journal task-finish` and `run-close` accepts an authenticated
  never-landed abort (new `abort-disposition` control with an in-memory
  disable) with at most one replay-exact abort decision, refuses a landing
  that cites an aborted chain, and `task-finish` inspects only the finishing
  task's chains, and `commit abort` refuses `closed` and `aborted` chains
  before any mutation so a landing is never rewritten and an abort is never
  retried. FR-021 journal-only correlation retires records bound to a
  chain with an abort decision and reports `terminal task '<task>' precedes
  a bound chain abort decision` when the task closes too early. Chains
  aborted before this release carry no decision and stay outside journal-only
  correlation until a retrospective path lands (spec revision 13; DM-001,
  FR-021, FR-210/FR-222 amendments; bead forge-plugin-437). The generation-1 `fr230-phase3-4-v2` manifest
  and its five result fixtures are re-bound to the changed `cli.py` subject.
- CI: the drift-check step wrote its summary into the checkout, so the
  worktree-clean check failed on every run; the summary now goes to the
  runner's temp directory and is uploaded from there (GH forge-plugin-76g).

### Added

- Phase-3 slice 7: the additive 41-member reason corpus, referenced 130-case
  hook matcher corpus, corpus-driven merge-approval and activation denials in
  `commit-guard.sh`, and the v2 byte-pin, hook, and manifest test modules.
- Commit guard fail-closed bounds: nested substitutions and case compounds
  reaching the 64-level bound, parsing plus per-action context resolution
  exceeding the 10-second budget, or any internal guard failure now deny on
  both channels with exit 2 instead of escaping as a traceback with a
  non-blocking exit; repository context, activation mode, and halt probes are
  memoized per distinct context; each bound has an in-memory disable test.
- Commit guard segmentation: a swallowed `case` compound can no longer hide
  the segments around it. Every command is also split raw with swallowing
  disabled and the union of actions and denials is enforced, so `case` words
  in quotes, comments, heredoc bodies, `${}`, `[[ ]]`, or `(( ))` never merge
  a raw push, commit, operator verb, or the halt check into an inert segment;
  case-arm bodies are visited once and case-word scans are linear, so
  alternating or wide case input stays fast.
- Phase-3 slice 7 evidence: the two planted-defect BLOCK eval baselines.
- Phase-3 slice 7 manifest: the generation-1 `fr230-phase3-4-v2` manifest and
  its five phase-3 PASS result fixtures under `tests/fixtures/fr230-results/`,
  bound to the reviewed `commit-guard.sh` subject candidate.
- Phase-3 slice 7 manifest rebind: the generation-1 manifest and its five
  result fixtures re-bound to the `commit-guard.sh` subject that carries the
  fail-closed parser bounds from review-final iteration 1.
- Phase-3 slice 7 manifest rebind (second): the manifest and fixtures
  re-bound to the guard subject that also carries the quoted-`case`
  segmentation fix and memoized resolution from review-final iteration 2.
- Phase-3 slice 7 manifest rebind (third): the manifest and fixtures
  re-bound to the guard subject that also carries the raw-split union and
  linear case-word scans from review-final iteration 3.
- Phase-3 slice 6 completes the merge inventory with real common-lock
  contention, fresh 300-second fence budgets, remote churn and destination-ref
  races, historical-attempt and safe-release recovery, serialized review
  edges, one shared hostile-path parser, and hermetic Revision-9 CI fixtures.
  The merge integration matrix is now split across
  `tests/test_cli_merge_integration.py` (shard 0) and two
  `tests/test_cli_merge_integration_shard<n>.py` siblings; full discovery
  runs all three, and a missing sibling refuses at load time.

## [0.6.10] - 2026-09-02

### Added

- Spec revision 12: one fenced composite performs fetch/name-status/full-patch
  when run-bound and fetch/full-patch when unbound, streaming patch bytes only
  into SHA-256 with no retained transcript; the sixteen-member scope-fetch
  sidecar /2 resolves DM-014/FR-236 for both modes. Also adds reservation-held
  surviving-fence clearing and loud explicit-recover-flag refusal outside owned
  conflict.
- Phase-3 slice 5: the dormant bounded-epoch merge finalize, recovery, cleanup,
  fenced gate execution, and Revision-12 composite bootstrap/run-scope proof
  engine, including one fenced fetch/name-status/full-patch process group,
  digest-streamed unbounded patch stdout, bound and unbound `/2` sidecars,
  reservation-held fence classification, loud conflict-recovery flags,
  observation-proven rebase recovery, contamination-safe conflict continuation,
  resumable scope sidecars, final-mode parking, push retry, and remote-tip carry.
- Spec revision 11: normative authority for the landed coordination fixes
  (replay history admission, operator tombstones, enumeration isolation, ingest
  evidence capture, typed readmission), the bounded receipts-ledger gap repair,
  the FR-236 per-operation publication budget, and the archive-mode changelog
  exemption.
- CI: a GitHub Actions workflow running the forge gates on pushes, pull
  requests, and a weekly schedule — full unittest discovery, routing/inventory
  conformance, STRICT evals, and the mechanical drift check in reduced-signal
  CI mode.
- Changelog gate configured in `forge-project.md`: code-class commits require a
  staged changelog entry; docs-class commits are exempt, and archive-only chains
  record a per-chain operator-directed skip until the auto-exemption ships.
- Phase-3 slice 4: the dormant merge verb lifecycle (start/refresh/verify/approve/
  abort/status) with atomic ownership publication and authenticated lineage.
- Phase-3 slice 3: merge candidate/admission, ordered gate, review, and run/task
  adapters (dormant; no `merge start` parser).
- Phase-3 slice 2: event-first chain-family routing and the DM-014 `MergeChainStore`
  with the nine-step transaction, replay repair, and frozen-chain isolation (dormant).
- Phase-3 slice 1: the FR-235 portable common-lock arbiter and `forge common-lock hold`
  long-lived wrapper with the FR-236 start-pipe fence (dormant).
- Spec revision 10: phase-3 authority adjudications — pending-phase-4 result bindings,
  epoch gate plans, post-fetch run-scope abort, normative v2/v4 layouts, the
  one-outstanding-disposition rule, and single-master-package oversized review.

### Fixed

- Engine policy reader (GH#12): `forge-project.md` fenced `bash`/`sh` cells may
  be uniformly indented (for example nested under a Markdown list item, as
  `/forge:init` has written them); the opening fence's exact indentation is
  stripped from every cell line so an indented cell is byte-identical to the
  same cell at column 0. A misaligned or mixed-indentation cell refuses with
  `forge: executable policy row malformed`; a CRLF closing fence now closes its
  cell. The cell reader is now a linear line scan with per-column closing-fence
  indexes instead of a lazy multi-line regex, so a policy full of unclosed
  openings parses in milliseconds rather than stalling for minutes.
  `forge --help` and `forge commit start --help` now list the global
  options (`--repo`, `--run-id`, `--chain-id`, `--json`, `--verbose`), state
  that `--run-id` requires `--task`, and note that `--task` is a verb option
  accepted only after `commit start`, `merge start`, or `journal ingest-chain`.
- Docs: `docs/updating-forge.md` documents plugin update mechanics and the
  pin-versus-track strategies for consumer repositories.
- Typed scope readmission now writes a contiguous batch receipt, and batch recovery can backfill one journal-proven historical receipt gap before clearing an exact landed intent.
- Commit-chain replay now preserves receipted history, isolates frozen chains, and supports explicit operator tombstones and frozen aborts.
- Commit-chain ingest now captures every cited evidence file into the run-relative content-addressed store.
- Activated runs now route scope readmission through the typed scope-change builder.
- Scope readmission preserves the current admitted set unless `--replace` is explicit, and containment refusals name escaped pathspecs.
- Run-bound changelog outputs declared by the pinned committed policy are treated as engine-injected gate paths in binding and ingest proofs.
- Revision-9 golden tests now skip with a stated reason on clean checkouts
  where the git-excluded origin-machine run journals cannot exist, instead of
  erroring (found by the CI candidate's binding review).

## [0.6.9] - 2026-08-29

### Added

- Archive/journal fidelity line: structured `forge-gate-binding/1` verdict bindings,
  chain-evidence embedding in run archives, typed journal builder verbs, batch
  intent/receipt crash recovery, run/task-bound chains with a receipted outbox, and
  the sixteen-proof retrospective `journal ingest-chain`.
- Spec revision 9 and the reason-codes/3 corpus (53 members) with its eval fixture.

### Fixed

- Operator-agent GitHub issues #5 (multi-session legacy journal tolerance, on the
  reporter's committed fixture) and #6.
- Gate-child environment scrub for `FORGE_SESSION_PID` across every stack cell.
- Archive renderer authority ordering and committed-archive preview.
- Legacy pre-revision-9 chain key-set tolerance.

## [0.6.8] - 2026-08-26

### Added

- Coordination hardening: successor-DAG retired-scope lifecycle, orphan
  classification, FR-019 append-time record schema, DM-010 stable live session
  identity, and the three-call commit Step 5.
- Spec revision 8 with nineteen new pinned literals.

### Fixed

- Operator-agent GitHub issues #1–#4, each with its reproduction committed as a
  regression test.

## [0.6.7] - 2026-08-26

### Added

- Spec revision 7: merge-chain authority (FR-230..FR-243, DM-014..DM-017), the
  forge-cli/2 41-member envelope enum, and bounded lock epochs.

### Fixed

- Reviewer verdict collection real-path handling (`/dev/fd` targets replaced by
  by-name re-opens).
- Assertion-sensor not-applicable short-circuit for docs-only chains.

## [0.6.6] - 2026-08-21

### Added

- CLI phase 1: the `scripts/forge/cli.py` commit-chain state machine
  (FR-210..FR-224, DM-012/DM-013) with staged-diff candidate identity, resumable
  `verify`, two-phase finalize, and the FR-221 dual-accept commit guard pinned by
  the 112-case invocation corpus.
