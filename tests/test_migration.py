from __future__ import annotations

import importlib.util
import inspect
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/forge/migrate-upstream.py"
INSTALLER = ROOT / "scripts/forge/install.sh"
LEGACY_ROOT = ".opencode"

spec = importlib.util.spec_from_file_location("forge_migrate_upstream", HELPER)
assert spec is not None and spec.loader is not None
migration = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = migration
spec.loader.exec_module(migration)


def marker(name: str, body: bytes) -> bytes:
    return (
        f"<!-- FORGE:REGION {name} BEGIN -->".encode("ascii")
        + body
        + f"<!-- FORGE:REGION {name} END -->".encode("ascii")
    )


def body(data: bytes, name: str) -> bytes:
    begin = f"<!-- FORGE:REGION {name} BEGIN -->".encode("ascii")
    end = f"<!-- FORGE:REGION {name} END -->".encode("ascii")
    return data.split(begin, 1)[1].split(end, 1)[0]


def repository_snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
    snapshot: dict[str, tuple[str, bytes | str]] = {}
    for path in root.rglob("*"):
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
            value = (f"special:{stat.S_IFMT(mode)}", b"")
        snapshot[relative.as_posix()] = value
    return snapshot


class ManifestClassifierTests(unittest.TestCase):
    def test_normative_salvage_sources_are_pinned(self) -> None:
        self.assertEqual(
            migration.SALVAGE_SOURCES,
            {
                "file-categories": ".opencode/rules/commit-workflow.md",
                "stack-validations": ".opencode/rules/commit-workflow.md",
                "changelog-policy": ".opencode/rules/commit-workflow.md",
                "review-prompt-project-focus": ".opencode/rules/commit-workflow.md",
                "gate1-test-command": ".opencode/rules/worktree-workflow.md",
                "completeness-project-items": ".opencode/rules/review-constitution.md",
                "project-triggers": ".opencode/rules/review-constitution.md",
                "project-overview": "AGENTS.md",
                "agent-project-context": ".codex/agents/implementer.toml",
            },
        )

    def test_truth_table_and_plugin_precedence(self) -> None:
        cases = {
            b"plugin_ref: abc\n": "plugin",
            b"x\nplugin_ref: abc\nupstream_commit: old\n": "plugin",
            b"upstream_commit: abc\n": "upstream",
            b"upstream_commit:\n": "upstream",
            b"region: gates (rules/gates.md)\n": "upstream",
            b"not_plugin_ref: abc\n": "malformed",
            b" plugin_ref: abc\n": "malformed",
            b"note: upstream_commit: abc\n": "malformed",
            b"note: region: gates (rules/gates.md)\n": "malformed",
            b"": "malformed",
        }
        for contents, expected in cases.items():
            with self.subTest(contents=contents):
                self.assertEqual(migration.classify_manifest(contents), expected)


