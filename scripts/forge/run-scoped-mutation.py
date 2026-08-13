#!/usr/bin/env python3
"""Run merge-time, changed-file-scoped mutation checks as advisory evidence."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

OUTPUT_LIMIT = 65_536
JOURNAL_OBSERVATION_LIMIT = 2_000
JOURNAL_TRUNCATION_MARKER = (
    "... [truncated for journal; full observation retained in mutation evidence]"
)
DEFAULT_TIMEOUT_SECONDS = 600
MALFORMED_DIAGNOSTIC = "forge: executable policy row malformed"
POLICY_ABSENT_DIAGNOSTIC = "forge: mutation policy absent at HEAD"
ABSENCE_RE = re.compile(
    r"No mutation tool available for ([^\s]+) — assertion-quality fallback only\."
)
ASCII_INTEGER_RE = re.compile(r"[0-9]+", re.ASCII)
TABLE_SEPARATOR_RE = re.compile(r":?-{3,}:?", re.ASCII)
GENERIC_TEST_COMPONENTS = {"test", "tests", "__tests__", "spec", "specs"}
DEPENDENCY_MANIFEST_BASENAMES = {
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "poetry.lock",
    "uv.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "Gemfile",
    "Gemfile.lock",
    "pom.xml",
    "composer.json",
    "composer.lock",
}
DEPENDENCY_MANIFEST_PATTERNS = ("requirements*.txt", "build.gradle*")
TEST_PATTERN_EXCLUSIONS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    # The Rust seed's `*.rs` pattern expresses that tests are commonly inline;
    # it cannot distinguish production modules, so use test-shaped paths only.
    "rust": ("*.rs",),
}


class PolicyError(RuntimeError):
    """The committed executable policy cannot be parsed safely."""


@dataclass(frozen=True)
class MutationRow:
    category: str
    command: str
    changed_files_form: str
    timeout: int


@dataclass(frozen=True)
class Change:
    status: str
    path: str


@dataclass(frozen=True)
class StackSeed:
    stack: str
    category: str
    test_patterns: tuple[str, ...]


@dataclass(frozen=True)
class RunOutcome:
    result: str
    outcome: str
    exit_code: int | None
    output: str


def json_text(value: object, **options: object) -> str:
    """Serialize JSON without letting surrogateescaped Git paths suppress evidence."""

    options.setdefault("ensure_ascii", False)
    rendered = json.dumps(value, **options)
    return rendered.encode("utf-8", errors="backslashreplace").decode("utf-8")


def region_body(policy: str, name: str) -> str:
    begin = f"<!-- FORGE:REGION {name} BEGIN -->"
    end = f"<!-- FORGE:REGION {name} END -->"
    if policy.splitlines().count(begin) != 1 or policy.splitlines().count(end) != 1:
        raise PolicyError(MALFORMED_DIAGNOSTIC)
    before, remainder = policy.split(begin, 1)
    body, after = remainder.split(end, 1)
    if end in before or begin in body or begin in after or end in after:
        raise PolicyError(MALFORMED_DIAGNOSTIC)
    return body.strip("\n")


def split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        raise PolicyError(MALFORMED_DIAGNOSTIC)
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in stripped[1:-1]:
        if escaped:
            if character == "|":
                current.append("|")
            else:
                current.extend(("\\", character))
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(TABLE_SEPARATOR_RE.fullmatch(cell) for cell in cells)


def is_one_command_line(value: str) -> bool:
    return bool(value) and "\n" not in value and "\r" not in value and "\x00" not in value


def parse_mutation_region(
    policy: str, stack_categories: dict[str, str] | None = None
) -> tuple[list[MutationRow], set[str]]:
    body = region_body(policy, "mutation-testing")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines or any("forge-init:" in line for line in lines):
        raise PolicyError(MALFORMED_DIAGNOSTIC)

    rows: list[MutationRow] = []
    absences: set[str] = set()
    header_seen = False
    separator_expected = False
    table_width = 0
    table_closed = False

    for line in lines:
        absence = ABSENCE_RE.fullmatch(line)
        if absence:
            stack = absence.group(1)
            if separator_expected or stack in absences:
                raise PolicyError(MALFORMED_DIAGNOSTIC)
            if header_seen:
                table_closed = True
            absences.add(stack)
            continue
        if not line.startswith("|"):
            raise PolicyError(MALFORMED_DIAGNOSTIC)

        cells = split_markdown_row(line)
        if cells in (
            ["category", "command", "changed-files form"],
            ["category", "command", "changed-files form", "timeout"],
        ):
            if header_seen or separator_expected:
                raise PolicyError(MALFORMED_DIAGNOSTIC)
            header_seen = True
            separator_expected = True
            table_width = len(cells)
            continue
        if separator_expected:
            if len(cells) != table_width or not is_separator(cells):
                raise PolicyError(MALFORMED_DIAGNOSTIC)
            separator_expected = False
            continue
        allowed_widths = {table_width}
        if table_width == 4:
            allowed_widths.add(3)
        if (
            table_closed
            or not header_seen
            or is_separator(cells)
            or len(cells) not in allowed_widths
        ):
            raise PolicyError(MALFORMED_DIAGNOSTIC)

        category, command, changed_files_form = cells[:3]
        timeout_cell = cells[3] if len(cells) == 4 else ""
        if (
            not category
            or not is_one_command_line(command)
            or not is_one_command_line(changed_files_form)
        ):
            raise PolicyError(MALFORMED_DIAGNOSTIC)
        if timeout_cell:
            if not ASCII_INTEGER_RE.fullmatch(timeout_cell) or int(timeout_cell) <= 0:
                raise PolicyError(MALFORMED_DIAGNOSTIC)
            timeout = int(timeout_cell)
        else:
            timeout = DEFAULT_TIMEOUT_SECONDS
        rows.append(MutationRow(category, command, changed_files_form, timeout))

    if separator_expected or (header_seen and not rows) or not (rows or absences):
        raise PolicyError(MALFORMED_DIAGNOSTIC)
    categories = [row.category for row in rows]
    if len(categories) != len(set(categories)):
        raise PolicyError(MALFORMED_DIAGNOSTIC)
    category_by_stack = stack_categories or {}
    absence_categories = {category_by_stack.get(stack, stack) for stack in absences}
    if set(categories) & absence_categories:
        raise PolicyError(MALFORMED_DIAGNOSTIC)
    return rows, absences


def unwrap_code_span(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped.startswith("`") and stripped.endswith("`"):
        return stripped[1:-1]
    return stripped


def parse_pattern_cell(value: str) -> tuple[str, ...]:
    code_spans = re.findall(r"`([^`]+)`", value)
    candidates = code_spans or [part.strip() for part in value.split(",")]
    return tuple(candidate for candidate in candidates if candidate and candidate != "lockfiles")


def parse_file_categories(policy: str) -> dict[str, tuple[str, ...]]:
    body = region_body(policy, "file-categories")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    table_started = False
    separator_expected = False
    categories: dict[str, tuple[str, ...]] = {}
    for line in lines:
        if "forge-init:" in line:
            raise PolicyError(MALFORMED_DIAGNOSTIC)
        if not line.startswith("|"):
            continue
        cells = split_markdown_row(line)
        lowered = [cell.casefold() for cell in cells]
        if lowered == ["category", "file patterns"]:
            if table_started:
                raise PolicyError(MALFORMED_DIAGNOSTIC)
            table_started = True
            separator_expected = True
            continue
        if separator_expected:
            if len(cells) != 2 or not is_separator(cells):
                raise PolicyError(MALFORMED_DIAGNOSTIC)
            separator_expected = False
            continue
        if table_started:
            if len(cells) != 2 or is_separator(cells):
                raise PolicyError(MALFORMED_DIAGNOSTIC)
            category = unwrap_code_span(cells[0])
            patterns = parse_pattern_cell(cells[1])
            if not category or not patterns or category in categories:
                raise PolicyError(MALFORMED_DIAGNOSTIC)
            categories[category] = patterns
    if not table_started or separator_expected or not categories:
        raise PolicyError(MALFORMED_DIAGNOSTIC)
    return categories


def parse_stack_seeds(seed_text: str) -> list[StackSeed]:
    sections = re.split(r"(?m)^## ", seed_text)[1:]
    seeds: list[StackSeed] = []
    for section in sections:
        heading, _, body = section.partition("\n")
        stack = heading.split(" ", 1)[0]
        category_match = re.search(r"(?m)^Category row: `(.+)`$", body)
        test_match = re.search(r"(?m)^Test file patterns: (.+)$", body)
        if not category_match or not test_match:
            continue
        category_cells = split_markdown_row(category_match.group(1).replace(r"\`", "`"))
        if len(category_cells) != 2:
            continue
        patterns = tuple(re.findall(r"`([^`]+)`", test_match.group(1)))
        seeds.append(StackSeed(stack, unwrap_code_span(category_cells[0]), patterns))
    return seeds


def path_matches(path: str, pattern: str) -> bool:
    normalized = path.removeprefix("./")
    if "/" in pattern:
        return fnmatch.fnmatchcase(normalized, pattern)
    return fnmatch.fnmatchcase(PurePosixPath(normalized).name, pattern)


def generic_test_path(path: str) -> bool:
    candidate = PurePosixPath(path)
    if any(part.casefold() in GENERIC_TEST_COMPONENTS for part in candidate.parts[:-1]):
        return True
    name = candidate.name
    return any(
        fnmatch.fnmatchcase(name, pattern)
        for pattern in (
            "test_*",
            "*_test.*",
            "*.test.*",
            "*.spec.*",
            "*Test.java",
            "*Tests.java",
            "*Test.kt",
            "*Spec.kt",
        )
    )


def is_test_path(path: str, category: str, seeds: list[StackSeed]) -> bool:
    excluded_seed_patterns = TEST_PATTERN_EXCLUSIONS_BY_CATEGORY.get(category, ())
    patterns = [
        pattern
        for seed in seeds
        if seed.category == category
        for pattern in seed.test_patterns
        if pattern not in excluded_seed_patterns
    ]
    return any(path_matches(path, pattern) for pattern in patterns) or generic_test_path(path)


def is_source_addition(change: Change, category: str, seeds: list[StackSeed]) -> bool:
    """Classify an added, category-matched path using committed policy plus fixed exclusions."""
    if change.status != "A" or is_test_path(change.path, category, seeds):
        return False
    name = PurePosixPath(change.path).name
    if name in DEPENDENCY_MANIFEST_BASENAMES or any(
        fnmatch.fnmatchcase(name, pattern) for pattern in DEPENDENCY_MANIFEST_PATTERNS
    ):
        return False
    return True


def parse_name_status(payload: bytes) -> list[Change]:
    tokens = payload.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    changes: list[Change] = []
    index = 0
    try:
        while index < len(tokens):
            status_token = tokens[index].decode("ascii")
            index += 1
            status = status_token[:1]
            if status not in {"A", "C", "D", "M", "R", "T", "U", "X", "B"}:
                raise PolicyError("forge: candidate diff unavailable")
            if status in {"R", "C"}:
                index += 1  # The old path is not an executable candidate path.
            path = tokens[index].decode("utf-8", "surrogateescape")
            index += 1
            changes.append(Change(status, path))
    except (IndexError, UnicodeError):
        raise PolicyError("forge: candidate diff unavailable") from None
    return changes


def diff_changes(repo: Path, base: str, head: str) -> list[Change]:
    process = subprocess.run(
        ["git", "diff", "--name-status", "-z", "--find-renames", f"{base}...{head}"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise PolicyError("forge: candidate diff unavailable")
    return parse_name_status(process.stdout)


def scoped_paths(
    row: MutationRow,
    category_patterns: tuple[str, ...],
    changes: list[Change],
    seeds: list[StackSeed],
) -> tuple[bool, list[str]]:
    triggered = False
    selected: list[str] = []
    for change in changes:
        if not any(path_matches(change.path, pattern) for pattern in category_patterns):
            continue
        if is_test_path(change.path, row.category, seeds) or is_source_addition(
            change, row.category, seeds
        ):
            triggered = True
            if change.status != "D" and change.path not in selected:
                selected.append(change.path)
    return triggered, selected


def kill_process_group(
    anchor: subprocess.Popen[bytes], process: subprocess.Popen[bytes] | None = None
) -> None:
    """Kill an owned group while its unreaped anchor keeps the PGID reserved."""
    try:
        os.killpg(anchor.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process is not None:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    try:
        anchor.wait(timeout=1)
    except subprocess.TimeoutExpired:
        anchor.kill()
        anchor.wait()


def run_command(command: str, paths: list[str], timeout: int, repo: Path) -> RunOutcome:
    started = time.monotonic()
    try:
        # Keep a dedicated group leader alive and unreaped until cleanup. This
        # reserves the PGID even after the command leader has been polled/reaped,
        # so cleanup can never signal a recycled, unrelated process group.
        anchor = subprocess.Popen(
            [sys.executable, "-c", "import signal; signal.pause()"],
            cwd=repo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return RunOutcome("inconclusive", "launch-failed", None, str(error))
    try:
        process = subprocess.Popen(
            ["bash", "-c", command, "forge", *paths],
            cwd=repo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=lambda: os.setpgid(0, anchor.pid),
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        kill_process_group(anchor)
        return RunOutcome("inconclusive", "launch-failed", None, str(error))

    assert process.stdout is not None
    descriptor = process.stdout.fileno()
    os.set_blocking(descriptor, False)
    selector = selectors.DefaultSelector()
    selector.register(descriptor, selectors.EVENT_READ)
    deadline = started + timeout
    output = bytearray()
    reached_eof = False
    disposition: RunOutcome | None = None
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                disposition = RunOutcome(
                    "inconclusive", "timed-out", None, output.decode("utf-8", "replace")
                )
                break
            # Poll periodically even when the command is silent. Some BSD/macOS
            # selector backends do not report a pipe EOF that predates registration.
            events = selector.select(min(remaining, 0.1))
            if events:
                try:
                    chunk = os.read(descriptor, min(8192, OUTPUT_LIMIT + 1 - len(output)))
                except BlockingIOError:
                    chunk = None
                if chunk:
                    output.extend(chunk)
                    if len(output) > OUTPUT_LIMIT:
                        del output[OUTPUT_LIMIT:]
                        disposition = RunOutcome(
                            "inconclusive",
                            "output-limit-exceeded",
                            None,
                            output.decode("utf-8", "replace"),
                        )
                        break
                elif chunk == b"":
                    reached_eof = True
                    try:
                        selector.unregister(descriptor)
                    except KeyError:
                        pass
            return_code = process.poll()
            if return_code is not None:
                # A background descendant can keep the inherited pipe open after
                # the command leader exits. Drain everything already available,
                # then report the leader's disposition; the anchored finally block
                # kills the remaining group without waiting for descendant EOF.
                while not reached_eof:
                    try:
                        trailing = os.read(descriptor, min(8192, OUTPUT_LIMIT + 1 - len(output)))
                    except BlockingIOError:
                        break
                    if trailing == b"":
                        reached_eof = True
                        break
                    output.extend(trailing)
                    if len(output) > OUTPUT_LIMIT:
                        del output[OUTPUT_LIMIT:]
                        disposition = RunOutcome(
                            "inconclusive",
                            "output-limit-exceeded",
                            None,
                            output.decode("utf-8", "replace"),
                        )
                        break
                if disposition is not None:
                    break
                disposition = RunOutcome(
                    "passed" if return_code == 0 else "failed",
                    "completed",
                    return_code,
                    output.decode("utf-8", "replace"),
                )
                break
    finally:
        selector.close()
        process.stdout.close()
        # A successful command can leave descendants behind. The scoped runner
        # owns this group and kills it before reaping the anchor that reserves it.
        kill_process_group(anchor, process)
    assert disposition is not None
    return disposition


def observation_for(
    row: MutationRow,
    paths: list[str],
    outcome: RunOutcome,
) -> str:
    path_json = json_text(paths, separators=(",", ":"))
    exit_part = "none" if outcome.exit_code is None else str(outcome.exit_code)
    output_part = outcome.output.rstrip("\n")
    return (
        f"tool={row.command}; scope={row.category}; outcome={outcome.outcome}; "
        f"exit_code={exit_part}; timeout={row.timeout}s; scoped_files={path_json}; "
        f"output={output_part}"
    )


def verification_record(
    *,
    task: str,
    scope: str,
    result: str,
    check: str,
    observation: str,
    method: str = "command",
) -> dict[str, object]:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "type": "verification",
        "id": f"mutation-{uuid.uuid4().hex}",
        "task": task,
        "criterion": f"mutation: {scope}",
        "method": method,
        "check": check,
        "result": result,
        "observation": observation,
        "recorded_at": timestamp,
    }


def append_record(path: Path, record: dict[str, object]) -> None:
    try:
        journal_record = record.copy()
        observation = journal_record.get("observation")
        if isinstance(observation, str) and len(observation) > JOURNAL_OBSERVATION_LIMIT:
            prefix_length = JOURNAL_OBSERVATION_LIMIT - len(JOURNAL_TRUNCATION_MARKER)
            journal_record["observation"] = observation[:prefix_length] + JOURNAL_TRUNCATION_MARKER
        with path.open("a", encoding="utf-8") as stream:
            stream.write(
                json_text(journal_record, separators=(",", ":")) + "\n"
            )
            stream.flush()
    except (OSError, UnicodeError):
        # Evidence is emitted before every append attempt. Journal persistence is
        # advisory, so a write failure degrades to that evidence-only record.
        return


def emit_evidence(record: dict[str, object], *, diagnostic: str | None = None) -> None:
    evidence = {
        key: record[key] for key in ("criterion", "result", "check", "observation") if key in record
    }
    if diagnostic is not None:
        evidence["diagnostic"] = diagnostic
    print(json_text({"type": "mutation_evidence", **evidence}))


def emit_unavailable(diagnostic: str) -> None:
    print(
        json_text(
            {
                "type": "mutation_evidence",
                "criterion": "mutation: policy",
                "result": "inconclusive",
                "check": "derive fixed candidate mutation scope",
                "observation": (
                    "tool=mutation-testing policy; scope=policy; "
                    f"outcome=unavailable; diagnostic={diagnostic}"
                ),
            },
        )
    )


def seed_category_map(seeds: list[StackSeed]) -> dict[str, str]:
    return {seed.stack: seed.category for seed in seeds}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Fixed full-SHA candidate base.")
    parser.add_argument("--head", required=True, help="Fixed full-SHA candidate head.")
    parser.add_argument("--journal", type=Path, help="Explicit open-run journal.jsonl path.")
    parser.add_argument("--task", help="Task id in the explicitly selected open run.")
    args = parser.parse_args(argv)
    if (args.journal is None) != (args.task is None):
        parser.error("--journal and --task must be supplied together")
    if args.task is not None and (not args.task or "\n" in args.task or "\r" in args.task):
        parser.error("--task must be a nonempty single-line value")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_process = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if repo_process.returncode != 0:
        emit_unavailable("forge: scoped mutation unavailable")
        return 0
    repo = Path(repo_process.stdout.strip())
    policy_process = subprocess.run(
        ["git", "show", "HEAD:forge-project.md"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    plugin_root = Path(__file__).resolve().parents[2]
    try:
        seed_text = (plugin_root / "system/seeds/validation-snippets/stacks.md").read_text(
            encoding="utf-8"
        )
        if policy_process.returncode != 0:
            raise PolicyError(POLICY_ABSENT_DIAGNOSTIC)
        seeds = parse_stack_seeds(seed_text)
        stack_categories = seed_category_map(seeds)
        rows, absences = parse_mutation_region(policy_process.stdout, stack_categories)
        categories = parse_file_categories(policy_process.stdout)
        changes = diff_changes(repo, args.base, args.head)
        if any(row.category not in categories for row in rows):
            raise PolicyError(MALFORMED_DIAGNOSTIC)
    except (OSError, UnicodeError, PolicyError) as error:
        diagnostic = str(error)
        if diagnostic == MALFORMED_DIAGNOSTIC:
            print(MALFORMED_DIAGNOSTIC)
            observation = (
                "tool=mutation-testing policy; scope=policy; outcome=malformed-skip; "
                "scoped_files=[]; timeout=not-applicable; "
                f"diagnostic={MALFORMED_DIAGNOSTIC}"
            )
            record = verification_record(
                task=args.task or "",
                scope="policy",
                result="skipped",
                check="git show HEAD:forge-project.md (mutation-testing)",
                observation=observation,
                method="inspection",
            )
            emit_evidence(record, diagnostic=MALFORMED_DIAGNOSTIC)
            if args.journal:
                append_record(args.journal, record)
        else:
            emit_unavailable(diagnostic)
        return 0

    evidence_emitted = False
    for row in rows:
        triggered, paths = scoped_paths(row, categories[row.category], changes, seeds)
        if not triggered:
            continue
        if paths:
            outcome = run_command(row.changed_files_form, paths, row.timeout, repo)
            result = outcome.result
            observation = observation_for(row, paths, outcome)
        else:
            result = "skipped"
            observation = (
                f"tool={row.command}; scope={row.category}; outcome=no-live-scope; "
                f"scoped_files=[]; timeout={row.timeout}s"
            )
        record = verification_record(
            task=args.task or "",
            scope=row.category,
            result=result,
            check=row.changed_files_form,
            observation=observation,
        )
        emit_evidence(record)
        if args.journal:
            append_record(args.journal, record)
        evidence_emitted = True

    for stack in sorted(absences):
        category = stack_categories.get(stack, stack)
        absence_text = f"No mutation tool available for {stack} — assertion-quality fallback only."
        patterns = categories.get(category)
        if patterns is None:
            record = verification_record(
                task=args.task or "",
                scope=category,
                result="skipped",
                check=absence_text,
                observation=(
                    f"tool=none; scope={category}; outcome=declared-absence; "
                    "scoped_files=[]; timeout=not-applicable"
                ),
                method="inspection",
            )
            emit_evidence(record)
            if args.journal:
                append_record(args.journal, record)
            evidence_emitted = True
            continue
        synthetic = MutationRow(category, f"No mutation tool available for {stack}", ":", 600)
        triggered, paths = scoped_paths(synthetic, patterns, changes, seeds)
        if triggered:
            record = verification_record(
                task=args.task or "",
                scope=category,
                result="skipped",
                check=absence_text,
                observation=(
                    f"tool=none; scope={category}; outcome=declared-absence; "
                    f"scoped_files={json_text(paths, separators=(',', ':'))}; "
                    "timeout=not-applicable"
                ),
                method="inspection",
            )
            emit_evidence(record)
            if args.journal:
                append_record(args.journal, record)
            evidence_emitted = True

    if not evidence_emitted:
        evaluated_categories = list(dict.fromkeys(row.category for row in rows))
        for stack in sorted(absences):
            category = stack_categories.get(stack, stack)
            if category not in evaluated_categories:
                evaluated_categories.append(category)
        record = verification_record(
            task=args.task or "",
            scope="policy",
            result="skipped",
            check="derive fixed candidate mutation scope",
            observation=(
                "tool=mutation-testing policy; scope=policy; outcome=not-applicable; "
                "categories_evaluated="
                + json_text(evaluated_categories, separators=(",", ":"))
            ),
            method="inspection",
        )
        emit_evidence(record)
        if args.journal:
            append_record(args.journal, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
