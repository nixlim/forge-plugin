from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

QUIET_GIT_SETTINGS = (
    ("maintenance.auto", "false"),
    ("maintenance.autoDetach", "false"),
    ("gc.auto", "0"),
    ("gc.autoDetach", "false"),
    ("receive.autoGc", "false"),
)


def _resolved_root(
    path: os.PathLike[str] | str, cwd: os.PathLike[str] | str | None
) -> Path:
    root = Path(path)
    if not root.is_absolute():
        root = (Path.cwd() if cwd is None else Path(cwd)) / root
    return root.resolve()


def _linked_worktree_config(git_file: Path) -> Path | None:
    try:
        prefix, location = git_file.read_text(encoding="utf-8").strip().split(":", 1)
    except (OSError, UnicodeError, ValueError):
        return None
    if prefix.lower() != "gitdir" or not location.strip():
        return None
    git_dir = Path(location.strip())
    if not git_dir.is_absolute():
        git_dir = git_file.parent / git_dir
    common_dir = git_dir
    try:
        common_location = (git_dir / "commondir").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        pass
    else:
        if common_location:
            common_dir = git_dir / common_location
    config = common_dir.resolve() / "config"
    return config if config.is_file() else None


def _repository_config(root: Path) -> Path:
    git_dir = root / ".git"
    worktree_config = git_dir / "config"
    if (
        worktree_config.is_file()
        and (git_dir / "HEAD").is_file()
        and (git_dir / "objects").is_dir()
        and (git_dir / "refs").is_dir()
    ):
        return worktree_config
    git_file = git_dir
    if git_file.is_file():
        linked_config = _linked_worktree_config(git_file)
        if linked_config is not None:
            return linked_config
    bare_config = root / "config"
    if (
        bare_config.is_file()
        and (root / "HEAD").is_file()
        and (root / "objects").is_dir()
        and (root / "refs").is_dir()
    ):
        return bare_config
    raise FileNotFoundError(f"Git repository config is absent under {root}")


def _append_quiet_settings(config: Path) -> None:
    if not config.is_file():
        raise FileNotFoundError(f"Git repository config is absent: {config}")
    rendered = "".join(
        f"[{key.split('.', 1)[0]}]\n\t{key.split('.', 1)[1]} = {value}\n"
        for key, value in QUIET_GIT_SETTINGS
    ).encode("ascii")
    if not rendered:
        return
    existing = config.read_bytes()
    separator = b"" if not existing or existing.endswith(b"\n") else b"\n"
    with config.open("ab") as handle:
        handle.write(separator + rendered)


def init_quiet_repository(
    path: os.PathLike[str] | str,
    *init_args: str,
    cwd: os.PathLike[str] | str | None = None,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Initialize one repository and persist settings that suppress auto workers."""
    result = subprocess.run(
        ["git", "init", *init_args, os.fspath(path)],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    root = _resolved_root(path, cwd)
    config = root / "config" if "--bare" in init_args else root / ".git" / "config"
    _append_quiet_settings(config)
    return result


def quiet_repository(path: os.PathLike[str] | str) -> None:
    """Persist quiet settings in an existing bare, regular, or linked repository."""
    _append_quiet_settings(_repository_config(_resolved_root(path, None)))


def _validated_config_count(environment: Mapping[str, str]) -> int:
    raw_count = environment.get("GIT_CONFIG_COUNT", "0")
    if not raw_count or any(character not in "0123456789" for character in raw_count):
        raise ValueError("GIT_CONFIG_COUNT must be a non-negative decimal")
    count = int(raw_count)
    for index in range(count):
        if (
            f"GIT_CONFIG_KEY_{index}" not in environment
            or f"GIT_CONFIG_VALUE_{index}" not in environment
        ):
            raise ValueError(f"GIT_CONFIG_COUNT entry {index} is incomplete")
    return count


def _already_has_quiet_tail(environment: Mapping[str, str], count: int) -> bool:
    if count < len(QUIET_GIT_SETTINGS):
        return False
    start = count - len(QUIET_GIT_SETTINGS)
    return all(
        environment[f"GIT_CONFIG_KEY_{start + offset}"] == key
        and environment[f"GIT_CONFIG_VALUE_{start + offset}"] == value
        for offset, (key, value) in enumerate(QUIET_GIT_SETTINGS)
    )


def with_quiet_git(environment: Mapping[str, str]) -> dict[str, str]:
    """Copy an environment and append quiet Git config without losing its entries."""
    count = _validated_config_count(environment)
    merged = dict(environment)
    if _already_has_quiet_tail(environment, count):
        return merged
    for offset, (key, value) in enumerate(QUIET_GIT_SETTINGS):
        merged[f"GIT_CONFIG_KEY_{count + offset}"] = key
        merged[f"GIT_CONFIG_VALUE_{count + offset}"] = value
    merged["GIT_CONFIG_COUNT"] = str(count + len(QUIET_GIT_SETTINGS))
    return merged