class LegacyRuntimeNameCarveOutTests(unittest.TestCase):
    def test_shipped_files_limit_opencode_to_migration_carve_out(self) -> None:
        inventory = subprocess.run(
            [
                "git",
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        allowed_files = {
            "UPSTREAM",
            "scripts/forge/migrate-upstream.py",
            "tests/test_migration.py",
        }
        allowed_prefixes = ("docs/design/", "docs/specs/")
        forbidden = b"opencode"
        violations: list[str] = []

        for raw_relative in inventory.split(b"\0"):
            if not raw_relative:
                continue
            relative = os.fsdecode(raw_relative)
            if relative in allowed_files or relative.startswith(allowed_prefixes):
                continue
            path = ROOT / relative
            if path.is_file() and forbidden in path.read_bytes().lower():
                violations.append(relative)

        self.assertEqual(
            sorted(violations),
            [],
            f"legacy runtime name appears outside migration carve-out: {sorted(violations)}",
        )


class InitMigrationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = (ROOT / "skills/init/SKILL.md").read_text(encoding="utf-8")

    def assert_controls_present(self, skill: str) -> None:
        phase0 = skill.index("## Phase 0")
        classifier = skill.index("migrate-upstream.py\" --classify")
        plan = skill.index("migrate-upstream.py\" --plan --target .")
        phase1 = skill.index("## Phase 1")
        migration = skill.index("migrate-upstream.py\" \\\n  --target")
        phase4 = skill.index("## Phase 4")
        strict_before_phase5 = skill.index(
            'STRICT=1 bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/run-evals.sh"',
            phase4,
        )
        phase5 = skill.index("## Phase 5")
        activation_guard = skill.index(
            "while it exists, refuse\n   activation and identify that exact colliding path"
        )
        phase6 = skill.index("## Phase 6")
        immediate_recheck = skill.index(
            "Immediately before either branch can write or commit `init_completed: true`, repeat the reviewer\nshadow check"
        )
        transition_check = skill.index(
            "detect a migration transition mechanically when `HEAD^:.forge-manifest` is upstream schema"
        )
        committed_report = skill.index(
            "Before any activation, a migration report must be\ncommitted"
        )
        reinit_flip = skill.index(
            "For a plugin-schema re-init, only after the comparison passes, atomically change exactly"
        )
        self.assertLess(phase0, classifier)
        self.assertLess(classifier, plan)
        self.assertLess(plan, phase1)
        self.assertLess(classifier, phase1)
        self.assertLess(phase1, migration)
        self.assertLess(migration, phase4)
        self.assertLess(strict_before_phase5, phase5)
        self.assertLess(phase5, activation_guard)
        self.assertLess(activation_guard, phase6)
        self.assertLess(phase6, immediate_recheck)
        self.assertLess(immediate_recheck, transition_check)
        self.assertLess(transition_check, committed_report)
        self.assertLess(committed_report, reinit_flip)
        for required in (
            "An imported fixture\nis never eligible for baseline recording",
            "must remain PENDING and fail the strict gate",
            "Never overwrite or re-mint an imported baseline.",
            "Only for a newly seeded fixture that did\nnot receive an imported baseline",
            "Never launch a baseline-recording run for an imported or previously\nexisting fixture.",
            "Before any activation, a migration report must be\ncommitted",
            "Apply FR-083's ordinary existing-policy rule",
            "Stop without staging,\ncommitting, pushing, launching a workflow, or writing `init_completed: true`",
            "follow the unchanged plugin re-init branch",
            "neither report presence nor\nprior conversational state may override FR-180 classification",
            "detect a migration transition mechanically when `HEAD^:.forge-manifest` is upstream schema",
            "have been added by that same commit",
            "For a plugin-schema re-init",
            "Removal or rename belongs to the operator and\n   requires explicit approval",
            "migration must never delete or rename it automatically",
            '${APPROVED_REGION_SELECTION_ARGS[@]+"${APPROVED_REGION_SELECTION_ARGS[@]}"}',
            "Do not use `eval` or concatenate shell command text.",
        ):
            self.assertIn(required, skill)

    def test_init_migration_controls_and_mutants(self) -> None:
        self.assert_controls_present(self.skill)
        controls = (
            "An imported fixture\nis never eligible for baseline recording",
            "must remain PENDING and fail the strict gate",
            "Never overwrite or re-mint an imported baseline.",
            "Only for a newly seeded fixture that did\nnot receive an imported baseline",
            "Before any activation, a migration report must be\ncommitted",
            "Apply FR-083's ordinary existing-policy rule",
            "Stop without staging,\ncommitting, pushing, launching a workflow, or writing `init_completed: true`",
            "follow the unchanged plugin re-init branch",
            "neither report presence nor\nprior conversational state may override FR-180 classification",
            "detect a migration transition mechanically when `HEAD^:.forge-manifest` is upstream schema",
            "have been added by that same commit",
            "while it exists, refuse\n   activation and identify that exact colliding path",
            "Immediately before either branch can write or commit `init_completed: true`, repeat the reviewer\nshadow check",
            "migrate-upstream.py\" --plan --target .",
            '${APPROVED_REGION_SELECTION_ARGS[@]+"${APPROVED_REGION_SELECTION_ARGS[@]}"}',
        )
        for control in controls:
            with self.subTest(disabled_control=control):
                self.assertEqual(self.skill.count(control), 1)
                disabled = self.skill.replace(control, "control disabled", 1)
                with self.assertRaises((AssertionError, ValueError)):
                    self.assert_controls_present(disabled)

        transition_block_start = self.skill.index(
            "detect a migration transition mechanically when `HEAD^:.forge-manifest` is upstream schema"
        )
        transition_block_end = self.skill.index(
            "committed, regardless of whether policy already existed at `HEAD`.",
            transition_block_start,
        ) + len("committed, regardless of whether policy already existed at `HEAD`.")
        transition_block = self.skill[transition_block_start:transition_block_end]
        without_transition = (
            self.skill[:transition_block_start] + self.skill[transition_block_end:]
        )
        flip_end = without_transition.index(
            "resulting uncommitted change, and stop."
        ) + len("resulting uncommitted change, and stop.")
        relocated = (
            without_transition[:flip_end]
            + "\n"
            + transition_block
            + without_transition[flip_end:]
        )
        with self.assertRaises((AssertionError, ValueError)):
            self.assert_controls_present(relocated)


class UpstreamMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="forge-migration-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "target"
        self.repo.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Forge Tests"], cwd=self.repo, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "forge@example.invalid"],
            cwd=self.repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"], cwd=self.repo, check=True
        )
        (self.repo / ".forge-manifest").write_bytes(b"upstream_commit: old\n")
        self.expected: dict[str, bytes] = {
            name: f"\r\n{name} \u2603 keeps bytes  \r\n".encode("utf-8")
            for name in migration.SALVAGE_SOURCES
        }
        grouped: dict[str, list[str]] = {}
        for name, source in migration.SALVAGE_SOURCES.items():
            grouped.setdefault(source, []).append(name)
        for source, names in grouped.items():
            path = self.repo / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"prefix\r\n" + b"\r\n".join(marker(name, self.expected[name]) for name in names))

        self.orphan_name = "future-orphan-runtime"
        orphan = self.repo / LEGACY_ROOT / "skills/future/SKILL.md"
        orphan.parent.mkdir(parents=True, exist_ok=True)
        self.orphan_body = b"\r\nunknown future body  \r\n"
        orphan.write_bytes(marker(self.orphan_name, self.orphan_body))
        self.unexpected_legacy = self.repo / LEGACY_ROOT / "runtime/unanticipated-live-7429.bin"
        self.unexpected_legacy.parent.mkdir(parents=True)
        self.unexpected_legacy.write_bytes(b"unexpected live artifact\n")
        (self.repo / LEGACY_ROOT / "empty-dir").mkdir()
        forge_orphan = self.repo / ".forge/tmp/live-upstream-region.md"
        forge_orphan.parent.mkdir(parents=True)
        self.forge_orphan_name = "orphan-under-forge"
        self.forge_orphan_body = b"\nlegacy body under forge tmp\n"
        forge_orphan.write_bytes(marker(self.forge_orphan_name, self.forge_orphan_body))

        tasks = self.repo / LEGACY_ROOT / "evals/tasks"
        tasks.mkdir(parents=True)
        self.fixture_bytes = b"---\nid: imported\ncategory: review\nagent: review-cheap\nexpected_verdict: BLOCK\n---\r\nfixture  \r\n"
        self.result_bytes = b"BLOCK\r\n"
        (tasks / "imported.md").write_bytes(self.fixture_bytes)
        (tasks / "imported.result").write_bytes(self.result_bytes)

        config = self.repo / ".codex/config.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        self.config_bytes = b"""# Legacy Forge Codex configuration
