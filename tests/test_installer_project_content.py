"""Integration tests for project-owned installer content."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import test_migration as migration_tests
from tests._git_env import init_quiet_repository

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/forge/install.sh"
MERGE_HELPER = ROOT / "scripts/forge/codex_layer_merge.py"
SPINE_BEGIN = b"<!-- FORGE:PROJECT-SPINE BEGIN -->"
SPINE_END = b"<!-- FORGE:PROJECT-SPINE END -->"


def replace_spine(document: bytes, body: bytes) -> bytes:
    prefix, remainder = document.split(SPINE_BEGIN, 1)
    _old, suffix = remainder.split(SPINE_END, 1)
    return prefix + SPINE_BEGIN + body + SPINE_END + suffix


def project_spine(document: bytes) -> bytes:
    return SPINE_BEGIN + document.split(SPINE_BEGIN, 1)[1].split(SPINE_END, 1)[0] + SPINE_END


def snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
    result: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        mode = path.lstat().st_mode
        if stat.S_ISREG(mode):
            value: tuple[str, bytes | str] = ("file", path.read_bytes())
        elif stat.S_ISDIR(mode):
            value = ("directory", b"")
        elif stat.S_ISLNK(mode):
            value = ("symlink", os.readlink(path))
        else:
            value = ("special", b"")
        result[relative.as_posix()] = value
    return result


def tree_hash(root: Path) -> str:
    entries = [
        [path, kind, value.hex() if isinstance(value, bytes) else value]
        for path, (kind, value) in snapshot(root).items()
    ]
    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


class _InstallerFixture(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="forge-project-content-")
        self.addCleanup(temporary.cleanup)
        self.scratch = Path(temporary.name)
        self.repo = self.scratch / "target repo"
        self.plugin = self.scratch / "plugin payload"
        self.repo.mkdir()
        self.plugin.mkdir()
        init_quiet_repository(self.repo, "--quiet").check_returncode()
        shutil.copytree(ROOT / "system", self.plugin / "system")

    def install(
        self,
        installer: Path = INSTALLER,
        extra_env: dict[str, str] | None = None,
        repo: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = {**os.environ, "CLAUDE_PLUGIN_ROOT": "ignored"}
        environment.update(extra_env or {})
        return subprocess.run(
            ["bash", str(installer), str(self.plugin)],
            cwd=repo or self.repo,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def first_install(self) -> None:
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)

    def copied_installer(self, old: str, new: str) -> Path:
        scripts = self.scratch / "mutant/scripts/forge"
        scripts.mkdir(parents=True)
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertEqual(source.count(old), 1)
        (scripts / "install.sh").write_text(source.replace(old, new, 1), encoding="utf-8")
        shutil.copy2(MERGE_HELPER, scripts / MERGE_HELPER.name)
        return scripts / "install.sh"

    def fresh_repository(self, scenario: str) -> Path:
        repo = self.scratch / scenario / "target repo"
        repo.mkdir(parents=True)
        init_quiet_repository(repo, "--quiet").check_returncode()
        return repo

    def assert_linked_claude_install(
        self,
        installer: Path,
        scenario: str,
        *,
        dangling: bool,
        target: str = "AGENTS.md",
    ) -> dict[str, tuple[str, bytes | str]]:
        repo = self.fresh_repository(scenario)
        linked_target = repo / target
        claude = repo / "CLAUDE.md"
        if not dangling:
            linked_target.write_bytes(b"")
        claude.symlink_to(target)

        result = self.install(installer, repo=repo)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(claude.is_symlink())
        self.assertTrue(claude.is_file())
        self.assertEqual(
            claude.read_bytes(), linked_target.read_bytes() + b"@forge-project.md\n"
        )
        stable = snapshot(repo)
        rerun = self.install(installer, repo=repo)
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        self.assertEqual(snapshot(repo), stable)
        return stable


class InstallerProjectContentTests(_InstallerFixture):
    def test_spine_bytes_and_original_install_date_survive_reinit(self) -> None:
        self.first_install()
        project_path = self.repo / "forge-project.md"
        first = project_path.read_bytes()
        old_date = b"Install date: `2000-02-29`"
        first, count = re.subn(
            rb"^Install date: `[^`]+`$", old_date, first, count=1, flags=re.MULTILINE
        )
        self.assertEqual(count, 1)
        custom_body = (
            b"\nProject rule with trailing bytes.  \r\n"
            b"Install date: `2099-12-31`\r\n\r\nNarrower rule.\t\n"
        )
        project_path.write_bytes(replace_spine(first, custom_body))

        template = self.plugin / "system/template/forge-project.md"
        template.write_bytes(
            template.read_bytes().replace(
                b"# Forge Plugin Project Instructions",
                b"# Forge Plugin Project Instructions (refreshed)",
                1,
            )
        )
        second = self.install()

        self.assertEqual(second.returncode, 0, second.stderr)
        merged = project_path.read_bytes()
        self.assertIn(b"(refreshed)", merged)
        self.assertEqual(project_spine(merged), SPINE_BEGIN + custom_body + SPINE_END)
        self.assertIn(old_date, merged)
        agents = (self.repo / "AGENTS.md").read_bytes()
        splice = agents.split(b"<!-- FORGE:BEGIN -->\n", 1)[1].split(
            b"<!-- FORGE:END -->", 1
        )[0]
        self.assertEqual(splice, merged)

        stable = snapshot(self.repo)
        third = self.install()
        self.assertEqual(third.returncode, 0, third.stderr)
        self.assertEqual(snapshot(self.repo), stable)
        self.assertIn("forge-project.md (unchanged)", third.stdout)

    def test_crlf_project_headings_and_spine_survive_reinit(self) -> None:
        self.first_install()
        project_path = self.repo / "forge-project.md"
        crlf = project_path.read_bytes().replace(b"\n", b"\r\n")
        custom = b"\r\nProject CRLF addendum.  \r\n"
        project_path.write_bytes(replace_spine(crlf, custom))

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(project_spine(project_path.read_bytes()), SPINE_BEGIN + custom + SPINE_END)

    def test_malformed_spine_variants_refuse_without_mutation(self) -> None:
        self.first_install()
        project_path = self.repo / "forge-project.md"
        canonical = project_path.read_bytes()
        region_begin = b"<!-- FORGE:REGION project-overview BEGIN -->"
        cases = {
            "missing-end": canonical.replace(SPINE_END, b"", 1),
            "missing-pair": canonical.replace(SPINE_BEGIN, b"", 1).replace(
                SPINE_END, b"", 1
            ),
            "duplicate": canonical.replace(SPINE_END, SPINE_END + b"\n" + SPINE_BEGIN, 1),
            "reversed": canonical.replace(SPINE_BEGIN, b"SPINE-TOKEN", 1)
            .replace(SPINE_END, SPINE_BEGIN, 1)
            .replace(b"SPINE-TOKEN", SPINE_END, 1),
            "inside-region": canonical.replace(SPINE_BEGIN, b"", 1)
            .replace(SPINE_END, b"", 1)
            .replace(region_begin, region_begin + b"\n" + SPINE_BEGIN + b"\n" + SPINE_END, 1),
            "region-inside-spine": replace_spine(
                canonical, b"\n<!-- FORGE:REGION nested BEGIN -->\n"
            ),
        }
        for label, malformed in cases.items():
            with self.subTest(case=label):
                project_path.write_bytes(malformed)
                before = snapshot(self.repo)
                result = self.install()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "forge: project spine addenda block malformed — repair forge-project.md",
                    result.stderr,
                )
                self.assertEqual(snapshot(self.repo), before)
                project_path.write_bytes(canonical)

    def test_legacy_divergence_is_preserved_as_blocking_collision(self) -> None:
        self.first_install()
        project_path = self.repo / "forge-project.md"
        installed = project_path.read_bytes()
        section = re.search(
            rb"### Project Spine Addenda\n.*?(?=## Plugin Skills\n)",
            installed,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(section)
        legacy = installed[: section.start()] + installed[section.end() :]
        legacy = legacy.replace(
            b"Keep the default branch linear.",
            b"Keep the default branch linear. Project-specific legacy text.",
            1,
        )
        project_path.write_bytes(legacy)

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / "forge-project.md.forge-prev").read_bytes(), legacy)
        self.assertIn("blocking collision", result.stdout)
        self.assertIn(SPINE_BEGIN, project_path.read_bytes())
        self.assertNotIn(b"Project-specific legacy text", project_path.read_bytes())
        stable = snapshot(self.repo)
        rerun = self.install()
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        self.assertEqual(snapshot(self.repo), stable)

    def test_differing_project_collision_sibling_refuses_without_mutation(self) -> None:
        self.first_install()
        project_path = self.repo / "forge-project.md"
        installed = project_path.read_bytes()
        section = re.search(
            rb"### Project Spine Addenda\n.*?(?=## Plugin Skills\n)",
            installed,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(section)
        legacy = installed[: section.start()] + installed[section.end() :]
        project_path.write_bytes(legacy.replace(b"Git Policy", b"Legacy Git Policy", 1))
        (self.repo / "forge-project.md.forge-prev").write_bytes(b"other project bytes\n")
        before = snapshot(self.repo)

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to overwrite project collision sibling", result.stderr)
        self.assertEqual(snapshot(self.repo), before)

    def test_symlinked_legacy_project_refuses_without_creating_sidecar(self) -> None:
        self.first_install()
        project_path = self.repo / "forge-project.md"
        installed = project_path.read_bytes()
        section = re.search(
            rb"### Project Spine Addenda\n.*?(?=## Plugin Skills\n)",
            installed,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(section)
        legacy = installed[: section.start()] + installed[section.end() :]
        outside = self.scratch / "legacy-project.md"
        outside.write_bytes(legacy.replace(b"Git Policy", b"Legacy Git Policy", 1))
        project_path.unlink()
        project_path.symlink_to(outside)
        before = snapshot(self.repo)

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("destination is not a regular file", result.stderr)
        self.assertFalse((self.repo / "forge-project.md.forge-prev").exists())
        self.assertEqual(snapshot(self.repo), before)

    def test_canonical_legacy_project_receives_slot_without_collision(self) -> None:
        self.first_install()
        project_path = self.repo / "forge-project.md"
        installed = project_path.read_bytes()
        section = re.search(
            rb"### Project Spine Addenda\n.*?(?=## Plugin Skills\n)",
            installed,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(section)
        project_path.write_bytes(installed[: section.start()] + installed[section.end() :])

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(SPINE_BEGIN, project_path.read_bytes())
        self.assertFalse((self.repo / "forge-project.md.forge-prev").exists())

    def test_legacy_projection_removes_only_one_separator_blank(self) -> None:
        self.first_install()
        project_path = self.repo / "forge-project.md"
        installed = project_path.read_bytes()
        section = re.search(
            rb"### Project Spine Addenda\n.*?(?=## Plugin Skills\n)",
            installed,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(section)
        legacy = installed[: section.start()] + installed[section.end() :]
        project_path.write_bytes(legacy)
        template = self.plugin / "system/template/forge-project.md"
        template.write_bytes(
            template.read_bytes().replace(
                SPINE_END + b"\n\n", SPINE_END + b"\n\n\n", 1
            )
        )

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / "forge-project.md.forge-prev").read_bytes(), legacy)
        self.assertIn("blocking collision", result.stdout)

    def test_symlinked_harness_files_reinitialize_with_base_behavior(self) -> None:
        cases = {
            "AGENTS.md": (
                "owner/agents.md",
                b"owner agent instructions\n",
                b"<!-- FORGE:BEGIN -->",
            ),
            "CLAUDE.md": ("AGENTS.md", None, b"@forge-project.md"),
            ".gitignore": (
                "owner/gitignore",
                b"owner ignore rule\n",
                b"# --- forge agent system --- #",
            ),
        }
        for index, (relative, (target_relative, target_bytes, expected)) in enumerate(
            cases.items()
        ):
            with self.subTest(destination=relative):
                repo = self.scratch / f"symlink-target-{index}"
                repo.mkdir()
                init_quiet_repository(repo, "--quiet").check_returncode()
                first = self.install(repo=repo)
                self.assertEqual(first.returncode, 0, first.stderr)
                destination = repo / relative
                target = repo / target_relative
                if target_bytes is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(target_bytes)
                target_before = target.read_bytes()
                destination.unlink()
                destination.symlink_to(os.path.relpath(target, destination.parent))

                result = self.install(repo=repo)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(destination.is_symlink())
                self.assertIn(expected, destination.read_bytes())
                self.assertEqual(target.read_bytes(), target_before)

    def test_fresh_dangling_claude_matches_base_behavior_and_is_idempotent(
        self,
    ) -> None:
        dangling = self.assert_linked_claude_install(
            INSTALLER, "dangling-claude", dangling=True
        )
        existing = self.assert_linked_claude_install(
            INSTALLER, "existing-claude-target", dangling=False
        )

        self.assertEqual(dangling, existing)

    def test_fresh_dangling_claude_accepts_earlier_project_output(self) -> None:
        self.assert_linked_claude_install(
            INSTALLER,
            "dangling-claude-to-project",
            dangling=True,
            target="forge-project.md",
        )

    def test_dangling_harness_refusal_preserves_tree_hash(self) -> None:
        cases = (
            ("agents", "AGENTS.md", "CLAUDE.md", False),
            ("gitignore", ".gitignore", "AGENTS.md", False),
            ("unplanned", "CLAUDE.md", "owner/missing.md", True),
            ("late-output", "CLAUDE.md", ".gitignore", False),
            ("missing-parent", "CLAUDE.md", "missing/../AGENTS.md", False),
            ("outside", "CLAUDE.md", "", False),
        )
        for label, relative, target, create_parent in cases:
            with self.subTest(case=label):
                repo = self.fresh_repository(f"dangling-refusal-{label}")
                if label == "outside":
                    outside = repo.with_name(f"{repo.name}-outside")
                    outside.mkdir()
                    target = os.path.relpath(outside / "AGENTS.md", repo)
                elif create_parent:
                    (repo / target).parent.mkdir(parents=True)
                destination = repo / relative
                destination.symlink_to(target)
                before = tree_hash(repo)

                result = self.install(repo=repo)

                self.assertEqual(result.returncode, 2)
                self.assertIn(
                    f"destination is not a regular file: {destination}", result.stderr
                )
                self.assertEqual(tree_hash(repo), before)

    def test_dangling_claude_allowance_disable_leg(self) -> None:
        mutant = self.copied_installer(
            '&& is_planned_dangling_claude_target "${destination}"; then',
            "&& false; then",
        )

        with self.assertRaises(AssertionError):
            self.assert_linked_claude_install(
                mutant, "disabled-dangling-claude", dangling=True
            )

    def test_nonregular_harness_refusal_preserves_tree_hash(self) -> None:
        template = self.plugin / "system/template/forge-project.md"
        original_template = template.read_bytes()
        for index, relative in enumerate(("AGENTS.md", "CLAUDE.md", ".gitignore")):
            with self.subTest(destination=relative):
                template.write_bytes(original_template)
                repo = self.scratch / f"refusal-target-{index}"
                repo.mkdir()
                init_quiet_repository(repo, "--quiet").check_returncode()
                first = self.install(repo=repo)
                self.assertEqual(first.returncode, 0, first.stderr)
                destination = repo / relative
                destination.unlink()
                destination.mkdir()
                template.write_bytes(
                    original_template.replace(
                        b"Use Decompose, Verify, Review, Reintegrate",
                        f"Use Decompose {index}, Verify, Review, Reintegrate".encode(),
                        1,
                    )
                )
                before = tree_hash(repo)

                result = self.install(repo=repo)

                self.assertEqual(result.returncode, 2)
                self.assertIn("destination is not a regular file", result.stderr)
                self.assertEqual(tree_hash(repo), before)
        template.write_bytes(original_template)


class InstallerCodexContentTests(_InstallerFixture):
    def test_foreign_hooks_merge_config_collides_and_rerun_is_stable(self) -> None:
        self.first_install()
        codex = self.repo / ".codex"
        hooks_path = codex / "hooks.json"
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        hooks["hooks"]["SessionStart"] = [
            {
                "hooks": [
                    {"type": "command", "command": "project-session", "timeout": 7}
                ]
            }
        ]
        hooks_path.write_text(json.dumps(hooks) + "\n", encoding="utf-8")
        config_path = codex / "config.toml"
        foreign_config = config_path.read_bytes() + b"\n[features]\nhooks = true\n"
        config_path.write_bytes(foreign_config)

        second = self.install()

        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("project-session", hooks_path.read_text(encoding="utf-8"))
        self.assertEqual(config_path.read_bytes(), foreign_config)
        self.assertEqual(
            (codex / "config.toml.forge-new").read_bytes(),
            (self.plugin / "system/codex/config.toml").read_bytes(),
        )
        stable = snapshot(self.repo)
        third = self.install()
        self.assertEqual(third.returncode, 0, third.stderr)
        self.assertEqual(snapshot(self.repo), stable)

    def assert_malformed_codex_refuses_without_mutation(
        self, relative: str, malformed: bytes
    ) -> None:
        self.first_install()
        (self.repo / ".codex" / relative).write_bytes(malformed)
        template = self.plugin / "system/template/forge-project.md"
        template.write_bytes(template.read_bytes().replace(b"Operating Model", b"Changed Model", 1))
        before = snapshot(self.repo)

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"forge install: malformed .codex/{relative}", result.stderr)
        self.assertEqual(snapshot(self.repo), before)

    def test_malformed_managed_json_refuses_before_any_mutation(self) -> None:
        self.assert_malformed_codex_refuses_without_mutation(
            "hooks.json", b'{"hooks": invalid, "marker": ": \'forge-managed\';"}\n'
        )

    def test_malformed_managed_toml_refuses_before_any_mutation(self) -> None:
        self.assert_malformed_codex_refuses_without_mutation(
            "config.toml", b'# forge-managed\napproval_policy = [\n'
        )

    def test_malformed_unmarked_json_refuses_before_any_mutation(self) -> None:
        self.assert_malformed_codex_refuses_without_mutation(
            "hooks.json", b'{"hooks": invalid}\n'
        )

    def test_malformed_unmarked_toml_refuses_before_any_mutation(self) -> None:
        self.assert_malformed_codex_refuses_without_mutation(
            "config.toml", b'project = [\n'
        )

    def test_non_config_codex_templates_refuse_before_any_mutation(self) -> None:
        self.first_install()
        template = self.plugin / "system/template/forge-project.md"
        template.write_bytes(template.read_bytes().replace(b"Operating Model", b"Changed Model", 1))
        plan = self.plugin / "system/codex/agents/plan.toml"
        before = snapshot(self.repo)

        plan.write_bytes(b"\xff")
        malformed = self.install()

        self.assertNotEqual(malformed.returncode, 0)
        self.assertIn("malformed Codex template agents/plan.toml", malformed.stderr)
        self.assertEqual(snapshot(self.repo), before)

        plan.write_bytes(b"model = [\n")
        malformed_toml = self.install()

        self.assertNotEqual(malformed_toml.returncode, 0)
        self.assertIn("malformed Codex template agents/plan.toml", malformed_toml.stderr)
        self.assertEqual(snapshot(self.repo), before)

        plan.unlink()
        plan.symlink_to(self.scratch / "missing-plan.toml")
        unsafe = self.install()

        self.assertNotEqual(unsafe.returncode, 0)
        self.assertIn("Codex template is not a regular file", unsafe.stderr)
        self.assertEqual(snapshot(self.repo), before)

    def test_non_config_codex_destination_refuses_before_any_mutation(self) -> None:
        self.first_install()
        template = self.plugin / "system/template/forge-project.md"
        template.write_bytes(template.read_bytes().replace(b"Operating Model", b"Changed Model", 1))
        destination = self.repo / ".codex/agents/plan.toml"
        destination.unlink()
        destination.mkdir()
        before = snapshot(self.repo)

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("destination is not a regular file", result.stderr)
        self.assertEqual(snapshot(self.repo), before)

    def test_staged_template_tree_is_immune_to_post_preflight_source_change(
        self,
    ) -> None:
        self.first_install()
        expected = (self.plugin / "system/codex/agents/plan.toml").read_bytes()
        mutant = self.copied_installer(
            "prepare_codex_layer\nverify_codex_preconditions",
            "prepare_codex_layer\n"
            "printf '\\377' > \"${CODEX_SOURCE}/agents/plan.toml\"\n"
            "verify_codex_preconditions",
        )

        result = self.install(mutant)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.repo / ".codex/agents/plan.toml").read_bytes(), expected
        )

    def test_post_prepare_target_change_refuses_before_installer_mutation(self) -> None:
        self.first_install()
        config = self.repo / ".codex/config.toml"
        raced = config.read_bytes() + b"\n[features]\nraced = true\n"
        project_before = (self.repo / "forge-project.md").read_bytes()
        mutant = self.copied_installer(
            "prepare_codex_layer\nverify_codex_preconditions",
            "prepare_codex_layer\n"
            "printf '\\n[features]\\nraced = true\\n' >> "
            '"${TARGET_ROOT}/.codex/config.toml"\n'
            "verify_codex_preconditions",
        )

        result = self.install(mutant)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Codex input changed after preflight", result.stderr)
        self.assertEqual(config.read_bytes(), raced)
        self.assertEqual((self.repo / "forge-project.md").read_bytes(), project_before)

    def test_target_local_tmpdir_is_not_used_for_preflight_staging(self) -> None:
        target_tmp = self.repo / "project tmp"
        target_tmp.mkdir()
        real_mktemp = shutil.which("mktemp")
        self.assertIsNotNone(real_mktemp)
        fake_bin = self.scratch / "fake-bin"
        fake_bin.mkdir()
        calls_path = self.scratch / "mktemp-calls.jsonl"
        shim = fake_bin / "mktemp"
        shim.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["FORGE_MKTEMP_LOG"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
real = os.environ["FORGE_REAL_MKTEMP"]
os.execv(real, [real, *sys.argv[1:]])
""",
            encoding="utf-8",
        )
        shim.chmod(0o755)

        result = self.install(
            extra_env={
                "TMPDIR": str(target_tmp),
                "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                "FORGE_MKTEMP_LOG": str(calls_path),
                "FORGE_REAL_MKTEMP": str(real_mktemp),
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(target_tmp.iterdir()), [])
        calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
        trusted_tmp = Path("/tmp").resolve()
        self.assertIn([str(trusted_tmp / "forge-project.XXXXXX")], calls)
        self.assertIn(["-d", str(trusted_tmp / "forge-codex.XXXXXX")], calls)

    def test_codex_template_filename_with_newline_installs_from_manifest(self) -> None:
        hostile = self.plugin / "system/codex" / "hostile\nname.txt"
        hostile.write_bytes(b"project template bytes\n")

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.repo / ".codex" / hostile.name).read_bytes(),
            b"project template bytes\n",
        )

    def test_preflight_disable_leg_exposes_partial_mutation(self) -> None:
        self.first_install()
        malformed = b'# forge-managed\napproval_policy = [\n'
        (self.repo / ".codex/config.toml").write_bytes(malformed)
        template = self.plugin / "system/template/forge-project.md"
        template.write_bytes(template.read_bytes().replace(b"Operating Model", b"Changed Model", 1))
        before = (self.repo / "forge-project.md").read_bytes()
        mutant = self.copied_installer(
            "prepare_codex_layer\nverify_codex_preconditions\nprintf 'forge install:",
            ": # prepare disabled in-memory fixture\n"
            ": # verification disabled in-memory fixture\n"
            "printf 'forge install:",
        )

        result = self.install(mutant)

        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual((self.repo / "forge-project.md").read_bytes(), before)

    def test_spine_carry_disable_leg_detects_project_text_loss(self) -> None:
        self.first_install()
        project = self.repo / "forge-project.md"
        custom = b"\nProject rule that must survive.\n"
        project.write_bytes(replace_spine(project.read_bytes(), custom))
        template = self.plugin / "system/template/forge-project.md"
        template.write_bytes(template.read_bytes().replace(b"Operating Model", b"Changed Model", 1))
        mutant = self.copied_installer(
            "if (@previous_project_spine) {",
            "if (0 && @previous_project_spine) {",
        )

        result = self.install(mutant)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(custom.strip(), project.read_bytes())


