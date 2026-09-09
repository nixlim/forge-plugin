"""Contract tests for the forge project template and commit skill."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import re
import unittest
from pathlib import Path

from tests._cli_loader import package_module

ROOT = Path(__file__).resolve().parents[1]
POLICY = package_module("policy")
TEMPLATE = (ROOT / "system" / "template" / "forge-project.md").read_text(
    encoding="utf-8"
)
ROOT_PROJECT = (ROOT / "forge-project.md").read_text(encoding="utf-8")
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
    "reviewer-facing-eval-triggers",
    "guard-denied-commands",
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

REVIEWER_EVAL_TRIGGER_TABLE = POLICY.REVIEWER_EVAL_TRIGGER_TABLE.rstrip("\n")


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


def document_region_body(document: str, name: str) -> str:
    match = re.search(
        rf"<!-- FORGE:REGION {re.escape(name)} BEGIN -->(.*?)"
        rf"<!-- FORGE:REGION {re.escape(name)} END -->",
        document,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing region {name}")
    return match.group(1)


class ForgeProjectTemplateTests(unittest.TestCase):
    def test_canonical_trigger_table_pins_spec_template_and_root_bytes(self) -> None:
        specification = (ROOT / "docs/specs/forge-plugin-spec.md").read_bytes()
        specification_match = re.search(
            rb"The `reviewer-facing-eval-triggers` region is the sole maintained "
            rb"reviewer-facing trigger path list and contains exactly these ordered rows:\n\n"
            rb"(\| control \| path patterns \|\n"
            rb"\|---\|---\|\n"
            rb"(?:\| [^\n]+ \|\n)+)",
            specification,
        )
        self.assertIsNotNone(specification_match)
        canonical = POLICY.REVIEWER_EVAL_TRIGGER_TABLE.encode("utf-8")
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            "3d1be7b789a8ee5cc7b5f65ac7f77a5ce3622fe0214a09650c85424c91147d93",
        )
        self.assertEqual(specification_match.group(1), canonical)
        for label, path in (
            ("template", ROOT / "system/template/forge-project.md"),
            ("root", ROOT / "forge-project.md"),
        ):
            with self.subTest(document=label):
                document = path.read_bytes()
                marker = b"<!-- FORGE:REGION reviewer-facing-eval-triggers BEGIN -->\n"
                end = b"<!-- FORGE:REGION reviewer-facing-eval-triggers END -->"
                body = document.split(marker, 1)[1].split(end, 1)[0]
                self.assertEqual(body, canonical)
                self.assertEqual(
                    hashlib.sha256(body).hexdigest(),
                    "3d1be7b789a8ee5cc7b5f65ac7f77a5ce3622fe0214a09650c85424c91147d93",
                )

    def test_sixteen_regions_are_complete_and_in_contract_order(self) -> None:
        begins = re.findall(r"<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->", TEMPLATE)
        ends = re.findall(r"<!-- FORGE:REGION ([a-z0-9-]+) END -->", TEMPLATE)
        self.assertEqual(begins, REGIONS)
        self.assertEqual(ends, REGIONS)
        for name in REGIONS:
            with self.subTest(region=name):
                body = region_body(name)
                if name == "reviewer-facing-eval-triggers":
                    self.assertNotIn("<!-- forge-init:", body)
                    self.assertEqual(body.strip(), REVIEWER_EVAL_TRIGGER_TABLE)
                else:
                    self.assertIn("<!-- forge-init:", body)
        self.assertEqual(
            document_region_body(
                ROOT_PROJECT, "reviewer-facing-eval-triggers"
            ).strip(),
            REVIEWER_EVAL_TRIGGER_TABLE,
        )
        self.assertEqual(
            document_region_body(ROOT_PROJECT, "guard-denied-commands").strip(),
            "No additional denied commands configured.",
        )
        guard_template = document_region_body(TEMPLATE, "guard-denied-commands")
        self.assertIn("<!-- forge-init:", guard_template)
        self.assertIn(
            "No additional denied commands configured.",
            guard_template,
        )

    def test_revision_two_region_defaults_are_conservative_and_complete(self) -> None:
        self.assertIn("fail closed", region_body("invariants"))
        self.assertIn("No mutation-testing policy is configured.", region_body("mutation-testing"))
        self.assertIn(
            "| fast | docs/**, .forge/history/**, .forge/evals/candidates/**, "
            "@formatting-only |",
            region_body("risk-tiers"),
        )
        self.assertIn(
            "| `docs` | `*.md`, `docs/**`, `.forge/history/**`, "
            "`.forge/evals/candidates/**` |",
            region_body("file-categories"),
        )
        self.assertIn("| docs |", region_body("risk-tiers"))

        for label, project in (("root", ROOT_PROJECT), ("template", TEMPLATE)):
            with self.subTest(project=label):
                self.assertRegex(
                    project,
                    r"(?m)^\| `docs` \|[^\n]*`\.forge/evals/candidates/\*\*` \|$",
                )
                self.assertRegex(
                    project,
                    r"(?m)^\| `control` \|[^\n]*`\.forge/evals/tasks/\*\*`[^\n]*\|$",
                )
                self.assertRegex(
                    project,
                    r"(?m)^\| fast \|[^\n]*\.forge/evals/candidates/\*\*[^\n]*\|$",
                )
                self.assertNotIn("`.forge/evals/**`", project)

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
            "learn",
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
            ".forge/evals/tasks/**",
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
        self.assertIn("`.forge/evals/candidates/**` is the sole\n   eval-path exception", COMMIT_SKILL)
        self.assertIn("advisory/docs-class and never as `control`", COMMIT_SKILL)
        self.assertIn("`.forge/evals/tasks/**`, or creating or changing its baseline", COMMIT_SKILL)
        self.assertNotIn("`.forge/evals/**`", COMMIT_SKILL)

    def test_standard_review_delegates_to_committed_prompt_construction(self) -> None:
        step_four = COMMIT_SKILL.split("## Step 4 —", 1)[1].split("## Step 5 —", 1)[0]
        controls = (
            "[`orchestrate`](../orchestrate/SKILL.md#forge-isolation-and-prompt-construction)",
            "mandatory FR-037 plugin role template",
            "committed `agent-project-context`",
            "committed `.forge/history/gotchas.md` prefix",
            "no task-assignment review payload beyond",
        )
        for control in controls:
            self.assertEqual(step_four.count(control), 1)

        positions = [step_four.index(control) for control in controls[1:]]
        self.assertEqual(positions, sorted(positions))

        for control in controls:
            with self.subTest(disabled=control):
                mutated = step_four.replace(control, "DISABLED_CONTROL", 1)
                with self.assertRaises(AssertionError):
                    for required in controls:
                        self.assertEqual(mutated.count(required), 1)

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
        self.assertIn("1200-second timeout", step_two)

    def test_review_loop_and_candidate_marker_contract(self) -> None:
        self.assertNotIn("git diff --cached", COMMIT_SKILL)
        self.assertNotIn("shasum -a 256", COMMIT_SKILL)
        self.assertIn("from forge_cli import candidate", COMMIT_SKILL)
        self.assertIn("candidate.snapshot(", COMMIT_SKILL)
        self.assertIn("candidate.observe_index(context)", COMMIT_SKILL)
        self.assertIn("candidate.render_marker(", COMMIT_SKILL)
        self.assertIn("candidate.marker_timestamp_for_cleanup(raw)", COMMIT_SKILL)
        self.assertIn("at most 8 review", COMMIT_SKILL)
        self.assertIn("requires explicit user approval", COMMIT_SKILL)
        self.assertIn("skip: user-directed", COMMIT_SKILL)
        self.assertIn(
            '`commit_marker="$forge_main_root/.forge/tmp/authorized/$authorization_id"`',
            COMMIT_SKILL,
        )
        self.assertIn("review_diff_sha256", COMMIT_SKILL)
        self.assertIn("review digest remains evidence", COMMIT_SKILL)
        self.assertIn("owner-controlled mode-0600 artifact", COMMIT_SKILL)
        self.assertIn("re-run the affected Step 2 validations", COMMIT_SKILL)
        self.assertIn("restart Step 4", COMMIT_SKILL)
        invalidation = "authorization_id=''\ncandidate_object_format=''\ncandidate_tree_oid=''"
        self.assertLess(COMMIT_SKILL.index(invalidation), COMMIT_SKILL.index("## Step 1 —"))
        control_wait = "then wait for explicit\napproval naming that authorization ID"
        pass_write = "raw = candidate.render_marker("
        self.assertLess(COMMIT_SKILL.index(invalidation), COMMIT_SKILL.index(control_wait))
        self.assertLess(COMMIT_SKILL.index(control_wait), COMMIT_SKILL.index(pass_write))
        self.assertIn("leaves no authorization marker behind", COMMIT_SKILL)
        self.assertIn("later Step 4 attempts refuse to consume them while fresh", COMMIT_SKILL)
        self.assertIn('quarantine_latch="${commit_marker}.quarantine"', COMMIT_SKILL)
        self.assertIn("retained marker is not a\nreusable capability", COMMIT_SKILL)

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
        self.assertIn("exact `authorization_id`", sensor)
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
        self.assertIn("exact\n`$authorization_id`", reviewer)
        self.assertIn("surface `/forge:commit`", reviewer)
        for severity in ("`CRITICAL`", "`MAJOR`", "`MINOR`"):
            self.assertIn(severity, reviewer)
        self.assertIn("no findings emits no finding event", reviewer)
        self.assertIn("after the verdict and findings are\npreserved", reviewer)
        self.assertIn("never changes the verdict, iteration, or exit\nstatus", reviewer)

    def test_gate_time_tiering_is_exact_promote_only_and_non_narrowable(self) -> None:
        for binding in (
            "FORGE_CANDIDATE_SCHEMA=forge-commit-candidate/2",
            'FORGE_CANDIDATE_AUTHORIZATION_ID="$authorization_id"',
            'FORGE_CANDIDATE_OBJECT_FORMAT="$candidate_object_format"',
            'FORGE_CANDIDATE_TREE_OID="$candidate_tree_oid"',
            'FORGE_CANDIDATE_BASE_COMMIT_OID="$candidate_base_commit_oid"',
        ):
            self.assertIn(binding, COMMIT_SKILL)
        self.assertIn('python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/risk_tier.py"', COMMIT_SKILL)
        self.assertIn('--repo "$PWD" --policy-sha "$policy_sha" --staged', COMMIT_SKILL)
        self.assertIn('declared_tier="${declared_tier:-}"', COMMIT_SKILL)
        self.assertIn('declared_args=()', COMMIT_SKILL)
        self.assertIn('"${declared_args[@]}"', COMMIT_SKILL)
        self.assertIn('fast|standard|hard)', COMMIT_SKILL)
        self.assertIn("metadata, evidence = map(json.loads, lines)", COMMIT_SKILL)
        self.assertIn("observed_paths != expected_paths", COMMIT_SKILL)
        self.assertIn('evidence.get("policy_sha") != sys.argv[1]', COMMIT_SKILL)
        self.assertIn('echo "forge: invalid risk-tier evidence"', COMMIT_SKILL)
        classifier = COMMIT_SKILL.split("Before selecting a reviewer", 1)[1].split(
            "Route the review as follows:", 1
        )[0]
        for evidence in (
            "exact snapshot\npath list",
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

    def test_shared_marker_renderer_and_parser_pin_exact_v2_bytes(self) -> None:
        candidate = package_module("candidate")
        tree_oid = "1" * 40
        authorization_id = candidate.authorization_id("sha1", tree_oid)
        observation = candidate.CandidateObservation(
            object_format="sha1",
            tree_oid=tree_oid,
            authorization_id=authorization_id,
        )
        authorized_at = "2026-09-07T12:00:00Z"
        now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
        prefix = (
            b"format: forge-commit-candidate/2\n"
            + f"candidate: {authorization_id}\n".encode("ascii")
            + f"tree: sha1:{tree_oid}\n".encode("ascii")
            + b"authorized-at: 2026-09-07T12:00:00Z\n"
        )
        vectors = (
            (candidate.render_marker(observation, authorized_at), prefix),
            (
                candidate.render_marker(observation, authorized_at, skip=True),
                prefix + b"skip: user-directed\n",
            ),
            (
                candidate.render_marker(
                    observation, authorized_at, fast_policy="2" * 40
                ),
                prefix + b"tier: fast\npolicy: " + b"2" * 40 + b"\n",
            ),
        )
        for rendered, expected in vectors:
            with self.subTest(lines=rendered.count(b"\n")):
                self.assertEqual(rendered, expected)
                parsed, reason = candidate.parse_marker(
                    rendered,
                    filename=authorization_id,
                    observation=observation,
                    now=now,
                )
                self.assertIsNotNone(parsed)
                self.assertIsNone(reason)
        for malformed in (
            prefix[:-1],
            prefix + b"\n",
            prefix.replace(b"\n", b"\r\n"),
            prefix + b"skip: user-directed\ntier: fast\n",
        ):
            with self.subTest(malformed=malformed):
                parsed, reason = candidate.parse_marker(
                    malformed,
                    filename=authorization_id,
                    observation=observation,
                    now=now,
                )
                self.assertIsNone(parsed)
                self.assertEqual(reason, "marker malformed")

    def test_skill_contains_only_the_three_exact_v2_marker_fences(self) -> None:
        standard = (
            "format: forge-commit-candidate/2\n"
            "candidate: <64-lowercase-hex authorization-id>\n"
            "tree: <sha1|sha256>:<full matching tree OID>\n"
            "authorized-at: <UTC ISO-8601>"
        )
        expected = (
            standard,
            standard + "\ntier: fast\npolicy: <full commit OID>",
            standard + "\nskip: user-directed",
        )
        observed = tuple(
            block
            for block in re.findall(r"```text\n(.*?)\n```", COMMIT_SKILL, re.DOTALL)
            if block.startswith("format: forge-commit-candidate/")
        )
        self.assertEqual(observed, expected)
        quarantine = (
            "format: forge-commit-candidate-quarantine/1\n"
            "candidate: <64-lowercase-hex authorization-id>\n"
            "produced: <full matching Git OID|none>\n"
            "reason: produced-commit-mismatch"
        )
        self.assertEqual(COMMIT_SKILL.count(f"```text\n{quarantine}\n```"), 1)

    def test_fast_skips_only_review_and_writes_exact_six_line_marker(self) -> None:
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
            "index-tree re-observation",
            "guard recomputation",
            "produced-commit\n  verification",
            "marker",
        ):
            with self.subTest(retained=retained):
                self.assertIn(retained, routing)
        marker = (
            "format: forge-commit-candidate/2\n"
            "candidate: <64-lowercase-hex authorization-id>\n"
            "tree: <sha1|sha256>:<full matching tree OID>\n"
            "authorized-at: <UTC ISO-8601>\n"
            "tier: fast\n"
            "policy: <full commit OID>"
        )
        self.assertIn(marker, COMMIT_SKILL)
        self.assertIn("candidate.render_marker(", COMMIT_SKILL)
        self.assertIn("candidate.parse_marker(", COMMIT_SKILL)
        self.assertIn('fast_policy=sys.argv[7] if sys.argv[6] == "fast" else None', COMMIT_SKILL)
        self.assertIn("exact six-line fast marker", COMMIT_SKILL)
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
        self.assertIn(
            "A skip directive never supplies that approval",
            " ".join(COMMIT_SKILL.split()),
        )
        self.assertIn("control-class commits are never autonomous", COMMIT_SKILL)
        skip_approval = "Wait for explicit\nuser approval naming that authorization ID"
        skip_write = "candidate.render_marker(observation, sys.argv[5], skip=True)"
        self.assertLess(COMMIT_SKILL.index(skip_approval), COMMIT_SKILL.index(skip_write))

    def test_step5_script_sequence_and_journal_rules_are_explicit(self) -> None:
        step5 = COMMIT_SKILL.split("## Step 5 — Prepare, Commit, Cleanup", 1)[1].split(
            "## User-Directed Skips", 1
        )[0]
        prepare = step5.split("### Tool call 1 — Prepare", 1)[1].split(
            "### Tool call 2 — Commit", 1
        )[0]
        commit = step5.split("### Tool call 2 — Commit", 1)[1].split(
            "### Tool call 3 — Cleanup", 1
        )[0]
        cleanup = step5.split("### Tool call 3 — Cleanup", 1)[1]
        halt = 'bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh" commit'
        acquire = 'bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/acquire-commit-lock.sh" || exit 1'
        in_lock_observation = "observed = candidate.observe_index(context)"
        standalone = commit.split("```bash", 1)[1].split("```", 1)[0].strip()
        positions = [prepare.index(value) for value in (halt, acquire, in_lock_observation)]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(
            standalone,
            "git commit --cleanup=verbatim -m <safely shell-quoted literal>",
        )
        self.assertNotIn('git commit -m "$commit_message"', COMMIT_SKILL)
        self.assertLess(prepare.index("trap 'cleanup_prepare_failure"), positions[0])
        self.assertGreater(prepare.index("prepare_cleanup_armed=0"), positions[-1])
        self.assertIn("disarm it only after every preparation check passes", prepare)
        self.assertIn("from forge_cli import candidate", prepare)
        self.assertIn("candidate.parse_marker(", prepare)
        self.assertIn("expected_base_commit_oid=", prepare)
        self.assertIn(
            'if [ "$pre_commit_head" != "$expected_base_commit_oid" ]; then',
            prepare,
        )
        self.assertIn(
            'FORGE_CANDIDATE_BASE_COMMIT_OID="$expected_base_commit_oid"',
            prepare,
        )
        self.assertIn(
            'for name in ("risk-tiers", "trigger-paths", "file-categories"):',
            prepare,
        )
        self.assertIn("--declared-tier fast --require-effective fast", prepare)
        self.assertIn("fast-path policy drift", prepare)
        self.assertIn("fast-path eligibility drift", prepare)
        self.assertIn("forge: prepared commit base %s", prepare)
        self.assertIn(
            'bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/release-commit-lock.sh" '
            "|| release_status=$?",
            cleanup,
        )
        self.assertIn('rm -f "$commit_marker" || {', cleanup)
        self.assertIn('if [ "$produced_mismatch" -eq 1 ]; then', cleanup)
        quarantine = cleanup.index('python3 - "$quarantine_latch"')
        release = cleanup.index("release-commit-lock.sh")
        self.assertLess(quarantine, release)
        self.assertIn("format: forge-commit-candidate-quarantine/1", cleanup)
        self.assertIn("reason: produced-commit-mismatch", cleanup)
        self.assertIn("os.O_WRONLY | os.O_CREAT | os.O_EXCL", cleanup)
        self.assertLess(
            cleanup.index('if [ "$produced_mismatch" -eq 1 ]; then', release),
            cleanup.index('rm -f "$commit_marker" || {'),
        )
        self.assertIn("hook allow or denial", step5)
        self.assertIn("Git success or failure", step5)
        self.assertIn("must never be retried", step5)
        self.assertIn('observed_head="$(git rev-parse HEAD', cleanup)
        self.assertIn("candidate.read_commit_object(context, observed_head)", cleanup)
        self.assertIn("produced.tree_headers != (expected_tree,)", cleanup)
        self.assertIn("produced.parent_headers != (reviewed_base,)", cleanup)
        self.assertIn("hashlib.sha256(produced.message).hexdigest()", cleanup)
        self.assertIn("commit_succeeded=1", cleanup)
        self.assertIn("commit outcome ambiguous — inspect HEAD before retrying", cleanup)
        self.assertIn(
            "forge: produced commit does not match authorized candidate — chain frozen; commit left untouched",
            cleanup,
        )
        self.assertIn("Never hold the lock across Step 4", COMMIT_SKILL)
        self.assertIn("Never infer the latest run", COMMIT_SKILL)
        self.assertIn("beginning exactly `gate-1: ` for project-test", COMMIT_SKILL)
        self.assertIn("beginning exactly `gate-2: ` for", COMMIT_SKILL)
        self.assertIn("criterion must be exactly `gate-3: review-final verdict`", COMMIT_SKILL)
        self.assertIn('`result: "failed"`', COMMIT_SKILL)
        self.assertIn("exact four-line standard/hard PASS marker", COMMIT_SKILL)
        self.assertIn("exact five-line user-skip marker", COMMIT_SKILL)
        self.assertIn("exact six-line fast marker younger than 30 minutes", COMMIT_SKILL)
        self.assertIn("candidate.parse_marker(", COMMIT_SKILL)
        self.assertNotIn("git diff --cached", COMMIT_SKILL)
        self.assertNotIn("shasum -a 256", COMMIT_SKILL)
        self.assertIn("failed to consume commit authorization marker", COMMIT_SKILL)
        self.assertIn('rm -f "$commit_marker" || {', COMMIT_SKILL)
        self.assertNotIn(".forge/tmp/commit-authorized", COMMIT_SKILL)
        self.assertIn("lock-release failure takes precedence", COMMIT_SKILL)
        self.assertLess(
            cleanup.index("release-commit-lock.sh"),
            cleanup.index('if [ "$release_status" -ne 0 ]'),
        )
        for condition in ("missing", "malformed", "stale"):
            self.assertIn(condition, COMMIT_SKILL)

    def test_decision_events_follow_the_primary_outcome_and_remain_advisory(self) -> None:
        step5 = COMMIT_SKILL.split("## Step 5 — Prepare, Commit, Cleanup", 1)[1].split(
            "## User-Directed Skips", 1
        )[0]
        commit = step5.index(
            "git commit --cleanup=verbatim -m <safely shell-quoted literal>"
        )
        cleanup_heading = step5.index("### Tool call 3 — Cleanup")
        release = step5.index("release-commit-lock.sh", cleanup_heading)
        marker_cleanup = step5.index('rm -f "$commit_marker"', cleanup_heading)
        gate_event = step5.index("--event gate_commit")
        fast_event = step5.index("--event fast_allowed")
        release_failure = step5.index(
            'if [ "$release_status" -ne 0 ]; then\n    exit "$release_status"',
            fast_event,
        )
        self.assertLess(commit, release)
        self.assertLess(release, marker_cleanup)
        self.assertLess(marker_cleanup, gate_event)
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