approval_policy = "on-failure"
sandbox_mode = "workspace-write"
[agents]
max_threads = 6
max_depth = 1
[agents."code-reviewer"]
config_file = "./agents/code-reviewer.toml"
[agents."review-final"]
config_file = "./agents/review-final.toml"
[agents."security-auditor"]
config_file = "./agents/security-auditor.toml"
"""
        config.write_bytes(self.config_bytes)
        self.hooks_bytes = b'{"hooks":{"Stop":[{"command":"bash legacy/scripts/aggregate-telemetry.sh .tmp/decisions --csv .tmp/telemetry-latest.csv"}]}}\n'
        (self.repo / ".codex/hooks.json").write_bytes(self.hooks_bytes)
        agents = self.repo / ".codex/agents"
        agents.mkdir(exist_ok=True)
        self.upstream_agent_names = {
            "code-reviewer.toml",
            "council-seat.toml",
            "debugger.toml",
            "docs-writer.toml",
            "implementer.toml",
            "review-cheap.toml",
            "review-final.toml",
            "security-auditor.toml",
            "simplifier.toml",
            "taskify-agent.toml",
            "test-runner.toml",
        }
        self.upstream_agent_bytes: dict[str, bytes] = {}
        for name in self.upstream_agent_names:
            if name == "implementer.toml":
                self.upstream_agent_bytes[name] = (agents / name).read_bytes()
                continue
            data = f"legacy agent {name}\r\n".encode("ascii")
            (agents / name).write_bytes(data)
            self.upstream_agent_bytes[name] = data

        for relative, contents in {
            "opencode.jsonc": b"{}\n",
            ".claude/commands/legacy.md": b"legacy command\n",
            ".claude/settings.json": b'{"hooks":{"Stop":[]}}\n',
            ".agents/skill.md": b"legacy skill\n",
            ".tmp/.commit-lock": b"old lock\n",
        }.items():
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)

        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "legacy fixture"],
            cwd=self.repo,
            check=True,
        )

    def run_helper(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(HELPER),
                "--target",
                str(self.repo),
                "--plugin-root",
                str(ROOT),
                "--timestamp",
                "2026-08-13T120000Z",
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_migrates_real_paths_bytes_evals_codex_and_disk_report(self) -> None:
        shadow = self.repo / ".claude/agents/review-final.md"
        shadow.parent.mkdir(parents=True, exist_ok=True)
        shadow.write_text("shadow\n", encoding="utf-8")

        result = self.run_helper()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("activation remains blocked by .claude/agents/review-final.md", result.stderr)
        project = (self.repo / "forge-project.md").read_bytes()
        for name, expected in self.expected.items():
            self.assertEqual(body(project, name), expected)
        self.assertEqual(
            (self.repo / ".forge/evals/tasks/imported.md").read_bytes(),
            self.fixture_bytes,
        )
        self.assertEqual(
            (self.repo / ".forge/evals/tasks/imported.result").read_bytes(),
            self.result_bytes,
        )
        self.assertEqual(
            (self.repo / ".codex/config.toml.pre-migration").read_bytes(),
            self.config_bytes,
        )
        self.assertEqual(
            (self.repo / ".codex/hooks.json.pre-migration").read_bytes(),
            self.hooks_bytes,
        )
        self.assertIn(b"# forge-managed", (self.repo / ".codex/config.toml").read_bytes())
        report = self.repo / ".forge/history/migrations/2026-08-13T120000Z.md"
        report_bytes = report.read_bytes()
        plugin_agent_names = {"implementer.toml", "review-cheap.toml"}
        legacy_section = report_bytes.split(b"## Legacy artifacts left in place\n\n", 1)[1].split(
            b"\n## Cross-system lock facts", 1
        )[0]
        for name in self.upstream_agent_names - plugin_agent_names:
            self.assertEqual(
                (self.repo / ".codex/agents" / name).read_bytes(),
                self.upstream_agent_bytes[name],
            )
            self.assertIn(f".codex/agents/{name}".encode(), report_bytes)
        for name in plugin_agent_names:
            self.assertEqual(
                (self.repo / ".codex/agents" / name).read_bytes(),
                (ROOT / "system/codex/agents" / name).read_bytes(),
            )
            self.assertNotIn(f"`.codex/agents/{name}`".encode(), legacy_section)
        self.assertIn(self.orphan_name.encode(), report_bytes)
        self.assertIn(self.forge_orphan_name.encode(), report_bytes)
        self.assertIn(b".forge/tmp/live-upstream-region.md", report_bytes)
        self.assertIn(self.forge_orphan_body, report_bytes)
        self.assertIn((LEGACY_ROOT + "/skills/future/SKILL.md").encode(), report_bytes)
        self.assertIn(self.orphan_body, report_bytes)
        self.assertIn(self.unexpected_legacy.relative_to(self.repo).as_posix().encode(), report_bytes)
        self.assertIn(f"{LEGACY_ROOT}/empty-dir/".encode(), report_bytes)
        self.assertIn(b".codex/agents/security-auditor.toml", report_bytes)
        self.assertIn(b".claude/settings.json (Stop hook present)", report_bytes)
        self.assertIn(b".tmp/.commit-lock", report_bytes)
        self.assertIn(b"AGENT_HALT` is shared", report_bytes)
        self.assertIn(b"Concurrent legacy `/commit` and `/forge:commit` are unsafe", report_bytes)
        self.assertTrue(shadow.exists())
        self.assertIn(b"upstream_commit:", (self.repo / ".forge-manifest").read_bytes())

    def test_divergence_refuses_before_mutation_then_explicit_source_wins(self) -> None:
        copy = self.repo / ".claude/agents/copy.md"
        copy.parent.mkdir(parents=True, exist_ok=True)
        chosen = b"\noperator selected this body\n"
        copy.write_bytes(marker("project-overview", chosen))
        before = {
            path.relative_to(self.repo).as_posix(): path.read_bytes()
            for path in self.repo.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }

        refused = self.run_helper()

        self.assertEqual(refused.returncode, 2)
        self.assertIn("divergent region project-overview", refused.stderr)
        after = {
            path.relative_to(self.repo).as_posix(): path.read_bytes()
            for path in self.repo.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        self.assertEqual(after, before)

        selected = self.run_helper(
            "--select", "project-overview=.claude/agents/copy.md"
        )
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(body((self.repo / "forge-project.md").read_bytes(), "project-overview"), chosen)
        report = (self.repo / ".forge/history/migrations/2026-08-13T120000Z.md").read_bytes()
        self.assertIn(b"`project-overview` from `.claude/agents/copy.md`", report)

    def test_plan_enumerates_all_copies_without_mutation(self) -> None:
        copy = self.repo / ".codex/agents/copy.toml"
        chosen = b"\nsecond live copy\n"
        copy.write_bytes(marker("project-overview", chosen))
        before = {
            path.relative_to(self.repo).as_posix(): path.read_bytes()
            for path in self.repo.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }

        result = subprocess.run(
            ["python3", str(HELPER), "--plan", "--target", str(self.repo)],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("project-overview: plugin destination", result.stdout)
        self.assertIn("AGENTS.md sha256=", result.stdout)
        self.assertIn(".codex/agents/copy.toml sha256=", result.stdout)
        self.assertIn(f"{self.orphan_name}: orphan", result.stdout)
        after = {
            path.relative_to(self.repo).as_posix(): path.read_bytes()
            for path in self.repo.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        self.assertEqual(after, before)

    def test_unfilled_source_is_not_salvaged(self) -> None:
        source = self.repo / migration.SALVAGE_SOURCES["project-overview"]
        source.write_bytes(marker("project-overview", b"\nforge-init: still unfilled\n"))
        subprocess.run(["git", "add", "AGENTS.md"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "unfilled"], cwd=self.repo, check=True)

        result = self.run_helper()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            b"forge-init:",
            body((self.repo / "forge-project.md").read_bytes(), "project-overview"),
        )

    def test_dirty_or_uncommitted_eval_refuses_before_mutation(self) -> None:
        fixture = self.repo / LEGACY_ROOT / "evals/tasks/imported.md"
        fixture.write_bytes(b"dirty working bytes\n")

        result = self.run_helper()

        self.assertEqual(result.returncode, 2)
        self.assertIn("differs from committed bytes", result.stderr)
        self.assertFalse((self.repo / "forge-project.md").exists())
        self.assertEqual(
            sorted(path.relative_to(self.repo / ".forge").as_posix() for path in (self.repo / ".forge").rglob("*")),
            ["tmp", "tmp/live-upstream-region.md"],
        )

    def test_eval_import_collision_refuses_without_overwrite_or_project_write(self) -> None:
        destination = self.repo / ".forge/evals/tasks/imported.result"
        destination.parent.mkdir(parents=True, exist_ok=True)
        original_destination = b"PASS\r\n"
        destination.write_bytes(original_destination)

        result = self.run_helper()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            result.stderr,
            "forge migration: eval import collision has different bytes: imported.result\n",
        )
        self.assertEqual(destination.read_bytes(), original_destination)
        self.assertFalse((self.repo / "forge-project.md").exists())

    def test_deleted_committed_eval_baseline_refuses_before_mutation(self) -> None:
        (self.repo / LEGACY_ROOT / "evals/tasks/imported.result").unlink()

        result = self.run_helper()

        self.assertEqual(result.returncode, 2)
        self.assertIn("committed upstream eval artifact is missing on disk", result.stderr)
        self.assertFalse((self.repo / "forge-project.md").exists())
        self.assertEqual(
            sorted(path.relative_to(self.repo / ".forge").as_posix() for path in (self.repo / ".forge").rglob("*")),
            ["tmp", "tmp/live-upstream-region.md"],
        )

    def test_report_is_collision_free_and_never_overwrites(self) -> None:
        reports = self.repo / ".forge/history/migrations"
        reports.mkdir(parents=True)
        first = reports / "2026-08-13T120000Z.md"
        second = reports / "2026-08-13T120000Z-02.md"
        first.write_bytes(b"first sentinel\n")
        second.write_bytes(b"second sentinel\n")

        result = self.run_helper()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(first.read_bytes(), b"first sentinel\n")
        self.assertEqual(second.read_bytes(), b"second sentinel\n")
        self.assertTrue((reports / "2026-08-13T120000Z-03.md").is_file())

    def test_report_publication_race_never_overwrites(self) -> None:
        original_publish = migration.publish_report_exclusive
        sentinel = b"concurrent writer sentinel\n"

        def raced_publish(root: Path, staged: Path, stamp: str) -> Path:
            directory = root / ".forge/history/migrations"
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"{stamp}.md").write_bytes(sentinel)
            return original_publish(root, staged, stamp)

        migration.publish_report_exclusive = raced_publish
        self.addCleanup(setattr, migration, "publish_report_exclusive", original_publish)

        report = migration.migrate(self.repo, ROOT, {}, "2026-08-13T120000Z")

        self.assertEqual(
            (self.repo / ".forge/history/migrations/2026-08-13T120000Z.md").read_bytes(),
            sentinel,
        )
        self.assertEqual(report.name, "2026-08-13T120000Z-02.md")
        self.assertIn(b"# Forge upstream migration", report.read_bytes())
        self.assertNotIn(b"Report:", report.read_bytes())

    def test_report_publication_links_complete_staged_bytes_without_delete_path(self) -> None:
        linked_sources: list[Path] = []
        original_link = migration.os.link

        def recording_link(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
            linked_sources.append(Path(source))
            original_link(source, destination)

        migration.os.link = recording_link
        self.addCleanup(setattr, migration.os, "link", original_link)
        with tempfile.TemporaryDirectory(prefix="forge-external-report-stage-") as temp:
            staged = Path(temp) / "staged-report.md"
            staged.write_bytes(b"complete staged report\n")
            report = migration.publish_report_exclusive(
                self.repo, staged, "2026-08-13T120000Z"
            )

        self.assertEqual(report.read_bytes(), b"complete staged report\n")
        self.assertEqual(len(linked_sources), 1)
        self.assertEqual(linked_sources[0].parent, self.repo / ".forge/history/migrations")
        self.assertFalse(
            list(
                (self.repo / ".forge/history/migrations").glob(
                    ".forge-migration-report-*.stage"
                )
            )
        )
        source = inspect.getsource(migration.publish_report_exclusive)
        self.assertIn("os.link(local_staged, destination)", source)
        self.assertNotIn("destination.unlink", source)

    def test_report_parent_shape_refuses_before_any_migration_write(self) -> None:
        history = self.repo / ".forge/history"
        history.mkdir(parents=True)
        (history / "migrations").write_bytes(b"not a directory\n")
        before = repository_snapshot(self.repo)

        result = self.run_helper()

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "migration output parent is not a directory: .forge/history/migrations",
            result.stderr,
        )
        self.assertEqual(repository_snapshot(self.repo), before)

    def test_active_agent_directory_refuses_before_any_migration_write(self) -> None:
        destination = self.repo / ".codex/agents/review-cheap.toml"
        destination.unlink()
        destination.mkdir()
        before = repository_snapshot(self.repo)

        result = self.run_helper()

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "migration output is not a regular file: .codex/agents/review-cheap.toml",
            result.stderr,
        )
        self.assertEqual(repository_snapshot(self.repo), before)

    def test_installer_destination_directory_refuses_before_any_migration_write(self) -> None:
        destination = self.repo / ".codex/config.toml"
        destination.unlink()
        destination.mkdir()
        before = repository_snapshot(self.repo)

        result = self.run_helper()

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "migration output is not a regular file: .codex/config.toml",
            result.stderr,
        )
        self.assertEqual(repository_snapshot(self.repo), before)

    def test_foreign_codex_collision_sibling_refuses_before_any_migration_write(self) -> None:
        config = self.repo / ".codex/config.toml"
        config.write_bytes(b"# project-owned config\n")
        sibling = self.repo / ".codex/config.toml.forge-new"
        sibling.mkdir()
        before = repository_snapshot(self.repo)

        result = self.run_helper()

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "migration output is not a regular file: .codex/config.toml.forge-new",
            result.stderr,
        )
        self.assertEqual(repository_snapshot(self.repo), before)

    def test_installer_directory_path_refuses_before_any_migration_write(self) -> None:
        occupied = self.repo / ".forge/history/runs"
        occupied.parent.mkdir(parents=True, exist_ok=True)
        occupied.write_bytes(b"occupied\n")
        before = repository_snapshot(self.repo)

        result = self.run_helper()

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "migration output parent is not a directory: .forge/history/runs",
            result.stderr,
        )
        self.assertEqual(repository_snapshot(self.repo), before)

    def test_imported_fixture_without_baseline_remains_pending(self) -> None:
        result_path = self.repo / LEGACY_ROOT / "evals/tasks/imported.result"
        subprocess.run(["git", "rm", "--quiet", str(result_path.relative_to(self.repo))], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "fixture pending"], cwd=self.repo, check=True
        )

        result = self.run_helper()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.repo / ".forge/evals/tasks/imported.md").read_bytes(), self.fixture_bytes
        )
        self.assertFalse((self.repo / ".forge/evals/tasks/imported.result").exists())

    def test_pre_migration_backup_collision_refuses_before_mutation(self) -> None:
        backup = self.repo / ".codex/config.toml.pre-migration"
        backup.write_bytes(b"different owner bytes\n")

        result = self.run_helper()

        self.assertEqual(result.returncode, 2)
        self.assertIn("pre-migration backup collision", result.stderr)
        self.assertFalse((self.repo / "forge-project.md").exists())
        self.assertEqual(backup.read_bytes(), b"different owner bytes\n")

    def test_special_pre_migration_backup_refuses_without_blocking_or_mutation(self) -> None:
        backup = self.repo / ".codex/config.toml.pre-migration"
        os.mkfifo(backup)
        before = repository_snapshot(self.repo)

        result = self.run_helper()

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "migration output is not a regular file: .codex/config.toml.pre-migration",
            result.stderr,
        )
        self.assertEqual(repository_snapshot(self.repo), before)

    def test_near_match_codex_owner_files_are_not_replaced_or_backed_up(self) -> None:
        config = self.repo / ".codex/config.toml"
        config.write_bytes(
            self.config_bytes.replace(b'[agents."security-auditor"]\n', b"")
        )

        result = self.run_helper()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            config.read_bytes(),
            self.config_bytes.replace(b'[agents."security-auditor"]\n', b""),
        )
        self.assertFalse((self.repo / ".codex/config.toml.pre-migration").exists())
        self.assertEqual(
            (self.repo / ".codex/hooks.json.pre-migration").read_bytes(), self.hooks_bytes
        )

    def test_near_match_hooks_owner_file_is_not_replaced_or_backed_up(self) -> None:
        hooks = self.repo / ".codex/hooks.json"
        hooks.write_bytes(b'{"hooks":{"Stop":[]}}\n')

        result = self.run_helper()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(hooks.read_bytes(), b'{"hooks":{"Stop":[]}}\n')
        self.assertFalse((self.repo / ".codex/hooks.json.pre-migration").exists())
        self.assertEqual(
            (self.repo / ".codex/config.toml.pre-migration").read_bytes(), self.config_bytes
        )

    def test_crlf_codex_signatures_preserve_exact_backups_and_replace_routing(self) -> None:
        config = self.repo / ".codex/config.toml"
        hooks = self.repo / ".codex/hooks.json"
        crlf_config = self.config_bytes.replace(b"\n", b"\r\n")
        crlf_hooks = self.hooks_bytes.replace(b"\n", b"\r\n")
        config.write_bytes(crlf_config)
        hooks.write_bytes(crlf_hooks)

        result = self.run_helper()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.repo / ".codex/config.toml.pre-migration").read_bytes(), crlf_config
        )
        self.assertEqual(
            (self.repo / ".codex/hooks.json.pre-migration").read_bytes(), crlf_hooks
        )
        self.assertIn(b"# forge-managed", config.read_bytes())
        self.assertIn(b": 'forge-managed';", hooks.read_bytes())

    def test_codex_signature_line_fragments_do_not_claim_project_files(self) -> None:
        config = self.repo / ".codex/config.toml"
        config.write_bytes(
            self.config_bytes.replace(
                b'approval_policy = "on-failure"\n',
                b'owner_note = "approval_policy = \\"on-failure\\""\n',
            )
        )

        result = self.run_helper()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.repo / ".codex/config.toml.pre-migration").exists())
        self.assertEqual(
            config.read_bytes(),
            self.config_bytes.replace(
                b'approval_policy = "on-failure"\n',
                b'owner_note = "approval_policy = \\"on-failure\\""\n',
            ),
        )

    def test_missing_plugin_codex_payload_refuses_before_mutation(self) -> None:
        plugin = Path(self.temp.name) / "plugin"
        shutil.copytree(ROOT / "system", plugin / "system")
        (plugin / "system/codex/config.toml").unlink()
        before = {
            path.relative_to(self.repo).as_posix(): path.read_bytes()
            for path in self.repo.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }

        result = subprocess.run(
            [
                "python3",
                str(HELPER),
                "--target",
                str(self.repo),
                "--plugin-root",
                str(plugin),
                "--timestamp",
                "2026-08-13T120000Z",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("missing plugin Codex payload", result.stderr)
        after = {
            path.relative_to(self.repo).as_posix(): path.read_bytes()
            for path in self.repo.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        self.assertEqual(after, before)


class InstallerMigrationControlsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="forge-install-control-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.plugin = Path(self.temp.name) / "plugin"
        self.repo.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"], cwd=self.repo, check=True
        )
        shutil.copytree(ROOT / "system", self.plugin / "system")
        (self.plugin / "scripts/forge").mkdir(parents=True)
        shutil.copy2(HELPER, self.plugin / "scripts/forge/migrate-upstream.py")

    def install(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(INSTALLER), str(self.plugin)],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(self.plugin)},
        )

    def test_malformed_manifest_refuses_without_mutation(self) -> None:
        manifest = self.repo / ".forge-manifest"
        manifest.write_bytes(b"not_plugin_ref: decoy\n")

        result = self.install()

        self.assertEqual(result.returncode, 2)
        self.assertIn("malformed .forge-manifest", result.stderr)
        self.assertEqual({path.name for path in self.repo.iterdir()}, {".git", ".forge-manifest"})

    def test_gitignore_reconciles_by_content_and_effective_postconditions(self) -> None:
        (self.repo / ".gitignore").write_text(
            "# --- forge agent system (legacy) --- #\n"
            "/.tmp/*\n"
            ".worktrees/\n"
            "/AGENT_HALT\n"
            "/AGENT_HALT_*\n"
            "*.local.md\n",
            encoding="utf-8",
        )

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.repo / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(text.count("# --- forge agent system --- #"), 1)
        for line in (self.plugin / "system/template/gitignore-block.txt").read_text().splitlines()[1:]:
            self.assertEqual(text.splitlines().count(line), 1, line)
        tmp = subprocess.run(
            ["git", "check-ignore", "-q", "--", ".forge/tmp"], cwd=self.repo
        )
        history = subprocess.run(
            ["git", "check-ignore", "-q", "--", ".forge/history/"], cwd=self.repo
        )
        self.assertEqual(tmp.returncode, 0)
        self.assertEqual(history.returncode, 1)
        self.assertTrue((self.repo / ".forge/history/migrations").is_dir())

    def test_incomplete_plugin_gitignore_block_is_repaired_by_content(self) -> None:
        (self.repo / ".gitignore").write_text(
            "# owner\n# --- forge agent system --- #\n/.forge/tmp/\n",
            encoding="utf-8",
        )

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.repo / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(text.count("# --- forge agent system --- #"), 1)
        for line in (self.plugin / "system/template/gitignore-block.txt").read_text().splitlines()[1:]:
            self.assertEqual(text.splitlines().count(line), 1)

    def test_existing_duplicate_effective_gitignore_entries_are_deduplicated(self) -> None:
        required = (self.plugin / "system/template/gitignore-block.txt").read_text()
        (self.repo / ".gitignore").write_text(
            "# owner\n# --- forge agent system --- #\n"
            + required
            + "/.forge/tmp/\n.worktrees/\n",
            encoding="utf-8",
        )

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = (self.repo / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines.count("# owner"), 1)
        self.assertEqual(lines.count("# --- forge agent system --- #"), 1)
        for line in required.splitlines()[1:]:
            self.assertEqual(lines.count(line), 1, line)

    def test_crlf_and_trailing_space_ignore_equivalents_form_one_canonical_block(self) -> None:
        required_lines = (
            self.plugin / "system/template/gitignore-block.txt"
        ).read_text().splitlines()
        existing = b"# owner\r\n" + b"\r\n".join(
            line.encode() + (b"   " if index % 2 else b"")
            for index, line in enumerate(required_lines)
        ) + b"\r\n"
        (self.repo / ".gitignore").write_bytes(existing)

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.repo / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# owner\n"))
        self.assertEqual(text.count(required_lines[0]), 1)
        block = text.split(required_lines[0], 1)[1].splitlines()
        for line in required_lines[1:]:
            self.assertEqual(text.splitlines().count(line), 1, line)
            self.assertIn(line, block)

    def test_preexisting_rules_are_relocated_under_distinct_header(self) -> None:
        required_lines = (
            self.plugin / "system/template/gitignore-block.txt"
        ).read_text().splitlines()
        (self.repo / ".gitignore").write_text(
            "# owner\n" + "\n".join(required_lines[1:]) + "\n",
            encoding="utf-8",
        )

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.repo / ".gitignore").read_text(encoding="utf-8")
        header = text.index(required_lines[0])
        for line in required_lines[1:]:
            self.assertGreater(text.index(line), header)
            self.assertEqual(text.splitlines().count(line), 1)

    def test_installer_recognizes_crlf_upstream_codex_signatures(self) -> None:
        (self.repo / ".forge-manifest").write_bytes(b"upstream_commit: old\n")
        codex = self.repo / ".codex"
        codex.mkdir()
        config = (
            b'approval_policy = "on-failure"\r\n'
            b'sandbox_mode = "workspace-write"\r\n'
            b'[agents."code-reviewer"]\r\n'
            b'[agents."review-final"]\r\n'
            b'config_file = "./agents/review-final.toml"\r\n'
            b'[agents."security-auditor"]\r\n'
        )
        hooks = (
            b'{"command":"aggregate-telemetry.sh .tmp/decisions --csv '
            b'.tmp/telemetry-latest.csv"}\r\n'
        )
        (codex / "config.toml").write_bytes(config)
        (codex / "hooks.json").write_bytes(hooks)

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((codex / "config.toml.pre-migration").read_bytes(), config)
        self.assertEqual((codex / "hooks.json.pre-migration").read_bytes(), hooks)
        self.assertIn(b"# forge-managed", (codex / "config.toml").read_bytes())
        self.assertIn(b": 'forge-managed';", (codex / "hooks.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
