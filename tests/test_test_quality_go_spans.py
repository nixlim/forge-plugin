"""Structural Go function-span coverage for the assertion-quality sensor."""

from __future__ import annotations

import json
import os
import random
import re
import runpy
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from tests import test_test_quality_go_helpers as helpers

ROOT = Path(__file__).resolve().parents[1]
SENSOR = ROOT / "scripts/forge/check-test-quality.py"
STACKS = ROOT / "system/seeds/validation-snippets/stacks.md"

FUNC_NAME_SPACE = "while index < len(source) and source[index].isspace():"
SAME_LINE_FUNC_NAME = (
    'while index < len(source) and source[index] in " \\t\\r":'
)
LINE_RECORDING = "span, resume = _go_declaration(masked_source, index, line)"
SHIFTED_LINE_RECORDING = "span, resume = _go_declaration(masked_source, index, line - 1)"
CONTINUED_RESULT_NEWLINE = "            if can_end:\n"
ALL_NEWLINES_END_DECLARATION = "            if True:\n"
GENERIC_CALL_SCAN = '''        if source[index : index + 1] == "[":
            type_end = _go_group_end(source, index)
            if type_end is None:
                break
            index = _go_skip_space(source, type_end + 1)
'''
DISABLED_GENERIC_CALL_SCAN = ""
RECEIVER_CLASSIFICATION = (
    "name, start, line, source[index + 1 : parameters_end], has_receiver,"
)
DISABLED_RECEIVER_CLASSIFICATION = (
    "name, start, line, source[index + 1 : parameters_end], False,"
)
KEYWORD_NAME_CHECK = "if name_match is None or name_match.group() in GO_KEYWORDS:"
DISABLED_KEYWORD_NAME_CHECK = "if name_match is None:"
IDENTIFIER_JUMP = '''        if word is not None and word.group() != "func":
            index = word.end()
            continue
'''
DISABLED_IDENTIFIER_JUMP = '''        if word is not None and word.group() != "func":
            index += 1
            continue
'''
TIMEOUT_SECONDS = 10.0
TOKEN_SCAN_TIMEOUT_SECONDS = 5.0
GO_ORACLE_TIMEOUT_SECONDS = 30.0

ReferenceToken = tuple[str, int, int]
ReferenceSpan = tuple[str, int, int, str, bool, int | None, int | None]
FindingRows = tuple[tuple[int, str], ...]
DifferentialCase = tuple[str, str, FindingRows, FindingRows]
REFERENCE_TOKEN_RE = re.compile(r"\n|[A-Za-z_]\w*|[^\s]")


def _reference_tokens(source: str) -> list[ReferenceToken]:
    return [
        (match.group(), match.start(), match.end())
        for match in REFERENCE_TOKEN_RE.finditer(source)
    ]


def _reference_identifier(token: str) -> bool:
    return token[:1] == "_" or token[:1].isalpha()


def _reference_group_end(tokens: list[ReferenceToken], start: int) -> int | None:
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = set(pairs.values())
    stack = [pairs[tokens[start][0]]]
    for index in range(start + 1, len(tokens)):
        lexeme = tokens[index][0]
        if lexeme in pairs:
            stack.append(pairs[lexeme])
        elif lexeme == stack[-1]:
            stack.pop()
            if not stack:
                return index
        elif lexeme in closing:
            return None
    return None


def _reference_skip_newlines(tokens: list[ReferenceToken], index: int) -> int:
    while index < len(tokens) and tokens[index][0] == "\n":
        index += 1
    return index


def _reference_token(tokens: list[ReferenceToken], index: int) -> str:
    return tokens[index][0] if index < len(tokens) else ""


def _reference_signature(
    tokens: list[ReferenceToken], index: int
) -> tuple[str, bool, int, int] | None:
    cursor = _reference_skip_newlines(tokens, index + 1)
    has_receiver = _reference_token(tokens, cursor) == "("
    if has_receiver:
        receiver_end = _reference_group_end(tokens, cursor)
        if receiver_end is None:
            return None
        cursor = _reference_skip_newlines(tokens, receiver_end + 1)
    name = _reference_token(tokens, cursor)
    if not _reference_identifier(name):
        return None
    cursor = _reference_skip_newlines(tokens, cursor + 1)
    if _reference_token(tokens, cursor) == "[":
        type_end = _reference_group_end(tokens, cursor)
        if type_end is None:
            return None
        cursor = _reference_skip_newlines(tokens, type_end + 1)
    if _reference_token(tokens, cursor) != "(":
        return None
    parameters_end = _reference_group_end(tokens, cursor)
    if parameters_end is None:
        return None
    return name, has_receiver, cursor, parameters_end


