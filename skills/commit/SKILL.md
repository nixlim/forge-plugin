---
name: commit
description: Run the five-step fail-closed forge commit gate chain over explicit target paths.
---

# Commit Gate Chain

Run this skill for every commit. Execute Steps 1–5 in order. Do not reorder, omit, or treat an
unavailable command or reviewer as a PASS. Any non-skipped failure stops the chain, surfaces the
failure, and leaves the change uncommitted when Git has not already produced it. The sole
post-production mismatch path leaves the divergent commit untouched for operator disposition.
Hold the commit lock only during Step 5, never during the Step 4 review loop.

Resolve all project gate configuration from one authenticated committed revision. At the start of
the chain, set `policy_sha` to the full result of `git rev-parse HEAD`, load the policy only with
`git show "${policy_sha}:forge-project.md"`, and use only those returned bytes for every policy read
in Steps 1–4, including classification, executable commands, changelog policy, review context,
invariants, `risk-tiers`, its fixed `FORGE:DEPENDENCY-MANIFEST-PATHS` block, `trigger-paths`, and
`file-categories`, and `reviewer-facing-eval-triggers`. Never open the working-tree
`forge-project.md`, a rendered copy, or duplicated defaults for policy. Keep the full `policy_sha`
with the gate evidence. If HEAD changes before the commit, discard the snapshot and restart the
chain; never relabel an older snapshot as current.
Before Step 1, require the committed `file-categories`, `stack-validations`, and
`gate1-test-command` regions to contain no `forge-init:` sentinel. For a missing committed file,
missing region, or unfilled region, print `forge: <region> not configured — run /forge:init` with
the affected region name and exit 1. The only missing-HEAD exception is `/forge:init`'s fixed,
plugin-owned first-policy bootstrap flow; it must execute no candidate policy command or prompt.
For every non-mutation executable policy cell, use the FR-149 runner discipline described in Step
2: repository-root working directory, `bash -c <complete-cell> forge`, separate later argv
parameters, an isolated process group, a 65,536-byte combined-output cap, and a fixed 1200-second
fail-closed timeout. This applies to stack validations and gate commands as well as invariants.

Only consult an orchestration journal when an open run has been explicitly identified by a run ID
passed by the orchestrator or confirmed by the user. Never infer the latest run. With no explicitly
identified open run, execute the complete chain without journal entries.

Before Step 1, compute no candidate and write no authorization. Authorization is a content-addressed
identity of the complete index tree, while its deterministic tree-to-tree patch has a separate
review-evidence digest. An earlier authorization ID cannot authorize a different tree; when this
chain later identifies a candidate, it owns only that marker path and must leave every other
agent's marker untouched.

```bash
authorization_id=''
candidate_object_format=''
candidate_tree_oid=''
candidate_base_commit_oid=''
review_diff_sha256=''
review_diff_byte_count=''
review_artifact=''
commit_marker=''
```

This preflight initialization is not a gate step.

## Step 1 — Classify

1. Run `git status --short`.
2. Resolve the explicit target paths and confirm that this session created or changed every one.
   Stop and ask the user about any path with uncertain ownership.
3. Classify every target against the `file-categories` region. A path may touch multiple categories;
   retain every match.
4. Apply this built-in `control` category independently of the project region:
   `forge-project.md`, `.forge-manifest`, `.codex/**`, `.forge/evals/tasks/**` including baselines,
   `AGENTS.md`, `CLAUDE.md`,
   `.claude/settings*.json`, and CI workflow definitions at `.github/workflows/**` or the project's
   equivalent CI paths recorded in `file-categories`. Project configuration may extend this list;
   it must never remove or narrow a built-in entry. `.forge/evals/candidates/**` is the sole
   eval-path exception: treat it as advisory/docs-class and never as `control`, even when an older
   or broader project `control` pattern would match it. Moving or copying a candidate into
   `.forge/evals/tasks/**`, or creating or changing its baseline there, is control-class promotion.

Record the task's declared/decomposed tier as `declared_tier`; it is advisory and may influence
implementer routing only. If the task/journal supplies no tier, leave it absent; the committed
exact-diff derivation remains authoritative. Accept only exact `fast`, `standard`, or `hard` when
one is supplied; stop on any other value.
Do not use it to authorize a gate. Final tier derivation occurs from the exact staged candidate in
Step 4, where gate-time classification may promote this declaration but can never demote it.

If any target is `control`, classify the whole commit as control-class. Control-class work is
`gated-approval`, runs Recorded-baseline integrity in Step 2, runs Candidate-bound fresh reviewer
evaluation after the Step 4 snapshot when the authenticated trigger matches, uses `review-final`
in Step 4, and never commits autonomously.

## Step 2 — Validate

Run the committed `gate1-test-command` first, targeted to the explicit target paths while retaining
its configured always-run blast-radius suite. Invoke its complete command unchanged from the
repository root as exactly one argument to `bash -c`, followed by literal `forge` as `$0` and every
derived repository-relative test path or scope as a separate subsequent argv element consumed via
`"$@"`. Never concatenate or interpolate target paths into the command. Use an isolated process
group, a 65,536-byte combined stdout/stderr cap, and the fixed 1200-second timeout. A nonzero exit,
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
bytes, and enforce a 1200-second timeout that kills the complete process group.

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

After preserving the sensor's primary result, retain each surfaced disposition until Step 4 has
computed the exact `authorization_id`. Then make exactly one advisory
`emit-decision-event.py` append attempt for each surfaced result: `assertion_blocking` for each
blocking finding, `assertion_advisory` for each advisory finding, absence, or inconclusive
disposition, and `assertion_waived` for each accepted per-file waiver. Use
`$authorization_id` as `--candidate`, the full `$policy_sha`, surface `/forge:commit`, and a
stable non-secret finding/disposition code as `--reason`. A clean sensor result with no surfaced
advisory disposition emits no assertion event. Event emission is advisory and occurs only after
the sensor result is preserved; an emitter failure never changes Step 2's result or exit status.

For every control-class commit, additionally run Recorded-baseline integrity in strict mode:

```bash
STRICT=1 bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/run-evals.sh"
```

An empty or malformed evaluation suite, missing result, or mismatched expected/result pair blocks
the commit. This mechanical layer proves only that the committed suite is nonempty and structurally
valid and that its recorded pairs agree; it does not launch an agent or claim that a reviewer still
produces the expected judgment. It is mandatory for every control-class candidate and no user skip
directive covers it.

