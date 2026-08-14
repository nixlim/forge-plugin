"""Contract tests for the forge project template and commit skill."""

from __future__ import annotations

import ast
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
DRIFT_CHECK = (ROOT / "scripts" / "forge" / "drift-check.sh").read_text(
    encoding="utf-8"
)

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
        self.assertIn(
            "| `docs` | `*.md`, `docs/**`, `.forge/history/**` |",
            region_body("file-categories"),
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

    def test_drift_stacks_equal_all_seeded_category_rows(self) -> None:
        python_body = DRIFT_CHECK.split("<<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0]
        module = ast.parse(python_body)
        assignments = [
            node
            for node in module.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "STACKS"
        ]
        self.assertEqual(len(assignments), 1)
        stacks = ast.literal_eval(assignments[0].value)

        seeded_rows = []
        for match in re.finditer(
            r"^## (?P<stack>[a-z0-9-]+) "
            r"\(markers?: (?P<markers>[^;\n)]+)(?:;[^)]*)?\)\n\n"
            r"Category row: `\| \\`(?P<category>[a-z0-9-]+)\\` \|",
            STACKS_SEED,
            flags=re.MULTILINE,
        ):
            seeded_rows.append(
                (
                    match.group("stack"),
                    (
                        tuple(re.findall(r"`([^`]+)`", match.group("markers"))),
                        match.group("category"),
                    ),
                )
            )
        self.assertEqual(len(seeded_rows), 9)
        actual_rows = [
            (stack, (frozenset(markers), category))
            for stack, (markers, category) in stacks.items()
        ]
        expected_rows = [
            (stack, (frozenset(markers), category))
            for stack, (markers, category) in seeded_rows
        ]
        self.assertEqual(actual_rows, expected_rows)

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
        for skill in (
            "init",
            "workflow",
            "orchestrate",
            "commit",
            "worktree-merge",
            "report",
            "drift",
        ):
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
        self.assertIn("fresh, read-only Codex `review-cheap`", COMMIT_SKILL)
        self.assertIn("`review-final` Claude agent", COMMIT_SKILL)
        self.assertIn("distinct agent from the author", COMMIT_SKILL)
        self.assertIn("Project configuration may extend this list", COMMIT_SKILL)
        self.assertIn("must never remove or narrow", COMMIT_SKILL)

    def test_step_two_uses_committed_policy_for_every_quality_surface(self) -> None:
        step_two = COMMIT_SKILL.split("## Step 2 — Validate", 1)[1].split(
            "## Step 3 —", 1
        )[0]
        self.assertIn('git show "${policy_sha}:forge-project.md"', COMMIT_SKILL)
        self.assertIn("set `policy_sha` to the full result of `git rev-parse HEAD`", COMMIT_SKILL)
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
        self.assertIn(
            'commit_marker="$forge_main_root/.forge/tmp/authorized/$reviewed_diff_sha256"',
            COMMIT_SKILL,
        )
        self.assertIn("reviewed_diff_sha256", COMMIT_SKILL)
        self.assertGreaterEqual(COMMIT_SKILL.count("set -o pipefail"), 3)
        self.assertIn("could not hash staged diff — review blocked", COMMIT_SKILL)
        self.assertIn("could not hash staged diff — review skip blocked", COMMIT_SKILL)
        self.assertIn("re-run the affected Step 2 validations", COMMIT_SKILL)
        self.assertIn("restart Step 4", COMMIT_SKILL)
        invalidation = "reviewed_diff_sha256=''\ncommit_marker=''"
        self.assertLess(COMMIT_SKILL.index(invalidation), COMMIT_SKILL.index("## Step 1 —"))
        control_wait = "then wait for explicit approval naming the reviewed candidate"
        pass_write = (
            "printf '%s\\n%s\\n' \"$reviewed_diff_sha256\" \"$reviewed_at\" "
            '> "$commit_marker"'
        )
        self.assertLess(COMMIT_SKILL.index(invalidation), COMMIT_SKILL.index(control_wait))
        self.assertLess(COMMIT_SKILL.index(control_wait), COMMIT_SKILL.index(pass_write))
        self.assertIn("leaves no authorization marker behind", COMMIT_SKILL)

    def test_assertion_and_reviewer_measurement_events_are_exact_and_advisory(self) -> None:
        sensor = COMMIT_SKILL.split(
            "After preserving the sensor's primary result", 1
        )[1].split("For a control-class commit", 1)[0]
        for event in (
            "`assertion_blocking`",
            "`assertion_advisory`",
            "`assertion_waived`",
        ):
            with self.subTest(event=event):
                self.assertIn(event, sensor)
        self.assertIn("exact `reviewed_diff_sha256`", sensor)
        self.assertIn("surface `/forge:commit`", sensor)
        self.assertIn("clean sensor result", sensor)
        self.assertIn("emits no assertion event", sensor)
        self.assertIn("only after\nthe sensor result is preserved", sensor)
        self.assertIn("never changes Step 2's result or exit status", sensor)

        reviewer = COMMIT_SKILL.split(
            "After preserving each reviewer's complete primary verdict", 1
        )[1].split("Give the reviewer", 1)[0]
        self.assertIn("`review_cheap_finding`", reviewer)
        self.assertIn("`review_final_finding`", reviewer)
        self.assertIn("exact\n`$reviewed_diff_sha256`", reviewer)
        self.assertIn("surface `/forge:commit`", reviewer)
        for severity in ("`CRITICAL`", "`MAJOR`", "`MINOR`"):
            self.assertIn(severity, reviewer)
        self.assertIn("no findings emits no finding event", reviewer)
        self.assertIn("after the verdict and findings are\npreserved", reviewer)
        self.assertIn("never changes the verdict, iteration, or exit\nstatus", reviewer)

    def test_gate_time_tiering_is_exact_promote_only_and_non_narrowable(self) -> None:
        invocation = (
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/risk_tier.py" \\\n'
            '  --repo "$PWD" --policy-sha "$policy_sha" --staged \\\n'
            '  "${declared_args[@]}"'
        )
        self.assertIn(invocation, COMMIT_SKILL)
        self.assertIn('declared_tier="${declared_tier:-}"', COMMIT_SKILL)
        self.assertIn('declared_args=()', COMMIT_SKILL)
        self.assertIn('"${declared_args[@]}"', COMMIT_SKILL)
        self.assertIn('fast|standard|hard)', COMMIT_SKILL)
        self.assertIn('effective_tier="$(python3 -c', COMMIT_SKILL)
        self.assertIn('json.load(sys.stdin).get("effective_tier")', COMMIT_SKILL)
        self.assertIn('echo "forge: invalid risk-tier evidence"', COMMIT_SKILL)
        classifier = COMMIT_SKILL.split("Before selecting a reviewer", 1)[1].split(
            "Route the review as follows:", 1
        )[0]
        for evidence in (
            "exact staged\npath list",
            "every matched tier/trigger/category row",
            "every formatting-category decision",
            "dependency-floor decision",
            "`declared_tier`",
            "`derived_tier`",
            "promote-only `effective_tier`",
            "full `policy_sha`",
        ):
            self.assertIn(evidence, classifier)
        self.assertIn("no gate-time demotion is possible", classifier)
        self.assertIn("non-narrowable hard floor", classifier)
        self.assertIn("malformed nonempty trigger row makes the whole candidate hard", classifier)
        self.assertIn("matching no tier row defaults to standard", classifier)
        self.assertIn("unknown\nmanifest membership impose at least standard", classifier)

    def test_fast_skips_only_review_and_writes_exact_four_line_marker(self) -> None:
        routing = COMMIT_SKILL.split("Route the review as follows:", 1)[1].split(
            "Give the reviewer", 1
        )[0]
        self.assertIn("`fast`: skip only this adversarial reviewer", routing)
        for retained in (
            "classification",
            "validation",
            "invariants",
            "assertion-quality",
            "changelog",
            "secret scan",
            "halt",
            "lock",
            "staged-diff re-verification",
            "guard recomputation",
            "marker",
        ):
            with self.subTest(retained=retained):
                self.assertIn(retained, routing)
        marker_write = (
            "printf '%s\\n%s\\n%s\\n%s\\n' \"$reviewed_diff_sha256\" \"$reviewed_at\" \\\n"
            "  'tier: fast' \"policy: $policy_sha\" > \"$commit_marker\""
        )
        self.assertIn(marker_write, COMMIT_SKILL)
        self.assertIn("if len(lines) not in (2, 3, 4):", COMMIT_SKILL)
        self.assertIn('lines[2] != "tier: fast"', COMMIT_SKILL)
        self.assertIn(r'r"policy: (?:[0-9a-f]{40}|[0-9a-f]{64})"', COMMIT_SKILL)
        self.assertIn("duplicated/combined/reordered annotation", COMMIT_SKILL)

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
            "'skip: user-directed' > \"$commit_marker\""
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
        self.assertIn("exact two-line standard/hard PASS marker", COMMIT_SKILL)
        self.assertIn("exact three-line user-skip marker", COMMIT_SKILL)
        self.assertIn("exact four-line fast marker", COMMIT_SKILL)
        self.assertIn("exact four-line fast marker younger than 30 minutes", COMMIT_SKILL)
        self.assertIn("set -o pipefail", COMMIT_SKILL)
        self.assertIn('if ! current_hash="$(git diff --cached | shasum -a 256', COMMIT_SKILL)
        self.assertIn("forge: could not hash staged diff — commit blocked", COMMIT_SKILL)
        self.assertIn("failed to consume commit authorization marker", COMMIT_SKILL)
        self.assertIn('rm -f "$commit_marker" || {', COMMIT_SKILL)
        self.assertNotIn(".forge/tmp/commit-authorized", COMMIT_SKILL)
        self.assertIn("lock-release failure takes precedence", COMMIT_SKILL)
        release_call = "\nrelease_commit_gate\nrelease_status=$?\n"
        clear_traps = "\ntrap - EXIT HUP INT TERM\n"
        self.assertLess(COMMIT_SKILL.index(release_call), COMMIT_SKILL.index(clear_traps))
        for condition in ("missing", "malformed", "stale"):
            self.assertIn(condition, COMMIT_SKILL)

    def test_decision_events_follow_the_primary_outcome_and_remain_advisory(self) -> None:
        commit = COMMIT_SKILL.index('git commit -m "$commit_message"')
        release = COMMIT_SKILL.index("\nrelease_commit_gate\nrelease_status=$?\n")
        gate_event = COMMIT_SKILL.index("--event gate_commit")
        fast_event = COMMIT_SKILL.index("--event fast_allowed")
        release_failure = COMMIT_SKILL.index(
            'if [ "$release_status" -ne 0 ]; then\n    exit "$release_status"',
            fast_event,
        )
        self.assertLess(commit, release)
        self.assertLess(release, gate_event)
        self.assertLess(gate_event, fast_event)
        self.assertLess(fast_event, release_failure)
        self.assertIn("--surface /forge:commit || :", COMMIT_SKILL)
        self.assertIn("event `review_block`", COMMIT_SKILL)
        self.assertIn("`user_skip` event", COMMIT_SKILL)
        self.assertIn("First deliver acceptance of the skip as the primary outcome", COMMIT_SKILL)
        self.assertIn("registers an in-flight writer but acquires no lock", COMMIT_SKILL)
        self.assertIn("os.O_WRONLY | os.O_APPEND | os.O_CREAT", COMMIT_SKILL)
        self.assertIn("makes exactly one `os.write()`", COMMIT_SKILL)
        self.assertIn("treats a short write as a failure", COMMIT_SKILL)
        self.assertIn("gates only drift-check's prune read-and-replace", COMMIT_SKILL)
        self.assertIn("does not extend to NFS/SMB network filesystems", COMMIT_SKILL)
        self.assertIn("Windows\nis out of scope", COMMIT_SKILL)
        self.assertIn("deduplicates both events by `(event, candidate)`", COMMIT_SKILL)

    def test_forbidden_legacy_and_blanket_staging_forms_are_absent(self) -> None:
        shipped = TEMPLATE + COMMIT_SKILL
        legacy_name = "open" + "code"
        self.assertNotIn(legacy_name, shipped.lower())
        self.assertNotIn(str(Path.home()), shipped)
        self.assertNotRegex(COMMIT_SKILL, r"git add\s+(?:-A|\.(?:\s|$))")


if __name__ == "__main__":
    unittest.main()
