---
name: init
description: Install or re-initialize Forge in the current Git repository, mine its real conventions, fill its fail-closed project regions, establish eval baselines, self-review the complete install, and wait for explicit approval. Use when asked to run /forge:init, initialize Forge, install Forge, or refresh an existing Forge installation.
---

# Initialize Forge

<!-- forge: rewritten from upstream — use the plugin root, one project file, two Codex agents, and an approval-only completion boundary -->

Install or refresh Forge in the current repository. Follow Phases 0 through 6 in order and fail
closed. If a required check, command, model, agent, or user decision is unavailable, stop, name the
blocker. Once initialization has made its first target-repository mutation, leave
`init_completed: false`. A Phase 0 failure before re-init invalidation leaves the existing manifest
unchanged because no install mutation has begun. Never guess project policy, weaken a gate,
overwrite operator content, run `git commit`, or run `git push`.

Treat every existing worktree change as operator-owned. Do not stash, discard, stage, or modify an
unrelated path. If unrelated changes prevent an attributable clean-tree check or complete install
diff, stop and ask the user to provide a clean target state.

## Phase 0 — Preconditions

Complete every precondition before running the installer.

1. Prove that the current directory is the Git repository root:

   ```bash
   REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 1
   test "$(pwd -P)" = "$(cd "$REPO_ROOT" && pwd -P)" || exit 1
   ```

   Stop if either command fails. Do not initialize a repository implicitly. Record the initial
   `git status --porcelain` so the eventual review diff can be limited to this init run.

2. Detect `.forge-manifest`. When it exists, classify the run as a re-init, read and report its
   installed version, plugin ref, project, branch, completion state, and region lines, then inspect
   `forge-project.md` directly. A region is unfilled when its body contains `forge-init:` and filled
   otherwise. The file is authoritative: do not infer filled state only from the manifest. Report
   filled and unfilled regions. Preserve filled bodies byte-for-byte and process only unfilled
   regions unless the user explicitly requests a change. Never overwrite an existing eval fixture
   or `.result` baseline.

3. Derive the proposed project name from the repository directory name. Detect the proposed
   default branch from `origin/HEAD`, falling back to `main` only when detection returns nothing:

   ```bash
   DEFAULT_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')"
   : "${DEFAULT_BRANCH:=main}"
   ```

   Ask the user to confirm both the project name and default branch. Do not continue on an
   ambiguous or rejected answer.

4. Resolve the Git common directory and run `command -v flock`. Report the exact merge lock path
   that this repository will use:

   - when `flock` exists, `${GIT_COMMON_DIR}/agent-rebase.lock` with a 300-second `flock` timeout;
   - otherwise, `${GIT_COMMON_DIR}/agent-rebase.lockdir` with the 300-second atomic `mkdir`
     fallback.

   Obtain `GIT_COMMON_DIR` with
   `git rev-parse --path-format=absolute --git-common-dir`. Missing `flock` is not a blocker when
   `mkdir` is available. Missing both lock mechanisms is a blocker. Never bypass locking.

5. Require `codex`. Read every `model = "..."` value from
   `${CLAUDE_PLUGIN_ROOT}/system/codex/agents/*.toml`, reject a missing or malformed value, and
   deduplicate the model names. Run exactly one trivial, read-only probe per distinct model, for
   example:

   ```bash
   codex exec --model "$MODEL" --sandbox read-only "Reply with exactly FORGE_MODEL_OK."
   ```

   A nonzero exit, rejected model, or unavailable model stops init immediately. Name the rejected
   model in the report; do not substitute a different model or lower its reasoning effort.

