"""Phase-1 Forge CLI integration with the PreToolUse commit guard."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
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
INSTALLER = ROOT / "scripts" / "forge" / "install.sh"
ARGV_CORPUS = ROOT / "system" / "fr223" / "hook-argv-cases-v1.json"
GITIGNORE_TEMPLATE = ROOT / "system" / "template" / "gitignore-block.txt"
MARKER_REASON = "forge: commit not authorized — run /forge:commit"
APPROVE_REASON = (
    "forge: operator verb denied — present the candidate and ask the operator "
    "to run this via ! (commit approve)"
)
SKIP_REASON = (
    "forge: operator verb denied — present the candidate and ask the operator "
    "to run this via ! (commit skip)"
)
CHAIN_ID = "c-2026-08-21T120000Z-0001"


def denial(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def load_guard_module(test: unittest.TestCase, name: str) -> ModuleType:
    shell = COMMIT_GUARD.read_text(encoding="utf-8")
    embedded = shell.split("<<'PY' || true\n", 1)[1].split("\nPY\n", 1)[0]
    definitions = embedded.split("\ntry:\n    raise SystemExit(main())", 1)[0]
    test.addCleanup(sys.modules.pop, name, None)
    module = ModuleType(name)
    module.__file__ = str(COMMIT_GUARD)
    sys.modules[name] = module
    exec(compile(definitions, str(COMMIT_GUARD), "exec"), module.__dict__)
    return module


class HookArgvCorpusIntegrationTests(unittest.TestCase):
    def test_all_112_cases_classify_and_execute_end_to_end(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_hook_integration")
        classify = module.classify_forge_cli_invocation

        cases = json.loads(ARGV_CORPUS.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(cases), 112)
        # Revision 13: the v3 generation supersedes one v1 expectation; the v1
        # bytes and every other row stay as pinned.
        superseded = {
            entry["id"]: entry
            for entry in json.loads(
                (ARGV_CORPUS.parent / "hook-argv-cases-v3.json").read_text(encoding="utf-8")
            )["supersedes"]
        }
        cases = [
            {**case, "expect": superseded[case["id"]]["expect"], "reason": superseded[case["id"]]["reason"]}
            if case["id"] in superseded else case
            for case in cases
        ]
        observed_denials: set[str] = set()
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(classify(case["command"]), case["expect"])
                result = subprocess.run(
                    ["bash", str(COMMIT_GUARD)],
                    cwd=ROOT,
                    env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)},
                    input=json.dumps(
                        {
                            "tool_name": "Bash",
                            "tool_input": {"command": case["command"]},
                        }
                    ),
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                if case["expect"].startswith("deny-"):
                    self.assertEqual(json.loads(result.stdout), denial(case["reason"]))
                    observed_denials.add(case["reason"])
                else:
                    self.assertEqual(result.stdout, "")

        self.assertEqual(observed_denials, {APPROVE_REASON, SKIP_REASON})


class HookChainIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-cli-hook-")
        self.addCleanup(self.temp_dir.cleanup)
        self.scratch = Path(self.temp_dir.name)
        self.repo = self.scratch / "main checkout"
        self.repo.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Forge Tests")
        self.git("config", "user.email", "forge-tests@example.invalid")
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\nplugin_ref: test-plugin\ninit_completed: true\n",
            encoding="utf-8",
        )
        (self.repo / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        self.git("add", ".forge-manifest", "tracked.txt")
        self.git("commit", "--quiet", "-m", "baseline")
        (self.repo / "change.txt").write_text("candidate\n", encoding="utf-8")
        self.git("add", "change.txt")
        self.candidate = hashlib.sha256(
            subprocess.run(
                ["git", "diff", "--cached"],
                cwd=self.repo,
                check=True,
                capture_output=True,
            ).stdout
        ).hexdigest()
        (self.repo / "nested").mkdir()

    def tearDown(self) -> None:
        self.wait_for_workers()
        super().tearDown()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def wait_for_workers(self) -> None:
        pending_dir = self.repo / ".forge" / "tmp"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not list(pending_dir.glob("decision-event-pending.*")):
                return
            time.sleep(0.01)

    def invoke(
        self,
        command: str,
        *,
        session: str | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
        if session is None:
            environment.pop("CLAUDE_SESSION_ID", None)
        else:
            environment["CLAUDE_SESSION_ID"] = session
        return subprocess.run(
            ["bash", str(COMMIT_GUARD)],
            cwd=cwd or self.repo,
            env=environment,
            input=json.dumps(
                {"tool_name": "Bash", "tool_input": {"command": command}}
            ),
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_allowed(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def assert_denied(
        self, result: subprocess.CompletedProcess[str], reason: str
    ) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), denial(reason))
        self.wait_for_workers()

    @staticmethod
    def iso_z(value: datetime) -> str:
        return (
            value.astimezone(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def write_chain(
        self,
        *,
        state: str = "authorized",
        session_identity: str = "owner-session",
        worktree_root: str | None = None,
        candidate: str | None = None,
        issued_at: datetime | None = None,
        expires_at: datetime | None = None,
        inactive_after: datetime | None = None,
        consumed: bool = False,
    ) -> Path:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        issued = issued_at or now
        expires = expires_at or issued + timedelta(minutes=30)
        candidate_sha = candidate or self.candidate
        authorization: dict[str, object]
        if state in {"authorized", "closed"}:
            authorization = {
                "token": "1" * 32,
                "candidate": candidate_sha,
                "issued_at": self.iso_z(issued),
                "expires_at": self.iso_z(expires),
                "consumed": consumed,
                "consumed_at": self.iso_z(now) if consumed else None,
            }
        else:
            authorization = {}
        head = self.git("rev-parse", "HEAD").stdout.strip()
        chain = {
            "schema": "forge-chain/1",
            "chain_id": CHAIN_ID,
            "kind": "commit",
            "state": state,
            "created_at": self.iso_z(now - timedelta(minutes=5)),
            "last_event_at": self.iso_z(now),
            "inactive_after": self.iso_z(
                inactive_after or now + timedelta(hours=24)
            ),
            "repo_head": head,
            "policy_source": {
                "path": "forge-project.md",
                "sha": head,
                "digest": "2" * 64,
            },
            "paths": ["change.txt"],
            "staging": {
                "worktree_root": worktree_root or str(self.repo.resolve()),
                "session_identity": session_identity,
                "staged_paths": ["change.txt"],
                "staged_at": self.iso_z(now),
                "classification_runs": 1,
                "anomalies": [],
            },
            "candidate": {
                "sha256": candidate_sha,
                "computed_at": self.iso_z(now),
            },
            "tier": {
                "declared": None,
                "derived": "standard",
                "effective": "standard",
                "control": False,
                "categories": ["docs"],
                "classification": {},
            },
            "steps": {},
            "review": {
                "iteration": 1,
                "request": None,
                "verdict": None,
                "dispositions": [],
                "operator_cosign_required": False,
                "residual_risk": None,
            },
            "approval": {},
            "authorization": authorization,
            "commit_result": {},
        }
        path = self.repo / ".forge" / "chains" / f"{CHAIN_ID}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                chain,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        return path

    def write_marker(self, contents: str | None = None) -> Path:
        marker = (
            self.repo / ".forge" / "tmp" / "authorized" / self.candidate
        )
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            contents
            if contents is not None
            else (
                f"{self.candidate}\n"
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
            ),
            encoding="utf-8",
        )
        return marker

    def test_chain_and_marker_each_authorize_independently(self) -> None:
        chain_path = self.write_chain()

        self.assert_allowed(self.invoke("git commit -m chain-authorized"))

        self.write_marker("malformed marker\n")
        self.assert_allowed(self.invoke("git commit -m chain-over-malformed-marker"))

        chain_path.write_text("{corrupt\n", encoding="utf-8")
        self.write_marker()
        self.assert_allowed(self.invoke("git commit -m marker-over-corrupt-chain"))

    def test_operator_denial_emits_one_guard_event_after_exact_decision(self) -> None:
        result = self.invoke(
            "python3 scripts/forge/cli.py commit approve --candidate "
            + self.candidate
        )

        self.assert_denied(result, APPROVE_REASON)
        event_path = self.repo / ".forge" / "tmp" / "decisions" / "events.jsonl"
        events = [
            json.loads(line)
            for line in event_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "guard_deny")
        self.assertEqual(events[0]["candidate"], self.candidate)
        self.assertEqual(events[0]["reason"], "operator-verb-approve")
        self.assertEqual(events[0]["surface"], "commit-guard")

    def test_invalid_chain_variants_fall_back_to_marker_evaluation(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        foreign = str((self.scratch / "foreign worktree").resolve())
        cases = {
            "expired": {
                "issued_at": now - timedelta(minutes=31),
                "expires_at": now - timedelta(minutes=1),
            },
            "expiry-boundary": {
                "issued_at": now - timedelta(minutes=30),
                "expires_at": now,
            },
            "future-issued": {
                "issued_at": now + timedelta(hours=1),
                "expires_at": now + timedelta(hours=1, minutes=30),
            },
            "consumed": {"consumed": True},
            "hash-mismatched": {"candidate": "0" * 64},
            "foreign-worktree": {"worktree_root": foreign},
        }
        for name, overrides in cases.items():
            with self.subTest(case=name):
                self.write_chain(**overrides)
                marker = (
                    self.repo
                    / ".forge"
                    / "tmp"
                    / "authorized"
                    / self.candidate
                )
                marker.unlink(missing_ok=True)
                self.assert_denied(
                    self.invoke("git commit -m not-authorized"),
                    f"{MARKER_REASON} (marker missing)",
                )

        chain_path = self.repo / ".forge" / "chains" / f"{CHAIN_ID}.json"
        chain_path.write_text("not json\n", encoding="utf-8")
        self.assert_denied(
            self.invoke("git commit -m corrupt-chain"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_malformed_resource_chain_files_do_not_suppress_valid_marker(self) -> None:
        marker = self.write_marker()
        issued = datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        chain_path = self.write_chain(issued_at=issued, expires_at=issued)
        self.assert_allowed(self.invoke("git commit -m overflowing-chain-time"))

        chain_path.write_text("[" * 1100 + "]" * 1100 + "\n", encoding="utf-8")
        self.assert_allowed(self.invoke("git commit -m deeply-nested-chain"))

        self.assertTrue(marker.is_file())

    def test_oversized_otherwise_valid_chain_is_rejected_by_both_size_checks(self) -> None:
        chain_path = self.write_chain()
        encoded = chain_path.read_bytes().rstrip(b"\n")
        chain_path.write_bytes(encoded + b" " * (1024 * 1024) + b"\n")
        self.assert_denied(
            self.invoke("git commit -m oversized-authorizing-chain"),
            f"{MARKER_REASON} (marker missing)",
        )

        module = load_guard_module(
            self, "forge_commit_guard_chain_size_integration"
        )
        directory = os.open(
            chain_path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        self.addCleanup(os.close, directory)

        with mock.patch.object(
            module.os,
            "read",
            side_effect=AssertionError("oversized state must not be read"),
        ) as read:
            self.assertIsNone(module._read_chain_state(directory, chain_path.name))
            read.assert_not_called()

        real_fstat = os.fstat

        def masked_size(descriptor: int) -> os.stat_result:
            values = list(real_fstat(descriptor))
            values[6] = 0
            return os.stat_result(values)

        with mock.patch.object(module.os, "fstat", side_effect=masked_size):
            self.assertIsNone(module._read_chain_state(directory, chain_path.name))

    def test_symlinked_chain_hierarchy_cannot_authorize(self) -> None:
        self.write_chain()
        forge = self.repo / ".forge"
        external_forge = self.scratch / "external forge"
        forge.rename(external_forge)
        forge.symlink_to(external_forge, target_is_directory=True)
        self.assert_denied(
            self.invoke("git commit -m symlinked-forge"),
            f"{MARKER_REASON} (marker missing)",
        )

        forge.unlink()
        external_forge.rename(forge)
        chains = forge / "chains"
        external_chains = self.scratch / "external chains"
        chains.rename(external_chains)
        chains.symlink_to(external_chains, target_is_directory=True)
        self.assert_denied(
            self.invoke("git commit -m symlinked-chains"),
            f"{MARKER_REASON} (marker missing)",
        )

        self.write_marker()
        self.assert_allowed(
            self.invoke("git commit -m marker-with-symlinked-chains")
        )

    def test_foreign_session_index_verbs_are_denied_for_live_chain(self) -> None:
        self.write_chain(state="verifying", session_identity="owner-session")
        nested = self.repo / "nested"
        commands = (
            "git add change.txt",
            "/usr/bin/git restore --staged change.txt",
            "git restore -S change.txt",
            "git restore -SW change.txt",
            "env TRACE=1 git reset HEAD -- change.txt",
            "cd nested && git rm --cached ../change.txt",
            f"git -C {shlex.quote(str(self.repo))} stash",
        )
        reason = (
            "forge: index verb denied — live commit chain "
            f"{CHAIN_ID} owns this worktree index; use the chain verbs or abort it"
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command, session="foreign-session", cwd=self.repo),
                    reason,
                )

        for command in commands:
            with self.subTest(owner_command=command):
                self.assert_allowed(
                    self.invoke(command, session="owner-session", cwd=self.repo)
                )

        for command in (
            "git restore -- change.txt",
            "git rm -- change.txt",
            "git restore -- --staged",
            "git restore -- -S",
            "git rm -- --cached",
        ):
            with self.subTest(non_mutating_command=command):
                self.assert_allowed(
                    self.invoke(command, session="foreign-session", cwd=nested)
                )

    def test_missing_terminal_inactive_or_unidentified_chain_does_not_deny_index(self) -> None:
        command = "git add change.txt"

        self.assert_allowed(self.invoke(command, session="foreign-session"))

        self.write_chain(state="closed", consumed=True)
        self.assert_allowed(self.invoke(command, session="foreign-session"))

        self.write_chain(
            state="verifying",
            inactive_after=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        self.assert_allowed(self.invoke(command, session="foreign-session"))

        self.write_chain(state="verifying", session_identity="")
        self.assert_allowed(self.invoke(command, session="foreign-session"))

        self.write_chain(state="verifying", session_identity="owner-session")
        self.assert_allowed(self.invoke(command, session=None))


class InstallerChainIgnoreIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-chain-ignore-")
        self.addCleanup(self.temp_dir.cleanup)
        self.scratch = Path(self.temp_dir.name)
        self.repo = self.scratch / "target repo"
        self.plugin = self.scratch / "plugin payload"
        self.repo.mkdir()
        self.plugin.mkdir()
        subprocess.run(
            ["git", "init", "--quiet"],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )
        shutil.copytree(ROOT / "system", self.plugin / "system")

    def install(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(INSTALLER), str(self.plugin)],
            cwd=self.repo,
            env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(self.plugin)},
            check=False,
            capture_output=True,
            text=True,
        )

    def check_ignore(self, relative: str) -> int:
        return subprocess.run(
            ["git", "check-ignore", "-q", "--", relative],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        ).returncode

    def test_fresh_install_and_reinit_effectively_ignore_chain_state(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)
        installed = (self.repo / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(installed, GITIGNORE_TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(installed.count("# --- forge agent system --- #"), 1)
        self.assertEqual(installed.count("/.forge/chains/"), 1)
        self.assertEqual(
            self.check_ignore(f".forge/chains/{CHAIN_ID}.json"), 0
        )
        for path in (
            ".forge/history/runs/run.md",
            ".forge/history/drift/report.md",
            ".forge/history/migrations/report.md",
            ".forge/history/gotchas.md",
            ".forge/evals/candidates/task.json",
            ".forge/evals/candidates/task.result",
        ):
            self.assertEqual(self.check_ignore(path), 1, path)

        (self.repo / ".gitignore").write_text(
            installed.replace("/.forge/chains/\n", ""), encoding="utf-8"
        )
        second = self.install()
        self.assertEqual(second.returncode, 0, second.stderr)
        repaired = (self.repo / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(repaired.count("# --- forge agent system --- #"), 1)
        self.assertEqual(repaired.count("/.forge/chains/"), 1)
        self.assertEqual(
            self.check_ignore(f".forge/chains/{CHAIN_ID}.json"), 0
        )
        for path in (
            ".forge/history/runs/run.md",
            ".forge/history/drift/report.md",
            ".forge/history/migrations/report.md",
            ".forge/history/gotchas.md",
            ".forge/evals/candidates/task.json",
            ".forge/evals/candidates/task.result",
        ):
            self.assertEqual(self.check_ignore(path), 1, path)

    def test_installer_postcondition_rejects_missing_chain_ignore_rule(self) -> None:
        template = self.plugin / "system" / "template" / "gitignore-block.txt"
        template.write_text(
            template.read_text(encoding="utf-8").replace("/.forge/chains/\n", ""),
            encoding="utf-8",
        )

        result = self.install()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(
            "forge install: .forge/chains/ must be ignored", result.stderr
        )

    def test_installer_rejects_nested_history_ignore_rule(self) -> None:
        (self.repo / ".gitignore").write_text(
            "/.forge/history/runs/\n", encoding="utf-8"
        )

        result = self.install()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(
            result.stderr,
            "forge install: .forge/history/ must not be ignored\n",
        )

    def test_installer_rejects_candidate_artifact_ignore_rule(self) -> None:
        (self.repo / ".gitignore").write_text(
            "/.forge/evals/candidates/*.json\n", encoding="utf-8"
        )

        result = self.install()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(
            result.stderr,
            "forge install: .forge/evals/candidates/ must not be ignored\n",
        )

    def test_source_and_template_blocks_pin_the_chain_entry(self) -> None:
        for path in (ROOT / ".gitignore", GITIGNORE_TEMPLATE):
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text.count("# --- forge agent system --- #"), 1)
                self.assertEqual(text.count("/.forge/chains/"), 1)
                self.assertNotIn("/.forge/history/", text)
                self.assertNotIn("/.forge/evals/candidates/", text)


if __name__ == "__main__":
    unittest.main()