Candidate-bound fresh reviewer evaluation is a separate Gate-2 requirement. Its applicability can
be decided only after Step 4 creates the v2 snapshot. The later Step 4 procedure derives that
decision solely from the snapshot's exact immutable path set and the authenticated
`reviewer-facing-eval-triggers` region; this skill must not restate, reconstruct, or maintain a
second trigger path list.

When an explicitly identified run is open, append one journal `verification` for every validation
execution. Follow `${CLAUDE_PLUGIN_ROOT}/docs/orchestration-contract.md` and DM-001. Use a criterion
beginning exactly `gate-1: ` for project-test executions. Use one beginning exactly `gate-2: ` for
lint, format, static-analysis, type, build, Recorded-baseline integrity, and Candidate-bound fresh
reviewer evaluation executions. A fresh-evaluation verification criterion is exactly
`gate-2: fresh reviewer evaluation`. If one configured command covers both concerns, append both
gate verifications against that same command, with evidence specific to each concern. Record the
exact command in `check`, the real result and exit evidence, and append a later passing recheck after
any failed execution. Do not fabricate or collapse distinct gate executions.

## Step 3 — Apply the Changelog Policy

Read and apply the committed `changelog-policy` region exactly. When it requires an entry, update
it and add that exact path to the explicit commit target set before Step 4. When it states that no
changelog gate is configured, report Step 3 as not applicable. Any ambiguity or unmet requirement
blocks the chain unless the user explicitly invokes the matching skip directive.

## Step 4 — Stage, Scan, and Review

Clear every candidate variable before staging or reviewing. Do not delete a marker belonging to a
different candidate:

```bash
authorization_id=''
candidate_object_format=''
candidate_tree_oid=''
candidate_base_commit_oid=''
review_diff_sha256=''
review_diff_byte_count=''
review_artifact=''
commit_marker=''
```

Repeat that reset whenever Step 4 restarts. A secret finding, reviewer launch failure,
unavailable reviewer, BLOCK, ambiguous verdict, identity mismatch, rejected control approval, or
iteration-cap escalation leaves no authorization marker behind. A marker from an earlier PASS is
never evidence for the current attempt, even if a later generation recreates the same tree.

Stage only the explicit target paths:

```bash
git add -- <target-path>...
```

Do not use blanket staging. Confirm that the staged set contains only the target paths. Immediately
after staging, create one immutable v2 snapshot with the shared candidate helper. Put the exact
`snapshot.review_diff` bytes in an owner-controlled mode-0600 artifact and retain the returned
authorization ID, object format, candidate tree OID, base commit OID, review digest, byte count,
raw/UTF-8 path lists, and resolved common checkout root. Parse JSON with a JSON parser; never `eval`
helper output.

```bash
review_artifact="$(mktemp "${TMPDIR:-/tmp}/forge-review.XXXXXX")" || exit 1
candidate_metadata="$(python3 - "$review_artifact" <<'PY'
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "scripts" / "forge"))
from forge_cli import candidate

context = candidate.discover_context(Path.cwd())
snapshot = candidate.snapshot(
    context,
    computed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
)
artifact = Path(sys.argv[1])
artifact.write_bytes(snapshot.review_diff)
os.chmod(artifact, 0o600)
print(json.dumps({
    "authorization_id": snapshot.authorization_id,
    "object_format": snapshot.object_format,
    "tree_oid": snapshot.tree_oid,
    "base_commit_oid": snapshot.base_commit_oid,
    "review_diff_sha256": snapshot.review_diff_sha256,
    "review_diff_byte_count": snapshot.review_diff_byte_count,
    "paths": snapshot.paths,
    "forge_main_root": str(context.common_dir.parent),
}, sort_keys=True, separators=(",", ":")))
PY
)" || exit 1
```

Set the shell variables above from those exact JSON fields, and require
`candidate_base_commit_oid` to equal the chain's pinned `policy_sha`; otherwise discard the snapshot
and restart from the new HEAD. Set
`commit_marker="$forge_main_root/.forge/tmp/authorized/$authorization_id"`. Before review, inspect
only that same-candidate path and its exact sibling `<authorization-id>.quarantine` with
`candidate.marker_timestamp_for_cleanup(...)`. Delete them only when that shared helper returns a
marker timestamp more than 30 minutes old, removing the authorization marker first and then its
quarantine latch. A fresh marker may be retained evidence of an already-produced mismatch, and an
unparseable or future-dated marker or a quarantine without its marker is ambiguous; leave those
entries byte-for-byte untouched and stop for operator inspection. This makes the produced-mismatch
retention survive a later `/forge:commit` attempt instead of silently consuming it. The helper's
bounded, pinned context and deterministic tree pair are the identity
implementation; do not reproduce its domain-separated hash, run a presentation diff to derive
authorization, or substitute a separately rendered path list.

```bash
test "$candidate_base_commit_oid" = "$policy_sha" || exit 1
python3 - "$commit_marker" <<'PY'
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "scripts" / "forge"))
from forge_cli import candidate

marker = Path(sys.argv[1])
quarantine = Path(f"{marker}.quarantine")
try:
    quarantine.lstat()
except FileNotFoundError:
    quarantined = False
except OSError:
    print("forge: existing candidate marker requires operator disposition", file=sys.stderr)
    raise SystemExit(2)
else:
    quarantined = True
try:
    with marker.open("rb") as stream:
        raw = stream.read(4097)
except FileNotFoundError:
    if quarantined:
        print("forge: existing candidate marker requires operator disposition", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(0)
except OSError:
    print("forge: existing candidate marker requires operator disposition", file=sys.stderr)
    raise SystemExit(2)
if len(raw) > 4096:
    print("forge: existing candidate marker requires operator disposition", file=sys.stderr)
    raise SystemExit(2)
authorized_at = candidate.marker_timestamp_for_cleanup(raw)
if authorized_at is None:
    print("forge: existing candidate marker requires operator disposition", file=sys.stderr)
    raise SystemExit(2)
age_seconds = (datetime.now(timezone.utc) - authorized_at).total_seconds()
if age_seconds <= 1800:
    print("forge: existing authorization marker is not stale — inspect prior commit outcome", file=sys.stderr)
    raise SystemExit(2)
try:
    marker.unlink()
except OSError:
    print("forge: failed to consume stale commit authorization marker", file=sys.stderr)
    raise SystemExit(1)
if quarantined:
    try:
        quarantine.unlink()
    except OSError:
        print("forge: failed to consume stale commit quarantine latch", file=sys.stderr)
        raise SystemExit(1)
PY
```

