from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import time
from unittest import mock

from tests.test_route_config_support import (
    ROOT,
    route_config,
    route_config_git,
    route_text,
)

EXPECTED_SEED = (
    "# <common-root>/.forge/local/routes.toml   — one per clone, "
    """never committed, owner-only
schema = "forge-routes/1"

# [implementer]
# provider = "codex"          # codex | claude
# model    = "gpt-5.6-sol"
# effort   = "ultra"

# [review-cheap]
# provider = "codex"
# model    = "gpt-5.6-sol"
# effort   = "high"

# [review-final]
# provider = "claude"
# model    = "fable"
# effort   = "high"

# [plan]
# provider = "codex"
# model    = "gpt-5.6-sol"
# effort   = "high"
"""
).encode()


class RouteSecurityMixin:
    def test_owner_only_and_read_only_modes_follow_the_write_bit_mask(self) -> None:
        for mode in (0o600, 0o400, 0o644):
            with self.subTest(mode=oct(mode)):
                self.write_routes(route_text(), mode=mode)
                self.assertTrue(self.load().local_present)
        for mode in (0o620, 0o602, 0o666):
            with self.subTest(mode=oct(mode)):
                self.write_routes(route_text(), mode=mode)
                self.assert_route_refusal("group/other-writable")

    def test_symlink_directory_fifo_and_foreign_owner_are_refused(self) -> None:
        path = self.write_routes(route_text())
        path.unlink()
        path.symlink_to(path.with_name("missing-target"))
        self.assert_route_refusal("symlink")
        path.unlink()
        path.mkdir()
        self.assert_route_refusal("nonregular")
        path.rmdir()
        os.mkfifo(path, 0o600)
        self.assert_route_refusal("nonregular")
        path.unlink()
        self.write_routes(route_text())
        with mock.patch.object(route_config.os, "geteuid", return_value=os.geteuid() + 1):
            self.assert_route_refusal("foreign owner")

    def test_live_routes_symlink_refusal_depends_on_nofollow(self) -> None:
        self.set_ignored(True)
        outside = self.scratch / "outside-routes.toml"
        outside.write_bytes(route_text())
        outside.chmod(0o600)
        path = self.repo / ".forge/local/routes.toml"
        path.parent.mkdir(parents=True)
        path.symlink_to(outside)

        def symlink_assertion() -> None:
            self.assert_route_refusal("symlink")

        symlink_assertion()
        with mock.patch.object(route_config.os, "O_NOFOLLOW", 0):
            with self.assertRaises(AssertionError):
                symlink_assertion()

    def test_size_limit_accepts_16_kib_and_refuses_one_byte_more(self) -> None:
        self.assertEqual(route_config.MAX_ROUTES_BYTES, 16 * 1024)
        prefix = b'schema = "forge-routes/1"\n#'
        exact = prefix + b"x" * (route_config.MAX_ROUTES_BYTES - len(prefix))
        self.write_routes(exact)
        self.assertTrue(self.load().local_present)
        self.write_routes(exact + b"x")
        self.assert_route_refusal("oversized")

    def test_tracked_unignored_and_unreadable_files_are_refused(self) -> None:
        path = self.write_routes(route_text())
        self.git(self.repo, "add", "-f", ".forge/local/routes.toml")
        self.assert_route_refusal("tracked")
        self.git(self.repo, "reset", "-q", "HEAD", "--", ".forge/local/routes.toml")
        self.write_routes(route_text(), ignored=False)
        self.assert_route_refusal("unignored")
        self.write_routes(route_text())
        denied = PermissionError(errno.EACCES, "denied", str(path))
        real_open = os.open

        def selective_open(file: object, *args: object, **kwargs: object) -> int:
            if os.fspath(file) == os.fspath(path):
                raise denied
            return real_open(file, *args, **kwargs)  # type: ignore[arg-type]

        with mock.patch.object(route_config.os, "open", side_effect=selective_open):
            self.assert_route_refusal("unreadable")

    def test_linked_worktree_root_copy_is_misplaced(self) -> None:
        linked = self.scratch / "linked"
        self.git(self.repo, "worktree", "add", "-q", "--detach", str(linked), "HEAD")
        expected = self.repo / ".forge/local/routes.toml"
        self.assertEqual(route_config.routes_path(self.repo), expected)
        self.assertEqual(route_config.routes_path(linked), expected)
        misplaced = linked / ".forge/local/routes.toml"
        misplaced.parent.mkdir(parents=True)
        misplaced.write_bytes(route_text())
        misplaced.chmod(0o600)
        self.assert_route_refusal("misplaced", linked)
        subdirectory = linked / "sub"
        subdirectory.mkdir()
        status, stdout, stderr = self.invoke(
            "check", "--repo", str(subdirectory)
        )
        self.assertEqual((status, stdout), (1, ""))
        self.assertEqual(stderr, "forge: routes file refused — misplaced\n")

    def test_git_calls_ignore_ambient_git_dir(self) -> None:
        head = self.commit_paths(
            {
                ".codex/agents/implementer.toml": (
                    'model = "target-model"\nmodel_reasoning_effort = "high"\n'
                )
            },
            "target route",
        )
        expected = route_config.resolve(self.repo, "implementer", head).as_dict()
        ambient = self.make_repo("ambient")
        with mock.patch.dict(os.environ, {"GIT_DIR": str(ambient / ".git")}):
            status, stdout, stderr = self.invoke(
                "resolve",
                "--repo",
                str(self.repo),
                "--role",
                "implementer",
                "--head",
                head,
            )
        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), expected)

    def test_git_environment_scrubs_every_repository_selector(self) -> None:
        expected = {
            "GIT_DIR",
            "GIT_COMMON_DIR",
            "GIT_INDEX_FILE",
            "GIT_WORK_TREE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_CEILING_DIRECTORIES",
            "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        }
        self.assertEqual(route_config_git.SCRUBBED_GIT_ENVIRONMENT, expected)
        injected = {name: f"sentinel-{name}" for name in expected}
        injected["FORGE_KEEP_ME"] = "preserved"
        with mock.patch.dict(os.environ, injected):
            environment = route_config_git._git_environment()
        self.assertTrue(expected.isdisjoint(environment))
        self.assertEqual(environment["FORGE_KEEP_ME"], "preserved")

    def test_git_timeouts_are_bounded_and_contextual(self) -> None:
        self.assertEqual(route_config.GIT_TIMEOUT_SECONDS, 30)
        head = self.head()
        survivor = self.scratch / "git-descendant-survived"
        fake_git = self.fake_executable(
            "git",
            "trap '' TERM\n"
            "(\n"
            "  trap '' TERM\n"
            "  sleep 0.3\n"
            f"  printf survived > {self.shell_path(survivor)}\n"
            ") &\n"
            "wait\n",
        )
        environment = {"PATH": f"{fake_git.parent}:/usr/bin:/bin"}
        started = time.monotonic()
        with (
            mock.patch.dict(os.environ, environment),
            mock.patch.object(route_config, "GIT_TIMEOUT_SECONDS", 0.02),
        ):
            status, stdout, stderr = self.invoke("check", "--repo", str(self.repo))
            self.assertEqual((status, stdout), (1, ""))
            self.assertEqual(stderr, "forge: routes file refused — git timed out\n")
            expected = "^forge: route resolution refused — git timed out$"
            with self.assertRaisesRegex(route_config.RouteRefusal, expected):
                route_config._head_oid(self.repo, head)
            with self.assertRaisesRegex(route_config.RouteRefusal, expected):
                route_config._git_blob(self.repo, head, "README.md")
        self.assertLess(time.monotonic() - started, 1.0)
        time.sleep(0.4)
        self.assertFalse(survivor.exists())

    def test_missing_file_is_default_resolution_and_check_reports_both_states(self) -> None:
        resolution = self.load()
        self.assertFalse(resolution.local_present)
        self.assertTrue(all(route.route_source == "plugin-default" for route in resolution.routes))
        status, stdout, stderr = self.invoke("check", "--repo", str(self.repo))
        self.assertEqual((status, stdout, stderr), (0, "no routes file\n", ""))
        self.write_routes(route_text())
        status, stdout, stderr = self.invoke("check", "--repo", str(self.repo))
        self.assertEqual((status, stdout, stderr), (0, "routes file ok\n", ""))

    def test_init_writes_exact_seed_modes_and_only_one_exclude_line(self) -> None:
        exclude = self.exclude_path()
        exclude.write_bytes(b"keep-one\nkeep-two")
        destination = route_config.init_routes(self.repo)
        seed = (ROOT / "system/local/routes.toml.seed").read_bytes()
        self.assertEqual(seed, EXPECTED_SEED)
        self.assertEqual(len(seed), 473)
        self.assertEqual(
            hashlib.sha256(seed).hexdigest(),
            "4d79d84719762a82302ca46f1d0230d262177ddeaad24f027d9a3127cef54a12",
        )
        active = [line for line in seed.splitlines() if line and not line.startswith(b"#")]
        self.assertEqual(active, [b'schema = "forge-routes/1"'])
        self.assertEqual(destination.read_bytes(), EXPECTED_SEED)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(destination.parent.stat().st_mode), 0o700)
        expected_exclude = b"keep-one\nkeep-two\n/.forge/local/\n"
        self.assertEqual(exclude.read_bytes(), expected_exclude)
        original = destination.read_bytes()
        for _attempt in range(2):
            with self.assertRaisesRegex(
                route_config.RouteRefusal,
                "^forge: route init refused — routes file already exists$",
            ):
                route_config.init_routes(self.repo)
        self.assertEqual(destination.read_bytes(), original)
        self.assertEqual(exclude.read_bytes().count(b"/.forge/local/\n"), 1)

    def test_init_repairs_exclude_before_existing_route_refusal(self) -> None:
        destination = self.repo / ".forge/local/routes.toml"
        destination.parent.mkdir(parents=True)
        sentinel = b'hand-made = "preserve exactly"\n'
        destination.write_bytes(sentinel)
        destination.chmod(0o600)
        exclude = self.exclude_path()
        exclude.write_bytes(b"keep-this\n")

        expected_refusal = "forge: route init refused — routes file already exists\n"
        status, stdout, stderr = self.invoke("init", "--repo", str(self.repo))
        self.assertEqual((status, stdout, stderr), (1, "", expected_refusal))
        self.assertEqual(destination.read_bytes(), sentinel)
        self.assertEqual(exclude.read_bytes(), b"keep-this\n/.forge/local/\n")

        route_identity = destination.stat()
        exclude_identity = exclude.stat()
        route_bytes = destination.read_bytes()
        exclude_bytes = exclude.read_bytes()
        status, stdout, stderr = self.invoke("init", "--repo", str(self.repo))
        self.assertEqual((status, stdout, stderr), (1, "", expected_refusal))
        self.assertEqual(destination.read_bytes(), route_bytes)
        self.assertEqual(exclude.read_bytes(), exclude_bytes)
        self.assertTrue(os.path.samestat(route_identity, destination.stat()))
        self.assertTrue(os.path.samestat(exclude_identity, exclude.stat()))

    def test_init_refuses_live_local_ancestor_symlink_without_escape(self) -> None:
        outside = self.scratch / "outside-local"
        outside.mkdir()
        forge = self.repo / ".forge"
        forge.mkdir()
        (forge / "local").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(
            route_config.RouteRefusal,
            "^forge: route init refused — unsafe local directory$",
        ):
            route_config.init_routes(self.repo)
        self.assertFalse((outside / "routes.toml").exists())

    def test_init_rolls_back_route_when_exclude_update_fails(self) -> None:
        destination = self.repo / ".forge/local/routes.toml"
        with mock.patch.object(
            route_config,
            "_update_exclude",
            side_effect=OSError(errno.EIO, "injected exclude failure"),
        ):
            with self.assertRaises(OSError):
                route_config.init_routes(self.repo)
        self.assertFalse(os.path.lexists(destination))
        self.assertEqual(route_config.init_routes(self.repo), destination)

    def test_partial_atomic_exclude_write_preserves_original_and_allows_retry(self) -> None:
        exclude = self.exclude_path()
        original = b"preserve-this-byte-for-byte\n"
        exclude.write_bytes(original)
        destination = self.repo / ".forge/local/routes.toml"
        real_write_all = route_config._write_all
        calls = 0

        def fail_second_write(descriptor: int, data: bytes) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                os.write(descriptor, data[:3])
                raise OSError(errno.EIO, "injected partial write")
            real_write_all(descriptor, data)

        with mock.patch.object(route_config, "_write_all", side_effect=fail_second_write):
            with self.assertRaises(OSError):
                route_config.init_routes(self.repo)
        self.assertEqual(exclude.read_bytes(), original)
        self.assertFalse(os.path.lexists(destination))
        self.assertEqual(route_config.init_routes(self.repo), destination)
        self.assertEqual(exclude.read_bytes(), original + route_config.EXCLUDE_LINE + b"\n")

    def test_init_refuses_info_exclude_symlink_without_modifying_target(self) -> None:
        exclude = self.exclude_path()
        outside = self.scratch / "outside-exclude"
        original = b"outside must remain unchanged\n"
        outside.write_bytes(original)
        exclude.unlink()
        exclude.symlink_to(outside)
        with self.assertRaisesRegex(
            route_config.RouteRefusal,
            "^forge: route init refused — unsafe info/exclude$",
        ):
            route_config.init_routes(self.repo)
        self.assertEqual(outside.read_bytes(), original)
        self.assertFalse(os.path.lexists(self.repo / ".forge/local/routes.toml"))

    def test_init_dedupe_is_opt_in_and_preserves_every_other_line(self) -> None:
        duplicate = b"alpha\n/.forge/local/\nbeta\n/.forge/local/\ngamma\n"
        self.exclude_path().write_bytes(duplicate)
        route_config.init_routes(self.repo)
        self.assertEqual(self.exclude_path().read_bytes(), duplicate)
        other = self.make_repo("dedupe")
        other_exclude = self.exclude_path(other)
        other_exclude.write_bytes(duplicate)
        route_config.init_routes(other, dedupe=True)
        self.assertEqual(
            other_exclude.read_bytes(),
            b"alpha\n/.forge/local/\nbeta\ngamma\n",
        )

    def test_init_cli_refuses_without_overwrite_and_usage_is_exit_two(self) -> None:
        status, stdout, stderr = self.invoke("init", "--repo", str(self.repo))
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn(str(self.repo / ".forge/local/routes.toml"), stdout)
        before = (self.repo / ".forge/local/routes.toml").read_bytes()
        status, stdout, stderr = self.invoke("init", "--repo", str(self.repo))
        self.assertEqual((status, stdout), (1, ""))
        self.assertEqual(stderr, "forge: route init refused — routes file already exists\n")
        self.assertEqual((self.repo / ".forge/local/routes.toml").read_bytes(), before)
        status, _stdout, stderr = self.invoke("check", "--repo", "relative")
        self.assertEqual(status, 2)
        self.assertIn("must be an absolute path", stderr)

    def test_ownership_untracked_and_ignore_controls_are_load_bearing(self) -> None:
        self.write_routes(route_text(), mode=0o620)

        def ownership_assertion() -> None:
            self.assert_route_refusal("group/other-writable")

        ownership_assertion()
        with mock.patch.object(route_config, "_validate_metadata", return_value=None):
            with self.assertRaises(AssertionError):
                ownership_assertion()
        self.write_routes(route_text())
        self.git(self.repo, "add", "-f", ".forge/local/routes.toml")

        def tracked_assertion() -> None:
            self.assert_route_refusal("tracked")

        tracked_assertion()
        with mock.patch.object(route_config, "_is_tracked", return_value=False):
            with self.assertRaises(AssertionError):
                tracked_assertion()
        self.git(self.repo, "reset", "-q", "HEAD", "--", ".forge/local/routes.toml")
        self.write_routes(route_text(), ignored=False)

        def ignored_assertion() -> None:
            self.assert_route_refusal("unignored")

        ignored_assertion()
        with mock.patch.object(route_config, "_is_ignored", return_value=True):
            with self.assertRaises(AssertionError):
                ignored_assertion()
