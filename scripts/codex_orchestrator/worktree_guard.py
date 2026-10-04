from __future__ import annotations

import os
import stat
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from . import chain_paths, journal

FORGE_SCRIPTS = Path(__file__).resolve().parents[1] / "forge"
if str(FORGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FORGE_SCRIPTS))

from commitment_paths import (  # noqa: E402
    commitment_surfaces,
    iter_record_citations,
    resolve_contained_path,
    surface_roots,
)

WORKTREE_GUARD_LEGS = frozenset({"recorded-repo", "cited-evidence"})
WORKTREE_GUARD_CITATION_SURFACES = (
    "execution.prompt",
    "execution.events",
    "execution.handoff",
    "execution_result.handoff",
    "verification.evidence",
    "decision.basis",
    "verification.observation",
)
WORKTREE_INPUT_CONTROLS = frozenset(
    {"symlinked-runs-root", "symlinked-run-directory", "symlinked-journal"}
)
INPUT_DIAGNOSTIC = "forge: worktree check refused — unreadable input"
RUN_INPUT_DIAGNOSTIC = "forge: worktree check refused — run {run_id}"


class WorktreeGuardError(RuntimeError):
    """Raised when the read-only cleanup proof cannot be completed."""

    def __init__(
        self, message: str = INPUT_DIAGNOSTIC, *, run_id: str | None = None
    ) -> None:
        super().__init__(message)
        self.run_id = run_id


@dataclass(frozen=True)
class WorktreeDependency:
    run_id: str
    relative_worktree: str


def _run_git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC) from exc


def _require_head(repository: Path) -> str:
    result = _run_git(repository, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    lines = result.stdout.splitlines()
    if result.returncode != 0 or len(lines) != 1 or not lines[0]:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)
    try:
        return lines[0].decode("ascii")
    except UnicodeError as exc:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC) from exc


def _archive_is_committed(repository: Path, head: str, run_id: str) -> bool:
    archive = f"{head}:.forge/history/runs/{run_id}.md"
    result = _run_git(repository, "cat-file", "-t", archive)
    if result.returncode == 0:
        return result.stdout == b"blob\n"
    path = f".forge/history/runs/{run_id}.md"
    presence = _run_git(
        repository, "ls-tree", "-z", head, "--", f":(literal){path}"
    )
    if presence.returncode != 0 or presence.stdout:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)
    return False


def _safe_output_text(value: str) -> bool:
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return all(
        ord(character) >= 32 and not 127 <= ord(character) <= 159
        for character in value
    )


def _safe_run_id(run_id: str) -> bool:
    return bool(
        run_id
        and not run_id.startswith(".")
        and all(character not in "/\\" for character in run_id)
        and _safe_output_text(run_id)
    )


def _citation_field_is_valid(
    extraction: str, value: object, *, allow_empty: bool = False
) -> bool:
    if extraction in {"direct", "tokens"}:
        return isinstance(value, str) and (bool(value) or allow_empty)
    if extraction in {"array", "token-array"}:
        return isinstance(value, list) and all(
            isinstance(member, str) and bool(member) for member in value
        )
    return False


def _legacy_declaration_line(records: list[dict[str, object]]) -> int | None:
    declaration = journal._legacy_compatibility_declaration(records)
    line = declaration.get("_line") if declaration is not None else None
    return line if isinstance(line, int) else None


def _record_kind(
    record: dict[str, object], declaration_line: int | None
) -> str:
    kind = record.get("type")
    if kind == "observation" and journal._legacy_allows(
        "observation", declaration_line, record
    ):
        return kind
    if not isinstance(kind, str) or kind not in journal.JOURNAL_ENTRY_TYPES:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)
    return kind


def _normalize_legacy_evidence(
    candidate: dict[str, object],
    kind: str,
    declaration_line: int | None,
    record: dict[str, object],
) -> None:
    evidence = candidate.get("evidence")
    if (
        kind == "verification"
        and isinstance(evidence, str)
        and evidence
        and journal._legacy_allows("string-evidence", declaration_line, record)
    ):
        candidate["evidence"] = [evidence]


def _validate_citation_fields(
    candidate: dict[str, object],
    kind: str,
    declaration_line: int | None,
    record: dict[str, object],
) -> None:
    for citation in (
        surface
        for surface in commitment_surfaces()
        if surface.owner == "record" and surface.record_type == kind
    ):
        assert citation.field is not None
        if citation.field not in candidate:
            continue
        value = candidate[citation.field]
        allow_empty = (
            citation.label == "execution.events"
            and (
                candidate.get("event_source") == "claude"
                or journal._legacy_allows("empty-events", declaration_line, record)
            )
        ) or (
            citation.label == "execution_result.handoff"
            and candidate.get("status") in {"blocked", "failed"}
        )
        if not _citation_field_is_valid(
            citation.extraction, value, allow_empty=allow_empty
        ):
            raise WorktreeGuardError(INPUT_DIAGNOSTIC)