class MigrationCodexPreflightTests(unittest.TestCase):
    def migration_fixture(self) -> migration_tests.UpstreamMigrationTests:
        fixture = migration_tests.UpstreamMigrationTests(
            "test_migrates_real_paths_bytes_evals_codex_and_disk_report"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_managed_foreign_config_sidecar_is_preflighted_before_migration_write(
        self,
    ) -> None:
        fixture = self.migration_fixture()
        config = fixture.repo / ".codex/config.toml"
        config.write_bytes(
            (ROOT / "system/codex/config.toml").read_bytes()
            + b"\n[features]\nhooks = true\n"
        )
        (fixture.repo / ".codex/hooks.json").write_bytes(
            b'{"hooks":{"Stop":[{"hooks":[{"command":'
            b'"bash legacy/scripts/aggregate-telemetry.sh .tmp/decisions '
            b'--csv .tmp/telemetry-latest.csv"}]}]}}\n'
        )
        sibling = fixture.repo / ".codex/config.toml.forge-new"
        sibling.write_bytes(b"different regular project sidecar\n")
        before = migration_tests.repository_snapshot(fixture.repo)

        result = fixture.run_helper()

        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing to overwrite non-forge collision sibling", result.stderr)
        self.assertEqual(migration_tests.repository_snapshot(fixture.repo), before)

    def test_migration_consumes_collision_plan_and_preserves_foreign_config(
        self,
    ) -> None:
        fixture = self.migration_fixture()
        config = fixture.repo / ".codex/config.toml"
        foreign = (
            (ROOT / "system/codex/config.toml").read_bytes()
            + b"\n[features]\nhooks = true\n"
        )
        config.write_bytes(foreign)
        hooks = fixture.repo / ".codex/hooks.json"
        hooks.write_bytes(
            b'{"hooks":{"Stop":[{"hooks":[{"command":'
            b'"bash legacy/scripts/aggregate-telemetry.sh .tmp/decisions '
            b'--csv .tmp/telemetry-latest.csv"}]}]}}\n'
        )

        result = fixture.run_helper()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config.read_bytes(), foreign)
        self.assertEqual(
            (fixture.repo / ".codex/config.toml.forge-new").read_bytes(),
            (ROOT / "system/codex/config.toml").read_bytes(),
        )
        self.assertIn(b": 'forge-managed';", hooks.read_bytes())

    def test_post_migration_reinit_renders_invalid_install_dates(self) -> None:
        fixture = self.migration_fixture()
        migrated = fixture.run_helper()
        self.assertEqual(migrated.returncode, 0, migrated.stderr)
        project = fixture.repo / "forge-project.md"
        token = b"{{FORGE_INSTALL_DATE}}"
        self.assertIn(b"Install date: `" + token + b"`", project.read_bytes())
        nested_date = b"Install date: `1999-12-31`"
        project.write_bytes(replace_spine(project.read_bytes(), b"\n" + nested_date + b"\n"))

        dates = {dt.date.today().isoformat().encode()}
        first = subprocess.run(
            ["bash", str(INSTALLER), str(ROOT)],
            cwd=fixture.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        dates.add(dt.date.today().isoformat().encode())

        self.assertEqual(first.returncode, 0, first.stderr)
        rendered = project.read_bytes()
        match = re.match(
            rb"# Forge Plugin Project Instructions\r?\n\r?\n"
            rb"Install date: `([^`]+)`",
            rendered,
        )
        self.assertIsNotNone(match)
        self.assertIn(match.group(1), dates)
        self.assertNotIn(token, rendered)
        self.assertIn(nested_date, rendered)
        self.assertNotIn(token, (fixture.repo / "AGENTS.md").read_bytes())

        current_date = match.group(1)
        for invalid_date in (
            b"not-a-date",
            b"2026-13-40",
            b"2025-02-29",
            b"0000-00-00",
        ):
            with self.subTest(invalid_date=invalid_date):
                current = project.read_bytes()
                project.write_bytes(
                    current.replace(
                        b"Install date: `" + current_date + b"`",
                        b"Install date: `" + invalid_date + b"`",
                        1,
                    )
                )
                dates = {dt.date.today().isoformat().encode()}
                result = subprocess.run(
                    ["bash", str(INSTALLER), str(ROOT)],
                    cwd=fixture.repo,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                dates.add(dt.date.today().isoformat().encode())

                self.assertEqual(result.returncode, 0, result.stderr)
                rerendered = project.read_bytes()
                rerendered_match = re.match(
                    rb"# Forge Plugin Project Instructions\r?\n\r?\n"
                    rb"Install date: `([^`]+)`",
                    rerendered,
                )
                self.assertIsNotNone(rerendered_match)
                current_date = rerendered_match.group(1)
                self.assertIn(current_date, dates)
                self.assertNotIn(invalid_date, rerendered)
                self.assertIn(nested_date, rerendered)
                self.assertNotIn(token, (fixture.repo / "AGENTS.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