6. Immediately before Phase 1, handle the manifest as the final precondition. On re-init, require
   the existing `.forge-manifest` to be well formed before making any target-repository mutation:
   require exactly one nonempty value for each single-valued DM-005 key, exact
   `forge_version: 1`, exactly one completion line whose value is `true` or `false`, and unique
   `region:` values drawn only from the nine defined regions. Cross-check its region lines against
   the filled bodies reported in step 2; a malformed, duplicate, unknown, or inconsistent value
   stops init without changing the manifest.

   Only after every preceding confirmation and model probe has passed, make re-init invalidation
   the first target-repository mutation. If the manifest contains the exact line
   `init_completed: true`, replace only that line with `init_completed: false` in a same-directory
   temporary file, verify every other byte is unchanged, and atomically rename the temporary file
   over `.forge-manifest`. If it already contains the exact line `init_completed: false`, leave the
   file byte-identical and do not rewrite it. An inability to complete the atomic replacement stops
   before Phase 1. On fresh init there is no manifest mutation here; create the first manifest only
   in Phase 5.

## Phase 1 — Mechanical install

Run the initial mechanical installer pass from the repository root:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/install.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Require exit 0 and inspect its written-versus-skipped summary. Verify that it rendered
`forge-project.md`, refreshed one `<!-- FORGE:BEGIN -->` / `<!-- FORGE:END -->` block in
`AGENTS.md`, ensured the exact line `@forge-project.md` in `CLAUDE.md`, installed `.codex/`,
appended one guarded Forge gitignore block, and created `.forge/evals/tasks/` plus `.forge/tmp/`.
Content outside the AGENTS markers must be unchanged.

Treat `config.toml.forge-new` or `hooks.json.forge-new` as a collision, not a successful merge.
Report each collision and ask the user how to merge the incoming Forge settings with the existing
file; never overwrite the existing file. An unresolved collision that prevents the required agents
or hook from being registered blocks completed initialization.

Tell the user this trust caveat explicitly: until the operator opens and TRUSTS this repository in
Codex, Codex skips the repository's `.codex/` configuration, agents, rules, and hooks. Never bypass
or claim to satisfy that trust decision for the operator.

## Phase 2 — Brownfield mining

Read and follow `${CLAUDE_PLUGIN_ROOT}/system/seeds/brownfield-exploration.md` before filling any
unfilled region. Mirror the repository's existing reality; do not introduce a parallel toolchain.
For a large repository, parallelize independent read-only searches and synthesize their evidence.

At minimum:

1. Read every CI pipeline definition. CI commands are the source of truth for
   `stack-validations` and `gate1-test-command`; prefer repository scripts called by CI over
   invented generic commands. Read
   `${CLAUDE_PLUGIN_ROOT}/system/seeds/validation-snippets/stacks.md` only as adaptation guidance.
2. Inventory language and package manifests, test layout, build scripts, monorepo boundaries,
   deploy and infrastructure files, required branch checks, CODEOWNERS, release and changelog
   practice, architecture and contributor docs, and existing agent instructions.
3. Adopt the repository's existing linters and formatters. Never replace them or silently add
   competing ones.
4. Inspect `git log` for recurring fix, revert, regression, migration, compatibility, and security
   patterns. Use evidenced patterns to form `project-triggers`, with real paths or history
   citations. Use churn, coupling, and dependency evidence to propose an always-run blast-radius
   suite.
5. When history shows merge commits or a PR merge workflow, surface its conflict with Forge's
   linear-history rule and obtain the user's decision. Do not hide or resolve that policy conflict
   by assumption.
6. Record both evidence found and material evidence sought but absent. A greenfield repository may
   have little evidence; say so instead of fabricating conventions.

Propose the targeted test command and always-run blast-radius suite to the user. The user must
confirm the blast-radius choice before the `gate1-test-command` region may be marked filled.

## Phase 3 — Region filling

Use only Phase 2 evidence and confirmed decisions. The root `forge-project.md` is the single
project-policy source. Preserve every `<!-- FORGE:REGION ... BEGIN -->` and matching END marker.
For each region still containing a `forge-init:` comment, replace its body and remove that comment.
Do not rewrite a carried-forward filled body on re-init.

End with all nine regions filled:

