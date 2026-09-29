"""Contracts for the standalone provider version-floor helper."""

from __future__ import annotations

import ast
import io
import os
import signal
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests._cli_loader import SCRIPTS_DIR, load_script, package_module

ROUTE_FLOOR = load_script("forge_route_floor_tests", SCRIPTS_DIR / "route_floor.py")
REVIEW_LAUNCH = package_module("engine._review_launch")


class RouteFloorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.environment = {"PATH": str(self.bin)}

    def _executable(self, name: str, body: str) -> Path:
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    def _version_executable(self, name: str, output: str) -> Path:
        return self._executable(name, f"print({output!r})")

    def _stubborn_provider(self, name: str, overflow: bool) -> tuple[Path, Path, Path]:
        pid_path = self.root / f"{name}.pid"
        ready_path = self.root / f"{name}.ready"
        term_path = self.root / f"{name}.term"
        child = (
            "import pathlib, signal, time\n"
            f"term = pathlib.Path({str(term_path)!r})\n"
            "signal.signal(signal.SIGTERM, "
            "lambda *_args: term.write_text('term', encoding='utf-8'))\n"
            f"pathlib.Path({str(ready_path)!r}).write_text('ready', encoding='utf-8')\n"
            "while True: time.sleep(1)\n"
        )
        output = "sys.stdout.write('x' * 4097); sys.stdout.flush()" if overflow else ""
        body = (
            "import pathlib, subprocess, sys, time\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child!r}])\n"
            f"pathlib.Path({str(pid_path)!r}).write_text(str(child.pid), encoding='utf-8')\n"
            f"ready = pathlib.Path({str(ready_path)!r})\n"
            "deadline = time.monotonic() + 5\n"
            "while not ready.exists() and time.monotonic() < deadline: time.sleep(0.01)\n"
            "if not ready.exists(): raise SystemExit(88)\n"
            f"{output}\n"
            "while True: time.sleep(1)"
        )
        return self._executable(name, body), pid_path, term_path

    @staticmethod
    def _process_running(pid: int) -> bool:
        stat_path = Path(f"/proc/{pid}/stat")
        try:
            if stat_path.exists():
                state = stat_path.read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
                return state != "Z"
            os.kill(pid, 0)
        except (OSError, IndexError):
            return False
        return True

    def _group_case(self, name: str, overflow: bool) -> tuple[bool, bool]:
        executable, pid_path, term_path = self._stubborn_provider(name, overflow)
        kind = "limit" if overflow else "timeout"
        bounds = (2, 4096, 0.2) if overflow else (1, 4096, 0.2)
        refusal = self._refusal("codex", executable, bounds=bounds)
        self.assertEqual(refusal.kind, kind)
        pid = int(pid_path.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 2
        while self._process_running(pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        still_running = self._process_running(pid)
        if still_running:
            os.kill(pid, signal.SIGKILL)
        return term_path.exists(), still_running

    def _refusal(
        self,
        provider: str,
        executable: Path,
        *,
        environment: dict[str, str] | None = None,
        bounds: tuple[float, int, float] = (10, 4096, 5),
        verb: str = "launch",
    ) -> object:
        timeout, limit, grace = bounds
        with self.assertRaises(ROUTE_FLOOR.FloorRefusal) as caught:
            ROUTE_FLOOR.check_floor(
                provider,
                str(executable),
                environment or self.environment,
                cwd=self.root,
                verb=verb,
                timeout_seconds=timeout,
                limit_bytes=limit,
                grace_seconds=grace,
            )
        return caught.exception

    def test_versions_below_at_and_above_each_floor(self) -> None:
        cases = (
            ("codex", "0.154.9", "below", None),
            ("codex", "codex-cli 0.155.0", "at", "0.155.0"),
            ("codex", "0.155.1", "above", "0.155.1"),
            ("claude", "2.1.282", "below", None),
            ("claude", "2.1.283 (Claude Code)", "at", "2.1.283"),
            ("claude", "2.2.0", "above", "2.2.0"),
        )
        for index, (provider, output, relation, expected) in enumerate(cases):
            executable = self._version_executable(f"provider-{index}", output)
            with self.subTest(provider=provider, relation=relation):
                if relation == "below":
                    refusal = self._refusal(provider, executable)
                    self.assertEqual(refusal.kind, "below")
                else:
                    self.assertEqual(
                        ROUTE_FLOOR.check_floor(
                            provider,
                            str(executable),
                            self.environment,
                            cwd=self.root,
                            verb="launch",
                        ),
                        expected,
                    )

    def test_claude_floor_refusal_and_control_are_load_bearing(self) -> None:
        executable = self._version_executable(
            "claude-immediate-below-floor", "2.1.282 (Claude Code)"
        )
        expected = (
            "forge: launch refused — claude version 2.1.282 "
            "is below required 2.1.283"
        )

        def assert_refusal() -> None:
            refusal = self._refusal("claude", executable)
            self.assertEqual(str(refusal), expected)

        assert_refusal()
        with (
            mock.patch.dict(ROUTE_FLOOR.FLOORS, {"claude": (2, 1, 282)}),
            self.assertRaises(AssertionError),
        ):
            assert_refusal()

    def test_limit_rejects_a_noninteger_value(self) -> None:
        arguments = ("codex", str(self.bin / "unused"), self.environment)
        common = {"cwd": self.root, "verb": "launch"}
        with self.assertRaisesRegex(TypeError, "limit_bytes must be an integer"):
            ROUTE_FLOOR.check_floor(*arguments, **common, limit_bytes=1.5)

    def test_stdout_precedes_stderr_when_selecting_the_first_version(self) -> None:
        executable = self._executable(
            "ordered", "import sys\nprint('codex-cli 0.155.1')\nprint('9.9.9', file=sys.stderr)"
        )
        self.assertEqual(
            ROUTE_FLOOR.check_floor(
                "codex", str(executable), self.environment, cwd=self.root, verb="launch"
            ),
            "0.155.1",
        )

    def test_unparseable_nonzero_missing_and_bounded_output_refusals(self) -> None:
        cases = (
            (
                "unparseable",
                self._executable("unreadable", "import os\nos.write(1, b'\\xfftext')"),
            ),
            (
                "exit",
                self._executable("nonzero", "import sys\nprint('0.155.0')\nsys.exit(7)"),
            ),
            ("unavailable", self.bin / "explicitly-missing-codex"),
            (
                "limit",
                self._executable("stdout-limit", "print('x' * 4097)"),
            ),
            (
                "limit",
                self._executable(
                    "stderr-limit", "import sys\nprint('x' * 4097, file=sys.stderr)"
                ),
            ),
        )
        for kind, executable in cases:
            with self.subTest(kind=kind, executable=executable.name):
                refusal = self._refusal("codex", executable)
                self.assertEqual(refusal.kind, kind)

    def test_each_stream_accepts_exactly_its_own_limit(self) -> None:
        executable = self._executable(
            "exact-limit",
            "import sys\n"
            "sys.stdout.write('x' * 4089 + '0.155.0')\n"
            "sys.stderr.write('y' * 4096)",
        )
        self.assertEqual(
            ROUTE_FLOOR.check_floor(
                "codex", str(executable), self.environment, cwd=self.root, verb="launch"
            ),
            "0.155.0",
        )

    def test_timeout_is_bounded_and_starts_a_new_session(self) -> None:
        executable = self._executable("timeout", "import time\ntime.sleep(10)")
        real_popen = ROUTE_FLOOR.subprocess.Popen
        sessions: list[bool] = []

        def record_popen(*args: object, **kwargs: object) -> object:
            sessions.append(bool(kwargs.get("start_new_session")))
            return real_popen(*args, **kwargs)

        started = time.monotonic()
        with mock.patch.object(
            ROUTE_FLOOR.subprocess, "Popen", side_effect=record_popen
        ):
            refusal = self._refusal("codex", executable, bounds=(0.05, 4096, 0.05))
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(refusal.kind, "timeout")
        self.assertEqual(sessions, [True])

    def test_timeout_and_limit_kill_stubborn_process_group(self) -> None:
        for name, overflow in (("timeout-group", False), ("limit-group", True)):
            with self.subTest(name=name):
                self.assertEqual(self._group_case(name, overflow), (True, False))

    def test_group_termination_control_is_load_bearing(self) -> None:
        def leader_only(process: object, _grace_seconds: float) -> None:
            process.kill()
            process.wait()

        with (
            mock.patch.object(ROUTE_FLOOR, "_terminate_probe", side_effect=leader_only),
            self.assertRaises(AssertionError),
        ):
            self.assertEqual(self._group_case("disabled-group-kill", False), (True, False))

    def test_caller_environment_is_passed_without_ambient_values(self) -> None:
        marker = self.root / "environment.txt"
        executable = self._executable(
            "environment",
            "import os, sys\n"
            "assert sys.argv[1:] == ['--version']\n"
            "assert sys.stdin.read() == ''\n"
            "open('environment.txt', 'w').write('|'.join(sorted(os.environ)))\n"
            "print(os.environ['FORGE_FLOOR_VERSION'])",
        )
        environment = {
            "PATH": str(self.bin),
            "FORGE_FLOOR_VERSION": "0.155.0",
        }
        with mock.patch.dict(os.environ, {"FORGE_AMBIENT_ONLY": "not-admitted"}):
            self.assertEqual(
                ROUTE_FLOOR.check_floor(
                    "codex", str(executable), environment, cwd=self.root, verb="launch"
                ),
                "0.155.0",
            )
        observed = set(marker.read_text(encoding="utf-8").split("|"))
        self.assertLessEqual(set(environment), observed)
        self.assertNotIn("FORGE_AMBIENT_ONLY", observed)

    def test_refusals_match_review_probe_for_every_kind_and_verb(self) -> None:
        factories = {
            "unavailable": lambda suffix: self.bin / f"missing-{suffix}",
            "timeout": lambda suffix: self._executable(
                f"timeout-{suffix}", "import time\ntime.sleep(10)"
            ),
            "limit": lambda suffix: self._executable(
                f"limit-{suffix}", "print('x' * 4097)"
            ),
            "exit": lambda suffix: self._executable(
                f"exit-{suffix}", "import sys\nsys.exit(23)"
            ),
            "unparseable": lambda suffix: self._executable(
                f"unparseable-{suffix}", "print('no semantic version here')"
            ),
            "below": lambda suffix: self._version_executable(
                f"below-{suffix}", "codex-cli 0.154.9"
            ),
        }
        for verb in ("launch", "review request"):
            for kind, factory in factories.items():
                with self.subTest(verb=verb, kind=kind):
                    executable = factory(f"{kind}-{verb.replace(' ', '-')}")
                    timeout = 0.05 if kind == "timeout" else 10
                    with (
                        mock.patch.object(
                            REVIEW_LAUNCH, "VERSION_PROBE_TIMEOUT_SECONDS", timeout
                        ),
                        mock.patch.object(REVIEW_LAUNCH, "TERMINATE_GRACE_SECONDS", 0.05),
                        self.assertRaises(REVIEW_LAUNCH.Refusal) as old,
                    ):
                        REVIEW_LAUNCH.probe_provider_version(
                            "codex",
                            str(executable),
                            self.environment,
                            self.root,
                            verb=verb,
                        )
                    new = self._refusal(
                        "codex",
                        executable,
                        verb=verb,
                        bounds=(timeout, 4096, 0.05),
                    )
                    self.assertEqual(new.kind, kind)
                    self.assertEqual(str(new), old.exception.message)

    def test_review_probe_delegates_with_live_bounds_and_refusal_shape(self) -> None:
        refusal = REVIEW_LAUNCH.route_floor.FloorRefusal(
            "forge: review request refused — codex executable is unavailable: fixture",
            "unavailable",
        )
        delegated = mock.Mock(side_effect=refusal)
        with (
            mock.patch.object(REVIEW_LAUNCH.route_floor, "check_floor", delegated),
            mock.patch.object(REVIEW_LAUNCH, "VERSION_PROBE_TIMEOUT_SECONDS", 1.25),
            mock.patch.object(REVIEW_LAUNCH, "VERSION_PROBE_LIMIT_BYTES", 321),
            mock.patch.object(REVIEW_LAUNCH, "TERMINATE_GRACE_SECONDS", 0.75),
            self.assertRaises(REVIEW_LAUNCH.Refusal) as caught,
        ):
            REVIEW_LAUNCH.probe_provider_version(
                "codex", "fixture", self.environment, self.root
            )
        delegated.assert_called_once_with(
            "codex",
            "fixture",
            self.environment,
            cwd=self.root,
            verb="review request",
            timeout_seconds=1.25,
            limit_bytes=321,
            grace_seconds=0.75,
        )
        self.assertEqual(caught.exception.message, refusal.message)
        self.assertEqual(caught.exception.expected, "available fixture executable")

    def _fake_route_config(
        self, providers: tuple[str, ...], environment: dict[str, str]
    ) -> tuple[object, mock.Mock, mock.Mock]:
        load = mock.Mock(
            return_value=SimpleNamespace(
                routes=tuple(SimpleNamespace(provider=item) for item in providers)
            )
        )
        allowed = mock.Mock(side_effect=lambda _provider: dict(environment))
        support = SimpleNamespace(_allowed_environment=allowed)
        module = SimpleNamespace(load=load, _probe_support=lambda: support)
        return module, load, allowed

    def test_cli_checks_each_distinct_provider_with_a_fake_only_path(self) -> None:
        log = self.root / "calls.txt"
        environment = dict(self.environment, LANG="C")
        self._executable(
            "codex",
            "import os\nassert os.environ['LANG'] == 'C'\n"
            f"open({str(log)!r}, 'a').write('codex\\n')\nprint('0.155.0')",
        )
        self._executable(
            "claude",
            "import os\nassert os.environ['LANG'] == 'C'\n"
            f"open({str(log)!r}, 'a').write('claude\\n')\nprint('2.1.283')",
        )
        module, load, allowed = self._fake_route_config(
            ("codex", "claude", "codex"), environment
        )
        with mock.patch.dict(sys.modules, {"route_config": module}):
            status = ROUTE_FLOOR.main(["--repo", str(self.root)])
        self.assertEqual(status, 0)
        load.assert_called_once_with(self.root, head="HEAD")
        self.assertEqual([call.args[0] for call in allowed.call_args_list], ["claude", "codex"])
        self.assertEqual(sorted(log.read_text(encoding="utf-8").splitlines()), ["claude", "codex"])

    def test_cli_refusal_and_usage_exit_codes(self) -> None:
        self._version_executable("codex", "codex-cli 0.150.0")
        module, _load, _allowed = self._fake_route_config(("codex",), self.environment)
        stderr = io.StringIO()
        with (
            mock.patch.dict(sys.modules, {"route_config": module}),
            redirect_stderr(stderr),
        ):
            status = ROUTE_FLOOR.main(["--repo", str(self.root)])
        self.assertEqual(status, 1)
        self.assertEqual(
            stderr.getvalue(),
            "forge: route floor refused — codex version 0.150.0 "
            "is below required 0.155.0\n",
        )

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            status = ROUTE_FLOOR.main(["--repo", "relative"])
        self.assertEqual(status, 2)
        self.assertIn(
            "route_floor.py: error: argument --repo: must be an absolute path",
            stderr.getvalue(),
        )

    def test_module_level_imports_are_stdlib_only(self) -> None:
        path = SCRIPTS_DIR / "route_floor.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        roots: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                roots.update(alias.name.partition(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                roots.add(node.module.partition(".")[0])
        self.assertLessEqual(roots, sys.stdlib_module_names | {"__future__"})
        self.assertNotIn("route_config_probe", source)
        self.assertIn('__import__("route_config")', source)


if __name__ == "__main__":
    unittest.main()
