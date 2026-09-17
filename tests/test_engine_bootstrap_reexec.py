"""The merge bootstrap child re-execs the shim resolved from ``runtime.__file__`` (split E1)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from tests._cli_loader import package_module

ROOT = Path(__file__).resolve().parents[1]
ENGINE = package_module("engine")
RUNTIME = package_module("runtime")


def _admission() -> object:
    return ENGINE.MergeAdmission(
        repository=ROOT,
        worktree=ROOT,
        worktree_identity={"git_dir": str(ROOT / ".git")},
        branch="main",
        target={},
        candidate_head="0" * 40,
        policy=None,
        declared_tier=None,
        run_task=None,
        status_output_digest="0" * 64,
    )


class BootstrapReexecTargetTests(unittest.TestCase):
    def test_child_argv_targets_the_shim_entry_point_through_runtime_script_dir(self) -> None:
        self.assertEqual(RUNTIME.SCRIPT_DIR, ROOT / "scripts" / "forge")
        argv = ENGINE._merge_bootstrap_child_argv(
            _admission(), fetch_argv=["git", "fetch"], remote_tip=None
        )
        self.assertEqual(argv[3], str(Path(RUNTIME.__file__).resolve().parents[1] / "cli.py"))
        self.assertEqual(argv[3], str(ROOT / "scripts" / "forge" / "cli.py"))
        self.assertTrue(Path(argv[3]).is_file())

    def test_child_argv_ignores_a_patched_script_dir_like_the_original(self) -> None:
        # Fixtures patch runtime.SCRIPT_DIR to a helpers directory that holds no cli.py; the
        # re-exec target must keep resolving to the real shim, exactly as the __file__ form did.
        with mock.patch.object(RUNTIME, "SCRIPT_DIR", Path("/nonexistent/helpers")):
            argv = ENGINE._merge_bootstrap_child_argv(
                _admission(), fetch_argv=[], remote_tip="1" * 40
            )
        self.assertEqual(argv[3], str(ROOT / "scripts" / "forge" / "cli.py"))
        self.assertEqual(argv[3], str(Path(RUNTIME.__file__).resolve().parents[1] / "cli.py"))


if __name__ == "__main__":
    unittest.main()
