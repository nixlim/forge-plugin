#!/usr/bin/env python3
"""Detect assertion-free tests without requiring target-project dependencies."""

from __future__ import annotations

import argparse
import ast
import builtins
import fnmatch
import io
import re
import sys
import tokenize
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from re import Pattern

FAILURE_MESSAGE = "forge: test-quality check failed to execute"
FINDING_TEMPLATE = "forge: assertion-free test detected: {path}:{line}:{name}"
INCONCLUSIVE_TEMPLATE = (
    "forge: assertion check inconclusive: {path}:{line}:{name} — advisory only"
)
NO_HEURISTIC_TEMPLATE = "forge: no seeded assertion heuristic for {stack} — advisory only"
WAIVER_TEMPLATE = "forge: assertion waiver: {path}: {reason}"

ASSERTION_HEURISTIC_RE = re.compile(r"^Assertion heuristic: (regex|literal): `([^`]+)`$")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
CODE_SPAN_RE = re.compile(r"`([^`]+)`")
WAIVER_RE = re.compile(r"^[ \t]*# forge-assertion-waiver: (?P<reason>\S(?:.*\S)?)[ \t]*$")
WAIVER_CANDIDATE_RE = re.compile(r"^[ \t]*#\s*forge-assertion-waiver:")

STACK_ALIASES = {
    "java-gradle / kotlin": "java-gradle-kotlin",
}
NODE_SUFFIXES = {".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"}
MAX_HELPER_DEPTH = 8
BUILTIN_NAMES = frozenset(dir(builtins))

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


class CheckFailure(Exception):
    """An input or execution failure covered by FR-144's exit-2 contract."""


class ContractArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CheckFailure(message)


@dataclass(frozen=True)
class StackRule:
    name: str
    patterns: tuple[str, ...]
    heuristic_kind: str | None
    heuristic_value: str | None
    compiled_regex: Pattern[str] | None
    explicit_absence: bool


@dataclass
class StackRuleBuilder:
    name: str
    patterns: tuple[str, ...] = ()
    heuristic_kind: str | None = None
    heuristic_value: str | None = None
    explicit_absence: bool = False
    saw_patterns: bool = False
    saw_assertion_declaration: bool = False

    def finish(self) -> StackRule:
        compiled: Pattern[str] | None = None
        if self.heuristic_kind == "regex":
            try:
                compiled = re.compile(self.heuristic_value or "", re.MULTILINE)
            except re.error as exc:
                raise CheckFailure("invalid assertion heuristic regex") from exc
        return StackRule(
            name=self.name,
            patterns=self.patterns,
            heuristic_kind=self.heuristic_kind,
            heuristic_value=self.heuristic_value,
            compiled_regex=compiled,
            explicit_absence=self.explicit_absence,
        )


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    name: str

    def render(self) -> str:
        return FINDING_TEMPLATE.format(path=self.path, line=self.line, name=self.name)


class AssertionStatus(Enum):
    FOUND = "found"
    MISSING = "missing"
    INCONCLUSIVE = "inconclusive"


class AssertionVisitor(ast.NodeVisitor):
    """Look for assertion evidence in one function, excluding nested scopes."""

    def __init__(self) -> None:
        self.found = False

    def visit_Assert(self, node: ast.Assert) -> None:  # noqa: N802
        self.found = True

    def visit_Raise(self, node: ast.Raise) -> None:  # noqa: N802
        self.found = True

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if _is_intrinsic_assertion_call(node):
            self.found = True
            return
        self.generic_visit(node)

    # Nested bodies are considered separately only when a call resolves to them.
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        return


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _qualified_call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _is_intrinsic_assertion_call(node: ast.Call) -> bool:
    name = _call_name(node.func)
    return (
        re.match(r"^assert(?:_|[A-Z])", name) is not None
        or (
            isinstance(node.func, ast.Attribute)
            and name in {"fail", "failIf", "failUnless"}
        )
    )


