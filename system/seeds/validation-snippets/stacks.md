# Per-stack validation snippets

<!-- forge: modified from upstream — re-rooted validation and Gate 1 output to forge-project.md. -->

Source material for `/forge:init` when filling the `file-categories`,
`stack-validations`, `gate1-test-command`, `mutation-testing`, and `invariants` regions of
`forge-project.md`. Detect stacks from the markers below and adapt commands to the repository's
actual scripts.
Prefer repository-owned `package.json` scripts, Makefile targets, or justfile targets
over raw defaults. Every generated section must preserve two upstream principles:
**prefer executable verification over static inspection** and **fix before
proceeding**.

Always include the generic `bash`, `docs`, `config`, and `control` categories from the
template. They are stack-independent.

The assertion sensor consumes the heading-scoped `Test file patterns:` and `Assertion heuristic:`
lines below. Each file pattern is a separate Markdown code span. A heuristic is exactly
`Assertion heuristic: regex: <code-span>` or `Assertion heuristic: literal: <code-span>`; keep it
to one line. Mutation and property entries are mining guidance, never permission to install a new
tool: init must prove that the repository already provides a usable invocation. When the listed
tool is not usable, record the explicit absence instead of inventing a command.

---

## node (marker: `package.json`; lockfiles: `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`)

Category row: `| \`npm\` | \`package.json\`, lockfiles, \`*.js\`, \`*.ts\`, \`*.tsx\`, \`*.jsx\` |`

Test file patterns: `*.test.js`, `*.spec.js`, `*.test.jsx`, `*.spec.jsx`, `*.test.ts`, `*.spec.ts`, `*.test.tsx`, `*.spec.tsx`
Assertion heuristic: regex: `(?:\bassert(?:\.[A-Za-z_][A-Za-z0-9_]*)?\s*\(|\bexpect\s*\(|\bshould(?:\.|\s))`
Mutation tool: `Stryker`; changed-files form: `npx stryker run --mutate "$@"`
Property library: `fast-check`; auditable subset command: `npm test -- "$@"`

Validation steps:
1. Install with the repository's package manager if dependencies are stale (`npm ci` / `pnpm install --frozen-lockfile` / `yarn --immutable` / `bun install`)
2. Lint: repository `lint` script if present (`npm run lint`)
3. Types: `typecheck` script or `npx tsc --noEmit` when `tsconfig.json` exists
4. Tests: repository `test` script
5. Build when the package builds: `npm run build`

## python (markers: `pyproject.toml`, `requirements*.txt`, `setup.py`; tools: uv/poetry/pip)

Category row: `| \`python\` | \`*.py\`, \`pyproject.toml\`, \`requirements*.txt\` |`

Test file patterns: `test_*.py`, `*_test.py`
Assertion heuristic: regex: `(?:\bassert\b|\braise\b|\bself\.assert[A-Za-z_][A-Za-z0-9_]*\s*\()`
Mutation tool: `mutmut`; changed-files form: `mutmut run --paths-to-mutate "$@"`
Property library: `Hypothesis`; auditable subset command: `pytest "$@"`

Validation steps:
1. Environment: `uv sync` / `poetry install` / `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'` according to repository tooling
2. Lint and format: `ruff check` (and `ruff format --check`) if configured; otherwise the configured linter
3. Types: `mypy` or `pyright` when configured
4. Tests: `pytest` or the repository's configured runner

## go (marker: `go.mod`)

Category row: `| \`go\` | \`*.go\`, \`go.mod\`, \`go.sum\` |`

Test file patterns: `*_test.go`
Assertion heuristic: regex: `(?:\b[A-Za-z_][A-Za-z0-9_]*\.(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow)\s*\(|\b(?:assert|require)\.[A-Za-z_][A-Za-z0-9_]*\s*\()`
No mutation tool available for go.
Mutation-testing region fallback: `No mutation tool available for go — assertion-quality fallback only.`
Property library: `rapid`; auditable subset command: `go test "$@"`

Validation steps:
1. `go build ./...`
2. `go vet ./...` plus `staticcheck ./...` when configured
3. `go test ./...` (targeted packages for large repositories, plus the designated blast-radius package always)

## rust (marker: `Cargo.toml`)

Category row: `| \`rust\` | \`*.rs\`, \`Cargo.toml\`, \`Cargo.lock\` |`

