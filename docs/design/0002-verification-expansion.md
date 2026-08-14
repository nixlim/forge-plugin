# forge-plugin — Verification Expansion: Test Quality, Invariants, Risk Tiers, Drift, Durable Intent, and dcg Integration

**Status:** Draft for review, 2026-08-11 (Igor + Claude). Records decisions D6–D14,
extending `0001-founding-decisions.md`. Input for a spec revision; not the spec.
**Revised:** 2026-08-11 after adversarial design review (codex-review-01: BLOCK, 2 CRITICAL /
5 MAJOR — all findings accepted; adjudication in run journal decision-02).
**Revised:** 2026-08-11 after binding review-final iteration 1 (BLOCK, 2 CRITICAL /
9 MAJOR / 4 MINOR — all 15 adjudications incorporated in this candidate).

**Motivation:** the AI-native SDLC analysis (2026-08-11, this session; source research
document "Challenging the traditional SDLC", v1.1) found forge's phase-4/5 core strong
but identified gaps concentrated on the *sensor* half of Böckeler's guides/sensors 2×2:
no test-quality sensor, no continuous drift sensing, no durable intent record, and no
downward risk tiering (every change pays the full chain — the Scott Logic
ceremony-cost failure mode). This document resolves all of them plus
property-based/scripted invariants.

Cross-cutting constraints carried forward from 0001 and the spec:

- Plugin runtime stays Python ≥ 3.10 stdlib + bash. Target repos use their own
  toolchains — feasibility mining happens at `/forge:init` time, per stack.
- Journal schema stays the upstream seven entry types. `validate --gates` recognizes
  exactly `gate-1: `/`gate-2: `/`gate-3: ` and rejects other `gate-*` prefixes
  (FR-023) — new sensors therefore enter as **ordinary verifications first**, and are
  promoted to enforced gate prefixes only via a control-class `validate` change.
- Everything below is control-class: spec revision → adversarial review → explicit
  approval before implementation.

---

## D6 — Test-quality sensor: mutation testing where feasible

**Resolution:** mutation testing is adopted as a *scoped, advisory-first* sensor, not
a universal blocking gate. The Python AST assertion sensor is the one deliberate
blocking escalation recorded below; non-Python assertion heuristics remain advisory.

- New `forge-project.md` region `mutation-testing`: a `| category | command |
  changed-files form | timeout |` table. `timeout` is a positive integer number of
  seconds and defaults to 600 when a legacy row has no column/cell. `/forge:init`
  mines feasibility per stack (mutmut / cosmic-ray for Python, cargo-mutants,
  Stryker, go-mutesting, …). Where no tool exists, init fills the region with the
  explicit text "No mutation tool available for <stack> — assertion-quality fallback
  only." — mirroring the `changelog-policy` pattern: *explicitly declared absence is
  a filled state*. "Where feasible" is recorded, never silently skipped.
- **Firing points:** (a) at `/forge:worktree-merge`, when the merge diff touches test
  files or adds source files, the *changed-files-scoped* mutation command runs after
  Gate 1; (b) the *full-suite* run belongs to the drift schedule (D9), never to the
  per-change path — per-change full mutation is the known cost failure at CI scale.
  Both firing points use the row/default timeout and an isolated process group;
  expiry kills that group. In merge, nonzero, timeout, or surviving-mutant results
  are Gate 3 evidence and never block or satisfy a gate. In drift, the same outcomes
  are nonfatal findings in the exit-1 summary and do not prevent the remaining
  mechanical inventory from running.
- A malformed `mutation-testing` region emits exactly `forge: executable policy row
  malformed`, skips the mutation run, and enters Gate 3 evidence without blocking.
  This is intentionally different from D7: malformed `invariants` remains
  fail-closed.
- **Recording:** journal `verification` with `criterion: "mutation: <scope>"` —
  deliberately *not* a `gate-*` prefix, so Level B validation is untouched. The
  observation includes scope, timeout, and completed/timed-out/malformed-skip
  disposition. A failing score is surfaced to the reviewer and recorded; it does
  not block.
- **Promotion path:** after a calibration period (enough drift reports to know the
  baseline score and runtime cost), a control-class change adds a `gate-1m: ` prefix
  to `validate --gates` and flips the merge-time scoped run to blocking. The
  threshold then lives in the `mutation-testing` region.
- **Seed contract:** every stack in
  `system/seeds/validation-snippets/stacks.md` gains (a) an assertion heuristic or
  explicit absence, (b) a mutation tool/changed-files form or explicit absence, and
  (c) a property library/subset command or explicit absence. Init records absences;
  it never invents a command.
- **Stdlib fallback sensor:** `scripts/forge/check-test-quality.py` uses Python `ast`
  for test functions with no recognized assertion/raise/expected-exception. An
  unwaived Python AST finding exits 1 and blocks commit Step 2. A non-Python seeded
  heuristic prints its findings and exits 0; a stack with no seeded heuristic prints
  an advisory and exits 0. A test file can carry one narrow, auditable line
  `# forge-assertion-waiver: <reason>`; it applies only to that file and the path plus
  reason remains review evidence, without skipping tests, mutation, or invariants.
- **REDLINE — D6 assertion escalation:** the earlier D6 draft described every
  assertion-free-test detector as a sensor. The accepted design deliberately
  escalates only the Python AST path to blocking because it has a structural parser;
  heuristic non-Python paths remain advisory to avoid false-positive gate failures.

**Rejected:** blocking mutation gate from day one (unknown runtime cost and score
baseline; Thoughtworks positions mutation as a meta-gate to *revive carefully*);
plugin-shipped mutation engine (violates stdlib-only; the target repo's toolchain
owns this); coverage thresholds as a substitute (the exact signal the research doc
shows pointing the wrong way).

