---
name: worktree-merge
description: Run the fail-closed four-gate worktree merge and locked rebase reintegration. Use when a completed forge worktree is ready to return to the repository's default branch.
---

# Worktree Merge

Run this workflow from the candidate worktree. Set `policy_sha` to the full output of
`git rev-parse HEAD`, and read all project gate configuration exclusively from that root-level
committed revision with `git show "${policy_sha}:forge-project.md"`. Never open the working-tree
file, a rendered copy, or duplicated defaults for policy. Retain the exact committed snapshot and
full SHA only for the current fixed candidate; if HEAD changes, discard both and resolve a new
revision before rerunning gates.
For every non-mutation executable policy cell, run from the repository root as
`bash -c <complete-cell> forge`: the complete unchanged cell is one argv element, literal `forge`
is `$0`, and every parameter is a separate later argv element. Never concatenate, interpolate,
wrap, or `eval` cells or parameters. Isolate each process group, cap combined output at 65,536
bytes, and enforce the fixed 1200-second fail-closed timeout. This discipline applies to Gate 1,
stack validations, and invariants; scoped mutation uses its committed per-row timeout below.

<!-- forge: modified from upstream — gate regions live only in forge-project.md (FR-073). -->

Run the two preconditions and Gates 1 through 4 in the exact order below. Fail closed: a dirty
worktree, missing configuration, failed command, BLOCK verdict, unavailable reviewer, missing
control approval, lock failure, rebase failure, re-verification failure, or push failure means no
merge. Surface the failure and leave the worktree and branch intact for inspection. Never delete
them on a failed merge.

Replace `<default-branch>` in the canonical commands below with the confirmed default branch from
the target repository's `.forge-manifest`. Never treat the candidate branch as the default branch.

## Preconditions

### 1. Require a clean worktree

Run:

```bash
git status --porcelain=v1 --untracked-files=all
```

Require empty output. If any line is returned, stop before Gate 1, show every dirty or untracked
path, and leave the worktree intact. Tell the user to commit the intended work through
`/forge:commit`. Discard work only after explicit user approval; never infer approval from a merge
request.

### Drift state is not a merge input

After the clean-worktree precondition passes, continue toward Gate 1 without consulting drift
state. `/forge:worktree-merge` itself ignores drift state: do not read
`.forge/history/drift/**` or `.forge/tmp/drift-block`. A recorded MAJOR or MINOR finding is
advisory to merge and does not stop or change the merge gates. An existing drift-block is likewise
not a merge input. Proceed through the remaining configured preconditions to Gate 1.

This merge contract does not change the separate workflow-opening rule for CRITICAL drift. It
does not authorize opening an orchestration run that rule prevents from opening.

### 2. Fix and classify the candidate

Capture the full candidate identity and the remote base that the gates inspect:

```bash
DEFAULT_BRANCH="<default-branch>"
CANDIDATE_HEAD="$(git rev-parse HEAD)"
policy_sha="$CANDIDATE_HEAD"
REVIEWED_BASE="$(git rev-parse "origin/${DEFAULT_BRANCH}")"
WORKTREE_DIR="$(git rev-parse --show-toplevel)"
BRANCH="$(git branch --show-current)"
git diff "origin/${DEFAULT_BRANCH}...HEAD"
git diff --name-only "origin/${DEFAULT_BRANCH}...HEAD"
```

The full merge-diff operation is `git diff origin/<default-branch>...HEAD`. Classify every changed
path from that range against the committed `file-categories` region returned by
`git show HEAD:forge-project.md` and the built-in `control` category. The built-in category always
includes:

- `forge-project.md`
- `.forge-manifest`
- `.codex/**`
- `.forge/evals/tasks/**`, including baselines
- `AGENTS.md`
- `CLAUDE.md`
- `.claude/settings*.json`
- `.github/workflows/**`, or equivalent CI configuration paths recorded in `file-categories`

Project configuration may extend `control`; it must never remove or narrow a built-in entry.
`.forge/evals/candidates/**` is the sole eval-path exception: classify it as advisory/docs-class,
not `control`, even when an older or broader project `control` pattern matches it. Moving or copying
a candidate into `.forge/evals/tasks/**`, or creating or changing its baseline there, is a
control-class promotion.
Fail closed if a changed path cannot be classified. Keep `CANDIDATE_HEAD` unchanged through Gates
1 through 4. If HEAD or the diff changes, restart at the clean-worktree precondition.

Derive merge-tier evidence mechanically from this exact candidate range and committed policy:

