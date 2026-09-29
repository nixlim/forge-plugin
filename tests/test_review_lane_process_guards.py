"""Real-process regression tests for review wrapper process-safety guards."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import suppress
from pathlib import Path
from unittest import mock

from tests._cli_loader import ROOT, package_module

ATTEMPT = package_module("engine._review_attempt")
ATTEMPT_PROC = package_module("engine._review_attempt_proc")
WRAPPER = package_module("engine._review_wrapper")
ATTEMPT_ID = "attempt-0123456789abcdef"

_NAMED_SLEEPER = r"""
import ctypes, pathlib, sys, time
name = bytes.fromhex(sys.argv[1])
if ctypes.CDLL(None).prctl(15, ctypes.c_char_p(name), 0, 0, 0) != 0:
    raise SystemExit(71)
pathlib.Path(sys.argv[2]).write_text(str(__import__('os').getpid()), encoding='ascii')
time.sleep(300)
"""

_TERM_IGNORING_TREE = r'''
import ctypes, json, os, pathlib, signal, subprocess, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
ctypes.CDLL(None).prctl(15, ctypes.c_char_p(b'\xff)reviewer'), 0, 0, 0)
child_source = """
import ctypes, signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
ctypes.CDLL(None).prctl(15, ctypes.c_char_p(b'\\xff)child'), 0, 0, 0)
time.sleep(300)
"""
child = subprocess.Popen([sys.executable, '-I', '-c', child_source])
marker = pathlib.Path(sys.argv[1])
temporary = marker.with_name(marker.name + '.tmp')
temporary.write_text(json.dumps([os.getpid(), child.pid]), encoding='ascii')
os.replace(temporary, marker)
print(json.dumps({"type": "system", "subtype": "init", "model": "guard-model",
                  "permissionMode": "default", "tools": ["Read"]}), flush=True)
if len(sys.argv) > 2 and sys.argv[2] == 'wrapper-crash':
    print('{"nested":' * 10000 + '0' + '}' * 10000, flush=True)
time.sleep(300)
'''

_NONLEADER_BRIDGE = r"""
import subprocess, sys
descriptor = int(sys.argv[1])
child = subprocess.Popen(
    [sys.executable, '-I', '-c', sys.argv[2], sys.argv[1], sys.argv[3]],
    env={},
    pass_fds=(descriptor,),
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
raise SystemExit(child.wait())
"""

_FIFO_PROBE = r"""
import os, sys
sys.path.insert(0, sys.argv[1])
from forge_cli.engine import _review_attempt as attempt
from forge_cli.engine import _review_wrapper as wrapper
from forge_cli.engine import _review_wrapper_io as wrapper_io

if sys.argv[4] == 'mutant':
    os.O_NONBLOCK = 0

directory = os.open(sys.argv[2], os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
try:
    if sys.argv[3] == 'completion.json':
        attempt.read_completion(directory, 'attempt-0123456789abcdef')
    elif sys.argv[3] == 'identity.json':
        attempt.read_identity(directory, 'attempt-0123456789abcdef')
    else:
        wrapper_io._open_events(directory, 'events.jsonl', True, wrapper.open_owner_regular)
except BaseException as exc:
    print(str(exc))
    raise SystemExit(0)
raise SystemExit(9)
"""


def _alive(pid: int) -> bool:
    try:
        data = Path(f"/proc/{pid}/stat").read_bytes()
        suffix = data[data.rfind(b")") + 2 :].split()
    except OSError:
        return False
    return bool(suffix) and suffix[0] != b"Z"


def _wait_path(path: Path, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


def _wait_dead(pid: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(pid):
            return
        time.sleep(0.02)
    raise AssertionError(f"PID {pid} survived")


@unittest.skipUnless(sys.platform.startswith("linux"), "real /proc tests need Linux")
class ReviewLaneProcessGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-review-guards-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.processes: list[subprocess.Popen[bytes]] = []
        self.groups: set[int] = set()
        self.addCleanup(self._cleanup_processes)

    def _cleanup_processes(self) -> None:
        for pgid in self.groups:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

    def _spawn(
        self, source: str, *arguments: str, new_session: bool = True
    ) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(
            [sys.executable, "-I", "-c", source, *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=new_session,
        )
        self.processes.append(process)
        if new_session:
            self.groups.add(process.pid)
        return process

    def _named(self, name: bytes, label: str) -> subprocess.Popen[bytes]:
        marker = self.root / f"{label}.pid"
        process = self._spawn(_NAMED_SLEEPER, name.hex(), str(marker))
        _wait_path(marker)
        self.assertIn(name, Path(f"/proc/{process.pid}/stat").read_bytes())
        return process

    def _identity(self, process: subprocess.Popen[bytes]) -> dict[str, object]:
        birth = WRAPPER.birth_identity(process.pid)
        self.assertIsNotNone(birth)
        return {
            "schema": WRAPPER.IDENTITY_SCHEMA,
            "attempt": ATTEMPT_ID,
            "wrapper_pid": process.pid,
            "pgid": process.pid,
            "wrapper_birth": birth,
            "reviewer_pid": None,
            "reviewer_birth": None,
            "started_at": "2026-09-27T12:00:00Z",
        }

    def _launch_wrapper(
        self,
        label: str,
        provider_source: str,
        *,
        wrapper_source: str | None = None,
        provider_arguments: tuple[str, ...] = (),
        nonleader_bridge: bool = False,
        timeout: float = 0.5,
    ) -> tuple[subprocess.Popen[bytes], Path]:
        attempt = self.root / label
        attempt.mkdir(mode=0o700)
        prompt = b"candidate: " + b"1" * 64 + b"\npackage: " + b"2" * 64 + b"\n"
        prompt_path = attempt / "prompt.txt"
        prompt_path.write_bytes(prompt)
        prompt_path.chmod(0o600)
        argv = [
            sys.executable,
            "-I",
            "-c",
            provider_source,
            *provider_arguments,
            "--tools",
            "Read",
        ]
        config = {
            "attempt": f"attempt-{hashlib.sha256(label.encode()).hexdigest()[:16]}",
            "argv": argv,
            "argv_digest": WRAPPER._canonical_digest(argv),
            "prompt_digest": hashlib.sha256(prompt).hexdigest(),
            "provider": "claude",
            "route_source": "committed-default",
            "route_sha256": "a" * 64,
            "sandbox": "instruction-bounded",
            "timeout": timeout,
            "grace": 0.2,
            "environment_names": [],
            "omitted_short": [],
        }
        descriptor = os.open(attempt, os.O_RDONLY | os.O_DIRECTORY)
        try:
            source = wrapper_source or WRAPPER.wrapper_source()
            encoded = json.dumps(config, sort_keys=True, separators=(",", ":"))
            command = [sys.executable, "-I", "-c", source, str(descriptor), encoded]
            if nonleader_bridge:
                command = [
                    sys.executable,
                    "-I",
                    "-c",
                    _NONLEADER_BRIDGE,
                    str(descriptor),
                    source,
                    encoded,
                ]
            process = subprocess.Popen(
                command,
                env={},
                pass_fds=(descriptor,),
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        finally:
            os.close(descriptor)
        self.processes.append(process)
        self.groups.add(process.pid)
        return process, attempt

    @staticmethod
    def _strict_parser(parser: object) -> object:
        def strict(data: bytes) -> tuple[str, int, int]:
            data.decode("ascii")
            return parser(data)  # type: ignore[operator]

        return strict

    def test_proc_scans_ignore_comm_bytes_and_owned_cancel_empties_group(self) -> None:
        self._named("réview)".encode(), "non-ascii-unrelated")
        invalid = self._named(b"review-\xff)", "invalid-unrelated")
        dead = self._spawn("import time; time.sleep(300)")
        dead_identity = self._identity(dead)
        os.killpg(dead.pid, signal.SIGTERM)
        dead.wait(timeout=5)
        self.groups.discard(dead.pid)

        def assert_empty() -> None:
            proof = ATTEMPT.prove_group_ownership(dead_identity)
            observed = ATTEMPT._observe_processes(dead_identity)
            self.assertEqual((proof.outcome, proof.members), ("group-empty", ()))
            self.assertEqual((observed.outcome, observed.reason), ("wrapper-lost", "group-empty"))

        assert_empty()
        strict_proc = self._strict_parser(ATTEMPT_PROC.parse_proc_stat)
        with (
            mock.patch.object(ATTEMPT_PROC, "parse_proc_stat", strict_proc),
            self.assertRaises(AssertionError),
        ):
            assert_empty()

        self.assertEqual(ATTEMPT_PROC.process_snapshot(invalid.pid)["status"], "alive")
        with (
            mock.patch.object(ATTEMPT_PROC, "parse_proc_stat", strict_proc),
            self.assertRaises(AssertionError),
        ):
            self.assertEqual(ATTEMPT_PROC.process_snapshot(invalid.pid)["status"], "alive")
        strict_wrapper = self._strict_parser(WRAPPER.parse_proc_stat)
        self.assertIsNotNone(WRAPPER.birth_identity(invalid.pid))
        with (
            mock.patch.object(WRAPPER, "parse_proc_stat", strict_wrapper),
            self.assertRaises(AssertionError),
        ):
            self.assertIsNotNone(WRAPPER.birth_identity(invalid.pid))

        owned = self._named(b"owned-\xff)", "owned-cancel")
        owned_identity = self._identity(owned)
        result = ATTEMPT.terminate_owned_group(owned_identity, 0.2, 3.0)
        owned.wait(timeout=5)
        self.groups.discard(owned.pid)
        self.assertEqual(result.outcome, "cancelled")
        self.assertEqual(ATTEMPT_PROC.group_members(owned.pid), ((), True))

        mutant_owned = self._named(b"mutant-\xff)", "mutant-cancel")
        mutant_identity = self._identity(mutant_owned)
        try:
            with (
                mock.patch.object(ATTEMPT_PROC, "parse_proc_stat", strict_proc),
                self.assertRaises(AssertionError),
            ):
                refused = ATTEMPT.terminate_owned_group(mutant_identity, 0.1, 0.1)
                self.assertEqual(refused.outcome, "cancelled")
        finally:
            os.killpg(mutant_owned.pid, signal.SIGKILL)
            mutant_owned.wait(timeout=5)
            self.groups.discard(mutant_owned.pid)

    def _assert_timeout_kills(self, source: str, label: str) -> None:
        marker = self.root / f"{label}.json"
        process, attempt = self._launch_wrapper(
            label, _TERM_IGNORING_TREE, wrapper_source=source,
            provider_arguments=(str(marker),),
        )
        pids: list[int] = []
        try:
            _wait_path(marker)
            pids = json.loads(marker.read_text(encoding="ascii"))
            completion_path = attempt / "completion.json"
            _wait_path(completion_path)
            completion = json.loads(completion_path.read_text(encoding="utf-8"))
            process.wait(timeout=5)
            for pid in pids:
                try:
                    _wait_dead(pid, 2.0)
                except AssertionError:
                    pass
            survivors = [pid for pid in pids if _alive(pid)]
            self.assertEqual((completion["timed_out"], completion["error"]), (True, None))
            self.assertEqual(survivors, [])
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.poll() is None:
                process.wait(timeout=5)
            for pid in pids:
                _wait_dead(pid)
            self.groups.discard(process.pid)

    def test_timeout_sigkills_term_ignoring_reviewer_and_descendant(self) -> None:
        source = WRAPPER.wrapper_source()
        self._assert_timeout_kills(source, "timeout-baseline")

        kill_anchor = "        os.killpg(pgid, signal.SIGKILL)\n"
        self.assertEqual(source.count(kill_anchor), 1)
        no_kill = source.replace(kill_anchor, "        pass  # SIGKILL disabled\n", 1)
        with self.assertRaises(AssertionError):
            self._assert_timeout_kills(no_kill, "timeout-no-kill")

        parser_anchor = "def parse_proc_stat(data: bytes) -> tuple[str, int, int]:\n"
        self.assertEqual(source.count(parser_anchor), 1)
        strict = source.replace(
            parser_anchor,
            parser_anchor + "    data.decode(\"ascii\")  # strict-comm mutant\n",
            1,
        )
        with self.assertRaises(AssertionError):
            self._assert_timeout_kills(strict, "timeout-strict-comm")

    def _wrapper_failure_group(
        self, source: str, label: str
    ) -> tuple[tuple[int, ...], bool]:
        marker = self.root / f"{label}.json"
        process, attempt = self._launch_wrapper(
            label,
            _TERM_IGNORING_TREE,
            wrapper_source=source,
            provider_arguments=(str(marker), "wrapper-crash"),
            timeout=30,
        )
        pids: list[int] = []
        try:
            _wait_path(marker)
            pids = json.loads(marker.read_text(encoding="ascii"))
            completion_path = attempt / "completion.json"
            _wait_path(completion_path)
            process.wait(timeout=5)
            completion = json.loads(completion_path.read_text(encoding="utf-8"))
            self.assertEqual(
                (completion["error"], completion["returncode"], completion["timed_out"]),
                ("wrapper failure", None, False),
            )
            return ATTEMPT_PROC.wait_group_empty(process.pid, 2.0)
        finally:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            if process.poll() is None:
                process.wait(timeout=5)
            for pid in pids:
                _wait_dead(pid)
            self.groups.discard(process.pid)

    def test_wrapper_failure_sweeps_reviewer_group(self) -> None:
        source = WRAPPER.wrapper_source()
        self.assertEqual(self._wrapper_failure_group(source, "failure-sweep"), ((), True))
        anchor = '    _terminate_group(int(identity["pgid"]), float(str(config["grace"])))\n'
        self.assertEqual(source.count(anchor), 1)
        disabled = source.replace(anchor, "    pass  # failure sweep disabled\n", 1)
        survivors = self._wrapper_failure_group(disabled, "failure-sweep-disabled")
        with self.assertRaises(AssertionError):
            self.assertEqual(survivors, ((), True))

    def _stop_nonleader_group(
        self,
        process: subprocess.Popen[bytes],
        wrapper_pid: object,
        reviewer_pid: object,
    ) -> None:
        if process.poll() is None:
            if type(wrapper_pid) is int:
                with suppress(ProcessLookupError):
                    os.kill(wrapper_pid, signal.SIGTERM)
            else:
                os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        if type(reviewer_pid) is int:
            _wait_dead(reviewer_pid)
        self.groups.discard(process.pid)

    def _nonleader_result(self, source: str, label: str) -> tuple[int, bool, bool]:
        marker = self.root / f"{label}.started"
        provider = (
            "import pathlib,sys,time; "
            "pathlib.Path(sys.argv[1]).write_text('started'); time.sleep(300)"
        )
        process, attempt = self._launch_wrapper(
            label,
            provider,
            wrapper_source=source,
            provider_arguments=(str(marker),),
            nonleader_bridge=True,
            timeout=30,
        )
        identity: dict[str, object] | None = None
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and process.poll() is None:
            try:
                identity = json.loads((attempt / "identity.json").read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(0.01)
                continue
            if identity.get("reviewer_pid") is not None:
                break
        if identity is None and (attempt / "identity.json").exists():
            identity = json.loads((attempt / "identity.json").read_text())
        wrapper_pid = identity.get("wrapper_pid") if identity else None
        reviewer_pid = identity.get("reviewer_pid") if identity else None
        self._stop_nonleader_group(process, wrapper_pid, reviewer_pid)
        return process.returncode, identity is not None, marker.exists()

    def test_nonleader_wrapper_publishes_no_identity_and_starts_no_reviewer(self) -> None:
        source = WRAPPER.wrapper_source()

        def assert_guard(candidate: str, label: str) -> None:
            self.assertEqual(self._nonleader_result(candidate, label), (1, False, False))

        assert_guard(source, "nonleader-baseline")
        anchor = (
            "    if pid != pgid or pid != os.getsid(0):\n"
            "        raise OSError(\"wrapper is not process-group leader\")\n"
        )
        self.assertEqual(source.count(anchor), 1)
        disabled = source.replace(
            anchor, anchor.replace(
                "if pid != pgid or pid != os.getsid(0):", "if False:"
            )
        )
        with self.assertRaises(AssertionError):
            assert_guard(disabled, "nonleader-disabled")

    def _fifo_probe(self, directory: Path, leaf: str, mutant: bool) -> str | None:
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    _FIFO_PROBE,
                    str(ROOT / "scripts" / "forge"),
                    str(directory),
                    leaf,
                    "mutant" if mutant else "baseline",
                ],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_fifo_attempt_artifacts_are_rejected_without_blocking(self) -> None:
        directory = self.root / "fifo-attempt"
        directory.mkdir(mode=0o700)
        expected = {
            "completion.json": "completion.json is unavailable or unsafe: unsafe attempt file",
            "identity.json": "identity.json is unavailable or unsafe: unsafe attempt file",
            "events.jsonl": "unsafe attempt file",
        }
        for leaf in expected:
            os.mkfifo(directory / leaf, 0o600)

        for leaf, diagnostic in expected.items():
            with self.subTest(leaf=leaf):
                self.assertEqual(self._fifo_probe(directory, leaf, False), diagnostic)
                with self.assertRaises(AssertionError):
                    self.assertEqual(self._fifo_probe(directory, leaf, True), diagnostic)


if __name__ == "__main__":
    unittest.main()
