"""Present non-printable test-path labels fail closed before diagnostics."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENSOR = ROOT / "scripts/forge/check-test-quality.py"
FAILURE = b"forge: test-quality check failed to execute\n"
SEED = "## go\nTest file patterns: `*_test.go`\nAssertion heuristic: literal: `t.Error`\n"
PRESENT_LABEL_GUARD = """        if not path_label.isprintable():
            raise CheckFailure("test path label is not printable")
"""

STRICT_STDIO = {**os.environ, "PYTHONIOENCODING": "utf-8:strict"}
UTF8_STDIO = {
    **{
        name: value
        for name, value in os.environ.items()
        if name != "PYTHONIOENCODING"
    },
    "LC_ALL": "C.UTF-8",
    "PYTHONUTF8": "1",
}
STDIO_MODES = (("strict", STRICT_STDIO), ("C.UTF-8", UTF8_STDIO))

GO_FINDING = """package tests

import "testing"

func TestBad(t *testing.T) {
    _ = 1
}
"""
PYTHON_FINDING = """def test_bad():
    value = 1
"""
PYTHON_CLEAN = """def test_clean():
    assert True
"""
PYTHON_WAIVED = """# forge-assertion-waiver: generated fixture
def test_generated():
    generated_oracle()
"""


class PresentLabelTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory(prefix="forge-test-quality-labels-")
        self.addCleanup(temp_dir.cleanup)
        self.scratch = Path(temp_dir.name)
        self.seed = self.scratch / "stacks.md"
        self.seed.write_text(SEED, encoding="utf-8")
        (self.scratch / "tests").mkdir()

    def write(self, label: str, contents: str) -> str:
        path = self.scratch / label
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        return label

    def write_non_utf8(self, raw_label: bytes, contents: str) -> str:
        label = os.fsdecode(raw_label)
        try:
            return self.write(label, contents)
        except OSError as exc:
            self.skipTest(f"filesystem rejects non-UTF-8 names: {exc}")

    def mutant(self) -> Path:
        source = SENSOR.read_text(encoding="utf-8")
        self.assertEqual(source.count(PRESENT_LABEL_GUARD), 1, PRESENT_LABEL_GUARD)
        mutant = self.scratch / "check-test-quality-label-guard-disabled.py"
        mutant.write_text(
            source.replace(PRESENT_LABEL_GUARD, "", 1),
            encoding="utf-8",
        )
        return mutant

    def run_sensor(
        self,
        *labels: str,
        sensor: Path = SENSOR,
        environment: dict[str, str] = STRICT_STDIO,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [
                sys.executable,
                str(sensor),
                "--stacks-file",
                str(self.seed),
                "--",
                *labels,
            ],
            cwd=self.scratch,
            check=False,
            capture_output=True,
            env=environment,
        )

    def assert_fails_closed(self, result: subprocess.CompletedProcess[bytes]) -> None:
        self.assertEqual((result.returncode, result.stdout, result.stderr), (2, b"", FAILURE))

    def assert_fails_closed_in_each_mode(self, label: str) -> None:
        for mode, environment in STDIO_MODES:
            with self.subTest(mode=mode, label=label):
                self.assert_fails_closed(self.run_sensor(label, environment=environment))

    def test_non_utf8_go_finding_fails_closed_in_each_stdio_mode(self) -> None:
        label = self.write_non_utf8(b"tests/bad\xff_test.go", GO_FINDING)

        self.assert_fails_closed_in_each_mode(label)

    def test_non_utf8_python_finding_fails_closed_in_each_stdio_mode(self) -> None:
        label = self.write_non_utf8(b"tests/test_bad\xff.py", PYTHON_FINDING)

        self.assert_fails_closed_in_each_mode(label)

    def test_clean_and_waived_non_utf8_python_files_fail_closed(self) -> None:
        cases = (
            (b"tests/test_clean\xff.py", PYTHON_CLEAN),
            (b"tests/test_waived\xff.py", PYTHON_WAIVED),
        )
        for raw_label, contents in cases:
            label = self.write_non_utf8(raw_label, contents)
            with self.subTest(label=label):
                self.assert_fails_closed_in_each_mode(label)

    def test_present_tab_label_fails_closed_in_each_stdio_mode(self) -> None:
        label = self.write("tests/test_bad\tlabel.py", PYTHON_CLEAN)

        self.assert_fails_closed_in_each_mode(label)

    def test_bad_label_suppresses_output_from_an_earlier_good_file(self) -> None:
        good = self.write("tests/test_good.py", PYTHON_WAIVED)
        bad = self.write_non_utf8(b"tests/test_bad\xff.py", PYTHON_FINDING)
        expected_good = b"forge: assertion waiver: tests/test_good.py: generated fixture\n"

        for mode, environment in STDIO_MODES:
            with self.subTest(mode=mode):
                good_result = self.run_sensor(good, environment=environment)
                self.assertEqual(
                    (good_result.returncode, good_result.stdout, good_result.stderr),
                    (0, expected_good, b""),
                )
                self.assert_fails_closed(
                    self.run_sensor(good, bad, environment=environment)
                )

    def test_removing_present_label_guard_restores_unsafe_output(self) -> None:
        label = self.write_non_utf8(b"tests/bad\xff_test.go", GO_FINDING)

        for mode, environment in STDIO_MODES:
            with self.subTest(mode=mode):
                self.assert_fails_closed(self.run_sensor(label, environment=environment))
                disabled = self.run_sensor(
                    label,
                    sensor=self.mutant(),
                    environment=environment,
                )
                self.assertNotEqual(disabled.returncode, 2, disabled.stderr)
                if mode == "strict":
                    self.assertIn(b"UnicodeEncodeError", disabled.stderr)
                else:
                    unsafe_labels = (b"\xff", b"\\udcff")
                    self.assertTrue(
                        any(value in disabled.stdout for value in unsafe_labels),
                        disabled.stdout,
                    )


if __name__ == "__main__":
    unittest.main()
