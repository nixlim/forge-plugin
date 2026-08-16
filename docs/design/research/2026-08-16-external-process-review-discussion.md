# External Process Review of forge-plugin — Discussion Record

**Date:** 2026-08-16
**Participants:** Igor (operator), Claude (session agent). The review itself was produced by a
third, external agent and relayed by Igor.
**Status:** verbatim record. The review and both discussion turns are reproduced exactly as
written. Outcomes are listed at the end.

---

## 1. Igor's message (relaying the external review)

> here's the feedback I got on forge-plugin from another agent:
>
> This is one of the few agent operating systems that starts from the right problem: generated
> code is cheap; a trustworthy "we checked this" is not. Almost every durable piece of Forge
> exists to test claims rather than produce more of them. That diagnosis is correct, and it
> shows.
>
> I did not run a line-by-line code review of the uncommitted spec diff. This is a process
> review of what the plugin actually implements.
>
> What the process is
>
> Forge is a fail-closed DVRR protocol for a Claude orchestrator driving Codex workers:
>
> 1. Decompose into owned files, acceptance criteria, and exact validation commands.
> 2. Delegate into isolated worktrees with disjoint file ownership.
> 3. Verify by re-running the project's own tests and lints in the orchestrator's environment.
> 4. Review with a binding, independent verdict.
> 5. Reintegrate only after those gates still pass against the current default branch, via
>    locked rebase.
>
> The role split is the structural idea. Codex implements. A different Codex session does
> first-pass review and is forbidden the implementer's handoff. Claude holds the binding
> review-final verdict. Author and judge do not share a model family. That is stronger than
> "the same agent reviews itself," and stronger than most same-family reviewer setups.
>
> Authority is explicit: autonomous after a clean gate chain; gated approval for control
> changes; advisory for learning; reserved for the operator (halt, secrets, production). A
> control change cannot commit itself.
>
> What is genuinely good
>
> Claims are not evidence. The orchestrator re-runs Gate 1 and Gate 2 itself. A handoff that
> says "all tests passed" is treated as a rumor. The founding notes say this caught the only
> false-green of the original build. That single rule is worth more than most of the ceremony
> around it.
>
> Fail-closed is real in the places that matter. Unconfigured gates refuse. Policy is read
> from committed HEAD via git show, not from a working-tree file the agent can edit mid-chain.
> Authorization is the SHA-256 of the exact staged bytes, stale after 30 minutes, consumed on
> use. Two concurrent chains cannot authorize each other's diffs. The PreToolUse hook is the
> last line of defense, not a suggestion.
>
> They are honest about the threat model. The spec says the enforcement layer stops accident,
> negligence, and prompt injection. It does not stop a deliberately adversarial orchestrator,
> because Claude is the operator's OS user. That sentence is rarer than it should be.
>
> Control integrity is the right meta-rule. "A gate satisfied by reducing its strength is a
> failure, not a pass." Golden-result rewriting, coverage narrowing, self-disposition of MAJOR
> findings, and silent model/effort substitution are all named as gaming. Tests are supposed
> to fail when the control is disabled in memory. Learning proposes eval candidates and
> gotchas and is forbidden from applying them. A system that rewrote its own gates from its
> own failures would be laundering regressions.
>
> Several rules were paid for in production, not invented. Detached nohup launches exist
> because the session layer killed Codex wrappers five times. Events files are created before
> the journal entry because a missing events path is fatal to the monitor. Implementers are
> never resumed because resume degraded to a read-only sandbox. SHAs are copied from command
> output because transcription errors are permanent in an append-only journal. Claude writes
> its own plan before reading a Codex proposal. That last one — anti-anchoring — is one of the
> smartest process rules in the repo.
>
> Risk tiers exist because they noticed the ceremony-cost failure mode. D6–D14 were a direct
> response to "every change pays the full chain." Fast / standard / hard, promote-only, a
> non-narrowable control floor, mutation as advisory-first, Python assertion sensing as the
> one blocking escalation: that is a mature second-system move.
>
> Where I think it is weaker
>
> The process is mostly a very long prompt with a hook at the end. Commit is 622 lines.
> Worktree-merge is 574. Init is 582. The eight skills together are ~2,800 lines of procedure,
> on top of a 1,179-line spec still marked Draft. An orchestrator will not reliably execute a
> 600-line skill without skipping, compressing, or "helpfully" inferring a skip. The hook, the
> marker grammar, validate --gates, and the tests-that-fail-when-disabled are the actual
> compiler. Everything else is an instruction manual for a fallible clerk. The next leap is
> not another lens or FR number. It is moving more of that clerk work into something
> unskippable by construction.
>
> Ceremony is still winning the dogfood. The 2026-08-15 drift report is mechanically clean,
> and its telemetry is telling: 1 eligible commit, 0 fast-path, 0 user skips, Gate 1 on a
> clean tree took 660 seconds. Merge Gate 3 is always review-final, even when every
> constituent commit was fast. That is conservative and correct for integration risk. It is
> also why the fast tier does not save what D6–D14 hoped it would. If the plugin cannot use
> its own cheap path on its own repo, operators of ordinary product repos will either skip the
> chain or stop installing it.
>
> The review constitution is a spec-reviewer's constitution. Eight lenses, RFC 2119, STRIDE,
> state machines, pagination, rate limits, encryption-at-rest: excellent for a requirements
> document. Applied to a 20-line bugfix it produces noise, hedged BLOCKs, or reviewers who
> learn to rubber-stamp the completeness checklist. The per-artefact profiles were meant to
> cut that noise. They extend the baseline; they never remove a lens. So the floor is still
> the spec floor.
>
> "Twice consecutively" is the right anti-flake instinct and is easy to fake. Two back-to-back
> runs of the same command in the same environment are not two independent verifications.
> Nothing mechanical distinguishes "ran it twice" from "reproduced it." Same for the
> 8-iteration cap: it stops infinite review loops, which is good, and it also trains the
> system to disposition findings as residual risk at iteration 8.
>
> The eval net is thin for a control system this large. Three golden tasks: injection is
> flagged, a planted bug is BLOCKed, a clean change PASSes. Empty suite fails closed, which is
> the right shape. Three fixtures do not pin the constitution, the hook parser, the marker
> grammar, the risk classifier, or the journal gate profile. Control-class work requires
> STRICT=1 evals, but STRICT over a tiny suite is a short fence.
>
> Mutation and most test-quality sensing are still advisory. That was a deliberate
> calibration, and I agree with not blocking merge on an unbaselined mutant score. It also
> means the "prove the tests actually test" story is incomplete. The Python AST assertion
> sensor is the one blocking tooth, and it only catches tests with no recognizable assert.
>
> Two process systems are spliced into the same repo. Forge owns DVRR, journals, and gate
> chains. Beads owns task tracking and a "work is not complete until git push" close protocol.
> Those close protocols are not the same. An agent following both will either violate Forge's
> commit/merge chain or violate Beads' mandatory push. Overlaying trackers is how process
> becomes theater.
>
> The durable-intent loop is specified more completely than it is populated. Journals are
> local-excluded working state; archives are supposed to be committed under
> .forge/history/runs/. That directory is empty in this checkout. Drift can still see
> historical journal patterns (the verification-expansion run had tasks with 4–6
> failed→passed cycles), but the "committed, append-only intent record" is not yet the corpus
> the README describes.
>
> The judgment
>
> Forge is not a workflow fashion. It is a control system for pairing a fallible generator
> with a fallible judge, written by people who have already lost work to session killers,
> false-green handoffs, and self-weakening gates.
>
> The parts I would keep in any agent process:
>
> • claims ≠ evidence
> • author and binding reviewer on different model families
> • committed policy, never working-tree policy
> • content-addressed, time-bounded authorization
> • fail-closed unconfigured gates
> • control changes cannot approve themselves
> • learning proposes and never applies
> • write your own plan before reading the other model's
>
> The parts I would treat as debt, not doctrine:
>
> • encoding the compiler in 600-line skills
> • applying a spec constitution to every artefact
> • a fast path that dogfood does not use
> • an eval suite too small to protect the controls
> • a second issue tracker with a conflicting close ritual
>
> If this process is for this plugin, and for other high-stakes control software, it is
> appropriately severe. If it is meant to be the default SDLC for every repo /forge:init
> touches, it will be skipped. The verification expansion already named that failure mode. The
> remaining work is to make the cheap path real, and to make more of the expensive path
> mechanical so the orchestrator cannot "follow the spirit" of a skill it did not actually
> run.
>
> I want to know what is your opinion.
>
> I like the idea that more of what we do in skills could be moved into CLI? I am not sure
> what is the range of the possible here
>
> DO NOT CHANGE ANY CODE - THIS IS A DISCUSSION ONLY AT PRESENT

