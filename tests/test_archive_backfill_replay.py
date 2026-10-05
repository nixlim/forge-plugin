"""Readmission-aware replay coverage for archive approval journals."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from tests._cli_loader import load_script
from tests._git_env import init_quiet_repository

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FORGE_SCRIPTS = SCRIPTS / "forge"
for import_root in (SCRIPTS, FORGE_SCRIPTS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from codex_orchestrator import builders, journal  # noqa: E402

CLOSING = load_script(
    "archive_backfill_replay_closing", FORGE_SCRIPTS / "archive_closing.py"
)


class ApprovalReplayFixture(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-approval-replay-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        initialized = init_quiet_repository(self.repo, "--quiet")
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.git("config", "user.name", "Approval Replay Fixture")
        self.git("config", "user.email", "approval-replay@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        (self.repo / "basis.txt").write_text("basis\n", encoding="utf-8")
        self.git("add", "basis.txt")
        self.git("commit", "--quiet", "-m", "fixture")
        self.head = self.git("rev-parse", "HEAD")

        self.run_id = "run-approval-replay"
        self.target = (
            self.repo / ".codex-orchestrator" / "runs" / "run-archive-target"
        )
        self.target_records = [
            {"type": "run_started", "run_id": self.target.name},
            {"type": "run_closed", "judgment": "passed"},
        ]
        self.environment = mock.patch.dict(
            os.environ, {"FORGE_SESSION_PID": str(os.getpid())}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        builders.run_open(
            self.repo,
            self.run_id,
            idempotency_key=self.key("open"),
            goal="Approve one archive operation",
            scope=["opening/**"],
            plugin_ref="forge-approval-replay-test",
        )
        builders.scope_change(
            self.repo,
            self.run_id,
            idempotency_key=self.key("readmit"),
            scope=["opening/**", "readmitted/**"],
        )
        builders.task_start(
            self.repo,
            self.run_id,
            idempotency_key=self.key("task"),
            task="task-readmitted",
            goal="Exercise the readmitted path",
            acceptance=["The task is replayable"],
            files=["readmitted/task.py"],
        )
        backfill = builders.decision_add(
            self.repo,
            self.run_id,
            idempotency_key=self.key("backfill approval"),
            resolution=(
                f"backfill-archive: {self.target.name} closing HEAD {self.head}; "
                f"archive HEAD {self.head}; judgment passed; approved replay"
            ),
            task=None,
            finding=None,
            outcome="operator_approval",
            risk=None,
            basis=(),
            binding_chain=None,
            binding_id=None,
        )
        legacy = builders.decision_add(
            self.repo,
            self.run_id,
            idempotency_key=self.key("legacy approval"),
            resolution=(
                f"legacy-archive-recovery: {self.target.name} recovered closing "
                f"HEAD {self.head}; approved replay"
            ),
            task=None,
            finding=None,
            outcome="operator_approval",
            risk=None,
            basis=(),
            binding_chain=None,
            binding_id=None,
        )
        self.tokens = {
            CLOSING.BACKFILL_APPROVAL_REFUSAL: (
                f"{self.run_id}:{backfill.records[0]['id']}"
            ),
            CLOSING.LEGACY_APPROVAL_REFUSAL: (
                f"{self.run_id}:{legacy.records[0]['id']}"
            ),
        }
        self.services = CLOSING.ClosingServices(
            self.run_git,
            self.stable_snapshot,
            self.only_record,
            self.unexpected_discrepancy,
            frozenset({"legacy-approval"}),
        )

    @staticmethod
    def key(label: str) -> str:
        return hashlib.sha256(label.encode("ascii")).hexdigest()

    def git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    @staticmethod
    def stable_snapshot(run_dir: Path) -> tuple[list[dict[str, object]], bytes]:
        raw = journal._stable_journal_read(run_dir / "journal.jsonl")
        records, issues = journal._decode_journal_snapshot(
            raw, allow_partial_final_line=False
        )
        if issues:
            raise AssertionError(issues)
        return [dict(record) for record in records], raw

    @staticmethod
    def run_git(
        repo: Path, *arguments: str
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *arguments],
            cwd=repo,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
        )

    @staticmethod
    def only_record(
        records: list[dict[str, object]], kind: str
    ) -> dict[str, object]:
        matches = [record for record in records if record.get("type") == kind]
        if len(matches) != 1:
            raise CLOSING.ArchiveRefusal("fixture invalid")
        return matches[0]

    @staticmethod
    def unexpected_discrepancy(code: str) -> None:
        raise AssertionError(f"unexpected authoritative discrepancy: {code}")

    def approval_evidence(self, refusal: str):
        return CLOSING._approval_evidence(
            self.repo,
            self.target,
            self.tokens[refusal],
            refusal,
            self.services,
        )

    def assert_replay_refuses(self, evidence) -> None:
        for refusal in (
            CLOSING.BACKFILL_APPROVAL_REFUSAL,
            CLOSING.LEGACY_APPROVAL_REFUSAL,
        ):
            with self.subTest(refusal=refusal), self.assertRaises(
                CLOSING.ArchiveRefusal
            ) as raised:
                CLOSING._replay_approval(evidence, self.repo, refusal)
            self.assertEqual(raised.exception.message, refusal)


class ApprovalReplayTests(ApprovalReplayFixture):
    def test_readmitted_task_is_accepted_by_both_approval_paths(self) -> None:
        backfill = CLOSING.backfill_closing_mode(
            self.repo,
            self.target,
            self.target_records,
            self.head,
            self.tokens[CLOSING.BACKFILL_APPROVAL_REFUSAL],
            self.services,
        )
        legacy = CLOSING.legacy_closing_mode(
            self.repo,
            self.target,
            CLOSING.LegacyRequest(
                self.target_records,
                self.head,
                self.tokens[CLOSING.LEGACY_APPROVAL_REFUSAL],
                True,
            ),
            self.services,
        )
        self.assertEqual(
            backfill.backfill_approval,
            self.tokens[CLOSING.BACKFILL_APPROVAL_REFUSAL],
        )
        self.assertEqual(
            legacy.legacy_approval,
            self.tokens[CLOSING.LEGACY_APPROVAL_REFUSAL],
        )

    def test_forcing_opening_scope_refuses_the_readmitted_task(self) -> None:
        opening_scope = ("opening/**",)
        with mock.patch.object(
            CLOSING,
            "_scope_after_replayed_record",
            side_effect=lambda _record, _scope: opening_scope,
        ):
            for refusal in (
                CLOSING.BACKFILL_APPROVAL_REFUSAL,
                CLOSING.LEGACY_APPROVAL_REFUSAL,
            ):
                with self.subTest(refusal=refusal), self.assertRaises(
                    CLOSING.ArchiveRefusal
                ) as raised:
                    self.approval_evidence(refusal)
                self.assertEqual(raised.exception.message, refusal)

    def test_task_outside_every_admitted_scope_refuses(self) -> None:
        evidence = self.approval_evidence(CLOSING.BACKFILL_APPROVAL_REFUSAL)
        records = [dict(record) for record in evidence.records]
        task = next(record for record in records if record.get("type") == "task")
        task["files"] = ["never-admitted/task.py"]
        self.assert_replay_refuses(replace(evidence, records=records))

    def test_later_readmission_does_not_retroactively_admit_task(self) -> None:
        evidence = self.approval_evidence(CLOSING.BACKFILL_APPROVAL_REFUSAL)
        records = [dict(record) for record in evidence.records]
        task_position = next(
            position
            for position, record in enumerate(records)
            if record.get("type") == "task"
        )
        readmission_position = next(
            position
            for position, record in enumerate(records)
            if record.get("resolution") == journal.READMISSION_RESOLUTION
        )
        self.assertEqual(readmission_position + 1, task_position)
        records[readmission_position], records[task_position] = (
            records[task_position],
            records[readmission_position],
        )

        with mock.patch.object(
            CLOSING,
            "_scope_after_replayed_record",
            wraps=CLOSING._scope_after_replayed_record,
        ) as advance_scope:
            self.assert_replay_refuses(replace(evidence, records=records))
        self.assertFalse(
            any(
                call.args[0].get("type") == "task"
                for call in advance_scope.call_args_list
            )
        )

    def test_narrowed_readmission_drops_opening_scope(self) -> None:
        evidence = self.approval_evidence(CLOSING.BACKFILL_APPROVAL_REFUSAL)
        records = [dict(record) for record in evidence.records]
        readmission = next(
            record
            for record in records
            if record.get("resolution") == journal.READMISSION_RESOLUTION
        )
        readmission["scope"] = ["readmitted/**"]
        task = next(record for record in records if record.get("type") == "task")
        task["files"] = ["opening/task.py"]

        self.assert_replay_refuses(replace(evidence, records=records))

    def test_malformed_readmission_record_refuses(self) -> None:
        evidence = self.approval_evidence(CLOSING.BACKFILL_APPROVAL_REFUSAL)
        records = [dict(record) for record in evidence.records]
        readmission = next(
            record
            for record in records
            if record.get("resolution") == journal.READMISSION_RESOLUTION
        )
        readmission["scope"] = ["../outside"]
        self.assert_replay_refuses(replace(evidence, records=records))


if __name__ == "__main__":
    unittest.main()
