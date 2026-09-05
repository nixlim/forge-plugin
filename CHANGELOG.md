# Changelog

All notable changes to the Forge plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Release dates are the UTC dates of the release commits.

## [Unreleased]

### Fixed

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
