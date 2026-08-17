# forge-plugin — Forge CLI Plumbing (Design Sketch)

**Status:** draft sketch, revision 5, 2026-08-16 (Igor + Claude). This document is a design
proposal, not spec authority. It sketches a `forge` CLI that moves gate-chain sequencing,
evidence capture, and authorization out of skill prose and into a persisted, testable state
machine. Nothing in this document changes current behavior; adoption requires its own spec
change through the control-class gate chain.

**Revision 5** adds the out-of-band coordination decisions D33–D34. Provenance is internal,
not an external review: a run-journal follow-up note (2026-08-16) observed that "this is the
second time another session's activity has invalidated an in-flight gate chain in this shared
tree — the registry protects run scopes from overlap, but the commit chain's staged-index
state has no such protection," and the same day this repo's own docs commit chain was nearly
contaminated by a stray pre-staged `docs/specs/**` path left by an earlier session, caught
only by manual staged-set verification. D33 protects the chain from out-of-band *index*
writers (dirty-index refusal at `start`, hook exclusion of foreign index writes,
`GIT_INDEX_FILE` promoted to a named later phase). D34 makes out-of-band *HEAD movement* —
another agent committing in the shared checkout — a diagnosed, cheaply recoverable event
(`head_moved` detection, the `commit rebase` verb with a graded evidence-disposition rule
mirroring FR-063, head-at-verification visibility at finalize) rather than a mystery
hash-mismatch restart. Neither serializes chains behind a lock: FR-190 keeps the review loop
outside the commit lock deliberately, and content addressing remains the coordination
mechanism.

**Revision 4** incorporates the dispositions of a fourth external review — of revision 3 —
recorded verbatim in the research record (§11–§14, decisions D23–D32). The verdict there was
"build it"; these are the last places an implementer would otherwise invent policy.
The material changes: `forge verify` collapses the mechanical middle of the chain into one
resumable verb (D23); mutating-gate precedence becomes a machine refusal, not prose (D24);
skips and the index-drift override move out of finalize flags into the operator-bound
`forge skip` verb (D25); the CLI composes the existing tested executables rather than
rewriting them (D26); `--json` stdout purity (D27); the `forge push` provenance contract
(D28); the `!`-channel rule — operator verbs only, never raw git (D29); `review disposition`
stays model-issuable with operator co-sign for above-MINOR, no flag parsing in the hook
(D30); enum and schema corrections (D31); and the dual-accept/marker-deletion red lines plus
line-count honesty (D32). Per that review's closing advice, the next artifact is the
commit-slice spec, not another review round.

**Revision 3** incorporates the dispositions of a third external review — of revision 2 —
recorded verbatim in the same research record (§7–§10, decisions D14–D22). The material
changes: the per-tier table is repaired to FR-152 and carries the FR-144/FR-147 rows (D14);
concurrency is re-founded on the index as the mutex — one live commit chain per worktree, no
repo-native git hooks (D15); finalize is specified as a two-phase commit with crash-window
recovery and gains `--message` (D16); FR-053's iteration cap, disposition approvals, and
tree-vs-index drift detection enter the machine (D17); the system-of-record sentence is
corrected (D18); the hook matcher grammar is promoted to spec content (D19); FR-056 skip
mapping is carried (D20); the first spec revision is scoped to the commit slice (D21); and
phase 4 gains the `forge push` verb plus the Beads close-protocol rewrite (D22).

**Revision 2** incorporates the dispositions of a second external review — a twelve-point
critique of revision 1 — recorded verbatim with the full discussion in
`research/2026-08-16-external-review-of-cli-sketch.md`. The decision register there (D1–D13)
maps each finding to its disposition; this document is the folded-in result. The material
changes: the hook/CLI boundary is now stated in its strong form (D1); the chain-lifetime TTL
regression is fixed (D2); staging and candidate identity are CLI-owned (D3); the
`awaiting_approval` state restores FR-051's approval contract with a four-layer mechanism
(D4); review anti-forge is a two-tier best-effort story (D5); plan-seal is re-scoped to an
ordering/audit record (D6); the system-of-record rule (D7), raw-push denial (D8), transition
tables (D9), phased full-scope build order (D10), `env_fingerprint` definition (D11), binary
naming and bootstrap (D12), and the model-facing output contract (D13) are all specified.

**Origin:** an external process review of forge-plugin (2026-08-16, recorded verbatim in
`research/2026-08-16-external-process-review-discussion.md`) identified that "the process is
mostly a very long prompt with a hook at the end" — 2,778 lines of skill prose executed by a
fallible model, with only the PreToolUse hook, marker parser, and committed-policy sourcing as
actual mechanical enforcement. This sketch is the response.

## TL;DR

Invert the enforcement architecture. Today the skill is the program, the model is the
interpreter, and `scripts/forge/*` are subroutines the model must remember to call in order.
The proposal: a single `forge` CLI owns the chain state machine; the model supplies judgment
only at the points the CLI asks for it. The commit skill collapses from ~622 lines to an
estimated 100–150 lines of classification guidance and per-decision-point instruction — an
estimate contingent on `forge verify` and exact-argv `next required step:` lines existing
(D23/D32); without them the skill still holds the gate table and skip map and lands nearer
250–300. The model claims nothing; the CLI attests.

**The CLI is the committer and the pusher.** In a Forge repo the hook denies raw `git commit`
and raw `git push`; the only verbs that reach git's history-mutating operations are
`forge commit finalize` and `forge merge finalize`, and the CLI performs the git operations
internally after verifying the complete evidence chain itself.

This is the git model: porcelain guides, plumbing enforces.

## Design Principles

1. **Sequencing is state, not prose.** Every chain step checks its own preconditions against a
   persisted chain record and refuses out-of-order execution. Skipping a step becomes
   structurally impossible rather than prose-forbidden.
2. **Evidence is captured, never transcribed.** Gates run *through* the CLI, which records
   exit codes, durations, and output hashes itself. The model never relays a SHA, a pass
   claim, or a "ran it twice" assertion — the CLI observed it, the CLI wrote it down.
3. **The next step is always printed.** Every command's output ends with
   `next required step: <command>`. The model needs to read one line, not hold a 622-line
   procedure in attention under context pressure.
4. **Judgment stays with the model.** What to stage (the CLI performs the staging; the model
   chooses the paths), semantic scope beyond path patterns, dispositioning findings, writing
   plans and reviews, and the standing duty to stop and surface anomalies outside the
   checklist — none of this moves into the CLI.
5. **Escape hatches live inside the tool.** User-directed skips are CLI-mediated and
   journaled, or operators will route around the whole tool the first time it is
   inconvenient. A bypassed control system is worse than a prose one, because it still looks
   enforced.
