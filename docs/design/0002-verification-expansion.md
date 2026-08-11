# forge-plugin — Verification Expansion: Test Quality, Invariants, Risk Tiers, Drift, Durable Intent, and dcg Integration

**Status:** Draft for review, 2026-08-11 (Igor + Claude). Records decisions D6–D11,
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
  iteration counts, block rate, halt/guard denials). Every emitting surface holds
  the shared `.forge/tmp/events.lock` for its single append, while the checker holds
  that same lock across the prune read and atomic replace, following the existing
  commit-lock bounded-wait, owner-only-release, fail-closed ownership convention.
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
  category. `.forge/tmp/` remains transient; `.forge/evals/` remains control.
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
