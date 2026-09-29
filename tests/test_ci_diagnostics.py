from __future__ import annotations

import io
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests._cli_loader import load_script

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS_PATH = ROOT / "scripts" / "ci_diagnostics.py"
DIAGNOSTICS = load_script("ci_diagnostics_test_subject", DIAGNOSTICS_PATH)
FINGERPRINT_PREFIXES = (
    "cpu.count=",
    "umask=",
    "git.version=",
    "git.template-dir=",
    "git.template-mode=",
    "python.version=",
    "python.executable=",
    "which.python3=",
    "which.claude=",
    "which.codex=",
    "disk./tmp=",
    "disk./dev/shm=",
    "disk.RUNNER_TEMP=",
    "proc.pressure.cpu=",
    "env.LANG=",
    "env.LC_ALL=",
    "env.TMPDIR=",
    "env.CLAUDE_PLUGIN_ROOT.set=",
    "rlimit.nofile=",
    "git.global-config-names=",
)


class _FakeWalkEntry:
    path = "/tmp/fake-entry"

    def stat(self, *, follow_symlinks: bool) -> SimpleNamespace:
        if follow_symlinks:
            raise AssertionError("walk followed a synthetic entry")
        return SimpleNamespace(st_mode=stat.S_IFREG, st_size=1)


class _GuardedScandir:
    def __init__(self) -> None:
        self.yielded = 0

    def __enter__(self) -> _GuardedScandir:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def __iter__(self) -> _GuardedScandir:
        return self

    def __next__(self) -> _FakeWalkEntry:
        self.yielded += 1
        if self.yielded > 3:
            raise AssertionError("walk eagerly consumed beyond its entry cap")
        return _FakeWalkEntry()


def _eager_walk_mutant(path: Path) -> SimpleNamespace:
    list(DIAGNOSTICS.os.scandir(path))
    return SimpleNamespace(entries=0, state="complete")


class DiagnosticsFixture:
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def make_test_root(self) -> Path:
        root = self.base / "root"
        tests = root / "tests"
        tests.mkdir(parents=True, exist_ok=True)
        (tests / "__init__.py").write_text("", encoding="utf-8")
        return root

    def write_module(self, root: Path, name: str, body: str) -> Path:
        path = root / "tests" / f"{name}.py"
        path.write_text(body, encoding="utf-8")
        return path

    def failure_line(self, name: str, seconds: str = "0.1") -> str:
        return f"gate-1 {name}: exit 1 ran 1 in {seconds}s FAILED\n"


