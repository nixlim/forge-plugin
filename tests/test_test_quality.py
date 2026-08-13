from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK_TEST_QUALITY = ROOT / "scripts/forge/check-test-quality.py"


class TestQualitySensorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-test-quality-")
        self.addCleanup(self.temp_dir.cleanup)
        self.scratch = Path(self.temp_dir.name)
        self.seed = self.scratch / "stacks.md"
        self.seed.write_text(
            """# Stack test metadata

## node
Test file patterns: `*.test.js`, `*.spec.ts`
Assertion heuristic: regex: `(?:expect\\s*\\(|assert\\.)`

## go
Test file patterns: `*_test.go`
Assertion heuristic: literal: `t.Error`

## rust
Test file patterns: `*_test.rs`
No seeded assertion heuristic for rust.
""",
            encoding="utf-8",
        )

    def write(self, relative_path: str, contents: str) -> Path:
        path = self.scratch / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        return path

    def run_sensor(
        self,
        *paths: Path | str,
        seed: Path | None = None,
        stack: str | None = None,
        sensor: Path = CHECK_TEST_QUALITY,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(sensor),
            "--stacks-file",
            str(seed or self.seed),
        ]
        if stack is not None:
            command.extend(["--stack", stack])
        command.append("--")
        command.extend(str(path) for path in paths)
        return subprocess.run(
            command,
            cwd=self.scratch,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def test_python_ast_finding_is_function_scoped_and_blocking(self) -> None:
        path = self.write(
            "test_example.py",
            """import unittest
import pytest

def test_assert_statement():
    assert True

def test_explicit_raise():
    raise RuntimeError("expected")

def test_assertion_method():
    unittest.TestCase().assertEqual(1, 1)

def test_expected_exception():
    with unittest.TestCase().assertRaises(ValueError):
        int("not-an-int")

def test_pytest_expected_exception():
    with pytest.raises(ValueError):
        int("not-an-int")

async def test_missing_oracle():
    value = 42
""",
        )

        result = self.run_sensor(path)

        expected = f"forge: assertion-free test detected: {path}:21:test_missing_oracle\n"
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout, expected)
        self.assertEqual(result.stderr, "")

    def test_uncalled_nested_helper_assertion_does_not_satisfy_outer_test(self) -> None:
        path = self.write(
            "test_uncalled_nested.py",
            """def test_outer():
    def helper():
        assert True
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:1:test_outer\n",
        )
        self.assertEqual(result.stderr, "")

    def test_called_nested_helper_assertion_satisfies_outer_test(self) -> None:
        path = self.write(
            "test_called_nested.py",
            """def test_outer():
    def helper():
        assert True
    helper()
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_called_module_helper_assertion_satisfies_test(self) -> None:
        path = self.write(
            "test_module_helper.py",
            """def verify_result():
    assert True

def test_outer():
    verify_result()
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_called_class_helper_assertion_satisfies_test(self) -> None:
        path = self.write(
            "test_class_helper.py",
            """class TestExample:
    def helper(self):
        assert True

    def test_outer(self):
        self.helper()
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_called_class_name_helper_assertion_satisfies_test(self) -> None:
        path = self.write(
            "test_class_name_helper.py",
            """class TestExample:
    @staticmethod
    def helper():
        assert True

    @staticmethod
    def test_outer():
        TestExample.helper()
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_unresolvable_imported_call_is_advisory(self) -> None:
        path = self.write(
            "test_imported_helper.py",
            """from helpers import verify_result

def test_outer():
    verify_result()
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion check inconclusive: {path}:3:test_outer — advisory only\n",
        )
        self.assertEqual(result.stderr, "")

    def test_unresolvable_self_attribute_call_is_advisory(self) -> None:
        path = self.write(
            "test_unittest_delegate.py",
            """import unittest

class TestExample(unittest.TestCase):
    def test_outer(self):
        self._check_valid()
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion check inconclusive: {path}:4:test_outer — advisory only\n",
        )
        self.assertEqual(result.stderr, "")

    def test_shadowed_pytest_module_call_does_not_rescue_missing_assertion(self) -> None:
        path = self.write(
            "test_shadowed_pytest.py",
            """import pytest

def test_outer(pytest):
    pytest.raises(ValueError)
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:3:test_outer\n",
        )
        self.assertEqual(result.stderr, "")

    def test_unrelated_pytest_alias_does_not_bless_local_helper(self) -> None:
        path = self.write(
            "test_scoped_pytest_alias.py",
            """def setup_alias():
    from pytest import raises as verify

def test_outer():
    def verify():
        value = 42
    verify()
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:4:test_outer\n",
        )
        self.assertEqual(result.stderr, "")

    def test_no_assertion_and_no_calls_is_blocking(self) -> None:
        path = self.write(
            "test_no_calls.py",
            """def test_without_assertion():
    value = 42
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:1:test_without_assertion\n",
        )
        self.assertEqual(result.stderr, "")

    def test_constructor_and_object_method_do_not_rescue_missing_assertion(self) -> None:
        path = self.write(
            "test_widget.py",
            """def test_widget():
    w = Widget()
    w.render()
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:1:test_widget\n",
        )
        self.assertEqual(result.stderr, "")

    def test_print_builtin_does_not_rescue_missing_assertion(self) -> None:
        path = self.write(
            "test_print.py",
            """def test_thing():
    print("x")
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:1:test_thing\n",
        )
        self.assertEqual(result.stderr, "")

    def test_len_builtin_does_not_rescue_missing_assertion(self) -> None:
        path = self.write(
            "test_len.py",
            """def test_len():
    len([1, 2])
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:1:test_len\n",
        )
        self.assertEqual(result.stderr, "")

    def test_imported_module_attribute_call_does_not_rescue_missing_assertion(
        self,
    ) -> None:
        path = self.write(
            "test_subprocess.py",
            """import subprocess

def test_run():
    subprocess.run(["true"])
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:3:test_run\n",
        )
        self.assertEqual(result.stderr, "")

    def test_unittest_imported_attribute_call_does_not_rescue_missing_assertion(
        self,
    ) -> None:
        path = self.write(
            "test_imported_attribute.py",
            """import helpers
import unittest

class TestThing(unittest.TestCase):
    def test_thing(self):
        helpers.verify_result()
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:5:test_thing\n",
        )
        self.assertEqual(result.stderr, "")

    def test_unresolvable_assertion_like_calls_do_not_rescue_missing_assertion(
        self,
    ) -> None:
        path = self.write(
            "test_unrelated_calls.py",
            """def test_builder_only():
    assertion_builder()

def test_unrelated_raises_helper():
    raises(ValueError)
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:1:test_builder_only\n"
            f"forge: assertion-free test detected: {path}:4:"
            "test_unrelated_raises_helper\n",
        )
        self.assertEqual(result.stderr, "")

    def test_nested_test_named_helper_is_not_a_separate_test(self) -> None:
        path = self.write(
            "test_nested_name.py",
            """def test_outer():
    def test_local_helper():
        build_fixture()
    assert True
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_aliased_pytest_expected_exception_is_recognized(self) -> None:
        path = self.write(
            "test_pytest_alias.py",
            """import pytest as pt
from pytest import raises as expect_raises

def test_module_alias():
    with pt.raises(ValueError):
        int("bad")

def test_imported_alias():
    with expect_raises(ValueError):
        int("bad")
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_valid_waiver_is_file_local_and_remains_visible(self) -> None:
        waived = self.write(
            "test_generated.py",
            """# forge-assertion-waiver: generated oracle is checked by the integration harness
def test_generated_snapshot():
    produce_snapshot()
""",
        )
        blocked = self.write(
            "test_other.py",
            """def test_still_checked():
    value = 42
""",
        )

        result = self.run_sensor(waived, blocked)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            f"forge: assertion waiver: {waived}: "
            "generated oracle is checked by the integration harness",
            result.stdout,
        )
        self.assertNotIn(f"{waived}:2:test_generated_snapshot", result.stdout)
        self.assertIn(f"{blocked}:1:test_still_checked", result.stdout)

    def test_waived_syntactically_invalid_python_is_skipped_entirely(self) -> None:
        path = self.write(
            "test_invalid_waived.py",
            """# forge-assertion-waiver: generated invalid fixture
def test_bad():
    value = (
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion waiver: {path}: generated invalid fixture\n",
        )
        self.assertEqual(result.stderr, "")

    def test_waiver_is_checked_before_invalid_python_encoding_cookie(self) -> None:
        path = self.scratch / "test_invalid_encoding_waived.py"
        path.write_bytes(
            b"# forge-assertion-waiver: generated fixture uses invalid source bytes\n"
            b"# coding: definitely-not-an-encoding\n"
            b"def test_generated():\n    generated_oracle()\n"
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion waiver: {path}: generated fixture uses invalid source bytes\n",
        )
        self.assertEqual(result.stderr, "")

        mutant = self.scratch / "check-test-quality-disabled.py"
        source = CHECK_TEST_QUALITY.read_text(encoding="utf-8")
        needle = """        if is_python:
            waiver = _waiver_reason(_read_python_waiver_source(path), True)
            if waiver is not None:
                inputs.append((path_label, path, "", waiver))
                continue
"""
        self.assertEqual(source.count(needle), 1)
        mutant.write_text(source.replace(needle, ""), encoding="utf-8")

        disabled = self.run_sensor(path, sensor=mutant)

        self.assertEqual(disabled.returncode, 2)
        self.assertEqual(disabled.stderr, "forge: test-quality check failed to execute\n")

    def test_non_utf8_waiver_reason_is_backslash_escaped(self) -> None:
        path = self.scratch / "test_non_utf8_waiver.py"
        path.write_bytes(
            b"# forge-assertion-waiver: caf\xe9 fixture\n"
            b"def test_generated():\n    generated_oracle()\n"
        )
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8:strict"

        result = self.run_sensor(path, environment=environment)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion waiver: {path}: caf\\xe9 fixture\n",
        )
        self.assertEqual(result.stderr, "")

    def test_waiver_text_inside_a_string_is_not_a_comment_waiver(self) -> None:
        path = self.write(
            "test_waiver_string.py",
            '''WAIVER_EXAMPLE = """
# forge-assertion-waiver: documentation is not a waiver
"""

def test_still_checked():
    value = 42
''',
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(f"{path}:5:test_still_checked", result.stdout)
        self.assertNotIn("forge: assertion waiver:", result.stdout)

    def test_non_python_regex_finding_is_advisory(self) -> None:
        path = self.write(
            "widget.test.js",
            """test("renders widget", () => {
  renderWidget();
});
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:1:renders widget\n",
        )

    def test_non_python_heuristic_is_applied_to_each_discovered_test(self) -> None:
        path = self.write(
            "mixed.test.js",
            """test("missing assertion", () => {
  renderWidget();
});
test("has assertion", () => {
  expect(value).toBe(1);
});
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:1:missing assertion\n",
        )

    def test_non_python_regex_match_is_case_sensitive_and_clean(self) -> None:
        clean = self.write(
            "clean.test.js",
            'test("works", () => { expect(value).toBe(1); });\n',
        )
        wrong_case = self.write(
            "wrong-case.test.js",
            'test("wrong case", () => { Expect(value).toBe(1); });\n',
        )

        clean_result = self.run_sensor(clean)
        wrong_case_result = self.run_sensor(wrong_case)

        self.assertEqual(clean_result.returncode, 0)
        self.assertEqual(clean_result.stdout, "")
        self.assertEqual(wrong_case_result.returncode, 0)
        self.assertIn("wrong case", wrong_case_result.stdout)

    def test_shipped_seed_is_loaded_relative_to_the_sensor(self) -> None:
        path = self.write(
            "shipped-seed.test.js",
            'test("uses shipped seed", () => { render(); });\n',
        )

        result = subprocess.run(
            [sys.executable, str(CHECK_TEST_QUALITY), "--", str(path)],
            cwd=self.scratch,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            f"forge: assertion-free test detected: {path}:1:uses shipped seed\n",
        )
        self.assertEqual(result.stderr, "")

    def test_literal_heuristic_is_interpreted_without_regex_semantics(self) -> None:
        finding = self.write(
            "math_test.go",
            """package math
func TestAdd(t *testing.T) { tError("missing separator") }
""",
        )
        clean = self.write(
            "clean_test.go",
            """package math
func TestAdd(t *testing.T) { t.Error("nope") }
""",
        )

        finding_result = self.run_sensor(finding)
        clean_result = self.run_sensor(clean)

        self.assertEqual(finding_result.returncode, 0)
        self.assertIn(f"{finding}:2:TestAdd", finding_result.stdout)
        self.assertEqual(clean_result.returncode, 0)
        self.assertEqual(clean_result.stdout, "")

    def test_explicit_absence_is_advisory_with_exact_diagnostic(self) -> None:
        path = self.write(
            "parser_test.rs",
            """#[test]
fn test_parser() { parse(); }
""",
        )

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            "forge: no seeded assertion heuristic for rust — advisory only\n",
        )

    def test_missing_stack_declaration_is_advisory(self) -> None:
        path = self.write("test_widget.rb", "def test_widget\n  widget\nend\n")

        result = self.run_sensor(path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            "forge: no seeded assertion heuristic for rb — advisory only\n",
        )

    def test_malformed_python_and_missing_file_use_exit_two_contract(self) -> None:
        malformed = self.write("test_bad.py", "def test_bad(:\n")
        for path in (malformed, self.scratch / "test_missing.py"):
            with self.subTest(path=path):
                result = self.run_sensor(path)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(
                    result.stderr,
                    "forge: test-quality check failed to execute\n",
                )

        valid = self.write("test_valid.py", "def test_valid():\n    assert True\n")
        missing_seed_result = self.run_sensor(valid, seed=self.scratch / "missing-stacks.md")
        self.assertEqual(missing_seed_result.returncode, 2)
        self.assertEqual(missing_seed_result.stdout, "")
        self.assertEqual(
            missing_seed_result.stderr,
            "forge: test-quality check failed to execute\n",
        )

    def test_malformed_seed_regex_and_waiver_use_exit_two_contract(self) -> None:
        bad_seed = self.write(
            "bad-stacks.md",
            """## node
Assertion heuristic: regex: `(`
""",
        )
        node_test = self.write("sensor.test.js", 'test("sensor", () => {});\n')
        bad_waiver = self.write(
            "test_bad_waiver.py",
            """# forge-assertion-waiver:
def test_bad_waiver():
    run()
""",
        )
        duplicate_waiver = self.write(
            "test_duplicate_waiver.py",
            """# forge-assertion-waiver: generated case one
# forge-assertion-waiver: generated case two
def test_duplicate_waiver():
    run()
""",
        )
        for result in (
            self.run_sensor(node_test, seed=bad_seed),
            self.run_sensor(bad_waiver),
            self.run_sensor(duplicate_waiver),
        ):
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertEqual(
                result.stderr,
                "forge: test-quality check failed to execute\n",
            )

    def test_mixed_python_and_non_python_findings_keep_blocking_precedence(self) -> None:
        advisory = self.write(
            "mixed.test.js",
            'test("advisory finding", () => { render(); });\n',
        )
        blocking = self.write(
            "test_mixed.py",
            """def test_blocking_finding():
    value = 42
""",
        )

        result = self.run_sensor(advisory, blocking)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(f"{advisory}:1:advisory finding", result.stdout)
        self.assertIn(f"{blocking}:1:test_blocking_finding", result.stdout)

    def test_no_paths_is_malformed_input(self) -> None:
        result = self.run_sensor()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr,
            "forge: test-quality check failed to execute\n",
        )


if __name__ == "__main__":
    unittest.main()
