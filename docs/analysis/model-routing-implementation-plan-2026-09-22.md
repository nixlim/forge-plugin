# Per-developer model routing — implementation plan (2026-09-22)

Status: **working implementation plan** (operator direction 2026-09-23, option (a) of the archive-precondition
question: committed as the working document through its own docs chain; review findings folded in first);
non-authoritative analysis note. Implementation began 2026-09-23: V1
landed as `83458df`, P0's record section as `b630964` (its probes 3b, 7 and 8b were inconclusive as run and were **re-run successfully on 2026-09-24** before L's run-open — 3b: the Claude review-cheap profile with Bash listed but not allowed attempts Bash and the host denies it, visible only in `permission_denials` while `is_error` stays false; 7: a 2 s timeout kill leaves whole JSON lines, a trailing newline and no survivor; 8 on a disk-backed directory: Codex emits no `model` field, so the launcher records model and effort from its own argv; 8b: Codex not logged in fails with 401 error events after 15 s of retries and refuses helper binaries under a tmp `CODEX_HOME` — raw outputs at `/home/agents/forge-p0-rerun-2026-09-24/`, recorded on bead forge-plugin-4g68.9; operator ruling 2026-09-24: the Claude OS sandbox is not required, so the `socat` probe is dropped and Claude-provider confinement is the instruction-bounded profile; the macOS check stays deferred to a local machine), R1 (0.6.13) as `679c651`, S (spec Revision 15) as `6fa8670` (landed 2026-09-23 through an unbound hard chain; the fresh-reviewer-evals step ran from a checkout at the chain's base revision because a candidate that changes the trigger table cannot parse the base policy under its own code — bead forge-plugin-rre3); V2 as `8702bd1` (2026-09-24, unbound hard chain, review-final PASS at iteration 2 after one BLOCK; the run closed blocked because a run-bound chain could not pass fresh-reviewer-evals — bug forge-plugin-4w5o), R2 (0.6.14) as `b533fd5` (2026-09-24), and the 4w5o fix as `d3bf5a2` (2026-09-24: the outer journal lock registry is context-propagating and fresh-eval workers run under a copied context, so run-bound chains pass fresh reviewer evals; one constraint found while landing it: a change to any FR-230 production subject must re-mint the phase-3 evidence manifest under `.forge/evals/tasks/`, and `.forge` is a transient scope root that `run-readmit` refuses, so such a candidate still cannot land run-bound — spec-level follow-up on bead forge-plugin-4w5o before chain L relies on run-bound landings for `scripts/forge/forge_cli/**` changes; that constraint was lifted by `eeeec5e`, spec Revision 16, and B landed as `e897c04` and L as `640b5dd` on 2026-09-24/25 through run-bound chains whose runs closed passed). J landed as `c35af17` on 2026-09-26 through run-bound chain `c-2026-09-26T005927Z-e6af` (J changed the spec — among other text, FR-247's deferral marker removed, DM-018's marker re-scoped to the `review.request.route` that chain E supplies, and the new helpers `scripts/forge/route_evidence.py` and `scripts/forge/route_provenance.py` named in the surface inventory; §5's J row lists the rest); its run closed blocked with the outcome landed, because the passed-close law refused on the journal ordering of two execution results (bug forge-plugin-7154). Revised 2026-09-25 with the operator's rulings for chain E (section 4: FR-246 amendment, cancel verbs, boundary-safe stream redaction; section 9 items 1-4 closed). Revised 2026-09-27 with the operator's rulings of that date: section 4's wrapper controls become the process-group design (the wrapper started under `setsid`, TERM then KILL to its whole group, the wrapper's own identity recorded before the reviewer starts, attempt-keyed `review collect` that ignores stale late completions; §4 also adds the bounded identity deadline that keeps a live spawn from being abandoned, the `wrapper-lost` state, and the proof `review cancel` needs before it kills a group whose leader is dead), replacing the blocked-child guard, readiness/release handshake and ownership pipe adopted in earlier iterations; two tradeoffs are accepted as out of scope and stated in section 4 (a descendant that deliberately detaches itself; transformed credential output); and the reviewer-facing trigger rows for `route_config.py` and `route_vocab.py`, which S planned but never landed, become policy task E0 inside chain E's run (sections 5 and 6). Docs chain `c-2026-09-26T140528Z-b2f7` (standard tier; review BLOCK with five MAJORs, all folded in here) is aborted by that ruling, and this revision re-lands through a chain declared hard with review-final as the gate. Its first-pass review is by Claude Sonnet 5 through the per-developer routes file (`review-cheap` = `claude` / `claude-sonnet-5` / `high`, `route_source: local`), orchestrated by hand until chain E makes the engine's review lane route-driven. Seven review-cheap iterations on the
earlier chain `c-2026-09-22T215657Z-8e17` (aborted as a candidate split) produced 24 plan-level findings,
all folded in (see the revision note below); the chain-level breakdown is what the runs execute, each
run's own FR-124 plan carries the exact grammars and tests (§12).
Revised 2026-09-23 after an independent read (four findings verified before adoption: task-completion
provenance guard missing; reviewer `sandbox` rule contradicted the Claude profile; S would have
inventoried a file L creates; L and E consumed prompts I created) and after the commit-chain
reviewer's iteration 1 (six findings, all verified: two-step vocabulary release for rollback safety;
J depends on L; test scopes split under the 500-line guard; 0.6.13/0.6.14 release chains; operator
approval named on every control-class chain; `routes.toml` mode `0600`, group/other-writable refused)
docs-chain iteration 4 (chain `c-2026-09-23T195113Z-e36c`, four findings verified before adoption: five-field route comparison in J; the `read` release gate accepted `x\n`, so the guard then enforced the one-empty-line frame; a parent-controlled readiness/release handshake so no unrecorded child runs; shape-aware credential redaction), docs-chain iteration 3 (credential redaction in persisted child streams with leak tests; P0's inconclusive probes stated as chain-L prerequisites; identity-checked `cancel` verb for wrapper-dead/child-alive; microsecond macOS identity or refuse), docs-chain iteration 2 (process birth identity in `child.pid` with identity-mismatch refusal and a PID-reuse test; durable `launch.json` marker bound to the execution record with idempotent terminal collection), iteration 7 (parser/dispatch/binding/import-layer registrations for E and I; `route_config.py init` invoked by the init skill step 5 and documented for manual use; `system/claude/**` and `system/local/**` in the trigger regions; route-table cardinality and per-provider `effort` sets; FR-244..247 carry the DM-014 deferral marker until their chains land), iteration 6 (`|| exit 97` guard so EOF never reaches `exec`; provenance cutoff keyed on `run_started.route` presence, not activation), iteration 5 (one `route_source` enum; trigger-table rows for the new control paths in S; blocked-child handshake before `child.pid` release; per-provider child-environment allowlist and leak test; §12 carries implementation detail to run-open plans), iteration 4 (V1 carries the FR-021/L73 non-mutating wording; orchestrator evidence in `run_started` only — no chain-state key; both child streams pumped and capped, both providers' streams validated; `CHANGELOG.md` in every code chain; exact `orchestrator-owned: ` decision grammar), iteration 3 (orchestrator evidence owned by J; one attach rule; J additive until I/P; peer vs dogfood corpus labelled) and iteration 2 (four findings, verified: provenance requires a `complete` implementer result; the
wrapper persists the child PID so `collect` sees both survivor directions; `monitor.py:78/88` and
`journal-patterns.py:421` added to the reader inventory; §11 compatibility and rollback per chain). The wrapper entries in this history — the `read` guard and its one-empty-line frame, `|| exit 97`, the blocked-child and readiness/release handshakes and the `child.pid` sidecar — record what those iterations adopted; the 2026-09-27 process-group design (§4) supersedes them.
Source of the design: `model-routing-design-2026-09-20.md` — section 10.6 (shape), 8.4.1 (vocabulary,
minus `orchestrator`), 10.5 (provider templates), 11.3 (layout constraints at `657f6c1`), 11.4 items
4–6 and 11.5 (operator decisions: routing first; confinement as ruled; `[plan]` full interchange).
Every file:line below was measured at `69bc28d`, except those added in the 2026-09-27 revision, which were measured at `c35af17`; the landed-state claims (this status, §1's task-completion provenance, §5's S, L and J rows, §6's J dependency and §7's Gate 1 rule) were rechecked against `c35af17` on 2026-09-27, and the anchors in rows for chains not yet opened are re-measured at each chain's run-open. **Level of detail:** this is the chain-level work
breakdown — scope, ordering, gates, controls, compatibility. Each chain's run-open writes its own
FR-124 plan into the run directory with exact grammars, diagnostics and test lists, reviewed by that
run's own review cycle; findings against implementation detail here are folded in where they change a
chain's scope or a control, and otherwise carried to that chain's run-open plan (§12). Method for the work itself: the operator's standing
direction — Codex (or Claude, once this lands) implementers inside Forge runs, the session
orchestrates only; every chain through the Forge commit / worktree-merge gates.

