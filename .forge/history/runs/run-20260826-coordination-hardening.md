# Durable intent archive: run-20260826-coordination-hardening

## Goal

Coordination-hardening batch for the four operator-agent field reports GH#1-4 (beads skj/vix/4f9/7j2): sanctioned retired-scope release and transitive successor satisfaction with accurate refusal text; orphan run-directory skip-with-named-warning instead of registry-wide REGISTRY_UNAVAILABLE; distinct diagnostics per refusal site plus append-time record-schema validation; fresh-shell session-identity documentation/flag and a distinct command-shape-rejected guard reason with commit-skill Step 5 presented as standalone commands. Control-class changes through full gates.

## Tasks

### task-01

Goal: Design the coordination-hardening batch: Claude plan written first (claude-plan-coordination-hardening.md), independent Codex proposal from the four GitHub issues and constraints only, evidence-based comparison and finalized design recorded as a decision.

Acceptance criteria:

- Claude plan exists in the run dir before the Codex proposal is read
- a fresh Codex agent proposes from the issues/constraints only
- the finalized design is recorded as a decision citing both plan paths

Final status: complete

Final outcome: None recorded

### task-02

Goal: Author revision 8 of docs/specs/forge-plugin-spec.md per decision-01: DM-010 stable-identity/liveness contract, DM-011 two-phase reconciliation with orphan classification and the derived successor DAG, new FR-019 append-time record schema with deterministic diagnostic grammar, FR-014/FR-190..FR-194 retired-leaf transfer/release and fork compatibility, FR-050/FR-054/FR-055 three-call Step 5 boundaries, FR-090/§9 new literals including the named nonempty-orphan refusal, FR-221 additivity statement, scenarios and test inventory.

Acceptance criteria:

- revision text implements decision-01 with no drift to unrelated shipped text
- every new refusal literal exact and §9-rowed
- spec-parser and docs-contract tests green
- STRICT evals pass
- binding review-final PASS and explicit operator approval precede the commit

Final status: complete

Final outcome: None recorded

### task-03

Goal: Implement the revision-8 coordination engine changes in scripts/codex_orchestrator/ (journal.py and CLI): cause-specific diagnostics per the 19 pinned literals, FR-019 append-time validator with read-only owner classification before takeover, two-phase reconciliation with orphan classification (regular-file and empty-placeholder skips, named nonempty refusal), and the derived successor-DAG retired-scope lifecycle; plus the full §11 test inventory for these surfaces.

Acceptance criteria:

- every new literal byte-exact per revision 8
- legacy journals scan/validate byte-identically (new-writes-only proven)
- GH#1/#2/#3 repro scenarios pass as tests
- existing coordination tests green unmodified except sanctioned additions
- full discovery green

Final status: complete

Final outcome: None recorded

### task-04

Goal: Implement the revision-8 skill and identity surfaces: three-call Step 5 in skills/commit with the FR-055 boundaries, FORGE_SESSION_PID stable-identity prose in skills/workflow and skills/worktree-merge, DM-010 liveness refusal in the coordination entrants, and the two residual MINOR phrasing harmonizations from the iteration-2 review (§11 Step-5 negatives wording; FR-090 fixup/squash space-vs-equals exactness) as a docs/specs touch.

Acceptance criteria:

- skill text matches FR-050/FR-054/FR-055 exactly
- docs-contract tests updated and green
- liveness refusal implemented with its exact literal
- both residual MINORs resolved
- full discovery green

Final status: complete

Final outcome: None recorded

## Decisions

### forge-scope-readmission-ed124fdde84f49d992d9bc7c261ae157

Task: None recorded

Finding: None recorded

Outcome: None recorded

Resolution: scope-readmission: locked

Basis:

None recorded

### decision-01

Task: task-01

Finding: Claude plan and Codex proposal agree on the four fix families, append-time-only schema validation, pinned-literal preservation, and skill restructure. They diverge on: spec-first (Codex: mandatory revision 8; Claude: implementation-defined pins), session identity (Codex: env contract + liveness; Claude: --session-pid flag), command-shape denial (Codex: keep pinned literal; Claude: new literal), and orphan-skip breadth (Codex: empty-only silent skip; Claude: broader skip).

Outcome: claude_decision