```bash
declared_tier="${declared_tier:-}"
declared_args=()
if [ -n "$declared_tier" ]; then
  case "$declared_tier" in
    fast|standard|hard) declared_args=(--declared-tier "$declared_tier") ;;
    *) echo "forge: invalid declared risk tier: $declared_tier" >&2; exit 1 ;;
  esac
fi
TIER_EVIDENCE="$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/risk_tier.py" \
  --repo "$PWD" --policy-sha "$policy_sha" "${declared_args[@]}" \
  --range "${REVIEWED_BASE}...${CANDIDATE_HEAD}")" || exit 1
```

If the task/journal supplies a declared/decomposed tier, set `declared_tier` to that exact
`fast`, `standard`, or `hard` value before this block. Otherwise omit the advisory declaration;
never pass an empty or invented tier.

The compact JSON evidence must retain the exact path list, matched tier/trigger/category rows,
formatting-category decisions, dependency-floor decision, declared, derived, and promote-only
effective tiers, and full policy SHA. The effective tier is the higher of declared and derived and
can never be demoted at gate time. Apply the same non-narrowable floors as commit: built-in plus
project-extended control, after the sole `.forge/evals/candidates/**` carve-out above, and all
`trigger-paths` matches are hard; malformed nonempty trigger rows
make the range hard; unmatched paths default standard; the committed dependency-manifest block and
unknown manifest membership are at least standard; and no policy row can weaken FR-156's
formatting-only exclusions. Do not reconstruct these predicates or read any working-tree policy.
Tier evidence routes reporting and control approval, but never removes a merge gate. In particular,
Gate 3 remains `review-final` and mandatory even if this range and every constituent commit are
fast.

## Required-region check

Before executing Gate 1, obtain the committed policy and verify that each of
`gate1-test-command`, `stack-validations`, and `file-categories` has both region markers and no
`forge-init:` sentinel. Use this fail-closed check, which never reads the working-tree policy:

```bash
if ! COMMITTED_POLICY="$(git show "${policy_sha}:forge-project.md" 2>/dev/null)"; then
  printf 'forge: %s not configured — run /forge:init\n' 'gate1-test-command' >&2
  exit 1
fi

require_filled_region() {
  REGION="$1"
  REGION_BEGIN="<!-- FORGE:REGION ${REGION} BEGIN -->"
  REGION_END="<!-- FORGE:REGION ${REGION} END -->"
  if ! printf '%s\n' "$COMMITTED_POLICY" | grep -Fxq "$REGION_BEGIN" ||
    ! printf '%s\n' "$COMMITTED_POLICY" | grep -Fxq "$REGION_END"; then
    printf 'forge: %s not configured — run /forge:init\n' "$REGION" >&2
    return 1
  fi
  REGION_BLOCK="$(
    printf '%s\n' "$COMMITTED_POLICY" |
      sed -n "/^<!-- FORGE:REGION ${REGION} BEGIN -->$/,/^<!-- FORGE:REGION ${REGION} END -->$/p"
  )"
  REGION_BODY="$(printf '%s\n' "$REGION_BLOCK" | sed '1d;$d')"
  if [ -z "$(printf '%s\n' "$REGION_BODY" | sed '/^[[:space:]]*$/d')" ] ||
    printf '%s\n' "$REGION_BODY" | grep -Fq 'forge-init:'; then
    printf 'forge: %s not configured — run /forge:init\n' "$REGION" >&2
    return 1
  fi
}

for REGION in gate1-test-command stack-validations file-categories; do
  require_filled_region "$REGION" || exit 1
done
```

The required failure contract is exactly
`forge: <region> not configured — run /forge:init`, followed by exit 1. When the file is missing,
the loop reports `gate1-test-command` first. Treat malformed or missing markers as unconfigured.

## Gate 1 — Project tests

Read the `gate1-test-command` region from the committed policy snapshot and execute its body
exactly once in the candidate worktree. Require exit 0. Do not substitute a remembered command,
an agent-reported result, a working-tree policy edit, or a narrower test selection. On failure,
show the command output and stop with the worktree intact.

### Scoped mutation evidence after Gate 1

After Gate 1 passes, run the plugin-owned scoped runner exactly once over the fixed candidate
range. The runner obtains policy itself with `git show HEAD:forge-project.md`, reads test-pattern
mining guidance from `${CLAUDE_PLUGIN_ROOT}/system/seeds/validation-snippets/stacks.md`, and derives
the qualifying repository-relative paths from the fixed diff. It selects a category only when that
diff touches one of the category's test files or has status `A` for one of its source files;
modified-only source is not a trigger. It executes at most one changed-files row per selected
category and passes only that category's selected paths.

