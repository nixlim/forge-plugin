from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
COMMIT_GUARD = ROOT / "scripts" / "forge" / "commit-guard.sh"
MARKER_REASON = "forge: commit not authorized — run /forge:commit"
GUARD_POLICY_MALFORMED = (
    "forge: guard-denied-commands policy malformed — repair committed "
    "forge-project.md"
)
GUARD_BOOTSTRAP_FAILURE = (
    "forge: commit guard internal failure — command was not classified "
    "(bootstrap); split the command"
)
DEPENDENCY_PATHS = (
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "requirements*.txt",
    "pyproject.toml",
    "poetry.lock",
    "uv.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "Gemfile",
    "Gemfile.lock",
    "pom.xml",
    "build.gradle*",
    "composer.json",
    "composer.lock",
)


class CommitGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-commit-guard-")
        self.addCleanup(self.temp_dir.cleanup)
        self.scratch = Path(self.temp_dir.name)
        self.repo = self.scratch / "main checkout"
        self.init_repo(self.repo)

    def tearDown(self) -> None:
        # Guard telemetry is deliberately detached from the primary denial.
        # Do not remove a scratch checkout while its advisory worker is using it.
        pending_dir = self.repo / ".forge/tmp"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            pending = list(pending_dir.glob("decision-event-pending.*"))
            if not pending:
                break
            time.sleep(0.01)
        super().tearDown()

    def wait_for_decision_workers(self, *, timeout: float = 5) -> None:
        pending_dir = self.repo / ".forge/tmp"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            active_pending = list(pending_dir.glob("decision-event-pending.*"))
            if not active_pending:
                # Avoid observing the unlink immediately before the event file's
                # directory entry becomes visible to this process.
                time.sleep(0.03)
                if not list(pending_dir.glob("decision-event-pending.*")):
                    return
            time.sleep(0.01)
        self.fail(f"decision-event worker did not finish: {active_pending}")

    def decision_failure_markers(self) -> list[Path]:
        return list((self.repo / ".forge/tmp").glob("decision-event-failed.*"))

    def wait_for_event_file(self, *, timeout: float = 5) -> Path:
        events = self.repo / ".forge/tmp/decisions/events.jsonl"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if events.stat().st_size:
                    return events
            except OSError:
                pass
            time.sleep(0.01)
        self.fail("decision-event worker did not write events.jsonl")

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
        guard: Path = COMMIT_GUARD,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(guard)],
            cwd=cwd or self.repo,
            input=json.dumps(
                {"tool_name": tool_name, "tool_input": {"command": command}}
            ),
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def mutant_guard(self, name: str, needle: str, replacement: str) -> Path:
        mutant_root = self.scratch / name
        shutil.copytree(ROOT / "scripts" / "forge", mutant_root / "scripts" / "forge")
        guard = mutant_root / "scripts" / "forge" / "commit-guard.sh"
        source = guard.read_text(encoding="utf-8")
        self.assertEqual(source.count(needle), 1, needle)
        guard.write_text(source.replace(needle, replacement), encoding="utf-8")
        return guard

    def base_guard(self) -> Path:
        base_root = self.scratch / "base-guard-tree"
        shutil.copytree(ROOT / "scripts" / "forge", base_root / "scripts" / "forge")
        shutil.copytree(ROOT / "system" / "fr223", base_root / "system" / "fr223")
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        source = subprocess.run(
            ["git", "show", "HEAD:scripts/forge/commit-guard.sh"],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
        ).stdout
        guard = base_root / "scripts" / "forge" / "commit-guard.sh"
        guard.write_bytes(source)
        return guard

    def fake_git_environment(self, name: str, body: str) -> dict[str, str]:
        fake_bin = self.scratch / name
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        fake_git.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = (
            f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"
        )
        return environment

    def load_guard_module(self, name: str) -> ModuleType:
        source = COMMIT_GUARD.read_text(encoding="utf-8")
        embedded = source.split("<<'PY' || true\n", 1)[1].split("\nPY\n", 1)[0]
        definitions = embedded.split("\ntry:\n    raise SystemExit(main())", 1)[0]
        self.addCleanup(sys.modules.pop, name, None)
        module = ModuleType(name)
        module.__file__ = str(COMMIT_GUARD)
        sys.modules[name] = module
        exec(compile(definitions, str(COMMIT_GUARD), "exec"), module.__dict__)
        return module

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
        expected = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        self.assertEqual(result.stdout, json.dumps(expected, ensure_ascii=False) + "\n")
        self.assertEqual(json.loads(result.stdout), expected)

    def track_manifest(self, *, cwd: Path | None = None) -> None:
        repo = cwd or self.repo
        (repo / ".forge-manifest").write_text(
            "forge_version: 1\nplugin_ref: test-plugin\ninit_completed: true\n",
            encoding="utf-8",
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

    def policy_text(
        self,
        *,
        fast_patterns: str = (
            "docs/**, .forge/history/**, .forge/evals/candidates/**, @formatting-only"
        ),
        triggers: str = "No trigger paths configured.",
        guard_denied_commands: str | None = None,
    ) -> str:
        dependencies = "\n".join(DEPENDENCY_PATHS)
        policy = f"""# Forge policy
<!-- FORGE:REGION file-categories BEGIN -->
| Category | File patterns |
|---|---|
| `docs` | `*.md`, `docs/**`, `.forge/evals/candidates/**` |
| `python` | `*.py`, `pyproject.toml` |
| `control` | `forge-project.md`, `.forge-manifest`, `.codex/**`, `.forge/evals/tasks/**`, `AGENTS.md`, `CLAUDE.md`, `.claude/settings*.json`, `.github/workflows/**` |
<!-- FORGE:REGION file-categories END -->
<!-- FORGE:REGION risk-tiers BEGIN -->
| tier | path patterns |
|---|---|
| fast | {fast_patterns} |
| standard | src/** |
| hard | forge-project.md |

| formatting-only category |
|---|
| docs |
<!-- FORGE:DEPENDENCY-MANIFEST-PATHS BEGIN -->
{dependencies}
<!-- FORGE:DEPENDENCY-MANIFEST-PATHS END -->
<!-- FORGE:REGION risk-tiers END -->
<!-- FORGE:REGION trigger-paths BEGIN -->
{triggers}
<!-- FORGE:REGION trigger-paths END -->
"""
        if guard_denied_commands is not None:
            policy += (
                "<!-- FORGE:REGION guard-denied-commands BEGIN -->\n"
                f"{guard_denied_commands}\n"
                "<!-- FORGE:REGION guard-denied-commands END -->\n"
            )
        return policy

    @staticmethod
    def guard_denied_body(*rows: tuple[str, str]) -> str:
        return "\n".join(
            (
                "| pattern | reason |",
                "|---|---|",
                *(f"| {pattern} | {reason} |" for pattern, reason in rows),
            )
        )

    @staticmethod
    def guard_denied_policy_bytes(body: str) -> bytes:
        return (
            "<!-- FORGE:REGION guard-denied-commands BEGIN -->\n"
            f"{body}\n"
            "<!-- FORGE:REGION guard-denied-commands END -->\n"
        ).encode("utf-8")

    def commit_policy(
        self,
        *,
        fast_patterns: str = (
            "docs/**, .forge/history/**, .forge/evals/candidates/**, @formatting-only"
        ),
        triggers: str = "No trigger paths configured.",
        guard_denied_commands: str | None = None,
        cwd: Path | None = None,
    ) -> str:
        repo = cwd or self.repo
        (repo / "forge-project.md").write_text(
            self.policy_text(
                fast_patterns=fast_patterns,
                triggers=triggers,
                guard_denied_commands=guard_denied_commands,
            ),
            encoding="utf-8",
        )
        (repo / ".forge-manifest").write_text(
            "forge_version: 1\nplugin_ref: test-plugin\ninit_completed: true\n",
            encoding="utf-8",
        )
        self.git("add", "forge-project.md", ".forge-manifest", cwd=repo)
        tree = self.git("write-tree", cwd=repo).stdout.strip()
        parent = self.git("rev-parse", "HEAD", cwd=repo).stdout.strip()
        commit = self.git(
            "commit-tree",
            tree,
            "-p",
            parent,
            cwd=repo,
            input_text="commit tier policy\n",
        ).stdout.strip()
        self.git("update-ref", "HEAD", commit, cwd=repo)
        return commit

    def stage_change(self, *, cwd: Path | None = None, name: str = "change.txt") -> None:
        repo = cwd or self.repo
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("reviewed change\n", encoding="utf-8")
        self.git("add", name, cwd=repo)

    def candidate_identity(
        self,
        *,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> tuple[str, str, str]:
        repo = cwd or self.repo
        object_format = subprocess.run(
            ["git", "rev-parse", "--show-object-format"],
            cwd=repo,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tree_oid = subprocess.run(
            ["git", "write-tree"],
            cwd=repo,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        preimage = (
            b"forge-commit-candidate/2\0"
            + object_format.encode("ascii")
            + b"\0"
            + tree_oid.encode("ascii")
            + b"\n"
        )
        return hashlib.sha256(preimage).hexdigest(), object_format, tree_oid

    def staged_hash(self, *, cwd: Path | None = None) -> str:
        return self.candidate_identity(cwd=cwd)[0]

    @staticmethod
    def marker_payload(
        candidate: str,
        object_format: str,
        tree_oid: str,
        timestamp: str,
        *annotations: str,
    ) -> str:
        return "\n".join(
            (
                "format: forge-commit-candidate/2",
                f"candidate: {candidate}",
                f"tree: {object_format}:{tree_oid}",
                f"authorized-at: {timestamp}",
                *annotations,
            )
        ) + "\n"

    def write_marker(
        self,
        *,
        cwd: Path | None = None,
        marker_root: Path | None = None,
        digest: str | None = None,
        timestamp: str | None = None,
        third_line: str | None = None,
        fourth_line: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> Path:
        root = marker_root or self.repo
        observed_digest, object_format, tree_oid = self.candidate_identity(
            cwd=cwd, environment=environment
        )
        marker_digest = digest or observed_digest
        marker = root / ".forge" / "tmp" / "authorized" / marker_digest
        marker.parent.mkdir(parents=True, exist_ok=True)
        reviewed_at = timestamp or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        annotations: list[str] = []
        if third_line is not None:
            annotations.append(third_line)
        if fourth_line is not None:
            annotations.append(fourth_line)
        marker.write_text(
            self.marker_payload(
                marker_digest,
                object_format,
                tree_oid,
                reviewed_at,
                *annotations,
            ),
            encoding="utf-8",
        )
        return marker

    def write_quarantine(self, marker: Path, *, produced: str | None = None) -> Path:
        quarantine = marker.with_name(f"{marker.name}.quarantine")
        produced_oid = produced or self.git("rev-parse", "HEAD").stdout.strip()
        quarantine.write_text(
            "format: forge-commit-candidate-quarantine/1\n"
            f"candidate: {marker.name}\n"
            f"produced: {produced_oid}\n"
            "reason: produced-commit-mismatch\n",
            encoding="ascii",
        )
        return quarantine

    def test_non_bash_and_irrelevant_bash_allow_silently(self) -> None:
        self.assert_allowed(self.invoke("git commit -m nope", tool_name="Read"))
        self.assert_allowed(self.invoke("printf '%s\\n' 'git commit'"))
        self.assert_allowed(self.invoke("bash -c 'git commit'"))

    def test_committed_guard_denylist_matches_resolved_token_prefix(self) -> None:
        reason = "force pushes require an operator-reviewed release path"
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(
                ("git push --force", reason),
            )
        )

        for command in (
            "git push --force origin main",
            "/usr/bin/env FORGE_TEST=1 /usr/bin/git -C . --no-pager "
            "push --force origin main",
            "printf x; git push --force origin main",
            "echo $(git push --force origin main)",
        ):
            with self.subTest(denied=command):
                self.assert_denied(
                    self.invoke(command),
                    f"forge: operator-denied command — {reason}",
                )

        for command in (
            "git push",
            "git push origin --force",
            "printf '%s\\n' 'git push --force origin main'",
            "sudo git push --force origin main",
            "command git push --force origin main",
            "bash -c 'git push --force origin main'",
        ):
            with self.subTest(allowed=command):
                self.assert_allowed(self.invoke(command))

    def test_guard_denylist_normalizes_bash_argv_before_prefix_matching(self) -> None:
        git_reason = "force pushes require an operator-reviewed release path"
        argument_reason = "the marker argument is operator-routed"
        octal_reason = "the decoded numeric argument is operator-routed"
        utf8_reason = "the decoded UTF-8 argument is operator-routed"
        control_reason = "the decoded control argument is operator-routed"
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(
                ("git push --force", git_reason),
                ("printf --flag marker", argument_reason),
                ("printf 777", octal_reason),
                ("printf é", utf8_reason),
                ("printf \x7f", control_reason),
            )
        )

        cases = (
            ("git>/dev/null push --force origin main", git_reason),
            ("git push --force>/dev/null", git_reason),
            ("printf --flag marker>/dev/null", argument_reason),
            ("g\\\nit push --force origin main", git_reason),
            ("git \\\npush \\\n--force origin main", git_reason),
            ("printf --flag mar\\\nker", argument_reason),
            ("$'git' push --force origin main", git_reason),
            ("git push $'--force' origin main", git_reason),
            ("printf --flag $'marker'", argument_reason),
            (r"printf $'\06777'", octal_reason),
            (r"printf $'\xc3\xa9'", utf8_reason),
            (r"printf $'\303\251'", utf8_reason),
            (r"printf $'\c?'", control_reason),
        )
        for command, reason in cases:
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command),
                    f"forge: operator-denied command — {reason}",
                )

        for command in (
            "git push --force</dev/null",
            "git push --force>>/dev/null",
            "git push --force 2>/dev/null",
            "git push --force&>/dev/null",
            "git push --force>&2",
            "git push --force<<<payload",
            "git push --force 3<>/dev/null",
            "git push --force 4<&0",
            "git push --force 5>>/dev/null",
            "git push --force {guard_fd}>/dev/null",
        ):
            with self.subTest(redirection=command):
                self.assert_denied(
                    self.invoke(command),
                    f"forge: operator-denied command — {git_reason}",
                )

        module = self.load_guard_module("forge_guard_denylist_argv_normalization")
        probes = (
            (
                "git push --force>/dev/null",
                [("git", "push", "--force")],
            ),
            (
                "git \\\npush \\\n--force origin main",
                [("git", "push", "--force", "origin", "main")],
            ),
            (
                "git push $'--force' origin main",
                [("git", "push", "--force", "origin", "main")],
            ),
            (r"printf $'\06777'", [("printf", "777")]),
            (r"printf $'\xc3\xa9'", [("printf", "é")]),
            (r"printf $'\303\251'", [("printf", "é")]),
            (r"printf $'\c?'", [("printf", "\x7f")]),
        )
        for command, expected in probes:
            with self.subTest(probe=command):
                self.assertEqual(module.find_direct_invocations(command), expected)

    def test_guard_denylist_preserves_quoted_redirection_and_continuation_text(
        self,
    ) -> None:
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(
                ("git commit -m a", "quoted comparison text"),
                ("echo --force", "quoted redirection text"),
                ("echo --forcemarker", "single-quoted continuation text"),
            )
        )
        (self.repo / ".forge-manifest").unlink()
        self.git("add", "-u", ".forge-manifest")
        tree = self.git("write-tree").stdout.strip()
        parent = self.git("rev-parse", "HEAD").stdout.strip()
        commit = self.git(
            "commit-tree",
            tree,
            "-p",
            parent,
            input_text="remove plugin activation manifest\n",
        ).stdout.strip()
        self.git("update-ref", "HEAD", commit)

        single_quoted_continuation = "echo '--force\\\nmarker'"
        commands = (
            'git commit -m "a>b"',
            "echo '--force>/dev/null'",
            single_quoted_continuation,
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(self.invoke(command))

        module = self.load_guard_module("forge_guard_denylist_quoted_text")
        expected = (
            ('git commit -m "a>b"', [("git", "commit", "-m", "a>b")]),
            (
                "echo '--force>/dev/null'",
                [("echo", "--force>/dev/null")],
            ),
            (
                single_quoted_continuation,
                [("echo", "--force\\\nmarker")],
            ),
        )
        for command, invocations in expected:
            with self.subTest(tokens=command):
                self.assertEqual(module.find_direct_invocations(command), invocations)

    def test_guard_denylist_unlexable_command_fails_closed(self) -> None:
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(
                ("echo guarded", "guarded echo"),
            )
        )
        self.assert_denied(self.invoke("echo 'unterminated"), GUARD_POLICY_MALFORMED)

    def test_guard_denylist_nonportable_ansi_c_quote_fails_closed(
        self,
    ) -> None:
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(
                ("git push --force", "force push is operator-routed"),
            )
        )
        environment = os.environ.copy()
        environment.update({"LC_ALL": "C", "LANG": "C"})
        commands = (
            r"printf $'\u00e9'",
            r"printf $'\u0061'",
            r"printf $'\U00000061'",
            (
                r"cat <<$'\u00e9'"
                "\nbody\n\\u00E9\ngit push --force origin main"
            ),
            (
                r"cat <<$'\u0061'"
                "\nbody\n\\u0061\ngit push --force origin main"
            ),
            (
                r"cat <<$'\U00000061'"
                "\nbody\n\\U00000061\ngit push --force origin main"
            ),
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command, environment=environment),
                    GUARD_POLICY_MALFORMED,
                )

    def test_guard_denylist_first_matching_row_supplies_reason(self) -> None:
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(
                ("git push", "all pushes are operator-routed"),
                ("git push --force", "force push specific reason"),
            )
        )

        self.assert_denied(
            self.invoke("git push --force origin main"),
            "forge: operator-denied command — all pushes are operator-routed",
        )

    def test_guard_denylist_excludes_heredoc_data_but_resumes_after_terminator(
        self,
    ) -> None:
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(
                ("rm -rf", "destructive removal is operator-routed"),
                ("git reset --hard", "hard reset is operator-routed"),
                ("git push --force", "force push is operator-routed"),
            )
        )
        data_only = (
            "python3 - <<'PY'\n"
            "rm -rf build\n"
            "git reset --hard\n"
            "PY\n"
            "printf '%s\\n' done"
        )
        tab_stripped = "python3 - <<-EOF\n\trm -rf build\n\tEOF\nprintf done"
        for command in (data_only, tab_stripped):
            with self.subTest(command=command):
                self.assert_allowed(self.invoke(command))
        self.assert_denied(
            self.invoke(data_only + "\nrm -rf build"),
            "forge: operator-denied command — destructive removal is operator-routed",
        )

        module = self.load_guard_module("forge_guard_denylist_heredoc_test")
        self.assertNotIn(("rm", "-rf", "build"), module.find_direct_invocations(data_only))
        self.assertNotIn(
            ("git", "reset", "--hard"), module.find_direct_invocations(data_only)
        )
        for opener in (
            "<<EOF",
            "<<'EOF'",
            '<<"EOF"',
            r"<<\EOF",
            "<<$'EOF'",
            r"<<$'E\x4fF'",
            '<<$"EOF"',
        ):
            command = f"python3 - {opener}\nrm -rf build\nEOF\nprintf done"
            with self.subTest(opener=opener):
                self.assertNotIn(
                    ("rm", "-rf", "build"),
                    module.find_direct_invocations(command),
                )
                self.assertIn(("printf", "done"), module.find_direct_invocations(command))
        empty_delimiter = "python3 - <<''\nrm -rf empty-data\n\nrm -rf real"
        empty_invocations = module.find_direct_invocations(empty_delimiter)
        self.assertNotIn(("rm", "-rf", "empty-data"), empty_invocations)
        self.assertIn(("rm", "-rf", "real"), empty_invocations)
        continued_delimiter = (
            "python3 - <<E\\\n"
            "OF\n"
            "rm -rf continued-data\n"
            "EOF\n"
            "rm -rf continued-real"
        )
        continued_invocations = module.find_direct_invocations(continued_delimiter)
        self.assertNotIn(("rm", "-rf", "continued-data"), continued_invocations)
        self.assertIn(("rm", "-rf", "continued-real"), continued_invocations)
        ansi_delimiter = (
            r"cat <<$'\06777'"
            "\nbody\n777\ngit push --force origin main"
        )
        self.assertIn(
            ("git", "push", "--force", "origin", "main"),
            module.find_direct_invocations(ansi_delimiter),
        )
        self.assert_denied(
            self.invoke(ansi_delimiter),
            "forge: operator-denied command — force push is operator-routed",
        )
        inexact_terminators = (
            "python3 - <<EOF\nrm -rf one\n EOF\nrm -rf two\nEOF\nprintf done"
        )
        self.assertNotIn(
            ("rm", "-rf", "two"),
            module.find_direct_invocations(inexact_terminators),
        )
        multiple = (
            "python3 - <<ONE 4<<TWO\n"
            "rm -rf first\nONE\n"
            "git reset --hard\nTWO\n"
            "printf done"
        )
        self.assertEqual(
            module.find_direct_invocations(multiple),
            [("python3", "-"), ("printf", "done")],
        )
        arithmetic = "printf $((1 << 2))\nrm -rf real"
        self.assertIn(("rm", "-rf", "real"), module.find_direct_invocations(arithmetic))
        unquoted_expansion = "cat <<EOF\n$(rm -rf expanded)\nEOF"
        multiline_expansion = "cat <<EOF\n$(\nrm -rf multiline\n)\nEOF"
        legacy_expansion = "cat <<EOF\n`rm -rf legacy`\nEOF"
        quoted_expansion = "cat <<'EOF'\n$(rm -rf quoted-data)\nEOF"
        escaped_expansion = r"cat <<EOF" + "\n" + r"\$(rm -rf escaped-data)" + "\nEOF"
        for command, expected in (
            (unquoted_expansion, ("rm", "-rf", "expanded")),
            (multiline_expansion, ("rm", "-rf", "multiline")),
            (legacy_expansion, ("rm", "-rf", "legacy")),
        ):
            with self.subTest(expanding=command):
                self.assertIn(expected, module.find_direct_invocations(command))
        for command in (quoted_expansion, escaped_expansion):
            with self.subTest(literal=command):
                self.assertFalse(
                    any(
                        invocation[:2] == ("rm", "-rf")
                        for invocation in module.find_direct_invocations(command)
                    )
                )
        self.assert_denied(
            self.invoke(unquoted_expansion),
            "forge: operator-denied command — destructive removal is operator-routed",
        )
        self.assert_allowed(self.invoke(quoted_expansion))
        with mock.patch.object(
            module,
            "_heredoc_expansion_view",
            side_effect=lambda raw: "".join(
                "\n" if char == "\n" else " " for char in raw
            ),
        ):
            self.assertNotIn(
                ("rm", "-rf", "expanded"),
                module.find_direct_invocations(unquoted_expansion),
            )
        with mock.patch.object(module, "without_heredoc_bodies", side_effect=lambda raw: raw):
            self.assertIn(
                ("rm", "-rf", "build"),
                module.find_direct_invocations(data_only),
            )

    def test_absent_guard_denylist_is_byte_identical_to_base_guard(self) -> None:
        self.commit_policy()
        base = self.base_guard()
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        environment.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "LC_ALL": "C",
                "LANG": "C",
            }
        )
        matrix = (
            ("printf '%s\\n' harmless", None),
            ("git push origin main", None),
            ("git commit -m guarded", f"{MARKER_REASON} (marker missing)"),
            (
                "python3 scripts/forge/cli.py commit approve",
                "forge: operator verb denied — present the candidate and ask the "
                "operator to run this via ! (commit approve)",
            ),
        )
        for command, expected_reason in matrix:
            with self.subTest(command=command):
                intact = self.invoke(command, environment=environment)
                baseline = self.invoke(
                    command,
                    environment=environment,
                    guard=base,
                )
                if expected_reason is None:
                    self.assert_allowed(intact)
                else:
                    self.assert_denied(intact, expected_reason)
                self.assertEqual(
                    (intact.returncode, intact.stdout, intact.stderr),
                    (baseline.returncode, baseline.stdout, baseline.stderr),
                )

    def test_guard_denylist_malformed_policy_fails_closed_for_every_command(self) -> None:
        malformed_bodies = {
            "bad table": "| command | reason |\n|---|---|\n| git push | nope |",
            "empty pattern": "| pattern | reason |\n|---|---|\n|  | operator note |",
            "multiline reason": (
                "| pattern | reason |\n|---|---|\n"
                "| git push | first line\nsecond line |"
            ),
        }
        for label, body in malformed_bodies.items():
            with self.subTest(policy=label):
                self.commit_policy(guard_denied_commands=body)
                for command in (
                    "printf '%s\\n' harmless",
                    "git push --force origin main",
                ):
                    self.assert_denied(self.invoke(command), GUARD_POLICY_MALFORMED)

    def test_guard_denylist_parser_enforces_exact_grammar_and_bounds(self) -> None:
        module = self.load_guard_module("forge_guard_denylist_policy_bounds_test")

        def parse(body: str) -> tuple[object, ...]:
            return module.parse_guard_denied_policy(
                self.guard_denied_policy_bytes(body)
            )

        exact_pattern = "é" * 2048
        exact_reason = "r" * 4096
        rules = parse(self.guard_denied_body((exact_pattern, exact_reason)))
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].pattern, (exact_pattern,))
        self.assertEqual(rules[0].reason, exact_reason)
        sixty_four = " ".join(f"p{index}" for index in range(64))
        self.assertEqual(
            len(parse(self.guard_denied_body((sixty_four, "bounded")))[0].pattern),
            64,
        )

        large_rows = tuple(
            (
                f"{index:03d}" + "x" * 4093,
                "r" * 4096,
            )
            for index in range(256)
        )
        large_policy = self.guard_denied_body(*large_rows)
        self.assertGreater(len(large_policy.encode("utf-8")), 2 * 1024 * 1024)
        self.assertEqual(len(parse(large_policy)), 256)

        invalid_bodies = (
            "|pattern|reason|\n|---|---|\n| git push | note |",
            "| pattern|reason |\n|---|---|\n| git push | note |",
            "| pattern | reason |\n| --- | --- |\n| git push | note |",
            self.guard_denied_body((" ".join("x" for _ in range(65)), "note")),
            self.guard_denied_body((("é" * 2048) + "x", "note")),
            self.guard_denied_body(("git push", "r" * 4097)),
            self.guard_denied_body(*((f"cmd {index}", "note") for index in range(257))),
            self.guard_denied_body(
                ("git push", "first"),
                ("git   push", "duplicate parsed tuple"),
            ),
            "| pattern | reason |\n|---|---|\n| 'git push | note |",
            "| pattern | reason |\n|---|---|",
        )
        for body in invalid_bodies:
            with self.subTest(body=body[:80]):
                with self.assertRaises(module.GuardDeniedPolicyError):
                    parse(body)

        for bad_byte in (b"\r", b"\x00", b"\xff"):
            policy = (
                b"<!-- FORGE:REGION guard-denied-commands BEGIN -->\n"
                b"| pattern | reason |\n|---|---|\n| git push | note "
                + bad_byte
                + b" |\n<!-- FORGE:REGION guard-denied-commands END -->\n"
            )
            with self.subTest(bad_byte=bad_byte):
                with self.assertRaises(module.GuardDeniedPolicyError):
                    module.parse_guard_denied_policy(policy)

        malformed_markers = (
            b"<!-- FORGE:REGION guard-denied-commands BEGIN -->\n",
            (
                b"<!-- FORGE:REGION guard-denied-commands BEGIN -->\n"
                b"<!-- FORGE:REGION guard-denied-commands BEGIN -->\n"
                b"<!-- FORGE:REGION guard-denied-commands END -->\n"
            ),
            b"prefix FORGE:REGION guard-denied-commands suffix\n",
        )
        for policy in malformed_markers:
            with self.subTest(policy=policy):
                with self.assertRaises(module.GuardDeniedPolicyError):
                    module.parse_guard_denied_policy(policy)

    def test_guard_denylist_committed_policy_read_has_absent_error_tristate(self) -> None:
        module = self.load_guard_module("forge_guard_denylist_source_state_test")
        context = mock.sentinel.context
        policy_sha = "a" * 40
        body = self.guard_denied_body(("git push", "operator routed"))
        policy = self.guard_denied_policy_bytes(body)

        resolved_head = module.GuardDeniedHeadResolution(
            state="resolved", policy_sha=policy_sha
        )
        with mock.patch.object(
            module, "guard_denied_head_policy", return_value=resolved_head
        ):
            with mock.patch.object(
                module,
                "run_context_git",
                return_value=subprocess.CompletedProcess(
                    [], 0, b"100644 blob " + (b"b" * 40) + b"\tforge-project.md\x00", b""
                ),
            ):
                with mock.patch.object(
                    module, "committed_policy", return_value=policy
                ) as committed:
                    resolved_sha, rules, error = module.committed_guard_denied_rules(
                        context
                    )
        self.assertEqual(resolved_sha, policy_sha)
        self.assertEqual(rules[0].pattern, ("git", "push"))
        self.assertIsNone(error)
        committed.assert_called_once_with(context, policy_sha)

        with mock.patch.object(
            module, "guard_denied_head_policy", return_value=resolved_head
        ):
            with mock.patch.object(
                module,
                "run_context_git",
                return_value=subprocess.CompletedProcess([], 0, b"", b""),
            ):
                self.assertEqual(
                    module.committed_guard_denied_rules(context),
                    (policy_sha, (), None),
                )
            with mock.patch.object(
                module,
                "run_context_git",
                return_value=subprocess.CompletedProcess([], 70, b"", b"failure"),
            ):
                self.assertEqual(
                    module.committed_guard_denied_rules(context),
                    (policy_sha, (), module.GUARD_DENIED_MALFORMED),
                )
            with mock.patch.object(module, "run_context_git", side_effect=OSError):
                self.assertEqual(
                    module.committed_guard_denied_rules(context),
                    (policy_sha, (), module.GUARD_DENIED_MALFORMED),
                )
            for unexpected in (
                b"040000 tree " + (b"b" * 40) + b"\tforge-project.md\x00",
                b"100644 blob bad\tforge-project.md\x00",
                b"100644 blob " + (b"b" * 40) + b"\tother.md\x00",
            ):
                with self.subTest(unexpected=unexpected):
                    with mock.patch.object(
                        module,
                        "run_context_git",
                        return_value=subprocess.CompletedProcess(
                            [], 0, unexpected, b""
                        ),
                    ):
                        self.assertEqual(
                            module.committed_guard_denied_rules(context),
                            (policy_sha, (), module.GUARD_DENIED_MALFORMED),
                        )
            exact_entry = b"100644 blob " + (b"b" * 40) + b"\tforge-project.md\x00"
            with mock.patch.object(
                module,
                "run_context_git",
                return_value=subprocess.CompletedProcess([], 0, exact_entry, b""),
            ):
                with mock.patch.object(module, "committed_policy", return_value=None):
                    self.assertEqual(
                        module.committed_guard_denied_rules(context),
                        (policy_sha, (), module.GUARD_DENIED_MALFORMED),
                    )
        with mock.patch.object(
            module,
            "guard_denied_head_policy",
            return_value=module.GuardDeniedHeadResolution(state="unborn"),
        ):
            self.assertEqual(
                module.committed_guard_denied_rules(context),
                ("", (), None),
            )
        with mock.patch.object(
            module,
            "guard_denied_head_policy",
            return_value=module.GuardDeniedHeadResolution(state="operational"),
        ):
            self.assertEqual(
                module.committed_guard_denied_rules(context),
                ("", (), module.GUARD_DENIED_MALFORMED),
            )

    def test_guard_denylist_policy_read_failure_denies_but_missing_file_is_noop(
        self,
    ) -> None:
        self.track_manifest()
        self.assert_allowed(self.invoke("printf '%s\\n' harmless"))

        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        fake_bin = self.scratch / "fake-bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/bin/sh\n"
            "case \" $* \" in\n"
            "  *\" --no-replace-objects ls-tree \"*) exit 70 ;;\n"
            "esac\n"
            f"exec {shlex.quote(real_git or 'git')} \"$@\"\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"
        self.assert_denied(
            self.invoke("printf '%s\\n' harmless", environment=environment),
            GUARD_POLICY_MALFORMED,
        )

        unborn = self.scratch / "unborn"
        self.git("init", "--quiet", str(unborn))
        self.git("symbolic-ref", "HEAD", "refs/heads/main", cwd=unborn)
        self.assert_allowed(
            self.invoke("printf '%s\\n' harmless", cwd=unborn)
        )

    def test_guard_denylist_repository_context_launch_failure_fails_closed(
        self,
    ) -> None:
        isolated_bin = self.scratch / "git-launch-failure-bin"
        isolated_bin.mkdir()
        for executable in ("bash", "dirname", "python3"):
            resolved = shutil.which(executable)
            self.assertIsNotNone(resolved)
            (isolated_bin / executable).symlink_to(Path(resolved or executable).resolve())
        environment = os.environ.copy()
        environment["PATH"] = str(isolated_bin)

        self.assert_denied(
            self.invoke("printf harmless", environment=environment),
            GUARD_POLICY_MALFORMED,
        )

    def test_guard_denylist_unclassified_repository_failure_fails_closed(
        self,
    ) -> None:
        environment = self.fake_git_environment(
            "unclassified-repository-failure-bin",
            "case \" $* \" in\n"
            "  *\" rev-parse --is-bare-repository \"*) printf '%s\\n' false ;;\n"
            "  *\" rev-parse --show-toplevel \"*)\n"
            "    printf '%s\\n' 'fatal: repository discovery failed' >&2\n"
            "    exit 128\n"
            "    ;;\n"
            "  *) exit 70 ;;\n"
            "esac\n",
        )
        self.assert_denied(
            self.invoke("printf harmless", environment=environment),
            GUARD_POLICY_MALFORMED,
        )

    def test_guard_denylist_git_config_read_failure_fails_closed(self) -> None:
        environment = os.environ.copy()
        environment["GIT_CONFIG_GLOBAL"] = os.sep
        self.assert_denied(
            self.invoke("printf harmless", environment=environment),
            GUARD_POLICY_MALFORMED,
        )

    def test_guard_denylist_undecodable_git_failure_uses_malformed_denial(
        self,
    ) -> None:
        environment = self.fake_git_environment(
            "undecodable-git-failure-bin",
            "printf '\\377' >&2\n"
            "exit 128\n",
        )
        self.assert_denied(
            self.invoke("printf harmless", environment=environment),
            GUARD_POLICY_MALFORMED,
        )

    def test_guard_denylist_determinate_non_repository_is_compatibility_noop(
        self,
    ) -> None:
        environment = self.fake_git_environment(
            "determinate-non-repository-bin",
            "if [ \"${LC_ALL-}:${LANG-}\" != C:C ]; then\n"
            "  printf '%s\\n' 'fatal: locale was not pinned' >&2\n"
            "  exit 70\n"
            "fi\n"
            "case \" $* \" in\n"
            "  *\" rev-parse --is-bare-repository \"*|"
            "*\" rev-parse --show-toplevel \"*)\n"
            "    printf '%s\\n' 'fatal: not a git repository (or any of the parent directories): .git' >&2\n"
            "    exit 128\n"
            "    ;;\n"
            "  *) exit 70 ;;\n"
            "esac\n",
        )
        outside = self.scratch / "outside-repository"
        outside.mkdir()
        environment["GIT_CEILING_DIRECTORIES"] = str(self.scratch)
        self.assert_allowed(
            self.invoke(
                "printf harmless",
                cwd=outside,
                environment=environment,
            )
        )

    def test_guard_denylist_repository_ceiling_matches_git_discovery(
        self,
    ) -> None:
        reason = "printf is operator-routed"
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(("printf", reason))
        )
        nested = self.repo / "nested"
        nested.mkdir()

        environment = os.environ.copy()
        environment["GIT_CEILING_DIRECTORIES"] = str(self.repo)
        probe = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=nested,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(probe.returncode, 0)
        self.assertTrue(probe.stderr.startswith("fatal: not a git repository"))
        self.assert_allowed(
            self.invoke("printf harmless", cwd=nested, environment=environment)
        )

        # A ceiling equal to the starting cwd is ignored by Git; discovery may
        # still reach parent metadata, so the committed rule remains active.
        environment["GIT_CEILING_DIRECTORIES"] = str(nested)
        self.assert_denied(
            self.invoke("printf harmless", cwd=nested, environment=environment),
            f"forge: operator-denied command — {reason}",
        )

    def test_guard_denylist_existing_unreadable_metadata_is_not_absence(
        self,
    ) -> None:
        environment = self.fake_git_environment(
            "unreadable-repository-metadata-bin",
            "printf '%s\\n' 'fatal: not a git repository (or any of the parent directories): .git' >&2\n"
            "exit 128\n",
        )
        git_dir = self.repo / ".git"
        original_mode = stat.S_IMODE(git_dir.stat().st_mode)
        git_dir.chmod(0)
        try:
            result = self.invoke("printf harmless", environment=environment)
        finally:
            git_dir.chmod(original_mode)
        self.assert_denied(result, GUARD_POLICY_MALFORMED)

    def test_guard_denylist_readable_invalid_metadata_confirms_absence(
        self,
    ) -> None:
        outside = self.scratch / "readable-invalid-metadata"
        outside.mkdir()
        (outside / ".git").mkdir()
        environment = os.environ.copy()
        environment.update({"LC_ALL": "C", "LANG": "C"})
        probe = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=outside,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(probe.returncode, 0)
        self.assertTrue(probe.stderr.startswith("fatal: not a git repository"))
        self.assert_allowed(
            self.invoke("printf harmless", cwd=outside, environment=environment)
        )

    def test_guard_denylist_unreadable_required_metadata_is_not_absence(
        self,
    ) -> None:
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(
                ("printf", "printf is operator-routed"),
            )
        )
        head = self.repo / ".git" / "HEAD"
        original_mode = stat.S_IMODE(head.stat().st_mode)
        head.chmod(0)
        environment = os.environ.copy()
        environment.update({"LC_ALL": "C", "LANG": "C"})
        try:
            probe = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.repo,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            result = self.invoke(
                "printf harmless", environment=environment
            )
        finally:
            head.chmod(original_mode)
        self.assertNotEqual(probe.returncode, 0)
        self.assertTrue(probe.stderr.startswith("fatal: not a git repository"))
        self.assert_denied(result, GUARD_POLICY_MALFORMED)

    def test_guard_denylist_corrupt_required_metadata_is_not_absence(
        self,
    ) -> None:
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(
                ("printf", "printf is operator-routed"),
            )
        )
        head = self.repo / ".git" / "HEAD"
        original_head = head.read_bytes()
        head.write_bytes(b"ref: garbage\n")
        environment = os.environ.copy()
        environment.update({"LC_ALL": "C", "LANG": "C"})
        try:
            probe = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.repo,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            result = self.invoke(
                "printf harmless", environment=environment
            )
        finally:
            head.write_bytes(original_head)
        self.assertNotEqual(probe.returncode, 0)
        self.assertTrue(probe.stderr.startswith("fatal: not a git repository"))
        self.assert_denied(result, GUARD_POLICY_MALFORMED)

    def test_guard_denylist_unresolvable_repository_path_fails_closed(self) -> None:
        missing = self.scratch / "does-not-exist"
        environment = self.fake_git_environment(
            "unresolvable-repository-path-bin",
            "case \" $* \" in\n"
            "  *\" rev-parse --is-bare-repository \"*) printf '%s\\n' false ;;\n"
            "  *\" rev-parse --show-toplevel \"*) "
            f"printf '%s\\n' {shlex.quote(str(missing))} ;;\n"
            "  *) exit 70 ;;\n"
            "esac\n",
        )
        self.assert_denied(
            self.invoke("printf harmless", environment=environment),
            GUARD_POLICY_MALFORMED,
        )

    def test_guard_denylist_operational_head_failure_is_not_unborn(self) -> None:
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(
                ("printf", "all printf commands are operator-routed"),
            )
        )
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        environment = self.fake_git_environment(
            "operational-head-failure-bin",
            "case \" $* \" in\n"
            "  *\" --no-replace-objects rev-parse --verify --quiet HEAD^{commit} \"*)\n"
            "    printf '%s\\n' 'fatal: object database unavailable' >&2\n"
            "    exit 128\n"
            "    ;;\n"
            "esac\n"
            f"exec {shlex.quote(real_git or 'git')} \"$@\"\n",
        )
        self.assert_denied(
            self.invoke("printf harmless", environment=environment),
            GUARD_POLICY_MALFORMED,
        )

    def test_guard_launcher_is_utf8_explicit_and_fails_closed_before_bootstrap(
        self,
    ) -> None:
        reason = "échec requires an operator"
        self.commit_policy(
            guard_denied_commands=self.guard_denied_body(("git push --force", reason))
        )
        environment = os.environ.copy()
        environment.update(
            {
                "LC_ALL": "C",
                "LANG": "C",
                "PYTHONCOERCECLOCALE": "0",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "0",
            }
        )
        self.assert_denied(
            self.invoke(
                "git push --force origin main",
                environment=environment,
            ),
            f"forge: operator-denied command — {reason}",
        )

        fd_failure = self.mutant_guard(
            "guard-bootstrap-fd-failure",
            'if ! exec 3<<<"$python_code"; then',
            'if ! exec 3<&-; then',
        )
        result = self.invoke("printf harmless", guard=fd_failure)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, GUARD_BOOTSTRAP_FAILURE + "\n")

        setup_failure = self.mutant_guard(
            "guard-bootstrap-setup-failure",
            'if ! exec 3<<<"$python_code"; then',
            "if ! false; then",
        )
        result = self.invoke("printf harmless", guard=setup_failure)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, GUARD_BOOTSTRAP_FAILURE + "\n")

    def test_guard_denylist_uses_committed_policy_not_index_or_worktree(self) -> None:
        reason = "committed operator policy"
        denied = self.guard_denied_body(("git push --force", reason))
        self.commit_policy(guard_denied_commands=denied)
        (self.repo / "forge-project.md").write_text(
            self.policy_text(
                guard_denied_commands="No additional denied commands configured."
            ),
            encoding="utf-8",
        )
        self.git("add", "forge-project.md")
        self.assert_denied(
            self.invoke("git push --force origin main"),
            f"forge: operator-denied command — {reason}",
        )

        self.commit_policy(
            guard_denied_commands="No additional denied commands configured."
        )
        (self.repo / "forge-project.md").write_text(
            self.policy_text(guard_denied_commands=denied),
            encoding="utf-8",
        )
        self.git("add", "forge-project.md")
        self.assert_allowed(self.invoke("git push --force origin main"))

    def test_guard_denylist_prefix_match_control_is_load_bearing_in_memory(self) -> None:
        module = self.load_guard_module("forge_guard_denylist_matcher_test")
        rules = module.parse_guard_denied_policy(
            (
                "<!-- FORGE:REGION guard-denied-commands BEGIN -->\n"
                + self.guard_denied_body(
                    ("git push --force", "operator-routed force push")
                )
                + "\n<!-- FORGE:REGION guard-denied-commands END -->\n"
            ).encode("utf-8")
        )
        invocations = [("git", "push", "--force", "origin", "main")]
        self.assertIsNotNone(module.guard_denied_match(invocations, rules))
        with mock.patch.object(
            module,
            "guard_denied_prefix_matches",
            return_value=False,
        ):
            self.assertIsNone(module.guard_denied_match(invocations, rules))

    def test_missing_stale_hash_mismatch_and_malformed_markers_are_denied(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        self.stage_change()
        candidate, object_format, tree_oid = self.candidate_identity()
        marker = self.repo / ".forge" / "tmp" / "authorized" / candidate
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        stale_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=31)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        cases: list[tuple[str, str | None]] = [
            ("missing", None),
            ("malformed", "not-a-marker\n"),
            (
                "stale",
                self.marker_payload(
                    candidate, object_format, tree_oid, stale_timestamp
                ),
            ),
            (
                "hash mismatch",
                self.marker_payload(
                    "0" * 64, object_format, tree_oid, now
                ),
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

    def test_content_addressed_lookup_isolates_candidates_and_sweeps_only_after_validation(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        candidate, object_format, tree_oid = self.candidate_identity()
        authorized = self.repo / ".forge/tmp/authorized"
        authorized.mkdir(parents=True)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        other = "1" * 64
        other_marker = authorized / other
        other_marker.write_text(
            self.marker_payload(other, object_format, tree_oid, now),
            encoding="utf-8",
        )
        stale_other = "2" * 64
        stale_other_marker = authorized / stale_other
        stale_at = (datetime.now(timezone.utc) - timedelta(minutes=31)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        stale_other_marker.write_text(
            self.marker_payload(stale_other, object_format, tree_oid, stale_at),
            encoding="utf-8",
        )

        # Another candidate can coexist, but it cannot authorize this index.
        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )
        self.assertTrue(other_marker.is_file())
        self.assertFalse(stale_other_marker.exists())

        # A current stale marker must be diagnosed before the age sweep removes it.
        current_marker = authorized / candidate
        current_marker.write_text(
            self.marker_payload(candidate, object_format, tree_oid, stale_at),
            encoding="utf-8",
        )
        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker stale)",
        )
        self.assertFalse(current_marker.exists())
        self.assertTrue(other_marker.is_file())

        # Exact same staged bytes select the same path and are admitted.
        current_marker.write_text(
            self.marker_payload(candidate, object_format, tree_oid, now),
            encoding="utf-8",
        )
        self.assert_allowed(self.invoke("git commit"))
        self.assertTrue(current_marker.is_file())
        self.assertTrue(other_marker.is_file())

    def test_candidate_filename_and_record_hash_must_agree(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        candidate, object_format, tree_oid = self.candidate_identity()
        marker = self.write_marker(digest=candidate)
        marker.write_text(
            self.marker_payload(
                "0" * 64,
                object_format,
                tree_oid,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
            encoding="utf-8",
        )

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker hash mismatch)",
        )

    def test_marker_tree_must_recompute_to_candidate_and_match_live_index(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        candidate, object_format, tree_oid = self.candidate_identity()
        wrong_tree = ("0" if tree_oid[0] != "0" else "1") + tree_oid[1:]
        marker = self.repo / ".forge/tmp/authorized" / candidate
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            self.marker_payload(
                candidate,
                object_format,
                wrong_tree,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
            encoding="utf-8",
        )

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker hash mismatch)",
        )

    def test_quarantine_latch_denies_valid_marker_and_expires_with_it(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        marker = self.write_marker()
        quarantine = self.write_quarantine(marker)

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker malformed)",
        )
        self.assertTrue(marker.is_file())
        self.assertTrue(quarantine.is_file())

        stale_at = (datetime.now(timezone.utc) - timedelta(minutes=31)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        marker.unlink()
        marker = self.write_marker(timestamp=stale_at)
        self.assertEqual(quarantine, marker.with_name(f"{marker.name}.quarantine"))
        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker malformed)",
        )
        self.assertFalse(marker.exists())
        self.assertFalse(quarantine.exists())

    def test_quarantine_latch_control_is_load_bearing(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        marker = self.write_marker()
        self.write_quarantine(marker, produced="none")

        intact = self.invoke("git commit")
        self.assert_denied(intact, f"{MARKER_REASON} (marker malformed)")
        mutant = self.mutant_guard(
            "quarantine-disabled-mutant",
            "        os.lstat(quarantine)",
            "        raise FileNotFoundError",
        )
        self.assert_allowed(self.invoke("git commit", guard=mutant))

    def test_retained_standard_marker_cannot_reauthorize_tree_already_at_head(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        marker = self.write_marker()
        authorized_tree = self.git("write-tree").stdout.strip()
        self.git("commit", "--quiet", "-m", "mismatching produced message")
        self.assertEqual(
            self.git("rev-parse", "HEAD^{tree}").stdout.strip(),
            authorized_tree,
        )

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker hash mismatch)",
        )
        self.assertTrue(marker.is_file())

        mutant = self.mutant_guard(
            "empty-tree-delta-disabled-mutant",
            "    return bool(path_bytes) and bool(paths)",
            "    return True",
        )
        self.assert_allowed(self.invoke("git commit", guard=mutant))

    def test_content_addressed_lookup_mutant_cannot_admit_another_candidate(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        other = "1" * 64
        self.write_marker(digest=other)
        mutant = self.mutant_guard(
            "first-authorization-marker-mutant",
            'marker = context.main_root / ".forge" / "tmp" / "authorized" / candidate',
            'marker = next((context.main_root / ".forge" / "tmp" / "authorized").iterdir())',
        )

        # The mutant resolves another session's record, proving filename/hash
        # agreement still kills cross-admission even if lookup is corrupted.
        self.assert_denied(
            self.invoke("git commit", guard=mutant),
            f"{MARKER_REASON} (marker hash mismatch)",
        )

    def test_current_candidate_validation_precedes_stale_sweep_mutant(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        stale_at = (datetime.now(timezone.utc) - timedelta(minutes=31)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.write_marker(timestamp=stale_at)
        mutant = self.mutant_guard(
            "sweep-before-validation-mutant",
            "        marker_state = (\n            marker_failure(context, classifier, observation)",
            "        sweep_stale_markers(context)\n        marker_state = (\n            marker_failure(context, classifier, observation)",
        )

        self.assert_denied(
            self.invoke("git commit", guard=mutant),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_only_exact_four_five_and_six_line_v2_marker_shapes_are_accepted(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        self.stage_change()

        self.write_marker()
        self.assert_allowed(self.invoke("git commit -m reviewed"))

        self.write_marker(third_line="skip: user-directed")
        self.assert_allowed(self.invoke("git commit -m user-directed"))

        candidate, object_format, tree_oid = self.candidate_identity()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for contents in (
            self.marker_payload(candidate, object_format, tree_oid, timestamp).rstrip("\n"),
            self.marker_payload(candidate, object_format, tree_oid, timestamp) + "extra\n",
            self.marker_payload(candidate, object_format, tree_oid, timestamp).replace(
                "format: forge-commit-candidate/2", "format: forge-commit-candidate/1"
            ),
            self.marker_payload(candidate, object_format, tree_oid, timestamp).replace(
                "authorized-at: ", ""
            ),
            self.marker_payload(candidate, object_format, tree_oid, timestamp).replace(
                tree_oid, tree_oid[:-1]
            ),
            self.marker_payload(candidate, object_format, tree_oid, timestamp).replace(
                "\n", "\r\n"
            ),
        ):
            with self.subTest(contents=contents):
                marker = (
                    self.repo
                    / ".forge"
                    / "tmp"
                    / "authorized"
                    / candidate
                )
                marker.write_text(contents, encoding="utf-8")
                self.assert_denied(
                    self.invoke("git commit"),
                    f"{MARKER_REASON} (marker malformed)",
                )

    def test_legacy_markers_never_admit_and_are_only_swept_after_expiry(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        candidate = self.staged_hash()
        marker_dir = self.repo / ".forge/tmp/authorized"
        marker_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        current_legacy = marker_dir / candidate
        current_legacy.write_text(f"{candidate}\n{now}\n", encoding="utf-8")

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker malformed)",
        )
        self.assertTrue(current_legacy.is_file())

        current_legacy.unlink()
        stale_legacy_id = "3" * 64
        stale_at = (datetime.now(timezone.utc) - timedelta(minutes=31)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        stale_legacy = marker_dir / stale_legacy_id
        stale_legacy.write_text(
            f"{stale_legacy_id}\n{stale_at}\nskip: user-directed\n",
            encoding="utf-8",
        )
        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )
        self.assertFalse(stale_legacy.exists())

    def test_gitlink_transition_matrix_ignores_configuration_and_invalidates_old_marker(self) -> None:
        self.track_manifest()
        empty_tree = self.git("mktree", input_text="").stdout.strip()
        first_gitlink = self.git(
            "commit-tree", empty_tree, input_text="first gitlink\n"
        ).stdout.strip()
        second_gitlink = self.git(
            "commit-tree", empty_tree, "-p", first_gitlink,
            input_text="second gitlink\n",
        ).stdout.strip()
        self.git("config", "diff.ignoreSubmodules", "all")
        self.git("config", "submodule.vendor.ignore", "all")
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "diff.ignoreSubmodules",
                "GIT_CONFIG_VALUE_0": "all",
                "GIT_CONFIG_KEY_1": "submodule.vendor.ignore",
                "GIT_CONFIG_VALUE_1": "all",
            }
        )

        old_candidate = self.staged_hash()
        self.write_marker(environment=environment)
        self.git(
            "update-index", "--add", "--cacheinfo", f"160000,{first_gitlink},vendor"
        )
        added_candidate = self.staged_hash()

        self.assertNotEqual(old_candidate, added_candidate)
        self.assertNotIn(
            "vendor", self.git("diff", "--cached", "--name-only").stdout.splitlines()
        )
        self.assert_denied(
            self.invoke("git commit", environment=environment),
            f"{MARKER_REASON} (marker missing)",
        )
        self.write_marker(environment=environment)
        self.assert_allowed(self.invoke("git commit", environment=environment))
        self.git("commit", "--quiet", "-m", "add gitlink")

        self.stage_change(name="docs/pre-existing.md")
        self.write_marker(environment=environment)
        self.assert_allowed(self.invoke("git commit", environment=environment))
        self.git("commit", "--quiet", "-m", "pre-existing gitlink")

        old_candidate = self.staged_hash()
        self.write_marker(environment=environment)
        self.git("update-index", "--cacheinfo", f"160000,{second_gitlink},vendor")
        changed_candidate = self.staged_hash()

        self.assertNotEqual(old_candidate, changed_candidate)
        self.assert_denied(
            self.invoke("git commit", environment=environment),
            f"{MARKER_REASON} (marker missing)",
        )
        self.write_marker(environment=environment)
        self.assert_allowed(self.invoke("git commit", environment=environment))
        self.git("commit", "--quiet", "-m", "change gitlink")

        old_candidate = self.staged_hash()
        self.write_marker(environment=environment)
        self.git("update-index", "--force-remove", "vendor")
        deleted_candidate = self.staged_hash()

        self.assertNotEqual(old_candidate, deleted_candidate)
        self.assert_denied(
            self.invoke("git commit", environment=environment),
            f"{MARKER_REASON} (marker missing)",
        )
        self.write_marker(environment=environment)
        self.assert_allowed(self.invoke("git commit", environment=environment))

    def test_guard_shared_candidate_observation_is_load_bearing(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        self.write_marker()
        self.assert_allowed(self.invoke("git commit"))

        mutant = self.mutant_guard(
            "candidate-helper-disabled-mutant",
            "        return candidate_module.observe_index(candidate_context)",
            '        raise RuntimeError("candidate observation disabled")',
        )
        self.assert_denied(
            self.invoke("git commit", guard=mutant),
            f"{MARKER_REASON} (marker hash mismatch)",
        )

    def test_fast_marker_is_admitted_only_for_independently_eligible_diff(self) -> None:
        policy_sha = self.commit_policy()
        self.stage_change(name="docs/guide.md")
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_allowed(self.invoke("git commit"))

    def test_fast_marker_permutations_and_malformed_annotations_are_denied(self) -> None:
        policy_sha = self.commit_policy()
        self.stage_change(name="docs/guide.md")
        digest = self.staged_hash()
        _, object_format, tree_oid = self.candidate_identity()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        malformed = (
            self.marker_payload(
                digest, object_format, tree_oid, timestamp,
                f"policy: {policy_sha}", "tier: fast",
            ),
            self.marker_payload(
                digest, object_format, tree_oid, timestamp,
                "tier: fast", f"policy: {policy_sha[:12]}",
            ),
            self.marker_payload(
                digest, object_format, tree_oid, timestamp,
                "tier: fast", f"policy:{policy_sha}",
            ),
            self.marker_payload(
                digest, object_format, tree_oid, timestamp,
                "skip: user-directed", "tier: fast",
            ),
            self.marker_payload(
                digest, object_format, tree_oid, timestamp,
                "tier: fast", f"policy: {policy_sha}", "extra",
            ),
        )
        marker = self.repo / ".forge/tmp/authorized" / digest
        marker.parent.mkdir(parents=True, exist_ok=True)
        for contents in malformed:
            with self.subTest(contents=contents):
                marker.write_text(contents, encoding="utf-8")
                self.assert_denied(
                    self.invoke("git commit"),
                    f"{MARKER_REASON} (marker malformed)",
                )

    def test_fast_marker_policy_region_drift_is_denied_exactly(self) -> None:
        policy_sha = self.commit_policy()
        (self.repo / "forge-project.md").write_text(
            self.policy_text(fast_patterns="docs/private/**"), encoding="utf-8"
        )
        self.git("add", "forge-project.md")
        tree = self.git("write-tree").stdout.strip()
        descendant = self.git(
            "commit-tree",
            tree,
            "-p",
            policy_sha,
            input_text="narrow policy\n",
        ).stdout.strip()
        self.git("update-ref", "HEAD", descendant)
        self.stage_change(name="docs/guide.md")
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (fast-path policy drift)",
        )

    def test_each_complete_policy_region_is_independently_continuity_checked(self) -> None:
        mutations = (
            ("risk-tiers", {"fast_patterns": "docs/private/**"}),
            ("trigger-paths", {"triggers": "| src/** | security |"}),
            ("file-categories", {}),
            (
                "guard-denied-commands",
                {
                    "guard_denied_commands": self.guard_denied_body(
                        ("git push --force", "operator-only")
                    )
                },
            ),
        )
        for region, changes in mutations:
            with self.subTest(region=region):
                repo = self.scratch / f"{region} checkout"
                self.init_repo(repo)
                base = (
                    {
                        "guard_denied_commands": (
                            "No additional denied commands configured."
                        )
                    }
                    if region == "guard-denied-commands"
                    else {}
                )
                policy_sha = self.commit_policy(cwd=repo, **base)
                updated = self.policy_text(**{**base, **changes})
                if region == "file-categories":
                    updated = updated.replace(
                        "| `docs` | `*.md`, `docs/**`, `.forge/evals/candidates/**` |",
                        "| `docs` | `*.md`, `docs/**`, `.forge/evals/candidates/**`, "
                        "`guides/**` |",
                    )
                (repo / "forge-project.md").write_text(updated, encoding="utf-8")
                self.git("add", "forge-project.md", cwd=repo)
                tree = self.git("write-tree", cwd=repo).stdout.strip()
                descendant = self.git(
                    "commit-tree",
                    tree,
                    "-p",
                    policy_sha,
                    cwd=repo,
                    input_text=f"change {region}\n",
                ).stdout.strip()
                self.git("update-ref", "HEAD", descendant, cwd=repo)
                self.stage_change(cwd=repo, name="docs/guide.md")
                self.write_marker(
                    cwd=repo,
                    marker_root=repo,
                    third_line="tier: fast",
                    fourth_line=f"policy: {policy_sha}",
                )

                self.assert_denied(
                    self.invoke("git commit", cwd=repo),
                    f"{MARKER_REASON} (fast-path policy drift)",
                )

    def test_fast_marker_nonancestor_policy_is_denied_exactly(self) -> None:
        head_policy = self.commit_policy()
        tree = self.git("rev-parse", f"{head_policy}^{{tree}}").stdout.strip()
        unrelated = self.git(
            "commit-tree", tree, input_text="unrelated policy commit\n"
        ).stdout.strip()
        self.stage_change(name="docs/guide.md")
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {unrelated}",
        )

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (fast-path policy drift)",
        )

    def test_fast_policy_reads_ignore_replace_refs(self) -> None:
        policy_sha = self.commit_policy()
        policy_parent = self.git("rev-parse", f"{policy_sha}^").stdout.strip()
        (self.repo / "forge-project.md").write_text(
            self.policy_text(fast_patterns="docs/private/**"), encoding="utf-8"
        )
        self.git("add", "forge-project.md")
        replacement_tree = self.git("write-tree").stdout.strip()
        replacement = self.git(
            "commit-tree",
            replacement_tree,
            "-p",
            policy_parent,
            input_text="replacement policy\n",
        ).stdout.strip()
        self.git("reset", "--hard", policy_sha)
        (self.repo / "docs/base.md").parent.mkdir(parents=True, exist_ok=True)
        (self.repo / "docs/base.md").write_text("base\n", encoding="utf-8")
        self.git("add", "docs/base.md")
        self.git("commit", "--quiet", "-m", "descendant")
        self.stage_change(name="docs/guide.md")
        self.git("replace", policy_sha, replacement)
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_allowed(self.invoke("git commit"))
        mutant = self.mutant_guard(
            "replace-enabled-policy-read-mutant",
            '''        result = run_context_git(
            context,
            "--no-replace-objects",
            "show",''',
            '''        result = run_context_git(
            context,
            "show",''',
        )
        self.assert_denied(
            self.invoke("git commit", guard=mutant),
            f"{MARKER_REASON} (fast-path policy drift)",
        )

    def test_fast_marker_standard_diff_is_promoted_and_denied_exactly(self) -> None:
        policy_sha = self.commit_policy()
        self.stage_change(name="src/service.py")
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (fast-path eligibility drift)",
        )
        self.wait_for_decision_workers()

        events = self.wait_for_event_file()
        emitted = [json.loads(line) for line in events.read_text().splitlines()]
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["event"], "fast_denied_eligibility")
        self.assertEqual(emitted[0]["candidate"], self.staged_hash())
        self.assertEqual(emitted[0]["policy_sha"], policy_sha)
        self.assertEqual(emitted[0]["reason"], "fast-path-eligibility-drift")
        self.assertFalse(any(item["event"] == "guard_deny" for item in emitted))

    def test_fast_classification_never_reads_working_tree_policy(self) -> None:
        policy_sha = self.commit_policy()
        self.stage_change(name="src/service.py")
        (self.repo / "forge-project.md").write_text(
            self.policy_text(fast_patterns="**"), encoding="utf-8"
        )
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (fast-path eligibility drift)",
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

    def test_malformed_working_tree_manifest_requires_marker(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n"
            "not_plugin_ref: decoy\n"
            "not_upstream_commit: decoy\n"
            "note: region: gates (forge-project.md)\n",
            encoding="utf-8",
        )
        self.stage_change()

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_upstream_schema_working_tree_manifest_leaves_only_halt_check(self) -> None:
        upstream_manifests = (
            "forge_version: 1\nupstream_commit: abc123\n",
            "forge_version: 1\nupstream_commit:\n",
            "forge_version: 1\nregion: gates (rules/gates.md)\n",
        )

        for index, contents in enumerate(upstream_manifests):
            with self.subTest(contents=contents):
                repo = self.scratch / f"upstream manifest {index}"
                self.init_repo(repo)
                (repo / ".forge-manifest").write_text(contents, encoding="utf-8")
                self.git("add", ".forge-manifest", cwd=repo)
                tree = self.git("write-tree", cwd=repo).stdout.strip()
                parent = self.git("rev-parse", "HEAD", cwd=repo).stdout.strip()
                commit = self.git(
                    "commit-tree",
                    tree,
                    "-p",
                    parent,
                    cwd=repo,
                    input_text="track upstream manifest\n",
                ).stdout.strip()
                self.git("update-ref", "HEAD", commit, cwd=repo)
                self.stage_change(cwd=repo)
                self.assert_allowed(self.invoke("git commit", cwd=repo))

                (repo / "AGENT_HALT_commit").write_text(
                    "operator pause\n", encoding="utf-8"
                )
                self.assert_denied(
                    self.invoke("git commit", cwd=repo),
                    "forge: operator halt engaged (AGENT_HALT_commit)",
                )

    def test_head_plugin_ref_match_is_anchored_not_a_bare_substring(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\nnot_plugin_ref: decoy\n", encoding="utf-8"
        )
        self.git("add", ".forge-manifest")
        tree = self.git("write-tree").stdout.strip()
        parent = self.git("rev-parse", "HEAD").stdout.strip()
        commit = self.git(
            "commit-tree",
            tree,
            "-p",
            parent,
            input_text="track non-plugin manifest\n",
        ).stdout.strip()
        self.git("update-ref", "HEAD", commit)
        (self.repo / ".forge-manifest").unlink()
        self.stage_change()

        self.assert_allowed(self.invoke("git commit"))

    def test_bootstrap_manifest_with_plugin_ref_stripped_still_requires_marker(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n"
            "installed: 2026-08-12\n"
            "project_name: bootstrap-fixture\n"
            "default_branch: main\n"
            "init_completed: false\n",
            encoding="utf-8",
        )
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

    def test_head_plugin_manifest_still_requires_marker_when_staged_for_deletion(self) -> None:
        self.track_manifest()
        (self.repo / ".forge-manifest").unlink()
        self.git("add", "-u", ".forge-manifest")

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_head_plugin_manifest_still_requires_marker_when_deleted_unstaged(self) -> None:
        self.track_manifest()
        (self.repo / ".forge-manifest").unlink()

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_manifest_schema_predicate_mutants_are_killed(self) -> None:
        disabled = self.mutant_guard(
            "manifest-predicate-disabled",
            "def manifest_requires_marker(context: RepoContext) -> bool:\n    try:\n",
            "def manifest_requires_marker(context: RepoContext) -> bool:\n"
            "    return False  # CONTROL DISABLED\n"
            "    try:\n",
        )
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\ninstalled: now\ninit_completed: false\n",
            encoding="utf-8",
        )
        self.stage_change()

        # The intact bootstrap/malformed-manifest tests expect denial. With the
        # predicate removed, that same positive assertion fails because the
        # commit is allowed.
        self.assert_allowed(self.invoke("git commit", guard=disabled))

        upstream_disabled = self.mutant_guard(
            "upstream-schema-disabled",
            "    return not is_upstream\n",
            "    return True  # CONTROL DISABLED: upstream schema recognition\n",
        )
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\nupstream_commit: abc123\n", encoding="utf-8"
        )

        # The intact upstream-schema test expects pass-through. Removing schema
        # recognition makes its assertion fail by arming the marker requirement.
        self.assert_denied(
            self.invoke("git commit", guard=upstream_disabled),
            f"{MARKER_REASON} (marker missing)",
        )

        substring = self.mutant_guard(
            "head-plugin-ref-substring",
            'HEAD_PLUGIN_REF_LINE = re.compile(br"^plugin_ref: ", re.MULTILINE)',
            'HEAD_PLUGIN_REF_LINE = re.compile(br"plugin_ref: ", re.MULTILINE)',
        )
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\nnot_plugin_ref: decoy\n", encoding="utf-8"
        )
        self.git("add", ".forge-manifest")
        tree = self.git("write-tree").stdout.strip()
        parent = self.git("rev-parse", "HEAD").stdout.strip()
        commit = self.git(
            "commit-tree",
            tree,
            "-p",
            parent,
            input_text="track non-plugin manifest\n",
        ).stdout.strip()
        self.git("update-ref", "HEAD", commit)
        (self.repo / ".forge-manifest").unlink()

        # The anchored-match test expects pass-through; a bare-substring mutant
        # instead arms on not_plugin_ref and is therefore observably killed.
        self.assert_denied(
            self.invoke("git commit", guard=substring),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_non_forge_repo_commit_and_push_pass_through(self) -> None:
        self.stage_change()

        self.assert_allowed(self.invoke("git commit -m ordinary"))
        self.assert_allowed(self.invoke("git push origin HEAD"))

    def test_authorized_candidate_rejects_index_mutation_and_commit_selection_forms(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        self.write_marker()
        unsafe = (
            "git add src/evil.py && git commit",
            "git commit -a",
            "git commit --all",
            "git commit --include src/evil.py",
            "git commit --only src/evil.py",
            "git commit src/evil.py",
            "git commit --patch",
            "git commit --interactive",
            "git commit --pathspec-from-file=paths.txt",
            "git commit -amessage",
            "git commit -C HEAD",
            "git commit --reuse-message HEAD",
            "git commit --reuse-message=HEAD",
            "git commit -c HEAD",
            "git commit --reedit-message HEAD",
            "git commit --reedit-message=HEAD",
            "git commit -F message.txt",
            "git commit --file message.txt",
            "git commit --file=message.txt",
            "git add src/evil.py & git commit",
            'git commit -m "$(git add src/evil.py)"',
            'git commit -m "<(git add src/evil.py)"',
        )
        for command in unsafe:
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command),
                    f"{MARKER_REASON} (marker hash mismatch)",
                )

    def test_authorized_candidate_accepts_value_less_benign_commit_flags(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        self.write_marker()
        benign = (
            "git commit -q -m x",
            "git commit --quiet -m x",
            "git commit -v -m x",
            "git commit --verbose -m x",
            "git commit -n -m x",
            "git commit --no-verify -m x",
            "git commit -s -m x",
            "git commit --signoff -m x",
            "git commit --no-edit",
        )
        for command in benign:
            with self.subTest(command=command):
                self.assert_allowed(self.invoke(command))

    def test_signing_flags_do_not_swallow_unsafe_commit_options(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        self.write_marker()
        bypasses = (
            "git commit -S --amend -m x",
            "git commit -S -a -m x",
            "git commit --gpg-sign --amend -m x",
            "git commit -m x -S --amend",
            "git commit -S- --amend -m x",
        )
        for command in bypasses:
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command),
                    f"{MARKER_REASON} (marker hash mismatch)",
                )

    def test_attached_signing_keys_preserve_clean_commit_candidate(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        self.write_marker()
        for command in (
            "git commit -S0123456789ABCDEF -m x",
            "git commit --gpg-sign=0123456789ABCDEF -m x",
        ):
            with self.subTest(command=command):
                self.assert_allowed(self.invoke(command))

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

    def test_halt_denial_emits_exactly_one_operator_halt_guard_event(self) -> None:
        self.stage_change(name="halted.txt")
        expected_candidate = self.staged_hash()
        expected_policy = self.git("rev-parse", "HEAD").stdout.strip()
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")

        self.assert_denied(
            self.invoke("git push origin HEAD"),
            "forge: operator halt engaged (AGENT_HALT)",
        )
        self.wait_for_decision_workers()

        events = self.wait_for_event_file()
        emitted = [json.loads(line) for line in events.read_text().splitlines()]
        guard_denials = [item for item in emitted if item["event"] == "guard_deny"]
        self.assertEqual(len(guard_denials), 1)
        self.assertEqual(guard_denials[0]["candidate"], expected_candidate)
        self.assertEqual(guard_denials[0]["policy_sha"], expected_policy)
        self.assertEqual(guard_denials[0]["reason"], "operator-halt")
        self.assertEqual(guard_denials[0]["surface"], "commit-guard")

    def test_denial_returns_before_slow_event_worker_and_pending_marker_is_cleaned(self) -> None:
        self.stage_change(name="slow-telemetry.txt")
        self.track_manifest()
        guard = self.mutant_guard(
            "slow-event-worker",
            "try:\n        result = subprocess.run(\n            sys.argv[5:],",
            "__import__('time').sleep(1.5)\n    try:\n        result = subprocess.run(\n            sys.argv[5:],",
        )

        started = time.monotonic()
        result = self.invoke("git commit", guard=guard)
        elapsed = time.monotonic() - started

        self.assert_denied(result, f"{MARKER_REASON} (marker missing)")
        self.assertLess(elapsed, 1.0, "advisory telemetry delayed the primary denial")
        pending_dir = self.repo / ".forge/tmp"
        deadline = time.monotonic() + 1
        markers: list[Path] = []
        while not markers and time.monotonic() < deadline:
            markers = list(pending_dir.glob("decision-event-pending.*"))
            time.sleep(0.01)
        self.assertTrue(markers, "slow detached worker did not advertise pending telemetry")
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            events = self.repo / ".forge/tmp/decisions/events.jsonl"
            if events.exists() and not self.decision_failure_markers():
                break
            time.sleep(0.01)
        self.assertFalse(self.decision_failure_markers())
        events = self.repo / ".forge/tmp/decisions/events.jsonl"
        records = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["event"] for record in records], ["guard_deny"])

    def test_event_worker_uses_birth_inode_when_pending_path_is_substituted(self) -> None:
        self.stage_change(name="substituted-telemetry.txt")
        self.track_manifest()
        events = self.repo / ".forge/tmp/decisions/events.jsonl"
        events.mkdir(parents=True)
        guard = self.mutant_guard(
            "substituted-event-marker",
            "try:\n        result = subprocess.run(\n            sys.argv[5:],",
            "__import__('time').sleep(1.5)\n    try:\n        result = subprocess.run(\n            sys.argv[5:],",
        )

        result = self.invoke("git commit", guard=guard)
        self.assert_denied(result, f"{MARKER_REASON} (marker missing)")
        pending_dir = self.repo / ".forge/tmp"
        deadline = time.monotonic() + 1
        markers: list[Path] = []
        while not markers and time.monotonic() < deadline:
            markers = list(pending_dir.glob("decision-event-pending.*"))
            time.sleep(0.01)
        self.assertEqual(len(markers), 1)

        marker = markers[0]
        original_inode = self.scratch / "original-marker-inode"
        victim = self.scratch / "substitution-victim"
        victim.write_text("do not touch\n", encoding="utf-8")
        os.link(marker, original_inode)
        marker.unlink()
        marker.symlink_to(victim)

        expected = "forge: decision event append skipped (event-append-write-failed)\n"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if original_inode.read_text(encoding="utf-8") == expected:
                break
            time.sleep(0.01)
        self.assertEqual(original_inode.read_text(encoding="utf-8"), expected)
        self.assertTrue(marker.is_symlink(), "worker removed the substituted pathname")
        self.assertEqual(victim.read_text(encoding="utf-8"), "do not touch\n")
        self.assertFalse(self.decision_failure_markers())
        marker.unlink()

    def test_failed_event_worker_is_counted_and_preserves_failure_marker(self) -> None:
        self.stage_change(name="failed-telemetry.txt")
        self.track_manifest()
        guard = self.mutant_guard(
            "failed-event-worker",
            "worker_failed = result is None or result.returncode != 0",
            "worker_failed = True",
        )

        self.assert_denied(
            self.invoke("git commit", guard=guard),
            f"{MARKER_REASON} (marker missing)",
        )
        deadline = time.monotonic() + 5
        failure_markers: list[Path] = []
        while time.monotonic() < deadline:
            failure_markers = self.decision_failure_markers()
            if failure_markers:
                break
            time.sleep(0.01)
        self.assertEqual(len(failure_markers), 1)
        self.assertIn("event-append-launch-failed", failure_markers[0].read_text(encoding="utf-8"))
        # This mutant forces the worker's durable failure branch after a real
        # emitter invocation; the event may therefore already be present.
        audit = (self.repo / ".forge/tmp/halt-audit.log").read_text(encoding="utf-8")
        self.assertIn("decision event append skipped (code event-append-launch-failed)", audit)

    def test_terminal_marker_write_failure_retains_honest_pending_marker(self) -> None:
        self.stage_change(name="unconfirmed-telemetry.txt")
        self.track_manifest()
        guard = self.mutant_guard(
            "unconfirmed-event-worker",
            """def write_marker(payload):
    try:
        os.lseek(marker_descriptor, 0, os.SEEK_SET)
""",
            """def write_marker(payload):
    return False
    try:
        os.lseek(marker_descriptor, 0, os.SEEK_SET)
""",
        )
        source = guard.read_text(encoding="utf-8")
        publish_needle = """def publish_failure_marker(payload):
    descriptor = None
    try:
"""
        publish_replacement = """def publish_failure_marker(payload):
    return False
    descriptor = None
    try:
"""
        self.assertEqual(source.count(publish_needle), 1, publish_needle)
        guard.write_text(
            source.replace(publish_needle, publish_replacement), encoding="utf-8"
        )
        tmp = self.repo / ".forge/tmp"
        audit = tmp / "halt-audit.log"
        audit.mkdir(parents=True)
        events = tmp / "decisions/events.jsonl"
        events.mkdir(parents=True)

        result = self.invoke("git commit", guard=guard)

        self.assert_denied(result, f"{MARKER_REASON} (marker missing)")
        deadline = time.monotonic() + 5
        pending: list[Path] = []
        while time.monotonic() < deadline:
            pending = list(tmp.glob("decision-event-pending.*"))
            if pending and not list(tmp.glob("decision-event-failed.*")):
                time.sleep(0.05)
                if list(tmp.glob("decision-event-pending.*")) == pending:
                    break
            time.sleep(0.01)
        self.assertEqual(len(pending), 1)
        self.assertEqual(
            pending[0].read_text(encoding="utf-8"),
            "forge: decision event outcome pending "
            "(code event-append-outcome-unconfirmed)\n",
        )
        self.assertFalse(self.decision_failure_markers())
        self.assertNotIn("event-append-write-failed", pending[0].read_text(encoding="utf-8"))
        self.assertTrue(events.is_dir())
        self.assertTrue(audit.is_dir())
        pending[0].unlink()

    def test_real_event_and_audit_failures_preserve_denial_and_failure_code(self) -> None:
        self.track_manifest()
        self.stage_change(name="failed-destinations.txt")
        tmp = self.repo / ".forge/tmp"
        events = tmp / "decisions/events.jsonl"
        events.mkdir(parents=True)
        audit = tmp / "halt-audit.log"
        audit.mkdir()

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

        deadline = time.monotonic() + 5
        failure_markers: list[Path] = []
        while time.monotonic() < deadline:
            failure_markers = self.decision_failure_markers()
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

    def test_real_append_failure_is_counted_once_with_exact_code(self) -> None:
        self.track_manifest()
        self.stage_change(name="single-failure.txt")
        tmp = self.repo / ".forge/tmp"
        events = tmp / "decisions/events.jsonl"
        events.mkdir(parents=True)

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )
        deadline = time.monotonic() + 5
        failure_markers: list[Path] = []
        while time.monotonic() < deadline:
            failure_markers = self.decision_failure_markers()
            if failure_markers:
                break
            time.sleep(0.01)
        self.assertEqual(len(failure_markers), 1)
        audit_lines = (tmp / "halt-audit.log").read_text(encoding="utf-8").splitlines()
        append_failures = [
            line for line in audit_lines if "decision event append skipped (code " in line
        ]
        self.assertEqual(len(append_failures), 1)
        self.assertIn("code event-append-write-failed", append_failures[0])
        self.assertNotIn("event-append-launch-failed", append_failures[0])

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
        guard_line = next(
            line for line in contents.splitlines()
            if "executable=git deny=operator-halt" in line
        )
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

    def test_distinct_linked_indexes_resolve_their_own_candidate_concurrently(self) -> None:
        self.track_manifest()
        first = self.scratch / "linked first"
        second = self.scratch / "linked second"
        self.git("worktree", "add", "--quiet", "-b", "first", str(first))
        self.git("worktree", "add", "--quiet", "-b", "second", str(second))
        self.stage_change(cwd=first, name="first.txt")
        self.stage_change(cwd=second, name="second.txt")
        first_hash = self.staged_hash(cwd=first)
        second_hash = self.staged_hash(cwd=second)
        self.assertNotEqual(first_hash, second_hash)
        first_marker = self.write_marker(cwd=first, marker_root=self.repo)
        second_marker = self.write_marker(cwd=second, marker_root=self.repo)

        processes = [
            subprocess.Popen(
                ["bash", str(COMMIT_GUARD)],
                cwd=worktree,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for worktree in (first, second)
        ]
        payload = json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "git commit"}}
        )
        results = [process.communicate(payload, timeout=10) for process in processes]
        for process, (stdout, stderr) in zip(processes, results, strict=True):
            self.assertEqual(process.returncode, 0)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "")
        self.assertTrue(first_marker.is_file())
        self.assertTrue(second_marker.is_file())

    def test_linked_worktree_fast_marker_reclassifies_linked_index(self) -> None:
        policy_sha = self.commit_policy()
        linked = self.scratch / "linked fast worktree"
        self.git("worktree", "add", "--quiet", "-b", "linked-fast", str(linked))
        self.stage_change(cwd=linked, name="docs/guide.md")
        self.write_marker(
            cwd=linked,
            marker_root=self.repo,
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_allowed(self.invoke("git commit", cwd=linked))

    def test_linked_fast_classifier_does_not_forward_ambient_repository_globals(self) -> None:
        policy_sha = self.commit_policy()
        linked = self.scratch / "linked ambient worktree"
        self.git("worktree", "add", "--quiet", "-b", "linked-ambient", str(linked))
        self.stage_change(cwd=linked, name="docs/guide.md")
        self.write_marker(
            cwd=linked,
            marker_root=self.repo,
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )
        invocation_cwd = linked / "nested"
        invocation_cwd.mkdir()
        linked_git_dir = Path(
            self.git("rev-parse", "--absolute-git-dir", cwd=linked).stdout.strip()
        )
        environment = os.environ.copy()
        environment["GIT_DIR"] = os.path.relpath(
            linked_git_dir, invocation_cwd.resolve()
        )
        environment["GIT_WORK_TREE"] = os.path.relpath(
            linked.resolve(), invocation_cwd.resolve()
        )

        self.assert_allowed(
            self.invoke("git commit", cwd=invocation_cwd, environment=environment)
        )

    def test_ambient_main_git_dir_cannot_authorize_linked_hard_index_as_fast(self) -> None:
        policy_sha = self.commit_policy()
        linked = self.scratch / "linked split worktree"
        self.git("worktree", "add", "--quiet", "-b", "linked-split", str(linked))
        self.stage_change(cwd=linked, name="docs/guide.md")
        (self.repo / "forge-project.md").write_text(
            self.policy_text() + "\nambient hard change\n",
            encoding="utf-8",
        )
        self.git("add", "forge-project.md", cwd=self.repo)
        self.write_marker(
            cwd=self.repo,
            marker_root=self.repo,
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )
        environment = os.environ.copy()
        environment["GIT_DIR"] = str(self.repo / ".git")

        self.assert_denied(
            self.invoke("git commit", cwd=linked, environment=environment),
            f"{MARKER_REASON} (fast-path eligibility drift)",
        )

    def test_fast_marker_preserves_inherited_alternate_index(self) -> None:
        policy_sha = self.commit_policy()
        alternate_index = self.scratch / "alternate.index"
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(alternate_index)
        subprocess.run(
            ["git", "read-tree", "HEAD"],
            cwd=self.repo,
            env=environment,
            check=True,
            capture_output=True,
        )
        alternate_doc = self.repo / "docs" / "alternate.md"
        alternate_doc.parent.mkdir(parents=True)
        alternate_doc.write_text("alternate index\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "docs/alternate.md"],
            cwd=self.repo,
            env=environment,
            check=True,
            capture_output=True,
        )
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
            environment=environment,
        )

        self.assert_allowed(self.invoke("git commit", environment=environment))

    def test_legacy_git_path_fallback_preserves_relative_alternate_index(self) -> None:
        policy_sha = self.commit_policy()
        nested = self.repo / "nested" / "deeper"
        nested.mkdir(parents=True)
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = "alternate.index"
        subprocess.run(
            ["git", "read-tree", "HEAD"],
            cwd=self.repo,
            env=environment,
            check=True,
            capture_output=True,
        )
        alternate_doc = self.repo / "docs" / "legacy-alternate.md"
        alternate_doc.parent.mkdir(parents=True)
        alternate_doc.write_text("legacy alternate index\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "docs/legacy-alternate.md"],
            cwd=self.repo,
            env=environment,
            check=True,
            capture_output=True,
        )
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
            environment=environment,
        )

        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        fake_bin = self.scratch / "legacy git bin"
        fake_bin.mkdir()
        git_wrapper = fake_bin / "git"
        git_wrapper.write_text(
            "#!/usr/bin/env bash\n"
            'if [[ "$1" == "rev-parse" && "$2" == "--path-format=absolute" ]]; then\n'
            "  exit 129\n"
            "fi\n"
            f"exec {shlex_quote(Path(real_git or ''))} \"$@\"\n",
            encoding="utf-8",
        )
        git_wrapper.chmod(0o755)
        environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"

        self.assert_allowed(
            self.invoke("git commit", cwd=nested, environment=environment)
        )

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

    def test_fast_classifier_uses_explicit_git_dir_and_work_tree_identity(self) -> None:
        policy_sha = self.commit_policy()
        self.stage_change(name="docs/guide.md")
        self.write_marker(
            cwd=self.repo,
            marker_root=self.scratch,
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )
        external_git_dir = self.scratch / "external fast admin.git"
        (self.repo / ".git").rename(external_git_dir)
        command = (
            f"git --git-dir={shlex_quote(external_git_dir)} "
            f"--work-tree={shlex_quote(self.repo)} commit"
        )

        self.assert_allowed(self.invoke(command, cwd=self.scratch))


def shlex_quote(value: Path) -> str:
    import shlex

    return shlex.quote(str(value))


if __name__ == "__main__":
    unittest.main()