class RerunTests(DiagnosticsFixture, unittest.TestCase):
    def test_rerun_classifies_pass_and_failure_and_sanitizes_tails(self) -> None:
        root = self.make_test_root()
        self.write_module(
            root,
            "test_pass",
            "import unittest\n"
            "class PassingTest(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n",
        )
        self.write_module(
            root,
            "test_fail",
            "import sys\n"
            "import unittest\n"
            "class FailingTest(unittest.TestCase):\n"
            "    def test_bad(self):\n"
            "        print('::error::forged', file=sys.stderr)\n"
            "        print('\\x1b[2J', file=sys.stderr)\n"
            "        self.fail('expected')\n",
        )
        gate_output = self.base / "gate.txt"
        gate_output.write_text(
            self.failure_line("test_pass") + self.failure_line("test_fail"),
            encoding="utf-8",
        )
        out_dir = self.base / "diagnostics"
        captured = io.StringIO()
        with redirect_stdout(captured):
            result = DIAGNOSTICS.rerun(gate_output, out_dir, root, 10, 30)

        output = captured.getvalue()
        self.assertEqual(result, 1)
        self.assertIn("test_pass: FLAKE-SUSPECT", output)
        self.assertIn("test_fail: REPRODUCIBLE", output)
        self.assertNotIn("\x1b", output)
        self.assertFalse(any(line.startswith("::") for line in output.splitlines()))
        hostile_lines = [line for line in output.splitlines() if "::error::forged" in line]
        self.assertTrue(hostile_lines)
        self.assertTrue(
            all(line.startswith("forge-ci: rerun test_fail | ") for line in hostile_lines)
        )
        summary = (out_dir / "rerun-summary.txt").read_text(encoding="utf-8")
        self.assertIn("FLAKE-SUSPECT", summary)
        self.assertIn("REPRODUCIBLE", summary)

    def test_timeout_kills_the_new_process_group(self) -> None:
        root = self.make_test_root()
        pgid_path = self.base / "rerun.pgid"
        self.write_module(
            root,
            "test_hang",
            "import os\n"
            "import time\n"
            "import unittest\n"
            "from pathlib import Path\n"
            "class HangingTest(unittest.TestCase):\n"
            "    def test_hang(self):\n"
            "        Path(os.environ['FORGE_TEST_PGID']).write_text(str(os.getpgrp()))\n"
            "        time.sleep(60)\n",
        )
        gate_output = self.base / "gate.txt"
        gate_output.write_text(self.failure_line("test_hang"), encoding="utf-8")
        captured = io.StringIO()
        with mock.patch.dict(os.environ, {"FORGE_TEST_PGID": str(pgid_path)}), redirect_stdout(
            captured
        ):
            result = DIAGNOSTICS.rerun(gate_output, self.base / "out", root, 1, 5)

        self.assertEqual(result, 1)
        self.assertIn("test_hang: INCONCLUSIVE", captured.getvalue())
        process_group = int(pgid_path.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        with self.assertRaises(ProcessLookupError):
            os.killpg(process_group, 0)

    def test_admission_is_strict_deduplicated_and_limited_to_three(self) -> None:
        root = self.make_test_root()
        for name in ("test_one", "test_two", "test_three", "test_four"):
            self.write_module(root, name, "# fixture\n")
        link_target = root / "directory-target"
        link_target.mkdir()
        (root / "tests" / "test_link.py").symlink_to(link_target, target_is_directory=True)
        gate_output = self.base / "gate.txt"
        gate_output.write_text(
            "gate-1 test_x; rm -rf: exit 1 ran 1 in 0.1s FAILED\n"
            "gate-1 ../x: exit 1 ran 1 in 0.1s FAILED\n"
            "gate-1 test_missing: exit 1 ran 1 in 0.1s FAILED\n"
            "gate-1 test_link: exit 1 ran 1 in 0.1s FAILED\n"
            "forge: drift gate-1 | gate-1 test_one: exit 1 ran 1 in ?s FAILED\n"
            "gate-1 test_one: exit 1 ran 1 in 0.1s FAILED\n"
            "gate-1 test_two: exit 1 ran 1 in 0.1s FAILED\n"
            "gate-1 test_three: exit 1 ran 1 in 0.1s FAILED\n"
            "gate-1 test_four: exit 1 ran 1 in 0.1s FAILED\n",
            encoding="utf-8",
        )

        self.assertEqual(
            DIAGNOSTICS.attributable_modules(gate_output, root),
            ["test_one", "test_two", "test_three"],
        )

    def test_launch_error_and_exhausted_deadline_are_inconclusive(self) -> None:
        root = self.make_test_root()
        self.write_module(root, "test_pass", "# fixture\n")
        config = DIAGNOSTICS.RerunConfig(root, self.base / "out", 1, 1)
        config.out_dir.mkdir()
        with mock.patch.object(DIAGNOSTICS.subprocess, "Popen", side_effect=OSError("no exec")):
            launch = DIAGNOSTICS._run_module(
                "test_pass",
                config,
                time.monotonic() + 1,
            )
        deadline = DIAGNOSTICS._run_module("test_pass", config, time.monotonic() - 1)
        self.assertEqual((launch.label, launch.detail), ("INCONCLUSIVE", "launch error"))
        self.assertEqual(
            (deadline.label, deadline.detail),
            ("INCONCLUSIVE", "deadline exhausted"),
        )

    def test_timeout_kill_targets_the_process_group_and_control_is_binding(self) -> None:
        def assert_group_kill(killer: object) -> None:
            process = mock.Mock(pid=43210)
            with mock.patch.object(DIAGNOSTICS.os, "killpg") as killpg:
                killer(process)
            killpg.assert_called_once_with(process.pid, signal.SIGKILL)
            process.wait.assert_called_once_with(timeout=10)

        def single_process_mutant(process: mock.Mock) -> None:
            process.kill()
            process.wait(timeout=10)

        assert_group_kill(DIAGNOSTICS._kill_process_group)
        with self.assertRaises(AssertionError):
            assert_group_kill(single_process_mutant)

    def test_rerun_always_fails_and_exit_control_is_binding(self) -> None:
        root = self.make_test_root()
        gate_output = self.base / "gate.txt"
        gate_output.write_text("no failure module here\n", encoding="utf-8")

        def assert_fail_closed(out_dir: Path) -> None:
            captured = io.StringIO()
            with redirect_stdout(captured):
                result = DIAGNOSTICS.rerun(gate_output, out_dir, root)
            self.assertNotEqual(result, 0)
            self.assertIn("no attributable gate-1 module line", captured.getvalue())

        assert_fail_closed(self.base / "normal")
        with mock.patch.object(DIAGNOSTICS, "RERUN_EXIT_CODE", 0), self.assertRaises(
            AssertionError
        ):
            assert_fail_closed(self.base / "mutant")


class StubTests(DiagnosticsFixture, unittest.TestCase):
    def install(self, name: str = "") -> tuple[Path, Path]:
        base = self.base / name if name else self.base
        stub_dir = base / "provider stubs"
        log_path = base / "diagnostics with space" / "provider launches.log"
        self.assertEqual(DIAGNOSTICS.install_stubs(stub_dir, log_path), 0)
        return stub_dir, log_path

    def invoke_stub(self, stub_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(stub_path), "a b", "$(touch pwned)", "x\ny"],
            cwd=self.base,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

    def test_stubs_are_fail_loud_literal_and_audited(self) -> None:
        stub_dir, log_path = self.install()
        for provider in DIAGNOSTICS.PROVIDERS:
            mode = stat.S_IMODE((stub_dir / provider).stat().st_mode)
            self.assertEqual(mode, 0o755)
        marker = stub_dir / DIAGNOSTICS.STUB_LOG_MARKER
        self.assertTrue(stat.S_ISREG(marker.stat(follow_symlinks=False).st_mode))
        self.assertEqual(marker.read_text(encoding="utf-8"), f"{log_path.resolve()}\n")
        result = self.invoke_stub(stub_dir / "claude")
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 97)
        self.assertIn(
            "forge-ci: provider stub claude invoked; tests must not launch a real provider",
            result.stderr,
        )
        self.assertEqual(log.count("claude"), 1)
        self.assertEqual(log.splitlines(), ["claude a b $(touch pwned) x?y"])
        self.assertFalse((self.base / "pwned").exists())
        with redirect_stderr(io.StringIO()):
            self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, log_path), 1)

    def test_audit_accepts_empty_log_and_rejects_missing_stubs(self) -> None:
        stub_dir, log_path = self.install()
        self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, log_path), 0)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(
                DIAGNOSTICS.stub_audit(self.base / "missing-stubs", log_path),
                1,
            )
        (stub_dir / "codex").unlink()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, log_path), 1)

    def test_audit_rejects_missing_log(self) -> None:
        stub_dir, log_path = self.install()
        log_path.unlink()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, log_path), 1)

    def test_audit_rejects_missing_log_directory(self) -> None:
        stub_dir, log_path = self.install()
        log_path.unlink()
        log_path.parent.rmdir()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, log_path), 1)

    def test_audit_rejects_log_replaced_by_directory(self) -> None:
        stub_dir, log_path = self.install()
        log_path.unlink()
        log_path.mkdir()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, log_path), 1)

    def test_audit_rejects_log_replaced_by_symlink(self) -> None:
        stub_dir, log_path = self.install()
        target = self.base / "empty-decoy.log"
        target.touch()
        log_path.unlink()
        log_path.symlink_to(target)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, log_path), 1)

    def test_audit_rejects_unreadable_log(self) -> None:
        stub_dir, log_path = self.install()
        original_open = DIAGNOSTICS.os.open

        def deny_log(path: object, *args: object, **kwargs: object) -> int:
            if Path(path) == log_path:
                raise PermissionError("launch log denied")
            return original_open(path, *args, **kwargs)

        with (
            mock.patch.object(DIAGNOSTICS.os, "open", side_effect=deny_log),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, log_path), 1)

    def test_audit_binds_log_to_installation_marker(self) -> None:
        stub_dir, log_path = self.install()
        marker = stub_dir / DIAGNOSTICS.STUB_LOG_MARKER
        marker.unlink()

        def assert_marker_required() -> None:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, log_path), 1)

        assert_marker_required()
        with (
            mock.patch.object(
                DIAGNOSTICS,
                "_installed_stub_log",
                return_value=str(log_path.resolve()),
            ),
            self.assertRaises(AssertionError),
        ):
            assert_marker_required()

        DIAGNOSTICS.install_stubs(stub_dir, log_path)
        other_log = self.base / "other.log"
        other_log.touch()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, other_log), 1)

    def test_missing_log_fail_closed_control_is_binding(self) -> None:
        stub_dir, log_path = self.install()
        log_path.unlink()

        def assert_missing_log_rejected() -> None:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, log_path), 1)

        assert_missing_log_rejected()
        with (
            mock.patch.object(DIAGNOSTICS, "_regular_file_size", return_value=0),
            self.assertRaises(AssertionError),
        ):
            assert_missing_log_rejected()

    def test_audit_tail_is_bounded_prefixed_and_sanitized(self) -> None:
        stub_dir, log_path = self.install()
        log_path.write_bytes(b"x" * 5000 + b"\n::error::forged\n\x1b[2J\n")
        captured = io.StringIO()
        with redirect_stderr(captured):
            result = DIAGNOSTICS.stub_audit(stub_dir, log_path)
        output = captured.getvalue()
        echoed = [line for line in output.splitlines() if "audit |" in line]
        self.assertEqual(result, 1)
        self.assertTrue(echoed)
        self.assertTrue(all(line.startswith("forge-ci: provider audit | ") for line in echoed))
        self.assertNotIn("\x1b", output)
        self.assertLess(len(output.encode("utf-8")), 5000)

    def test_stub_logging_control_is_binding(self) -> None:
        stub_dir, log_path = self.install()

        def assert_launch_detected() -> None:
            log_path.write_text("", encoding="utf-8")
            result = self.invoke_stub(stub_dir / "claude")
            self.assertEqual(result.returncode, 97)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(DIAGNOSTICS.stub_audit(stub_dir, log_path), 1)

        assert_launch_detected()
        stub = stub_dir / "claude"
        source = stub.read_text(encoding="utf-8")
        self.assertEqual(source.count('} >> "$log"'), 1)
        stub.write_text(source.replace('} >> "$log"', "}", 1), encoding="utf-8")
        stub.chmod(0o755)
        with self.assertRaises(AssertionError):
            assert_launch_detected()


