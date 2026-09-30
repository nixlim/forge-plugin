"""Go same-file ``t.Helper()`` delegation in the assertion-quality sensor."""

from __future__ import annotations

import runpy
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENSOR = ROOT / "scripts/forge/check-test-quality.py"
STACKS = ROOT / "system/seeds/validation-snippets/stacks.md"

DELEGATION_CHECK = (
    "and not _go_call_names(masked_source[function.body or slice(0)]) & helpers"
)
DIRECT_ASSERTION_SPAN = "rule, source[direct_span]"
DIRECT_ASSERTION_BODY = "rule, source[function.body or slice(0)]"
LEGACY_DIRECT_SPANS = "legacy_spans = _go_direct_test_spans(source)"
DISABLED_LEGACY_DIRECT_SPANS = "legacy_spans = {}"
TEST_RECEIVER_EXCLUSION = (
    'tests = [f for f in functions if not f.has_receiver and f.name.startswith("Test")]'
)
DISABLED_TEST_RECEIVER_EXCLUSION = (
    'tests = [f for f in functions if f.name.startswith("Test")]'
)
NO_TESTS_HEURISTIC_SUPPRESSION = (
    "return [] if _heuristic_matches(rule, source) else [fallback]"
)
DISABLED_NO_TESTS_HEURISTIC_SUPPRESSION = "return [fallback]"
HELPER_MARKER_CHECK = "        if _go_is_assertion_helper(function.parameters, body):\n"
DISABLED_HELPER_MARKER_CHECK = "        if True:\n"
HELPER_MARKER_PATTERN = r'r"(?<![\w.])(?P<name>[A-Za-z_]\w*)\.Helper\s*\(\s*\)"'
QUALIFIED_HELPER_MARKER_PATTERN = r'r"(?<![\w])(?P<name>[A-Za-z_]\w*)\.Helper\s*\(\s*\)"'
DIRECT_HELPERS_ONLY = "range(MAX_HELPER_DEPTH)"
GO_CALL_PATTERN = "not (qualified or declaration_name)"
GO_CALL_PATTERN_WITH_DOTTED_NAMES = "not declaration_name"
LINE_COMMENT_MASK = '    r"//[^\\n]*"\n'
BLOCK_COMMENT_MASK = '    r"|/\\*(?:[^*]|\\*(?!/))*(?:\\*/|\\Z)"\n'
INTERPRETED_STRING_MASK = r'''    r'|"(?:\\[^\n]|[^"\\\n])*(?:"|\\?(?=\n|\Z))'
'''
INTERPRETED_STRING_WITH_EOF_ONLY = r'''    r'|"(?:\\[^\n]|[^"\\\n])*(?:"|\Z)'
'''
INTERPRETED_STRING_WITHOUT_ESCAPES = r'''    r'|"(?:[^"\\\n])*(?:"|\\?(?=\n|\Z))'
'''
RAW_STRING_MASK = '    r"|`[^`]*(?:`|\\Z)"\n'
RUNE_LITERAL_MASK = (
    '    r"|\'(?:\\\\[^\\n]|[^\'\\\\\\n])*(?:\'|\\\\?(?=\\n|\\Z))"\n'
)
RUNE_LITERAL_WITH_EOF_ONLY = (
    '    r"|\'(?:\\\\[^\\n]|[^\'\\\\\\n])*(?:\'|\\Z)"\n'
)
DISABLED_INITIAL_MASK = '    r"(?!)"\n'
DISABLED_MASK_BRANCH = '    r"|(?!)"\n'
GO_PARAMETER_TYPES = r"(?:\*testing\.T|testing\.TB)"
GROUPED_PARAMETER_NAMES = 'parameters.update((*pending, match.group("name")))'
DISABLED_GROUPED_PARAMETER_NAMES = 'parameters.add(match.group("name"))'
HELPER_DEPTH = "MAX_HELPER_DEPTH = 8"
DECLARATION_SKIP = "not (qualified or declaration_name)"
DUPLICATE_NAME_EXCLUSION = "counts[function.name] != 1"
MASKED_GO_ANALYSIS = "rule, source, masked_source, functions"
UNMASKED_GO_ANALYSIS = "rule, source, source, functions"
MASKED_SPAN_PASS = "functions = _go_function_spans(masked_source)"
UNMASKED_SPAN_PASS = "functions = _go_function_spans(source)"
EXACT_BODY_END = "body_end = _go_group_end(source, body_open) if body_open is not None else None"
UNBOUNDED_BODY_END = "body_end = len(source) - 1 if body_open is not None else None"
FIRST_BODY_CLOSE = 'body_end = source.find("}", body_open) if body_open is not None else None'
EXACT_BODY_SLICE = "slice(body_open + 1, body_end) if body_end is not None else None"
FALLBACK_BODY_SLICE = (
    "slice(body_open + 1, body_end) if body_end is not None "
    "else slice(parameters_end + 1, len(source))"
)
LARGE_FILE_TIMEOUT_SECONDS = 10.0
MALFORMED_LITERAL_TIMEOUT_SECONDS = 5.0


