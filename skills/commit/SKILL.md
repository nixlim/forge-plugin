---
name: commit
description: Run the five-step fail-closed forge commit gate chain over explicit target paths.
---

# Commit Gate Chain

Run this skill for every commit. Execute Steps 1–5 in order. Do not reorder, omit, or treat an
unavailable command or reviewer as a PASS. Any non-skipped failure stops the chain, surfaces the
failure, and leaves the change uncommitted. Hold the commit lock only during Step 5, never during
the Step 4 review loop.

Resolve all project gate configuration from one authenticated committed revision. At the start of
the chain, set `policy_sha` to the full result of `git rev-parse HEAD`, load the policy only with
`git show "${policy_sha}:forge-project.md"`, and use only those returned bytes for every policy read
in Steps 1–4, including classification, executable commands, changelog policy, review context,
invariants, `risk-tiers`, its fixed `FORGE:DEPENDENCY-MANIFEST-PATHS` block, `trigger-paths`, and
`file-categories`. Never open the working-tree `forge-project.md`, a rendered copy, or duplicated
defaults for policy. Keep the full `policy_sha` with the gate evidence. If HEAD changes before the
commit, discard the snapshot and restart the chain; never relabel an older snapshot as current.
Before Step 1, require the committed `file-categories`, `stack-validations`, and
`gate1-test-command` regions to contain no `forge-init:` sentinel. For a missing committed file,
missing region, or unfilled region, print `forge: <region> not configured — run /forge:init` with
the affected region name and exit 1. The only missing-HEAD exception is `/forge:init`'s fixed,
plugin-owned first-policy bootstrap flow; it must execute no candidate policy command or prompt.
For every non-mutation executable policy cell, use the FR-149 runner discipline described in Step
2: repository-root working directory, `bash -c <complete-cell> forge`, separate later argv
parameters, an isolated process group, a 65,536-byte combined-output cap, and a fixed 300-second
fail-closed timeout. This applies to stack validations and gate commands as well as invariants.

Only consult an orchestration journal when an open run has been explicitly identified by a run ID
passed by the orchestrator or confirmed by the user. Never infer the latest run. With no explicitly
identified open run, execute the complete chain without journal entries.

Before Step 1, invalidate authorization from any earlier chain attempt:

```bash
rm -f .forge/tmp/commit-authorized
```

This preflight invalidation is not a gate step. It ensures an early classification or validation
failure cannot leave prior authorization usable.

## Step 1 — Classify

1. Run `git status --short`.
2. Resolve the explicit target paths and confirm that this session created or changed every one.
   Stop and ask the user about any path with uncertain ownership.
3. Classify every target against the `file-categories` region. A path may touch multiple categories;
   retain every match.
4. Apply this built-in `control` category independently of the project region:
   `forge-project.md`, `.forge-manifest`, `.codex/**`, `.forge/evals/**`, `AGENTS.md`, `CLAUDE.md`,
   `.claude/settings*.json`, and CI workflow definitions at `.github/workflows/**` or the project's
   equivalent CI paths recorded in `file-categories`. Project configuration may extend this list;
   it must never remove or narrow a built-in entry.

Record the task's declared/decomposed tier as `declared_tier`; it is advisory and may influence
implementer routing only. If the task/journal supplies no tier, leave it absent; the committed
exact-diff derivation remains authoritative. Accept only exact `fast`, `standard`, or `hard` when
one is supplied; stop on any other value.
Do not use it to authorize a gate. Final tier derivation occurs from the exact staged candidate in
Step 4, where gate-time classification may promote this declaration but can never demote it.

If any target is `control`, classify the whole commit as control-class. Control-class work is
`gated-approval`, runs the evaluation harness in Step 2, uses `review-final` in Step 4, and never
commits autonomously.

## Step 2 — Validate

Run the committed `gate1-test-command` first, targeted to the explicit target paths while retaining
its configured always-run blast-radius suite. Invoke its complete command unchanged from the
repository root as exactly one argument to `bash -c`, followed by literal `forge` as `$0` and every
derived repository-relative test path or scope as a separate subsequent argv element consumed via
`"$@"`. Never concatenate or interpolate target paths into the command. Use an isolated process
group, a 65,536-byte combined stdout/stderr cap, and the fixed 300-second timeout. A nonzero exit,
launch failure, output-limit breach, timeout, missing command, or malformed command blocks Step 2.