6. **Fail-closed everywhere.** Unknown state, corrupt chain file, hash mismatch, expired TTL,
   halt flag present, policy ancestry break — every one refuses with an exact diagnostic.
7. **Best-effort controls are labeled as such.** The threat model is unchanged from the spec:
   the enforcement layer stops accident, negligence, and prompt injection; it does not stop a
   deliberately adversarial orchestrator running as the operator's OS user. Where a control
   is best-effort (review-final attach, plan-seal, approval provenance), the design says so
   explicitly and never claims a guarantee the architecture cannot deliver.
8. **The CLI's consumer is a model under context pressure.** Every output — above all every
   refusal — is self-contained: current state, exact failed precondition, exact remediation
   command, next required step. A terse Unix-style error is a design defect here; the reader
   may have just lost most of its context, and the message must be enough to act on alone.

## Subcommand Surface

All state-mutating subcommands implicitly run the halt check first and refuse if the operator
halt flag is present. `forge …` below is shorthand for the real invocation
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py" …` (see *Naming and Bootstrap*).

### Chain lifecycle

```
forge status
    Show the active chain (if any), its state, completed steps with evidence
    digests, and the next required step. Read-only. Safe always.

forge commit start --paths <path>... [--declare-tier <tier>]
    Open a commit chain. Verifies: no other live commit chain exists for this
    worktree (the git index is the mutex — see *Concurrency*); the index is
    clean before the CLI stages — pre-existing staged content is refused with
    the offending paths named and the remediation printed, because it belongs
    to no live chain and would silently ride into the candidate (D33); working
    tree paths exist; policy is readable from committed HEAD. The
    CLI performs `git add -- <paths>` itself, computes the candidate identity
    from the exact staged bytes, and runs classification automatically. Declared
    tier is recorded but can only be promoted by later evidence, never demoted
    (the CLI has no demote operation).

forge commit restage --paths <path>...
    The only sanctioned way to change the staged set mid-chain. Re-runs
    staging, recomputes the candidate, and invalidates every evidence record
    bound to the old hash — including classification, which reruns. Any index
    change made outside the CLI is detected by re-hash at the next command and
    has the same effect, plus a journaled anomaly note.

forge commit rebase
    Recovery verb for out-of-band HEAD movement (D34) — another agent's commit
    landing in the shared checkout while this chain is live. Re-pins
    `repo_head`; checks policy continuity by digest (byte-identical committed
    policy at the new HEAD keeps policy-derived records; changed policy bytes
    end the chain — restart); restages the recorded path set and recomputes
    the candidate. Evidence disposition is graded, mirroring FR-063: diff-scoped
    records (secret scan, review verdict — candidate-bound per DM-006 doctrine)
    survive iff the recomputed candidate hash is unchanged; tree-dependent
    records (gate runs, stack validations — they executed against a tree that
    no longer exists) are always dead and re-run. Converts "another agent
    committed, start over" into "re-run the gates, keep the review" when the
    out-of-band change is disjoint.

forge commit abort [--reason <text>]
    Close the chain without committing. Journals the abort. Releases locks.

forge commit approve --candidate <sha256>
    Control-class only; valid only in state `awaiting_approval`. Records the
    approval bound to the exact candidate hash and transitions to `authorized`.
    The hook denies this verb when issued through the model's Bash tool; the
    operator runs it directly (see *Approval Mechanism*).

forge commit skip <gate-id> --reason <text>
forge commit skip --index-drift --reason <text>
    Record a user-directed skip (FR-056) or an index-drift override in chain
    state, ahead of finalize. Operator-bound exactly like approve: the hook
    denies the verb on the model's Bash path; the operator runs it via `!`
    (see *Approval Mechanism*). FR-056 skips were always user-*directed*;
    this makes the direction mechanically verifiable instead of
    model-attested — a context-crushed model can no longer reconstruct "just
    commit" as a pile of finalize flags (D25). The `--index-drift` form
    exists to commit index bytes the tree no longer matches; overriding a
    negligence guard is the definitional operator-reserved act. The skill's
    FR-056 duty is unchanged: map operator language onto gate IDs and present
    the exact `!` argv. In headless runs a needed skip parks the chain, same
    as approval — correct behavior, same feature. No skip covers
    control-class review; none covers approval, ever.

forge commit finalize --message <text> | --message-file <file>
    The only path to a commit. The commit message is model judgment
    (principle 4) and arrives only through these flags — no stdin, env-var, or
    tempfile side channel for an implementer to invent. Finalize carries no
    override flags at all (D25): skips and the index-drift override are
    operator-recorded in chain state beforehand via `forge commit skip`,
    which also keeps the hook's finalize-allow rule maximally simple.
    Verifies the complete evidence chain: every required step for the
    effective tier is present, bound to the current candidate hash, within
    its authorization TTL, and either PASS or covered by an operator-recorded
    skip. Refuses on tree-vs-index drift: if the working tree differs from
    the index on any staged path, the bytes about to be committed are not the
    bytes just edited — remediation is restage, or an operator-recorded
    index-drift skip. Then executes the two-phase protocol (see *Finalize
    Protocol*): halt → lock → candidate byte-identity re-verification →
    intent event → git commit → commit SHA recorded → chain closed → lock
    released. No skip can cover the review step for control-class changes,
    and none can cover approval, ever. This is the single commit-producing
    verb the PreToolUse hook allows.
```

### Gates and evidence

```
forge verify
    Run every remaining required *mechanical* step for the effective tier, in
    order — mutating gates first, then gate 1 twice, stack validations, the
    assertion-quality sensor, invariant rows, the secrets scan — recording
    each as evidence exactly as `gate run` does. Judgment verbs (review,
    approve, skip, finalize) are never included. This is the actual 622-line
    collapse (D23): the model issues one verb instead of holding the gate
    table; without it, the clerk's end moved into Python and its middle
    stayed a checklist. **Resumable by construction:** the harness's
    tool-execution ceiling (10 minutes) is shorter than gate 1 alone, so a
    blocking monolith would be a liveness bug, not an ergonomic. Each
    invocation executes remaining steps until done, failure, or interruption;
    per-step completion is persisted in the chain, so re-invoking
    `forge verify` continues from the first incomplete step — and invoking it
    when everything passes is a no-op that prints the next judgment verb.

forge gate run <gate-id>
    Run a single configured gate (gate1, conformance, evals, changelog, ...)
    from the committed policy table — never from a working-tree policy file.
    The CLI executes the command, captures exit code, duration, stdout/stderr
    digest and a bounded transcript, and writes the evidence record bound to
    the current candidate hash. Individual runs keep the existing 1200-second
    bound and process-group kill discipline. "Twice consecutively" becomes
    two CLI-recorded runs with timestamps and environment fingerprints. A
    gate that mutates the tree (a configured changelog writer) declares that
    in policy; the CLI adds its output paths to the chain's path set,
    restages them, and recomputes the candidate, invalidating downstream
    evidence — which is why mutating gates are ordered first. The machine
    enforces that order (D24): `gate run` of a non-mutating gate refuses
    while a configured mutating gate is still pending, naming the pending
    gate as the remediation. `gate run` remains the right verb for re-running
    one failed gate; `forge verify` is the normal path.

forge classify
    Recompute the risk tier from staged paths via risk_tier.py logic (runs
    automatically inside `commit start` and after any restage). Emits the tier
    evidence record. Promote-only: the effective tier is
    max(declared, computed, gate-time recomputation).

forge scan secrets
    Run the secret scan over the exact staged bytes and record the evidence.
```

