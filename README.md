# claude-forge

A Claude Code plugin merging **forge** (DVRR governance: gate chain, adversarial
review constitution, worktree discipline, kill-switch, evals) with
**codex-orchestrator** (durable journal-based orchestration of headless Codex CLI
agents) into one streamlined system for the **Claude + Codex pair**. Claude
orchestrates, verifies, and holds the binding review verdict; Codex implements and
first-pass reviews. No opencode support — this is a deliberate divergence from
upstream forge.

**Start here:** [docs/design/0001-founding-decisions.md](docs/design/0001-founding-decisions.md)
— architecture, the five resolved design decisions, operational hardening set, and
the upstream contribution strategy.

Upstreams (assessed cherry-pick, no automatic sync):

- https://github.com/nixlim/forge (itself vendored from mock-server/mockserver-monorepo, Apache-2.0)
- https://github.com/alexzh3/codex-orchestrator (via the nixlim fork)

Status: design phase. Next step is the full specification.
