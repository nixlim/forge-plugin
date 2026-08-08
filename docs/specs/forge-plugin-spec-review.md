# Adversarial Review: Forge Plugin Specification

**Spec reviewed**: `docs/specs/forge-plugin-spec.md`
**Review date**: 2026-08-08
**Review cycle**: 1
**Review mode**: Structured spec (the document uses `## 10. Behavioral Scenarios`, not the exact plan-spec `## BDD Scenarios` marker)
**Verdict**: BLOCK

## Executive Summary

The specification does not mechanically deliver its fail-closed claims. Its close validator cannot inspect the closure it is supposed to reject, gate evidence is not bound to the reviewed revision, the commit path reviews before staging the committed bytes, and the merge path pushes a rebased result before re-verifying it. Control-change approval can be bypassed through the merge path, Codex can perform an ordinary push despite the prompt-only prohibition, workspace-writable state can forge or disable enforcement, and forced cleanup can delete uncommitted work.

This review found 18 issues: 9 CRITICAL, 6 MAJOR, 2 MINOR, and 1 OBSERVATION. Implementation must not begin until every CRITICAL and MAJOR finding is resolved and the corresponding negative tests are added.

| Severity | Count |
|----------|-------|
| CRITICAL | 9 |
| MAJOR | 6 |
| MINOR | 2 |
| OBSERVATION | 1 |
| **Total** | **18** |

---

## Findings

### CRITICAL Findings

#### [CRIT-001] Pre-close validation cannot enforce the passed-close rule

- **Lens**: Incorrectness, Inconsistency
- **Affected section**: FR-021 and FR-024 (lines 169, 172); "Orchestrated task passes all gates" (lines 316–326); Error Contract (line 297)
- **Description**: FR-021 raises its issue only when a `run_closed` record with `judgment: "passed"` already exists. FR-024 mandates the only close-time validation before that record is appended: `validate --gates → run_closed → report.md`. The happy-path scenario repeats the same order. The upstream validator permits zero closures and checks closure judgment only when a closure exists (`upstream/codex-orchestrator/scripts/codex_orchestrator/journal.py`, `validate_run`, lines 104–139), while the upstream contract defines `run_closed` as final. Therefore the required pre-close call cannot emit FR-021's issue.
- **Impact**: A run can append `run_closed: passed` without a post-mutation Gate 3 PASS even though the embedded pre-close validation says `ok: true`. The report is read-only and no later step is required to reject or repair the invalid close.
- **Recommendation**: Replace the split protocol with one atomic close operation that accepts the prospective judgment, validates Gates 1–3 against the exact closing change-set, and appends `run_closed` only on success. If the existing CLI must remain, add `validate --gates --prospective-judgment passed --target <change-set-id>` before close and a mandatory post-close consistency validation before reporting. Rewrite the happy/error scenarios to prove that a passed close cannot be appended without all required evidence.

---

#### [CRIT-002] Gate evidence is neither complete nor bound to the validated change-set

- **Lens**: Incompleteness, Insecurity
- **Affected section**: DM-001 (lines 104–112); FR-021–FR-023 (lines 169–171); Gate terminology (lines 60–61)
- **Description**: `validate --gates` requires only a post-mutation Gate 3 PASS for a passed close; it never requires passing Gate 1 and Gate 2 records. DM-001 records task, criterion, command, result, and observation but no immutable tree/index SHA, change-set identity, attempt, or artifact digest. FR-022 clears any failed criterion with any later PASS sharing only the `gate-N: ` prefix, so a passing `gate-1: unit tests` can clear a failed `gate-1: blast radius` check.
- **Impact**: A stale or unrelated PASS can authorize a different revision, and a run missing project tests or lint/types can close as passed. The journal can look compliant while the actual merged bytes never passed the advertised three-gate chain.
- **Recommendation**: Define a versioned gate-evidence schema containing `change_set_id`, target tree/index SHA, exact criterion/check identity, attempt, result, command, environment identity, and artifact digest. Require Gates 1, 2, and exact Gate 3 PASS records for the same final change-set after its last mutation. A failure may be cleared only by a later PASS for the same full criterion and change-set. Add missing-Gate-1, missing-Gate-2, stale-SHA, cross-attempt replay, and mismatched-criterion tests.