Run every executable command in the committed `stack-validations` region for every category
touched by the target paths. Run all applicable commands when categories overlap. Prefer execution
evidence over static inspection, and treat any missing applicable command, nonzero exit, malformed
result, or unavailable tool as failure.

Validate the entire committed `invariants` region before executing any row. It accepts only the
table `| invariant | check command | enforcement point |`, with nonempty invariant and command
cells and an enforcement point exactly equal to `commit`, `merge`, or `hook`. An empty command,
malformed row, multi-row command, unknown enforcement point, or otherwise unparseable nonempty
region prints this exact first line and blocks Step 2 without executing any invariant row:

```text
forge: executable policy row malformed
```

Run every `commit` row from the validated table. From the repository root, invoke the complete
command cell unchanged as exactly one argument to `bash -c`, followed by the literal `forge` as
`$0`. Never concatenate, interpolate, source-wrap, or `eval` a command cell. When a check has
parameters, pass each repository-relative path or scope as one subsequent argv element for the
cell to consume through `"$@"`; never splice a path, diff, invariant name, or region text into the
command string. Give every check its own process group, cap combined stdout and stderr at 65,536
bytes, and enforce a 300-second timeout that kills the complete process group.

A nonzero exit, launch failure, or output-limit breach blocks with this exact first line, followed
only by capped diagnostics:

```text
forge: invariant failed (commit): <invariant>
```

A timeout blocks with this exact first line:

```text
forge: invariant timed out (commit): <invariant>
```

Derive every touched test file mechanically from the explicit target paths. When at least one is
touched, run all paths as separate argv elements after `--`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-test-quality.py" -- <touched-test-path>...
```

Exit 1 from the Python AST branch and exit 2 for sensor failure both block Step 2. Exit 0 is a
pass for gate flow, but preserve every non-Python advisory, missing-heuristic notice, and valid
waiver path plus reason in Step 2 and review evidence. A waiver suppresses only that file's
assertion sensor; it never skips tests, mutation checks, invariants, or another file.

For a control-class commit, additionally run:

```bash
STRICT=1 bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/run-evals.sh"
```

An empty or malformed evaluation suite, pending result, or regression blocks the commit. Strict
evaluation is mandatory when a control-class change touches an agent prompt template, the review
constitution, model/effort/sandbox routing, execpolicy rules, or a Codex or Claude model/provider
version.

When an explicitly identified run is open, append one journal `verification` for every validation
execution. Follow `${CLAUDE_PLUGIN_ROOT}/docs/orchestration-contract.md` and DM-001. Use a criterion
beginning exactly `gate-1: ` for project-test executions. Use one beginning exactly `gate-2: ` for
lint, format, static-analysis, type, build, and evaluation-harness executions. If one configured
command covers both concerns, append both gate verifications against that same command, with
evidence specific to each concern. Record the exact command in `check`, the real result and exit
evidence, and append a later passing recheck after any failed execution. Do not fabricate or
collapse distinct gate executions.

## Step 3 — Apply the Changelog Policy

Read and apply the committed `changelog-policy` region exactly. When it requires an entry, update
it and add that exact path to the explicit commit target set before Step 4. When it states that no
changelog gate is configured, report Step 3 as not applicable. Any ambiguity or unmet requirement
blocks the chain unless the user explicitly invokes the matching skip directive.

## Step 4 — Stage, Scan, and Review

Delete any authorization left by an earlier attempt before staging or reviewing:

```bash
rm -f .forge/tmp/commit-authorized
```

Repeat that deletion whenever Step 4 restarts. A secret finding, reviewer launch failure,
unavailable reviewer, BLOCK, ambiguous verdict, hash mismatch, rejected control approval, or
iteration-cap escalation leaves no authorization marker behind. A marker from an earlier PASS is
never evidence for the current attempt, even when the staged bytes happen to be identical.

Stage only the explicit target paths:

```bash
git add -- <target-path>...
```

Do not use blanket staging. Confirm that the staged set contains only the target paths. The sole
review input is the exact stdout of:

```bash
git diff --cached
```

Before sending any staged-diff bytes to a reviewer, scan the entire staged patch for API keys,
tokens, passwords, private keys, credentials, and staged environment-file contents, using the
repository's configured secret scanner when present plus direct inspection for obvious secrets. A
finding BLOCKS the chain. Do not send or echo the value. Unstage every affected file with
`git restore --staged -- <affected-path>...`, inform the user which paths were affected, and stop.
Never redact, omit, or silently exclude a file from review while leaving it staged.

Immediately before reviewer launch, compute the candidate identity:

```bash
set -o pipefail
if ! reviewed_diff_sha256="$(git diff --cached | shasum -a 256 | awk '{print $1}')"; then
  echo "forge: could not hash staged diff — review blocked" >&2
  exit 1
