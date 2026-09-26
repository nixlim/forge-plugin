"""Historical archive replay coverage for the Route V2 writer vocabulary."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
ARCHIVER = ROOT / "scripts" / "forge" / "archive-run.py"
RECOVERY_RUN_ID = "recovery-route-vocabulary"
TARGET_RUN_ID = "legacy-route-target"


def load_archiver() -> object:
    name = "_forge_archive_replay_vocabulary_tests"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    specification = importlib.util.spec_from_file_location(name, ARCHIVER)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def key(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


archive = load_archiver()


class ArchiveReplayVocabularyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-archive-replay-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Archive Replay"],
            cwd=self.repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "replay@example.invalid"],
            cwd=self.repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"],
            cwd=self.repo,
            check=True,
        )
        (self.repo / ".gitignore").write_text(
            ".codex-orchestrator/\n", encoding="utf-8"
        )
        (self.repo / "tracked").write_text("fixture\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", ".gitignore", "tracked"], cwd=self.repo, check=True
        )
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "fixture"],
            cwd=self.repo,
            check=True,
        )
        self.head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.environment = mock.patch.dict(
            os.environ, {"FORGE_SESSION_PID": str(os.getpid())}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self._build_recovery_run()
        self._build_target_run()

    def _build_recovery_run(self) -> None:
        builders = archive.journal_builders
        builders.run_open(
            self.repo,
            RECOVERY_RUN_ID,
            idempotency_key=key("open recovery"),
            goal="Approve one historical archive recovery",
            scope=["tracked"],
            plugin_ref="forge-test-route-v2",
        )
        builders.task_start(
            self.repo,
            RECOVERY_RUN_ID,
            idempotency_key=key("start recovery task"),
            task="task-01",
            goal="Recover the historical archive",
            acceptance=["The historical journal remains readable"],
            files=["tracked"],
        )
        self.recovery = (
            self.repo / ".codex-orchestrator" / "runs" / RECOVERY_RUN_ID
        )
        for name in ("prompt.md", "handoff.md", "events.jsonl"):
            (self.recovery / name).write_text("fixture\n", encoding="utf-8")

        route_vocab = archive.journal_engine.route_vocab
        with mock.patch.object(route_vocab, "validate_new_write", return_value=None):
            builders.execution_start(
                self.repo,
                RECOVERY_RUN_ID,
                **self.execution_arguments(
                    "implementation",
                    agent="legacy-implementer",
                    provider="codex-cli",
                    role="implementation",
                    mode="read-only",
                    event_source="legacy/path/events.jsonl",
                ),
            )
            builders.execution_start(
                self.repo,
                RECOVERY_RUN_ID,
                **self.execution_arguments(
                    "reviewer",
                    agent="legacy-reviewer",
                    provider="claude",
                    role="reviewer",
                    mode="read-only",
                    event_source="agent-tool",
                ),
            )

        self.resolution = (
            f"legacy-archive-recovery: {TARGET_RUN_ID} recovered closing HEAD "
            f"{self.head}; operator verified the historical route records"
        )
        decision = builders.decision_add(
            self.repo,
            RECOVERY_RUN_ID,
            idempotency_key=key("approve recovery"),
            resolution=self.resolution,
            task=None,
            finding=None,
            outcome="operator_approval",
            risk=None,
            basis=(),
            binding_chain=None,
            binding_id=None,
        )
        self.approval = f"{RECOVERY_RUN_ID}:{decision.records[0]['id']}"
        self._install_historical_lone_sandbox()

    def _install_historical_lone_sandbox(self) -> None:
        # Model pre-DM-018 persisted data while retaining stable-read receipt
        # coverage for the rewritten canonical journal bytes.
        journal = self.recovery / "journal.jsonl"
        ledger = self.recovery / archive.journal_engine.BATCH_RECEIPTS_NAME
        records = [json.loads(line) for line in journal.read_bytes().splitlines()]
        receipts = [json.loads(line) for line in ledger.read_bytes().splitlines()]
        reviewer = next(
            record for record in records if record.get("agent") == "legacy-reviewer"
        )
        reviewer["sandbox"] = "danger-full-access"
        batches = [archive.journal_engine._journal_line(record) for record in records]
        self.assertEqual(len(batches), len(receipts))
        journal_raw = b""
        for receipt, batch_bytes in zip(receipts, batches, strict=True):
            receipt["base_size"] = len(journal_raw)
            receipt["batch_sha256"] = hashlib.sha256(batch_bytes).hexdigest()
            journal_raw += batch_bytes
            receipt["journal_size"] = len(journal_raw)
            receipt["journal_sha256"] = hashlib.sha256(journal_raw).hexdigest()
        journal.write_bytes(journal_raw)
        ledger.write_bytes(
            b"".join(
                archive.journal_engine._canonical_json_bytes(receipt) + b"\n"
                for receipt in receipts
            )
        )

    def execution_arguments(self, label: str, **updates: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "idempotency_key": key(f"execution {label}"),
            "agent": f"agent-{label}",
            "task": "task-01",
            "provider": "codex",
            "role": "implementer",
            "mode": "headless",
            "model": "historical-model",
            "effort": "high",
            "worktree": str(self.repo),
            "head": self.head,
            "prompt": "prompt.md",
            "handoff": "handoff.md",
            "event_source": "exec",
            "events": "events.jsonl",
        }
        arguments.update(updates)
        if arguments["event_source"] != "exec":
            arguments["events"] = None
        return arguments

    def _build_target_run(self) -> None:
        self.target = self.repo / ".codex-orchestrator" / "runs" / TARGET_RUN_ID
        self.target.mkdir()
        records = (
            {
                "type": "run_started",
                "run_id": TARGET_RUN_ID,
                "repo": str(self.repo),
                "repo_head": self.head,
                "goal": "Preserve one historical run",
                "scope": ["tracked"],
            },
            {"type": "run_closed", "judgment": "passed"},
        )
        (self.target / "journal.jsonl").write_text(
            "".join(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )

    def closing_mode(self) -> object:
        return archive.closing_mode_from_options(
            repo=self.repo.resolve(),
            run_dir=self.target,
            closing_head=None,
            legacy_recovered_head=self.head,
            legacy_approval=self.approval,
            prove_legacy_approval=True,
        )

    def legacy_execution(self) -> dict[str, object]:
        records, _raw = archive.stable_journal_snapshot(self.recovery)
        return next(
            {
                name: value
                for name, value in record.items()
                if name != "_line"
            }
            for record in records
            if record.get("type") == "execution"
        )

    def test_legacy_vocabulary_recovery_archives_without_refusal(self) -> None:
        records, _raw = archive.stable_journal_snapshot(self.recovery)
        executions = [record for record in records if record.get("type") == "execution"]
        self.assertEqual(["implementation", "reviewer"], [row["role"] for row in executions])
        self.assertEqual(["codex-cli", "claude"], [row["provider"] for row in executions])
        self.assertEqual(
            ["legacy/path/events.jsonl", "agent-tool"],
            [row["event_source"] for row in executions],
        )
        self.assertEqual(["read-only", "read-only"], [row["mode"] for row in executions])
        self.assertEqual(
            archive.ClosingMode(self.head, self.approval), self.closing_mode()
        )

    def test_legacy_lone_sandbox_archives_without_route_trio_revalidation(self) -> None:
        records, _raw = archive.stable_journal_snapshot(self.recovery)
        reviewer = next(
            record for record in records if record.get("agent") == "legacy-reviewer"
        )
        self.assertEqual("danger-full-access", reviewer["sandbox"])
        self.assertNotIn("route_source", reviewer)
        self.assertNotIn("route_sha256", reviewer)
        with mock.patch.object(
            archive.journal_engine.route_evidence,
            "validate_execution",
            side_effect=AssertionError("historical route controls were invoked"),
        ):
            self.assertEqual(
                archive.ClosingMode(self.head, self.approval), self.closing_mode()
            )

    def test_dropping_replay_capability_refuses_legacy_rows(self) -> None:
        validator = archive.journal_engine._validate_proposed_record
        observed: list[object | None] = []
        refusals: list[str] = []

        def without_capability(record: object, **arguments: object) -> object:
            observed.append(arguments.pop("_historical_replay", None))
            try:
                return validator(record, **arguments)
            except archive.journal_engine.CoordinationRefusal as exc:
                refusals.append(str(exc))
                raise

        with mock.patch.object(
            archive.journal_engine,
            "_validate_proposed_record",
            new=without_capability,
        ):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal,
                "^forge: archive refused — legacy recovery approval missing or mismatched$",
            ):
                self.closing_mode()

        self.assertGreaterEqual(len(observed), 3)
        self.assertTrue(
            all(token is archive.journal_engine._HISTORICAL_REPLAY for token in observed)
        )
        self.assertEqual(
            [
                "forge: journal append refused — invalid journal record: execution role "
                "'implementation' is not canonical; use implementer"
            ],
            refusals,
        )

    def test_typed_builder_cannot_receive_replay_capability(self) -> None:
        builder = archive.journal_builders.execution_start
        self.assertNotIn("_historical_replay", inspect.signature(builder).parameters)
        arguments = self.execution_arguments("bypass", role="implementation")
        arguments["_historical_replay"] = archive.journal_engine._HISTORICAL_REPLAY
        journal_before = (self.recovery / "journal.jsonl").read_bytes()

        with self.assertRaisesRegex(TypeError, "unexpected keyword argument"):
            builder(self.repo, RECOVERY_RUN_ID, **arguments)

        arguments.pop("_historical_replay")
        with self.assertRaises(archive.journal_engine.CoordinationRefusal) as caught:
            builder(self.repo, RECOVERY_RUN_ID, **arguments)
        self.assertEqual(
            "forge: journal append refused — invalid journal record: execution role "
            "'implementation' is not canonical; use implementer",
            str(caught.exception),
        )
        self.assertEqual(journal_before, (self.recovery / "journal.jsonl").read_bytes())

    def test_replay_capability_is_identity_bound_and_keeps_shape_checks(self) -> None:
        record = self.legacy_execution()
        arguments = {
            "run_id": RECOVERY_RUN_ID,
            "repo_root": self.repo.resolve(),
            "scope": ("tracked",),
        }
        with self.assertRaises(archive.journal_engine.CoordinationRefusal) as wrong:
            archive.journal_engine._validate_proposed_record(
                record, **arguments, _historical_replay=object()
            )
        self.assertEqual(
            "forge: journal append refused — invalid journal record: execution role "
            "'implementation' is not canonical; use implementer",
            str(wrong.exception),
        )

        record["sandbox"] = 7
        with self.assertRaises(archive.journal_engine.CoordinationRefusal) as malformed:
            archive.journal_engine._validate_proposed_record(
                record,
                **arguments,
                _historical_replay=archive.journal_engine._HISTORICAL_REPLAY,
            )
        self.assertEqual(
            f"{archive.journal_engine.INVALID_JOURNAL_RECORD}: "
            "execution.sandbox must be a string",
            str(malformed.exception),
        )

        record.pop("sandbox")
        record["execution"] = "legacy-execution"
        with self.assertRaises(archive.journal_engine.CoordinationRefusal) as malformed:
            archive.journal_engine._validate_proposed_record(
                record,
                **arguments,
                _historical_replay=archive.journal_engine._HISTORICAL_REPLAY,
            )
        self.assertEqual(
            f"{archive.journal_engine.INVALID_JOURNAL_RECORD}: "
            "execution.execution must match execution-NN",
            str(malformed.exception),
        )


if __name__ == "__main__":
    unittest.main()
