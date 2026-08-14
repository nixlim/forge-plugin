from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "skills/worktree-merge/SKILL.md").read_text(encoding="utf-8")


class WorktreeMergeSkillTests(unittest.TestCase):
    def test_frontmatter_and_single_region_source(self) -> None:
        self.assertTrue(SKILL.startswith("---\nname: worktree-merge\n"))
        self.assertIn("exclusively from that root-level\ncommitted revision", SKILL)
        for region in (
            "gate1-test-command",
            "stack-validations",
            "file-categories",
            "mutation-testing",
        ):
            with self.subTest(region=region):
                self.assertIn(region, SKILL)
        self.assertIn("forge: <region> not configured — run /forge:init", SKILL)

    def test_preconditions_and_gates_are_ordered(self) -> None:
        required = (
            "git status --porcelain=v1 --untracked-files=all",
            "git diff origin/<default-branch>...HEAD",
            "## Gate 1 — Project tests",
            "## Gate 2 — Stack validations",
            "## Gate 3 — Binding adversarial review",
            "## Gate 4 — Summary and authority",
        )
        positions = [SKILL.index(item) for item in required]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Fail closed", SKILL)
        self.assertIn("maximum of 8 review iterations", SKILL)
        self.assertIn("never merge", SKILL)

    def test_noncritical_drift_is_advisory_before_gate_one(self) -> None:
        clean_tree = SKILL.index("git status --porcelain=v1 --untracked-files=all")
        drift_contract = SKILL.index("### Drift state is not a merge input")
        gate_one = SKILL.index("## Gate 1 — Project tests")
        self.assertLess(clean_tree, drift_contract)
        self.assertLess(drift_contract, gate_one)

        contract = SKILL[drift_contract:gate_one]
        required_in_order = (
            "After the clean-worktree precondition passes",
            "continue toward Gate 1 without consulting drift\nstate",
            "do not read\n`.forge/history/drift/**` or `.forge/tmp/drift-block`",
            "A recorded MAJOR or MINOR finding",
            "advisory to merge and does not stop or change the merge gates",
            "An existing drift-block is likewise\nnot a merge input",
            "Proceed through the remaining configured preconditions to Gate 1",
        )
        positions = [contract.index(item) for item in required_in_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("separate workflow-opening rule for CRITICAL drift", contract)
        self.assertIn("does not authorize opening an orchestration run", contract)

    def test_merge_derives_tier_from_exact_committed_candidate_policy(self) -> None:
        invocation = (
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/risk_tier.py" \\\n'
            '  --repo "$PWD" --policy-sha "$policy_sha" "${declared_args[@]}" \\\n'
            '  --range "${REVIEWED_BASE}...${CANDIDATE_HEAD}"'
        )
        self.assertIn('policy_sha="$CANDIDATE_HEAD"', SKILL)
        self.assertIn('git show "${policy_sha}:forge-project.md"', SKILL)
        self.assertIn('declared_tier="${declared_tier:-}"', SKILL)
        self.assertIn('declared_args=()', SKILL)
        self.assertIn(invocation, SKILL)
        tiering = SKILL.split("Derive merge-tier evidence", 1)[1].split("Before Gate 1", 1)[0]
        for evidence in (
            "exact path list",
            "matched tier/trigger/category rows",
            "formatting-category decisions",
            "dependency-floor decision",
            "declared, derived, and promote-only\neffective tiers",
            "full policy SHA",
        ):
            self.assertIn(evidence, tiering)
        self.assertIn("can never be demoted at gate time", tiering)
        self.assertIn("non-narrowable floors", tiering)
        self.assertIn("malformed nonempty trigger rows\nmake the range hard", tiering)
        self.assertIn("unmatched paths default standard", tiering)
        self.assertIn("unknown manifest membership are at least standard", tiering)

    def test_control_category_and_approval_are_fail_closed(self) -> None:
        for path in (
            "`forge-project.md`",
            "`.forge-manifest`",
            "`.codex/**`",
            "`.forge/evals/tasks/**`",
            "`AGENTS.md`",
            "`CLAUDE.md`",
            "`.claude/settings*.json`",
            "`.github/workflows/**`",
        ):
            with self.subTest(path=path):
                self.assertIn(path, SKILL)
        self.assertIn("`.forge/evals/candidates/**` is the sole eval-path exception", SKILL)
        self.assertIn("classify it as advisory/docs-class", SKILL)
        self.assertIn("`.forge/evals/tasks/**`, or creating or changing its baseline", SKILL)
        self.assertNotIn("`.forge/evals/**`", SKILL)
        self.assertIn("wait for explicit user approval naming that same SHA", SKILL)
        self.assertIn("Never approve a control-class merge autonomously", SKILL)
        self.assertIn("Use `CANDIDATE_HEAD` as the Gate 4\ncandidate identity", SKILL)

    def test_dm001_gate_records_and_fixed_review_diff(self) -> None:
        self.assertIn('git diff "${REVIEWED_BASE}...${CANDIDATE_HEAD}"', SKILL)
        self.assertIn("exact, unmodified diff", SKILL)
        self.assertIn("explicitly identified orchestration run", SKILL)
        self.assertIn("including every in-lock re-run", SKILL)
        self.assertIn("exactly `gate-1: `", SKILL)
        self.assertIn("exactly `gate-2: `", SKILL)
        self.assertIn("exactly\n`gate-3: review-final verdict`", SKILL)
        flattened = " ".join(SKILL.split())
        self.assertIn(
            "resolved full-SHA `${REVIEWED_BASE}...${CANDIDATE_HEAD}` range",
            flattened,
        )
        self.assertIn("`${INTEGRATED_BASE}...${INTEGRATED_HEAD}` range", SKILL)
        self.assertIn('git diff "${INTEGRATED_BASE}...${INTEGRATED_HEAD}"', SKILL)
        self.assertIn("wait for explicit user approval naming that exact SHA", flattened)
        self.assertIn('require `git rev-parse HEAD` to equal `AUTHORIZED_HEAD`', SKILL)

    def test_gate_three_is_unconditional_after_all_fast_commits(self) -> None:
        gate3 = SKILL.split("## Gate 3", 1)[1].split("## Gate 4", 1)[0]
        self.assertIn("Gate 3 is unconditional", gate3)
        self.assertIn("effective-fast\nrange", gate3)
        self.assertIn("branch composed entirely of four-line fast-marker commits", gate3)
        self.assertIn("`review-final`", gate3)
        self.assertIn("never removes a merge gate", SKILL)

    def test_merge_review_block_event_is_post_outcome_and_advisory(self) -> None:
        gate3 = SKILL.split("## Gate 3", 1)[1].split("## Gate 4", 1)[0]
        delivered = gate3.index("first deliver and preserve the binding BLOCK outcome")
        emitted = gate3.index("emit-decision-event.py")
        self.assertLess(delivered, emitted)
        self.assertIn("event `review_block`", gate3)
        self.assertIn("SHA-256 of the exact reviewed merge diff", gate3)
        self.assertIn("surface `/forge:worktree-merge`", gate3)
        self.assertIn("never changes the Gate 3 verdict or exit status", gate3)
        self.assertIn("registers an in-flight writer but acquires no lock", SKILL)
        self.assertIn("os.O_WRONLY | os.O_APPEND | os.O_CREAT", SKILL)
        self.assertIn("makes exactly one `os.write()`", SKILL)
        self.assertIn("treats a short write as a failure", SKILL)
        self.assertIn("gates only drift-check's prune read-and-replace", SKILL)
        self.assertIn("does not extend to NFS/SMB network filesystems", SKILL)
        self.assertIn("Windows is out of scope", SKILL)
        self.assertIn("deduplicates merge review blocks by `(event, candidate)`", SKILL)

    def test_assertion_and_reviewer_measurement_events_are_exact_and_advisory(self) -> None:
        sensor = SKILL.split("After preserving the sensor's primary result", 1)[1].split(
            "## Gate 3", 1
        )[0]
        for event in (
            "`assertion_blocking`",
            "`assertion_advisory`",
            "`assertion_waived`",
        ):
            with self.subTest(event=event):
                self.assertIn(event, sensor)
        self.assertIn("exact merge-diff bytes", sensor)
        self.assertIn("surface\n`/forge:worktree-merge`", sensor)
        self.assertIn("clean\nsensor result", sensor)
        self.assertIn("emits no assertion event", sensor)
        self.assertIn("in-lock Gate 2 rerun", sensor)
        self.assertIn("never changes the\nGate 2 result or exit status", sensor)

        reviewer = SKILL.split(
            "After preserving each `review-final` invocation's complete verdict", 1
        )[1].split("For a revision", 1)[0]
        self.assertIn("`review_final_finding`", reviewer)
        self.assertIn("exact reviewed merge diff", reviewer)
        self.assertIn("surface\n`/forge:worktree-merge`", reviewer)
        for severity in ("`CRITICAL`", "`MAJOR`", "`MINOR`"):
            self.assertIn(severity, reviewer)
        self.assertIn("every required in-lock review", reviewer)
        self.assertIn("no findings emits no\nfinding event", reviewer)
        self.assertIn("never changes the verdict, review iteration, or exit status", reviewer)

    def test_scoped_mutation_runner_is_ordered_advisory_and_reviewed(self) -> None:
        gate_1_pass = SKILL.index("Require exit 0. Do not substitute")
        mutation = SKILL.index(
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/run-scoped-mutation.py"'
        )
        gate_2 = SKILL.index("## Gate 2 — Stack validations")
        gate_3 = SKILL.index("## Gate 3 — Binding adversarial review")
        evidence_handoff = SKILL.index(
            "Also give the reviewer the complete contents of `MUTATION_EVIDENCE_FILE`"
        )
        self.assertLess(gate_1_pass, mutation)
        self.assertLess(mutation, gate_2)
        self.assertLess(gate_2, gate_3)
        self.assertGreater(evidence_handoff, gate_3)
        self.assertIn('--base "$REVIEWED_BASE" --head "$CANDIDATE_HEAD"', SKILL)
        self.assertIn('--range "${INTEGRATED_BASE}...${INTEGRATED_HEAD}"', SKILL)
        integrated = SKILL.split("then replace the earlier tier evidence fail closed:", 1)[1]
        self.assertIn('TIER_EVIDENCE="$(python3', integrated)
        self.assertIn('--policy-sha "$policy_sha"', integrated)
        self.assertIn('"${declared_args[@]}"', integrated)
        self.assertIn(')" || exit 1', integrated)
        self.assertIn("A nonzero result, timeout, output-limit breach, launch failure", SKILL)
        self.assertIn("It never blocks merge and never satisfies Gate 1", SKILL)
        self.assertIn("criterion exactly `mutation: <scope>`", SKILL)
        self.assertIn("Never use\na `gate-` prefix for mutation evidence.", SKILL)

    def test_locked_rebase_contract_is_complete(self) -> None:
        for command in (
            'bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh"',
            "git rev-parse --path-format=absolute --git-common-dir",
            "agent-rebase.lock",
            "agent-rebase.lockdir",
            "flock --timeout 300",
            'trap \'rmdir "$LOCK_DIR"\' EXIT',
            "git fetch origin <default-branch>",
            "git rebase origin/<default-branch>",
            "git push origin HEAD:<default-branch>",
        ):
            with self.subTest(command=command):
                self.assertIn(command, SKILL)
        self.assertIn("Never skip locking", SKILL)
        self.assertGreaterEqual(SKILL.count("holder hint:"), 2)
        self.assertIn("Never create a merge commit", SKILL)
        self.assertIn("Do not defer a\nre-run until after the push", SKILL)

    def test_reverification_cleanup_and_record_authority(self) -> None:
        self.assertIn(
            "If `DEFAULT_ADVANCED=1` or `CANDIDATE_REWRITTEN=1`, re-run Gate 1 and Gate 2",
            SKILL,
        )
        self.assertIn("If conflicts were resolved, Gate 3 is mandatory", SKILL)
        self.assertIn("If `CANDIDATE_REWRITTEN=1` without conflicts", SKILL)
        self.assertIn("pure fast-forward", SKILL)
        self.assertIn("git merge-base --is-ancestor", SKILL)
        self.assertIn('git worktree remove "$WORKTREE_DIR"', SKILL)
        self.assertIn("worktree removal failed — branch preserved", SKILL)
        self.assertIn("failed to release rebase lock directory", SKILL)
        cleanup = SKILL.split("## Cleanup after successful push", maxsplit=1)[1].split(
            "## Record authority and report", maxsplit=1
        )[0]
        self.assertNotIn("--force", cleanup)
        self.assertIn("agent handoff and claimed gate result as a claim", SKILL)
        self.assertIn("integration target, not in the agent's worktree", SKILL)

    def test_unsafe_bulk_stage_commands_are_absent(self) -> None:
        self.assertNotIn("git add .", SKILL)
        self.assertNotIn("git add -A", SKILL)


if __name__ == "__main__":
    unittest.main()