Before sending any review bytes, scan the complete immutable review artifact for API keys, tokens,
passwords, private keys, credentials, and environment-file contents, using the repository's
configured secret scanner when present plus direct inspection for obvious secrets. A finding
BLOCKS the chain. Do not send or echo the value. Unstage every affected path with
`git restore --staged -- <affected-path>...`, remove this attempt's artifact and marker, inform the
user which paths were affected, and stop. Never redact, omit, regenerate, or silently exclude a
path while leaving it staged. Before the scanner and again before reviewer launch, require the
artifact's byte count and SHA-256 to equal the snapshot metadata; a changed artifact restarts Step
4. For an explicitly identified run, copy those exact verified bytes into that run's execution
directory before citing them. Otherwise remove the temporary artifact when the attempt terminates.

After the immutable artifact passes the secret scan, derive fresh-evaluation applicability with the
shared policy parser and evaluator. Supply only the pinned `policy_sha` policy bytes and the exact
bytewise-sorted `snapshot.paths`; never use target arguments, `git status`, working-tree paths, or a
locally duplicated pattern list. A missing or malformed authenticated
`reviewer-facing-eval-triggers` region blocks every control-class chain. For the fixed plugin-owned
first-policy bootstrap, where no authenticated base region exists, treat applicability as
unconditionally true and run the complete supported fresh-review fixture set.

When the derivation returns matches, report the matched control row names sourced from that result,
not a restated list of their path patterns, and run exactly one `fresh-reviewer-evals` Gate-2 suite
request for this candidate generation. Require its canonical manifest to validate and its outcome
to be `PASS` while naming this snapshot's authorization ID, object format, tree OID, base commit,
review-diff digest, and byte count. Exit 1 is a reviewer-verdict mismatch and blocks this generation;
exit 2, absent evidence, stale or foreign binding, an unavailable reviewer, or any other non-PASS
result fails closed. An unchanged candidate must not rerun a complete mismatch to seek a different
judgment. A changed candidate restarts Step 4 and receives a new snapshot and request.

This fresh suite is distinct from both Recorded-baseline integrity and the one binding reviewer
selected below. Neither can satisfy the other. `fresh-reviewer-evals` follows the ordinary
mechanical-gate skip rule: only explicit operator direction durably recorded on the current
candidate's chain may waive the PASS requirement above; no fast classification, broad
user-directed step skip, CI result, later review, or approval can substitute for that record.

Before selecting a reviewer, mechanically classify the snapshot's exact immutable path/tree
evidence against the same committed policy snapshot. Invoke the shared classifier with the full
immutable revision and the advisory declaration, then require its path set to equal
`snapshot.paths` and use `candidate.observe_index(context)` to prove that the live index still has
the same object format, tree OID, and authorization ID:

```bash
declared_tier="${declared_tier:-}"
declared_args=()
if [ -n "$declared_tier" ]; then
  case "$declared_tier" in
    fast|standard|hard) declared_args=(--declared-tier "$declared_tier") ;;
    *) echo "forge: invalid declared risk tier: $declared_tier" >&2; exit 1 ;;
  esac
fi
TIER_EVIDENCE="$(
  FORGE_CANDIDATE_SCHEMA=forge-commit-candidate/2 \
  FORGE_CANDIDATE_AUTHORIZATION_ID="$authorization_id" \
  FORGE_CANDIDATE_OBJECT_FORMAT="$candidate_object_format" \
  FORGE_CANDIDATE_TREE_OID="$candidate_tree_oid" \
  FORGE_CANDIDATE_BASE_COMMIT_OID="$candidate_base_commit_oid" \
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/risk_tier.py" \
    --repo "$PWD" --policy-sha "$policy_sha" --staged \
    "${declared_args[@]}"
)" || exit 1
effective_tier="$(printf '%s\n%s\n' "$candidate_metadata" "$TIER_EVIDENCE" | python3 -c '
import json
import sys

lines = sys.stdin.read().splitlines()
if len(lines) != 2:
    raise SystemExit(2)
metadata, evidence = map(json.loads, lines)
expected_paths = metadata.get("paths")
path_evidence = evidence.get("paths")
if not isinstance(expected_paths, list) or not isinstance(path_evidence, list):
    raise SystemExit(2)
try:
    observed_paths = [item["path"] for item in path_evidence]
except (KeyError, TypeError):
    raise SystemExit(2)
if observed_paths != expected_paths or evidence.get("policy_sha") != sys.argv[1]:
    raise SystemExit(2)
value = evidence.get("effective_tier")
if value not in {"fast", "standard", "hard"}:
    raise SystemExit(2)
print(value)
' "$policy_sha")" || {
  echo "forge: invalid risk-tier evidence" >&2
  exit 1
}
```

Preserve the classifier's compact JSON object as gate evidence and bind it alongside the snapshot's
authorization ID and review-evidence digest. The classifier object must identify the exact snapshot
path list, every matched tier/trigger/category row, every formatting-category decision, the
dependency-floor decision, `declared_tier`, `derived_tier`, promote-only `effective_tier`, and the
full `policy_sha`. Treat an unknown tier or any snapshot/path mismatch as failure. `effective_tier`
is the higher of declared and derived (`hard >
standard > fast`): no gate-time demotion is possible. The classifier applies the
non-narrowable hard floor formed by the built-in and project-extended control category, after the
sole `.forge/evals/candidates/**` carve-out above, plus every `trigger-paths` match;
a malformed nonempty trigger row makes the whole candidate hard. A path
matching no tier row defaults to standard. The committed dependency-manifest block and unknown
manifest membership impose at least standard, and the formatting-only exclusion/predicate in
FR-156 cannot be relaxed by project rows. Never reconstruct, narrow, or override any classifier
floor in this skill.

Route the review as follows:

- `fast`: skip only this adversarial reviewer. Continue every remaining Step 4 operation and all of
  Step 5; fast never skips classification, validation, invariants, assertion-quality, changelog,
  secret scan, halt, lock, index-tree re-observation, guard recomputation, produced-commit
  verification, or the marker.
