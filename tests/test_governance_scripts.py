from __future__ import annotations

import os
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

    def audit_lines(self) -> list[str]:
        audit = self.repo / ".forge/tmp/halt-audit.log"
        return audit.read_text(encoding="utf-8").splitlines()

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
