# Updating forge

Forge is not an ordinary plugin: it is your repository's gate authority. Its
skills, hooks, commit guard, and review routing decide what may be committed
and merged. Updating it therefore deserves a deliberate choice between two
postures — both fully supported.

## How updates propagate

Forge installs from its marketplace (this repository's
`.claude-plugin/marketplace.json`). The update signal is the version string in
`plugin.json`: when a release bumps it on `main`, consumers see the new
version. Delivery depends on your marketplace registration:

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
them first. Forge releases are themselves gate-reviewed before they ship, but
that is our review, not yours.

## Posture 2 — pin and review (rigor)

Best when your own governance posture says a gate authority never changes
silently — the same principle forge enforces inside your repository. Pin the
plugin entry to a version or commit `sha` in your marketplace registration,
and move deliberately:

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
  tightens `run-readmit` to superset-or-`--replace` semantics and adds
  required typed idempotency keys. If you scripted around old behavior, those scripts
  fail loudly rather than silently — by design.
- **Local modifications do not survive updates.** Any patch you carry in the
  plugin cache is overwritten by every update; re-apply and re-verify after
  each one, or upstream the change.

## Where release information lives

- `CHANGELOG.md` — every release, Keep a Changelog format.
- GitHub releases and issue references — fixes are committed with the issues
  they close.
- If you file issues here, fixes that close them cite your issue number, and
  the issue is closed when the fix lands in a release you can install.
