from __future__ import annotations

import json
import stat
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PluginLoadContractTests(unittest.TestCase):
    def test_plugin_metadata_and_exact_six_skill_surfaces(self) -> None:
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
            ["commit", "init", "orchestrate", "report", "workflow", "worktree-merge"],
        )
        for name in skill_directories:
            contents = (skill_root / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(contents.startswith("---\n"), name)
            self.assertRegex(contents, r"(?m)^name: [^\n]+$", name)
            self.assertIn("\ndescription:", contents, name)
        self.assertFalse((ROOT / "commands").exists())

    def test_hooks_json_discovers_exact_pretooluse_and_stop_hooks(self) -> None:
        hook_file = ROOT / "hooks" / "hooks.json"
        loaded = json.loads(hook_file.read_text(encoding="utf-8"))
        self.assertEqual(set(loaded), {"hooks"})
        self.assertEqual(set(loaded["hooks"]), {"PreToolUse", "Stop"})

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
                        }
                    ],
                }
            ],
        )

        guard = ROOT / "scripts/forge/commit-guard.sh"
        self.assertTrue(stat.S_IMODE(guard.stat().st_mode) & stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
