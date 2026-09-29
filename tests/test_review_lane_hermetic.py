"""Regression guard for review tests that cross the provider-launch boundary."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIRS = (
    "/usr/local/sbin",
    "/usr/local/bin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
)
REVIEW_LAUNCH_TESTS = (
    "tests.test_fresh_reviewer_cli.FreshReviewerCLIProvenanceTests."
    "test_review_final_package_contains_complete_fresh_material",
)


def provider_free_path(
    directories: tuple[str, ...],
    providers: tuple[str, ...] = ("claude", "codex"),
) -> tuple[str, list[str]]:
    kept = []
    dropped = []
    for directory in directories:
        if any(shutil.which(provider, path=directory) is not None for provider in providers):
            dropped.append(directory)
        else:
            kept.append(directory)
    return os.pathsep.join(kept), dropped


class ReviewLaneHermeticTests(unittest.TestCase):
    def test_review_launch_tests_pass_without_installed_providers(self) -> None:
        provider_path, dropped = provider_free_path(CANDIDATE_DIRS)
        for provider in ("claude", "codex"):
            self.assertIsNone(shutil.which(provider, path=provider_path))
        self.assertIsNotNone(
            shutil.which("git", path=provider_path),
            "a provider CLI shares a directory with git "
            f"({', '.join(dropped)}); install claude/codex outside the system bin "
            "directories, or run this guard on a host where they are separate",
        )
        environment = dict(
            os.environ, PATH=provider_path, PYTHONDONTWRITEBYTECODE="1"
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

    def test_provider_free_path_drops_provider_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider_dir = root / "provider-bin"
            git_dir = root / "git-bin"
            provider_dir.mkdir()
            git_dir.mkdir()
            for executable in (provider_dir / "claude", git_dir / "git"):
                executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                executable.chmod(0o755)
            directories = (str(provider_dir), str(git_dir))

            def assert_contract() -> None:
                path, dropped = provider_free_path(directories)
                self.assertEqual(path, str(git_dir))
                self.assertEqual(dropped, [str(provider_dir)])

            assert_contract()
            with mock.patch.object(shutil, "which", return_value=None):
                with self.assertRaises(AssertionError):
                    assert_contract()


if __name__ == "__main__":
    unittest.main()
