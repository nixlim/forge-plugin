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
# Names that live in forge_cli and must be patched there, never on a CLI copy.
MOVED_NAMES = frozenset({
    "ReasonCode", "V2ReasonCode", "Revision9ReasonCode", "OUTPUT_SCHEMA", "REVISION9_OUTPUT_SCHEMA",
    "ENVELOPE_KEYS", "Outcome", "Refusal", "FrozenError",
    "sha256_bytes", "REGION_ORDER", "Policy", "PolicyError", "_dedent_fenced_cell", "_fence_lines",
    "_fenced_shell_cells", "_parse_changelog", "_parse_invariants", "_parse_regions", "parse_policy",
    "COMMAND_TIMEOUT_SECONDS", "OUTPUT_CAP_BYTES", "ProcessResult", "_kill_process_group", "utc_now",
    "run_bounded", "_REQUIRED_REVISION9_STATE_CONTROLS", "REVISION9_STATE_CONTROLS",
    "MERGE_LIFECYCLE_ACTIVE", "SCRIPT_DIR", "PLUGIN_ROOT", "_COORDINATION_MODULE_CACHE",
    "_COORDINATION_MODULE_LOCK", "_coordination_modules", "_fast_mechanical_skips",
})


class CliLoaderTests(unittest.TestCase):
    def test_distinct_names_yield_independent_modules(self) -> None:
        """Two loads under different names are distinct objects with independent globals."""
        first = _cli_loader.load_cli("_cli_loader_test_first")
        second = _cli_loader.load_cli("_cli_loader_test_second")
        self.assertIsNot(first, second)
        self.assertIs(sys.modules["_cli_loader_test_first"], first)
        self.assertIs(sys.modules["_cli_loader_test_second"], second)
        self.assertEqual(first.__file__, str(_cli_loader.CLI_PATH))
        # Shim-resident names stay independently patchable per module: patching one
        # load never touches the other (moved names are canonical instead; see below).
        original = second.INACTIVE_SECONDS
        with mock.patch.object(first, "INACTIVE_SECONDS", original + 1):
            self.assertEqual(second.INACTIVE_SECONDS, original)
            self.assertEqual(first.INACTIVE_SECONDS, original + 1)
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
        shared_import = re.compile(r"^from tests\._cli_loader import ", flags=re.MULTILINE)
        for path in sorted(ROOT.glob("tests/test_*.py")):
            if path.name == Path(__file__).name:
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"^def (load_script|load_module)\(", text, flags=re.MULTILINE):
                offenders.append(f"{path.name}: private load_script/load_module definition")
            # Any in-process load of the shim: through a loader call naming the CLI
            # path constant, or a direct spec_from_file_location on cli.py.
            loads_cli = (
                re.search(r"load_(script|module|cached)\(\s*[^)]*\b(CLI_PATH|CLI)\s*\)", text) is not None
                or re.search(r"spec_from_file_location\([^)]*cli\.py", text) is not None
            )
            if loads_cli and shared_import.search(text) is None:
                offenders.append(f"{path.name}: loads cli.py without the shared loader")
            # A moved name patched on a per-module CLI copy would be silently ineffective:
            # the shim reads runtime controls by attribute and the package modules are
            # process-global, so such patches must target the canonical module.
            for match in re.finditer(
                r"patch\.object\(\s*([A-Za-z_][A-Za-z_0-9.]*)\s*,\s*\"([A-Za-z_0-9]+)\"", text
            ):
                target, name = match.group(1), match.group(2)
                canonical = any(token in target.lower() for token in ("runtime", "policy", "envelope"))
                if name in MOVED_NAMES and not canonical:
                    offenders.append(f"{path.name}: patches moved name {name} on {target}")
        self.assertEqual(offenders, [])

    def test_runtime_controls_are_canonical_and_forwarded_by_the_shim(self) -> None:
        """Phase 2a: the shim reads runtime controls by attribute and forwards reads (PEP 562)."""
        runtime = _cli_loader.package_module("runtime")
        cli = _cli_loader.load_cli("_cli_loader_test_runtime")
        other = _cli_loader.load_cli("_cli_loader_test_runtime_other")
        for name in runtime.__all__:
            with self.subTest(name=name):
                self.assertIs(getattr(cli, name), getattr(runtime, name))
        self.assertNotIn("utc_now", vars(cli))
        with self.assertRaises(AttributeError):
            getattr(cli, "no_such_runtime_control_xyz")
        # One patch on the canonical module is observed by every loaded shim.
        import datetime as dt
        fixed = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)
        with mock.patch.object(runtime, "utc_now", lambda: fixed):
            self.assertEqual(cli.iso_z(), "2026-01-02T03:04:05Z")
            self.assertEqual(other.iso_z(), "2026-01-02T03:04:05Z")
            self.assertIs(cli.utc_now(), fixed)
        with mock.patch.object(runtime, "MERGE_LIFECYCLE_ACTIVE", True):
            self.assertIs(cli.MERGE_LIFECYCLE_ACTIVE, True)
            self.assertIs(other.MERGE_LIFECYCLE_ACTIVE, True)
        self.assertIs(cli.MERGE_LIFECYCLE_ACTIVE, False)
        # The spec-required in-memory disable of a Revision-9 state control still works
        # through the canonical module.
        with mock.patch.object(
            runtime, "REVISION9_STATE_CONTROLS", runtime.REVISION9_STATE_CONTROLS - {"run-binding-shape"}
        ):
            self.assertNotIn("run-binding-shape", cli.REVISION9_STATE_CONTROLS)
        self.assertEqual(runtime.SCRIPT_DIR, _cli_loader.SCRIPTS_DIR)
        self.assertEqual(runtime.PLUGIN_ROOT, ROOT)

    def test_package_modules_are_canonical_and_reexported_by_the_shim(self) -> None:
        """Phase 1: envelope and policy live in forge_cli; the shim re-exports the same objects."""
        envelope = _cli_loader.package_module("envelope")
        policy = _cli_loader.package_module("policy")
        cli = _cli_loader.load_cli("_cli_loader_test_reexport")
        other = _cli_loader.load_cli("_cli_loader_test_reexport_other")
        for name in ("ReasonCode", "V2ReasonCode", "Refusal", "FrozenError", "Outcome", "OUTPUT_SCHEMA", "REVISION9_OUTPUT_SCHEMA"):
            with self.subTest(name=name):
                self.assertIs(getattr(cli, name), getattr(envelope, name))
                self.assertIs(getattr(other, name), getattr(envelope, name))
        for name in ("parse_policy", "Policy", "PolicyError", "_fence_lines", "_dedent_fenced_cell", "sha256_bytes"):
            with self.subTest(name=name):
                self.assertIs(getattr(cli, name), getattr(policy, name))
        self.assertIs(_cli_loader.package_module("policy"), policy)
        # A patch on the canonical module is what parse_policy observes.
        with mock.patch.object(policy, "_dedent_fenced_cell", lambda cell, prefix: "PATCHED"):
            self.assertEqual(policy._fenced_shell_cells.__globals__["_dedent_fenced_cell"]("x", ""), "PATCHED")


if __name__ == "__main__":
    unittest.main()
