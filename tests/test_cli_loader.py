"""Contract tests for the shared CLI test loader (cli split phase 0, bead forge-plugin-95e.1)."""

from __future__ import annotations

import os
import re
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests import _cli_loader

ROOT = Path(__file__).resolve().parents[1]


class CliLoaderTests(unittest.TestCase):
    def test_distinct_names_yield_independent_modules(self) -> None:
        """Two loads under different names are distinct objects with independent globals."""
        first = _cli_loader.load_cli("_cli_loader_test_first")
        second = _cli_loader.load_cli("_cli_loader_test_second")
        self.assertIsNot(first, second)
        self.assertIs(sys.modules["_cli_loader_test_first"], first)
        self.assertIs(sys.modules["_cli_loader_test_second"], second)
        self.assertEqual(first.__file__, str(_cli_loader.CLI_PATH))
        # The spec-required in-memory control-disable pattern stays patchable
        # per module: patching one load never touches the other.
        original = second.MERGE_LIFECYCLE_ACTIVE
        with mock.patch.object(first, "MERGE_LIFECYCLE_ACTIVE", not original):
            self.assertEqual(second.MERGE_LIFECYCLE_ACTIVE, original)
            self.assertNotEqual(first.MERGE_LIFECYCLE_ACTIVE, original)
        # The canonical in-memory control seams remain attributes of each load.
        self.assertTrue(hasattr(first, "REVISION9_STATE_CONTROLS"))
        self.assertTrue(callable(getattr(first, "validate_state", None)))

    def test_cached_loader_returns_the_registered_module(self) -> None:
        loaded = _cli_loader.load_cached("_cli_loader_test_cached", _cli_loader.CLI_PATH)
        again = _cli_loader.load_cached("_cli_loader_test_cached", _cli_loader.CLI_PATH)
        self.assertIs(loaded, again)
        fresh = _cli_loader.load_script("_cli_loader_test_cached_fresh", _cli_loader.CLI_PATH)
        self.assertIsNot(fresh, loaded)

    def test_shim_path_and_package_dir_are_pinned(self) -> None:
        self.assertEqual(_cli_loader.CLI_PATH, ROOT / "scripts" / "forge" / "cli.py")
        self.assertEqual(_cli_loader.CLI_PACKAGE_DIR, ROOT / "scripts" / "forge" / "forge_cli")
        self.assertTrue(_cli_loader.CLI_PATH.is_file())

    def test_no_file_under_the_cli_package_is_executable(self) -> None:
        """The interpreter-loaded package must never enter the executable inventory."""
        package = _cli_loader.CLI_PACKAGE_DIR
        if not package.exists():
            self.skipTest("forge_cli package not yet created (phase 1+)")
        for directory, _dirs, files in os.walk(package):
            for name in files:
                path = Path(directory, name)
                mode = path.stat(follow_symlinks=False).st_mode
                with self.subTest(path=str(path.relative_to(ROOT))):
                    self.assertFalse(stat.S_ISREG(mode) and mode & 0o111)

    def test_every_test_module_loads_the_cli_through_the_shared_loader(self) -> None:
        """No test module keeps a private CLI loader (later phases retarget one place)."""
        offenders: list[str] = []
        for path in sorted(ROOT.glob("tests/test_*.py")):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^def (load_script|load_module)\(", text, flags=re.MULTILINE):
                offenders.append(f"{path.name}: private load_script/load_module definition")
            loads_cli = re.search(r"load_(script|module|cached)\([^)]*CLI_PATH\)", text) is not None
            if loads_cli and "from tests._cli_loader import" not in text:
                offenders.append(f"{path.name}: loads CLI_PATH without the shared loader")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