- `standard`: launch a fresh, read-only Codex `review-cheap` execution with the complete iteration
  protocol below. Use the canonical committed-only prompt construction and preparation in
  [`orchestrate`](../orchestrate/SKILL.md#forge-isolation-and-prompt-construction), with the same
  repository worktree used to create the immutable review artifact, recorded for the execution, and passed to
  `-C`.
  When an explicitly identified run is open, record it before launch.
- `hard`: launch the `review-final` Claude agent. Every control or trigger-path match is hard, and
  control-class hard candidates retain explicit candidate-bound human approval. This reviewer is
  instruction-bounded and execution-capable: it shares the writable worktree, may run inspection
  and execution-backed checks, and must never mutate the repository through Bash. Its missing
  Edit/Write tools are not an OS-level read-only sandbox.

When a reviewer is required, it must be a distinct agent from the author. A reused author context,
unavailable reviewer, launch error, missing verdict, or anything other than explicit PASS/BLOCK is
not a PASS. On each BLOCK, first preserve the primary BLOCK result, then make exactly one advisory
append attempt with `emit-decision-event.py` using event `review_block`, candidate
`$authorization_id`, full `$policy_sha`, surface `/forge:commit`, and a stable non-secret reason. Do not
let event failure change the BLOCK outcome or its exit status.

After preserving each reviewer's complete primary verdict and findings, make exactly one advisory
event append attempt per finding that invocation raised. A `review-cheap` invocation uses
`review_cheap_finding`; a `review-final` invocation uses `review_final_finding`. Pass the exact
`$authorization_id` as `--candidate`, the full `$policy_sha`, surface `/forge:commit`, and the
finding's normalized stable severity (`CRITICAL`, `MAJOR`, or `MINOR`) as `--reason`. Count findings
from every invocation, including a BLOCK later superseded by a fresh review. A reviewer invocation
with no findings emits no finding event. These attempts occur after the verdict and findings are
preserved and remain advisory: an emitter failure never changes the verdict, iteration, or exit
status.

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

Beyond the mandatory FR-037 plugin role template, committed `agent-project-context`, and optional
committed `.forge/history/gotchas.md` prefix, provide no task-assignment review payload beyond that
instruction, its three spliced region bodies, the snapshot metadata (including both
`authorization_id` and `review_diff_sha256`), and the exact bytes read from `review_artifact`. Do
not substitute a summary, a regenerated or moving-index patch, a commit range, handoff, or the
author's claimed results.

After the verdict, re-observe the index with the shared helper:

```bash
python3 - "$authorization_id" "$candidate_object_format" "$candidate_tree_oid" <<'PY'
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "scripts" / "forge"))
from forge_cli import candidate

context = candidate.discover_context(Path.cwd())
expected = candidate.CandidateObservation(
    object_format=sys.argv[2],
    tree_oid=sys.argv[3],
    authorization_id=sys.argv[1],
)
if candidate.observe_index(context) != expected:
    raise SystemExit(1)
PY
```

If that comparison fails, discard the verdict and restart Step 4. Any index-tree change after
review invalidates the candidate and requires a new snapshot, secret scan, and review. Never retain
an old verdict merely because a later snapshot has the same authorization ID.

For each BLOCK, address every MAJOR or CRITICAL finding or consciously disposition it before the
next review. Dispositioning any finding above MINOR requires explicit user approval; never
self-approve it. After any fix, re-run the affected Step 2 validations before staging the fix and
launching a fresh re-review. One reviewer invocation is one iteration. Stop after at most 8 review
iterations. If iteration 8 does not PASS, record the outstanding findings and why they remain as
residual risk, escalate to the user, and never commit.

When an explicitly identified run is open, append a journal gate verification for every Step 4
review. Its criterion must be exactly `gate-3: review-final verdict`; its `check` must name
both the exact 64-hex `authorization_id` and the separately named `review_diff_sha256`, not either
variable name; a BLOCK uses `result: "failed"`. Normalize and count every finding by `CRITICAL`,
`MAJOR`, and `MINOR`, and
record whether this invocation used `review-cheap` or `review-final`. Record the observation as
exactly `<PASS|BLOCK>; <critical-plus-major-count> CRITICAL/MAJOR findings; severities
CRITICAL=<count>,MAJOR=<count>,MINOR=<count>; reviewer <review-cheap|review-final>; iteration
<number> of 8.` Thread the authorization ID unchanged into the marker and any control-class
approval prompt. The review digest remains evidence of the exact artifact and never authorizes.

After PASS and a matching post-review tree observation, capture `reviewed_at` immediately as the
actual verdict time:

```bash
reviewed_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
```

For fast, perform the same post-classification index-tree re-observation immediately before
capturing `reviewed_at`; any mismatch restarts Step 4 and reclassifies the replacement candidate.
Here the timestamp is the mechanical fast authorization time, not a review verdict time.

For a control-class commit, present the immutable review artifact, PASS verdict, exact
`authorization_id`, object format, tree OID, and review digest to the user, then wait for explicit
approval naming that authorization ID. Keep the marker absent while waiting; review evidence is not
authorization and a PASS alone does not authorize a control commit. After approval, re-observe the
index with the shared helper and require the same object format, tree OID, and authorization ID. If
the tree changed or the captured PASS time is now older than 30 minutes, keep the marker absent and
restart Step 4. A refusal or anything other than explicit candidate-bound approval leaves the
marker absent and stops the chain. Do not enter Step 5 autonomously.

Immediately before writing either authorization-marker shape, validate the stable live
`FORGE_SESSION_PID` inherited from the long-lived harness exactly as DM-010 requires. It must be a
positive base-10 PID that names a live same-host owner in this PID namespace. On missing or
malformed identity, print exactly
`forge: FORGE_SESSION_PID must be exported as a positive base-10 integer`; when the syntactically
valid PID is dead or its liveness cannot be verified, print exactly
`forge: FORGE_SESSION_PID does not name a live same-host session owner`. Stop before marker
mutation in either case. The harness exports this identity; this skill must never export or
substitute shell `$$`, `$PPID`, or a transient tool-process PID for it.

Only after any required control approval and the final matching tree observation, write exactly one
marker through `candidate.render_marker(...)`; do not hand-render or duplicate its grammar. Create
the parent directory mode 0700, create the absent marker mode 0600, and write all returned bytes.
Pass `fast_policy=policy_sha` only for an eligible fast candidate; otherwise pass neither annotation.

The standard/hard marker is exactly four LF-terminated lines:

```text
format: forge-commit-candidate/2
candidate: <64-lowercase-hex authorization-id>
tree: <sha1|sha256>:<full matching tree OID>
authorized-at: <UTC ISO-8601>
```

The eligible-fast marker is exactly six LF-terminated lines:

```text
format: forge-commit-candidate/2
candidate: <64-lowercase-hex authorization-id>
tree: <sha1|sha256>:<full matching tree OID>
authorized-at: <UTC ISO-8601>
tier: fast
policy: <full commit OID>
```

```bash
python3 - "$commit_marker" "$authorization_id" "$candidate_object_format" \
  "$candidate_tree_oid" "$reviewed_at" "$effective_tier" "$policy_sha" <<'PY'
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "scripts" / "forge"))
from forge_cli import candidate

marker = Path(sys.argv[1])
observation = candidate.CandidateObservation(sys.argv[3], sys.argv[4], sys.argv[2])
raw = candidate.render_marker(
    observation,
    sys.argv[5],
    fast_policy=sys.argv[7] if sys.argv[6] == "fast" else None,
)
marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    view = memoryview(raw)
    while view:
        view = view[os.write(descriptor, view):]
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
```

The only other admitted v2 shape is the exact five-line user-skip marker below. Any missing marker,
other line count, malformed format/ID/tree/timestamp, filename mismatch,
duplicated/combined/reordered annotation, or unexpected value is invalid. Bare legacy two-, three-,
or four-line markers are cleanup-only and never authorize after upgrade. The fast annotation is a
guard input, never proof: the guard independently validates policy ancestry and byte continuity and
recomputes eligibility from the exact immutable tree evidence.

## Step 5 — Prepare, Commit, Cleanup

Step 5 is exactly three distinct Bash tool calls in the order below. Set each call's tool working
directory directly to the target repository. Every fresh tool shell inherits the same stable live
`FORGE_SESSION_PID` injected by the long-lived harness; never export or substitute shell `$$`,
`$PPID`, or a transient tool-process PID as that identity. Values carried from Step 4 do not survive
as shell variables: replace each angle-bracket metavariable below with the safely shell-quoted
literal value already observed for this repository and candidate. Before the calls, calculate the
SHA-256 of the exact message body that `--cleanup=verbatim -m` will write: UTF-8 encode the literal
and append one LF only when those bytes do not already end in LF. Carry that value as
`expected_message_sha256`; do not hash a display rendering.

### Tool call 1 — Prepare

The prepare call validates the inherited identity before touching the lock or marker, runs the halt
check, acquires the persistent PID-owned commit lock, and uses the shared candidate helper to parse
the exact v2 marker, enforce its 30-minute TTL, and re-observe the index tree inside the lock. Still
under that lock, current HEAD must equal the snapshot's recorded `candidate_base_commit_oid`; the
captured pre-commit parent is never minted from a later same-tree HEAD. For a six-line fast marker,
also require its policy revision to equal that reviewed base and repeat FR-154's policy-continuity
and immutable-tree fast-eligibility recomputation before preparation succeeds. Bare legacy markers
are never accepted. Its cleanup is failure-only:
arm it before the halt check and disarm it only after every preparation check passes, so success
deliberately leaves the lock and candidate marker in place for the standalone commit call.

```bash
python3 - <<'PY'
import os
import re
import sys


invalid = "forge: FORGE_SESSION_PID must be exported as a positive base-10 integer"
not_live = "forge: FORGE_SESSION_PID does not name a live same-host session owner"
raw_pid = os.environ.get("FORGE_SESSION_PID", "")
if re.fullmatch(r"[1-9][0-9]*", raw_pid) is None:
    print(invalid, file=sys.stderr)
    raise SystemExit(1)
try:
    os.kill(int(raw_pid), 0)
except (OverflowError, OSError):
    print(not_live, file=sys.stderr)
    raise SystemExit(1)
PY

commit_marker=<safely-shell-quoted-absolute-candidate-marker-literal>
expected_authorization_id=<safely-shell-quoted-64-hex-authorization-id-literal>
expected_object_format=<safely-shell-quoted-sha1-or-sha256-literal>
expected_tree_oid=<safely-shell-quoted-full-tree-oid-literal>
expected_base_commit_oid=<safely-shell-quoted-reviewed-base-commit-oid-literal>
expected_message_sha256=<safely-shell-quoted-exact-message-digest-literal>
test -n "$commit_marker" || exit 1
lock_maybe_acquired=0
prepare_cleanup_armed=1

cleanup_prepare_failure() {
    prepare_status="$1"
    release_status=0
    marker_status=0
    trap - EXIT HUP INT TERM
    if [ "$prepare_cleanup_armed" -eq 1 ]; then
        if [ "$lock_maybe_acquired" -eq 1 ]; then
            bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/release-commit-lock.sh" || release_status=$?
        fi
        rm -f "$commit_marker" || {
            marker_status=$?
            echo "forge: failed to consume commit authorization marker: $commit_marker" >&2
        }
    fi
    if [ "$release_status" -ne 0 ]; then
        exit "$release_status"
    fi
    if [ "$marker_status" -ne 0 ]; then
        exit "$marker_status"
    fi
    exit "$prepare_status"
}
trap 'cleanup_prepare_failure "$?"' EXIT
trap 'exit 1' HUP INT TERM

bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh" commit || exit 1
lock_maybe_acquired=1
bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/acquire-commit-lock.sh" || exit 1

if ! fast_policy_sha="$(python3 - "$commit_marker" "$expected_authorization_id" \
  "$expected_object_format" "$expected_tree_oid" "$expected_message_sha256" <<'PY'
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "scripts" / "forge"))
from forge_cli import candidate


def deny(reason: str) -> None:
    print(
        f"forge: commit not authorized — run /forge:commit ({reason})",
        file=sys.stderr,
    )
    raise SystemExit(1)


marker = Path(sys.argv[1])
try:
    with marker.open("rb") as stream:
        raw = stream.read(4097)
except FileNotFoundError:
    deny("marker missing")
except OSError:
    deny("marker malformed")
if len(raw) > 4096:
    deny("marker malformed")
if re.fullmatch(r"[0-9a-f]{64}", sys.argv[5]) is None:
    deny("marker malformed")

context = candidate.discover_context(Path.cwd())
expected = candidate.CandidateObservation(
    object_format=sys.argv[3],
    tree_oid=sys.argv[4],
    authorization_id=sys.argv[2],
)
observed = candidate.observe_index(context)
if observed != expected:
    deny("marker hash mismatch")
parsed, reason = candidate.parse_marker(
    raw,
    filename=marker.name,
    observation=observed,
)
if parsed is None:
    deny(reason or "marker malformed")
print(parsed.fast_policy or "")
PY
)"; then
    exit 1
fi

pre_commit_head="$(git rev-parse --verify 'HEAD^{commit}')" || exit 1
if [ "$pre_commit_head" != "$expected_base_commit_oid" ]; then
    echo "forge: commit not authorized — run /forge:commit (marker hash mismatch)" >&2
    exit 1
fi

if [ -n "$fast_policy_sha" ]; then
    if [ "$fast_policy_sha" != "$expected_base_commit_oid" ]; then
        echo "forge: commit not authorized — run /forge:commit (fast-path policy drift)" >&2
        exit 1
    fi
    if ! python3 - "$fast_policy_sha" <<'PY'
import subprocess
import sys


def git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def region(policy: bytes, name: str) -> bytes | None:
    begin = f"<!-- FORGE:REGION {name} BEGIN -->".encode()
    end = f"<!-- FORGE:REGION {name} END -->".encode()
    if policy.count(begin) != 1 or policy.count(end) != 1:
        return None
    start = policy.find(begin)
    finish = policy.find(end, start + len(begin))
    if finish < 0:
        return None
    return policy[start : finish + len(end)]


revision = sys.argv[1]
resolved = git("rev-parse", "--verify", f"{revision}^{{commit}}")
ancestor = git("merge-base", "--is-ancestor", revision, "HEAD")
current = git("show", "HEAD:forge-project.md")
historical = git("show", f"{revision}:forge-project.md")
if (
    resolved.returncode != 0
    or resolved.stdout.decode("ascii", "replace").strip() != revision
    or ancestor.returncode != 0
    or current.returncode != 0
    or historical.returncode != 0
):
    raise SystemExit(1)
for name in ("risk-tiers", "trigger-paths", "file-categories"):
    current_region = region(current.stdout, name)
    historical_region = region(historical.stdout, name)
    if name == "trigger-paths" and current_region is None and historical_region is None:
        continue
    if current_region is None or historical_region is None or current_region != historical_region:
        raise SystemExit(1)
PY
    then
        echo "forge: commit not authorized — run /forge:commit (fast-path policy drift)" >&2
        exit 1
    fi
    if ! FORGE_CANDIDATE_SCHEMA=forge-commit-candidate/2 \
      FORGE_CANDIDATE_AUTHORIZATION_ID="$expected_authorization_id" \
      FORGE_CANDIDATE_OBJECT_FORMAT="$expected_object_format" \
      FORGE_CANDIDATE_TREE_OID="$expected_tree_oid" \
      FORGE_CANDIDATE_BASE_COMMIT_OID="$expected_base_commit_oid" \
      python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/risk_tier.py" \
        --repo "$PWD" --policy-sha "$fast_policy_sha" --staged \
        --declared-tier fast --require-effective fast >/dev/null 2>&1
    then
        echo "forge: commit not authorized — run /forge:commit (fast-path eligibility drift)" >&2
        exit 1
    fi
fi

printf 'forge: prepared commit base %s\n' "$pre_commit_head"
prepare_cleanup_armed=0
trap - EXIT HUP INT TERM
```

### Tool call 2 — Commit

The command cell is exactly the following one executable segment after replacing the metavariable
with the safely shell-quoted literal commit message. Do not add a preceding command, `cd`, variable
assignment or expansion, command or process substitution, pathspec, or unsafe option. The
PreToolUse commit guard requires this standalone shape; a marker does not authorize an unstable
command shape.

```bash
git commit --cleanup=verbatim -m <safely shell-quoted literal>
```

Record the exact numeric tool status when it is known, or the literal `unknown` when transport or
interruption obscures it. Also retain the full pre-commit HEAD printed by prepare as
`forge: prepared commit base <sha>`. Regardless of hook allow or denial and regardless of
Git success or failure, immediately run the cleanup call below. An interruption before or after the
commit boundary retains the same unconditional-cleanup duty before any later attempt.

### Tool call 3 — Cleanup

Replace the metavariables with safely shell-quoted literals from the observed commit result and
Steps 1–4. Before releasing the lock, reconcile an unknown or nonzero tool status against the
authoritative HEAD with `candidate.read_commit_object(...)`: durable success requires HEAD movement,
exactly the reviewed snapshot base as its one expected parent, exactly one expected tree, and the
exact intended message-body digest. That durable truth overrides a transport interruption or
numeric nonzero tool status and forbids a retry. A produced-object mismatch releases the lock but
first atomically publishes the exact same-candidate sibling
`<authorization-id>.quarantine` while the lock remains held. Any filesystem entry at that sibling
makes the guard deny through its existing `marker malformed` reason, so the retained marker is not a
reusable capability. It then releases the lock and deliberately retains both entries until the
marker TTL expires; later Step 4 attempts refuse to consume them while fresh. It emits no success
event and uses the exact commit-left-untouched diagnostic below. The mode-0600 latch is strict ASCII
and exactly four LF-terminated lines (`produced: none` means Git returned success without moving
HEAD):

```text
format: forge-commit-candidate-quarantine/1
candidate: <64-lowercase-hex authorization-id>
produced: <full matching Git OID|none>
reason: produced-commit-mismatch
```
An unchanged HEAD after ordinary Git failure remains an ordinary failure and consumes the marker.
Outside the produced-mismatch branch, a lock-release failure takes precedence when both cleanup
actions fail.

```bash
commit_marker=<safely-shell-quoted-absolute-candidate-marker-literal>
pre_commit_head=<safely-shell-quoted-pre-commit-full-sha-literal>
expected_base_commit_oid=<safely-shell-quoted-reviewed-base-commit-oid-literal>
commit_status=<observed-numeric-status-or-safely-quoted-unknown-literal>
effective_tier=<safely-shell-quoted-effective-tier-literal>
policy_sha=<safely-shell-quoted-full-policy-sha-literal>
expected_authorization_id=<safely-shell-quoted-64-hex-authorization-id-literal>
expected_object_format=<safely-shell-quoted-sha1-or-sha256-literal>
expected_tree_oid=<safely-shell-quoted-full-tree-oid-literal>
expected_message_sha256=<safely-shell-quoted-exact-message-digest-literal>
quarantine_latch="${commit_marker}.quarantine"
release_status=0
marker_status=0
commit_succeeded=0
commit_ambiguous=0
produced_mismatch=0

observed_head="$(git rev-parse HEAD 2>/dev/null)" || observed_head=''
if [ "$pre_commit_head" != "$expected_base_commit_oid" ]; then
    produced_mismatch=1
elif [ -n "$observed_head" ] && [ "$observed_head" != "$expected_base_commit_oid" ]; then
    if python3 - "$observed_head" "$expected_base_commit_oid" "$expected_authorization_id" \
      "$expected_object_format" "$expected_tree_oid" "$expected_message_sha256" <<'PY'
import hashlib
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "scripts" / "forge"))
from forge_cli import candidate

observed_head, reviewed_base, expected_id, object_format, expected_tree, message_digest = sys.argv[1:]
context = candidate.discover_context(Path.cwd())
if observed_head == reviewed_base:
    raise SystemExit(1)
if candidate.authorization_id(object_format, expected_tree) != expected_id:
    raise SystemExit(1)
produced = candidate.read_commit_object(context, observed_head)
if produced.tree_headers != (expected_tree,):
    raise SystemExit(1)
if produced.parent_headers != (reviewed_base,):
    raise SystemExit(1)
if hashlib.sha256(produced.message).hexdigest() != message_digest:
    raise SystemExit(1)
PY
    then
        commit_succeeded=1
    else
        produced_mismatch=1
    fi
elif [ "$commit_status" = 0 ]; then
    produced_mismatch=1
fi

case "$commit_status" in
    0)
        :
        ;;
    unknown)
        :
        ;;
    ''|*[!0-9]*)
        commit_ambiguous=1
        ;;
    *)
        :
        ;;
esac

if [ "$produced_mismatch" -eq 1 ]; then
    python3 - "$quarantine_latch" "$expected_authorization_id" \
      "$expected_object_format" "$observed_head" "$expected_base_commit_oid" <<'PY'
import os
from pathlib import Path
import re
import stat
import sys

latch = Path(sys.argv[1])
candidate_id, object_format, observed_head, reviewed_base = sys.argv[2:]
oid_length = {"sha1": 40, "sha256": 64}.get(object_format)
if re.fullmatch(r"[0-9a-f]{64}", candidate_id) is None or oid_length is None:
    raise SystemExit(1)
produced = "none" if not observed_head or observed_head == reviewed_base else observed_head
if produced != "none" and re.fullmatch(rf"[0-9a-f]{{{oid_length}}}", produced) is None:
    raise SystemExit(1)
raw = (
    "format: forge-commit-candidate-quarantine/1\n"
    f"candidate: {candidate_id}\n"
    f"produced: {produced}\n"
    "reason: produced-commit-mismatch\n"
).encode("ascii")
try:
    descriptor = os.open(latch, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    # Any existing filesystem entry is already fail-closed to the guard. Never replace it.
    raise SystemExit(0)
try:
    view = memoryview(raw)
    while view:
        view = view[os.write(descriptor, view):]
    os.fsync(descriptor)
finally:
    os.close(descriptor)
if not stat.S_ISREG(latch.lstat().st_mode) or latch.read_bytes() != raw:
    raise SystemExit(1)
PY
    quarantine_status=$?
else
    quarantine_status=0
fi

bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/release-commit-lock.sh" || release_status=$?

if [ "$produced_mismatch" -eq 1 ]; then
    if [ "$quarantine_status" -ne 0 ]; then
        echo "forge: failed to quarantine produced-commit mismatch authorization" >&2
    fi
    echo "forge: produced commit does not match authorized candidate — chain frozen; commit left untouched" >&2
    exit 2
fi

rm -f "$commit_marker" || {
    marker_status=$?
    echo "forge: failed to consume commit authorization marker: $commit_marker" >&2
}

if [ "$commit_ambiguous" -eq 1 ]; then
    echo "forge: commit outcome ambiguous — inspect HEAD before retrying" >&2
    exit 1
fi
if [ "$commit_succeeded" -ne 1 ]; then
    if [ "$commit_status" = unknown ]; then
        exit 1
    fi
    exit "$commit_status"
fi

# The successful commit outcome above is already final. Event writes are advisory.
committed_sha="$observed_head"
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
if [ "$marker_status" -ne 0 ]; then
    exit "$marker_status"
fi
exit 0
```

The prepare call's failure-only trap is active before the halt check and invokes the release script
once acquisition might have started, so a halt, lock-acquisition failure, later prepare failure, or
prepare interruption invalidates the marker. Successful preparation disarms that trap without
releasing anything. The standalone commit call then leaves both resources for cleanup. Cleanup
releases only a lock matching the unchanged inherited `FORGE_SESSION_PID` and refuses a foreign
owner. It deletes the marker after verified success or unchanged-HEAD ordinary Git failure, but
never after produced-identity mismatch. That mismatch has already published the sibling quarantine
latch before lock release, so the retained marker cannot authorize another commit; both entries
remain until shared-parser stale cleanup. Failure to delete a marker that should be consumed is a
Step 5 failure.

The acquire script owns `.forge/tmp/commit-lock`, whose record format is `<PID> <TIMESTAMP>` and
whose owner is the stable live harness-injected `FORGE_SESSION_PID` inherited unchanged by all
three fresh shells. It owns stale-PID takeover, 2-second polling, and the 300-second timeout.
Never hold the lock across Step 4. The release path and marker deletion are mandatory whether commit
succeeds, commit fails without producing a commit, tree verification detects restaging, the hook
denies the commit, or a tool call is interrupted. The sole marker-retention exception is a Git-zero
result without HEAD movement or a produced parent/tree/message mismatch. Publish the quarantine
latch before release, retain it with the marker, print exactly
`forge: produced commit does not match authorized candidate — chain frozen; commit left untouched`,
and exit 2. Never retry that successful Git invocation. Never create, delete, or bypass an operator
halt sentinel without explicit user direction.

Step 5 accepts only an exact four-line standard/hard PASS marker, exact five-line user-skip marker,
or exact six-line fast marker younger than 30 minutes. It fails closed on a missing, malformed,
stale, or hash-mismatched marker before committing. Old bare two-, three-, and four-line marker
forms are cleanup-only and never authorize. The PreToolUse commit guard independently enforces
freshness and shape and recomputes fast eligibility at `git commit`; never bypass or reinterpret its
decision.

When an explicitly identified run is open, record the verified produced parent/tree/message tuple as
a passing `gate-2: produced commit identity` verification before reporting landing success. The two
post-success calls occur only after the commit succeeds, the produced identity passes, and mandatory
marker cleanup has run; a release diagnostic may already have been reported without retracting that
commit. A successful commit followed by cleanup failure must be reported as commit success together
with the cleanup failure and must never be retried. `gate_commit` supplies the eligible-commit
denominator; a fast commit additionally owns the sole `fast_allowed` event. After preserving that primary outcome, the advisory emitter
registers an in-flight writer but acquires no lock. It opens the canonical
`.forge/tmp/decisions/events.jsonl` with `os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT,
0o600)`, makes exactly one `os.write()`, and treats a short write as a failure. The
`.forge/tmp/events.lock` gates only drift-check's prune read-and-replace and its coordination with
registered writers; it never serializes event appends. Registration or append failure may be
reported but must never change, undo, or misreport the already-delivered commit result. This
non-interleaving guarantee relies on POSIX `O_APPEND` semantics on a local filesystem on the
supported macOS and Linux platforms; it does not extend to NFS/SMB network filesystems, and Windows
is out of scope. Downstream aggregation deduplicates both events by `(event, candidate)` when the
resulting full commit SHA is nonempty.

## User-Directed Skips

Map skip directives exactly:

| User directive | Skip exactly |
|---|---|
| `"skip tests"` or `"skip validation"` | Step 2 |
| `"skip changelog"` | Step 3 |
| `"skip review"` | Step 4 |
| `"just commit"` or `"skip everything"` | Steps 2–4 |

Warn in the reply about every skipped step. Do not infer a skip from urgency or convenience. Steps
1 and 5 are never skipped by these directives. For a control-class candidate, the table never skips
Recorded-baseline integrity or an applicable `fresh-reviewer-evals` Gate-2 step; run both required
layers even when the containing step otherwise has a user-directed skip.
Record every user-directed skip durably as soon as the directive is accepted, before the next step
can fail, including a Step
2-only or Step 3-only skip. First deliver acceptance of the skip as the primary outcome, then make
exactly one advisory `user_skip` event attempt through `emit-decision-event.py` using the v2
`authorization_id` when a snapshot already exists (otherwise `""`), the full `policy_sha`, surface
`/forge:commit`, and a stable
non-secret reason identifying the mapped skip. Event failure never retracts the accepted skip or
changes any subsequent gate status. When an explicitly identified run is open, append a journal
`decision` naming the user's directive, skipped steps, authorization ID when already available, and
user authority. With no such run, append the audit line shown below immediately.

For a Step 4 skip, first reset every candidate variable exactly as at the start of Step 4 without
deleting another candidate's marker. Still stage only the explicit target paths. Run the exact
`candidate.snapshot(...)` artifact block from Step 4, parse its JSON without `eval`, and secret-scan
that immutable artifact; do not launch a reviewer. Re-observe the index with
`candidate.observe_index(...)`, require the recorded object format/tree/authorization tuple, and
capture the skip time, but do not write the marker yet:

```bash
commit_marker="$forge_main_root/.forge/tmp/authorized/$authorization_id"
reviewed_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
```

For a control-class candidate, present the immutable review artifact, skip warning, authorization
ID, object format, tree OID, and review digest while the marker remains absent. Wait for explicit
user approval naming that authorization ID before Step 5. A skip directive never supplies that
approval, and control-class commits are never autonomous. After approval, use the shared helper to
require the same live tree identity. If the tree changed, approval was refused, or the captured skip
time is now older than 30 minutes, keep the marker absent and stop or restart Step 4 as applicable.

Only after that control approval when required, resolve the common main-checkout root as above,
validate the same stable live harness-injected `FORGE_SESSION_PID` under DM-010 before marker
mutation. Never export or substitute shell `$$`, `$PPID`, or another transient PID as that identity.
Then create `.forge/tmp/authorized/`, set `commit_marker` to the exact authorization-ID path, and
write the marker through the same atomic writer as Step 4, with `skip=True` and no fast policy:

```bash
python3 - "$commit_marker" "$authorization_id" "$candidate_object_format" \
  "$candidate_tree_oid" "$reviewed_at" <<'PY'
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "scripts" / "forge"))
from forge_cli import candidate

marker = Path(sys.argv[1])
observation = candidate.CandidateObservation(sys.argv[3], sys.argv[4], sys.argv[2])
raw = candidate.render_marker(observation, sys.argv[5], skip=True)
marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    view = memoryview(raw)
    while view:
        view = view[os.write(descriptor, view):]
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
```

The skip marker is exactly five LF-terminated lines:

```text
format: forge-commit-candidate/2
candidate: <64-lowercase-hex authorization-id>
tree: <sha1|sha256>:<full matching tree OID>
authorized-at: <UTC ISO-8601>
skip: user-directed
```

This is a user authorization marker, never review-backed evidence. For every skip with no
explicitly identified run, set `skipped_steps` to the exact mapped step string and append this audit
line:

```bash
mkdir -p .forge/tmp
printf '%s skip: user-directed (pid %s, steps %s)\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$FORGE_SESSION_PID" "$skipped_steps" >> .forge/tmp/halt-audit.log
```

Do not infer a journal run for the skip record. Continue through Step 5, where the in-lock tree
re-observation, produced-commit verification, and mandatory release still apply.

## Orchestrated Checkpoints

When the workflow identifies an open run explicitly, use its run ID for all Step 2 and Step 4
records and for any skip decision. A checkpoint commit is mandatory after every verified task; the
orchestrator invokes this skill with that task's explicit files and run ID. Agent claims are not
gate evidence: record only executions and results observed under the journal contract.
