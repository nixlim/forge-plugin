# Changelog

All notable changes to the Forge plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Release dates are the UTC dates of the release commits.

## [Unreleased]

### Changed

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