## D7 — Property-based and scripted invariants, enforced by script/hook

**Resolution:** every declared invariant must be an *executable check*, not review
prose. "A gate is a command; an invariant without a command is a review bullet, and
it is moved there explicitly."

Two invariant kinds, one region. New `forge-project.md` region `invariants`:
`| invariant | check command | enforcement point |` with enforcement points
`commit` (Step 2), `merge` (Gate 2), and `hook`.

- **Code-level properties** (property-based tests: hypothesis, proptest, fast-check,
  jqwik — mined per stack by init): live in the target repo's test suite, so Gate 1
  already enforces them; the region row names the property-test subset command so
  the invariant is *visible and auditable*, and so the reviewer knows which
  invariants are machine-checked (and stops re-litigating them — noise reduction).
  Init seeds guidance from the per-stack property-library entry in `stacks.md`; an
  explicit absence is recorded where none exists, and the invariant then falls back
  to a scripted check or a review bullet rather than an invented library command.
- **Repo/system invariants** (layering rules, forbidden imports, path conventions,
  schema shapes, "no absolute paths", "no secrets in config"): scripted checks,
  fail-closed at their declared gate. These run in commit Step 2 and merge Gate 2
  alongside stack-validations — invariant failure is a gate failure.
- **Hook enforcement (early warning layer):** a new plugin hook script
  `scripts/forge/invariant-guard.sh` registered PostToolUse on Edit/Write. It runs
  only invariants marked `hook`, under a strict per-check time budget (≤2 s), and is
  inert outside forge-initialized repos. Hook findings are *feedback to the working
  agent* (fix now, cheaply), not the enforcement point — blocking stays at the
  gates, where fail-closed semantics and audit already exist. Rationale: PostToolUse
  cannot un-write a file, and making a hook the enforcement point would put a
  gate-strength control in the least auditable layer; the gate chain is where
  control-integrity policy already binds.
- **Policy source and execution discipline (revised 2026-08-11):** every enforcement
  surface — the PostToolUse invariant-guard hook *and* the gate-time invariant
  execution at commit Step 2 / merge Gate 2 — reads the invariant/policy regions
  from the **committed HEAD revision** of `forge-project.md`
  (e.g. `git show HEAD:forge-project.md`), never the working-tree copy. Region
  content is passed to checks as argv, never shell-interpolated; checks run in an
  isolated process group with capped output; at gate enforcement a timeout is
  fail-closed (the hook layer stays advisory/warn within its ≤2 s budget). Mutable
  working-tree content is untrusted data per `rules/untrusted-input.md`; only
  reviewed, committed policy is executable — an unreviewed working-tree edit to
  `forge-project.md` therefore cannot inject a command into any enforcement
  surface before it has passed review. The spec revision must state this
  dependency explicitly.

**Rejected:** invariants as constitution/review prose only (inferential sensor doing
a computational sensor's job — the exact over-weighting of guides the research doc
warns about); PreToolUse blocking on every edit (latency tax on all agents, and
enforcement would precede the change being complete); a plugin-invented invariant
DSL (commands are the DSL; stdlib-only, zero new syntax).

## D8 — Risk-tier task routing: fast / standard / hard

**Resolution:** three tiers, assigned per change, controlling review depth. Tiering
only ever *reduces* ceremony below today's default on an explicit allowlist;
everything else is unchanged or stricter.

- New `forge-project.md` region `risk-tiers`: a `| tier | path patterns |` table,
  a per-category `| formatting-only category |` opt-in table, and the fixed
  dependency-manifest block below. A separate `trigger-paths` region contains only
  positive repository-relative Git pathspec globs and is used **only** for tiering.
  `project-triggers` remains mechanically inert prose review context.
  A legacy repo with no `trigger-paths` region, or a filled region containing exactly
  `No trigger paths configured.`, contributes zero glob rows; the control floor still
  applies. A malformed nonempty trigger row makes the diff hard.
- Built-in hard floor (non-narrowable, like the `control` category): the entire
  built-in/project-extended `control` category and all matched `trigger-paths` rows
  are **hard**; anything matching no tier row defaults to **standard**. Fail-closed
  by construction.
- **fast** — mechanical gates only: targeted Gate 1, Gate 2 stack-validations,
  applicable assertion-quality and invariant checks, changelog policy, secret scan,
  halt/lock. *Skips adversarial review.* The gate-pass
  marker carries new DM-006 annotation lines recording both the derived tier AND
  the policy revision — `tier: fast` and `policy: <sha>` (the commit SHA whose
  `forge-project.md` supplied `risk-tiers`), parallel to `skip: user-directed` —
  so the commit guard still requires a chain-written marker and the skip of review
  is durably distinguishable from a user-directed skip.
  Initial eligibility floor shipped in the template: `docs/**` and the reserved
  `@formatting-only` selector; the formatting-only category table initially contains
  only `docs`. Formatting-only is opt-in per `file-categories` category and valid
  only for a committed whitespace-insensitive category row. The
  non-narrowable exclusion floor is Python, YAML, Make, shell, Haskell, Nim, and
  anything init cannot classify. It accepts only modifications of existing
  nonbinary text files for which corresponding leading whitespace is byte-identical
  and the blobs differ solely in trailing space/tab or CR/LF line-ending style.
  Any leading/interior whitespace change, file or line addition/deletion, rename,
  copy, type change, or binary change disqualifies; a Python de-indent and a YAML
  nesting change therefore derive standard even if hostile policy tries to opt them
  in.
