# Brownfield exploration protocol

<!-- forge: modified from upstream — re-rooted distributed project sections to the nine regions in forge-project.md and repo-local .forge state. -->

How `/forge:init` explores a repository that already has code, CI, and conventions
before filling any region. **Mirror the repository's existing reality; never invent a
parallel one.** A gate that runs different commands than CI, a changelog rule the
project does not follow, or triggers for failure modes the project never has all
erode trust. Every filled region must be traceable to evidence from this exploration.

For large repositories, fan the read-only steps out to exploration subagents and
synthesize the results. For small repositories, do them inline. Record what was
found and what was looked for but absent in the init summary.

## 1. CI mining (highest value)

Find and read the real pipeline definitions:

| CI system | Look for |
|-----------|----------|
| GitHub Actions | `.github/workflows/*.yml` |
| GitLab | `.gitlab-ci.yml`, `.gitlab/` |
| Buildkite | `.buildkite/` |
| Jenkins | `Jenkinsfile*` |
| CircleCI | `.circleci/config.yml` |
| Azure | `azure-pipelines.yml` |

Extract the **exact commands** CI runs for tests, lint, type checks, builds, and
matrix dimensions such as runtime versions and operating systems. CI definitions are
the source of truth for:

- `stack-validations` — local validation should predict a green pipeline;
- `gate1-test-command` — the CI test job or its safe fast subset, plus the confirmed
  blast-radius suite;
- `project-overview` — the CI system, trigger model, and relevant repository facts.

If a CI command cannot run locally because it needs services, secrets, or cloud
access, say so in the region and choose the strongest safe local substitute. Never
silently replace it with a weaker check.

## 2. Convention mining

- **Lint and format configuration:** inspect `.eslintrc*`, `biome.json`,
  `ruff.toml`, relevant `pyproject.toml` tool sections, `.golangci.yml`,
  `clippy.toml`, `checkstyle*.xml`, `.editorconfig`, and `prettier*`. Adopt the
  configured tools; never introduce a replacement linter or formatter.
- **Commit and review conventions:** inspect commit-lint configuration, evidence in
  `git log --oneline -50`, pull-request templates, `CODEOWNERS`, and
  `CONTRIBUTING.md`. Feed verified conventions into project context and review focus.
- **Changelog reality:** determine whether `CHANGELOG.md` or `changelog.md` is
  actively maintained. Mirror its actual format in `changelog-policy`; if absent or
  abandoned, use the exact no-gate sentence allowed by DM-003.
- **Branch and merge conventions:** inspect `git log --merges -20`. If history shows
  merge commits or the host requires pull-request merges, surface the conflict with
  Forge's linear-history rule and ask the user to decide. Do not silently impose or
  relax either workflow.
- **Protected branches and required checks:** inspect repository-host protection
  settings when available. Required status checks belong in Gate 1 or stack
  validations.

## 3. History mining (triggers and blast radius)

- **Bug-fix patterns:** inspect `git log --oneline --grep='fix' -100`, then repeat for
  `revert`, `regression`, `leak`, `race`, and `CVE`. Read representative fix diffs.
  Recurring defect classes become `project-triggers` rows with real file or pattern
  citations.
- **Churn and coupling:** use
  `git log --format= --name-only -200 | sort | uniq -c | sort -rn | head -20` as one
  signal. The hottest heavily depended-on module is a blast-radius candidate, not an
  automatic choice.
- **Fast reverts:** a revert within 14 days of its original commit indicates a weak
  verification area. Feed that evidence into `project-triggers`, review focus, and
  the proposed Gate 1 suite.

The user must confirm the always-run blast-radius suite before
`gate1-test-command` is marked filled. If confirmation is withheld, leave that region
unfilled and fail closed.

## 4. Documentation and architecture indexing

- Inventory `README*`, `docs/`, `ARCHITECTURE*`, ADR directories, and any wiki linked
  from repository documentation. Put only verified, useful references into
  `project-overview` and `agent-project-context`.
- Map module layout, ownership boundaries, conventions, and test commands into the
  short `agent-project-context` region that is injected into every agent prompt.
- Detect monorepos through workspace manifests. Make validations path-scoped per
  package while retaining the confirmed blast-radius suite.

## 5. Existing agent-tooling detection

Read pre-existing `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/`, and `.cursor/`
content. The mechanical installer preserves AGENTS.md content outside the Forge
markers, appends rather than replaces the CLAUDE.md import, and writes incoming
Forge `config.toml` or `hooks.json` as `.forge-new` when a non-Forge file already
exists. Read both sides of any `.forge-new` collision and propose a merge; never
discard existing instructions unread.

## 6. Verification of the exploration

Before region filling is accepted, prove the proposed customization against reality:

1. Confirm every command cited in a region exists in the repository as a script,
   target, workflow step, or executable.
2. Run the assembled `stack-validations` commands on the clean tree; they must pass.
3. Run the assembled `gate1-test-command` on the clean tree; it must pass. Time it,
   and split targeted checks from the always-run blast-radius suite if needed.
4. Trace each of the nine filled regions to CI, configuration, code, history,
   documentation, or an explicit user decision.

A gate that fails on untouched code is miscalibrated. Stop init and report the
evidence instead of weakening the gate or marking the region filled.