def _reference_ends_statement(token: str) -> bool:
    return _reference_identifier(token) or token in {")", "]", "}"}


def _reference_body(
    tokens: list[ReferenceToken], index: int
) -> tuple[int | None, int | None, int]:
    depth = 0
    previous = ")"
    while index < len(tokens):
        token, start, stop = tokens[index]
        if token == "\n" and depth == 0:
            if _reference_ends_statement(previous):
                return None, None, index + 1
            index += 1
            continue
        if token == ";" and depth == 0:
            return None, None, index + 1
        if token == "{" and depth == 0:
            body_end = _reference_group_end(tokens, index)
            if body_end is None:
                return None, None, len(tokens)
            return stop, tokens[body_end][1], body_end + 1
        if token in "([":
            depth += 1
        elif token in ")]" and depth:
            depth -= 1
        if token != "\n":
            previous = token
        index += 1
    return None, None, index


def _reference_declaration(
    source: str, tokens: list[ReferenceToken], index: int
) -> tuple[ReferenceSpan | None, int]:
    signature = _reference_signature(tokens, index)
    if signature is None:
        return None, index + 1
    name, has_receiver, parameters_open, parameters_end = signature
    body_start, body_stop, resume = _reference_body(tokens, parameters_end + 1)
    declaration_start = tokens[index][1]
    span = (
        name,
        declaration_start,
        source.count("\n", 0, declaration_start) + 1,
        source[tokens[parameters_open][2] : tokens[parameters_end][1]],
        has_receiver,
        body_start,
        body_stop,
    )
    return span, resume


def reference_spans(masked_source: str) -> list[ReferenceSpan]:
    """Find spans with a token-boundary design independent of production grammar."""
    tokens = _reference_tokens(masked_source)
    spans: list[ReferenceSpan] = []
    index = depth = 0
    previous: str | None = None
    while index < len(tokens):
        lexeme = tokens[index][0]
        at_boundary = previous is None or previous in {"\n", ";"}
        if depth == 0 and lexeme == "func" and at_boundary:
            span, resume = _reference_declaration(masked_source, tokens, index)
            if span is not None:
                spans.append(span)
            if resume > index + 1:
                previous = tokens[resume - 1][0]
                index = resume
                continue
        if lexeme in "([{":
            depth += 1
        elif lexeme in ")]}" and depth:
            depth -= 1
        previous = lexeme
        index += 1
    return spans


GO_PARSER_ORACLE = r"""
package main

import (
    "encoding/json"
    "fmt"
    "go/ast"
    "go/parser"
    "go/token"
    "io"
    "os"
)

type span struct {
    Name             string `json:"name"`
    DeclarationStart int    `json:"declaration_start"`
    Line             int    `json:"line"`
    Parameters       string `json:"parameters"`
    HasReceiver      bool   `json:"has_receiver"`
    BodyStart        *int   `json:"body_start"`
    BodyStop         *int   `json:"body_stop"`
}

func fail(format string, arguments ...interface{}) {
    fmt.Fprintf(os.Stderr, format+"\n", arguments...)
    os.Exit(2)
}

func offset(files *token.FileSet, position token.Pos) int {
    return files.PositionFor(position, false).Offset
}

func main() {
    source, err := io.ReadAll(io.LimitReader(os.Stdin, 1<<20))
    if err != nil {
        fail("read fixture: %v", err)
    }
    files := token.NewFileSet()
    file, err := parser.ParseFile(files, "fixture.go", source, parser.AllErrors)
    if err != nil {
        fail("parse fixture: %v", err)
    }
    spans := make([]span, 0)
    for _, item := range file.Decls {
        function, ok := item.(*ast.FuncDecl)
        if !ok {
            continue
        }
        opening := offset(files, function.Type.Params.Opening)
        closing := offset(files, function.Type.Params.Closing)
        position := files.PositionFor(function.Type.Func, false)
        found := span{
            Name: function.Name.Name,
            DeclarationStart: position.Offset,
            Line: position.Line,
            Parameters: string(source[opening+1 : closing]),
            HasReceiver: function.Recv != nil,
        }
        if function.Body != nil {
            bodyStart := offset(files, function.Body.Lbrace) + 1
            bodyStop := offset(files, function.Body.Rbrace)
            found.BodyStart = &bodyStart
            found.BodyStop = &bodyStop
        }
        spans = append(spans, found)
    }
    if err := json.NewEncoder(os.Stdout).Encode(spans); err != nil {
        fail("encode spans: %v", err)
    }
}
"""