- **Dependency bumps stay standard.** The template's plugin-owned fixed block inside
  `risk-tiers` is control-class and initially contains exactly: `package.json`,
  `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `requirements*.txt`,
  `pyproject.toml`, `poetry.lock`, `uv.lock`, `Cargo.toml`, `Cargo.lock`, `go.mod`,
  `go.sum`, `Gemfile`, `Gemfile.lock`, `pom.xml`, `build.gradle*`, `composer.json`,
  `composer.lock`. Init preserves the block; the classifier and guard parse this
  same committed source, never duplicate the list. A stack whose manifests are
  unknown is at least standard. The slopsquatting/keyv evidence makes deps
  supply-chain surface, not low-risk churn.
- **standard** — today's default chain unchanged: review-cheap (Codex, fresh,
  read-only) with the full iteration protocol.
- **hard** — review-final binding verdict; where the change is control-class,
  explicit human approval as today. A `trigger-paths` match promotes to hard even
  outside control paths (auth, crypto, migrations — per-repo).
- **Tier is derived from the diff at gate time**, not only declared at decompose
  time. Declared tier may inform implementer routing (advisory: a fast-tier task may
  run the implementer at lower effort; model/effort values remain control-class per
  FR-030), but the gate-time diff classification *wins and only promotes*: a task
  declared fast whose diff touches a standard/hard path is promoted automatically.
  Demotion at gate time is impossible. Tier classification never reads the
  working-tree `forge-project.md`: classifier and guard independently parse the
  same committed `risk-tiers` (including formatting/dependency blocks),
  `trigger-paths`, and `file-categories` source and apply the identical predicate to
  the exact staged diff. The marker's `policy: <sha>` must be ancestor-or-equal to
  HEAD and those regions must remain byte-identical; any mismatch or eligibility
  drift is denied (revised 2026-08-11).
- **Audit + monitoring:** each fast allowance, fast policy/eligibility denial, user
  skip, review BLOCK, halt event, and guard denial appends one compact JSON line in
  `.forge/tmp/decisions/events.jsonl`; successful gate-chain commits also emit the
  denominator event. `aggregate-telemetry.sh` extends its existing CSV with the
  corresponding counters. The eligible commit population is all successful
  gate-chain commits in the window, regardless of tier/skip. Every drift report
  records the rate; quarter-over-quarter comparison reads the prior **committed**
  reports under `.forge/history/drift/`, never transient event/CSV files. Benchmark
  discipline borrowed from Cloudflare's 0.6% break-glass rate: growth without a
  matching committed allowlist change becomes a drift finding.

**Rejected:** auto-merge without any marker (guard hook bypass — weakens an existing
control); LLM-classified risk tier (the classifier becomes an uncalibrated judge
deciding its own scrutiny level; globs are dumb but auditable); time-based fast
lanes ("small diff = safe" is exactly the assumption the research doc's deep-vs-
shallow error-shift evidence breaks).

## D9 — Continuous drift sensing

**Resolution:** wire the constitution's existing-but-orphaned `review-periodic`
profile into an operable loop with a mechanical half and a semantic half.

- **Mechanical half — `scripts/forge/drift-check.sh`** (bash + stdlib, CI-cron
  friendly, no LLM): runs STRICT evals; re-runs Gate 1 and Gate 2 on the clean tree
  (miscalibration detection — a gate failing on untouched code); full invariant
  sweep; full-suite mutation run where configured (D6); file-category coverage
  check (tracked files matching no `file-categories` row = classification drift);
  region staleness (unfilled sentinels, commands referencing deleted paths);
  window-bounded telemetry aggregation (skip rate, fast-path rate and
  policy/eligibility denials, eligible gate-chain commit population, review
  iteration counts, block rate, halt/guard denials). Every emitting surface registers
  an in-flight writer before checking the prune lock. If the lock is present, the
  emitter unregisters, revalidates stale ownership under the lock-state mutex, and
  retries at a sub-second interval for at most 5 seconds; expiry skips only the append
  and records `event-append-lock-timeout` through the advisory failure audit without
  changing the primary result or exit status. Once no prune lock is present, the
  emitter uses one checked POSIX `O_APPEND` write without acquiring
  `.forge/tmp/events.lock`. The checker alone holds that lock across writer drain,
  prune read, and atomic replace, following the existing owner-only-release and
  fail-closed ownership convention.
  The prune cutoff is `min(generated_at − retention_bound, window_start)`: it
  removes only entries with `at` earlier than the cutoff, so it never removes an
  entry with `at >= window_start`. A prune housekeeping failure is recorded in
  `telemetry.event_prune.failure` and leaves the aggregation-produced exit code
  unchanged rather than causing exit 2; a successful prune records entries removed
  plus the new oldest event. The checker applies the explicit window bounds directly
  to the counters embedded in JSON and does not request, write, retain, or read a
  CSV artifact. Output is Drift summary schema v1 with
  `schema_version: 1`, a consistently object-valued `status` whose state is `ok`,
  `findings`, or `failed`,
  typed checks/telemetry arrays/objects, and one finding shape shared with the
  semantic severity ladder. The spec pins literal objects for exit 0, exit 1,
  dirty-precondition exit 2, and non-dirty exit 2. The transient
  `.forge/tmp/drift/<UTC-date>.json` is overwritten on another run the same day; it
  is not the durable collision-free store.
- **Semantic half — new skill `/forge:drift`:** consumes only the mechanical Drift
  summary schema v1 JSON, including its window-bounded telemetry object, then runs
  a review under the `review-periodic` profile (drift from standards, recurring
  failure patterns, accumulating risk). The FR-093 Stop-hook artifact
  `.forge/tmp/telemetry-latest.csv` is never input to `drift-check.sh`,
  `/forge:drift`, or the committed report. Findings use the
  normal severity ladder; a CRITICAL drift finding (e.g. evidence of gate gaming,
  eval regression) writes `.forge/tmp/drift-block`, alongside ignored locks and
  markers, containing the finding summary, timestamp, and committed report path.
  The workflow skill's run-open preconditions check for it and REFUSE to open new
  runs while it is present — explicitly a run-open refusal, not a halt sentinel:
  agents never create or clear `AGENT_HALT` sentinels. Forge agents/cleanup also
  never clear this file; clearance is operator-only manual deletion after reading
  the report. Its ignored location leaves all clean-tree predicates unchanged,
  never prevents `drift-check.sh` from reaching its ordinary exit 0/1, and is not
  inspected by merge gates; non-CRITICAL drift never stops merge. Otherwise drift
  output is advisory (revised 2026-08-11).
- **New `forge-project.md` region `drift-config`** (joins the DM-003 additions):
  exactly one cadence (`cadence: <positive-integer>d`, default `14d`), committed
  report retention (`retention: forever|<positive-integer>d`, default `forever`),
  and event-stream retention (`event-retention: <positive-integer>d`, default
  `400d`). Event retention must be at least `366d`, the maximum span of four
  consecutive UTC quarters; a lower committed value is malformed. Missing/invalid
  configuration, including a below-floor event-retention value, falls back to all
  three defaults — drift sensing never fails closed. Report retention remains
  operator-only; `drift-check.sh` alone uses event retention to prune `events.jsonl`
  and records the prune outcome in schema-v1 JSON. The cutoff clamp is the
  mechanical guarantee; lower-bound validation is the operator-facing signal.
- **Scheduling (no daemon exists):** three layers. (a) documented CI scheduled job
  invoking `drift-check.sh` (mechanical, cheap, needs no Claude); (b)
  `scripts/forge/drift-staleness.sh`, registered by plugin `hooks/hooks.json` on
  SessionStart and as one member of the Stop union with telemetry aggregation,
  warns when the newest committed report is older than the cadence in
  `drift-config` (default 14 days); (c) the operator runs `/forge:drift` on that
  nudge. The installed Codex hook layer retains Stop only and no SessionStart. Every
  plugin Stop/SessionStart command is silent, exit 0, and write-free outside a repo
  with `.forge-manifest`. The plugin never self-schedules semantic work.
- **Output is durable:** `.forge/history/drift/<date>.md`, committed via the commit
  chain. It is docs/fast-eligible subject to D8's promote-only hard floors; when it
  remains fast, the report's own commit does not create a review loop. History
  collision suffixes prevent overwrite, and prior-quarter comparisons read these
  committed reports only. The current report sources its window and counters
  exclusively from the mechanical JSON's telemetry object.

**Rejected:** drift checks folded into every commit (wrong cadence — drift is
*outside* the change lifecycle by definition; per-commit placement is exactly what
the research doc says teams get wrong); LLM-run scheduled autonomous drift sessions
(unattended semantic authority contradicts the risk/authority model — `advisory`
until a human reads it).

## D10 — Durable intent: the archive step

**Resolution:** the run journal stays git-excluded (upstream compatibility, FR-015);
a *distilled, committed* record becomes mandatory at close.

- The gated close sequence gains one step, with the archive landing BEFORE the
  report: `validate --gates → run_closed → validate --gates → archive → report.md`
  (revised 2026-08-11; the previous ordering was circular against the refusal rule
  below).
- **Archive** = `.forge/history/runs/<run-id>.md`, committed: the run goal;
  per-task acceptance criteria; every `decision` with its `basis` (including the
  FR-124 independent-plan document, copied in); the gate evidence table (which
  gates, verdicts, iteration counts); residual risks and follow-ups; provenance
  (run ID, starting and closing HEAD SHAs recorded from command output). In short:
  the *why* and the *evidence*, without the event-stream bulk.
- The report skill refuses to write `report.md` until the archive file exists and
  is committed (extends the existing "report refused while validation dirty"
  rule).
  The archive commit rides the chain as docs/fast-eligible, subject to D8's
  promote-only hard floors; when it remains fast, durable intent costs one
  mechanical-gate commit rather than a review loop.
- `.forge/history/` is committed (never gitignored) and joins the `docs` file
  category. `.forge/tmp/` remains transient; `.forge/evals/tasks/` remains control,
  while `.forge/evals/candidates/` is advisory/docs-class until promotion.
- This makes the repository pass the research doc's SDD test — "what happens to the
  spec after merge?" — with: *it is committed, versioned, and greppable next to the
  code it explains.* Onboarding (human or agent) reads `.forge/history/runs/`
  as the decision log the git history alone cannot supply.

**Rejected:** committing the full journal (event-stream noise, size, and upstream
tooling expects the exclude protocol); git notes (invisible to most tooling and to
agents reading the tree); relying on the PR description (forge reintegrates by
fast-forward push — there is no PR to carry it).

## D11 — dcg command-guard integration at init (added 2026-08-11)

**Resolution:** `/forge:init`, during its mechanical phase, checks `command -v dcg`.
When dcg is present it runs `dcg allow core.git:branch-force-delete --project
--reason "forge worktree-merge deletes branches only after merge-base containment
proof"`, idempotently (skipped when `dcg allowlist list` already shows the entry),
and records the action in the init output. Absence of dcg is not an error.