Test file patterns: `*.rs`
Assertion heuristic: regex: `(?:\b(?:assert|assert_eq|assert_ne|debug_assert|debug_assert_eq|debug_assert_ne)!\s*\(|\bshould_panic\b)`
Mutation tool: `cargo-mutants`; changed-files form: `for file do cargo mutants --file "$file" || exit; done`
Property library: `proptest`; auditable subset command: `cargo test -- "$@"`

Validation steps:
1. `cargo check --all-targets`
2. `cargo clippy --all-targets -- -D warnings` when clippy is configured
3. `cargo fmt --check`
4. `cargo test` (targeted `-p <crate>` for workspaces, plus the designated blast-radius crate always)

## java-maven (markers: `pom.xml`, `mvnw`)

Category row: `| \`java\` | \`*.java\`, \`pom.xml\` |`

Test file patterns: `*Test.java`, `*Tests.java`
Assertion heuristic: regex: `\b(?:assert[A-Z][A-Za-z0-9_]*|assertThat|fail)\s*\(`
No mutation tool available for java-maven.
Mutation-testing region fallback: `No mutation tool available for java-maven — assertion-quality fallback only.`
Property library: `jqwik`; auditable subset command: `./mvnw test -Dtest="$1"`

Validation steps:
1. Identify affected modules from file paths
2. `./mvnw test -pl <module1>,<module2>`
3. `./mvnw verify -pl <module>` for modules with integration tests
4. Always additionally run the designated blast-radius module's suite

## java-gradle-kotlin (markers: `build.gradle`, `build.gradle.kts`, `gradlew`)

Category row: `| \`jvm\` | \`*.java\`, \`*.kt\`, \`build.gradle*\` |`

Test file patterns: `*Test.java`, `*Tests.java`, `*Test.kt`, `*Spec.kt`
Assertion heuristic: regex: `\b(?:assert[A-Z][A-Za-z0-9_]*|assertThat|fail)\s*\(`
No mutation tool available for java-gradle-kotlin.
Mutation-testing region fallback: `No mutation tool available for java-gradle-kotlin — assertion-quality fallback only.`
Property library: `Kotest property testing`; auditable subset command: `./gradlew test --tests "$1"`

Validation steps:
1. `./gradlew build -x test` (compile plus configured static checks)
2. `./gradlew test` (module-scoped `:module:test` for multi-project builds)

## terraform (marker: `*.tf`)

Category row: `| \`terraform\` | \`*.tf\`, \`*.tfvars.example\` |`

Test file patterns: `*.tftest.hcl`
Assertion heuristic: regex: `\bassert\s*\{`
No mutation tool available for terraform.
Mutation-testing region fallback: `No mutation tool available for terraform — assertion-quality fallback only.`
No property library available for terraform.

Validation steps:
1. `terraform fmt -check -recursive`
2. `terraform init -backend=false` if `.terraform/` is missing
3. `terraform validate` for each affected module
4. `terraform plan` with placeholder variables when real credentials are unavailable

## docker (markers: `Dockerfile*`, `docker-compose*.yml`)

Category row: `| \`docker\` | \`Dockerfile*\`, \`docker-compose*.yml\` |`

Test file patterns: `Dockerfile*`
No seeded assertion heuristic for docker.
No mutation tool available for docker.
Mutation-testing region fallback: `No mutation tool available for docker — assertion-quality fallback only.`
No property library available for docker.

Validation steps:
1. `docker build` every changed Dockerfile with the correct context
2. `hadolint <Dockerfile>` when available
3. Smoke-run the built image when feasible (`--version` or startup help)

## helm (marker: `Chart.yaml`)

Category row: `| \`helm\` | \`helm/**\`, \`Chart.yaml\`, \`values.yaml\` |`

Test file patterns: `*/tests/*_test.yaml`, `*/tests/*_test.yml`
Assertion heuristic: literal: `asserts:`
No mutation tool available for helm.
Mutation-testing region fallback: `No mutation tool available for helm — assertion-quality fallback only.`
No property library available for helm.

Validation steps: `helm lint` followed by `helm template` for the chart directory.

---

## Gate 1 command derivation

Compose `gate1-test-command` from the detected stacks: targeted test commands for the
affected paths plus one **always-run blast-radius suite**, chosen from the package,
module, or crate on which the rest of the repository depends most. CI definitions
remain the source of truth. Ask the user to confirm the blast-radius choice before
removing the region's `forge-init:` sentinel.
