from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_SECTION = re.compile(
    r"^\[project\]\s*$\n(?P<body>.*?)(?=^\[|\Z)", flags=re.MULTILINE | re.DOTALL
)
PROJECT_VERSION = re.compile(r'^version\s*=\s*"([^"]+)"\s*$', flags=re.MULTILINE)
RELEASE_HEADING = re.compile(
    r"^## \[(\d+\.\d+\.\d+)\](?: .*)?$", flags=re.MULTILINE
)


class VersionTests(unittest.TestCase):
    def test_plugin_manifest_omits_version(self) -> None:
        plugin = json.loads(
            (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        self.assertNotIn("version", plugin)

    def test_marketplace_plugin_omits_version(self) -> None:
        marketplace = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )

        self.assertNotIn("version", marketplace["plugins"][0])

    def test_project_version_matches_newest_changelog_heading(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        project_section = PROJECT_SECTION.search(pyproject)
        if project_section is None:
            self.fail("pyproject.toml must contain a [project] table")
        project_version = PROJECT_VERSION.search(project_section.group("body"))
        if project_version is None:
            self.fail("pyproject.toml [project] must declare version")
        release_heading = RELEASE_HEADING.search(changelog)
        if release_heading is None:
            self.fail("CHANGELOG.md must contain a release heading")

        self.assertEqual(project_version.group(1), release_heading.group(1))


if __name__ == "__main__":
    unittest.main()