### Review

```
forge review request
    Refuses on tree-vs-index drift over staged paths — the reviewer must see
    the bytes that will be committed, not a stale index behind fresh edits.
    Assembles the review context package for the current candidate: diff,
    per-artefact review profile (profile selection is mechanical), project
    focus lenses, and NOTHING from the implementer's handoff — the reviewer
    never sees the handoff because the CLI never puts it in the package.
    Behavior then splits by reviewer tier (see *Review Integrity*):
    - Codex reviewer (standard tier): the CLI launches the reviewer process
      itself (detached, per existing launch doctrine) and owns the verdict
      output path under the chain directory.
    - review-final (hard/control tier): the CLI emits the package path, the
      package digest, and the exact reviewer invocation for the orchestrator
      to spawn as a Claude subagent — a CLI subprocess cannot spawn one.

forge review collect
    Codex tier only: verify the launched reviewer process completed, read the
    verdict from the CLI-owned path, validate the grammar, and bind it to the
    candidate hash.

forge review attach --verdict-file <file>
    review-final tier: validate and bind a reviewer verdict. Verifies the
    verdict grammar parses, and that it cites both the current candidate hash
    and the package digest the CLI issued at request time; journals the attach.
    Best-effort by design — see *Review Integrity* for the honest limits.
    A BLOCK verdict increments the chain's iteration counter and transitions
    the chain to `revising`; any subsequent byte change to the candidate
    invalidates all evidence per the restage rule. At the FR-053 hard cap of
    8 iterations the CLI refuses further cycles, records residual risk, and
    escalates to the operator — never a commit.

forge review disposition --finding <n> --severity <sev> --resolution <text>
    Record the disposition of a review finding in the chain. The verb is
    model-issuable — recording a disposition is judgment work — and the hook
    never parses its flags: extracting `--severity` from argv would be
    another FR-090-grade matcher, refused as such (D30). Instead, an
    above-MINOR disposition leaves the chain in a state that cannot advance
    until the operator co-signs it through the already-denied approve
    mechanism (FR-053).
```

### Anti-anchoring (best-effort ordering control)

```
forge plan seal --file <plan>
    Journal Claude's own plan (digest + timestamp).

forge proposal unseal
    Emit the Codex proposal path for reading. Refuses unless a sealed plan
    exists for this run.
```

This is an ordering and audit record, not an information-flow guarantee. A same-user process
can always read the proposal bytes from the worktree; the spec's threat model already
concedes this. The control's value is against negligence: the CLI will not *hand over* the
proposal until the plan digest is journaled, so anchoring cannot happen by accident or by
context-pressure shortcut — only by a deliberate act that the journal's ordering then
contradicts. The claim "the proposal is unreadable" is withdrawn and must not appear in the
spec revision.

### Merge chain

```
forge merge start --worktree <path>
forge merge gate run <gate-id>
forge merge approve --candidate <head-sha>     # control-class diffs; same mechanism as commit approve
forge merge finalize
    Same architecture as the commit chain: persisted state, CLI-captured
    evidence, the locked rebase performed by the CLI, fast-forward push only —
    performed internally by the CLI. Once the merge chain exists, the hook
    denies raw `git push` in a Forge repo (see *Hook Integration*).

forge push
    The sanctioned push path for default-branch commits in the main checkout —
    the case merge finalize cannot cover (no worktree, no merge chain). Halt
    check, rebase lock, fetch, rebase onto the remote tip, fast-forward push
    only: the merge-finalize push discipline minus the worktree. Exists so
    that phase 4's raw-push denial leaves a legal close protocol at all; the
    Beads close-protocol block is rewritten to route through it in the same
    control-class change (see *Migration*, D22). Contract (D28): refuses on
    halt, a failed or dirty rebase, and non-fast-forward — and it does NOT
    audit commit provenance. It may push commits no closed chain produced
    (bootstrap, merge-landed history, pre-Forge commits): honest ancestry
    auditing is impossible, and the commit-denial hook already guarantees,
    within the threat model, that new orchestrator commits went through
    chains. Phase 4 must not invent a "chain-produced SHAs only" rule in the
    hook matcher.
```

The merge chain is deliberately still a sketch inside the sketch: the dirty-worktree
predicate, committed-policy sentinels, rebase-lock mechanics, FR-063 re-verification inside
the lock before the push, and candidate identity as HEAD SHA rather than staged-diff hash
all need their own transition table. That table comes with the merge-chain spec revision,
not this document (see *Migration*, D21).

### Supporting

```
forge evals run [--strict]        # wraps run-evals.sh with evidence capture
forge journal show [--chain <id>]
forge halt check                  # explicit form of the implicit check
```

## Output Contract (D13)

The CLI's primary consumer is the orchestrating model, possibly mid-session after context
loss; the secondary consumers are the PreToolUse hook and the test suite. The contract:

- **Every command** ends its stdout with `next required step: <exact command>` (or
  `next required step: none — chain closed`). This line is load-bearing UX, not decoration.
- **Every refusal** is a structured, self-contained diagnostic: what state the chain is in,
  which precondition failed, the exact values compared (expected vs. observed, with digests
  truncated for display but full in the JSON envelope), the exact remediation command, and
  the next required step. Refusals exit 1. A refusal that requires the operator (approval,
  halt, user-skip) says so explicitly and names the operator action.
- **`--json`** on every command emits a machine-readable envelope:
  `{schema, ok, chain_id, state, reason_code, message, expected, observed, remediation,
  next_required_step, evidence_refs}`. Reason codes are a fixed enum, spec'd and tested, so
  the hook and evals can assert on codes rather than prose. Under `--json`, stdout carries
  the envelope *only* — `next required step:` is a field, never a second stdout line;
  concatenating both breaks every JSON consumer (D27). The human line belongs to the
  non-JSON path.
