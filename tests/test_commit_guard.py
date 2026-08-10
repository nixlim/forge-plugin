from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT_GUARD = ROOT / "scripts" / "forge" / "commit-guard.sh"
MARKER_REASON = "forge: commit not authorized — run /forge:commit"


class CommitGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-commit-guard-")
        self.addCleanup(self.temp_dir.cleanup)
        self.scratch = Path(self.temp_dir.name)
        self.repo = self.scratch / "main checkout"
        self.init_repo(self.repo)

    def init_repo(self, path: Path) -> None:
        subprocess.run(
            ["git", "init", "--quiet", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.git("config", "user.name", "Forge Tests", cwd=path)
        self.git("config", "user.email", "forge-tests@example.invalid", cwd=path)
        self.git("symbolic-ref", "HEAD", "refs/heads/main", cwd=path)
        empty_tree = self.git("mktree", cwd=path, input_text="").stdout.strip()
        initial_commit = self.git(
            "commit-tree", empty_tree, cwd=path, input_text="scratch repository\n"
        ).stdout.strip()
        self.git("update-ref", "refs/heads/main", initial_commit, cwd=path)

    def git(
        self,
        *arguments: str,
        cwd: Path | None = None,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd or self.repo,
            input=input_text,
            check=True,
            capture_output=True,
            text=True,
        )

    def invoke(
        self,
        command: str,
        *,
        cwd: Path | None = None,
        tool_name: str = "Bash",
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(COMMIT_GUARD)],
            cwd=cwd or self.repo,
            input=json.dumps(
                {"tool_name": tool_name, "tool_input": {"command": command}}
            ),
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def assert_allowed(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def assert_denied(
        self,
        result: subprocess.CompletedProcess[str],
        reason: str,
    ) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            json.loads(result.stdout),
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
        )

    def track_manifest(self, *, cwd: Path | None = None) -> None:
        repo = cwd or self.repo
        (repo / ".forge-manifest").write_text(
            "forge_version: 1\ninit_completed: true\n", encoding="utf-8"
        )
        self.git("add", ".forge-manifest", cwd=repo)
        tree = self.git("write-tree", cwd=repo).stdout.strip()
        parent = self.git("rev-parse", "HEAD", cwd=repo).stdout.strip()
        commit = self.git(
            "commit-tree",
            tree,
            "-p",
            parent,
            cwd=repo,
            input_text="track forge manifest\n",
        ).stdout.strip()
        self.git("update-ref", "HEAD", commit, cwd=repo)

    def stage_change(self, *, cwd: Path | None = None, name: str = "change.txt") -> None:
        repo = cwd or self.repo
        (repo / name).write_text("reviewed change\n", encoding="utf-8")
        self.git("add", name, cwd=repo)

    def staged_hash(self, *, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=cwd or self.repo,
            check=True,
            capture_output=True,
        )
        return hashlib.sha256(result.stdout).hexdigest()

    def write_marker(
        self,
        *,
        cwd: Path | None = None,
        marker_root: Path | None = None,
        digest: str | None = None,
        timestamp: str | None = None,
        third_line: str | None = None,
    ) -> Path:
        root = marker_root or self.repo
        marker = root / ".forge" / "tmp" / "commit-authorized"
        marker.parent.mkdir(parents=True, exist_ok=True)
        reviewed_at = timestamp or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        lines = [digest or self.staged_hash(cwd=cwd), reviewed_at]
        if third_line is not None:
            lines.append(third_line)
        marker.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return marker

    def test_non_bash_and_irrelevant_bash_allow_silently(self) -> None:
        self.assert_allowed(self.invoke("git commit -m nope", tool_name="Read"))
        self.assert_allowed(self.invoke("printf '%s\\n' 'git commit'"))
        self.assert_allowed(self.invoke("bash -c 'git commit'"))

    def test_missing_stale_hash_mismatch_and_malformed_markers_are_denied(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        self.stage_change()
        marker = self.repo / ".forge" / "tmp" / "commit-authorized"
        stale_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=31)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        cases: list[tuple[str, str | None]] = [
            ("missing", None),
            ("malformed", "not-a-marker\n"),
            (
                "stale",
                f"{self.staged_hash()}\n{stale_timestamp}\n",
            ),
            (
                "hash mismatch",
                f"{'0' * 64}\n{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n",
            ),
        ]
        for failure, contents in cases:
            with self.subTest(failure=failure):
                if contents is None:
                    marker.unlink(missing_ok=True)
                else:
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.write_text(contents, encoding="utf-8")
                self.assert_denied(
                    self.invoke("git commit -m guarded"),
                    f"{MARKER_REASON} (marker {failure})",
                )

        audit = self.repo / ".forge" / "tmp" / "halt-audit.log"
        self.assertEqual(stat.S_IMODE(audit.stat().st_mode), 0o600)
        self.assertEqual(len(audit.read_text(encoding="utf-8").splitlines()), 4)

    def test_only_exact_two_and_three_line_marker_shapes_are_accepted(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        self.stage_change()

        self.write_marker()
        self.assert_allowed(self.invoke("git commit -m reviewed"))

        self.write_marker(third_line="skip: user-directed")
        self.assert_allowed(self.invoke("git commit -m user-directed"))

        for contents in (
            f"{self.staged_hash()}\n",
            f"{self.staged_hash()}\n2026-08-08T00:00:00Z\nunexpected\n",
            f"{self.staged_hash()}\n2026-08-08T00:00:00Z\nskip: user-directed\nextra\n",
            f"{'A' * 64}\n2026-08-08T00:00:00Z\n",
            f"{self.staged_hash()}\nnot-a-timestamp\n",
        ):
            with self.subTest(contents=contents):
                marker = self.repo / ".forge" / "tmp" / "commit-authorized"
                marker.write_text(contents, encoding="utf-8")
                self.assert_denied(
                    self.invoke("git commit"),
                    f"{MARKER_REASON} (marker malformed)",
                )

    def test_future_marker_timestamp_allows_only_clock_skew(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        self.stage_change()

        one_hour_ahead = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.write_marker(timestamp=one_hour_ahead)
        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker malformed)",
        )

        one_minute_ahead = (datetime.now(timezone.utc) + timedelta(seconds=60)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.write_marker(timestamp=one_minute_ahead)
        self.assert_allowed(self.invoke("git commit"))

    def test_working_tree_only_manifest_requires_marker(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        self.stage_change()

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_any_working_tree_manifest_entry_requires_marker(self) -> None:
        manifest = self.repo / ".forge-manifest"
        self.stage_change()

        manifest.mkdir()
        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )
        manifest.rmdir()

        manifest.symlink_to("missing-manifest-target")
        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_head_tracked_manifest_still_requires_marker_when_staged_for_deletion(self) -> None:
        self.track_manifest()
        (self.repo / ".forge-manifest").unlink()
        self.git("add", "-u", ".forge-manifest")

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_non_forge_repo_commit_and_push_pass_through(self) -> None:
        self.stage_change()

        self.assert_allowed(self.invoke("git commit -m ordinary"))
        self.assert_allowed(self.invoke("git push origin HEAD"))

    def test_all_required_command_forms_are_detected(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        self.stage_change()
        self.assert_allowed(self.invoke("env git status"))
        git_path = "/usr/bin/git" if Path("/usr/bin/git").is_file() else "git"
        cases = [
            (f"git -C {shlex_quote(self.repo)} commit", self.scratch),
            (f"{git_path} commit", self.repo),
            ("env A=b git commit", self.repo),
            ("env -i PATH=/usr/bin git commit -m x", self.repo),
            ("env -u FOO A=b git commit", self.repo),
            ("env env git commit", self.repo),
            ("env -0 -v -uFOO -C . -P /usr/bin A=b git commit", self.repo),
            ("env -S 'A=b -- git commit'", self.repo),
            (
                "env --ignore-environment --unset=FOO --chdir=. "
                "--null --block-signal PIPE "
                "--default-signal PIPE --ignore-signal INT "
                "--list-signal-handlers --debug --split-string='git commit'",
                self.repo,
            ),
            ("FOO=bar git commit", self.repo),
            (">/dev/null git commit", self.repo),
            ("> /dev/null git commit", self.repo),
            ("git 2>/dev/null commit", self.repo),
            (f"cd {shlex_quote(self.repo)} && git commit", self.scratch),
            ("printf before\ngit commit", self.repo),
            ("printf before | git commit", self.repo),
            ("true ; git commit", self.repo),
            ("false || git commit", self.repo),
            (
                "git -c core.pager=cat --git-dir=.git --work-tree=. --no-pager commit",
                self.repo,
            ),
            ("git --no-advice commit", self.repo),
        ]
        for command, cwd in cases:
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command, cwd=cwd),
                    f"{MARKER_REASON} (marker missing)",
                )

        tilde_environment = os.environ.copy()
        tilde_environment["HOME"] = str(self.scratch)
        self.assert_denied(
            self.invoke(
                "git -C ~/main\\ checkout commit",
                cwd=self.scratch,
                environment=tilde_environment,
            ),
            f"{MARKER_REASON} (marker missing)",
        )

        variable_environment = os.environ.copy()
        variable_environment["REPO"] = str(self.repo)
        for command, cwd in (
            ('git -C "$REPO" commit', self.scratch),
            ('cd "$REPO" && git commit', self.scratch),
            ('git -C "$PWD" commit', self.repo),
        ):
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command, cwd=cwd, environment=variable_environment),
                    f"{MARKER_REASON} (marker missing)",
                )

    def test_env_split_string_and_chdir_use_the_effective_git_context(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        self.stage_change()
        git_path = "/usr/bin/git" if Path("/usr/bin/git").is_file() else "git"

        for command in (
            "env -S 'git commit -m x'",
            "env -S 'env git commit -m x'",
            f"env -S 'A=b {git_path} commit -m x'",
        ):
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command),
                    f"{MARKER_REASON} (marker missing)",
                )
        self.assert_allowed(self.invoke("env -S 'git status'"))
        self.assert_allowed(self.invoke("env --split-string 'git status'"))

        for command in (
            "env --split-string 'git commit -m x'",
            "env --unset FOO git commit",
        ):
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command),
                    f"{MARKER_REASON} (marker missing)",
                )

        for command in (
            f"env -C {shlex_quote(self.repo)} git commit",
            f"env -C {shlex_quote(self.repo)} git -C . commit",
            f"env --chdir {shlex_quote(self.repo)} git commit",
        ):
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command, cwd=self.scratch),
                    f"{MARKER_REASON} (marker missing)",
                )

    def test_halt_precedes_marker_check_and_blocks_push_in_any_repo(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        (self.repo / "AGENT_HALT_commit").write_text("operator pause\n")

        for command in ("git commit", "git push origin HEAD"):
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command),
                    "forge: operator halt engaged (AGENT_HALT_commit)",
                )
        halt_audit = self.repo / ".forge" / "tmp" / "halt-audit.log"
        self.assertEqual(stat.S_IMODE(halt_audit.stat().st_mode), 0o600)

        other = self.scratch / "ordinary repo"
        self.init_repo(other)
        (other / "AGENT_HALT").write_text("global pause\n")
        self.assert_denied(
            self.invoke(f"git -C {shlex_quote(other)} push", cwd=self.scratch),
            "forge: operator halt engaged (AGENT_HALT)",
        )

        bare_parent = self.scratch / "bare parent"
        bare_parent.mkdir()
        bare_repo = bare_parent / "origin.git"
        subprocess.run(
            ["git", "init", "--bare", "--quiet", str(bare_repo)],
            check=True,
            capture_output=True,
            text=True,
        )
        (bare_parent / "AGENT_HALT").write_text("bare pause\n", encoding="utf-8")
        self.assert_denied(
            self.invoke(f"git -C {shlex_quote(bare_repo)} push", cwd=self.scratch),
            "forge: operator halt engaged (AGENT_HALT)",
        )

    def test_non_utf8_halt_contents_still_emit_a_deny(self) -> None:
        (self.repo / "AGENT_HALT").write_bytes(b"operator pause: \xff\n")
        self.assert_denied(
            self.invoke("git push origin HEAD"),
            "forge: operator halt engaged (AGENT_HALT)",
        )

    def test_block_audit_is_mode_600_truncated_and_redacts_secrets(self) -> None:
        (self.repo / "AGENT_HALT").write_text("pause\n")
        command = (
            "git push DB_PASSWORD=hunter2 OPENAI_API_KEY=api-secret-value "
            "BEARER_TOKEN=supersecretvalue bearer=othersecret "
            '"Authorization: Bearer bearer-secret-value" sk-supersecrettoken '
            "-----BEGIN PRIVATE KEY-----\nprivate-key-bytes\n"
            "-----END PRIVATE KEY----- "
            + "x" * 400
        )

        self.assert_denied(
            self.invoke(command),
            "forge: operator halt engaged (AGENT_HALT)",
        )

        audit = self.repo / ".forge" / "tmp" / "halt-audit.log"
        self.assertEqual(stat.S_IMODE(audit.stat().st_mode), 0o600)
        contents = audit.read_text(encoding="utf-8")
        for secret in (
            "hunter2",
            "api-secret-value",
            "supersecretvalue",
            "othersecret",
            "bearer-secret-value",
            "sk-supersecrettoken",
            "private-key-bytes",
        ):
            self.assertNotIn(secret, contents)
        guard_line = contents.splitlines()[-1]
        self.assertIn("executable=git deny=operator-halt", guard_line)
        self.assertIn("[REDACTED]", guard_line)
        self.assertIn("[REDACTED PEM BLOCK]", guard_line)
        excerpt = guard_line.split(" excerpt=", 1)[1]
        self.assertLessEqual(len(excerpt), 200)

    def test_linked_worktree_uses_main_checkout_marker_and_audit_root(self) -> None:
        self.track_manifest()
        linked = self.scratch / "linked worktree"
        self.git("worktree", "add", "--quiet", "-b", "linked", str(linked))
        self.stage_change(cwd=linked, name="linked.txt")

        main_marker = self.write_marker(cwd=linked, marker_root=self.repo)
        self.assert_allowed(self.invoke("git commit", cwd=linked))

        main_marker.unlink()
        self.write_marker(cwd=linked, marker_root=linked)
        self.assert_denied(
            self.invoke("git commit", cwd=linked),
            f"{MARKER_REASON} (marker missing)",
        )
        self.assertTrue((self.repo / ".forge/tmp/halt-audit.log").is_file())
        self.assertFalse((linked / ".forge/tmp/halt-audit.log").exists())

    def test_explicit_external_git_dir_and_work_tree_keep_repository_context(self) -> None:
        external_git_dir = self.scratch / "external admin.git"
        (self.repo / ".git").rename(external_git_dir)
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        command = (
            f"git --git-dir={shlex_quote(external_git_dir)} "
            f"--work-tree={shlex_quote(self.repo)} commit"
        )

        self.assert_denied(
            self.invoke(command, cwd=self.scratch),
            f"{MARKER_REASON} (marker missing)",
        )
        audit = self.scratch / ".forge/tmp/halt-audit.log"
        self.assertTrue(audit.is_file())
        self.assertEqual(stat.S_IMODE(audit.stat().st_mode), 0o600)

        (self.scratch / "AGENT_HALT").write_text("pause\n")
        push_command = command.rsplit(" ", 1)[0] + " push"
        self.assert_denied(
            self.invoke(push_command, cwd=self.scratch),
            "forge: operator halt engaged (AGENT_HALT)",
        )


def shlex_quote(value: Path) -> str:
    import shlex

    return shlex.quote(str(value))


if __name__ == "__main__":
    unittest.main()
