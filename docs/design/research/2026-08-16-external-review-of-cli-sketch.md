# External Review of the Forge CLI Sketch (Revision 1) — Discussion Record

**Date:** 2026-08-16
**Participants:** Igor (operator), Claude (session agent). The review itself was produced by a
third, external agent and relayed by Igor.
**Subject:** `docs/design/0003-forge-cli-plumbing.md` revision 1, in the context of
`research/2026-08-16-external-process-review-discussion.md`.
**Status:** verbatim record. The review, Claude's analysis, and the follow-up exchanges are
reproduced as written. Decisions are listed at the end: D1–D13 are folded into revision 2 of
the design doc; §7–§10 record a third external review (of revision 2) whose dispositions
D14–D22 are folded into revision 3; §11–§14 record a fourth and final external review (of
revision 3) whose dispositions D23–D32 are folded into revision 4. The fourth review's
verdict was "build it" and its closing advice — no further essay reviews; the next artifact
is the commit-slice spec — was accepted.

---

## 1. Igor's message (relaying the external review of the sketch)

> we are discussing this document: docs/design/0003-forge-cli-plumbing.md
> in this context: docs/design/research/2026-08-16-external-process-review-discussion.md
>
> the external review on the design sketch:
>
> What is already good
>
> The enforcement inversion is correct. Today scripts/forge/* are subroutines a model must
> remember to call in order. A persisted state machine that refuses out-of-order steps is the
> only way "skipping a step is structurally impossible" becomes true.
>
> Evidence captured, not transcribed is the second founding idea, applied to the clerk.
> Twice-consecutive, SHAs, and "I ran Gate 1" stop being claims. That is the same doctrine as
> "handoffs are not gate evidence," moved to where it was missing.
>
> next required step: is the right UX. Enforcement is the refuse; the printed line is how a
> context-crushed model finds the refuse's front door.
>
> Judgment stays with the model is the correct cut. Staging scope, disposition, writing the
> review, and "stop, this looks wrong" must not move into Python. Principle 4 plus the
> over-mechanization note in the ledger are doing real work.
>
> Escape hatches inside the tool. Without this, the first inconvenient chain produces
> git commit --no-verify folklore and you have a cargo-cult control system. Putting skips in
> finalize and journaling them is the grown-up version of the current three-line skip marker.
>
> Fast path as opt-out. This is the only design that will move fast_allowed off zero. A cheap
> path that costs a 622-line skill to claim is not a cheap path. Auto-classify at commit start
> is the right default.
>
> review request as information-flow control (no handoff in the package) is stronger than "do
> not paste the handoff." Same idea as plan-seal / proposal-unseal.
>
> Additive migration (hook accepts either → dogfood this repo → delete markers) is the only
> safe decommission. Do not skip phase 1.
>
> The honest ledger is the strongest section. Complexity moves; uniform failure beats silent
> skip; the CLI becomes the thing "tests that fail when the control is disabled" can actually
> target.
>
> What will bite you if you spec this as written
>
> These are not nits. They are the places an implementer will invent policy.
>
> 1. The hook/CLI boundary is the whole design, and it is ambiguous.
>
> Claude Code PreToolUse sees the command the model submitted. If the model runs
> forge commit finalize and that binary subprocesses git commit, the hook typically never sees
> the inner git. The sentence "the hook authorizes a git commit only when invoked through
> forge commit finalize" can be read three ways:
>
> • Model still runs git commit; hook checks the chain file (today's marker, renamed).
> • Model runs forge commit finalize; hook allows that argv; CLI commits internally (hook
>   never sees git).
> • Both.
>
> The strong shape is: in a Forge repo the hook denies raw git commit and git push. It allows
> only forge commit finalize / forge merge finalize. The CLI is the committer. Write that
> down. The current wording preserves the idea that git commit is still the model's verb.
>
> 2. Chain TTL of 30 minutes from start is a regression.
>
> Today the 30 minutes starts at authorization after PASS, not at chain open. Gate 1 on this
> repo is already ~11 minutes. A standard/hard chain with review and one revision will die
> mid-flight. Keep per-authorization TTL. Bound individual gate runs with the existing 1200s.
> Do not expire the whole chain at 30 minutes from create.
>
> 3. Candidate identity cannot be computed at commit start.
>
> Start knows paths. The candidate is the SHA-256 of git diff --cached after staging.
> Changelog (Step 3 today) mutates the tree and adds a path, which must recompute the
> candidate and invalidate downstream evidence. Spell a restage rule: CLI owns
> git add -- <paths> (and the changelog path if that gate writes one); any other index change
> kills bound evidence, including classify.
>
> 4. Control-class approval is missing.
>
> Current law: PASS does not authorize a control commit; the user must name the candidate SHA;
> the marker stays absent until that happens. finalize as "the only path to a commit" will
> autonomously ship hooks/, skills/, docs/specs/** unless you add an awaiting-approval state
> that cannot transition to authorized without an operator-bound record. This is not optional.
>
> 5. review attach --verdict-file is forgeable.
>
> The model can write PASS and a fake reviewer identity. Distinct-session checks on a file the
> author session created are theater. Either:
>
> • forge review request launches the reviewer (or a nonce only that process receives), and
>   attach requires the nonce, or
> • attach reads a verdict from a CLI-owned path the author cannot write.
>
> "Emits the exact reviewer invocation" still leaves launch and the verdict file with the
> model. That is the current skill, with extra JSON.
>
> 6. Plan-seal is theater unless the proposal is unreadable.
>
> The orchestrator can cat the worktree. Unseal-as-ordering only works if the proposal bytes
> live in a CLI-owned object (mode, encryption, or a path the model is actually prevented from
> reading — which a same-user agent is not). Same threat model as the spec: you cannot bind
> Claude. So either defer plan-seal, or define a best-effort seal that is an audit record, not
> an information-flow guarantee. Do not claim "the proposal is unreadable."
>
> 7. Two systems of record.
>
> You already have journal.jsonl. Adding .forge/chains/ without a rule produces split-brain
> (validate --gates vs chain file). Say: the chain file is SoR for the commit/merge chain. If
> a run is open, the CLI appends the existing journal verification/decision shapes (no new
> journal type). Archives cite chain_id. Do not make the model copy between them.
>
> 8. Push is still the hole.
>
> merge finalize doing the locked rebase and FF push is right. The hook must deny raw
> git push in a Forge repo or Beads/habit will walk around merge finalize the same way they
> walk around /forge:worktree-merge today. The sketch never says this.
>
> 9. Step order per tier is not a table.
>
> Implied: start → classify → gates → secrets → review → finalize. Missing: changelog
> mutation, STRICT evals on control, invariants, assertion sensor, "invalidate from classify
> downward if paths change," and "no skip covers review for control-class." Put a transition
> table in the spec. The state enum is not a substitute.
>
> 10. Scope is a whole product.
>
> Commit + merge + evals + journal + halt + plan-seal in one CLI is how this becomes a year of
> control-class work and never deletes the marker grammar. Vertical slice:
>
> 1. status, commit start/abort, classify, gate run, scan secrets, review request/attach
>    (with a real anti-forge story), commit finalize
> 2. Hook dual-accept (marker or chain)
> 3. Dogfood on this repo
> 4. Then merge, then plan-seal if you still believe in it
>
> 11. env_fingerprint is undefined.
>
> If it is so tight that two consecutive runs on the same laptop differ, twice-consecutive
> never passes. If it is so loose it is always equal, it does not measure independence. Decide
> what it hashes (cwd, policy SHA, command digest, maybe sys.version) and admit that two
> back-to-back CLI runs still are not two independent environments. The win is "the CLI
> observed both," not "they were independent."
>
> 12. Init bootstrap and forge on PATH.
>
> Preserve the /forge:init first-policy exception (no HEAD, no candidate policy). Name the
> binary so it does not collide with Foundry's forge —
> python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py" is enough; a PATH name forge will
> surprise people.
>
> I do not agree with everything in external review. You analyse for yourself.

---

## 2. Claude's analysis

> I've checked the review's factual claims against the spec (FR-090, DM-006,
> FR-051/FR-060/FR-083) and the sketch. My assessment: the review is mostly right, and on
> four points (2, 4, 7, 8) it's confirmably right against our own committed law. But it
> overstates what's achievable on point 5, picks the wrong remedy on 6, and misses one
> architectural consequence of its own point 1.
>
> ### Confirmed against the repo — accept these
>
> **Point 2 (TTL) — the reviewer is right and the sketch is wrong.** DM-006 is explicit: the
> marker goes stale 30 minutes after **line 2, the timestamp at authorization**. My schema
> example shows chain `expires_at` = `created_at` + 30 min, which silently moves the clock to
> chain open. With Gate 1 alone at ~11 minutes and a review cycle on top, standard/hard
> chains die mid-flight. The fix: keep per-authorization TTL exactly as DM-006 has it; the
> chain-level bound, if kept at all, should be a generous inactivity timeout (hours) for
> abandoned-chain garbage collection, never an authorization freshness control.
>
> **Point 4 (control-class approval) — the most important finding, and it's a genuine hole in
> my sketch.** FR-051: control changes are gated-approval — "after PASS, the skill presents
> the change and waits for explicit user approval instead of committing autonomously." FR-060
> Gate 4 binds approval to the candidate HEAD SHA. The sketch's state enum has no state
> between review-PASS and authorized. As drafted, `finalize` would autonomously ship
> `hooks/`, `skills/`, `docs/specs/**`. The enum needs `awaiting_approval`, reachable only
> for control-class tiers, exiting only via an approval record that names the candidate hash.
> One honesty note the reviewer didn't add: the CLI can't verify the *operator* granted
> approval — the model can type `forge approve` too. Within our stated threat model
> (accident, negligence, injection — not an adversarial orchestrator) a mandatory, journaled,
> candidate-bound approval step is still the right control; it just isn't operator-binding,
> and the spec should say so rather than imply it.
>
> **Point 8 (push) — confirmed hole.** FR-090's matcher already matches the `push`
> subcommand, but the guard blocks push **only on halt** — clause (b), the whole marker
> chain, applies to `git commit` alone. Raw `git push` is essentially ungated today, and the
> Beads push mandate is standing pressure to use it. The `Close Protocol Precedence`
> paragraph in CLAUDE.md is prose patching a mechanical gap. End-state must be: hook denies
> raw `git push` in a Forge repo; `forge merge finalize` is the only push path. Sequencing
> constraint: push denial can't precede the merge chain's existence, so it lands with the
> dual-accept phase, not before.
>
> **Points 1, 3, 7, 9, 11, 12 — accept, mostly spec-writing discipline.** The hook/CLI
> boundary must be written as one sentence with no third reading; my preferred shape matches
> the reviewer's strong form — hook denies raw `git commit`/`git push`, allows only the
> finalize verbs, CLI is the committer. Candidate identity computed at `start` is simply
> wrong as sketched; the restage rule — CLI owns `git add -- <paths>`, any out-of-band index
> change kills bound evidence including classify — is the right answer and is compatible with
> Principle 4 (the model still decides *what* to stage; the CLI performs the staging). Chain
> file as SoR for the chain, CLI appending existing journal shapes, archives citing
> `chain_id` — accept as written. Transition table including invalidation edges belongs in
> the spec. `env_fingerprint` should be defined as a context record (cwd, policy digest,
> command digest, interpreter version, platform) with the honest claim being "the CLI
> observed both runs," not "independent verification." And a PATH binary named `forge`
> collides with Foundry's forge; `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py"` is
> enough, and FR-090 will need a spec'd argv matcher for that invocation form just like it
> has for git.
>
> ### Where I disagree or would reframe
>
> **Point 5 (verdict forgery) — right diagnosis, but the proposed fix is only
> half-achievable, and the reviewer doesn't distinguish the two reviewer types.** For the
> **Codex first-pass reviewer**, the strong shape works fully: the CLI launches the Codex
> process itself, owns the verdict output path, and captures the run as evidence — same
> doctrine as gate capture, and it genuinely closes the forgery path. For **review-final**,
> it cannot work as described: review-final is a Claude subagent spawned through the Agent
> tool *by the orchestrator*. Any nonce the CLI mints passes through the orchestrator's
> context when it composes the subagent prompt; a CLI subprocess cannot spawn Claude
> subagents itself. The honest achievable control there: CLI records the package digest,
> requires the verdict to cite package digest + candidate hash, and journals the attach —
> which converts "one sloppy Write call under context pressure" into "deliberate multi-step
> forgery." That moves the failure out of the negligence class our threat model targets, and
> no further. The spec should state this asymmetry, not paper over it.
>
> **Point 6 (plan-seal) — agree it's not an information-flow guarantee; disagree with
> deferring it.** Keep it, downgraded: the seal is an *ordering and audit record* — the CLI
> refuses to hand over the proposal path until a plan digest is journaled. A same-user model
> can always `cat` the worktree, exactly as the spec's threat model already concedes for
> everything else. The rule was always anti-anchoring (a negligence control), never
> anti-adversary. Fix the claim ("the proposal is unreadable" must go), keep the mechanism.
>
> **Point 10 (scope) — accept the vertical slice, with one amendment.** Slice 1 as listed
> includes "review attach with a real anti-forge story," which per point 5 is the hardest
> item in the whole design for review-final. I'd land slice 1 with the Codex-reviewer
> anti-forge story real and review-final attach explicitly validated-but-trusted, documented
> as such, rather than block the slice on an unachievable guarantee.
>
> ### What the review missed
>
> The consequence of its own point 1: once the CLI is the committer, the inner `git commit`
> runs inside the CLI subprocess and **the PreToolUse hook never sees it** — so every check
> FR-090 currently performs at the last line of defense (halt, staged-bytes identity, marker
> validation) must move *into* the CLI's finalize path, and the hook's job shrinks to "deny
> raw git verbs, allow the finalize argv." That's the correct architecture, but it means the
> CLI inherits the hook's status as last line of defense, and the "tests that fail when the
> control is disabled in memory" requirement must target the CLI's internal checks with the
> same severity the hook parser tests have today.
>
> Net: adopt points 2, 3, 4, 7, 8, 9, 11, 12 essentially as given; adopt 1 in the strong
> form with the hook-consequence spelled out; adopt 10 with the review-final carve-out;
> reframe 5 as a two-tier story (real for Codex, best-effort for review-final); keep
> plan-seal against the reviewer's defer option but rewrite its claim. Point 4 is the one
> I'd treat as blocking — the sketch as written repeals FR-051's approval contract, which is
> precisely the kind of silent gate-weakening the whole system exists to refuse.

---

## 3. Igor's disposition on scope

> so I agree with your report apart from this:
> Point 10 (scope) — accept the vertical slice, with one amendment. […]
>
> we can build out the whole thing, we do not go for unachievable guarantee, ours is best
> effort as outlined in your point 6 discussion.
>
> let's amend/expand the design doc with these decisions

---

## 4. Follow-up: why point 4 is blocking (Igor asked for the explanation)

Claude's explanation, summarized from the full response: FR-051 makes control-class changes
gated-approval — a reviewer PASS never authorizes the commit; the skill must present the
change and wait for explicit user approval, and FR-060 binds that approval to the exact
candidate SHA. Revision 1's state enum (`… → reviewing → authorized → committing`) transitions
to `authorized` on the review verdict alone, with no state in which the machine waits for the
operator — and since `finalize` is "the only path to a commit," the transition table becomes
the law once markers are deleted. Nobody wrote "remove the approval requirement"; it simply
has no corresponding state, so in the migrated world it would cease to exist — control-class
changes (hooks, skills, the spec itself) would ship autonomously on a PASS. That is a
design-time instance of the exact failure mode the governance spine names ("a gate satisfied
by reducing its strength is a failure, not a pass"), and it would leave no runtime anomaly to
notice. Hence blocking: the design is not implementable until `awaiting_approval` exists,
entered after review PASS for control-class chains, exited only by a journaled approval
record naming the candidate hash. Caveat recorded: the CLI can prove an approval command ran,
not that the operator ran it; within the stated threat model that is still the right control,
and the spec must not claim operator-binding.

---

## 5. Follow-up: the approval mechanism (Igor: "add awaiting_approval and make Claude trigger AskUserQuestion?")

Claude's response, summarized: AskUserQuestion alone is presentation, not enforcement — its
answer is delivered into the model's context, the CLI never sees it, and asking at all is at
the model's discretion. The agreed layering, strongest first:

1. **State machine (floor):** control-class chains enter `awaiting_approval` after review
   PASS; `finalize` refuses without an approval record naming the current candidate hash.
2. **Hook-denied model approval + operator-run approval (normative):** the PreToolUse hook
   denies the approve verb when invoked by the model's Bash tool, instructing it to present
   the candidate SHA and ask the operator to run the exact approve command via the `!`
   prefix. User-typed `!` commands execute outside the model's Bash tool path, so the only
   way the approve command runs is the operator typing it — as close to operator-binding as
   a same-user architecture gets. Precondition: an eval confirming `!`-prefix commands
   bypass PreToolUse in current Claude Code (dcg experience suggests they do; it must be an
   eval, not an assumption).
3. **Permission ask-rule (fallback posture):** keep the approve verb permanently out of the
   allowlist so any model invocation raises a harness permission prompt showing the SHA in
   argv. Weaker (defeated by bypassPermissions), but still a user click outside the model.
4. **AskUserQuestion (presentation):** the conversational step presenting the diff summary
   and SHA before the operator acts.

Honest limits recorded: approval binds to *someone at the terminal*, not to an informed
decision; in headless/autonomous runs control-class chains park in `awaiting_approval` until
a human shows up — correct behavior, stated as a feature.

Igor: **"Agreed with your layering, fold it in and proceed with rewrite. also, we need to
make sure that all cli commands can be verbose and all error messages produced by CLI are
helpful for the model/harness using it."**

---

## 6. Decisions (folded into design doc revision 2)

| # | Finding | Decision |
|---|---------|----------|
| D1 | Hook/CLI boundary ambiguous | Strong form: hook denies raw `git commit`/`git push`; only the finalize verbs pass; the CLI is the committer and pusher. FR-090's last-line checks move into the CLI finalize path; the CLI inherits last-line-of-defense severity and its internal checks get control-disable tests. |
| D2 | 30-min chain TTL is a regression | Per-authorization 30-min TTL preserved (DM-006 semantics). Chain-level bound becomes a generous inactivity expiry (GC for abandoned chains), never authorization freshness. Gate runs keep the existing 1200s bound. |
| D3 | Candidate unknowable at start | CLI owns staging (`git add -- <paths>`) and computes the candidate from exact staged bytes after staging. Mutating steps (changelog) are CLI-restaged with recompute; any out-of-band index change kills all bound evidence including classify. |
| D4 | Control-class approval missing | `awaiting_approval` state added; exit only via journaled approval naming the candidate hash. Four-layer mechanism per §5 above; hook-denied model approve + operator `!` invocation is normative; `!`-bypass eval is a migration precondition. Not claimed operator-binding. |
| D5 | Verdict forgeability | Two-tier, both best-effort, honestly labeled: Codex reviewers are CLI-launched with CLI-owned verdict paths and captured runs (closes the negligence path structurally); review-final attach validates candidate-hash + package-digest citations and is journaled (converts sloppy forgery into deliberate multi-step forgery, no further). |
| D6 | Plan-seal theater | Kept as best-effort ordering + audit record. The unreadability claim is removed. |
| D7 | Two systems of record | Chain file is SoR for the commit/merge chain. With a run open, the CLI appends existing journal verification/decision shapes (no new journal type). Archives cite `chain_id`. The model never copies between them. |
| D8 | Raw push ungated | Hook denies raw `git push` in a Forge repo once `merge finalize` exists; lands with the dual-accept phase. |
| D9 | No transition table | Per-tier step table and transition table with invalidation edges added to the doc; the spec revision must carry the normative version. |
| D10 | Scope | Build the whole thing (Igor's direction) — full slice including review request/attach under the best-effort posture; phased: commit chain → hook dual-accept → dogfood → merge chain + push denial → marker deletion → plan-seal. |
| D11 | env_fingerprint undefined | Defined field set (cwd, repo HEAD, policy digest, command digest, interpreter version, platform). Claim is "the CLI observed both runs," never independence. |
| D12 | Naming/bootstrap | No PATH binary named `forge` (Foundry collision). Invocation is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py"`; the hook gets a spec'd argv matcher for that form. FR-083's first-policy bootstrap exception preserved. |
| D13 | CLI output contract (Igor) | Every command supports verbose output; every message — especially refusals — is written for a model/harness consumer: self-contained state, exact failed precondition, exact remediation command, machine-readable envelope, and the `next required step:` line. |

---

## 7. Third external review — of revision 2 (relayed by Igor, 2026-08-16)

> I have a review from external agent. I do not agree with all its findings
>
> The inversion is right. Revision 2 is the first version I would actually build from. I
> would not spec it as written.
>
> The diagnosis that started this — "the process is a very long prompt with a hook at the
> end" — is correct. A persisted state machine that refuses out of order, captures evidence
> itself, and prints the next step is the only shape that makes "skipping a step is
> structurally impossible" true. Judgment staying with the model, skips living inside the
> tool, honest best-effort labels, and the four-layer approval story are the right cuts. The
> twelve-point review of revision 1 was mostly right, and the dispositions (D1–D13) folded in
> the ones that were.
>
> What remains is the same class of defect revision 1 had on approval: law that exists in the
> spec has no corresponding state or row, so an implementer will silently repeal it.
>
> **The table repeals FR-152**
>
> This is the blocking one, and it is the same failure mode as the missing awaiting_approval
> state.
>
> FR-152 is explicit: a fast commit still runs classification, staging, gate 1, stack
> validations, invariant and assertion-quality checks, changelog policy, secret scan, halt,
> lock, and hash check. It skips only the reviewer.
>
> The "Required steps per tier" table marks gate 1 and stack validations as — for fast. The
> surrounding prose says the table is "structure, not policy," but the cells are policy. An
> implementer will copy them. Auto-classify at commit start is the right lever for the
> fast_allowed = 0 finding. Deleting gate 1 is a different change: it makes the cheap path
> cheap by weakening it. The dogfood metric would then move for the wrong reason.
>
> The same table also drops FR-144 / FR-147 (invariants and the assertion-quality sensor).
> The external review already called that out; revision 2 did not put them back.
>
> **The index is the real mutex, not the path set**
>
> commit start refuses an overlapping live path set. Git has one index per worktree. Two live
> commit chains in the same worktree, even on disjoint paths, share that index. Chain B's
> git add -- <paths> leaves chain A's staged bytes in place; B's candidate then includes A's
> files, or B has to reset and destroy A's staging.
>
> Today's concurrency model (FR-190) is cross-worktree: each authorizer hashes
> git diff --cached in its own Git context. Same-worktree multi-chain is a new, harder
> problem the sketch treats as already solved.
>
> The conservative rule, and the one that matches current law: at most one live commit chain
> per worktree. Cross-worktree concurrency stays content-addressed. GIT_INDEX_FILE per chain
> is the other honest option; overlapping-path locks are not.
>
> Do not "fix" this with a repo-native pre-commit / commit-msg hook. Founding D1 lets Codex
> commit inside execution worktrees, and those commits do not go through Claude's PreToolUse
> hook. Stay at PreToolUse. The rhetoric "the CLI is the committer" will tempt someone to
> install a Git hook and break implementer worktrees.
>
> **Finalize is a two-phase commit that is not specified**
>
> "Write the event first, then the materialized state" is crash-safe for JSON. It is not
> crash-safe for git commit.
>
> • Event "committed" written, then git commit fails → replay thinks history moved.
> • git commit succeeds, then the chain-close write dies → a real commit with an open chain.
>
> That split is the first production incident this design will have, and it happens on the
> path that is now the last line of defense. Spell the order (lock → re-verify index → commit
> → close → release), and spell recovery for each crash window. committing exists in the enum
> and has no recovery story.
>
> finalize also has no --message (and no --file). The CLI is the committer; the model still
> owns the message under principle 4. Without a flag, the implementer invents git commit
> inside the CLI from stdin, an env var, or a tempfile.
>
> **A few more silent-law holes**
>
> FR-053 is not in the machine. Eight-iteration cap, re-verify before re-review, user
> approval to disposition anything above MINOR. reviewing → revising → classifying has none
> of that. After a BLOCK, an in-place edit of already-staged files does not change the index,
> so the next finalize can commit the bytes the reviewer rejected. Detect working-tree vs
> index drift on staged paths, and make restage mandatory to leave revising.
>
> validate --gates is the wrong SoR sentence. That command validates orchestration-journal
> gates (gate-1: / gate-2: / gate-3: on a run). It is not a commit-authorization reader.
> D7's rule should be: the chain file is SoR for commit/merge authorization; the journal
> remains SoR for the run narrative; validate --gates keeps reading the journal. Mixing them
> is the split-brain D7 was trying to prevent.
>
> The hook matcher for the CLI argv is as hard as FR-090. python3, python, /usr/bin/python3,
> -m, a relative path to cli.py, CLAUDE_PLUGIN_ROOT resolving to cache vs marketplace vs
> local checkout. Phase 0 names this as an eval. The spec needs the matcher grammar, not just
> "a spec'd argv pattern."
>
> Skip mapping (FR-056) is not carried. --user-skip <gate> on finalize is cleaner than
> today's "skip tests" prose, but the skill still has to map operator language onto gate IDs,
> and "just commit" still cannot cover review-for-control or approval.
>
> Merge is still a sketch inside the sketch. Dirty-worktree predicate, committed-policy
> sentinels, rebase lock, FR-063 re-verify-inside-the-lock-before-push, candidate identity as
> HEAD SHA rather than staged-diff hash — none of that is in the transition table. Fine if
> the first spec revision is the commit slice only. Dangerous if "build the whole thing"
> means one spec PR.
>
> Phase 4 vs Beads. After raw git push is denied,
> git pull --rebase && bd dolt push && git push is no longer a legal close protocol.
> merge finalize has to absorb that, or the Beads block in AGENTS.md has to change in the
> same control-class change. Do not leave it as prose precedence.
>
> You analyse for yourself.

---

## 8. Claude's analysis of the third review

Verified against the spec before dispositioning: FR-152, FR-190, FR-053, FR-056, FR-063,
FR-031, FR-020/021 (`validate --gates`), FR-144/FR-147.

**Confirmed blocking — the table repeals FR-152.** FR-152 verbatim requires a fast commit to
run classification/staging, targeted `gate1-test-command`, category stack validations,
test-quality and invariant checks, changelog policy, secret scan, halt, lock, hash check, and
guard recomputation — "It skips only the adversarial reviewer." Revision 2's per-tier table
marked gate 1 and stack validations "—" for fast, and dropped the FR-144/FR-147 rows
entirely. The "structure, not policy" disclaimer does not survive an implementer copying
cells. Fast must be cheap to *claim* (auto-classify), never cheap by being *weaker* — a
weakened fast tier would also move the `fast_allowed` dogfood metric for the wrong reason.
Same defect class as revision 1's missing `awaiting_approval`.

**Confirmed — the index is the real mutex.** FR-190's concurrency is cross-context
content-addressing; git has one index per worktree, so two live chains in one worktree
corrupt each other's staging regardless of path overlap. Adopted: at most one live commit
chain per worktree; cross-worktree concurrency stays content-addressed; `GIT_INDEX_FILE` per
chain noted as a future option, not built. Also adopted verbatim: no repo-native git hooks —
FR-031 lets Codex implementers commit inside their worktrees, and those processes never pass
through Claude's PreToolUse hook; a repo pre-commit hook would break them. Enforcement stays
at PreToolUse.

**Confirmed — finalize is an unspecified two-phase commit,** on the path that is now the
last line of defense. Adopted: explicit order (halt → lock → re-verify candidate byte
identity → write intent event → `git commit` → record produced commit SHA → close chain →
release lock) with a deterministic recovery rule per crash window; `committing` becomes a
diagnosable recovery state. `finalize` gains `--message` / `--message-file` (the message is
model judgment under principle 4).

**Confirmed — `validate --gates` was the wrong SoR sentence** (Claude's own error in
revision 2): FR-020/021 define `--gates` as journal-level gate enforcement over run
journals; it is not a commit-authorization reader. Corrected: chain file is SoR for
commit/merge authorization; journal remains SoR for the run narrative; `validate --gates`
keeps reading only the journal.

**Confirmed — matcher grammar, FR-056 carry-over, merge scoping.** The CLI-argv matcher has
FR-090-grade combinatorics and the spec revision must carry the grammar itself. FR-056's
operator-language → gate-ID mapping stays a skill duty, with "just commit" never covering
control-class review or approval. The first spec revision covers the commit slice only
(phases 0–2); the merge chain is its own later spec revision — "build the whole thing" means
all phases get built, not one omnibus spec PR.

**Confirmed with extension — phase 4 vs Beads, plus a liveness hole the review implies but
does not name.** After raw-push denial, `merge finalize` cannot absorb the Beads close
protocol because that push happens on the *default branch in the main checkout*, where no
merge chain exists — phase 4 as drafted leaves no sanctioned push path at all for
main-checkout commits. Adopted: a `forge push` verb (halt-checked, rebase-locked,
fast-forward-only — merge-finalize push discipline minus the worktree), and the phase-4
control-class change rewrites the Beads close-protocol block in CLAUDE.md/AGENTS.md to route
through it, retiring the prose-precedence paragraph. `bd dolt push` is untouched (not git).

**Partial pushback — FR-053.** The review's headline scenario ("after a BLOCK, an in-place
edit does not change the index, so the next finalize can commit the bytes the reviewer
rejected") cannot happen in revision 2's machine as written: `finalize` refuses outside
`authorized`; a BLOCK lands in `revising`, whose only exit is `restage` — which re-stages
the full recorded path set (picking up tree edits), recomputes the candidate, and
invalidates everything back to `classifying`. Mandatory restage is already structural, and
re-verify-before-re-review falls out of invalidation for free. What *is* genuinely missing
and was adopted: the 8-iteration cap (counter in chain state; at the cap, refuse and
escalate — never commit), dispositions above MINOR requiring operator approval (recorded
disposition entries gated by the same operator mechanism as approval), and tree-vs-index
drift detection on staged paths at review-request and finalize time (a refusal with
remediation — the useful kernel of the review's scenario, as a negligence trap even though
the committed-rejected-bytes path is closed).

---

## 9. Igor's disposition

> proceed

---

## 10. Decisions (folded into design doc revision 3)

| # | Finding | Decision |
|---|---------|----------|
| D14 | Per-tier table repeals FR-152 and drops FR-144/FR-147 (blocking) | Fast column corrected: fast runs every step and skips only the reviewer. Invariant-check and assertion-sensor rows added for all tiers. Table disclaimer rewritten: the row structure is normative to FR-050/FR-152; only the commands come from committed policy. |
| D15 | Index is the mutex; git-hook temptation | At most one live commit chain per worktree; cross-worktree concurrency stays FR-190 content-addressed. `GIT_INDEX_FILE` per chain recorded as a future option only. Enforcement stays at PreToolUse; repo-native git hooks are prohibited (they would break FR-031 implementer worktree commits). |
| D16 | Finalize two-phase commit unspecified; no message flag | Normative finalize order (halt → lock → re-verify → intent event → `git commit` → record SHA → close → release) with per-crash-window recovery; `committing` is a diagnosable recovery state. `--message`/`--message-file` added. |
| D17 | FR-053 not in the machine | Iteration counter with hard cap 8 (at cap: refuse, record residual risk, escalate — never commit); dispositions above MINOR require the operator approval mechanism; tree-vs-index drift on staged paths refused at review request and finalize. Mandatory restage out of `revising` already existed and is credited as closing the committed-rejected-bytes path. |
| D18 | `validate --gates` SoR sentence wrong | Chain file is SoR for commit/merge authorization; journal is SoR for the run narrative; `validate --gates` reads only the journal. |
| D19 | Matcher grammar missing | The spec revision must carry the CLI-argv matcher grammar itself (interpreter forms, path forms, plugin-root resolutions), FR-090-grade; the Phase 0 eval pins it. |
| D20 | FR-056 skip mapping not carried | Skill maps operator skip language onto gate IDs; the CLI accepts only gate IDs; "just commit" never covers control-class review or approval. |
| D21 | Merge is a sketch inside the sketch | First spec revision = commit slice only (phases 0–2). Merge chain (dirty-worktree predicate, sentinels, rebase lock, FR-063 re-verify-inside-the-lock, HEAD-SHA candidate identity) is its own later spec revision before phase 3. |
| D22 | Phase 4 vs Beads; no main-checkout push path | New `forge push` verb: halt-checked, rebase-locked, fast-forward-only push for default-branch commits. The phase-4 change also rewrites the Beads close-protocol block (CLAUDE.md/AGENTS.md) to route through Forge verbs and retires the prose-precedence paragraph. |

---

## 11. The fourth (final) external review — of revision 3, verbatim

> I think this is the right next leap for Forge, and revision 3 is the first version I would
> turn into a spec. The founding inversion is correct. The two review passes earned their
> keep. What is left is not "is this the architecture?" — it is a short list of places an
> implementer will still invent policy.
>
> **The diagnosis is right**
>
> Today the commit skill is a 622-line program and the model is the interpreter.
> scripts/forge/* are subroutines the clerk has to remember to call. The PreToolUse hook,
> the marker grammar, and committed-policy sourcing are the actual compiler. That is exactly
> what the process review said, and it matches the file: Step 5 alone is a shell program
> embedded in markdown, and the model is trusted to paste it in order.
>
> A persisted state machine that refuses out-of-order steps is the only way "skipping is
> structurally impossible" becomes true. Evidence captured by the CLI, never transcribed by
> the model, is the same "claims are not evidence" doctrine applied to the clerk.
> `next required step:` is the right UX for a reader that just lost its context.
>
> The cut in principle 4 is the one I would defend: the CLI stages, classifies, runs,
> records, commits, and pushes; the model chooses paths, writes the message, writes the
> review, disposition-judges, and keeps the duty to stop when something looks wrong outside
> the checklist. Move any of that into Python and you have gotten the inversion wrong.
>
> **What revision 3 actually fixed**
>
> The earlier holes were real, and they are closed on paper:
>
> - hook/CLI boundary in the strong form (CLI is the committer; hook denies raw git
>   commit/push)
> - TTL restored to issuance, not chain-open
> - awaiting_approval restores FR-051 instead of silently repealing it
> - per-tier table no longer repeals FR-152
> - index as mutex, not path-overlap theater
> - finalize as a two-phase commit with crash-window recovery
> - honest labels on review-final attach and plan-seal
> - first spec scoped to the commit slice
> - forge push so phase 4 does not outlaw the Beads close path
>
> The honest ledger is doing real work. "Complexity moves; uniform failure beats silent
> skip; the CLI becomes the thing disable-in-memory tests can actually target" is the
> correct trade.
>
> **What I would still change before a spec PR**
>
> These are the remaining "implementer invents policy" points. Same class as the ones the
> external reviews already caught.
>
> 1. **The clerk is only half-collapsed.** The surface is still forge gate run <gate-id>.
>    Gate 1 twice, stack validations, assertion sensor, invariants, secrets — that is the
>    long part of the chain, and it is mechanical. Finalize-refuses-if-missing is
>    fail-closed, but it is not "skipping is structurally impossible." It is "skipping is
>    caught at the end."
>
>    If every command prints the exact next argv (forge gate run changelog, then forge gate
>    run gate1, …), the skill can be tiny. If it prints a template, the model still holds
>    the table.
>
>    I would add forge verify (or make gate run with no id mean "run every remaining
>    required mechanical step in order"). Mutating gates first, then the rest,
>    classify/restage automatic. Judgment verbs stay separate: review, approve, finalize.
>    That is the actual 622 → 100-line collapse. Without it, you have moved the end of the
>    clerk into Python and left the middle as a checklist.
>
> 2. **Mutating-gate order is load-bearing and unenforced.** Restage kills all bound
>    evidence. If the model runs Gate 1 twice and then changelog, both Gate 1 records die.
>    The table says "mutating gates ordered first." The machine should refuse gate run
>    gate1 while a configured mutating gate is still pending. Otherwise dogfood will teach
>    models to burn 20 minutes and then invalidate it.
>
> 3. **--user-skip and --confirm-index are the new marker.** Approve is hook-denied on the
>    model's Bash path. Skips are not. A context-crushed model can reconstruct "just
>    commit" as finalize --user-skip gate1 --user-skip … --confirm-index. That is today's
>    FR-056, with nicer flags.
>
>    Either bind skips the same way as approve (operator ! / permission prompt), or label
>    them honestly as model-issuable and journaled — same threat-model class as the current
>    skip marker, not a stronger control. --confirm-index in particular should be
>    operator-bound. It exists to commit index bytes the tree no longer matches. That is
>    exactly the negligence trap the drift check is there to stop.
>
> 4. **Say the CLI composes the existing scripts. Do not rewrite them.** Halt, lock,
>    risk_tier.py, secret scan, evals, journal verification/decision shapes, FR-154's
>    independent fast recomputation — those are the tested control surface. If cli.py
>    inlines them, phase 1 is a control-class rewrite disguised as a wrapper, and every
>    disable-in-memory test has to be re-proven against a new implementation.
>
>    One sentence in the spec: the CLI is a state machine that invokes the existing
>    executables, records what they returned, and owns sequencing/authorization. It does
>    not reimplement halt, lock, classification, or the secret scan.
>
> 5. **--json vs next required step: will be implemented wrong.** If both go to stdout,
>    every JSON consumer breaks. --json means stdout is only the envelope; the human line
>    is for the non-JSON path. Obvious, and therefore someone will concatenate them.
>
> 6. **forge push is still a sketch, same as merge.** Halt, rebase lock, FF-only is the
>    start of a contract, not the contract. The missing sentence: may it push commits that
>    no closed chain produced? I think the answer has to be yes (bootstrap, implementer
>    worktree commits that landed via merge, anything already on main). Then say so, and
>    say what it refuses (dirty rebase, non-FF, halt). Do not let phase 4 invent a "only
>    chain-produced SHAs" rule in the hook matcher.
>
> 7. **The !-bypass that makes approval real also makes ! git commit real.** Phase 0
>    pinning the bypass is correct. The matching skill rule is missing: the model may ask
>    the operator to run ! … approve (and maybe ! … --user-skip). It may never ask them to
>    run raw git. Under the stated threat model that is the whole control.
>
> Smaller nits, not blocking: the enum draws open and the table never uses it; review
> disposition is ambiguous about whether the whole verb is hook-denied or only above-MINOR
> (if the hook has to parse --severity, that is another FR-090-grade matcher);
> env_fingerprint is well-defined as an identity record but silent on what a mismatch
> between the two required Gate 1 runs does; changelog output paths are not specified to
> join the chain's paths set; reconstructibility-from-events does not hold across the git
> side-effect — recovery must observe HEAD, which the finalize section already says, and
> the schema notes should not contradict it.
>
> **Defense in depth**
>
> Phase 4 is a real concentration of risk. Today a buggy skill still hits an independent
> hook that re-hashes, checks the marker, and recomputes fast eligibility. After phase 4
> the hook is an argv matcher and the CLI is the last line of defense. That is acceptable
> only if:
>
> - every finalize check keeps hook-parser severity (disable-in-memory test, pinned
>   diagnostic)
> - those checks call the existing guard logic rather than a second copy
> - phase 1 dual-accept is not skipped
> - the marker grammar is not deleted until the eval net actually pins the machine
>
> The doc already says most of that. I would treat "do not skip dual-accept" as a red line,
> not a preference.
>
> The 100–150 line skill estimate is only true if next required step is an exact argv
> and/or forge verify exists. Otherwise the skill still contains the gate table, skip map,
> review loop, and approval presentation, and you will land around 250–300. Still a win.
> Not the number on the page.
>
> **Verdict**
>
> Build it. First spec PR = commit slice only (phases 0–2), as D21 already says. Before
> that PR, close the four holes that will otherwise become invented policy: mechanical
> verify, mutating-gate precedence as a refuse, skip/--confirm-index authority, and
> "compose, don't rewrite."
>
> I would not run this through another external essay review. The next useful artifact is
> the commit-slice spec with a normative transition table, the matcher grammar, and the
> output-contract reason-code enum — the things this sketch correctly leaves for the spec.

Igor's framing on relaying it: "I do not agree with all its findings. You analyse for
yourself."

---

## 12. Claude's analysis of the fourth review

Confirmed most of it; disagreed with the remedies on one finding; found a harness
constraint the reviewer missed that changes the shape of their biggest proposal.

**Point 1 (`forge verify`) — adopt, with a correction the reviewer missed.** The diagnosis
is right: with only `gate run <id>`, the mechanical middle is still a checklist the model
holds, and finalize-refuses-if-missing is "caught at the end," not "structurally
impossible." But the Bash tool's execution ceiling is 10 minutes and Gate 1 alone runs ~11:
a single blocking `forge verify` cannot complete inside one tool call. Verify must
therefore be **resumable by construction** — each invocation executes remaining steps until
done, failure, or interruption; per-step completion is persisted; re-invocation continues
from the first incomplete step; a fully-passed verify is a no-op printing the next judgment
verb. Without this, verify ships as a blocking monolith and dies at the harness timeout on
every standard commit. `gate run <id>` stays for re-running one failed gate.

**Point 2 (mutating-gate precedence) — adopt as given.** `gate run` of a non-mutating gate
refuses while a configured mutating gate is pending. With verify doing the ordering
automatically, the refusal is the backstop for the manual path.

**Point 3 (skips/--confirm-index) — right finding, both offered remedies wrong; a third is
strictly better.** Option (a), binding skips as finalize flags, forces the hook to parse
`--user-skip` out of argv — exactly the FR-090-grade flag-parsing the reviewer warns
against in their own disposition nit. Option (b) concedes the hole. The clean resolution:
skips stop being finalize flags entirely. A separate `forge commit skip <gate-id> --reason`
verb (plus `--index-drift` form) records the skip in chain state before finalize, and the
verb is hook-denied on the model's Bash path and operator-run via `!`, identical to
approve — verb-level denial, no flag parsing. Finalize carries no override flags at all,
which also keeps its hook-allow rule maximally simple. This is honest law, not new law:
FR-056 skips were always user-*directed*; this makes the direction mechanically verifiable
instead of model-attested. Headless runs park on a needed skip exactly as on approval.

**Point 4 (compose, don't rewrite) — adopt**, plus the extraction nuance: where an
interface genuinely does not fit CLI invocation (hook-shaped logic in `commit-guard.sh`),
the sanctioned move is extracting a shared function from the existing script — its own
control-class change, tests pointed at one implementation — never a second copy in Python.

**Points 5, 6, 7 and the nits — adopt.** `--json` stdout carries the envelope only.
`forge push` refuses on halt, failed/dirty rebase, and non-FF, and explicitly does not
audit provenance — it may push commits no closed chain produced, because honest ancestry
auditing is impossible and the commit-denial hook already covers new orchestrator commits
within the threat model. The `!`-channel rule is the best small catch of the round: the
model may ask the operator to run Forge operator verbs via `!`, never raw git — a
constitutional rule in the skills plus a temptation eval. `review disposition` resolved
without flag parsing: the verb is model-issuable; an above-MINOR disposition parks the
chain until operator co-sign through the already-denied approve mechanism. Nits: `open`
dropped from the enum; an env_fingerprint mismatch between the two Gate-1 runs voids the
pair; changelog-gate output paths join the chain's path set and are CLI-staged; the
reconstructible-from-events note gains the "except across the git side effect" caveat.

**Defense in depth — adopt; red lines promoted to normative MUST** (phase 1 dual-accept
may not be skipped; the marker grammar is not deleted until the eval net pins the machine).
Line-count honesty adopted: 100–150 is contingent on verify plus exact-argv next-step
lines; otherwise 250–300.

---

## 13. Igor's disposition

> fold these into revision 4 and append this final round to the research record

---

## 14. Decisions (folded into design doc revision 4)

| # | Finding | Decision |
|---|---------|----------|
| D23 | The clerk is only half-collapsed | New `forge verify` verb: runs every remaining required mechanical step in order (mutating gates first); judgment verbs excluded. Resumable by construction — the 10-minute harness tool ceiling is shorter than Gate 1 alone, so verify continues from the first incomplete step on re-invocation; a fully-passed verify is a no-op printing the next judgment verb. `gate run <id>` remains for single-gate re-runs. |
| D24 | Mutating-gate order load-bearing but unenforced | Machine refusal: `gate run` of a non-mutating gate refuses while a configured mutating gate is pending, naming the pending gate as remediation. |
| D25 | `--user-skip`/`--confirm-index` are the new marker | Skips leave finalize entirely. Operator-bound `forge commit skip <gate-id> --reason` and `forge commit skip --index-drift` verbs, hook-denied on the model's Bash path, operator-run via `!` (same mechanism as approve). Finalize carries no override flags. FR-056 mapping stays a skill duty; the skill presents the exact `!` argv. |
| D26 | Compose, don't rewrite | New Implementation Rule section: `cli.py` invokes the existing tested executables and owns only sequencing, evidence, and authorization; it never reimplements halt, lock, classification, or the secret scan. Interface mismatches are resolved by extracting shared functions from the existing scripts, never by a second copy. |
| D27 | `--json` purity | Under `--json`, stdout is the envelope only; `next required step:` is a field, never a second stdout line. |
| D28 | `forge push` contract underspecified | It refuses on halt, failed/dirty rebase, and non-fast-forward; it does NOT audit commit provenance and may push commits no closed chain produced. Phase 4 must not invent a "chain-produced SHAs only" hook rule. |
| D29 | `!`-bypass also enables `! git commit` | Constitutional rule in skills plus temptation eval: the model may ask the operator to run Forge operator verbs (approve, skip) via `!`; never raw git or any enforcement-bypassing command. |
| D30 | `review disposition` hook-denial ambiguity | The verb is model-issuable; the hook never parses its flags. Above-MINOR dispositions park the chain until operator co-sign via the already-denied approve mechanism. |
| D31 | Nits: unused `open`; env_fingerprint mismatch; changelog paths; reconstructibility | `open` removed (chains are born in `classifying`); a fingerprint mismatch between the two Gate-1 runs voids the pair; mutating-gate output paths join the chain path set and are CLI-staged; reconstructible-from-events carries the "except across the git side effect — recovery observes HEAD" caveat. |
| D32 | Red lines and line-count honesty | Phase-1 dual-accept and marker-grammar retention until the eval net pins the machine are normative MUSTs. The 100–150-line skill estimate is stated as contingent on D23; otherwise 250–300. |
