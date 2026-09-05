# forge-plugin

A Claude Code plugin for running headless coding agents against a repository you
still trust afterwards.

Generating code has become cheap. Verifying it, understanding it, and being able
to say honestly what was checked has not. forge-plugin is built around that
asymmetry: agent output is treated as a claim, and nearly everything durable in
the system exists to test claims rather than to produce more of them.

It merges two systems — **forge** (gate chains, an adversarial review
constitution, worktree discipline, a kill-switch, eval regressions) and
**codex-orchestrator** (durable journal-based orchestration of headless Codex CLI
agents) — into one arrangement for the **Claude + Codex pair**. Claude
orchestrates, verifies, and holds the binding review verdict. Codex implements and
performs the first-pass review. Support for other harnesses is deliberately out of
scope.

## How it works

**Separate the author from the judge, across model families.** The implementer is
a fresh Codex agent in an isolated worktree. The first-pass reviewer is a
different Codex agent that never sees the implementer's handoff or its claimed
results. The binding verdict comes from a read-only Claude reviewer. An author and
its judge never share a model's blind spots.

**Trust nothing that was merely reported.** Agent handoffs are claims, not
evidence. The orchestrator re-runs every gate in its own environment before any
commit. A run's history records what was actually observed — command output, exit
codes, SHAs read from git rather than remembered.

**Fail closed.** Gates are unconfigured until `/forge:init` fills them, and an
unconfigured gate refuses rather than passes. A commit without a review-backed
marker is denied by a `PreToolUse` hook, not by an agent's good intentions.

**Prove the controls work.** Gates ship with tests that fail when the control is
disabled. A test that still passes with its control removed is treated as a
defect, not as coverage.

## Requirements

- Claude Code ≥ 2.x
- Python ≥ 3.10 (standard library only — no packages, no build step)
- OpenAI Codex CLI on `PATH` (`codex --version`), authenticated
- bash on macOS (BSD userland) or Linux. Reintegration locking needs no `flock`
  binary: the worktree-merge skill holds the portable Git-common-dir arbiter
  through the Forge CLI (`common-lock hold`), which takes its optional kernel
  layer through Python's `fcntl`. Only the commit-lock helper pair
  (`acquire-commit-lock.sh` and `release-commit-lock.sh`, which also guard the
  decision-event lock) needs `flock` or `lockf`.

## Install

The repository is its own plugin marketplace. From any Claude Code session:

```
/plugin marketplace add nixlim/forge-plugin
/plugin install forge@forge
/reload-plugins
```

(For a local checkout, pass the absolute path to the repo instead of the GitHub
slug.) Restart the session afterwards so the skills and hooks load. You should see
eight skills:

| Skill | Purpose |
|---|---|
| `/forge:init` | Install or refresh the per-repo layer (region file, AGENTS.md splice, `.codex/`, evals) |
| `/forge:workflow` | Run a full orchestration lifecycle (plan → tasks → gated close → archive → report) |
| `/forge:orchestrate` | One focused Codex-agent execution, review, or verification cycle |
| `/forge:report` | Author the final report after a gated close |
| `/forge:commit` | The five-step fail-closed commit gate chain |
| `/forge:worktree-merge` | The four-gate merge chain with locked-rebase reintegration |
| `/forge:drift` | Mechanical drift sensing, then an operator-invoked periodic semantic review |
| `/forge:learn` | Advisory journal-derived learning: proposes eval candidates and traceable gotchas |

Installing also registers a **PreToolUse commit guard**, an advisory **PostToolUse
invariant guard**, a **Stop union** that independently runs telemetry aggregation
and the drift-staleness nudge, and a **SessionStart** nudge. Every Stop and
SessionStart member is silent and inert outside a forge-initialized repository.

## Per-repository setup

In the repository you want to govern:

```
/forge:init
```

Init confirms the project name and default branch; installs `forge-project.md`
(fourteen configuration regions, rendered into both CLAUDE.md and AGENTS.md), the
`.codex/` layer (agent routing plus an execpolicy deny-list), the gitignore block,
and `.forge/` state directories; mines your CI configuration and git history to
propose gate commands; seeds and baselines the eval suite; then presents the whole
install diff for your explicit approval. It never commits on its own.

Until the regions are filled, gates fail closed — a merge stops with
`forge: gate1-test-command not configured — run /forge:init`.

If the repository already carries an older non-plugin forge installation, init
detects it and migrates: regions are salvaged byte-identically from their original
locations, eval fixtures are imported **with their committed baselines rather than
re-recorded** (re-minting would launder an existing reviewer regression into a
fresh "correct" result), and everything left behind is enumerated in a committed
migration report.

## What gets verified

Each layer answers a different question, and each is configured per repository
rather than assumed.

| Layer | Question it answers |
|---|---|
| **Gate 1 / Gate 2** | Do the project's own tests, linters and type checks pass? |
| **Invariants** | Do the repository's declared structural rules still hold? Every declared invariant must be an executable command; one that cannot be scripted is moved to a review bullet explicitly. |
| **Assertion sensor** | Does this test actually assert anything? Blocks confidently assertion-free Python tests; advisory where it cannot resolve the delegation. |
| **Scoped mutation** | Do the tests detect a deliberately broken implementation? Runs on changed files after Gate 1, advisory, with a documented path to becoming blocking once its cost and baseline are known. |
| **Adversarial review** | Does the change do what was intended, and what did the last reviewer miss? Eight baseline lenses plus a per-artefact profile; binary PASS/BLOCK, no hedging. |
| **Risk tiers** | How much scrutiny does *this* diff deserve? Derived from the diff at gate time against committed policy, promote-only, with a non-narrowable floor for control-class paths. |
| **Drift sensing** | Has anything decayed since the last change? Evals, gates on a clean tree, invariants, full mutation, category coverage, region staleness, telemetry. |
| **Learning loop** | Which failure shapes keep recurring, and what control would have caught them? Proposes; never applies. |

