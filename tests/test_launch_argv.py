"""Exact argv and committed-prompt tests for typed launches."""

from __future__ import annotations

import errno
import os
import shutil
import subprocess
import threading
import unittest
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests._cli_loader import patch_engine
from tests._launch_support import (
    ENGINE,
    LAUNCH_LANE,
    ROOT,
    STRIPPED_PATH,
    LaunchLaneSupport,
    digest,
)


def _release_fifo_reader(path: Path, finished: threading.Event) -> None:
    for _attempt in range(200):
        if finished.is_set():
            return
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as exc:
            if exc.errno != errno.ENXIO:
                raise
            finished.wait(0.01)
        else:
            os.close(descriptor)
            return
    raise AssertionError("FIFO reader could not be released")


def _probe_fifo_read(
    path: Path,
    flags: Callable[[], int],
) -> tuple[bool, Exception | None]:
    started = threading.Event()
    finished = threading.Event()
    outcomes: list[Exception | None] = []

    def observed_flags() -> int:
        started.set()
        return flags()

    def read_fifo() -> None:
        try:
            LAUNCH_LANE.read_brief(path)
        except Exception as exc:  # noqa: BLE001 - reported to the test thread.
            outcomes.append(exc)
        else:
            outcomes.append(None)
        finally:
            finished.set()

    with mock.patch.object(
        LAUNCH_LANE,
        "_brief_open_flags",
        side_effect=observed_flags,
    ):
        reader = threading.Thread(target=read_fifo, daemon=True)
        reader.start()
        if not started.wait(1):
            raise AssertionError("FIFO reader did not reach open")
        blocked = not finished.wait(0.5)
        if blocked:
            _release_fifo_reader(path, finished)
        if not finished.wait(1):
            raise AssertionError("FIFO reader did not finish")
    reader.join(timeout=1)
    if reader.is_alive() or len(outcomes) != 1:
        raise AssertionError("FIFO reader thread did not terminate cleanly")
    return blocked, outcomes[0]


