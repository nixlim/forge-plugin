from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERBATIM_CODEX_PATHS = (
    "agents/implementer.toml",
    "agents/plan.toml",
    "agents/review-cheap.toml",
    "config.toml",
    "hooks.json",
    "prompts/implementer.md",
    "prompts/plan.md",
    "prompts/review-cheap.md",
    "rules/forge.rules",
)

# Deliberately excluded transformed installer outputs: forge-project.md receives token rendering
# and region merging; AGENTS.md receives a managed-block splice; CLAUDE.md receives an appended
# import; and .gitignore receives block reconciliation and appending.


def assert_bytes_equal(
    test_case: unittest.TestCase, template: bytes, installed: bytes
) -> None:
    test_case.assertEqual(installed, template)


class InstalledPromptSyncTests(unittest.TestCase):
    def test_tracked_verbatim_codex_copies_match_templates(self) -> None:
        for relative in VERBATIM_CODEX_PATHS:
            with self.subTest(relative=relative):
                template = (ROOT / "system/codex" / relative).read_bytes()
                installed = (ROOT / ".codex" / relative).read_bytes()
                assert_bytes_equal(self, template, installed)

    def test_each_equality_check_rejects_a_one_byte_installed_mutation(self) -> None:
        for relative in VERBATIM_CODEX_PATHS:
            with self.subTest(relative=relative):
                template = (ROOT / "system/codex" / relative).read_bytes()
                installed = (ROOT / ".codex" / relative).read_bytes()
                self.assertTrue(installed)
                mutated = bytes([installed[0] ^ 1]) + installed[1:]

                with self.assertRaises(AssertionError):
                    assert_bytes_equal(self, template, mutated)


if __name__ == "__main__":
    unittest.main()