## 1. End state (what a developer gets)

```toml
# <common-root>/.forge/local/routes.toml   — one per clone, never committed, owner-only
schema = "forge-routes/1"

# [implementer]
# provider = "codex"          # codex | claude
# model    = "gpt-5.6-sol"
# effort   = "ultra"

# [review-cheap]
# provider = "codex"
# model    = "gpt-5.6-sol"
# effort   = "high"

# [review-final]
# provider = "claude"
# model    = "fable"
# effort   = "high"

# [plan]
# provider = "claude"
# model    = "fable"
# effort   = "high"
```

- Seed ships fully commented out; an untouched role follows the **committed default at the launch
  HEAD**, then the plugin default (uninstalled repos). No environment layer. Keys other than
  `schema`, the four tables and `provider` / `model` / `effort` are malformed; a malformed, foreign-
  owned, symlinked, oversized (> 16 KiB), tracked, un-ignored or misplaced (linked-worktree root)
  file **refuses** the launch, as does one whose mode is group- or other-writable (`st_mode & 0o022`)
  — another local user must not be able to change a developer's provider or confinement selection;
  `route_config.py init` writes the seed `0600`. A bad file is never a "mismatch".
- **Table cardinality and validation:** every table is optional; a present table must carry all three
  keys (`provider`, `model`, `effort`) — a partial table is malformed, never inherited; `provider` ∈
  {`codex`, `claude`}; `model` matches the model-id grammar (§2); `effort` ∈ the provider's accepted
  set from the committed profile table (Codex: `minimal | low | medium | high | ultra`; Claude:
  `low | medium | high | max` — both confirmed by probe 0 before L opens); a value outside the
  provider's set, or a model/effort pair the profile table forbids, is malformed with a diagnostic
  naming the table and key; an absent table = committed default for that role. Negative tests cover
  each rule.
- Governed and committed (control-class): the role table; **eight (provider, role) profiles** —
  argv template + permission/sandbox profile + recorded `sandbox` value; role prompts and bodies;
  reviewer authority; gates; shipped defaults; Gate 2 (candidate-bound, Codex, unchanged).