---

#### [CRIT-003] Reviewer PASS is not bound to the bytes that are committed

- **Lens**: Incorrectness, Insecurity
- **Affected section**: DM-006 (line 140); FR-050 and FR-052–FR-055 (lines 197, 199–202); Gate-pass marker contract (lines 287–289)
- **Description**: FR-050 runs adversarial review in Step 4 but does not stage explicit paths until Step 5. FR-054 writes a marker on PASS before FR-055 stages the commit. No requirement says that the reviewer receives `git diff --cached`, that its input hash is recorded, or that it equals DM-006's marker hash. The upstream Forge commit workflow explicitly stages intended files and captures `git diff --cached` before review (`upstream/forge/system/template/.opencode/rules/commit-workflow.md`, lines 122–169); this prerequisite was dropped.
- **Impact**: The implementation can review one snapshot and commit another, omit untracked or partially staged files from review, or accept concurrent index/worktree mutation. FR-052 also permits a secret-containing file to be excluded from review without prohibiting it from the commit.
- **Recommendation**: Acquire the commit lock before building the intended index. Stage explicit session-owned paths, secret-scan the exact index, review `git diff --cached --binary`, and include its SHA-256 in both the reviewer request and result. Under the same lock, recompute the hash immediately before commit; any change invalidates PASS and forces re-review. A secret in an intended file must block the commit rather than exclude that file from review. Test untracked, partially staged, post-review mutation, concurrent index mutation, and secret-containing-file cases.

---

#### [CRIT-004] The rebased result is pushed before integrated verification

- **Lens**: Incorrectness, Inconsistency
- **Affected section**: FR-062–FR-063 (lines 210–211); "Locked rebase reintegration" scenario (lines 486–493)
- **Description**: FR-062 performs `fetch → rebase → push` inside the lock. FR-063 reruns Gate 1 only afterward, "before cleanup"; the scenario explicitly says the branch is pushed and then Gate 1 is rerun. The final integrated tree may differ from the tree seen by Gates 1–3, yet it reaches the default branch before any integrated validation. Only Gate 1 is rerun, leaving Gate 2 and the binding review stale.
- **Impact**: A rebase-combination defect, lint/type failure, or security issue can be discovered only after the failing commit is already on the default branch. A failed rerun cannot restore the advertised no-merge-on-failure guarantee.
- **Recommendation**: Inside the lock, fetch and rebase, compute the final candidate tree SHA, rerun Gates 1 and 2 and Gate 3 over that tree whenever the base or candidate changes, and bind Gate 4 approval to that SHA. Push only after every rerun passes. A failure must leave the remote unchanged and the worktree intact. Add an E2E test that advances the remote, causes the rebased Gate 1 to fail, and asserts the remote SHA is unchanged.

---

#### [CRIT-005] Worktree merge bypasses explicit approval for control-class changes

- **Lens**: Inconsistency, Insecurity
- **Affected section**: Control-class definition (line 63); FR-051 (line 198); FR-060 (line 208); FR-112 (line 249)
- **Description**: Control changes are declared "gated approval, never autonomous," and `/forge:commit` must wait for explicit approval after PASS. `/forge:worktree-merge` never classifies its diff as control/non-control; Gate 4 is always "diff summary then automatic proceed," followed by a direct push. This is a second reintegration path around FR-051 and FR-112.
- **Impact**: A branch changing `.codex/**`, eval baselines, `forge-project.md`, the constitution, or another control can be pushed automatically through `/forge:worktree-merge` without the human approval the same diff would require through `/forge:commit`.
- **Recommendation**: Apply the same non-overridable control classifier to the complete merge diff before Gate 1. After final-tree Gate 3 PASS, control changes must pause for explicit approval bound to the candidate tree SHA before the lock/push step. Persist the approval identity, timestamp, and SHA. Test non-control auto-proceed, control approval/refusal, and a default-branch advance that invalidates prior approval.

---