```bash
MUTATION_EVIDENCE_FILE=".forge/tmp/mutation-evidence-${CANDIDATE_HEAD}.log"
mkdir -p .forge/tmp
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/run-scoped-mutation.py" \
  --base "$REVIEWED_BASE" --head "$CANDIDATE_HEAD" \
  >"$MUTATION_EVIDENCE_FILE" 2>&1 ||
  printf '%s\n' '{"type":"mutation_evidence","criterion":"mutation: policy","result":"inconclusive","check":"scoped mutation runner","observation":"tool=mutation-testing runner; scope=policy; outcome=unavailable"}' \
    >>"$MUTATION_EVIDENCE_FILE"
cat "$MUTATION_EVIDENCE_FILE"
```

When, and only when, an explicitly identified orchestration run is open, add both
`--journal <that-run-dir>/journal.jsonl` and `--task <that-run-task-id>` to this single invocation.
Pass both values as separate argv elements and never infer a "latest" run. The runner appends one
ordinary `verification` per applicable execution. Without those explicit values it prints the same
evidence without creating or selecting a journal.

The runner validates the complete committed `mutation-testing` region before running any row. A
valid table is `| category | command | changed-files form | timeout |`; the executable cells are
nonempty, single-line command cells, and a nonempty timeout is ASCII base-10 digits whose numeric
value is greater than zero. A legacy row with no timeout column or an empty timeout cell uses 600
seconds. The exact infeasible-stack declarations written by `/forge:init` are evidence, not
executable rows.

If the region or any row is malformed, execute no mutation row, print exactly
`forge: executable policy row malformed` as the first line, carry the skip into Gate 3 evidence,
and continue to Gate 2. Malformed mutation policy never blocks or satisfies a gate.

For every applicable valid row, derive the repository-relative changed-file scope from the fixed
candidate diff and execute the row's complete `changed-files form` cell unchanged as exactly one
argument to `bash -c`, with literal `forge` as `$0` and every scoped path as one subsequent argv
element consumed through `"$@"`. Never concatenate the full-suite command with the changed-files
form, interpolate paths or diff content into the command cell, or use `eval`; commit and merge
paths must not substitute an unscoped/full mutation run. Run from the repository root in an
isolated process group, cap combined stdout and stderr at 65,536 bytes, use the row timeout, and
kill the complete process group on timeout.

A nonzero result, timeout, output-limit breach, launch failure, or surviving mutant is advisory:
surface it in Gate 3 evidence and continue. It never blocks merge and never satisfies Gate 1,
Gate 2, or Gate 3. For an explicitly identified open run, record each result as an ordinary
`verification` with criterion exactly `mutation: <scope>`; record command, outcome, scoped files,
timeout, and completed/timed-out/malformed-skip state in the existing fields. The stable execution
scope is the mutation row's category; a whole-region malformed skip uses scope `policy`. Never use
a `gate-` prefix for mutation evidence.

## Gate 2 — Stack validations

Read the `stack-validations` region from the committed policy snapshot. Execute every configured
validation for every category touched by the classified full merge diff. Require every command to
exit 0. Missing, ambiguous, or non-executable validation configuration blocks the merge. On any
failure, show the command and output and stop with the worktree intact.

Before executing an invariant, validate the complete committed `invariants` region as exactly the
table `| invariant | check command | enforcement point |`. Every data row needs nonempty invariant
and single-line command cells and an enforcement point exactly equal to `commit`, `merge`, or
`hook`. On an empty command, malformed row, multi-row command, unknown point, or otherwise
unparseable nonempty region, execute no invariant and fail Gate 2 with the exact first line
`forge: executable policy row malformed`.

Run every `merge` row from the validated table. From the repository root, invoke the complete
command cell unchanged as exactly one argument to `bash -c`, followed by literal `forge` as `$0`.
Pass each parameter as one subsequent argv element consumed through `"$@"`; never concatenate,
interpolate, source-wrap, or `eval` a cell. Use an isolated process group, cap combined stdout and
stderr at 65,536 bytes, and enforce a fixed 1200-second timeout that kills the complete process
group. A nonzero result, launch failure, or output-limit breach fails Gate 2 with exact first line
`forge: invariant failed (merge): <invariant>`. A timeout fails with exact first line
`forge: invariant timed out (merge): <invariant>`. Only capped diagnostics may follow.

