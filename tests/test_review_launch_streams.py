"""Stream, cap, timeout, and signal-atomicity tests for the review wrapper."""

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
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from tests._cli_loader import package_module

LAUNCH = package_module("engine._review_launch")
LANE_API = package_module("engine._review_lane_api")
WRAPPER = package_module("engine._review_wrapper")
WRAPPER_IO = package_module("engine._review_wrapper_io")


def _alive(pid: int) -> bool:
    try:
        data = Path(f"/proc/{pid}/stat").read_bytes()
    except OSError:
        return False
    return WRAPPER.parse_proc_stat(data)[0] != "Z"


@dataclass(frozen=True)
class WrapperLaunchOptions:
    wrapper_source: str | None = None
    emit_claude_init: bool = True
    claude_init: dict[str, object] | None = None
    claude_options: tuple[str, ...] = ("--tools", "Read,Grep")


class WrapperHarness(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-review-streams-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.processes: list[subprocess.Popen[bytes]] = []
        self.addCleanup(self._cleanup_processes)

    def _cleanup_processes(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def launch(
        self,
        name: str,
        source: str,
        *,
        settings: tuple[str, float] = ("claude", 5.0),
        arguments: tuple[str, ...] = (),
        environment: dict[str, str] | None = None,
        options: WrapperLaunchOptions | None = None,
    ) -> tuple[subprocess.Popen[bytes], Path]:
        selected = options or WrapperLaunchOptions()
        provider, timeout = settings
        attempt = self.root / name
        attempt.mkdir(mode=0o700)
        prompt = b"candidate: " + b"1" * 64 + b"\npackage: " + b"2" * 64 + b"\n"
        prompt_path = attempt / "prompt.txt"
        prompt_path.write_bytes(prompt)
        prompt_path.chmod(0o600)
        argv = [sys.executable, "-I", "-c", source, *arguments]
        if provider == "claude":
            if not selected.claude_options:
                raise ValueError("Claude harness needs a --tools profile")
            event = selected.claude_init if selected.claude_init is not None else {
                "type": "system",
                "subtype": "init",
                "model": "fixture-model",
                "permissionMode": "default",
                "tools": ["Read", "Grep"],
            }
            prelude = (
                "import json as _forge_json, sys as _forge_sys\n"
                f"_forge_sys.argv = _forge_sys.argv[:-{len(selected.claude_options)}]\n"
            )
            if selected.emit_claude_init:
                prelude += (
                    f"print(_forge_json.dumps({event!r}), flush=True)\n"
                )
            argv = [
                sys.executable,
                "-I",
                "-c",
                prelude + source,
                *arguments,
                *selected.claude_options,
            ]
        child_environment = environment or {}
        config = {
            "attempt": f"attempt-{len(self.processes) + 1:016x}",
            "argv": argv,
            "argv_digest": WRAPPER._canonical_digest(argv),
            "prompt_digest": hashlib.sha256(prompt).hexdigest(),
            "provider": provider,
            "route_source": "committed-default",
            "route_sha256": "a" * 64,
            "sandbox": "read-only" if provider == "codex" else "instruction-bounded",
            "timeout": timeout,
            "grace": 1.0,
            "environment_names": sorted(child_environment),
            "omitted_short": [],
        }
        descriptor = os.open(attempt, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    selected.wrapper_source or WRAPPER.wrapper_source(),
                    str(descriptor),
                    json.dumps(config, sort_keys=True, separators=(",", ":")),
                ],
                env=child_environment,
                pass_fds=(descriptor,),
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        finally:
            os.close(descriptor)
        self.processes.append(process)
        return process, attempt

    def completion(self, process: subprocess.Popen[bytes], attempt: Path) -> dict[str, object]:
        path = attempt / "completion.json"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not path.exists():
            time.sleep(0.01)
        self.assertTrue(path.exists(), "wrapper did not publish completion")
        process.wait(timeout=10)
        return json.loads(path.read_text(encoding="utf-8"))

    def wait_identity(self, attempt: Path) -> dict[str, object]:
        path = attempt / "identity.json"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(0.01)
                continue
            if record.get("reviewer_pid") is not None:
                return record
            time.sleep(0.01)
        self.fail("wrapper did not publish reviewer identity")


@unittest.skipUnless(sys.platform.startswith("linux"), "process-group checks need Linux")
class ReviewLaunchStreamTests(WrapperHarness):
    def review_paths(self, label: str) -> object:
        attempt_name = f"attempt-{hashlib.sha256(label.encode()).hexdigest()[:16]}"
        attempt = self.root / label
        attempt.mkdir(mode=0o700)
        worktree = self.root / "worktree"
        plugin = self.root / "plugin"
        worktree.mkdir(exist_ok=True)
        plugin.mkdir(exist_ok=True)
        return LAUNCH.ReviewPaths(
            chain_id="c-review-stream-fixture",
            attempt=attempt_name,
            attempt_relative=f"review/iteration-01/{attempt_name}",
            attempt_dir=attempt,
            worktree=worktree,
            plugin_root=plugin,
            package_path=attempt / "package.txt",
            prompt_path=attempt / "prompt.txt",
            events_path=attempt / "events.jsonl",
            stderr_path=attempt / "stderr.log",
            identity_path=attempt / "identity.json",
            completion_path=attempt / "completion.json",
            verdict_path=attempt / "verdict.txt",
            staging_path=attempt / "verdict.staging",
            role_body_path=None,
            role_body=b"",
            role_body_digest=None,
        )

    def prepared_launch(
        self, label: str, source: str, timeout: int, grace: int
    ) -> object:
        environment = {"PATH": "/trusted/bin", "USER": "fixture-user"}
        route = LAUNCH.ReviewRoute(
            "review-cheap",
            "codex",
            "gpt-fixture",
            "high",
            "committed-default",
            "b" * 64,
            "read-only",
        )

        def digest(value: object) -> str:
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            return hashlib.sha256(encoded).hexdigest()

        context = SimpleNamespace(command_digest=digest)
        with (
            mock.patch.object(
                LAUNCH,
                "allowed_environment",
                return_value=(environment, tuple(sorted(environment)), ()),
            ),
            mock.patch.object(LAUNCH, "probe_provider_version", return_value="0.155.0"),
            mock.patch.object(
                LAUNCH,
                "reviewer_argv",
                return_value=[sys.executable, "-I", "-c", "raise SystemExit(0)"],
            ),
            mock.patch.object(LANE_API, "wrapper_source", return_value=source),
            mock.patch.dict(LAUNCH.PROFILE_TIMEOUT_SECONDS, {"review": timeout}),
            mock.patch.object(LAUNCH, "TERMINATE_GRACE_SECONDS", grace),
        ):
            return LAUNCH.prepare_review_launch(
                context,
                None,
                self.review_paths(label),
                route,
                b"candidate: " + b"1" * 64 + b"\npackage: " + b"2" * 64 + b"\n",
            )

    def test_committed_stream_and_deadline_bounds_are_pinned(self) -> None:
        self.assertEqual(WRAPPER.EVENTS_LIMIT_BYTES, 16 * 1024 * 1024)
        self.assertEqual(WRAPPER.STDERR_LIMIT_BYTES, 1024 * 1024)
        self.assertEqual(WRAPPER.VERDICT_LIMIT_BYTES, 65_536)
        self.assertEqual(WRAPPER.STREAM_DRAIN_SECONDS, 1.0)
        self.assertEqual(LAUNCH.PROFILE_TIMEOUT_SECONDS["review"], 2400)
        self.assertEqual(LAUNCH.IDENTITY_DEADLINE_SECONDS, 60)
        self.assertEqual(LAUNCH.VERSION_PROBE_TIMEOUT_SECONDS, 10)
        self.assertEqual(LAUNCH.VERSION_PROBE_LIMIT_BYTES, 4096)
        source = WRAPPER.wrapper_source()
        self.assertLess(len(source.encode()), 131_072)
        self.assertIn("def _drain_child", source)

    def test_production_launcher_binds_isolation_source_limits_and_environment(self) -> None:
        source = WRAPPER.wrapper_source()
        baseline = self.prepared_launch("prepared-a", source, 2400, 5)
        timeout = self.prepared_launch("prepared-b", source, 7, 5)
        grace = self.prepared_launch("prepared-c", source, 2400, 1)
        changed_source = self.prepared_launch("prepared-d", source + "\n# source mutant\n", 2400, 5)
        launches = (baseline, timeout, grace, changed_source)
        self.addCleanup(lambda: [LAUNCH.close_review_launch(item) for item in launches])

        def assert_isolated(launch: object) -> None:
            self.assertEqual(launch.launcher_argv[:4], (sys.executable, "-I", "-c", source))

        assert_isolated(baseline)
        mutant = SimpleNamespace(
            launcher_argv=(sys.executable, "-c", source, *baseline.launcher_argv[4:])
        )
        with self.assertRaises(AssertionError):
            assert_isolated(mutant)
        self.assertEqual(len({item.launcher_argv_digest for item in launches}), 4)
        config = json.loads(baseline.config_json)
        self.assertEqual((config["timeout"], config["grace"]), (2400, 5))

        sentinel = object()
        with mock.patch.object(LANE_API.subprocess, "Popen", return_value=sentinel) as popen:
            self.assertIs(LAUNCH.launch_review_wrapper(baseline), sentinel)
        popen.assert_called_once_with(
            list(baseline.launcher_argv),
            cwd=str(baseline.paths.worktree),
            env={"PATH": "/trusted/bin", "USER": "fixture-user"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            pass_fds=(baseline.attempt_fd,),
        )

    def test_reviewer_inherits_only_the_recorded_environment(self) -> None:
        child = SimpleNamespace(pid=4321)
        order: list[str] = []
        replace_json = mock.Mock(side_effect=lambda *_args: order.append("identity"))
        state = {
            "argv": ["provider", "--fixture"],
            "environment": {"ALLOWED": "recorded-value"},
            "identity": {},
            "birth_identity": lambda pid: {"pid": pid, "starttime": "fixture"},
            "replace_json": replace_json,
            "directory": 17,
            "publication_lock": WRAPPER.attempt_publication_lock,
        }

        def flock(_fd: int, mode: int) -> None:
            order.append("unlock" if mode == WRAPPER.fcntl.LOCK_UN else "lock")

        def spawn(*_args: object, **_kwargs: object) -> object:
            order.append("spawn")
            return child

        with (
            mock.patch.dict(os.environ, {"UNRECORDED": "must-not-pass"}),
            mock.patch.object(WRAPPER.fcntl, "flock", side_effect=flock),
            mock.patch.object(WRAPPER_IO.subprocess, "Popen", side_effect=spawn) as popen,
        ):
            self.assertIs(WRAPPER_IO._spawn_reviewer(state), child)
        popen.assert_called_once_with(
            ["provider", "--fixture"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            env={"ALLOWED": "recorded-value"},
        )
        self.assertEqual(order, ["lock", "spawn", "identity", "unlock"])
        self.assertEqual(state["identity"]["reviewer_pid"], 4321)
        replace_json.assert_called_once_with(17, "identity.json", state["identity"])

        blocked = mock.MagicMock()
        blocked.return_value.__enter__.return_value = False
        state["publication_lock"] = blocked
        with mock.patch.object(WRAPPER_IO.subprocess, "Popen") as popen:
            self.assertIsNone(WRAPPER_IO._spawn_reviewer(state))
        popen.assert_not_called()
        blocked.return_value.__enter__.return_value = True
        with self.assertRaises(AssertionError):
            with mock.patch.object(WRAPPER_IO.subprocess, "Popen", return_value=child) as disabled:
                WRAPPER_IO._spawn_reviewer(state)
                disabled.assert_not_called()

    def test_first_bad_line_is_terminal_for_both_providers(self) -> None:
        source = "import os; os.write(1, b'not-json\\n{\\\"type\\\":\\\"later\\\"}\\n')"
        for provider in ("codex", "claude"):
            with self.subTest(provider=provider):
                process, attempt = self.launch(
                    f"bad-{provider}",
                    source,
                    settings=(provider, 5.0),
                    environment={"CANARY": "not-json"},
                    options=WrapperLaunchOptions(emit_claude_init=False),
                )
                completion = self.completion(process, attempt)
                self.assertEqual(completion["error"], "bad line 1")
                self.assertIsNone(completion["returncode"])
                self.assertEqual(
                    (attempt / "events.jsonl").read_bytes(), b"<redacted:CANARY>\n"
                )

    def test_claude_init_mismatches_stop_early_with_the_closed_error(self) -> None:
        valid = {
            "type": "system",
            "subtype": "init",
            "model": "fixture-model",
            "permissionMode": "default",
            "tools": ["Read", "Grep"],
        }
        result_first = (
            "import json,sys;sys.stdin.read();"
            "print(json.dumps({'type':'result','is_error':False,"
            "'result':'VERDICT: PASS'}),flush=True)"
        )
        cases = (
            (
                "wrong-mode",
                "import time; time.sleep(300)",
                True,
                {**valid, "permissionMode": "default"},
                ("--tools", "Read,Grep", "--dangerously-skip-permissions"),
            ),
            (
                "missing-tool",
                "import time; time.sleep(300)",
                True,
                {**valid, "tools": ["Read"]},
                ("--tools", "Read,Grep"),
            ),
            (
                "missing-init",
                "pass",
                False,
                None,
                ("--tools", "Read,Grep"),
            ),
            (
                "result-first",
                result_first,
                False,
                None,
                ("--tools", "Read,Grep"),
            ),
        )
        for label, source, emit, event, options in cases:
            with self.subTest(case=label):
                started = time.monotonic()
                process, attempt = self.launch(
                    f"init-{label}",
                    source,
                    options=WrapperLaunchOptions(
                        emit_claude_init=emit,
                        claude_init=event,
                        claude_options=options,
                    ),
                )
                completion = self.completion(process, attempt)
                self.assertEqual(completion["error"], "claude init mismatch")
                self.assertIsNone(completion["returncode"])
                self.assertEqual(completion["verdict_size"], 0)
                self.assertLess(time.monotonic() - started, 3.0)

    def test_claude_init_checks_are_load_bearing_in_composed_source(self) -> None:
        source = """
import json, sys
sys.stdin.read()
print(json.dumps({'type':'result','is_error':False,
                  'result':'VERDICT: PASS'}), flush=True)
"""
        invalid = {
            "type": "system",
            "subtype": "init",
            "permissionMode": "default",
            "tools": ["Read", "Grep"],
        }

        def assert_rejected(label: str, wrapper_source: str | None = None) -> None:
            process, attempt = self.launch(
                label,
                source,
                options=WrapperLaunchOptions(
                    wrapper_source=wrapper_source,
                    claude_init=invalid,
                    claude_options=(
                        "--tools",
                        "Read,Grep",
                        "--dangerously-skip-permissions",
                    ),
                ),
            )
            completion = self.completion(process, attempt)
            self.assertEqual(completion["error"], "claude init mismatch")

        assert_rejected("init-composed")
        wrapper_source = WRAPPER.wrapper_source()
        anchor = "    return None if valid else CLAUDE_INIT_MISMATCH\n"
        self.assertEqual(wrapper_source.count(anchor), 1)
        disabled = wrapper_source.replace(anchor, "    return None\n", 1)
        with self.assertRaises(AssertionError):
            assert_rejected("init-composed-disabled", disabled)

    def test_claude_argv_guards_are_load_bearing_in_composed_source(self) -> None:
        cases = (
            (
                "duplicate-permission-same",
                ("--permission-mode", "acceptEdits", "--permission-mode",
                 "acceptEdits", "--tools", "Read,Grep"),
            ),
            (
                "duplicate-permission-different",
                ("--permission-mode", "acceptEdits", "--permission-mode",
                 "default", "--tools", "Read,Grep"),
            ),
            (
                "missing-permission-value",
                ("--tools", "Read,Grep", "--permission-mode"),
            ),
            (
                "empty-permission-value",
                ("--permission-mode", "", "--tools", "Read,Grep"),
            ),
            (
                "short-flag-permission-value",
                ("--permission-mode", "-p", "--tools", "Read,Grep"),
            ),
            ("missing-tools-value", ("--tools",)),
            ("empty-tools-value", ("--tools", "")),
            ("short-flag-tools-value", ("--tools", "-p")),
        )

        def assert_configuration_failure(
            label: str,
            claude_options: tuple[str, ...],
            wrapper_source: str | None = None,
        ) -> None:
            process, attempt = self.launch(
                label,
                "pass",
                options=WrapperLaunchOptions(
                    wrapper_source=wrapper_source,
                    claude_options=claude_options,
                ),
            )
            completion = self.completion(process, attempt)
            identity = json.loads(
                (attempt / "identity.json").read_text(encoding="utf-8")
            )
            self.assertEqual(completion["error"], "wrapper failure")
            self.assertIsNone(identity["reviewer_pid"])

        wrapper_source = WRAPPER.wrapper_source()
        anchor = '''def _claude_flag_value(
    argv: list[str], flag: str, *, required: bool
) -> str | None:
    count = argv.count(flag)
    if count > 1 or (required and count != 1):
        raise ValueError("launch configuration")
    if count == 0:
        return None
    index = argv.index(flag) + 1
    if index >= len(argv) or not argv[index] or argv[index].startswith("-"):
        raise ValueError("launch configuration")
    return argv[index]
'''
        replacement = '''def _claude_flag_value(
    argv: list[str], flag: str, *, required: bool
) -> str | None:
    if flag not in argv:
        return None
    index = argv.index(flag) + 1
    if index >= len(argv) or not argv[index] or argv[index].startswith("-"):
        return "Read,Grep" if flag == "--tools" else "acceptEdits"
    return argv[index]
'''
        self.assertEqual(wrapper_source.count(anchor), 1)
        disabled = wrapper_source.replace(anchor, replacement, 1)
        for label, claude_options in cases:
            with self.subTest(case=label):
                assert_configuration_failure(label, claude_options)
                with self.assertRaises(AssertionError):
                    assert_configuration_failure(
                        f"{label}-disabled", claude_options, disabled
                    )

    def test_missing_claude_init_check_is_load_bearing_in_memory(self) -> None:
        expectation = ("default", ("Read",))

        def assert_missing() -> None:
            self.assertEqual(
                WRAPPER._EventCapture([], expectation).final_error(),
                "claude init mismatch",
            )

        assert_missing()
        with (
            mock.patch.object(WRAPPER._EventCapture, "final_error", return_value=None),
            self.assertRaises(AssertionError),
        ):
            assert_missing()

    def test_missing_claude_init_check_is_load_bearing_in_composed_source(self) -> None:
        def assert_missing_rejected(
            label: str, wrapper_source: str | None = None
        ) -> None:
            process, attempt = self.launch(
                label,
                "pass",
                options=WrapperLaunchOptions(
                    wrapper_source=wrapper_source,
                    emit_claude_init=False,
                ),
            )
            completion = self.completion(process, attempt)
            self.assertEqual(completion["error"], "claude init mismatch")

        assert_missing_rejected("init-missing-composed")
        wrapper_source = WRAPPER.wrapper_source()
        anchor = (
            "    def final_error(self) -> str | None:\n"
            "        if self.claude_init is not None and self.line == 0:\n"
            "            return CLAUDE_INIT_MISMATCH\n"
            "        return None\n"
        )
        replacement = (
            "    def final_error(self) -> str | None:\n"
            "        return None\n"
        )
        self.assertEqual(wrapper_source.count(anchor), 1)
        disabled = wrapper_source.replace(anchor, replacement, 1)
        with self.assertRaises(AssertionError):
            assert_missing_rejected("init-missing-composed-disabled", disabled)

    def test_valid_json_precedes_raw_redaction_when_value_is_false(self) -> None:
        source = """
import json, sys
sys.stdin.read()
print(json.dumps({'type':'result','is_error':False,
                  'result':'VERDICT: PASS false'}), flush=True)
"""
        process, attempt = self.launch(
            "json-before-redaction", source, environment={"CANARY": "false"}
        )
        completion = self.completion(process, attempt)
        self.assertIsNone(completion["error"])
        event = json.loads((attempt / "events.jsonl").read_bytes().splitlines()[-1])
        self.assertIs(event["is_error"], False)
        self.assertEqual(event["result"], "VERDICT: PASS <redacted:CANARY>")

        payload = json.dumps({"type": "result", "is_error": False, "result": "false"}).encode()
        patterns = [(b"false", b"<redacted:CANARY>")]

        def assert_json_first() -> None:
            persisted: list[bytes] = []
            state = {
                "capture": WRAPPER._EventCapture(patterns),
                "stdout_redactor": WRAPPER._StreamRedactor(patterns),
                "stdout_buffer": bytearray(),
                "error": None,
                "persisting": True,
            }
            def write(_state: object, _label: str, data: bytes) -> bool:
                persisted.append(data)
                return True

            with mock.patch.object(WRAPPER_IO, "_persist_stream", side_effect=write):
                WRAPPER_IO._consume_stdout(state, payload + b"\n", final=True)
            self.assertIsNone(state["error"])
            self.assertIs(json.loads(b"".join(persisted))["is_error"], False)

        def raw_first(state: dict[str, Any], raw: bytes, terminated: bool) -> None:
            redacted = state["stdout_redactor"].feed(raw, final=True)
            persisted, error = state["capture"].line_bytes(redacted, terminated=terminated)
            if WRAPPER_IO._persist_stream(state, "stdout", persisted):
                state["error"] = error

        assert_json_first()
        with mock.patch.object(WRAPPER_IO, "_persist_stdout_line", raw_first):
            with self.assertRaises(AssertionError):
                assert_json_first()

    def test_both_stream_caps_publish_exact_error_and_kill_the_group(self) -> None:
        source = """
import os, pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(300)'])
pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding='ascii')
label, amount = sys.argv[2], int(sys.argv[3])
if label == 'stdout':
    os.write(1, b'{"type":"event","blob":"' + b'x' * amount + b'"}\\n')
else:
    os.write(2, b'x' * amount)
time.sleep(300)
"""
        cases = (
            ("stdout", WRAPPER.EVENTS_LIMIT_BYTES + 1, "events cap"),
            ("stderr", WRAPPER.STDERR_LIMIT_BYTES + 1, "stderr cap"),
        )
        for label, amount, expected in cases:
            with self.subTest(stream=label):
                marker = self.root / f"{label}.pid"
                process, attempt = self.launch(
                    f"cap-{label}", source, arguments=(str(marker), label, str(amount))
                )
                completion = self.completion(process, attempt)
                self.assertEqual(completion["error"], expected)
                self.assertIsNone(completion["returncode"])
                grandchild = int(marker.read_text(encoding="ascii"))
                deadline = time.monotonic() + 5
                while _alive(grandchild) and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertFalse(_alive(grandchild))

    def test_timeout_completion_is_durable_before_term_and_bytes_stop(self) -> None:
        marker = self.root / "term-observation.json"
        source = """
import json, pathlib, signal, sys, time
completion, events, marker = map(pathlib.Path, sys.argv[1:])
def term(_signum, _frame):
    marker.write_text(json.dumps({'completion': completion.exists(),
                                  'events': events.stat().st_size}), encoding='utf-8')
signal.signal(signal.SIGTERM, term)
print(json.dumps({'type':'system','subtype':'init','model':'stream-model'}), flush=True)
while True:
    time.sleep(1)
"""
        attempt = self.root / "timeout"
        process, attempt = self.launch(
            "timeout",
            source,
            settings=("claude", 1.0),
            arguments=(
                str(attempt / "completion.json"),
                str(attempt / "events.jsonl"),
                str(marker),
            ),
        )
        completion = self.completion(process, attempt)
        observed = json.loads(marker.read_text(encoding="utf-8"))
        self.assertTrue(completion["timed_out"])
        self.assertIsNone(completion["error"])
        self.assertTrue(observed["completion"])
        self.assertEqual(observed["events"], completion["events_bytes"])
        self.assertEqual((attempt / "events.jsonl").stat().st_size, completion["events_bytes"])

    def test_reviewer_exit_has_bounded_drain_then_sweeps_pipe_holder(self) -> None:
        marker = self.root / "pipe-holder.pid"
        source = """
import json, pathlib, subprocess, sys
child = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(300)'])
pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding='ascii')
sys.stdin.read()
print(json.dumps({'type':'result','is_error':False,'result':'VERDICT: PASS'}), flush=True)
"""
        started = time.monotonic()
        process, attempt = self.launch("bounded-drain", source, arguments=(str(marker),))
        completion = self.completion(process, attempt)
        elapsed = time.monotonic() - started
        self.assertIsNone(completion["error"])
        self.assertLess(elapsed, 3.0)
        child = int(marker.read_text(encoding="ascii"))
        deadline = time.monotonic() + 5
        while _alive(child) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(_alive(child))

    def test_external_term_leaves_completion_authority_to_canceller(self) -> None:
        source = "import sys,time; sys.stdin.read(); time.sleep(300)"
        process, attempt = self.launch("external-term", source, settings=("claude", 30))
        self.wait_identity(attempt)
        os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
        self.assertFalse((attempt / "completion.json").exists())
        self.assertNotIn("SIG_IGN", WRAPPER.wrapper_source())

    def test_pending_external_term_wins_shared_publication_race(self) -> None:
        order: list[str] = []
        operation = mock.Mock(side_effect=lambda: order.append("publish"))

        def exercise(pending: bool) -> bool:
            order.clear()
            operation.reset_mock()

            def flock(_fd: int, mode: int) -> None:
                order.append("unlock" if mode == WRAPPER.fcntl.LOCK_UN else "lock")

            def mask(how: int, _signals: object) -> set[signal.Signals]:
                order.append("block" if how == signal.SIG_BLOCK else "restore")
                return set()

            with (
                mock.patch.object(WRAPPER.fcntl, "flock", side_effect=flock),
                mock.patch.object(WRAPPER.signal, "pthread_sigmask", side_effect=mask),
                mock.patch.object(
                    WRAPPER.signal,
                    "sigpending",
                    side_effect=lambda: order.append("pending")
                    or ({signal.SIGTERM} if pending else set()),
                ),
                mock.patch.object(WRAPPER, "_EXTERNAL_TERM", False),
            ):
                return WRAPPER._publish_before_external_term(17, operation)

        self.assertFalse(exercise(True))
        operation.assert_not_called()
        self.assertEqual(order, ["lock", "block", "pending", "restore", "unlock"])
        with self.assertRaises(AssertionError):
            self.assertFalse(exercise(False))
        guard = mock.Mock(return_value=False)
        state = {"directory": 17, "publish_before_term": guard}
        self.assertFalse(WRAPPER_IO._publish_result(state, None, b"", None))
        guard.assert_called_once()

    def test_wrapper_failure_uses_shared_publication_guard(self) -> None:
        replace, guard = mock.Mock(), mock.Mock(return_value=False)
        with (
            mock.patch.multiple(
                WRAPPER,
                _read_leaf=mock.Mock(return_value=b'{"pgid":17}'),
                _completion=mock.Mock(return_value={"error": "wrapper failure"}),
                atomic_replace_json=replace,
                _terminate_group=mock.Mock(),
                _publish_before_external_term=guard,
                create=True,
            ),
            mock.patch.object(WRAPPER.os, "listdir", return_value=[]),
        ):
            WRAPPER._publish_wrapper_failure(17, {"grace": 5})
        guard.assert_called_once()
        replace.assert_not_called()

    def test_cap_control_is_load_bearing_in_memory(self) -> None:
        events = os.open(self.root / "unit-events", os.O_WRONLY | os.O_CREAT, 0o600)
        stderr = os.open(self.root / "unit-stderr", os.O_WRONLY | os.O_CREAT, 0o600)
        self.addCleanup(os.close, events)
        self.addCleanup(os.close, stderr)
        state = {
            "persisting": True,
            "limits": {"stdout": 3, "stderr": 3},
            "written": {"stdout": 0, "stderr": 0},
            "events_fd": events,
            "stderr_fd": stderr,
            "error": None,
        }

        def assert_cap() -> None:
            self.assertFalse(WRAPPER_IO._persist_stream(state, "stdout", b"four"))
            self.assertEqual(state["error"], "events cap")

        assert_cap()
        state.update(persisting=True, error=None)
        with mock.patch.object(WRAPPER_IO, "_persist_stream", return_value=True):
            with self.assertRaises(AssertionError):
                assert_cap()


if __name__ == "__main__":
    unittest.main()