def large_delegating_source(row_count: int) -> str:
    rows = "".join(
        f'        row("case-{index:05d}", "{index:034d}"),\n'
        for index in range(row_count)
    )
    return f'''package x
func base(t *testing.T) {{ t.Helper(); t.Errorf("failure") }}
func TestLarge(t *testing.T) {{
    cases := []any{{
{rows}    }}
    _ = cases
    base(t)
}}
'''


class GoHelperTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory(prefix="forge-test-quality-go-helper-")
        self.addCleanup(temp_dir.cleanup)
        self.scratch = Path(temp_dir.name)
        self.mutant_number = 0

    def write(self, relative_path: str, source: str) -> str:
        path = self.scratch / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return relative_path

    def mutant(self, needle: str, replacement: str) -> Path:
        source = SENSOR.read_text(encoding="utf-8")
        self.assertEqual(source.count(needle), 1, needle)
        self.mutant_number += 1
        path = self.scratch / f"check-test-quality-disabled-{self.mutant_number}.py"
        path.write_text(source.replace(needle, replacement), encoding="utf-8")
        return path

    def run_sensor(
        self,
        *labels: str,
        sensor: Path = SENSOR,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(sensor),
                "--stacks-file",
                str(STACKS),
                "--",
                *labels,
            ],
            cwd=self.scratch,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def finding(self, label: str, source: str, name: str) -> str:
        marker = f"func {name}("
        self.assertEqual(source.count(marker), 1)
        line = source.count("\n", 0, source.index(marker)) + 1
        return f"forge: assertion-free test detected: {label}:{line}:{name}\n"

    def assert_advisory(
        self, result: subprocess.CompletedProcess[str], output: str
    ) -> None:
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, output, ""))