Derive touched test paths mechanically from the fixed candidate diff. If any are touched, run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-test-quality.py" -- <touched-test-path>...
```

Pass each path as its own argv element. Exit 1 from the Python AST branch or exit 2 from sensor
failure blocks Gate 2. Exit 0 advances, while every non-Python advisory, no-heuristic notice, and
valid waiver path plus reason remains in Gate 2 and Gate 3 evidence. A waiver affects only the
assertion sensor for its one file; it never skips tests, scoped mutation, invariants, or sensing in
another file.

After preserving the sensor's primary result, hash the exact merge-diff bytes used for this gate
candidate and make exactly one advisory `emit-decision-event.py` append attempt for each surfaced
result: `assertion_blocking` for every blocking finding, `assertion_advisory` for every advisory
finding, absence, or inconclusive disposition, and `assertion_waived` for every accepted per-file
waiver. Use that lowercase SHA-256 as `--candidate`, the full `policy_sha`, surface
`/forge:worktree-merge`, and a stable non-secret finding/disposition code as `--reason`. A clean
sensor result with no surfaced advisory disposition emits no assertion event. Apply this same rule
to an in-lock Gate 2 rerun, using the exact integrated merge diff it sensed. These attempts happen
only after the sensor result is preserved and are advisory; an emitter failure never changes the
Gate 2 result or exit status.

## Gate 3 — Binding adversarial review

Gate 3 is unconditional. Do not skip, downgrade, replace, or auto-PASS it for an effective-fast
range, for a branch composed entirely of four-line fast-marker commits, or for prior commit-level
review evidence. Merge composition and integration risk are assessed independently here.

Start the `review-final` Claude agent as a reviewer distinct from the author. Give it the full
`CANDIDATE_HEAD`, the constitution at
`${CLAUDE_PLUGIN_ROOT}/rules/review-constitution.md`, and the exact, unmodified diff generated for
the resolved full-SHA candidate range:

```bash
git diff "${REVIEWED_BASE}...${CANDIDATE_HEAD}"
```

This is the fixed-SHA form of the required canonical
`git diff origin/<default-branch>...HEAD` operation. Do not regenerate the review input from moving
symbolic refs after fixing the candidate identity.

Also give the reviewer the complete contents of `MUTATION_EVIDENCE_FILE` as a distinct evidence
block, including passing runs, nonzero exits, timeouts, output-limit or launch failures, exact
declared-absence notices, and `forge: executable policy row malformed` skips. Do not edit or
summarize away an advisory outcome before review. This evidence informs Gate 3; it never counts as
or satisfies the Gate 3 verdict.

Require the binding verdict to be exactly PASS or BLOCK. PASS advances to Gate 4. BLOCK, an
ambiguous response, or an unavailable reviewer stops reintegration. Report all findings. On every
explicit BLOCK, first deliver and preserve the binding BLOCK outcome, then make exactly one
advisory append attempt through `${CLAUDE_PLUGIN_ROOT}/scripts/forge/emit-decision-event.py` with
event `review_block`, candidate equal to the lowercase SHA-256 of the exact reviewed merge diff,
full `policy_sha`, surface `/forge:worktree-merge`, and a stable non-secret reason. An event timeout or append
failure never changes the Gate 3 verdict or exit status.

After preserving each `review-final` invocation's complete verdict and findings, make exactly one
advisory `review_final_finding` append attempt per finding it raised. Use the lowercase SHA-256 of
the exact reviewed merge diff as `--candidate`, the full `policy_sha`, surface
`/forge:worktree-merge`, and the finding's normalized stable severity (`CRITICAL`, `MAJOR`, or
`MINOR`) as `--reason`. Count findings from every invocation, including BLOCKs later superseded and
every required in-lock review of the integrated range. An invocation with no findings emits no
finding event. These attempts occur after the verdict and findings are preserved; emitter failure
never changes the verdict, review iteration, or exit status.

For a revision, commit the fix through `/forge:commit`, re-establish a clean worktree, and re-run
the affected Gates 1 and 2 before re-review. Use a maximum of 8 review iterations. Dispositioning
any finding above MINOR requires explicit user approval. At the 8-iteration cap without PASS,
record the residual risk—every outstanding finding and why it remains—escalate to the user, and
never merge.

When, and only when, an explicitly identified orchestration run is open, journal every Gate 1 and
Gate 2 execution under that run, including every in-lock re-run. Begin each Gate 1 criterion
exactly `gate-1: ` and each Gate 2 criterion exactly `gate-2: `. Use exactly
`gate-3: review-final verdict` for every Gate 3 execution. For the initial Gate 3, its `check` names
the resolved full-SHA `${REVIEWED_BASE}...${CANDIDATE_HEAD}` range that generated the exact review
diff. A post-rebase Gate 3 instead names the actual full-SHA
`${INTEGRATED_BASE}...${INTEGRATED_HEAD}` range it reviewed. Resolve the applicable variables before
writing each record; do not record variable names, short SHAs, symbolic refs, or an inferred
"latest" run. Normalize and count every finding by `CRITICAL`, `MAJOR`, and `MINOR`; the reviewer
is `review-final`. Record the observation as exactly `<PASS|BLOCK>; <critical-plus-major-count>
CRITICAL/MAJOR findings; severities CRITICAL=<count>,MAJOR=<count>,MINOR=<count>; reviewer
<review-cheap|review-final>; iteration <number> of 8.`

## Gate 4 — Summary and authority

Show all of the following:

```bash
git diff --stat origin/<default-branch>...HEAD
git diff --name-only origin/<default-branch>...HEAD
git rev-parse HEAD
```

Also show the Gate 1, Gate 2, and Gate 3 results in one line each. Confirm that `git rev-parse
HEAD` still equals `CANDIDATE_HEAD`; otherwise restart the chain.

If the classified diff touches any `control` path, present the summary with the full
`CANDIDATE_HEAD` and wait for explicit user approval naming that same SHA. Do not acquire the lock,
rebase, or push before approval. Never approve a control-class merge autonomously. If the diff is
non-control, proceed automatically after a clean Gate 4. Use `CANDIDATE_HEAD` as the Gate 4
candidate identity; never substitute a branch name, short SHA, or moving ref in the summary or
approval request.

## Locked rebase reintegration

<!-- forge: modified from upstream — halt path is plugin-rooted; re-verification is in-lock and pre-push; the lock is FR-235's portable arbiter via `common-lock hold` (Revision 13, bead forge-plugin-9qf.7). -->

Run the halt check before acquiring the lock:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh" || {
  echo "operator halt engaged — not merging" >&2
  exit 1
}
```

