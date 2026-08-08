# Adjudicated Review: forge-plugin Specification

Source: `docs/specs/forge-plugin-spec-review.md` (external model, verdict BLOCK, 18 findings).
Adjudication: Claude (this session, 2026-08-08) — every finding verified against the spec text, `upstream/` sources, the grill-spec skill, and current Codex documentation.
Outcome: 9 confirmed, 7 partially confirmed, 1 refuted (MIN-002 evidence; heading fix kept as NIT), 1 observation accepted as convention.
Corrections applied relative to the source review: schema-level gate evidence replaced with convention-level change-set identity (preserves D4 Level B); lock-across-review replaced with marker-hash binding + lock over stage-verify→commit (preserves 8-iteration protocol); per-FR traceability matrix declined (plan-spec template mandates rolled-up ranges); model routing resolved by user directive (gpt-5.6 series; implementer = gpt-5.6-sol @ ultra).

Cycle: 1

## Issues

```yaml
issues:
  - id: ADJ-001
    severity: BLOCKER
    dimension: Incorrectness
    section: "FR-021, FR-024 (Level B / close sequence)"
    finding: >
      Temporal gap: FR-021's issue fires only when a run_closed judgment:passed entry
      already exists, but FR-024 mandates validate --gates BEFORE run_closed is appended
      and nothing mandates a post-close validation. Within the prescribed lifecycle the
      central Level B check can never fire; it is post-hoc only.
    recommendation: >
      Close sequence becomes: validate --gates (pre-close, advisory) -> run_closed ->
      validate --gates (MUST exit 0) -> report.md. The report skill MUST refuse to write
      report.md if the post-close validation reports issues. Update FR-024, the workflow
      skill close sequence, SC-002/SC-003 fixtures, and the doc-contract assertion for the
      close sequence string.

  - id: ADJ-002
    severity: BLOCKER
    dimension: Incompleteness
    section: "FR-021 (Level B)"
    finding: >
      A passed close requires only a passing gate-3 verification; no gate-1 or gate-2
      records are required at all. A run can close passed with tests/lint never journaled.
    recommendation: >
      FR-021 requires, for a run_closed judgment:passed, passing verifications for ALL
      THREE gate prefixes (gate-1:, gate-2:, gate-3:) positioned after the terminal
      execution_result of every mutating execution. Zero-mutating runs remain exempt.

  - id: ADJ-003
    severity: BLOCKER
    dimension: Incorrectness
    section: "FR-022 (Level B recheck matching)"
    finding: >
      Failed-gate rechecks match by "gate-N: " prefix, so a passing "gate-1: unit tests"
      clears an unrelated failed "gate-1: blast radius" verification.
    recommendation: >
      Rechecks MUST match on the exact criterion string of the failed verification, not
      the prefix. Update FR-022, its issue string, and SC-003 fixtures.

  - id: ADJ-004
    severity: BLOCKER
    dimension: Insecurity
    section: "FR-050, FR-052, FR-054, DM-006 (commit chain byte-binding)"
    finding: >
      Review (Step 4) happens before staging (Step 5); the spec never requires that the
      reviewed bytes equal the staged bytes equal the marker hash. Upstream
      commit-workflow.md stages first and reviews git diff --cached; the spec dropped
      that ordering. FR-052 additionally allows secret-containing files to be "excluded"
      from review yet still committed.
    recommendation: >
      Reorder: stage explicit paths FIRST; secret-scan and review exactly git diff
      --cached; a secret finding BLOCKS (files are unstaged, never silently excluded);
      DM-006 marker hash = SHA-256 of the reviewed staged diff; the PreToolUse guard
      recomputes git diff --cached at commit time and denies on mismatch. The commit lock
      covers stage-verify -> commit only, NOT the review loop (8-iteration protocol vs
      300s lock timeout).

  - id: ADJ-005
    severity: BLOCKER
    dimension: Insecurity
    section: "FR-062, FR-063 (merge chain ordering)"
    finding: >
      Inside the rebase lock the sequence is fetch -> rebase -> push, with Gate 1 re-run
      only after the push ("before cleanup"). A rebase-broken result reaches the default
      branch before any re-verification. (Verified: this ordering is inherited verbatim
      from upstream worktree-workflow.md Step 7 — an upstream weakness, not a new
      drafting error; fix it here regardless.)
    recommendation: >
      Inside the lock: fetch; rebase; if the base advanced, re-run Gate 1 AND Gate 2
      against the integrated tree BEFORE push; if the rebase had conflicts, additionally
      re-run Gate 3 (content changed); any failure leaves the remote untouched and
      releases the lock. Update the Locked rebase scenario and traceability row.

  - id: ADJ-006
    severity: BLOCKER
    dimension: Insecurity
    section: "FR-060 (merge chain, Gate 4)"
    finding: >
      /forge:worktree-merge never classifies the merge diff as control/non-control; Gate 4
      is "diff summary then automatic proceed". Since Codex implementers commit ungated in
      worktrees (D1), reintegration is the ONLY governance point — control-class changes
      (.codex/**, eval baselines, forge-project.md, constitution) can reach the default
      branch without human approval, bypassing FR-051.
    recommendation: >
      Classify the full merge diff (origin/<default>...HEAD) against the control category
      before Gate 1. If control-class paths are touched, require explicit user approval
      after Gate 3 PASS and before the lock/push, with the approval bound to the candidate
      SHA. Add an Error Path scenario.

  - id: ADJ-007
    severity: BLOCKER
    dimension: Insecurity
    section: "FR-039, SC-006 (execpolicy)"
    finding: >
      forge.rules denies only force-push variants; SC-006 asserts plain "git push origin
      HEAD" is NOT forbidden — inherited from upstream forge where the primary agent
      pushed. In this design no Codex process ever pushes (D1: Claude owns all
      reintegration), so any push capability is pure attack/accident surface.
    recommendation: >
      Deny ALL git push forms in forge.rules (prefix rule on "git push"). Flip SC-006 to
      expect verdict=forbidden for plain push. Note Codex sandbox default network
      restrictions as defense-in-depth, not as the control.

  - id: ADJ-008
    severity: BLOCKER
    dimension: Insecurity
    section: "FR-090 (commit guard scoping)"
    finding: >
      The marker check applies only when .forge-manifest exists in the working tree, so
      the very commit that deletes .forge-manifest evades the guard, and any actor can
      disable enforcement by deleting one file.
    recommendation: >
      The guard treats a repo as forge-governed when .forge-manifest is tracked in HEAD
      (e.g. git ls-files --error-unmatch / git cat-file -e HEAD:.forge-manifest), not when
      it is present in the working tree. Removing forge governance therefore requires a
      commit that itself passes the gate chain. Add an adversarial scenario (manifest
      staged for deletion).

  - id: ADJ-009
    severity: BLOCKER
    dimension: Insecurity
    section: "FR-064, FR-131 (worktree cleanup)"
    finding: >
      Implementers only MAY commit; Gate 3 reviews only the committed range; cleanup runs
      git worktree remove --force + git branch -D with no clean-tree precondition.
      Uncommitted/untracked work is silently absent from review AND destroyed on the
      success path.
    recommendation: >
      Precondition for the merge gates: git status --porcelain=v1 --untracked-files=all in
      the worktree MUST be empty; dirty -> stop and recover (commit via chain or
      explicitly discard with user approval). Use non-force worktree remove as backstop;
      delete the branch only after the push is verified. Add Error Path scenario.

  - id: ADJ-010
    severity: BLOCKER
    dimension: Infeasibility
    section: "FR-030, FR-034, FR-038 (model routing)"
    finding: >
      Two confirmed defects: (a) the codex exec launch pattern selects no model or
      reasoning effort, and .codex/agents/*.toml configures in-session subagents, not
      direct launches — FR-030's role/model matrix has no executable mechanism; (b) the
      model names (gpt-5, gpt-4o, gpt-4o-mini) are stale — current Codex models are the
      gpt-5.6 family (sol/terra/luna) with effort levels Low..Ultra.
    recommendation: >
      Launch commands MUST pass explicit model and reasoning-effort config (e.g.
      -c model="gpt-5.6-sol" -c model_reasoning_effort="ultra" — verify exact key against
      current Codex config reference during implementation). Routing per user directive:
      implementer = gpt-5.6-sol @ ultra; review-cheap = gpt-5.6-terra @ medium (luna as
      fallback; final tier to confirm with user). Journal the resolved model/effort per
      execution entry. /forge:init MUST probe model availability. Verify config keys
      (max_threads, max_depth, approval_policy=on-failure) against current docs; add a
      real-CLI smoke test (SHOULD) beside the fake_codex replay.

  - id: ADJ-011
    severity: WARNING
    dimension: Incompleteness
    section: "DM-001, FR-054, FR-062 (change-set identity)"
    finding: >
      Gate evidence, reviewer verdict, marker, and push are not bound to one candidate
      identity; each stage names its subject differently or not at all. (Source review
      demanded a versioned evidence schema — rejected: violates D4 Level B. Adopt at
      convention level.)
    recommendation: >
      Thread one candidate identity through the pipeline as convention: gate-3
      verification check field records the reviewed candidate (worktree HEAD SHA or
      staged-diff SHA-256); marker records the same hash; merge approval and push refer to
      the same SHA. No journal schema change.

  - id: ADJ-012
    severity: WARNING
    dimension: Incompleteness
    section: "FR-051, FR-112 (control category minimum)"
    finding: >
      The built-in control set omits CI workflow definitions (declared source of truth for
      gate commands per FR-081) and, in the plugin's own repo, the enforcement machinery
      itself (skills/, hooks/, scripts/, rules/, agents/). Whether project config can
      REDUCE the built-in set is unstated. (Blanket "all tests are control-class" from the
      source review declined — test-weakening is handled at the review layer per FR-126.)
    recommendation: >
      Add CI definitions (.github/workflows/**, or project CI config path) to the built-in
      control set. Generalize FR-112: forge-plugin's own repo declares its enforcement
      surfaces control-class via its own file-categories. State explicitly: project
      file-categories may EXTEND but never remove built-in control entries.

  - id: ADJ-013
    severity: WARNING
    dimension: Incompleteness
    section: "New section (threat model)"
    finding: >
      The spec never states what the enforcement layer defends against. Markers, manifest,
      and sentinels are same-OS-user files; against a fully adversarial orchestrator no
      local mechanism holds (no privilege boundary). Codex agents, however, are
      sandbox-confined to worktrees and cannot reach main-root state. (Source review's
      "orchestrator-owned directory permissions" declined — same-user, no boundary.)
    recommendation: >
      Add an explicit Threat Model subsection: guards defend against accident, negligence,
      and prompt-injection-driven attempts by either model; they do NOT defend against a
      deliberately adversarial orchestrator with shell access; the kill-switch and audit
      log are operator-facing controls; anything stronger requires an external
      broker/signer and is deferred.

  - id: ADJ-014
    severity: WARNING
    dimension: Inoperability
    section: "FR-035, FR-041 (process identity)"
    finding: >
      nohup ... & disown in a non-interactive shell does not guarantee a new process
      group, and no PID/PGID is recorded anywhere — FR-041's "check the launched process
      group" has nothing recorded to check.
    recommendation: >
      Detach via setsid (or equivalent start_new_session) and write a pid file (PID, PGID,
      launch timestamp) into the execution directory at launch, before arming the monitor.
      FR-041's ambiguity protocol references the pid file for liveness. Full
      timeout/cancel/PID-reuse protocol deferred.

  - id: ADJ-015
    severity: WARNING
    dimension: Inconsistency
    section: "FR-024 vs FR-057 (standalone commit)"
    finding: >
      FR-024 unconditionally requires /forge:commit to invoke validate --gates, but
      validate needs a run directory and FR-057 makes journal involvement conditional on
      an open run. Standalone commits (no run) are unspecified and "latest run" inference
      would race.
    recommendation: >
      Scope FR-024's unconditional requirement to the workflow close sequence. /forge:commit
      invokes validate --gates only when an explicitly identified run is open (run ID
      passed or recorded in session state); with no open run, the commit chain runs
      without journal entries. Never infer "latest".

  - id: ADJ-016
    severity: WARNING
    dimension: Incompleteness
    section: "FR-002, FR-090, SC-005 (hook registration and matching)"
    finding: >
      The packaging inventory never names the hook registration artifact (hooks/hooks.json)
      and no test exercises discovery via plugin load. The matcher "contains git commit or
      git push" misses git -C <path> commit — a form Claude uses routinely — plus
      absolute-path git, env-prefixed, and newline-separated forms.
    recommendation: >
      Add the hook registration file to the packaging FRs and a plugin-load discovery
      smoke test. Specify tolerant matching: a git invocation (git, <path>/git, env ...
      git) followed by a commit/push subcommand token, allowing intervening global options
      including -C/-c/--git-dir, across chained and newline-separated command segments.
      Document that exotic wrappers/aliases are out of scope per the threat model.

  - id: ADJ-017
    severity: WARNING
    dimension: Inconsistency
    section: "DM-006, FR-056 (skip marker format)"
    finding: >
      DM-006 defines the marker as exactly two lines; FR-056 appends a third
      "skip: user-directed" line. Strict guard parsing rejects sanctioned skips;
      permissive parsing violates DM-006. The skip override also leaves no durable audit
      (marker deleted after commit).
    recommendation: >
      DM-006: lines 1-2 mandatory, optional line 3 annotation (skip: user-directed); guard
      accepts both forms. Journal a decision entry (run open) or append to the audit log
      (no run) recording the user-directed skip durably.

  - id: ADJ-018
    severity: NIT
    dimension: Inconsistency
    section: "FR-083 (init ordering)"
    finding: >
      .forge-manifest is control-class yet written AFTER the binding install review — the
      reviewed snapshot omits a control-class artifact. Impact small (manifest is
      mechanical; user approval sees everything).
    recommendation: >
      Write .forge-manifest with init_completed: false before the install review; flip to
      true only after user approval. Review covers the complete install output.

  - id: ADJ-019
    severity: NIT
    dimension: Insecurity
    section: "FR-094, DM-007 (block telemetry)"
    finding: >
      Blocked-command audit lines log the raw command line, which can embed secrets.
      Mitigated by local-only, gitignored log; still nearly free to harden.
    recommendation: >
      Log executable, reason code, and a truncated pattern-redacted excerpt instead of the
      raw line; restrictive file permissions; size cap/rotation note.

  - id: ADJ-020
    severity: NIT
    dimension: Ambiguity
    section: "Section 10 heading"
    finding: >
      Heading reads "## 10. Behavioral Scenarios"; grill-spec's plan-spec-mode detector
      keys on the exact string "## Behavioral Scenarios". (Source review's claimed
      "## BDD Scenarios" marker does not exist in the skill — evidence refuted; the
      numbered-heading risk is real.) Per-FR matrix demand declined: plan-spec template
      mandates rolled-up ranges.
    recommendation: >
      Rename the heading to exactly "## Behavioral Scenarios" (drop the number).
```