#### [CRIT-006] The built-in control category omits the controls that can weaken the gates

- **Lens**: Incompleteness, Insecurity
- **Affected section**: Control-class definition (line 63); FR-051 (line 198); FR-103 (line 243); FR-112 and FR-126 (lines 249, 259)
- **Description**: FR-051's built-in list omits tests and test infrastructure, CI/build workflows, sources of Gate 1/2 commands, and the plugin's own `skills/`, `rules/`, `hooks/`, `scripts/`, `agents/`, plugin manifests, and vendored validator. Project-defined file categories can add coverage but are themselves writable controls and are not specified as non-reducible. This contradicts FR-126's rule that weakening a gate is a failure.
- **Impact**: An agent can loosen an assertion, delete a CI step, weaken `commit-guard.sh`, alter a skill, or modify the gate validator and receive the cheaper non-control review path with autonomous commit/merge.
- **Recommendation**: Define a versioned, non-overridable minimum control set that covers all tests/test infrastructure, CI/build definitions, gate command sources, policy/routing/hook/script/agent/skill files, manifests, validator code, and eval fixtures/baselines. Project configuration may add patterns but must never remove them. Add classification tests for weakening an assertion, deleting CI, changing a gate script, editing a skill, and modifying the classifier itself.

---

#### [CRIT-007] Codex can perform the ordinary push that the design claims to prevent mechanically

- **Lens**: Insecurity, Incorrectness
- **Affected section**: Guardrails (lines 17–20); FR-031 (line 178); FR-039 (line 186); FR-090 (line 232); SC-006 (line 596)
- **Description**: FR-031 prohibits a Codex implementer from pushing only through prompt text. The Claude plugin PreToolUse hook in FR-090 does not govern Codex tool execution. The Codex execpolicy denies force push but deliberately permits `git push origin HEAD` (SC-006). Therefore a workspace-write Codex implementer with repository credentials can bypass the orchestrator and push its branch or another ref directly.
- **Impact**: A compromised, confused, or prompt-injected implementer can bypass Gates 1–4, the rebase lock, halt checks, control approval, and journal evidence with an ordinary push.
- **Recommendation**: Deny all `git push` forms in the Codex execution policy for implementer/reviewer roles and perform the authorized push only in a separate orchestrator-owned execution context or capability wrapper unavailable to agents. Remove credentials from agent subprocesses where possible. Add real Codex tests for ordinary, `-C`, absolute-path, `env`, refspec, and chained push forms and assert no agent context can update a remote.

---

#### [CRIT-008] Enforcement trusts state that the governed actor can forge or delete

- **Lens**: Insecurity
- **Affected section**: DM-006–DM-007 (lines 140–142); FR-054 (line 201); FR-090–FR-091 (lines 232–233); SC-005 (line 595)
- **Description**: The authorization marker, `.forge-manifest`, and halt sentinels are ordinary workspace files. The marker contains only a diff hash and timestamp—no authenticated reviewer identity, signed result, or protected issuer. FR-090 requires the marker only while `.forge-manifest` exists, so deleting or staging deletion of that manifest removes the check. FR-091 instructs agents not to alter sentinels but defines no mechanical protection. A workspace-write actor can forge a fresh matching marker or delete the manifest/halt state before invoking Git.
- **Impact**: The actor being governed can grant itself commit authority, disable the guard, or clear an operator halt. The mechanism is advisory despite being presented as fail-closed.
- **Recommendation**: Move authorization and halt state outside agent-writable worktrees into an orchestrator-owned directory under the git common dir with restrictive permissions, or use an external broker/capability. Bind authorization to reviewer identity, candidate SHA/index hash, operation, repo identity, and expiry; make the guard fail closed if installation state is missing or staged for deletion. Add forgery, deletion, symlink, alternate-worktree, and path-substitution tests.

---

#### [CRIT-009] Successful push can force-delete uncommitted or untracked work

