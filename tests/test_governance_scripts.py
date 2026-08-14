from __future__ import annotations

import os
import json
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK_HALT = ROOT / "scripts/forge/check-halt.sh"
ACQUIRE_LOCK = ROOT / "scripts/forge/acquire-commit-lock.sh"
RELEASE_LOCK = ROOT / "scripts/forge/release-commit-lock.sh"
EMIT_EVENT = ROOT / "scripts/forge/emit-decision-event.py"


class ScratchGitRepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-governance-")
        self.addCleanup(self.temp_dir.cleanup)
        self.scratch = Path(self.temp_dir.name)
        self.repo = self.scratch / "main checkout"

        subprocess.run(
            ["git", "init", "--quiet", str(self.repo)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.git("config", "user.name", "Forge Tests")
        self.git("config", "user.email", "forge-tests@example.invalid")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")

        # Create the fixture's initial commit with plumbing so the test suite
        # never invokes the porcelain commit command prohibited for this task.
        empty_tree = self.git("mktree", input_text="").stdout.strip()
        initial_commit = self.git(
            "commit-tree", empty_tree, input_text="scratch repository\n"
        ).stdout.strip()
        self.git("update-ref", "refs/heads/main", initial_commit)

    def git(
        self,
        *args: str,
        cwd: Path | None = None,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.repo,
            input=input_text,
            check=True,
            capture_output=True,
            text=True,
        )

    def run_script(
        self,
        script: Path,
        *args: str,
        cwd: Path | None = None,
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            ["bash", str(script), *args],
            cwd=cwd or self.repo,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )


class CheckHaltScriptTests(ScratchGitRepoTestCase):
    AUDIT_LINE = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z halt detected "
        r"\(pid [1-9]\d*, cwd .+, sentinel (?P<sentinel>AGENT_HALT(?:_[^)]+)?)\)$"
    )

    def tearDown(self) -> None:
        # check-halt deliberately returns the primary denial before its
        # advisory event worker finishes. Drain any worker touching the
        # scratch repository before TemporaryDirectory cleanup.
        events_lock = self.repo / ".forge/tmp/events.lock"
        deadline = time.monotonic() + 7
        while time.monotonic() < deadline:
            tmp = self.repo / ".forge/tmp"
            state_locks = list(tmp.glob("events.lock.state*"))
            pending = list(tmp.glob("halt-event-pending.*"))
            if not events_lock.exists() and not state_locks and not pending:
                time.sleep(0.03)
                if not events_lock.exists() and not list(tmp.glob("halt-event-pending.*")):
                    break
            time.sleep(0.01)
        super().tearDown()

    def audit_lines(self) -> list[str]:
        audit = self.repo / ".forge/tmp/halt-audit.log"
        return audit.read_text(encoding="utf-8").splitlines()

    def mutant_check_halt(self, name: str, needle: str, replacement: str) -> Path:
        source = CHECK_HALT.read_text(encoding="utf-8")
        self.assertEqual(source.count(needle), 1, f"mutation needle drifted: {name}")
        mutant = self.scratch / name / "check-halt.sh"
        mutant.parent.mkdir(parents=True)
        mutant.write_text(source.replace(needle, replacement), encoding="utf-8")
        mutant.chmod(0o755)
        return mutant

    def test_global_sentinel_halts_and_appends_contract_audit_lines(self) -> None:
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")

        first = self.run_script(CHECK_HALT)
        second = self.run_script(CHECK_HALT)

        self.assertEqual(first.returncode, 1, first.stderr)
        self.assertEqual(second.returncode, 1, second.stderr)
        self.assertIn("AGENT_HALT", first.stderr)
        lines = self.audit_lines()
        self.assertEqual(len(lines), 2, "halt auditing must be append-only")
        for line in lines:
            match = self.AUDIT_LINE.fullmatch(line)
            self.assertIsNotNone(match, line)
            self.assertEqual(match.group("sentinel"), "AGENT_HALT")

    def test_outside_git_warns_and_allows_progress(self) -> None:
        result = self.run_script(CHECK_HALT, cwd=self.scratch)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("warning: outside a git repository", result.stderr)

    def test_scoped_sentinel_only_halts_matching_scope(self) -> None:
        (self.repo / "AGENT_HALT_commit").write_text("pause commits\n", encoding="utf-8")

        unscoped = self.run_script(CHECK_HALT)
        scoped = self.run_script(CHECK_HALT, "commit")

        self.assertEqual(unscoped.returncode, 0, unscoped.stderr)
        self.assertEqual(scoped.returncode, 1, scoped.stderr)
        self.assertIn("AGENT_HALT_commit", scoped.stderr)
        lines = self.audit_lines()
        self.assertEqual(len(lines), 1)
        match = self.AUDIT_LINE.fullmatch(lines[0])
        self.assertIsNotNone(match, lines[0])
        self.assertEqual(match.group("sentinel"), "AGENT_HALT_commit")

    def test_halt_event_is_appended_after_primary_diagnostic(self) -> None:
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")
        (self.repo / "staged.txt").write_text("candidate\n", encoding="utf-8")
        self.git("add", "staged.txt")
        staged_diff = self.git("diff", "--cached").stdout
        expected_candidate = subprocess.run(
            ["shasum", "-a", "256"], input=staged_diff,
            capture_output=True, text=True, check=True,
        ).stdout.split()[0]
        expected_policy = self.git("rev-parse", "HEAD").stdout.strip()

        result = self.run_script(CHECK_HALT)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("forge: operator halt engaged", result.stderr)
        events = self.repo / ".forge/tmp/decisions/events.jsonl"
        deadline = time.monotonic() + 2
        while not events.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(events.exists(), "advisory halt event was not appended")
        item = json.loads(events.read_text(encoding="utf-8"))
        self.assertEqual(item["event"], "halt_event")
        self.assertEqual(item["candidate"], expected_candidate)
        self.assertEqual(item["policy_sha"], expected_policy)
        self.assertEqual(item["reason"], "AGENT_HALT")

    def test_real_event_and_audit_failures_preserve_halt_and_failure_code(self) -> None:
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")
        tmp = self.repo / ".forge/tmp"
        events = tmp / "decisions/events.jsonl"
        events.mkdir(parents=True)
        audit = tmp / "halt-audit.log"
        audit.mkdir()

        result = self.run_script(
            CHECK_HALT,
            env_overrides={"CLAUDE_PLUGIN_ROOT": str(ROOT)},
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("forge: operator halt engaged (AGENT_HALT)", result.stderr)
        deadline = time.monotonic() + 5
        failure_markers: list[Path] = []
        while time.monotonic() < deadline:
            failure_markers = list(tmp.glob("halt-event-failed.*"))
            if failure_markers:
                break
            time.sleep(0.01)
        self.assertEqual(len(failure_markers), 1)
        self.assertEqual(
            failure_markers[0].read_text(encoding="utf-8"),
            "forge: decision event append skipped (event-append-write-failed)\n",
        )
        self.assertTrue(events.is_dir())
        self.assertTrue(audit.is_dir())

    def test_fifo_directory_creation_failure_never_cleans_root_exit(self) -> None:
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")
        rm_trace = self.scratch / "rm-targets"
        bash_env = self.scratch / "fail-fifo-directory.bash"
        bash_env.write_text(
            "mktemp() {\n"
            '  if [[ "${1:-}" == "-d" && "${2:-}" == *forge-halt-exit.* ]]; then\n'
            "    return 1\n"
            "  fi\n"
            '  command mktemp "$@"\n'
            "}\n"
            "rm() {\n"
            '  printf "%s\\n" "$@" >>"${FORGE_TEST_RM_TRACE:?}"\n'
            '  command rm "$@"\n'
            "}\n",
            encoding="utf-8",
        )

        result = self.run_script(
            CHECK_HALT,
            env_overrides={
                "BASH_ENV": str(bash_env),
                "CLAUDE_PLUGIN_ROOT": str(ROOT),
                "FORGE_TEST_RM_TRACE": str(rm_trace),
            },
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr,
            "forge: operator halt engaged (AGENT_HALT)\n"
            "AI SDLC activity is paused. Do not start new work, commit, push, or\n"
            "perform external or irreversible actions. Sentinel reason (if given):\n"
            "----\noperator pause\n",
        )
        audit_lines = self.audit_lines()
        launch_failures = [
            line for line in audit_lines
            if "decision event append skipped (event-append-launch-failed)" in line
        ]
        self.assertEqual(len(launch_failures), 1)
        self.assertRegex(
            launch_failures[0],
            r"^\d{4}-\d{2}-\d{2}T.*Z forge: decision event append skipped "
            r"\(event-append-launch-failed\)$",
        )
        rm_targets = rm_trace.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any("forge-halt-staged." in target for target in rm_targets))
        self.assertNotIn("/exit", rm_targets)
        tmp = self.repo / ".forge/tmp"
        self.assertFalse(list(tmp.glob("halt-event-pending.*")))
        self.assertFalse(list(tmp.glob("halt-event-failed.*")))

    def test_missing_marker_with_healthy_emitter_audit_is_counted_once(self) -> None:
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")
        tmp = self.repo / ".forge/tmp"
        events = tmp / "decisions/events.jsonl"
        events.mkdir(parents=True)
        marker_open = """            try:
                marker_fd = os.open(
                    marker_path,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
"""
        mutant = self.mutant_check_halt(
            "healthy-emitter-audit-without-marker",
            marker_open,
            """            try:
                raise OSError("forced pending-marker creation failure")
                marker_fd = os.open(
                    marker_path,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
""",
        )

        result = self.run_script(
            mutant, env_overrides={"CLAUDE_PLUGIN_ROOT": str(ROOT)},
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr,
            "forge: operator halt engaged (AGENT_HALT)\n"
            "AI SDLC activity is paused. Do not start new work, commit, push, or\n"
            "perform external or irreversible actions. Sentinel reason (if given):\n"
            "----\noperator pause\n",
        )
        diagnostic = "decision event append skipped (code event-append-write-failed)"
        deadline = time.monotonic() + 5
        failures: list[str] = []
        while time.monotonic() < deadline:
            failures = [line for line in self.audit_lines() if diagnostic in line]
            if failures:
                break
            time.sleep(0.01)
        self.assertEqual(len(failures), 1)
        self.assertRegex(
            failures[0], r"^\d{4}-\d{2}-\d{2}T.*Z " + re.escape(diagnostic) + r"$"
        )
        self.assertFalse(list(tmp.glob("halt-event-pending.*")))
        self.assertFalse(list(tmp.glob("halt-event-failed.*")))
        self.assertTrue(events.is_dir())

    def test_marker_creation_and_emitter_failures_are_counted_without_changing_halt(self) -> None:
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")
        tmp = self.repo / ".forge/tmp"
        events = tmp / "decisions/events.jsonl"
        events.mkdir(parents=True)
        mutant = self.mutant_check_halt(
            "marker-create-failure",
            "if not pending:\n    pending_dir = Path(audit).parent",
            "if not pending:\n    raise_creation_failure = True\n    pending_dir = Path(audit).parent",
        )
        mutant_text = mutant.read_text(encoding="utf-8")
        needle = """            try:
                marker_fd = os.open(
                    marker_path,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
"""
        replacement = """            try:
                if raise_creation_failure:
                    raise_creation_failure = False
                    raise OSError("forced pending-marker creation failure")
                marker_fd = os.open(
                    marker_path,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
"""
        self.assertEqual(mutant_text.count(needle), 1)
        mutant.write_text(mutant_text.replace(needle, replacement), encoding="utf-8")
        plugin_root = self.scratch / "emitter-audit-failure"
        forge_scripts = plugin_root / "scripts/forge"
        shutil.copytree(ROOT / "scripts/forge", forge_scripts)
        emitter = forge_scripts / "emit-decision-event.py"
        emitter_text = emitter.read_text(encoding="utf-8")
        audit_open = """        descriptor = os.open(
            audit_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600
        )
"""
        self.assertEqual(emitter_text.count(audit_open), 1)
        emitter.write_text(
            emitter_text.replace(
                audit_open,
                '        raise OSError("forced emitter audit failure")\n',
            ),
            encoding="utf-8",
        )

        result = self.run_script(
            mutant,
            env_overrides={"CLAUDE_PLUGIN_ROOT": str(plugin_root)},
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("forge: operator halt engaged (AGENT_HALT)", result.stderr)
        deadline = time.monotonic() + 5
        diagnostic = "decision event append skipped (code event-append-write-failed)"
        while time.monotonic() < deadline:
            lines = self.audit_lines()
            if any(diagnostic in line for line in lines):
                break
            time.sleep(0.01)
        failures = [line for line in self.audit_lines() if diagnostic in line]
        self.assertEqual(len(failures), 1)
        self.assertRegex(failures[0], r"^\d{4}-\d{2}-\d{2}T.*Z " + re.escape(diagnostic) + r"$")
        self.assertFalse(list(tmp.glob("halt-event-pending.*")))
        self.assertFalse(list(tmp.glob("halt-event-failed.*")))

    def test_marker_path_substitution_does_not_touch_substitute_or_victim(self) -> None:
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")
        tmp = self.repo / ".forge/tmp"
        events = tmp / "decisions/events.jsonl"
        events.mkdir(parents=True)
        ready = self.scratch / "worker-ready"
        release = self.scratch / "worker-release"
        mutant = self.mutant_check_halt(
            "marker-path-substitution",
            "armed = b\"\"\nwhile True:",
            """Path(os.environ["FORGE_TEST_MARKER_READY"]).write_text("ready\\n")
while not Path(os.environ["FORGE_TEST_MARKER_RELEASE"]).exists():
    __import__("time").sleep(0.005)
armed = b""
while True:""",
        )
        env = os.environ.copy()
        env.update(
            CLAUDE_PLUGIN_ROOT=str(ROOT),
            FORGE_TEST_MARKER_READY=str(ready),
            FORGE_TEST_MARKER_RELEASE=str(release),
        )
        result = subprocess.run(
            ["bash", str(mutant)], cwd=self.repo, env=env,
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("forge: operator halt engaged (AGENT_HALT)", result.stderr)
        deadline = time.monotonic() + 3
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(ready.exists(), "detached worker did not reach substitution barrier")
        markers = list(tmp.glob("halt-event-pending.*"))
        self.assertEqual(len(markers), 1)
        marker = markers[0]
        birth_inode = self.scratch / "halt-marker-birth-inode"
        victim = self.scratch / "substitution-victim"
        victim.write_text("do not touch\n", encoding="utf-8")
        os.link(marker, birth_inode)
        marker.unlink()
        marker.symlink_to(victim)
        release.touch()

        expected = "forge: decision event append skipped (event-append-write-failed)\n"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if birth_inode.read_text(encoding="utf-8") == expected:
                break
            time.sleep(0.01)
        self.assertEqual(birth_inode.read_text(encoding="utf-8"), expected)
        self.assertTrue(marker.is_symlink())
        self.assertEqual(victim.read_text(encoding="utf-8"), "do not touch\n")
        self.assertFalse(list(tmp.glob("halt-event-failed.*")))
        marker.unlink()

    def test_halt_event_worker_waits_for_actual_parent_exit_beyond_two_seconds(self) -> None:
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")
        parent_held = self.scratch / "parent-held"
        bash_env = self.scratch / "hold-parent.bash"
        bash_env.write_text(
            "rmdir() {\n"
            '  : >"${FORGE_TEST_PARENT_HELD:?}"\n'
            "  sleep 2.5\n"
            '  command rmdir "$@"\n'
            "}\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.update(
            BASH_ENV=str(bash_env),
            CLAUDE_PLUGIN_ROOT=str(ROOT),
            FORGE_TEST_PARENT_HELD=str(parent_held),
        )
        process = subprocess.Popen(
            ["bash", str(CHECK_HALT)], cwd=self.repo, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.monotonic() + 2
        while not parent_held.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(parent_held.exists(), "halt process never reached the held-exit point")

        events = self.repo / ".forge/tmp/decisions/events.jsonl"
        time.sleep(2.1)
        self.assertIsNone(process.poll(), "halt process exited before the hold elapsed")
        self.assertFalse(events.exists(), "event was appended before the halt process exited")

        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 1, stderr)
        self.assertEqual(stdout, "")
        self.assertIn("forge: operator halt engaged (AGENT_HALT)", stderr)
        deadline = time.monotonic() + 3
        while not events.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(events.exists(), "event was not appended after actual parent exit")

    def test_linked_worktree_resolves_sentinel_and_audit_to_main_checkout(self) -> None:
        linked = self.scratch / "linked worktree"
        self.git("worktree", "add", "--quiet", "-b", "linked-test", str(linked))
        (self.repo / "AGENT_HALT").write_text("shared pause\n", encoding="utf-8")

        result = self.run_script(CHECK_HALT, cwd=linked)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue((self.repo / ".forge/tmp/halt-audit.log").is_file())
        self.assertFalse(
            (linked / ".forge/tmp/halt-audit.log").exists(),
            "linked worktrees must not receive private halt state",
        )
        self.assertEqual(
            self.AUDIT_LINE.fullmatch(self.audit_lines()[0]).group("sentinel"),
            "AGENT_HALT",
        )


class CommitLockScriptTests(ScratchGitRepoTestCase):
    @property
    def lock_file(self) -> Path:
        return self.repo / ".forge/tmp/commit-lock"

    def write_lock(self, owner_pid: int, timestamp: int | None = None) -> None:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file.write_text(
            f"{owner_pid} {timestamp if timestamp is not None else int(time.time())}\n",
            encoding="utf-8",
        )

    def test_stale_pid_lock_is_taken_over(self) -> None:
        self.write_lock(999_999_999, 1)
        session_pid = os.getpid()

        result = self.run_script(
            ACQUIRE_LOCK,
            env_overrides={"FORGE_SESSION_PID": str(session_pid)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("removing stale commit lock", result.stderr)
        record = self.lock_file.read_text(encoding="utf-8").strip()
        self.assertRegex(record, rf"^{session_pid} [0-9]+$")

        released = self.run_script(
            RELEASE_LOCK,
            env_overrides={"FORGE_SESSION_PID": str(session_pid)},
        )
        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertFalse(self.lock_file.exists())

    def test_explicit_event_lock_is_acquired_and_released(self) -> None:
        event_lock = self.repo / ".forge/tmp/events.lock"
        session_pid = os.getpid()

        acquired = self.run_script(
            ACQUIRE_LOCK,
            ".forge/tmp/events.lock",
            env_overrides={"FORGE_SESSION_PID": str(session_pid)},
        )

        self.assertEqual(acquired.returncode, 0, acquired.stderr)
        self.assertEqual(
            acquired.stdout.strip(),
            f"forge: event lock acquired (PID {session_pid})",
        )
        self.assertRegex(
            event_lock.read_text(encoding="utf-8").strip(),
            rf"^{session_pid} [0-9]+$",
        )
        released = self.run_script(
            RELEASE_LOCK,
            ".forge/tmp/events.lock",
            env_overrides={"FORGE_SESSION_PID": str(session_pid)},
        )
        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertFalse(event_lock.exists())

    def test_dead_event_lock_owner_is_recovered_on_acquisition(self) -> None:
        event_lock = self.repo / ".forge/tmp/events.lock"
        event_lock.parent.mkdir(parents=True)
        event_lock.write_text("999999999 1\n", encoding="utf-8")
        session_pid = os.getpid()

        acquired = self.run_script(
            ACQUIRE_LOCK,
            ".forge/tmp/events.lock",
            env_overrides={"FORGE_SESSION_PID": str(session_pid)},
        )

        self.assertEqual(acquired.returncode, 0, acquired.stderr)
        self.assertIn("forge: removing stale event lock", acquired.stderr)
        self.assertRegex(
            event_lock.read_text(encoding="utf-8").strip(),
            rf"^{session_pid} [0-9]+$",
        )
        released = self.run_script(
            RELEASE_LOCK,
            ".forge/tmp/events.lock",
            env_overrides={"FORGE_SESSION_PID": str(session_pid)},
        )
        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertFalse(event_lock.exists())

    def test_malformed_event_lock_owner_is_recovered_on_acquisition(self) -> None:
        event_lock = self.repo / ".forge/tmp/events.lock"
        event_lock.parent.mkdir(parents=True)
        session_pid = os.getpid()

        for malformed in ("", "0 1\n", "not-a-pid 1\n", "123 not-a-time\n", "123 1 extra\n"):
            with self.subTest(record=malformed):
                event_lock.write_text(malformed, encoding="utf-8")
                acquired = self.run_script(
                    ACQUIRE_LOCK,
                    ".forge/tmp/events.lock",
                    env_overrides={"FORGE_SESSION_PID": str(session_pid)},
                )

                self.assertEqual(acquired.returncode, 0, acquired.stderr)
                self.assertIn("forge: removing stale event lock", acquired.stderr)
                self.assertRegex(
                    event_lock.read_text(encoding="utf-8").strip(),
                    rf"^{session_pid} [0-9]+$",
                )
                released = self.run_script(
                    RELEASE_LOCK,
                    ".forge/tmp/events.lock",
                    env_overrides={"FORGE_SESSION_PID": str(session_pid)},
                )
                self.assertEqual(released.returncode, 0, released.stderr)
                self.assertFalse(event_lock.exists())

    def test_ownerless_event_state_mutex_gets_short_recovery_grace(self) -> None:
        event_state_guard = self.repo / ".forge/tmp/events.lock.state"
        event_state_guard.mkdir(parents=True)
        sleep_log = self.scratch / "sleep.log"
        real_sleep = shutil.which("sleep")
        self.assertIsNotNone(real_sleep)
        fake_bin = self.scratch / "fake-sleep-bin"
        fake_bin.mkdir()
        sleep_wrapper = fake_bin / "sleep"
        sleep_wrapper.write_text(
            "#!/usr/bin/env bash\n"
            'printf "%s\\n" "$1" >>"${FORGE_TEST_SLEEP_LOG:?}"\n'
            f"exec {shlex.quote(real_sleep or '')} \"$@\"\n",
            encoding="utf-8",
        )
        sleep_wrapper.chmod(0o755)

        acquired = self.run_script(
            ACQUIRE_LOCK,
            ".forge/tmp/events.lock",
            env_overrides={
                "FORGE_SESSION_PID": str(os.getpid()),
                "FORGE_TEST_SLEEP_LOG": str(sleep_log),
                "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            },
        )

        self.assertEqual(acquired.returncode, 0, acquired.stderr)
        self.assertEqual(sleep_log.read_text(encoding="utf-8").splitlines(), ["0.1"])
        self.assertIn("recovering ownerless event-lock state mutex", acquired.stderr)
        released = self.run_script(
            RELEASE_LOCK,
            ".forge/tmp/events.lock",
            env_overrides={"FORGE_SESSION_PID": str(os.getpid())},
        )
        self.assertEqual(released.returncode, 0, released.stderr)

    def test_explicit_event_lock_uses_hard_five_second_profile(self) -> None:
        event_lock = self.repo / ".forge/tmp/events.lock"
        event_lock.parent.mkdir(parents=True)
        event_lock.write_text(f"{os.getpid()} {int(time.time())}\n", encoding="utf-8")
        started = time.monotonic()

        result = self.run_script(
            ACQUIRE_LOCK,
            ".forge/tmp/events.lock",
            env_overrides={
                "FORGE_SESSION_PID": str(os.getppid()),
                "FORGE_COMMIT_LOCK_TIMEOUT": "1",
            },
        )

        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertGreaterEqual(elapsed, 4.5)
        self.assertLess(elapsed, 7)
        self.assertIn("another session is pruning events; waiting up to 5s", result.stderr)
        self.assertIn("failed to acquire event lock after 5s", result.stderr)

    def test_live_prune_lock_delays_emitter_then_append_is_lossless(self) -> None:
        event_lock = self.repo / ".forge/tmp/events.lock"
        holder = subprocess.Popen(["sleep", "10"])
        emitter: subprocess.Popen[str] | None = None
        try:
            acquired = self.run_script(
                ACQUIRE_LOCK,
                ".forge/tmp/events.lock",
                env_overrides={"FORGE_SESSION_PID": str(holder.pid)},
            )
            self.assertEqual(acquired.returncode, 0, acquired.stderr)

            policy_sha = self.git("rev-parse", "HEAD").stdout.strip()
            emitter = subprocess.Popen(
                [
                    "python3", str(EMIT_EVENT),
                    "--at", "2026-08-12T10:00:00Z",
                    "--candidate", "a" * 64,
                    "--event", "guard_deny",
                    "--policy-sha", policy_sha,
                    "--reason", "marker-missing",
                    "--surface", "commit-guard",
                ],
                cwd=self.repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            writer_dir = self.repo / ".forge/tmp/event-writers"
            deadline = time.monotonic() + 2
            while not writer_dir.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(writer_dir.exists(), "emitter did not reach writer registration")
            time.sleep(0.1)
            self.assertIsNone(emitter.poll(), "emitter did not wait for the live prune lock")
            expected_lock = f"{holder.pid} "
            self.assertTrue(
                event_lock.read_text(encoding="utf-8").startswith(expected_lock),
                "recovery helper disturbed the live prune lock",
            )
            events = self.repo / ".forge/tmp/decisions/events.jsonl"
            self.assertFalse(events.exists(), "emitter appended before prune-lock release")

            released_at = time.monotonic()
            released = self.run_script(
                RELEASE_LOCK,
                ".forge/tmp/events.lock",
                env_overrides={"FORGE_SESSION_PID": str(holder.pid)},
            )
            self.assertEqual(released.returncode, 0, released.stderr)
            stdout, stderr = emitter.communicate(timeout=5)
            self.assertEqual(emitter.returncode, 0, stderr)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "")
            self.assertLess(
                time.monotonic() - released_at,
                2,
                "emitter did not append promptly after prune-lock release",
            )

            records = [
                json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["candidate"], "a" * 64)
            self.assertFalse(
                (self.repo / ".forge/tmp/halt-audit.log").exists(),
                "successful lock handoff emitted an obsolete append-lock failure audit",
            )
        finally:
            if emitter is not None and emitter.poll() is None:
                emitter.terminate()
                emitter.wait(timeout=5)
            if holder.poll() is None:
                holder.terminate()
                holder.wait(timeout=5)

    def test_emitter_live_prune_lock_timeout_is_advisory_and_counted(self) -> None:
        """FR-157: bound live prune-lock waiting without changing the primary result."""
        event_lock = self.repo / ".forge/tmp/events.lock"
        holder = subprocess.Popen(["sleep", "30"])
        try:
            acquired = self.run_script(
                ACQUIRE_LOCK,
                ".forge/tmp/events.lock",
                env_overrides={"FORGE_SESSION_PID": str(holder.pid)},
            )
            self.assertEqual(acquired.returncode, 0, acquired.stderr)
            policy_sha = self.git("rev-parse", "HEAD").stdout.strip()

            started = time.monotonic()
            result = subprocess.run(
                [
                    "python3", str(EMIT_EVENT),
                    "--at", "2026-08-12T10:00:01Z",
                    "--candidate", "b" * 64,
                    "--event", "guard_deny",
                    "--policy-sha", policy_sha,
                    "--reason", "marker-missing",
                    "--surface", "commit-guard",
                ],
                cwd=self.repo,
                check=False,
                capture_output=True,
                text=True,
                timeout=7,
            )
            elapsed = time.monotonic() - started

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(
                result.stderr,
                "forge: decision event append skipped (event-append-lock-timeout)\n",
            )
            self.assertGreaterEqual(elapsed, 4.5)
            self.assertLess(elapsed, 7)
            self.assertTrue(
                event_lock.read_text(encoding="utf-8").startswith(f"{holder.pid} "),
                "emitter disturbed the live prune lock",
            )
            self.assertFalse((self.repo / ".forge/tmp/decisions/events.jsonl").exists())
            self.assertEqual(
                (self.repo / ".forge/tmp/halt-audit.log")
                .read_text(encoding="utf-8")
                .splitlines(),
                [
                    "2026-08-12T10:00:01Z decision event append skipped "
                    "(code event-append-lock-timeout)"
                ],
            )
        finally:
            if event_lock.exists() and holder.poll() is None:
                self.run_script(
                    RELEASE_LOCK,
                    ".forge/tmp/events.lock",
                    env_overrides={"FORGE_SESSION_PID": str(holder.pid)},
                )
            if holder.poll() is None:
                holder.terminate()
                holder.wait(timeout=5)

    def test_emitter_recovers_stale_event_lock_then_appends(self) -> None:
        event_lock = self.repo / ".forge/tmp/events.lock"
        event_lock.parent.mkdir(parents=True)
        policy_sha = self.git("rev-parse", "HEAD").stdout.strip()

        for index, stale_record in enumerate(("999999999 1\n", "malformed\n")):
            with self.subTest(record=stale_record):
                event_lock.write_text(stale_record, encoding="utf-8")
                result = subprocess.run(
                    [
                        "python3", str(EMIT_EVENT),
                        "--at", f"2026-08-12T10:01:0{index}Z",
                        "--candidate", f"{index + 1}" * 64,
                        "--event", "guard_deny",
                        "--policy-sha", policy_sha,
                        "--reason", "marker-missing",
                        "--surface", "commit-guard",
                    ],
                    cwd=self.repo,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")
                self.assertFalse(event_lock.exists())

        events = self.repo / ".forge/tmp/decisions/events.jsonl"
        records = [
            json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(records), 2)
        self.assertEqual([record["candidate"] for record in records], ["1" * 64, "2" * 64])
        self.assertFalse((self.repo / ".forge/tmp/halt-audit.log").exists())

    def test_emitter_lock_recovery_infrastructure_failure_is_advisory_and_counted(self) -> None:
        event_lock = self.repo / ".forge/tmp/events.lock"
        state_lock = self.repo / ".forge/tmp/events.lock.state.lock"
        event_lock.parent.mkdir(parents=True)
        event_lock.write_text("999999999 1\n", encoding="utf-8")
        state_lock.mkdir()
        policy_sha = self.git("rev-parse", "HEAD").stdout.strip()

        result = subprocess.run(
            [
                "python3", str(EMIT_EVENT),
                "--at", "2026-08-12T10:02:00Z",
                "--candidate", "c" * 64,
                "--event", "guard_deny",
                "--policy-sha", policy_sha,
                "--reason", "marker-missing",
                "--surface", "commit-guard",
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr.strip(),
            "forge: decision event append skipped (event-append-lock-recovery-failed)",
        )
        self.assertEqual(event_lock.read_text(encoding="utf-8"), "999999999 1\n")
        self.assertFalse((self.repo / ".forge/tmp/decisions/events.jsonl").exists())
        audit_lines = (
            self.repo / ".forge/tmp/halt-audit.log"
        ).read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            audit_lines,
            [
                "2026-08-12T10:02:00Z decision event append skipped "
                "(code event-append-lock-recovery-failed)"
            ],
        )

    def test_event_emitter_short_write_is_advisory_and_counted(self) -> None:
        mutant = self.scratch / "emit-decision-event-short-write.py"
        source = EMIT_EVENT.read_text(encoding="utf-8")
        needle = "written = os.write(descriptor, payload)\n"
        self.assertEqual(source.count(needle), 1)
        mutant.write_text(
            source.replace(needle, "written = os.write(descriptor, payload[:-1])\n"),
            encoding="utf-8",
        )

        policy_sha = self.git("rev-parse", "HEAD").stdout.strip()
        for second in range(2):
            result = subprocess.run(
                [
                    "python3", str(mutant),
                    "--at", f"2026-08-12T10:00:0{second}Z",
                    "--candidate", "b" * 64,
                    "--event", "guard_deny",
                    "--policy-sha", policy_sha,
                    "--reason", "marker-missing",
                    "--surface", "commit-guard",
                ],
                cwd=self.repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stderr.strip(),
                "forge: decision event append skipped (event-append-write-failed)",
            )

        audit_lines = (
            self.repo / ".forge/tmp/halt-audit.log"
        ).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(audit_lines), 2)
        self.assertTrue(
            all(
                line.endswith(
                    "decision event append skipped (code event-append-write-failed)"
                )
                for line in audit_lines
            )
        )

    def test_corrupt_event_lock_release_fails_closed(self) -> None:
        event_lock = self.repo / ".forge/tmp/events.lock"
        event_lock.parent.mkdir(parents=True)
        event_lock.write_text("corrupt\n", encoding="utf-8")

        result = self.run_script(
            RELEASE_LOCK,
            ".forge/tmp/events.lock",
            env_overrides={"FORGE_SESSION_PID": str(os.getpid())},
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr.strip(),
            "forge: corrupt event lock has no verifiable owner; refusing to release it",
        )
        self.assertTrue(event_lock.exists())

    def test_missing_event_lock_release_fails_closed(self) -> None:
        result = self.run_script(
            RELEASE_LOCK,
            ".forge/tmp/events.lock",
            env_overrides={"FORGE_SESSION_PID": str(os.getpid())},
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr.strip(),
            "forge: event lock is missing; ownership is unverifiable; refusing release",
        )

    def test_event_lock_release_cannot_unlink_cross_pid_replacement(self) -> None:
        event_lock = self.repo / ".forge/tmp/events.lock"
        state_lock = self.repo / ".forge/tmp/events.lock.state.lock"
        event_lock.parent.mkdir(parents=True)
        owner_a = os.getpid()
        owner_b_process = subprocess.Popen(["sleep", "10"])
        state_holder: subprocess.Popen[str] | None = None
        releaser: subprocess.Popen[str] | None = None
        try:
            event_lock.write_text(f"{owner_a} {int(time.time())}\n", encoding="utf-8")
            state_holder = subprocess.Popen(
                [
                    "python3",
                    "-c",
                    (
                        "import fcntl, sys; "
                        "f = open(sys.argv[1], 'a+'); "
                        "fcntl.flock(f, fcntl.LOCK_EX); "
                        "print('locked', flush=True); "
                        "sys.stdin.readline()"
                    ),
                    str(state_lock),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(state_holder.stdout.readline().strip(), "locked")
            environment = os.environ.copy()
            environment["FORGE_SESSION_PID"] = str(owner_a)
            releaser = subprocess.Popen(
                ["bash", str(RELEASE_LOCK), ".forge/tmp/events.lock"],
                cwd=self.repo,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(0.1)
            self.assertIsNone(releaser.poll(), "release did not wait on event state mutex")

            replacement = f"{owner_b_process.pid} {int(time.time())}\n"
            event_lock.write_text(replacement, encoding="utf-8")
            state_holder.communicate("\n", timeout=5)
            stdout, stderr = releaser.communicate(timeout=5)

            self.assertEqual(releaser.returncode, 1, stdout)
            self.assertIn(
                f"event lock is owned by PID {owner_b_process.pid}, not this session ({owner_a})",
                stderr,
            )
            self.assertIn("refusing to release a foreign event lock", stderr)
            self.assertEqual(event_lock.read_text(encoding="utf-8"), replacement)
        finally:
            if state_holder is not None and state_holder.poll() is None:
                state_holder.communicate("\n", timeout=5)
            if releaser is not None and releaser.poll() is None:
                releaser.terminate()
                releaser.wait(timeout=5)
            if owner_b_process.poll() is None:
                owner_b_process.terminate()
                owner_b_process.wait(timeout=5)

    def test_event_emitter_appends_exact_sorted_json_shape(self) -> None:
        result = subprocess.run(
            [
                "python3", str(EMIT_EVENT), "--at", "2026-08-12T10:00:00Z",
                "--candidate", "a" * 40, "--event", "gate_commit",
                "--policy-sha", "b" * 40, "--reason", "admitted",
                "--surface", "forge-commit",
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        line = (self.repo / ".forge/tmp/decisions/events.jsonl").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            line,
            '{"at":"2026-08-12T10:00:00Z","candidate":"' + "a" * 40 +
            '","event":"gate_commit","policy_sha":"' + "b" * 40 +
            '","reason":"admitted","surface":"forge-commit"}\n',
        )

    def test_event_emitter_uses_current_utc_when_at_is_omitted(self) -> None:
        result = subprocess.run(
            [
                "python3", str(EMIT_EVENT),
                "--candidate", "a" * 64, "--event", "guard_deny",
                "--policy-sha", "b" * 40, "--reason", "marker-missing",
                "--surface", "commit-guard",
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        item = json.loads(
            (self.repo / ".forge/tmp/decisions/events.jsonl").read_text(
                encoding="utf-8"
            )
        )
        self.assertRegex(
            item["at"],
            r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",
        )

    def test_event_emitter_accepts_all_thirteen_event_shapes(self) -> None:
        policy_sha = self.git("rev-parse", "HEAD").stdout.strip()
        event_shapes = (
            ("gate_commit", "a" * 40), ("fast_allowed", "b" * 40),
            ("fast_denied_policy", "c" * 64),
            ("fast_denied_eligibility", "d" * 64),
            ("user_skip", "e" * 64), ("review_block", "f" * 64),
            ("guard_deny", "1" * 64), ("halt_event", "2" * 64),
            ("assertion_blocking", "3" * 64),
            ("assertion_advisory", "4" * 64),
            ("assertion_waived", "5" * 64),
            ("review_cheap_finding", "6" * 64),
            ("review_final_finding", "7" * 64),
        )
        for index, (event, candidate) in enumerate(event_shapes):
            result = subprocess.run(
                [
                    "python3", str(EMIT_EVENT), "--at", f"2026-08-12T10:00:{index:02d}Z",
                    "--candidate", candidate, "--event", event,
                    "--policy-sha", policy_sha, "--reason", "decision",
                    "--surface", "fixture",
                ], cwd=self.repo, check=False, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        lines = (self.repo / ".forge/tmp/decisions/events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        items = [json.loads(line) for line in lines]
        self.assertEqual([item["event"] for item in items], [item[0] for item in event_shapes])
        for line, item, (_event, candidate) in zip(lines, items, event_shapes):
            self.assertEqual(
                set(item), {"at", "candidate", "event", "policy_sha", "reason", "surface"}
            )
            self.assertEqual(item["candidate"], candidate)
            self.assertNotIn(" ", line)

    def test_event_emitter_accepts_sha256_git_object_ids(self) -> None:
        result = subprocess.run(
            [
                "python3", str(EMIT_EVENT),
                "--candidate", "a" * 64, "--event", "gate_commit",
                "--policy-sha", "b" * 64, "--reason", "admitted",
                "--surface", "/forge:commit",
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        item = json.loads(
            (self.repo / ".forge/tmp/decisions/events.jsonl").read_text(encoding="utf-8")
        )
        self.assertEqual(item["candidate"], "a" * 64)
        self.assertEqual(item["policy_sha"], "b" * 64)

    def test_event_emitter_rejects_empty_success_candidate(self) -> None:
        result = subprocess.run(
            [
                "python3", str(EMIT_EVENT),
                "--candidate", "", "--event", "gate_commit",
                "--policy-sha", "b" * 40, "--reason", "admitted",
                "--surface", "/forge:commit",
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.repo / ".forge/tmp/decisions/events.jsonl").exists())

    def test_event_emitter_accepts_empty_gate_outcome_candidate(self) -> None:
        result = subprocess.run(
            [
                "python3", str(EMIT_EVENT),
                "--candidate", "", "--event", "review_block",
                "--policy-sha", "b" * 40, "--reason", "review-block",
                "--surface", "/forge:commit",
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        item = json.loads(
            (self.repo / ".forge/tmp/decisions/events.jsonl").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(item["event"], "review_block")
        self.assertEqual(item["candidate"], "")

    def test_event_emitter_rejects_empty_measurement_candidate(self) -> None:
        for event in (
            "assertion_blocking", "assertion_advisory", "assertion_waived",
            "review_cheap_finding", "review_final_finding",
        ):
            with self.subTest(event=event):
                result = subprocess.run(
                    [
                        "python3", str(EMIT_EVENT), "--candidate", "",
                        "--event", event, "--policy-sha", "b" * 40,
                        "--reason", "finding", "--surface", "/forge:commit",
                    ],
                    cwd=self.repo,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2)
        self.assertFalse((self.repo / ".forge/tmp/decisions/events.jsonl").exists())

    def test_concurrent_stale_takeover_has_exactly_one_winner(self) -> None:
        self.write_lock(999_999_999, 1)
        owners = [subprocess.Popen(["sleep", "10"]) for _ in range(2)]
        contenders: list[subprocess.Popen[str]] = []
        try:
            for owner in owners:
                env = os.environ.copy()
                env.update(
                    {
                        "FORGE_SESSION_PID": str(owner.pid),
                        "FORGE_COMMIT_LOCK_TIMEOUT": "1",
                    }
                )
                contenders.append(
                    subprocess.Popen(
                        ["bash", str(ACQUIRE_LOCK)],
                        cwd=self.repo,
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                )

            results = [contender.communicate(timeout=5) for contender in contenders]
            returncodes = sorted(contender.returncode for contender in contenders)
            self.assertEqual(returncodes, [0, 1], results)
            lock_owner = int(self.lock_file.read_text(encoding="utf-8").split()[0])
            self.assertIn(lock_owner, {owner.pid for owner in owners})
            self.assertFalse((self.lock_file.parent / "commit-lock.state").exists())
        finally:
            for contender in contenders:
                if contender.poll() is None:
                    contender.terminate()
                    contender.wait(timeout=5)
            for owner in owners:
                if owner.poll() is None:
                    owner.terminate()
                    owner.wait(timeout=5)

    def test_linked_worktree_shares_main_checkout_lock_authority(self) -> None:
        linked = self.scratch / "linked lock worktree"
        self.git("worktree", "add", "--quiet", "-b", "linked-lock-test", str(linked))
        holder = subprocess.Popen(["sleep", "10"])
        try:
            acquired = self.run_script(
                ACQUIRE_LOCK,
                env_overrides={"FORGE_SESSION_PID": str(holder.pid)},
            )
            self.assertEqual(acquired.returncode, 0, acquired.stderr)

            contender_pid = os.getpid()
            started = time.monotonic()
            blocked = self.run_script(
                ACQUIRE_LOCK,
                cwd=linked,
                env_overrides={
                    "FORGE_SESSION_PID": str(contender_pid),
                    "FORGE_COMMIT_LOCK_TIMEOUT": "1",
                },
            )
            elapsed = time.monotonic() - started

            self.assertEqual(blocked.returncode, 1, blocked.stderr)
            self.assertLess(elapsed, 4)
            self.assertIn("failed to acquire commit lock after 1s", blocked.stderr)
            self.assertIn(f"held by PID {holder.pid}", blocked.stderr)
            self.assertFalse(
                (linked / ".forge/tmp/commit-lock").exists(),
                "linked worktrees must not receive private commit-lock state",
            )

            foreign_release = self.run_script(
                RELEASE_LOCK,
                cwd=linked,
                env_overrides={"FORGE_SESSION_PID": str(contender_pid)},
            )
            self.assertEqual(foreign_release.returncode, 1, foreign_release.stderr)
            self.assertIn(
                "refusing to release a foreign commit lock", foreign_release.stderr
            )
            self.assertEqual(
                self.lock_file.read_text(encoding="utf-8").split()[0],
                str(holder.pid),
            )

            released = self.run_script(
                RELEASE_LOCK,
                env_overrides={"FORGE_SESSION_PID": str(holder.pid)},
            )
            self.assertEqual(released.returncode, 0, released.stderr)
            self.assertFalse(self.lock_file.exists())
        finally:
            if holder.poll() is None:
                holder.terminate()
                holder.wait(timeout=5)

    def test_unknown_path_format_output_falls_back_to_legacy_git(self) -> None:
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        fake_bin = self.scratch / "fake-bin"
        fake_bin.mkdir()
        git_wrapper = fake_bin / "git"
        git_wrapper.write_text(
            "#!/usr/bin/env bash\n"
            'if [[ "$*" == "rev-parse --path-format=absolute --git-common-dir" ]]; then\n'
            "  printf '%s\\n' '--path-format=absolute' '.git'\n"
            "  exit 0\n"
            "fi\n"
            f"exec {shlex.quote(real_git or '')} \"$@\"\n",
            encoding="utf-8",
        )
        git_wrapper.chmod(0o755)
        fallback_path = f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"

        acquired = self.run_script(
            ACQUIRE_LOCK,
            env_overrides={
                "FORGE_SESSION_PID": str(os.getpid()),
                "PATH": fallback_path,
            },
        )
        self.assertEqual(acquired.returncode, 0, acquired.stderr)

        released = self.run_script(
            RELEASE_LOCK,
            env_overrides={
                "FORGE_SESSION_PID": str(os.getpid()),
                "PATH": fallback_path,
            },
        )
        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertFalse(self.lock_file.exists())

    def test_orphaned_stale_state_mutex_is_recovered_within_poll_budget(self) -> None:
        state_guard = self.lock_file.parent / "commit-lock.state"
        state_guard.mkdir(parents=True)
        (state_guard / "owner").write_text("999999999 1\n", encoding="utf-8")
        session_pid = os.getpid()
        started = time.monotonic()

        result = self.run_script(
            ACQUIRE_LOCK,
            env_overrides={
                "FORGE_SESSION_PID": str(session_pid),
                "FORGE_COMMIT_LOCK_TIMEOUT": "3",
            },
        )

        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(
            elapsed,
            2,
            "a dead state-mutex owner must be recovered before one main-lock poll",
        )
        self.assertFalse(state_guard.exists())
        self.assertRegex(
            self.lock_file.read_text(encoding="utf-8").strip(),
            rf"^{session_pid} [0-9]+$",
        )

        released = self.run_script(
            RELEASE_LOCK,
            env_overrides={"FORGE_SESSION_PID": str(session_pid)},
        )
        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertFalse(self.lock_file.exists())

    def test_ownerless_state_mutex_is_recovered(self) -> None:
        state_guard = self.lock_file.parent / "commit-lock.state"
        state_guard.mkdir(parents=True)
        started = time.monotonic()

        result = self.run_script(
            ACQUIRE_LOCK,
            env_overrides={
                "FORGE_SESSION_PID": str(os.getpid()),
                "FORGE_COMMIT_LOCK_TIMEOUT": "3",
            },
        )

        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(elapsed, 2.5)
        self.assertIn("recovering ownerless commit-lock state mutex", result.stderr)
        self.assertFalse(state_guard.exists())

        released = self.run_script(
            RELEASE_LOCK,
            env_overrides={"FORGE_SESSION_PID": str(os.getpid())},
        )
        self.assertEqual(released.returncode, 0, released.stderr)

    def test_timeout_override_fails_with_holder_hint_and_preserves_lock(self) -> None:
        holder_pid = os.getpid()
        self.write_lock(holder_pid)
        started = time.monotonic()

        result = self.run_script(
            ACQUIRE_LOCK,
            env_overrides={
                "FORGE_SESSION_PID": str(os.getppid()),
                "FORGE_COMMIT_LOCK_TIMEOUT": "1",
            },
        )

        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertLess(elapsed, 4)
        self.assertIn("failed to acquire commit lock after 1s", result.stderr)
        self.assertIn(f"held by PID {holder_pid}", result.stderr)
        self.assertEqual(
            self.lock_file.read_text(encoding="utf-8").split()[0], str(holder_pid)
        )

    def test_release_refuses_foreign_owner(self) -> None:
        holder_pid = os.getpid()
        self.write_lock(holder_pid)

        result = self.run_script(
            RELEASE_LOCK,
            env_overrides={"FORGE_SESSION_PID": str(os.getppid())},
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("refusing to release a foreign commit lock", result.stderr)
        self.assertTrue(self.lock_file.exists())
        self.assertEqual(
            self.lock_file.read_text(encoding="utf-8").split()[0], str(holder_pid)
        )


if __name__ == "__main__":
    unittest.main()
