"""Focused tests for scripts/check_file_length.py (the size-budget control)."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_file_length", ROOT / "scripts" / "check_file_length.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["check_file_length"] = MODULE
SPEC.loader.exec_module(MODULE)


def _python_file(directory: Path, name: str, code_lines: int) -> Path:
    path = directory / name
    body = ["# comment-only lines and blanks do not count", ""]
    body.extend(f"value_{index} = {index}" for index in range(code_lines))
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


class CheckFileLengthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # resolve(): the hook normalises absolute paths lexically against os.getcwd(),
        # so a symlinked TMPDIR (macOS /var -> /private/var) must not skew the key.
        self.root = Path(self.tmp.name).resolve()
        self.previous_cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.previous_cwd)
        _python_file(self.root, "grown.py", 12)
        _python_file(self.root, "same.py", 10)
        _python_file(self.root, "small.py", 3)
        (self.root / ".refactor-baseline.json").write_text(
            json.dumps({"grown.py": 10, "same.py": 10}), encoding="utf-8"
        )

    def run_main(self, argv: list[str], stdin: str = "") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["check_file_length.py", *argv]),
            mock.patch.object(sys, "stdin", io.StringIO(stdin)),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            status = MODULE.main()
        return status, out.getvalue(), err.getvalue()

    def test_code_lines_ignores_blank_and_comment_lines(self) -> None:
        self.assertEqual(MODULE.code_lines("small.py"), 3)

    def test_plain_mode_reports_grown_grandfathered_file_and_exits_one(self) -> None:
        status, out, _ = self.run_main(["--max", "5", "grown.py", "same.py", "small.py"])
        self.assertEqual(status, 1)
        self.assertIn("grown.py: grandfathered at 10 code lines but grew to 12", out)
        self.assertNotIn("same.py:", out)
        self.assertIn("1 file(s) violate the size budget (max 5", out)

    def test_plain_mode_exits_zero_within_budget(self) -> None:
        status, out, _ = self.run_main(["--max", "5", "small.py", "same.py"])
        self.assertEqual(status, 0)
        self.assertEqual(out, "ok: 2 files within budget (max 5)\n")

    def test_hook_exits_two_with_exact_diagnostic_for_grown_file(self) -> None:
        payload = json.dumps({"tool_input": {"file_path": str(self.root / "grown.py")}})
        status, _, err = self.run_main(["--hook", "--max", "5"], stdin=payload)
        self.assertEqual(status, 2)
        expected = "FILE SIZE GUARD: grown.py: grandfathered at 10 code lines but grew to 12."
        self.assertTrue(err.startswith(expected), err)
        self.assertIn("Split it into a package first", err)

    def test_hook_is_silent_for_unchanged_grandfathered_malformed_and_non_python(self) -> None:
        for stdin in (
            json.dumps({"tool_input": {"file_path": "same.py"}}),
            json.dumps({"tool_input": {"file_path": "notes.md"}}),
            "not json at all",
        ):
            status, out, err = self.run_main(["--hook", "--max", "5"], stdin=stdin)
            self.assertEqual((status, out, err), (0, "", ""), stdin)

    def test_hook_control_disabled_in_memory_stops_the_guard(self) -> None:
        payload = json.dumps({"tool_input": {"file_path": "grown.py"}})
        with mock.patch.object(MODULE, "check", return_value=[]):
            status, _, err = self.run_main(["--hook", "--max", "5"], stdin=payload)
        self.assertEqual((status, err), (0, ""))


if __name__ == "__main__":
    unittest.main()