class FingerprintTests(DiagnosticsFixture, unittest.TestCase):
    def assert_fingerprint_schema(self, output: str) -> None:
        lines = output.splitlines()
        missing = [
            prefix
            for prefix in FINGERPRINT_PREFIXES
            if not any(line.startswith(prefix) for line in lines)
        ]
        self.assertEqual(missing, [])

    def test_fingerprint_is_bounded_secret_free_and_missing_pressure_is_safe(self) -> None:
        out_path = self.base / "diagnostics" / "fingerprint.txt"
        missing_pressure = self.base / "no-pressure"
        captured = io.StringIO()
        environment = {
            "FORGE_CI_FAKE_SECRET": "sentinel-do-not-print",
            "RUNNER_TEMP": str(self.base),
        }
        with mock.patch.dict(os.environ, environment, clear=False), mock.patch.object(
            DIAGNOSTICS,
            "CPU_PRESSURE_PATH",
            missing_pressure,
        ), redirect_stdout(captured):
            result = DIAGNOSTICS.fingerprint(out_path)
        output = captured.getvalue()
        self.assertEqual(result, 0)
        self.assertEqual(output, out_path.read_text(encoding="utf-8"))
        self.assert_fingerprint_schema(output)
        self.assertIn("proc.pressure.cpu=unavailable", output)
        self.assertNotIn("sentinel-do-not-print", output)
        self.assertLessEqual(len(output.encode("utf-8")), DIAGNOSTICS.FINGERPRINT_OUTPUT_BYTES)

        bounded_stdout = io.StringIO()
        with mock.patch.object(
            DIAGNOSTICS,
            "_template_modes",
            return_value=["x" * 1000] * 1000,
        ), mock.patch.object(
            DIAGNOSTICS,
            "verify_stubs",
            return_value=True,
        ), redirect_stdout(bounded_stdout):
            DIAGNOSTICS.fingerprint(
                self.base / "bounded.txt",
                self.base / "expected-stubs",
            )
        self.assertLessEqual(
            (self.base / "bounded.txt").stat().st_size,
            DIAGNOSTICS.FINGERPRINT_OUTPUT_BYTES,
        )
        self.assert_fingerprint_schema(bounded_stdout.getvalue())
        self.assertIn("provider-stubs=verified", bounded_stdout.getvalue())
        self.assertIn("git.template-mode=truncated", bounded_stdout.getvalue())

    def test_fingerprint_field_controls_are_binding(self) -> None:
        path = self.base / "fingerprint.txt"
        with redirect_stdout(io.StringIO()):
            DIAGNOSTICS.fingerprint(path)
        output = path.read_text(encoding="utf-8")
        self.assert_fingerprint_schema(output)
        for prefix in FINGERPRINT_PREFIXES:
            with self.subTest(prefix=prefix):
                mutant = "\n".join(
                    line for line in output.splitlines() if not line.startswith(prefix)
                )
                with self.assertRaises(AssertionError):
                    self.assert_fingerprint_schema(mutant)

    def test_environment_non_disclosure_control_is_binding(self) -> None:
        original = DIAGNOSTICS._fingerprint_lines

        def assert_secret_absent(path: Path) -> None:
            with redirect_stdout(io.StringIO()):
                DIAGNOSTICS.fingerprint(path)
            self.assertNotIn("sentinel-mutant-secret", path.read_text(encoding="utf-8"))

        def leaking_lines(expect_stubs: Path | None) -> tuple[list[str], bool]:
            lines, verified = original(expect_stubs)
            leaked = f"{os.environ['FORGE_CI_FAKE_SECRET']} {dict(os.environ)!r}"
            return [leaked, *lines], verified

        with mock.patch.dict(
            os.environ,
            {"FORGE_CI_FAKE_SECRET": "sentinel-mutant-secret"},
        ):
            assert_secret_absent(self.base / "normal.txt")
            with mock.patch.object(
                DIAGNOSTICS,
                "_fingerprint_lines",
                side_effect=leaking_lines,
            ), self.assertRaises(AssertionError):
                assert_secret_absent(self.base / "mutant.txt")

    def test_expected_stub_verification_is_contained_and_binding(self) -> None:
        stub_dir = self.base / "stubs"
        stub_dir.mkdir()
        outside = self.base / "outside-claude"
        outside.write_text("not a stub\n", encoding="utf-8")
        codex = stub_dir / "codex"
        codex.write_text("stub\n", encoding="utf-8")

        def fake_which(name: str) -> str:
            paths = {"python3": sys.executable, "claude": str(outside), "codex": str(codex)}
            return paths[name]

        def assert_rejected(path: Path) -> None:
            with redirect_stdout(io.StringIO()):
                result = DIAGNOSTICS.fingerprint(path, stub_dir)
            self.assertEqual(result, 1)

        with mock.patch.object(DIAGNOSTICS.shutil, "which", side_effect=fake_which):
            assert_rejected(self.base / "rejected.txt")
            with mock.patch.object(
                DIAGNOSTICS,
                "verify_stubs",
                return_value=True,
            ), self.assertRaises(AssertionError):
                assert_rejected(self.base / "mutant.txt")

    def test_probe_timeout_is_tolerated(self) -> None:
        with mock.patch.object(
            DIAGNOSTICS.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["git"], 10),
        ):
            self.assertEqual(DIAGNOSTICS._run_probe(("git", "--version")), "unavailable")