GO_PARSER_FIXTURE = '''package oracle

var callback func(int) error
var factory = func() func(int) error {
    return func(int) error { return nil }
}
type Callback func()
type Box[T any] struct{}
type Result struct{ Value int }

func external(value int) int
func (box *Box[T]) Method(cb func(int) error) (int, error) {
    if cb != nil { return 1, nil }
    return 0, nil
}
func generic[T comparable](value T) struct{ Value T } {
    return struct{ Value T }{Value: value}
}
func interfaceResult() interface{ Run() } { return nil }
func multiline(value int) *
Result { return nil }
func
TestMasked(t *testing.T) {
retry:
    channels := map[string]chan int{}
    if false { goto retry }
    interpreted := "} func TestString(t *testing.T) {"
    raw := `} func TestRaw(t *testing.T) {`
    runeValue := '}'
    // } func TestComment(t *testing.T) {
    /* func TestBlock(t *testing.T) {} */
    closure := func() { nested() }
    _, _, _, _, _ = channels, interpreted, raw, runeValue, closure
}
func TestSubtest(t *testing.T) {
    t.Run("child", func(t *testing.T) {})
}
'''

EXPECTED_GO_ORACLE_NAMES = [
    "external",
    "Method",
    "generic",
    "interfaceResult",
    "multiline",
    "TestMasked",
    "TestSubtest",
]


def project_span(span: object) -> tuple[object, ...]:
    body = span.body
    return (
        span.name,
        span.declaration_start,
        span.line,
        span.parameters,
        span.has_receiver,
        None if body is None else body.start,
        None if body is None else body.stop,
    )


BODY_FORMS = (
    "{}\n",
    "{\n    if true { nested() }\n}\n",
    "{\n    closure := func() { nested() }\n    closure()\n}\n",
    '''{
    // } func TestComment(t *testing.T) {
    interpreted := "{ } func TestString(t *testing.T) {}"
    raw := `} func TestRaw(t *testing.T) {`
    runeValue := '{'
    _, _, _ = interpreted, raw, runeValue
}
''',
)
# The independent reference deliberately treats the first top-level brace after
# parameters as the body. Explicit cases and the Go parser oracle below cover
# brace-bearing result types without copying production's struct/interface grammar.
RESULT_FORMS = (
    "",
    " error",
    " []byte",
    " (int, error)",
    " *\nResult",
    " func (int) error",
)
PARAMETER_FORMS = ("", "t *testing.T", "t *testing.T, cb func(int) error")
RECEIVER_FORMS = (
    "(r *Box[T]) ",
    "(r *Box[T])",
    "((r *Box[T])) ",
    "(r (*Box[T]))",
)
TOP_LEVEL_DECOYS = (
    "",
    '// func TestComment(t *testing.T) {}\n',
    'var text = "func TestString(t *testing.T) { }"\n',
    "var raw = `func TestRaw(t *testing.T) { }`\n",
    'var registry = map[string]func(){"x": func() { nested() }}\n',
    "var callback func (int) error\n",
    "type Callback func ()\n",
    "var factory = func () func (int) error {\n"
    "    return func (int) error { return nil }\n"
    "}\n",
)


def random_declaration(rng: random.Random, serial: int) -> str:
    has_receiver = rng.randrange(5) == 0
    prefix = "func\n" if rng.randrange(4) == 0 else "func "
    receiver = rng.choice(RECEIVER_FORMS) if has_receiver else ""
    name_prefix = rng.choice(("Test", "helper", "work"))
    name = f"{name_prefix}{serial}"
    type_parameters = "[T comparable]" if not has_receiver and rng.randrange(4) == 0 else ""
    parameters = rng.choice(PARAMETER_FORMS)
    result = rng.choice(RESULT_FORMS)
    header = f"{prefix}{receiver}{name}{type_parameters}({parameters}){result}"
    return header + ("\n" if rng.randrange(5) == 0 else " " + rng.choice(BODY_FORMS))