fi
```

Before selecting a reviewer, mechanically classify those exact staged bytes against the same
committed policy snapshot. Invoke the shared classifier with the full immutable revision and the
advisory declaration; its default diff is the index, so do not pass working-tree paths or a
different range:

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
  --repo "$PWD" --policy-sha "$policy_sha" --staged \
  "${declared_args[@]}")" || exit 1
effective_tier="$(python3 -c \
  'import json,sys; value=json.load(sys.stdin).get("effective_tier"); sys.exit(2) if value not in {"fast","standard","hard"} else print(value)' \
  <<<"$TIER_EVIDENCE")" || {
  echo "forge: invalid risk-tier evidence" >&2
  exit 1
}
```

Preserve the classifier's compact JSON object as gate evidence. It must identify the exact staged
path list, every matched tier/trigger/category row, every formatting-category decision, the
dependency-floor decision, `declared_tier`, `derived_tier`, promote-only `effective_tier`, and the
full `policy_sha`. Treat an unknown tier as failure. `effective_tier` is the higher of declared and
derived (`hard > standard > fast`): no gate-time demotion is possible. The classifier applies the
non-narrowable hard floor formed by the built-in and project-extended control category plus every
`trigger-paths` match; a malformed nonempty trigger row makes the whole candidate hard. A path
matching no tier row defaults to standard. The committed dependency-manifest block and unknown
manifest membership impose at least standard, and the formatting-only exclusion/predicate in
FR-156 cannot be relaxed by project rows. Never reconstruct, narrow, or override any classifier
floor in this skill.

Route the review as follows:

- `fast`: skip only this adversarial reviewer. Continue every remaining Step 4 operation and all of
  Step 5; fast never skips classification, validation, invariants, assertion-quality, changelog,
  secret scan, halt, lock, staged-diff re-verification, guard recomputation, or the marker.
- `standard`: launch a fresh, read-only Codex `review-cheap` execution with the complete iteration
  protocol below. When an explicitly identified run is open, record it before launch.
- `hard`: launch the `review-final` Claude agent. Every control or trigger-path match is hard, and
  control-class hard candidates retain explicit candidate-bound human approval.

When a reviewer is required, it must be a distinct agent from the author. A reused author context,
unavailable reviewer, launch error, missing verdict, or anything other than explicit PASS/BLOCK is
not a PASS. On each BLOCK, first preserve the primary BLOCK result, then make exactly one advisory
append attempt with `emit-decision-event.py` using event `review_block`, candidate
`$reviewed_diff_sha256`, full `$policy_sha`, surface `/forge:commit`, and a stable non-secret reason. Do not
let event failure change the BLOCK outcome or its exit status.

Give the reviewer the following upstream review instruction. Replace each angle-bracket slot with
the byte-for-byte interior of the named region from the committed HEAD snapshot obtained at chain
start; do not source the content elsewhere:

```text
Review these changes adversarially using `${CLAUDE_PLUGIN_ROOT}/rules/review-constitution.md`.

Apply all 8 lenses (Ambiguity, Incompleteness, Inconsistency, Infeasibility, Insecurity,
Inoperability, Incorrectness, Overcomplexity) as the baseline, and additionally apply the
matching per-artefact profile — select it from the profiles table in the constitution
(e.g. review-coding for code+tests, review-deployment for infra/IaC, review-documentation
for docs). The profile extends the baseline; it never lets you skip a lens. Pay special attention to:
- Hallucinated function/method/module names that don't exist (COR-07)
- Plausible-looking but incorrect logic (COR-05)
- Missing error handling or edge cases (INC-01, INC-07)
- Security issues (SEC-06: secrets in logs, SEC-05: input validation, SEC-12: template injection)

<review-prompt-project-focus region body>

Apply every matching project trigger:
<project-triggers region body>

Include every project-specific completeness item:
<completeness-project-items region body>

Format findings with principle IDs (e.g., [SEC-06] CRITICAL: ...).
Complete the Review Completeness Check.
Provide PASS or BLOCK verdict with severity-ranked findings.
```

