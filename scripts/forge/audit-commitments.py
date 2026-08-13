#!/usr/bin/env python3
"""Audit a closed orchestration journal and render its open commitments.

The archive writer consumes this program's stdout verbatim.  A failed audit
therefore writes nothing to stdout and prevents the archive from being made.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from commitment_paths import path_tokens  # noqa: E402

from scripts.codex_orchestrator.journal import (  # noqa: E402
    TERMINAL_TASK_STATUSES,
    read_journal,
    record_line,
)

DIAGNOSTIC_PREFIX = "forge: commitment audit failed — "
CORRECTION_TOKEN = "citation-correction:"
DECISION_CORRECTION = re.compile(
    r"^(?P<id>\S+) basis\[(?P<index>[0-9]+)\]: (?P<path>.+)$"
)
VERIFICATION_CORRECTION = re.compile(
    r"^(?P<id>\S+) observation: (?P<token>.+?) -> (?P<path>.+)$"
)


@dataclass(frozen=True)
class Failure(Exception):
    exit_code: int
    diagnostic: str


@dataclass(frozen=True)
class Citation:
    value: str
    source: str
    target: tuple[str, str, int | str]


@dataclass(frozen=True)
class Correction:
    target: tuple[str, str, int | str]
    corrected_path: str
    supplier: str


@dataclass(frozen=True)
class AuditedCitation:
    original: Citation
    value: str
    correction: Correction | None = None

    def missing_finding(self) -> str:
        if self.correction is None:
            return f"{self.value} ({self.original.source})"
        return (
            f"{self.value} (corrected from {self.original.value} for "
            f"{self.original.source} by decision {self.correction.supplier})"
        )

    def correction_finding(self) -> str | None:
        if self.correction is None:
            return None
        return (
            f"decision {self.correction.supplier} applied to {self.original.source}: "
            f"{self.original.value} -> {self.value}"
        )


def fail(exit_code: int, diagnostic: str) -> None:
    raise Failure(exit_code, diagnostic)


def parse_argv(argv: list[str]) -> Path:
    if len(argv) != 2 or argv[0] != "--run-dir" or not argv[1]:
        fail(2, "usage: audit-commitments.py --run-dir <run-dir>")
    try:
        return Path(argv[1]).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        fail(2, f"invalid run directory: {exc}")


def record_name(record: dict[str, object]) -> str:
    kind = record.get("type")
    identifier = record.get("id")
    if isinstance(identifier, str) and identifier:
        return f"{kind} {identifier}"
    return record_line(record)


def closed_records(
    run_dir: Path,
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    records, issues = read_journal(run_dir / "journal.jsonl")
    if issues:
        fail(2, f"journal invalid: {issues[0]}")
    starts = [record for record in records if record.get("type") == "run_started"]
    closures = [record for record in records if record.get("type") == "run_closed"]
    if len(starts) != 1:
        fail(2, f"journal must contain exactly one run_started entry; found {len(starts)}")
    if len(closures) != 1:
        fail(2, f"journal must contain exactly one run_closed entry; found {len(closures)}")
    if not records or records[-1] is not closures[0]:
        fail(2, "run_closed must be the final journal entry")
    return records, starts[0], closures[0]


def known_tasks(records: Iterable[dict[str, object]]) -> set[str]:
    return {
        task_id
        for record in records
        if record.get("type") == "task"
        and isinstance((task_id := record.get("id")), str)
        and task_id
    }


def resolution_task_pattern(known: set[str]) -> re.Pattern[str] | None:
    """Match exact journal task IDs plus task-shaped unresolved references."""

    alternatives = "|".join(re.escape(value) for value in sorted(known, key=len, reverse=True))
    known_branch = f"{alternatives}|" if alternatives else ""
    return re.compile(
        rf"(?<![A-Za-z0-9_.-])({known_branch}(?:[A-Za-z0-9]+[._-])*task[._-]"
        rf"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)(?=$|[^A-Za-z0-9_.-]|\.(?![A-Za-z0-9]))",
        re.IGNORECASE,
    )


def without_recorded_branch_names(prose: str, branches: Iterable[str]) -> str:
    """Mask exact branch tokens without hiding longer task-shaped references."""

    for branch in sorted(branches, key=len, reverse=True):
        branch_token = re.compile(
            rf"(?<![A-Za-z0-9_./-]){re.escape(branch)}"
            rf"(?=$|[^A-Za-z0-9_./-]|\.(?![A-Za-z0-9]))"
        )
        prose = branch_token.sub("", prose)
    return prose


def audit_unknown_task_references(records: list[dict[str, object]]) -> list[str]:
    known = known_tasks(records)
    known_folded = {task.casefold() for task in known}
    branch_names = recorded_branches(records)
    findings: list[str] = []
    task_pattern = resolution_task_pattern(known)
    for record in records:
        if "task" in record:
            task = record.get("task")
            if isinstance(task, str) and task and task not in known:
                findings.append(f"{task} ({record_name(record)} task field)")
        if record.get("type") != "decision":
            continue
        resolution = record.get("resolution")
        if not isinstance(resolution, str):
            continue
        if resolution.startswith(CORRECTION_TOKEN):
            continue
        prose = without_recorded_branch_names(resolution, branch_names)
        for task in task_pattern.findall(prose):
            if task.casefold() not in known_folded:
                findings.append(f"{task} ({record_name(record)} resolution)")
    return findings


def audit_non_terminal_tasks(records: list[dict[str, object]]) -> list[str]:
    latest: dict[str, dict[str, object]] = {}
    for record in records:
        if record.get("type") != "task":
            continue
        task = record.get("id")
        if isinstance(task, str) and task:
            latest[task] = record
    return [
        f"{task} (latest status: {record.get('status')})"
        for task, record in latest.items()
        if record.get("status") not in TERMINAL_TASK_STATUSES
    ]


def citations(records: Iterable[dict[str, object]]) -> list[Citation]:
    result: list[Citation] = []
    for record in records:
        if record.get("type") == "decision":
            basis = record.get("basis", [])
            if not isinstance(basis, list):
                fail(2, f"{record_name(record)} basis must be an array")
            for index, value in enumerate(basis):
                if not isinstance(value, str):
                    fail(2, f"{record_name(record)} basis[{index}] must be a string")
                for token in path_tokens(value, context="basis"):
                    result.append(
                        Citation(
                            token,
                            f"{record_name(record)} basis[{index}]",
                            ("decision", str(record.get("id")), index),
                        )
                    )
        elif record.get("type") == "verification":
            observation = record.get("observation")
            if isinstance(observation, str):
                for token in path_tokens(observation, context="observation"):
                    result.append(
                        Citation(
                            token,
                            f"{record_name(record)} observation",
                            ("verification", str(record.get("id")), token),
                        )
                    )
    return result


def citation_corrections(
    records: list[dict[str, object]], source_citations: list[Citation]
) -> dict[tuple[str, str, int | str], Correction]:
    available = {citation.target for citation in source_citations}
    result: dict[tuple[str, str, int | str], Correction] = {}
    for record in records:
        if record.get("type") != "decision":
            continue
        resolution = record.get("resolution")
        if not isinstance(resolution, str) or not resolution.startswith(CORRECTION_TOKEN):
            continue
        supplier = record.get("id")
        if not isinstance(supplier, str) or not supplier:
            fail(2, f"{record_name(record)} correction supplier must have an id")
        suffix = resolution[len(CORRECTION_TOKEN) :]
        lines = suffix.splitlines()
        if lines and not lines[0].strip():
            lines = lines[1:]
        for line in lines:
            decision_match = DECISION_CORRECTION.fullmatch(line)
            verification_match = VERIFICATION_CORRECTION.fullmatch(line)
            if decision_match is not None:
                target: tuple[str, str, int | str] = (
                    "decision",
                    decision_match.group("id"),
                    int(decision_match.group("index")),
                )
                corrected_path = decision_match.group("path")
            elif verification_match is not None:
                target = (
                    "verification",
                    verification_match.group("id"),
                    verification_match.group("token"),
                )
                corrected_path = verification_match.group("path")
            else:
                break
            if target not in available:
                if target[0] == "decision":
                    named_target = f"decision {target[1]} basis[{target[2]}]"
                else:
                    named_target = (
                        f"verification {target[1]} observation token {target[2]}"
                    )
                fail(
                    6,
                    f"citation correction target does not exist: {named_target} "
                    f"(supplied by decision {supplier})",
                )
            result[target] = Correction(target, corrected_path, supplier)
    return result


def apply_corrections(
    source_citations: list[Citation],
    corrections: dict[tuple[str, str, int | str], Correction],
) -> list[AuditedCitation]:
    return [
        AuditedCitation(
            citation,
            corrections[citation.target].corrected_path,
            corrections[citation.target],
        )
        if citation.target in corrections
        else AuditedCitation(citation, citation.value)
        for citation in source_citations
    ]


def confined_existing(root: Path, relative: str) -> bool:
    try:
        value = Path(relative)
        if value.is_absolute():
            return False
        root = root.resolve()
        target = (root / value).resolve()
        target.relative_to(root)
        return target.exists()
    except (OSError, RuntimeError, ValueError):
        return False


def confined_relative_path(relative: str) -> bool:
    try:
        value = Path(relative)
        if value.is_absolute():
            return False
        normalized = (Path("/") / value).resolve()
        normalized.relative_to(Path("/"))
        return ".." not in value.parts
    except (OSError, RuntimeError, ValueError):
        return False


def recorded_branches(records: Iterable[dict[str, object]]) -> list[str]:
    branches: list[str] = []
    for record in records:
        if record.get("type") != "execution":
            continue
        branch = record.get("branch")
        if isinstance(branch, str) and branch and branch not in branches:
            branches.append(branch)
    return branches


def branch_contains(repo_root: Path, branch: str, relative: str) -> bool:
    if not confined_relative_path(relative):
        return False
    try:
        valid_branch = subprocess.run(
            ["git", "-C", str(repo_root), "check-ref-format", "--branch", branch],
            check=False,
            capture_output=True,
        )
        if (
            valid_branch.returncode != 0
            or valid_branch.stdout != f"{branch}\n".encode()
        ):
            return False
        result = subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "-e", "--", f"{branch}:{relative}"],
            check=False,
            capture_output=True,
        )
    except OSError:
        return False
    return result.returncode == 0


def recorded_branch_contains(
    repo_root: Path, branches: Iterable[str], relative: str
) -> bool:
    # CONTROL branch-aware BEGIN
    return any(branch_contains(repo_root, branch, relative) for branch in branches)
    # CONTROL branch-aware END


def audit_missing_paths(
    audited_citations: list[AuditedCitation],
    records: list[dict[str, object]],
    run_dir: Path,
    start: dict[str, object],
) -> list[str]:
    roots = [run_dir]
    repo = start.get("repo")
    if not isinstance(repo, str) or not repo or not Path(repo).is_absolute():
        fail(2, "run_started repo must name an existing absolute directory")
    try:
        repo_root = Path(repo).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        fail(2, "run_started repo must name an existing absolute directory")
    if not repo_root.is_dir():
        fail(2, "run_started repo must name an existing absolute directory")
    if repo_root not in roots:
        roots.append(repo_root)
    branches = recorded_branches(records)
    return [
        citation.missing_finding()
        for citation in audited_citations
        if not any(confined_existing(root, citation.value) for root in roots)
        and not recorded_branch_contains(repo_root, branches, citation.value)
    ]


def commitment_items(close: dict[str, object], field: str) -> list[str]:
    if field not in close:
        return []
    values = close.get(field)
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value for value in values
    ):
        fail(2, f"run_closed {field} must be an array of non-empty strings")
    return values


def render_section(title: str, values: list[str]) -> str:
    body = "\n".join(f"- {value}" for value in values) if values else "None recorded"
    return f"## {title}\n\n{body}\n"


def audit(run_dir: Path) -> str:
    records, start, close = closed_records(run_dir)
    source_citations = citations(records)
    audited_citations = [
        AuditedCitation(citation, citation.value) for citation in source_citations
    ]

    # CONTROL citation-correction BEGIN
    corrections = citation_corrections(records, source_citations)
    audited_citations = apply_corrections(source_citations, corrections)
    # CONTROL citation-correction END

    # CONTROL unknown-task BEGIN
    unknown = audit_unknown_task_references(records)
    if unknown:
        fail(3, f"unknown task reference: {unknown[0]}")
    # CONTROL unknown-task END

    # CONTROL terminal-task BEGIN
    non_terminal = audit_non_terminal_tasks(records)
    if non_terminal:
        fail(4, f"task is non-terminal at close: {non_terminal[0]}")
    # CONTROL terminal-task END

    # CONTROL cited-path BEGIN
    missing = audit_missing_paths(audited_citations, records, run_dir, start)
    if missing:
        fail(5, f"cited path does not exist within run or repository: {missing[0]}")
    # CONTROL cited-path END

    risks = commitment_items(close, "risks")
    follow_ups = commitment_items(close, "follow_ups")
    correction_findings = [
        finding
        for citation in audited_citations
        if (finding := citation.correction_finding()) is not None
    ]
    correction_section = (
        render_section("Citation Corrections", correction_findings) + "\n"
        if correction_findings
        else ""
    )
    return (
        correction_section
        + render_section("Residual Risks", risks)
        + "\n"
        + render_section("Follow-ups", follow_ups)
    )


def main(argv: list[str] | None = None) -> int:
    try:
        output = audit(parse_argv(sys.argv[1:] if argv is None else argv))
    except Failure as exc:
        sys.stderr.write(f"{DIAGNOSTIC_PREFIX}{exc.diagnostic}\n")
        return exc.exit_code
    except (OSError, RuntimeError, ValueError) as exc:
        sys.stderr.write(f"{DIAGNOSTIC_PREFIX}audit could not execute: {exc}\n")
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
