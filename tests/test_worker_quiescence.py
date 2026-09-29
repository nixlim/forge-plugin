from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from tests import _worker_quiescence as quiescence
from tests._git_env import init_quiet_repository

ROOT = Path(__file__).resolve().parents[1]

WORKER_SOURCE = r"""
from pathlib import Path
import os
import sys
import time

root = Path(sys.argv[1])
marker = root / sys.argv[2] if sys.argv[2] else None
release = Path(sys.argv[3])
late = Path(sys.argv[4])
if marker is not None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("pending\n", encoding="utf-8")
print(os.getpid(), flush=True)
while not release.exists():
    time.sleep(0.01)
late.parent.mkdir(parents=True, exist_ok=True)
late.write_text("after release\n", encoding="utf-8")
if marker is not None:
    marker.unlink()
"""

LAUNCHER_SOURCE = r"""
from pathlib import Path
import subprocess
import sys

worker = subprocess.Popen(
    [sys.executable, "-c", sys.argv[1], *sys.argv[2:6]],
    cwd=sys.argv[2],
    stdin=subprocess.DEVNULL,
    start_new_session=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    close_fds=True,
    text=True,
)
assert worker.stdout is not None
pid = worker.stdout.readline()
if not pid:
    raise SystemExit("worker exited before advertising its pid")
Path(sys.argv[6]).write_text(pid, encoding="utf-8")
"""

HALT_WORKER_NEEDLE = """try:
    result = subprocess.run(
        sys.argv[5:], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, check=False,
    )"""


class WorkerQuiescenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-quiescence-")
        self.addCleanup(self.temp_dir.cleanup)
        self.scratch = Path(self.temp_dir.name)
        self.repo = self.scratch / "repo"
        self.releases: list[Path] = []
        init_quiet_repository(self.repo, "--quiet").check_returncode()
        self.git("config", "user.name", "Forge Tests")
        self.git("config", "user.email", "forge-tests@example.invalid")
        self.git("commit", "--allow-empty", "--quiet", "-m", "initial")
        self.addCleanup(self.ensure_workers_stop)

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def ensure_workers_stop(self) -> None:
        if not self.scratch.exists():
            return
        for release in self.releases:
            try:
                release.touch(exist_ok=True)
            except OSError:
                pass
        try:
            quiescence.wait_for_quiescence(self.scratch, deadline=0.5)
        except AssertionError:
            pass

    def launch_worker(self, *, marker: bool = True) -> tuple[int, Path, Path]:
        sequence = len(self.releases)
        release = self.scratch / f"release-{sequence}"
        late = self.scratch / f"late-{sequence}" / "after.txt"
        pid_file = self.scratch / f"worker-{sequence}.pid"
        marker_name = ".forge/tmp/decision-event-pending.X" if marker else ""
        self.releases.append(release)
        subprocess.run(
            [
                sys.executable,
                "-c",
                LAUNCHER_SOURCE,
                WORKER_SOURCE,
                str(self.scratch),
                marker_name,
                str(release),
                str(late),
                str(pid_file),
            ],
            cwd=self.scratch,
            check=True,
            capture_output=True,
            text=True,
        )
        return int(pid_file.read_text(encoding="utf-8")), release, late

    def release_after_scan(
        self,
        release: Path,
        *,
        expected_pid: int | None = None,
    ) -> threading.Timer:
        original = quiescence.resident_processes
        timer = threading.Timer(0, release.touch)
        started = False

        def scan(root: Path) -> list[int] | None:
            nonlocal started
            residents = original(root)
            if not started and (
                expected_pid is None or expected_pid in (residents or [])
            ):
                started = True
                timer.start()
            return residents

        self.addCleanup(self.join_timer, timer)
        patcher = mock.patch.object(quiescence, "resident_processes", scan)
        patcher.start()
        self.addCleanup(patcher.stop)
        return timer

    def _fake_proc_process(
        self,
        pid: int,
        comm: bytes,
        *,
        state: bytes = b"S",
    ) -> tuple[Path, Path]:
        proc = self.scratch / "proc"
        self_dir = proc / "self"
        self_dir.mkdir(parents=True)
        (self_dir / "cwd").symlink_to(self.scratch, target_is_directory=True)
        process_dir = proc / str(pid)
        process_dir.mkdir()
        fields = [state, *([b"0"] * 18), b"424242"]
        (process_dir / "stat").write_bytes(
            str(pid).encode("ascii")
            + b" ("
            + comm
            + b") "
            + b" ".join(fields)
            + b"\n"
        )
        (process_dir / "cwd").symlink_to(self.scratch, target_is_directory=True)
        return proc, process_dir

    @staticmethod
    def join_timer(timer: threading.Timer) -> None:
        if timer.ident is not None:
            timer.join(timeout=5)

    @staticmethod
    def legacy_wait_for_decision_workers(repo: Path) -> None:
        pending_dir = repo / ".forge/tmp"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not list(pending_dir.glob("decision-event-pending.*")):
                return
            time.sleep(0.01)

    def test_slow_worker_finishes_before_quiescence_returns(self) -> None:
        pid, release, late = self.launch_worker()
        release_timer = self.release_after_scan(release)

        quiescence.wait_for_quiescence(self.scratch, deadline=5)
        release_timer.join(timeout=5)

        self.assertEqual(late.read_text(encoding="utf-8"), "after release\n")
        residents = quiescence.resident_processes(self.scratch)
        if residents is not None:
            self.assertNotIn(pid, residents)
        shutil.rmtree(self.scratch)

    def test_slow_worker_disable_leg_returns_while_worker_is_resident(self) -> None:
        pid, release, late = self.launch_worker()

        with (
            mock.patch.object(quiescence, "PENDING_PATTERNS", ()),
            mock.patch.object(quiescence, "resident_processes", return_value=[]),
        ):
            quiescence.wait_for_quiescence(self.scratch, deadline=0.5)

        self.assertFalse(late.exists())
        self.assertTrue(self.process_exists(pid))
        release.touch()
        quiescence.wait_for_quiescence(self.scratch, deadline=5)
        shutil.rmtree(self.scratch)

    @unittest.skipUnless(Path("/proc/self/cwd").exists(), "requires Linux procfs")
    def test_markerless_worker_waits_through_process_scan(self) -> None:
        pid, release, late = self.launch_worker(marker=False)
        release_timer = self.release_after_scan(release, expected_pid=pid)

        quiescence.wait_for_quiescence(self.scratch, deadline=5)
        release_timer.join(timeout=5)

        self.assertTrue(late.is_file())
        self.assertNotIn(pid, quiescence.resident_processes(self.scratch) or [])

    @unittest.skipUnless(Path("/proc/self/cwd").exists(), "requires Linux procfs")
    def test_markerless_worker_disable_leg_returns_early(self) -> None:
        pid, release, late = self.launch_worker(marker=False)
        original_scan = quiescence.resident_processes

        with mock.patch.object(quiescence, "resident_processes", return_value=[]):
            quiescence.wait_for_quiescence(self.scratch, deadline=0.5)

        self.assertFalse(late.exists())
        self.assertIn(pid, original_scan(self.scratch) or [])
        release.touch()
        quiescence.wait_for_quiescence(self.scratch, deadline=5)

    def test_process_scan_accepts_non_utf8_comm_bytes_with_disable_leg(self) -> None:
        pid = 910001
        proc, _process_dir = self._fake_proc_process(pid, b"worker-\xff")
        original_parser = quiescence._parse_process_status

        with mock.patch.object(quiescence, "_PROC", proc):
            self.assertEqual(quiescence.resident_processes(self.scratch), [pid])

        def decode_as_utf8(stat: bytes) -> tuple[bytes, bytes] | None:
            return original_parser(stat.decode("utf-8").encode("utf-8"))

        with (
            mock.patch.object(quiescence, "_PROC", proc),
            mock.patch.object(
                quiescence,
                "_parse_process_status",
                side_effect=decode_as_utf8,
            ),
            self.assertRaises(UnicodeDecodeError),
        ):
            quiescence.resident_processes(self.scratch)

    def test_process_scan_uses_last_closing_paren_with_disable_leg(self) -> None:
        pid = 910002
        proc, _process_dir = self._fake_proc_process(
            pid,
            b"worker) (nested",
            state=b"Z",
        )

        with mock.patch.object(quiescence, "_PROC", proc):
            self.assertEqual(quiescence.resident_processes(self.scratch), [])

        def parse_after_first_paren(stat: bytes) -> tuple[bytes, bytes] | None:
            closing = stat.find(b")")
            fields = stat[closing + 1 :].split()
            if closing < 0 or len(fields) < 20:
                return None
            return fields[0], fields[19]

        with (
            mock.patch.object(quiescence, "_PROC", proc),
            mock.patch.object(
                quiescence,
                "_parse_process_status",
                side_effect=parse_after_first_paren,
            ),
        ):
            self.assertEqual(quiescence.resident_processes(self.scratch), [pid])

    def test_process_scan_tolerates_vanishing_pid_with_disable_leg(self) -> None:
        proc, process_dir = self._fake_proc_process(910003, b"vanishing-worker")
        stat_path = process_dir / "stat"
        stat = stat_path.read_bytes()
        original_status = quiescence._process_status

        def vanish_then_check(selected: Path) -> tuple[bytes, bytes] | None:
            (selected / "stat").unlink()
            return original_status(selected)

        with (
            mock.patch.object(quiescence, "_PROC", proc),
            mock.patch.object(
                quiescence,
                "_process_status",
                side_effect=vanish_then_check,
            ),
        ):
            self.assertEqual(quiescence.resident_processes(self.scratch), [])
        self.assertFalse(stat_path.exists())
        stat_path.write_bytes(stat)

        def vanish_without_guard(selected: Path) -> tuple[bytes, bytes] | None:
            selected_stat = selected / "stat"
            selected_stat.unlink()
            return quiescence._parse_process_status(selected_stat.read_bytes())

        with (
            mock.patch.object(quiescence, "_PROC", proc),
            mock.patch.object(
                quiescence,
                "_process_status",
                side_effect=vanish_without_guard,
            ),
            self.assertRaises(FileNotFoundError),
        ):
            quiescence.resident_processes(self.scratch)

    @unittest.skipUnless(Path("/proc/self/cwd").exists(), "requires Linux procfs")
    def test_deadline_kills_worker_and_reports_marker_and_process(self) -> None:
        pid, _release, _late = self.launch_worker()

        with self.assertRaises(AssertionError) as raised:
            quiescence.wait_for_quiescence(self.scratch, deadline=0.5)

        message = str(raised.exception)
        self.assertIn("decision-event-pending.X", message)
        self.assertIn(str(pid), message)
        self.assertNotIn(pid, quiescence.resident_processes(self.scratch) or [])
        shutil.rmtree(self.scratch)

    @unittest.skipUnless(Path("/proc/self/cwd").exists(), "requires Linux procfs")
    def test_deadline_disable_leg_returns_while_worker_is_resident(self) -> None:
        pid, release, late = self.launch_worker()

        with mock.patch.object(quiescence, "_fail_quiescence") as disabled:
            quiescence.wait_for_quiescence(self.scratch, deadline=0)

        disabled.assert_called_once()
        self.assertFalse(late.exists())
        self.assertIn(pid, quiescence.resident_processes(self.scratch) or [])
        release.touch()
        quiescence.wait_for_quiescence(self.scratch, deadline=5)

    def test_real_halt_worker_outlives_legacy_wait_but_not_quiescence(self) -> None:
        guard_root = self.scratch / "copied-guard"
        shutil.copytree(ROOT / "scripts/forge", guard_root / "scripts/forge")
        shutil.copytree(ROOT / "system/fr223", guard_root / "system/fr223")
        release = self.scratch / "halt-worker-release"
        self.releases.append(release)
        guard = guard_root / "scripts/forge/commit-guard.sh"
        halt = guard_root / "scripts/forge/check-halt.sh"
        source = halt.read_text(encoding="utf-8")
        self.assertEqual(source.count(HALT_WORKER_NEEDLE), 1)
        blocking = (
            f"while not Path({str(release)!r}).exists():\n"
            "    __import__('time').sleep(0.01)\n"
            + HALT_WORKER_NEEDLE
        )
        halt.write_text(
            source.replace(HALT_WORKER_NEEDLE, blocking),
            encoding="utf-8",
        )
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")

        environment = {
            key: value for key, value in os.environ.items() if not key.startswith("GIT_")
        }
        environment["CLAUDE_PLUGIN_ROOT"] = str(guard_root)
        result = subprocess.run(
            ["bash", str(guard)],
            cwd=self.repo,
            input=json.dumps(
                {"tool_name": "Bash", "tool_input": {"command": "git push origin HEAD"}}
            ),
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            json.loads(result.stdout),
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "forge: operator halt engaged (AGENT_HALT)"
                    ),
                }
            },
        )

        self.legacy_wait_for_decision_workers(self.repo)
        self.assertFalse(
            list((self.repo / ".forge/tmp").glob("decision-event-pending.*"))
        )
        self.assertTrue(list(self.repo.rglob("halt-event-pending.*")))

        release.touch()
        quiescence.wait_for_quiescence(self.scratch, deadline=10)

        self.assertFalse(list(self.scratch.rglob("*-event-pending.*")))
        events_path = self.repo / ".forge/tmp/decisions/events.jsonl"
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            Counter(event["event"] for event in events),
            Counter({"guard_deny": 1, "halt_event": 1}),
        )
        shutil.rmtree(self.scratch)

    @staticmethod
    def process_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True


if __name__ == "__main__":
    unittest.main()