---

## 2. Claude's response

> I've looked at the skill sizes and the existing `scripts/forge/` inventory to ground this.
> My opinion, in two parts: the review, then the CLI question.
>
> ### On the review itself
>
> It's the most accurate external read of Forge I've seen, and its central criticism is
> correct: **the enforcement architecture is inverted.** The things that actually cannot be
> bypassed — the PreToolUse hook, the marker parser, committed-policy sourcing,
> content-addressed authorization — total maybe a few hundred lines of code. The things that
> direct the work — 2,778 lines of skill prose plus a 1,179-line spec — are executed by the
> model, and a model executing a 622-line procedure is exactly the "fallible clerk" the
> reviewer describes. I live inside this system; the failure mode is not disobedience, it's
> lossy compression. Under context pressure a long skill gets summarized in the model's
> working attention, and steps whose absence isn't mechanically detected are the ones that
> get compressed out. The hook only catches the ones someone thought to encode in the marker
> grammar.
>
> The dogfood telemetry point (0 fast-path uses, 660s Gate 1 on a clean tree) is the most
> dangerous finding, and I'd add a diagnosis the reviewer didn't quite reach: the fast path
> is unused partly because *claiming* it costs work. The model must classify, compute tier
> evidence, and justify eligibility — so the path of least resistance is to just run the full
> chain. A cheap path that requires effort to claim is not a cheap path.
>
> Two places I'd push back mildly:
>
> - **"Twice consecutively is easy to fake"** — true but slightly misaimed. That rule was
>   anti-flake, never anti-fraud; nothing about it was meant to be adversarially robust. The
>   real issue is that it's the model transcribing "I ran it twice," which is the same
>   transcription-trust problem as everything else, and it has the same fix (below).
> - **The Beads splice** is real, but the conflict is narrower than presented: Beads' "push
>   before done" and Forge's gate chain conflict only at session close. It's resolvable by
>   one sentence of precedence ("Beads close protocol is satisfied only through the Forge
>   chain") rather than being structural rot. It should still be fixed — as written, an agent
>   genuinely can't satisfy both.
>
> ### The CLI question — what's the range of the possible?
>
> Large. I think this is the single highest-leverage direction for Forge, and the range is
> bigger than "extract some helper scripts." The design shift is:
>
> **Today:** the skill is the program, the model is the interpreter, and the CLI scripts are
> subroutines the model must remember to call in the right order. `skills/commit/SKILL.md` is
> 622 lines mostly because it must specify sequencing, preconditions, marker grammar, and
> invariant restatements in prose — precisely the parts a model executes least reliably.
>
> **Possible:** a single `forge` CLI that owns the state machine, and the model only supplies
> judgment at the points the CLI asks for it. The skill shrinks to "run
> `forge commit start --paths ...` and do what it tells you."
>
> Concretely, what's mechanizable:
>
> 1. **Chain sequencing as persisted state.** `forge commit start` creates a
>    content-addressed chain record; each subsequent subcommand (`forge gate run 1`,
>    `forge review attach`, `forge commit finalize`) checks its own preconditions against
>    that record and *refuses out of order*. Skipping a step becomes structurally impossible
>    rather than prose-forbidden. Each command ends its output with "next required step: X" —
>    the model never needs to hold the whole procedure in attention, only the current edge of
>    the graph.
>
> 2. **Evidence capture without transcription.** Gates run *through* the CLI, which records
>    exit codes, durations, and output hashes into the journal itself. The "copy SHAs from
>    command output" rule, the twice-consecutively honesty problem, and false-green handoffs
>    all share one root cause: the model relaying facts it observed. If the CLI observes and
>    attests, that class of failure disappears. Two runs recorded by the CLI with timestamps
>    and environment fingerprints actually *is* mechanical evidence of two runs.
>
> 3. **The marker grammar mostly dissolves.** Markers exist so the hook can parse the model's
>    *claims*. If a passing gate run is recorded by the CLI that executed it, the
>    authorization artifact is written by code, and the hook checks an artifact chain instead
>    of parsing prose claims. That deletes the grammar, its parser, and their failure modes.
>
> 4. **Even some "behavioral" rules are mechanizable by controlling information flow.** The
>    anti-anchoring rule ("write your own plan before reading the Codex proposal") can be
>    enforced: the CLI withholds the proposal until Claude's plan is journaled. Same for "the
>    first-pass reviewer is forbidden the implementer's handoff" — have the CLI construct the
>    reviewer's context package rather than trusting the orchestrator not to paste. These are
>    currently the least enforceable rules in the repo, and they become hard guarantees.
>
> 5. **Fast-path becomes opt-out.** `risk_tier.py` already computes tier evidence; if the
>    chain CLI computes eligibility itself and defaults to the fast profile when the paths
>    qualify, the cheap path costs nothing to claim — which is the only way dogfood (and
>    ordinary repos) will ever use it. Promote-only is trivially enforced in code: the CLI
>    simply has no demote operation.
>
> What stays in the skill, because it's genuine judgment: what to stage, how to classify
> semantic scope beyond path patterns, dispositioning findings, writing plans and reviews,
> and the standing duty to stop and surface when something looks wrong outside the checklist.
> That last one matters — the risk of over-mechanization is a model that stops noticing
> anomalies because the CLI's green light became the only signal it attends to. I'd estimate
> the commit skill collapses from 622 lines to roughly 100–150: classification guidance plus
> per-decision-point instructions.
>
> Two honest costs:
>
> - **Complexity moves; it doesn't vanish.** The CLI becomes control-class code with its own
>   test surface. But that's the trade you want: a state machine in Python is unit-testable,
>   and "tests that fail when the control is disabled" finally has a real target. You cannot
>   unit-test prose executed by an LLM. This is the git model — porcelain guides, plumbing
>   enforces — and it's proven.
> - **Escape hatches must live inside the tool.** User-directed skips need to be
>   `forge commit finalize --user-skip=gate2 --reason=...`, journaled, or operators will
>   route around the entire CLI the first time it's inconvenient — and a bypassed control
>   system is worse than a prose one, because it still *looks* enforced.
>
> If I ranked the reviewer's debt list by leverage, the CLI-ification is first, because it's
> the one that pays down three others simultaneously: it's what makes the fast path actually
> cheap, it shrinks the skills, and it converts the thin eval net's job from "pin the clerk's
> behavior" (huge surface) to "pin the state machine" (small, testable surface). The eval
> suite is thin today partly because the thing it would need to pin — model adherence to
> prose — is nearly unpinnable. Shrink what the model is trusted with, and three golden tasks
> stop being obviously insufficient.

---

## 3. Igor's direction (follow-up)

> It's resolvable by one sentence of precedence
>   ("Beads close protocol is satisfied only through the Forge chain")
>
> do this change now
>
> then:
> sketch what the forge CLI's subcommand surface and chain-state schema would look like as a
> design doc
> do this. and record this discussions please in .md verbatim please

---

## 4. Outcomes

1. **Close-protocol precedence** added to `CLAUDE.md` as a `## Close Protocol Precedence`
   section, placed outside the managed `BEADS INTEGRATION` block so a beads re-render cannot
   overwrite it: the Beads close protocol (including its mandatory push) is satisfied only
   through the Forge commit and merge gate chains; on conflict the Forge chain governs.
2. **CLI design sketch** written as `docs/design/0003-forge-cli-plumbing.md` — subcommand
   surface, chain-state schema, hook integration, migration phases, and the honest cost
   ledger. Draft proposal only; adoption requires its own control-class spec change.
3. **This record** — the discussion preserved verbatim.
