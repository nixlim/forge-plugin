from __future__ import annotations

import subprocess
from pathlib import Path


class ChainPathError(RuntimeError):
    """Raised when the Git-common chain authority cannot be resolved."""


def common_worktree_root(repository: Path) -> Path:
    """Return the main-checkout root that owns worktree-transparent chains.

    Git stores ``--git-common-dir`` beneath the main checkout for both the
    main worktree and every registered linked worktree.  DM-012/DM-014 chain
    authority therefore belongs beside that common directory, never beside a
    caller's linked-worktree ``.git`` file.
    """

    try:
        worktree = Path(repository).expanduser().resolve(strict=True)
        if not worktree.is_dir():
            raise ValueError("repository is not a directory")
        common: Path | None = None
        for arguments, require_absolute in (
            (("--path-format=absolute", "--git-common-dir"), True),
            (("--git-common-dir",), False),
        ):
            completed = subprocess.run(
                ["git", "-C", str(worktree), "rev-parse", *arguments],
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
                continue
            candidate = Path(rendered)
            if require_absolute and not candidate.is_absolute():
                continue
            if not candidate.is_absolute():
                candidate = worktree / candidate
            try:
                common = candidate.resolve(strict=True)
            except OSError:
                continue
            break
        if common is None or not common.is_dir():
            raise ValueError("Git common directory is unavailable")
        root = common.parent.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Git common worktree root is unavailable")
        return root
    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise ChainPathError("Git-common chain authority is unavailable") from exc


def chain_storage_root(repository: Path) -> Path:
    """Return the sole DM-012/DM-014 chain storage root for ``repository``."""

    return common_worktree_root(repository) / ".forge" / "chains"