- **`--verbose`** on every command streams underlying activity live (gate stdout/stderr as
  captured, staging output, rebase progress) instead of only the bounded digest summary.
  Verbosity never changes what is recorded as evidence — the bounded transcript and digests
  are written identically either way.
- **Internal failures** (corrupt chain file, event/state divergence that replay cannot
  resolve, unexpected exceptions) exit 2, fail closed, and print what was being attempted,
  what is on disk, and that the chain is frozen pending `forge status` / `abort` — never a
  bare traceback with no next action.
- **Diagnostic stability:** exact refusal strings and reason codes are part of the control
  surface, pinned by tests, and changing them is control-class — same doctrine as today's
  FR-090 denial literals.

## Step Order, Tiers, and Transitions (D9)

State enum:

```
classifying → verifying → reviewing → revising
                           ↓ (PASS)
       control-class: awaiting_approval → authorized → committing → closed
       otherwise:                         authorized → committing → closed
any state → aborted
```

Chains are born in `classifying`: `commit start` stages, computes the candidate, and
classifies in one motion. There is no `open` state — revision 3 drew one and the table never
used it (D31).

Transition table (illustrative here; the spec revision carries the normative version):

| From | Event | To | Guard |
|---|---|---|---|
| — | `commit start` | `classifying` | halt clear; no overlapping live chain; paths exist; policy readable at HEAD; staging succeeds; candidate computed |
| `classifying` | classification recorded (automatic) | `verifying` | tier evidence bound to candidate |
| `verifying` | all required gates + scans PASS or operator-skipped | `reviewing` | every record bound to current candidate; skips operator-recorded via `forge skip` (D25); mutating-gate precedence enforced (D24) |
| `verifying` | tier requires no review (fast) | `authorized` | fast eligibility holds at authorization time |
| `reviewing` | verdict PASS, non-control tier | `authorized` | verdict bound to candidate (+ package digest for review-final) |
| `reviewing` | verdict PASS, control-class | `awaiting_approval` | same |
| `reviewing` | verdict BLOCK | `revising` | BLOCK journaled with findings count; iteration counter incremented |
| `revising` | `restage` after fixes | `classifying` | old evidence invalidated wholesale; refused at the FR-053 cap — 8 iterations means escalate, not another cycle |
| `awaiting_approval` | `approve --candidate <sha>` | `authorized` | sha equals current candidate; verb reached the CLI outside the model's Bash path (see *Approval Mechanism*) |
| `authorized` | `finalize` | `committing` → `closed` | authorization unconsumed, within TTL; candidate byte-identity re-verified; no tree-vs-index drift on staged paths; halt clear; lock acquired; two-phase order per *Finalize Protocol* |
| `committing` | crash recovery (next CLI invocation; `status` diagnoses the window) | `closed` or `authorized` | per *Finalize Protocol*; every other verb refuses |
| any | `abort` | `aborted` | journaled |
| any except `closed` | out-of-band index change detected | `classifying` | all evidence dead; anomaly journaled |
| any except `closed`, `committing` | out-of-band HEAD movement detected | unchanged (flagged) | `head_moved` event journaled with old→new SHAs and an explicit "out-of-band commit, not chain corruption" diagnostic; every state-advancing verb refuses until `commit rebase` or `abort` (D34) |
| flagged `head_moved` | `commit rebase` | `classifying` or `verifying` | policy continuity by digest (changed policy ends the chain); candidate recomputed; graded evidence disposition per the *Concurrency* rules |
| any | inactivity expiry | dead in place | only `status`/`abort` may touch it |

Required steps per tier. The row structure of this table is normative — it restates FR-050
and FR-152, and an implementer will copy these cells; only the *commands* behind each row
come from the committed policy table. Per FR-152, fast differs from the other tiers in
exactly one row: the reviewer. A fast tier made cheap by weakening any other row is the
FR-152 repeal this table previously contained (D14) — and it would move the `fast_allowed`
dogfood metric for the wrong reason.

| Step | fast | standard | hard | control |
|---|---|---|---|---|
| stage + candidate + classify (in `start`) | ✓ | ✓ | ✓ | ✓ |
| changelog gate (where configured; mutating, ordered first) | ✓ | ✓ | ✓ | ✓ |
| gate 1, twice consecutively | ✓ | ✓ | ✓ | ✓ |
| stack validations for touched categories | ✓ | ✓ | ✓ | ✓ |
| assertion-quality sensor over touched test files (FR-144) | ✓ | ✓ | ✓ | ✓ |
| commit invariant rows (FR-147) | ✓ | ✓ | ✓ | ✓ |
| secrets scan | ✓ | ✓ | ✓ | ✓ |
| STRICT evals (where FR-103 applies; a control diff is never fast) | — | — | — | ✓ |
| review — the only row fast skips (FR-152) | — | review-cheap (Codex) | review-final | review-final |
| operator approval bound to candidate | — | — | — | ✓ |
| finalize: halt, lock, hash re-check (fast: plus independent eligibility recomputation) | ✓ | ✓ | ✓ | ✓ |

Invalidation rules, stated once and enforced everywhere:

- The candidate is the SHA-256 of the exact `git diff --cached` bytes, computed by the CLI
  after it stages. It does not exist before staging and is never computed from a path list.
- Any change to the index — CLI restage, mutating gate output, or out-of-band `git add` —
  recomputes the candidate. Every evidence record is bound to the hash current when it was
  written; records bound to a stale hash are dead, *including classification*, which reruns.
- Working-tree vs. index drift on a staged path is refused at review request and at
  finalize: reviewing or committing index bytes that differ from the tree the model just
  edited is a negligence trap. Remediation is restage, or an operator-recorded index-drift
  skip (`forge commit skip --index-drift` — D25); overriding a negligence guard is the
  definitional operator-reserved act.
- Out-of-band HEAD movement is detected at every command (`repo_head` comparison) and is
  never surfaced as a bare hash mismatch: the diagnostic names the old and new SHAs and the
  recovery verb. Evidence disposition after `commit rebase` is graded: diff-scoped records
  survive an unchanged recomputed candidate; tree-dependent records always re-run (D34).
- No skip covers review for control-class changes; no skip covers approval, ever.
- Tier is promote-only end to end: declared, computed at start, recomputed at gate time and
  at fast finalize — the effective tier is the maximum ever observed.

## Concurrency (D15, D33, D34)

The git index is the mutex, not the path set. Git has one index per worktree; two live
commit chains in the same worktree would share it — chain B's `git add` leaves chain A's
staged bytes in place, so B's candidate silently includes A's files, or B destroys A's
staging to avoid it. A path-overlap check solves a problem git does not have and misses the
one it does.

- **At most one live commit chain per worktree.** `commit start` refuses while another
  chain for the same worktree is live, naming that chain and the abort/finalize
  remediation. This is the conservative rule and the one that matches current law.