Provide no review payload beyond that instruction, its three spliced region bodies, and the exact
`git diff --cached` output. Do not substitute a summary, unstaged diff, commit range, handoff, or
author's claimed results.

After the verdict, recompute the staged-diff hash:

```bash
if ! current_diff_sha256="$(git diff --cached | shasum -a 256 | awk '{print $1}')"; then
  echo "forge: could not re-hash staged diff — review blocked" >&2
  exit 1
fi
test "$current_diff_sha256" = "$reviewed_diff_sha256" || exit 1
```

If that comparison fails, discard the verdict and restart Step 4. Any staging change after review
invalidates the candidate and requires a new secret scan and review.

For each BLOCK, address every MAJOR or CRITICAL finding or consciously disposition it before the
next review. Dispositioning any finding above MINOR requires explicit user approval; never
self-approve it. After any fix, re-run the affected Step 2 validations before staging the fix and
launching a fresh re-review. One reviewer invocation is one iteration. Stop after at most 8 review
iterations. If iteration 8 does not PASS, record the outstanding findings and why they remain as
residual risk, escalate to the user, and never commit.

When an explicitly identified run is open, append a journal gate verification for every Step 4
review. Its criterion must be exactly `gate-3: review-final verdict`; its `check` must name
the exact 64-hex value held in `reviewed_diff_sha256`, not the variable name; a BLOCK uses
`result: "failed"` and records the verdict and finding count in `observation`. Thread that same
SHA-256 unchanged into the gate-pass marker and any control-class approval prompt.

After PASS and a matching post-review hash, capture `reviewed_at` immediately as the actual verdict
time:

```bash
reviewed_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
```

For fast, perform the same post-classification staged-diff re-hash immediately before capturing
`reviewed_at`; any mismatch restarts Step 4 and reclassifies the replacement candidate. Here the
timestamp is the mechanical fast authorization time, not a review verdict time.

For a control-class commit, present the change, PASS verdict, and that exact SHA-256 to the user,
then wait for explicit approval naming the reviewed candidate. Keep the authorization marker absent
while waiting; a PASS alone does not authorize a control commit. After approval, recompute the
staged-diff SHA-256 and require it to equal `reviewed_diff_sha256`. If the staged diff changed or the
captured PASS time is now older than 30 minutes, delete any marker and restart Step 4. A refusal or
anything other than explicit candidate-bound approval leaves the marker absent and stops the chain.
Do not enter Step 5 autonomously.

Only after any required control approval and the final matching hash, write the marker:

```bash
mkdir -p .forge/tmp
printf '%s\n%s\n' "$reviewed_diff_sha256" "$reviewed_at" > .forge/tmp/commit-authorized
```

The review-PASS marker has exactly two lines: the reviewed staged-diff SHA-256 and the UTC PASS
timestamp. For an eligible fast candidate, instead write exactly this four-line marker, using the
same full policy revision that supplied every tier region:

```bash
printf '%s\n%s\n%s\n%s\n' "$reviewed_diff_sha256" "$reviewed_at" \
  'tier: fast' "policy: $policy_sha" > .forge/tmp/commit-authorized
```

The only other valid shape is the exact three-line user-skip marker below. Any missing marker,
other line count, malformed hash or timestamp, duplicated/combined/reordered annotation, or
unexpected value is invalid. The fast annotation is a guard input, never proof: the commit guard
independently validates policy ancestry and byte continuity and recomputes eligibility from the
exact staged diff.

## Step 5 — Halt, Lock, Re-verify, Commit, Release

Set `commit_message` to the exact descriptive message before running this sequence. Run the halt
check first, acquire the commit lock second, re-hash inside the lock, commit only on an exact marker
match, and release the lock after both successful and failed commit attempts:

