#!/usr/bin/env python3
"""Audit a closed orchestration journal and render its open commitments.

The archive writer consumes this program's stdout verbatim.  A failed audit
therefore writes nothing to stdout and prevents the archive from being made.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from commitment_paths import (  # noqa: E402
    AUDIT_ACTIVATED_REQUIRED,
    AUDIT_CAPTURE_SURROGATE,
    AUDIT_OPTIONAL_DERIVED,
    AUDIT_RECORD_CITATION,
    AUDIT_STRUCTURED_LANDING,
    CAPTURED_PACKAGE_NAMES,
    CommitmentPathSurface,
    CommitmentPathResolution,
    RecordPathCitation,
    commitment_surfaces,
    iter_record_citations,
    parse_run_captured_path,
    resolution_matches_surface,
    resolve_surface_path,
    validate_surface_path,
)

from scripts.codex_orchestrator.journal import (  # noqa: E402
    TERMINAL_TASK_STATUSES,
    WRITER_CONTRACT,
    _legacy_compatibility_declaration,
    read_journal,
    record_line,
)

DIAGNOSTIC_PREFIX = "forge: commitment audit failed — "
CORRECTION_TOKEN = "citation-correction:"
FORGE_SOURCE_MARKERS = (
    "tests/test_repo_conformance.py",
    ".claude-plugin/plugin.json",
    "docs/specs/forge-plugin-spec.md",
)
HISTORICAL_ROUTING_HEADING = "## Historical Routing Findings\n\n"
DECISION_CORRECTION = re.compile(
    r"^(?P<id>\S+) basis\[(?P<index>[0-9]+)\]: (?P<path>.+)$"
)
VERIFICATION_CORRECTION = re.compile(
    r"^(?P<id>\S+) observation: (?P<token>.+?) -> (?P<path>.+)$"
)

# FR-018(b): operator-directed dispensation of exactly-named missing citations in a
# closed journal. The two target shapes mirror FR-191's correction grammar; the leg
# below is the in-memory disable control — with it removed, dispensation flags parse
# but grant nothing, so every missing citation keeps the fail(5) refusal.
DISPENSATION_LEGS = frozenset({"dispense-citation"})
DISPENSE_BASIS_TARGET = re.compile(r"^(?P<id>\S+) basis\[(?P<index>[0-9]+)\]$")
DISPENSE_OBSERVATION_TARGET = re.compile(r"^(?P<id>\S+) observation: (?P<token>.+)$")


@dataclass(frozen=True)
class Failure(Exception):
    exit_code: int
    diagnostic: str


@dataclass(frozen=True)
class Citation:
    value: str
    source: str
    target: tuple[str, str, int | str] | None
    surface: CommitmentPathSurface
    line: int = 0


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


def parse_argv(argv: list[str]) -> tuple[Path, tuple[str, ...], str | None]:
    run_dir_value: str | None = None
    dispense_targets: list[str] = []
    dispense_reason: str | None = None
    index = 0
    while index < len(argv):
        flag = argv[index]
        if index + 1 >= len(argv):
            fail(2, f"missing value for {flag}")
        value = argv[index + 1]
        if flag == "--run-dir":
            if run_dir_value is not None:
                fail(2, "duplicate --run-dir")
            run_dir_value = value
        elif flag == "--dispense-citation":
            dispense_targets.append(value)
        elif flag == "--dispense-reason":
            if dispense_reason is not None:
                fail(2, "duplicate --dispense-reason")
            dispense_reason = value
        else:
            fail(
                2,
                "usage: audit-commitments.py --run-dir <run-dir> "
                "[--dispense-citation <target>]... [--dispense-reason <text>]",
            )
        index += 2
    if not run_dir_value:
        fail(
            2,
            "usage: audit-commitments.py --run-dir <run-dir> "
            "[--dispense-citation <target>]... [--dispense-reason <text>]",
        )
    if dispense_targets and dispense_reason is None:
        fail(2, "--dispense-citation requires --dispense-reason")
    if dispense_reason is not None:
        if not dispense_targets:
            fail(2, "--dispense-reason requires at least one --dispense-citation")
        if (
            not dispense_reason.strip()
            or "\r" in dispense_reason
            or "\n" in dispense_reason
        ):
            fail(2, "dispensation reason must be a nonempty single line")
    try:
        run_dir = Path(run_dir_value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        fail(2, f"invalid run directory: {exc}")
    return run_dir, tuple(dispense_targets), dispense_reason


def parse_dispensation_targets(
    raw_targets: Iterable[str],
    records: Iterable[dict[str, object]],
) -> list[tuple[str, str, int | str]]:
    """Parse FR-018(b) targets into audit citation keys, failing closed on ambiguity."""

    decisions: dict[str, int] = {}
    verifications: dict[str, int] = {}
    for record in records:
        identifier = record.get("id")
        if not isinstance(identifier, str):
            continue
        if record.get("type") == "decision":
            decisions[identifier] = decisions.get(identifier, 0) + 1
        elif record.get("type") == "verification":
            verifications[identifier] = verifications.get(identifier, 0) + 1

    targets: list[tuple[str, str, int | str]] = []
    for raw in raw_targets:
        basis_match = DISPENSE_BASIS_TARGET.match(raw)
        observation_match = (
            DISPENSE_OBSERVATION_TARGET.match(raw) if basis_match is None else None
        )
        if basis_match is not None:
            identifier = basis_match.group("id")
            if decisions.get(identifier, 0) > 1:
                fail(2, f"ambiguous dispensation target (duplicate id): {raw}")
            targets.append(("decision", identifier, int(basis_match.group("index"))))
        elif observation_match is not None:
            identifier = observation_match.group("id")
            if verifications.get(identifier, 0) > 1:
                fail(2, f"ambiguous dispensation target (duplicate id): {raw}")
            targets.append(
                ("verification", identifier, observation_match.group("token"))
            )
        else:
            fail(2, f"malformed dispensation target: {raw}")
    return targets


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
        rf"[0-9][A-Za-z0-9]*(?:[._-][A-Za-z0-9]+)*)(?=$|[^A-Za-z0-9_.-]|\.(?![A-Za-z0-9]))",
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


def _citation_target(
    record: dict[str, object], citation: RecordPathCitation
) -> tuple[str, str, int | str] | None:
    """Keep correction/dispensation authority narrower than audit coverage."""

    if not citation.surface.correctable:
        return None
    identifier = str(record.get("id"))
    if citation.surface.label == "decision.basis" and citation.index is not None:
        return "decision", identifier, citation.index
    if (
        citation.surface.label == "verification.observation"
        and citation.token is not None
    ):
        return "verification", identifier, citation.token
    return None


def _citation_source(
    record: dict[str, object], citation: RecordPathCitation
) -> str:
    if citation.surface.label == "decision.basis":
        return f"{record_name(record)} basis[{citation.index}]"
    if citation.surface.label == "verification.observation":
        return f"{record_name(record)} observation"
    if citation.surface.label == "verification.evidence":
        return f"{record_name(record)} evidence[{citation.index}]"
    execution = record.get("execution")
    if isinstance(execution, str) and execution:
        return f"{record.get('type')} {execution} {citation.surface.field}"
    return f"{record_name(record)} {citation.surface.field}"


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
        elif record.get("type") == "verification" and "evidence" in record:
            evidence = record.get("evidence")
            if not isinstance(evidence, list):
                fail(2, f"{record_name(record)} evidence must be an array")
            for index, value in enumerate(evidence):
                if not isinstance(value, str):
                    fail(2, f"{record_name(record)} evidence[{index}] must be a string")

        for expanded in iter_record_citations(record, enforcement="audit"):
            result.append(
                Citation(
                    expanded.value,
                    _citation_source(record, expanded),
                    _citation_target(record, expanded),
                    expanded.surface,
                    int(record.get("_line", 0)),
                )
            )
    return result


def citation_corrections(
    records: list[dict[str, object]], source_citations: list[Citation]
) -> dict[tuple[str, str, int | str], Correction]:
    available = {
        citation.target
        for citation in source_citations
        if citation.target is not None
    }
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
        if citation.target is not None and citation.target in corrections
        else AuditedCitation(citation, citation.value)
        for citation in source_citations
    ]


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


def recorded_repository(start: dict[str, object]) -> Path:
    """Return the one existing absolute repository recorded by run_started."""

    repo = start.get("repo")
    if not isinstance(repo, str) or not repo or not Path(repo).is_absolute():
        fail(2, "run_started repo must name an existing absolute directory")
    try:
        repo_root = Path(repo).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        fail(2, "run_started repo must name an existing absolute directory")
    if not repo_root.is_dir():
        fail(2, "run_started repo must name an existing absolute directory")
    return repo_root


def audit_missing_paths(
    audited_citations: list[AuditedCitation],
    records: list[dict[str, object]],
    run_dir: Path,
    repo_root: Path,
) -> list[AuditedCitation]:
    branches = recorded_branches(records)
    missing: list[AuditedCitation] = []
    for citation in audited_citations:
        selected = resolve_surface_path(
            citation.original.surface,
            citation.value,
            repository=repo_root,
            run_dir=run_dir,
        )
        if resolution_matches_surface(citation.original.surface, selected):
            continue
        # A recorded branch can supply a path absent from both working roots,
        # but cannot override an anchored symlink escape or a present non-file.
        if (
            selected is not None
            and selected.contained
            and not selected.anchored
            and recorded_branch_contains(repo_root, branches, citation.value)
        ):
            continue
        missing.append(citation)
    return missing


def _path_observation(value: os.stat_result) -> tuple[int, ...]:
    """Return the identity and mutation fields needed around a no-follow read."""

    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _surface_digest(
    surface: CommitmentPathSurface,
    selected: CommitmentPathResolution | None,
) -> str | None:
    """Hash one stable surface file without following its final component."""

    if not resolution_matches_surface(surface, selected) or selected is None:
        return None
    descriptor = -1
    try:
        before = os.lstat(selected.candidate)
        descriptor = os.open(
            selected.candidate,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        opened = os.fstat(descriptor)
        if _path_observation(opened) != _path_observation(before):
            return None
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        rebound = os.lstat(selected.candidate)
        if (
            _path_observation(after) != _path_observation(before)
            or _path_observation(rebound) != _path_observation(before)
        ):
            return None
        return digest.hexdigest()
    except (OSError, RuntimeError, ValueError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _surface_finding(value: str, source: str) -> None:
    """Keep the established audit path diagnostic for every table projection."""

    fail(
        5,
        "cited path does not exist within run or repository: "
        f"{value} ({source})",
    )


def _derived_parent(
    surface: CommitmentPathSurface,
    *,
    repository: Path,
    run_dir: Path,
) -> Path | None:
    if surface.direct_child_parent == "run":
        return run_dir
    if surface.direct_child_parent == "archive-history":
        return repository / ".forge" / "history" / "runs"
    return None


def _audit_derived_node(
    surface: CommitmentPathSurface,
    *,
    value: str,
    repository: Path,
    run_dir: Path,
    required: bool,
) -> None:
    """Require or conditionally validate one table-derived direct child."""

    root = run_dir if surface.roots == ("run",) else repository
    candidate = root / value
    try:
        os.lstat(candidate)
    except FileNotFoundError:
        if required:
            _surface_finding(value, surface.label)
        return
    except OSError:
        _surface_finding(value, surface.label)
    selected = validate_surface_path(
        surface,
        value,
        repository=repository,
        run_dir=run_dir,
        direct_parent=_derived_parent(
            surface,
            repository=repository,
            run_dir=run_dir,
        ),
        require_file=True,
    )
    if _surface_digest(surface, selected) is None:
        _surface_finding(value, surface.label)


def _audit_structured_landings(
    surface: CommitmentPathSurface,
    records: list[dict[str, object]],
    *,
    run_id: str,
    repository: Path,
    run_dir: Path,
) -> None:
    """Validate the durable capture triplet carried by each ingest landing."""

    for record in records:
        if (
            record.get("type") != "decision"
            or record.get("outcome") != "chain-landing"
            or not isinstance(record.get("binding"), dict)
        ):
            continue
        basis = record.get("basis")
        if not isinstance(basis, list) or not basis:
            # Native event-drained landings carry an empty basis; retrospective
            # ingest landings are distinguished by their nonempty capture triplet.
            continue
        parsed = [
            parse_run_captured_path(value, run_id=run_id)
            if isinstance(value, str)
            else None
            for value in basis
        ]
        if (
            len(parsed) != len(CAPTURED_PACKAGE_NAMES)
            or any(value is None for value in parsed)
            or tuple(value.name for value in parsed if value is not None)
            != CAPTURED_PACKAGE_NAMES
        ):
            value = next(
                (member for member in basis if isinstance(member, str)),
                "<structured landing basis>",
            )
            _surface_finding(value, f"{record_name(record)} ingest.captured_package")
        for index, captured in enumerate(parsed):
            assert captured is not None
            candidate = run_dir / captured.relative
            selected = validate_surface_path(
                surface,
                captured.relative,
                repository=repository,
                run_dir=run_dir,
                direct_parent=candidate.parent,
                require_file=True,
            )
            if _surface_digest(surface, selected) != captured.digest:
                _surface_finding(
                    captured.relative,
                    f"{record_name(record)} basis[{index}]",
                )


def audit_projected_surfaces(
    records: list[dict[str, object]],
    start: dict[str, object],
    *,
    repository: Path,
    run_dir: Path,
) -> None:
    """Apply every non-record audit policy projected from the shared table."""

    run_id = start.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        fail(2, "run_started run_id must be a nonempty string")
    activated = start.get("writer_contract") == WRITER_CONTRACT
    for surface in commitment_surfaces(enforcement="audit"):
        policy = surface.audit_policy
        if policy == AUDIT_RECORD_CITATION:
            if surface.owner != "record":
                fail(2, f"invalid commitment audit policy: {surface.label}")
            continue
        if policy == AUDIT_CAPTURE_SURROGATE:
            # Caller source spellings are intentionally absent from durable
            # records; the structured capture package below is their surrogate.
            continue
        if policy == AUDIT_STRUCTURED_LANDING:
            _audit_structured_landings(
                surface,
                records,
                run_id=run_id,
                repository=repository,
                run_dir=run_dir,
            )
            continue
        if policy in {AUDIT_OPTIONAL_DERIVED, AUDIT_ACTIVATED_REQUIRED}:
            if surface.derived_path is None:
                fail(2, f"invalid commitment audit policy: {surface.label}")
            value = surface.derived_path.format(run_id=run_id)
            _audit_derived_node(
                surface,
                value=value,
                repository=repository,
                run_dir=run_dir,
                required=policy == AUDIT_ACTIVATED_REQUIRED and activated,
            )
            continue
        fail(2, f"invalid commitment audit policy: {surface.label}")


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


def forge_source_root(start: dict[str, object]) -> Path | None:
    """Return the recorded repository root only when all source markers are tracked."""

    repo_value = start.get("repo")
    if not isinstance(repo_value, str):
        return None
    try:
        repo = Path(repo_value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    try:
        root_result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        fail(2, f"repository conformance could not identify the repository: {exc}")
    if root_result.returncode != 0:
        return None
    try:
        root = Path(root_result.stdout.decode("utf-8").strip()).resolve(strict=True)
    except (OSError, UnicodeError, RuntimeError, ValueError):
        fail(2, "repository conformance returned an invalid repository root")
    if repo != root:
        return None
    try:
        marker_result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--error-unmatch",
                *FORGE_SOURCE_MARKERS,
            ],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        fail(2, f"repository conformance could not inspect source markers: {exc}")
    return root if marker_result.returncode == 0 else None


def audit_repo_conformance(
    start: dict[str, object], run_dir: Path
) -> str:
    """Run forge-plugin dogfood conformance and return its archival Markdown."""

    source_root = forge_source_root(start)
    if source_root is None:
        return ""
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(source_root / "tests/test_repo_conformance.py"),
                "--run-dir",
                str(run_dir),
            ],
            cwd=source_root,
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        fail(2, f"repository conformance could not execute: {exc}")

    stdout = result.stdout.decode("utf-8", errors="backslashreplace")
    stderr = result.stderr.decode("utf-8", errors="backslashreplace")
    if result.returncode != 0:
        details = []
        if stderr.strip():
            details.append(f"stderr: {stderr.strip()}")
        if stdout.strip():
            details.append(f"stdout: {stdout.strip()}")
        suffix = f": {'; '.join(details)}" if details else ""
        fail(result.returncode, f"repository conformance failed{suffix}")
    if stderr:
        fail(2, f"repository conformance emitted stderr: {stderr.strip()}")
    if not stdout.startswith(HISTORICAL_ROUTING_HEADING) or not stdout.endswith("\n"):
        fail(2, "repository conformance output is invalid")
    return stdout


def audit(
    run_dir: Path,
    dispense_targets: tuple[str, ...] = (),
    dispense_reason: str | None = None,
) -> str:
    records, start, close = closed_records(run_dir)
    repo_root = recorded_repository(start)
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

    missing = audit_missing_paths(
        audited_citations,
        records,
        run_dir,
        repo_root,
    )
    # A journal-dialect-compat declaration (the legacy posture whose grammar
    # is owned by scripts/codex_orchestrator/journal.py's
    # _legacy_compatibility_declaration) covers citations
    # recorded before it: the run is closed, so the sanctioned
    # citation-correction append can no longer repair them. They degrade to a
    # visible Legacy Citations section instead of refusing the archive. A
    # corrected citation is a modern repair and is never tolerated here;
    # records at or after the declaration and undeclared journals keep the
    # exact refusal. Only the refusal lives inside the control block, so the
    # disable sensor removes the gate without breaking the rendering.
    declaration = _legacy_compatibility_declaration(records)
    declaration_line = int(declaration["_line"]) if declaration is not None else None
    legacy_citations = [
        citation
        for citation in missing
        if citation.correction is None
        and citation.original.surface.legacy_missing
        and declaration_line is not None
        and 0 < citation.original.line < declaration_line
    ]
    hard_missing = [
        citation for citation in missing if citation not in legacy_citations
    ]

    # FR-018(b): operator-directed dispensation degrades exactly the named missing
    # citations to the visible section below. Targets are exact — one that names a
    # resolvable citation, an already-tolerated legacy citation, or nothing in the
    # journal fails closed instead of being ignored. With the dispensation leg
    # disabled in memory, parsed targets grant nothing and every missing citation
    # keeps the fail(5) refusal.
    parsed_targets = parse_dispensation_targets(dispense_targets, records)
    dispensed_citations: list[AuditedCitation] = []
    for raw, target in zip(dispense_targets, parsed_targets):
        matched = [
            citation
            for citation in hard_missing
            if citation.original.target == target
        ]
        if not matched:
            if any(
                citation.original.target == target for citation in legacy_citations
            ):
                fail(
                    2,
                    "dispensation names a citation already tolerated as legacy: "
                    f"{raw}",
                )
            if any(
                citation.original.target == target
                for citation in audited_citations
            ):
                fail(2, f"dispensation names a citation that resolves: {raw}")
            fail(2, f"dispensation names a citation the journal does not contain: {raw}")
        if "dispense-citation" in DISPENSATION_LEGS:
            dispensed_citations.extend(
                citation
                for citation in matched
                if citation not in dispensed_citations
            )
    hard_missing = [
        citation for citation in hard_missing if citation not in dispensed_citations
    ]
    # CONTROL cited-path BEGIN
    if hard_missing:
        fail(
            5,
            "cited path does not exist within run or repository: "
            f"{hard_missing[0].missing_finding()}",
        )
    # CONTROL cited-path END

    audit_projected_surfaces(
        records,
        start,
        repository=repo_root,
        run_dir=run_dir,
    )

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
    legacy_section = (
        render_section(
            "Legacy Citations",
            [citation.missing_finding() for citation in legacy_citations],
        )
        + "\n"
        if legacy_citations
        else ""
    )
    dispensed_section = (
        render_section(
            "Dispensed Citations",
            [
                f"{citation.missing_finding()} — reason: {dispense_reason}"
                for citation in dispensed_citations
            ],
        )
        + "\n"
        if dispensed_citations
        else ""
    )
    # CONTROL repo-conformance BEGIN
    conformance_section = audit_repo_conformance(start, run_dir)
    conformance_prefix = conformance_section + "\n" if conformance_section else ""
    # CONTROL repo-conformance END
    return (
        conformance_prefix
        + correction_section
        + legacy_section
        + dispensed_section
        + render_section("Residual Risks", risks)
        + "\n"
        + render_section("Follow-ups", follow_ups)
    )


def main(argv: list[str] | None = None) -> int:
    try:
        run_dir, dispense_targets, dispense_reason = parse_argv(
            sys.argv[1:] if argv is None else argv
        )
        output = audit(run_dir, dispense_targets, dispense_reason)
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
