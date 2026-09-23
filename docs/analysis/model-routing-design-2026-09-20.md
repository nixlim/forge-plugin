# Per-developer model routing — design record (2026-09-20)

Status: **design discussion, no implementation**. Non-authoritative analysis note (tracked since `69bc28d`); nothing here is
spec authority. Method: two read-only multi-agent workflows (7 surface readers + completeness
critic; 3 designs x 3 adversarial critic lenses x 2 judges + synthesis), every claim
spot-verified against the tree at `78d9610` (branch `refactor/split-engine-class`).
Section 8 records the second review pass requested after the operator's comments.
**Section 10 (third pass, same day) supersedes sections 3, 7, 8.4 and 9 wherever they
differ**: the orchestrator leaves the local config, review-final becomes an engine-launched
headless CLI process, and the provider becomes per-developer for every launched role. File
and line references anywhere in this record are indicative only — the engine split is still
moving code; exact locations are re-derived when implementation starts (section 10.8).
**Section 11 (2026-09-22) is that re-derivation** against `657f6c1`, records the operator's
GH#13 precedence direction, and lists the items still open before an implementation plan.

## 1. Operator positions this record rests on

| Date | Position | Source |
|---|---|---|
| 2026-09-03 | **AGREED with the counterpart (GH#13 / bead `forge-plugin-eki`)**: route authority = a committed `routing` region in `forge-project.md` rendered by `/forge:init`; typed `execution-start` refuses off-table provider/model/effort/sandbox; break-glass via a journaled, execution-count-bounded operator decision; run-close refuses without it. Filed because a consumer orchestrator silently switched implementers from Codex to Claude subagents with no record. | `bd show forge-plugin-eki` |
| 2026-09-20 | **Ratified (terminal)**: *model identity* (which model, and its effort, performs a role) is routine per-developer configuration; *reviewer authority, permissions/sandbox, and gates* stay governed (committed, control-class). Motivation: several people share a repo but hold different Codex and Claude model access; one committed route cannot serve them, and per-person edits to committed routing would fight. | this session |
| 2026-09-20 | **Scope extension (terminal)**: switching must cover *all* models — not only the Codex implementer and first-pass reviewer, but the **orchestrator** (the Claude Code session: Anthropic or third-party models routed through Claude Code) and **review-final** (the Claude subagent: same). | this session |
| 2026-09-20 | **Terminology must be aligned** across journal, prose, TOML, agent names and evidence before any enum is enforced (section 5). | this session |
| 2026-09-20 | **Proposal to evaluate**: models live in `<common-root>/.forge/local/routes.toml`; before every run a hook or script verifies that the frontmatter/prose that points at a model matches `routes.toml` for that role (section 7). | this session |

The 2026-09-20 positions supersede eki *in part*. Because eki was a cross-repo `AGREED:`
position, the change needs an explicit operator nod and an `AGREED:` restatement on GH#13
and in-channel before any spec text lands (CLAUDE.md channel rules 3 and 8).

## 2. Where the route lives today (verified)

| # | Surface | Content | What reads it |
|---|---|---|---|
| 1 | `docs/specs/forge-plugin-spec.md` FR-030 / FR-111 | implementer `gpt-5.6-sol`/`ultra`/`workspace-write`; review-cheap `gpt-5.6-sol`/`high`/`read-only`; review-final `fable`/`high`. FR-030: *"Changing any model/effort/sandbox value is a control-class change."* | `tests/test_repo_conformance.py` regex-parses both lines |
| 2 | `system/codex/agents/{implementer,review-cheap}.toml` → installed `.codex/agents/*.toml` | same literals | init probe, journal-patterns, conformance, installer tests, fresh evals. **Not** the launch: every Forge launch passes `-c model=` explicitly (ADJ-010) |
| 3 | `agents/review-final.md` frontmatter | `model: fable`, `effort: high` | Claude Code's agent loader when the session spawns `review-final` by name |
| 4 | `skills/orchestrate/SKILL.md` role table + `references/{review,monitoring}.md` | prose literals the session substitutes into `codex exec` argv | the orchestrating session |
| 5 | engine `review_request` (`_engine.py:2562-2580`, moving to `_verbs_review_request.py` in c07) | hardcoded `model=gpt-5.6-sol`, `model_reasoning_effort=high`, `-s read-only` | commit-chain review-cheap launch |
| 6 | `fresh_evals.py:_route_and_prompt_controls` | route parsed from the **candidate git tree** blob `.codex/agents/review-cheap.toml`, byte-equal to the `system/` copy; launched with `--ignore-user-config --ignore-rules --strict-config`; bound into fixture-package digests (DM-012) | Gate 2 |
| 7 | orchestrator (Claude main session) | **no route anywhere** — "host session" in the role table; never pinned, probed or recorded | — |

Checks that would notice a deviation: `test_repo_conformance.check_current` (spec == TOML ==
frontmatter; committed invariant at commit and merge, dogfood only); `journal-patterns.py`
and `check_run` (recorded model/effort == committed at the execution's HEAD; informational /
non-fatal finding); fresh evals (route re-derived from the candidate tree; INVALID on any
difference); init step 5 (probes only `system/codex/agents/*.toml` models, forbids
substitution). **Nothing in the chain verifies the launched model against committed bytes**:
`review collect` binds only to the argv the engine itself built.

Facts that bound any design:

- **No Forge-authored record carries an observed model.** Codex `exec --json` streams carry
  no model field; the typed run-open records no Claude/Codex version; every model/effort record
  Forge writes is *launcher intent* (argv or a hand-transcribed journal field). The host does
  observe the Claude lanes (§8.1): the Agent tool result names the model review-final started
  on, and SessionStart / PostModelSwitch hooks can carry the session model.
- FR-005: Python ≥ 3.10 standard library only. No YAML parser in the tree. TOML is the house
  route format; `tomllib` is 3.11+, so a regex line grammar keeps the floor literally true.
- `/.forge/tmp/` and `/.forge/chains/` are ignored by the shipped gitignore block; `.forge` as
  a first path segment is refused from every run-bound candidate scope (`candidate.py:36`).
  Machine-local state is anchored at the git-common-dir parent by hooks, guard and CLI, so it
  is shared by linked worktrees. `install.sh` anchors on `show-toplevel` instead.
- `.git/info/exclude` is the FR-015 per-clone exclusion protocol already used for
  `/.codex-orchestrator/`.
- `hooks/hooks.json`: PreToolUse matches **Bash only** (`commit-guard.sh`); PostToolUse
  `Edit|Write` is the advisory `invariant-guard.sh`; SessionStart and Stop run
  `drift-staleness.sh`. Operator rule: a guard may err toward denial, never allowance; no Bash
  modelling; legibility is the product.
- `builders.py` (9431) and `journal.py` (8261) sit at their `.refactor-baseline.json` ceilings
  and are listed out of refactor scope; new logic must live in new modules.
- The committed pins were never a capability floor: `3814d67` (terra/medium → sol/high,
  "Both previously disagreed with what actually ran") and `3bbd2b1` (opus → fable) changed the
  authority to match one machine's practice.
- Pre-existing consumer bug, out of scope: fresh evals require `rules/review-constitution.md`
  from the candidate tree; `install.sh` never installs `rules/`.

## 3. First-pass recommended design (Codex roles only)

Synthesis of the "reconciled with eki" design with grafts; judges 118.75 / 110.75 / 107.5.

| | |
|---|---|
| File | `<common-root>/.forge/local/routes.toml`; one per clone; a copy at a linked-worktree root is refused as misplaced |
| Exclusion | `route_config.py init` appends `/.forge/local/` to `git rev-parse --git-path info/exclude` (FR-015 precedent). No `install.sh`, gitignore-block, region or manifest change |
| Format | TOML-shaped, fixed regex line grammar (`journal-patterns.py:28-31` precedent); `schema = "forge-routes/1"`; optional `[implementer]` / `[review-cheap]` tables with `model` / `effort`; any other key malformed. **Seed ships every table commented out** so an untouched role follows the committed default at the launch HEAD and plugin upgrades reach every machine |
| Ownership | no symlink, `O_NOFOLLOW`, `S_ISREG`, `st_uid == geteuid`, ≤ 16 KiB, must be untracked and ignored |
| Governed (committed) | provider per role, journal role, sandbox, reviewer authority, gates, and the *shipped defaults*; FR-030/032/052/111 grammar unchanged; mirrored by a `ROLE_TABLE` constant in new `scripts/forge/route_config.py` |
| Precedence | local table → committed default at launch HEAD (`git show HEAD:.codex/agents/<role>.toml`, else `system/codex/agents/…` — journal-patterns' order) → plugin file only for uninstalled repos. **No env-var layer** |
| Mechanism | typed `run-open` freezes a digested snapshot into `run_started.route` (FR-019 known-optional); run-bound `review request` and every `execution-start` compare and **refuse divergence**; unbound chains read at launch. Chain `STATE_KEYS` untouched |
| Evidence | `execution` gains `route_source` (`local` / `committed-default` / `plugin-default`), `route_sha256`, optional checked `sandbox`; chain `review.request` gains `route`; all launcher intent, stated as such in FR text |
| Conformance | journal-patterns status gains `local` (values differ *and* honoured provenance); `matched` when equal regardless of source; provenance honoured only for typed-opened / activated runs; `check_run` finding line gains `; developer-local selection (route_sha256 …)` |
| Gate 2 | **unchanged, candidate-bound** (every critic: honouring the local selection there is CRITICAL — the reviewer-routing trigger exists to evaluate the route a candidate changes). A developer lacking the default model uses the operator-terminal `commit skip fresh-reviewer-evals` |
| review-final | **v1: frontmatter-only**, builder pins `(claude, review)` records to it (ends `fable` vs `claude-fable-5` drift). *Superseded by the scope extension — see section 8* |
| Init / install | `install.sh` untouched; `route_config.py init \| show \| probe`; init step 5 runs `init` then `probe` (one bounded `codex exec` per resolved Codex model/effort pair) before the first tracked mutation — implements the spec's promised live smoke |
| GH#13 incident | still caught: off-table provider refused at `execution-start`; `task-finish --status complete` with no execution record and `run-close --judgment passed` with any such task are refused (today `task_finish` requires no execution — eki's "dead-ends at close, loudly" is not yet true) |
| Size | ~500 new production lines in new modules; net-non-positive edits in `builders.py` / `journal.py`; ~700 test lines in new modules; ~16 spec sentences + new FR-244 |
| Sequencing | (0) land `refactor/split-engine-class` through c07; (1) decisions → `AGREED:` restatement → spec chain; (2) leaf chain; (3) journal chain; (4) engine chain (STRICT fresh evals); (5) prose chain; (6) release notes |

Honest limits: Codex remains required for implementer, first-pass review and fresh evals;
self-downgrade is bounded and legible, not prevented (same uid, advisory Edit/Write hook);
the Codex `model_provider` endpoint stays unrecorded for chain and orchestrator launches; a
strict role enum refuses spellings the live corpus already contains (section 5).

## 4. Gaps the operator identified in the first pass

1. **Orchestrator model** is not covered. The main session's model is chosen by Claude Code
   (`--model`, `/model`, settings `model`, environment), may be an Anthropic model or a
   third-party model routed through Claude Code, and is nowhere pinned, probed or recorded.
2. **review-final model** must be switchable per developer (Anthropic or third-party through
   Claude Code), not frozen to `model: fable` frontmatter.
3. **Terminology** must be aligned before any enum is enforced (section 5).
4. A **pre-run verification** of model-bearing frontmatter/prose against `routes.toml` was
   proposed (section 7).

## 5. Terminology and enum alignment — must be settled first

The first-pass design enforces a strict `role` enum at the typed `execution-start` builder.
Measured against the 153 live execution records in `.codex-orchestrator/runs/*/journal.jsonl`
this repo's own corpus would be refused 66 times out of 153:

| Field | Spellings in use | Where |
|---|---|---|
| journal `role` | `implementation` 56, `review` 31, **`reviewer` 33, `implementer` 24, `implement` 8, `plan` 1** | live journals; spec FR-030 and the orchestrate role table say `implementation` / `review`; `journal-patterns.committed_route` and `check_run` recognise only those two (anything else → `unavailable` / fatal "unknown Codex execution role") |
| journal `provider` | `codex` 129, `claude` 24 | journals; `fresh_evals.Route.provider` is the literal **`codex-cli`**; test fixtures use **`openai`** |
| Claude model id | **`fable` 18, `claude-fable-5` 6** for the identical frontmatter | hand-transcribed by the orchestrator (bead `forge-plugin-68r`) |
| agent / config names | `implementer`, `review-cheap` (Codex TOML `name`), `review-final` (Claude agent `name`) | `system/codex/agents/*.toml`, `agents/review-final.md` |
| role-table labels | "Claude main session", "Fresh Codex implementer", "Fresh Codex first-pass reviewer", "Claude subagent `review-final`" | `skills/orchestrate/SKILL.md:21-24`; journal role for review-final is `n/a`, for the main session `n/a` |
| orchestrator | **no identifier at all** | — |

Consequences today: 66/153 rows are invisible to drift (`unavailable`), three closed dogfood
runs are unarchivable (fatal role error), and the one real deviation in the corpus — seven
implementers launched at effort `high` under an `ultra` route in `run-20260910-release-0611`
— is hidden behind the `implementer` spelling.

Any route design keyed on `(provider, role)` inherits this. Before an enum is enforced the
project needs **one canonical vocabulary** used identically by `routes.toml` table names,
journal `role`/`provider` values, agent/TOML names, the orchestrate role table, spec FR-030,
drift rows and archive text — plus a stated migration for the existing corpus (accept legacy
spellings on records that predate the change; refuse only new records). Candidate canonical
set (decision for the operator; the second review pass evaluates it):

| Role id | Provider id | Today's names it replaces |
|---|---|---|
| `orchestrator` | `claude-code` | "Claude main session", "host session" |
| `implementer` | `codex` | journal `implementation` / `implementer` / `implement`, TOML `implementer`, "Fresh Codex implementer" |
| `review-cheap` | `codex` | journal `review` / `reviewer` (codex), TOML `review-cheap`, "first-pass reviewer" |
| `review-final` | `claude-code` | journal `review` / `reviewer` (claude), agent `review-final`, "binding final reviewer" |
| `plan` | — | one live record; either admitted as a role or refused with a migration note |

Model identifiers need the same treatment: one canonical spelling per provider namespace
(Claude Code aliases such as `opus`/`sonnet`/`fable` vs full ids such as `claude-opus-5`;
Codex ids such as `gpt-5.6-sol`), recorded verbatim as passed at launch.

## 6. What the pasted external design got right and wrong

Right: local file as primary interface; create-once / preserve on upgrade; frozen snapshot for
worktrees; record selections in evidence; reclassify model identity; provider change as a
separate extension. Wrong for this repo: YAML (FR-005); explicit seeded defaults (freezes
upgrades); `install.sh` gitignore-block integration (byte-pinned template, no path for
developers #2..N); "run applicable evaluations against those selections" (the Gate 2
CRITICAL); env overrides (unrecorded, reach gate children); unaware of eki.

## 7. Proposal under evaluation: pre-run verification of model-bearing frontmatter

Operator proposal: `routes.toml` is the single source of models; before every run a hook or
script verifies that the frontmatter (and prose) that points at a model matches the value
for that role in `routes.toml`.

Surfaces that "point at a model" today: `agents/review-final.md` frontmatter (`model`,
`effort`) — a **plugin** file under `${CLAUDE_PLUGIN_ROOT}`, machine-local but overwritten
by plugin upgrades and pinned by FR-111 and the dogfood conformance invariant; the
orchestrate role table and reference prose; `system/codex/agents/*.toml` / installed
`.codex/agents/*.toml`; the engine literal; Claude Code's own session-model configuration
(settings `model`, `--model`, environment). Skills (`SKILL.md`) carry no model frontmatter.

Questions the second pass must answer: which of these surfaces a verifier compares against
which; whether a mismatch is reported, refused, or *repaired* (generating frontmatter from
`routes.toml` is a write into a control-class plugin file); which hook event runs it
(SessionStart vs run-open vs commit start) and what that hook can observe about the live
session model; how it relates to the run snapshot already in the first-pass design; and how it
stays inside the operator rule that guards err toward denial and never model Bash.

## 8. Second review pass (orchestrator + review-final + verification hook)

### 8.1 Host facts the extended design depends on (Claude Code docs, re-verified)

| Fact | Consequence |
|---|---|
| Subagent model resolution: (1) per-invocation Agent-tool `model` parameter → (2) frontmatter `model` (`sonnet`/`opus`/`haiku`/`fable`, a full id, or `inherit`) → (3) `CLAUDE_CODE_SUBAGENT_MODEL` (`_FORCE=1` beats frontmatter, not the parameter) → (4) session model. `effort` **is** a frontmatter field for subagents. | The session can select review-final's model per spawn from `routes.toml` without touching the plugin file. |
| **Agent-team teammates** take the model named in the spawn prompt, then the definition's model, fix it at spawn, and **ignore frontmatter `effort`**. 103 of 126 dogfood review-final launches were teammates; no spec, skill or agent definition mentions teams. | The skills must prescribe one launch path, or handle both; `[review-final].effort` is unenforceable on the teammate path. |
| The Agent tool's PostToolUse `tool_response` carries `resolvedModel` / `modelsUsed` (subagents) or `model` + `teammate_id` (teammates). | **Host-observed model evidence for review-final exists** and a PostToolUse hook matched on `Agent` can capture it. Across 126 launches the unchanged `model: fable` frontmatter resolved to `claude-fable-5`, then `claude-fable-5-1[1m]`, with an 11-launch reversion on one harness version. Section 2's "no observed-model evidence" is true for Forge-authored records only. |
| Main-session precedence: `/model` (persists to `~/.claude/settings.json`) > `claude --model` > `ANTHROPIC_MODEL` > settings `model` (managed > `--settings` > `.claude/settings.local.json` > `.claude/settings.json` > `~/.claude/settings.json`) > `ANTHROPIC_DEFAULT_MODEL` > org/account default; resumed sessions restore the transcript's model; gateway ids pass through unvalidated. | Forge cannot select the orchestrator model; it can declare, observe (below), record, and at most confirm a switch. |
| Hooks: SessionStart input has an **optional** `model` (absent after `/clear` or recovery); `PreModelSwitch` (≥ 2.1.251) can deny/ask an interactive or SDK switch (not automatic fallback or resume); `PostModelSwitch` observes all; every hook gets `effort.level`; `CLAUDE_EFFORT` is exported into Bash cells; SessionStart exit 2 is not honoured; **stderr from an exit-0 hook goes to the debug log only** (so `drift-staleness.sh`'s nudge is silent today); `additionalContext`/stdout on SessionStart reaches the session; `CLAUDE_ENV_FILE` persists env only for later Bash cells. | The orchestrator route can be observed at start and on switches, never selected; the only Forge-ownable enforcement is `PreModelSwitch`. |
| Subagent scope: managed > `--agents` > `.claude/agents/` > `~/.claude/agents/` > plugin. A **user-scope** `~/.claude/agents/review-final.md` shadows the plugin reviewer and nothing detects it (FR-183 checks the project path only). Plugin files live in `~/.claude/plugins/cache/forge/forge/<version>/` and are replaced on update; `${CLAUDE_PLUGIN_DATA}` is the persistent per-user plugin data dir. Whether plugin `userConfig` substitution reaches YAML frontmatter is undocumented. | "Verify frontmatter matches `routes.toml`" has no per-developer frontmatter to compare on the Claude side unless a shadow agent is generated. |
| Adding any hook to `hooks/hooks.json` requires FR-001/FR-093 rewrites ("SessionStart invokes only `drift-staleness.sh`") and `tests/test_plugin_load.py` byte-pin changes; it does **not** invalidate FR-223 (its `hook_config_digest` covers only the probe's own files). | Hooks are control-class but do not force an evidence re-mint. |
| Dogfood measurement: chain review cells run `scripts/forge/cli.py` from the checkout with `CLAUDE_PLUGIN_ROOT` unset, so the engine embeds the checkout's `agents/review-final.md` while Claude Code loads the cache copy (identical today). | Any package-header route line must also record which plugin root the engine read. |
| `docs/design/0001-founding-decisions.md:56-60`: review-final gives "cross-model separation of duties by construction". The spec spine defines separation by agent/role only; same-model orchestrator + review-final is already the live state on some machines. | Routing review-final to a non-Anthropic model through a gateway removes the founding cross-model property; the design must say whether that is reported or refused. |

### 8.2 Vocabulary findings that refine section 5

- `review-cheap` / `review-final` are **already** the canonical reviewer ids in the chain (`BINDING_REVIEW_ROLES`), the Gate-3 observation grammar, drift `by_reviewer_role` and archive regexes; `implementer` matches the Codex TOML `name` and `config.toml` key. Adopting them as journal `role` ids merges two namespaces at zero cost on the chain side.
- Renaming provider `claude` → `claude-code` would be a gratuitous break (24 live rows, committed archives, `journal-patterns.py:203`, `check_run`, the contract's `event_source: "claude"`). Keep `codex` / `claude`; the real inconsistency is the fresh-eval literal `codex-cli` (`fresh_evals.py:2166`).
- `journal.py:8185` and `:8404` use `role == "review"` as the **only** non-mutating marker, so the 33 `reviewer` rows are misclassified as mutating executions for gate vetoes and landing checks — a correctness bug independent of routing.
- `event_source` has three spellings (`exec` 84, `codex` 44, `claude` 24) plus one path value; the 44 `codex` rows bypass the events-required rule. `mode` mixes launch mode and sandbox (`headless` 38, `detached` 47, `subagent` 24, `read-only` 20, `workspace-write` 24).
- The DM-001 activation boundary cannot separate legacy from canonical rows: all three legacy-spelling runs are typed-opened. Migration = append-time enum for **new** writes (FR-019 L761 "adds no enum" amended) + one shared read-side legacy normalisation map used by `journal-patterns`, `check_run`, `journal.py` mutation classification and `learn-proposals`.
- Model ids: record verbatim what was passed (Codex argv) or declared (Claude); host-reported ids sometimes carry a `[1m]` suffix (`claude-fable-5-1[1m]`) and aliases such as `fable` re-point across harness releases; conformance must state a suffix rule and never compare by alias semantics.
- The orchestrator is spelled "Claude main session", "host session", "Claude Code planner · orchestrator", `claude-main` and `claude-code-tui` across spec, skills and FR-223 fixtures; the FR-223 fixture ids are byte-pinned and must coexist with any new `orchestrator` role id.

### 8.3 Pre-existing defects surfaced by the readers (to file as beads; none fixed here)

1. `hooks/hooks.json:31`, `scripts/forge/commit-guard.sh:4471`, `engine/_command_lock.py:28` read `CLAUDE_SESSION_ID`; the documented variable is `CLAUDE_CODE_SESSION_ID`. 940/940 telemetry rows are `nosession`; the `foreign-chain-index-owner` guard branch never fires in a real session; FR-093's session-id MUST is unmet; tests pass only because they export the undocumented name.
2. `drift-staleness.sh` warns on stderr with exit 0; the host routes that to the debug log, so FR-165's SessionStart nudge never reaches the session or the user.
3. FR-015's `info/exclude` append is prose-only and non-idempotent: this clone's `.git/info/exclude` holds `/.codex-orchestrator/` 25 times.
4. `journal.py` classifies every `reviewer`-spelled execution as mutating (8.2).
5. Consumer repos: fresh evals require `rules/review-constitution.md` from the candidate tree; `install.sh` never installs `rules/` (section 2).
6. Agent-team teammates are the dominant review-final launch path and are undocumented; frontmatter `effort: high` is not applied to them.
7. `UPSTREAM:90` still says review-final records `opus`/`high` — stale committed prose.
8. `system/codex/agents/review-cheap.toml:21` and `system/codex/hooks.json:13` reference `${CLAUDE_PLUGIN_ROOT}` inside Codex processes, which never set it.

### 8.4 Decision

Second panel: 3 designs (A declare-and-record · B observe-and-bind · C generated shadow
frontmatter, the operator's proposal made as safe as possible) × 3 critic lenses (all nine
SOUND_WITH_FIXES; C carried three CRITICALs) × 2 judges (both chose **A as base with B's
receipt-bound `review attach` grafted**; totals 56.5/55.5/52 and 57/54.5/39.5) → synthesis.

**Recommended: "declare, record, bind at attach".** The first-pass Codex design stands
unchanged. `routes.toml` gains `[orchestrator]`, `[review-final]` and `[plan]`. Nothing new
refuses the orchestrator. Review-final becomes verdict-bound in the only way the host allows:
the declared route is written into the review package header (already inside
`package_digest`, which the verdict must cite) and a PostToolUse hook on `Agent` writes a
host-observed launch receipt that `review attach` reads automatically; **when the hook is live
for the session**, attach refuses a review-final launch whose requested or observed model is
divergent from the declared route (commit chain escape: operator-terminal
`commit skip review-final-receipt`; merge chain: re-spawn as prescribed). When no session
receipt exists (plugin disabled, older harness, pre-hook session) attach proceeds and records
`unobserved`. This refuses only the session's own deviation from a declaration it was shown.

#### 8.4.1 Canonical vocabulary (adopt verbatim; prerequisite chain)

| Field | New writes (append-time enum) | Read-side legacy map (never re-validated) |
|---|---|---|
| `role` | `implementer` (codex, `workspace-write`, **mutating**) · `review-cheap` (codex, `read-only`) · `review-final` (claude, orchestrator tree) · `plan` (codex, `read-only`, admitted — decision 2) · `monitoring` · **`orchestrator` is a routes table and snapshot key only, never an execution role** | `implementation`/`implementer`/`implement` → `implementer`; `review`/`reviewer` + codex → `review-cheap`; `review`/`reviewer` + claude → `review-final`; `(claude, implementation)` → off-table |
| `provider` | `codex` · `claude` — **the launching runtime, never the model vendor**; a third-party model through Claude Code is `provider: claude` | fresh-eval literal `codex-cli` documented as the Gate-2-only spelling and mapped → `codex` (no rename: it is inside recorded fixture digests) |
| `event_source` | `exec` · `claude` | `codex` → `exec` (44 rows currently bypass the events-required rule); `agent-tool` → `claude` |
| `mode` | `headless` · `detached` · `subagent` · `teammate` (launch path only) | `read-only`/`workspace-write` in `mode` → legacy sandbox; `orchestrator-inline` → refused on write |
| `sandbox` | new known-optional checked field; required `read-only` for `plan`/`review-cheap` | — |
| model ids | **recorded verbatim** (Codex argv token; Claude declared string; host string incl. any `[1m]`); grammar `^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}(\[1m\])?$`; `inherit` refused in v1 | comparison strips one `[1m]`, matches Anthropic family aliases by family, adds a non-refusing `matched-provider` for Bedrock/Vertex prefix/suffix forms |
| non-mutating marker | `route_vocab.is_non_mutating` on the **raw** spelling (`review|reviewer|review-cheap|review-final|plan|monitoring`) replaces `journal.py:8185/:8404` `role == "review"` | fixes the 33 misclassified rows |

Where it lives: new `scripts/forge/route_vocab.py` (sibling seam like `commitment_paths.py`,
importable from both packages). Spec: Terminology L73/L74, FR-019 L748/L755/L761 ("adds no
enum" amended; **the activating candidate must carry the orchestrate role table, the contract
example and every writer surface — FR-019 L748 "same candidate"**), FR-021 L812, FR-030 L826,
FR-033 L829, scenarios L2109-2129, FR-103/DM-012 `codex-cli` sentence. Ship as its own patch
release so consumers align spellings before routes land (decision 16).

Consumer impact measured on a local peer corpus (152 executions): `implementation` ×68,
`(claude, implementation)` ×29, `event_source: agent-tool` ×27, `mode: orchestrator-inline` ×1
— the GH#13 shape as routine practice. These are refused on new writes after the vocabulary
release (decision 4) and must be named in the `AGREED:` restatement and release notes.

#### 8.4.2 Per-role treatment

| Role | Selection | Observation (host) | Recording | Enforcement |
|---|---|---|---|---|
| **orchestrator** | none by Forge; `[orchestrator]` is a **declaration**; `route_config.py show` prints the host command that realises it (`claude --model …`, settings snippet) | SessionStart `model` (optional), `PostModelSwitch` `to_model`/`source` (incl. auto-fallback, resume), hook `effort.level`, else `$CLAUDE_EFFORT` (`env-reported`) — via a per-session sidecar | `run_started.route.roles.orchestrator` + known-optional `run_started.orchestrator` = {declared, self_report, host_observed}; run-open takes `--orchestrator-model/--orchestrator-effort` (self-report) | **never refused**; divergence → SessionStart/PostModelSwitch context line, `check_run` finding, drift `local` |
| **review-final** | session spawns `forge:review-final` as a **subagent** (no `name`; teams off-switch printed when the sidecar shows a teammate launch), passing the declared model **both** as the Agent-tool `model` parameter and as a `Model: <declared>` prompt line (teammates honour the prompt) | PostToolUse `Agent`: `tool_input.model`, `resolvedModel`/`modelsUsed` (subagent) or `model`+`teammate_id` (teammate) → one receipt file per launch under `<common-root>/.forge/tmp/route-hooks/<session>/` | package header route line (in `package_digest`); receipt bound to the request (`subagent_type == forge:review-final`, package digest among the prompt's 64-hex tokens, `at ≥ requested_at`, once per iteration); Gate-3 projection cites the copied receipt | `review attach` refuses `requested ≠ declared`, `observed divergent`, or `launch-unobserved` **only when the hook is live**; otherwise proceeds and records `unobserved` |
| **implementer / review-cheap / plan** | first-pass design, unchanged (local table → committed default at launch HEAD → plugin) | none exists (no model field in any Codex stream) | `execution.route_source/route_sha256/sandbox`; chain `review.request.route` | first pass: off-table provider/role and off-snapshot model refuse at `execution-start`; run-bound `review request` refuses only when the **developer file's** sha changed since run-open (committed-default drift never refuses) |

`agents/review-final.md` keeps `model: fable` as the committed default. **Effort (decision 5,
recommended a):** FR-111 drops `effort: high`, the reviewer inherits the session effort the
developer controls (`/effort`, `CLAUDE_CODE_EFFORT_LEVEL`), `[review-final].effort` declares
the minimum, the receipt's `effort.level` is the executed effort on both launch paths, and
attach refuses below-declared. This is the only premise-consistent per-developer effort path
(teammates ignore frontmatter effort; the Agent-tool parameter carries no effort).

**Model-id limit for review-final (verified from this session's Agent tool schema):** the
`model` parameter is an alias enum (`sonnet | opus | haiku | fable`). Full ids and gateway ids
cannot be passed per spawn in this harness version; a third-party model for review-final is
reached by declaring the alias and mapping it host-side (`ANTHROPIC_DEFAULT_<FAMILY>_MODEL`,
Bedrock/Vertex env). Phase-0 probe: whether dropping `model:` from FR-111 and using
`CLAUDE_CODE_SUBAGENT_MODEL` (accepts a full id, but applies to every subagent) is a better v2
selector for full ids.

**Separation of duties** stays agent/role-based (spec spine). The founding "cross-model
separation by construction" becomes a **recorded** property: `check_run` emits
`same-model binding review` for both author pairs (orchestrator/review-final in chains;
implementer/review-final in runs) and a `vendor-coincidence-suspected` heuristic on recorded
ids; never refused (decision 12).

#### 8.4.3 Ruling on the pre-run verification proposal

- **Accepted:** `<common-root>/.forge/local/routes.toml` is the single per-developer
  declaration for all roles, owner-controlled, info/exclude'd, frozen per run, with a
  comparison point before every run: SessionStart `additionalContext` (the first working
  "tell the session something at start" channel in this plugin), typed run-open, `commit start`,
  `review request`, plus developer-initiated `route_config.py check | show [--run-id]`.
- **Rejected as stated** ("frontmatter/prose pointing at a model must match `routes.toml`"):
  the only model-bearing frontmatter is one plugin-cache file for every developer, replaced on
  every plugin update and pinned by FR-111 + two tests; skills carry no model frontmatter; the
  orchestrator has none; the engine reads the checkout copy while Claude Code loads the cache
  copy; and **equal strings are not equal models** — unchanged `model: fable` executed as three
  different ids across harness versions. Equality is reachable only through a control-class write
  the next update discards, and the one honest attempt to manufacture per-developer frontmatter
  (design C's generated shadow) loses `${CLAUDE_PLUGIN_ROOT}` substitution in the loaded body,
  mislabels caller values as host-observed, and is invisible to the merge chain.
- **Re-cut as:** declared (`routes.toml` / committed default) **vs** snapshot
  (`run_started.route`) **vs** host-observed (SessionStart / PostModelSwitch / Agent PostToolUse)
  **vs** self-reported. A malformed, foreign-owned, symlinked, oversized, tracked, un-ignored or
  misplaced file refuses (a bad file is not a mismatch). Orchestrator divergence is reported,
  never refused. Review-final divergence refuses at attach when the hook is live.

#### 8.4.4 Hooks added (one script, three registrations; control-class; no FR-223 re-mint)

| Event | Matcher | Does | Blocks |
|---|---|---|---|
| SessionStart | — | after `drift-staleness.sh`: `route-hook.sh` → resolves routes, appends `{model?, source, effort}` to the session sidecar, injects the resolved route table + host model as `additionalContext` | no |
| PostModelSwitch | — | appends the switch; one stdout line naming the new model vs `[orchestrator]` | no |
| PostToolUse | `Agent` | writes the launch receipt (subagent and teammate shapes); context line on review-final divergence | no |

Inert outside a git repo or without `.forge-manifest`; parses only named stdin keys; fixed
literal diagnostics; exit 0 always. Cost: FR-001/FR-093 rewrites, `tests/test_plugin_load.py`
byte-pin rewrite, `hooks/**` chain. `PreModelSwitch` is **not** added (decision 7): it would
refuse routine configuration against the operator's own hand, hard-refuse on Remote
Control/`-p`/SDK, and fail open on a traceback. Dogfood precondition: this repo runs with
`forge@forge: false` and the marketplace cache is 0.6.12 (158 commits behind), so no hook fires
here until the session runs `claude --plugin-dir <checkout>` (decision 15).

#### 8.4.5 Evidence classes (stated on every record and in FR text)

`declared` (routes table / committed default; `source` ∈ local · committed-default ·
plugin-default · none) · `self-reported` (session-transcribed) · `host-observed` (emitted by
Claude Code to a plugin hook; same-uid coordination evidence, never authentication; attests the
model a launch **started** on) · `env-reported` (`$CLAUDE_EFFORT`) · `launch-argv` (engine-built
Codex argv + digests). Codex executions have no host-observed class.

#### 8.4.6 Size and sequencing

≈ 1,200 new production lines across ~17 files, all in new modules (`route_vocab.py`,
`route_config.py`, `route-hook.sh`, `route_binding.py`, `engine/_route_receipt.py`,
`app/_merge_review_receipt.py`, seed) plus net-non-positive edits in `builders.py`,
`journal.py`, `learn-proposals.py`, `_merge_engine.py`, `test_repo_conformance.py`; no
`install.sh`, `fresh_evals.py`, gitignore-block, region or chain-state-key change. Tests in new
modules only. Phases: (0) land the engine split through c08 + scratch-project host probes
(SessionStart `model` presence; Agent-tool parameter value space; teammate `tool_response`
delivery to a PostToolUse hook; `${user_config}` in frontmatter) → (1) decisions, `AGREED:`
restatement, **vocabulary chain** (own patch release) → (2) routes spec chain (Revision 15,
FR-244/FR-245) → (3) leaf chain (`route_config.py` + seed) → (4) journal chain → (5) hooks chain
→ (6) engine chain (STRICT fresh evals) → (7) prose chain → (8) release notes.

#### 8.4.7 Decisions for the operator (recommendation first)

1. Re-ratify the eki/GH#13 supersession as re-cut and authorise the `AGREED:` restatement (§8.4.9).
2. `plan` and `monitoring` as non-mutating roles — **admit**.
3. `codex-cli` — **document + normalise**, no rename.
4. Legacy spellings on new writes — **refuse with exact diagnostics** (b: one-release grace with `route_source: legacy-spelling`).
5. Review-final effort — **(a) FR-111 drops `effort:`; session effort governs; declared minimum enforced at attach** (b: keep `high`, unswitchable).
6. `inherit` for `[review-final].model` — **refuse in v1**.
7. `PreModelSwitch` — **none in v1**.
8. `review attach` on `launch-unobserved` under a live hook — **refuse** (commit skip exists; merge: re-spawn).
9. SubagentStart receipt of the loaded `agent_type` — **defer**.
10. Drift routing schema — **keep 8-key element**, statuses `matched | local | mismatched | unavailable`.
11. Learning provenance — **keep v1**.
12. Same-model / same-vendor author pairs — **record as findings**, amend Intent L6 + founding footnote.
13. Net-non-positive edits in the five ceiling files — **sanction** (else split first).
14. Approval binding — **print the reviewer line** in approve outcomes/prompt (b: require `--reviewer-model` on approve when `source == local`).
15. Dogfood launch mode — **`claude --plugin-dir <checkout>`** with the plugin re-enabled.
16. Release placement — **after 8mf, before b0b; vocabulary chain as its own patch release; re-point eki**.
17. Drift-staleness nudge rides the SessionStart hook's stdout — **yes, same chain**.
18. Gate 2 — **candidate-bound** (carried).
19. Chain `--ignore-user-config --strict-config` and consumer `rules/` gap — **defer as beads** (carried).
20. `(claude, implementer)` and `orchestrator-inline` — **stay off-table/refused**; a Claude implementer is a separate spec revision.
21. Phase-0 host probes — **delegate, record results here before the spec chain**; a negative Agent-tool result limits v1 review-final switching to the four aliases.

#### 8.4.8 Residual risks

Host-observed evidence is same-uid writable (sidecars, receipts, self-reports): a deleted
sidecar reads as `hooks-not-live` → `unobserved`, never `matched`, so a downgrade cannot
masquerade as verified, but a forged receipt is undetectable. Decision 5a couples the binding
reviewer's effort to the session effort (a developer orchestrating below the declared minimum
meets an attach refusal until `/effort` up). The vocabulary release refuses the peer's routine
spellings on new writes at their first `execution-start` after upgrade. The vocabulary
candidate is the heaviest single chain and cannot be split (FR-019 L748). The Codex lane still
has no host-observed class and no `--ignore-user-config` on the chain launch. Drift v1 stays
blind to host-observed divergence until a schema bump. User-scope / `--agents` / managed shadows
of `review-final` remain undetected by FR-183 (the receipt reveals the executed model, not the
definition that ran).

#### 8.4.9 `AGREED:` restatement (post on GH#13 and in-channel only after the terminal nod)

> AGREED: (supersedes the 2026-09-03 routing-region position in part) 1. No committed
> `routing` region in forge-project.md. 2. Model identity — model and effort per role — is
> per-developer configuration in `<common-root>/.forge/local/routes.toml` (info/exclude'd, never
> committed) for the orchestrator, implementer, review-cheap, review-final and plan roles; a
> typed run freezes it in `run_started.route`. 3. Provider, journal role, sandbox, reviewer
> authority, gates and the committed default routes stay committed and control-class. 4. From
> forge <release>, new journal `execution` records use exactly: `role` implementer |
> review-cheap | review-final | plan | monitoring; `provider` codex | claude; `event_source`
> exec | claude; `mode` headless | detached | subagent | teammate; known-optional `sandbox`
> (required `read-only` for plan/review-cheap). The typed builder refuses legacy spellings on new
> writes with a diagnostic naming the canonical id; historical records are read through a
> normalisation map and never rewritten. 5. `(claude, implementer)` is off the committed role
> table and refused at `execution-start`. 6. Break-glass is dropped; provider substitution is a
> spec-level extension. 7. A complete task with a file scope needs an `implementer` execution, a
> bound `chain-landing` decision or an `orchestrator-owned` decision. 8. Drift "absence MINOR" is
> dropped. 9. Host-observed model evidence (SessionStart / PostModelSwitch / Agent PostToolUse)
> is recorded; `review attach` refuses a review-final launch that a live route hook shows ran off
> the declared route; the orchestrator's model is recorded, never refused. 10. Gate 2 stays
> candidate-bound.

Also re-point beads `forge-plugin-eki` and `forge-plugin-68r`, and mirror the durable lines
into beads memory.

## 9. First-pass operator decisions (superseded by §8.4.7; kept for reference)

Items 1, 2, 6, 7, 11, 12 carried over unchanged; item 3 (review-final) and item 9
(vocabulary) were re-cut by the second pass.

1. Re-ratify the eki supersession and authorise the `AGREED:` restatement.
2. Gate 2: candidate-bound (rec) vs honour the local selection.
3. review-final selection mechanism — reopened by the scope extension.
4. Extra self-downgrade mitigation: none (rec) vs Edit/Write deny hook vs `route accept` verb.
5. Sanction net-non-positive edits to `builders.py` / `journal.py` (rec) vs split first.
6. `--ignore-user-config --strict-config` on the chain review-cheap launch: defer, bead (rec).
7. Archive legibility: Learning-provenance v1 untouched (rec) vs v2 with route fields.
8. `--sandbox` on `execution-start`: optional-but-checked (rec) vs required.
9. Role enum and canonical vocabulary (section 5) — now a prerequisite, not an option.
10. Release placement: after 8mf, before b0b; re-point eki (rec).
11. Consumer `rules/review-constitution.md` install gap: in-release vs own bead.
12. Exclusion mechanism: info/exclude via `route_config.py init` (rec) vs gitignore-block line.

## 10. Third review pass (2026-09-20, terminal): orchestrator out, headless review-final, provider interchange

Requested by the operator: re-verify the record independently; test the position that the
orchestrator is an operator session choice and does not belong in the local config; check
whether a Claude Code session can launch Claude Code headless through the CLI, so that
review-final is freed from agent frontmatter, Agent-tool and teammate semantics and the
providers (`codex` CLI / `claude` CLI) become interchangeable. Method: three read-only
verifiers (routing surfaces, review lanes, corpus re-measurement) plus live host probes run
from inside the orchestrating session (Claude Code 2.1.278, codex-cli 0.155.0, Linux,
subscription OAuth). No repository change was made.

### 10.1 Verification of sections 2, 5 and 8

Confirmed exactly: every section 5 corpus count (153 executions and all role / provider /
model / `event_source` / `mode` spellings; 66 of 153 invisible to drift; seven implementers at
`high` under a committed `ultra` route in `run-20260910-release-0611`); 126 review-final
launches with 103 realised teammates (105 requested a teammate, two failed on tmux pane
exhaustion); FR-030 / FR-111 text; Codex TOML literals and byte-identical installed copies;
review-final frontmatter; the fresh-eval candidate-tree route and its `codex-cli` literal; the
`CLAUDE_SESSION_ID` defect at all three sites (the host exports `CLAUDE_CODE_SESSION_ID`);
`/.codex-orchestrator/` ×25 in `info/exclude`; the forge plugin disabled in this repo with
cache 0.6.12; the Agent-tool `model` parameter being the alias enum
`sonnet | opus | haiku | fable`.

Corrections (locations deliberately given without line numbers):

- The `role == "review"` non-mutating marker lives in `scripts/codex_orchestrator/journal.py`,
  not under `scripts/forge/`.
- `check_run` lives in `tests/test_repo_conformance.py`, not in `journal-patterns.py`.
- The `.forge` first-segment refusal is `candidate.valid_scope_path`; the cited line is only the
  `_TRANSIENT_SCOPE_ROOTS` constant, which also lists `.codex-orchestrator` and `.worktrees`.
- Stop runs two hooks (`aggregate-telemetry.sh`, then `drift-staleness.sh`).
- ADJ-010 is in `docs/specs/forge-plugin-spec-review-adjudicated.md`, not the spec, and its
  recommendation text still carries a stale `terra`/`medium` route.
- "Every Forge launch passes `-c model=`" is true for Codex launches only; nothing passes a
  model when review-final is spawned.
- The engine review-cheap argv is still inside `engine/_engine.py`; the `_verbs_review_*`
  modules are planned, not present.
- Missed by earlier passes: the orchestrate role table gives review-final `project-configured`
  while FR-111 pins `fable` / `high`, and no test compares them; a committed fixture journal
  stores a model id in `run_started.claude_version`, which nothing validates.
- `UPSTREAM` still claims review-final records `opus` / `high`; no `opus` value exists in any
  journal or launch (already defect 8.3.7).
- Not re-verified: the section 8.1 hook-event facts (`PreModelSwitch`, `PostModelSwitch`,
  SessionStart `model`). They are moot under 10.2 and 10.3.

### 10.2 Orchestrator: out of the local config (operator position, confirmed)

Nothing in Forge selects, pins, probes or validates the main-session model: the role table
says `host session`; the init model probe reads only the Codex TOMLs; `committed_route` has no
orchestrator row; separation of duties is agent-distinctness in the spec, rules and skills; the
founding "cross-model separation by construction" is Codex implementer versus Claude reviewer.
Section 8.4.2 already conceded that Forge cannot select the orchestrator and never refuses it,
so `[orchestrator]` would be a key with no effect plus a standing false-divergence signal on
every `/model` switch. The section 1 scope extension is re-cut as **"every model Forge
launches"**.

Removed from the design: the `[orchestrator]` table; the SessionStart and PostModelSwitch hook
registrations; the per-session sidecar; `run_started.orchestrator`;
`--orchestrator-model` / `--orchestrator-effort`; the `orchestrator` vocabulary id;
decisions 7 and 17.

**Evidence only (operator decision):** at typed run-open and `commit start` the CLI reads the
last `message.model` from the session transcript located through `$CLAUDE_CODE_SESSION_ID`
(probed: the variable is exported into Bash cells and the transcript carries the model on every
assistant turn). Recorded as `observed` / `unobserved`; never compared against a declaration,
never refused. The transcript layout is an undocumented host detail, so this is a best-effort
evidence class and its absence is not a finding.

### 10.3 Host probes: headless Claude Code launched from a Claude Code session

| Probe | Result |
|---|---|
| nested `claude -p` from a session Bash cell, subscription OAuth | works, exit 0 |
| launch from a detached wrapper (`start_new_session`, no TTY, prompt on a stdin pipe, stdout to an events file, environment reduced to `HOME PATH LANG USER`) | works; the verdict arrives in the final `result` event |
| `--model <full id>` and `--effort <level>` | accepted; `init.model`, every `assistant.message.model` and the result's `modelUsage` keys report the executed id |
| `--model` versus `ANTHROPIC_MODEL` | the environment value is honoured per process; the flag wins |
| `ANTHROPIC_BASE_URL` set for the child only | honoured by the child (dead endpoint: no result, retried until the external timeout); the parent session is unaffected — a gateway model can be given to one role. **A wrapper timeout is mandatory** |
| `--agent forge:review-final --plugin-dir <checkout> --model haiku` (no safe mode) | committed agent body loaded as the system prompt and run on haiku: the CLI `--model` beats frontmatter `model: fable` |
| the same with `--safe-mode` | refused, agent not found: safe mode disables plugins |
| `--safe-mode --system-prompt-file <role body>` | works; `${CLAUDE_PLUGIN_ROOT}` stays literal, so the launcher must expand or drop those three references (the package already inlines the constitution bytes) |
| `--safe-mode`, and separately `--setting-sources ""` | both suppress a project `SessionStart` hook and the project `CLAUDE.md`; without them both apply |
| `--tools "Read,Grep,Glob"` | only those tools exist in the child |
| `--tools …,Bash --allowedTools "<pattern>" --permission-prompts none` | the allow-listed command ran; `touch` was denied, listed in the result's `permission_denials`, no file created |
| implementer shape: `--permission-mode acceptEdits --tools "Read,Write,Edit,Bash"` | file written in the working directory, zero denials |
| three concurrent headless children | all succeeded |
| **safe-mode implementer, realistic task** (scratch git repo with a failing test; `--safe-mode --append-system-prompt-file <implementer prompt>`, brief on stdin, `--permission-mode acceptEdits --allowedTools "Bash" --permission-prompts none`) | unimpeded: read, edited, ran the tests through Bash, committed; 7 turns, zero denials on the task. A `Write` outside the working directory was **denied** by the host and listed in `permission_denials` (file tools are confined to the working directory; Bash is not) |
| safe-mode default tool set | broad (`Task`, `WebFetch`, `WebSearch`, `Cron*`, `Workflow`, `SendMessage`, `RemoteTrigger`, `PushNotification`, `EnterWorktree` …) — a committed profile must pin `--tools` explicitly |
| child with no credentials (`HOME` pointed at an empty directory) | fails in ~70 ms at zero cost: exit 1, result `is_error: true`, `terminal_reason: "api_error"`, `result: "Not logged in · Please run /login"`, empty `modelUsage`. **`subtype` still reads `"success"`** — a launcher must key on the exit code and `is_error`, never on `subtype` |
| `--bare` | requires `ANTHROPIC_API_KEY` (never reads OAuth): unusable for subscription developers; use `--safe-mode` |
| Claude Code OS sandbox (`sandbox.enabled`; bubblewrap + socat on Linux) | `socat` absent on this machine: the host **fails open** ("Commands will run WITHOUT sandboxing") and a write outside the working directory succeeded |

Operator rulings on the unprobed items (terminal, same day):

- **Login state is the operator's responsibility.** A developer opens and logs in each CLI
  before a run. Forge does not manage or refresh credentials; a parent/child refresh race is
  out of scope. The launcher's only duty is legibility: on the not-logged-in shape above (and
  the Codex equivalent) it refuses with a fixed diagnostic that names the provider CLI and the
  manual re-login step, then the verb is simply re-run.
- **Linux is assumed for now.** macOS is checked later on a local machine; the per-provider
  argv templates may then need an OS check.
- **"Gateway model"** means a model reached by pointing the `claude` CLI at something other
  than Anthropic's first-party API — Bedrock / Vertex / Foundry, or an LLM proxy set through
  `ANTHROPIC_BASE_URL` — where the model id is that endpoint's own. Probed: the child honours
  per-process endpoint variables. Not probed (none is configured here): a complete run against
  such an endpoint, and what model id the stream then reports. **Operator ruling: gateway
  endpoints are best-effort** — Forge passes the declared model id and the developer's
  endpoint environment through unchanged, records what the stream reports, and makes no
  promise beyond that until a user reports a problem. No probe, no gateway-specific code, and
  no comparison rule for gateway id forms in v1 (this also drops the `matched-provider`
  comparison status sketched in 8.4.1).
- Still to establish at implementation start: the minimum Claude Code version carrying
  `--safe-mode`, `--permission-prompts` and `--effort`.

### 10.4 Review-final becomes an engine-launched headless process (operator decision: headless only)

`docs/design/0003-forge-cli-plumbing.md` states that a CLI subprocess cannot spawn
review-final; 10.3 falsifies that premise. Review-final moves onto the lane review-cheap
already uses — `review request` builds the package and launches a detached wrapper;
`review collect` binds the argv digest, prompt digest and completion record — and
**`review attach` is retired for it** in the commit chain, the merge chain and init (FR-083).
Today the orchestrating session hand-carries the binding verdict into a file and the engine
validates only grammar and digests (FR-216: "best-effort, validated-but-trusted"); that tier
ends.

Dissolved by this move: the Agent-tool alias enum limit; teammate effort loss and the
tmux pane failures; user-scope / `--agents` / managed shadows of the agent (FR-183's threat);
plugin-cache versus checkout role-template divergence; the PostToolUse `Agent` receipt hook
and its sidecar; the `hooks-not-live` / `unobserved` attach states; decisions 5, 6, 8, 9, 14,
15 and 21; the whole "frontmatter must match `routes.toml`" question of section 7. **With 10.2
no hook is added at all**: section 8.4.4 is deleted, with its FR-001 / FR-093 rewrites and the
`tests/test_plugin_load.py` byte-pin change.

Kept: the role template `agents/review-final.md` stays committed and inside `package_digest`
(its `model:` / `effort:` frontmatter stops being load-bearing; FR-111 is re-cut accordingly);
the verdict grammar; `BINDING_REVIEW_ROLES`; the Gate 3 projection.

**Reviewer tools (operator decision): parity with today** — Read, Grep, Glob, LS and
unrestricted Bash, instruction-bounded by the existing FR-111 paragraph. New relative to today:
every command the reviewer ran and every permission denial is in the captured event stream.

**Observed model:** the child's own stream (`init.model`, per-message `model`, `modelUsage`) is
written into the engine-owned events file and digested by the completion record. It is
same-uid evidence, not authentication, but it is the same trust class as the rest of the lane
and needs no hook. The Codex lane still has no observed-model source.

### 10.5 Provider interchange (operator decision: every launched role — implementer, review-cheap, review-final, and, per 11.4 item 6, plan)

A role's route is `{provider: codex | claude, model, effort}`, all three keys per-developer in
`routes.toml`, for each of the four launched roles (the plan role was added by 11.4 item 6). This reverses section 8.4.9 items 3, 5 and 6 (provider committed;
`(claude, implementer)` refused; provider substitution a spec-level extension) and therefore
cuts deeper into the AGREED eki / GH#13 position than the second pass did. The GH#13 incident
was a *silent, unrecorded* provider switch; a declared, snapshotted, journaled provider is a
different thing — but the restatement must be re-cut and re-ratified in the terminal before
anything is posted (channel rules 3 and 8).

Committed and control-class: the role table; **one argv template and one permission / sandbox
profile per (provider, role)**; role templates and prompts; reviewer authority; gates; shipped
defaults; Gate 2.

| | `codex` CLI | `claude` CLI |
|---|---|---|
| prompt | stdin (`-`) | stdin (`-p`) |
| verdict / last message | `--output-last-message <path>` | final `result` event on stdout (`--output-format stream-json`) |
| events | `--json` on stdout | `stream-json --verbose` on stdout |
| model / effort | `-c model=` / `-c model_reasoning_effort=` | `--model` / `--effort` |
| isolation from user config | `--ignore-user-config --ignore-rules --strict-config` (fresh evals only today) | `--safe-mode --strict-mcp-config` |
| read-only reviewer | OS sandbox `-s read-only` | tool list + permission rules; Bash instruction-bounded |
| implementer confinement | OS sandbox `workspace-write` | **instruction-bounded (operator decision)** |
| observed model | none | in the stream |

Because the Claude OS sandbox fails open when its dependencies are missing, the operator ruled
a Claude implementer instruction-bounded rather than sandbox-required. This must be stated,
not implied: the threat-model sentence "Codex agents are sandbox-confined to their worktrees"
and the FR-030 sandbox column gain a per-provider value, and the journal `sandbox` field
records which one ran (`workspace-write` | `read-only` | `instruction-bounded`), so a run's
confinement strength stays legible. Sandbox is never a `routes.toml` key.

**Claude implementer profile (operator direction: implementation must proceed unimpeded, and
be safe where possible).** Safe mode plus launcher-supplied context, mirroring
`system/codex/prompts/`: `--safe-mode --strict-mcp-config`, a committed implementer prompt through
`--append-system-prompt-file` (Claude Code's own coding system prompt is kept), the task brief on
stdin, an explicit coding `--tools` list, `--permission-mode acceptEdits`, Bash allowed without
patterns, `--permission-prompts none`. The child therefore never loads the orchestrator's
`CLAUDE.md` (push mandate, beads and channel rules), plugins, hooks or MCP servers. Probed
working end to end (10.3). What the host gives for free: file tools confined to the working
directory, every denial reported in the result. What stays instruction-bounded: Bash. Open
refinement, unprobed here because `socat` is absent: enabling the Claude OS sandbox when Forge
itself finds its dependencies present and recording `workspace-write` instead of
`instruction-bounded` — including whether `git commit` in a linked worktree (which writes into
the common `.git` outside the working directory) survives it. Whatever project rules an
implementer needs (file-size budget, lint gate) must be carried by the committed implementer
prompt or the brief, since `CLAUDE.md` is not read.

Implementer launches are skill-prose-driven today (the session substitutes literals into a
`nohup codex exec` block). Interchange requires a typed verb that emits the argv for a role from
the resolved route, so the session never hand-substitutes a provider's flags.

Gate 2 is unchanged: candidate-bound, Codex route, `SUPPORTED_REVIEW_AGENTS = {review-cheap}`.
A developer without Codex access still cannot run fresh evals — interchange does not fix that,
and the operator-terminal `commit skip fresh-reviewer-evals` remains the only path.

### 10.6 Resulting shape

1. **Vocabulary chain first**, as section 8.4.1 minus the `orchestrator` id, with `sandbox`
   gaining `instruction-bounded` and `(claude, implementer)` admitted. It stands on its own:
   the 33 `reviewer` rows classed as mutating are a live correctness bug.
2. **`<common-root>/.forge/local/routes.toml`**: `[implementer]`, `[review-cheap]`,
   `[review-final]`, `[plan]`; keys `provider`, `model`, `effort`; seed fully commented out;
   ownership / exclusion / grammar rules of section 3 unchanged; precedence local → committed
   default at launch HEAD → plugin default; no environment layer.
3. **One generalised review lane** in the engine for both reviewers and both providers:
   per-provider argv template and IO shape, a wrapper timeout, a sanitised child environment,
   route and observed model in the request / completion records, route line in the package
   header. The merge lane needs a new module (`_merge_engine.py` is at its baseline ceiling).
4. **Typed implementer launch** from the resolved route; `execution-start` compares against the
   run snapshot as in section 3.
5. **Orchestrator**: transcript-read evidence only (10.2).
6. No hooks, no generated frontmatter, no receipts, no sidecars.

Spec surface: FR-030, FR-052, FR-111, FR-132, FR-183, FR-216, FR-060 / FR-083 wording, the
threat model, the Gate 3 journal law, plus the vocabulary items of 8.4.1. Skills: commit,
worktree-merge, orchestrate (+ references), init. The section 8.4.6 size estimate is void; a new
one is owed at implementation start.

### 10.7 Status of the section 8.4.7 decisions

Carried unchanged: 2, 3, 4, 10, 11, 13, 16, 18, 19. Dropped as moot: 5, 6, 7, 8, 9, 14, 15,
17, 21. Re-cut: 1 (the supersession is now larger — 10.5); 12 (same-model findings are computed
from recorded routes for implementer / reviewer pairs, and from transcript evidence where it
exists for the orchestrator; still never refused); 20 (`(claude, implementer)` is **admitted**;
`orchestrator-inline` stays refused). The section 8.4.9 restatement text is void and must be
redrafted for terminal review before any post.

Taken in this pass (terminal): orchestrator = evidence only through the transcript read;
review-final = headless only; interchange = all three roles; reviewer Bash = parity with today;
Claude implementer = instruction-bounded.

### 10.8 Before implementation

This work is the first item after the engine refactors land. At that point, and not before:
re-derive every file and line reference in this record against the then-current tree (the
engine split is relocating the review verbs; nothing here should be trusted as a location);
establish the Claude Code version floor and an init probe for it; check macOS locally and add an
OS check to the argv templates if needed; probe the opportunistic OS sandbox on a machine that
has its dependencies. **The `AGREED:` restatement is postponed until the design is settled in
full** (operator, terminal); it is then redrafted for terminal review, beads `forge-plugin-eki`
and `forge-plugin-68r` are re-pointed, and the vocabulary spec chain opens. Nothing is posted to
GH#13 or the channel before that.

## 11. Re-derivation against `657f6c1` (2026-09-22, post engine and MergeEngine splits)

Requested by the operator once the refactor campaign's engine work landed (Engine class split `d885f97`, MergeEngine decompose `657f6c1`). Method: three read-only readers (route surfaces,
review-lane layout, corpus/tracker/host) plus two direct probes from the orchestrating session;
no repository change other than this section. Operator directions taken at the same time:
**this record takes precedence over the GH#13 / `forge-plugin-eki` position wherever they
conflict; GH#13 is re-analysed after the change lands, if anything of it remains.**

### 11.1 What moved, what did not

Only two route-relevant things changed between `78d9610` and `657f6c1`:

| Surface | Then | Now |
|---|---|---|
| review-cheap argv | `engine/_engine.py:2575` | `scripts/forge/forge_cli/engine/_verbs_review_request.py` — `review_request` L194, argv list L360-379 (`--output-last-message` L364, `-s read-only` L368-369, `model=gpt-5.6-sol` L373, `model_reasoning_effort=high` L375); launcher argv L381-390, `Popen(start_new_session=True)` L392-401; review-final branch L436-458 launches nothing and records an `invocation` string. The module is at **458 of 500 code lines** — the new launch code cannot live there. |
| `.refactor-baseline.json` | `app/_merge_engine.py` 10302, `engine/_engine.py` 3574 listed | both delisted (`_merge_engine.py` 224, `_engine.py` 324). Added: `app/_engine_lock.py` 578, `_engine_recover.py` 584, `_engine_recover_conflict.py` 830. Still exactly at ceiling: `builders.py` 9431, `journal.py` 8261, `fresh_evals.py` 3000, `candidate.py` 1195, `test_repo_conformance.py` 991. |

Section 10.6 item 3's premise ("`_merge_engine.py` is at its baseline ceiling") is therefore
void; the new-module conclusion stands for a different reason (11.3).

Everything else in section 2 is byte-unchanged: spec FR-030 (L826) and FR-111 (L928) literals;
`system/codex/agents/*.toml` and their byte-identical `.codex/` copies; `agents/review-final.md`
frontmatter (`model: fable` L4, `effort: high` L5); the orchestrate role table (SKILL.md L21-24;
review-final still `project-configured`) and the `references/{review,monitoring}.md` literals;
`fresh_evals._route_and_prompt_controls` L2065 with `provider="codex-cli"` L2166 and the
`--ignore-user-config --ignore-rules --strict-config` argv L1039-1041; `journal-patterns.py`
`committed_route` L185 (three rows) and the TOML/YAML regex grammar L28-31;
`test_repo_conformance.check_current` L302 / `check_run` L354; `journal.py` `role == "review"`
L8185 / L8404; `builders.execution_start` L9142 with `validate()` L9177-9191 accepting any
non-empty string (no role/provider enum anywhere, including `journal.py:1976-1998` and the
`codex_orch_tools.py:204` parser); `candidate._TRANSIENT_SCOPE_ROOTS` L36 / `valid_scope_path`
L967; `hooks/hooks.json` registrations.

### 11.2 Corpus, tracker, host (re-measured)

- **Corpus unchanged**: 19 runs, newest `run-20260910-release-0611`; 153 executions with the
  exact section 5 spellings and counts; `sandbox`, `route`, `claude_version` absent on every
  execution; `effort` ultra 81 / high 72. One `event_source` value is a literal events path
  (`run-20260906-95e4-phase3`), the row the earlier 152-sum omitted. `run_started.route` 0/19;
  `run_started.claude_version` 7/19, four of them carrying the model id `claude-fable-5` (10.1);
  the 12 runs from 2026-08-29 carry `writer_contract` instead — the natural home for a route
  snapshot under FR-019.
- **Tracker**: `forge-plugin-eki` OPEN P2 with the 2026-09-03 design in its notes; `68r` OPEN
  P3; `8mf` (0.7.0 epic) OPEN P1; `b0b` OPEN P2 "after 0.7.0"; `5gw` (DM-010 `CLAUDE_PID`)
  OPEN P1. No other open bead concerns model/provider routing. **No beads memory holds the
  2026-09-03 `AGREED:` line** (channel rule 8 mirroring was never done for eki).
- **GH#13**: OPEN, last activity 2026-09-02T23:47Z; a single `AGREED` comment (committed
  `routing` region; execution-start off-table refusal; count-bounded break-glass; close /
  task-finish refusal). Nothing since. No other open issue (#7-#30) concerns model routing.
- **Host**: Claude Code **2.1.280** (was 2.1.278), codex-cli **0.155.1**, Python 3.13.5;
  `bwrap` present, `socat` still absent (OS sandbox still fails open, 10.3). All flags the
  10.5 templates need are present: `--safe-mode`, `--permission-prompts`, `--effort`,
  `--setting-sources`, `--strict-mcp-config`, `--agent`, `--plugin-dir`, `--permission-mode`,
  `--append-system-prompt`, `--system-prompt`. `--system-prompt-file` and
  `--append-system-prompt-file` are **hidden from `--help` but accepted** (probed: both fail
  with "… file not found", not "unknown option") — the launcher must not derive flag support
  from `--help` text; the version floor (10.8) is still to be established.
- **Defects of 8.3 all still present**, with one correction: `CLAUDE_SESSION_ID` is read at
  **four** sites, not three — `hooks/hooks.json:31`, `commit-guard.sh:4471`,
  `chain_core/_merge_chain.py:324`, `engine/_command_lock.py:28` (only `fr223_eval.py:1294`
  uses the documented `CLAUDE_CODE_SESSION_ID`). `info/exclude` still holds
  `/.codex-orchestrator/` ×25; `UPSTREAM:90` still says `opus`/`high`;
  `docs/design/0003-forge-cli-plumbing.md` L271 and L804-805 still state the falsified
  "a CLI subprocess cannot spawn review-final" premise. Section 2 also omits the Stop hook's
  `aggregate-telemetry.sh` (the `hooks.json:31` site).

### 11.3 Layout facts the implementation plan must respect

- **Review lanes today.** Commit lane: `_dispatch.py:97-104` → `Engine` verbs bound at
  `engine/_engine.py:292-298`; `_review_package` (`_verbs_review_request.py:75`) picks the
  reviewer by tier at L89 (`standard` → review-cheap, else review-final); wrapper source is the
  inline `REVIEW_LAUNCHER_CODE` at `engine/_state.py:119` (nothing written to disk), it
  recomputes the argv and prompt digests (~L131-135, ~L177); completion record
  `forge-review-process/1` (`_state.py` ~L229-255: `argv_digest, completed_at, error,
  prompt_digest, returncode, reviewer_pid, schema, started_at, verdict_digest, verdict_size,
  wrapper_pid`); `review_collect` (`_verbs_review_collect.py:139`) requires
  `reviewer == "review-cheap"` (L145); `review_attach` (L317) requires `review-final` (L323).
  Merge lane: `app/_engine_review_request.py` — `review_request` L112 is review-final only
  (L166), emits an invocation string, launches nothing; **`review_collect` L227 always refuses
  (L233)**; `app/_engine_review_verdict.review_attach` L16, `reviewer_role="review-final"` L124,
  PASS writes `delta.authorization` L140-151; bound at `app/_merge_engine.py:147-151`.
  `BINDING_REVIEW_ROLES` at `codex_orchestrator/journal.py:124`, checked at `journal.py:1318`
  and `builders.py:6268`. `SUPPORTED_REVIEW_AGENTS = {"review-cheap"}` at `fresh_evals.py:44`.
- **Where the generalised lane goes.** A new `engine/` leaf beside `_review_transport.py`
  (import-linter contract 3: the leaf layer `_archive … _parser | _review_transport` sits above
  `_core` > `_state`, below every `_verbs_*`), taking over the launch block at
  `_verbs_review_request.py:333-413`. Contract 1 (`app > engine > chain_core > fresh_evals >
  candidate | runtime | policy | envelope`) lets `app/_engine_review_request.py` call it, so the
  merge lane's headless review-final launch and a real merge-lane `review_collect` reuse the same
  code — that is why the merge side needs a new module (`_engine_review_request.py` is 231 lines
  and may take the call, but the collect logic is new).
- **Where `routes.toml` parsing and the vocabulary go.** `commitment_paths.py` is a top-level
  `scripts/forge/` module outside both packages, imported by `journal.py:30`, `builders.py:23`,
  `batch.py:18` and lazily by `chain_core/_core.py:46/66`; no contract governs it. Contract 5
  forbids `codex_orchestrator → forge_cli` (with three named ignores), so stdlib-only
  `scripts/forge/route_vocab.py` and `route_config.py` follow the `commitment_paths` pattern
  exactly, as section 8.4.1 assumed.
- **Ceiling files.** `builders.py` and `journal.py` are at their ceilings and carry
  per-file ruff ignores (`C901 PLR09xx PLR1702 …`); CLAUDE.md now forbids adding to that list.
  Decision 13 (net-non-positive edits) stands; the `execution_start` route comparison and the
  `run_started.route` freeze are the only edits those files take, and each must be a call into a
  new module. `_verbs_review_request.py` has 42 lines of headroom, so its change is likewise a
  call-out, not new logic.
- **Snapshot points.** Commit chain: `_verbs_lifecycle.start` L41, state from
  `_command_lock._new_state` L18, `store.create(state, "chain_started")` L136. Merge chain:
  `_engine_start_chain._initial_merge_state` L100 / `start_chain` L307 / `store.create` L358.
  Typed run-open: `builders.run_open` L8816, `run_started` dict L8906-8923 (repeated
  L8954-8964), schema check `journal.py:1880`. Chain state keys: `chain_core/_state.py:43`
  (`STATE_KEYS`) and `:70` (`MERGE_STATE_KEYS`), mirrored in `builders.py:305/329`,
  `fr223_eval.py:130` and `commit-guard.sh:406` — a route entry under `review.request` (8.4.2)
  stays inside an existing key and needs no key change; a new top-level key would touch all five
  mirrors and FR-223.
- **Plugin root.** `chain_core/_commit_chain.plugin_root` L1873 (`$CLAUDE_PLUGIN_ROOT`, else
  `runtime.PLUGIN_ROOT` L55 = the checkout); role template read at
  `_verbs_review_request.py:102-108` (commit) and `app/_engine_review_request.py:33` (merge).
- **Tests.** Review-lane coverage lives in `test_cli_chain`, `test_cli_merge_lifecycle`,
  `test_revision9_coordination`, `test_cli_merge_integration`, `test_cli_merge_adapters`,
  `test_fresh_reviewer_cli`, `test_cli_merge_store`, `test_cli_chain_finalize` — all
  grandfathered ceilings — and `test_revision10_review_transport` (12 tests, the only one with
  room). New tests go in new modules (8.4.6 stands).

### 11.4 Consequences for the design

1. **Section 10.6 stands in full.** No re-derived fact contradicts it. Two premises are
   corrected: the merge lane's new module is justified by the absent `review_collect` and the
   shared launch leaf, not by a `_merge_engine.py` ceiling; and the hidden-flag finding adds a
   launcher rule (feature-detect by version floor, never by `--help`).
2. **GH#13 / eki precedence (operator, 2026-09-22).** Where this record and the 2026-09-03
   `AGREED` position conflict — no committed `routing` region, provider per developer, no
   break-glass, enforcement at `execution-start` against the run snapshot plus the task-finish
   / run-close rule of 8.4.9 item 7 — **this record governs**. The GH#13 incident (a silent,
   unrecorded provider switch) is still prevented: a declared, snapshotted, journaled provider
   is refused when it diverges from the run snapshot, and a complete task with a file scope
   needs an `implementer` execution. What remains of GH#13 after the change (the AGENTS.md /
   CLAUDE.md contradiction detector it deferred; the drift-MINOR-on-absent-region idea) is
   re-analysed then, not now. `eki` and `68r` are re-pointed when the `AGREED:` restatement is
   redrafted (10.8); the beads-memory mirror of the 2026-09-03 line is owed regardless.
3. **Sequencing tension to settle before the plan.** Decision 16 ("after 8mf, before b0b") is
   listed as carried in 10.7, but 10.8 makes this work "the first item after the engine
   refactors land" — and `8mf` (0.7.0) is still open. One of the two must give; the
   recommendation is 10.8 (routing first, as its own patch release for the vocabulary chain,
   then 0.7.0), because the vocabulary release is the consumer-facing prerequisite and 8mf's
   design is itself marked provisional pending post-refactor re-verification.
4. **Confinement under provider interchange — needs an explicit operator re-confirmation.**
   Raised by the commit-chain reviewer on this record (iteration 2, [CON-06/SEC-02]): with
   `provider` per developer, the *effective* confinement of the implementer role changes with
   the developer's choice — OS `workspace-write` sandbox under `codex`, instruction-bounded Bash
   under `claude` (10.5) — so section 1's "sandbox and permissions stay governed" is true of the
   committed *profiles* but not of the confinement a given run actually gets. The operator ruled
   the Claude implementer instruction-bounded (10.5) knowing the OS sandbox fails open without
   `socat`. The record now states the consequence plainly: **choosing `provider = "claude"` for
   `[implementer]` is a developer-local weakening of confinement relative to the committed
   default**, made legible by the journal `sandbox` field and the archive. Options for the
   operator to confirm at plan start: (a) accept as ruled, with the `sandbox` field and a
   `check_run` finding `implementer ran instruction-bounded` as the legibility floor
   (recommended — it is the ruling already taken); (b) keep `provider` governed for
   `[implementer]` only, per-developer for the reviewers; (c) require the Claude OS sandbox
   (`bwrap` + `socat`) when `provider = "claude"` and refuse the launch when its dependencies
   are absent. Sections 1 and 10.5 are read with this item.
5. **Detached-lane fail-closed controls are plan-level requirements, not open design.** Raised
   as [INC-07/SEC-09/OPS-02]: 10.3/10.6 name only "a wrapper timeout". Measured on `engine/_state.py` `REVIEW_LAUNCHER_CODE` (L119-260) at `69bc28d`: the existing
   wrapper **has** argv- and prompt-digest recomputation, owner-controlled `O_NOFOLLOW` descriptors
   for prompt / events / verdict, a 65,536-byte verdict cap, and a tmp-then-`os.replace`
   completion record; it **lacks** a timeout, process-group termination, any cap on the
   `events.jsonl` output, and any validation of the event stream (the child's stdout/stderr go
   straight to the file). The generalised lane keeps the former and **must add** the latter,
   stated in the plan as executable tests: `start_new_session=True` process group with TERM-then-KILL on timeout; a fixed
   fail-closed timeout per (provider, role) profile; a combined-output byte cap on the events
   file with over-cap = failure; a completion record written tmp-then-`os.replace` whose absence
   after the wrapper exits is a failure; exit-code-and-`is_error` keyed success (never
   `subtype`, 10.3); malformed, truncated or non-JSON stream lines = failure with the line
   number in the diagnostic; the not-logged-in shape refused with the fixed diagnostic (10.3);
   survivor states (wrapper alive / child dead and the reverse) reported by `review collect`
   exactly as today's `_verbs_review_collect` does for the Codex lane. None of these is new
   policy; they are the FR-149 / DM-012 discipline applied to a second argv template.
6. **`[plan]` route — full interchange (operator decision, 2026-09-22).** Raised as
   [AMB-04/INC-11]: 8.4.1 admits `plan` and 10.6 lists `[plan]` in `routes.toml`, but 10.5 supplied
   argv templates only for implementer and the two reviewers, and the tree holds no plan prompt
   (`system/codex/prompts/` has `implementer.md` and `review-cheap.md` only; the one live plan
   execution is `codex-plan-01` in `run-20260910-release-0611`, codex / `gpt-5.6-sol` / `high`,
   detached). The operator chose **option (c), full interchange**: `plan` is a routable role like
   the other three, `provider` `codex` | `claude`, read-only on both providers (the operator
   prefers Claude models for planning; other developers may prefer Codex). The two plan profiles,
   stated here so this record stands alone:
   - `(codex, plan)`: the review-cheap argv shape of 10.5 with the plan prompt — `codex exec --json
     --output-last-message <plan.md> -s read-only -c approval_policy=never -c model=<m>
     -c model_reasoning_effort=<e> -C <worktree> -`, prompt = `system/codex/prompts/plan.md` +
     brief on stdin; OS sandbox `read-only`; recorded `sandbox: read-only`.
   - `(claude, plan)`: `claude -p --safe-mode --strict-mcp-config --output-format stream-json
     --verbose --model <m> --effort <e> --system-prompt-file <plugin>/system/claude/prompts/plan.md
     --tools "Read,Grep,Glob,LS" --permission-prompts none`, brief on stdin, cwd = worktree; no
     Bash and no write tools, so the host's file-tool confinement is the whole confinement;
     recorded `sandbox: read-only`; the plan text is the final `result` event.
   Both profiles are committed control (one row each in the profile table). **Launch and collection
   path — the same typed lane as the implementer (10.5, last paragraph):** the orchestrating session
   never hand-substitutes argv; it calls the engine's typed launch verb (`launch --role plan
   --run-id … --task …`), which resolves the route at the launch HEAD, emits the profile's argv,
   writes `prompt.md` and the brief, appends the journal `execution` (provider, canonical role
   `plan`, model, effort, `sandbox: read-only`, `route_source`, `route_sha256`), and starts the
   detached wrapper of 10.4 (process group, fixed timeout, output caps, `child.pid` sidecar); the
   wrapper owns the child, its `events.jsonl` and the plan text (Codex: `--output-last-message`;
   Claude: the final `result` event), and writes the completion record; `launch collect` reads
   that record, writes the plan text to `handoff.md`, and appends the terminal `execution_result`
   (`complete` on exit 0 with a nonempty plan, otherwise `failed` with the wrapper's error), the
   Claude lane adding the stream-observed model. `execution-start` refuses any other provider for
   `plan` and any `sandbox` other than `read-only`. Consequences: v1 ships **eight** committed (provider, role)
   profiles; `system/codex/prompts/plan.md` and `system/codex/agents/plan.toml` are auto-installed
   by `install_codex_layer` (which mirrors every `system/codex/**` file), so the `.codex` inventory
   pin at `tests/test_installer.py:340-352` gains the two paths, as do the exhaustive-inventory and
   plan-role contract tests (only those; the exact set is re-derived by `grep -rn` at that chain's
   start, not asserted here); the Claude plan body lives beside the Claude
   implementer body under `system/claude/prompts/`; the orchestrate role table gains a `plan`
   row; `committed_route` and `check_run` gain the `(codex|claude, plan)` rows. `monitoring`
   remains a vocabulary id only — it names the session's own monitoring pass and is never
   routable. The implementation plan that sequences this work is a separate working document,
   not part of this record.
7. **Ready for the implementation plan.** Items 3, 4 and 6 were decided on 2026-09-22 (11.5); the
   plan is a separate working document (not in this record). Its inputs are fixed: the shape in 10.6, the vocabulary in 8.4.1 (minus `orchestrator`), the per-provider
   templates in 10.5 with the controls of item 5, the `[plan]` interchange of item 6, the layout
   constraints in 11.3, and the version-floor probe as the first task.

### 11.5 Operator decisions (terminal, 2026-09-22 evening)

| Item | Decision | Consequence |
|---|---|---|
| 11.4.3 sequencing | **Routing first.** The routing work precedes `8mf` (0.7.0) and `b0b`; the order of every other open bead is re-adjusted afterwards, operator-led. Decision 16 of 8.4.7 is superseded. | vocabulary chain = next patch release; routes = the next minor; version placement proposed in the plan, confirmed by the operator at release |
| 11.4.4 confinement | **As ruled** in 10.5: the Claude implementer is instruction-bounded; `provider` stays per-developer for every launched role. | legibility floor = journal `sandbox` field + `check_run` finding `implementer ran instruction-bounded`; the threat-model sentence and FR-030 sandbox column gain per-provider values |
| 11.4.6 `[plan]` | **Full interchange** (option c). | eight committed (provider, role) profiles; plan prompt per provider; `plan` row in the role table and in `committed_route` / `check_run` |

Also taken: the record's four MINORs from the `69bc28d` review (bead `forge-plugin-dwf1`) are
corrected in place above; the reviewer's claim about `REVIEW_LAUNCHER_CODE` was measured before the
text was changed (11.4 item 5).

## 12. Host probes (2026-09-23, run `run-20260923-route-p0`)

Executed by the orchestrating session (the Codex `workspace-write` sandbox has no `network_access`
override, so a Codex implementer cannot call the `claude` CLI; enabling it would be a control-class
sandbox change). Scratch git repository under `/dev/shm/forge-p0/scratch` (one failing test,
`calc.py` / `test_calc.py`); every probe run with `timeout`, stdin from a brief file, stdout and
stderr captured per probe under `/dev/shm/forge-p0/out/<probe>/` (`argv.txt`, `exit`, `seconds`,
`stdout`, `stderr`), model `haiku` at effort `low` to keep the cost trivial; home paths redacted.
Script: session scratchpad `routing/p0-probes.sh`. Journal: verification records `check-01..`
on task-01 of the run.

| # | Probe | Result |
|---|---|---|
| 1 | Versions | Claude Code **2.1.280**; codex-cli **0.155.1**; Python 3.13.5; `bwrap` present; `socat` absent |
| 2 | Flag presence | all of `--safe-mode --strict-mcp-config --permission-prompts --effort --tools --allowedTools --permission-mode --output-format --verbose --model --append-system-prompt --system-prompt --plugin-dir --agent --bare --setting-sources` documented in `--help`; `--system-prompt-file` and `--append-system-prompt-file` **absent from `--help` but accepted** (nonexistent path → exit 1, `Error: System prompt file not found` / `Error: Append system prompt file not found`, not "unknown option") |
| 3 | review-cheap (claude): `--safe-mode --strict-mcp-config --output-format stream-json --verbose --model haiku --effort low --system-prompt-file <body> --tools Read,Grep,Glob,LS,Bash --permission-prompts none` | exit 0 in 9 s; `init.model` `claude-haiku-4-5-20251001`; tools ['Bash', 'Glob', 'Grep', 'Read']; result `subtype=success is_error=False terminal_reason=completed num_turns=4`; `modelUsage` keys ['claude-haiku-4-5-20251001']; verdict text starts `VERDICT: BLOCK finding: add(2, 3) returns -1 (subtraction in` (the planted bug was caught) |
| 3b | same with `--allowedTools ""` and a brief asking for `touch DENY_ME.txt` | exit 0; **inconclusive**: the model reviewed instead of attempting the command (`permission_denials` empty, file absent) — the denial path must be exercised with a brief that forces the tool call |
| 4 | plan (claude): as 3 without Bash (`--tools Read,Grep,Glob,LS`) | exit 0 in 8 s; tools ['Glob', 'Grep', 'Read']; `terminal_reason=completed`; a 3-step plan came back as the `result` text |
| 5 | implementer (claude): `--safe-mode --strict-mcp-config --append-system-prompt-file <impl body> --tools Read,Write,Edit,Bash,Grep,Glob --permission-mode acceptEdits --allowedTools Bash --permission-prompts none` | exit 0 in 14 s, 7 turns, zero denials; `calc.py` fixed and **committed inside the scratch repo** (`fix add`, Co-Authored-By trailer added by the CLI); tools ['Bash', 'Edit', 'Glob', 'Grep', 'Read', 'Write'] |
| 5b | implementer Write outside cwd (`/dev/shm/forge-p0/OUTSIDE.txt`) | exit 0; **denied by the host**: `permission_denials` = [('Write', '/dev/shm/forge-p0/OUTSIDE.txt')]; file absent; result text explains the path is outside the allowed working directory |
| 6 | not logged in (`HOME` = empty dir) | exit **1** in 1 s; `is_error=True`, `terminal_reason=api_error`, **`subtype=success`**, `modelUsage` empty, `assistant.message.model` `<synthetic>`, result text `Not logged in · Please run /login` — the launcher keys on exit code + `is_error`, never `subtype` |
| 7 | timeout kill shape (`timeout -k 5 8`) | **inconclusive**: the child completed in 6 s before the limit; all 7 stream lines parsed as JSON. Re-run with a longer brief or a 2 s limit at L's run-open |
| 8 | Codex counterpart (`codex exec --json --output-last-message … -s read-only -c approval_policy=never -c model=gpt-5.6-sol -c model_reasoning_effort=low -C <scratch> -`) | exit 0 in 53 s; **no `"model"` field in any stream event** (0 lines); last message `VERDICT: BLOCK finding: calc.py and test_calc.py are not present in the accessib` — the reviewer reported the files as not present in its accessible directory under `read-only` on `/dev/shm` (to re-check with a disk-backed scratch at L's run-open) |
| 8b | Codex not logged in (`HOME`/`CODEX_HOME` = empty) | exit 1 in 0 s, **inconclusive**: fails first on `CODEX_HOME points to … but that path does not exist`; the real not-logged-in shape needs an existing empty `CODEX_HOME` |
| 9 | Claude OS sandbox | `socat` absent on this host: fails open (10.3); not probed |

**Version floor (measured):** Claude Code ≥ 2.1.278 is known-good for every flag the 10.5 templates
use (2.1.278 probed on 2026-09-20, 2.1.280 today, both accepting the hidden `-file` flags); codex-cli
≥ 0.155.0. The launcher detects support by **version floor**, never by `--help` text (probe 2).
Open at chain L's run-open: probes 3b, 7 and 8b re-run with corrected briefs, and probe 8 on a
disk-backed scratch directory.
