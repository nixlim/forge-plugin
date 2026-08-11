"""Integration and payload contract tests for the Forge installer."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "forge" / "install.sh"
DCG_CONFIGURATOR = ROOT / "scripts" / "forge" / "configure-dcg.sh"
TEMPLATE = ROOT / "system" / "template" / "forge-project.md"
BEGIN = "<!-- FORGE:BEGIN -->"
END = "<!-- FORGE:END -->"


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
        self.assertNotIn("{{FORGE_INSTALL_DATE}}", project)
        self.assertRegex(project, r"Install date: `\d{4}-\d{2}-\d{2}`")
        self.assertIn("forge-init:", project)
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
        self.assertTrue((self.repo / ".forge/tmp").is_dir())
        self.assertTrue((self.repo / ".forge/tmp/drift").is_dir())
        self.assertTrue((self.repo / ".forge/tmp/decisions").is_dir())
        self.assertEqual(
            self.read(".gitignore"),
            (self.plugin / "system/template/gitignore-block.txt").read_text(),
        )
        self.assertEqual(
            self.read(".gitignore").count("# --- forge agent system --- #"), 1
        )

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
            re.findall(
                r"<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->",
                migrated,
            ),
            [
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
            ],
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
            "review-cheap": ("gpt-5.6-terra", "medium", "read-only"),
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

    def test_rules_keep_upstream_denies_verbatim_and_add_blanket_push_deny(self) -> None:
        upstream = (ROOT / ".upstream/forge/system/template/.codex/rules/forge.rules").read_text()
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
        self.assertIn(".forge/tmp/telemetry-latest.csv", telemetry)

        seeds = ROOT / "system/seeds"
        expected = {
            "README.md",
            "brownfield-exploration.md",
            "eval-tasks/injection-is-flagged.template.md",
            "eval-tasks/review-catches-planted-bug.template.md",
            "eval-tasks/review-passes-clean-change.template.md",
            "validation-snippets/stacks.md",
        }
        actual = {
            path.relative_to(seeds).as_posix()
            for path in seeds.rglob("*")
            if path.is_file() and path.name != "CLAUDE.md"
        }
        self.assertEqual(actual, expected)
        shipped = "\n".join(path.read_text() for path in seeds.rglob("*") if path.is_file())
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
            "all fourteen regions filled",
            ".forge/history/runs/",
            ".forge/history/drift/",
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
            "No mutation tool available for <stack> — assertion-quality fallback only.",
            "No trigger paths configured.",
            "forge: executable policy row malformed",
            "git show HEAD:forge-project.md",
            "isolated clean checkout",
            "first-policy bootstrap",
            "two-line reviewed marker",
            "second explicit approval",
        ):
            self.assertIn(required, skill)

        phase1 = skill.index("## Phase 1")
        invalidation = skill.index("make re-init invalidation")
        phase5 = skill.index("## Phase 5")
        freeze = skill.index("freeze the review candidate")
        phase6 = skill.index("## Phase 6")
        approval_recheck = skill.index("After explicit approval")
        completion_flip = skill.index("Only after that comparison passes")
        self.assertLess(invalidation, phase1)
        self.assertLess(phase5, freeze)
        self.assertLess(freeze, phase6)
        self.assertLess(phase6, approval_recheck)
        self.assertLess(approval_recheck, completion_flip)
        self.assertIn("byte-for-byte with the reviewed snapshot", skill)
        self.assertIn("invalidates both `review-final` PASS and", skill)


if __name__ == "__main__":
    unittest.main()