def _normalize_record(
    record: dict[str, object], declaration_line: int | None
) -> dict[str, object]:
    kind = _record_kind(record, declaration_line)
    candidate = dict(record)
    _normalize_legacy_evidence(candidate, kind, declaration_line, record)
    _validate_citation_fields(candidate, kind, declaration_line, record)
    return candidate


def _normalize_record_shapes(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    declaration_line = _legacy_declaration_line(records)
    return [_normalize_record(record, declaration_line) for record in records]


def _recorded_repository(opening: dict[str, object], common_root: Path) -> Path:
    recorded = opening.get("repo")
    if recorded is None:
        return common_root
    if not isinstance(recorded, str) or not recorded or not Path(recorded).is_absolute():
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)
    try:
        return Path(os.path.realpath(recorded))
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC) from exc


def _is_inside(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _depends_on_recorded_repo(recorded_repo: Path, worktree: Path) -> bool:
    return "recorded-repo" in WORKTREE_GUARD_LEGS and _is_inside(
        recorded_repo, worktree
    )


def _resolve_citation(value: str, roots: tuple[Path, ...]) -> Path:
    try:
        candidate = Path(value).expanduser()
        if candidate.is_absolute():
            return candidate.resolve(strict=False)
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC) from exc
    selected = resolve_contained_path(value, roots)
    if selected is None:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)
    return selected.resolved


def _depends_on_citation(
    records: list[dict[str, object]],
    *,
    repository: Path,
    run_dir: Path,
    worktree: Path,
) -> bool:
    if "cited-evidence" not in WORKTREE_GUARD_LEGS:
        return False
    for record in records:
        for citation in iter_record_citations(record, enforcement="audit"):
            if citation.surface.label not in WORKTREE_GUARD_CITATION_SURFACES:
                continue
            roots = surface_roots(
                citation.surface,
                repository=repository,
                run_dir=run_dir,
            )
            resolved = _resolve_citation(citation.value, roots)
            if _is_inside(resolved, worktree):
                return True
    return False


def _runs_root_entries(runs_root: Path) -> tuple[os.DirEntry[str], ...] | None:
    try:
        root_stat = runs_root.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(root_stat.st_mode):
        if "symlinked-runs-root" in WORKTREE_INPUT_CONTROLS:
            raise WorktreeGuardError(INPUT_DIAGNOSTIC)
        return None
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or not _readable_mode(root_stat.st_mode, directory=True)
        or runs_root.resolve(strict=True) != runs_root
    ):
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)
    with os.scandir(runs_root) as iterator:
        entries = tuple(sorted(iterator, key=lambda entry: os.fsencode(entry.name)))
    _require_same_entry(runs_root, root_stat)
    return entries


def _readable_mode(mode: int, *, directory: bool = False) -> bool:
    read_mask = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    execute_mask = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    return bool(mode & read_mask) and (not directory or bool(mode & execute_mask))


def _require_same_entry(path: Path, observed: os.stat_result) -> None:
    rebound = path.lstat()
    if (rebound.st_dev, rebound.st_ino, rebound.st_mode) != (
        observed.st_dev,
        observed.st_ino,
        observed.st_mode,
    ):
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)


def _journal_path_for_entry(runs_root: Path, entry: os.DirEntry[str]) -> Path | None:
    observed = entry.stat(follow_symlinks=False)
    entry_path = runs_root / entry.name
    if stat.S_ISREG(observed.st_mode) and not entry.name.startswith("."):
        _require_same_entry(entry_path, observed)
        return None
    if not _safe_run_id(entry.name):
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)
    if stat.S_ISLNK(observed.st_mode):
        if "symlinked-run-directory" in WORKTREE_INPUT_CONTROLS:
            raise WorktreeGuardError(INPUT_DIAGNOSTIC)
        return None
    if not stat.S_ISDIR(observed.st_mode) or not _readable_mode(
        observed.st_mode, directory=True
    ):
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)
    return _journal_for_directory(entry_path, observed)


