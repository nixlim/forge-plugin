# Updating forge

Forge is not an ordinary plugin: its skills, hooks, commit guard, and review
routing help cooperative agents follow the repository's gate workflow, avoid
mistakes, and understand refusals. These controls do not form a tamper-proof OS
boundary, so updating them deserves a deliberate choice between two postures —
both supported by the plugin's update flow.

## How updates propagate

Forge installs from its marketplace (this repository's
`.claude-plugin/marketplace.json`). The update signal is each commit on `main`:
with no version in either plugin manifest, Claude Code names the cache directory
for the installed plugin by that commit's SHA. Releases are identified by the
`CHANGELOG.md` heading, `pyproject.toml`, and the annotated tag `vX.Y.Z`.
Delivery depends on your marketplace registration:

- **`autoUpdate: true`** — Claude Code refreshes the marketplace and its
  installed plugins at **session startup**. A running session keeps the copy
  it loaded; the next session gets the new version.
- **Manual (default)** — nothing changes until you run `claude plugin update`
  (or use the `/plugin` UI).

Versioning follows semver intent: patch/minor releases are additive or
fail-closed-tightening; anything that changes what a gate accepts is called
out in release notes and `CHANGELOG.md` (Keep a Changelog format, repository
root).

## Posture 1 — autoUpdate (convenience)

Best when you track forge closely and want fixes as they ship. Enable
`autoUpdate` on the marketplace registration in your settings. You get defect
fixes (often for failure modes you have not hit yet) at the next session
start, with no action.

Trade-off: control-surface changes arrive without your operator reviewing
them first. The project workflow requires a separate gate review before a
release ships, but the automated release end-to-end test is only plumbing
integration: it uses scripted verdicts, including a literal `PASS`, rather than
a live reviewer. Any actual project review is our review, not yours.

## Posture 2 — pin and review (rigor)

Best when your own governance posture says gate instructions should not change
silently — the same principle the Forge workflow asks cooperative agents to
follow inside your repository. Pin the plugin entry in your marketplace
registration to `nixlim/forge-plugin#vX.Y.Z` (a tag ref) for a release, or to a
commit SHA, and move deliberately:

1. Read the release notes and the `[Unreleased]`→version diff in
   `CHANGELOG.md`.
2. Skim the spec revision entries (`docs/specs/forge-plugin-spec.md` header
   carries the revision history) for normative changes to gates you rely on.
3. Update the pin; restart; run your project's own gates once on a
   throwaway change to observe the new behavior before trusting it.

## After any update

- **Re-run a trivial commit through the chain** before important work: gate
  behavior changes (new denials, new required steps such as a changelog gate)
  surface immediately and cheaply there.
- **Check the changelog for consumer-visible semantics**: e.g. 0.6.9+
  activated runs validate journal record shapes at append time (malformed
  records refuse at the first write instead of poisoning the run); 0.6.10
  adds required typed idempotency keys; after 0.6.10 the worktree-merge skill
  takes its reintegration lock through `common-lock hold` (no `flock` binary
  consulted; a dead lock owner is an operator-cleared condition) and gated run
  close retires restaged-candidate gate sets from FR-021 correlation. If you scripted around old behavior, those scripts
  fail loudly rather than silently — by design.
- **0.7.0 consumer semantics:** `.forge/local/routes.toml` is opt-in;
  `review attach` is retired for new requests in favor of `review collect`;
  Claude Code 2.1.283 or newer and Codex CLI 0.155.0 or newer are required.
- **From 0.7.1:** the plugin manifests no longer declare a
  version, so plugin caches are keyed by commit SHA and updates track each
  commit on `main`. The `v0.7.0` tag itself still ships versioned manifests.
  Pin `nixlim/forge-plugin#vX.Y.Z` for release-only updates.
- **From 0.8.0 (Revision 22):** the release is breaking for callers of the FR-256 retired
  surfaces: the verbs and flags `validate --gates`, `journal close-preflight`, `run-readmit`, `run-retire`, `journal batch-recover`, `journal ingest-chain`, `chain outbox-drain`, `commit abort-disposition`, `journal verification-add`, `commit start --archive-run-id <run-id>` including its legacy/backfill flag pairs and `worktree-check`; the executables `archive-run.py`, `audit-commitments.py` and `journal-patterns.py`; their interpreter-loaded helper modules `archive_closing.py`, `chain_evidence_codec.py`, `commitment_paths.py`, `learn-proposals.py`, `learn-proposals-locked.py` and `route_provenance.py`; and `/forge:learn`. Existing run
  directories, journals, activated bindings and committed archives are left
  untouched and readable. After the upgrade FR-253's built-in control set and
  FR-254's floor apply to your own paths of those names, and project control
  extensions survive `init`.
  Collect or cancel every in-flight managed launch before updating; afterwards
  `launch collect` and `launch cancel` refuse older uncollected launches.
- **Local modifications do not survive updates.** Any patch you carry in the
  plugin cache is overwritten by every update; re-apply and re-verify after
  each one, or upstream the change.

## Where release information lives

- `CHANGELOG.md` — every release, Keep a Changelog format.
- GitHub releases and issue references — fixes are committed with the issues
  they close.
- If you file issues here, fixes that close them cite your issue number, and
  the issue is closed when the fix lands in a release you can install.
