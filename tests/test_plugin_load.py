from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PluginLoadContractTests(unittest.TestCase):
    def test_plugin_metadata_and_exact_seven_skill_surfaces(self) -> None:
        plugin = json.loads(
            (ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
        )
        marketplace = json.loads(
            (ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plugin["name"], "forge")
        self.assertEqual(marketplace["plugins"][0]["name"], "forge")
        self.assertEqual(marketplace["plugins"][0]["source"], "./")

        skill_root = ROOT / "skills"
        skill_directories = sorted(
            path.name for path in skill_root.iterdir() if path.is_dir()
        )
        self.assertEqual(
            skill_directories,
            [
                "commit",
                "drift",
                "init",
                "orchestrate",
                "report",
                "workflow",
                "worktree-merge",
            ],
        )
        for name in skill_directories:
            contents = (skill_root / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(contents.startswith("---\n"), name)
            self.assertRegex(contents, r"(?m)^name: [^\n]+$", name)
            self.assertIn("\ndescription:", contents, name)
        self.assertFalse((ROOT / "commands").exists())

    def test_hooks_json_discovers_commit_invariant_stop_and_session_hooks(self) -> None:
        hook_file = ROOT / "hooks" / "hooks.json"
        loaded = json.loads(hook_file.read_text(encoding="utf-8"))
        self.assertEqual(set(loaded), {"hooks"})
        self.assertEqual(
            set(loaded["hooks"]),
            {"PreToolUse", "PostToolUse", "Stop", "SessionStart"},
        )

        pretool = loaded["hooks"]["PreToolUse"]
        self.assertEqual(
            pretool,
            [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/forge/commit-guard.sh",
                        }
                    ],
                }
            ],
        )
        posttool = loaded["hooks"]["PostToolUse"]
        self.assertEqual(
            posttool,
            [
                {
                    "matcher": "Edit|Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "${CLAUDE_PLUGIN_ROOT}/scripts/forge/"
                                "invariant-guard.sh"
                            ),
                        }
                    ],
                }
            ],
        )
        stop = loaded["hooks"]["Stop"]
        self.assertEqual(
            stop,
            [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "${CLAUDE_PLUGIN_ROOT}/scripts/forge/aggregate-telemetry.sh "
                                ".forge/tmp/decisions --csv "
                                ".forge/tmp/telemetry-latest.csv"
                            ),
                        },
                        {
                            "type": "command",
                            "command": (
                                "${CLAUDE_PLUGIN_ROOT}/scripts/forge/"
                                "drift-staleness.sh"
                            ),
                        },
                    ],
                }
            ],
        )
        session_start = loaded["hooks"]["SessionStart"]
        self.assertEqual(
            session_start,
            [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "${CLAUDE_PLUGIN_ROOT}/scripts/forge/"
                                "drift-staleness.sh"
                            ),
                        }
                    ],
                }
            ],
        )

        guard = ROOT / "scripts/forge/commit-guard.sh"
        self.assertTrue(stat.S_IMODE(guard.stat().st_mode) & stat.S_IXUSR)
        invariant_guard = ROOT / "scripts/forge/invariant-guard.sh"
        self.assertTrue(
            stat.S_IMODE(invariant_guard.stat().st_mode) & stat.S_IXUSR
        )

        for script_name in ("aggregate-telemetry.sh", "drift-staleness.sh"):
            script = ROOT / "scripts/forge" / script_name
            self.assertTrue(script.is_file(), script_name)
            self.assertTrue(stat.S_IMODE(script.stat().st_mode) & stat.S_IXUSR)

    def test_plugin_stop_and_session_hooks_are_inert_without_forge_manifest(self) -> None:
        loaded = json.loads(
            (ROOT / "hooks/hooks.json").read_text(encoding="utf-8")
        )["hooks"]
        commands = [
            (event, hook["command"])
            for event in ("Stop", "SessionStart")
            for group in loaded[event]
            for hook in group["hooks"]
        ]
        self.assertEqual(len(commands), 3)
        self.assertTrue(all("&&" not in command for _, command in commands))
        self.assertTrue(all(";" not in command for _, command in commands))

        def snapshot_tree(cwd: Path) -> list[tuple[str, int, int, bytes | str | None]]:
            snapshot = []
            for path in sorted(cwd.rglob("*")):
                metadata = path.lstat()
                if path.is_symlink():
                    contents: bytes | str | None = os.readlink(path)
                elif path.is_file():
                    contents = path.read_bytes()
                else:
                    contents = None
                snapshot.append(
                    (
                        path.relative_to(cwd).as_posix(),
                        metadata.st_mode,
                        metadata.st_mtime_ns,
                        contents,
                    )
                )
            return snapshot

        def assert_hooks_are_inert(cwd: Path, scenario: str) -> None:
            env = os.environ.copy()
            env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
            before = snapshot_tree(cwd)
            for command_index, (event, command) in enumerate(commands):
                expanded = command.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT))
                with self.subTest(
                    scenario=scenario,
                    event=event,
                    command_index=command_index,
                ):
                    result = subprocess.run(
                        shlex.split(expanded),
                        cwd=cwd,
                        env=env,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, expanded)
                    self.assertEqual(result.stdout, "", expanded)
                    self.assertEqual(result.stderr, "", expanded)
                    self.assertEqual(snapshot_tree(cwd), before, expanded)

        with tempfile.TemporaryDirectory() as temporary_directory:
            cwd = Path(temporary_directory)
            assert_hooks_are_inert(cwd, "outside git")

        with tempfile.TemporaryDirectory() as temporary_directory:
            cwd = Path(temporary_directory)
            for args in (
                ("init",),
                ("config", "user.name", "Forge Tests"),
                ("config", "user.email", "forge-tests@example.invalid"),
                ("config", "commit.gpgsign", "false"),
            ):
                result = subprocess.run(
                    ["git", *args],
                    cwd=cwd,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            (cwd / "tracked.txt").write_text("committed\n", encoding="utf-8")
            for args in (("add", "tracked.txt"), ("commit", "-m", "initial")):
                result = subprocess.run(
                    ["git", *args],
                    cwd=cwd,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((cwd / ".forge-manifest").exists())
            assert_hooks_are_inert(cwd, "git repository without manifest")


if __name__ == "__main__":
    unittest.main()