REGRESSION_SOURCES = {
    "delegates_test.go": """package x
func helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestDelegates(t *testing.T) { helper(t) }
""",
    "one_line_helper_test.go": """package x
func noop(t *testing.T) {}
var registry = map[string]func(*testing.T){"x": func(t *testing.T) { t.Helper(); t.Errorf("x") }}
func TestUsesNoop(t *testing.T) { noop(t) }
""",
    "one_line_test.go": """package x
func helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestEmpty(t *testing.T) {}
var registry = map[string]func(){"x": func() { helper(nil) }}
""",
    "nested_test.go": """package x
func helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestNested(t *testing.T) { if true { setup() }; helper(t) }
""",
    "closure_test.go": """package x
func helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestClosure(t *testing.T) { func() { setup() }(); helper(t) }
""",
    "duplicate_test.go": """package x
func helper(t *testing.T) { t.Helper(); t.Errorf("first") }
func helper(t *testing.T) { t.Helper(); t.Errorf("second") }
func TestDuplicate(t *testing.T) { helper(t) }
""",
    "indented_test.go": """package x
func helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
    func TestIndented(t *testing.T) {}
func trailing(t *testing.T) { helper(t) }
""",
    "declaration_test.go": """package x
func helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestDeclaration(t *testing.T) { if false { func helper(t) } }
""",
    "trailing_direct_test.go": """package x
func TestTrailing(t *testing.T) {}
func trailing(t *testing.T) { t.Errorf("failure") }
""",
    "raw_phantom_test.go": """package x
func helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestRaw(t *testing.T) {
    fixture := `func TestPhantom(t *testing.T) {}`
    _ = fixture
    helper(t)
}
/* func TestOld(t *testing.T) {} */
""",
    "marker_borrow_test.go": """package x
func mark(t *testing.T) { t.Helper() }
var registry = map[string]func(*testing.T){"x": func(t *testing.T) { t.Errorf("x") }}
func TestMarker(t *testing.T) { mark(t) }
""",
    "bodiless_test.go": """package x
func TestExternal(t *testing.T)
func later(t *testing.T) { t.Errorf("failure") }
""",
    "newline_test.go": """package x
func
helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func
TestIdle(t *testing.T) {}
""",
    "multiline_result_test.go": """package x
func helper(t *testing.T) *
Result { t.Helper(); t.Errorf("failure"); return nil }
func TestMultilineResult(t *testing.T) { helper(t) }
""",
    "generic_call_test.go": """package x
type H[T any] struct{}
type G[T any] struct{}
func helper[T any](t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestGenericCall(t *testing.T) { helper[G[H[int]]](t) }
""",
    "qualified_call_test.go": """package x
func helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestQualified(t *testing.T) { other . helper(t) }
""",
}


def regression_source(label: str) -> str:
    return REGRESSION_SOURCES[label]