1. `project-overview`
2. `file-categories`
3. `stack-validations`
4. `gate1-test-command`
5. `changelog-policy`
6. `review-prompt-project-focus`
7. `project-triggers`
8. `completeness-project-items`
9. `agent-project-context`

Make every configured validation executable in this repository. Include the confirmed targeted
test and always-run blast-radius suite in `gate1-test-command`. Use 3–5 evidenced review-focus
bullets, 3–8 trigger rows, 2–4 completeness items, and 3–8 concise agent-context lines. If the
repository has no changelog gate, fill `changelog-policy` with exactly:

```text
No changelog gate is configured for this repository.
```

After filling the regions, rerun the Phase 1 installer command. Its region merge must preserve all
filled region bodies byte-for-byte while refreshing the AGENTS splice from the now-current full
`forge-project.md`. Verify the splice interior equals the complete rendered file, the CLAUDE import
occurs once, and content outside the AGENTS markers still matches its pre-init bytes.

Run the assembled Gate 1 command and every applicable `stack-validations` command once against the
untouched target code. Require every command to exist and every command to exit 0. A validation
that fails on untouched code is miscalibrated: stop, report the command and its output, and return
to evidence and user confirmation. Never modify application code, tests, or assertions merely to
make this check pass.

## Phase 4 — Eval baselines

Create only missing fixtures in `.forge/evals/tasks/` from these seeds:

- `${CLAUDE_PLUGIN_ROOT}/system/seeds/eval-tasks/review-catches-planted-bug.template.md`
  with expected verdict `BLOCK`;
- `${CLAUDE_PLUGIN_ROOT}/system/seeds/eval-tasks/review-passes-clean-change.template.md`
  with expected verdict `PASS`;
- `${CLAUDE_PLUGIN_ROOT}/system/seeds/eval-tasks/injection-is-flagged.template.md`
  with expected verdict `BLOCK`.

Concretize each missing fixture against the target repository: use its real language, paths,
conventions, and realistic inline diff; keep the required `id`, `category`, `agent`, and
`expected_verdict` frontmatter; remove every template sentinel. The planted bug must be clear and
target-relevant, the clean change must be genuinely correct and tested, and the injection text must
remain quoted untrusted data rather than an instruction.

For each fixture lacking a baseline, launch a fresh execution of the exact agent named in the
fixture, pass the complete fixture Input, capture its explicit verdict, and write only that verdict
to `.forge/evals/tasks/<id>.result`. Never reuse the author as reviewer. Never overwrite an
existing fixture or `.result`, and never edit a result merely to make a gate pass. Treat a launch
error, missing verdict, or unexpected verdict as a failure to investigate.