```bash
commit_marker='.forge/tmp/commit-authorized'
export FORGE_SESSION_PID=$$
lock_maybe_acquired=0

release_commit_gate() {
    release_status=0
    marker_status=0
    if [ "$lock_maybe_acquired" -eq 1 ]; then
        bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/release-commit-lock.sh" || release_status=$?
    fi
    rm -f "$commit_marker" || {
        marker_status=$?
        echo "forge: failed to consume commit authorization marker: $commit_marker" >&2
    }
    if [ "$release_status" -ne 0 ]; then
        return "$release_status"
    fi
    return "$marker_status"
}
trap 'release_commit_gate' EXIT
trap 'exit 1' HUP INT TERM

bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh" commit || exit 1
lock_maybe_acquired=1
bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/acquire-commit-lock.sh" || exit 1

if ! python3 - "$commit_marker" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import re
import sys


def deny(reason: str) -> None:
    print(
        f"forge: commit not authorized — run /forge:commit (marker {reason})",
        file=sys.stderr,
    )
    raise SystemExit(1)


marker = Path(sys.argv[1])
try:
    lines = marker.read_text(encoding="utf-8").splitlines()
except (FileNotFoundError, OSError, UnicodeError):
    deny("missing" if not marker.exists() else "malformed")

if len(lines) not in (2, 3, 4):
    deny("malformed")
if len(lines) == 3 and lines[2] != "skip: user-directed":
    deny("malformed")
if len(lines) == 4:
    if lines[2] != "tier: fast" or re.fullmatch(
        r"policy: (?:[0-9a-f]{40}|[0-9a-f]{64})", lines[3]
    ) is None:
        deny("malformed")
if re.fullmatch(r"[0-9a-f]{64}", lines[0]) is None:
    deny("malformed")
try:
    passed_at = datetime.strptime(lines[1], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
except ValueError:
    deny("malformed")
if (datetime.now(timezone.utc) - passed_at).total_seconds() > 1800:
    deny("stale")
PY
then
    exit 1
fi

authorized_hash="$(sed -n '1p' "$commit_marker")"
set -o pipefail
if ! current_hash="$(git diff --cached | shasum -a 256 | awk '{print $1}')"; then
    echo "forge: could not hash staged diff — commit blocked" >&2
    exit 1
fi
if [ "$current_hash" != "$authorized_hash" ]; then
    echo "forge: staged diff changed after review — re-run Step 4" >&2
    exit 1
fi

git commit -m "$commit_message"
commit_status=$?
if [ "$commit_status" -eq 0 ]; then
    committed_sha="$(git rev-parse HEAD)" || commit_status=$?
fi

release_commit_gate
release_status=$?
trap - EXIT HUP INT TERM
if [ "$commit_status" -ne 0 ]; then
    exit "$commit_status"
fi

# The successful commit outcome above is already final. Event writes are advisory.
event_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/emit-decision-event.py" \
  --at "$event_at" --candidate "$committed_sha" --event gate_commit \
  --policy-sha "$policy_sha" --reason '' --surface /forge:commit || :
if [ "$effective_tier" = fast ]; then
    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/emit-decision-event.py" \
      --at "$event_at" --candidate "$committed_sha" --event fast_allowed \
      --policy-sha "$policy_sha" --reason '' --surface /forge:commit || :
fi
if [ "$release_status" -ne 0 ]; then
    exit "$release_status"
fi
exit 0
```

The cleanup trap is active before the halt check and remains active through explicit release, so a
halt, lock-acquisition failure, later failure, or interruption invalidates the marker. It invokes
the release script once acquisition might have started; that script removes only a matching
`FORGE_SESSION_PID` lock and refuses a foreign owner. Failure to delete the authorization marker is
itself a Step 5 failure; lock-release failure takes precedence when both cleanup operations fail.

The acquire script owns `.forge/tmp/commit-lock`, whose record format is `<PID> <TIMESTAMP>` and
whose owner is `FORGE_SESSION_PID`. It owns stale-PID takeover, 2-second polling, and the 300-second
timeout. Never hold the lock across Step 4. The release path and marker deletion are mandatory
whether commit succeeds, commit fails, hash verification detects restaging, or the shell receives
an interruption. A hash mismatch means staging drifted: do not commit; restart Step 4. Never create,
delete, or bypass an operator halt sentinel without explicit user direction.

