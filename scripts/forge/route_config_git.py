"""Bounded Git calls and owner-only path checks for route configuration.

The private-group check requires NSS to enumerate matching owner and group
records. A directory service can still hide another account's primary or
supplementary membership in that group, so such unseen memberships remain a
risk; the synchronous NSS calls also have no local timeout.
"""

from __future__ import annotations

import errno
import grp
import os
import pwd
import signal
import stat
import subprocess
import time
from pathlib import Path

ACL_XATTRS = frozenset({"system.posix_acl_access", "system.richacl", "system.nfs4_acl"})
DEFAULT_ACL_XATTRS = frozenset({"system.posix_acl_default"})
NO_XATTR_SUPPORT = frozenset({errno.ENOTSUP, errno.EOPNOTSUPP})

SCRUBBED_GIT_ENVIRONMENT = frozenset(
    {
        "GIT_DIR",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_WORK_TREE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_REPLACE_REF_BASE",
        "GIT_LITERAL_PATHSPECS",
        "GIT_GLOB_PATHSPECS",
        "GIT_NOGLOB_PATHSPECS",
        "GIT_ICASE_PATHSPECS",
        "GIT_ATTR_NOSYSTEM",
        "GIT_ATTR_SOURCE",
    }
)


class RouteRefusal(RuntimeError):
    """A fail-closed route configuration refusal."""


def _identity_is_enumerable(
    owner: pwd.struct_passwd,
    group: grp.struct_group,
    accounts: list[pwd.struct_passwd],
    groups: list[grp.struct_group],
) -> bool:
    owner_visible = any(
        entry.pw_uid == owner.pw_uid
        and entry.pw_name == owner.pw_name
        and entry.pw_gid == owner.pw_gid
        for entry in accounts
    )
    matching_groups = [entry for entry in groups if entry.gr_gid == group.gr_gid]
    group_visible = bool(matching_groups) and all(
        entry.gr_gid == group.gr_gid
        and entry.gr_name == group.gr_name
        and set(entry.gr_mem) == set(group.gr_mem)
        for entry in matching_groups
    )
    return owner_visible and group_visible


def _owner_private_group(uid: int, gid: int) -> bool:
    """Return whether ``gid`` is ``uid``'s enumerable, private primary group."""

    try:
        owner = pwd.getpwuid(uid)
        group = grp.getgrgid(gid)
        accounts = pwd.getpwall()
        groups = grp.getgrall()
    except (KeyError, OSError):
        return False
    if owner.pw_gid != gid or not _identity_is_enumerable(owner, group, accounts, groups):
        return False
    foreign = {entry.pw_name for entry in accounts if entry.pw_uid != uid}
    aliases = {entry.pw_name for entry in accounts if entry.pw_uid == uid}
    if any(name in foreign or name not in aliases for name in group.gr_mem):
        return False
    return not any(entry.pw_gid == gid and entry.pw_uid != uid for entry in accounts)


def _may_have_acl(descriptor: int, names: frozenset[str]) -> bool:
    listxattr = getattr(os, "listxattr", None)
    if listxattr is None:
        return True
    try:
        present = listxattr(descriptor)
    except OSError as exc:
        return exc.errno not in NO_XATTR_SUPPORT
    return not names.isdisjoint(present)


def _may_have_access_acl(descriptor: int) -> bool:
    """Return whether an access ACL may widen the group-class write bit."""

    return _may_have_acl(descriptor, ACL_XATTRS)


def default_acl_risk(descriptor: int, replacement_mode: int) -> bool:
    """Return whether a default ACL may grant group-class replacement writes."""

    try:
        group_writable = (os.fstat(descriptor).st_mode | replacement_mode) & stat.S_IWGRP
    except OSError:
        return True
    if not group_writable:
        return False
    return _may_have_acl(descriptor, DEFAULT_ACL_XATTRS)


def owner_only_writable(descriptor: int, metadata: os.stat_result) -> bool:
    """Return whether the inode is writable only by its owner or private group."""

    if metadata.st_mode & stat.S_IWOTH:
        return False
    if not metadata.st_mode & stat.S_IWGRP:
        return True
    if _may_have_access_acl(descriptor):
        return False
    return _owner_private_group(metadata.st_uid, metadata.st_gid)


def _git_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        if name in SCRUBBED_GIT_ENVIRONMENT or name.startswith("GIT_CONFIG_"):
            environment.pop(name)
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return environment


def _signal_group(process: subprocess.Popen[bytes], signum: signal.Signals) -> None:
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def _stop_group(process: subprocess.Popen[bytes], timeout: float) -> None:
    grace = max(0.01, min(timeout, 1.0))
    _signal_group(process, signal.SIGTERM)
    time.sleep(grace)
    _signal_group(process, signal.SIGKILL)
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        process.kill()
    if process.stdout is not None:
        process.stdout.close()


def run_git(
    repo: Path,
    *arguments: str,
    timeout: float,
    resolution: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    """Run Git for ``repo`` with fixed bounds and no ambient repository selectors."""

    command = ["git", "-C", str(repo), *arguments]
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_git_environment(),
        start_new_session=True,
    ) as process:
        try:
            stdout, _stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _stop_group(process, timeout)
            subject = "route resolution" if resolution else "routes file"
            raise RouteRefusal(f"forge: {subject} refused — git timed out") from exc
        return subprocess.CompletedProcess(command, process.returncode, stdout, None)


def git_path(repo: Path, argument: str, *, timeout: float) -> Path:
    """Resolve one Git path query or refuse as unreadable."""

    result = run_git(repo, "rev-parse", argument, timeout=timeout)
    if result.returncode != 0:
        raise RouteRefusal("forge: routes file refused — unreadable")
    try:
        raw = result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RouteRefusal("forge: routes file refused — unreadable") from exc
    if not raw:
        raise RouteRefusal("forge: routes file refused — unreadable")
    path = Path(raw)
    return (path if path.is_absolute() else repo / path).resolve()
