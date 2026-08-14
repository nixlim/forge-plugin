#!/usr/bin/env python3
"""Serialize the allowlisted learning proposal writer across processes."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import runpy
import stat
import sys
from typing import Iterator


ORIGINAL = Path(__file__).with_name("learn-proposals.py")
DIAGNOSTIC = "forge: learning proposal refused — unsafe-lock"


class LockFailure(RuntimeError):
    pass


def ensure_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        try:
            path.mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise LockFailure from exc
        metadata = path.lstat()
    except OSError as exc:
        raise LockFailure from exc
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise LockFailure


@contextmanager
def proposal_lock(repo: Path) -> Iterator[None]:
    if not repo.is_dir() or repo.is_symlink():
        raise LockFailure
    forge = repo / ".forge"
    tmp = forge / "tmp"
    ensure_directory(forge)
    ensure_directory(tmp)
    lock_path = tmp / "learn-proposals.lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise LockFailure from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise LockFailure
        with os.fdopen(descriptor, "r+b", closefd=True) as handle:
            descriptor = -1
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def locked_run(repo: Path, argv: list[str]) -> None:
    with proposal_lock(repo):
        previous = sys.argv
        sys.argv = [str(ORIGINAL), *argv]
        try:
            runpy.run_path(str(ORIGINAL), run_name="__main__")
        finally:
            sys.argv = previous


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--repo", required=True)
    try:
        args, _ = parser.parse_known_args(argv)
        locked_run(Path(args.repo), argv)
    except LockFailure:
        print(DIAGNOSTIC, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