Step 5 accepts only an exact two-line standard/hard PASS marker, exact three-line user-skip marker,
or exact four-line fast marker younger than 30 minutes. It fails closed on a missing, malformed, or
stale marker before committing. The PreToolUse commit guard independently enforces freshness and
shape and recomputes fast eligibility at `git commit`; never bypass or reinterpret its decision.

The two post-success calls occur only after the commit succeeds and mandatory marker cleanup has
run; a release diagnostic may already have been reported without retracting that commit. `gate_commit` supplies the eligible-commit denominator; a fast commit additionally owns
the sole `fast_allowed` event. The emitter holds `.forge/tmp/events.lock` only for its one compact
sorted-key JSONL append, with its local 2-second polling and hard 5-second bound. Its stable timeout
code is `event-append-lock-timeout`. A timeout, append failure, or release failure may be reported
but must never change, undo, or misreport the already-delivered commit result. Downstream
aggregation deduplicates both events by `(event, candidate)` when the resulting full commit SHA is
nonempty.

## User-Directed Skips

Map skip directives exactly:

| User directive | Skip exactly |
|---|---|
| `"skip tests"` or `"skip validation"` | Step 2 |
| `"skip changelog"` | Step 3 |
| `"skip review"` | Step 4 |
| `"just commit"` or `"skip everything"` | Steps 2–4 |

Warn in the reply about every skipped step. Do not infer a skip from urgency or convenience. Steps
1 and 5 are never skipped by these directives. Record every user-directed skip durably as soon as
the directive is accepted, before the next step can fail, including a Step 2-only or Step 3-only
skip. First deliver acceptance of the skip as the primary outcome, then make exactly one advisory
`user_skip` event attempt through `emit-decision-event.py` using the staged-diff SHA-256 when staged
state is available (otherwise `""`), the full `policy_sha`, surface `/forge:commit`, and a stable non-secret
reason identifying the mapped skip. Event failure never retracts the accepted skip or changes any
subsequent gate status. When an explicitly identified run is open, append a journal `decision` naming the user's
directive, skipped steps, candidate SHA-256 when already available, and user authority. With no such
run, append the audit line shown below immediately.

For a Step 4 skip, first delete any earlier authorization marker. Still stage only the explicit
target paths and secret-scan the staged candidate; do not launch a reviewer. Hash the current staged
diff and capture the skip time, but do not write the marker yet:

```bash
rm -f .forge/tmp/commit-authorized
mkdir -p .forge/tmp
set -o pipefail
if ! reviewed_diff_sha256="$(git diff --cached | shasum -a 256 | awk '{print $1}')"; then
  echo "forge: could not hash staged diff — review skip blocked" >&2
  exit 1
fi
reviewed_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
```

For a control-class candidate, present the staged change, skip warning, and exact SHA-256 while the
marker remains absent. Wait for explicit user approval naming that candidate SHA-256 before Step 5.
A skip directive never supplies that approval, and control-class commits are never autonomous. After
approval, recompute the staged-diff SHA-256 and require the same value. If staging changed, approval
was refused, or the captured skip time is now older than 30 minutes, keep the marker absent and stop
or restart Step 4 as applicable.

Only after that control approval when required, write the user-directed marker:

```bash
printf '%s\n%s\n%s\n' "$reviewed_diff_sha256" "$reviewed_at" 'skip: user-directed' > .forge/tmp/commit-authorized
```

The third line must be exactly `skip: user-directed`, so this marker has exactly three lines. This
is a skip marker, never review-backed evidence. For every skip with no explicitly identified run,
set `skipped_steps` to the
exact mapped step string and append this audit line:

```bash
mkdir -p .forge/tmp
printf '%s skip: user-directed (pid %s, steps %s)\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$$" "$skipped_steps" >> .forge/tmp/halt-audit.log
```

Do not infer a journal run for the skip record. Continue through Step 5, where the in-lock hash
re-verification and mandatory release still apply.

## Orchestrated Checkpoints

When the workflow identifies an open run explicitly, use its run ID for all Step 2 and Step 4
records and for any skip decision. A checkpoint commit is mandatory after every verified task; the
orchestrator invokes this skill with that task's explicit files and run ID. Agent claims are not
gate evidence: record only executions and results observed under the journal contract.