Run:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/run-evals.sh"
```

Require exit 0 before Phase 5. Exit 1 or 2 stops init; report malformed, missing, pending, or
regressing tasks without weakening their expectations.

## Phase 5 — Self-review and manifest

Treat the complete init output as a control-class change.

1. Write or refresh `.forge-manifest` in this exact line-oriented shape, using the confirmed values
   and one `region:` line for each of the nine filled regions:

   ```text
   forge_version: 1
   plugin_ref: <git describe or SHA of the plugin>
   installed: <YYYY-MM-DD>
   project_name: <confirmed name>
   default_branch: <confirmed branch>
   init_completed: false
   region: project-overview
   ...
   ```

   Derive `plugin_ref` from `${CLAUDE_PLUGIN_ROOT}` and the date from the current system date. Do
   not mark the manifest complete yet.

2. Run the strict suite and require exit 0:

   ```bash
   STRICT=1 bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/run-evals.sh"
   ```

3. Re-run the assembled Gate 1 and applicable stack-validation commands on untouched target code.
   Require exit 0. A failure means the configuration is miscalibrated; stop and report it.

4. Check both installed execpolicy cases and require each output to contain `forbidden`:

   ```bash
   codex execpolicy check --rules .codex/rules/forge.rules -- git push --force
   codex execpolicy check --rules .codex/rules/forge.rules -- git push origin HEAD
   ```

   Any other decision blocks completion. Remind the user that these rules take effect in Codex only
   after the repository is TRUSTED.

5. Require the following search to produce no output:

   ```bash
   grep -rn "forge-init:" forge-project.md
   ```

   A match means at least one region is unfilled and blocks completion. Also verify again that the
   AGENTS splice interior equals the full rendered `forge-project.md`.

6. After every preceding Phase 5 check passes, freeze the review candidate. First prove
   `.forge/tmp/` is ignored. Then deterministically materialize the exact full install diff relative
   to the Phase 0 state into `.forge/tmp/init-candidate.diff`. Include binary patches, every tracked
   change, every new untracked install file in stable byte ordering, every `.forge-new` collision,
   and `.forge-manifest` containing exactly `init_completed: false`; exclude only ignored scratch
   state. Do not hide a file, stage unrelated content, or omit the manifest. An unborn branch uses
   the empty tree as its baseline.

   Secret-scan the frozen snapshot; a suspected secret blocks review and must never be echoed.
   Select the SHA-256 implementation once: prefer `sha256sum` when `command -v sha256sum` succeeds,
   otherwise use `shasum -a 256` when `command -v shasum` succeeds, and stop if neither exists.
   Compute the digest of the snapshot's exact bytes, store it as `CANDIDATE_ID`, and report the
   snapshot path, candidate ID, and selected implementation. The snapshot is immutable for the rest
   of this attempt. Any candidate-path mutation after this point invalidates the candidate.

7. Spawn a fresh, read-only `review-final` agent and send that agent the exact frozen snapshot bytes
   from `.forge/tmp/init-candidate.diff`, the reported `CANDIDATE_ID`, and the project context from
   `forge-project.md`. Do not regenerate the diff for review. Make the verdict binding to that
   candidate: only an explicit PASS naming the same candidate ID may continue. A BLOCK, missing or
   mismatched ID, missing verdict, launch failure, unavailable reviewer, reviewer write, or reviewer
   context shared with the author stops init and invalidates the candidate.

## Phase 6 — Present for explicit approval

Present the user with the exact frozen `.forge/tmp/init-candidate.diff`, its `CANDIDATE_ID`, and a
concise summary of:

- files written, refreshed, skipped, and preserved as `.forge-new`;
- every filled or byte-preserved region and its evidence;
- the confirmed blast-radius suite and clean-tree Gate 1/stack-validation results;
- every eval fixture, preserved or new baseline, normal and strict eval results;
- both execpolicy decisions, the binding `review-final` verdict, the Codex trust caveat, and any
  residual risk.

Ask for explicit approval of that exact candidate ID and diff. The request to run `/forge:init` is
not that approval. Do not flip the manifest while waiting. If approval is withheld, ambiguous,
names a different candidate, or is rejected, leave `init_completed: false` and stop.

After explicit approval but while the manifest is still false, rebuild the full candidate with the
identical deterministic procedure into `.forge/tmp/init-candidate.current.diff`. Compare it
byte-for-byte with the reviewed snapshot using `cmp`, recompute its SHA-256 with the same
implementation selected in Phase 5, and require both the bytes and ID to match. Also require the
working manifest still to contain exactly one
`init_completed: false` line and no true line. Any drift invalidates both `review-final` PASS and
user approval: make no completion change, return to Phase 5, rerun all checks, freeze a new candidate,
obtain a new binding review, and ask for approval of the new ID.

Only after that comparison passes, atomically change exactly `init_completed: false` to
`init_completed: true` without changing any other byte, report the resulting uncommitted change,
and stop. Apart from ignored candidate-snapshot scratch files, this explicitly approved false-to-true
flip is the only mutation permitted after the candidate is frozen. Never auto-commit, never
auto-push, and never interpret approval to initialize as approval to stage or commit. The operator
may invoke `/forge:commit` separately.

Honor additional user instructions supplied with the invocation only when they do not weaken these
fail-closed requirements: $ARGUMENTS