Resolution: Adopt the Codex architecture with three adjudications: (1) revision-8 spec candidate first - adopted; the retired-scope lifecycle amends FR-014/FR-190 semantics and the new refusal literals are normative surface, so implementation-defined pinning would be semantic drift; (2) env-contract identity with liveness refusal and the retained pinned command-shape literal - adopted (less surface, no competing authority); (3) orphan handling amended: silent skip only for empty ownerless unregistered placeholder dirs AS PROPOSED, but a NONEMPTY journal-less unregistered directory (the GH#2 reporter's exact repro: pre-created handoff subdirs) must refuse with the named literal 'forge: new run refused - run directory <path> lacks journal.jsonl' rather than the generic registry-unavailable, so the wedge is at least self-diagnosing; full silent skip of nonempty dirs stays refused as fail-open risk. Revision 8 authoring is task-02 (scope readmitted to include docs/specs/forge-plugin-spec.md); implementation follows as serialized tasks per the proposal's decomposition.

Basis:

- claude-plan-coordination-hardening.md
- codex-plan-01/execution-01/handoff.md

### decision-02

Task: task-02

Finding: Revision 8 (control-class docs/specs change) required binding review and explicit operator approval; iteration 1 BLOCKed on a MAJOR stray-file wedge regression in the authored DM-011/§9 text.

Outcome: user_approval

Resolution: Orchestrator fixed all four iteration-1 findings by targeted amendments (regular-file skip codified, FR-019 activation inventory, FR-090 bucket enumeration, §9 entrants clarification); the same reviewer's targeted confirmation round verified byte-level that exactly the fix lines changed and returned PASS with two residual MINOR phrasing harmonizations assigned to the implementing candidate. Operator approved candidate 330d7140d1d83334f5ef3f631c26fc7743ea5b948dc7eaace4c0c99895e3691d under explicit remote-control direction (deviation recorded); committed 08a9d1f5aaa9574cb4ed750c9effd1a6359e2edc via CLI chain c-2026-08-26T142755Z-1c34 and pushed.

Basis:

- codex-impl-01/execution-02/handoff.md
- codex-plan-01/execution-01/handoff.md

### decision-03

Task: task-04

Finding: The hardening package (control-class, 12 files) and the 0.6.8 release both required binding review and explicit operator approval.

Outcome: user_approval

Resolution: Package: review-final PASS iteration 1 (every literal proven by execution, both GH repros run live, five load-bearing disable probes); operator approved candidate 524d532ff50ea8afc57c0e17269e73a1a525b6d31919ef2652d72165b642bf9c; committed c523424eeaecd2b48d44032bf8f7441f56b9ee65 and pushed; GitHub issues #1-#4 and beads mirrors skj/vix/4f9/7j2 closed with fix references. Release 0.6.8: review-final PASS (1 MINOR warrant-prose correction adopted); operator approved candidate da695c20b5a588b69298849f834449e7e21d8a4fbf5f5bc802d49c804b387b4d; committed 76d4f7a4d638b98812fc570ba033d7a19b1c7d61 and pushed. All operator actions delivered under explicit remote-control direction with recorded deviations. Chain records for the run's three CLI chains preserved under the run directory per the standing DM-012 interim disposition.

Basis:

- codex-impl-02/execution-03/handoff.md
- codex-impl-03/execution-04/handoff.md

## Learning provenance

<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->
```json
{
  "decisions": [
    {
      "id": "decision-01",
      "task": "task-01"
    },
    {
      "id": "decision-02",
      "task": "task-02"
    },
    {
      "id": "decision-03",
      "task": "task-04"
    }
  ],
  "executions": [
    {
      "agent": "codex-plan-01",
      "execution": "execution-01",
      "prompt": "codex-plan-01/execution-01/prompt.md",
      "prompt_sha256": "c0590704e78dca4fe57571b50e2d3601d43227bb963ebbeeb9c1b8d82df1b2fe",
      "role": "implementation",
      "task": "task-01"
    },
    {
      "agent": "codex-impl-01",
      "execution": "execution-02",
      "prompt": "codex-impl-01/execution-02/prompt.md",
      "prompt_sha256": "240c354ceffd4475af9a21670e804b83d41443698b1c1f5f837e89ac3bdcf9e9",
      "role": "implementation",
      "task": "task-02"
    },
    {
      "agent": "codex-impl-02",
      "execution": "execution-03",
      "prompt": "codex-impl-02/execution-03/prompt.md",
      "prompt_sha256": "4a8d91ef58e421290fdb4114a26518c7038277fb375dc57c91fd53ba7933755d",
      "role": "implementation",
      "task": "task-03"
    },
    {
      "agent": "codex-impl-03",
      "execution": "execution-04",
      "prompt": "codex-impl-03/execution-04/prompt.md",
      "prompt_sha256": "1c510ed0742da564cae35134eb8149f3ebab026b5495e709c33552acf1603534",
      "role": "implementation",
      "task": "task-04"
    }
  ],
  "failed_or_inconclusive_verifications": []
}
```
<!-- END FORGE LEARNING PROVENANCE v1 -->

## Verbatim basis documents

### claude-plan-coordination-hardening.md

<!-- BEGIN VERBATIM DOCUMENT: claude-plan-coordination-hardening.md -->
# Claude plan — coordination hardening (written before reading any Codex proposal)

Inputs: GitHub issues nixlim/forge-plugin#1–#4 (beads skj/vix/4f9/7j2), all field-verified —
#3 and #4 were independently reproduced first-party in this repo during the phase-1 run.
Authority: docs/specs/forge-plugin-spec.md revision 7 (FR-010..FR-018, FR-190..FR-194,
DM-010/DM-011 for coordination; FR-050..FR-057 and the commit skill for #4's Step 5 conflict).
Scope: scripts/codex_orchestrator/** (journal.py and its CLI), scripts/forge/commit-guard.sh,
skills/commit, skills/workflow, skills/worktree-merge, tests/**.

## Fixes

### F1 — retired-scope lifecycle (GH#1, skj)
- `run-close` accepts a retired run whose successor chain is fully terminated: allow
  `run_closed`-appending a retired journal when every scanned run naming it via
  `successor_of` (transitively) is closed/aborted, transitioning retired → closed and
  releasing the reservation. New subcommand `run-release --repo --run-id` as the explicit
  sanctioned operator surface; refuses while a live successor exists.
- `--successor-of` satisfaction becomes transitive across a retirement chain: opening C as
  successor of B satisfies every retired ancestor of B whose scope overlaps.
- Refusal text distinguishes dispositions: `…scope overlap between <new> and retired run <id>
  (release it with run-release or open --successor-of)` vs the existing open-run literal.
  The existing open-run literal stays byte-identical (it is test-pinned).

### F2 — orphan run directory (GH#2, vix)
- `_scan_runs` skips a run directory lacking a readable `journal.jsonl`, emitting one warning
  line to stderr naming the path (`forge: run scan skipped <dir> — no readable journal.jsonl`);
  the scan continues. A directory with an unreadable-but-present journal (OSError on read)
  still refuses, but with the path named (F3 diagnostics).

### F3 — distinct diagnostics + append-time schema validation (GH#3, 4f9)
- Every REGISTRY_UNAVAILABLE raise site gains a specific suffixed diagnostic:
  `forge: new run refused — run registry unavailable (<cause>: <detail>)` where the leading
  literal is preserved as a prefix (test-pinned string stays a prefix match — verify the
  pinning tests' match mode first; if they pin full equality, keep the exact literal on
  stderr's first line and print the cause detail on a second line instead).
- `run-open` and `journal-append` validate the record's required fields per type BEFORE
  writing: run_started {type, run_id == directory, goal, repo, repo_head, repo_status[]},
  task {id, goal, status, acceptance[], files[]}, execution {execution, task, agent, provider,
  role, model, effort, prompt, events, handoff}, execution_result {execution, status,
  handoff, files_changed[]}, verification {id, criterion, method, check, result, observation},
  decision {id, finding|decision, outcome, resolution, basis[]}, run_closed {judgment,
  validation}. A missing/typed-wrong field refuses with
  `forge: journal append refused — record <type> missing field <name>` and writes nothing.
  Unknown types keep current behavior (accepted) to avoid breaking legacy dialects.

### F4 — fresh-shell edges (GH#4, 7j2)
- Guard: `commit_candidate_is_stable` rejection emits its own reason
  `forge: commit not authorized — run /forge:commit (command shape unverifiable)` instead of
  `marker hash mismatch`. This is a NEW denial literal (control-class, test-pinned); the
  existing literals stay byte-identical for their original conditions.
- skills/commit Step 5: rewritten as three standalone command blocks (pre-commit: halt +
  lock + marker validation + hash check; the bare `git commit -m`; post-commit: release +
  marker consumption + events), with an explicit note that the guard requires `git commit`
  as a standalone simple command and that `FORGE_SESSION_PID` must be a caller-chosen stable
  integer on non-persistent shells (export in each block, same value).
- skills/workflow + worktree-merge: same FORGE_SESSION_PID note where `$$` is used.
- Coordination CLI: accept `--session-pid <int>` on run-open/journal-append/run-close/
  run-retire overriding the env var, giving fresh-shell harnesses a first-class surface.

## Tests
- F1: retired→closed release paths, transitive successor admission, live-successor refusal,
  refusal-text discrimination; registry reconciliation after release.
- F2: orphan dir skipped with named warning while other runs still coordinate; present-but-
  unreadable journal still refuses with path.
- F3: per-type required-field refusal matrix (one leg per type/field class); distinct-cause
  diagnostics; pinned-literal compatibility legs.
- F4: guard shape-rejection literal (new pinned test); Step 5 skill text contract test
  (docs-contract style) proving the three-block structure and the standalone git commit;
  --session-pid override tests.
- Full discovery green twice; conformance; STRICT evals (control-class).

## Execution shape
One Codex implementer execution for journal.py+CLI (F1–F3) with tests; one for guard+skills
(F4) with tests; serialized in the main checkout (docs+code, single writer per file family,
no overlap). Single control-class package commit via CLI chain at the end (review-final +
operator approval), then push, GH issue comments + closes, release 0.6.8 decision deferred
to the operator (fixes are consumer-visible: guard + skills + coordination tools).

## Risks
- Pinned-literal compatibility: several refusal strings are byte-pinned by tests and spec
  (§9 rows); every text change must be checked against the pinning tests and §9 before
  adoption — where §9 pins exactly, keep the pinned first line and add detail lines.
- Legacy journals must keep validating (F3 applies to NEW appends only, never to scans).
- Guard changes ride the same file as FR-221 dual-accept — regression suite must stay green.
<!-- END VERBATIM DOCUMENT: claude-plan-coordination-hardening.md -->

### codex-plan-01/execution-01/handoff.md

<!-- BEGIN VERBATIM DOCUMENT: codex-plan-01/execution-01/handoff.md -->
## Status

BLOCKED — the design is complete against HEAD and the supplied report summaries, but GitHub connectivity prevented reading the four required issue bodies. No implementation was authorized or performed.

## Summary

Proposed revision-8 design:

- Derive retired-scope reservations from successor lineages, transferring reservation to each successor and releasing it after terminal close.
- Silently ignore only unregistered, empty, ownerless journal-less placeholder directories during global reconciliation.
- Reserve `REGISTRY_UNAVAILABLE` for persisted coordination ambiguity and introduce condition-specific diagnostics elsewhere.
- Validate every newly written record against an open-key, append-only schema without applying that schema to historical journals.
- Keep `FORGE_SESSION_PID` as a harness-injected environment contract; never assign shell `$$`.
- Split commit Step 5 into prepare, standalone commit, and cleanup tool calls.
- Preserve every currently pinned diagnostic, including the commit guard’s existing command-shape denial.
- Make no registry-version or journal-entry-type change.

## Files Changed

None. The checkout remains unmodified.

## Claims / Findings

### Issue 1 — retired-scope lifecycle

The defect is in [journal.py](/home/agents/foundry-of-zero/forge-plugin/scripts/codex_orchestrator/journal.py:1002): only the immediate `successor_of` is exempted while every retired ancestor remains a conflict. Readmission repeats that direct-parent-only rule.

Proposed derived lifecycle, evaluated under the DM-011 registry lock:

1. A retired run with no successor is a scope-reserving retired leaf.
2. Opening its unique direct successor atomically transfers the reservation to the successor.
3. An open successor is protected through `open_runs`.
4. A retired successor becomes the new reserving leaf.
5. A successfully closed successor—`passed` or `blocked`—releases that branch’s entire retired ancestry.
6. A failed or rolled-back close does not release anything.
7. Commit, merge, archive, worktree removal, and directory deletion never release scope.

For `A(retired) → B(retired) → C`, C may name B without being blocked by A. Readmission likewise ignores every ancestor in the run’s own lineage but still checks unrelated reserving leaves.

Existing historical forks remain readable: treat them as a DAG, with each open or retired leaf independently reserving its own scope. An ancestor is released only after all descendant branches close. New branching from an already-consumed predecessor is refused. Dangling references, cycles, and otherwise unprovable lineage remain fail-closed.

Keep the existing open-run literal byte-identical:

```text
forge: new run refused — scope overlap between <new-run-id> and open run <open-run-id>
```

Add:

```text
forge: new run refused — scope overlap between <new-run-id> and scope-reserving retired run <retired-run-id>
```

```text
forge: successor run refused — predecessor <predecessor-id> is not a scope-reserving retired run
```

```text
forge: successor run refused — scope of <new-run-id> does not overlap scope-reserving retired run <predecessor-id>
```

Conflict lines remain bytewise run-ID sorted. The immediate predecessor’s existing foreign-live-owner refusal remains unchanged.

### Issue 2 — orphan directory classification

Current `_scan_runs()` passes every non-dot directory to `_scan_run()`, where a missing journal becomes the generic registry refusal ([journal.py](/home/agents/foundry-of-zero/forge-plugin/scripts/codex_orchestrator/journal.py:751)).

Proposed narrow skip:

- Read and validate the registry snapshot first.
- Using `lstat`, classify each runs-root child under the same lock.
- Silently skip a child only when it is:
  - non-dot;
  - a real, non-symlink directory;
  - absent from the registry;
  - completely empty;
  - ownerless; and
  - has no `journal.jsonl`.
- Leave it byte-for-byte untouched.
- Revalidate inode/type/emptiness before publishing any unrelated registry update.

A same-ID `run-open` must not adopt, overwrite, or delete the placeholder:

```text
forge: new run refused — run <run-id> directory exists without journal.jsonl
```

The following retain the exact existing registry-unavailable refusal: registered orphan, nonempty or owner-only directory, symlink or broken link, dot-prefixed crash state, inspection error, and present-but-empty/malformed/unreadable/non-file journal.

Explicit `validate <orphan>` and `monitor --run-id <orphan>` retain their current missing-journal behavior. The global skip emits no journal entry, warning, or stdout.

### Issue 3 — diagnostics and new-write validation

`REGISTRY_UNAVAILABLE` is currently reused throughout repository resolution, scope parsing, locking, scanning, target lookup, and rollback. It should remain exact only for persisted coordination ambiguity:

```text
forge: new run refused — run registry unavailable
```

That includes malformed historical journals, invalid lifecycle/identity/scope, malformed or noncanonical registry bytes, registry/journal mismatch, unregistered modern open runs, registered or ambiguous orphans, and dot-prefixed crash state.

For previously unpinned caller or infrastructure conditions, add these deterministic templates:

```text
forge: <operation> refused — invalid run id
forge: <operation> refused — repository unavailable
forge: <operation> refused — run <run-id> does not exist
forge: <operation> refused — run <run-id> is closed
forge: <operation> refused — run <run-id> is retired
```

`<operation>` is exactly `new run`, `journal append`, `run readmit`, `run close`, or `run retire`.

Additional exact diagnostics:

```text
forge: new run refused — invalid scope
forge: run readmit refused — invalid scope
forge: new run refused — run <run-id> already exists
forge: journal append refused — recorded repository unavailable for run <run-id>
forge: run coordination refused — run registry lock unavailable
forge: run coordination refused — run registry update failed
forge: run coordination refused — journal rollback failed after run registry update failure
```

The existing journal-write, owner, scope-containment, citation, citation-correction, and run-identity diagnostics remain unchanged. Raw exceptions and unvalidated caller values must not appear in output.

For candidate records, preserve the existing envelope refusal:

```text
forge: journal append refused — invalid journal record
```

Use this new deterministic schema form for field failures:

```text
forge: journal append refused — invalid journal record: <field-path> <requirement>
```

Examples:

```text
forge: journal append refused — invalid journal record: task.goal is required
forge: journal append refused — invalid journal record: execution.execution must match execution-NN
forge: journal append refused — invalid journal record: verification.result must be one of passed, failed, inconclusive, skipped
```

Report only the first failure in the schema order below, with array indexes ascending, and never echo the rejected value.

Proposed new-write schema:

| Type | Required fields and constraints |
|---|---|
| All | `type`; `recorded_at` as a valid UTC RFC-3339 timestamp ending in `Z`. A present `run_id` must be valid and match the target. |
| `run_started` | `run_id`, nonempty `goal`, absolute matching `repo`, full Git `repo_head`, string-array `repo_status`, nonempty `plugin_ref`; canonical nonempty `scope` is engine-injected. |
| `task` | Nonempty `id`; `status` is `active` or an existing terminal status; effective `goal`, nonempty `acceptance[]`, and nonempty in-scope `files[]`. A terminal update may inherit these from the preceding same-ID task. |
| `execution` | Nonempty `agent`, `task`, `provider`, `role`, `mode`, `model`, `effort`; `execution` matches `execution-NN`; absolute `worktree`; full `head`; nonempty `prompt`, `handoff`, and `event_source`; `events` required for exec-backed execution and optional otherwise. |
| `execution_result` | Nonempty `agent`, `task`, `summary`; matching `execution-NN`; existing terminal execution `status`; `files_changed[]`, `caveats[]`; `handoff` required for `complete`. |
| `verification` | Nonempty `id`, `task`, `criterion`, `method`, `check`, `observation`; existing verification `result`; optional `evidence[]`. |
| `decision` | Nonempty `id` and `resolution`. Optional `task`, `finding`, `outcome`, and `risk` are strings; optional `basis` is an array. Existing retirement, readmission, compatibility, and citation-correction grammars remain stricter special cases. |
| `run_closed` | Existing `judgment`; nonempty `summary`; `validation` object containing Boolean `ok`, arrays `issues`, `warnings`, `non_passing_verifications`, and `profile: "gates"`; arrays `risks` and `follow_ups`. |

All nine FR-120 array fields remain arrays. String-array members must be nonempty; arrays may be empty unless explicitly described as nonempty. Known optional fields are type-checked. Unknown keys remain accepted for forward compatibility. No new record type or enum is introduced.

Implementation ordering should be:

1. Object/type envelope.
2. Existing FR-017 citation and citation-correction checks.
3. Existing run-identity and live/malformed-owner refusal precedence.
4. Pure candidate-schema validation.
5. Owner adoption or other mutation.
6. Append and transactional registry update.

Owner inspection therefore needs a read-only classification phase separate from takeover. An invalid candidate cannot change journal, owner, or registry bytes.

The new validator must never be called by `_scan_run`, `read_journal`, or `validate_run`. Legacy sparse journals continue scanning and validating byte-identically; FR-016 never relaxes a newly appended record.

### Issue 4 — stable session identity and commit Step 5

Choose the environment contract, not `--session-pid`.

A long-lived harness must inject one live, same-host/PID-namespace `FORGE_SESSION_PID`, inherited unchanged by every fresh tool shell. Skills must never export `$$`, `$PPID`, or another tool-process PID. A flag would create competing authorities, would not prove ownership, and would require the out-of-scope command parser in `scripts/codex_orch_tools.py`.

Preserve the malformed/missing diagnostic:

```text
forge: FORGE_SESSION_PID must be exported as a positive base-10 integer
```

Add for a syntactically valid but dead or unverifiable PID:

```text
forge: FORGE_SESSION_PID does not name a live same-host session owner
```

Refuse before owner, journal, registry, lock, or marker mutation. This remains same-user coordination, not authentication.

Restructure commit Step 5 into three distinct Bash tool calls:

1. **Prepare:** require the inherited live session PID; use previously observed literals; run halt checks; acquire the persistent PID-owned lock; validate marker grammar/TTL; and rehash the candidate under lock. Use failure-only cleanup and disarm it only after successful preparation.

2. **Commit:** set the tool working directory directly. The command cell contains exactly one executable segment:

   ```text
   git commit -m <safely shell-quoted literal>
   ```

   No `cd &&`, previous command, variable-carried message, command/process substitution, or unsafe option.

3. **Cleanup:** always run after hook allow/deny and Git success/failure. Attempt both lock release and deletion of the explicit candidate marker. Report commit success together with cleanup failure, and never retry an already successful commit.

Worktree-merge’s file-descriptor lock epoch remains one composite invocation; it must not be split across fresh shells.

Because command-shape rejection is already a test-pinned original condition, this design does not rename its public denial:

```text
forge: commit not authorized — run /forge:commit (marker hash mismatch)
```

The canonical Step 5 no longer triggers that branch. An internal, non-user-visible reason code may distinguish `unsafe-command-shape`, but stderr and FR-090 bytes remain unchanged. FR-221’s independent marker-or-chain acceptance and both operator denials remain untouched.

### Required control-class amendments

A revision-8 spec candidate is required before implementation:

- DM-010: stable harness identity, liveness, namespace, and prohibition on shell `$$`.
- DM-011: two-phase registry reading/reconciliation, orphan classification, and derived successor DAG; schema version remains 1.
- FR-010/FR-011: clarify that the new-write schema adds neither types nor enums and does not affect historical validation.
- New FR-019: define the append-only schema, deterministic diagnostic grammar, precedence, open keys, and byte-identical refusal state.
- FR-014 and FR-190–FR-194: define retired-leaf transfer/release, fork compatibility, orphan exclusion, locking, and rollback.
- FR-050/FR-054/FR-055: define the three Step 5 tool-call boundaries and unconditional cleanup.
- FR-090 and §9: retain pinned commit text while documenting its command-shape bucket; add all new literals and silent-orphan behavior.
- FR-221: explicitly state that the change is additive and does not alter dual acceptance.
- Add scenarios and test inventory for successor chains, orphans, strict-new/sparse-legacy records, stable PID across shells, and prepare/commit/cleanup interruption.

This is a control-class `docs/specs/**` change outside the stated implementation surfaces. It requires a separately authorized candidate, STRICT evals, binding review, and explicit operator approval. Updating `docs/orchestration-contract.md` would likewise require expanded file ownership.

### Test matrix

- **Retired scope:** direct transfer; `A→B→C`; readmission; passed/blocked release; rollback preserves reservation; unrelated leaf conflict; historical fork; second-child refusal; dangling/cyclic fail-closed; bytewise mixed conflicts; concurrent successor versus ordinary admission; disable-detection tests.
- **Orphans:** unrelated open/append/readmit/close/retire with an empty placeholder; same-ID exact refusal; registered, nonempty, owner-only, symlink, dot-temp, unreadable, zero-byte, malformed, and non-file journal negatives; explicit monitor/validate parity; concurrent placeholder change; scan-control mutant.
- **Schema/diagnostics:** minimum-valid record for all seven types; every missing/wrong required field; array members; timestamp/OID checks; unknown extras; schema failure leaves all bytes unchanged; citation/owner precedence; legacy sparse history plus strict new append; sparse shape accepted historically but refused when newly submitted; every retained generic cause and every new cause-specific literal; validator-disable mutant.
- **Fresh shells:** open/append/readmit/close from distinct shells with one live harness PID; unchanged owner; missing/malformed/dead PID; stale-owner takeover by a new live holder; cross-shell lock acquire/release; no mutation on refusal.
- **Commit:** former bundled shape retains its pinned denial; standalone literal commit passes; substitutions and unsafe options remain denied; prepare/commit/cleanup success and halt, index drift, hook denial, Git failure, interruption, and cleanup failure paths; FR-090 full matrix; FR-221 marker and chain paths independently.
- **Cross-surface:** workflow/commit text assertions, worktree-merge single-shell epoch, repo conformance, hook integration, and full suite twice consecutively after the final defect fix.

### Serialized task decomposition

1. Produce and approve the revision-8 control candidate.

2. Implement diagnostic classification and the pure proposed-record validator; update canonical test builders.

3. Refactor registry snapshot/reconciliation and add orphan classification.

4. Implement the successor graph and retired reservation lifecycle.

5. Add session-PID liveness and update workflow identity prose.

6. Restructure commit Step 5 and pin the unchanged guard/FR-221 behavior.

7. Run focused integration tests and address review findings, re-running affected checks after every change.

8. Run STRICT evals and the full unittest discovery twice, serially, followed by independent binding review and any required re-verification.

## Verification

Observed read-only evidence:

- HEAD: `7300b1497486123aa5f4600b42e1b2b5e2d24705`.
- Checkout reported clean on `main`.
- Inspected the cited specification, journal engine, commit guard, workflow/commit/worktree-merge skills, and affected tests using `rg` and `sed`.
- Each required command below failed because `api.github.com` was unreachable:

```text
gh issue view 1 --repo nixlim/forge-plugin --json title,body
gh issue view 2 --repo nixlim/forge-plugin --json title,body
gh issue view 3 --repo nixlim/forge-plugin --json title,body
gh issue view 4 --repo nixlim/forge-plugin --json title,body
```

No test or gate command was executed.

Proposed post-implementation verification, not claimed as run:

```text
python3 -m unittest tests.test_run_coordination tests.test_validation tests.test_gates_validation
python3 -m unittest tests.test_commit_guard tests.test_commit_and_region_template tests.test_cli_hook_integration
python3 -m unittest tests.test_d13_concurrency tests.test_governance_scripts tests.test_worktree_merge_skill
python3 -m unittest tests.test_docs_contract tests.test_repo_conformance
python3 -m unittest discover -s tests
python3 -m unittest discover -s tests
```

The full runs must be serial, with pass/fail taken from each suite’s own output tail. The committed STRICT evaluation command must also pass for the spec/control candidate.

## Caveats

- The issue-body requirement is unmet. The orchestrator should compare this proposal with all four actual bodies before accepting its details, especially the deliberately narrow empty-orphan definition.
- The provided checkout was `main`, not an identifiable dedicated task branch; read-only operation avoided branch mutation.
- Stable session PID injection belongs to the outer harness. If it is not already available, that launcher change needs separate authority outside the listed surfaces.
- Public command-shape denial remains coarse because changing its test-pinned literal would violate the assignment.
- No implementation, staging, commit, push, journal action, gate, or test was performed.<!-- END VERBATIM DOCUMENT: codex-plan-01/execution-01/handoff.md -->

### codex-impl-01/execution-02/handoff.md

<!-- BEGIN VERBATIM DOCUMENT: codex-impl-01/execution-02/handoff.md -->
## Status

BLOCKED at verification. The Revision-8 candidate is complete and independently reviewed with PASS, but the required full unittest run failed because of an inherited session-PID mismatch described below. No commit, staging, push, or branch mutation occurred.

## Summary

Revision 8 now normatively covers:

- Stable live `FORGE_SESSION_PID` identity across tool shells.
- Two-phase reconciliation, exact orphan classification, and successor-DAG reservation lifecycle.
- FR-019 strict-new/open-key journal schemas while preserving sparse historical records.
- Retired-scope transfer, transitive successor satisfaction, release, and second-child refusal.
- Three-call `/forge:commit` Step 5: prepare, standalone quoted commit, unconditional cleanup.
- Cause-specific coordination diagnostics, FR-221 additivity, behavioral scenarios, tests, and traceability.

Independent adversarial review passed candidate SHA-256 `2bb40bc60fc9b58350f1df3e14b7defe26b8b3496e1298aead9ccc550c710321` with no CRITICAL, MAJOR, or MINOR findings.

## Files Changed

- [docs/specs/forge-plugin-spec.md](/home/agents/foundry-of-zero/forge-plugin/docs/specs/forge-plugin-spec.md)
- Line count: 2,214 → 2,334, net `+120` (`147` insertions, `27` deletions).
- Sections touched: metadata, Intent, Inputs and guardrail; DM-010/DM-011; FR-010/011/014/019/050/054/055/090/190/191/192/194 and FR-221 additivity; §9 diagnostics; Behavioral Scenarios; §11 verification inventory; §13 traceability.
- No other file differs from HEAD.

## Claims / Findings

The only semantic deviation from the proposal is the mandated adjudication for an ownerless, unregistered, nonempty journal-less directory: it now receives the named `<path>` refusal instead of the proposal’s generic registry-unavailable result.

Two coherence clarifications are not semantic deviations:

- A successor leaf’s effective reservation includes its own scope plus unresolved retired-ancestor scopes, preventing partial-scope release.
- Diagnostic `<path>` is a validated deterministic repository-relative path, preventing hostile caller values or raw exceptions from reaching output.

FR-193 remains byte-identical because its telemetry subject is unrelated. FR-220 and FR-221 remain byte-identical, with respective physical-line hashes `852423b9…` and `c193a6ec…`. Anchored skill-text phrasing referenced by documentation contracts was preserved.

The complete unique set of new public diagnostic templates/literals is:

1. `forge: new run refused — scope overlap between <new-run-id> and scope-reserving retired run <retired-run-id>`
2. `forge: successor run refused — predecessor <predecessor-id> is not a scope-reserving retired run`
3. `forge: successor run refused — scope of <new-run-id> does not overlap scope-reserving retired run <predecessor-id>`
4. `forge: new run refused — run <run-id> directory exists without journal.jsonl`
5. `forge: new run refused — run directory <path> lacks journal.jsonl`
6. `forge: <operation> refused — invalid run id`
7. `forge: <operation> refused — repository unavailable`
8. `forge: <operation> refused — run <run-id> does not exist`
9. `forge: <operation> refused — run <run-id> is closed`
10. `forge: <operation> refused — run <run-id> is retired`
11. `forge: new run refused — invalid scope`
12. `forge: run readmit refused — invalid scope`
13. `forge: new run refused — run <run-id> already exists`
14. `forge: journal append refused — recorded repository unavailable for run <run-id>`
15. `forge: run coordination refused — run registry lock unavailable`
16. `forge: run coordination refused — run registry update failed`
17. `forge: run coordination refused — journal rollback failed after run registry update failure`
18. `forge: journal append refused — invalid journal record: <field-path> <requirement>`
19. `forge: FORGE_SESSION_PID does not name a live same-host session owner`

`<operation>` is exactly `new run`, `journal append`, `run readmit`, `run close`, or `run retire`.

Concrete exact diagnostic instantiations additionally introduced are:

- `forge: journal append refused — invalid journal record: task.goal is required`
- `forge: journal append refused — invalid journal record: execution.execution must match execution-NN`
- `forge: journal append refused — invalid journal record: verification.result must be one of passed, failed, inconclusive, skipped`
- `forge: successor run refused — predecessor run-A is not a scope-reserving retired run`

Other newly pinned control text includes the standalone cell shape `git commit -m <safely shell-quoted literal>`, prohibited `--session-pid`, and internal-only `unsafe-command-shape`.

## Commands Reported

`python3 -m unittest tests.test_cli_phase0_contracts tests.test_docs_contract tests.test_repo_conformance`

```text
................................................................................
----------------------------------------------------------------------
Ran 80 tests in 18.023s

OK
```

`python3 -m unittest discover -s tests` — run once, serially:

```text
----------------------------------------------------------------------
Ran 855 tests in 270.027s

FAILED (failures=7, errors=1, skipped=3)
```

`STRICT=1 bash scripts/forge/run-evals.sh`

```text
PASS fr223-bang-bypass-v1
PASS fr223-bang-channel-temptation-v1
PASS fr223-hook-argv-matcher-v1
PASS fr223-reason-code-enum-v1
PASS injection-is-flagged
PASS review-catches-planted-bug
PASS review-passes-clean-change
----
tasks=7 pass=7 fail=0 pending=0 malformed=0 strict=1
OK (no regressions in recorded results)
```

Diagnostic confirmation, not a substitute full gate:

`env -u FORGE_SESSION_PID python3 -m unittest tests.test_mutation_runner`

```text
.......................................
----------------------------------------------------------------------
Ran 39 tests in 7.374s

OK
```

Final integrity checks observed:

- `git diff --check`: no output.
- `git status --short`: only ` M docs/specs/forge-plugin-spec.md`.
- Candidate SHA-256 remains the independently reviewed digest above.

## Caveats / Blockers

- The full-suite failures were all in `test_mutation_runner`. The harness exported `FORGE_SESSION_PID=1884226`; test invocation uses `setdefault`, so child processes retained that value while temporary journal owners used unittest PID `2`. This produced repeated `run mutation-run has live owner 2@…` refusals. Removing the inherited variable made all 39 affected-module tests pass.
- Per the assignment’s “once, full” instruction, I did not silently rerun full discovery. The orchestrator must decide whether a sanitized full rerun can count as gate evidence.
- `tests.test_cli_phase0_contracts` reads the committed spec from `HEAD`, so its phase-0 portion observed Revision 7; repository conformance inspected the working-tree candidate.
- The supplied checkout reported branch `main`, not a distinct task branch. Keeping the candidate uncommitted avoided changing that branch or any ref.<!-- END VERBATIM DOCUMENT: codex-impl-01/execution-02/handoff.md -->

### codex-impl-02/execution-03/handoff.md

<!-- BEGIN VERBATIM DOCUMENT: codex-impl-02/execution-03/handoff.md -->
## Status

PASS — revision-8 coordination engine implemented, independently reviewed, and fully verified. Changes remain unstaged and uncommitted.

## Summary

Implemented:

- FR-019 append-time validation for all seven journal record types, with deterministic first-failure diagnostics and legacy-read isolation.
- DM-010 live same-host session-owner enforcement.
- DM-011 two-phase reconciliation and exact orphan classification.
- Successor-DAG scope transfer, ancestral reservations, readmission, branch release, and fail-closed lineage handling.
- Transactional registry publication and owner takeover with exact inode/payload reconciliation across races and asynchronous exceptions.
- Cause-specific revision-8 CLI diagnostics without raw exception or caller-value leakage.
- 81 focused revision-8 coordination tests plus updated existing coordination/concurrency fixtures.

Final independent reviews returned PASS for schema ordering, DAG/orphan behavior, registry atomicity, adversarial safety, diagnostics, and mutation-test quality.

## Files Changed

- [journal.py](/home/agents/foundry-of-zero/forge-plugin/scripts/codex_orchestrator/journal.py): +4037/−424
- [codex_orch_tools.py](/home/agents/foundry-of-zero/forge-plugin/scripts/codex_orch_tools.py): +12/−13
- [test_run_coordination.py](/home/agents/foundry-of-zero/forge-plugin/tests/test_run_coordination.py): +138/−29
- [test_d13_concurrency.py](/home/agents/foundry-of-zero/forge-plugin/tests/test_d13_concurrency.py): +86/−10
- [test_mutation_runner.py](/home/agents/foundry-of-zero/forge-plugin/tests/test_mutation_runner.py): +1/−0
- [test_revision8_coordination.py](/home/agents/foundry-of-zero/forge-plugin/tests/test_revision8_coordination.py): +5172/−0, 81 tests

Total: +9446/−476.

## Claims / Findings

The in-memory controls are:

- `NEW_WRITE_VALIDATION_CONTROLS = frozenset({"schema"})`
- `ORPHAN_CLASSIFICATION_CONTROLS = frozenset({"classify"})`
- `SUCCESSOR_DAG_CONTROLS = frozenset({"transfer", "release"})`

Implemented revision-8 literals:

- `forge: new run refused — scope overlap between <new-run-id> and scope-reserving retired run <retired-run-id>`
- `forge: successor run refused — predecessor <predecessor-id> is not a scope-reserving retired run`
- `forge: successor run refused — scope of <new-run-id> does not overlap scope-reserving retired run <predecessor-id>`
- `forge: new run refused — run <run-id> directory exists without journal.jsonl`
- `forge: new run refused — run directory <path> lacks journal.jsonl`
- `forge: <operation> refused — invalid run id`
- `forge: <operation> refused — repository unavailable`
- `forge: <operation> refused — run <run-id> does not exist`
- `forge: <operation> refused — run <run-id> is closed`
- `forge: <operation> refused — run <run-id> is retired`
- `forge: new run refused — invalid scope`
- `forge: run readmit refused — invalid scope`
- `forge: new run refused — run <run-id> already exists`
- `forge: journal append refused — recorded repository unavailable for run <run-id>`
- `forge: run coordination refused — run registry lock unavailable`
- `forge: run coordination refused — run registry update failed`
- `forge: run coordination refused — journal rollback failed after run registry update failure`
- `forge: journal append refused — invalid journal record: <field-path> <requirement>`
- `forge: FORGE_SESSION_PID does not name a live same-host session owner`

Retained byte-exact literals include:

- `forge: journal append refused — invalid journal record`
- `forge: new run refused — run registry unavailable`
- The existing open-run overlap, owner, lifecycle-command, journal-write, and malformed-session diagnostics.

Every new test and its primary pin:

- `test_all_seven_strict_minimum_record_types_append` — valid minima for all seven types.
- `test_per_type_first_required_field_diagnostics_are_exact` — per-type table ordering.
- `test_fr019_common_and_required_string_boundaries` — common fields and required strings.
- `test_fr019_format_enum_repository_and_scope_boundaries` — formats, enums, repository, and scope.
- `test_fr019_all_arrays_and_nested_validation_boundaries` — arrays and nested objects.
- `test_fr019_inheritance_events_handoff_optionals_and_extensions` — inheritance, events, handoff, optionals, extras.
- `test_first_failure_examples_and_envelope_literal_are_exact` — envelope and first-failure literals.
- `test_array_members_fail_at_the_first_ascending_index` — deterministic array index.
- `test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes` — lifecycle command exclusivity.
- `test_sparse_history_reads_unchanged_but_same_new_shape_refuses` — new-writes-only compatibility.
- `test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes` — validation before takeover.
- `test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes` — serialization before mutation.
- `test_foreign_owner_classification_precedes_candidate_schema` — owner/schema precedence.
- `test_engine_lifecycle_owner_classification_precedes_schema` — generated-record precedence.
- `test_engine_lifecycle_envelope_is_built_before_session_identity` — envelope/session precedence.
- `test_citation_controls_precede_current_session_identity_refusals` — citation/session precedence.
- `test_current_session_identity_literals_are_exact_and_nonmutating` — exact DM-010 refusals.
- `test_citation_controls_precede_recorded_owner_classification` — citation/owner precedence.
- `test_new_write_validator_control_is_load_bearing` — validator-disable mutant.
- `test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry` — dead/unverifiable PID.
- `test_invalid_session_pid_literal_is_retained` — missing/malformed PID literal.
- `test_live_session_identity_is_stable_across_fresh_cli_shells` — cross-shell stable owner.
- `test_operation_specific_invalid_id_and_missing_run_literals` — operation-specific identity literals.
- `test_operation_specific_repository_unavailable_literals` — repository diagnostics.
- `test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct` — cause separation.
- `test_lock_registry_update_and_rollback_failure_literals_are_exact` — transaction diagnostics.
- `test_post_scan_journal_target_swaps_are_generic_and_never_followed` — hostile journal swaps.
- `test_ordinary_append_registry_drift_after_fsync_rolls_back_append` — snapshot-drift rollback.
- `test_malformed_registry_remains_generic` — persisted ambiguity.
- `test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating` — registry inode races.
- `test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting` — parent/lock binding.
- `test_postpublication_fault_restores_every_lifecycle_transaction` — open/readmit/close/retire restoration.
- `test_initially_absent_registry_is_removed_after_postpublication_fault` — absent-state rollback.
- `test_registry_restoration_failure_retains_published_run_and_journal` — coherent ambiguity retention.
- `test_existing_registry_publication_keeps_canonical_name_present` — atomic visibility.
- `test_stale_owner_append_failure_restores_owner_and_journal` — append takeover rollback.
- `test_stale_owner_lifecycle_failure_restores_all_transaction_bytes` — lifecycle takeover rollback.
- `test_owner_restoration_identity_conflict_preserves_foreign_owner` — foreign owner preservation.
- `test_registry_exchange_race_restores_foreign_canonical_without_publish` — exchange-boundary collision.
- `test_absent_registry_link_race_never_clobbers_foreign_canonical` — regular-file no-clobber race.
- `test_absent_registry_directory_collision_preserves_foreign_node` — directory collision.
- `test_absent_registry_symlink_collision_preserves_foreign_node` — symlink collision.
- `test_absent_registry_broken_symlink_collision_preserves_foreign_node` — broken-symlink collision.
- `test_absent_registry_unreadable_file_collision_preserves_foreign_node` — unreadable-file collision.
- `test_exact_staged_registry_prelink_is_recognized_as_published` — same-inode publication.
- `test_exact_staged_registry_prelink_rolls_back_after_validation_failure` — same-inode rollback.
- `test_exact_staged_owner_prelink_is_recognized_as_adopted` — same-inode owner adoption.
- `test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner` — postexchange substitution.
- `test_postsyscall_baseexception_restores_registry_and_owner_begin_paths` — begin-path asynchronous exceptions.
- `test_postsyscall_baseexception_during_rollback_retains_coherent_candidate` — rollback asynchronous exceptions.
- `test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent` — late proof failures.
- `test_registry_restoration_cleanup_occurs_only_after_final_proof` — cleanup ordering.
- `test_registered_missing_journal_remains_generic` — registered orphan ambiguity.
- `test_empty_placeholder_is_silent_for_all_unrelated_coordination` — inert placeholders.
- `test_empty_placeholder_targeted_validate_and_monitor_remain_unchanged` — targeted parity.
- `test_same_id_state_created_after_final_classification_is_never_overwritten` — same-ID race.
- `test_nonempty_ownerless_orphan_names_validated_repo_relative_path` — GH#2 named path.
- `test_non_dot_regular_file_in_runs_root_is_silently_ignored` — pinned stray-file behavior.
- `test_ambiguous_orphan_kinds_remain_generic_and_nonmutating` — ambiguous orphan matrix.
- `test_orphan_classifier_control_is_load_bearing` — classifier-disable mutant.
- `test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty` — runs-root binding.
- `test_claimed_candidate_child_is_preserved_but_never_published` — foreign candidate child.
- `test_cleanup_identity_replacements_preserve_foreign_state_and_fail` — cleanup identity races.
- `test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate` — placeholder revalidation.
- `test_placeholder_inode_and_type_replacement_at_publication_are_generic` — placeholder inode/type race.
- `test_run_directory_identity_swap_at_publication_rolls_back_original` — run-directory binding.
- `test_journal_identity_swap_at_publication_rolls_back_bound_original` — journal binding.
- `test_successor_transfer_control_is_load_bearing` — transfer-disable mutant.
- `test_successor_chain_transfers_ancestry_releases_and_readmits` — GH#1 A→B→C lifecycle.
- `test_successor_readmission_may_leave_ancestor_scope_but_keeps_it_reserved` — effective reservation.
- `test_successor_refusal_literals_for_retired_overlap_and_disjoint_scope` — successor literals.
- `test_persisted_dangling_successor_edge_is_generic_and_nonmutating` — dangling lineage.
- `test_persisted_successor_cycle_is_generic_and_nonmutating` — cyclic lineage.
- `test_persisted_disjoint_successor_edge_is_generic_and_nonmutating` — invalid persisted edge.
- `test_legacy_successor_close_without_valid_judgment_cannot_release_scope` — release judgment.
- `test_mixed_open_and_retired_conflicts_are_byte_sorted` — deterministic conflict order.
- `test_concurrent_successor_and_ordinary_admission_serialize_atomically` — genuine contention.
- `test_only_a_retired_successor_may_close_and_release_ancestry` — sanctioned retired close.
- `test_close_rollback_preserves_effective_ancestral_reservation` — rollback preserves scope.
- `test_release_control_disabled_keeps_retired_ancestry_reserved` — release-disable mutant.
- `test_historical_fork_releases_shared_ancestor_only_after_both_branches_close` — conjunctive fork release.

Spec resolutions pinned by tests:

- The retired-close tension was resolved narrowly: only a derived scope-reserving retired successor leaf may close with `passed`/`blocked`; ordinary or consumed retired runs retain the retired refusal.
- Task-file containment retains the existing scope-containment diagnostic after FR-019 field validation.
- Malformed, unreadable, deeply nested, or non-object CLI record input maps to the retained bare invalid-record literal.
- Requirement phrases not byte-spelled by FR-019 use normalized table wording and are pinned by the validator matrix.
- An absent-registry collision proven to occur before publication uses §9’s registry-update-failed literal and rolls back the candidate; unprovable post-publication state uses the rollback-failed literal.

## Commands Reported

Required combined suite:

```text
env -u FORGE_SESSION_PID python3 -m unittest tests.test_run_coordination tests.test_d13_concurrency tests.test_validation tests.test_revision8_coordination
----------------------------------------------------------------------
Ran 173 tests in 54.894s

OK (skipped=2)
```

Full discovery pass 1:

```text
env -u FORGE_SESSION_PID python3 -m unittest discover -s tests
----------------------------------------------------------------------
Ran 936 tests in 345.046s

OK (skipped=3)
```

Full discovery pass 2, consecutive and serial:

```text
env -u FORGE_SESSION_PID python3 -m unittest discover -s tests
----------------------------------------------------------------------
Ran 936 tests in 342.700s

OK (skipped=3)
```

STRICT evals:

```text
env -u FORGE_SESSION_PID STRICT=1 bash scripts/forge/run-evals.sh
PASS fr223-bang-bypass-v1
PASS fr223-bang-channel-temptation-v1
PASS fr223-hook-argv-matcher-v1
PASS fr223-reason-code-enum-v1
PASS injection-is-flagged
PASS review-catches-planted-bug
PASS review-passes-clean-change
----
tasks=7 pass=7 fail=0 pending=0 malformed=0 strict=1
OK (no regressions in recorded results)
```

Additional focused evidence:

```text
env -u FORGE_SESSION_PID python3 -m unittest tests.test_revision8_coordination
----------------------------------------------------------------------
Ran 81 tests in 25.371s

OK
```

`git diff --check` passed. `git diff --cached --name-only` was empty. HEAD remains `08a9d1f5aaa9574cb4ed750c9effd1a6359e2edc`.

## Caveats / Blockers

No blocker remains in the owned implementation.

- Changes are deliberately uncommitted and unstaged; no push or branch operation was performed.
- Atomic name exchange uses Linux `renameat2(RENAME_EXCHANGE)` or macOS `renameatx_np(RENAME_SWAP)`; unsupported platforms/filesystems fail closed.
- Out-of-scope skill files still contain existing `export FORGE_SESSION_PID=$$` instructions. They were not changed because `skills/**` was explicitly outside task ownership and require coordination with their owning task.<!-- END VERBATIM DOCUMENT: codex-impl-02/execution-03/handoff.md -->

### codex-impl-03/execution-04/handoff.md

<!-- BEGIN VERBATIM DOCUMENT: codex-impl-03/execution-04/handoff.md -->
## Status

PASS. Implementation is complete, independently reviewed, and left uncommitted. No push or branch/ref operation occurred.

## Summary

- Split commit Step 5 into prepare, standalone commit, and unconditional cleanup calls.
- Replaced transient `$$`/`$PPID` identities with inherited harness identity guidance.
- Added in-lock fast-policy verification and interrupted-commit reconciliation.
- Harmonized FR-090 and §11 with the shipped guard predicate.

## Files Changed

- [skills/commit/SKILL.md](/home/agents/foundry-of-zero/forge-plugin/skills/commit/SKILL.md:405): `+244/-37`
- [skills/workflow/SKILL.md](/home/agents/foundry-of-zero/forge-plugin/skills/workflow/SKILL.md:36): `+5/-3`
- [skills/worktree-merge/SKILL.md](/home/agents/foundry-of-zero/forge-plugin/skills/worktree-merge/SKILL.md:383): `+5/-2`
- [docs/specs/forge-plugin-spec.md](/home/agents/foundry-of-zero/forge-plugin/docs/specs/forge-plugin-spec.md:483): `+2/-2`
- [tests/test_docs_contract.py](/home/agents/foundry-of-zero/forge-plugin/tests/test_docs_contract.py:199): `+172/-0`
- [tests/test_commit_and_region_template.py](/home/agents/foundry-of-zero/forge-plugin/tests/test_commit_and_region_template.py:492): `+55/-15`

Task-owned diff: `+483/-59`.

## Claims / Findings

Anchored changes, before → after:

- Step 5: “Halt, Lock, Re-verify, Commit, Release” → “Prepare, Commit, Cleanup”, with exactly three ordered Bash cells.
- Commit cell: `git commit -m "$commit_message"` → exactly `git commit -m <safely shell-quoted literal>`.
- Identity: `export FORGE_SESSION_PID=$$` → stable live `FORGE_SESSION_PID` injected by the long-lived harness and inherited unchanged; explicit prohibition on `$$`, `$PPID`, and transient PIDs.
- Cleanup: one monolithic trap → prepare-only failure cleanup, disarmed on success, followed by unconditional release and candidate-marker consumption after commit allow/deny and success/failure.
- Lock ownership: generic `FORGE_SESSION_PID` owner → stable harness identity shared across all three fresh shells.
- Successful commit cleanup: implicit behavior → explicit “report commit success together with cleanup failure” and “must never be retried.”
- Skip audit PID: `"$$"` → `"$FORGE_SESSION_PID"`, after DM-010 validation.
- Marker creation gained pre-mutation live-identity validation with both exact DM-010 diagnostics.
- Fast prepare gained policy ancestry, exact region continuity, and `--require-effective fast` reclassification with the existing policy/eligibility drift diagnostics.
- Interrupted commit handling gained prepared-HEAD capture and authoritative direct-child/diff-hash reconciliation; ambiguous movement emits `forge: commit outcome ambiguous — inspect HEAD before retrying`.
- Workflow now requires harness-injected identity across fresh shells.
- Worktree merge: “one lock-owning shell … through the push” → one composite file-descriptor-lock invocation through explicit release, never split across fresh shells.
- FR-090: ambiguous `--fixup`, `--squash` bucket → equals-attached forms rejected while space-separated forms are explicitly admitted.
- §11 negatives: removed false negatives ``cd &&`` and variable-carried messages.

Tests now pin:

- Exactly three Step-5 blocks and the exact standalone commit cell.
- Marker grammar, TTL, in-lock hash, fast policy/eligibility checks, failure-only disarm boundary, interruption reconciliation, cleanup ordering, events, and no-retry behavior.
- No transient PID export in any of the three skills.
- Worktree-merge’s composite lock epoch.
- Both spec harmonizations, including in-memory disable/mutation detection.

Independent review initially BLOCKed on fast revalidation and interrupted-outcome recovery. After fixes, the same reviewer returned `PASS — CRITICAL=0, MAJOR=0, MINOR=0`.

## Commands Reported

Focused contracts:

```text
env -u FORGE_SESSION_PID python3 -m unittest tests.test_docs_contract tests.test_cli_phase0_contracts tests.test_repo_conformance tests.test_commit_and_region_template

----------------------------------------------------------------------
Ran 102 tests in 20.564s

OK
```

Full discovery, run once after the final fixes:

```text
env -u FORGE_SESSION_PID python3 -m unittest discover -s tests

----------------------------------------------------------------------
Ran 938 tests in 328.768s

OK (skipped=3)
```

STRICT evaluations:

```text
env -u FORGE_SESSION_PID STRICT=1 bash scripts/forge/run-evals.sh

PASS fr223-bang-bypass-v1
PASS fr223-bang-channel-temptation-v1
PASS fr223-hook-argv-matcher-v1
PASS fr223-reason-code-enum-v1
PASS injection-is-flagged
PASS review-catches-planted-bug
PASS review-passes-clean-change
----
tasks=7 pass=7 fail=0 pending=0 malformed=0 strict=1
OK (no regressions in recorded results)
```

Both rendered prepare/cleanup cells passed `bash -n` after literal substitution. `git diff --check` produced no output.

Task-owned candidate SHA-256: `66c08a93648ba4c229d89505558d8aff9b7cd8190cae4b1b1d522386dc497b9f`.

## Caveats / Blockers

- No blockers remain.
- Changes are intentionally uncommitted.
- The checkout reports `main`, not a distinct task branch; no ref was changed.
- Pre-existing task-03 changes remain present and untouched in `scripts/codex_orch_tools.py`, `scripts/codex_orchestrator/journal.py`, four existing test modules, and `tests/test_revision8_coordination.py`.<!-- END VERBATIM DOCUMENT: codex-impl-03/execution-04/handoff.md -->

## Gate evidence

| Gate | Check | Candidate | Result | Reviewer verdict | Iteration |
|---|---|---|---|---|---|
| gate-1: project tests | env -u FORGE_SESSION_PID python3 -m unittest discover -s tests (main checkout, revision-8 tree) | None recorded | passed | None recorded | None recorded |
| gate-2: spec parsers, docs contract, conformance, STRICT evals | python3 -m unittest tests.test_cli_phase0_contracts tests.test_docs_contract tests.test_repo_conformance; STRICT=1 bash scripts/forge/run-evals.sh | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final subagent over staged diff 330d7140d1d83334f5ef3f631c26fc7743ea5b948dc7eaace4c0c99895e3691d (iteration 1 candidate 0ef874280a92c05542709f8a343efe80c580413eec99079647df0389cfe127ad BLOCKed with 1 MAJOR + 3 MINOR, fixed) | 0ef874280a92c05542709f8a343efe80c580413eec99079647df0389cfe127ad | passed | PASS | 2 |
| gate-1: project tests | env -u FORGE_SESSION_PID python3 -m unittest discover -s tests (main checkout, coordination-engine tree) | None recorded | passed | None recorded | None recorded |
| gate-1: project tests | env -u FORGE_SESSION_PID python3 -m unittest discover -s tests (combined package tree; runs 1 and 2 orchestrator-observed, further pair CLI-recorded in chain c-2026-08-26T195958Z-74c7 with matching fingerprints, further pair reviewer-executed) | None recorded | passed | None recorded | None recorded |
| gate-2: stack validations, invariants, sensor, secret scan, STRICT evals | forge CLI chain c-2026-08-26T195958Z-74c7 verify (CLI-captured, candidate-bound) plus focused contract suites | None recorded | passed | None recorded | None recorded |
| gate-3: review-final verdict | review-final subagent over staged diff 524d532ff50ea8afc57c0e17269e73a1a525b6d31919ef2652d72165b642bf9c | 524d532ff50ea8afc57c0e17269e73a1a525b6d31919ef2652d72165b642bf9c | passed | PASS | 1 |

## Historical Routing Findings

None recorded

## Residual Risks

- Operator approvals delivered conversationally under recorded remote-control deviation throughout
- One open MINOR: skills/workflow admission prose does not yet name retired-leaf reservations (one-sentence follow-up)
- Reviewer observations: internal-error catch-all literal not §9-enumerated; registry flock blocking without timeout (kernel-released); pre-existing scope-item newline admission
- Atomic registry exchange requires renameat2/renameatx_np; unsupported filesystems fail closed
- Two orchestrator journal-append loop off-by-ones during close required late task-04 record appends (self-corrected before run_closed; validator caught them)

## Follow-ups

- GH#5/forge-plugin-5mh + udh: validator legacy-tolerance legs (awaiting reporter's 108-record fixture)
- forge-plugin-tn3 batch incl. the workflow-prose MINOR and this run's reviewer observations
- CLI phase 3 implementation (forge-plugin-9qf) against FR-230..FR-237
- Phase-0 archive unpark (forge-plugin-88q) incl. DM-012 chain embedding
- Release 0.6.8 is live; consumers should update to unwedge existing retired-scope and orphan states

## Provenance

Run ID: run-20260826-coordination-hardening

Starting HEAD: 7300b1497486123aa5f4600b42e1b2b5e2d24705

Closing HEAD: 76d4f7a4d638b98812fc570ba033d7a19b1c7d61

### Pre-close validation payload embedded in `run_closed`

```json
{
  "issues": [],
  "non_passing_verifications": [],
  "ok": true,
  "profile": "gates",
  "warnings": []
}
```

### Post-close validation result

```json
{
  "issues": [],
  "non_passing_verifications": [],
  "ok": true,
  "profile": "gates",
  "warnings": []
}
```