Both the commit chain and the merge chain end in a binding review, and the merge
chain's final gate is mandatory even when every constituent commit took the fast
tier.

## Operator controls

- **Kill-switch** — create `AGENT_HALT` (or scoped `AGENT_HALT_commit`) at the
  main checkout root and every commit, push and reintegration stops until you
  remove it. Agents never create or clear sentinels.
- **Control-class changes** — gates, the constitution, agent routing, hooks,
  evals and `forge-project.md` always route to the binding reviewer and wait for
  your explicit approval.
- **Audit** — guard denials and halt detections append to
  `.forge/tmp/halt-audit.log`; full orchestration history lives in the run journal
  under `.codex-orchestrator/runs/<run-id>/`.
- **Dead merge-lock owner** — a reintegration holder killed outright leaves its
  arbiter owner record (`agent-rebase.lockdir` and `agent-rebase.lock.intent`
  in the Git common directory) and later entrants refuse until it is cleared.
  Only you clear it, after proving the recorded host and PID dead; agents never
  remove lock artifacts.

## The durable record

A run's journal is working state and stays out of git. What survives is a
distilled archive, committed at close under `.forge/history/runs/<run-id>.md`: the
goal, per-task acceptance criteria, every decision with its basis, the gate
evidence table with verdicts and iteration counts, residual risks, and provenance
SHAs read from command output.

Before that archive is written, a mechanical audit checks the journal's own
bookkeeping — that no decision references a task which does not exist, that no
task is left non-terminal, and that every artifact the journal claims exists
actually does. A failed audit means no archive, and no archive means no report.

Because the journal is append-only, a mistyped citation cannot simply be edited
away. It is corrected by appending a correction entry, and the archive records both
the correction and the original error, so the mistake stays visible rather than
being quietly rewritten.

## Evals

Golden control regressions live in `.forge/evals/tasks/`. Journal-derived fixtures
preserve the exact recorded agent prompt and name both their source run and
execution; the committed `.result` is the accepted verdict baseline. Routing,
reviewer, constitution or other control-class changes require a strict run:

```sh
STRICT=1 scripts/forge/run-evals.sh
```

An empty suite exits non-zero. A gate that no fixture exercises is not satisfied
by having no fixtures.

## Learning loop

After the archive commit and final report — and, on the drift side, after the
durable drift report — `/forge:learn` runs as a best-effort advisory pass over
three committed inputs: the journal-derived pattern output, the archive corpus
under `.forge/history/runs/`, and the current gotchas file. It clusters recurring
failure shapes and names the control that would have caught each one earlier.

It proposes and nothing more. Candidate fixtures land in
`.forge/evals/candidates/` carrying the exact recorded prompt and its source run
and execution; observations append to `.forge/history/gotchas.md`, which then
feeds forward into later agent prompts.
It never promotes or applies a fixture, changes a control, commits, or blocks a
run from closing — a system that rewrote its own controls from its own failure
history would be gaming its own gates.

## Scheduled mechanical drift sensing

Point scheduled CI at the mechanical checker, with `CLAUDE_PLUGIN_ROOT` set to
the installed plugin root. It runs only the mechanical checker and does not invoke an
LLM. Scheduled CI never launches semantic review or any model; the semantic half
is operator-invoked:

```yaml
on:
  schedule:
    - cron: "17 4 * * 1"
jobs:
  forge-drift-mechanical:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          path: project
      - uses: actions/checkout@v4
        with:
          repository: nixlim/forge-plugin
          path: forge-plugin
      - name: Run Forge mechanical drift checks
        working-directory: project
        env:
          CLAUDE_PLUGIN_ROOT: ${{ github.workspace }}/forge-plugin
        run: '"${CLAUDE_PLUGIN_ROOT}/scripts/forge/drift-check.sh"'
```

When the Stop or SessionStart nudge reports a stale drift report, invoke
`/forge:drift` interactively for the semantic half. A CRITICAL drift finding
writes a block that refuses new runs until you clear it.

## Concurrency

Several agents can work in one repository. Per-commit authorization is
content-addressed by the staged diff, so two chains can hold authorization at once
and one candidate's marker can never admit another. Journals record an owner and
refuse an append from a live foreign owner. Runs are admitted by declared file
scope rather than refused outright, and overlapping scopes are named on refusal.
Reintegrations serialize through one portable arbiter in the Git common directory,
so every worktree and every entrant on Linux or macOS contends on the same lock.

Decision-event emission is lossless under concurrency on local POSIX filesystems
(macOS and Linux). The guarantee does not extend to NFS or SMB, and Windows is out
of scope.

## Development

```sh
python3 -m unittest discover -s tests
```

The suite is stdlib only and currently runs roughly 650 tests. `UPSTREAM` records
both vendored upstream SHAs and every deliberate deviation.

- Design decisions: [docs/design/0001-founding-decisions.md](docs/design/0001-founding-decisions.md)
  and [docs/design/0002-verification-expansion.md](docs/design/0002-verification-expansion.md)
- Full specification: [docs/specs/forge-plugin-spec.md](docs/specs/forge-plugin-spec.md)
- Orchestration contract: [docs/orchestration-contract.md](docs/orchestration-contract.md)

Upstreams (assessed cherry-pick, no automatic sync):

- https://github.com/nixlim/forge (itself vendored from mock-server/mockserver-monorepo, Apache-2.0)
- https://github.com/alexzh3/codex-orchestrator (via the nixlim fork)

## Licence

Apache-2.0. See [LICENSE](LICENSE).
