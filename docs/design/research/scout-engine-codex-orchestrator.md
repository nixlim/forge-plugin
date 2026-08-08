# codex-orchestrator recon report (scout-engine, 2026-08-08)

Repo: `upstream/codex-orchestrator` @ `ca0141b` ("Add orchestrator overview to README"), release **0.5.0** ("prompt-first orchestration rewrite", PR #23). 39 files, ~3.9k lines. All paths below are relative to the repo root.

**Top-level layout**
```
.claude-plugin/{plugin.json,marketplace.json}
docs/{orchestration-contract.md,benchmarks.md,assets/}
scripts/codex_orch_tools.py                 # stable entry point invoked by path
scripts/codex_orchestrator/{__init__,cli,journal,events,monitor}.py
skills/{orchestrate,workflow,report}/SKILL.md
skills/orchestrate/references/{monitoring,review,consensus,compute}.md
tests/{test_*.py,fixtures/,replay/long-run-001/}
pyproject.toml  README.md  LICENSE  .gitignore
```
There is **no `commands/` directory** — `tests/test_docs_contract.py:55` actively asserts `list((ROOT / "commands").glob("*.md")) == []` ("skills are not duplicated by command stubs"). There is no CI config, no `.github/`.

---

## 1. Journal schema

### On-disk location

Run root convention (README "Run Layout"; `skills/orchestrate/SKILL.md` "Durable Run"):

```text
.codex-orchestrator/runs/<run-id>/
  journal.jsonl
  <provider>-<role>-<NN>/execution-<NN>/
    prompt.md
    events.jsonl
    handoff.md
  evidence/                 # optional
  report.md                 # after run_closed
```

`<run-id>` is free-form (`"run-20260710-01"` in docs, `"long-run-001"` in the fixture). Agent dirs are named `codex-impl-01`, `codex-review-01` (i.e. `<provider>-<role>-<NN>`); each execution dir is `execution-<NN>`. Journal-declared paths are resolved by `journal.resolve_run_path()`: absolute paths as-is, otherwise relative to the run dir.

The run root is **git-excluded locally**, never via tracked `.gitignore`: the workflow appends `/.codex-orchestrator/` to `$(git rev-parse --git-path info/exclude)` and verifies with `git check-ignore -q .codex-orchestrator/.ignore-check` before creating the run.

### Invariants (docs/orchestration-contract.md §"Journal Entries", lines 29–37)

- One Claude orchestrator owns and appends to `journal.jsonl`; every nonblank line is one JSON object with `recorded_at`.
- Each `agent` + `execution` pair may occur in at most one `execution` and one `execution_result`.
- `verification` and `decision` IDs must each be unique within their entry type.
- Task IDs **intentionally repeat** to record status changes; the latest entry is current.
- On duplicate identity: "retain the journal, stop appending, and start a successor run that references the prior run instead of rewriting history."
- Explicitly: "The fields below are the prompted run protocol, not a complete runtime-enforced schema."

### The seven entry types

Canonical set is duplicated in three places — `scripts/codex_orchestrator/journal.py:6-14` (`JOURNAL_ENTRY_TYPES`), `docs/orchestration-contract.md`, and `tests/test_docs_contract.py:8-16`:

```python
JOURNAL_ENTRY_TYPES = {
    "run_started", "task", "execution", "execution_result",
    "verification", "decision", "run_closed",
}
```

Enum constants (`journal.py:16-18`):
```python
TERMINAL_TASK_STATUSES      = {"complete", "blocked", "failed"}
TERMINAL_EXECUTION_STATUSES = {"complete", "blocked", "failed"}
VERIFICATION_RESULTS        = {"passed", "failed", "inconclusive", "skipped"}
```
Plus `run_closed.judgment ∈ {"passed", "blocked"}` (`journal.py:138`) and `decision.outcome ∈ {consensus, claude_decision, user_action_required}` (documented only — **not** runtime-checked).

#### 1. `run_started` — first entry

Fields: `type`, `run_id`, `goal` (concise original goal), `repo` (absolute target worktree), `repo_head` (full 40-char starting commit), `repo_branch` (**only when HEAD is attached** — omit if detached), `repo_status` (array of exact lines from `git status --short --untracked-files=all`, captured *after* locally excluding the run root and *before* creating it), `plugin_ref`, `claude_version`, `codex_version`, `recorded_at`. "Omit an unavailable version or detached `repo_branch`; do not guess it."

```jsonl
{"type":"run_started","run_id":"run-20260710-01","goal":"Add request validation without changing the public API.","repo":"/work/project","repo_head":"0123456789abcdef0123456789abcdef01234567","repo_branch":"feature/request-validation","repo_status":[],"plugin_ref":"git:abc1234","claude_version":"2.1.0","codex_version":"0.110.0","recorded_at":"2026-07-10T12:00:00Z"}
```

#### 2. `task` — repeatable per id

Fields: `type`, `id`, `status` ∈ `pending|active|complete|blocked|failed`, `goal`, `acceptance` (array of criteria strings), `files` (allowed/owned paths or globs — required on active tasks before parallel execution; parallel tasks must have disjoint ownership or isolated worktrees), `recorded_at`. Note `pending` and `active` are documented statuses but **not** in `TERMINAL_TASK_STATUSES`; validation requires the latest status per id to be terminal.

```jsonl
{"type":"task","id":"task-01","status":"active","goal":"Add request validation.","acceptance":["Invalid input is rejected","Relevant tests pass"],"files":["src/api.py","tests/test_api.py"],"recorded_at":"2026-07-10T12:01:00Z"}
```

#### 3. `execution` — appended **before** launch

Identity = `agent` + `execution`. Fields: `type`, `agent`, `execution`, `task`, `provider`, `role`, `mode` (`"headless"`), `event_source` (`"exec"` for Codex CLI stream, `"claude"` for a Claude agent), `model`, `effort`, `session_id` (when known; an execution result may supply it later), `worktree` (absolute), `head` (full SHA), `branch` (when attached), `prompt`, `events` (may be omitted for a Claude agent), `handoff`, `recorded_at`.

```jsonl
{"type":"execution","agent":"codex-impl-01","execution":"execution-01","task":"task-01","provider":"codex","role":"implementation","mode":"headless","event_source":"exec","model":"gpt-5","effort":"high","worktree":"/work/project-codex-impl-01","head":"0123456789abcdef0123456789abcdef01234567","branch":"codex-impl-01","prompt":"codex-impl-01/execution-01/prompt.md","events":"codex-impl-01/execution-01/events.jsonl","handoff":"codex-impl-01/execution-01/handoff.md","recorded_at":"2026-07-10T12:02:00Z"}
```

#### 4. `execution_result`

Fields: `type`, `agent`, `execution`, `task`, `status` ∈ `complete|blocked|failed`, `session_id`, `handoff`, `summary`, `files_changed` (array — "Claude's compact attribution note", explicitly *not* authoritative), `caveats` (array), `recorded_at`. "An execution is in flight until a matching terminal execution result exists. Completed executions require a nonempty handoff. A missing handoff for a blocked or failed execution is reported as a warning and must not be fabricated."

```jsonl
{"type":"execution_result","agent":"codex-impl-01","execution":"execution-01","task":"task-01","status":"complete","session_id":"thread-123","handoff":"codex-impl-01/execution-01/handoff.md","summary":"Implemented validation and tests.","files_changed":["src/api.py","tests/test_api.py"],"caveats":[],"recorded_at":"2026-07-10T12:20:00Z"}
```

#### 5. `verification`

Fields: `type`, `id` (unique), `task`, `criterion`, `method` (`"command"` / `"inspection"` in examples — free-form, not validated), `check` (exact command or inspection), `result` ∈ `passed|failed|inconclusive|skipped`, `observation`, `evidence` (optional array of paths), `recorded_at`. "The agent's `Commands Reported` section is not a verification."

```jsonl
{"type":"verification","id":"check-01","task":"task-01","criterion":"Relevant tests pass","method":"command","check":"python -m pytest tests/test_api.py -q","result":"passed","observation":"12 tests passed; exit code 0.","evidence":["evidence/task-01-tests.txt"],"recorded_at":"2026-07-10T12:25:00Z"}
```

#### 6. `decision`

Fields: `type`, `id` (unique), `task`, `finding`, `outcome` ∈ `consensus|claude_decision|user_action_required`, `resolution`, `basis` (array referencing checks, handoffs, evidence, or repo paths), `risk`, `recorded_at`.

```jsonl
{"type":"decision","id":"decision-01","task":"task-01","finding":"The first implementation accepted whitespace-only names.","outcome":"consensus","resolution":"Reject stripped empty names and retain the regression test.","basis":["check-01","codex-impl-01/execution-02/handoff.md"],"risk":"low","recorded_at":"2026-07-10T12:45:00Z"}
```

#### 7. `run_closed` — final entry

Fields: `type`, `judgment` ∈ `passed|blocked`, `summary`, `validation` (verbatim copy of the pre-close `validate` JSON: `{ok, issues, warnings, non_passing_verifications}`), `risks` (array), `follow_ups` (array), `recorded_at`.

```jsonl
{"type":"run_closed","judgment":"passed","summary":"All acceptance criteria were independently verified.","validation":{"ok":true,"issues":[],"warnings":[],"non_passing_verifications":[]},"risks":[],"follow_ups":[],"recorded_at":"2026-07-10T13:00:00Z"}
```

### Record-authority hierarchy (contract §"Record Authority")

Prompt = assigned scope · Event stream = what the harness emitted · Handoff = agent *claims* · Evidence = inspectable observation · Verification = Claude's evaluation · Decision = Claude's resolution · Journal = Claude's compact chronology · **Repository** = "the final state relative to the recorded starting baseline determines what code was actually delivered."

Key line: *"A handoff can establish that an agent claimed a test passed, and an event stream can establish that the harness emitted that claim. Neither establishes that the test passed against the accepted repository state."*

### Handoff contract (contract lines 131–151)

Every agent prompt requires exactly these six headings, in order:
```markdown
## Status

## Summary

## Files Changed

## Claims / Findings

## Commands Reported

## Caveats / Blockers
```
Codex writes this via `--output-last-message`. "Do not rewrite a handoff into a cleaner summary."

---

## 2. The `validate` tool

**Module:** `scripts/codex_orchestrator/journal.py` → `validate_run(run_dir: Path) -> dict[str, object]` (lines 104–278). CLI wrapper: `cli.command_validate` (`cli.py:84-87`).

**Invocation** — by path, from the workflow skill (`skills/workflow/SKILL.md` step 9):
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" validate \
  .codex-orchestrator/runs/<run-id>
```
Single positional arg `run_dir` ("Run directory containing journal.jsonl"). Subparser help: *"Check prompt-first run structure without making acceptance judgments."*

**Output** — plain JSON on stdout via `json.dumps(payload, sort_keys=True)`, *not* a journal entry:
```json
{
  "ok": true,
  "issues": [],
  "warnings": [],
  "non_passing_verifications": []
}
```
**Exit code:** `0` if `payload["ok"]` else `1`. `ok == not issues` — warnings do not fail it.

**Complete list of checks** (in code order):

| # | Check | Severity |
|---|---|---|
| 1 | Journal file exists (`missing journal: {path}`) | issue |
| 2 | Each line parses as JSON (`line N: invalid JSON: {msg}`); UTF-8 decode errors → `could not read journal: …` | issue |
| 3 | Each entry is a JSON **object** (`line N: journal entry must be an object`) | issue |
| 4 | `type` is one of the seven (`line N: unknown journal entry type: {kind!r}`) | issue |
| 5 | Exactly one `run_started`, and it is the **first** record | issue |
| 6 | At most one `run_closed`, and it is the **final** record | issue |
| 7 | `run_closed.judgment ∈ {passed, blocked}` | issue |
| 8 | Duplicate `verification` / `decision` `id` | issue |
| 9 | `task.id` non-empty string | issue |
| 10 | Duplicate `execution` identity (`agent`+`execution`); missing agent/execution | issue |
| 11 | `execution.prompt` and `execution.events` — if the key is present it must name a string, and the resolved file must exist | issue |
| 12 | `execution_result.status ∈ {complete, blocked, failed}` | issue |
| 13 | Duplicate `execution_result` for the same identity; missing agent/execution | issue |
| 14 | `verification.result ∈ {passed, failed, inconclusive, skipped}` | issue |
| 15 | `verification.evidence` must be a list; each item a non-empty string naming an existing file | issue |
| 16 | Latest status per task id ∈ `{complete, blocked, failed}` (`task {id} is not terminal; latest status is {status!r}`) | issue |
| 17 | `task` references on `execution`/`execution_result`/`verification`/`decision` must be strings naming a recorded task | issue |
| 18 | Every `execution` has a terminal `execution_result` | issue |
| 19 | `execution_result.task` matches `execution.task` when both recorded | issue |
| 20 | `execution` line number < `execution_result` line number (ordering) | issue |
| 21 | Handoff present and **nonempty** (`st_size > 0`), taking `handoff` from execution and/or result | **issue if result.status == "complete", else warning** |
| 22 | `execution_result` referencing an unknown `execution` | issue |
| 23 | Every non-`passed` verification is copied into `non_passing_verifications` (subset of keys `id, task, criterion, result, check, observation` that are present) | descriptive, non-failing |

**Explicit non-goals** (contract lines 188–191): "Validation does not enforce every documented field, confine paths, resolve decision bases, match reruns, clear failures, infer consensus, verify process provenance, or decide acceptance." It is called "a small omission check, not truth or acceptance validation." Sparse entries like `{"type":"run_started"}` with no other fields **pass** (`tests/test_validation.py::test_sparse_open_run_is_ready_to_close_and_cli_exits_zero`).

---

## 3. CLI surface

`scripts/codex_orchestrator/cli.py`. Parser description: *"Inspect managed Codex exec streams and validate orchestration runs."* Subcommand is required (`dest="command", required=True`). **Three subcommands: `state`, `monitor`, `validate`.**

> Note: there is **no `codex_orchestrator` console-script entry point**. The only entry is `scripts/codex_orch_tools.py`, whose docstring says: *"Invoked by path from the plugin skills, so this stable entry point remains in `scripts/`. Command coordination lives in `codex_orchestrator.cli`."* It does `from codex_orchestrator.cli import main` (relies on the script's own directory being on `sys.path`), and `raise SystemExit(main())`.

### `state <thread_id> [--json] [--file PATH] [--dump-event-types]`
Help: "Classify a Codex agent state." `--file` = "Managed Codex exec JSONL path."; `--json` = "Emit machine-readable JSON."; `--dump-event-types` = "Print observed event types."

Output payloads:
- normal: `{thread_id, source:"exec", path, status, details, compatibility}` → exit `0`
- `--dump-event-types`: `{thread_id, source:"exec", path, event_types:{<type>:count}, compatibility}` → exit `2` if `parse_confidence == "low"` else `0`
- low confidence: `{…, status:"unknown", compatibility}` on stdout **plus** the `incompatible_message()` on **stderr** → exit `2`
- missing/non-file `--file` (or omitted): `{type:"state_error", thread_id, path, message:"event stream does not exist or is not a file"}` → exit `1`; read error → `"could not read event stream: {exc}"` → exit `1`

`details` includes only present keys: `usage`, `error`, `thread_id`, `last_agent_message`.
`status` values: `idle | starting | active | complete | failed | unknown`.
Without `--json` the payload is printed as a raw Python dict (`print(payload)`) — the skills always pass `--json`.

### `monitor [--run-id ID] [--repo PATH] [--log PATH ...] [--once] [--stale-seconds N] [--poll-interval S] [--fail-on-agent-failure]`
Help: "Watch in-flight agent event streams from the prompt-first run layout."
- `--run-id` = "Run id under .codex-orchestrator/runs."; `--repo` = "Repository root paired with --run-id."
- `--log` = "Explicit managed exec stream path. Repeatable." (`action="append"`)
- `--once` = "Scan once and exit."
- `--stale-seconds` int, **default 600** = "Emit stale after this many idle seconds."
- `--poll-interval` float, **default 30.0** = "Seconds between watch scans."
- `--fail-on-agent-failure` = "Exit nonzero when a watched agent fails."

### `validate <run_dir>`
See §2.

---

## 4. Monitor + events

### `events.py` — stream parsing

`PARSER_VERSION = "0.1.0"`. Recognized Codex exec event types (`EXEC_EVENT_TYPES`):
```python
{"thread.started","turn.started","turn.completed","turn.failed",
 "item.started","item.updated","item.completed","error"}
```

`summarize_stream(path)` reads line-by-line via `readline()` into a `StreamSummary` dataclass (`status`, `event_counts: Counter`, `known_count`, `parse_errors`, `unknown_event_types: set`, `thread_id`, `usage`, `error`, `last_agent_message`, `terminal`). Memory is O(distinct types) — `tests/test_tools.py::test_stream_summary_memory_does_not_scale_with_event_count` asserts peak < 2 MB over 50 000 events.

State transitions in `StreamSummary.consume()`:
- `thread.started` → `status="starting"`, captures `thread_id`, **resets** usage/error/last_agent_message/terminal
- `turn.started` → `active`
- `turn.completed` → `complete`, `usage = event["usage"]`, `terminal = record`
- `turn.failed` → `failed`, `error = event["error"]`
- `error` (and *not* a reconnect notice) → `failed`, `error = event.get("error") or event.get("message")`
- `item.completed` with `item.type == "agent_message"` → `last_agent_message = item["text"]`
- Later events supersede earlier ones (a `turn.started` after a `turn.completed` yields `active`).

Parse-robustness details:
- `decode_event_line()` maps unparseable lines to synthetic types `"<invalid-json>"` (JSONDecodeError / invalid UTF-8) and `"<non-object>"`; missing `type` → `"<missing>"`. Both synthetic types increment `parse_errors`.
- An **unterminated final line** (no trailing `\n`) that fails to parse is treated as a partial write and **skipped** (`break`); if status was still `idle` it becomes `starting`. A *complete* unterminated final line is consumed normally.
- `is_reconnect_notice()`: an `error` event whose JSON dump lowercased contains `"reconnecting"` is counted as known and does **not** fail the agent (fixture: `{"type":"error","message":"Reconnecting... 1/3"}`).

`compatibility(summary)` → `{parser_version, parse_confidence, unknown_event_types (sorted), warnings}`. `parse_confidence = "low"` iff `event_count > 0 and unknown_count > known_count` (strict majority unknown), else `"high"`. `warnings = ["no events found"]` when the stream is empty.

`incompatible_message()`:
> `ERROR: Codex exec JSONL appears incompatible (parser 0.1.0). Run state --dump-event-types and update the parser. Do not infer agent status.`

### `monitor.py` — target discovery and notifications

**How event files are discovered.** Two mutually exclusive selectors, enforced by `resolve_monitor_targets()`: `selectors = bool(args.log) + bool(args.run_id or args.repo)` must equal exactly 1, else
`{"type":"monitor_error","message":"provide exactly one target: --repo with --run-id or one or more --log paths"}` → exit 1. `--repo`/`--run-id` must be given together. Run dir is composed as `Path(repo) / ".codex-orchestrator" / "runs" / run_id`.

`inflight_targets(run_dir)` reads `journal.jsonl` with `allow_partial_final_line=True`, builds the set of identities that already have a terminal `execution_result`, then yields a `MonitorTarget(path, agent, execution)` for every `execution` entry that is **not** completed, **skipping** `event_source == "claude"`. Errors (emitted as `monitor_error` payloads, and any error aborts with exit 1):
- run dir missing / not a directory
- any journal read issue → `"could not read run journal: {issues}"`
- `execution entry is missing agent or execution`
- `execution <a>/<e> has no events file` (missing/empty `events`)
- `execution <a>/<e> uses unsupported event source; only managed exec streams are supported` (anything other than `None` or `"exec"`)
- `execution <a>/<e> has an invalid events path: {exc}`

**Notification payloads** (`emit_monitor` → one compact sorted JSON line per event, flushed). Base shape from `monitor_payload()`: `{type, path, source:"exec", thread_id, mtime}` plus `agent`/`execution` when known; `parse_errors` added when nonzero.

| `type` | Emitted when | Extra fields |
|---|---|---|
| `codex_agent_complete` | summary status `complete` with a terminal record | `usage` |
| `codex_agent_failed` | status `failed` | `error` (from `turn.failed`) or `message` (from `error`, via `event_text()`) |
| `codex_agent_unknown` | `parse_confidence == "low"` | `compatibility` |
| `codex_agent_stale` | see below | `idle_seconds` |
| `monitor_error` | any of the above errors, or stream missing / not a file / unreadable | `path`, `message` |

**Stale detection.** After ruling out low confidence and a terminal event: `idle_seconds = int(time.time() - path.stat().st_mtime)`; if `stale_seconds >= 0 and idle_seconds >= stale_seconds` → emit `codex_agent_stale`. Staleness is therefore purely **file-mtime based**, not stream-content based, and a negative `--stale-seconds` disables it. `thread_id` falls back to `"unknown"` when the stream has no `thread.started`.

**Loop semantics** (`command_monitor`): each pass re-resolves targets (so newly appended `execution` entries are picked up), scans only targets not yet in `done`, and marks a target `done` on any outcome ≠ `"active"`. `--once` scans once; otherwise it sleeps `max(0.1, poll_interval)` and repeats until all targets are done.
**Exit codes:** `2` if any `unknown` was seen; `1` if `failed` was seen **and** `--fail-on-agent-failure`; `1` immediately on any `error`; else `0`. No targets at all → `0`.

**Known failure modes / sharp edges** (from `tests/test_monitor.py`, 500 lines, 19 tests):
- A **stale** or **unknown** outcome marks the target done — the monitor will not resume watching it even if the agent later writes more events (`test_stale_stream_is_reported`, `test_low_parser_confidence_is_terminal`).
- A journal whose final line is a partial write is tolerated *only while unterminated*; once the newline lands, a malformed line becomes a hard error (`test_partial_final_journal_line_is_ignored_only_while_unterminated`).
- A replaced/recreated stream mid-watch is handled (`test_watch_mode_handles_a_replaced_stream`).
- A journal-declared events path that is a directory, missing, or invalid → `monitor_error` + exit 1.
- Non-`exec` event sources are rejected outright (`test_non_exec_journal_stream_is_rejected`).
- Silence is explicitly declared ambiguous by the docs: *"Treat silence and staleness as ambiguous; inspect the handoff and repository before appending `execution_result`."*

---

## 5. Skills

All three are plain `SKILL.md` files with two-key frontmatter (`name`, `description`) — no `allowed-tools`, no `argument-hint`. Names are namespaced with the plugin name.

### `skills/orchestrate/SKILL.md` (68 lines)
```yaml
name: codex-orchestrator-orchestrate
description: Run a focused Codex-agent execution, monitoring, review, or verification phase.
```
Title "Claude-Codex Orchestration". Scope: **one focused agent cycle** inside a run; the workflow skill owns planning/init/decomposition/closure/reporting. "Prefer Codex as the first mover for bounded coding tasks."

**Focused Agent Cycle (10 steps):** 1 read complete journal + current task + references → 2 confirm acceptance criteria and owned `files` → 3 compare active task files/shared resources, serialize overlap or use a worktree → 4 reuse a relevant agent or create a named one (independent review ⇒ fresh agent + fresh native session) → 5 resolve absolute `worktree`, full HEAD, attached branch; **save the exact prompt and append `execution` before launch** → 6 monitor with the bundled tools without editing files owned by the active agent → 7 save the exact handoff, inspect it and the repo, append terminal `execution_result` → 8 record material checks as `verification` → 9 record only consequential resolutions as `decision` → 10 append `complete` / `failed` / `blocked`, otherwise keep the task `active` and return unresolved work to the workflow.

Reference map (read only what the phase needs): `references/monitoring.md` (execution capture, CLI monitoring, handoffs), `references/review.md` (verification and independent review), `references/consensus.md` (consensus and decision outcomes), `references/compute.md` (parallel ownership, worktrees, compute gating). It points at `${CLAUDE_PLUGIN_ROOT}/docs/orchestration-contract.md` for journal semantics and — per `test_docs_contract.py:333` — must **not** mention `run_started` or `run_closed` itself.

### `skills/workflow/SKILL.md` (75 lines)
```yaml
name: codex-orchestrator-workflow
description: Run the full Codex orchestration workflow end to end.
```
Owns the lifecycle planning → final report; delegates each focused cycle to `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/SKILL.md`.

**Run Initialization** (verbatim):
```bash
REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"
EXCLUDE_FILE="$(git rev-parse --git-path info/exclude)"
grep -qxF '/.codex-orchestrator/' "$EXCLUDE_FILE" ||
  printf '\n/.codex-orchestrator/\n' >> "$EXCLUDE_FILE"
grep -qxF '/.codex-orchestrator/' "$EXCLUDE_FILE"
git check-ignore -q .codex-orchestrator/.ignore-check
git rev-parse HEAD
git branch --show-current
git status --short --untracked-files=all
```
"Do not create the run unless both exclude checks succeed." Never edit tracked `.gitignore`.

**Full Workflow (11 steps):** 1 inspect repo/user context → 2 run init, create `.codex-orchestrator/runs/<run-id>/journal.jsonl`, append `run_started` → 3 Claude turns the goal into a concrete plan (deliverables, acceptance criteria, risks, verification paths) → 4 optional Codex plan review; for a "consequential or hard-to-reverse design choice", first ask a **fresh** Codex agent to propose an approach from **only the goal, constraints, and acceptance criteria**, then Claude compares "using evidence rather than agent count" → 5 split into active `task` entries with owned `files` → 6 per task use the orchestrate skill (assign **or resume** a Codex agent) → 7 record consequential `decision`s; terminal `task` only after criteria evaluated → 8 re-read the journal and inspect final repo state + diff → 9 run `validate` (command in §2) → 10 resolve omissions by **appending only**; never rewrite history; on unfixable structural conflict start a successor run; else append one final `run_closed` → 11 invoke `${CLAUDE_PLUGIN_ROOT}/skills/report/SKILL.md` once.

Canonical close sequence, asserted by `test_docs_contract.py:58` to appear **only** in this file: **`validate → run_closed → report.md`**.

### `skills/report/SKILL.md` (124 lines)
```yaml
name: codex-orchestrator-report
description: Author the final report from a completed orchestration run after its descriptive close check.
```
**Preconditions:** `run_closed.validation` holds the complete validation result; every execution has a terminal result and every task is terminal; `run_closed` is the final entry and carries `judgment: passed|blocked`; no further work planned. "Never edit the journal merely to make the report look complete."

Claim→source mapping: actual delivery ← final repo state vs the `run_started` baseline; Claude's checks ← verification observations + evidence; assigned scope ← exact prompts; agent claims ← exact handoffs; chronology ← journal entries; ambiguous process activity ← raw events; decisions/judgment ← decision + `run_closed`.

**Required `report.md` structure — exactly these five `##` sections, in order, no others:**
```markdown
# Report

## Summary

## Changes

## Orchestration Graph

## Consensus

## Final Results
```
`Final Results` contains exactly two `###` subsections in order: `### Gate Result`, `### Risks / Follow-ups` (write `None recorded.` when nothing remains), and ends with one compact `Run metadata` bullet carrying the Claude Code and Codex CLI versions from `run_started`. "Do not add protocol/schema versions or a Reproducibility section."

`Orchestration Graph` = a Mermaid `flowchart TD` with root node `A_CLAUDE{{"Claude Code<br/>planner · orchestrator"}}`, separate non-empty Claude-agent and Codex-agent subgraphs, one node per named agent ordered by first execution (resumed executions combined into that agent's node, with task/model/effort/result/terminal status). Allowed edge labels: `assign`, `review`, `verified`, `resolution`, `consensus`, `claude_decision`, `produced`, `fix required`, `recheck`, `accepted`. Reconstructed facts marked `inferred`; "never infer verification results, decision outcomes, judgments, or terminal status."

### Exact `codex exec` command patterns (`skills/orchestrate/references/monitoring.md`)

Pre-launch git capture, from the same path passed to `-C`:
```bash
git -C <worktree> rev-parse --show-toplevel
git -C <worktree> rev-parse HEAD
git -C <worktree> branch --show-current
```

**Fresh headless execution:**
```bash
EXECUTION_DIR=".codex-orchestrator/runs/<run-id>/codex-impl-01/execution-01"
codex exec --json --output-last-message "$EXECUTION_DIR/handoff.md" \
  -s workspace-write -c approval_policy=never -C <worktree> \
  - \
  < "$EXECUTION_DIR/prompt.md" \
  > "$EXECUTION_DIR/events.jsonl"
```
Constraints: **"Never use `--ephemeral`."** Broad access only with explicit authorization and isolation. Prompt is fed on **stdin** via the bare `-` argument; stdout is the event stream; the handoff comes from `--output-last-message`. "Extract the last completed agent message from events only when normal handoff capture failed."

**Independent review** (`references/review.md`) — plain `codex exec`, *not* the `review` subcommand:
```bash
EXECUTION_DIR=".codex-orchestrator/runs/<run-id>/codex-review-01/execution-01"
codex exec -C <worktree> -s workspace-write -c approval_policy=never --json \
  --output-last-message "$EXECUTION_DIR/handoff.md" \
  - \
  < "$EXECUTION_DIR/prompt.md" \
  > "$EXECUTION_DIR/events.jsonl"
```
Rationale quoted: *"the Codex CLI does not accept a stdin review prompt together with the `review` subcommand's revision selectors."* Write the exact commit SHA into `prompt.md`. Reviewer gets goal + acceptance criteria + constraints + exact target, and must **not** receive "the implementer handoff, claimed test results, earlier review verdicts, or Claude's tentative conclusion." Never resume the implementation session for review. `workspace-write` is retained so repository checks can create normal temporary outputs; confirm the review worktree is clean afterward.

**Monitoring invocations from the skill:**
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" state <session-id> \
  --file <events-jsonl> --json

python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" monitor \
  --repo <repo> --run-id <run-id>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" monitor \
  --log <events-jsonl> --fail-on-agent-failure
```
"After context loss, call `state` again. Do not persist parser positions in the journal."

**Worktrees / compute** (`references/compute.md`): `git worktree add ../<repo>-codex-impl-01 -b codex-impl-01`; do not integrate or remove a worktree until the execution stopped, the handoff is saved, and Claude inspected the diff; after integrating, rerun the affected acceptance checks in the target before marking complete. GPU gating: `nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader` and `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader`.

---

## 6. Plugin packaging

**`.claude-plugin/plugin.json`** (verbatim): `name: "codex-orchestrator"`, `description: "Coordinate reusable monitored OpenAI Codex agents from Claude Code."`, `version: "0.5.0"`, `author: {name: "alexzh3"}`, `license: "MIT"`, `homepage: "https://github.com/alexzh3/codex-orchestrator"`, `keywords: ["codex","orchestration","claude-code","code-review","workflow"]`. **No `commands`, `skills`, `hooks`, or `mcpServers` keys** — skills are discovered by convention from `skills/`.

**`.claude-plugin/marketplace.json`**: `name: "codex-orchestrator"`, `description: "Claude Code plugin for coordinating reusable monitored OpenAI Codex agents."`, `owner: {name: "alexzh3"}`, `plugins: [{name: "codex-orchestrator", source: "./", description: "...", version: "0.5.0", author: {name: "alexzh3"}}]`.

Install path (README): `/plugin marketplace add alexzh3/codex-orchestrator` → `/plugin install codex-orchestrator@codex-orchestrator` → `/reload-plugins`. Skill invocations surface as `/codex-orchestrator:orchestrate`, `/codex-orchestrator:workflow`, `/codex-orchestrator:report`.

**`pyproject.toml`** — 17 lines, first line load-bearing:
```toml
# Dev-tooling config only; NOT a package/build manifest - plugin runs via bare python3 <path>.

[project]
name = "codex-orchestrator"
version = "0.5.0"
description = "Coordinate reusable monitored OpenAI Codex agents from Claude Code."
readme = "README.md"
requires-python = ">=3.10"
license = "MIT"
authors = [{ name = "alexzh3" }]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```
**No `[build-system]`, no `dependencies`, no `[project.scripts]` / entry points.** Runtime dependency set is the **stdlib only** (`argparse, json, pathlib, subprocess, time, dataclasses, collections.Counter`). Python **≥ 3.10** (uses `X | None` unions and `Counter.total()`). Requirements per README: Claude Code, OpenAI Codex CLI, Python 3.10+, a Git repository, and "a meaningful verification path such as tests, typecheck, lint, build, benchmark, screenshot, or manual inspection."

`.gitignore`: `.codex-orchestrator/`, `.claude/settings.local.json`, `.pytest_cache/`, `.ruff_cache/`, `.venv/`, `__pycache__/`, `*.pyc`, `.env`, `uv.lock`.

---

## 7. Test suite

**Framework:** `unittest` only (stdlib) — every module ends with `if __name__ == "__main__": unittest.main()`. No pytest dependency, no conftest, no CI workflow. Convention: `ROOT = Path(__file__).resolve().parents[1]`; CLI-level tests shell out with `subprocess.run([sys.executable, str(SCRIPT), ...], cwd=ROOT, text=True, capture_output=True)` against `scripts/codex_orch_tools.py`; unit-level tests import `from scripts.codex_orchestrator.journal import validate_run` (run from ROOT, implicit namespace packages, no installed package). `tests/test_monitor.py` uses `timeout=5` on every subprocess. Fixtures are built in `tempfile.TemporaryDirectory()`.

| Module | Lines | What it verifies |
|---|---:|---|
| `tests/test_version.py` | 30 | `plugin.json.version`, `marketplace.json.plugins[0].version`, and `pyproject.toml` `version` all equal `EXPECTED_VERSION = "0.5.0"`. |
| `tests/test_tools.py` | 193 | The `state` subcommand end-to-end: partial/unterminated final events, complete/failed/starting classification, reconnect-vs-real-error, later activity superseding an earlier completion, unknown format → exit 2 + stderr, `--dump-event-types`, missing `--file` → exit 1, and O(1) memory over 50 000 events. |
| `tests/test_validation.py` | 393 | 15 tests over `validate_run` + the `validate` CLI: sparse runs pass, unreadable/unknown types, invalid UTF-8 and NUL/unresolvable paths reported not raised, lifecycle marker rules, terminal task status, execution↔result pairing/order/task-mismatch, declared-file and handoff severity split (issue vs warning), non-passing verifications stay visible without failing structure, duplicate verification/decision ids, evidence list-item errors, and that sparse optional metadata is *not* schema-checked. |
| `tests/test_monitor.py` | 500 | 19 tests over `monitor` (see §4). |
| `tests/test_docs_contract.py` | 420 | 24 tests treating the prose as a contract: no `commands/*.md` stubs; the close sequence string lives only in the workflow skill; README diagram + usage example; journal-is-not-evidence framing; run init with git baseline and local exclude; execution records worktree/ref before launch; resumed agent uses the next execution dir; uniqueness + successor-run guidance matches runtime; benchmark tag wording; validation documented as an omission check; review context isolation; plain `codex exec` with an exact-SHA prompt; consensus by evidence not agent count; GPU gating commands; task outcome definitions; worktree re-verification in the target; replay dir documented as a generated scaffold; risk-scaled review effort; skill ownership split; absence of removed `event_source: "ide"` / `mode: "observe"` / `codex://threads/` workflows; no `$CODEX` override; and that **only ` ```jsonl ` fences** contain journal examples and each such line parses as exactly one entry. |
| `tests/test_report_skill.py` | 66 | The report skill contains the exact 5-section template, `### Gate Result` / `### Risks / Follow-ups`, the Mermaid root node string, the closed-and-validated preconditions, claim-specific sources, "create the final `report.md` once", and that the close-sequence phrase is *absent* here. |
| `tests/test_prompt_first_workflow.py` | 230 | The replay integration test — see below. |

**Fixtures** (`tests/fixtures/`), all tiny hand-written JSONL:
- `exec_stream.jsonl` (6 events): `thread.started` (`thread_id: "exec-complete-001"`) → `turn.started` → `item.started` (reasoning) → a reconnect `error` → `item.completed` agent_message `"Implemented the scoped change."` → `turn.completed` with `usage:{input_tokens:120,output_tokens:45}`.
- `exec_failed_stream.jsonl` (4 events): ends `{"type":"turn.failed","error":{"message":"pytest failed"}}`.
- `unknown_format.jsonl` (3 events): `{"kind":"alien.event",...}` — no `type` key, drives `parse_confidence: "low"`.

**Replay fixture `tests/replay/long-run-001/`.** Documented (contract lines 159–162) as *"a checked-in input scaffold, not a standalone valid closed run."* Checked in: `journal.jsonl` (12 entries), `fake_codex.py`, and the two `prompt.md` files. Deliberately **absent** and generated at test time: `events.jsonl`, `handoff.md`, `evidence/unit-tests.txt`, `src/example.py`, `tests/test_example.py` (the test raises `AssertionError` if any pre-exists). `report.md` is never created — the test asserts it does not exist.

The journal covers `run_started` (`run_id: "long-run-001"`, `repo: "/fixture/project"`, 40-char `repo_head`, `repo_branch: "fixture-main"`, `plugin_ref/claude_version/codex_version: "fixture"`) → two active `task`s → `execution`/`execution_result` for `codex-impl-01/execution-01` (`session_id: "fixture-impl"`) and `codex-review-01/execution-01` (`session_id: "fixture-review"`) → two `verification`s (`check-01` command-based with `evidence:["evidence/unit-tests.txt"]`, `check-02` inspection-based) → both tasks `complete` → `run_closed` with `judgment: "passed"`.

`fake_codex.py` is a Codex stand-in accepting only `exec --json --output-last-message PATH`; it reads the prompt from stdin, branches on the literal marker `"# Review assignment"`, writes/validates `src/example.py` + `tests/test_example.py`, runs `python3 -m unittest discover -s tests -p test_example.py -q`, writes the canonical six-heading handoff, and prints four events (`thread.started` with `thread_id` `fixture-impl`/`fixture-review`, `turn.started`, `item.completed` agent_message, `turn.completed` with usage).

`test_prompt_first_workflow.py` asserts, in one `setUpClass`-built temp copy: exactly 2 launches with the expected `(agent, execution)` set; absolute `worktree`, 40-char `head`, non-empty `branch`; both `prompt.md` **and** `handoff.md` carry exactly the six `HANDOFF_HEADINGS` in order; evidence files exist; no `decision` entries; last entry is `run_closed` with `judgment == "passed"`; `state` reports `complete` for both streams with `details.last_agent_message` equal to the handoff text; `monitor --repo … --run-id long-run-001 --once` over a journal truncated to pre-result entries emits exactly 2 `codex_agent_complete` notifications; and `validate` on the finished copy exits 0 with `ok: true`, empty `issues` and empty `non_passing_verifications`.

---

## 8. Resume semantics

There is **no dedicated resume code path** — resume is entirely a prompted protocol, expressed in `skills/orchestrate/references/monitoring.md` (lines 61–75) and pinned by `tests/test_docs_contract.py::test_resumed_agent_uses_the_next_execution_directory`.

```bash
EXECUTION_DIR=".codex-orchestrator/runs/<run-id>/codex-impl-01/execution-02"
codex exec -C <worktree> -s workspace-write -c approval_policy=never \
  resume --json \
  --output-last-message "$EXECUTION_DIR/handoff.md" \
  <session-id> - \
  < "$EXECUTION_DIR/prompt.md" \
  > "$EXECUTION_DIR/events.jsonl"
```
Note the argument order: global flags, then the `resume` subcommand, then `--json`/`--output-last-message`, then `<session-id>` followed by the bare `-` for stdin.

Documented semantics:
- "Resume a relevant idle session as the **next execution under the same agent**" — resuming creates `execution-02`, `execution-03`, … under the *same* agent directory; a **fresh native session requires a new named agent**.
- "Read the absolute `worktree` from the preceding execution and use it with `-C` and the same `session_id`."
- "Inspect its current HEAD and branch and record them in the new execution; **the prior `head` is a snapshot, so do not check out or reset to it merely because the worktree advanced.**"
- "Use an absolute `EXECUTION_DIR` when the shell runs elsewhere."
- Contract line 71: worktree/head/branch are recorded on `execution` precisely "so resume and integration use the same target after context loss."
- `execution.session_id` may be omitted at launch and supplied later by `execution_result.session_id` — that is the id fed back into `codex exec … resume`.
- Review isolation overrides resume: `references/review.md` — "Start a fresh named `codex-review-NN` agent and native session; **never resume the implementation session**." Reuse of a review session is allowed only "for a targeted recheck"; a distinct unresolved question requires a fresh reviewer.
- `skills/report/SKILL.md:83` — in the Orchestration Graph, "combine that agent's resumed executions in its node".

There is **no replay/resume of the orchestrator itself**: after Claude's own context loss the recovery procedure is to re-read `journal.jsonl` and re-run `state` ("After context loss, call `state` again. Do not persist parser positions in the journal.").

---

### Cross-cutting notes for the merge spec

- Every runtime knob is stdlib-only Python invoked as `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" <subcommand>`; there is no importable/installed package and no console script. A merged plugin can keep this "bare path invocation" contract cheaply.
- The seven-type set is triplicated (`journal.py`, contract doc, `test_docs_contract.py`) — adding an eighth type means touching all three plus `test_docs_contract.jsonl_records`.
- The whole design deliberately separates **descriptive omission checking** (`validate`, machine) from **acceptance judgment** (`run_closed.judgment`, Claude). Any move toward validate-enforced gates is a departure from this repo's stated stance ("Validation does not … decide acceptance"), which is worth naming explicitly in the merged spec.
- Documentation is enforced by tests as a contract (24 assertions in `test_docs_contract.py` over README/docs/skills prose), so prose edits in a merge will break tests unless the assertions are migrated.
