---
name: learn
description: Run Forge's advisory journal-derived learning pass after a committed run archive or durable drift report, producing only candidate eval proposals and traceable gotcha appends.
---

# Learn

Run this skill for `/forge:learn`, or as the best-effort post-report pass named by the workflow and
drift skills. Treat the entire learning loop as `advisory`. Run it only after the workflow's
archive-only commit and `report.md`, or after the drift skill has committed its durable report and
finished CRITICAL-block handling. A refusal or failure never changes, blocks, or delays run close,
the report outcome, or the already reported drift outcome.

Before continuing, require the caller to identify which completed lifecycle boundary authorized the
invocation: either the workflow's committed run archive plus completed report, or the drift skill's
committed report plus completed block handling. Refuse when that ordering provenance is absent or
cannot be verified. This is an orchestration precondition, not semantic-review evidence.

## 1. Materialize Exactly Three Inputs

Resolve the target repository and one immutable input snapshot first:

```bash
REPO="$(git rev-parse --show-toplevel)" || exit 1
INPUT_HEAD="$(git -C "$REPO" rev-parse HEAD)" || exit 1
INPUT_DIR="$(mktemp -d)" || exit 1
PATTERNS_FILE="$INPUT_DIR/journal-patterns.json"
ARCHIVES_FILE="$INPUT_DIR/committed-archives.json"
GOTCHAS_FILE="$INPUT_DIR/committed-gotchas.json"
PROPOSALS_FILE="$INPUT_DIR/learn-proposals.json"
```

Materialize the following three evidence inputs as three distinct files. Record `INPUT_HEAD`, each
input file identity, and every source path in the launch assignment so the reviewer can identify
the HEAD and path provenance; Inputs 2 and 3 also embed their committed HEAD/path provenance. The
review constitution and assignment are control instructions, not additional evidence inputs.
Do not attach any other repository content, tool output, prior conversation, or
working-tree file to the reviewer.

### Input 1 — Canonical journal patterns

Use the already captured `journal_patterns` object when this invocation follows `/forge:drift`.
For a post-run invocation, enumerate existing
`.codex-orchestrator/runs/*/journal.jsonl` paths in bytewise path order and pass them as positional
arguments to:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/journal-patterns.py" \
  --repo "$REPO" --revision "$INPUT_HEAD" <ordered-journal-paths...> > "$PATTERNS_FILE"