Only the operator may create, remove, or bypass a halt sentinel. A nonzero halt result stops before
lock acquisition.

The rebase lock is FR-235's mandatory Git-common-dir portable arbiter, held for this skill by the
Forge CLI's long-lived wrapper `common-lock hold`. The wrapper acquires the portable owner first
and the optional kernel `flock` layer second (through Python's `fcntl.flock` on `agent-rebase.lock`
wherever the interpreter provides it — the `flock` binary is irrelevant to the wrapper), releases
them in reverse order, and never selects a backend by host capability: Linux and macOS entrants
contend on the same no-replace inode namespace, and `flock` alone is never a complete lock. This skill no longer creates `agent-rebase.lockdir` itself
or falls back to a `mkdir` mutex; both would collide with the arbiter's namespace.

Resolve the shared lock location exactly from the Git common directory and open the two
readiness/release pipes the wrapper protocol requires:

```bash
GIT_COMMON_DIR="$(git rev-parse --path-format=absolute --git-common-dir)"
mkdir -p .forge/tmp
LOCK_READY_FIFO=".forge/tmp/rebase-lock-ready.${FORGE_SESSION_PID}"
LOCK_RELEASE_FIFO=".forge/tmp/rebase-lock-release.${FORGE_SESSION_PID}"
LOCK_OUTCOME=".forge/tmp/rebase-lock-outcome.${FORGE_SESSION_PID}.json"
rm -f "$LOCK_READY_FIFO" "$LOCK_RELEASE_FIFO" "$LOCK_OUTCOME"
mkfifo -m 600 "$LOCK_READY_FIFO" "$LOCK_RELEASE_FIFO" || {
  echo "forge: cannot create rebase lock pipes under .forge/tmp — not merging" >&2
  exit 1
}
exec 8<>"$LOCK_READY_FIFO" 9<>"$LOCK_RELEASE_FIFO"
```

Keep one lock-owning shell alive from acquisition through explicit release. This file-descriptor
lock epoch is one composite invocation and must not be split across fresh tool shells. The shell
inherits the stable live `FORGE_SESSION_PID` injected by the long-lived harness unchanged; never
export or substitute `$$`, `$PPID`, or any transient tool-process PID as that identity. Start the
holder as a standalone default-branch push entrant (owner kind `push`, operation `push`; this
legacy skill owns no CLI merge chain) and wait for its readiness record, which arrives only once
the complete lock is held:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py" --json --repo "$PWD" \
  common-lock hold --owner-kind push --operation push --ready-fd 8 \
  <"$LOCK_RELEASE_FIFO" >"$LOCK_OUTCOME" 2>&1 9>&- &
