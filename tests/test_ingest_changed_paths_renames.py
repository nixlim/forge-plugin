"""Regression coverage for rename sources in retrospective ingest proofs."""

from __future__ import annotations

import inspect
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests import test_revision9_matrix as MATRIX
from tests._cli_loader import package_module

MERGE_INGEST = package_module("chain_core._ingest_merge")
COMMIT_CHAIN = package_module("chain_core._commit_chain")
RUNTIME = package_module("runtime")
JOURNAL = RUNTIME._coordination_modules()[2]
TASK_FILES = ("docs/**",)


def _nul_paths(output: bytes) -> tuple[str, ...]:
    return tuple(item.decode("utf-8") for item in output.split(b"\0") if item)


def _within_task_scope(paths: tuple[str, ...]) -> bool:
    return all(
        any(JOURNAL.pathspec_contained(path, pattern) for pattern in TASK_FILES)
        for path in paths
    )


class LandedRenameNamesTests(unittest.TestCase):
    """Exercise each name-list helper against a real exact rename."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-ingest-renames-")
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name) / "repo"
        self.repository.mkdir()
        self.environment = {
            "PATH": os.environ.get("PATH", os.defpath),
            "GIT_AUTHOR_NAME": "Forge Rename Fixture",
            "GIT_AUTHOR_EMAIL": "forge-rename@example.invalid",
            "GIT_COMMITTER_NAME": "Forge Rename Fixture",
            "GIT_COMMITTER_EMAIL": "forge-rename@example.invalid",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "LC_ALL": "C",
        }
        self.git("init", "--quiet")
        (self.repository / "scripts").mkdir()
        (self.repository / "docs").mkdir()
        (self.repository / "scripts" / "tool.py").write_text(
            "VALUE = 1\nSECOND = 2\nTHIRD = 3\n", encoding="utf-8"
        )
        self.git("add", "scripts/tool.py")
        self.git("commit", "--quiet", "-m", "fixture base")
        self.base = self.git("rev-parse", "HEAD")
        self.git("mv", "scripts/tool.py", "docs/tool.md")
        self.git("commit", "--quiet", "-m", "rename tool into docs")
        self.head = self.git("rev-parse", "HEAD")
        plain_names = self.git("diff", "--name-only", f"{self.base}...{self.head}")
        self.assertEqual(plain_names.splitlines(), ["docs/tool.md"])

    def git(self, *argv: str) -> str:
        result = subprocess.run(
            ["git", *argv],
            cwd=self.repository,
            env=self.environment,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def assert_helper_covers_rename_source(
        self,
        module: object,
        helper: object,
        *arguments: object,
    ) -> None:
        with mock.patch.dict(os.environ, self.environment, clear=True):
            observed = helper(self.repository, *arguments)
        self.assertEqual(observed.returncode, 0)
        paths = _nul_paths(observed.stdout)
        self.assertEqual(set(paths), {"docs/tool.md", "scripts/tool.py"})
        self.assertFalse(_within_task_scope(paths))
        self.assertFalse(JOURNAL.pathspec_contained("scripts/tool.py", "docs/**"))

        real_run = subprocess.run

        def run_with_rename_detection(
            argv: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[bytes]:
            weakened_argv = [item for item in argv if item != "--no-renames"]
            return real_run(weakened_argv, **kwargs)

        with mock.patch.dict(
            os.environ, self.environment, clear=True
        ), mock.patch.object(
            module.subprocess,
            "run",
            side_effect=run_with_rename_detection,
        ) as weakened_run:
            weakened = helper(self.repository, *arguments)
        weakened_run.assert_called_once()
        self.assertIn("--no-renames", weakened_run.call_args.args[0])
        weakened_paths = _nul_paths(weakened.stdout)
        self.assertEqual(weakened_paths, ("docs/tool.md",))
        self.assertTrue(_within_task_scope(weakened_paths))

    def test_merge_and_commit_helpers_keep_both_rename_sides_in_proof_16(self) -> None:
        self.assert_helper_covers_rename_source(
            MERGE_INGEST,
            MERGE_INGEST._landed_range_names,
            f"{self.base}...{self.head}",
        )
        self.assert_helper_covers_rename_source(
            COMMIT_CHAIN,
            COMMIT_CHAIN._landed_commit_names,
            self.base,
            self.head,
        )


class IngestRenameWiringTests(unittest.TestCase):
    """Prove the merge verifier consumes the helper and both verifiers are wired."""

    def run_matrix_case(
        self,
        helper_effect: object | None = None,
    ) -> tuple[unittest.TestResult, mock.Mock, dict[str, str], float]:
        case = MATRIX.Revision9MergeIngestArchiveMatrixTests(
            "test_real_merge_ingest_closes_and_renders_deterministically"
        )
        original_build = case.build_real_merge_package
        original_helper = MERGE_INGEST._landed_range_names
        observed_package: dict[str, str] = {}

        def capture_package(
        ) -> tuple[bytes, bytes, bytes, str, str, tuple[object, ...]]:
            package = original_build()
            observed_package["candidate_head"] = package[3]
            observed_package["remote_tip"] = package[4]
            return package

        helper_patch = (
            mock.patch.object(MERGE_INGEST, "_landed_range_names", wraps=original_helper)
            if helper_effect is None
            else mock.patch.object(
                MERGE_INGEST,
                "_landed_range_names",
                side_effect=helper_effect,
            )
        )
        authority = MATRIX.ARCHIVE._CLI_INGEST_AUTHORITY
        result = unittest.TestResult()
        with mock.patch.object(
            case,
            "build_real_merge_package",
            side_effect=capture_package,
        ), mock.patch.object(
            MATRIX.ARCHIVE, "_CLI_INGEST_AUTHORITY", authority
        ), helper_patch as observed_helper:
            started = time.monotonic()
            case.run(result)
            elapsed = time.monotonic() - started
        expected_range = (
            f"{observed_package['remote_tip']}..."
            f"{observed_package['candidate_head']}"
        )
        observed_helper.assert_any_call(case.repo.resolve(), expected_range)
        return result, observed_helper, observed_package, elapsed

    def test_real_merge_ingest_uses_names_helper_and_rejects_injected_path(
        self,
    ) -> None:
        passing, _observed, _package, passing_elapsed = self.run_matrix_case()
        self.assertTrue(
            passing.wasSuccessful(),
            {"errors": passing.errors, "failures": passing.failures},
        )

        original_helper = MERGE_INGEST._landed_range_names

        def add_out_of_scope_path(
            repository: Path, revision_range: str
        ) -> subprocess.CompletedProcess[bytes]:
            landed = original_helper(repository, revision_range)
            return subprocess.CompletedProcess(
                args=landed.args,
                returncode=landed.returncode,
                stdout=(landed.stdout or b"") + b"scripts/tool.py\0",
                stderr=landed.stderr,
            )

        failing, _observed, _package, failing_elapsed = self.run_matrix_case(
            add_out_of_scope_path
        )
        self.assertEqual(failing.errors, [], failing.errors)
        self.assertEqual(len(failing.failures), 1, failing.failures)
        print(
            "nested revision9 merge-ingest wiring timing: "
            f"pass={passing_elapsed:.3f}s disable={failing_elapsed:.3f}s"
        )

    def test_ingest_verifier_sources_call_only_the_extracted_name_helpers(self) -> None:
        merge_source = inspect.getsource(
            MERGE_INGEST._verify_and_build_merge_ingest_records
        )
        commit_source = inspect.getsource(COMMIT_CHAIN._verify_and_build_ingest_records)
        self.assertIn("_landed_range_names(", merge_source)
        self.assertNotIn('"--name-only"', merge_source)
        self.assertIn("_landed_commit_names(", commit_source)
        self.assertNotIn('"--name-only"', commit_source)


if __name__ == "__main__":
    unittest.main()