class LaunchArgvTests(LaunchLaneSupport, unittest.TestCase):
    def test_exact_provider_argv_for_all_four_launch_cells(self) -> None:
        staging = self.scratch / "handoff.staging"
        codex = str(self.bin_dir / "codex")
        claude = str(self.bin_dir / "claude")
        common_codex = (
            codex,
            "exec",
            "--json",
            "--output-last-message",
            str(staging),
        )
        cases = {
            ("codex", "implementer"): common_codex
            + (
                "-s", "workspace-write", "-c", "approval_policy=never", "-c",
                "model=gpt-fixture", "-c", "model_reasoning_effort=opaque",
                "-C", str(self.linked_worktree), "-",
            ),
            ("codex", "plan"): common_codex
            + (
                "-s", "read-only", "-c", "approval_policy=never", "-c",
                "model=gpt-fixture", "-c", "model_reasoning_effort=opaque",
                "-C", str(self.linked_worktree), "-",
            ),
            ("claude", "implementer"): (
                claude, "-p", "--safe-mode", "--strict-mcp-config",
                "--output-format", "stream-json", "--verbose", "--model",
                "gpt-fixture", "--effort", "opaque", "--append-system-prompt-file",
                str(ROOT / "system/claude/prompts/implementer.md"), "--tools",
                "Read,Write,Edit,Bash,Grep,Glob", "--permission-mode", "acceptEdits",
                "--allowedTools", "Bash", "--permission-prompts", "none",
                "--no-session-persistence",
            ),
            ("claude", "plan"): (
                claude, "-p", "--safe-mode", "--strict-mcp-config",
                "--output-format", "stream-json", "--verbose", "--model",
                "gpt-fixture", "--effort", "opaque", "--system-prompt-file",
                str(ROOT / "system/claude/prompts/plan.md"), "--tools",
                "Read,Grep,Glob", "--permission-prompts", "none",
                "--no-session-persistence",
            ),
        }
        for (provider, role), expected in cases.items():
            with self.subTest(provider=provider, role=role):
                actual = LAUNCH_LANE.launch_argv(
                    provider,
                    role,
                    "gpt-fixture",
                    "opaque",
                    worktree=self.linked_worktree,
                    plugin_root=ROOT,
                    staging=staging,
                )
                self.assertEqual(actual, expected)

    def test_every_cell_uses_selected_cwd_and_exact_saved_stdin(self) -> None:
        for index, (provider, role) in enumerate(
            (
                ("codex", "implementer"),
                ("codex", "plan"),
                ("claude", "implementer"),
                ("claude", "plan"),
            ),
            start=1,
        ):
            with self.subTest(provider=provider, role=role):
                self.configure_route(role, provider)
                run_id = f"run-20260928-launch-cell-{index}"
                engine = self.ready_engine(run_id)
                expected = LAUNCH_LANE.prepare_prompt(
                    engine.ctx,
                    LAUNCH_LANE.PromptRequest(
                        role, provider, self.linked_worktree, self.head, self.brief
                    ),
                ).prompt
                calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

                def capture(
                    launcher_argv: tuple[str, ...],
                    *,
                    _calls: list[tuple[tuple[str, ...], dict[str, object]]] = calls,
                    _index: int = index,
                    **kwargs: object,
                ) -> SimpleNamespace:
                    _calls.append((tuple(launcher_argv), dict(kwargs)))
                    return SimpleNamespace(pid=420_000 + _index)

                with patch_engine("spawn_wrapper", side_effect=capture):
                    outcome = self.launch_direct(
                        role=role, engine=engine, worktree=self.linked_worktree
                    )
                self.assertTrue(outcome.ok)
                self.assertEqual(calls[0][1]["cwd"], self.linked_worktree)
                records = self.execution_records(run_id)
                directory = (
                    self.run_dir(self.repo, run_id)
                    / str(records[0]["agent"])
                    / str(records[0]["execution"])
                )
                self.assertEqual((directory / "prompt.md").read_bytes(), expected)

    def test_prompt_uses_committed_context_and_ignores_untracked_gotchas(self) -> None:
        committed = subprocess.run(
            ["git", "-C", str(self.linked_worktree), "show", f"{self.head}:forge-project.md"],
            check=True,
            capture_output=True,
        ).stdout
        begin = b"<!-- FORGE:REGION agent-project-context BEGIN -->\n"
        end = b"<!-- FORGE:REGION agent-project-context END -->"
        context = committed.split(begin, 1)[1].split(end, 1)[0]
        project = self.linked_worktree / "forge-project.md"
        project.write_bytes(committed.replace(context, b"dirty context\n", 1))
        untracked = self.linked_worktree / ".forge/history/gotchas.md"
        untracked.parent.mkdir(parents=True, exist_ok=True)
        untracked.write_text("dirty untracked gotcha\n", encoding="utf-8")
        engine = self.ready_engine(open_task=False)
        for provider, role in (("codex", "plan"), ("claude", "plan")):
            with self.subTest(provider=provider):
                body_path = ROOT / f"system/{provider}/prompts/{role}.md"
                body = body_path.read_bytes()
                material = LAUNCH_LANE.prepare_prompt(
                    engine.ctx,
                    LAUNCH_LANE.PromptRequest(
                        role, provider, self.linked_worktree, self.head, self.brief
                    ),
                )
                prefix = body + b"\n" if provider == "codex" else b"\n"
                self.assertEqual(
                    material.prompt,
                    prefix
                    + b"--- committed agent-project-context ---\n"
                    + context
                    + b"\n--- task assignment ---\n"
                    + self.brief.read_bytes(),
                )
                self.assertEqual(material.role_body_path, body_path)
                self.assertEqual(material.role_body_sha256, digest(body))

    def test_prompt_ignores_committed_and_working_tree_gotchas(self) -> None:
        gotchas = self.repo / ".forge/history/gotchas.md"
        gotchas.parent.mkdir(parents=True, exist_ok=True)
        gotchas.write_text("committed gotcha\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.repo), "add", ".forge/history/gotchas.md"],
            check=True,
        )
        subprocess.run(
            [
                "git", "-C", str(self.repo), "-c", "user.name=Forge Tests",
                "-c", "user.email=forge-tests@example.invalid", "commit", "--quiet",
                "-m", "fixture gotchas",
            ],
            check=True,
        )
        self.head = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", str(self.linked_worktree), "merge", "--ff-only", self.head],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        linked_gotchas = self.linked_worktree / ".forge/history/gotchas.md"
        linked_gotchas.write_text("dirty gotcha\n", encoding="utf-8")
        engine = self.ready_engine(open_task=False)
        for provider in ("codex", "claude"):
            material = LAUNCH_LANE.prepare_prompt(
                engine.ctx,
                LAUNCH_LANE.PromptRequest(
                    "implementer", provider, self.linked_worktree, self.head, self.brief
                ),
            )
            self.assertNotIn(b"committed gotcha\n", material.prompt)
            self.assertNotIn(b"dirty gotcha", material.prompt)

    def test_brief_validation_refuses_every_unsafe_shape(self) -> None:
        diagnostic = LAUNCH_LANE.BRIEF_REFUSAL_MESSAGE
        invalid: list[Path] = []
        missing = self.scratch / "missing.md"
        invalid.append(missing)
        directory = self.scratch / "brief-dir"
        directory.mkdir()
        invalid.append(directory)
        nul = self.scratch / "brief-nul"
        nul.write_bytes(b"bad\0brief")
        invalid.append(nul)
        non_utf8 = self.scratch / "brief-non-utf8"
        non_utf8.write_bytes(b"\xff")
        invalid.append(non_utf8)
        oversized = self.scratch / "brief-oversized"
        oversized.write_bytes(b"x" * (LAUNCH_LANE.BRIEF_LIMIT_BYTES + 1))
        invalid.append(oversized)
        for path in invalid:
            with self.subTest(path=path.name), self.assertRaises(ENGINE.Refusal) as caught:
                LAUNCH_LANE.read_brief(path)
            self.assertEqual(caught.exception.message, diagnostic)
        self.assertEqual(LAUNCH_LANE.read_brief(self.brief), self.brief.read_bytes())

    def test_brief_owner_and_group_write_controls_are_load_bearing(self) -> None:
        def assert_refused(
            path: Path,
            diagnostic: str = LAUNCH_LANE.BRIEF_REFUSAL_MESSAGE,
        ) -> None:
            with self.assertRaises(ENGINE.Refusal) as caught:
                LAUNCH_LANE.read_brief(path)
            self.assertEqual(caught.exception.message, diagnostic)

        def assert_accepted(path: Path) -> None:
            try:
                actual = LAUNCH_LANE.read_brief(path)
            except ENGINE.Refusal as exc:
                raise AssertionError("safe brief was refused") from exc
            self.assertEqual(actual, path.read_bytes())

        private_group = self.scratch / "brief-private-group.md"
        private_group.write_text("private group\n", encoding="utf-8")
        private_group.chmod(0o620)
        with mock.patch.object(
            LAUNCH_LANE, "owner_only_writable", return_value=True
        ):
            assert_accepted(private_group)
        with (
            mock.patch.object(
                LAUNCH_LANE, "owner_only_writable", return_value=False
            ),
            self.assertRaises(AssertionError),
        ):
            assert_accepted(private_group)

        shared_group = self.scratch / "brief-shared-group.md"
        shared_group.write_text("shared group\n", encoding="utf-8")
        shared_group.chmod(0o660)
        with mock.patch.object(
            LAUNCH_LANE, "owner_only_writable", return_value=False
        ):
            assert_refused(shared_group)
        with (
            mock.patch.object(
                LAUNCH_LANE, "owner_only_writable", return_value=True
            ),
            self.assertRaises(AssertionError),
        ):
            assert_refused(shared_group)

        world_writable = self.scratch / "brief-world-writable.md"
        world_writable.write_text("unsafe mode\n", encoding="utf-8")
        world_writable.chmod(0o602)
        assert_refused(world_writable)
        with (
            mock.patch.object(
                LAUNCH_LANE, "_brief_metadata_is_safe", return_value=True
            ),
            self.assertRaises(AssertionError),
        ):
            assert_refused(world_writable)

        with mock.patch.object(
            LAUNCH_LANE.os, "geteuid", return_value=os.geteuid() + 1
        ):
            assert_refused(self.brief)
            with (
                mock.patch.object(
                    LAUNCH_LANE, "_brief_metadata_is_safe", return_value=True
                ),
                self.assertRaises(AssertionError),
            ):
                assert_refused(self.brief)

    def test_brief_canonical_path_and_no_follow_controls_are_load_bearing(self) -> None:
        def assert_refused(
            path: Path,
            diagnostic: str = LAUNCH_LANE.BRIEF_REFUSAL_MESSAGE,
        ) -> None:
            with self.assertRaises(ENGINE.Refusal) as caught:
                LAUNCH_LANE.read_brief(path)
            self.assertEqual(caught.exception.message, diagnostic)

        leaf_link = self.scratch / "brief-leaf-link.md"
        leaf_link.symlink_to(self.brief)
        real_parent = self.scratch / "real-brief-parent"
        real_parent.mkdir()
        parent_brief = real_parent / "brief.md"
        parent_brief.write_text("safe bytes\n", encoding="utf-8")
        parent_brief.chmod(0o600)
        linked_parent = self.scratch / "linked-brief-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        loop_a = self.scratch / "brief-loop-a"
        loop_b = self.scratch / "brief-loop-b"
        loop_a.symlink_to(loop_b.name)
        loop_b.symlink_to(loop_a.name)
        original_flags = LAUNCH_LANE._brief_open_flags

        for path in (leaf_link, linked_parent / "brief.md", loop_a):
            with self.subTest(path=path):
                assert_refused(path, LAUNCH_LANE.BRIEF_PATH_REFUSAL_MESSAGE)

        with mock.patch.object(
            LAUNCH_LANE.Path,
            "resolve",
            side_effect=RuntimeError("symlink loop"),
        ):
            assert_refused(loop_a, LAUNCH_LANE.BRIEF_PATH_REFUSAL_MESSAGE)

        with (
            mock.patch.object(
                LAUNCH_LANE, "_brief_path_is_canonical", return_value=True
            ),
            self.assertRaises(AssertionError),
        ):
            assert_refused(
                linked_parent / "brief.md",
                LAUNCH_LANE.BRIEF_PATH_REFUSAL_MESSAGE,
            )

        def flags_without_no_follow() -> int:
            return original_flags() & ~os.O_NOFOLLOW

        with mock.patch.object(
            LAUNCH_LANE, "_brief_path_is_canonical", return_value=True
        ):
            assert_refused(leaf_link)
            with (
                mock.patch.object(
                    LAUNCH_LANE,
                    "_brief_open_flags",
                    side_effect=flags_without_no_follow,
                ),
                self.assertRaises(AssertionError),
            ):
                assert_refused(leaf_link)

    def test_brief_under_traverse_only_ancestor_is_readable(self) -> None:
        directory = self.scratch / "traverse-only"
        directory.mkdir()
        brief = directory / "brief.md"
        brief.write_text("traverse only\n", encoding="utf-8")
        brief.chmod(0o600)
        directory.chmod(0o311)
        original = LAUNCH_LANE._read_owner_brief

        def assert_readable() -> None:
            try:
                actual = LAUNCH_LANE.read_brief(brief)
            except ENGINE.Refusal as exc:
                raise AssertionError("traverse-only ancestor was refused") from exc
            self.assertEqual(actual, brief.read_bytes())

        def requires_parent_read(path: Path) -> bytes:
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            os.close(descriptor)
            return original(path)

        try:
            assert_readable()
            with (
                mock.patch.object(
                    LAUNCH_LANE,
                    "_read_owner_brief",
                    side_effect=requires_parent_read,
                ),
                self.assertRaises(AssertionError),
            ):
                assert_readable()
        finally:
            directory.chmod(0o700)

    def test_brief_parent_swap_after_canonical_check_is_refused(self) -> None:
        original_check = LAUNCH_LANE._brief_path_is_canonical

        def prepare(
            label: str,
        ) -> tuple[Path, bytes, Callable[[Path], bool]]:
            checked_parent = self.scratch / f"{label}-checked-parent"
            redirected_parent = self.scratch / f"{label}-redirected-parent"
            parked_parent = self.scratch / f"{label}-parked-parent"
            checked_parent.mkdir()
            redirected_parent.mkdir()
            checked_brief = checked_parent / "brief.md"
            redirected_brief = redirected_parent / "brief.md"
            checked_brief.write_bytes(b"checked brief\n")
            redirected = b"redirected same-owner brief\n"
            redirected_brief.write_bytes(redirected)
            checked_brief.chmod(0o600)
            redirected_brief.chmod(0o600)

            def swap_after_check(path: Path) -> bool:
                canonical = original_check(path)
                self.assertTrue(canonical)
                checked_parent.rename(parked_parent)
                checked_parent.symlink_to(redirected_parent, target_is_directory=True)
                return canonical

            return checked_brief, redirected, swap_after_check

        checked_brief, _redirected, swap_after_check = prepare("enforced")
        with (
            mock.patch.object(
                LAUNCH_LANE,
                "_brief_path_is_canonical",
                side_effect=swap_after_check,
            ),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            LAUNCH_LANE.read_brief(checked_brief)
        self.assertEqual(
            caught.exception.message,
            LAUNCH_LANE.BRIEF_PATH_BINDING_REFUSAL_MESSAGE,
        )

        checked_brief, redirected, swap_after_check = prepare("disabled")
        with (
            mock.patch.object(
                LAUNCH_LANE,
                "_brief_path_is_canonical",
                side_effect=swap_after_check,
            ),
            mock.patch.object(
                LAUNCH_LANE,
                "_brief_descriptor_matches_path",
                return_value=True,
            ),
        ):
            self.assertEqual(LAUNCH_LANE.read_brief(checked_brief), redirected)

        with mock.patch.object(LAUNCH_LANE.sys, "platform", "unsupported"):
            with self.assertRaises(ENGINE.Refusal) as caught:
                LAUNCH_LANE.read_brief(self.brief)
        self.assertEqual(
            caught.exception.message,
            LAUNCH_LANE.BRIEF_PATH_BINDING_REFUSAL_MESSAGE,
        )

    def test_brief_descriptor_path_uses_macos_getpath_buffer(self) -> None:
        descriptor = os.open(self.brief, os.O_RDONLY)
        encoded = os.fsencode(self.brief)
        returned = encoded + b"\0" * (1024 - len(encoded))
        try:
            with (
                mock.patch.object(LAUNCH_LANE.sys, "platform", "darwin"),
                mock.patch.object(
                    LAUNCH_LANE.fcntl,
                    "F_GETPATH",
                    50,
                    create=True,
                ),
                mock.patch.object(
                    LAUNCH_LANE.fcntl,
                    "fcntl",
                    return_value=returned,
                ) as get_path,
            ):
                self.assertTrue(
                    LAUNCH_LANE._brief_descriptor_matches_path(
                        descriptor,
                        self.brief,
                    )
                )
            get_path.assert_called_once_with(descriptor, 50, b"\0" * 1024)
        finally:
            os.close(descriptor)

    def test_fifo_brief_open_is_nonblocking_and_control_is_load_bearing(self) -> None:
        fifo = self.scratch / "brief.fifo"
        os.mkfifo(fifo, 0o600)
        original_flags = LAUNCH_LANE._brief_open_flags

        def flags_without_nonblock() -> int:
            return original_flags() & ~os.O_NONBLOCK

        blocked, outcome = _probe_fifo_read(fifo, original_flags)
        self.assertFalse(blocked)
        self.assertIsInstance(outcome, ENGINE.Refusal)
        self.assertEqual(
            getattr(outcome, "message", None),
            LAUNCH_LANE.BRIEF_REFUSAL_MESSAGE,
        )
        blocked, outcome = _probe_fifo_read(fifo, flags_without_nonblock)
        self.assertTrue(blocked)
        self.assertIsInstance(outcome, ENGINE.Refusal)
        self.assertEqual(
            getattr(outcome, "message", None),
            LAUNCH_LANE.BRIEF_REFUSAL_MESSAGE,
        )

    def test_launch_argv_is_hermetic_under_stripped_path(self) -> None:
        self.assertEqual(os.environ["PATH"], STRIPPED_PATH)
        self.assertIsNone(shutil.which("codex", path=STRIPPED_PATH))
        self.assertIsNone(shutil.which("claude", path=STRIPPED_PATH))
        self.assertTrue(Path(LAUNCH_LANE.CODEX_EXECUTABLE).is_absolute())
        self.assertTrue(Path(LAUNCH_LANE.CLAUDE_EXECUTABLE).is_absolute())
        self.assertEqual(
            LAUNCH_LANE.launch_argv(
                "codex", "plan", "model", "opaque", worktree=self.linked_worktree,
                plugin_root=ROOT, staging=self.scratch / "handoff.staging",
            )[0],
            str(self.bin_dir / "codex"),
        )


if __name__ == "__main__":
    unittest.main()
