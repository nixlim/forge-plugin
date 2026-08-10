from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "skills/worktree-merge/SKILL.md").read_text(encoding="utf-8")


class WorktreeMergeSkillTests(unittest.TestCase):
    def test_frontmatter_and_single_region_source(self) -> None:
        self.assertTrue(SKILL.startswith("---\nname: worktree-merge\n"))
        self.assertIn("exclusively\nfrom the root-level `forge-project.md`", SKILL)
        for region in ("gate1-test-command", "stack-validations", "file-categories"):
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

    def test_control_category_and_approval_are_fail_closed(self) -> None:
        for path in (
            "`forge-project.md`",
            "`.forge-manifest`",
            "`.codex/**`",
            "`.forge/evals/**`",
            "`AGENTS.md`",
            "`CLAUDE.md`",
            "`.claude/settings*.json`",
            "`.github/workflows/**`",
        ):
            with self.subTest(path=path):
                self.assertIn(path, SKILL)
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