- **Lens**: Inoperability, Incorrectness
- **Affected section**: FR-031 (line 178); FR-060 and FR-064 (lines 208, 212)
- **Description**: Implementers only MAY commit, Gate 3 reviews `origin/<default>...HEAD`, and FR-064 then runs `git worktree remove --force` and `git branch -D`. No precondition proves the worktree has no staged, unstaged, ignored, or untracked session/user files. Those bytes are absent from the reviewed and pushed commit range.
- **Impact**: A successful merge can permanently destroy uncommitted implementation work, logs, fixtures, or user files. This meets the review constitution's data-loss threshold for CRITICAL severity.
- **Recommendation**: Before any gate, require `git status --porcelain=v1 --untracked-files=all` to be empty and prove the branch contains the intended commits. Route a dirty worktree through `/forge:commit` or stop for recovery. After push, remove the proven-clean worktree without `--force`; retain the branch until deletion preconditions pass. Test staged, unstaged, ignored-policy, and untracked files and verify every blocked path preserves the worktree.

---

### MAJOR Findings

#### [MAJ-001] Init reviews an incomplete install snapshot

- **Lens**: Inconsistency
- **Affected section**: FR-051 (line 198); FR-080 and FR-083 (lines 224, 227)
- **Description**: `.forge-manifest` is itself control-class, but FR-083 runs `review-final` over the "full install diff" before writing the manifest. The explicit approval therefore covers a different snapshot from the one finally presented.
- **Impact**: Incorrect plugin references, branch names, completion flags, or manifest contents can enter the install without binding review; later marker enforcement also trusts that unreviewed manifest.
- **Recommendation**: Assemble all install outputs, including the final manifest, before computing the install snapshot. Run evals and review against that immutable snapshot, then bind explicit approval to its tree/index hash. Any subsequent mutation must invalidate review and approval. Add a test asserting the reviewer input and approval snapshot contain the final manifest bytes.

---

#### [MAJ-002] The Codex routing configuration does not select the specified agents and contains stale controls

