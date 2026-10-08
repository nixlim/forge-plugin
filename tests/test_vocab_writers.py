"""The public journal verbs produce the Revision-22 record vocabulary."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tests._git_env import init_quiet_repository

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/codex_orch_tools.py"
CLI = ROOT / "scripts/forge/cli.py"


def invoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


class VocabularyWriterTests(unittest.TestCase):
    def test_run_open_from_linked_worktree_uses_main_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            main = Path(temporary) / "main"
            linked = Path(temporary) / "linked"
            self.assertEqual(init_quiet_repository(main, "-q").returncode, 0)
            subprocess.run(["git", "-C", str(main), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit", "-q",
                            "--allow-empty", "-m", "initial"], check=True)
            subprocess.run(["git", "-C", str(main), "worktree", "add", "-q",
                            "-b", "linked", str(linked)], check=True)
            result = invoke("run-open", "--repo", str(linked), "--run-id", "run",
                            "--intent", "work", "--actor", "operator")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((main / ".codex-orchestrator/runs/run/journal.jsonl").is_file())
            self.assertFalse((linked / ".codex-orchestrator").exists())

    def test_every_kept_verb_writes_its_plain_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            identity = ("--repo", str(repo), "--run-id", "run")
            route = (
                "--task", "task-01", "--role", "implementer", "--provider", "codex",
                "--model", "gpt-test", "--effort", "high", "--sandbox", "workspace-write",
                "--route-source", "local", "--route-sha256", "a" * 64,
                "--worktree", str(repo),
            )
            commands = [
                (
                    "run-open", *identity, "--intent", "ship", "--actor", "operator",
                    "--reference", "missing-chain",
                ),
                (
                    "journal", "task-start", *identity, "--task", "task-01",
                    "--title", "Build", "--scope", "src/**",
                ),
                (
                    "journal", "task-finish", *identity, "--task", "task-01",
                    "--title", "Build", "--scope", "src/**", "--status", "complete",
                ),
                (
                    "journal", "execution-start", *identity, *route,
                    "--execution", "execution-01", "--agent", "impl-01",
                    "--session-id", "session-01",
                ),
                (
                    "journal", "execution-result", *identity, *route,
                    "--agent", "impl-01", "--execution", "execution-01",
                    "--started-at", "2026-10-07T00:00:00Z",
                    "--status", "complete", "--exit-status", "0",
                    "--output", "impl-01/execution-01/handoff.md",
                    "--input-tokens", "12", "--output-tokens", "7",
                ),
                (
                    "journal", "decision-add", *identity, "--text", "Use the patch",
                    "--actor", "operator", "--reference", ".forge/chains/chain-01/verdict.json",
                ),
                ("run-close", *identity, "--outcome", "completed"),
            ]
            records = []
            for command in commands:
                result = invoke(*command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                records.append(json.loads(result.stdout))
            on_disk = [
                json.loads(line)
                for line in (repo / ".codex-orchestrator/runs/run/journal.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
        self.assertEqual(on_disk, records)
        self.assertEqual(
            [record["kind"] for record in records],
            [
                "run_started", "task", "task", "execution_started",
                "execution_finished", "decision", "run_closed",
            ],
        )
        self.assertTrue(all(record["run_id"] == "run" for record in records))
        self.assertEqual(records[0]["repository"], str(repo))
        self.assertEqual(records[0]["intent"], "ship")
        self.assertEqual(records[0]["references"], ["missing-chain"])
        self.assertEqual(records[1]["scope"], "src/**")
        self.assertEqual(records[2]["description"], "complete")
        self.assertEqual(records[3]["execution_id"], "execution-01")
        self.assertNotIn("attempt_id", records[3])
        self.assertEqual(records[3]["sandbox"], "workspace-write")
        self.assertEqual(records[3]["route_source"], "local")
        self.assertEqual(records[3]["route_sha256"], "a" * 64)
        self.assertEqual(records[3]["session_id"], "session-01")
        self.assertRegex(records[3]["started_at"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(records[4]["model"], "gpt-test")
        self.assertEqual(records[4]["sandbox"], "workspace-write")
        self.assertEqual(records[4]["route_source"], "local")
        self.assertEqual(records[4]["route_sha256"], "a" * 64)
        self.assertEqual(records[4]["exit_status"], 0)
        self.assertEqual(records[4]["output_tokens"], 7)
        self.assertEqual(records[5]["references"], [".forge/chains/chain-01/verdict.json"])
        self.assertEqual(
            records[6], {"kind": "run_closed", "run_id": "run", "outcome": "completed"}
        )

    def test_close_does_not_seal_and_duplicate_task_needs_no_prior_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            identity = ("--repo", temporary, "--run-id", "run")
            for command in (
                ("run-close", *identity, "--outcome", "first"),
                ("run-close", *identity, "--outcome", "again"),
                (
                    "journal", "task-finish", *identity, "--task", "unknown",
                    "--title", "Unknown", "--scope", "other/**", "--status", "complete",
                ),
            ):
                result = invoke(*command)
                self.assertEqual(result.returncode, 0, result.stderr)
            path = Path(temporary) / ".codex-orchestrator/runs/run/journal.jsonl"
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 3)

    def test_retired_verbs_and_flags_use_argparse_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            identity = ("--repo", temporary, "--run-id", "run")
            commands = (
                ("run-readmit", *identity),
                ("run-retire", *identity),
                ("journal-append", *identity, "--record-json", "x"),
                ("worktree-check", *identity),
                ("run-open", *identity, "--intent", "x", "--actor", "y", "--scope", "src/**"),
                ("run-open", *identity, "--intent", "x", "--actor", "y", "--successor-of", "old"),
                ("run-open", *identity, "--intent", "x", "--actor", "y", "--record-json", "x"),
                ("run-close", *identity, "--outcome", "x", "--judgment", "passed"),
                ("run-open", *identity, "--intent", "x", "--actor", "y", "--idempotency-key", "x"),
                (
                    "journal", "task-start", *identity, "--task", "t",
                    "--title", "T", "--scope", "src/**", "--replace",
                ),
                ("journal", "verification-add", *identity),
                ("journal", "batch-recover", *identity),
                ("journal", "close-preflight", *identity),
            )
            for command in commands:
                with self.subTest(command=command):
                    result = invoke(*command)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("usage:", result.stderr)
            self.assertFalse((Path(temporary) / ".codex-orchestrator").exists())

    def test_retired_flags_are_refused_by_both_writers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for flag in (
                "--closing-head", "--legacy-approval", "--legacy-recovered-head",
                "--dispense-reason", "--dispense-citation", "--backfill-closing-head",
                "--archive-run-id", "--scope", "--successor-of", "--gates",
            ):
                with self.subTest(script=CLI.name, flag=flag):
                    result = subprocess.run(
                        [sys.executable, str(CLI), "--json", "commit", "start",
                         "--paths", "README.md", flag, "x"],
                        capture_output=True, text=True, check=False, cwd=temporary,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(
                        json.loads(result.stdout)["message"],
                        f"invalid CLI invocation: unrecognized arguments: {flag} x",
                    )
            identity = ("--repo", temporary, "--run-id", "run")
            for verb, required, flag in (
                ("run-close", ("--outcome", "x"), "--summary"),
                ("run-close", ("--outcome", "x"), "--risk"),
                ("run-close", ("--outcome", "x"), "--follow-up"),
                ("run-open", ("--intent", "x", "--actor", "y"), "--goal"),
                ("run-open", ("--intent", "x", "--actor", "y"), "--plugin-ref"),
            ):
                with self.subTest(script=SCRIPT.name, flag=flag):
                    result = invoke(verb, *identity, *required, flag, "x")
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("usage:", result.stderr)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_concurrent_execution_starts_keep_caller_ids_and_untorn_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            identity = ("--repo", temporary, "--run-id", "run")
            command = (
                "journal", "execution-start", *identity, "--task", "t",
                "--role", "implementer", "--provider", "codex",
                "--model", "gpt-test", "--effort", "low", "--sandbox", "workspace-write",
                "--route-source", "local", "--route-sha256", "a" * 64,
                "--worktree", temporary,
            )
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(
                    lambda index: invoke(*command, "--execution", f"execution-{index + 1:02d}"),
                    range(16),
                ))
            self.assertTrue(all(result.returncode == 0 for result in results))
            path = Path(temporary) / ".codex-orchestrator/runs/run/journal.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            records = [json.loads(line) for line in lines]
            self.assertEqual(len(records), 16)
            self.assertEqual(
                {record["execution_id"] for record in records},
                {f"execution-{number:02d}" for number in range(1, 17)},
            )
            self.assertTrue(all("attempt_id" not in record for record in records))

    def test_prose_execution_verbs_require_route_source_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            identity = ("--repo", temporary, "--run-id", "run")
            route = (
                "--task", "task-01", "--role", "implementer", "--provider", "codex",
                "--model", "gpt-test", "--effort", "high", "--sandbox", "workspace-write",
                "--route-source", "local", "--route-sha256", "a" * 64,
                "--worktree", temporary, "--execution", "execution-01",
            )
            verbs = (
                ("execution-start", ()),
                ("execution-result", ("--started-at", "2026-10-07T00:00:00Z",
                                      "--status", "complete", "--exit-status", "0",
                                      "--output", "handoff.md")),
            )
            for verb, extra in verbs:
                for option in ("--route-source", "--route-sha256"):
                    with self.subTest(verb=verb, missing=option):
                        index = route.index(option)
                        without = route[:index] + route[index + 2:]
                        result = invoke("journal", verb, *identity, *without, *extra)
                        self.assertEqual(result.returncode, 2)
                        self.assertIn(option, result.stderr)
            self.assertFalse((Path(temporary) / ".codex-orchestrator").exists())

    def test_execution_start_preserves_caller_id_without_consulting_legacy_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".codex-orchestrator/runs/run/journal.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text(
                '{"type":"execution","execution":"execution-04"}\n',
                encoding="utf-8",
            )
            result = invoke(
                "journal", "execution-start", "--repo", temporary, "--run-id", "run",
                "--task", "t", "--role", "implementer", "--provider", "codex",
                "--model", "gpt-test", "--effort", "low", "--sandbox", "workspace-write",
                "--route-source", "local", "--route-sha256", "a" * 64,
                "--worktree", temporary, "--execution", "execution-04",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["execution_id"], "execution-04")

    def test_execution_start_accepts_arbitrary_string_ids_without_content_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = (
                "journal", "execution-start", "--repo", temporary, "--run-id", "run",
                "--task", "t", "--role", "implementer", "--provider", "codex",
                "--model", "gpt-test", "--effort", "low", "--sandbox", "workspace-write",
                "--route-source", "local", "--route-sha256", "a" * 64,
                "--worktree", temporary,
            )
            missing = invoke(*base)
            self.assertEqual(missing.returncode, 2)
            self.assertFalse((Path(temporary) / ".codex-orchestrator").exists())
            for execution in ("execution-100", "execution-1", "../execution-01", "custom id"):
                with self.subTest(execution=execution):
                    result = invoke(*base, "--execution", execution)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout)["execution_id"], execution)