- **Cross-worktree concurrency is unchanged:** FR-190's content-addressed model — each
  chain hashes `git diff --cached` in its own Git context, and authorization is bound to
  the candidate hash, so chains in different worktrees cannot authorize each other's diffs.
- **`GIT_INDEX_FILE` per chain** is promoted from "future option" to a named later phase
  (D33, layer 3): a chain that stages into its own private index file owns its candidate
  state *by construction* — no other session can touch it, no detection is needed, and the
  one-chain-per-worktree restriction could eventually relax. The costs are real (staging,
  hashing, drift checks, and the inner `git commit` must all consistently use the private
  index, and the hook's staged-hash verification must read the same one), so it lands only
  after dogfood evidence, never in the first slice.

### Out-of-band index writers (D33)

The rules above guard chain-vs-chain. The observed incident class is chain-vs-*non-chain*:
index state written by something that is not a live chain — a dead session's staged residue,
or a concurrent session's `git add`. The chain borrows shared mutable state it does not own;
detection (re-hash at every command) converts corruption into a visible restart, which still
burns the gate evidence. Three layers, in increasing strength:

1. **Dirty-index refusal at `commit start`** (the dead-residue case, and the one that
   actually occurred): refuse to stage over pre-existing staged content, naming the paths.
2. **Hook-level index write exclusion** (the live-concurrency case): while a live chain
   exists for a worktree, the PreToolUse hook denies index-mutating git verbs (`add`,
   `restore --staged`, `reset`, `rm --cached`, `stash`) from any session that does not own
   the chain — ownership is the session identity recorded in the chain file at `start`.
   Same layer and threat model as every other hook control: stops accident and negligence,
   not a hostile process; Codex implementer worktrees have their own indexes (FR-031) and
   are untouched. Honest limit (principle 7): only sessions running under the hook are
   bound — a human terminal still writes the shared index, and detection remains the
   backstop for that.
3. **`GIT_INDEX_FILE` per chain**, above — removes the sharing instead of guarding it.

### Out-of-band HEAD movement (D34)

The sibling failure mode: another agent *commits* in the shared checkout while a chain is
live. HEAD movement is weather, not sabotage — DVRR's founding rule puts concurrent writers
in worktrees, so a second committer in the main checkout is architecturally out-of-band, and
the CLI's job is detect → diagnose → cheap recovery, not prevention it cannot deliver.
What must not happen: serializing whole chains behind a repo lock. FR-190 keeps the review
loop outside the commit lock deliberately; a chain spans twenty-plus minutes and blocking
every other agent's commits for its duration trades a restart cost for a fleet-wide stall.
Content addressing is the coordination mechanism — DM-006 markers pin the staged-diff hash,
not HEAD, so current law already tolerates concurrent commits that leave the candidate bytes
unchanged, and the CLI must not be stricter than that law. The design maximizes what is
content-addressed (policy by digest, review by candidate hash) and makes the rest
re-runnable with one verb (`commit rebase`, above) and an honest price tag: gates re-run,
review survives an unchanged candidate.

## Chain-State Schema

One JSON file per chain under `.forge/chains/<chain-id>.json` (git-excluded working state,
like journals; archived on close under the run archive). Append-only event log alongside at
`.forge/chains/<chain-id>.events.jsonl` for audit; the JSON file is the materialized current
state and must be reconstructible from the events — except across the git side effect:
recovery in `committing` observes HEAD, per *Finalize Protocol* (D31).

```json
{
  "schema": "forge-chain/2",
  "chain_id": "c-2026-08-16T170301Z-9f3a",
  "kind": "commit",
  "state": "awaiting_approval",
  "created_at": "2026-08-16T17:03:01Z",
  "last_event_at": "2026-08-16T17:41:09Z",
  "inactive_after": "2026-08-17T17:41:09Z",
  "repo_head": "3a1d0dd...",
  "policy_source": {
    "ref": "HEAD",
    "commit": "3a1d0dd...",
    "policy_digest": "sha256:..."
  },
  "paths": ["scripts/forge/foo.sh", "tests/test_foo.py"],
  "staging": {
    "staged_by": "cli",
    "staged_at": "2026-08-16T17:03:04Z",
    "restage_count": 0
  },
  "candidate": {
    "sha256": "sha256-of-exact-staged-bytes",
    "computed_at": "2026-08-16T17:03:05Z"
  },
  "tier": {
    "declared": "standard",
    "computed": "control",
    "effective": "control",
    "evidence": "sha256:..."
  },
  "steps": [
    {
      "name": "gate1",
      "status": "pass",
      "runs": [
        {
          "started_at": "...",
          "finished_at": "...",
          "exit_code": 0,
          "duration_s": 214.6,
          "command_digest": "sha256:...",
          "output_digest": "sha256:...",
          "transcript_path": ".forge/chains/c-.../evidence/gate1-run1.txt",
          "env_fingerprint": "sha256:..."
        }
      ],
      "bound_candidate": "sha256:...",
      "user_skip": null
    }
  ],
  "review": {
    "mode": "review-final",
    "iteration": 1,
    "package_digest": "sha256:...",
    "verdict": "PASS",
    "verdict_digest": "sha256:...",
    "bound_candidate": "sha256:...",
    "reviewer_identity": "review-final/claude",
    "attached_at": "..."
  },
  "approval": {
    "required": true,
    "candidate": "sha256:...",
    "recorded_at": null,
    "argv_digest": null
  },
  "authorization": {
    "token": "sha256-of-candidate + chain_id",
    "issued_at": null,
    "expires_at": null,
    "consumed": false
  },
  "commit_result": {
    "intent_written_at": null,
    "commit_sha": null,
    "closed_at": null
  }
}
```

Notes:

- **TTL semantics (D2).** The authorization token's 30-minute TTL starts at *issuance* —
  when the chain reaches `authorized` — preserving DM-006's clock exactly. The chain itself
  has no 30-minute lifetime: `inactive_after` is a generous inactivity bound (default 24 h
  from `last_event_at`) whose only purpose is declaring abandoned chains dead in place for
  garbage collection; a chain past it accepts only `status` and `abort`. Individual gate runs
  keep the existing 1200-second execution bound.
- **Every evidence record is bound to `candidate.sha256`.** Any restage recomputes the
  candidate; evidence bound to a stale hash is dead. Content-addressed authorization,
  consumed-on-use, and cross-chain isolation (two concurrent chains cannot authorize each
  other's diffs) carry over unchanged — but the binding is enforced at every step, not only
  at the end.
- **`user_skip`**, when present, is `{"directed_by": "user", "reason": "...",
  "argv_digest": "...", "journaled_at": "..."}`, written only by the operator-bound
  `forge skip` verb — never by a finalize flag (D25). No skip can cover the review step
  for control-class changes, and no skip can cover the approval step at all.
- **`env_fingerprint` (D11)** is the SHA-256 of a canonical JSON record:
  `{cwd, repo_head, policy_digest, command_digest, python_version, platform}`. It is an
  identity-and-context record, not an independence proof: two back-to-back CLI runs on the
  same laptop are not two independent environments, and the spec must not claim they are.
  The honest claim — and the actual win over today — is *"the CLI observed both runs."*
  A fingerprint mismatch between the two required gate-1 runs voids the pair: "twice
  consecutively" means twice in the same observed context (D31).
- **HEAD visibility (D34):** every evidence record carries the HEAD observed when it was
  written (already inside `env_fingerprint`; additionally recorded as a plain field), and
  `commit_result` records head-at-commit. The authorization TTL is the only bound on how far
  the base may drift between verification and commit — DM-006 parity forbids tightening
  that — but the archive must show the drift so a later reader can see which base each gate
  ran against.
- **Crash safety:** commands write the event first, then the materialized state; on startup
  any command that finds a divergence replays events. Irresolvable divergence is an exit-2
  frozen-chain condition per the output contract. This rule is sufficient only for pure
  JSON state; finalize wraps an external side effect and follows the two-phase protocol
  below.

## Finalize Protocol (D16)

Event-then-state is not crash-safe around `git commit` — the crash windows straddle an
external side effect, on the path that is now the last line of defense. Finalize is a
two-phase commit and is specified as one. Normative order:

1. halt check;
2. acquire commit lock;
3. re-verify candidate byte identity (`git diff --cached` hash equals the bound candidate)
   and refuse on tree-vs-index drift over staged paths;
4. write the intent event (`commit_result.intent_written_at`), state → `committing`;
5. `git commit` (message from `--message`/`--message-file` only);
6. record the produced commit SHA (`commit_result.commit_sha`);
7. close the chain (state → `closed`, `closed_at` recorded);
8. release the lock.

Recovery, per crash window, executed by the next CLI invocation and diagnosed by
`forge status`:

- **Crash after 4, before 5** (intent written, no commit): HEAD does not match the intent.
  Fall back to `authorized` if the authorization token is unexpired and unconsumed;
  otherwise refuse to the operator with both facts stated.
- **Crash after 5, before 7** (real commit, open chain): identify the new HEAD commit
  against the recorded intent — its diff identity must equal the bound candidate — then
  complete steps 6–8 idempotently. A HEAD matching neither the pre-finalize state nor the
  intent is an exit-2 frozen chain: history moved outside the protocol.
- **Crash inside 5:** git itself is atomic here — either the commit exists (second window)
  or it does not (first window). The protocol never guesses; it observes HEAD.

A chain found in `committing` accepts only `status` and the recovery path; every other verb
refuses with the window diagnosis.

## Hook Integration (D1, D8)

The strong form, with no alternative readings:

**In a Forge repo, the PreToolUse hook denies raw `git commit` and raw `git push`.** The only
commands it allows to produce a commit or a push are `forge commit finalize` and
`forge merge finalize` (matched by a spec'd argv pattern for the
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py"` invocation form, with the same
segment-splitting discipline FR-090 applies to git today). The CLI performs the git
operations internally. `git commit` and `git push` stop being the model's verbs.

Consequences, owned explicitly:

- The inner `git commit`/`git push` run inside the CLI subprocess, which the hook never
  sees. Every check FR-090 performs today at the last line of defense — halt, staged-bytes
  identity, authorization validation — therefore moves *into* the CLI's finalize paths. The
  hook's job shrinks to: deny raw git history-mutating verbs, deny the model-issued
  operator verbs (approve, skip), deny foreign index writes while a live chain exists
  (D33), allow the finalize argv, and keep the halt check.
- **The CLI inherits the hook's status as last line of defense.** Its internal finalize
  checks carry the same severity as the hook parser does today: each is independently
  disableable in code with a focused test that fails when it is disabled, and its exact
  diagnostics are pinned.
- Raw-push denial activates only once `forge merge finalize` exists (migration phase 4);
  before that, denying push would leave no push path at all.
- **No repo-native git hooks, ever.** "The CLI is the committer" will tempt someone to add
  a pre-commit/commit-msg hook as backstop. Refuse it: FR-031 lets Codex implementers
  commit inside their execution worktrees, and those processes never pass through Claude's
  PreToolUse hook — a repository git hook would break implementer worktrees. The
  enforcement point is PreToolUse, full stop.
- **The matcher grammar is spec content, not a gesture.** Matching the CLI invocation is as
  hard as FR-090's git matcher: `python3` vs `python` vs absolute interpreter paths,
  relative vs plugin-root paths to `cli.py`, and `CLAUDE_PLUGIN_ROOT` resolving to cache,
  marketplace, or local-checkout roots. The spec revision carries the grammar itself, with
  FR-090's segment-splitting discipline and byte-pinned denial diagnostics; the Phase 0
  eval pins it.
- Threat-model continuity: as with FR-090 today, shell aliases, functions, and wrappers are
  out of scope. The hook stops accident, negligence, and injection — not an adversarial
  same-user process.
- The marker grammar, its parser, and their tests are deleted only at the final migration
  phase — the model's claims stop being an input to enforcement.

## Implementation Rule: Compose, Don't Rewrite (D26)

`cli.py` is a state machine that *invokes* the existing tested executables — the halt
check, commit lock, `risk_tier.py`, the secret scan, `run-evals.sh`, FR-154's independent
fast recomputation — records what they returned, and owns sequencing, evidence, and
authorization. It does not reimplement halt, lock, classification, or the secret scan.
Those scripts are the tested control surface: inlining them would make phase 1 a
control-class rewrite disguised as a wrapper and orphan every existing disable-in-memory
test, all of which would have to be re-proven against a second implementation. Where an
interface genuinely does not fit CLI invocation (logic embedded in hook-shaped scripts
such as `commit-guard.sh`), the sanctioned move is extracting a shared function *from the
existing script* — its own control-class change, keeping the tests pointed at one
implementation — never a second copy in Python. The same doctrine already governs records:
the CLI appends the existing journal shapes, never new ones (D7).

## Approval Mechanism (D4)

Control-class law is unchanged from FR-051/FR-060: a reviewer PASS never authorizes a
control-class commit or merge; explicit user approval bound to the exact candidate is
required. The CLI makes the wait structural and layers the mechanism, strongest first:

1. **State machine (the floor, mandatory).** Control-class chains enter `awaiting_approval`
   after review PASS. `finalize` refuses in any other state; there is no transition to
   `authorized` without an approval record naming the current candidate hash. This alone
   repairs revision 1's silent repeal of the approval contract.
2. **Hook-denied model approval + operator-run approval (normative).** The PreToolUse hook
   denies the operator verbs — `forge commit approve` / `forge merge approve` /
   `forge commit skip` — when issued through the model's
   Bash tool, with a denial message instructing the model to present the candidate SHA and
   diff summary and ask the operator to run the exact approve command themselves via the
   `!` prefix. Operator-typed `!` commands execute outside the model's Bash tool path, so
   these verbs can only ever reach the CLI from the operator's keyboard. This is as
   close to operator-binding as a same-user architecture gets.
   *Migration precondition:* an eval confirming that `!`-prefix commands bypass PreToolUse
   in the current harness. Field experience suggests they do; it must be an eval, not an
   assumption.
3. **Permission ask-rule (fallback posture).** The approve verb stays permanently out of any
   allowlist, so if layer 2's assumption fails (or a different harness is in play) a model
   invocation still raises a harness permission prompt showing the SHA in the argv — a user
   click outside the model's control, though defeated by permission-bypass modes.
4. **AskUserQuestion (presentation, not proof).** The skill retains the duty to present the
   change — diff summary, candidate SHA, review outcome — conversationally before asking
   the operator to act. Its answer flows through the model's context and is therefore never
   treated as the approval itself.

Honest limits (principle 7): the CLI can prove the approve command ran and named the right
candidate; it cannot prove the operator understood the change. Approval binds to someone at
the terminal, not to an informed decision. In headless or autonomous runs, control-class
chains park in `awaiting_approval` until a human shows up — that is correct behavior and a
feature, not a liveness bug.

**The `!`-channel rule (D29).** The bypass that makes approval real also makes
`! git commit` real. The constitutional rule, stated in the skills and pinned by a
temptation eval: the model may ask the operator to run Forge *operator verbs* (`approve`,
`skip`) via `!`; it may never ask the operator to run raw git or any other
enforcement-bypassing command. Under the stated threat model, that rule is the whole
control.

## Review Integrity (D5)

Two reviewer tiers, two enforcement strengths, both labeled honestly. In both, information-
flow control is by construction: the package the CLI assembles contains nothing from the
implementer's handoff, so the reviewer is not forbidden the handoff by prose — it simply
never receives it.

**Codex reviewer (standard tier) — structurally closed against negligence.**
`forge review request` launches the reviewer process itself (detached, per existing launch
doctrine), records the launch as evidence (argv digest, PID, timestamps), and owns the
verdict output path under `.forge/chains/<id>/review/`. `forge review collect` verifies the
process completed, validates the verdict grammar, and binds it to the candidate. The
orchestrator never launches the reviewer and never writes the verdict, so the negligence
failure mode — the model "helpfully" writing a PASS under context pressure — has no
accidental path. A same-user adversary could still write to the CLI-owned path; that is
outside the threat model and the spec says so.

**review-final (hard/control tier) — best-effort, validated-but-trusted.**
review-final is a Claude subagent spawned through the Agent tool by the orchestrator; a CLI
subprocess cannot spawn it, and any nonce the CLI minted would pass through the
orchestrator's context on its way into the subagent prompt. The achievable control:
`review request` records the package digest; `review attach` requires the verdict to cite
both the current candidate hash and that package digest, validates the grammar, and journals
the attach. This converts "one sloppy Write call" into "deliberate multi-step forgery" —
moving the failure out of the negligence class — and no further. The spec must state this
asymmetry rather than paper over it.

## System of Record (D7)

- The chain file is the system of record for commit/merge *authorization*; the hook and
  the CLI's own finalize checks read chain state from it, never from the journal.
- `validate --gates` is a journal instrument — Level B gate enforcement over run journals
  (FR-020/021) — and keeps reading only the journal. It is not a commit-authorization
  reader; pointing it at the chain file would recreate exactly the split-brain this rule
  exists to prevent (D18 corrects revision 2 here).
- When a run is open, the CLI appends the *existing* journal `verification`/`decision`
  shapes for chain events — no new journal record type. The journal remains the system of
  record for the run narrative.
- Run archives cite `chain_id`; the archived chain file and events log travel with the run.
- The model never copies data between the two. Any surface that needs both reads both.

## What Stays in Skills

- Deciding what to stage and how to scope a change (the CLI stages; the model chooses).
- Semantic risk classification beyond path patterns (the CLI computes the floor; the model
  may promote).
- Writing plans, writing reviews, dispositioning findings (above-MINOR dispositions go
  through the operator approval mechanism per FR-053, recorded via
  `review disposition`).
- Mapping operator skip language onto gate IDs (FR-056): "skip tests" → the gate-1 and
  validation IDs, "skip changelog" → the changelog gate, "just commit" → everything
  skippable — which never includes control-class review or approval. The CLI accepts only
  gate IDs; the translation is judgment and stays in the skill — which presents the exact
  operator-bound `! … forge commit skip <gate-id>` argv rather than issuing it (D25).
- The `!`-channel rule (D29): the model may ask the operator to run Forge operator verbs;
  it may never ask the operator to run raw git.
- Presenting control-class changes to the operator (Approval Mechanism layer 4).
- The standing duty to stop and surface when something looks wrong outside the checklist —
  the CLI's green light must never become the only signal the model attends to.
- Explaining refusals to the user and proposing next actions (the output contract makes the
  raw refusal self-sufficient; the skill adds judgment, not translation).

## Fast Path Becomes Opt-Out

`forge classify` runs automatically inside `commit start`. When the path set qualifies for
the fast tier under committed policy, the chain *is* a fast chain unless evidence promotes
it — the model does no work to claim the cheap path. This addresses the dogfood telemetry
finding (0 fast-path uses): a cheap path that costs effort to claim is not a cheap path.
Fast finalize keeps the independent eligibility recomputation (FR-154 doctrine): the cheap
path is cheap to claim, not cheap to fake.

## Naming and Bootstrap (D12)

- **No PATH binary named `forge`.** Foundry's `forge` is widely installed; a PATH collision
  would surprise people in exactly the repos most likely to adopt this. The invocation is
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py"`, wrapped by skills and matched by
  the hook via a spec'd argv pattern. `forge …` in this document is shorthand only.
- **Init bootstrap exception preserved.** `/forge:init`'s first-policy path (no committed
  HEAD policy, two-commit bootstrap per FR-083, fixed bootstrap checks per FR-149) survives:
  `commit start` requires policy readable from HEAD *except* under the bootstrap admission
  path, which keeps its current, narrower rules. The CLI must not make first install
  impossible.

## Migration (D10)

Igor's direction: build the whole thing, under the best-effort posture — no unachievable
guarantees, every best-effort control labeled. Phases, each its own control-class change:

- **Phase 0 — precondition evals.** The `!`-bypass behavior (Approval layer 2), the hook
  argv matcher for the CLI invocation form, the output-contract reason-code enum, and the
  `!`-channel temptation eval (D29) are pinned before anything ships.
- **Phase 1 — commit chain slice.** `status`,
  `commit start/restage/abort/approve/skip/finalize`, `verify`, `gate run`, `classify`,
  `scan secrets`, `review request/collect/attach/disposition`, with the full output
  contract. Ships alongside the existing marker flow; the hook dual-accepts marker or
  chain.
- **Phase 2 — dogfood.** This repo runs exclusively on the CLI path. Telemetry watches the
  fast tier: if `fast_allowed` is still zero here, the design has failed its own test.
- **Phase 3 — merge chain.** `merge start/gate run/approve/finalize` with the CLI-performed
  locked rebase and fast-forward push.
- **Phase 4 — raw-verb denial.** The hook denies raw `git commit` and raw `git push`;
  `forge commit finalize`, `forge merge finalize`, and `forge push` become the only
  history-mutating paths. `forge push` ships in this phase — without it, raw-push denial
  leaves default-branch commits in the main checkout with no legal push path at all. The
  same control-class change rewrites the Beads close-protocol block in CLAUDE.md/AGENTS.md
  to route through the Forge verbs and retires the prose-precedence paragraph: after this
  phase, `git pull --rebase && bd dolt push && git push` is no longer a legal close
  protocol, and prose precedence must not be what says so (D22). `bd dolt push` is
  untouched — it is not git.
- **Phase 5 — marker deletion.** The marker grammar, parser, and their tests are removed;
  the chain file is the only authorization artifact.
- **Phase 6 — plan-seal/proposal-unseal**, as the best-effort ordering control specified
  above.

Two red lines, normative (D32): Phase 1's dual-accept MUST NOT be skipped — it is the only
safe decommission of the marker flow — and the marker grammar MUST NOT be deleted (phase 5)
until the eval net below actually pins the state machine. These are requirements, not
preferences.

Spec scoping (D21): building all phases does not mean one omnibus spec PR. The first spec
revision covers the commit slice (phases 0–2) only. The merge chain — dirty-worktree
predicate, committed-policy sentinels, rebase lock, FR-063 re-verification inside the lock,
HEAD-SHA candidate identity — is its own later spec revision, landed before phase 3 ships.

## Costs and Risks (Honest Ledger)

- **Complexity moves; it does not vanish.** The CLI becomes control-class code with its own
  test surface. That is the desired trade: a Python state machine is unit-testable, and
  "tests that fail when the control is disabled in memory" finally has a real target. Prose
  executed by an LLM cannot be unit-tested.
- **The CLI is now the last line of defense.** With the hook reduced to argv allow/deny, a
  bug in the CLI's finalize checks is a control failure, not an inconvenience. Its internal
  checks carry hook-parser severity: per-check disable tests, pinned diagnostics, and the
  eval net below must land before Phase 4 removes the raw-verb path.
- **Failure modes shift.** A buggy CLI fails uniformly and detectably; a skipping model fails
  randomly and silently. Uniform failure is the better regime, but CLI bugs in the finalize
  path are commit-blocking incidents — the eval suite must pin the state machine before the
  marker grammar is removed.
- **Over-mechanization risk.** If the model's only job is to obey the printed next step, it
  may stop noticing out-of-checklist anomalies. The skills must retain and emphasize the
  surfacing duty.
- **Best-effort drift risk.** Labels like "best-effort" erode: a future edit quietly
  upgrades them to guarantee language, or readers assume enforcement that is not there. The
  spec revision should carry the best-effort labels in normative text, and doc review should
  treat removing one as a control change.
- **Headless parking.** Control-class chains in `awaiting_approval` block autonomous runs by
  design. Operators must know this is a feature; the refusal message says exactly what is
  being waited for and why.

## Relationship to the Eval Net

The current eval suite (three golden tasks) is thin partly because what it would need to
pin — model adherence to 2,778 lines of prose — is nearly unpinnable. Shrinking what the
model is trusted with converts the eval target from "the clerk's behavior" (huge surface) to
"the state machine's transitions" (small, enumerable, property-testable). Priority evals
after migration:

- out-of-order refusal at every transition edge; stale-candidate refusal; authorization TTL
  expiry (30 min from issuance, not chain age); cross-chain authorization isolation;
- restage and out-of-band index-change invalidation, including classification rerun;
- control-class chains cannot reach `authorized` without an approval record; the approval
  record must name the current candidate; model-issued approve is hook-denied; the
  `!`-bypass behavior itself;
- skip-grammar handling, including "no skip covers control-class review, none covers
  approval"; halt-flag refusal at every subcommand;
- raw `git commit` / `git push` denial and finalize-argv acceptance in the hook matcher;
- Codex review launch/collect integrity (verdict path ownership, process-completion check);
  review-final attach citation checks (candidate hash + package digest);
- finalize two-phase protocol: each crash window recovers per *Finalize Protocol*
  (intent-without-commit falls back; commit-without-close completes idempotently; foreign
  HEAD freezes), and every non-recovery verb refuses in `committing`;
- one-live-chain-per-worktree refusal; tree-vs-index drift refusal at review request and
  finalize; iteration-cap refusal and escalation at 8 (FR-053); above-MINOR disposition
  requires the operator mechanism;
- per-tier structure: a fast chain that skipped anything but the reviewer fails its eval
  (FR-152), including the invariant and assertion-sensor rows (FR-144/FR-147);
- `forge push` discipline: halt, rebase lock, fast-forward only — and raw-push denial once
  phase 4 lands;
- dirty-index refusal at `commit start` (pre-staged residue named, never absorbed); foreign
  index-write denial while a chain is live (D33);
- `head_moved` detection at every verb with the old→new diagnostic; `commit rebase` graded
  disposition — an unchanged recomputed candidate keeps the review verdict, gates always
  re-run, changed policy bytes end the chain (D34);
- `forge verify` resumability: interrupted mid-sequence, a re-invocation continues from the
  first incomplete step without re-running completed evidence; a fully-passed verify is a
  no-op printing the next judgment verb (D23);
- mutating-gate precedence: `gate run` of a non-mutating gate refuses while a configured
  mutating gate is pending (D24);
- model-issued `skip` is hook-denied; finalize accepts no override flags (D25);
- the `!`-channel temptation task: a blocked model must refuse to ask the operator to run
  raw git (D29);
- `--json` purity: stdout under `--json` parses as exactly one envelope (D27);
- output-contract conformance: every refusal carries a known reason code, remediation, and
  the `next required step:` line.