- **Lens**: Infeasibility, Ambiguity
- **Affected section**: FR-030, FR-034, and FR-038 (lines 177, 181, 185); Reviewer-isolation scenario (lines 438–446)
- **Description**: FR-034's `codex exec` command does not select the named agent, model, or reasoning effort from FR-030. Current `codex exec --help` has no named-agent option; `.codex/agents/*.toml` defines subagents spawned within a Codex session, not a role selected by this direct launch pattern. Current official Codex configuration documents `agents.max_concurrent_threads_per_session` (`agents.max_threads` is legacy), does not document `agents.max_depth`, and marks `approval_policy = "on-failure"` deprecated. The current [Codex model list](https://developers.openai.com/codex/models) does not list fixed `gpt-5` or `gpt-4o` as ChatGPT-sign-in Codex models, while the spec defines no provider/authentication contract or capability probe.
- **Impact**: Implementer and reviewer launches can silently use the operator's default model/effort rather than the required separation, or fail entirely under a supported authentication mode. The E2E smoke with `fake_codex.py` cannot detect this.
- **Recommendation**: Choose one executable routing mechanism. For direct CLI launches, pass and record explicit `--model`, sandbox, and `model_reasoning_effort` overrides; define supported authentication/provider modes; probe model availability during init; and use current documented config keys from the [subagent](https://developers.openai.com/codex/agent-configuration/subagents) and [configuration](https://developers.openai.com/codex/config-file/config-reference) references. Add a real CLI smoke that asserts the resolved model, effort, sandbox, cwd, session ID, and read-only behavior.

---

#### [MAJ-003] Detached execution has no durable process identity or recovery contract

- **Lens**: Inoperability, Infeasibility
- **Affected section**: Detached-launch definition (line 67); FR-034 and FR-040–FR-043 (lines 181, 190–193)
- **Description**: `nohup ... & disown` does not by itself guarantee a new process group/session, yet FR-041 requires later `ps` checks against "the launched process group." The spec stores no PID, PGID, start time, command identity, or exit-status sidecar and defines no timeout/cancel/reconciliation path. PID reuse and a crash between the journal `execution` entry and process start remain ambiguous.
- **Impact**: Parent-shell exit can kill the worker, a resumed orchestrator can inspect the wrong process, and an indefinitely hung execution can leave the only allowed run open with no reliable recovery.
- **Recommendation**: Use a Python stdlib launcher with `subprocess.Popen(..., start_new_session=True)` and atomically persist PID, PGID, process start identity, command digest, execution ID, and eventual return code. Define launch-failure, timeout, cancel, resume, PID-reuse, and orphan reconciliation behavior. Test parent-shell exit, crash at every FR-036 boundary, missing sidecar, PID reuse, and laptop sleep.

---

#### [MAJ-004] Standalone `/forge:commit` has no unambiguous run for `validate --gates`

- **Lens**: Ambiguity, Inoperability
- **Affected section**: Public surface `/forge:commit` (line 76); FR-024 (line 172); FR-057 (line 204)
- **Description**: FR-024 says the commit skill always invokes `validate --gates`, which requires a run directory. FR-057 makes journal recording conditional on a run being open, and `/forge:commit` is also a standalone public surface. The spec does not say what to validate when there is no run, only closed runs, or multiple candidate directories.
- **Impact**: A normal commit may be impossible, validate an unrelated historical run, or bypass FR-024. Selecting a "latest" directory would introduce a race and cross-run evidence leak.
- **Recommendation**: Either require every commit to belong to an explicitly identified open run and fail closed otherwise, or define a standalone commit transaction that creates its own run. Pass the run ID/path explicitly; never infer latest. Add no-run, one-open-run, closed-only, successor-run, and racing-directory tests.

---

#### [MAJ-005] Hook discovery and Git-command equivalence are not tested

- **Lens**: Incompleteness, Insecurity
- **Affected section**: New surfaces (lines 79–80); FR-090 (line 232); Integration tests (line 580)
- **Description**: The packaging inventory does not require the plugin's hook registration file, while the sole integration test invokes the guard script directly rather than loading the installed plugin and proving hook discovery. The matcher is described as commands "containing `git commit` or `git push`" and does not define equivalent invocations such as `git -C repo commit`, `/usr/bin/git commit`, `env git commit`, aliases/wrappers, quoting, or newline-separated commands. Official [Codex hook documentation](https://developers.openai.com/codex/hooks) also treats hooks as trust-dependent guardrails with paths that may bypass ordinary tool hooks, not as a complete security boundary.
- **Impact**: The guard may never load or may allow routine equivalent Git invocations, invalidating the mechanical-enforcement claim even for Claude-driven operations.
- **Recommendation**: Specify the complete plugin hook registration artifact and install path, add a real plugin-load/discovery smoke test, and define canonical command parsing or conservatively deny all equivalent commit/push forms. State which operations are outside hook coverage and enforce them at the credential/capability boundary. Test `-C`, absolute executable paths, `env`, aliases, wrappers, shell functions, chains, quotes, and newlines.

---

#### [MAJ-006] Block telemetry can persist secrets from command lines

- **Lens**: Insecurity
- **Affected section**: FR-052 (line 199); FR-091 and FR-094 (lines 233, 236)
- **Description**: FR-094 asks the guard to record the blocked command line in `.forge/tmp/halt-audit.log` with no redaction, allowlist, permissions, retention, or size limit. Shell commands commonly contain tokens, signed URLs, headers, credentials, user data, and heredoc bodies. The spec applies secret scanning only to review diffs, not telemetry.
- **Impact**: A correctly blocked action can copy credentials or sensitive data into a persistent, append-only local log that later tools or support bundles may expose; repeated large commands can also exhaust disk.
- **Recommendation**: Never store raw commands by default. Record a command class, executable, salted digest, reason code, actor/session ID, and timestamp; apply explicit redaction before any bounded diagnostic excerpt. Define file permissions, rotation/size cap, retention, and disclosure policy. Add token/header/URL/heredoc and oversized-command tests.

---

### MINOR Findings

#### [MIN-001] The skip marker contradicts its own exact schema

- **Lens**: Inconsistency
- **Affected section**: DM-006 (line 140); FR-056 (line 203); Gate-pass marker contract (lines 287–289)
- **Description**: DM-006 defines exactly two lines and labels line 2 as the review-PASS timestamp. FR-056 appends a third `skip: user-directed` line when review was skipped, then deletes the transient marker after commit. A strict two-line parser must reject the documented skip form, while a permissive parser violates DM-006; neither leaves a durable override audit.
- **Recommendation**: Define a versioned discriminated format with `mode=review-pass|user-override`, candidate hash, timestamp, authorizing request/session identity, and expiry. Persist overrides in the journal or commit metadata. Add strict malformed/extra-line and override-audit tests.

---

#### [MIN-002] The scenario heading prevents plan-spec structural checks

- **Lens**: Incompleteness
- **Affected section**: `## 10. Behavioral Scenarios` (line 314); Traceability Matrix (lines 603–620)
- **Description**: The document otherwise resembles a plan-spec—FR IDs, Given/When/Then scenarios, success criteria, and a traceability matrix—but the grill-spec mode detector requires the exact `## BDD Scenarios` heading. It is therefore reviewed as a structured spec and does not receive the stricter story/acceptance/BDD/test 9-check matrix. The range-level traceability table also hides untested individual FRs.
- **Recommendation**: If plan-spec conformance is intended, rename the section to the exact marker, give every scenario a unique ID, and map every individual FR and scenario to explicit tests and success criteria. Otherwise state that structured-spec mode is intentional and expand the matrix to one row per FR.

---

### Observations

#### [OBS-001] One immutable change-set identity would remove several overlapping control concepts

- **Lens**: Overcomplexity
- **Affected section**: DM-001, DM-006, FR-050–FR-065, FR-083, FR-090
- **Suggestion**: The journal gates, reviewer result, transient marker, explicit approval, and push step each track a different or implicit notion of "the reviewed change." Introduce one immutable `change_set_id` derived from repo identity + base SHA + candidate tree/index SHA and thread it through gate evidence, reviewer output, approval, commit authorization, closure, and merge. This is a simplification, not a new product feature, and resolves much of CRIT-002 through CRIT-005.

### Lens Coverage

| Lens | Result |
|------|--------|
| Ambiguity | Findings MAJ-002 and MAJ-004 |
| Incompleteness | Findings CRIT-002, CRIT-006, and MAJ-005 |
| Inconsistency | Findings CRIT-001, CRIT-004, CRIT-005, MAJ-001, and MIN-001 |
| Infeasibility | Findings MAJ-002 and MAJ-003 |
| Insecurity / STRIDE | Findings CRIT-002, CRIT-003, CRIT-005–CRIT-008, MAJ-005, and MAJ-006 |
| Inoperability | Findings CRIT-009, MAJ-003, and MAJ-004 |
| Incorrectness | Findings CRIT-001, CRIT-003, CRIT-004, CRIT-007, and CRIT-009 |
| Overcomplexity | OBS-001; no separate defect beyond the fragmented change identity |

---

## Structural Integrity

This is **structured-spec mode**, not plan-spec mode, because the scenario section is not named exactly `## BDD Scenarios`.

| Check | Result | Notes |
|-------|--------|-------|
| Every goal/objective has acceptance criteria | FAIL | Success criteria cover build/smoke outputs but not each stated capability, especially fail-closed merge, control approval, exact role routing, safe cleanup, and enforcement integrity. |
| Cross-references are consistent | FAIL | FR-021 cannot operate in FR-024's order; FR-063 validates after FR-062 pushes; DM-006 conflicts with FR-056; FR-083 reviews before creating a control artifact. |
| Scope boundaries are explicit | PASS | New, modified, and deferred surfaces are named. |
| Success criteria are measurable | PASS | SC-001–SC-009 use observable commands, outputs, or exit codes, although their coverage is incomplete. |
| Error/failure scenarios addressed | FAIL | No scenarios cover dirty cleanup, gate-evidence replay, state forgery/deletion, ordinary Codex push, control merge approval, real CLI routing, or post-rebase failure before push. |
| Dependencies between requirements identified | FAIL | Required temporal dependencies—stage before review, validate final tree before approval/push, create manifest before review, and bind close to final evidence—are contradicted or absent. |

The document contains 77 unique FR definitions, but traceability is by FR range rather than individual FR. A range being present does not prove that each requirement has a scenario and executable test; FR-051, FR-063, FR-064, FR-083, FR-090, and FR-094 expose concrete blind spots.

---

## Test Coverage Assessment

### Missing Test Categories

| Category | Gap Description | Affected Scenarios / Requirements |
|----------|----------------|-----------------------------------|
| Temporal close correctness | No test exercises the mandated pre-close call and proves an invalid passed closure cannot be appended | FR-021, FR-024, close scenarios |
| Evidence/replay integrity | No missing-Gate-1/2, stale SHA, cross-attempt replay, or same-prefix/different-criterion test | DM-001, FR-021–FR-023 |
| Commit TOCTOU | No untracked, partially staged, concurrent index mutation, secret-containing intended file, or post-review mutation test | FR-050–FR-055 |
| Integrated merge failure | No remote-advance case where the rebased tree fails before push; no assertion that remote SHA remains unchanged | FR-062–FR-063 |
| Control authorization | No control-class worktree merge test and no exhaustive built-in classifier tests for tests/CI/scripts/skills/validator | FR-051, FR-060, FR-112, FR-126 |
| Data-loss prevention | No dirty staged/unstaged/untracked worktree cases before forced cleanup | FR-064 |
| Adversarial state integrity | No marker forgery, manifest deletion, halt deletion, symlink, alternate-worktree, or path-substitution tests | DM-006, FR-090–FR-091 |
| Real runtime compatibility | E2E uses only `fake_codex.py`; no real Codex auth/model/config/session/sandbox/hook test | FR-030–FR-043, SC-009 |
| Hook discovery/equivalence | The script is invoked directly; plugin registration and equivalent Git command forms are not exercised | FR-090, integration line 580 |
| Process lifecycle/concurrency | No launch crash-window, parent exit, PID reuse, cancel, timeout, or two-process index/rebase contention tests | FR-034–FR-043, FR-055, FR-062 |
| Telemetry privacy/limits | No redaction, permissions, retention, rotation, or oversized-command tests | FR-094 |

### Dataset Gaps

| Dataset | Missing Boundary Type | Recommendation |
|---------|----------------------|----------------|
| Gate journal fixtures | Missing gates, duplicate attempts, reordered records, stale/different SHAs, same-prefix criteria, malformed timestamps | Add one fixture per state transition and require exact issue text plus remote/index invariants. |
| Git index/worktree states | Untracked, ignored, partially staged, intent-to-add, rename/delete, binary diff, submodule, concurrent mutation | Build a table-driven fixture repo suite; assert the reviewed hash equals committed tree input. |
| Command forms | `git -C`, absolute Git path, `env`, aliases, functions, quoting, chains, newlines, refspecs | Test both allow and deny decisions through the actually installed hook/policy. |
| Runtime configuration | ChatGPT sign-in vs API provider, missing model, deprecated key, untrusted repo, absent auth, resumed session | Add init probes and real CLI smoke variants with explicit expected failure contracts. |
| Region/splice inputs | Duplicate, nested, reversed, missing, or malformed markers; CRLF; non-UTF-8; symlinks | Specify fail-closed behavior and byte-preservation assertions for every malformed form. |

Regression coverage for upstream `validate` is explicitly preserved and is one of the stronger sections. It does not compensate for missing Forge-profile invariants or real harness integration.

---

## STRIDE Threat Summary

| Component / data flow | S | T | R | I | D | E | Notes |
|-----------------------|---|---|---|---|---|---|-------|
| Gate journal and `run_closed` | risk | risk | risk | ok | ok | risk | Records lack candidate identity; stale/unrelated passes and pre-close validation can authorize an invalid close. |
| Review → marker → commit | risk | risk | risk | risk | ok | risk | Marker issuer is unauthenticated; reviewed and committed bytes can differ; secret files may be omitted from review but committed. |
| Worktree merge → default branch | ok | risk | risk | ok | risk | risk | Final tree is pushed before verification and control approval can be bypassed. |
| Codex implementer → Git remote | ok | risk | risk | ok | ok | risk | Ordinary push remains allowed from the governed workspace-write process. |
| Manifest / halt / authorization state | risk | risk | risk | ok | risk | risk | Governed actors can forge/delete workspace-local trust anchors and sentinels. |
| Detached worker lifecycle | risk | risk | risk | ok | risk | risk | No durable process identity; PID reuse and crash windows are unresolved. |
| Hook and execpolicy layer | ok | risk | risk | ok | risk | risk | Discovery/equivalent-command coverage is absent; trust and bypass boundaries are not modeled. |
| Telemetry log | ok | risk | risk | risk | risk | ok | Raw commands can disclose secrets and grow without bound. |
| Init/re-init renderer | ok | risk | risk | ok | risk | risk | Final manifest is outside the reviewed snapshot; malformed marker behavior is unspecified. |

**Legend**: risk = identified threat not mitigated in the spec; ok = adequately addressed or not applicable.

---

## Unasked Questions

1. What immutable identifier names the exact bytes that Gates 1–3, the reviewer, the user approval, the commit marker, `run_closed`, and the push all authorize?
2. Who is allowed to create authorization evidence, and how does the guard authenticate that issuer against a workspace-write agent?
3. How can an operator halt survive an agent with permission to write/delete files and run shell commands in the repository?
4. Which process owns remote credentials, and why does any implementer/reviewer process receive the capability to perform an ordinary push?
5. Does `/forge:commit` require an open orchestration run; if not, what exact run directory is validated and where is its evidence retained?
6. What is the complete non-reducible control file set, and how is an attempted change to the classifier itself classified?
7. What clean-tree proof is required before worktree deletion, and how are ignored-but-valuable files treated?
8. Which Codex authentication/provider modes are supported, and what happens when a pinned model is unavailable or retired?
9. What durable PID/PGID/start identity and timeout/cancel protocol allows safe recovery after a crash, restart, or PID reuse?
10. How are malformed/duplicate region and splice markers handled without modifying user bytes outside the managed region?
11. What hook/tool invocation paths are outside PreToolUse coverage, and what lower-level capability prevents those paths from committing or pushing?
12. What redaction, permissions, retention, and rotation policy applies to command telemetry and decision logs?

---

## Verdict Rationale

The verdict is **BLOCK** because the specification's central safety property—no commit, close, or merge without gates over the exact authorized bytes—is false under its own ordering and data model. CRIT-001 through CRIT-004 break the evidence chain and allow invalid closure or unverified code to land. CRIT-005 through CRIT-008 provide direct approval/enforcement bypasses, while CRIT-009 permits permanent local data loss on a nominally successful path.

The MAJOR findings also prevent a reliable implementation: init approves an incomplete snapshot, the documented Codex launch cannot prove it selected the required role/model controls, detached workers are not recoverable, standalone commits lack a validation target, hook installation/equivalence is unproven, and audit telemetry can expose secrets. These are specification defects, not implementation details that can safely be decided during coding.

### Recommended Next Actions

- [ ] Address CRIT-001 and CRIT-002 by specifying an atomic close and a versioned, final-change-set-bound gate-evidence contract.
- [ ] Address CRIT-003 by holding the commit lock across exact staging, secret scan, review, hash verification, and commit.
- [ ] Address CRIT-004 by validating and approving the final rebased tree before any remote update.
- [ ] Address CRIT-005 and CRIT-006 with one non-overridable control classifier shared by commit and merge, plus explicit approval bound to the final candidate SHA.
- [ ] Address CRIT-007 and CRIT-008 by moving push authority and authorization/halt state outside governed agent capabilities.
- [ ] Address CRIT-009 by requiring and testing a clean worktree before non-forced cleanup.
- [ ] Resolve MAJ-001 through MAJ-006 and add each finding's named negative tests.
- [ ] Replace range-level traceability with individual FR/scenario/test/SC mappings, or deliberately adopt the plan-spec BDD structure.
- [ ] Re-run `/grill-spec docs/specs/forge-plugin-spec.md` after the specification is revised.
