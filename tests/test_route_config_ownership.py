from __future__ import annotations

import errno
import grp
import os
import pwd
import stat
import struct
import types
import unittest
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from unittest import mock

from tests.test_route_config_support import ROOT, route_config, route_text
from tests.test_route_config_support import route_config_git as ownership
from tests.test_route_config_support import route_config_probe as probe

UMASKS = (0o002, 0o022)
LOCAL_REFUSAL = "forge: route init refused — unsafe local directory\n"
EXCLUDE_REFUSAL = "forge: route init refused — unsafe info/exclude\n"
SCRATCH_REFUSAL = "forge: route probe refused — unsafe scratch directory"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _passwd(name: str, uid: int, gid: int) -> pwd.struct_passwd:
    return pwd.struct_passwd((name, "x", uid, gid, "", "/tmp", "/bin/sh"))


def _legacy_writable(_descriptor: int, metadata: os.stat_result) -> bool:
    return not metadata.st_mode & 0o022


def _primary_gid_only(uid: int, gid: int) -> bool:
    return ownership.pwd.getpwuid(uid).pw_gid == gid


def _default_acl_first(descriptor: int, metadata: os.stat_result) -> bool:
    if stat.S_ISDIR(metadata.st_mode) and ownership._may_have_acl(
        descriptor, ownership.DEFAULT_ACL_XATTRS
    ):
        return False
    return ownership.owner_only_writable(descriptor, metadata)