class SnapshotTests(DiagnosticsFixture, unittest.TestCase):
    def test_snapshot_confines_output_and_always_returns_zero(self) -> None:
        out_dir = self.base / "snapshots"
        walk = DIAGNOSTICS.WalkResult(2, 10, "complete")
        with mock.patch.object(DIAGNOSTICS, "_walk_usage", return_value=walk), mock.patch.object(
            DIAGNOSTICS,
            "_filtered_processes",
            return_value=["1 0 1 00:01 python worker.py"],
        ), mock.patch.dict(os.environ, {"RUNNER_TEMP": str(self.base)}):
            result = DIAGNOSTICS.snapshot("../post-gate1", out_dir)
        self.assertEqual(result, 0)
        self.assertEqual(
            [path.name for path in out_dir.iterdir()],
            ["snapshot-.._post-gate1.txt"],
        )
        snapshot_path = out_dir / "snapshot-.._post-gate1.txt"
        payload = snapshot_path.read_text(encoding="utf-8")
        required = (
            "process | 1 0 1 00:01 python worker.py",
            "walk./tmp=entries=2 size=10 state=complete",
            "walk.RUNNER_TEMP=entries=2 size=10 state=complete",
        )

        def assert_snapshot_controls(text: str) -> None:
            for expected in required:
                self.assertIn(expected, text)

        assert_snapshot_controls(payload)
        for expected in required:
            with self.subTest(expected=expected), self.assertRaises(AssertionError):
                assert_snapshot_controls(payload.replace(expected, "", 1))
        self.assertFalse((self.base / "snapshot-post-gate1.txt").exists())

        with mock.patch.object(
            DIAGNOSTICS,
            "_filtered_processes",
            side_effect=OSError("ps unavailable"),
        ), redirect_stderr(io.StringIO()):
            self.assertEqual(DIAGNOSTICS.snapshot("failure", out_dir), 0)

    def test_process_snapshot_excludes_self_and_caps_rows_and_width(self) -> None:
        header = "PID PPID PGID ELAPSED COMMAND\n"
        own = f"{os.getpid()} 1 1 00:00 python helper.py\n"
        unrelated = "8 1 8 00:00 sleep 5\n"
        rows = "".join(
            f"{index + 100} 1 1 00:00 python {'x' * 3000}\n" for index in range(250)
        )
        completed = subprocess.CompletedProcess([], 0, stdout=header + own + unrelated + rows)
        with mock.patch.object(DIAGNOSTICS.subprocess, "run", return_value=completed):
            selected = DIAGNOSTICS._filtered_processes()
        self.assertEqual(len(selected), DIAGNOSTICS.SNAPSHOT_PROCESS_LIMIT)
        self.assertTrue(all(len(line) <= DIAGNOSTICS.SNAPSHOT_LINE_CHARS for line in selected))
        self.assertFalse(any(line.startswith(str(os.getpid()) + " ") for line in selected))

    def test_walk_has_entry_cap_and_does_not_follow_symlinked_directory(self) -> None:
        root = self.base / "walk"
        root.mkdir()
        target = self.base / "target"
        target.mkdir()
        (target / "hidden").write_text("hidden", encoding="utf-8")
        (root / "link").symlink_to(target, target_is_directory=True)
        for index in range(5):
            (root / f"file-{index}").write_text("x", encoding="utf-8")
        with mock.patch.object(DIAGNOSTICS, "SNAPSHOT_ENTRY_LIMIT", 3):
            capped = DIAGNOSTICS._walk_usage(root)
        self.assertEqual((capped.entries, capped.state), (3, "entry-cap"))

    def test_walk_streaming_control_is_binding(self) -> None:
        root = self.base / "streaming-walk"
        root.mkdir()

        def assert_bounded(walker: object) -> None:
            guarded = _GuardedScandir()
            with (
                mock.patch.object(DIAGNOSTICS.os, "scandir", return_value=guarded),
                mock.patch.object(DIAGNOSTICS, "SNAPSHOT_ENTRY_LIMIT", 3),
            ):
                result = walker(root)
            self.assertEqual(
                (result.entries, result.size, result.state),
                (3, 3, "entry-cap"),
            )

        assert_bounded(DIAGNOSTICS._walk_usage)
        with self.assertRaises(AssertionError):
            assert_bounded(_eager_walk_mutant)


if __name__ == "__main__":
    unittest.main()
