"""Focused process-group regression tests for ``forge_cli.runtime``."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from typing import Callable
import unittest
from unittest import mock

from tests._cli_loader import package_module


RUNTIME = package_module("runtime")


_DESCENDANT_PROGRAM = """
import pathlib
import signal
import sys
import time

ready_path, release_path, output_path = sys.argv[1:]
signal.signal(signal.SIGTERM, signal.SIG_IGN)
pathlib.Path(ready_path).write_text("ready", encoding="ascii")
while not pathlib.Path(release_path).exists():
    time.sleep(0.002)
pathlib.Path(output_path).write_text("survived", encoding="ascii")
time.sleep(30)
"""


_LEADER_PROGRAM = """
import os
import pathlib
import signal
import subprocess
import sys
import time

child_program, ready_path, release_path, output_path = sys.argv[1:]
child_ready_path = ready_path + ".child"
signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen(
    [sys.executable, "-c", child_program, child_ready_path, release_path, output_path],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
deadline = time.monotonic() + 2.0
while not pathlib.Path(child_ready_path).exists():
    if child.poll() is not None or time.monotonic() >= deadline:
        raise SystemExit(2)
    time.sleep(0.002)
signal.signal(signal.SIGTERM, signal.SIG_DFL)
pathlib.Path(ready_path).write_text(
    f"{os.getpid()} {os.getpgrp()} {child.pid}",
    encoding="ascii",
)
while True:
    time.sleep(30)
"""


class RuntimeProcessGroupTests(unittest.TestCase):
    @staticmethod
    def _wait_until(predicate: Callable[[], bool], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            if predicate():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.005, remaining))

    @staticmethod
    def _process_group_is_gone(process_group: int) -> bool:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return True
        except OSError:
            return False
        return False

    def _read_ready_record(
        self,
        process: subprocess.Popen[bytes],
        ready_path: Path,
    ) -> tuple[int, int, int]:
        record: tuple[int, int, int] | None = None

        def ready() -> bool:
            nonlocal record
            try:
                fields = ready_path.read_text(encoding="ascii").split()
                if len(fields) != 3:
                    return False
                record = (int(fields[0]), int(fields[1]), int(fields[2]))
            except (FileNotFoundError, OSError, ValueError):
                return False
            return True

        self.assertTrue(
            self._wait_until(ready, 1.0),
            f"process tree did not become ready (leader returncode={process.poll()})",
        )
        assert record is not None
        leader_pid, process_group, _child_pid = record
        self.assertEqual(leader_pid, process.pid)
        self.assertEqual(process_group, process.pid)
        self.assertGreater(process_group, 1)
        self.assertNotEqual(process_group, os.getpgrp())
        return record

    def _spawn_process_tree(
        self,
        directory: Path,
    ) -> tuple[subprocess.Popen[bytes], Path, Path, Path, tuple[int, int, int]]:
        ready_path = directory / "ready"
        release_path = directory / "release"
        output_path = directory / "descendant-output"
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                _LEADER_PROGRAM,
                _DESCENDANT_PROGRAM,
                str(ready_path),
                str(release_path),
                str(output_path),
            ],
            cwd=directory,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            record = self._read_ready_record(process, ready_path)
        except BaseException:
            self._cleanup_process_tree(process, process.pid)
            raise
        return process, ready_path, release_path, output_path, record

    @staticmethod
    def _cleanup_process_tree(
        process: subprocess.Popen[bytes], process_group: int
    ) -> None:
        if process_group > 1 and process_group != os.getpgrp():
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=0.2)
        if process.stderr is not None:
            process.stderr.close()

    def _assert_leader_exit_kills_descendant(
        self,
        process: subprocess.Popen[bytes],
        release_path: Path,
        output_path: Path,
        record: tuple[int, int, int],
    ) -> None:
        _leader_pid, process_group, _child_pid = record
        RUNTIME._kill_process_group(process)
        self._assert_group_gone_before_descendant_write(
            process_group, release_path, output_path
        )

    def _assert_group_gone_before_descendant_write(
        self,
        process_group: int,
        release_path: Path,
        output_path: Path,
    ) -> None:
        observation: str | None = None

        def observed() -> bool:
            nonlocal observation
            if output_path.exists():
                observation = "descendant-wrote"
                return True
            if self._process_group_is_gone(process_group):
                observation = "group-gone"
                return True
            return False

        release_path.write_text("write now", encoding="ascii")
        self.assertTrue(
            self._wait_until(observed, 0.75),
            "process-group death remained unproved after cleanup returned",
        )
        self.assertEqual(
            observation,
            "group-gone",
            "descendant wrote after cleanup returned",
        )
        self.assertFalse(output_path.exists())

    def test_leader_exit_does_not_leave_term_ignoring_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            process, _ready, release, output, record = self._spawn_process_tree(
                Path(temporary)
            )
            try:
                self._assert_leader_exit_kills_descendant(
                    process, release, output, record
                )
            finally:
                self._cleanup_process_tree(process, record[1])

    def test_disabling_group_probe_restores_leader_only_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            process, _ready, release, output, record = self._spawn_process_tree(
                Path(temporary)
            )
            try:
                with mock.patch.object(
                    RUNTIME, "_process_group_exists", return_value=False
                ), self.assertRaises(AssertionError):
                    self._assert_leader_exit_kills_descendant(
                        process, release, output, record
                    )
            finally:
                self._cleanup_process_tree(process, record[1])

    def test_group_that_dies_during_term_grace_receives_no_sigkill(self) -> None:
        process = mock.Mock(pid=211)
        process.wait.return_value = 0
        sent: list[int] = []

        def signal_group(_process_group: int, chosen_signal: int) -> None:
            sent.append(chosen_signal)
            if chosen_signal == 0:
                raise ProcessLookupError

        with mock.patch.object(
            RUNTIME.os, "killpg", side_effect=signal_group
        ), mock.patch.object(
            RUNTIME.time, "monotonic", side_effect=[10.0, 10.05]
        ), mock.patch.object(RUNTIME.time, "sleep") as sleeper:
            RUNTIME._kill_process_group(process)

        self.assertEqual(sent, [signal.SIGTERM, 0])
        process.wait.assert_called_once_with(timeout=0.25)
        sleeper.assert_called_once()
        self.assertAlmostEqual(sleeper.call_args.args[0], 0.20)
        process.kill.assert_not_called()

    def test_leader_surviving_term_grace_receives_group_sigkill(self) -> None:
        process = mock.Mock(pid=223)
        process.wait.side_effect = subprocess.TimeoutExpired(["child"], 0.25)
        sent: list[int] = []

        def signal_group(_process_group: int, chosen_signal: int) -> None:
            sent.append(chosen_signal)

        with mock.patch.object(
            RUNTIME.os, "killpg", side_effect=signal_group
        ), mock.patch.object(
            RUNTIME.time, "monotonic", side_effect=[20.0, 20.25]
        ), mock.patch.object(RUNTIME.time, "sleep") as sleeper:
            RUNTIME._kill_process_group(process)

        self.assertEqual(sent, [signal.SIGTERM, 0, signal.SIGKILL])
        process.wait.assert_called_once_with(timeout=0.25)
        sleeper.assert_not_called()
        process.kill.assert_not_called()

    def test_nonlookup_group_errors_retain_leader_fallbacks(self) -> None:
        process = mock.Mock(pid=227)
        process.wait.side_effect = subprocess.TimeoutExpired(["child"], 0.25)
        sent: list[int] = []

        def signal_group(_process_group: int, chosen_signal: int) -> None:
            sent.append(chosen_signal)
            raise PermissionError("group signal unavailable")

        with mock.patch.object(
            RUNTIME.os, "killpg", side_effect=signal_group
        ), mock.patch.object(
            RUNTIME.time, "monotonic", side_effect=[30.0, 30.25]
        ), mock.patch.object(RUNTIME.time, "sleep"):
            RUNTIME._kill_process_group(process)

        self.assertEqual(sent, [signal.SIGTERM, 0, signal.SIGKILL])
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()

    def test_run_bounded_timeout_returns_after_entire_group_is_dead(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            ready_path = directory / "ready"
            release_path = directory / "release"
            output_path = directory / "descendant-output"
            process_group = 0
            try:
                result = RUNTIME.run_bounded(
                    [
                        sys.executable,
                        "-c",
                        _LEADER_PROGRAM,
                        _DESCENDANT_PROGRAM,
                        str(ready_path),
                        str(release_path),
                        str(output_path),
                    ],
                    cwd=directory,
                    timeout=0.75,
                    cap=1024,
                )
                fields = ready_path.read_text(encoding="ascii").split()
                self.assertEqual(len(fields), 3)
                leader_pid, process_group, _child_pid = map(int, fields)
                self.assertEqual(leader_pid, process_group)
                self.assertTrue(result.timed_out)
                self._assert_group_gone_before_descendant_write(
                    process_group, release_path, output_path
                )
            finally:
                if process_group <= 1:
                    try:
                        process_group = int(
                            ready_path.read_text(encoding="ascii").split()[1]
                        )
                    except (FileNotFoundError, IndexError, OSError, ValueError):
                        process_group = 0
                if process_group > 1 and process_group != os.getpgrp():
                    try:
                        os.killpg(process_group, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