- A typed run freezes the resolved routes into `run_started.route`; `execution-start` and run-bound
  `review request` refuse divergence from the snapshot; unbound chains resolve at launch and record
  the route in the review request and package header. The orchestrator's model is evidence only: chain J's `run_open` reads the last
  `message.model` from the session transcript located through `$CLAUDE_CODE_SESSION_ID` (host
  detail, best effort) into known-optional `run_started.orchestrator_model` = `{observed: <id>}` or
  `{observed: null, reason: <transcript-absent|var-unset|unreadable>}`; **run records only** — chain
  state gains no key (a run-bound chain cites its run's record; an unbound chain records nothing); never compared, never refused; `check_run`
  reports `same-model binding review` from it (decision 12).
- **Task-completion provenance** (8.4.9 item 7; FR-247, landed by chain J in `c35af17` — `builders.task_finish`
  L9111 calls `route_provenance.enforce_task_finish` and `run_close` L9718 calls `enforce_run_close`, both defined in the new `scripts/forge/route_provenance.py`): `task-finish
  --status complete` on a task with `files[]` refuses unless the journal holds, for that task, an `implementer`
  execution **whose terminal `execution_result` has `status: complete`** (a failed, blocked or
  still-in-flight execution is not provenance), a bound `chain-landing` decision, or an
  `orchestrator-owned` decision — exact grammar: a typed `decision` with `task: <id>`, `resolution`
  beginning exactly `orchestrator-owned: ` followed by a nonempty reason, and nonempty `basis[]` citing
  the evidence (paths or journal ids); written by the run owner through `journal decision-add` like
  every decision, so its authority is the run owner's. This admission is legibility, not
  enforcement: the orchestrator can always record one, and it is visible in the archive and to
  `check_run` as `orchestrator-owned completion` — the GH#13 failure was the *absence* of any
  record, which this makes impossible without an explicit, attributable line; `run-close --judgment passed` refuses while any complete task lacks that provenance.
  Applies only to runs whose `run_started` carries the `route` key (a J-era run); runs opened before J,
  including already-activated ones, are never provenance-checked, so no pre-J completed task is
  stranded at `run-close`. Historical records never re-validated. This is the rule that makes a
  GH#13-shaped silent substitution dead-end loudly at close.
- Legibility: every execution / review record carries `route_source` — exactly one of `local`,
  `committed-default`, `plugin-default`, `unrecorded` (never stored: a launch that passed no route fields — prose
  launches until chain I, and runs opened before chain J) — the same four-value enum in the journal
  schema, every diagnostic and the §11 compatibility tests, `route_sha256`, `sandbox` (`workspace-write` | `read-only` |
  `instruction-bounded`), and — Claude lane only — the stream-observed model id. `check_run`
  emits `implementer ran instruction-bounded` and `same-model binding review` as findings, never
  refusals.

## 2. Canonical vocabulary (final; the vocabulary chain enforces it on new writes)

| Field | New writes | Read-side legacy map (never re-validated, never rewritten) |
|---|---|---|
| `role` | `implementer` · `review-cheap` · `review-final` · `plan` · `monitoring` | `implementation`/`implementer`/`implement` → `implementer`; `review`/`reviewer` + `codex` → `review-cheap`; `review`/`reviewer` + `claude` → `review-final` |
| `provider` | `codex` · `claude` (the launching CLI, never the model vendor) | fresh-eval literal `codex-cli` documented as Gate-2-only, mapped → `codex` (inside recorded fixture digests; no rename) |
| `event_source` | `exec` · `claude` | `codex` → `exec`; `agent-tool` → `claude`; a literal path (one live row) → `exec` |
| `mode` | `headless` · `detached` · `subagent` · `teammate` | `read-only`/`workspace-write` in `mode` → legacy sandbox; `orchestrator-inline` → refused on write |
| `sandbox` | known-optional, checked: `workspace-write` · `read-only` · `instruction-bounded`. The **required value is the committed profile's declared value for (provider, role)** (§3): codex implementer `workspace-write`; codex review-cheap / plan `read-only`; claude plan `read-only` (no Bash); claude implementer, review-cheap and review-final `instruction-bounded` (Bash granted). Validation compares the recorded value to the profile table, never to a per-role constant; the test covers all eight cells | — |
| model ids | verbatim; grammar `^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}(\[1m\])?$`; `inherit` refused | comparison strips one `[1m]`; aliases compared by family, never by alias semantics |
| non-mutating | `route_vocab.is_non_mutating(raw_role)` on `review|reviewer|review-cheap|review-final|plan|monitoring` | replaces `journal.py:8185` / `:8404` `role == "review"` (fixes 33 misclassified live rows) |

Consumer impact (the **peer's** corpus, 152 executions — distinct from this repository's 153-execution dogfood corpus used in §7): `implementation` ×68, `(claude, implementation)` ×29,
`event_source: agent-tool` ×27, `orchestrator-inline` ×1 — all refused on new writes after the
vocabulary release with a diagnostic naming the canonical id. Named in the release notes and in the
`AGREED:` restatement.

## 3. Provider profiles (committed; one argv template + one permission profile per cell)

| role \ provider | `codex` | `claude` |
|---|---|---|
| implementer | `codex exec --json --output-last-message <handoff> -s workspace-write -c approval_policy=never -c model=<m> -c model_reasoning_effort=<e> -C <worktree> -` ; sandbox `workspace-write` | `claude -p --safe-mode --strict-mcp-config --output-format stream-json --verbose --model <m> --effort <e> --append-system-prompt-file <plugin>/system/claude/prompts/implementer.md --tools "Read,Write,Edit,Bash,Grep,Glob" --permission-mode acceptEdits --allowedTools "Bash" --permission-prompts none` , cwd = worktree, brief on stdin; sandbox **`instruction-bounded`** (11.4.4) |
| plan | review-cheap template with `system/codex/prompts/plan.md`, `-s read-only`; sandbox `read-only` | review-cheap Claude template with `system/claude/prompts/plan.md`; tools `Read,Grep,Glob,LS`; sandbox `read-only` |
| review-cheap | existing `_verbs_review_request.py:360-379` argv; sandbox `read-only` | `claude -p --safe-mode --strict-mcp-config --output-format stream-json --verbose --model <m> --effort <e> --system-prompt-file <plugin>/system/claude/prompts/review-cheap.md --tools "Read,Grep,Glob,LS,Bash" --permission-prompts none`; Bash instruction-bounded (parity with today's review-final, 10.4); sandbox **`instruction-bounded`** |
| review-final | same as review-cheap `codex` with the review-final body as prompt | `--system-prompt-file <plugin>/agents/review-final.md` body (frontmatter stripped, `${CLAUDE_PLUGIN_ROOT}` expanded by the launcher); tools `Read,Bash,Glob,Grep,LS` (FR-111 parity); sandbox **`instruction-bounded`** |

**Child environment (both providers): allowlist, never inherit.** Base allowlist `HOME PATH LANG
LC_ALL USER TMPDIR TERM`; Codex adds `CODEX_HOME`; Claude adds the gateway/endpoint names the 10.3
ruling passes through unchanged (`ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`,
`CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, `AWS_*`, `GOOGLE_*`, `CLOUD_ML_REGION`) — the
developer's own credentials for their own child, per the login-is-the-operator's ruling; never any
`ANTHROPIC_MODEL`/`ANTHROPIC_DEFAULT_*` (the route decides the model), never `FORGE_SESSION_PID`,
`CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`, `CLAUDE_*` hook variables, or `CODEX_*` beyond `CODEX_HOME`.
The allowlist is one committed table in `route_config_probe.py` (chain L placed it there; E imports it); values are never written to any record or
log (the completion record stores only the sorted **names** that were passed). Because a child can print
its own environment, the wrapper's stream pumps **redact** the value of EVERY admitted allowlisted variable that was
passed (not only credential-bearing names: FR-245 says records and logs carry only the sorted admitted names, never their
values, so `ANTHROPIC_BASE_URL`, `CLOUD_ML_REGION`, `HOME` and every other passed value are redacted the same way; an admitted
variable whose value is shorter than four bytes is NOT PASSED to the child at all — its name is recorded under `omitted_short`
in the completion record — because a one-to-three-byte value can be neither redacted safely nor allowed to reach a log, so
no raw or JSON-escaped value of any length can persist; tests cover 0-, 1-, 2- and 3-byte values for a credential name and a base-URL name) before a byte
reaches `events.jsonl` or `stderr.log`, and both files are created `0600`; the Codex `--output-last-message` capture is a
mediated boundary: Codex writes it to an owner-only STAGING file (`0600`, under the attempt directory, opened with
`O_NOFOLLOW`, never the durable artifact path), and only the wrapper reads that staging file, applies the same redaction, publishes
the redacted bytes to the durable `verdict.txt` by tmp-then-`os.replace`, takes the verdict digest over the redacted bytes and
unlinks the staging file — so unredacted bytes never reach a durable artifact (test: a fake provider that echoes every passed
value into its last message yields a durable verdict containing only `<redacted:NAME>` and no staging file afterwards); the
Claude verdict is extracted from the already-redacted stream. Redaction is
**shape-aware**, because an exact raw-value match is not enough: the stdout pump parses each line-JSON
event and replaces the value inside every string (matching both the raw value and its JSON-escaped form —
quotes, backslashes and `\uXXXX` escapes — then re-serialising), and a line that is not valid JSON is
redacted as raw text and still counted as the stream's first bad line; the stderr pump replaces raw values
**longest-first** so a secret that is a prefix of another cannot leave a suffix behind; every replacement
is `<redacted:NAME>`. Redaction is **boundary-safe**: both pumps match the raw and escaped forms as byte patterns across
read boundaries (a carry buffer one byte shorter than the longest secret is held back until the next chunk or EOF), so a
credential that contains a literal newline or is split across two reads still cannot reach the persisted stream; per the
operator ruling of 2026-09-25 redaction is the only control here — no launch-time refusal is applied to secret values that
contain CR or LF. Tests: a canary variable set in the parent is absent from the child's `env` output;
a child that prints its environment on stdout and stderr shows every passed value only as
`<redacted:NAME>` in both persisted streams and in the extracted verdict artifact; adversarial values containing `"`, `\`, newlines and
non-ASCII, one secret that is a prefix of another, and a value printed already JSON-escaped inside a
`stream-json` `result` string — asserting that neither the raw nor the escaped form survives in either
file. Redaction is scoped to those two forms: a value the child emits transformed (base64, hex, split across separate strings or otherwise re-encoded) is not redacted — an accepted out-of-scope tradeoff (operator ruling 2026-09-27, §4).

Verdict / handoff capture: Codex → `--output-last-message`; Claude → the final `result` event of the
stream (the wrapper extracts `result.result` into `verdict.txt` / `handoff.md`; `is_error`,
`terminal_reason`, exit code decide success — never `subtype`). Observed model: Claude stream
`init.model` / `message.model` / `modelUsage` keys → completion record `observed_model`; Codex none.
Not-logged-in shape (exit 1, `is_error`, `Not logged in`) → fixed diagnostic naming the provider CLI
and the manual re-login step; the verb is re-run by the developer (10.3 ruling). Hidden flags
(`--system-prompt-file`, `--append-system-prompt-file`) are accepted by Claude Code 2.1.280 but absent
from `--help` — feature detection is by **version floor**, never by `--help` text.

## 4. Fail-closed controls of the generalised lane (executable tests, per 11.4 item 5)

Kept from `REVIEW_LAUNCHER_CODE` (`engine/_state.py:119-260`): argv and prompt digest recomputation;
owner-controlled `O_NOFOLLOW` regular-file descriptors; 65,536-byte verdict cap; tmp-then-
`os.replace` completion record. **Kept too, and now load-bearing**: `review request` already starts the wrapper under `setsid` (`Popen(start_new_session=True)`,
`_verbs_review_request.py:398`) and the wrapper starts the reviewer without a new session (`engine/_state.py:182`), so the
wrapper leads a session and process group that the reviewer and every descendant stay in (Python `subprocess` and Node drop
inherited descriptors but keep the group — measured 2026-09-27); E's lane keeps that shape for both reviewers and I's
`launch` reuses it. **Added**: `wait(timeout=T)` with
`killpg(SIGTERM)` then `SIGKILL` after 5 s to that whole group, `T` fixed per profile (review 1200 s, implementer 3600 s,
plan 1200 s — plan values, operator confirms); child **stdout and stderr both on pipes**, drained concurrently by the wrapper (one thread each, or
`selectors`), stdout appended to `events.jsonl` under a 16 MiB cap and stderr to `stderr.log` under a
1 MiB cap, either over-cap = group kill + `error: "events cap"` / `"stderr cap"`; per-line JSON
validation of the event stream for **both providers** (Codex `--json` and Claude `stream-json` are
both one JSON object per line) with the first bad line number in `error`; a provider whose stream
stops being line-JSON fails closed, never silently; completion record (`forge-review-process/2`) gains `provider`, `route_source`, `route_sha256`,
`sandbox`, `observed_model`, `timed_out`, `events_bytes`, `pgid`, `attempt` (`review collect` accepts `/1`
records for requests made before the upgrade, §11). **Survivor states in both directions**: today
`review_collect` (`_verbs_review_collect.py:170-171`) probes only the wrapper PID from the request and
learns the child's PID only from the completion record the wrapper writes at exit, so a child that
outlives a dead wrapper is undetectable. FR-246 as committed specifies a child started blocked behind `sh -c 'read _ <&3 || exit 97; exec "$@"'` and released by
one LF on fd 3 once a `child.pid` sidecar is durable; per the operator rulings of 2026-09-25 and 2026-09-27, chain E
**amends FR-246 in its own candidate** to the process-group design below — the fd-3 guard, the LF release frame, the
exit-97 paths and the child sidecar are removed; the `setsid` wrapper as group leader, its self-recorded identity, the
group kill, attempt-keyed `collect` with its `launching`, `abandoned`, `wrapper-lost` and `stale` outcomes, the `/2`
record's `child_pgid` replaced by `pgid` and `attempt`, and the cancellation verb with its group-ownership proof are
added; the real-pipe / real-`sh` control test becomes a real-process-group test — under binding review and operator
approval, so the spec and the shipped wrapper agree at landing. **Wrapper identity before the reviewer runs:** the
wrapper's first act is to publish an owner-only identity record in the attempt directory — its PID, its PGID (equal to
its PID: `setsid` made it the group leader) and **the kernel process-birth identity**: on Linux the `starttime` field of
`/proc/<pid>/stat` plus the boot id from `/proc/sys/kernel/random/boot_id`; on macOS the `kinfo_proc` `p_starttime` at
microsecond resolution read through `sysctl kern.proc.pid.<pid>` (never `ps -o lstart=`, whose one-second resolution
cannot separate rapid reuse); where an identity cannot be read at that resolution the probe reports `identity-unproven`
and automated kills are refused; tmp-then-`os.replace` + `fsync`. Only then does it start the reviewer — the ruling's
"then execs the reviewer", done as a child started without a new session, because the wrapper stays alive as the group
leader that pumps, caps, redacts and writes the completion record — so the reviewer and every descendant keep the
wrapper's PGID; right after the start the wrapper adds the reviewer's PID and birth identity to its record (a second
atomic replace), and because it is itself a group member it publishes its completion record before its own group kill
reaches it (exact order in E's run-open plan, §12). There is no readiness wait and no release handshake: the wrapper
never waits on its parent, and a parent that dies at any moment leaves an attempt that either gains the wrapper's
identity record before any reviewer starts or never starts one. The launching verb (`review request`, or I's `launch`,
which reuses this wrapper) persists its durable owner record *before* spawning the wrapper — the `review.request` chain
event, which records the attempt id of the random `attempt-<hex>` directory the verb already creates, or the
`launch.json` marker plus the `execution-start` journal record, each tmp-then-`os.replace` + `fsync`. Until a bounded
identity deadline has passed (60 s after the owner record, plan value) an attempt with neither an identity record nor a
completion is `launching` and `collect` waits; after it, that attempt is a durable **abandoned intent** (the parent died
before or during the spawn, or the wrapper died before its identity write): `collect` (or the next `review request` /
`launch`) transitions it to `abandoned` with a completion-shaped record (`error: "abandoned"`, no identity), clears the
request and admits a retry under a new attempt id. The wrapper's identity publish and `collect`'s abandonment both claim
the attempt by exclusive creation, so exactly one wins and a wrapper that loses exits without starting the reviewer
(exact claim rule in E's run-open plan, §12). An identity record whose wrapper is gone, whose group has no member left
and whose attempt holds no completion is **`wrapper-lost`** (wrapper and reviewer both died without publishing) and is
cleared the same way. **Attempt-keyed collect:** `review collect` accepts only the attempt id the current request
records; a completion that appears in any other attempt directory — the late finish of a cancelled or abandoned attempt,
bounded by its own profile timeout while its wrapper lives — is recorded as `stale` and ignored, never admitted as
verdict evidence and never a chain transition, so a retry cannot collide with its predecessor. `review collect`
probes the recorded wrapper and its group separately — every probe and every kill first re-reads the live birth identity
and refuses to act when it differs from the record (a reused PID is reported as `identity-mismatch`, never killed, never
counted as alive; the group rule is below), reporting `wrapper-dead / child-alive` (a group member outlives the wrapper:
refuse; ended only by the
new identity-checked **`review cancel`** (declared by chain E) / **`launch cancel`** (declared by chain I) verbs — each a NEW verb registered in `engine/_parser.py`, dispatched from `app/_dispatch.py`, bound as an `Engine` method (`review cancel` also as a `MergeEngine` method, since shared review dispatch selects `MergeEngine` for merge chains), inventoried in `test_repo_conformance`, with its own §11 compatibility row and tests,
which re-checks the recorded identities, sends TERM and, after 5 s, KILL to the whole group when the group is proven ours
(below), waits for the group to empty, and writes a `cancelled` completion record — the wrapper's own kill path cannot
run once the wrapper is dead) and `wrapper-alive / child-dead` (wait for the completion record) as distinct diagnostics.
Tests, with a real `setsid` wrapper and real processes: the identity record exists and matches the wrapper before the
reviewer's first instruction (a marker reviewer asserts it); a reviewer that starts a Python `subprocess` grandchild and
a descriptor-dropping child leaves no survivor after the timeout kill or `review cancel`; the parent killed before the
spawn (`launching` inside the deadline, then `abandoned`, retry admitted) and after it (identity findable, `review
cancel` empties the group); a wrapper that loses the claim to `abandoned` (no reviewer starts); the wrapper killed while
the reviewer lives (`wrapper-dead / child-alive`, then `review cancel`) and after the reviewer has also exited
(`wrapper-lost`); a PID-reuse case (a different process at the recorded PID: `identity-mismatch`, no kill); and a late
completion in a cancelled attempt's directory (recorded `stale`, chain state unchanged). Each
control gets a test that fails when the control is disabled in memory (completeness item 1).

**Recovery transitions (every durable request or execution can be retried or closed):** the table below is the contract E
(review lane) and I (launch lane) implement and test, one row per failure class; `request` means the `review.request`
chain event or the `launch.json` marker, `clear` means the verb records the terminal completion, appends the matching
chain event / journal `execution_result`, and returns the chain (or task) to the state it had before the request, so the
next `review request` / `launch` starts a fresh attempt under a new attempt id and directory (the review iteration number advances only where the row consumes the iteration); a completion that later lands in a superseded attempt's directory is `stale` and ignored. | failure | durable
evidence | `collect` reports | transition |
|---|---|---|---|
| pre-spawn failure (route refusal, executable missing, version below floor, prompt write error) | no request written, or
the request written and immediately superseded by a `launch-failed` completion the verb itself writes | `launch-failed:
<cause>` | request cleared in the same verb; retry allowed |
| abandoned (parent died before or during the spawn, or the wrapper died before its identity write — no reviewer ever started) | request whose attempt holds neither an identity record nor a completion | `launching` (wait) until the identity deadline, then `abandoned` | clear; iteration NOT consumed; retry allowed under a new attempt id |
| stale (a completion in an attempt directory the current request does not record: the late finish of a cancelled or abandoned attempt) | that attempt's own completion | `stale`, recorded and ignored | none: never verdict evidence, never a chain transition |
| authentication failure (Codex 401 shape, Claude `Not logged in`) | completion with `error: not-logged-in` | the exact
FR-245 refusal literal for the provider | clear; retry allowed after the operator logs in (never automated) |
| timeout / cap breach / bad stream line | completion with `timed_out: true` or `error: events cap|stderr cap|bad line
N` | the same, as a BLOCK-shaped refusal with the evidence path | review: chain to `revising` with the iteration consumed
(the request was real); launch: `execution_result: failed` |
| cancellation (`review cancel` / `launch cancel`) | `cancelled` completion | `cancelled` | request cleared; iteration NOT
consumed; retry allowed under a new attempt id, so a late completion of the cancelled attempt is `stale` |
| wrapper-dead / child-alive | the recorded group still has a member, wrapper gone, no completion | refusal naming `cancel` | only `cancel` ends it |
| wrapper-lost (wrapper and reviewer both died without publishing a completion) | identity record, wrapper gone, the recorded group empty, no completion | `wrapper-lost` | clear; iteration NOT consumed; retry allowed under a new attempt id |
| wrapper-alive / child-dead | wrapper still draining | wait | none until the completion record |

**Survivors after the leader exits:** the wrapper is the group leader, so its recorded PID is also the PGID, and the
group itself is the ownership boundary — no descriptor token, since Python `subprocess` and Node drop inherited
descriptors but keep the group (measured 2026-09-27). Every probe and every kill re-reads identity first. A live process
at the recorded PID with the recorded birth identity is our wrapper, so the group is ours. With the wrapper gone, the
group is ours only if it has never emptied, because POSIX never reuses a process-group id while any member lives: a
process the wrapper recorded (the reviewer) that is still alive with its recorded birth identity and still carries the
recorded PGID proves that, and `cancel` then kills the group although its leader is dead. Members that carry the recorded
PGID (`/proc/<pid>/stat` field 5 on Linux; `pgrep -g` on macOS) with no recorded process among them cannot be told apart
from a recycled id (our whole group exited, an unrelated process received the id, led a new session and exited leaving
members), so `cancel` kills nothing, reports `identity-unproven` with their PIDs and still clears the request with a
`cancelled` completion; any late output of that attempt is `stale`. A live process at the recorded PID with a different
birth identity means our wrapper and group are gone and the id was recycled (reported `identity-mismatch`, never
killed); a boot id that differs from the recorded one means every recorded process is gone; no member at all is
`group-empty` — in all three cases an attempt without a completion is `wrapper-lost`. Tests cover
leader-dead / group-alive with the reviewer still alive (the group is killed), leader-dead with only an unrecorded
grandchild left (`identity-unproven`, nothing killed, request cleared), leader-alive, group-empty, and a recycled-id fake
(an unrelated process at the recorded PID with a later birth time), which is refused.

**Accepted tradeoffs (operator ruling 2026-09-27; out of scope, stated in E's FR-246 amendment rather than claimed as
covered):** (1) a descendant that deliberately detaches itself (`setsid` / `setpgid`) leaves the wrapper's group and
escapes the group kill and the group probe — implementers can do the same today; (2) credential redaction (§3) matches
only a passed value's raw and JSON-escaped forms, so a value a child emits transformed — base64, hex, split across
separate strings or otherwise re-encoded — is not redacted.

## 5. Work breakdown — chains

Each chain = one bead, one Forge run (typed run-open, one implementer task per row where the
chain has more than one seam), one commit chain or one worktree branch reintegrated through the
worktree-merge chain. Tier is derived by the classifier; the column gives the expected result.

| # | Chain | Scope (new files **bold**) | Spec / skills touched | Tier · gates | Size (prod / test lines) |
|---|---|---|---|---|---|
| 0 | **Probes & version floor** | measured facts appended to the record §12: Claude Code floor for `--safe-mode`, `--permission-prompts`, `--effort`, hidden `-file` flags (2.1.278 known good); codex floor 0.155; a complete headless run of each of the four Claude profiles in a scratch repo (verdict/handoff extraction, denials list, `modelUsage`); Claude OS sandbox with `socat` present on one machine — DROPPED by the operator ruling of 2026-09-24 (no OS sandbox); macOS check of the argv templates | none | docs-only · standard | 0 / 0 |
| 0.5 | **`AGREED:` restatement draft** | text redrafted from 8.4.9 for items 3/5/6 reversal (10.5) and the plan role; presented in the terminal; **not posted** until the operator's nod; beads `eki`, `68r` re-pointed then | none | docs-only | 0 / 0 |
| V1 | **Vocabulary — readers** (release **0.6.13**) | **`scripts/forge/route_vocab.py`** (enums, legacy map, `is_non_mutating`, model-id grammar; stdlib; `commitment_paths.py` pattern); every **reader** accepts both legacy and canonical spellings through the map: `journal.py:8185/8404` → `is_non_mutating`; `journal-patterns.committed_route` L185 **and its per-task reviewer count at L421** (`role == "review"` today), `check_run` L354, `learn-proposals.py`, drift `by_reviewer_role`, and **`scripts/codex_orchestrator/monitor.py:78/88`** (special-cases `claude` and rejects any `event_source` outside `{None, exec}` — must map `codex` → `exec`, `agent-tool` → `claude`, literal path → `exec`); the inventory is completed at run-open by `grep -rn` over `scripts/` and `tests/` for every role / provider / event_source / mode literal, with each hit's disposition in the handoff; **writers unchanged**. Purpose: a consumer on 0.6.13 reads records written by 0.6.14+ (and a 0.6.14 → 0.6.13 rollback is non-fatal). **`tests/test_route_vocab.py`**, **`tests/test_vocab_readers.py`** (live-corpus fixture: 153 rows normalise; three legacy runs archive; canonical-spelled fixture rows read on this version) | **Terminology L73** ("Mutating execution | a journal `execution` whose `role` is not `\"review\"`" → "… whose raw `role` is not one `route_vocab.is_non_mutating` accepts") and **FR-021 L812** (same substitution) move here because V1 changes that semantics; FR-200 (journal-patterns); §5 inventory L115 adds `route_vocab.py`; no enum text yet | **hard** (`scripts/**`) · STRICT evals · review-final · operator approval | ~250 / ~450 |
| R1 | **Release 0.6.13** | `CHANGELOG.md` `[Unreleased]` → `[0.6.13]`; `.claude-plugin/plugin.json` + marketplace version; version tests; notes: readers accept canonical ids, no behaviour change for writers, 0.6.14 will refuse legacy spellings on new writes (one-release notice) | — | control (`.claude-plugin/**`) · review-final · operator approval | small |
| V2 | **Vocabulary — writers** (release **0.6.14**) | `builders.execution_start` L9142 calls `route_vocab.validate_new_write(...)` (net-non-positive edit); `journal.py:1976-1998` same call; `codex_orch_tools.py:204` parser unchanged (no `choices`: the builder refuses); orchestrate role table L21-24 rows renamed; `docs/orchestration-contract.md` example; **`tests/test_vocab_writers.py`** (fail-when-disabled: each legacy spelling refused on a new write with the canonical id in the diagnostic; the FR-019 same-candidate rule checked against every writer surface) | Terminology L73-74; FR-019 L748/L755/L761 ("adds no enum" amended; every writer surface in the same candidate); FR-021 L812; FR-030 L826 role ids; FR-033 L829; FR-103/DM-012 `codex-cli` sentence; scenarios L2109-2129 | **hard** (spec + skills) · STRICT evals · review-final · operator approval; fresh evals fire (`skills/orchestrate/SKILL.md` is a `reviewer-routing` + `model-provider-version` trigger) | ~150 / ~400 |
| R2 | **Release 0.6.14** | changelog / versions / version tests as R1; notes name every refused legacy spelling and the peer-corpus impact (§2) | — | control · review-final · operator approval | small |
| S | **Spec Revision 15** | Every new requirement carries the repository's own deferral marker until its chain lands — the DM-014 precedent ("phase-3 authority; implementation deferred"): each of FR-244..247 and DM-018 is written as "(Revision 15 authority; implementation deferred to chain <L\|J\|E\|I>)", and the landing chain removes the marker in the same candidate as its tests — exact ownership: FR-244 → L (done, `640b5dd`), FR-247 → J, DM-018's run/execution fields → J (J re-scopes the DM-018 marker to `review.request.route` → E), FR-246 → E, FR-245 → I as the last of B/E/I — so no intermediate tree claims a control it does not have and the fail-when-disabled completeness item binds only at the landing chain. **FR-244** routes file (grammar, ownership, exclusion, precedence, snapshot, refusals, evidence classes); **FR-245** provider profiles matrix (§3) and `sandbox` values; **FR-246** headless review-final lane, `review attach` retired for review-final in commit chain, merge chain and init (FR-083, FR-216 amendments; FR-211 states unchanged); **DM-018** `run_started.route` and `review.request.route` records; **FR-247** task-completion provenance (§1) at `task-finish` and `run-close`; **`forge-project.md` `reviewer-facing-eval-triggers`** gains rows so the new control surfaces fire fresh evals: `reviewer-routing` += `scripts/forge/route_config.py, scripts/forge/route_vocab.py, scripts/forge/forge_cli/app/**, system/local/**` (of these four, S landed only `scripts/forge/forge_cli/app/**` and `system/local/**` — measured at `c35af17`; the two route-file rows never landed and are E0's, §5 E row and §6); `agent-prompt-template` += `system/claude/prompts/**` (pattern rows may precede the files; the same rows go into the plugin's rendered-policy template under `system/` and the installer test that pins it, and the `trigger-paths` and `project-triggers` regions gain `system/claude/**` and `system/local/**` — `scripts/forge/route_config.py` is already covered by the `scripts/forge/**` trigger row and needs no row of its own); the same rows land in every rendered policy copy under `system/` and in the installer/conformance tests that pin them; FR-030 (role table with per-provider sandbox column), FR-034 (argv pattern per provider), FR-052 (routing by tier unchanged, provider from route), FR-060, FR-111 (frontmatter no longer load-bearing; body pinned), FR-132, FR-183 (shadow threat re-cut: the launcher reads the plugin body), threat model L41 sentence; Learning provenance untouched. **No inventory row for files this chain does not create** — `test_every_inventoried_script_exists` (`test_repo_conformance.py:453`) fails on an inventoried absent path | all of the left column | **hard** · STRICT evals · review-final · operator approval | ~120 spec sentences / conformance tests updated |
| B | **Role bodies** | **`system/codex/prompts/plan.md`**, **`system/codex/agents/plan.toml`**, `system/codex/config.toml` gains `[agents."plan"]`; **`system/claude/prompts/{implementer,plan,review-cheap}.md`** (Claude role bodies read from the plugin root; `agents/review-final.md` stays the review-final body); installer inventory pins (`test_installer.py:340-352`, `test_docs_contract.py`, `test_fresh_eval_policy.py`, `_fresh_eval_support.py`, `test_e2e_smoke.py`) gain the two Codex paths; `journal-patterns.committed_route` L185 and `check_run` gain the `(codex|claude, plan)` rows; `test_repo_conformance.ROLE_PATHS` gains `plan` | FR-030 role table row, FR-245 prompt inventory | **hard** · `system/codex/agents/**` is a `reviewer-routing` + `model-provider-version` trigger → fresh evals; review-final; operator approval | ~150 prose / ~150 |
| L | **Leaf: `route_config.py` + seed** (landed `640b5dd`, 2026-09-25) | **`scripts/forge/route_config.py`** (`init` — writes the seed once, idempotent `info/exclude` append; `show`; `check`; `resolve --role --head` JSON; `probe` — one bounded launch per resolved (provider, model, effort) pair, Codex via `codex exec`, Claude via the `plan` profile with B's `plan.md` body and a one-line brief), **`scripts/forge/route_config_git.py`** (bounded, environment-scrubbed Git boundary) and **`scripts/forge/route_config_probe.py`** (the probe half: FR-245 argv templates, the environment allowlist table, caps, group teardown — the allowlist lives HERE, and chain E imports it from here); **`system/local/routes.toml.seed`**; six test modules **`tests/test_route_config.py`**, `_grammar.py`, `_security.py` (ownership matrix, misplaced copy, git scrub), `_resolution.py` (precedence at a fixed HEAD, review-final frontmatter chain), `_probe.py` (fake CLIs), `_support.py` | FR-244 conformance; §5 inventory L115 adds `route_config.py` (created here) | **hard** (`scripts/**` is control) · STRICT evals · review-final · **operator approval**; fresh evals fired (L's candidate touched the spec, a `model-provider-version` trigger, and the `system/local/**` seed); `route_config.py`'s own `reviewer-routing` row never landed (E0 adds it) | ~450 / ~600 |
| J | **Journal** (landed `c35af17`, 2026-09-26; its run closed blocked with the outcome landed — journal ordering, bug forge-plugin-7154) | `builders.run_open` L8900 gains `route` through `route_evidence.opening_fields` (the new `scripts/forge/route_evidence.py`, which resolves all four roles through L's `route_config.load` at `repo_head`, digested); `journal.py:1918` schema (`route_evidence.validate_run_started`): `route` known-optional object; `builders.execution_start` gains **known-optional** `sandbox`, `route_source`, `route_sha256`; when a record carries them and the run has a snapshot, **all five** route fields — `provider`, `model`, `effort`, `route_source`, `route_sha256` — are compared to the frozen `run_started.route` entry for that role and any divergence refuses, naming the field (`forge: execution refused — route diverges from run snapshot for <role>: <field>`), with one independent mismatch test per field; a record **without** route fields (a prose launch — the only launch path until chain I) is accepted and stored unchanged — no field is written for it — and every reader projects it as `route_source: unrecorded` (DM-018: projection only, never stored, never rewritten) with a `check_run` finding, so J never strands the documented launch path; chain I makes the fields mandatory for `launch`-made executions and chain P retires the prose launch blocks; `codex_orch_tools.py` parser adds `--sandbox --route-source --route-sha256`; `journal-patterns` status gains `local`; `check_run` finding `; developer-local selection (route_sha256 …)` and `implementer ran instruction-bounded`; **orchestrator evidence**: `route_evidence.orchestrator_model()` (transcript read, bounded, best effort) called from `run_open` only, recorded as above (no chain-state key; §11 J row), tested with a fixture transcript and with the variable unset; **task-completion provenance**: `builders.task_finish` and `run_close` call `route_provenance.enforce_task_finish` / `enforce_run_close` (the new `scripts/forge/route_provenance.py`, built on its `completion_provenance(records, task)`) and refuse per §1; **`tests/test_route_snapshot.py`**, **`tests/test_task_completion_provenance.py`** (fail-when-disabled: a complete task with zero executions and decisions is refused; an implementer execution with a `failed` result, or with no `execution_result` yet, is refused; a `complete` result for the task admits; a bound `chain-landing` decision admits; an `orchestrator-owned: ` decision with `task`, reason and nonempty `basis[]` admits, and one missing any of the three is refused with the grammar in the diagnostic; an implementer execution recorded against a different task does not; the distinct empty-`files[]` branch: `task-finish --status complete` on a task with empty `files[]` is admitted without provenance, and `run-close --judgment passed` then refuses naming that task — a fail-when-disabled test for exactly that transition) | DM-018 (marker re-scoped to `review.request.route` → E; the run-open writer obligation; the route-trio and absent-role refusals), FR-247 (deferral marker removed), FR-019 (known-optional fields), the drift summary schema's `journal_patterns.routing` elements (`route_source`, status `local`); the surface inventory names `route_evidence.py` and `route_provenance.py` | **hard** · STRICT evals · fresh evals (the spec is a `model-provider-version` trigger) · review-final · **operator approval** (the spec changed here) | ~250 (all call-outs into new modules) / ~500 |
| E | **Engine: generalised review lane** | **`engine/_review_launch.py`** (profiles table import from `route_config`; wrapper source with §4 controls; Claude result extraction; not-logged-in refusal); `_verbs_review_request.py` L333-413 replaced by one call (module stays ≤ 500); `_review_package` L89 keeps tier→reviewer, provider from route; route line in package header (`package_digest`); `review.request` gains `route`; `_verbs_review_collect.review_collect` L145 accepts both reviewers, `review_attach` L323 refuses every review-final request made by the new lane (a request carrying `pid`/`provider`) with a diagnostic naming `review collect`; the **only** admission left is a pre-E request still `reviewing` at upgrade (shape: `invocation`, no `pid`) — no flag, no operator skip, no release-long grace (FR-246; §11 E row states the same rule); merge lane: **`app/_engine_review_launch.py`** implementing `review_request` launch + a real `review_collect` (L227 refusal removed), `_engine_review_verdict.review_attach` L16 retired the same way; `plugin_root` L1873 recorded in the header; integration surfaces: `engine/_parser.py:254-263` (no new verbs — `review request/collect` keep their shape), `engine/_engine.py:292-298` binding unchanged, `app/_merge_engine.py:147-151` binds the merge-lane collect, `pyproject.toml` `[tool.importlinter]` contract 3 gains `_review_launch` in the leaf layer and contract 4 gains `_engine_review_launch` among the `_engine_*` layer; `tests/test_repo_conformance` inventory rows for both modules; **`tests/test_review_launch.py`**, **`tests/test_merge_review_collect.py`**; `test_revision10_review_transport.py` extended (the only non-grandfathered lane test); **declares the new `review cancel` verb** (parser, dispatch, `Engine` binding AND the `MergeEngine` binding in `app/_merge_engine.py` with its body in `app/_engine_review_launch.py`, since shared review dispatch selects `MergeEngine` for merge chains; contract-3 and contract-4 layers, inventory, §11 row, tests on both lanes) and **amends FR-246** to §4's process-group design (the `setsid` wrapper as group leader, TERM then KILL to its whole group, the wrapper's identity recorded before the reviewer starts, attempt-keyed collect with `launching`, `abandoned`, `wrapper-lost` and `stale`, the `/2` record's `child_pgid` replaced by `pgid` and `attempt`, cancellation with its group-ownership proof, the two accepted tradeoffs stated; the fd-3 guard, LF release frame, child-sidecar-before-release ordering and exit-97 paths removed) in the same candidate, removing FR-246's deferral marker. **Policy task E0 opens E's run and lands first** (operator ruling 2026-09-27): `reviewer-routing` gains `scripts/forge/route_config.py` and `scripts/forge/route_vocab.py` in every pinned copy — the spec's trigger table (L282), `forge-project.md`, `system/template/forge-project.md`, `REVIEWER_EVAL_TRIGGER_TABLE` in `scripts/forge/forge_cli/policy.py`, the `AGENTS.md` mirror and the tests that pin them — and absorbs bead forge-plugin-9a5k (`AGENTS.md` region mirrors, the `OPERATIONS.md:354` Gate-1 wording, the Gate-1 cell's unguarded PSI read, `.refactor/type-baseline.json` made control-class); it lands through its own chain before E's engine candidate, while no other chain is mid-flight, with fresh-reviewer-evals run under base-revision code (bead forge-plugin-rre3 precedent) | FR-216, FR-246 (amended here), FR-052; E0: the reviewer-facing trigger table | **hard** · `engine/**` is a `reviewer-routing` **and** `model-provider-version` trigger → fresh evals per generation (~15 min); review-final; operator approval; E0 **hard** (`docs/specs/**`, `forge-project.md`) · STRICT evals · fresh evals (the spec is a `model-provider-version` trigger; run under base-revision code) · review-final · operator approval | ~700 / ~900 |
| I | **Typed launches: implementer & plan** | `cli.py launch --role implementer\|plan --run-id --task …` (new engine verb in **`engine/_verbs_launch.py`**; registered in `engine/_parser.py`, dispatched from `app/_dispatch.py:48-104` beside `review`, bound as an `Engine` method at `engine/_engine.py:292-298`, added to contract 3's `_verbs_*` layer in `pyproject.toml`, exported through `forge_cli.app.__all__` if the other verbs are, and inventoried in `test_repo_conformance`): resolves the route, emits the profile argv, writes prompt/brief, writes a durable `launch.json` marker (wrapper PID/PGID/birth identity, argv digest, prompt digest, route sha, requested_at) and appends `execution-start` with the route fields and `launch_marker` naming it, launches detached with the §4 wrapper, and `launch collect` binds to that marker to record the Claude `observed_model` and the terminal `execution_result`; role bodies and prompts come from B; `skills/init/SKILL.md` step 5 becomes: `python3 scripts/forge/route_config.py init` (writes the commented seed once, idempotent `info/exclude` append; a consumer without a Forge init run invokes the same command by hand — documented in the seed header and the release notes) then `route_config.py probe`; init's re-init path re-runs `init` and refuses to overwrite an existing file; tests cover fresh init, re-init, and the manual command; **`tests/test_launch_verb.py`**; **declares the new `launch cancel` verb** (same registration set as E's `review cancel`) and removes FR-245's deferral marker as the last of B/E/I | FR-030/FR-034 (verb replaces prose), FR-031/FR-033 unchanged, FR-245 (marker removed), init skill step 5 | **hard** · `engine/**` trigger → fresh evals; review-final; operator approval | ~400 / ~600 |
| P | **Prose** | `skills/orchestrate/SKILL.md` (role table with `plan` row and per-provider sandbox; launch blocks replaced by the `launch` verb), `references/{review,monitoring}.md`, `skills/commit/SKILL.md` (Step 4 hard → `review request` + `review collect`, no spawn), `skills/worktree-merge/SKILL.md` (Gate 3 the same), `skills/init/SKILL.md` (step 5 probe; FR-083 review-final via the lane); `UPSTREAM:90`; `docs/design/0003-forge-cli-plumbing.md:271, 804-805`; `docs/design/0001-founding-decisions.md:56-60` footnote (cross-model separation becomes recorded, decision 12); `agents/review-final.md` frontmatter note | FR-111 wording | **hard** · STRICT evals · `skills/commit/SKILL.md` is a `commit-review-prompt` trigger → fresh evals; review-final · **operator approval** | ~200 / conformance tests |
| R | **Release 0.7.0** | `CHANGELOG.md` `[Unreleased]` → `[0.7.0]`; `.claude-plugin/plugin.json`, marketplace version; release notes naming: refused legacy spellings (from V's notes), `routes.toml` opt-in, `review attach` retirement, consumer version floor; in-channel post after the `AGREED:` restatement is ratified and posted (rule 5, rule 8) | — | control (`.claude-plugin/**`) · review-final · operator approval | small |
| G | **GH#13 re-analysis** | after R ships: what of GH#13 remains (AGENTS.md/CLAUDE.md contradiction detector; drift-MINOR-on-absent-region); close or re-scope the issue and bead `eki`; `68r` closes with V (alias comparison by family) | — | docs / beads | — |

**Every code chain's scope includes `CHANGELOG.md`** (the changelog gate requires a staged `[Unreleased]` entry for any candidate touching python/bash/config/control; only the docs-only chains 0, 0.5 and G are exempt). Sizes are the record's 8.4.6 estimate re-cut for eight profiles and the merge-lane collect; a
fresh estimate is owed at each chain's run-open. **Every named test module is a family, not one
file**: the 500-code-line guard covers `tests/**`, so a ~600-line test scope is two or more modules
(e.g. `test_review_launch_codex.py` / `test_review_launch_claude.py` / `test_review_launch_controls.py`),
each under 500 lines, planned as such at run-open. Everything new lives in new modules; `builders.py`,
`journal.py`, `fresh_evals.py`, `_verbs_review_request.py` take call-outs only (decision 13; CLAUDE.md
forbids new per-file-ignores). No hook, no `install.sh` change, no gitignore-block change, no chain
state-key change (`route` lives under the existing `review.request` and `run_started` keys).

## 6. Sequencing and dependencies

```
0 probes ──┐
0.5 AGREED draft (terminal) ──┐
V1 readers ─► R1 0.6.13 ─► V2 writers ─► R2 0.6.14 ─► S spec rev 15 ─► B role bodies ─► L leaf ─► J journal ─► E0 trigger rows + 9a5k ─► E engine ─► I launches ─► P prose ─► R 0.7.0 ─► G GH#13
                                                                          (J resolves through L's route_config.load; E needs J's snapshot; L's probe and E's Claude reviewer read B's bodies; E0 is the policy task that opens E's run)
```

- **Vocabulary ships in two patch releases**: V1/R1 (0.6.13) makes every reader accept canonical
  ids while writers are unchanged, so a consumer on 0.6.13 reads 0.6.14 records and a rollback from
  0.6.14 is non-fatal; V2/R2 (0.6.14) switches the writers and refuses legacy spellings, carrying the
  consumer-impact statement. V2 cannot be split further (FR-019 L748: every writer surface in the
  same candidate). Downgrade below 0.6.13 after 0.6.14 records exist is not supported and is said so
  in R2's notes.
- S before any code that the spec must authorise (project trigger: `docs/specs/**` → STRICT evals +
  binding review + operator approval). S can be drafted while V is in review.
- B (role bodies) precedes L so `route_config.py probe` and E's Claude reviewer exercise their real
  bodies, not placeholders.
- **J depends on L** (`run_open` freezes the route through L's `route_config.load`, called from `route_evidence.resolve_snapshot` in `c35af17`); L then J, not
  parallel worktrees; E depends on both (profiles from L, snapshot from J).
- **E0 lands first inside E's run** (operator ruling 2026-09-27): the `reviewer-routing` rows for
  `scripts/forge/route_config.py` and `scripts/forge/route_vocab.py` that S planned but never landed, plus bead
  forge-plugin-9a5k, as one hard policy chain before E's engine candidate. It changes committed policy, so it lands only
  while no other chain is mid-flight (Revision 17's `forge-project.md` change forced J's first commit chain,
  `c-2026-09-25T111248Z-dbfe`, to abort: a chain cannot commit-rebase across a policy change), and its
  fresh-reviewer-evals run from a checkout at the chain's base revision (bead forge-plugin-rre3), because a candidate that
  changes the trigger table cannot parse the base policy under its own code.
- I depends on E (shares the wrapper) and on B's bodies. Between J and P the session still launches
  by prose (orchestrate references, unchanged), which J admits without route fields (`route_source:
  unrecorded`); the refusal for missing route fields arrives with I's `launch` verb and P's prose.
- P last among code chains: prose must describe verbs that exist.
- Version proposal (operator confirms at each release chain): V1 = **0.6.13**, V2 = **0.6.14**; S…P = **0.7.0**; `8mf`'s guard/hook
  epic moves to **0.8.0**; `b0b` after that. This is the "routing first" decision applied to the
  release ladder — the other beads' order is re-adjusted by the operator once V2 is out.

## 7. Verification strategy (per chain, from the project's completeness items)

1. Every changed control has a test that fails when the control is disabled in memory: route file
   ownership checks; snapshot divergence refusal; wrapper timeout / cap / stream validation; legacy
   spelling refusal on new writes; `review attach` refusal for review-final; `is_non_mutating`
   classification; task-completion provenance refusal at `task-finish` and `run-close`.
2. Routing and the executable inventory conform: `tests.test_repo_conformance` extended for the plan
   row, the eight profiles, `route_vocab.py` / `route_config.py` in §5 inventory.
3. Full unittest discovery through the Gate 1 cell on the final candidate and again inside the merge lock — once per
   candidate since Revision 17 (`7ff9ad6`: a work queue over min(8, cpu) workers under the host gate slot).
4. STRICT evals plus binding review-final and candidate-bound operator approval for every control-class
   chain (all code chains here are control-class); **fresh reviewer evals** for V2, B, E0, E, I, P (trigger
   paths) and for every chain that edits `docs/specs/forge-plugin-spec.md` (a `model-provider-version` trigger) — plan ~15 minutes per generation and a skip only by operator-terminal direction.
5. Rollback and live corpus: a fixture of 0.6.14-shaped records is read by the V1 readers without a
   fatal (the two-step's reason for existing); the live-corpus fixture: the 19 dogfood journals (153 executions) must normalise, archive and drift
   without a fatal; the three legacy-spelling runs become archivable (bead value on its own).
6. Dogfood: after E, this repository's own commit chains run review-cheap through the new lane;
   after I, the next refactor session's implementer launches through `launch` (the plan says whether
   dogfood uses `codex` or `claude` per role — the developer's `routes.toml`, which is the point).

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Forged same-uid evidence (`routes.toml`, completion records, `observed_model`) | stated evidence classes in every record (8.4.5); coordination evidence, never authentication; a deleted or bad file refuses, never reads as `matched` |
| Claude OS sandbox fails open without `socat` | ruled instruction-bounded (11.4.4); `sandbox` field makes it legible; probe 0 measures the `bwrap`+`socat` path for a later opt-in |
| Vocabulary release refuses a peer's routine spellings at first `execution-start` | 0.6.13 ships readers first and gives one-release notice; 0.6.14 notes and the `AGREED:` restatement; diagnostics name the canonical id; read-side map keeps their archives valid |
| Hidden CLI flags change or disappear | version floor recorded in `route_config.py probe` and FR-245; the launcher refuses below the floor |
| Gateway endpoints (`ANTHROPIC_BASE_URL`, Bedrock/Vertex) | best-effort by ruling (10.3): pass through, record what the stream reports, no comparison rule |
| Eight profiles is a wide review surface | profiles are one table in `route_config.py` + one test matrix; every profile has a probe-0 transcript before the code chain opens |
| Merge-lane `review_collect` is new code on the reintegration path | its own chain (E) with worktree-merge dogfood on the next refactor branch before R |
| `builders.py` / `journal.py` at ceiling | call-outs only; the file-length guard is the blocker, not a warning |

## 9. Open points for the operator (small; defaults stated)

1. Timeouts per profile (§4 defaults 1200 / 3600 / 1200 s) — **confirmed by the operator 2026-09-25**.
2. Claude role-body location: `system/claude/prompts/` (proposed, mirrors `system/codex/prompts/`)
   versus `agents/` — the latter is what Claude Code loads as subagents, which these bodies are not. **Ruled
   `system/claude/prompts/` by the operator 2026-09-24; landed in chain B.**
3. `review attach` retirement: outright for every new request (accepted default); the sole
   admission is a pre-upgrade `invocation`-shaped request still `reviewing` — by shape, not by
   release, so it ends when no such request exists (§11). **Confirmed by the operator 2026-09-25: no flag, no operator
   skip, no grace period.**
4. Whether `plan` executions are admitted in commit chains (a chain-bound planning pass) or runs
   only (proposed: runs only in v1). **Ruled runs-only by the operator 2026-09-24; chain B's bodies say so.**

## 10. Beads to open (after operator review of this plan)

One epic `routing-0.7.0` with children `route-0-probes`, `route-0.5-agreed-draft`, `route-V1-vocab-readers`,
`route-R1-release-0.6.13`, `route-V2-vocab-writers`, `route-R2-release-0.6.14`, `route-S-spec-rev15`, `route-B-role-bodies`, `route-L-route-config`, `route-J-journal-snapshot`,
`route-E-review-lane`, `route-I-launch-verb`, `route-P-prose`, `route-R-release-0.7.0`,
`route-G-gh13-reanalysis`; `--deps` per §6; `eki` and `68r` re-pointed at 0.5 / V1; `dwf1` closes
with this plan's docs chain.

## 11. Compatibility, rollback and in-flight chains (per chain)

Chain state carries `schema` and `policy_source` but no plugin version, so every rule below keys on
**record shape**, never on a version number. Each release chain's notes state its downgrade rule.

| Chain | Persisted shape it changes | Forward (old records on new code) | Backward (new records on old code) | In-flight at upgrade |
|---|---|---|---|---|
| V1 / V2 | journal `execution` values | legacy spellings read through the map | 0.6.13 readers accept canonical ids; below 0.6.13 the canonical ids are fatal to `check_run` — stated as unsupported in R2's notes | none (journal writes are single records) |
| S | spec text only | — | — | — |
| B | prompt files, `config.toml` | — | an older installer ignores unknown `system/` files; `.codex/` pins are per version | — |
| L | `routes.toml` (developer-owned) | absent file = committed default | an older plugin never reads it; the file is inert | — |
| J | `run_started.route`, `execution.{sandbox,route_source,route_sha256}` — all **known-optional** under FR-019 ("unknown keys remain accepted") | absent fields = pre-route run: comparison skipped, nothing written; readers project `route_source: unrecorded` | older readers ignore the unknown keys | a run opened before J has no snapshot: `execution-start` on it records the route with `snapshot: absent` and never refuses; the provenance guard applies only to runs whose `run_started` carries the `route` key (written only from J on) — a durable, record-shaped cutoff; runs opened before J, activated or not, are never provenance-checked at `task-finish` or `run-close` |
| E | `review.request` gains `route`, `provider` and the `attempt` id `collect` binds to; completion record `forge-review-process/2`; the wrapper's identity record in the attempt directory; E0: policy text only | a request without `provider` is a pre-E Codex request: `collect` takes the `/1` path with the wrapper-PID-only probe and says so in its diagnostic | old `collect` refuses a `/2` completion by schema, so a chain finishes on the version that requested its review; new `review request` refuses when the outstanding request's shape is newer than the running code (`forge: review request shape newer than this plugin — finish or abort the chain on the requesting version`) | a `review-final` request recorded with `invocation` (no `pid`) and still `reviewing` at upgrade keeps `review attach` admitted **for that request only**; a new request after E uses the lane. The retirement is by request shape, not by release date, and the grace ends when no such request exists. `review cancel` (bound on both `Engine` and `MergeEngine`) acts only on a request that carries an `attempt` id with a wrapper identity record, so it refuses a pre-E request by shape; E0 lands only while no chain is mid-flight |
| I | `execution` rows written by `launch` (`mode: detached`, route fields) | — | as J | an execution launched by prose before I carries no `launch_marker` and is collected by prose; `launch collect` refuses any execution without a `launch_marker`, or whose marker's wrapper birth identity, argv digest or prompt digest do not match the wrapper's §4 identity record and completion record; on completion it writes the terminal `execution_result` (`complete` on exit 0 with a nonempty handoff, else `failed` with the wrapper error) exactly once — the marker records `collected_at` and a repeat collect is idempotent |
| P | prose only | — | an older cache reading newer prose is the cache-vs-checkout condition already present today | — |
| R | versions | — | — | — |

Reverse-order rollback: releases roll back newest-first (0.7.0 → 0.6.14 → 0.6.13); each step's rule is
the "backward" cell above; a step is safe when no chain is `reviewing` with a newer-shaped request and
no run opened under the newer version is still open (close or retire it first — the workflow's
machine-move rule). In-flight cancellation: `commit abort` / `chain tombstone` for chains, `run-retire`
for runs, the §4 process-group kill for a detached child; the kill itself is not new, while the identity-checked
`review cancel` (E) and `launch cancel` (I) verbs ARE new and are declared in their chains' §5 rows. Each chain's tests include one
"old record on new code" fixture and, where the backward cell is not "ignored", one "new record on
old code" refusal fixture run against the previous module version vendored into the test.

## 12. Carried to run-open plans

Items the commit-chain reviewer raised that belong to a chain's own FR-124 plan rather than to this
breakdown; each is repeated in the owning bead's description so it cannot be lost:

- E: exact wrapper state machine (`setsid` start, identity record before the reviewer starts and the reviewer's identity
  added after it, both stream pumps, caps, timeout, group-kill order with the wrapper's own completion record published
  first), the identity deadline and the exclusive claim between the wrapper's identity publish and `collect`'s
  abandonment, completion-record `/2` field grammar, identity-record grammar, the attempt-keyed `collect` and `stale`
  record, survivor-state diagnostics and the group-ownership proof, the allowlist table and its leak test; E0's exact
  trigger-row text and the list of tests that pin it.
- I: how the `launch.json` marker comes to carry the wrapper PID, PGID and birth identity DM-018 lists for it, now
  that §4 writes the owner record before the spawn and the wrapper publishes its identity itself (read back into the
  marker, or DM-018's `launch_marker` wording amended in I's candidate).
- J: `route_source` enum in the schema table; snapshot comparison rule text; `orchestrator-owned: `
  decision grammar; provenance negative-test matrix; `orchestrator_model` transcript reader bounds.
- L: `routes.toml` line grammar (regex set), ownership matrix (`st_uid`, `st_mode & 0o022`, size,
  `S_ISREG`, `O_NOFOLLOW`, tracked/ignored/misplaced checks), `probe` argv per provider.
- S: FR text for every row in §5, the trigger-table rows, and the `sandbox`-per-profile table.
- V1/V2: the complete literal inventory with dispositions (V1 run-open produces it).