class FunctionScopeVisitor(ast.NodeVisitor):
    """Collect calls and bindings in one function-like lexical scope."""

    def __init__(self) -> None:
        self.calls: list[ast.Call] = []
        self.helpers: dict[str, list[FunctionNode]] = {}
        self.classes: dict[str, list[ast.ClassDef]] = {}
        self.other_bindings: set[str] = set()
        self.non_class_bindings: set[str] = set()
        self.non_import_bindings: set[str] = set()
        self.assigned_bindings: set[str] = set()
        self.imported_bindings: set[str] = set()
        self.pytest_module_imports: set[str] = set()
        self.pytest_call_imports: set[str] = set()

    def _add_non_import_binding(self, name: str) -> None:
        self.other_bindings.add(name)
        self.non_class_bindings.add(name)
        self.non_import_bindings.add(name)
        self.assigned_bindings.add(name)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        self.calls.append(node)
        self.generic_visit(node)

    def _visit_function(self, node: FunctionNode) -> None:
        self.helpers.setdefault(node.name, []).append(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.classes.setdefault(node.name, []).append(node)
        self.other_bindings.add(node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        return

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if isinstance(node.ctx, ast.Store | ast.Del):
            self._add_non_import_binding(node.id)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            name = alias.asname or alias.name.split(".", 1)[0]
            self.other_bindings.add(name)
            self.non_class_bindings.add(name)
            self.imported_bindings.add(name)
            if alias.name == "pytest":
                self.pytest_module_imports.add(name)
            else:
                self.non_import_bindings.add(name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        for alias in node.names:
            name = alias.asname or alias.name
            self.other_bindings.add(name)
            self.non_class_bindings.add(name)
            self.imported_bindings.add(name)
            if node.module == "pytest" and alias.name in {"fail", "raises"}:
                self.pytest_call_imports.add(name)
            else:
                self.non_import_bindings.add(name)

    def visit_Global(self, node: ast.Global) -> None:  # noqa: N802
        for name in node.names:
            self._add_non_import_binding(name)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:  # noqa: N802
        for name in node.names:
            self._add_non_import_binding(name)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        if node.name is not None:
            self._add_non_import_binding(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:  # noqa: N802
        if node.name is not None:
            self._add_non_import_binding(node.name)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:  # noqa: N802
        if node.name is not None:
            self._add_non_import_binding(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:  # noqa: N802
        if node.rest is not None:
            self._add_non_import_binding(node.rest)
        self.generic_visit(node)


class TestFunctionCollector(ast.NodeVisitor):
    """Collect module functions and class methods without entering functions."""

    def __init__(self) -> None:
        self.functions: list[tuple[FunctionNode, ast.ClassDef | None]] = []
        self.classes: list[ast.ClassDef] = []
        self._class_stack: list[ast.ClassDef] = []

    def _visit_function(self, node: FunctionNode) -> None:
        if node.name.startswith("test"):
            owner = self._class_stack[-1] if self._class_stack else None
            self.functions.append((node, owner))
        # A function nested inside another function is a helper, not a
        # separately collected test. Never descend into function bodies here.

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.classes.append(node)
        self._class_stack.append(node)
        for statement in node.body:
            self.visit(statement)
        self._class_stack.pop()


def _canonical_heading(raw_heading: str) -> str | None:
    heading = raw_heading.split(" (", 1)[0].strip()
    heading = STACK_ALIASES.get(heading, heading)
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*", heading):
        return heading
    return None


def parse_stack_rules(path: Path) -> dict[str, StackRule]:
    try:
        contents = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CheckFailure("could not read stack seed") from exc

    builders: dict[str, StackRuleBuilder] = {}
    current: StackRuleBuilder | None = None

    for raw_line in contents.splitlines():
        heading_match = HEADING_RE.fullmatch(raw_line)
        if heading_match:
            name = _canonical_heading(heading_match.group(1))
            if name is None:
                current = None
                continue
            if name in builders:
                raise CheckFailure("duplicate stack heading")
            current = StackRuleBuilder(name=name)
            builders[name] = current
            continue

        if current is None:
            continue

        if raw_line.startswith("Test file patterns:"):
            if current.saw_patterns:
                raise CheckFailure("duplicate test file patterns")
            patterns = tuple(CODE_SPAN_RE.findall(raw_line))
            if not patterns:
                raise CheckFailure("malformed test file patterns")
            current.patterns = patterns
            current.saw_patterns = True
            continue

        heuristic_match = ASSERTION_HEURISTIC_RE.fullmatch(raw_line)
        if heuristic_match:
            if current.saw_assertion_declaration:
                raise CheckFailure("duplicate assertion heuristic")
            current.heuristic_kind = heuristic_match.group(1)
            current.heuristic_value = heuristic_match.group(2)
            current.saw_assertion_declaration = True
            continue

        absence = f"No seeded assertion heuristic for {current.name}."
        if raw_line == absence:
            if current.saw_assertion_declaration:
                raise CheckFailure("duplicate assertion heuristic")
            current.explicit_absence = True
            current.saw_assertion_declaration = True
            continue

        if raw_line.startswith("Assertion heuristic:") or raw_line.startswith(
            "No seeded assertion heuristic for "
        ):
            raise CheckFailure("malformed assertion heuristic")

    return {name: builder.finish() for name, builder in builders.items()}


def _read_source(path: Path) -> str:
    try:
        if path.suffix.lower() == ".py":
            with tokenize.open(path) as source_file:
                return source_file.read()
        return path.read_text(encoding="utf-8")
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise CheckFailure("could not read test file") from exc


def _python_comment_lines(source: str) -> list[str]:
    comments: list[str] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type != tokenize.COMMENT:
                continue
            prefix = token.line[: token.start[1]]
            if prefix.strip():
                continue
            comments.append(token.string)
    except (IndentationError, SyntaxError, tokenize.TokenError):
        # A leading waiver comment may already have been tokenized before an
        # invalid generated fixture fails tokenization. Preserve those comments
        # so the waiver can skip analysis; without a waiver, ast.parse still
        # enforces the normal exit-2 contract below.
        pass
    return comments


def _waiver_reason(source: str, is_python: bool) -> str | None:
    candidates: list[str] = []
    malformed = False
    lines = _python_comment_lines(source) if is_python else source.splitlines()
    for line in lines:
        if not WAIVER_CANDIDATE_RE.match(line):
            continue
        match = WAIVER_RE.fullmatch(line)
        if match is None:
            malformed = True
            continue
        candidates.append(match.group("reason"))

    if malformed or len(candidates) > 1:
        raise CheckFailure("malformed assertion waiver")
    return candidates[0] if candidates else None


def _function_has_direct_assertion(node: FunctionNode) -> bool:
    visitor = AssertionVisitor()
    for statement in node.body:
        visitor.visit(statement)
        if visitor.found:
            return True
    return False


def _scope_for_statements(
    statements: Sequence[ast.stmt], extra_bindings: Sequence[str] = ()
) -> FunctionScopeVisitor:
    visitor = FunctionScopeVisitor()
    for name in extra_bindings:
        visitor._add_non_import_binding(name)
    for statement in statements:
        visitor.visit(statement)
    return visitor


def _parameter_names(node: FunctionNode) -> tuple[str, ...]:
    arguments = node.args
    names = [
        argument.arg
        for argument in (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
        )
    ]
    if arguments.vararg is not None:
        names.append(arguments.vararg.arg)
    if arguments.kwarg is not None:
        names.append(arguments.kwarg.arg)
    return tuple(names)


def _unique_helper(scope: FunctionScopeVisitor, name: str) -> FunctionNode | None:
    candidates = scope.helpers.get(name, [])
    if name in scope.other_bindings or len(candidates) != 1:
        return None
    return candidates[0]


def _unique_class(scope: FunctionScopeVisitor, name: str) -> ast.ClassDef | None:
    candidates = scope.classes.get(name, [])
    if (
        name in scope.helpers
        or name in scope.non_class_bindings
        or len(candidates) != 1
    ):
        return None
    return candidates[0]


def _scope_binds(scope: FunctionScopeVisitor, name: str) -> bool:
    return name in scope.helpers or name in scope.other_bindings


class AssertionResolver:
    """Resolve assertion delegation conservatively within one Python file."""

    def __init__(
        self,
        tree: ast.Module,
        classes: Sequence[ast.ClassDef],
    ) -> None:
        self.module_scope = _scope_for_statements(tree.body)
        self.class_scopes = {
            id(class_node): _scope_for_statements(class_node.body)
            for class_node in classes
        }
        self.method_owners: dict[int, ast.ClassDef] = {}
        for class_node in classes:
            class_scope = self.class_scopes[id(class_node)]
            for candidates in class_scope.helpers.values():
                for candidate in candidates:
                    self.method_owners[id(candidate)] = class_node

    @staticmethod
    def _has_pytest_call_import(scope: FunctionScopeVisitor, name: str) -> bool:
        return (
            name in scope.pytest_call_imports
            and name not in scope.pytest_module_imports
            and name not in scope.non_import_bindings
            and name not in scope.helpers
            and name not in scope.classes
        )

    @staticmethod
    def _has_pytest_module_import(scope: FunctionScopeVisitor, name: str) -> bool:
        return (
            name in scope.pytest_module_imports
            and name not in scope.pytest_call_imports
            and name not in scope.non_import_bindings
            and name not in scope.helpers
            and name not in scope.classes
        )

    def _binding_scope(
        self, local_scope: FunctionScopeVisitor, name: str
    ) -> FunctionScopeVisitor:
        if _scope_binds(local_scope, name):
            return local_scope
        return self.module_scope

    @staticmethod
    def _has_unshadowed_import(scope: FunctionScopeVisitor, name: str) -> bool:
        return (
            name in scope.imported_bindings
            and name not in scope.assigned_bindings
            and name not in scope.helpers
            and name not in scope.classes
        )

    def _is_assertion_call(
        self, call: ast.Call, local_scope: FunctionScopeVisitor
    ) -> bool:
        if _is_intrinsic_assertion_call(call):
            return True
        if isinstance(call.func, ast.Name):
            name = call.func.id
            scope = self._binding_scope(local_scope, name)
            return self._has_pytest_call_import(scope, name)
        if not isinstance(call.func, ast.Attribute):
            return False
        if call.func.attr not in {"fail", "raises"}:
            return False
        if not isinstance(call.func.value, ast.Name):
            return False
        name = call.func.value.id
        scope = self._binding_scope(local_scope, name)
        return self._has_pytest_module_import(scope, name)

    def _resolve_named_call(
        self,
        name: str,
        local_scope: FunctionScopeVisitor,
        owner: ast.ClassDef | None,
    ) -> tuple[FunctionNode, ast.ClassDef | None] | None:
        if name in local_scope.helpers or name in local_scope.other_bindings:
            local_helper = _unique_helper(local_scope, name)
            if local_helper is None:
                return None
            return local_helper, owner

        module_helper = _unique_helper(self.module_scope, name)
        if module_helper is None:
            return None
        return module_helper, None

    def _method_receiver_names(
        self, node: FunctionNode, owner: ast.ClassDef | None
    ) -> set[str]:
        if owner is None or self.method_owners.get(id(node)) is not owner:
            return set()
        if any(
            _qualified_call_name(decorator) == "staticmethod"
            for decorator in node.decorator_list
        ):
            return set()
        positional = (*node.args.posonlyargs, *node.args.args)
        return {positional[0].arg} if positional else set()

    def _resolve_call(
        self,
        call: ast.Call,
        node: FunctionNode,
        owner: ast.ClassDef | None,
        local_scope: FunctionScopeVisitor,
    ) -> tuple[FunctionNode, ast.ClassDef | None] | None:
        if isinstance(call.func, ast.Name):
            return self._resolve_named_call(call.func.id, local_scope, owner)

        if not isinstance(call.func, ast.Attribute):
            return None
        if not isinstance(call.func.value, ast.Name):
            return None
        receiver = call.func.value.id
        target_class: ast.ClassDef | None = None
        if owner is not None and receiver in self._method_receiver_names(node, owner):
            target_class = owner
        elif not _scope_binds(local_scope, receiver):
            target_class = _unique_class(self.module_scope, receiver)
        if target_class is None:
            return None

        class_scope = self.class_scopes[id(target_class)]
        method = _unique_helper(class_scope, call.func.attr)
        if method is None:
            return None
        return method, target_class

    def _is_plausible_external_delegate(
        self,
        call: ast.Call,
        local_scope: FunctionScopeVisitor,
    ) -> bool:
        if isinstance(call.func, ast.Name):
            name = call.func.id
            if name in BUILTIN_NAMES or name[:1].isupper():
                return False
            scope = self._binding_scope(local_scope, name)
            return self._has_unshadowed_import(scope, name)

        return (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "self"
        )

    def analyze(
        self,
        node: FunctionNode,
        owner: ast.ClassDef | None,
        *,
        depth: int = 0,
        visiting: frozenset[int] = frozenset(),
    ) -> AssertionStatus:
        if _function_has_direct_assertion(node):
            return AssertionStatus.FOUND
        if depth >= MAX_HELPER_DEPTH:
            return AssertionStatus.INCONCLUSIVE
        if id(node) in visiting:
            return AssertionStatus.MISSING

        local_scope = _scope_for_statements(node.body, _parameter_names(node))
        inconclusive = False
        next_visiting = visiting | {id(node)}
        for call in local_scope.calls:
            if self._is_assertion_call(call, local_scope):
                return AssertionStatus.FOUND
            resolved = self._resolve_call(call, node, owner, local_scope)
            if resolved is None:
                inconclusive = inconclusive or self._is_plausible_external_delegate(
                    call,
                    local_scope,
                )
                continue
            helper, helper_owner = resolved
            status = self.analyze(
                helper,
                helper_owner,
                depth=depth + 1,
                visiting=next_visiting,
            )
            if status is AssertionStatus.FOUND:
                return AssertionStatus.FOUND
            if status is AssertionStatus.INCONCLUSIVE:
                inconclusive = True

        if inconclusive:
            return AssertionStatus.INCONCLUSIVE
        return AssertionStatus.MISSING


def _python_diagnostics(path_label: str, source: str) -> tuple[list[str], bool]:
    try:
        tree = ast.parse(source, filename=path_label)
    except (SyntaxError, ValueError) as exc:
        raise CheckFailure("could not parse Python test") from exc

    collector = TestFunctionCollector()
    collector.visit(tree)
    test_functions = collector.functions
    test_functions.sort(
        key=lambda item: (item[0].lineno, item[0].col_offset, item[0].name)
    )
    resolver = AssertionResolver(tree, collector.classes)
    output: list[str] = []
    blocking = False
    for node, owner in test_functions:
        status = resolver.analyze(node, owner)
        if status is AssertionStatus.FOUND:
            continue
        if status is AssertionStatus.INCONCLUSIVE:
            output.append(
                INCONCLUSIVE_TEMPLATE.format(
                    path=path_label,
                    line=node.lineno,
                    name=node.name,
                )
            )
            continue
        output.append(Finding(path_label, node.lineno, node.name).render())
        blocking = True
    return output, blocking


def _path_matches_pattern(path: Path, pattern: str) -> bool:
    candidates = {path.as_posix(), path.name}
    try:
        candidates.add(path.resolve().relative_to(Path.cwd().resolve()).as_posix())
    except (OSError, ValueError):
        pass

    patterns = {pattern}
    if pattern.startswith("**/"):
        patterns.add(pattern[3:])
    return any(
        fnmatch.fnmatchcase(candidate, candidate_pattern)
        for candidate in candidates
        for candidate_pattern in patterns
    )


def _has_marker(path: Path, marker_names: Sequence[str]) -> bool:
    starts = [path.resolve().parent, Path.cwd().resolve()]
    visited: set[Path] = set()
    for start in starts:
        for directory in (start, *start.parents):
            if directory in visited:
                continue
            visited.add(directory)
            if any((directory / marker).exists() for marker in marker_names):
                return True
    return False


def _fallback_stack(path: Path) -> str:
    name = path.name
    suffix = path.suffix.lower()
    lower_parts = {part.lower() for part in path.parts}

    if suffix == ".py":
        return "python"
    if suffix in NODE_SUFFIXES:
        return "node"
    if suffix == ".go":
        return "go"
    if suffix == ".rs":
        return "rust"
    if suffix == ".kt" or suffix == ".kts":
        return "java-gradle-kotlin"
    if suffix == ".java":
        if _has_marker(path, ("build.gradle", "build.gradle.kts", "gradlew")):
            return "java-gradle-kotlin"
        return "java-maven"
    if suffix == ".tf" or name.endswith(".tftest.hcl"):
        return "terraform"
    if name.startswith("Dockerfile") or "docker" in lower_parts:
        return "docker"
    if "helm" in lower_parts or name in {"Chart.yaml", "Chart.yml"}:
        return "helm"
    return suffix.removeprefix(".") or "unknown"


def _infer_stack(path: Path, rules: dict[str, StackRule], override: str | None) -> str:
    if override is not None:
        return override

    matches = [
        name
        for name, rule in rules.items()
        if any(_path_matches_pattern(path, pattern) for pattern in rule.patterns)
    ]
    if len(matches) == 1:
        return matches[0]
    if "java-maven" in matches and "java-gradle-kotlin" in matches:
        if _has_marker(path, ("build.gradle", "build.gradle.kts", "gradlew")):
            return "java-gradle-kotlin"
        if _has_marker(path, ("pom.xml", "mvnw")):
            return "java-maven"
    if matches:
        return matches[0]
    return _fallback_stack(path)


def _heuristic_matches(rule: StackRule, source: str) -> bool:
    if rule.heuristic_kind == "literal":
        return (rule.heuristic_value or "") in source
    if rule.heuristic_kind == "regex" and rule.compiled_regex is not None:
        return rule.compiled_regex.search(source) is not None
    return False


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _non_python_test_spans(
    stack: str, source: str, fallback_name: str
) -> list[tuple[int, int, int, str]]:
    patterns: tuple[Pattern[str], ...]
    if stack == "node":
        patterns = (
            re.compile(
                r"(?m)^\s*(?:it|test)\s*(?:\.\w+)*\s*\(\s*"
                r"(?P<quote>['\"])(?P<name>.+?)(?P=quote)"
            ),
        )
    elif stack == "go":
        patterns = (re.compile(r"(?m)^\s*func\s+(?P<name>Test\w*)\s*\("),)
    elif stack == "rust":
        patterns = (re.compile(r"(?m)^\s*(?:pub\s+)?(?:async\s+)?fn\s+(?P<name>test\w*)\s*\("),)
    elif stack in {"java-maven", "java-gradle-kotlin"}:
        patterns = (
            re.compile(
                r"(?m)^\s*(?:public\s+|private\s+|protected\s+)?"
                r"(?:suspend\s+)?(?:fun|void)\s+(?P<name>\w+)\s*\("
            ),
        )
    elif stack == "terraform":
        patterns = (re.compile(r'(?m)^\s*run\s+"(?P<name>[^"]+)"\s*\{'),)
    else:
        patterns = ()

    locations: list[tuple[int, int, str]] = []
    for pattern in patterns:
        for match in pattern.finditer(source):
            locations.append(
                (match.start(), _line_number(source, match.start()), match.group("name"))
            )
    locations.sort()
    if not locations:
        return [(0, len(source), 1, fallback_name)]

    spans: list[tuple[int, int, int, str]] = []
    for index, (start, line, name) in enumerate(locations):
        end = locations[index + 1][0] if index + 1 < len(locations) else len(source)
        spans.append((start, end, line, name))
    return spans


def check_files(
    path_labels: Sequence[str], stacks_file: Path, stack_override: str | None
) -> tuple[list[str], bool]:
    if not path_labels:
        raise CheckFailure("no test files supplied")

    seen: set[str] = set()
    inputs: list[tuple[str, Path, str, str | None]] = []
    for path_label in path_labels:
        if path_label in seen:
            continue
        seen.add(path_label)
        path = Path(path_label)
        if not path.is_file():
            raise CheckFailure("test path is not a file")
        source = _read_source(path)
        waiver = _waiver_reason(source, path.suffix.lower() == ".py")
        inputs.append((path_label, path, source, waiver))

    rules = parse_stack_rules(stacks_file)
    output: list[str] = []
    blocking = False

    for path_label, path, source, waiver in inputs:
        if waiver is not None:
            output.append(WAIVER_TEMPLATE.format(path=path_label, reason=waiver))
            continue

        if path.suffix.lower() == ".py":
            diagnostics, python_blocking = _python_diagnostics(path_label, source)
            output.extend(diagnostics)
            blocking = blocking or python_blocking
            continue

        stack = _infer_stack(path, rules, stack_override)
        rule = rules.get(stack)
        if (
            rule is None
            or rule.explicit_absence
            or rule.heuristic_kind is None
            or rule.heuristic_value is None
        ):
            output.append(NO_HEURISTIC_TEMPLATE.format(stack=stack))
            continue

        for start, end, line, name in _non_python_test_spans(stack, source, path.name):
            if not _heuristic_matches(rule, source[start:end]):
                output.append(Finding(path_label, line, name).render())

    return output, blocking


def build_parser() -> ContractArgumentParser:
    default_stacks_file = (
        Path(__file__).resolve().parents[2] / "system/seeds/validation-snippets/stacks.md"
    )
    parser = ContractArgumentParser(
        description=(
            "Detect assertion-free touched test files. Python findings block; "
            "seeded non-Python heuristic findings are advisory."
        )
    )
    parser.add_argument(
        "--stacks-file",
        type=Path,
        default=default_stacks_file,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--stack",
        dest="stack_override",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("files", nargs="*", help="touched test file paths")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.stack_override is not None and not re.fullmatch(
            r"[a-z0-9][a-z0-9-]*", args.stack_override
        ):
            raise CheckFailure("invalid stack override")
        output, blocking = check_files(
            args.files,
            args.stacks_file,
            args.stack_override,
        )
    except CheckFailure:
        print(FAILURE_MESSAGE, file=sys.stderr)
        return 2
    except Exception:
        # FR-144 requires tool failures to have one stable, fail-closed diagnostic.
        print(FAILURE_MESSAGE, file=sys.stderr)
        return 2

    for line in output:
        print(line)
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