Rationale: worktree-merge cleanup deletes branches with `git branch -D` only after
a merge-base containment proof, which dcg cannot see; in hook mode the resulting
WARN becomes a permissionDecision "ask" that interrupts every merge.

**Rejected:** global rule demotion (broader than needed); skill-side pattern
evasion (violates control-integrity).

## D12 — Migration from upstream forge (added 2026-08-11)

**Problem:** the plugin has no concept of upstream forge (github.com/nixlim/forge, the
non-plugin installation) as a pre-existing installation in a target repository. Both
systems write a root file named `.forge-manifest` with incompatible schemas, and the
region *names* match while their *file locations* do not. Evidence gathered 2026-08-11 by
read-only inspection of both installers (`forge/bin/forge-install.sh` vs
`forge-plugin/scripts/forge/install.sh`) and both template trees.

Today's behaviour, both paths bad:

- **Skill path:** `/forge:init` Phase 0 rejects upstream's manifest as malformed (no
  `plugin_ref`; `region: <name> (<file>)` form) and refuses. Meanwhile the PreToolUse
  guard arms off the *presence* of `.forge-manifest`, which upstream wrote — so enabling
  the plugin denies every `git commit` while the only command that could authorize one
  (`/forge:commit`) requires a `forge-project.md` that init just declined to create. A
  fail-closed deadlock with no in-product recovery.