class RouteOwnershipMixin:
    @contextmanager
    def _umask(self, mask: int) -> Iterator[None]:
        previous = os.umask(mask)
        try:
            yield
        finally:
            os.umask(previous)

    @contextmanager
    def _group(self, private: bool, acl: bool = False) -> Iterator[None]:
        with (
            mock.patch.object(ownership, "_owner_private_group", return_value=private),
            mock.patch.object(ownership, "_may_have_access_acl", return_value=acl),
            mock.patch.object(route_config, "default_acl_risk", return_value=False),
        ):
            yield

    def _skip_default_acl(self) -> None:
        listxattr = getattr(os, "listxattr", None)
        if listxattr is not None:
            with suppress(OSError):
                if "system.posix_acl_default" in listxattr(self.scratch):
                    self.skipTest("scratch directory carries system.posix_acl_default")

    def _stock_clone(self, name: str, mask: int) -> Path:
        self._skip_default_acl()
        with self._umask(mask):
            source = self.make_repo(f"{name}-source")
            keep = source / ".forge/history/keep"
            keep.parent.mkdir(parents=True)
            keep.write_text("keep\n", encoding="utf-8")
            self.git(source, "add", ".forge/history/keep")
            self.git(source, "commit", "-q", "-m", "tracked forge")
            clone = self.scratch / name
            self.git(self.scratch, "clone", "-q", str(source), str(clone))
        (clone / ".git/info").chmod(0o777 & ~mask)
        (clone / ".git/info/exclude").chmod(0o666 & ~mask)
        (clone / ".forge").chmod(0o777 & ~mask)
        return clone

    def _plain_repo(self, name: str, mask: int) -> Path:
        self._skip_default_acl()
        with self._umask(mask):
            repo = self.make_repo(name)
        (repo / ".git/info").chmod(0o777 & ~mask)
        (repo / ".git/info/exclude").chmod(0o666 & ~mask)
        return repo

    def _init_status(self, repo: Path, mask: int) -> tuple[int, str, str]:
        with self._umask(mask):
            return self.invoke("init", "--repo", str(repo))

    def _assert_init_refusal(self, repo: Path, mask: int, diagnostic: str) -> None:
        self.assertEqual(self._init_status(repo, mask), (1, "", diagnostic))
        self.assertFalse((repo / ".forge/local/routes.toml").exists())

    def _assert_init_success(self, repo: Path, mask: int) -> None:
        status, _stdout, stderr = self._init_status(repo, mask)
        self.assertEqual((status, stderr), (0, ""))

    def _assert_disabled(self, function: Callable[..., object], *args: object) -> None:
        with self.assertRaises(AssertionError):
            function(*args)

    def _both_umasks(self, function: Callable[[int], object]) -> tuple[int, int]:
        for mask in UMASKS:
            with self.subTest(umask=oct(mask)):
                function(mask)
        return UMASKS

    def _lookup_private(
        self,
        entries: list[object],
        members: list[str],
        gid: int = 1000,
        *,
        owner: object | None = None,
        groups: list[object] | None = None,
    ) -> bool:
        group = grp.struct_group(("owners", "x", gid, members))
        resolved_owner = owner if owner is not None else entries[0]
        enumerated_groups = [group] if groups is None else groups
        with (
            mock.patch.object(ownership.pwd, "getpwuid", return_value=resolved_owner),
            mock.patch.object(ownership.grp, "getgrgid", return_value=group),
            mock.patch.object(ownership.pwd, "getpwall", return_value=entries),
            mock.patch.object(ownership.grp, "getgrall", return_value=enumerated_groups),
        ):
            return ownership._owner_private_group(1000, gid)

    def _access_acl(self, item: list[str] | OSError) -> bool:
        kwargs = {"side_effect": item} if isinstance(item, OSError) else {"return_value": item}
        with mock.patch.object(ownership.os, "listxattr", create=True, **kwargs):
            return ownership._may_have_access_acl(-1)

    def test_owner_only_modes_accept_without_group_lookup(self) -> None:
        lookup = mock.Mock(side_effect=AssertionError("group lookup must stay lazy"))
        with mock.patch.object(ownership, "_owner_private_group", lookup):
            for mode in (0o700, 0o755, 0o711, 0o500, 0o644):
                with self.subTest(mode=oct(mode)):
                    metadata = types.SimpleNamespace(st_mode=mode, st_uid=1000, st_gid=1000)
                    self.assertTrue(ownership.owner_only_writable(-1, metadata))

    def test_missing_listxattr_accepts_real_owner_only_directory_and_file(self) -> None:
        directory = self.scratch / "owner-only"
        directory.mkdir()
        directory.chmod(0o700)
        file = directory / "routes.toml"
        file.write_bytes(b"")
        file.chmod(0o600)
        descriptors = [os.open(path, os.O_RDONLY) for path in (directory, file)]
        for descriptor in descriptors:
            self.addCleanup(os.close, descriptor)
        metadata = [os.fstat(descriptor) for descriptor in descriptors]
        lookup = mock.Mock(side_effect=AssertionError("group lookup must stay lazy"))
        with (
            mock.patch.object(ownership.os, "listxattr", None, create=True),
            mock.patch.object(ownership, "_owner_private_group", lookup),
        ):
            self.assertEqual([stat.S_IMODE(item.st_mode) for item in metadata], [0o700, 0o600])
            self.assertTrue(ownership.owner_only_writable(descriptors[0], metadata[0]))
            self.assertTrue(ownership.owner_only_writable(descriptors[1], metadata[1]))
            self._assert_disabled(
                self.assertTrue, _default_acl_first(descriptors[0], metadata[0])
            )
        lookup.assert_not_called()

    def test_missing_listxattr_still_refuses_group_writable_file(self) -> None:
        file = self.scratch / "group-writable"
        file.write_bytes(b"")
        file.chmod(0o660)
        descriptor = os.open(file, os.O_RDONLY)
        self.addCleanup(os.close, descriptor)
        metadata = os.fstat(descriptor)
        with (
            mock.patch.object(ownership.os, "listxattr", None, create=True),
            mock.patch.object(ownership, "_owner_private_group", return_value=True),
        ):
            self.assertFalse(ownership.owner_only_writable(descriptor, metadata))
            with mock.patch.object(ownership, "_may_have_access_acl", return_value=False):
                result = ownership.owner_only_writable(descriptor, metadata)
            self._assert_disabled(self.assertFalse, result)

    def test_init_and_probe_succeed_without_listxattr(self) -> None:
        self.fake_executable("codex", 'printf ok > "$4"\n')
        repo = self._plain_repo("no-listxattr", 0o022)
        unsafe = self._plain_repo("no-listxattr-group", 0o022)
        (unsafe / ".git/info").chmod(0o770)
        info = repo / ".git/info"
        exclude = info / "exclude"
        info.chmod(0o700)
        exclude.chmod(0o600)
        with mock.patch.object(ownership.os, "listxattr", None, create=True):
            with mock.patch.object(ownership, "_owner_private_group", return_value=True):
                self._assert_init_refusal(unsafe, 0o022, EXCLUDE_REFUSAL)
                with (
                    mock.patch.object(ownership, "_may_have_access_acl", return_value=False),
                    mock.patch.object(route_config, "default_acl_risk", return_value=False),
                ):
                    self._assert_disabled(
                        self._assert_init_refusal, unsafe, 0o022, EXCLUDE_REFUSAL
                    )
            with mock.patch.object(probe, "owner_only_writable", _default_acl_first):
                self._assert_disabled(self._assert_init_success, repo, 0o022)
            self._assert_init_success(repo, 0o022)
            with self._umask(0o022):
                (repo / ".forge/tmp").mkdir()
            self._assert_probe_success(repo, 0o022)

    def _assert_other_modes_refused(self) -> None:
        for mode in (0o702, 0o757, 0o777, 0o1777, 0o666):
            metadata = types.SimpleNamespace(st_mode=mode, st_uid=1000, st_gid=1000)
            self.assertFalse(ownership.owner_only_writable(-1, metadata))

    def test_other_writable_is_refused_even_for_a_private_group(self) -> None:
        with self._group(private=True):
            self._assert_other_modes_refused()
            disabled = types.SimpleNamespace(
                S_ISDIR=stat.S_ISDIR, S_IWOTH=0, S_IWGRP=stat.S_IWGRP
            )
            with mock.patch.object(ownership, "stat", disabled):
                self._assert_disabled(self._assert_other_modes_refused)

    def test_group_writable_needs_private_group_and_no_access_acl(self) -> None:
        metadata = types.SimpleNamespace(st_mode=0o775, st_uid=1000, st_gid=1000)
        cases = ((True, False, True), (False, False, False), (True, True, False))
        for private, acl, expected in cases:
            with self.subTest(private=private, acl=acl), self._group(private, acl):
                self.assertEqual(ownership.owner_only_writable(-1, metadata), expected)

    def test_private_group_lookup_table(self) -> None:
        owner = _passwd("owner", 1000, 1000)
        alias = _passwd("alias", 1000, 1000)
        ambiguous = [owner, _passwd("shared", 1000, 2000), _passwd("shared", 1001, 2000)]
        cases = (
            ("private", [owner], [], 1000, True),
            ("duplicate owner", [owner, owner], [], 1000, True),
            ("same uid primary alias", [owner, alias], [], 1000, True),
            ("owner member", [owner], ["owner"], 1000, True),
            ("alias member", [owner, alias], ["alias"], 1000, True),
            ("foreign member", [owner, _passwd("foreign", 1001, 2000)], ["foreign"], 1000, False),
            ("unknown member", [owner], ["missing"], 1000, False),
            ("ambiguous member", ambiguous, ["shared"], 1000, False),
            ("foreign primary", [owner, _passwd("other", 1001, 1000)], [], 1000, False),
            ("non-primary gid", [owner], [], 1001, False),
        )
        for label, entries, members, gid, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(self._lookup_private(entries, members, gid), expected)
        for module, target in ((ownership.pwd, "getpwuid"), (ownership.grp, "getgrgid")):
            missing = mock.patch.object(module, target, side_effect=KeyError())
            with self.subTest(target=target), missing:
                self.assertFalse(ownership._owner_private_group(1000, 1000))
        group_entry = grp.struct_group(("owners", "x", 1000, []))
        with (
            mock.patch.object(ownership.pwd, "getpwuid", return_value=owner),
            mock.patch.object(ownership.grp, "getgrgid", return_value=group_entry),
            mock.patch.object(ownership.pwd, "getpwall", side_effect=OSError()),
        ):
            self.assertFalse(ownership._owner_private_group(1000, 1000))

        def strict_members(_uid: int, gid: int) -> bool:
            return not bool(ownership.grp.getgrgid(gid).gr_mem)

        with mock.patch.object(ownership, "_owner_private_group", side_effect=strict_members):
            result = self._lookup_private([owner], ["owner"])
            self._assert_disabled(self.assertTrue, result)
        with mock.patch.object(ownership, "_owner_private_group", side_effect=_primary_gid_only):
            result = self._lookup_private([owner, _passwd("other", 1001, 1000)], [])
            self._assert_disabled(self.assertFalse, result)

    def test_private_group_refuses_unenumerable_or_divergent_identity(self) -> None:
        owner = _passwd("owner", 1000, 1000)
        group = grp.struct_group(("owners", "x", 1000, []))
        cases = (
            ("missing owner", [], [group]),
            ("missing group", [owner], []),
            ("owner gid", [_passwd("owner", 1000, 2000)], [group]),
            (
                "group members",
                [owner],
                [grp.struct_group(("owners", "x", 1000, ["other"]))],
            ),
            (
                "duplicate group",
                [owner],
                [group, grp.struct_group(("alias", "x", 1000, ["other"]))],
            ),
        )
        for label, accounts, groups in cases:
            with self.subTest(missing=label):
                self.assertFalse(
                    self._lookup_private(accounts, [], owner=owner, groups=groups)
                )
                with mock.patch.object(
                    ownership, "_identity_is_enumerable", return_value=True
                ):
                    result = self._lookup_private(
                        accounts, [], owner=owner, groups=groups
                    )
                self._assert_disabled(self.assertFalse, result)

    def test_access_acl_probe_fails_closed(self) -> None:
        with mock.patch.object(ownership.os, "listxattr", None, create=True):
            self.assertTrue(ownership._may_have_access_acl(-1))
        cases = [
            (OSError(errno.ENOTSUP, "unsupported"), False),
            (OSError(errno.EOPNOTSUPP, "unsupported"), False),
            (OSError(errno.EACCES, "failed"), True),
            (OSError(errno.EIO, "failed"), True),
            *[([name], True) for name in ownership.ACL_XATTRS],
            (["system.posix_acl_default"], False),
            (["security.selinux", "user.note"], False),
        ]
        for result, expected in cases:
            with self.subTest(result=result):
                self.assertEqual(self._access_acl(result), expected)

    def test_info_default_acl_is_refused_and_disable_leg_detects_control(self) -> None:
        repo = self._plain_repo("default-acl", 0o022)
        info = repo / ".git/info"
        info.chmod(0o775)
        (info / "exclude").unlink()
        expected = info.stat()

        def fake_listxattr(target: object) -> list[str]:
            if not isinstance(target, int):
                return []
            try:
                actual = os.fstat(target)
            except OSError:
                return []
            return (
                ["system.posix_acl_default"]
                if os.path.samestat(actual, expected)
                else []
            )

        with (
            mock.patch.object(ownership, "_owner_private_group", return_value=True),
            mock.patch.object(ownership, "_may_have_access_acl", return_value=False),
            mock.patch.object(
                ownership.os, "listxattr", side_effect=fake_listxattr, create=True
            ),
        ):
            self._assert_init_refusal(repo, 0o022, EXCLUDE_REFUSAL)
            with mock.patch.object(
                route_config, "default_acl_risk", return_value=False
            ):
                self._assert_disabled(
                    self._assert_init_refusal, repo, 0o022, EXCLUDE_REFUSAL
                )

    def test_default_acl_outside_info_is_ignored_for_owner_only_directory(self) -> None:
        repo = self._plain_repo("local-default-acl", 0o022)
        local = repo / ".forge/local"
        local.mkdir(parents=True)
        local.chmod(0o700)
        expected = local.stat()

        def fake_listxattr(target: object) -> list[str]:
            if not isinstance(target, int):
                return []
            try:
                actual = os.fstat(target)
            except OSError:
                return []
            return (
                ["system.posix_acl_default"]
                if os.path.samestat(actual, expected)
                else []
            )

        with mock.patch.object(
            ownership.os, "listxattr", side_effect=fake_listxattr, create=True
        ):
            with mock.patch.object(probe, "owner_only_writable", _default_acl_first):
                self._assert_disabled(self._assert_init_success, repo, 0o022)
            self._assert_init_success(repo, 0o022)

    @unittest.skipUnless(hasattr(os, "setxattr"), "os.setxattr unavailable")
    def test_real_posix_access_acl_on_a_group_writable_directory_is_refused(self) -> None:
        directory = self.scratch / "acl"
        directory.mkdir()
        directory.chmod(0o775)
        undefined = 0xFFFFFFFF
        entries = ((0x01, 7, undefined), (0x02, 7, 65534), (0x04, 5, undefined),
                   (0x10, 7, undefined), (0x20, 5, undefined))
        blob = struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in entries)
        try:
            os.setxattr(directory, "system.posix_acl_access", blob)
        except OSError as exc:
            self.skipTest(f"filesystem rejected POSIX ACL xattr: {exc}")
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, descriptor)
        metadata = os.fstat(descriptor)
        private = mock.patch.object(ownership, "_owner_private_group", return_value=True)
        with private:
            self.assertFalse(ownership.owner_only_writable(descriptor, metadata))
        with private, mock.patch.object(ownership, "_may_have_access_acl", return_value=False):
            result = ownership.owner_only_writable(descriptor, metadata)
            self._assert_disabled(self.assertFalse, result)

    def _private_init_leg(self, mask: int) -> None:
        repo = self._stock_clone(f"private-{mask:o}", mask)
        info_mode = _mode(repo / ".git/info")
        exclude_mode = _mode(repo / ".git/info/exclude")
        with self._group(private=True):
            self._assert_init_success(repo, mask)
        routes = repo / ".forge/local/routes.toml"
        self.assertEqual((_mode(routes), _mode(routes.parent)), (0o600, 0o700))
        self.assertEqual((repo / ".git/info/exclude").read_bytes().count(b"/.forge/local/\n"), 1)
        self.assertEqual(_mode(repo / ".git/info/exclude"), exclude_mode)
        self.assertEqual(_mode(repo / ".git/info"), info_mode)

    def test_init_accepts_a_private_group_stock_clone_under_both_umasks(self) -> None:
        self._both_umasks(self._private_init_leg)
        legacy = self._stock_clone("private-legacy", 0o002)
        with mock.patch.object(probe, "owner_only_writable", _legacy_writable):
            self._assert_disabled(self._assert_init_success, legacy, 0o002)

    def _shared_init_leg(self, mask: int) -> None:
        tracked = self._stock_clone(f"shared-tracked-{mask:o}", mask)
        plain = self._plain_repo(f"shared-plain-{mask:o}", mask)
        with self._group(private=False):
            if mask == 0o002:
                self._assert_init_refusal(tracked, mask, LOCAL_REFUSAL)
                self._assert_init_refusal(plain, mask, EXCLUDE_REFUSAL)
            else:
                self._assert_init_success(tracked, mask)
                self._assert_init_success(plain, mask)

    def test_init_refuses_shared_group_directories_under_both_umasks(self) -> None:
        self._both_umasks(self._shared_init_leg)
        repo = self._stock_clone("shared-disabled", 0o002)
        with self._group(private=True):
            self._assert_disabled(self._assert_init_refusal, repo, 0o002, LOCAL_REFUSAL)

    def _world_writable_leg(self, mask: int) -> None:
        targets = (("forge", ".forge", 0o777, LOCAL_REFUSAL),
                   ("info", ".git/info", 0o777, EXCLUDE_REFUSAL),
                   ("exclude", ".git/info/exclude", 0o666, EXCLUDE_REFUSAL))
        for label, relative, mode, diagnostic in targets:
            repo = self._stock_clone(f"world-{label}-{mask:o}", mask)
            Path(repo, relative).chmod(mode)
            with self._group(private=True):
                self._assert_init_refusal(repo, mask, diagnostic)

    def test_init_refuses_world_writable_paths_under_both_umasks(self) -> None:
        self._both_umasks(self._world_writable_leg)
        repo = self._stock_clone("world-disabled", 0o022)
        (repo / ".forge").chmod(0o777)
        with mock.patch.object(probe, "owner_only_writable", return_value=True):
            self._assert_disabled(self._assert_init_refusal, repo, 0o022, LOCAL_REFUSAL)

    def _isolated_exclude(self, name: str, mask: int) -> Path:
        repo = self._plain_repo(name, mask)
        (repo / ".git/info").chmod(0o755)
        (repo / ".git/info/exclude").chmod(0o664)
        return repo

    def _exclude_rule_leg(self, mask: int) -> None:
        accepted = self._isolated_exclude(f"file-private-{mask:o}", mask)
        with self._group(private=True):
            self._assert_init_success(accepted, mask)
        self.assertEqual(_mode(accepted / ".git/info/exclude"), 0o664)
        shared = self._isolated_exclude(f"file-shared-{mask:o}", mask)
        with self._group(private=False):
            self._assert_init_refusal(shared, mask, EXCLUDE_REFUSAL)
        disabled = self._isolated_exclude(f"file-disabled-{mask:o}", mask)
        with self._group(private=True):
            self._assert_disabled(self._assert_init_refusal, disabled, mask, EXCLUDE_REFUSAL)
        legacy = self._isolated_exclude(f"file-legacy-{mask:o}", mask)
        with mock.patch.object(route_config, "owner_only_writable", _legacy_writable):
            self._assert_disabled(self._assert_init_success, legacy, mask)

    def test_init_exclude_file_group_rule_under_both_umasks(self) -> None:
        self.assertEqual(self._both_umasks(self._exclude_rule_leg), UMASKS)

    def _foreign_owner_leg(self, mask: int) -> None:
        real_uid = os.geteuid()
        repo = self._stock_clone(f"foreign-{mask:o}", mask)
        with self._group(private=True), mock.patch.object(
            probe.os, "geteuid", return_value=real_uid + 1
        ):
            self._assert_init_refusal(repo, mask, LOCAL_REFUSAL)

    def test_init_refuses_foreign_owned_directory_under_both_umasks(self) -> None:
        self.assertEqual(self._both_umasks(self._foreign_owner_leg), UMASKS)

    def test_routes_file_mask_is_unchanged_by_a_private_group(self) -> None:
        lookup = mock.Mock(side_effect=AssertionError("routes file must not consult NSS"))
        with mock.patch.object(ownership, "_owner_private_group", lookup):
            for mask in UMASKS:
                for mode in (0o620, 0o660, 0o602):
                    with self.subTest(umask=oct(mask), mode=oct(mode)), self._umask(mask):
                        self.write_routes(route_text(), mode=mode)
                        self.assert_route_refusal("group/other-writable")
            with mock.patch.object(
                route_config, "_validate_metadata", return_value=None
            ):
                self._assert_disabled(self.assert_route_refusal, "group/other-writable")

    def _probe_result(self, repo: Path, mask: int) -> str | None:
        spec = probe.ProbeSpec("codex", "gpt-5.6-sol", "high", ("plan",))
        with self._umask(mask):
            outcome = probe.probe_routes(repo, ROOT, [spec], environ=self.probe_environment())[0]
        return outcome.diagnostic

    def _assert_probe_success(self, repo: Path, mask: int) -> None:
        self.assertIsNone(self._probe_result(repo, mask))
        self.assertEqual(_mode(repo / ".forge/tmp/route-probe"), 0o700)
        self.assertEqual(_mode(repo / ".forge/tmp"), 0o777 & ~mask)

    def _probe_leg(self, mask: int) -> None:
        self.fake_executable("codex", 'printf ok > "$4"\n')
        repo = self._stock_clone(f"probe-{mask:o}", mask)
        with self._umask(mask):
            (repo / ".forge/tmp").mkdir()
        with self._group(private=True):
            self._assert_probe_success(repo, mask)
        if mask == 0o002:
            shared = self._stock_clone("probe-shared", mask)
            with self._umask(mask):
                (shared / ".forge/tmp").mkdir()
            with self._group(private=False):
                self.assertEqual(self._probe_result(shared, mask), SCRATCH_REFUSAL)
            with self._group(private=True):
                result = self._probe_result(shared, mask)
                self._assert_disabled(self.assertEqual, result, SCRATCH_REFUSAL)

    def test_probe_scratch_accepts_private_group_ancestors_under_both_umasks(self) -> None:
        self._both_umasks(self._probe_leg)
        legacy = self._stock_clone("probe-legacy", 0o002)
        with self._umask(0o002):
            (legacy / ".forge/tmp").mkdir()
        with mock.patch.object(probe, "owner_only_writable", _legacy_writable):
            self._assert_disabled(self._assert_probe_success, legacy, 0o002)

    def test_fixture_umask_is_pinned_to_022(self) -> None:
        current = os.umask(0o022)
        os.umask(current)
        self.assertEqual(current, 0o022)
