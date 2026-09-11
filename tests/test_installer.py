"""Integration and payload contract tests for the Forge installer."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "forge" / "install.sh"
DCG_CONFIGURATOR = ROOT / "scripts" / "forge" / "configure-dcg.sh"
TEMPLATE = ROOT / "system" / "template" / "forge-project.md"
INIT_SKILL = (ROOT / "skills" / "init" / "SKILL.md").read_text(encoding="utf-8")
UPSTREAM_RULES_FIXTURE = ROOT / "tests" / "fixtures" / "upstream-forge.rules"
VENDORED_UPSTREAM_RULES = ROOT / ".upstream/forge/system/template/.codex/rules/forge.rules"
BEGIN = "<!-- FORGE:BEGIN -->"
END = "<!-- FORGE:END -->"
REGION_ORDER = (
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
)
STACK_FENCE_ERROR = (
    "forge: stack-validations region present but contains no fenced shell cell — "
    "write one fenced ```bash or ```sh cell per stack category (see /forge:init)"
)


def region_body(document: str, name: str) -> str:
    match = re.search(
        rf"<!-- FORGE:REGION {re.escape(name)} BEGIN -->(.*?)"
        rf"<!-- FORGE:REGION {re.escape(name)} END -->",
        document,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing region {name}")
    return match.group(1)


def replace_region(document: str, name: str, body: str) -> str:
    pattern = re.compile(
        rf"(<!-- FORGE:REGION {re.escape(name)} BEGIN -->).*?"
        rf"(<!-- FORGE:REGION {re.escape(name)} END -->)",
        flags=re.DOTALL,
    )
    replaced, count = pattern.subn(rf"\g<1>{body}\g<2>", document)
    if count != 1:
        raise AssertionError(f"expected one {name} region, found {count}")
    return replaced


def toml_string(document: str, key: str) -> str:
    match = re.search(
        rf'^{re.escape(key)}\s*=\s*"([^"]*)"\s*$',
        document,
        flags=re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"missing TOML string key {key}")
    return match.group(1)


@dataclass(frozen=True)
class InitApprovalTrace:
    phase1_recorded: tuple[str, ...]
    phase5_reported: tuple[str, ...]
    phase6_approval: tuple[str, ...]


def init_phase(document: str, number: int) -> str:
    match = re.search(
        rf"^## Phase {number}\b.*?(?=^## Phase [0-6]\b|\Z)",
        document,
        flags=re.DOTALL | re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"missing Phase {number}")
    return match.group(0)


def init_policy_self_check_cell(skill: str = INIT_SKILL) -> str:
    phase3 = init_phase(skill, 3)
    anchor = "Before any policy command or Phase 4 work, run this parser-only self-check"
    _before, separator, after = phase3.partition(anchor)
    if not separator:
        raise AssertionError("init policy self-check is missing or misplaced")
    match = re.search(r"```bash\n(.*?)\n```", after, flags=re.DOTALL)
    if match is None:
        raise AssertionError("init policy self-check has no executable cell")
    return match.group(1)


def run_init_policy_self_check(
    repository: Path, *, cell: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", cell or init_policy_self_check_cell()],
        cwd=repository,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)},
        check=False,
        capture_output=True,
        text=True,
    )


def canonical_reviewer_eval_table() -> str:
    """Read the complete canonical trigger table from specification authority."""
    specification = (ROOT / "docs/specs/forge-plugin-spec.md").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"The `reviewer-facing-eval-triggers` region is the sole maintained "
        r"reviewer-facing trigger path list and contains exactly these ordered rows:\n\n"
        r"(\| control \| path patterns \|\n"
        r"\|---\|---\|\n"
        r"(?:\| [^\n]+ \|\n)+)",
        specification,
    )
    if match is None:
        raise AssertionError("specification lacks the canonical reviewer trigger table")
    return match.group(1)


def canonical_reviewer_eval_patterns() -> tuple[str, ...]:
    """Read the complete canonical trigger inventory from specification authority."""

    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in canonical_reviewer_eval_table().splitlines()[2:]
    ]
    patterns = tuple(
        pattern.strip()
        for row in rows
        for pattern in row[1].split(",")
        if pattern.strip()
    )
    if len(rows) != 6 or not patterns:
        raise AssertionError("canonical reviewer trigger table is incomplete")
    return patterns


def assert_commit_fresh_eval_source_contract(skill: str) -> None:
    """Compile the Step 4 source-of-truth prose into a fail-closed contract."""

    step4 = skill[skill.index("## Step 4"):skill.index("## Step 5")]
    match = re.search(
        r"After the immutable artifact passes the secret scan,.*?"
        r"(?=Before selecting a reviewer,)",
        step4,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("fresh-evaluation procedure is not ordered before review")
    procedure = " ".join(match.group(0).split())
    for required in (
        (
            "Supply only the pinned `policy_sha` policy bytes and the exact "
            "bytewise-sorted `snapshot.paths`"
        ),
        (
            "never use target arguments, `git status`, working-tree paths, or a "
            "locally duplicated pattern list"
        ),
        (
            "A missing or malformed authenticated `reviewer-facing-eval-triggers` "
            "region blocks every control-class chain"
        ),
        (
            "report the matched control row names sourced from that result, not a "
            "restated list of their path patterns"
        ),
    ):
        if required not in procedure:
            raise AssertionError(f"fresh-evaluation source contract missing: {required}")
    for duplicated_pattern in canonical_reviewer_eval_patterns():
        if duplicated_pattern in procedure:
            raise AssertionError(
                f"fresh-evaluation procedure duplicates a trigger: {duplicated_pattern}"
            )


def simulate_init_approval_reporting(
    skill: str,
    *,
    dcg_result: str,
    plugin_ref: str,
) -> InitApprovalTrace:
    """Compile the skill's cross-phase reporting contract and drive both branches."""

    phase1 = init_phase(skill, 1)
    phase5 = init_phase(skill, 5)
    phase6 = init_phase(skill, 6)
    dcg_failure = "forge: dcg allowlist update failed"
    warning_template = (
        "forge: warning — plugin_ref is dirty and installation is not reproducible "
        "from a commit: <ref>"
    )

    if not re.search(
        r"Retain the helper's exact recorded result for the\s+Phase 6 approval summary",
        phase1,
    ):
        raise AssertionError("Phase 1 does not carry the exact dcg result to Phase 6")
    if not re.search(
        rf"non-fatal\s+`{re.escape(dcg_failure)}` result must remain visible there",
        phase1,
    ):
        raise AssertionError("Phase 1 does not preserve a non-fatal dcg failure")
    if not re.search(
        rf"the exact Phase 1 dcg integration result, including\s+`{re.escape(dcg_failure)}` "
        r"verbatim",
        phase6,
    ):
        raise AssertionError("Phase 6 does not consume the exact Phase 1 dcg result")

    if not re.search(
        r"If\s+the derived ref ends in `-dirty`, retain that exact ref in the manifest "
        r"and warn exactly",
        phase5,
    ):
        raise AssertionError("Phase 5 does not condition the warning on a dirty ref")
    if f"`{warning_template}`" not in phase5:
        raise AssertionError("Phase 5 does not define the exact dirty-ref warning")
    if not re.search(
        r"This warning does not block initialization, but it must also be repeated in "
        r"the Phase 6 approval\s+summary",
        phase5,
    ):
        raise AssertionError("Phase 5 does not carry the dirty-ref warning to Phase 6")
    if not re.search(
        r"any dirty\s+`plugin_ref` reproducibility warning from Phase 5",
        phase6,
    ):
        raise AssertionError("Phase 6 does not consume the Phase 5 dirty-ref warning")

    phase5_reported: list[str] = []
    if plugin_ref.endswith("-dirty"):
        phase5_reported.append(warning_template.replace("<ref>", plugin_ref))
    return InitApprovalTrace(
        phase1_recorded=(dcg_result,),
        phase5_reported=tuple(phase5_reported),
        phase6_approval=(dcg_result, *phase5_reported),
    )


class InstallerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-installer-")
        self.addCleanup(self.temp_dir.cleanup)
        self.scratch = Path(self.temp_dir.name)
        self.repo = self.scratch / "target repo"
        self.plugin = self.scratch / "plugin payload"
        self.repo.mkdir()
        self.plugin.mkdir()
        subprocess.run(
            ["git", "init", "--quiet"],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )
        shutil.copytree(ROOT / "system", self.plugin / "system")

    def install(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(INSTALLER), str(self.plugin)],
            cwd=self.repo,
            env={**os.environ, "CLAUDE_PLUGIN_ROOT": "ignored-when-argument-is-present"},
            check=False,
            capture_output=True,
            text=True,
        )

    def read(self, relative: str) -> str:
        return (self.repo / relative).read_text(encoding="utf-8")

    def test_fresh_install_writes_complete_fail_closed_scaffold(self) -> None:
        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        project = self.read("forge-project.md")
        agents = self.read("AGENTS.md")
        self.assertEqual(
            tuple(
                re.findall(
                    r"<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->",
                    project,
                )
            ),
            REGION_ORDER,
        )
        self.assertNotIn("{{FORGE_INSTALL_DATE}}", project)
        self.assertRegex(project, r"Install date: `\d{4}-\d{2}-\d{2}`")
        self.assertIn("forge-init:", project)
        self.assertEqual(
            region_body(project, "reviewer-facing-eval-triggers").strip(),
            canonical_reviewer_eval_table().strip(),
        )
        self.assertNotIn(
            "forge-init:", region_body(project, "reviewer-facing-eval-triggers")
        )
        guard_body = region_body(project, "guard-denied-commands")
        self.assertIn("forge-init:", guard_body)
        self.assertIn("No additional denied commands configured.", guard_body)
        sentinel_search = subprocess.run(
            ["grep", "-rln", "forge-init:", "forge-project.md"],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(sentinel_search.returncode, 0)
        self.assertEqual(sentinel_search.stdout.strip(), "forge-project.md")
        self.assertEqual(agents, f"{BEGIN}\n{project}{END}\n")
        self.assertEqual(self.read("CLAUDE.md"), "@forge-project.md\n")

        codex_files = {
            path.relative_to(self.repo).as_posix()
            for path in (self.repo / ".codex").rglob("*")
            if path.is_file()
        }
        self.assertEqual(
            codex_files,
            {
                ".codex/config.toml",
                ".codex/hooks.json",
                ".codex/agents/implementer.toml",
                ".codex/agents/review-cheap.toml",
                ".codex/prompts/implementer.md",
                ".codex/prompts/review-cheap.md",
                ".codex/rules/forge.rules",
            },
        )
        self.assertTrue((self.repo / ".forge/evals/tasks").is_dir())
        self.assertTrue((self.repo / ".forge/history/runs").is_dir())
        self.assertTrue((self.repo / ".forge/history/drift").is_dir())
        self.assertTrue((self.repo / ".forge/history/migrations").is_dir())
        self.assertTrue((self.repo / ".forge/tmp").is_dir())
        self.assertTrue((self.repo / ".forge/tmp/authorized").is_dir())
        self.assertTrue((self.repo / ".forge/tmp/drift").is_dir())
        self.assertTrue((self.repo / ".forge/tmp/decisions").is_dir())
        self.assertEqual(
            self.read(".gitignore"),
            (self.plugin / "system/template/gitignore-block.txt").read_text(),
        )
        self.assertEqual(
            self.read(".gitignore").count("# --- forge agent system --- #"), 1
        )
        history_ignore = subprocess.run(
            ["git", "check-ignore", "-q", "--", ".forge/history/.forge-ignore-check"],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        tmp_ignore = subprocess.run(
            ["git", "check-ignore", "-q", "--", ".forge/tmp/.forge-ignore-check"],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(history_ignore.returncode, 1)
        self.assertEqual(tmp_ignore.returncode, 0)
        self.assertFalse((self.repo / ".forge/history/.forge-ignore-check").exists())
        self.assertFalse((self.repo / ".forge/tmp/.forge-ignore-check").exists())

        gate1 = region_body(project, "gate1-test-command")
        command_match = re.search(r"```bash\n(.*?)\n```", gate1, flags=re.DOTALL)
        self.assertIsNotNone(command_match)
        gate = subprocess.run(
            ["bash", "-c", command_match.group(1)],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(gate.returncode, 1)
        self.assertIn("not configured", gate.stderr)

    def test_reinstall_is_idempotent_and_obeys_both_region_merge_directions(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)

        installed = self.read("forge-project.md")
        filled_body = "\n\n  Keep leading and trailing bytes.  \n\n"
        installed = replace_region(installed, "project-overview", filled_body)
        mutation_absence = (
            "\nNo mutation tool available for python — assertion-quality fallback only.\n"
        )
        installed = replace_region(installed, "mutation-testing", mutation_absence)
        empty_triggers = "\nNo trigger paths configured.\n"
        installed = replace_region(installed, "trigger-paths", empty_triggers)
        filled_guard_denylist = (
            "\n| pattern | reason |\n"
            "|---|---|\n"
            "| git push --force | operator approval is required |\n"
        )
        installed = replace_region(
            installed,
            "guard-denied-commands",
            filled_guard_denylist,
        )
        (self.repo / "forge-project.md").write_text(installed, encoding="utf-8")

        fresh_path = self.plugin / "system/template/forge-project.md"
        fresh = fresh_path.read_text(encoding="utf-8")
        fresh = fresh.replace(
            "# Forge Plugin Project Instructions",
            "# Forge Plugin Project Instructions (refreshed scaffold)",
            1,
        )
        fresh = replace_region(
            fresh,
            "project-overview",
            "\nTHIS FRESH FILLED BODY MUST LOSE\n",
        )
        refreshed_unfilled = (
            "\n<!-- forge-init: refreshed sentinel proves the template wins -->\n"
            "No changelog gate is configured for this repository.\n"
        )
        fresh = replace_region(fresh, "changelog-policy", refreshed_unfilled)
        fresh_path.write_text(fresh, encoding="utf-8")

        fixture = self.repo / ".forge/evals/tasks/already-here.md"
        baseline = self.repo / ".forge/evals/tasks/already-here.result"
        fixture.write_bytes(b"fixture bytes\x00stay\n")
        baseline.write_bytes(b"PASS\nexisting baseline\n")
        second = self.install()

        self.assertEqual(second.returncode, 0, second.stderr)
        merged = self.read("forge-project.md")
        self.assertIn("# Forge Plugin Project Instructions (refreshed scaffold)", merged)
        self.assertEqual(region_body(merged, "project-overview"), filled_body)
        self.assertEqual(
            region_body(merged, "changelog-policy"), refreshed_unfilled
        )
        self.assertEqual(region_body(merged, "mutation-testing"), mutation_absence)
        self.assertEqual(region_body(merged, "trigger-paths"), empty_triggers)
        self.assertEqual(
            region_body(merged, "guard-denied-commands"),
            filled_guard_denylist,
        )
        self.assertEqual(fixture.read_bytes(), b"fixture bytes\x00stay\n")
        self.assertEqual(baseline.read_bytes(), b"PASS\nexisting baseline\n")
        self.assertEqual(self.read("AGENTS.md").count(BEGIN), 1)
        self.assertEqual(self.read("AGENTS.md").count(END), 1)
        self.assertEqual(self.read("CLAUDE.md").splitlines().count("@forge-project.md"), 1)
        self.assertEqual(
            self.read(".gitignore").count("# --- forge agent system --- #"), 1
        )

    def test_reinstall_refreshes_only_the_fixed_dependency_manifest_block(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)

        project = self.read("forge-project.md")
        canonical_risk = region_body(project, "risk-tiers")
        fixed_match = re.search(
            r"<!-- FORGE:DEPENDENCY-MANIFEST-PATHS BEGIN -->.*?"
            r"<!-- FORGE:DEPENDENCY-MANIFEST-PATHS END -->",
            canonical_risk,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(fixed_match)
        fixed_block = fixed_match.group(0)
        owner_prefix = "\nowner risk policy prefix  \n"
        owner_suffix = "\n\towner risk policy suffix\n"
        altered_block = fixed_block.replace("package.json", "owner-only.lock", 1)
        filled_risk = owner_prefix + altered_block + owner_suffix
        project = replace_region(project, "risk-tiers", filled_risk)
        (self.repo / "forge-project.md").write_text(project, encoding="utf-8")

        second = self.install()

        self.assertEqual(second.returncode, 0, second.stderr)
        merged_risk = region_body(self.read("forge-project.md"), "risk-tiers")
        self.assertEqual(merged_risk, owner_prefix + fixed_block + owner_suffix)
        self.assertNotIn("owner-only.lock", merged_risk)

    def test_reinstall_refreshes_a_narrowed_reviewer_trigger_table(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)

        project = self.read("forge-project.md")
        operator_body = "\noperator project overview stays byte-identical  \n"
        project = replace_region(project, "project-overview", operator_body)
        narrowed = region_body(project, "reviewer-facing-eval-triggers").replace(
            "| constitution | rules/** |",
            "| constitution | rules/never/** |",
        )
        project = replace_region(
            project, "reviewer-facing-eval-triggers", narrowed
        )
        (self.repo / "forge-project.md").write_text(project, encoding="utf-8")

        second = self.install()

        self.assertEqual(second.returncode, 0, second.stderr)
        refreshed_project = self.read("forge-project.md")
        refreshed = region_body(refreshed_project, "reviewer-facing-eval-triggers")
        self.assertEqual(refreshed, "\n" + canonical_reviewer_eval_table())
        self.assertNotIn("rules/never/**", refreshed)
        self.assertEqual(
            region_body(refreshed_project, "project-overview"), operator_body
        )
        agents = self.read("AGENTS.md")
        self.assertEqual(
            agents.split(BEGIN + "\n", 1)[1].split(END, 1)[0],
            refreshed_project,
        )

        stable_project = (self.repo / "forge-project.md").read_bytes()
        stable_agents = (self.repo / "AGENTS.md").read_bytes()
        third = self.install()
        self.assertEqual(third.returncode, 0, third.stderr)
        self.assertEqual((self.repo / "forge-project.md").read_bytes(), stable_project)
        self.assertEqual((self.repo / "AGENTS.md").read_bytes(), stable_agents)

    def test_malformed_filled_dependency_manifest_block_stops_before_write(self) -> None:
        base = (self.plugin / "system/template/forge-project.md").read_text(
            encoding="utf-8"
        )
        canonical = region_body(base, "risk-tiers")
        canonical = re.sub(r"<!-- forge-init:.*?-->\n", "", canonical, flags=re.DOTALL)
        begin = "<!-- FORGE:DEPENDENCY-MANIFEST-PATHS BEGIN -->"
        end = "<!-- FORGE:DEPENDENCY-MANIFEST-PATHS END -->"
        malformed_bodies = {
            "missing": canonical.replace(begin, "", 1),
            "duplicate": canonical.replace(begin, f"{begin}\n{begin}", 1),
            "misordered": canonical.replace(begin, "TOKEN", 1)
            .replace(end, begin, 1)
            .replace("TOKEN", end, 1),
        }

        for label, body in malformed_bodies.items():
            with self.subTest(case=label):
                project = replace_region(base, "risk-tiers", body)
                before = project.encode("utf-8")
                (self.repo / "forge-project.md").write_bytes(before)

                result = self.install()

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "forge: dependency-manifest block malformed — repair forge-project.md",
                    result.stderr,
                )
                self.assertEqual((self.repo / "forge-project.md").read_bytes(), before)
                self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_reinstall_migrates_the_exact_legacy_nine_region_inventory(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)

        project = self.read("forge-project.md")
        legacy = project.split("\n## Mutation Testing\n", 1)[0] + "\n"
        legacy_body = "\nlegacy project overview stays byte-identical\n"
        legacy = replace_region(legacy, "project-overview", legacy_body)
        (self.repo / "forge-project.md").write_text(legacy, encoding="utf-8")

        second = self.install()

        self.assertEqual(second.returncode, 0, second.stderr)
        migrated = self.read("forge-project.md")
        self.assertEqual(region_body(migrated, "project-overview"), legacy_body)
        self.assertEqual(
            tuple(
                re.findall(
                    r"<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->",
                    migrated,
                )
            ),
            REGION_ORDER,
        )

    def test_reinstall_migrates_the_exact_predecessor_fifteen_region_inventory(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)

        project = self.read("forge-project.md")
        predecessor_body = "\nfifteen-region project overview stays byte-identical\n"
        project = replace_region(project, "project-overview", predecessor_body)
        project, replacements = re.subn(
            r"\n?<!-- FORGE:REGION guard-denied-commands BEGIN -->.*?"
            r"<!-- FORGE:REGION guard-denied-commands END -->\n?",
            "\n",
            project,
            flags=re.DOTALL,
        )
        self.assertEqual(replacements, 1)
        self.assertEqual(
            tuple(
                re.findall(
                    r"<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->",
                    project,
                )
            ),
            REGION_ORDER[:-1],
        )
        (self.repo / "forge-project.md").write_text(project, encoding="utf-8")

        second = self.install()

        self.assertEqual(second.returncode, 0, second.stderr)
        migrated = self.read("forge-project.md")
        self.assertEqual(region_body(migrated, "project-overview"), predecessor_body)
        self.assertEqual(
            region_body(migrated, "guard-denied-commands"),
            region_body(
                (self.plugin / "system/template/forge-project.md").read_text(
                    encoding="utf-8"
                ),
                "guard-denied-commands",
            ),
        )
        self.assertEqual(
            tuple(
                re.findall(
                    r"<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->",
                    migrated,
                )
            ),
            REGION_ORDER,
        )

    def test_reinstall_migrates_the_exact_predecessor_fourteen_region_inventory(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)

        project = self.read("forge-project.md")
        predecessor_body = "\npredecessor project overview stays byte-identical\n"
        project = replace_region(project, "project-overview", predecessor_body)
        project, replacements = re.subn(
            r"\n?<!-- FORGE:REGION guard-denied-commands BEGIN -->.*?"
            r"<!-- FORGE:REGION guard-denied-commands END -->\n?",
            "\n",
            project,
            flags=re.DOTALL,
        )
        self.assertEqual(replacements, 1)
        project, replacements = re.subn(
            r"\n?<!-- FORGE:REGION reviewer-facing-eval-triggers BEGIN -->.*?"
            r"<!-- FORGE:REGION reviewer-facing-eval-triggers END -->\n?",
            "\n",
            project,
            flags=re.DOTALL,
        )
        self.assertEqual(replacements, 1)
        self.assertEqual(
            tuple(
                re.findall(
                    r"<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->",
                    project,
                )
            ),
            REGION_ORDER[:-2],
        )
        (self.repo / "forge-project.md").write_text(project, encoding="utf-8")

        second = self.install()

        self.assertEqual(second.returncode, 0, second.stderr)
        migrated = self.read("forge-project.md")
        self.assertEqual(region_body(migrated, "project-overview"), predecessor_body)
        self.assertEqual(
            region_body(migrated, "reviewer-facing-eval-triggers"),
            region_body(
                (self.plugin / "system/template/forge-project.md").read_text(
                    encoding="utf-8"
                ),
                "reviewer-facing-eval-triggers",
            ),
        )
        self.assertEqual(
            region_body(migrated, "guard-denied-commands"),
            region_body(
                (self.plugin / "system/template/forge-project.md").read_text(
                    encoding="utf-8"
                ),
                "guard-denied-commands",
            ),
        )
        self.assertEqual(
            tuple(
                re.findall(
                    r"<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->",
                    migrated,
                )
            ),
            REGION_ORDER,
        )

    def test_reinstall_rejects_a_missing_region_outside_the_legacy_shape(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)

        project = self.read("forge-project.md")
        project, replacements = re.subn(
            r"<!-- FORGE:REGION invariants BEGIN -->.*?"
            r"<!-- FORGE:REGION invariants END -->",
            "",
            project,
            flags=re.DOTALL,
        )
        self.assertEqual(replacements, 1)
        before_project = project.encode("utf-8")
        before_agents = (self.repo / "AGENTS.md").read_bytes()
        (self.repo / "forge-project.md").write_bytes(before_project)

        second = self.install()

        self.assertNotEqual(second.returncode, 0)
        self.assertIn("missing or reordered regions", second.stderr)
        self.assertEqual((self.repo / "forge-project.md").read_bytes(), before_project)
        self.assertEqual((self.repo / "AGENTS.md").read_bytes(), before_agents)

    def test_existing_agent_content_outside_markers_is_byte_preserved(self) -> None:
        before = b"owner instructions without a trailing newline"
        old_block = b"\n<!-- FORGE:BEGIN -->\nstale\n<!-- FORGE:END -->"
        after = b"\nowner suffix\x00remains\n"
        (self.repo / "AGENTS.md").write_bytes(before + old_block + after)
        (self.repo / "CLAUDE.md").write_bytes(b"owner Claude instructions")
        (self.repo / ".gitignore").write_bytes(b"owner-ignore-pattern")

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = self.read("forge-project.md").encode()
        expected = before + b"\n" + BEGIN.encode() + b"\n" + rendered + END.encode() + after
        self.assertEqual((self.repo / "AGENTS.md").read_bytes(), expected)
        self.assertEqual(
            (self.repo / "CLAUDE.md").read_bytes(),
            b"owner Claude instructions\n@forge-project.md\n",
        )
        self.assertEqual(
            (self.repo / ".gitignore").read_bytes(),
            b"owner-ignore-pattern\n"
            + (self.plugin / "system/template/gitignore-block.txt").read_bytes(),
        )

    def test_repository_history_ignore_rule_fails_closed_with_exact_diagnostic(self) -> None:
        (self.repo / ".gitignore").write_bytes(b"/.forge/history/\n")

        result = self.install()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            result.stderr,
            "forge install: .forge/history/ must not be ignored\n",
        )
        self.assertFalse((self.repo / ".forge/history/.forge-ignore-check").exists())
        self.assertFalse((self.repo / ".forge/tmp/.forge-ignore-check").exists())

    def test_ignore_check_does_not_use_history_as_transient_storage(self) -> None:
        probe = self.repo / ".forge/history/.forge-ignore-check"
        probe.parent.mkdir(parents=True)
        probe.write_bytes(b"pre-existing history bytes\n")

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(probe.read_bytes(), b"pre-existing history bytes\n")

    def test_missing_tmp_ignore_rule_fails_closed_with_exact_diagnostic(self) -> None:
        block = self.plugin / "system/template/gitignore-block.txt"
        block.write_text(
            block.read_text(encoding="utf-8").replace("/.forge/tmp/\n", ""),
            encoding="utf-8",
        )

        result = self.install()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            result.stderr,
            "forge install: .forge/tmp/ must be ignored\n",
        )
        self.assertFalse((self.repo / ".forge/history/.forge-ignore-check").exists())
        self.assertFalse((self.repo / ".forge/tmp/.forge-ignore-check").exists())

    def test_disabling_ignore_invariant_is_detected_by_the_fixture(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertEqual(installer.count("verify_history_ignore_invariant"), 2)

        mutated = installer.replace("verify_history_ignore_invariant\n", "", 1)

        self.assertEqual(mutated.count("verify_history_ignore_invariant"), 1)
        with self.assertRaises(AssertionError):
            self.assertEqual(mutated.count("verify_history_ignore_invariant"), 2)

    def test_malformed_existing_region_markers_fail_without_overwrite(self) -> None:
        malformed = (
            b"owner scaffold\n"
            b"<!-- FORGE:REGION project-overview BEGIN -->\n"
            b"filled owner content without an end marker\n"
        )
        (self.repo / "forge-project.md").write_bytes(malformed)

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("region", result.stderr.lower())
        self.assertEqual((self.repo / "forge-project.md").read_bytes(), malformed)
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_unknown_existing_region_fails_without_silent_discard(self) -> None:
        existing = (self.plugin / "system/template/forge-project.md").read_bytes()
        existing += (
            b"\n<!-- FORGE:REGION owner-extension BEGIN -->\n"
            b"filled owner extension\n"
            b"<!-- FORGE:REGION owner-extension END -->\n"
        )
        (self.repo / "forge-project.md").write_bytes(existing)

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stderr.lower(), r"(?:unexpected|unknown) region")
        self.assertEqual((self.repo / "forge-project.md").read_bytes(), existing)
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_duplicate_agents_splice_markers_fail_without_rewriting_agents(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)
        block = (self.repo / "AGENTS.md").read_bytes()
        duplicated = b"owner prefix\n" + block + b"owner middle\n" + block + b"owner suffix\n"
        (self.repo / "AGENTS.md").write_bytes(duplicated)

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("marker", result.stderr.lower())
        self.assertEqual((self.repo / "AGENTS.md").read_bytes(), duplicated)

    def test_existing_non_forge_codex_files_are_preserved_with_incoming_siblings(self) -> None:
        codex = self.repo / ".codex"
        codex.mkdir()
        existing_config = (
            b'approval_policy = "never"\n'
            b"# owner configuration for a forge-managed deployment\n"
        )
        existing_hooks = b'{"hooks":{"Stop":[]},"owner":"forge-managed"}\n'
        (codex / "config.toml").write_bytes(existing_config)
        (codex / "hooks.json").write_bytes(existing_hooks)

        first = self.install()
        second = self.install()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((codex / "config.toml").read_bytes(), existing_config)
        self.assertEqual((codex / "hooks.json").read_bytes(), existing_hooks)
        self.assertEqual(
            (codex / "config.toml.forge-new").read_bytes(),
            (self.plugin / "system/codex/config.toml").read_bytes(),
        )
        self.assertEqual(
            (codex / "hooks.json.forge-new").read_bytes(),
            (self.plugin / "system/codex/hooks.json").read_bytes(),
        )
        self.assertIn("preserved", (first.stdout + first.stderr).lower())
        self.assertIn("skipped", (second.stdout + second.stderr).lower())

    def test_project_owned_config_forge_new_collision_fails_without_overwrite(self) -> None:
        codex = self.repo / ".codex"
        codex.mkdir()
        original = b'approval_policy = "never"\n'
        owner_sidecar = b"owner sidecar must survive\n"
        (codex / "config.toml").write_bytes(original)
        (codex / "config.toml.forge-new").write_bytes(owner_sidecar)

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forge-new", result.stderr.lower())
        self.assertEqual((codex / "config.toml").read_bytes(), original)
        self.assertEqual((codex / "config.toml.forge-new").read_bytes(), owner_sidecar)

    def test_project_owned_hooks_forge_new_collision_fails_without_overwrite(self) -> None:
        codex = self.repo / ".codex"
        codex.mkdir()
        original = b'{"hooks":{"Stop":[]}}\n'
        owner_sidecar = b'{"owner":"sidecar must survive"}\n'
        (codex / "hooks.json").write_bytes(original)
        (codex / "hooks.json.forge-new").write_bytes(owner_sidecar)

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forge-new", result.stderr.lower())
        self.assertEqual((codex / "hooks.json").read_bytes(), original)
        self.assertEqual((codex / "hooks.json.forge-new").read_bytes(), owner_sidecar)


class DcgConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-dcg-")
        self.addCleanup(self.temp_dir.cleanup)
        self.scratch = Path(self.temp_dir.name)
        self.fake_bin = self.scratch / "bin"
        self.fake_bin.mkdir()
        self.log = self.scratch / "dcg-argv"

    def install_fake_dcg(self) -> None:
        fake_dcg = self.fake_bin / "dcg"
        fake_dcg.write_text(
            """#!/usr/bin/env bash
set -u
{
    printf '%s\\0' "$#"
    printf '%s\\0' "$@"
} >> "${FAKE_DCG_LOG}"

if [ "$#" -eq 2 ] && [ "$1" = allowlist ] && [ "$2" = list ]; then
    printf '%s' "${FAKE_DCG_LIST_OUTPUT-}"
    exit "${FAKE_DCG_LIST_STATUS-0}"
fi

if [ "${1-}" = allow ]; then
    exit "${FAKE_DCG_ALLOW_STATUS-0}"
fi

exit 97
""",
            encoding="utf-8",
        )
        fake_dcg.chmod(0o755)

    def configure(
        self,
        *,
        list_output: str = "",
        list_status: int = 0,
        allow_status: int = 0,
        fake_dcg: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if fake_dcg:
            self.install_fake_dcg()
        search_path = str(self.fake_bin)
        if fake_dcg:
            search_path += f"{os.pathsep}/usr/bin{os.pathsep}/bin"
        environment = {
            **os.environ,
            "PATH": search_path,
            "FAKE_DCG_LOG": str(self.log),
            "FAKE_DCG_LIST_OUTPUT": list_output,
            "FAKE_DCG_LIST_STATUS": str(list_status),
            "FAKE_DCG_ALLOW_STATUS": str(allow_status),
        }
        return subprocess.run(
            ["/bin/bash", str(DCG_CONFIGURATOR)],
            cwd=self.scratch,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def logged_invocations(self) -> list[list[str]]:
        fields = self.log.read_bytes().split(b"\0")
        self.assertEqual(fields.pop(), b"")
        invocations: list[list[str]] = []
        while fields:
            count = int(fields.pop(0))
            invocations.append(
                [fields.pop(0).decode("utf-8") for _ in range(count)]
            )
        return invocations

    def test_absent_dcg_is_skipped_without_error(self) -> None:
        result = self.configure(fake_dcg=False)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "forge: dcg not found — no project allowlist change\n",
        )
        self.assertEqual(result.stderr, "")
        self.assertFalse(self.log.exists())

    def test_missing_project_rule_invokes_exact_allow_command(self) -> None:
        result = self.configure(
            list_output=(
                "Allowlist entries:\n\n"
                '{"type":"rule","value":"core.git:branch-force-delete"} [user]\n'
                '{"type":"rule","value":"core.git:status"} [project]\n'
            )
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "forge: dcg allowlisted core.git:branch-force-delete for this project\n",
        )
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            self.logged_invocations(),
            [
                ["allowlist", "list"],
                [
                    "allow",
                    "core.git:branch-force-delete",
                    "--project",
                    "--reason",
                    "forge worktree-merge deletes branches only after merge-base containment proof",
                ],
            ],
        )

    def test_existing_project_rule_is_not_mutated(self) -> None:
        result = self.configure(
            list_output=(
                "Allowlist entries:\n\n"
                '{ "type" : "rule", "value" : '
                '"core.git:branch-force-delete" }   [ project ]\n'
            )
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "forge: dcg allowlist already contains "
            "core.git:branch-force-delete for this project\n",
        )
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.logged_invocations(), [["allowlist", "list"]])

    def test_allowlist_inspection_failure_is_nonfatal(self) -> None:
        result = self.configure(list_status=23)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "forge: dcg allowlist update failed\n")
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.logged_invocations(), [["allowlist", "list"]])

    def test_allowlist_update_failure_is_nonfatal(self) -> None:
        result = self.configure(allow_status=24)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "forge: dcg allowlist update failed\n")
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            self.logged_invocations(),
            [
                ["allowlist", "list"],
                [
                    "allow",
                    "core.git:branch-force-delete",
                    "--project",
                    "--reason",
                    "forge worktree-merge deletes branches only after merge-base containment proof",
                ],
            ],
        )