```

With no journals, pass no positional journal path; the extractor's available empty-corpus result
is still valid. When following drift, write only the literal seven-member `journal_patterns`
object from the validated mechanical summary to `PATTERNS_FILE` in canonical sorted-key JSON.
Validate the exact FR-200 schema and canonical bytes after materializing it. Refuse before any
semantic launch or proposal write unless `journal_patterns.available` is literally `true` and
`failure` is the empty string. Do not reinterpret an unavailable result.

### Input 2 — Committed archive corpus

Enumerate only committed archive paths with:

```bash
git -C "$REPO" ls-tree -r --name-only "$INPUT_HEAD" -- .forge/history/runs/
```

Sort the returned paths by their UTF-8 bytes. For each path shaped
`.forge/history/runs/<run-id>.md`, read the object only with
`git -C "$REPO" show "$INPUT_HEAD:$path"`; never read the worktree copy. Materialize one canonical
JSON array in `ARCHIVES_FILE`. Each element must contain exactly `head`, `path`, and `content`, with
`head` equal to `INPUT_HEAD` and `path` equal to the committed path. Materialize an empty array when
no committed archive exists. Refuse on a malformed path, failed object read, or non-UTF-8 object.

Only an archive whose committed `content` contains one canonical JSON object between the exact
`<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->` and
`<!-- END FORGE LEARNING PROVENANCE v1 -->` delimiters may supply proposal provenance. That object
must expose `decisions` as exact recorded `id`/`task` mappings, `executions` as exact recorded
`agent`/`execution`/`role`/`task`/`prompt`/`prompt_sha256` mappings and
`failed_or_inconclusive_verifications` as exact recorded
`id`/`task`/`result`/`criterion`/`observation` mappings. An older archive without that section remains
review context but cannot earn a candidate or gotcha. Never supplement missing archive provenance by
reading the live journal, the worktree, Input 1, Input 3, or by guessing.

### Input 3 — Current committed gotchas

Test the committed object at `$INPUT_HEAD:.forge/history/gotchas.md`. When present, read it only
with:

```bash
git -C "$REPO" show "$INPUT_HEAD:.forge/history/gotchas.md"
```

Materialize `GOTCHAS_FILE` as a canonical JSON object with exactly `content`, `head`, `path`, and
`present`. Use the exact committed bytes as UTF-8 `content`, the captured `INPUT_HEAD`, path
`.forge/history/gotchas.md`, and `present: true`. When the committed object is absent, materialize
the same object with empty `content`, the same head and path, and `present: false`. This explicit
empty object is still the third input. Never read a working-tree-only gotcha.

## 2. Run One Fresh Periodic Review

Launch one fresh reviewer with read-only tools and the complete
`${CLAUDE_PLUGIN_ROOT}/rules/review-constitution.md` baseline using profile `review-periodic`
version 1.1. Give it exactly `PATTERNS_FILE`, `ARCHIVES_FILE`, and `GOTCHAS_FILE` as its three
separately named evidence inputs. Do not resume a prior reviewer and do not give the reviewer a
repository worktree or mutation tool.

Cluster recurring failures by shape. Give every proposed shape a concise name, identify the exact
journal/archive evidence that supports it, and state which earlier control would have caught it.
Do not infer recurrence from similarity alone when the cited evidence cannot establish it.

For every candidate and gotcha, select one exact archive element as its provenance authority. Copy
`run_id` from that element's `.forge/history/runs/<run-id>.md` path; copy `agent`, `execution`, their
task mapping, and each failed or inconclusive verification identity only from that archive's
`Learning provenance` object; and copy decision IDs only from that same canonical object.
Every cited decision and verification must name the execution's task in that archive. Input 1 and
Input 3 may support clustering and shape naming, but they cannot supply or repair proposal identity.

Require the reviewer to return only one schema-v1 JSON object with exactly integer
`schema_version: 1`, string `input_head`, and `candidates` and `gotchas` arrays. Set `input_head` to
the literal full `INPUT_HEAD` shared by the three committed input materializations; it binds each
proposal's `run_id` to `.forge/history/runs/<run-id>.md` at that exact commit.
Each candidate object has exactly `agent`, `category`, `execution`, `expected`,
`expected_verdict`, `id`, `run_id`, and `scenario`. Each gotcha object has exactly `agent`,
`entries`, `execution`, `line`, and `run_id`:

```json
{
  "candidates": [
    {
      "agent": "<recorded agent>",
      "category": "<fixture category>",
      "execution": "<recorded execution id>",
      "expected": "<expected behavior and the earlier catching control>",
      "expected_verdict": "BLOCK",
      "id": "<candidate id>",
      "run_id": "<recorded run id>",
      "scenario": "<named failure shape and evidence-backed scenario>"
    }
  ],
  "gotchas": [
    {
      "agent": "<recorded agent>",
      "entries": [
        {"id": "<recorded decision id>", "type": "decision"},
        {"id": "<recorded verification id>", "type": "verification"}
      ],
      "execution": "<recorded execution id>",
      "line": "<one-line named failure shape and earlier catching control>",
      "run_id": "<recorded run id>"
    }
  ],
  "input_head": "<full INPUT_HEAD>",
  "schema_version": 1
}
```

The `entries` value must be a nonempty array of exact `id`/`type` objects, where `type` is
`decision` or `verification`; every cited entry must exist exactly once in the named run and name
the same task as the recorded execution. At least one cited entry must be a `verification` whose
recorded result is `failed` or `inconclusive`; a healthy or unrelated entry did not earn a gotcha.
Select `expected_verdict` from exactly `PASS`, `BLOCK`, or `FLAG` using FR-100 semantics; the example's
`BLOCK` value is illustrative, not the only allowed verdict. Use `FLAG` only for a recorded non-review
monitoring agent, and never for a review agent; review agents have only `PASS` or `BLOCK` outcomes.
The `line` value must contain no CR or LF. The deterministic writer validates those entries, then
renders the appended gotcha line with citations to its run ID, execution ID, and every decision or
verification ID used. The reviewer never receives or returns the recorded prompt. `run_id` plus
`execution` instructs the deterministic writer to hydrate the exact recorded `prompt.md` from that
run's journal provenance; this preserves FR-102 without creating a fourth semantic input.

Before hydrating any proposal, require the named journal to end in exactly one final `run_closed`
with judgment `passed` or `blocked`, and require the named execution's task to contain a recorded
`failed` or `inconclusive` verification. A still-open or healthy run is not a failure-run source.

## 3. Enforce Advisory Authority

The reviewer is read-only and the deterministic proposal writer is the only mutation mechanism.
Apply this complete negative-write matrix to the reviewer, the orchestrator, and the writer:

| Forbidden surface or action | Prohibition |
|---|---|
| `.forge/evals/tasks/` | Never create, edit, delete, or promote a fixture there. |
| any `.result` baseline | Never create, edit, delete, regenerate, or bless a baseline. |
| `rules/` or the review constitution | Never change policy or constitutional text. |
| `forge-project.md` | Never change repository policy. |
| `.forge-manifest` | Never change installation authority. |
| routing configuration | Never change routing or model selection. |
| hooks | Never change or bypass a hook. |
| gates | Never change, weaken, waive, or bypass a gate. |
| execpolicy | Never change execution policy. |
| agent definitions | Never change any Codex or Claude agent definition. |
| any other control surface | Never mutate a control not named above. |

Never auto-apply, promote, approve, weaken, or commit a proposal. Never stage candidates or
gotchas. Candidate promotion remains a separate FR-051 independent review and explicit
operator-approval path; `/forge:learn` cannot perform or authorize it. Proposal creation must not
write, reopen, or amend `run_closed`, the committed archive, or `report.md`.

## 4. Validate and Write Proposals

Reject reviewer output that is not one strict JSON object in the exact schema above, contains an
extra key, lacks a key, cites an unavailable, open, or healthy run/execution, requests a forbidden
path/action, uses a multiline gotcha, lacks the full input head, names an archive absent at that
commit, or uses a proposal provenance value not exposed by the single run-id-derived committed
archive. Save the accepted object verbatim as `PROPOSALS_FILE`, then invoke only:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/learn-proposals-locked.py" \
  --repo "$REPO" --proposal "$PROPOSALS_FILE"
```

The writer may create collision-free FR-102 candidate fixtures only under
`.forge/evals/candidates/` and may append traceable lines only at EOF of
`.forge/history/gotchas.md`. It mechanically hydrates a candidate's exact Input prompt from the
named run and execution, and it must preserve every pre-existing gotchas byte as an exact prefix.
Before either write, require the repository's current committed `HEAD` to remain exactly
`input_head`. Refuse a candidate path already present at `input_head`, even when its working-tree
copy was deleted. When committed gotchas exist at `input_head`, require those exact bytes to remain
the working file's prefix; preserve and append after any prior uncommitted learning suffix.
It reads each run-id-derived archive through the proposal's committed `input_head`, mechanically
cross-checks archive and journal identities, requires the journal prompt path and the SHA-256 of its
single-link regular-file bytes to match the archive, and renders the exact
`<input_head>:<archive-path>` citation into each candidate and gotcha.
It never consumes candidates as a gate.

Report the three input identities, reviewer identity, named shapes, created candidate paths, gotcha
append count, and any refusal. Leave all proposal changes unstaged and uncommitted for a later
ordinary commit. A failure remains advisory and never changes any completed close, report, drift
block, or prior verdict.