class GoHelperDelegationTests(GoHelperTestCase):
    def test_gh36_same_file_helper_satisfies_test(self) -> None:
        source = """package x

import "testing"

func requireStatus(t *testing.T, got, want int) {
    t.Helper()
    if got != want {
        t.Fatalf("got %d, want %d", got, want)
    }
}
func TestCancel(t *testing.T) {
    requireStatus(t, 1, 1)
}
"""
        label = self.write("internal/x/cancel_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")
        disabled = self.mutant(DELEGATION_CHECK, "and True")
        self.assert_advisory(
            self.run_sensor(label, sensor=disabled),
            self.finding(label, source, "TestCancel"),
        )

    def test_helper_marker_is_required(self) -> None:
        source = """package x

import "testing"

func noHelper(t *testing.T) {
    t.Fatalf("failure")
}
func TestC(t *testing.T) {
    noHelper(t)
}
"""
        label = self.write("marker_test.go", source)
        expected = self.finding(label, source, "TestC")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(HELPER_MARKER_CHECK, DISABLED_HELPER_MARKER_CHECK)
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_helper_marker_requires_bare_parameter_receiver(self) -> None:
        source = """package x

import "testing"

func qualifiedMarker(t *testing.T) {
    holder.t.Helper()
    t.Fatalf("failure")
}
func TestQualifiedMarker(t *testing.T) {
    qualifiedMarker(t)
}
"""
        label = self.write("qualified_marker_test.go", source)
        expected = self.finding(label, source, "TestQualifiedMarker")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(
            HELPER_MARKER_PATTERN,
            QUALIFIED_HELPER_MARKER_PATTERN,
        )
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_transitive_helper_chain_resolves(self) -> None:
        source = """package x

import "testing"

func base(tb testing.TB, got int) {
    tb.Helper()
    tb.Errorf("unexpected value: %d", got)
}
func outer(t *testing.T) {
    t.Helper()
    base(t, 1)
}
func TestChain(t *testing.T) {
    outer(t)
}
"""
        label = self.write("chain_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")
        disabled = self.mutant(DIRECT_HELPERS_ONLY, "range(0)")
        self.assert_advisory(
            self.run_sensor(label, sensor=disabled),
            self.finding(label, source, "TestChain"),
        )

    def test_qualified_call_does_not_resolve_same_file_helper(self) -> None:
        source = """package x

import "testing"

func requireStatus(t *testing.T) {
    t.Helper()
    t.Fatalf("bad status")
}
func TestQualified(t *testing.T) {
    other . requireStatus(t)
}
"""
        label = self.write("qualified_test.go", source)
        expected = self.finding(label, source, "TestQualified")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(GO_CALL_PATTERN, GO_CALL_PATTERN_WITH_DOTTED_NAMES)
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_helper_parameter_type_is_restricted(self) -> None:
        source = """package x

import "testing"

type fakeT struct{}

func wrongType(t *fakeT) {
    t.Helper()
    t.Errorf("failure")
}
func TestWrongType(t *testing.T) {
    wrongType(nil)
}
"""
        label = self.write("typed_test.go", source)
        expected = self.finding(label, source, "TestWrongType")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(GO_PARAMETER_TYPES, r"\S+")
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_grouped_testing_parameter_name_is_recognized(self) -> None:
        source = """package x
func helper(t, u, v *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestGrouped(t *testing.T) { helper(t, t, t) }
"""
        label = self.write("grouped_parameter_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")
        disabled = self.mutant(
            GROUPED_PARAMETER_NAMES, DISABLED_GROUPED_PARAMETER_NAMES
        )
        self.assert_advisory(
            self.run_sensor(label, sensor=disabled),
            self.finding(label, source, "TestGrouped"),
        )

    def test_helper_chain_stops_at_depth_bound(self) -> None:
        direct = """func helper0(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
"""
        wrappers = "".join(
            f"""func helper{index}(t *testing.T) {{
    t.Helper()
    helper{index - 1}(t)
}}
"""
            for index in range(1, 10)
        )
        source = (
            'package x\n\nimport "testing"\n\n'
            + direct
            + wrappers
            + """func TestTooDeep(t *testing.T) {
    helper9(t)
}
"""
        )
        label = self.write("deep_test.go", source)
        expected = self.finding(label, source, "TestTooDeep")

        self.assert_advisory(self.run_sensor(label), expected)
        raised_bound = self.mutant(HELPER_DEPTH, "MAX_HELPER_DEPTH = 9")
        self.assert_advisory(self.run_sensor(label, sensor=raised_bound), "")


