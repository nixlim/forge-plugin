from __future__ import annotations

import errno
import os
import subprocess
from pathlib import Path

RECORDED_REPOSITORY_LEGS = frozenset({"absent-worktree"})


class ResolutionError(RuntimeError):
    """The recorded repository cannot be proved from caller-owned authority."""


def _git_directory(repository: Path, *arguments: str) -> Path:
    completed = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", *arguments],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    rendered = completed.stdout.rstrip("\n")
    if (
        completed.returncode != 0
        or not rendered
        or "\n" in rendered
        or "\r" in rendered
    ):
        raise ResolutionError
    candidate = Path(rendered)
    if not candidate.is_absolute():
        candidate = repository / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ResolutionError from exc
    if not resolved.is_dir():
        raise ResolutionError
    return resolved


def _git_common_directory(repository: Path) -> Path:
    try:
        return _git_directory(
            repository, "--path-format=absolute", "--git-common-dir"
        )
    except ResolutionError:
        return _git_directory(repository, "--git-common-dir")


def _present_repository(
    recorded: str, caller_repository: Path, state_root: Path
) -> Path:
    try:
        repository = Path(recorded).expanduser().resolve(strict=True)
        caller = Path(caller_repository).expanduser().resolve(strict=True)
        state = Path(state_root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ResolutionError from exc
    if not repository.is_dir() or not caller.is_dir() or not state.is_dir():
        raise ResolutionError
    try:
        top_level = _git_directory(repository, "--show-toplevel")
        recorded_common = _git_common_directory(repository)
        caller_common = _git_common_directory(caller)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ResolutionError from exc
    if recorded_common != caller_common or caller_common.parent != state:
        raise ResolutionError
    return top_level


def _absent_repository(
    recorded: str, *, state_root: Path, run_dir: Path
) -> tuple[Path, Path]:
    if "absent-worktree" not in RECORDED_REPOSITORY_LEGS:
        raise ResolutionError
    if not os.path.isabs(recorded) or os.path.normpath(recorded) != recorded:
        raise ResolutionError
    state = Path(os.path.realpath(state_root))
    candidate = Path(recorded)
    worktrees = state / ".worktrees"
    try:
        below_worktrees = candidate.relative_to(worktrees)
        absent_relative = candidate.relative_to(state)
    except ValueError as exc:
        raise ResolutionError from exc
    if below_worktrees == Path("."):
        raise ResolutionError
    expected_run_dir = state / ".codex-orchestrator" / "runs" / Path(run_dir).name
    if Path(run_dir) != expected_run_dir:
        raise ResolutionError
    return state, absent_relative


def resolve(
    recorded: object,
    *,
    state_root: Path,
    run_dir: Path,
    caller_repository: Path | None = None,
) -> tuple[Path, Path | None]:
    """Resolve ``run_started.repo`` without trusting an absent recorded path."""

    if (
        not isinstance(recorded, str)
        or not recorded
        or not os.path.isabs(recorded)
    ):
        raise ResolutionError
    try:
        os.lstat(recorded)
    except OSError as exc:
        if exc.errno not in {errno.ENOENT, errno.ENOTDIR}:
            raise ResolutionError from exc
        return _absent_repository(
            recorded,
            state_root=state_root,
            run_dir=run_dir,
        )
    except ValueError as exc:
        raise ResolutionError from exc
    try:
        # State root is the caller Git common directory's parent. With a
        # separate Git directory or submodule it is not the checkout, so it is
        # absent-path policy data and must never be queried as Git authority.
        caller = Path(recorded) if caller_repository is None else caller_repository
        return _present_repository(recorded, caller, state_root), None
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ResolutionError from exc
