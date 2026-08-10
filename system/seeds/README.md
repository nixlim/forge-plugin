# Forge seeds — project material generated during init

<!-- forge: modified from upstream — re-rooted generated evals and all project configuration to forge-plugin paths. -->

Nothing in this directory is copied verbatim into a target repository. `/forge:init`
uses these files as source material to generate the per-project layer:

- `eval-tasks/` — starter golden-task templates for `.forge/evals/tasks/`. Init
  concretizes each template against the target repository, then runs the named agent
  and records the baseline in `tasks/<id>.result` without overwriting an existing
  fixture or result.
- `brownfield-exploration.md` — the exploration protocol for repositories with
  existing code, CI, and conventions. Its findings supply all nine regions in the
  root-level `forge-project.md`.
- `validation-snippets/` — per-stack file-category rows and validation commands for
  the `file-categories`, `stack-validations`, and `gate1-test-command` regions in
  `forge-project.md`. Init adapts them to the repository's actual scripts and CI.

Generated eval tasks retain the upstream fixture frontmatter keys (`id`, `category`,
`agent`, `expected_verdict`). Generated validation sections retain the upstream
principles: prefer executable verification over static inspection, use CI as the
source of truth, and fix failures before proceeding.
