# Orchestration Contract

A run directory contains one append-only `journal.jsonl`. It records executions and decisions so
an operator can reconstruct what happened. The journal does not authorize launches, checks,
approvals, commits, merges, or run closure. Gate and candidate authority lives in `.forge/chains/`
and the observed Git and review evidence used by the relevant skill.

## Records and evidence

The prompt is the exact execution input, the event stream is raw provider output, and the handoff
is an agent claim. The launch marker and completion artefacts determine whether a managed launch
is in flight or has already been collected. A gate result is established by its own observed
command or chain evidence. A reference in a journal record is a link, not proof or permission.

Each new journal line is a JSON object with `kind` and `run_id`. The run ID is nonempty, is not
dot-prefixed, and contains no path separator, NUL, or control character. The writer serializes
complete line appends under one `fcntl.flock` and returns; it does not check run ownership, file
scope, task state, route consistency, chain state, references, or prior closure. It refuses only a
malformed envelope or I/O failure. An invalid run ID is refused before any directory or file is
created, without echoing the value.

The writer reports I/O failure as `forge: journal append failed: I/O error`, a missing or
non-object envelope as `forge: journal append refused: record must be a JSON object with kind and run_id`,
and an invalid run ID as `forge: <operation> refused — invalid run id`. It makes no other policy
refusal.

The public writer verbs and records are:

| Verb | New record | Contents |
|---|---|---|
| `run-open` | `run_started` | repository, intent text, actor |
| `journal task-start`, `journal task-finish` | `task` | task ID, title, free-text scope; finish may describe status |
| `journal execution-start` | `execution_started` | execution/task IDs, actual route, worktree, start time |
| `journal execution-result` | `execution_finished` | execution/task IDs, actual route, worktree, times, exit status, output path, reported tokens |
| `journal decision-add` | `decision` | free text, actor, optional references |
| `run-close` | `run_closed` | free-text outcome |

For example:

```jsonl
{"kind":"run_started","run_id":"run-01","repository":"/work/project","intent":"Add request validation","actor":"Claude"}
{"kind":"task","run_id":"run-01","task_id":"task-01","title":"Validate input","scope":"src/api.py and tests"}
{"kind":"execution_started","run_id":"run-01","execution_id":"execution-01","task_id":"task-01","role":"implementer","provider":"codex","model":"gpt-5.6-sol","effort":"ultra","worktree":"/work/project-impl","started_at":"2026-10-07T12:00:00Z","sandbox":"workspace-write","route_source":"committed-default","route_sha256":"7dc8bec71a109e095bfef57db5c7c6744dd4dcd88fd472a33a23c60adc5cba00"}
{"kind":"execution_finished","run_id":"run-01","execution_id":"execution-01","task_id":"task-01","role":"implementer","provider":"codex","model":"gpt-5.6-sol","effort":"ultra","worktree":"/work/project-impl","started_at":"2026-10-07T12:00:00Z","ended_at":"2026-10-07T12:20:00Z","status":"complete","exit_status":0,"output":"codex-impl-01/execution-01/handoff.md","sandbox":"workspace-write","route_source":"committed-default","route_sha256":"7dc8bec71a109e095bfef57db5c7c6744dd4dcd88fd472a33a23c60adc5cba00"}
{"kind":"decision","run_id":"run-01","text":"Retain the regression test","actor":"Claude"}
{"kind":"run_closed","run_id":"run-01","outcome":"Delivered; checks passed"}
```

<!-- forge: modified from upstream — describe non-authorizing launch journaling. -->
The launcher allocates execution and attempt IDs under the run's append lock, saves its prompt
and marker, appends `execution_started`, launches a detached wrapper, and writes a
three-line `pid` file (PID, PGID, UTC launch timestamp). `forge launch collect` maps the completion
artefact to `execution_finished`; a repeat collect after the marker is collected appends nothing.
An interrupted collect may append a second finish record when the first append succeeded before
the marker update. Every new execution record describes the route actually used: role, provider,
model, effort, sandbox, `route_source`, and `route_sha256`. A later execution may resolve a
different route.

The run's `.execution-ids/` directory holds owner-only `execution-NN` reservations. A prose
launcher chooses the next free ID under the run's executions root and reserves it there, using
the same allocation rule as `forge launch`; a managed launch uses the ID printed on its start
receipt. Each managed execution also has a `worktree` sidecar containing the canonical absolute
worktree path and a newline. The marker binds to that path during collect and cancel.

New records may cite chain IDs and verdict paths as references. They are not checked against
chain state. A close is descriptive; subsequent facts may be appended. The writer does not pair
executions or enforce task completion.

## Structural reading

`state` and `monitor` read records as data. Readers carry unknown and every legacy kind through
without changing the stored bytes. Historical records using `type` remain readable, including
legacy records without `run_id` after `run_started`. The committed `tests/replay/` fixtures are
preserved inputs and validate with no issue.

`validate <run_dir>` checks only that each line parses to a JSON object with a current
`kind`/`run_id` envelope or a legacy `type` envelope. It emits sorted-key JSON with `ok` and
`issues`, and exits 0 exactly when issues is empty. A malformed line contributes exactly
`forge: journal validate failed: malformed JSON object at line <n>`. Unknown kinds and unfamiliar
fields are accepted. Validation does not replay lifecycle state, evaluate gates, derive a
judgment, or grant permission to any operation.

## Reporting

Keep exact prompts, raw events, handoffs, and useful observations under the local run directory.
Compare the final repository with its observed starting state, inspect check results and review
verdicts at their source, and report chain outcomes from `.forge/chains/`. Treat a handoff as a
claim until it has been checked. Correct a mistake by appending a later fact; never rewrite an
existing journal line or historical fixture.