class GoMaskingTests(GoHelperTestCase):
    def assert_mask_blocks_delegation(
        self,
        label: str,
        source: str,
        name: str,
        needle: str,
        replacement: str = DISABLED_MASK_BRANCH,
    ) -> None:
        expected = self.finding(label, source, name)
        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(needle, replacement)
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def assert_helper_assertion_decoy_is_masked(
        self, label: str, source: str, name: str
    ) -> None:
        expected = self.finding(label, source, name)
        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(MASKED_GO_ANALYSIS, UNMASKED_GO_ANALYSIS)
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_interpreted_string_assertion_does_not_resolve_helper(self) -> None:
        source = """package x

import "testing"

func fakeAssertion(t *testing.T) {
    t.Helper()
    msg := "t.Errorf(fake)"
    _ = msg
}
func TestStringAssertion(t *testing.T) {
    fakeAssertion(t)
}
"""
        label = self.write("string_assertion_test.go", source)

        self.assert_helper_assertion_decoy_is_masked(
            label, source, "TestStringAssertion"
        )

    def test_comment_assertion_does_not_resolve_helper(self) -> None:
        source = """package x

import "testing"

func fakeAssertion(t *testing.T) {
    t.Helper()
    // t.Errorf(fake)
}
func TestCommentAssertion(t *testing.T) {
    fakeAssertion(t)
}
"""
        label = self.write("comment_assertion_test.go", source)

        self.assert_helper_assertion_decoy_is_masked(
            label, source, "TestCommentAssertion"
        )

    def test_transitive_string_assertion_does_not_resolve_chain(self) -> None:
        source = """package x

import "testing"

func stepOne(t *testing.T) {
    t.Helper()
    msg := "t.Errorf(fake)"
    _ = msg
}
func stepTwo(t *testing.T) {
    t.Helper()
    stepOne(t)
}
func TestTransitiveStringAssertion(t *testing.T) {
    stepTwo(t)
}
"""
        label = self.write("transitive_string_assertion_test.go", source)

        self.assert_helper_assertion_decoy_is_masked(
            label, source, "TestTransitiveStringAssertion"
        )

    def test_raw_string_assertion_does_not_resolve_helper(self) -> None:
        source = """package x

import "testing"

func fakeAssertion(t *testing.T) {
    t.Helper()
    fixture := `t.Errorf(fake)`
    _ = fixture
}
func TestRawStringAssertion(t *testing.T) {
    fakeAssertion(t)
}
"""
        label = self.write("raw_string_assertion_test.go", source)

        self.assert_helper_assertion_decoy_is_masked(
            label, source, "TestRawStringAssertion"
        )

    def test_line_comment_call_does_not_delegate(self) -> None:
        source = """package x

import "testing"

func requireStatus(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestFakeCommentedCall(t *testing.T) {
    // requireStatus(t)
}
"""
        label = self.write("line_comment_call_test.go", source)

        self.assert_mask_blocks_delegation(
            label,
            source,
            "TestFakeCommentedCall",
            LINE_COMMENT_MASK,
            DISABLED_INITIAL_MASK,
        )

    def test_interpreted_string_call_does_not_delegate(self) -> None:
        source = """package x

import "testing"

func requireStatus(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestFakeStringCall(t *testing.T) {
    message := "requireStatus(t)"
    _ = message
}
"""
        label = self.write("string_call_test.go", source)

        self.assert_mask_blocks_delegation(
            label, source, "TestFakeStringCall", INTERPRETED_STRING_MASK
        )

    def test_line_comment_helper_marker_does_not_mark_helper(self) -> None:
        source = """package x

import "testing"

func fakeHelper(t *testing.T) {
    // t.Helper()
    t.Errorf("failure")
}
func TestFakeHelperMarker(t *testing.T) {
    fakeHelper(t)
}
"""
        label = self.write("line_comment_marker_test.go", source)

        self.assert_mask_blocks_delegation(
            label,
            source,
            "TestFakeHelperMarker",
            LINE_COMMENT_MASK,
            DISABLED_INITIAL_MASK,
        )

    def test_block_comment_spanning_lines_does_not_delegate(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestBlockComment(t *testing.T) {
    /* removed call:
    base(t)
    */
}
"""
        label = self.write("block_comment_call_test.go", source)

        self.assert_mask_blocks_delegation(
            label, source, "TestBlockComment", BLOCK_COMMENT_MASK
        )

    def test_raw_string_masks_call_and_function_declaration(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestRawString(t *testing.T) {
    fixture := `
base(t)
func phantom(t *testing.T) {
`
    _ = fixture
}
"""
        label = self.write("raw_string_call_test.go", source)

        self.assert_advisory(
            self.run_sensor(label), self.finding(label, source, "TestRawString")
        )

    def test_masked_test_declarations_do_not_bound_or_create_tests(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestRawFunctionBoundary(t *testing.T) {
    fixture := `
func TestPhantom(t *testing.T) {
`
    _ = fixture
    base(t)
}
/*
func TestOld(t *testing.T) {}
*/
"""
        label = self.write("raw_string_boundary_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")
        raw_mask_disabled = self.mutant(RAW_STRING_MASK, DISABLED_MASK_BRANCH)
        self.assert_advisory(
            self.run_sensor(label, sensor=raw_mask_disabled),
            self.finding(label, source, "TestRawFunctionBoundary"),
        )
        unmasked_spans = self.mutant(MASKED_SPAN_PASS, UNMASKED_SPAN_PASS)
        self.assert_advisory(
            self.run_sensor(label, sensor=unmasked_spans),
            self.finding(label, source, "TestRawFunctionBoundary"),
        )

    def test_raw_string_function_is_not_helper_duplicate(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
var fixture = `
func base(t *testing.T) {
}
`
func TestRealCall(t *testing.T) {
    base(t)
}
"""
        label = self.write("raw_string_duplicate_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")
        disabled = self.mutant(MASKED_SPAN_PASS, UNMASKED_SPAN_PASS)
        self.assert_advisory(
            self.run_sensor(label, sensor=disabled),
            self.finding(label, source, "TestRealCall"),
        )

    def test_escaped_quote_does_not_end_interpreted_string(self) -> None:
        source = r'''package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestEscapedQuote(t *testing.T) {
    message := "base(t) before an escaped quote: \" still text"
    _ = message
}
'''
        label = self.write("escaped_quote_call_test.go", source)

        self.assert_mask_blocks_delegation(
            label,
            source,
            "TestEscapedQuote",
            INTERPRETED_STRING_MASK,
            INTERPRETED_STRING_WITHOUT_ESCAPES,
        )

    def test_rune_double_quote_does_not_open_interpreted_string(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestRuneQuote(t *testing.T) {
    quote, message := '\"', "base(t)"
    _, _ = quote, message
}
"""
        label = self.write("rune_quote_call_test.go", source)

        self.assert_mask_blocks_delegation(
            label, source, "TestRuneQuote", RUNE_LITERAL_MASK
        )

    def test_malformed_literal_masking_finishes_within_hang_guard(self) -> None:
        pair_count = 60_000
        malformed_string = ('"' + "\\") * pair_count
        malformed_rune = ("'" + "\\") * pair_count
        source = f'''package x

var stringFixture = {malformed_string}
var runeFixture = {malformed_rune}
func TestAfterMalformed(t *testing.T) {{
    t.Errorf("failure")
}}
'''
        label = self.write("malformed_literals_test.go", source)

        started = time.perf_counter()
        result = self.run_sensor(label, timeout=MALFORMED_LITERAL_TIMEOUT_SECONDS)
        elapsed = time.perf_counter() - started

        self.assert_advisory(result, "")
        self.assertLess(elapsed, MALFORMED_LITERAL_TIMEOUT_SECONDS)
        for needle, replacement in (
            (INTERPRETED_STRING_MASK, INTERPRETED_STRING_WITH_EOF_ONLY),
            (RUNE_LITERAL_MASK, RUNE_LITERAL_WITH_EOF_ONLY),
        ):
            with self.subTest(needle=needle):
                disabled = self.mutant(needle, replacement)
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.run_sensor(
                        label,
                        sensor=disabled,
                        timeout=MALFORMED_LITERAL_TIMEOUT_SECONDS,
                    )

    def test_comment_call_does_not_resolve_transitive_helper(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func outer(t *testing.T) {
    t.Helper()
    // base(t)
}
func TestFakeTransitiveCall(t *testing.T) {
    outer(t)
}
"""
        label = self.write("transitive_comment_call_test.go", source)

        self.assert_mask_blocks_delegation(
            label,
            source,
            "TestFakeTransitiveCall",
            LINE_COMMENT_MASK,
            DISABLED_INITIAL_MASK,
        )

    def test_mask_preserves_offsets_and_newlines(self) -> None:
        namespace = runpy.run_path(
            str(SENSOR), run_name="forge_test_quality_sensor"
        )
        mask = namespace["_mask_go_non_code"]
        source = 'start // comment\r\nvalue := `raw\ntext`\nend'

        masked = mask(source)
        expected = (
            "start "
            + " " * len("// comment")
            + "\r\nvalue := "
            + " " * len("`raw")
            + "\n"
            + " " * len("text`")
            + "\nend"
        )

        self.assertEqual(masked, expected)
        self.assertEqual(len(masked), len(source))
        self.assertEqual(
            [index for index, char in enumerate(masked) if char == "\n"],
            [index for index, char in enumerate(source) if char == "\n"],
        )

    def test_direct_assertion_heuristic_remains_lexical(self) -> None:
        source = r'''package x

import "testing"

func TestLexicalAssertion(t *testing.T) {
    message := "t.Errorf(\"fixture text\")"
    _ = message
}
'''
        label = self.write("lexical_assertion_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")


class GoHelperBoundaryTests(GoHelperTestCase):
    def test_trailing_helper_is_outside_test_body(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestIdle(t *testing.T) {
}
func trailing(t *testing.T) {
    t.Helper()
    base(t)
}
"""
        label = self.write("trailing_test.go", source)
        expected = self.finding(label, source, "TestIdle")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(
            EXACT_BODY_END,
            UNBOUNDED_BODY_END,
        )
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_multiline_test_uses_following_function_as_body_boundary(self) -> None:
        for indentation in ("", "    "):
            source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestIdle(t *testing.T) {
    }
""" + (
                f"{indentation}func trailing(t *testing.T) {{\n"
                f"{indentation}    t.Helper()\n"
                f"{indentation}    base(t)\n"
                f"{indentation}}}\n"
            )
            label = self.write(f"one_line_{len(indentation)}_test.go", source)
            expected = self.finding(label, source, "TestIdle")

            with self.subTest(indentation=repr(indentation)):
                self.assert_advisory(self.run_sensor(label), expected)
                disabled = self.mutant(
                    EXACT_BODY_END,
                    UNBOUNDED_BODY_END,
                )
                self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_one_line_test_stops_before_top_level_registry(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}

func TestEmpty(t *testing.T) {}
var registry = map[string]func(*testing.T){
    "case": func(t *testing.T) {
        base(t)
    },
}
"""
        label = self.write("one_line_registry_test.go", source)
        expected = self.finding(label, source, "TestEmpty")

        self.assert_advisory(self.run_sensor(label), expected)
        unbounded = self.mutant(EXACT_BODY_END, UNBOUNDED_BODY_END)
        self.assert_advisory(self.run_sensor(label, sensor=unbounded), "")

    def test_nested_block_does_not_hide_later_helper_call(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestAfterBlock(t *testing.T) {
    if true {
        t.Log("setup")
    }
    base(t)
}
"""
        label = self.write("nested_block_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")
        disabled = self.mutant(
            EXACT_BODY_END,
            FIRST_BODY_CLOSE,
        )
        self.assert_advisory(
            self.run_sensor(label, sensor=disabled),
            self.finding(label, source, "TestAfterBlock"),
        )

    def test_anonymous_function_does_not_end_test_body(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestIIFE(t *testing.T) {
    func() {
        t.Log("setup")
    }()
    base(t)
}
"""
        label = self.write("anonymous_function_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")
        disabled = self.mutant(
            EXACT_BODY_END,
            FIRST_BODY_CLOSE,
        )
        self.assert_advisory(
            self.run_sensor(label, sensor=disabled),
            self.finding(label, source, "TestIIFE"),
        )

    def test_declaration_syntax_is_not_a_helper_call(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestIdle(t *testing.T) {
    if false { func base(t) }
}
"""
        label = self.write("declaration_syntax_test.go", source)
        expected = self.finding(label, source, "TestIdle")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(DECLARATION_SKIP, "not qualified")
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_duplicate_helper_name_is_excluded(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("first failure")
}
func base(t *testing.T) {
    t.Helper()
    t.Errorf("second failure")
}
func TestIdle(t *testing.T) {
    base(t)
}
"""
        label = self.write("duplicate_helper_test.go", source)
        expected = self.finding(label, source, "TestIdle")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(
            DUPLICATE_NAME_EXCLUSION,
            "False",
        )
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_indented_test_does_not_inherit_trailing_helper_delegation(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
    func TestIndented(t *testing.T) {
    }
func trailing(t *testing.T) {
    t.Helper()
    base(t)
}
"""
        label = self.write("indented_test.go", source)
        expected = self.finding(label, source, "TestIndented")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(EXACT_BODY_END, UNBOUNDED_BODY_END)
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_missing_column_zero_signature_gets_no_delegation_fallback(self) -> None:
        source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
    func TestIndented(t *testing.T) {
    }
    func trailing(t *testing.T) {
        t.Helper()
        base(t)
    }
"""
        label = self.write("no_signature_test.go", source)
        expected = self.finding(label, source, "TestIndented")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(EXACT_BODY_END, UNBOUNDED_BODY_END)
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_test_signature_without_opening_brace_gets_no_delegation(self) -> None:
        for suffix in ("\nbase(t)\n", "\n{\n    base(t)\n}\n"):
            source = """package x

import "testing"

func base(t *testing.T) {
    t.Helper()
    t.Errorf("failure")
}
func TestMalformed(t *testing.T)""" + suffix
            label = self.write(f"malformed_{len(suffix)}_test.go", source)
            expected = self.finding(label, source, "TestMalformed")

            with self.subTest(suffix=repr(suffix)):
                self.assert_advisory(self.run_sensor(label), expected)
                disabled = self.mutant(
                    EXACT_BODY_SLICE,
                    FALLBACK_BODY_SLICE,
                )
                self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_direct_assertion_uses_declaration_to_next_test_span(self) -> None:
        source = """package x
func TestBorrowed(t *testing.T) {
    trailingBefore(t)
}
func trailingBefore(t *testing.T) { t.Errorf("failure") }
func TestRawBoundary(t *testing.T) {}
var fixture = `
func TestPhantom(t *testing.T) {}
`
func trailingAfter(t *testing.T) { t.Errorf("failure") }
func TestNext(t *testing.T) {}
"""
        label = self.write("trailing_direct_assertion_test.go", source)
        next_finding = self.finding(label, source, "TestNext")
        expected = self.finding(label, source, "TestRawBoundary") + next_finding

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(DIRECT_ASSERTION_SPAN, DIRECT_ASSERTION_BODY)
        self.assert_advisory(
            self.run_sensor(label, sensor=disabled),
            self.finding(label, source, "TestBorrowed") + expected,
        )
        legacy_disabled = self.mutant(
            LEGACY_DIRECT_SPANS,
            DISABLED_LEGACY_DIRECT_SPANS,
        )
        self.assert_advisory(
            self.run_sensor(label, sensor=legacy_disabled),
            next_finding,
        )

    def test_test_receiver_is_not_a_free_test_function(self) -> None:
        source = """package x

import (
    "testing"
    "github.com/stretchr/testify/suite"
)

type ExampleSuite struct { suite.Suite }

func assertingHelper(t *testing.T) {
    t.Errorf("failure")
}
func (suite *ExampleSuite) TestCase() {
}
"""
        label = self.write("testify_suite_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")
        disabled = self.mutant(
            TEST_RECEIVER_EXCLUSION,
            DISABLED_TEST_RECEIVER_EXCLUSION,
        )
        line = source.count("\n", 0, source.index("func (suite *ExampleSuite)")) + 1
        expected = f"forge: assertion-free test detected: {label}:{line}:TestCase\n"
        self.assert_advisory(
            self.run_sensor(label, sensor=disabled),
            expected,
        )

    def test_helpers_only_assertion_suppresses_no_tests_fallback(self) -> None:
        source = """package x

func helper(t *testing.T) {
    t.Errorf("failure")
}
"""
        label = self.write("helpers_only_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")
        disabled = self.mutant(
            NO_TESTS_HEURISTIC_SUPPRESSION,
            DISABLED_NO_TESTS_HEURISTIC_SUPPRESSION,
        )
        fallback = f"forge: assertion-free test detected: {label}:1:{label}\n"
        self.assert_advisory(self.run_sensor(label, sensor=disabled), fallback)

    def test_test_and_helper_analysis_build_one_span_table(self) -> None:
        namespace = runpy.run_path(
            str(SENSOR), run_name="forge_test_quality_sensor"
        )
        check_files = namespace["check_files"]
        sensor_globals = check_files.__globals__
        span_pass = sensor_globals["_go_function_spans"]
        calls = 0

        def counted(source: str):
            nonlocal calls
            calls += 1
            return span_pass(source)

        source = """package x
func helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestDelegates(t *testing.T) { helper(t) }
func TestIdle(t *testing.T) {}
"""
        path = self.scratch / "single_test.go"
        path.write_text(source, encoding="utf-8")
        sensor_globals["_go_function_spans"] = counted
        try:
            actual, blocking = check_files([str(path)], STACKS, None)
        finally:
            sensor_globals["_go_function_spans"] = span_pass

        self.assertFalse(blocking)
        self.assertEqual(
            actual,
            [f"forge: assertion-free test detected: {path}:4:TestIdle"],
        )
        self.assertEqual(calls, 1)

    def test_large_delegating_table_finishes_well_below_old_runtime(self) -> None:
        source = large_delegating_source(20_000)
        self.assertGreaterEqual(len(source.encode()), 1_000_000)
        self.assertLessEqual(len(source.encode()), 2_000_000)
        label = self.write("large_table_test.go", source)

        started = time.perf_counter()
        result = self.run_sensor(label, timeout=LARGE_FILE_TIMEOUT_SECONDS)
        elapsed = time.perf_counter() - started

        self.assert_advisory(result, "")
        # This is a hang guard, not a benchmark. The fixed 1.3 MB path measured
        # 0.264 s locally; 10 s is 37x that and far below the old 426 s.
        self.assertLess(elapsed, LARGE_FILE_TIMEOUT_SECONDS)

    def test_mutually_recursive_helpers_terminate_without_resolving(self) -> None:
        source = """package x

import "testing"

func first(t *testing.T) {
    t.Helper()
    second(t)
}
func second(t *testing.T) {
    t.Helper()
    first(t)
}
func TestCycle(t *testing.T) {
    first(t)
}
"""
        label = self.write("cycle_test.go", source)

        self.assert_advisory(
            self.run_sensor(label), self.finding(label, source, "TestCycle")
        )

    def test_node_regex_output_is_unchanged(self) -> None:
        source = """function requireStatus() {
  expect(status).toBe("ready");
}

test("delegated node", () => {
  requireStatus();
});
test("direct node", () => {
  expect(status).toBe("ready");
});
"""
        label = self.write("status.test.js", source)
        expected = (
            f"forge: assertion-free test detected: {label}:4:delegated node\n"
        )

        self.assert_advisory(self.run_sensor(label), expected)


if __name__ == "__main__":
    unittest.main()