LOCK_HOLDER_PID=$!
LOCK_READY=""
LOCK_WAITED=0
while [ -z "$LOCK_READY" ]; do
  read -r -t 5 LOCK_READY <&8 && break
  LOCK_WAITED=$((LOCK_WAITED + 5))
  kill -0 "$LOCK_HOLDER_PID" 2>/dev/null || break
  [ "$LOCK_WAITED" -lt 330 ] || break
done
if [ -z "$LOCK_READY" ]; then
  echo "forge: rebase lock unavailable (holder hint: inspect ${GIT_COMMON_DIR}/agent-rebase.lockdir and $LOCK_OUTCOME)" >&2
  exec 8<&- 9>&-
  wait "$LOCK_HOLDER_PID" 2>/dev/null
  cat "$LOCK_OUTCOME" >&2 2>/dev/null
  exit 1
fi
printf '%s\n' "$LOCK_READY" | python3 -c '
import json, sys
record = json.loads(sys.stdin.readline())
assert record["schema"] == "forge-common-lock-ready/1"
assert set(record) == {"schema", "owner_digest", "nonce", "pid"}
' || {
  echo "forge: rebase lock readiness record is malformed (holder hint: inspect ${GIT_COMMON_DIR}/agent-rebase.lockdir)" >&2
  exec 8<&- 9>&-
  wait "$LOCK_HOLDER_PID" 2>/dev/null
  exit 1
}
```

The wrapper writes exactly one canonical `forge-common-lock-ready/1` record on descriptor 8 after
the complete lock is held, then blocks on its stdin for the single release frame. The `9>&-` on the
wrapper's command line is load-bearing: the wrapper reads the release pipe through its stdin only
and must not inherit the shell's read-write descriptor 9, or it would itself hold a writer on that
pipe and never observe the end-of-file that completes the release. The readiness wait polls in
5-second slices so a wrapper that refuses or dies immediately stops the merge at once, while a
contended lock waits up to the wrapper's 300-second shared deadline (330 seconds of slices). The
same discipline applies to every command run inside the lock epoch: descriptors 8 and 9 are
inherited by every child the shell starts, so run each in-lock command (the fetch, the rebase,
every Gate 1/2/3 re-run, the mutation runner, the reviewer launch, and the push) with `8<&- 9>&-`
appended, and never leave a backgrounded helper running past the release. A child that outlives
the release while holding descriptor 9 keeps a writer on the release pipe and the wrapper cannot
observe end-of-file; the bounded release wait below then reports `lock-release-failed` instead of
hanging. A refusal, an
exhausted 300-second shared deadline, or a holder that dies before readiness produces no record, so
the bounded wait ends and the merge stops with the holder hint and the wrapper's own `forge-cli/2`
outcome. Never skip locking. If the wrapper is unavailable or refuses, fail loudly and leave the
worktree intact. The lock is released only by the explicit release frame below or by the wrapper
observing end-of-file on its stdin: exiting the lock-owning shell closes descriptor 9, the wrapper
releases the portable owner and any `flock` layer, and reports the missing frame as a refusal. A
holder killed outright (for example by a harness kill of the whole process group) drops its kernel
`flock` but leaves a dead portable owner record behind, and the next entrant refuses until that
owner is cleared. In this phase no automated recovery surface is live for it: clearing a dead
owner is an operator-reserved action. Never delete `agent-rebase.lockdir` or
`agent-rebase.lock.intent` from this skill; report the holder hint, and the operator, after proving
the recorded host and PID dead, removes exactly those two owner artifacts by hand and records the
removal as a decision before any further reintegration.

Inside the lock, first prove that HEAD is still the approved/reviewed candidate. Then fetch and
rebase:

```bash
[ "$(git rev-parse HEAD 8<&- 9>&-)" = "$CANDIDATE_HEAD" ] || {
  echo "forge: candidate HEAD changed after gates — rerun /forge:worktree-merge" >&2
  exit 1
}
git fetch origin "$DEFAULT_BRANCH" --quiet 8<&- 9>&-
FETCHED_BASE="$(git rev-parse "origin/${DEFAULT_BRANCH}" 8<&- 9>&-)"
DEFAULT_ADVANCED=0
[ "$FETCHED_BASE" = "$REVIEWED_BASE" ] || DEFAULT_ADVANCED=1
git rebase "origin/${DEFAULT_BRANCH}" 8<&- 9>&-
```

Every command in the fences from here to the release carries `8<&- 9>&-`; apply the same suffix to
any conflict-resolution command, `git rebase --continue`, `git rebase --abort`, and every gate,
mutation, or reviewer launch you issue inside the lock.

The canonical operations are `git fetch origin <default-branch>` followed by
`git rebase origin/<default-branch>`. Never create a merge commit. Never run `git merge`, use a
non-rebase pull, or create or push an intermediate integration branch. Reintegrate concurrent
worktrees one at a time under this lock.

If rebase stops on conflicts, keep the lock, resolve only the named conflicts, stage each resolved
path explicitly, and run `git rebase --continue 8<&- 9>&-`. Record that conflicts were resolved. If they
cannot be resolved safely, run `git rebase --abort`, exit without pushing, release the lock, and
leave the worktree and branch present.

After a successful rebase, capture the exact integrated identity before any re-verification:

```bash
INTEGRATED_BASE="$(git rev-parse "origin/${DEFAULT_BRANCH}" 8<&- 9>&-)"
INTEGRATED_HEAD="$(git rev-parse HEAD 8<&- 9>&-)"
INTEGRATED_RANGE="${INTEGRATED_BASE}...${INTEGRATED_HEAD}"
CANDIDATE_REWRITTEN=0
[ "$INTEGRATED_HEAD" = "$CANDIDATE_HEAD" ] || CANDIDATE_REWRITTEN=1
```

### In-lock re-verification

Perform all required re-runs inside the lock and before push:

- If `DEFAULT_ADVANCED=1` or `CANDIDATE_REWRITTEN=1`, re-run Gate 1 and Gate 2 against the
  integrated tip. First discard the earlier policy snapshot and obtain current policy again with
  a fresh full `policy_sha="$(git rev-parse HEAD)"` and
  `git show "${policy_sha}:forge-project.md"`; then replace the earlier tier evidence fail closed:

  ```bash
  TIER_EVIDENCE="$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/risk_tier.py" \
    --repo "$PWD" --policy-sha "$policy_sha" "${declared_args[@]}" \
    --range "${INTEGRATED_BASE}...${INTEGRATED_HEAD}" 8<&- 9>&-)" || exit 1
  ```

  Preserve this replacement evidence as the only tier authority for the integrated candidate.
  Between the two gates, also run the applicable advisory scoped
  mutation checks by repeating the plugin runner invocation with `--base "$INTEGRATED_BASE"` and
  `--head "$INTEGRATED_HEAD"`, replacing the earlier mutation evidence file (and passing the same
  explicitly selected journal/task pair when a run is open). Re-derive changed paths and
  assertion-sensor inputs from `INTEGRATED_RANGE`; require clean Gate 1 and Gate 2 passes while
  preserving mutation findings as Gate 3 evidence.
  This covers both remote movement after the initial gates and a candidate that was already behind
  the default branch when the chain began. Never push an untested integrated tree.
- If conflicts were resolved, Gate 3 is mandatory on the post-rebase candidate because the content
  changed. If `CANDIDATE_REWRITTEN=1` without conflicts, also re-run Gate 3 so the binding review,
  approval, and pushed SHA identify the same candidate as DM-001 requires. Give `review-final`
  exactly `git diff "${INTEGRATED_BASE}...${INTEGRATED_HEAD}"` and journal that actual resolved
  full-SHA range. Require PASS before push. This strengthened identity rebind includes every
  conflict-resolution case.
- If the rebase is a pure fast-forward with no new default-branch commits and no conflict
  resolution, perform no re-run.

Any required re-run failure stops before push. Exit the lock-owning shell so the lock releases,
leave the remote untouched, and preserve the worktree and branch for inspection. Do not defer a
re-run until after the push.

When a rebase changed the candidate identity, repeat Gate 4 over `INTEGRATED_RANGE`. For a control
diff, present the new full `INTEGRATED_HEAD` and wait for explicit user approval naming that exact
SHA while the rebase lock remains held; the earlier approval for `CANDIDATE_HEAD` does not authorize
a rewritten candidate. For a non-control diff, proceed automatically after the clean repeated
summary. Set `AUTHORIZED_HEAD="$INTEGRATED_HEAD"` only after the binding re-review and any required
approval. When the candidate was not rewritten, set `AUTHORIZED_HEAD="$CANDIDATE_HEAD"` from the
original Gate 4. Immediately before push, require `git rev-parse HEAD` to equal `AUTHORIZED_HEAD`;
otherwise stop without touching the remote.

Only after every required in-lock re-run passes, fast-forward the candidate with exactly this ref
mapping, the lock descriptors closed for the push process:

```bash
git push origin HEAD:<default-branch> 8<&- 9>&-
```

Substitute the confirmed default branch for the placeholder. Do not push any other ref. Treat a
non-fast-forward rejection or any other push error as a failed merge.

After a successful push, release the lock explicitly by sending the wrapper its single release
frame, closing the release pipe, and requiring the wrapper's final outcome to report the release:

```bash
printf 'release\n' >&9
exec 9>&- 8<&-
LOCK_RELEASE_WAITED=0
while kill -0 "$LOCK_HOLDER_PID" 2>/dev/null && [ "$LOCK_RELEASE_WAITED" -lt 60 ]; do
  sleep 1
  LOCK_RELEASE_WAITED=$((LOCK_RELEASE_WAITED + 1))
