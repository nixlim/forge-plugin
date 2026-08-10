# forge-plugin

A Claude Code plugin merging **forge** (DVRR governance: gate chain, adversarial
review constitution, worktree discipline, kill-switch, evals) with
**codex-orchestrator** (durable journal-based orchestration of headless Codex CLI
agents) into one streamlined system for the **Claude + Codex pair**. Claude
orchestrates, verifies, and holds the binding review verdict; Codex implements and
first-pass reviews. Other-harness support is out of scope — this is a deliberate
divergence from upstream forge.

## Requirements

- Claude Code ≥ 2.x
- Python ≥ 3.10 (standard library only — no packages, no build step)
- OpenAI Codex CLI on `PATH` (`codex --version`), authenticated
- bash (macOS BSD userland and Linux both supported); `flock` optional (a portable
  fallback lock is used where it is absent)

## Install

The repository is its own plugin marketplace. From any Claude Code session:

```
/plugin marketplace add nixlim/forge-plugin
/plugin install forge@forge
```

(For a local checkout, pass the absolute path to the repo instead of the GitHub
slug.) Restart the session afterwards so the skills and hooks load. You should see
six skills:

| Skill | Purpose |
|---|---|
| `/forge:init` | Install/refresh the per-repo layer (region file, AGENTS.md splice, `.codex/`, evals) |
| `/forge:workflow` | Run a full orchestration lifecycle (plan → tasks → gated close → report) |
| `/forge:orchestrate` | One focused Codex-agent execution/review/verification cycle |
| `/forge:report` | Author the final report after a gated close |
| `/forge:commit` | The 5-step fail-closed commit gate chain |
| `/forge:worktree-merge` | The 4-gate merge chain with locked rebase reintegration |

Installing the plugin also registers two hooks: a **PreToolUse commit guard**
(blocks `git commit`/`git push` under an operator halt, and requires a
review-backed authorization marker in forge-initialized repos) and a **Stop
telemetry hook** (aggregates decision telemetry; inert outside forge repos).

## Per-repository setup

In the repo you want to govern:

```
/forge:init
```

Init confirms the project name and default branch, installs `forge-project.md`
(nine configuration regions rendered into both CLAUDE.md and AGENTS.md), the
`.codex/` layer (agent routing plus an execpolicy deny-list), the gitignore
block, and `.forge/` state directories; mines your CI and git history to
propose gate commands; seeds and baselines the eval suite; then presents the
whole install diff for your explicit approval — it never commits on its own.

Until init fills the regions, the gates fail closed: merges stop with
`forge: gate1-test-command not configured — run /forge:init`.

## Operator controls

- **Kill-switch**: create `AGENT_HALT` (or scoped `AGENT_HALT_commit`) at the main
  checkout root — all commits, pushes, and reintegration stop until you remove it.
  Agents never create or remove sentinels themselves.
- **Control-class changes** (gates, constitution, routing, hooks, evals,
  `forge-project.md`) always route to the binding `review-final` agent and wait
  for your explicit approval.
- **Audit**: guard blocks and halt detections append to
  `.forge/tmp/halt-audit.log`; orchestration history lives in the run journal
  under `.codex-orchestrator/runs/<run-id>/`.

## Development

```
python3 -m unittest discover -s tests
```

176 tests, stdlib only. `UPSTREAM` records both vendored upstream SHAs and every
deliberate deviation. Design background:
[docs/design/0001-founding-decisions.md](docs/design/0001-founding-decisions.md);
full specification: [docs/specs/forge-plugin-spec.md](docs/specs/forge-plugin-spec.md).

Upstreams (assessed cherry-pick, no automatic sync):

- https://github.com/nixlim/forge (itself vendored from mock-server/mockserver-monorepo, Apache-2.0)
- https://github.com/alexzh3/codex-orchestrator (via the nixlim fork)