def _journal_for_directory(
    entry_path: Path, observed: os.stat_result
) -> Path | None:
    with os.scandir(entry_path) as iterator:
        child_names = {child.name for child in iterator}
    _require_same_entry(entry_path, observed)
    if "journal.jsonl" not in child_names:
        if child_names:
            raise WorktreeGuardError(INPUT_DIAGNOSTIC)
        # worktree-check is read-only and does not reconcile or mutate the run
        # registry, so an empty ownerless placeholder needs no registry lookup.
        return None
    candidate = entry_path / "journal.jsonl"
    journal_stat = candidate.stat(follow_symlinks=False)
    if stat.S_ISLNK(journal_stat.st_mode):
        if "symlinked-journal" in WORKTREE_INPUT_CONTROLS:
            raise WorktreeGuardError(INPUT_DIAGNOSTIC)
        return candidate
    if (
        not stat.S_ISREG(journal_stat.st_mode)
        or not _readable_mode(journal_stat.st_mode)
        or journal_stat.st_size <= 0
    ):
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)
    return candidate


def _iter_journal_paths(common_root: Path) -> Iterator[Path]:
    runs_root = common_root / ".codex-orchestrator" / "runs"
    try:
        entries = _runs_root_entries(runs_root)
        if entries is None:
            return
        for entry in entries:
            candidate = _journal_path_for_entry(runs_root, entry)
            if candidate is not None:
                yield candidate
    except WorktreeGuardError:
        raise
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC) from exc


def _journal_paths(common_root: Path) -> tuple[Path, ...]:
    return tuple(_iter_journal_paths(common_root))


def _require_current_owner(
    journal_path: Path,
    state: journal.RunState,
) -> None:
    if state.legacy or state.pre_coordination:
        return
    owner = journal._read_owner_observation(journal_path.parent / "owner")
    if owner is None:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)


def _validated_journal(
    journal_path: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    raw = journal._stable_journal_read(journal_path)
    records, issues = journal._decode_journal_snapshot(
        raw, allow_partial_final_line=False
    )
    if issues:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC)
    state = journal._scan_run(journal_path.parent, raw=raw)
    normalized = _normalize_record_shapes(records)
    _require_current_owner(journal_path, state)
    return normalized[0], normalized


def _dependency_for_journal(
    repository: Path,
    head: str,
    target: Path,
    common_root: Path,
    relative: str,
    journal_path: Path,
) -> WorktreeDependency | None:
    run_id = journal_path.parent.name
    try:
        opening, citation_records = _validated_journal(journal_path)
        recorded_repo = _recorded_repository(opening, common_root)
        if _archive_is_committed(repository, head, run_id):
            return None
        recorded_dependency = _depends_on_recorded_repo(recorded_repo, target)
        citation_dependency = _depends_on_citation(
            citation_records,
            repository=common_root,
            run_dir=journal_path.parent,
            worktree=target,
        )
        if recorded_dependency or citation_dependency:
            return WorktreeDependency(run_id, relative)
        return None
    except WorktreeGuardError as exc:
        raise WorktreeGuardError(run_id=run_id) from exc
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise WorktreeGuardError(run_id=run_id) from exc


def find_dependency(repo: Path, worktree: Path) -> WorktreeDependency | None:
    """Return the first unarchived run that still depends on ``worktree``."""

    try:
        repository = repo.expanduser().resolve(strict=True)
        target = worktree.expanduser().resolve(strict=True)
        if not repository.is_dir() or not target.is_dir():
            raise WorktreeGuardError(INPUT_DIAGNOSTIC)
        common_root = chain_paths.common_worktree_root(repository)
        head = _require_head(repository)
        relative = Path(os.path.relpath(target, common_root)).as_posix()
        if not _safe_output_text(relative):
            raise WorktreeGuardError(INPUT_DIAGNOSTIC)
        for journal_path in _iter_journal_paths(common_root):
            dependency = _dependency_for_journal(
                repository, head, target, common_root, relative, journal_path
            )
            if dependency is not None:
                return dependency
        if _require_head(repository) != head:
            raise WorktreeGuardError(INPUT_DIAGNOSTIC)
    except WorktreeGuardError:
        raise
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise WorktreeGuardError(INPUT_DIAGNOSTIC) from exc
    return None


def _input_diagnostics(error: WorktreeGuardError) -> tuple[str, ...]:
    diagnostics = [INPUT_DIAGNOSTIC]
    if error.run_id is not None:
        diagnostics.append(RUN_INPUT_DIAGNOSTIC.format(run_id=error.run_id))
    return tuple(diagnostics)


def main(repo: Path, worktree: Path) -> int:
    try:
        dependency = find_dependency(repo, worktree)
        if dependency is None:
            return 0
        print(
            "forge: worktree cleanup deferred — run "
            f"{dependency.run_id} has no committed archive and depends on "
            f"{dependency.relative_worktree}",
            file=sys.stderr,
        )
    except WorktreeGuardError as exc:
        for diagnostic in _input_diagnostics(exc):
            print(diagnostic, file=sys.stderr)
        return 2
    except Exception:
        print(INPUT_DIAGNOSTIC, file=sys.stderr)
        return 2
    return 1