done
if kill -0 "$LOCK_HOLDER_PID" 2>/dev/null; then
  echo "forge: failed to release rebase lock — lock-release-failed: holder still running after 60 s, a child may hold the release pipe (holder hint: inspect ${GIT_COMMON_DIR}/agent-rebase.lockdir and $LOCK_OUTCOME)" >&2
  exit 1
fi
wait "$LOCK_HOLDER_PID"
LOCK_EXIT=$?
python3 -c '
import json, sys
outcome = json.loads(open(sys.argv[1], "rb").read().splitlines()[-1])
assert outcome["schema"] == "forge-cli/2"
assert outcome["reason_code"] == "ok"
assert outcome["message"] == "forge: common rebase lock released"
' "$LOCK_OUTCOME" && [ "$LOCK_EXIT" -eq 0 ] || {
  echo "forge: failed to release rebase lock — lock-release-failed (holder hint: inspect ${GIT_COMMON_DIR}/agent-rebase.lockdir and $LOCK_OUTCOME)" >&2
  exit 1
}
rm -f "$LOCK_READY_FIFO" "$LOCK_RELEASE_FIFO"
```

The push has already landed when release runs; a release failure is reported as a failed merge
step so the operator inspects the retained owner before any further reintegration, exactly as
FR-235's `lock-release-failed` disposition requires. After a clean release the owner record and
`agent-rebase.lockdir` are gone; the regular file `agent-rebase.lock` that the optional `flock`
layer uses legitimately persists and is not a retained owner.

## Cleanup after successful push

Do not enter cleanup unless the push succeeded. Capture and verify containment before removing
anything:

```bash
PUSHED_HEAD="$(git rev-parse HEAD)"
MAIN_WORKTREE="$(cd "${GIT_COMMON_DIR}/.." && pwd -P)"
git fetch origin "$DEFAULT_BRANCH" --quiet
git merge-base --is-ancestor "$PUSHED_HEAD" "origin/${DEFAULT_BRANCH}" || {
  echo "forge: pushed candidate is not contained in origin/${DEFAULT_BRANCH} — cleanup refused" >&2
  exit 1
}
cd "$MAIN_WORKTREE"
git worktree remove "$WORKTREE_DIR" || {
  echo "forge: worktree removal failed — branch preserved" >&2
  exit 1
}
git branch -D "$BRANCH"
```

Run the worktree-removal command exactly as shown; do not add options that discard residual files.
If removal finds residual tracked or untracked files, stop cleanup and keep the branch. Delete the
branch only after `git merge-base --is-ancestor` confirms that its pushed tip is contained in the
remote default branch. No failed merge path may remove either the worktree or the branch.

## Record authority and report

Every decision append is advisory and occurs only after its primary outcome has been delivered.
The emitter registers an in-flight writer but acquires no lock. It opens the canonical
`.forge/tmp/decisions/events.jsonl` with `os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT,
0o600)`, makes exactly one `os.write()`, and treats a short write as a failure. The
`.forge/tmp/events.lock` gates only drift-check's prune read-and-replace and its coordination with
registered writers; it never serializes event appends. Registration or append failures cannot
alter a permission decision, review BLOCK, push, cleanup, or its exit status. This non-interleaving
guarantee relies on POSIX `O_APPEND` semantics on a local filesystem on the supported macOS and
Linux platforms; it does not extend to NFS/SMB network filesystems, and Windows is out of scope.
Aggregation deduplicates merge review blocks by `(event, candidate)`.

Treat every agent handoff and claimed gate result as a claim, never gate evidence. Before any
commit or merge that reintegrates agent work, the orchestrator must itself re-run Gates 1 and 2 in
its own integration target, not in the agent's worktree. Record only the orchestrator's observed
commands, outputs, and exit statuses as gate evidence.

Report the four gate results, any in-lock re-runs, the pushed full SHA, the default branch, lock
outcome, and cleanup outcome. Never report reintegration or cleanup as successful unless the
corresponding command succeeded.
