"""New-write coverage for the canonical route vocabulary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/forge"))

import route_vocab  # noqa: E402

import codex_orch_tools  # noqa: E402
from codex_orchestrator import builders, journal  # noqa: E402

PATTERNS = ROOT / "scripts/forge/journal-patterns.py"
LEGACY_FIXTURE = ROOT / "tests/replay/gates-missing-gate-3"
RUN_ID = "run-20260923-vocabulary-writers"
RECORDED_AT = "2026-09-23T12:00:00Z"


def key(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def refusal(field: str, raw: str, replacement: str) -> str:
    return (
        "forge: journal append refused — invalid journal record: "
        f"execution {field} {raw!r} is not canonical; use {replacement}"
    )


class VocabularyWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-vocabulary-writers-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        subprocess.run(["git", "init", "--quiet", str(self.repo)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "-c",
                "user.name=Vocabulary Tests",
                "-c",
                "user.email=vocabulary@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--allow-empty",
                "--quiet",
                "-m",
                "base",
            ],
            check=True,
        )
        self.head = self.git("rev-parse", "HEAD").stdout.strip()
        self.environment = mock.patch.dict(
            os.environ, {"FORGE_SESSION_PID": str(os.getpid())}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        builders.run_open(
            self.repo,
            RUN_ID,
            idempotency_key=key("open"),
            goal="Exercise canonical route writes",
            scope=["src/**"],
            plugin_ref="forge-test-route-v2",
        )
        builders.task_start(
            self.repo,
            RUN_ID,
            idempotency_key=key("task"),
            task="task-01",
            goal="Exercise vocabulary validation",
            acceptance=["Canonical execution records are the only new writes"],
            files=["src/example.py"],
        )
        run_dir = self.repo / ".codex-orchestrator/runs" / RUN_ID
        for relative in ("prompt.md", "events.jsonl", "handoff.md"):
            (run_dir / relative).write_text("evidence\n", encoding="utf-8")
        self.execution_number = 0

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def execution_arguments(self, **updates: object) -> dict[str, object]:
        self.execution_number += 1
        arguments: dict[str, object] = {
            "idempotency_key": key(f"execution-{self.execution_number}-{updates!r}"),
            "agent": f"vocabulary-agent-{self.execution_number:02d}",
            "task": "task-01",
            "provider": "codex",
            "role": "implementer",
            "mode": "headless",
            "model": "gpt-vocabulary",
            "effort": "high",
            "worktree": str(self.repo.resolve()),
            "head": self.head,
            "prompt": "prompt.md",
            "handoff": "handoff.md",
            "event_source": "exec",
            "events": "events.jsonl",
        }
        arguments.update(updates)
        return arguments

    def execution_record(self, **updates: object) -> dict[str, object]:
        record: dict[str, object] = {
            "type": "execution",
            "recorded_at": RECORDED_AT,
            "run_id": RUN_ID,
            "execution": "execution-01",
            "agent": "vocabulary-agent-01",
            "task": "task-01",
            "provider": "codex",
            "role": "implementer",
            "mode": "headless",
            "model": "gpt-vocabulary",
            "effort": "high",
            "worktree": str(self.repo.resolve()),
            "head": self.head,
            "prompt": "prompt.md",
            "handoff": "handoff.md",
            "event_source": "exec",
            "events": "events.jsonl",
        }
        record.update(updates)
        return record

    def legacy_cases(self) -> tuple[tuple[str, str, str, dict[str, str]], ...]:
        mode_ids = "one of " + ", ".join(route_vocab.MODE_IDS)
        return (
            ("role", "implementation", "implementer", {}),
            ("role", "implement", "implementer", {}),
            ("role", "review", "review-cheap", {}),
            ("role", "reviewer", "review-cheap", {}),
            ("role", "review", "review-final", {"provider": "claude"}),
            ("role", "reviewer", "review-final", {"provider": "claude"}),
            ("provider", "codex-cli", "codex", {}),
            ("event_source", "codex", "exec", {}),
            ("event_source", "agent-tool", "claude", {}),
            ("event_source", "capture/events.jsonl", "exec", {}),
            ("mode", "read-only", mode_ids, {}),
            ("mode", "workspace-write", mode_ids, {}),
            ("mode", "orchestrator-inline", mode_ids, {}),
        )

    def assert_builder_refuses(self, case: tuple[str, str, str, dict[str, str]]) -> None:
        field, raw, replacement, context = case
        arguments = self.execution_arguments(**context, **{field: raw})
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            builders.execution_start(self.repo, RUN_ID, **arguments)
        self.assertEqual(refusal(field, raw, replacement), str(caught.exception))

    def assert_append_refuses(self, case: tuple[str, str, str, dict[str, str]]) -> None:
        field, raw, replacement, context = case
        record = self.execution_record(**context, **{field: raw})
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            journal._validate_proposed_record(
                record,
                run_id=RUN_ID,
                repo_root=self.repo.resolve(),
                scope=("src/**",),
            )
        self.assertEqual(refusal(field, raw, replacement), str(caught.exception))

    def test_every_legacy_spelling_is_refused_by_both_new_write_surfaces(self) -> None:
        for case in self.legacy_cases():
            field, raw, _replacement, context = case
            with self.subTest(surface="builder", field=field, raw=raw, context=context):
                self.assert_builder_refuses(case)
            with self.subTest(surface="append", field=field, raw=raw, context=context):
                self.assert_append_refuses(case)

    def test_refusal_tests_fail_when_the_shared_validator_is_disabled(self) -> None:
        case = ("role", "implementation", "implementer", {})
        self.assert_builder_refuses(case)
        self.assert_append_refuses(case)
        with mock.patch.object(route_vocab, "validate_new_write", return_value=None):
            with self.assertRaises(AssertionError):
                self.assert_builder_refuses(case)
            with self.assertRaises(AssertionError):
                self.assert_append_refuses(case)

    def test_route_vocabulary_refusal_precedes_sandbox_validation(self) -> None:
        for sandbox in (7, "unconfined"):
            with self.subTest(surface="builder", sandbox=sandbox):
                with self.assertRaises(journal.CoordinationRefusal) as caught:
                    builders.execution_start(
                        self.repo,
                        RUN_ID,
                        **self.execution_arguments(
                            role="implementation", sandbox=sandbox
                        ),
                    )
                self.assertEqual(
                    refusal("role", "implementation", "implementer"),
                    str(caught.exception),
                )
            with self.subTest(surface="append", sandbox=sandbox):
                with self.assertRaises(journal.CoordinationRefusal) as caught:
                    journal._validate_proposed_record(
                        self.execution_record(
                            role="implementation", sandbox=sandbox
                        ),
                        run_id=RUN_ID,
                        repo_root=self.repo.resolve(),
                        scope=("src/**",),
                    )
                self.assertEqual(
                    refusal("role", "implementation", "implementer"),
                    str(caught.exception),
                )

    def test_canonical_writes_accept_all_ids_and_claude_implementer(self) -> None:
        cases = (
            ("claude", "implementer", "headless", "exec"),
            ("codex", "review-cheap", "detached", "claude"),
            ("claude", "review-final", "subagent", "exec"),
            ("codex", "plan", "teammate", "claude"),
            ("codex", "monitoring", "headless", "exec"),
        )
        for provider, role, mode, event_source in cases:
            with self.subTest(
                provider=provider, role=role, mode=mode, event_source=event_source
            ):
                arguments = self.execution_arguments(
                    provider=provider, role=role, mode=mode, event_source=event_source
                )
                outcome = builders.execution_start(self.repo, RUN_ID, **arguments)
                record = outcome.records[0]
                self.assertEqual(
                    (provider, role, mode, event_source),
                    tuple(record[field] for field in ("provider", "role", "mode", "event_source")),
                )

    def test_sandbox_is_optional_and_accepts_only_known_values(self) -> None:
        without_sandbox = builders.execution_start(
            self.repo, RUN_ID, **self.execution_arguments()
        ).records[0]
        self.assertNotIn("sandbox", without_sandbox)
        for sandbox in route_vocab.SANDBOX_IDS:
            with self.subTest(sandbox=sandbox):
                outcome = builders.execution_start(
                    self.repo,
                    RUN_ID,
                    **self.execution_arguments(sandbox=sandbox),
                )
                self.assertEqual(sandbox, outcome.records[0]["sandbox"])
                journal._validate_proposed_record(
                    self.execution_record(sandbox=sandbox),
                    run_id=RUN_ID,
                    repo_root=self.repo.resolve(),
                    scope=("src/**",),
                )

        diagnostic = (
            f"{journal.INVALID_JOURNAL_RECORD}: execution.sandbox must be one of "
            + ", ".join(route_vocab.SANDBOX_IDS)
        )
        for surface in ("builder", "append"):
            with self.subTest(surface=surface):
                with self.assertRaises(journal.CoordinationRefusal) as caught:
                    if surface == "builder":
                        builders.execution_start(
                            self.repo,
                            RUN_ID,
                            **self.execution_arguments(sandbox="unconfined"),
                        )
                    else:
                        journal._validate_proposed_record(
                            self.execution_record(sandbox="unconfined"),
                            run_id=RUN_ID,
                            repo_root=self.repo.resolve(),
                            scope=("src/**",),
                        )
                self.assertEqual(diagnostic, str(caught.exception))

    def test_execution_start_parser_exposes_optional_sandbox(self) -> None:
        arguments = [
            "journal",
            "execution-start",
            "--repo",
            str(self.repo),
            "--run-id",
            RUN_ID,
            "--idempotency-key",
            key("parser"),
            "--agent",
            "agent-01",
            "--task",
            "task-01",
            "--provider",
            "codex",
            "--role",
            "implementer",
            "--mode",
            "headless",
            "--model",
            "gpt-vocabulary",
            "--effort",
            "high",
            "--worktree",
            str(self.repo),
            "--head",
            self.head,
            "--prompt",
            "prompt.md",
            "--handoff",
            "handoff.md",
            "--event-source",
            "exec",
            "--events",
            "events.jsonl",
        ]
        self.assertIsNone(codex_orch_tools._typed_parser().parse_args(arguments).sandbox)
        for sandbox in route_vocab.SANDBOX_IDS:
            with self.subTest(sandbox=sandbox):
                parsed = codex_orch_tools._typed_parser().parse_args(
                    [*arguments, "--sandbox", sandbox]
                )
                self.assertEqual(sandbox, parsed.sandbox)

        legacy = list(arguments)
        legacy[legacy.index("implementer")] = "implementation"
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/codex_orch_tools.py"), *legacy],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual(
            refusal("role", "implementation", "implementer") + "\n",
            result.stderr,
        )

    def test_writer_surfaces_change_together_without_legacy_literals(self) -> None:
        sources = {
            "builder": self.source_between(
                "scripts/codex_orchestrator/builders.py",
                "def execution_start(",
                "def execution_result(",
            ),
            "append": self.source_between(
                "scripts/codex_orchestrator/journal.py",
                '    if kind == "execution":',
                '    if kind == "execution_result":',
            ),
            "parser": self.source_between(
                "scripts/codex_orch_tools.py",
                '    execution_started = journal_subparsers.add_parser("execution-start")',
                '    execution_finished = journal_subparsers.add_parser("execution-result")',
            ),
            "dispatch": self.source_between(
                "scripts/codex_orch_tools.py",
                '        elif args.journal_command == "execution-start":',
                '        elif args.journal_command == "execution-result":',
            ),
        }
        self.assertNotIn("route_vocab.validate_new_write(", sources["builder"])
        self.assertIn("route_vocab.validate_new_write(", sources["append"])
        for surface, source in sources.items():
            with self.subTest(surface=surface):
                self.assertIn("sandbox", source)
                for literal in (
                    '"implementation"',
                    '"implement"',
                    '"review"',
                    '"reviewer"',
                    '"codex-cli"',
                    '"agent-tool"',
                    '"read-only"',
                    '"workspace-write"',
                    '"orchestrator-inline"',
                ):
                    self.assertNotIn(literal, source)
                self.assertIsNone(re.search(r'["\'][^"\']*/events\.jsonl["\']', source))

    def source_between(self, relative: str, start: str, end: str) -> str:
        source = (ROOT / relative).read_text(encoding="utf-8")
        self.assertEqual(1, source.count(start), start)
        tail = source.split(start, 1)[1]
        self.assertIn(end, tail)
        return start + tail.split(end, 1)[0]

    def test_historical_legacy_fixture_still_validates_and_extracts_patterns(self) -> None:
        historical = self.repo / ".codex-orchestrator/runs/run-historical-vocabulary"
        shutil.copytree(LEGACY_FIXTURE, historical)
        journal_path = historical / "journal.jsonl"
        records, read_issues = journal.read_journal(journal_path)
        self.assertEqual([], read_issues)
        self.assertTrue(
            any(
                record.get("type") == "execution"
                and record.get("role") == "implementation"
                for record in records
            )
        )

        validation = journal.validate_run(historical, gates=False)
        self.assertEqual(
            {
                "ok": True,
                "issues": [],
                "warnings": [],
                "non_passing_verifications": [],
            },
            validation,
        )
        patterns = subprocess.run(
            [
                sys.executable,
                str(PATTERNS),
                "--repo",
                str(self.repo),
                "--revision",
                self.head,
                str(journal_path),
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, patterns.returncode, patterns.stderr)
        payload = json.loads(patterns.stdout)
        self.assertTrue(payload["available"])


if __name__ == "__main__":
    unittest.main()