class InstallerPayloadContractTests(unittest.TestCase):
    def test_init_policy_self_check_accepts_fences_and_refuses_prose(self) -> None:
        with tempfile.TemporaryDirectory(prefix="forge-init-policy-check-") as temporary:
            repository = Path(temporary)
            policy_path = repository / "forge-project.md"
            valid = (ROOT / "forge-project.md").read_text(encoding="utf-8")
            policy_path.write_text(valid, encoding="utf-8")

            accepted = run_init_policy_self_check(repository)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(accepted.stdout, "")
            self.assertEqual(accepted.stderr, "")

            marker = repository / "inline-prose-must-not-run"
            prose = replace_region(
                valid,
                "stack-validations",
                f"\n1. Python: `touch {marker}`\n2. Tests: `python3 -m unittest`\n",
            )
            policy_path.write_text(prose, encoding="utf-8")
            refused = run_init_policy_self_check(repository)

            self.assertEqual(refused.returncode, 1)
            self.assertEqual(refused.stdout, "")
            self.assertEqual(refused.stderr, STACK_FENCE_ERROR + "\n")
            self.assertFalse(marker.exists())

    def test_init_policy_self_check_control_disabled_in_memory_accepts_prose(self) -> None:
        cell = init_policy_self_check_cell()
        parse_call = 'parse_policy("init-candidate", Path(sys.argv[2]).read_bytes())'
        self.assertEqual(cell.count(parse_call), 1)
        self.assertIn("from forge_cli.policy import PolicyError, parse_policy", cell)

        with tempfile.TemporaryDirectory(prefix="forge-init-policy-mutant-") as temporary:
            repository = Path(temporary)
            valid = (ROOT / "forge-project.md").read_text(encoding="utf-8")
            prose = replace_region(
                valid,
                "stack-validations",
                "\n1. Python tests: `python3 -m unittest`\n",
            )
            (repository / "forge-project.md").write_text(prose, encoding="utf-8")

            real = run_init_policy_self_check(repository, cell=cell)
            disabled = cell.replace(parse_call, "Path(sys.argv[2]).read_bytes()", 1)
            bypassed = run_init_policy_self_check(repository, cell=disabled)

        self.assertEqual(real.returncode, 1)
        self.assertEqual(real.stderr, STACK_FENCE_ERROR + "\n")
        self.assertEqual(bypassed.returncode, 0, bypassed.stderr)

    def test_init_policy_self_check_isolates_python_startup(self) -> None:
        cell = init_policy_self_check_cell()
        self.assertIn('python3 -I -B - "${CLAUDE_PLUGIN_ROOT}"', cell)

        with tempfile.TemporaryDirectory(prefix="forge-init-policy-isolated-") as temporary:
            repository = Path(temporary)
            marker = repository / "startup-module-ran"
            (repository / "forge-project.md").write_bytes(
                (ROOT / "forge-project.md").read_bytes()
            )
            (repository / "sitecustomize.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n",
                encoding="utf-8",
            )

            result = run_init_policy_self_check(repository)
            startup_ran = marker.exists()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertFalse(startup_ran)

    def test_installer_region_inventory_has_current_and_exact_migration_shapes(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")
        match = re.search(r"my @required = qw\((.*?)\n\s*\);", installer, re.DOTALL)
        self.assertIsNotNone(match)
        self.assertEqual(tuple(match.group(1).split()), REGION_ORDER)
        self.assertIn(
            "my @predecessor_required = @required[0 .. 13];",
            installer,
        )
        self.assertIn(
            "my @guard_predecessor_required = @required[0 .. 14];",
            installer,
        )
        self.assertIn("my @legacy_required = @required[0 .. 8];", installer)
        self.assertIn(
            "$previous_inventory eq $guard_predecessor_inventory",
            installer,
        )
        self.assertIn(
            "$previous_inventory eq $predecessor_inventory",
            installer,
        )
        self.assertIn("$previous_inventory eq $legacy_inventory", installer)

    def test_codex_config_and_agents_match_routing_contract(self) -> None:
        config = (ROOT / "system/codex/config.toml").read_text(encoding="utf-8")
        self.assertEqual(toml_string(config, "approval_policy"), "on-failure")
        self.assertEqual(toml_string(config, "sandbox_mode"), "workspace-write")
        self.assertRegex(config, r"(?m)^max_threads\s*=\s*6\s*$")
        self.assertRegex(config, r"(?m)^max_depth\s*=\s*1\s*$")
        registrations = set(re.findall(r'^\[agents\."([^"]+)"\]$', config, re.MULTILINE))
        self.assertEqual(registrations, {"implementer", "review-cheap"})

        expected = {
            "implementer": ("gpt-5.6-sol", "ultra", "workspace-write"),
            "review-cheap": ("gpt-5.6-sol", "high", "read-only"),
        }
        for name, routing in expected.items():
            agent = (ROOT / f"system/codex/agents/{name}.toml").read_text(
                encoding="utf-8"
            )
            with self.subTest(agent=name):
                self.assertEqual(
                    (
                        toml_string(agent, "model"),
                        toml_string(agent, "model_reasoning_effort"),
                        toml_string(agent, "sandbox_mode"),
                    ),
                    routing,
                )
        implementer = (ROOT / "system/codex/agents/implementer.toml").read_text()
        self.assertIn("You may commit inside this worktree.", implementer)
        self.assertIn("You must NEVER push", implementer)
        self.assertIn("never touch any branch other than your own", implementer)

    def test_upstream_rules_baseline_is_committable(self) -> None:
        # Regression guard: this contract used to read `.upstream/`, which is gitignored, so
        # it raised FileNotFoundError in every clean checkout instead of asserting anything.
        # The baseline must live on a path Git will carry into a fresh clone.
        self.assertTrue(UPSTREAM_RULES_FIXTURE.is_file())
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--", str(UPSTREAM_RULES_FIXTURE)],
            cwd=ROOT,
            capture_output=True,
        )
        self.assertEqual(
            ignored.returncode,
            1,
            f"{UPSTREAM_RULES_FIXTURE} is gitignored and cannot reach a clean checkout",
        )

    @unittest.skipUnless(
        VENDORED_UPSTREAM_RULES.is_file(),
        "vendored .upstream/ checkout not present",
    )
    def test_upstream_rules_fixture_matches_vendored_upstream(self) -> None:
        # The fixture carries only the prefix_rule blocks, so compare those rather than
        # whole bytes; upstream prose is intentionally not vendored.
        pattern = r"prefix_rule\(\n.*?\n\)"
        self.assertEqual(
            re.findall(pattern, UPSTREAM_RULES_FIXTURE.read_text(), re.DOTALL),
            re.findall(pattern, VENDORED_UPSTREAM_RULES.read_text(), re.DOTALL),
            "tests/fixtures/upstream-forge.rules is stale against .upstream/",
        )

    def test_rules_keep_upstream_denies_verbatim_and_add_blanket_push_deny(self) -> None:
        upstream = UPSTREAM_RULES_FIXTURE.read_text()
        installed = (ROOT / "system/codex/rules/forge.rules").read_text()
        upstream_rules = re.findall(r"prefix_rule\(\n.*?\n\)", upstream, re.DOTALL)
        self.assertEqual(len(upstream_rules), 4)
        for rule in upstream_rules:
            self.assertIn(rule, installed)
        self.assertEqual(installed.count("prefix_rule("), 5)
        self.assertRegex(
            installed,
            r'pattern\s*=\s*\["git",\s*"push"\][\s\S]*?decision\s*=\s*"forbidden"',
        )

    def test_hooks_seeds_and_init_skill_are_re_rooted_and_complete(self) -> None:
        hooks_path = ROOT / "system/codex/hooks.json"
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        commands = [entry["command"] for entry in hooks["hooks"]["Stop"][0]["hooks"]]
        self.assertEqual(len(commands), 2)
        self.assertTrue(any("display notification" in command for command in commands))
        telemetry = next(command for command in commands if "aggregate-telemetry.sh" in command)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/forge/aggregate-telemetry.sh", telemetry)
        self.assertIn(".forge/tmp/decisions", telemetry)
        self.assertIn('json.load(sys.stdin).get("session_id")', telemetry)
        self.assertIn("--append-csv", telemetry)
        self.assertIn(".forge/tmp/telemetry.csv", telemetry)
        self.assertIn("--session", telemetry)
        self.assertIn('--session "$session_id"', telemetry)
        self.assertNotIn("--csv", telemetry)
        self.assertNotIn("telemetry-latest.csv", telemetry)
        self.assertIn("# forge: modified from upstream", telemetry)
        self.assertIn(": 'forge-managed';", telemetry)
        self.assertRegex(telemetry, r"\|\|\s*true\s*$")

        seeds = ROOT / "system/seeds"
        expected = {
            "README.md",
            "brownfield-exploration.md",
            "eval-tasks/injection-is-flagged.template.md",
            "eval-tasks/review-catches-planted-bug.template.md",
            "eval-tasks/review-passes-clean-change.template.md",
            "validation-snippets/stacks.md",
        }
        # Enumerate what Git would ship, not what is on disk: local tooling scratch
        # (CLAUDE.md stubs, .devlog state) is gitignored and never reaches a clone.
        listed = subprocess.run(
            [
                "git", "ls-files", "-z", "--cached", "--others",
                "--exclude-standard", "--", "system/seeds",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        shipped_paths = sorted(entry for entry in listed.split("\0") if entry)
        actual = {entry.removeprefix("system/seeds/") for entry in shipped_paths}
        self.assertEqual(actual, expected)
        shipped = "\n".join((ROOT / entry).read_text() for entry in shipped_paths)
        legacy_name = "open" + "code"
        self.assertNotIn(legacy_name, shipped.lower())

        skill = (ROOT / "skills/init/SKILL.md").read_text(encoding="utf-8")
        phases = re.findall(r"^## Phase ([0-6])\b", skill, flags=re.MULTILINE)
        self.assertEqual(phases, list("0123456"))
        for required in (
            "origin/HEAD",
            "command -v flock",
            "init_completed: false",
            "STRICT=1",
            "review-final",
            "init_completed: true",
            "git push --force",
            "git push origin HEAD",
            "forbidden",
            "TRUST",
            ".forge/tmp/init-candidate.diff",
            "CANDIDATE_ID",
            "sha256sum",
            "shasum -a 256",
            "all sixteen regions filled",
            "reviewer-facing-eval-triggers",
            "sole maintained source",
            "Recorded-baseline integrity",
            "Candidate-bound fresh reviewer evaluation",
            "matched control row names",
            "FR-083 and FR-103",
            "separately authorized future revision",
            (
                "forge: fresh reviewer eval evidence invalid: fixed first-policy "
                "fresh-evaluation coordinator is\n   unavailable"
            ),
            "init must stop before\n   `review-final`",
            ".forge/history/runs/",
            ".forge/history/drift/",
            ".forge/tmp/authorized/",
            ".forge/tmp/drift/",
            ".forge/tmp/decisions/",
            "scripts/forge/configure-dcg.sh",
            "command -v dcg",
            "dcg allowlist list",
            (
                "dcg allow core.git:branch-force-delete --project --reason "
                '"forge worktree-merge deletes branches only after merge-base '
                'containment proof"'
            ),
            "forge: dcg not found — no project allowlist change",
            "forge: dcg allowlisted core.git:branch-force-delete for this project",
            "forge: dcg allowlist already contains core.git:branch-force-delete for this project",
            "Retain the helper's exact recorded result for the",
            "must remain visible there",
            "forge: warning — plugin_ref is dirty and installation is not reproducible from a commit: <ref>",
            "This warning does not block initialization",
            "the exact Phase 1 dcg integration result",
            "any dirty\n  `plugin_ref` reproducibility warning from Phase 5",
            "No mutation tool available for <stack> — assertion-quality fallback only.",
            "No trigger paths configured.",
            "forge: executable policy row malformed",
            "git show HEAD:forge-project.md",
            "isolated clean checkout",
            "first-policy bootstrap",
            "four-line v2 reviewed marker",
            "tree authorization ID",
            "second explicit approval",
        ):
            self.assertIn(required, skill)
        phase3_region_inventory = re.search(
            r"End with all sixteen regions filled:\n\n"
            r"((?:[1-9][0-9]*\. \x60[a-z0-9-]+\x60\n)+)",
            init_phase(skill, 3),
        )
        self.assertIsNotNone(phase3_region_inventory)
        self.assertEqual(
            tuple(
                (int(position), name)
                for position, name in re.findall(
                    r"^([1-9][0-9]*)\. \x60([a-z0-9-]+)\x60$",
                    phase3_region_inventory.group(1),
                    flags=re.MULTILINE,
                )
            ),
            tuple(enumerate(REGION_ORDER, start=1)),
        )
        self.assertIn(
            "fixed-authority bootstrap coordinator is not implemented or authorized "
            "in this revision",
            " ".join(skill.split()),
        )

        specification = (ROOT / "docs/specs/forge-plugin-spec.md").read_text(
            encoding="utf-8"
        )
        for required in (
            "this revision specifies the first-policy bootstrap fresh-review requirement",
            "does not implement or authorize its fixed-authority coordinator",
            "separately authorized future revision supplies that coordinator",
            "every bootstrap fresh-review request MUST fail closed",
            "init stops before `review-final`",
        ):
            self.assertIn(required, specification)

        phase1 = skill.index("## Phase 1")
        invalidation = skill.index("make re-init invalidation")
        phase5 = skill.index("## Phase 5")
        freeze = skill.index("freeze the review candidate")
        fresh_evaluation = skill.index(
            "Require Candidate-bound fresh reviewer evaluation"
        )
        binding_review = skill.index("Spawn a fresh, read-only `review-final` agent")
        phase6 = skill.index("## Phase 6")
        approval_recheck = skill.index("After explicit approval")
        completion_flip = skill.index("Only after that comparison passes")
        self.assertLess(invalidation, phase1)
        self.assertLess(phase5, freeze)
        self.assertLess(freeze, fresh_evaluation)
        self.assertLess(fresh_evaluation, binding_review)
        self.assertLess(freeze, phase6)
        self.assertLess(phase6, approval_recheck)
        self.assertLess(approval_recheck, completion_flip)
        self.assertIn("byte-for-byte with the reviewed snapshot", skill)
        self.assertIn("invalidates both `review-final` PASS and", skill)

    def test_commit_skill_keeps_eval_layers_distinct_and_uses_one_trigger_source(self) -> None:
        skill = (ROOT / "skills/commit/SKILL.md").read_text(encoding="utf-8")
        step2 = skill[skill.index("## Step 2"):skill.index("## Step 3")]
        step4 = skill[skill.index("## Step 4"):skill.index("## Step 5")]

        for required in (
            "Recorded-baseline integrity",
            "does not launch an agent",
            "Candidate-bound fresh reviewer evaluation",
            "reviewer-facing-eval-triggers",
            "snapshot.paths",
            "matched control row names",
            "must not restate, reconstruct, or maintain a\nsecond trigger path list",
            "fresh-reviewer-evals",
            "unconditionally true",
        ):
            self.assertIn(required, step2 + step4)
        self.assertIn("Neither can satisfy the other", step4)
        assert_commit_fresh_eval_source_contract(skill)

        mutants = {
            "authenticated base": (
                "Supply only the pinned `policy_sha` policy bytes",
                "Supply the working-tree policy bytes",
            ),
            "exact snapshot paths": (
                "exact\nbytewise-sorted `snapshot.paths`",
                "caller-selected target paths",
            ),
            "alternate-source prohibition": (
                (
                    "never use target arguments, `git status`, working-tree paths, or a\n"
                    "locally duplicated pattern list"
                ),
                "prefer caller targets and locally duplicated defaults",
            ),
            "malformed source fails closed": (
                (
                    "A missing or malformed authenticated\n"
                    "`reviewer-facing-eval-triggers` region blocks every control-class chain"
                ),
                "A missing trigger region means that no fresh evaluation applies",
            ),
            "matched row names only": (
                (
                    "report the matched control row names sourced from that result,\n"
                    "not a restated list of their path patterns"
                ),
                "report a locally maintained list of matching path patterns",
            ),
        }
        for label, (control, replacement) in mutants.items():
            with self.subTest(disabled_control=label):
                self.assertEqual(skill.count(control), 1)
                disabled = skill.replace(control, replacement, 1)
                with self.assertRaises(AssertionError):
                    assert_commit_fresh_eval_source_contract(disabled)

        duplicated_trigger = skill.replace(
            "After the immutable artifact passes the secret scan,",
            (
                "After the immutable artifact passes the secret scan, preselect "
                "`agents/**` candidates, then"
            ),
            1,
        )
        with self.assertRaises(AssertionError):
            assert_commit_fresh_eval_source_contract(duplicated_trigger)

    def test_codex_stop_hook_appends_rows_for_distinct_stdin_sessions(self) -> None:
        hooks = json.loads(
            (ROOT / "system/codex/hooks.json").read_text(encoding="utf-8")
        )
        commands = [entry["command"] for entry in hooks["hooks"]["Stop"][0]["hooks"]]
        telemetry = next(command for command in commands if "aggregate-telemetry.sh" in command)

        with tempfile.TemporaryDirectory(prefix="forge-codex-stop-hook-") as temp_dir:
            repo = Path(temp_dir)
            subprocess.run(
                ["git", "init", "--quiet"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            (repo / ".forge-manifest").write_text(
                "forge_version: 1\n", encoding="utf-8"
            )
            decisions = repo / ".forge/tmp/decisions"
            decisions.mkdir(parents=True)
            event = {
                "at": "2026-08-12T10:00:00Z",
                "candidate": "a" * 64,
                "event": "assertion_advisory",
                "policy_sha": "b" * 40,
                "reason": "inconclusive",
                "surface": "/forge:commit",
            }
            (decisions / "events.jsonl").write_text(
                json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )

            sessions = ("codex-session-a", "codex-session-b")
            for session_id in sessions:
                result = subprocess.run(
                    ["bash", "-c", telemetry],
                    cwd=repo,
                    env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)},
                    input=json.dumps({"session_id": session_id}),
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            with (repo / ".forge/tmp/telemetry.csv").open(newline="") as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(rows[0][0], "session")
            self.assertEqual(sum(row[0] == "session" for row in rows), 1)
            self.assertEqual(tuple(row[0] for row in rows[1:]), sessions)

    def test_init_approval_surface_controls_are_observed(self) -> None:
        skill = (ROOT / "skills/init/SKILL.md").read_text(encoding="utf-8")
        dcg_failure = "forge: dcg allowlist update failed"

        dirty = simulate_init_approval_reporting(
            skill,
            dcg_result=dcg_failure,
            plugin_ref="955ae34-dirty",
        )
        self.assertEqual(dirty.phase1_recorded, (dcg_failure,))
        self.assertEqual(
            dirty.phase5_reported,
            (
                "forge: warning — plugin_ref is dirty and installation is not "
                "reproducible from a commit: 955ae34-dirty",
            ),
        )
        self.assertEqual(
            dirty.phase6_approval,
            (*dirty.phase1_recorded, *dirty.phase5_reported),
        )

        clean = simulate_init_approval_reporting(
            skill,
            dcg_result="forge: dcg not found — no project allowlist change",
            plugin_ref="955ae34",
        )
        self.assertEqual(clean.phase5_reported, ())
        self.assertEqual(clean.phase6_approval, clean.phase1_recorded)

        mutants = {
            "dcg Phase 1 carry": (
                "Retain the helper's exact recorded result for the\nPhase 6 approval summary",
                "Retain the helper's result for later reporting",
            ),
            "dcg non-fatal failure preservation": (
                "non-fatal\n`forge: dcg allowlist update failed` result must remain visible there",
                "non-fatal dcg failures may be omitted",
            ),
            "dcg Phase 6 consumption": (
                "the exact Phase 1 dcg integration result",
                "the Phase 1 integration status",
            ),
            "dirty warning condition": (
                "If\n   the derived ref ends in `-dirty`",
                "If the derived ref is nonempty",
            ),
            "dirty warning text": (
                "forge: warning — plugin_ref is dirty and installation is not reproducible from a commit: <ref>",
                "forge: warning — plugin_ref could be dirty: <ref>",
            ),
            "dirty Phase 5 carry": (
                "This warning does not block initialization, but it must also be repeated in the Phase 6 approval\n   summary",
                "This warning does not block initialization",
            ),
            "dirty Phase 6 consumption": (
                "any dirty\n  `plugin_ref` reproducibility warning from Phase 5",
                "the Phase 5 plugin ref",
            ),
        }
        for label, (control, replacement) in mutants.items():
            with self.subTest(disabled_control=label):
                self.assertEqual(skill.count(control), 1)
                disabled = skill.replace(control, replacement, 1)
                with self.assertRaises(AssertionError):
                    simulate_init_approval_reporting(
                        disabled,
                        dcg_result=dcg_failure,
                        plugin_ref="955ae34-dirty",
                    )


if __name__ == "__main__":
    unittest.main()