- **Script path (`install.sh` run directly):** silent overwrite of
  `.codex/agents/{implementer,review-cheap}.toml` (preservation covers only
  `config.toml|hooks.json`), zero region carry-forward, a double-appended gitignore block
  (upstream's header is `# --- forge agent system (appended by forge-install.sh) --- #`;
  the plugin's guard is a whole-line `grep -qxF` against a shorter string), an
  AGENTS.md carrying two contradictory instruction hierarchies, and the plugin's own
  `.codex/` layer never activating (upstream's files lack the `# forge-managed` sentinel,
  so the plugin writes `.forge-new` siblings and leaves upstream's routing live).

**Resolution:** `/forge:init` gains an explicit migration branch. Detection, salvage, and
an honest orphan report — never silent adoption, never silent loss.

- **Detection.** An existing `.forge-manifest` is classified before anything else:
  *plugin-schema* (an anchored `^plugin_ref: ` line) → today's re-init path, unchanged;
  *upstream-schema* (has `upstream_commit:`, or any `region: <name> (<file>)` line) →
  migration; *neither* → malformed, refuse as today. Presence of `.opencode/` or
  `opencode.jsonc` corroborates and is reported, but the manifest is the discriminator.
- **Guard deadlock fix (control-class, and the reason this cannot wait for a later
  release).** The commit guard's marker requirement stops keying off the bare filename.
  It arms when `HEAD:.forge-manifest` carries an anchored `^plugin_ref: ` line — the
  DM-005 match rule, never an unqualified substring — **or** when `.forge-manifest`
  exists in the worktree and does *not* parse as upstream schema. The `plugin_ref` test
  applies to the `HEAD` disjunct only: a worktree manifest parsing as neither schema is
  malformed, and malformed arms. A repo carrying only upstream's manifest gets the halt
  check alone, exactly like any non-forge repo, so enabling the plugin can never deadlock
  commits in a repo it does not yet manage. What FR-090 preserves is stated precisely:
  deleting a committed plugin manifest, or staging its deletion, still does not lift the
  guard, because the `HEAD` copy still counts. The worktree disjunct cannot be written as
  a `plugin_ref` test, because in the FR-083 first-install bootstrap window
  `.forge-manifest` exists in the worktree only and the bootstrap commit is itself
  guard-mediated — a plain working-tree edit stripping the `plugin_ref` line (an Edit,
  which no PreToolUse hook intercepts) would drop the guard to halt-only and admit an
  unauthorized commit of the bootstrap policy.
- **Region salvage.** Migration reads upstream's *actual* region locations rather than the
  plugin's single file, and carries filled bodies forward byte-identically into
  `forge-project.md`: `file-categories`, `stack-validations`, `changelog-policy`,
  `review-prompt-project-focus` from `.opencode/rules/commit-workflow.md`;
  `gate1-test-command` from `.opencode/rules/worktree-workflow.md`;
  `completeness-project-items`, `project-triggers` from
  `.opencode/rules/review-constitution.md`; `project-overview` from `AGENTS.md`;
  `agent-project-context` from `.codex/agents/implementer.toml` (the plugin keeps one
  copy where upstream spreads the region across 21 template files — 7 agents ×
  `.claude/agents/`, `.codex/agents/`, `.opencode/agents/` — as counted today; the actual
  set is enumerated at migration time, and divergent copies are surfaced for operator
  choice, never silently merged). Upstream regions with no plugin destination
  (`project-docs`, `project-policies`, `conversational-routing`, `test-commands`, and
  `skill-project-context` from `.opencode/skills/*/SKILL.md`) are quoted verbatim into
  the migration report so nothing vanishes unrecorded. That orphan set is not a
  hand-written list: migration enumerates every `FORGE:REGION <name> BEGIN` marker found
  in the upstream tree and reports whichever names have no plugin destination, so a
  region added upstream later cannot silently drop out. Fourteen names today — nine
  salvaged, five orphaned. A salvaged region is still subject to FR-082: the assembled
  Gate 1 and stack validations must pass on the clean tree, or init stops.
- **Eval continuity (the only place today's behaviour silently weakens a gate).** Upstream
  fixtures and committed `.result` baselines under `.opencode/evals/tasks/` are copied
  into `.forge/evals/tasks/` **before** seeding, and baselines are never re-recorded for
  an imported fixture. Re-minting baselines from current agents would launder an existing
  reviewer regression into a fresh "correct" baseline; that is forbidden. Seed fixtures
  are added only for gaps the imported suite does not already cover, and `STRICT=1
  run-evals.sh` must pass against the imported baselines before Phase 5.
- **Binding-reviewer collision.** Upstream's `.claude/agents/review-final.md` declares the
  same `name: review-final` as the plugin's agent and, being project-scoped, wins
  resolution — so the binding verdict silently comes from an agent anchored on the
  upstream constitution path. Migration detects it, and requires operator-approved
  removal or rename before `init_completed` flips true. Init refuses to complete while a
  project-scoped `review-final` shadows the plugin's, because every gate-3 verdict after
  that point would be attributable to the wrong reviewer.
- **`.codex/` layer.** Upstream-authored `config.toml`/`hooks.json` are recognised by
  their upstream content signature (not by the `# forge-managed` sentinel they predate)
  and are treated as forge-managed for replacement purposes, with the originals preserved
  as `<file>.pre-migration` — so the plugin's two-agent routing actually takes effect
  instead of silently sitting in `.forge-new` files. Upstream's nine unused agent TOMLs
  are left on disk, deregistered by the replaced `config.toml`, and listed in the report.
- **Gitignore reconciliation.** A substring test on `--- forge agent system` matches
  upstream's longer header, but it is a *detection* signal only, never an append guard.
  The two blocks differ in content — upstream ignores `/.tmp/*`, the plugin ignores
  `/.forge/tmp/` — so skipping the append on a header match would leave `.forge/tmp/`
  unignored and the tree permanently dirty: DM-007's premise fails, FR-160 returns
  `dirty-worktree` on every drift run, FR-060(a) blocks every merge, and FR-170 refuses
  every close. Migration therefore reconciles block **content**: it appends the
  plugin's missing entries under a distinct plugin header, or rewrites upstream's block
  in place. The post-migration invariant is asserted before init completes — `git
  check-ignore .forge/tmp` must succeed, and `.forge/history/` must **not** be ignored.
- **Orphan report (mandatory output).** Migration writes
  `.forge/history/migrations/<date>.md` — committed, same durability rule as DM-008 —
  listing every artifact left in place and still live, enumerated from what is actually
  on disk at migration time rather than from a fixed literal list: `.opencode/**`,
  `opencode.jsonc`, `.claude/commands/*`, `.claude/settings.json`'s Stop hook,
  `.agents/`, the deregistered agent TOMLs, the legacy `.tmp/` state directory and its
  `.tmp/.commit-lock`. The report names the two live cross-system facts explicitly: the
  `AGENT_HALT` sentinel path is shared (the kill-switch works across both systems) and
  the rebase lock path is identical (merge serialization survives), while the **commit
  lock path is not** (`.tmp/.commit-lock` vs `.forge/tmp/commit-lock`), so running
  upstream's `/commit` and `/forge:commit` concurrently is unsafe until the legacy
  command surfaces are removed. Removal of legacy trees is the operator's decision,
  never automatic — migration reports, the operator disposes.

**Rejected:** silent adoption of upstream state (violates the control-integrity
requirement that gate configuration changes be visible and reviewed); automatic deletion
of `.opencode/**` and the legacy `.claude/` command surfaces (destructive, and they may
still be in use by other harnesses — the operator decides); re-minting eval baselines from
current agents (laundering a possible regression into a passing baseline); treating the
bare presence of `.forge-manifest` as proof of a plugin installation (the defect that
causes today's deadlock); and leaving migration to a documented manual procedure (the
failure is silent and the guard deadlock is not self-evident — this has to be mechanical).

**Spec scope:** D12 becomes FR-180..FR-18x plus a redline to FR-090's manifest predicate
and FR-101's baseline rule, in a **separate Revision 3** (run task-09), not in Revision 2.
Revision 2's review loop is at iteration 4 of the 8-iteration cap; folding a new FR range
into a converging candidate would consume the remaining budget and mix two unrelated
review histories. The guard-predicate redline is the one piece that could justify
promotion into Revision 2 if the operator wants the deadlock closed sooner.

## D13 — Multiple agents in one repository (added 2026-08-12)

**Problem:** forge supports parallelism *within* one orchestration run — per-task
worktrees, disjoint file ownership, ≤10 concurrent Codex executions — but not
several independent orchestrators in the same repository. FR-014 refuses to open
a second run outright, and the spec already records the gap: "Concurrent
orchestration runs in one repository — the single-active-run rule (FR-014) covers
the release; multi-run coordination needs its own locking design" (spec:98).

Evidence gathered 2026-08-12 by inspecting the lock scripts, the guard, and both
run journals.

### What already holds under concurrency

These are verified, not assumed:

- **Worktree isolation.** Each implementer runs in its own `git worktree` with
  the Codex sandbox confined to it (FR-131/FR-132); worktrees have independent
  indexes, so staging cannot bleed.
- **Locks are worktree-transparent.** `commit-lock` and `agent-rebase.lock`
  resolve through `git rev-parse --git-common-dir`, so every worktree contends
  for the *same* lock. Proven in run-20260808 check-15: a worktree acquire
  blocked against the main-checkout lock and timed out naming it.
- **Kill-switch is repo-wide.** `AGENT_HALT` resolves to the main checkout root
  from any worktree.
- **Event appends are atomic on supported local POSIX filesystems.** Emitters register
  in-flight writers, wait up to 5 seconds with sub-second retries while a live prune
  owns `.forge/tmp/events.lock`, and make one checked `O_APPEND` write after the lock
  clears. A timeout skips the append and records `event-append-lock-timeout` through
  the advisory failure audit. Emitters never acquire the lock; it is reserved for
  prune read-and-replace.

### The primary defect: repo-scoped marker, session-scoped work

`.forge/tmp/commit-authorized` is **one file for the whole repository**, but
FR-050 deliberately does *not* hold the commit lock across the Step 4 review
loop (holding it would serialize reviews, which are the slow part).

Sequence with two agents:

1. A stages, reviews, writes marker(hash A).
2. B stages in its own worktree, reviews, writes marker(hash B) — clobbering A's.
3. A acquires the commit lock, recomputes its staged-diff hash, sees a mismatch,
   and is denied.

The outcome is **fail-closed** — no unauthorized commit — but it is a livelock:
each collision costs A a full review cycle, and nothing prevents indefinite
mutual clobbering. Timings put a review cycle at 6–17 minutes, so this is
expensive, not merely inelegant.

### Secondary gaps

- **Journal ownership is convention, not enforcement.** The contract says "one
  Claude orchestrator owns and appends to journal.jsonl … Do not let two
  orchestration loops write the same run" — nothing enforces it. Two writers
  produce interleaved or duplicated entry identities, which the contract says
  can only be repaired by starting a successor run.
- **`telemetry-latest.csv` is overwrite-not-append**, so the last Stop hook to
  fire wins and concurrent sessions lose each other's aggregation.
- **FR-014 is a blanket refusal.** It protects correctness by forbidding the
  scenario rather than supporting it.

### Resolutions

- **Session-scoped commit state.** The gate-pass marker becomes per-session
  rather than per-repo — either `.forge/tmp/commit-authorized.<session>` or a
  content-addressed `.forge/tmp/authorized/<staged-diff-sha256>` — and the guard
  resolves the marker belonging to *its* invoking context. Content-addressing is
  the stronger option: the marker's identity already *is* the hash, so a
  collision is impossible by construction and the guard's existing
  recompute-and-compare becomes a lookup. DM-006's grammar and the 30-minute
  staleness rule carry over unchanged; only the path changes. Stale markers are
  swept by age.
- **Journal ownership enforcement.** A run directory gains an owner record
  (session PID + host + start time) written at `run_started` and checked before
  every append, using the same stale-PID takeover discipline as the commit lock.
  A foreign live owner is a hard refusal, not a warning.
- **Run registry replacing the blanket refusal.** FR-014 becomes: a second run
  may open when its declared file scope is disjoint from every open run's, or
  when the operator designates it a successor. Overlapping scopes are refused
  with both run IDs named. This keeps the property FR-014 was protecting
  (two runs never mutate the same files) while permitting the case the operator
  needs.
- **Append-only telemetry.** `telemetry-latest.csv` becomes per-session or
  append-with-session-column, so no session's aggregation is lost.
- **A real concurrency harness.** Tests that run two commit chains and two
  merges *simultaneously* against one repository and assert: no marker
  cross-admission, no interleaved journal identities, no lost telemetry rows,
  no deadlock, and correct fail-closed behaviour on genuine contention. Nothing
  here is trustworthy without it — every existing concurrency claim in this
  system is proven by single-threaded tests plus inspection.

**Rejected:** holding the commit lock across the review loop (serializes the
slowest phase — reviews take 6–17 min — and converts a livelock into a
guaranteed queue); per-worktree `.forge/` state (breaks the worktree-transparent
locking that currently works, and fragments the audit log); advisory-only
documentation telling operators not to run two agents (the failure is silent to
the second agent and the deadlock is not self-evident).

**Spec scope:** D13 becomes FR-190..FR-19x plus redlines to FR-014 (run
admission), FR-050/FR-054 (marker path), DM-006 (marker location), and DM-007
(state layout), in its own revision after the current run closes. It touches the
guard and marker contract that task-05 is modifying, so it must not be
implemented concurrently with it.

## D14 — Journal-derived learning loop (added 2026-08-12)

**Problem:** forge has the *doctrine* for learning from its own failures and no
*mechanism* for it. Three places already say the system should learn:

- **FR-102** makes journal-derived fixtures the preferred growth source for the
  eval suite: "a recorded failure run supplies the exact prompt (fixture Input),
  the expected verdict, and provenance (run id + execution id)".
- **`rules/evaluation-harness.md`**: "New real-world failure patterns should
  become golden fixtures."
- The constitution's **`review-periodic`** profile lists "recurrence of known
  failure patterns" as a thing reviews must detect.

Nothing invokes any of it. No code reads a journal and produces a fixture, a
rule, or a pattern report. This is the guides-heavy / sensors-light imbalance
that motivated D6–D10, applied to the harness's own memory — and the field data
confirms the consequence: in both myagentsgigs and palimpsest the eval suite was
seeded at install and **never re-run or grown**, so a year of recorded failures
produced zero fixtures.

The cost is measurable in this run. It generated at least five distinct,
*repeating* failure shapes, every one of which was caught by a human or a
reviewer noticing "this is the Nth time", never by the system:

| Pattern | Occurrences | How it was caught |
|---|---|---|
| Orchestrator instruction generalises a locally-correct rule to a context where the requirement inverts | 4 (decisions 13, 20, 24, 34) | Binding reviewer, each time independently |
| A shipped test asserts the defect as intended behaviour | 3 (task-03, task-04, task-05) | Binding reviewer, by mutation probing |
| New `scripts/forge/` executable missing from the spec §5 inventory | 2 (task-03, task-04) | Orchestrator, by accident |
| Recorded execution routing diverges from committed agent TOML | 2 (this run's reviews, palimpsest's 61 default-routed executions) | Orchestrator, when asked an unrelated question |
| Committed control relaxed instead of escalated / correctly escalated | 1 + 1 (FR-085 relaxation, then task-06 refusal) | Binding reviewer, then the instruction added after it |

Decision-38's commitment audit is the mechanical half of the answer and catches
none of these: a missing task entry is a *structural* property, whereas "this
adjudication has the same shape as three earlier ones" is a *semantic* one.

**Resolution:** a two-half learning loop matching forge's own guides/sensors
split, with a hard constraint on authority.

- **Mechanical half — `scripts/forge/journal-patterns.py`.** Deterministic
  extraction over one or many journals, no LLM: verification `result` sequences
  per task (iteration counts, BLOCK→PASS latency), decision outcome mix,
  execution routing vs the committed agent TOML (the decision-32 check,
  generalised across runs), finding counts by severity and by reviewer role, and
  frequency of exact-string diagnostics. Emits sorted-key JSON on the schema-v1
  pattern. This is what makes recurrence *countable* rather than remembered.
- **Semantic half — `/forge:learn`,** a skill running the `review-periodic`
  profile over (a) the mechanical output, (b) the run archives under
  `.forge/history/runs/` (D10 — the archive is what makes this possible across
  runs; without it each run's reasoning is lost with its journal), and (c) the
  current `gotchas` file. Its job is exactly the thing the mechanical half
  cannot do: cluster failures by *shape*, name the shape, and say what control
  would have caught it earlier.
- **Two output artefacts, both proposals, never applied automatically:**
  1. **Candidate eval fixtures** in FR-102's existing form — exact recorded
     prompt as Input, expected verdict, provenance (run id + execution id).
     Written to `.forge/evals/candidates/`, never to `tasks/`.
  2. **Candidate gotchas** appended to `.forge/history/gotchas.md` (committed,
     append-only): one line per observed failure shape, each traceable to the
     journal entries that produced it, in the style the harness-engineering
     literature calls a steering loop — every line earned by a real failure.
- **Authority constraint (non-negotiable).** The learning loop MUST NOT modify
  any control: not the constitution, not routing, not gates, not eval baselines,
  not `forge-project.md`. Fixtures land in `candidates/` and require the normal
  control-class path — independent review plus explicit operator approval — to
  become baselined. A system that rewrites its own controls from its own
  failure history is precisely the gate-gaming the control-integrity rule
  forbids; the loop's authority class is `advisory`.
- **Consumption.** The `gotchas` file joins the agent-prompt assembly (FR-037)
  the way `agent-project-context` already does, so a shape observed once becomes
  feed-forward context for every later agent. That is the actual learning: not
  the report, the injection.
- **Cadence.** Mechanical half runs inside `drift-check.sh` (D9) — it is a drift
  measurement. Semantic half runs at the archive step of a run close (D10) and
  on the drift cadence, so it sees both the just-finished run and the corpus.

**Rejected:** auto-appending fixtures to `tasks/` with fresh baselines (mints a
baseline from possibly-regressed current agents — the exact laundering D12's
migration rules forbid); an LLM writing directly into the constitution or
`forge-project.md` (control-class surfaces, and self-modification of gates is
gate gaming by construction); pattern detection from commit messages instead of
the journal (the myagentsgigs analysis showed message conventions dominate that
signal); and a purely mechanical loop with no semantic half (it would have
caught none of the five patterns above).

**Spec scope:** FR-200..FR-20x, a `gotchas` addition to DM-008's
`.forge/history/` layout, `.forge/evals/candidates/` in DM-007, and a redline to
FR-037 for prompt assembly. Depends on D10 (archive corpus) and consumes D9's
telemetry and the deferred disposition counters. Lands in the same revision as
D12/D13 (task-09) or the one after; implementation after task-10.

---

## Interactions and ordering

- D7's invariants slot into merge Gate 2 and commit Step 2; D6's assertion-quality
  sensor runs at commit Step 2, while scoped mutation runs after merge Gate 1 as
  non-gating Gate 3 evidence. There are no new gate numbers and no `validate`
  change. Ship first.
- D8 depends on nothing but touches the guard marker contract (DM-006 annotation),
  `risk-tiers`/`trigger-paths` shared committed sources, the commit/merge skills, and
  the guard — the most control-sensitive change; ship second with its per-surface
  decision event stream and extended `aggregate-telemetry.sh` CSV. D9's mechanical
  half applies that aggregation with its explicit window and embeds the counters
  in schema-v1 JSON from day one; its semantic half consumes only that JSON.
- D9 consumes D6 (full mutation), D7 (invariant sweep), and D8 (tier telemetry);
  ship third. D10 is independent and small; it can ship alongside any of them.
- Every decision here is control-class. Path: revise the spec (candidate FR ranges:
  FR-139 test-quality seeds/sensors, FR-145 invariants, FR-150 risk tiers and
  decision telemetry, FR-160 drift, FR-170 archive; DM-003 has exactly fourteen
  regions: the original nine in their shipped order followed by the five additions
  `mutation-testing`, `invariants`, `risk-tiers`, `drift-config`, `trigger-paths`;
  DM-006 gains the `tier: fast` and `policy: <sha>` annotations; and DM-008 defines
  the `.forge/history/` layout with its close sequence `validate --gates →
  run_closed → validate --gates → archive → report.md`), then adversarial review of
  the revision, then implement per the repo's own doctrine. The revision must include
  explicit REDLINES to existing FR-050, FR-052, FR-054 and DM-006 — the
  mandatory-review language gains the fast-tier exception — not just new FR ranges.
- The same exact fourteen-region order must replace the closed nine-region inventory
  in `system/template/forge-project.md`, `scripts/forge/install.sh`, and
  `tests/test_commit_and_region_template.py`; re-init tests refresh the delimited
  plugin-owned dependency block from the template while preserving all surrounding
  user-filled bytes. `system/seeds/validation-snippets/stacks.md`
  gains the per-stack assertion/mutation/property triple. `hooks/hooks.json` gains
  plugin SessionStart and Stop-union wiring for the new
  `scripts/forge/drift-staleness.sh`; the Codex layer keeps Stop only.
- D11 remains part of this revision's init surface: dcg allowlisting follows the
  fourteen-region mechanical install and preserves its idempotent absent/present
  behavior.
