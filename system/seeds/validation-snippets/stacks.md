# Per-stack validation snippets

<!-- forge: modified from upstream — re-rooted validation and Gate 1 output to forge-project.md. -->

Source material for `/forge:init` when filling the `file-categories`,
`stack-validations`, and `gate1-test-command` regions of `forge-project.md`. Detect
stacks from the markers below and adapt commands to the repository's actual scripts.
Prefer repository-owned `package.json` scripts, Makefile targets, or justfile targets
over raw defaults. Every generated section must preserve two upstream principles:
**prefer executable verification over static inspection** and **fix before
proceeding**.

Always include the generic `bash`, `docs`, `config`, and `control` categories from the
template. They are stack-independent.

---

## node (marker: `package.json`; lockfiles: `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`)

Category row: `| \`npm\` | \`package.json\`, lockfiles, \`*.js\`, \`*.ts\`, \`*.tsx\`, \`*.jsx\` |`

Validation steps:
1. Install with the repository's package manager if dependencies are stale (`npm ci` / `pnpm install --frozen-lockfile` / `yarn --immutable` / `bun install`)
2. Lint: repository `lint` script if present (`npm run lint`)
3. Types: `typecheck` script or `npx tsc --noEmit` when `tsconfig.json` exists
4. Tests: repository `test` script
5. Build when the package builds: `npm run build`

## python (markers: `pyproject.toml`, `requirements*.txt`, `setup.py`; tools: uv/poetry/pip)

Category row: `| \`python\` | \`*.py\`, \`pyproject.toml\`, \`requirements*.txt\` |`

Validation steps:
1. Environment: `uv sync` / `poetry install` / `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'` according to repository tooling
2. Lint and format: `ruff check` (and `ruff format --check`) if configured; otherwise the configured linter
3. Types: `mypy` or `pyright` when configured
4. Tests: `pytest` or the repository's configured runner

## go (marker: `go.mod`)

Category row: `| \`go\` | \`*.go\`, \`go.mod\`, \`go.sum\` |`

Validation steps:
1. `go build ./...`
2. `go vet ./...` plus `staticcheck ./...` when configured
3. `go test ./...` (targeted packages for large repositories, plus the designated blast-radius package always)

## rust (marker: `Cargo.toml`)

Category row: `| \`rust\` | \`*.rs\`, \`Cargo.toml\`, \`Cargo.lock\` |`

Validation steps:
1. `cargo check --all-targets`
2. `cargo clippy --all-targets -- -D warnings` when clippy is configured
3. `cargo fmt --check`
4. `cargo test` (targeted `-p <crate>` for workspaces, plus the designated blast-radius crate always)

## java-maven (markers: `pom.xml`, `mvnw`)

Category row: `| \`java\` | \`*.java\`, \`pom.xml\` |`

Validation steps:
1. Identify affected modules from file paths
2. `./mvnw test -pl <module1>,<module2>`
3. `./mvnw verify -pl <module>` for modules with integration tests
4. Always additionally run the designated blast-radius module's suite

## java-gradle / kotlin (markers: `build.gradle`, `build.gradle.kts`, `gradlew`)

Category row: `| \`jvm\` | \`*.java\`, \`*.kt\`, \`build.gradle*\` |`

Validation steps:
1. `./gradlew build -x test` (compile plus configured static checks)
2. `./gradlew test` (module-scoped `:module:test` for multi-project builds)

## terraform (marker: `*.tf`)

Category row: `| \`terraform\` | \`*.tf\`, \`*.tfvars.example\` |`

Validation steps:
1. `terraform fmt -check -recursive`
2. `terraform init -backend=false` if `.terraform/` is missing
3. `terraform validate` for each affected module
4. `terraform plan` with placeholder variables when real credentials are unavailable

## docker (markers: `Dockerfile*`, `docker-compose*.yml`)

Category row: `| \`docker\` | \`Dockerfile*\`, \`docker-compose*.yml\` |`

Validation steps:
1. `docker build` every changed Dockerfile with the correct context
2. `hadolint <Dockerfile>` when available
3. Smoke-run the built image when feasible (`--version` or startup help)

## helm (marker: `Chart.yaml`)

Category row: `| \`helm\` | \`helm/**\`, \`Chart.yaml\`, \`values.yaml\` |`

Validation steps: `helm lint` followed by `helm template` for the chart directory.

---

## Gate 1 command derivation

Compose `gate1-test-command` from the detected stacks: targeted test commands for the
affected paths plus one **always-run blast-radius suite**, chosen from the package,
module, or crate on which the rest of the repository depends most. CI definitions
remain the source of truth. Ask the user to confirm the blast-radius choice before
removing the region's `forge-init:` sentinel.