def differential_cases() -> list[DifferentialCase]:
    return [
        (
            "delegates_test.go",
            regression_source("delegates_test.go"),
            ((3, "TestDelegates"),),
            (),
        ),
        (
            "one_line_helper_test.go",
            regression_source("one_line_helper_test.go"),
            ((4, "TestUsesNoop"),),
            ((4, "TestUsesNoop"),),
        ),
        (
            "one_line_test.go",
            regression_source("one_line_test.go"),
            ((3, "TestEmpty"),),
            ((3, "TestEmpty"),),
        ),
        (
            "nested_test.go",
            regression_source("nested_test.go"),
            ((3, "TestNested"),),
            (),
        ),
        (
            "closure_test.go",
            regression_source("closure_test.go"),
            ((3, "TestClosure"),),
            (),
        ),
        (
            "duplicate_test.go",
            regression_source("duplicate_test.go"),
            ((4, "TestDuplicate"),),
            ((4, "TestDuplicate"),),
        ),
        (
            "indented_test.go",
            regression_source("indented_test.go"),
            ((3, "TestIndented"),),
            ((3, "TestIndented"),),
        ),
        (
            "declaration_test.go",
            regression_source("declaration_test.go"),
            ((3, "TestDeclaration"),),
            ((3, "TestDeclaration"),),
        ),
        (
            "trailing_direct_assertion_outside_test.go",
            regression_source("trailing_direct_test.go"),
            (),
            (),
        ),
        (
            "raw_phantom_test.go",
            regression_source("raw_phantom_test.go"),
            ((3, "TestRaw"),),
            (),
        ),
        (
            "marker_borrow_test.go",
            regression_source("marker_borrow_test.go"),
            ((4, "TestMarker"),),
            ((4, "TestMarker"),),
        ),
        (
            "bodiless_external_decl_test.go",
            regression_source("bodiless_test.go"),
            (),
            (),
        ),
        (
            "newline_test.go",
            regression_source("newline_test.go"),
            ((4, "TestIdle"),),
            ((4, "TestIdle"),),
        ),
        (
            "multiline_result_test.go",
            regression_source("multiline_result_test.go"),
            ((4, "TestMultilineResult"),),
            (),
        ),
        (
            "generic_call_test.go",
            regression_source("generic_call_test.go"),
            ((5, "TestGenericCall"),),
            (),
        ),
        (
            "qualified_call_test.go",
            regression_source("qualified_call_test.go"),
            ((3, "TestQualified"),),
            ((3, "TestQualified"),),
        ),
        (
            "raw_function_boundary_test.go",
            '''package x
func helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestBoundary(t *testing.T) {
    fixture := `
func TestPhantom(t *testing.T) {}
`
    _ = fixture
    helper(t)
}
/*
func TestOld(t *testing.T) {}
*/
''',
            ((3, "TestBoundary"), (5, "TestPhantom"), (11, "TestOld")),
            (),
        ),
        (
            "label_and_goto_test.go",
            '''package x

func TestLabel(t *testing.T) {
start:
    if ready() { goto start }
}
''',
            ((2, "TestLabel"),),
            ((3, "TestLabel"),),
        ),
        (
            "chan_map_keywords_in_body_test.go",
            '''package x

func TestKeywords(t *testing.T) {
    var values chan map[string]func()
    _ = values
}
''',
            ((2, "TestKeywords"),),
            ((3, "TestKeywords"),),
        ),
        (
            "subtest_run_with_closure_test.go",
            '''package x
func helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestSubtest(t *testing.T) {
    t.Run("child", func(t *testing.T) { helper(t) })
}
''',
            ((3, "TestSubtest"),),
            (),
        ),
        (
            "two_level_chain_test.go",
            '''package x
func base(tb testing.TB) { tb.Helper(); tb.Errorf("bad") }
func outer(t *testing.T) { t.Helper(); base(t) }
func TestChain(t *testing.T) { outer(t) }
''',
            ((4, "TestChain"),),
            (),
        ),
        (
            "grouped_param_names_test.go",
            '''package x
func helper(t, u, v *testing.T) { t.Helper(); t.Errorf("bad") }
func TestGrouped(t *testing.T) { helper(t, t, t) }
''',
            ((3, "TestGrouped"),),
            (),
        ),
        (
            "raw_string_duplicate_helper_test.go",
            '''package x
var fixture = `func helper(t *testing.T) { t.Helper(); t.Errorf("phantom") }`
func helper(t *testing.T) { t.Helper(); t.Errorf("real") }
func TestRawDuplicate(t *testing.T) { helper(t) }
''',
            ((4, "TestRawDuplicate"),),
            (),
        ),
        (
            "nested_block_no_hide_test.go",
            '''package x
func helper(t *testing.T) { t.Helper(); if failed() { t.Errorf("bad") } }
func TestNestedBlock(t *testing.T) { helper(t) }
''',
            ((3, "TestNestedBlock"),),
            (),
        ),
        (
            "anon_function_no_end_test.go",
            '''package x
func helper(t *testing.T) { t.Helper(); func() { t.Errorf("bad") }() }
func TestAnon(t *testing.T) { helper(t) }
''',
            ((3, "TestAnon"),),
            (),
        ),
        (
            "one_line_registry_test.go",
            '''package x
var registry = map[string]func(*testing.T){"x": func(t *testing.T) { t.Errorf("x") }}

func TestRegistry(t *testing.T) { noop(t) }
''',
            ((3, "TestRegistry"),),
            ((4, "TestRegistry"),),
        ),
        (
            "direct_errorf_test.go",
            '''package x
func TestDirect(t *testing.T) { t.Errorf("failure") }
''',
            (),
            (),
        ),
        (
            "direct_require_test.go",
            '''package x
func TestRequire(t *testing.T) { require.Equal(t, 1, 2) }
''',
            (),
            (),
        ),
        (
            "assertion_free_test.go",
            '''package x
func TestEmpty(t *testing.T) {}
''',
            ((2, "TestEmpty"),),
            ((2, "TestEmpty"),),
        ),
        (
            "method_receiver_helper_test.go",
            '''package x
func (s *Suite) helper(t *testing.T) { t.Helper(); t.Errorf("bad") }
func TestMethod(t *testing.T) { helper(t) }
''',
            ((3, "TestMethod"),),
            ((3, "TestMethod"),),
        ),
        (
            "fallback_without_assertion.go",
            '''package x
func helper(t *testing.T) {}
''',
            ((1, "fallback_without_assertion.go"),),
            ((1, "fallback_without_assertion.go"),),
        ),
        (
            "multiple_tests_mixed_test.go",
            '''package x
func TestAsserted(t *testing.T) { t.Errorf("bad") }
func TestEmpty(t *testing.T) {}
''',
            ((3, "TestEmpty"),),
            ((3, "TestEmpty"),),
        ),
    ]


