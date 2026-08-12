"""Contract tests for the forge project template and commit skill."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "system" / "template" / "forge-project.md").read_text(
    encoding="utf-8"
)
COMMIT_SKILL = (ROOT / "skills" / "commit" / "SKILL.md").read_text(
    encoding="utf-8"
)
STACKS_SEED = (
    ROOT / "system" / "seeds" / "validation-snippets" / "stacks.md"
).read_text(encoding="utf-8")

REGIONS = [
    "project-overview",
    "file-categories",
    "stack-validations",
    "gate1-test-command",
    "changelog-policy",
    "review-prompt-project-focus",
    "project-triggers",
    "completeness-project-items",
    "agent-project-context",
    "mutation-testing",
    "invariants",
    "risk-tiers",
    "drift-config",
    "trigger-paths",
]

DEPENDENCY_MANIFEST_PATHS = [
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "requirements*.txt",
    "pyproject.toml",
    "poetry.lock",
    "uv.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "Gemfile",
    "Gemfile.lock",
    "pom.xml",
    "build.gradle*",
    "composer.json",
    "composer.lock",
]

SEEDED_STACKS = [
    "node",
    "python",
    "go",
    "rust",
    "java-maven",
    "java-gradle-kotlin",
    "terraform",
    "docker",
    "helm",
]

GATE1_DEFAULT = (
    'echo "forge: Gate 1 test command not configured — run /forge:init before merging" '
    ">&2; exit 1"
)


def region_body(name: str) -> str:
    match = re.search(
        rf"<!-- FORGE:REGION {re.escape(name)} BEGIN -->(.*?)"
        rf"<!-- FORGE:REGION {re.escape(name)} END -->",
        TEMPLATE,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing region {name}")
    return match.group(1)


class ForgeProjectTemplateTests(unittest.TestCase):
    def test_fourteen_regions_are_complete_and_in_contract_order(self) -> None:
        begins = re.findall(r"<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->", TEMPLATE)
        ends = re.findall(r"<!-- FORGE:REGION ([a-z0-9-]+) END -->", TEMPLATE)
        self.assertEqual(begins, REGIONS)
        self.assertEqual(ends, REGIONS)
        for name in REGIONS:
            with self.subTest(region=name):
                self.assertIn("<!-- forge-init:", region_body(name))

    def test_revision_two_region_defaults_are_conservative_and_complete(self) -> None:
        self.assertIn("fail closed", region_body("invariants"))
        self.assertIn("No mutation-testing policy is configured.", region_body("mutation-testing"))
        self.assertIn(
            "| fast | docs/**, .forge/history/**, @formatting-only |",
            region_body("risk-tiers"),
        )
        self.assertIn("| docs |", region_body("risk-tiers"))

        drift = re.sub(r"<!--.*?-->", "", region_body("drift-config"), flags=re.DOTALL)
        self.assertEqual(
            [line for line in drift.splitlines() if line],
            ["cadence: 14d", "retention: forever", "event-retention: 400d"],
        )
        trigger_paths = re.sub(
            r"<!--.*?-->", "", region_body("trigger-paths"), flags=re.DOTALL
        ).strip()
        self.assertEqual(trigger_paths, "No trigger paths configured.")

    def test_dependency_manifest_block_is_the_exact_fixed_floor(self) -> None:
        body = region_body("risk-tiers")
        match = re.search(
            r"<!-- FORGE:DEPENDENCY-MANIFEST-PATHS BEGIN -->\n(.*?)\n"
            r"<!-- FORGE:DEPENDENCY-MANIFEST-PATHS END -->",
            body,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1).splitlines(), DEPENDENCY_MANIFEST_PATHS)

    def test_every_seeded_stack_declares_test_quality_mining_triple(self) -> None:
        headings = re.findall(r"^## ([a-z0-9-]+) ", STACKS_SEED, flags=re.MULTILINE)
        self.assertEqual(headings, SEEDED_STACKS)

        for index, stack in enumerate(SEEDED_STACKS):
            start = STACKS_SEED.index(f"## {stack} ")
            if index + 1 < len(SEEDED_STACKS):
                end = STACKS_SEED.index(f"## {SEEDED_STACKS[index + 1]} ")
            else:
                end = STACKS_SEED.index("## Gate 1 command derivation")
            section = STACKS_SEED[start:end]
            with self.subTest(stack=stack):
                self.assertIn("Test file patterns:", section)
                self.assertTrue(
                    re.search(
                        r"^Assertion heuristic: (?:regex|literal): `[^`]+`$",
                        section,
                        flags=re.MULTILINE,
                    )
                    or f"No seeded assertion heuristic for {stack}." in section
                )
                self.assertTrue(
                    re.search(
                        r"^Mutation tool: `[^`]+`; changed-files form: `[^`]+`$",
                        section,
                        flags=re.MULTILINE,
                    )
                    or (
                        f"No mutation tool available for {stack}." in section
                        and section.count(
                            "Mutation-testing region fallback: "
                            f"`No mutation tool available for {stack} — "
                            "assertion-quality fallback only.`"
                        )
                        == 1
                    )
                )
                self.assertTrue(
                    "Property library:" in section
                    or f"No property library available for {stack}." in section
                )

    def test_init_declares_absence_as_a_filled_mixed_stack_state(self) -> None:
        init_skill = (ROOT / "skills" / "init" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(
            "That exact declared-absence sentence is the detected stack's filled "
            "`mutation-testing` state",
            init_skill,
        )
        self.assertIn("It is never a silent skip.", init_skill)
        self.assertIn(
            "In a mixed-stack repository keep\nall executable rows under one table header",
            init_skill,
        )
        self.assertIn(
            "one exact declared-absence sentence outside\nthe table for each infeasible "
            "detected stack",
            init_skill,
        )

    def test_gate1_unfilled_body_has_exact_fail_closed_command(self) -> None:
        body = re.sub(r"<!--.*?-->", "", region_body("gate1-test-command"), flags=re.DOTALL)
        body = body.replace("```bash", "").replace("```", "").strip()
        self.assertEqual(body, GATE1_DEFAULT)

    def test_static_spine_and_plugin_skill_pointers_are_present(self) -> None:
        self.assertIn("Install date: `{{FORGE_INSTALL_DATE}}`", TEMPLATE)
        for word in ("Decompose", "Verify", "Review", "Reintegrate"):
            self.assertIn(word, TEMPLATE)
        self.assertIn(
            "A gate satisfied by reducing its strength is a failure, not a pass.",
            TEMPLATE,
        )
        for skill in ("init", "workflow", "orchestrate", "commit", "worktree-merge", "report"):
            self.assertIn(f"${{CLAUDE_PLUGIN_ROOT}}/skills/{skill}/SKILL.md", TEMPLATE)


class CommitSkillTests(unittest.TestCase):
    def test_five_steps_are_in_exact_order_and_fail_closed(self) -> None:
        headings = re.findall(r"^## Step ([1-5]) —", COMMIT_SKILL, flags=re.MULTILINE)
        self.assertEqual(headings, ["1", "2", "3", "4", "5"])
        self.assertIn("fail-closed", COMMIT_SKILL.lower())
        self.assertIn("leaves the change uncommitted", COMMIT_SKILL)

    def test_control_paths_and_review_routing_are_explicit(self) -> None:
        for path in (
            "forge-project.md",
            ".forge-manifest",
            ".codex/**",
            ".forge/evals/**",
            "AGENTS.md",
            "CLAUDE.md",
            ".claude/settings*.json",
            ".github/workflows/**",
        ):
            self.assertIn(path, COMMIT_SKILL)
        self.assertIn("fresh Codex `review-cheap`", COMMIT_SKILL)
        self.assertIn("`review-final` Claude agent", COMMIT_SKILL)
        self.assertIn("distinct agent from the author", COMMIT_SKILL)
        self.assertIn("Project configuration may extend this list", COMMIT_SKILL)
        self.assertIn("must never remove or narrow", COMMIT_SKILL)

    def test_step_two_uses_committed_policy_for_every_quality_surface(self) -> None:
        step_two = COMMIT_SKILL.split("## Step 2 — Validate", 1)[1].split(
            "## Step 3 —", 1
        )[0]
        self.assertIn("git show HEAD:forge-project.md", COMMIT_SKILL)
        self.assertIn("committed `gate1-test-command`", step_two)
        self.assertIn("committed `stack-validations`", step_two)
        self.assertIn("committed `invariants`", step_two)
        self.assertIn("check-test-quality.py", step_two)
        self.assertIn('literal `forge` as `$0`', step_two)
        self.assertIn("65,536-byte", step_two)
        self.assertIn("300-second timeout", step_two)

    def test_review_loop_and_candidate_marker_contract(self) -> None:
        self.assertIn("git diff --cached", COMMIT_SKILL)
        self.assertIn("shasum -a 256", COMMIT_SKILL)
        self.assertIn("at most 8 review", COMMIT_SKILL)
        self.assertIn("requires explicit user approval", COMMIT_SKILL)
        self.assertIn("skip: user-directed", COMMIT_SKILL)
        self.assertIn(".forge/tmp/commit-authorized", COMMIT_SKILL)
        self.assertIn("reviewed_diff_sha256", COMMIT_SKILL)
        self.assertGreaterEqual(COMMIT_SKILL.count("set -o pipefail"), 3)
        self.assertIn("could not hash staged diff — review blocked", COMMIT_SKILL)
        self.assertIn("could not hash staged diff — review skip blocked", COMMIT_SKILL)
        self.assertIn("re-run the affected Step 2 validations", COMMIT_SKILL)
        self.assertIn("restart Step 4", COMMIT_SKILL)
        invalidation = "rm -f .forge/tmp/commit-authorized"
        self.assertLess(COMMIT_SKILL.index(invalidation), COMMIT_SKILL.index("## Step 1 —"))
        control_wait = "then wait for explicit approval naming the reviewed candidate"
        pass_write = (
            "printf '%s\\n%s\\n' \"$reviewed_diff_sha256\" \"$reviewed_at\" "
            "> .forge/tmp/commit-authorized"
        )
        self.assertLess(COMMIT_SKILL.index(invalidation), COMMIT_SKILL.index(control_wait))
        self.assertLess(COMMIT_SKILL.index(control_wait), COMMIT_SKILL.index(pass_write))
        self.assertIn("leaves no authorization marker behind", COMMIT_SKILL)

    def test_skip_mapping_is_exact(self) -> None:
        rows = {
            '`"skip tests"` or `"skip validation"`': "Step 2",
            '`"skip changelog"`': "Step 3",
            '`"skip review"`': "Step 4",
            '`"just commit"` or `"skip everything"`': "Steps 2–4",
        }
        for directive, target in rows.items():
            self.assertIn(f"| {directive} | {target} |", COMMIT_SKILL)
        self.assertIn("Record every user-directed skip durably", COMMIT_SKILL)
        self.assertIn(
            "including a Step 2-only or Step 3-only skip",
            " ".join(COMMIT_SKILL.split()),
        )
        self.assertIn("A skip directive never supplies that approval", COMMIT_SKILL)
        self.assertIn("control-class commits are never autonomous", COMMIT_SKILL)
        skip_approval = "Wait for explicit user approval naming that candidate SHA-256"
        skip_write = (
            "printf '%s\\n%s\\n%s\\n' \"$reviewed_diff_sha256\" \"$reviewed_at\" "
            "'skip: user-directed' > .forge/tmp/commit-authorized"
        )
        self.assertLess(COMMIT_SKILL.index(skip_approval), COMMIT_SKILL.index(skip_write))

    def test_step5_script_sequence_and_journal_rules_are_explicit(self) -> None:
        halt = 'bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh" commit'
        acquire = 'bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/acquire-commit-lock.sh" || exit 1'
        in_lock_hash = 'if ! current_hash="$(git diff --cached | shasum -a 256'
        commit = 'git commit -m "$commit_message"'
        release = "\nrelease_commit_gate\nrelease_status=$?\n"
        positions = [
            COMMIT_SKILL.index(value)
            for value in (halt, acquire, in_lock_hash, commit, release)
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(COMMIT_SKILL.index("trap 'release_commit_gate' EXIT"), positions[0])
        self.assertIn("Never hold the lock across Step 4", COMMIT_SKILL)
        self.assertIn("Never infer the latest run", COMMIT_SKILL)
        self.assertIn("beginning exactly `gate-1: ` for project-test", COMMIT_SKILL)
        self.assertIn("beginning exactly `gate-2: ` for", COMMIT_SKILL)
        self.assertIn("criterion must be exactly `gate-3: review-final verdict`", COMMIT_SKILL)
        self.assertIn('`result: "failed"`', COMMIT_SKILL)
        self.assertIn("exact two-line PASS marker", COMMIT_SKILL)
        self.assertIn("exact three-line user-skip marker", COMMIT_SKILL)
        self.assertIn("30-minute freshness", COMMIT_SKILL)
        self.assertIn("set -o pipefail", COMMIT_SKILL)
        self.assertIn('if ! current_hash="$(git diff --cached | shasum -a 256', COMMIT_SKILL)
        self.assertIn("forge: could not hash staged diff — commit blocked", COMMIT_SKILL)
        self.assertIn("failed to consume commit authorization marker", COMMIT_SKILL)
        self.assertIn("lock-release failure takes precedence", COMMIT_SKILL)
        release_call = "\nrelease_commit_gate\nrelease_status=$?\n"
        clear_traps = "\ntrap - EXIT HUP INT TERM\n"
        self.assertLess(COMMIT_SKILL.index(release_call), COMMIT_SKILL.index(clear_traps))
        for condition in ("missing", "malformed", "stale"):
            self.assertIn(condition, COMMIT_SKILL)

    def test_forbidden_legacy_and_blanket_staging_forms_are_absent(self) -> None:
        shipped = TEMPLATE + COMMIT_SKILL
        legacy_name = "open" + "code"
        self.assertNotIn(legacy_name, shipped.lower())
        self.assertNotIn(str(Path.home()), shipped)
        self.assertNotRegex(COMMIT_SKILL, r"git add\s+(?:-A|\.(?:\s|$))")


if __name__ == "__main__":
    unittest.main()
