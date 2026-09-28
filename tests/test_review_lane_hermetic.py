"""Regression guard for review tests that cross the provider-launch boundary."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRIPPED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
REVIEW_LAUNCH_TESTS = (
    "tests.test_fresh_reviewer_cli.FreshReviewerCLIProvenanceTests."
    "test_review_final_package_contains_complete_fresh_material",
)


class ReviewLaneHermeticTests(unittest.TestCase):
    def test_review_launch_tests_pass_without_installed_providers(self) -> None:
        for provider in ("claude", "codex"):
            self.assertIsNone(shutil.which(provider, path=STRIPPED_PATH))
        environment = dict(
            os.environ, PATH=STRIPPED_PATH, PYTHONDONTWRITEBYTECODE="1"
        )
        for target in REVIEW_LAUNCH_TESTS:
            with self.subTest(target=target):
                process = subprocess.run(
                    [sys.executable, "-m", "unittest", target],
                    cwd=ROOT,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=120,
                    check=False,
                )
                self.assertEqual(
                    process.returncode,
                    0,
                    f"{target} failed under stripped PATH:\n{process.stdout[-8000:]}",
                )


if __name__ == "__main__":
    unittest.main()