def finding_rows(label: str, stdout: str) -> FindingRows:
    prefix = f"forge: assertion-free test detected: {label}:"
    rows: list[tuple[int, str]] = []
    for rendered in stdout.splitlines():
        if not rendered.startswith(prefix):
            raise AssertionError(f"unexpected differential output: {rendered!r}")
        location = rendered.removeprefix(prefix)
        line_text, separator, name = location.partition(":")
        if not separator or not line_text.isdecimal() or not name:
            raise AssertionError(f"malformed differential finding: {rendered!r}")
        rows.append((int(line_text), name))
    return tuple(rows)


class GoSpanPropertyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.namespace = runpy.run_path(str(SENSOR), run_name="forge_test_quality_sensor")
        cls.mask = staticmethod(cls.namespace["_mask_go_non_code"])
        cls.spans = staticmethod(cls.namespace["_go_function_spans"])

    def test_random_go_like_files_match_independent_reference(self) -> None:
        rng = random.Random(0xF09E)
        for case in range(400):
            declarations = [
                rng.choice(TOP_LEVEL_DECOYS) + random_declaration(rng, case * 10 + item)
                for item in range(rng.randint(1, 8))
            ]
            source = "package property\n" + "".join(declarations)
            masked = self.mask(source)
            expected = reference_spans(masked)
            actual = [project_span(span) for span in self.spans(masked)]
            with self.subTest(case=case, source=source):
                self.assertEqual(actual, expected)

    def test_spans_match_optional_go_parser_oracle(self) -> None:
        go_executable = shutil.which("go")
        if go_executable is None:
            self.skipTest("optional go/parser oracle requires 'go' on PATH")
        self.assertTrue(GO_PARSER_FIXTURE.isascii())
        with tempfile.TemporaryDirectory(prefix="forge-go-parser-oracle-") as temp_dir:
            scratch = Path(temp_dir)
            oracle_path = scratch / "oracle.go"
            oracle_path.write_text(GO_PARSER_ORACLE, encoding="utf-8")
            go_paths = {
                "GOCACHE": scratch / "go-cache",
                "GOMODCACHE": scratch / "go-mod-cache",
                "GOPATH": scratch / "go-path",
                "GOTMPDIR": scratch / "go-tmp",
            }
            for path in go_paths.values():
                path.mkdir()
            environment = dict(os.environ)
            environment.update(
                {name: str(path) for name, path in go_paths.items()}
            )
            environment.update(
                {
                    "CGO_ENABLED": "0",
                    "GO111MODULE": "off",
                    "GOENV": "off",
                    "GOFLAGS": "",
                    "GOPROXY": "off",
                    "GOSUMDB": "off",
                    "GOTELEMETRY": "off",
                    "GOTOOLCHAIN": "local",
                    "GOWORK": "off",
                }
            )
            result = subprocess.run(
                [go_executable, "run", str(oracle_path)],
                cwd=scratch,
                env=environment,
                input=GO_PARSER_FIXTURE,
                check=False,
                capture_output=True,
                text=True,
                timeout=GO_ORACLE_TIMEOUT_SECONDS,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        oracle = [
            (
                item["name"],
                item["declaration_start"],
                item["line"],
                item["parameters"],
                item["has_receiver"],
                item["body_start"],
                item["body_stop"],
            )
            for item in json.loads(result.stdout)
        ]
        actual = [
            project_span(span) for span in self.spans(self.mask(GO_PARSER_FIXTURE))
        ]
        self.assertEqual([span[0] for span in oracle], EXPECTED_GO_ORACLE_NAMES)
        self.assertEqual(oracle[0][-2:], (None, None))
        self.assertEqual(actual, oracle)

    def test_span_table_covers_receivers_generics_results_and_bodiless(self) -> None:
        source = """package x
func external(value int) int
func (box *Box[T]) Method(cb func(int) error) (int, error) {}
func generic[T comparable](value T) struct{ Value T } { return struct{ Value T }{value} }
func
TestNewline(t *testing.T) {}
"""
        actual = [project_span(span) for span in self.spans(self.mask(source))]

        self.assertEqual(
            [span[0] for span in actual],
            ["external", "Method", "generic", "TestNewline"],
        )
        self.assertIsNone(actual[0][-1])
        self.assertTrue(actual[1][4])
        self.assertEqual(
            source[actual[2][-2] : actual[2][-1]].strip(),
            "return struct{ Value T }{value}",
        )
        self.assertEqual(actual[3][2], 5)

    def test_compact_nested_receivers_and_function_type_decoys(self) -> None:
        source = """package x
var callback func (int) error
var factory = func () func (int) error {
    return func (int) error { return nil }
}
func(r *Box[T])Compact() {}
func((r *Box[T]))Nested() {}
func helper(t *testing.T) *
Result { return nil }
type Callback func ()
func TestActual(t *testing.T) {}
"""
        actual = [project_span(span) for span in self.spans(self.mask(source))]

        self.assertEqual(
            [span[0] for span in actual],
            ["Compact", "Nested", "helper", "TestActual"],
        )
        self.assertEqual([span[4] for span in actual], [True, True, False, False])
        self.assertEqual(source[actual[2][-2] : actual[2][-1]].strip(), "return nil")

    def test_superseded_per_analysis_scanners_are_absent(self) -> None:
        for name in (
            "GO_BODY_END_RE",
            "GO_FUNCTION_RE",
            "GO_TEST_BODY_OPEN_RE",
            "_go_body",
            "_go_same_line_body_end",
            "_go_test_body",
        ):
            with self.subTest(name=name):
                self.assertNotIn(name, self.namespace)


class GoSpanRegressionTests(helpers.GoHelperTestCase):
    def test_one_line_noop_cannot_borrow_marker_or_assertion(self) -> None:
        source = regression_source("one_line_helper_test.go")
        label = self.write("one_line_noop_test.go", source)
        expected = self.finding(label, source, "TestUsesNoop")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(helpers.EXACT_BODY_END, helpers.UNBOUNDED_BODY_END)
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_one_line_marker_cannot_borrow_later_assertion(self) -> None:
        source = """package x
func mark(t *testing.T) { t.Helper() }
var registry = map[string]func(*testing.T){"x": func(t *testing.T) { t.Errorf("x") }}
func TestUsesMark(t *testing.T) { mark(t) }
"""
        label = self.write("one_line_marker_test.go", source)
        expected = self.finding(label, source, "TestUsesMark")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(helpers.EXACT_BODY_END, helpers.UNBOUNDED_BODY_END)
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_func_newline_name_is_structural_and_reports_func_line(self) -> None:
        source = regression_source("newline_test.go")
        label = self.write("newline_name_test.go", source)
        expected = f"forge: assertion-free test detected: {label}:4:TestIdle\n"

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(FUNC_NAME_SPACE, SAME_LINE_FUNC_NAME)
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")
        shifted = self.mutant(LINE_RECORDING, SHIFTED_LINE_RECORDING)
        shifted_output = expected.replace(":4:TestIdle", ":3:TestIdle")
        self.assert_advisory(self.run_sensor(label, sensor=shifted), shifted_output)

    def test_func_newline_layout_finishes_within_hang_guard(self) -> None:
        declarations = "".join(
            f"func\nh{index:04d}(t *testing.T) {{ t.Helper() }}\n"
            for index in range(4_000)
        )
        source = "package x\n" + declarations + "func\nTestIdle(t *testing.T) {}\n"
        self.assertGreater(len(source.encode()), 150_000)
        label = self.write("newline_scale_test.go", source)

        started = time.perf_counter()
        result = self.run_sensor(label, timeout=TIMEOUT_SECONDS)
        elapsed = time.perf_counter() - started

        line = source.count("\n", 0, source.index("func\nTestIdle")) + 1
        expected = f"forge: assertion-free test detected: {label}:{line}:TestIdle\n"
        self.assert_advisory(result, expected)
        self.assertLess(elapsed, TIMEOUT_SECONDS)

    def test_long_top_level_tokens_finish_within_hang_guard(self) -> None:
        disabled = self.mutant(IDENTIFIER_JUMP, DISABLED_IDENTIFIER_JUMP)
        tokens = {
            "identifier": "identifier" * 18_750,
            "hex_literal": "0x" + "f" * 150_000,
        }
        for kind, token in tokens.items():
            source = f"package x\n{token}\nfunc TestIdle(t *testing.T) {{}}\n"
            label = self.write(f"long_{kind}_test.go", source)
            expected = self.finding(label, source, "TestIdle")

            with self.subTest(kind=kind, sensor="production"):
                started = time.perf_counter()
                result = self.run_sensor(
                    label, timeout=TOKEN_SCAN_TIMEOUT_SECONDS
                )
                elapsed = time.perf_counter() - started
                self.assert_advisory(result, expected)
                self.assertLess(elapsed, TOKEN_SCAN_TIMEOUT_SECONDS)
            with self.subTest(kind=kind), self.assertRaises(subprocess.TimeoutExpired):
                self.run_sensor(
                    label,
                    sensor=disabled,
                    timeout=TOKEN_SCAN_TIMEOUT_SECONDS,
                )

    def test_multiline_scalar_result_keeps_helper_body(self) -> None:
        source = regression_source("multiline_result_test.go")
        label = self.write("multiline_result_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")
        disabled = self.mutant(
            CONTINUED_RESULT_NEWLINE,
            ALL_NEWLINES_END_DECLARATION,
        )
        self.assert_advisory(
            self.run_sensor(label, sensor=disabled),
            self.finding(label, source, "TestMultilineResult"),
        )

    def test_compact_nested_method_receiver_cannot_be_free_helper(self) -> None:
        source = """package x
func(r (*Box[T]))helper(t *testing.T) { t.Helper(); t.Errorf("failure") }
func TestMethodName(t *testing.T) { helper(t) }
"""
        label = self.write("compact_receiver_test.go", source)
        expected = self.finding(label, source, "TestMethodName")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(
            RECEIVER_CLASSIFICATION,
            DISABLED_RECEIVER_CLASSIFICATION,
        )
        self.assert_advisory(self.run_sensor(label, sensor=disabled), "")

    def test_spaced_function_types_and_literals_are_not_declarations(self) -> None:
        source = """package x
var callback func (int) error
var factory = func () func (int) error {
    return func (int) error { return nil }
}
type Callback func ()
func TestDecoys(t *testing.T) { factory() }
"""
        label = self.write("function_type_decoys_test.go", source)
        expected = self.finding(label, source, "TestDecoys")

        self.assert_advisory(self.run_sensor(label), expected)
        disabled = self.mutant(KEYWORD_NAME_CHECK, DISABLED_KEYWORD_NAME_CHECK)
        namespace = runpy.run_path(str(disabled), run_name="disabled_go_span_sensor")
        masked = namespace["_mask_go_non_code"](source)
        names = [span.name for span in namespace["_go_function_spans"](masked)]
        self.assertIn("func", names)

    def test_generic_helper_call_is_resolved(self) -> None:
        source = regression_source("generic_call_test.go")
        label = self.write("generic_call_test.go", source)

        self.assert_advisory(self.run_sensor(label), "")
        disabled = self.mutant(GENERIC_CALL_SCAN, DISABLED_GENERIC_CALL_SCAN)
        self.assert_advisory(
            self.run_sensor(label, sensor=disabled),
            self.finding(label, source, "TestGenericCall"),
        )

    def test_nested_bracket_call_scan_finishes_within_hang_guard(self) -> None:
        nested_expression = "a[" * 60_000 + "0" + "]" * 60_000
        source = (
            "package x\n"
            "func TestNestedBrackets(t *testing.T) {\n"
            f"    _ = {nested_expression}\n"
            "}\n"
        )
        self.assertGreater(len(source.encode()), 150_000)
        label = self.write("nested_bracket_scale_test.go", source)

        started = time.perf_counter()
        result = self.run_sensor(label, timeout=TIMEOUT_SECONDS)
        elapsed = time.perf_counter() - started

        self.assert_advisory(
            result,
            self.finding(label, source, "TestNestedBrackets"),
        )
        self.assertLess(elapsed, TIMEOUT_SECONDS)

    def test_base_differential_has_only_expected_directions(self) -> None:
        base_source = subprocess.run(
            ["git", "show", "109c565:scripts/forge/check-test-quality.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        base_sensor = self.scratch / "base-check-test-quality.py"
        base_sensor.write_text(base_source, encoding="utf-8")

        cases = differential_cases()
        self.assertGreaterEqual(len(cases), 30)
        for label, source, expected_base, expected_candidate in cases:
            relative = self.write(label, source)
            base = self.run_sensor(relative, sensor=base_sensor)
            candidate = self.run_sensor(relative)
            with self.subTest(label=label, base=base.stdout, candidate=candidate.stdout):
                self.assertEqual((base.returncode, base.stderr), (0, ""))
                self.assertEqual((candidate.returncode, candidate.stderr), (0, ""))
                self.assertEqual(finding_rows(label, base.stdout), expected_base)
                self.assertEqual(
                    finding_rows(label, candidate.stdout), expected_candidate
                )


if __name__ == "__main__":
    unittest.main()
