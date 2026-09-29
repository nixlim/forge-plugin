"""Focused tests for working-tree drift hidden from ordinary ``git diff``."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._cli_loader import package_module

REPOSITORY = package_module("chain_core._repository")
Repository = REPOSITORY.Repository
FLAG_SUFFIX = "index flag: git diff cannot compare it; clear the flag, then restage)"


def flagged(path: str, name: str) -> str:
    return f"{path} ({name} {FLAG_SUFFIX}"


class TreeIndexDriftFlagsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-tree-index-drift-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository_number = 0
        self.git_environment = dict(
            os.environ,
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
        )

    def git(self, repo: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            env=self.git_environment,
            check=False,
            capture_output=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            result.stdout.decode("utf-8", "replace")
            + result.stderr.decode("utf-8", "replace"),
        )
        return result

    def make_repo(self, files: dict[str, str]) -> Path:
        self.repository_number += 1
        repo = self.root / f"repo-{self.repository_number}"
        repo.mkdir()
        self.git(repo, "init", "-q")
        self.git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
        self.git(repo, "config", "user.name", "Forge Test")
        self.git(repo, "config", "user.email", "forge-test@example.invalid")
        for relative, content in files.items():
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        self.git(repo, "add", "--all")
        tree = self.git(repo, "write-tree").stdout.decode("ascii").strip()
        commit = self.git(repo, "commit-tree", tree, "-m", "fixture base")
        self.git(repo, "update-ref", "HEAD", commit.stdout.decode("ascii").strip())
        return repo

    def test_assume_unchanged_is_reported_and_parser_disable_reopens_bypass(
        self,
    ) -> None:
        path = "tests/test_a.py"
        repo = self.make_repo({path: "def test_a():\n    assert True\n"})
        (repo / path).write_text("def test_a():\n    pass\n", encoding="utf-8")
        self.git(repo, "add", "--", path)
        self.git(repo, "update-index", "--assume-unchanged", path)
        (repo / path).write_text("def test_a():\n    assert True\n", encoding="utf-8")
        repository = Repository(repo)

        self.assertEqual(
            repository.tree_index_drift([path]), [flagged(path, "assume-unchanged")]
        )
        with mock.patch.object(REPOSITORY, "_flagged_index_labels", return_value=[]):
            self.assertEqual(repository.tree_index_drift([path]), [])

    def test_skip_worktree_deletion_is_reported_and_parser_disable_reopens_bypass(
        self,
    ) -> None:
        path = "tests/test_b.py"
        repo = self.make_repo({path: "def test_b():\n    pass\n"})
        self.git(repo, "update-index", "--skip-worktree", path)
        (repo / path).unlink()
        repository = Repository(repo)

        self.assertEqual(
            repository.tree_index_drift([path]), [flagged(path, "skip-worktree")]
        )
        with mock.patch.object(REPOSITORY, "_flagged_index_labels", return_value=[]):
            self.assertEqual(repository.tree_index_drift([path]), [])

    def test_both_flags_are_reported(self) -> None:
        path = "tests/test_c.py"
        repo = self.make_repo({path: "def test_c():\n    pass\n"})
        self.git(repo, "update-index", "--assume-unchanged", path)
        self.git(repo, "update-index", "--skip-worktree", path)
        (repo / path).write_text("def test_c():\n    assert True\n", encoding="utf-8")

        self.assertEqual(
            Repository(repo).tree_index_drift([path]),
            [flagged(path, "assume-unchanged+skip-worktree")],
        )

    def test_flag_is_reported_when_working_bytes_equal_index(self) -> None:
        path = "equal.txt"
        repo = self.make_repo({path: "equal\n"})
        self.git(repo, "update-index", "--assume-unchanged", path)

        self.assertEqual(
            Repository(repo).tree_index_drift([path]),
            [flagged(path, "assume-unchanged")],
        )

    def test_unflagged_clean_modified_and_empty_paths_keep_existing_behavior(self) -> None:
        path = "plain.txt"
        repo = self.make_repo({path: "base\n"})
        repository = Repository(repo)
        (repo / path).write_text("modified\n", encoding="utf-8")
        self.assertEqual(repository.tree_index_drift([path]), [path])

        (repo / path).write_text("base\n", encoding="utf-8")
        self.assertEqual(repository.tree_index_drift([path]), [])
        with mock.patch.object(repository, "git") as git:
            self.assertEqual(repository.tree_index_drift([]), [])
        git.assert_not_called()

    def test_flagged_path_outside_requested_paths_is_not_reported(self) -> None:
        repo = self.make_repo({"inside.txt": "inside\n", "outside.txt": "outside\n"})
        self.git(repo, "update-index", "--assume-unchanged", "outside.txt")
        (repo / "outside.txt").write_text("hidden\n", encoding="utf-8")

        self.assertEqual(Repository(repo).tree_index_drift(["inside.txt"]), [])

    def test_fsmonitor_hidden_modification_and_disable_seam(self) -> None:
        repo = self.make_repo({"f": "base\n"})
        hook = repo / "fsmonitor.sh"
        hook.write_text('#!/bin/sh\nprintf \'%s\\0\' "$2"\n', encoding="utf-8")
        hook.chmod(0o700)
        self.git(repo, "config", "core.fsmonitor", str(hook))
        self.git(repo, "update-index", "--fsmonitor")
        self.git(repo, "status", "--short")
        (repo / "f").write_text("modified\n", encoding="utf-8")
        if self.git(repo, "diff", "--name-only", "--", "f").stdout:
            self.skipTest("installed Git does not reproduce fsmonitor-hidden drift")
        repository = Repository(repo)

        self.assertEqual(repository.tree_index_drift(["f"]), ["f"])
        with mock.patch.object(REPOSITORY, "_DRIFT_NO_FSMONITOR", ()):
            self.assertEqual(repository.tree_index_drift(["f"]), [])

    def test_literal_pathspecs_limit_drift_and_disable_seam(self) -> None:
        literal = "g/t[1].py"
        matched = "g/t1.py"
        repo = self.make_repo({literal: "base\n", matched: "base\n"})
        (repo / literal).write_text("literal modified\n", encoding="utf-8")
        (repo / matched).write_text("matched modified\n", encoding="utf-8")
        repository = Repository(repo)

        self.assertEqual(repository.tree_index_drift([literal]), [literal])
        with mock.patch.object(REPOSITORY, "_DRIFT_LITERAL_PATHSPECS", ()):
            self.assertEqual(repository.tree_index_drift([literal]), [matched, literal])

    def test_flag_parser_handles_tags_duplicates_and_malformed_records(self) -> None:
        raw = (
            b"H cached\0M conflict\0M conflict\0"
            b"h assumed\0m assumed-unmerged\0S skipped\0s both\0"
            b"h first\0S first\0Q mystery\0h\0hx\0\0"
        )

        self.assertEqual(
            REPOSITORY._flagged_index_labels(raw),
            [
                flagged("assumed", "assume-unchanged"),
                flagged("assumed-unmerged", "assume-unchanged"),
                flagged("skipped", "skip-worktree"),
                flagged("both", "assume-unchanged+skip-worktree"),
                flagged("first", "assume-unchanged"),
                flagged("mystery", "unrecognised index flag Q"),
                "h (unrecognised index flag)",
                "hx (unrecognised index flag)",
            ],
        )


if __name__ == "__main__":
    unittest.main()
