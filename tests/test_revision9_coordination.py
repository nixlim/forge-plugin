from __future__ import annotations

import base64
import copy
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, nullcontext
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "scripts/codex_orch_tools.py"
FIXTURES = ROOT / "tests/fixtures"

sys.path.insert(0, str(ROOT / "scripts"))
from codex_orchestrator import batch, builders, journal  # noqa: E402


JOURNAL_FIXTURE_SHA256 = (
    "dd0695b47a37506a10efa9f7889855ada36e7cf9d09fdfdae284c57b049eed86"
)
OUTPUT_FIXTURE_SHA256 = (
    "41e563086b48340bb03f35734b6469551d9aab26efe14f12d38f88aebda3aa60"
)


def key(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class Revision9FixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-revision9-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.run_dir = Path(self.temporary.name) / "prose-and-position"
        self.run_dir.mkdir()
        shutil.copyfile(
            FIXTURES / "prose-and-position-journal.jsonl",
            self.run_dir / "journal.jsonl",
        )
        self.records = [
            json.loads(line)
            for line in (self.run_dir / "journal.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        for record in self.records:
            if record.get("type") != "execution":
                continue
            for field in ("prompt", "events"):
                self._materialize(str(record[field]))
            if record.get("agent") != "codex-impl-05":
                self._materialize(str(record["handoff"]))

    def _materialize(self, value: str) -> None:
        target = Path(value)
        if not target.is_absolute():
            target = self.run_dir / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture evidence\n", encoding="utf-8")

    def validate(self) -> dict[str, object]:
        return journal.validate_run(self.run_dir, gates=True)

    def test_pinned_fixture_hashes_and_old_comparator_partition(self) -> None:
        journal_bytes = (FIXTURES / "prose-and-position-journal.jsonl").read_bytes()
        output_bytes = (FIXTURES / "validate-gates-0.6.4-output.json").read_bytes()
        self.assertEqual(hashlib.sha256(journal_bytes).hexdigest(), JOURNAL_FIXTURE_SHA256)
        self.assertEqual(hashlib.sha256(output_bytes).hexdigest(), OUTPUT_FIXTURE_SHA256)
        self.assertEqual(len(journal_bytes.splitlines()), 109)

        comparator = json.loads(output_bytes)
        issues = comparator["issues"]
        self.assertEqual(len(issues), 18)
        self.assertEqual(
            sum("execution_result status is not terminal: completed" in item for item in issues),
            4,
        )
        self.assertEqual(sum("duplicate execution_result" in item for item in issues), 4)
        self.assertEqual(sum("duplicate decision id" in item for item in issues), 1)
        self.assertEqual(sum("unknown gate criterion" in item for item in issues), 1)
        self.assertEqual(sum("referenced evidence[0] file does not exist" in item for item in issues), 8)
        self.assertEqual(len(comparator["non_passing_verifications"]), 10)

    def test_declared_fixture_has_exact_enabled_outcome(self) -> None:
        result = self.validate()
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["profile"], "gates")
        self.assertEqual(len(result["warnings"]), 20)
        self.assertEqual(len(result["non_passing_verifications"]), 10)
        suffixes = (
            "interpreted execution_result status 'completed' as status 'complete'",
            "tolerated duplicate execution_result for ",
            "tolerated duplicate decision id decision-06; occurrences at lines 39, 104",
            "tolerated unknown gate criterion: gate-1 targeted tests: touched Go packages pass on the implementer worktree",
            "tolerated missing evidence[0] file: ",
        )
        for suffix in suffixes:
            self.assertTrue(any(suffix in warning for warning in result["warnings"]), suffix)

    def test_each_new_compatibility_control_restores_only_its_partition(self) -> None:
        cases = (
            ("execution-result-status", 4, "execution_result status is not terminal: completed"),
            ("duplicate-execution-result", 4, "duplicate execution_result"),
            ("duplicate-decision-id", 1, "duplicate decision id"),
            ("unknown-gate-criterion", 1, "unknown gate criterion"),
            ("missing-evidence-file", 8, "referenced evidence[0] file does not exist"),
        )
        for leg, expected_count, needle in cases:
            with self.subTest(leg=leg), mock.patch.object(
                journal,
                "LEGACY_COMPATIBILITY_LEGS",
                journal.LEGACY_COMPATIBILITY_LEGS - {leg},
            ):
                result = self.validate()
                self.assertEqual(len(result["issues"]), expected_count)
                self.assertTrue(all(needle in issue for issue in result["issues"]))

        status_map = dict(journal.LEGACY_EXECUTION_STATUS_MAP)
        status_map.pop("completed")
        with mock.patch.object(journal, "LEGACY_EXECUTION_STATUS_MAP", status_map):
            result = self.validate()
        self.assertEqual(len(result["issues"]), 4)
        self.assertTrue(
            all(
                "execution_result status is not terminal: completed" in issue
                for issue in result["issues"]
            )
        )


class Revision9BuilderBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-revision9-builder-")
        self.addCleanup(self.temporary.cleanup)
        self.env = os.environ.copy()
        self.env["FORGE_SESSION_PID"] = str(os.getpid())
        self.repo, self.head = self._new_repo("repo")

    def _new_repo(self, name: str) -> tuple[Path, str]:
        repo = Path(self.temporary.name) / name
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.name=Forge Tests",
                "-c",
                "user.email=forge-tests@example.invalid",
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
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return repo, head

    @contextmanager
    def api_environment(self):
        with mock.patch.dict(os.environ, self.env, clear=True):
            yield

    def run_dir(self, repo: Path, run_id: str) -> Path:
        return repo / ".codex-orchestrator/runs" / run_id

    def open_run(self, repo: Path, run_id: str, label: str = "open") -> batch.BatchOutcome:
        return builders.run_open(
            repo,
            run_id,
            idempotency_key=key(f"{run_id}-{label}"),
            goal="Exercise Revision 9",
            scope=["src/**"],
            plugin_ref="forge-test-revision-9",
        )

    def start_task(self, repo: Path, run_id: str, label: str = "task") -> batch.BatchOutcome:
        return builders.task_start(
            repo,
            run_id,
            idempotency_key=key(f"{run_id}-{label}"),
            task="task-01",
            goal="Implement the typed transaction",
            acceptance=["The focused behavior passes"],
            files=["src/example.py"],
        )

    def test_typed_builder_round_trip_ids_receipts_and_idempotency(self) -> None:
        run_id = "run-20260828-revision9-roundtrip"
        with self.api_environment():
            opened = self.open_run(self.repo, run_id)
            self.assertFalse(opened.repeated)
            self.assertEqual(opened.records[0]["writer_contract"], journal.WRITER_CONTRACT)
            repeated_open = self.open_run(self.repo, run_id)
            self.assertTrue(repeated_open.repeated)
            self.assertEqual(repeated_open.records, opened.records)

            started = self.start_task(self.repo, run_id)
            self.assertEqual(started.records[0]["status"], "active")
            repeated_task = self.start_task(self.repo, run_id)
            self.assertTrue(repeated_task.repeated)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                "idempotency key already names different content",
            ):
                builders.task_start(
                    self.repo,
                    run_id,
                    idempotency_key=key(f"{run_id}-task"),
                    task="task-01",
                    goal="Different content",
                    acceptance=["The focused behavior passes"],
                    files=["src/example.py"],
                )

            run_dir = self.run_dir(self.repo, run_id)
            for relative in ("prompt.md", "events.jsonl", "handoff.md"):
                (run_dir / relative).write_text("evidence\n", encoding="utf-8")
            execution = builders.execution_start(
                self.repo,
                run_id,
                idempotency_key=key("execution"),
                agent="codex-impl-01",
                task="task-01",
                provider="openai",
                role="implementation",
                mode="headless",
                model="gpt-test",
                effort="high",
                worktree=str(self.repo.resolve()),
                head=self.head,
                prompt="prompt.md",
                handoff="handoff.md",
                event_source="exec",
                events="events.jsonl",
            )
            self.assertEqual(execution.records[0]["execution"], "execution-01")
            builders.execution_result(
                self.repo,
                run_id,
                idempotency_key=key("result"),
                execution="execution-01",
                agent="codex-impl-01",
                task="task-01",
                status="complete",
                summary="Implementation complete",
                files_changed=["src/example.py"],
                caveats=[],
                handoff="handoff.md",
            )
            verification = builders.verification_add(
                self.repo,
                run_id,
                idempotency_key=key("verification"),
                task="task-01",
                criterion="focused Revision 9 behavior",
                method="unittest",
                check="python3 -m unittest",
                result="passed",
                observation="passed",
                evidence=[],
                binding_chain=None,
                binding_id=None,
            )
            decision = builders.decision_add(
                self.repo,
                run_id,
                idempotency_key=key("decision"),
                task="task-01",
                resolution="Use the verified implementation",
                finding=None,
                outcome=None,
                risk=None,
                basis=[],
                binding_chain=None,
                binding_id=None,
            )
            self.assertEqual(verification.records[0]["id"], "check-01")
            self.assertEqual(decision.records[0]["id"], "decision-01")
            builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=key("finish"),
                task="task-01",
                status="complete",
            )
            builders.run_close(
                self.repo,
                run_id,
                idempotency_key=key("close"),
                judgment="blocked",
                summary="Focused transaction complete; outer gates pending",
                risks=[],
                follow_ups=[],
            )

        records, issues = journal.read_journal(
            self.run_dir(self.repo, run_id) / "journal.jsonl"
        )
        self.assertEqual(issues, [])
        self.assertEqual([record["type"] for record in records], [
            "run_started", "task", "execution", "execution_result", "verification",
            "decision", "task", "run_closed",
        ])
        self.assertTrue(all(record["run_id"] == run_id for record in records))
        self.assertTrue(all("recorded_at" in record for record in records))
        receipts = [
            json.loads(line)
            for line in (
                self.run_dir(self.repo, run_id) / journal.BATCH_RECEIPTS_NAME
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(receipts), 8)
        self.assertTrue(all(receipt["schema"] == journal.BATCH_RECEIPT_SCHEMA for receipt in receipts))
        self.assertTrue(all(set(receipt) == batch._receipt_keys() for receipt in receipts))

    def _leave_complete_intent(
        self, repo: Path, run_id: str
    ) -> tuple[Path, dict[str, object]]:
        self.open_run(repo, run_id)
        def crash_after_journal(
            locked: batch.BatchLock,
            intent: dict[str, object],
            _observation: journal.FileObservation,
            **_kwargs: object,
        ) -> batch.BatchOutcome:
            batch_bytes = base64.urlsafe_b64decode(
                str(intent["batch_bytes"])
                + "=" * (-len(str(intent["batch_bytes"])) % 4)
            )
            descriptor = os.open(
                "journal.jsonl",
                os.O_WRONLY | os.O_APPEND,
                dir_fd=locked.run_descriptor,
            )
            try:
                os.write(descriptor, batch_bytes)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            raise RuntimeError("crash")

        with mock.patch.object(batch, "_recover_locked", side_effect=crash_after_journal):
            with self.assertRaisesRegex(RuntimeError, "crash"):
                self.start_task(repo, run_id)
        run_dir = self.run_dir(repo, run_id)
        intent = json.loads(
            (run_dir / journal.BATCH_INTENT_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(intent["schema"], journal.BATCH_INTENT_SCHEMA)
        self.assertEqual(set(intent), batch._intent_keys())
        self.assertNotIn("=", intent["batch_bytes"])
        self.assertNotIn("=", intent["receipt_bytes"])
        return run_dir, intent

    def _leave_base_intent(
        self, repo: Path, run_id: str
    ) -> tuple[Path, dict[str, object]]:
        self.open_run(repo, run_id)
        original = batch._write_intent

        def crash_after_intent(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("crash after intent")

        with mock.patch.object(batch, "_write_intent", side_effect=crash_after_intent):
            with self.assertRaisesRegex(RuntimeError, "crash after intent"):
                self.start_task(repo, run_id)
        run_dir = self.run_dir(repo, run_id)
        intent = json.loads(
            (run_dir / journal.BATCH_INTENT_NAME).read_text(encoding="utf-8")
        )
        return run_dir, intent

    def test_exact_prefix_and_torn_receipt_recovery(self) -> None:
        with self.api_environment():
            for suffix, tear_receipt in (("partial", False), ("receipt", True)):
                repo, _ = self._new_repo(f"repo-{suffix}")
                run_id = f"run-20260828-recovery-{suffix}"
                run_dir, intent = self._leave_complete_intent(repo, run_id)
                batch_bytes = base64.urlsafe_b64decode(
                    intent["batch_bytes"] + "=" * (-len(intent["batch_bytes"]) % 4)
                )
                journal_path = run_dir / "journal.jsonl"
                with journal_path.open("r+b") as stream:
                    stream.truncate(intent["base_size"])
                    stream.seek(intent["base_size"])
                    stream.write(batch_bytes[: max(1, len(batch_bytes) // 2)])
                if tear_receipt:
                    receipt_bytes = base64.urlsafe_b64decode(
                        intent["receipt_bytes"]
                        + "=" * (-len(intent["receipt_bytes"]) % 4)
                    )
                    ledger = run_dir / journal.BATCH_RECEIPTS_NAME
                    with ledger.open("ab") as stream:
                        stream.write(receipt_bytes[: max(1, len(receipt_bytes) // 2)])
                recovered = batch.recover_batch(repo, run_id)
                self.assertTrue(recovered.repeated)
                self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())
                self.assertEqual(recovered.records[0]["type"], "task")
                records, issues = journal.read_journal(journal_path)
                self.assertEqual(issues, [])
                self.assertEqual([record["type"] for record in records], ["run_started", "task"])

    def test_pending_reader_refuses_without_mutation_and_absent_lock_is_read_only(self) -> None:
        run_id = "run-20260828-reader-pending"
        with self.api_environment():
            run_dir, _ = self._leave_complete_intent(self.repo, run_id)
        before = {
            path.name: path.read_bytes()
            for path in run_dir.iterdir()
            if path.is_file()
        }
        records, issues = journal.read_journal(run_dir / "journal.jsonl")
        after = {
            path.name: path.read_bytes()
            for path in run_dir.iterdir()
            if path.is_file()
        }
        self.assertEqual(records, [])
        self.assertEqual(issues, [journal.JOURNAL_READ_TRANSACTION_REFUSAL])
        self.assertEqual(after, before)

        historical = Path(self.temporary.name) / "historical"
        historical.mkdir()
        historical_journal = historical / "journal.jsonl"
        historical_journal.write_bytes(journal._journal_line({"type": "historical"}))
        records, issues = journal.read_journal(historical_journal)
        self.assertEqual(issues, [])
        self.assertEqual(records[0]["type"], "historical")
        self.assertEqual(set(path.name for path in historical.iterdir()), {"journal.jsonl"})

    def test_torn_intent_never_becomes_authoritative(self) -> None:
        with self.api_environment():
            for cut in (1, -1):
                with self.subTest(cut=cut):
                    repo, _ = self._new_repo(f"repo-torn-intent-{cut}")
                    run_id = f"run-20260828-torn-intent-{str(cut).replace('-', 'last')}"
                    run_dir, _ = self._leave_base_intent(repo, run_id)
                    intent_path = run_dir / journal.BATCH_INTENT_NAME
                    raw = intent_path.read_bytes()
                    length = cut if cut > 0 else len(raw) + cut
                    with intent_path.open("r+b") as stream:
                        stream.truncate(length)
                    journal_before = (run_dir / "journal.jsonl").read_bytes()
                    receipts_before = (
                        run_dir / journal.BATCH_RECEIPTS_NAME
                    ).read_bytes()
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal, "journal diverged from intent"
                    ):
                        batch.recover_batch(repo, run_id)
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal, "journal diverged from intent"
                    ):
                        self.start_task(repo, run_id)
                    self.assertEqual(
                        (run_dir / "journal.jsonl").read_bytes(), journal_before
                    )
                    self.assertEqual(
                        (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(),
                        receipts_before,
                    )
                    self.assertEqual(intent_path.read_bytes(), raw[:length])

    def test_self_consistent_intent_substitution_after_prepare_is_refused(self) -> None:
        repo, _ = self._new_repo("repo-intent-substitution")
        run_id = "run-20260828-intent-substitution"
        with self.api_environment():
            self.open_run(repo, run_id)
            run_dir = self.run_dir(repo, run_id)
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            receipts_before = (
                run_dir / journal.BATCH_RECEIPTS_NAME
            ).read_bytes()
            original = batch._write_intent

            def substitute(locked: batch.BatchLock, intended: dict[str, object]) -> None:
                replacement = copy.deepcopy(intended)
                replacement_key = key("substituted-key")
                replacement_request = key("substituted-request")
                receipt_bytes = base64.urlsafe_b64decode(
                    str(replacement["receipt_bytes"])
                    + "=" * (-len(str(replacement["receipt_bytes"])) % 4)
                )
                receipt = json.loads(receipt_bytes)
                receipt["idempotency_key"] = replacement_key
                receipt["request_sha256"] = replacement_request
                substituted_receipt = journal._canonical_json_bytes(receipt) + b"\n"
                replacement["idempotency_key"] = replacement_key
                replacement["request_sha256"] = replacement_request
                replacement["receipt_bytes"] = (
                    base64.urlsafe_b64encode(substituted_receipt)
                    .rstrip(b"=")
                    .decode("ascii")
                )
                return original(locked, replacement)

            with mock.patch.object(batch, "_write_intent", side_effect=substitute):
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal, "journal diverged from intent"
                ):
                    self.start_task(repo, run_id)
            self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_before)
            self.assertEqual(
                (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(), receipts_before
            )

    def test_activated_missing_stable_lock_or_receipt_ledger_diverges(self) -> None:
        with self.api_environment():
            for missing_name in (
                journal.BATCH_LOCK_NAME,
                journal.BATCH_RECEIPTS_NAME,
            ):
                with self.subTest(missing_name=missing_name):
                    repo, _ = self._new_repo(
                        f"repo-missing-{missing_name.strip('.').replace('.', '-')}"
                    )
                    run_id = f"run-20260828-missing-{key(missing_name)[:8]}"
                    self.open_run(repo, run_id)
                    run_dir = self.run_dir(repo, run_id)
                    (run_dir / missing_name).unlink()
                    journal_before = (run_dir / "journal.jsonl").read_bytes()
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal, "journal diverged from intent"
                    ):
                        self.start_task(repo, run_id)
                    self.assertEqual(
                        (run_dir / "journal.jsonl").read_bytes(), journal_before
                    )
                    self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

    def test_ledger_wide_duplicate_and_unrelated_invalid_receipts_freeze(self) -> None:
        with self.api_environment():
            for attack in ("duplicate", "unrelated-invalid"):
                with self.subTest(attack=attack):
                    repo, _ = self._new_repo(f"repo-ledger-{attack}")
                    run_id = f"run-20260828-ledger-{attack}"
                    self.open_run(repo, run_id)
                    run_dir = self.run_dir(repo, run_id)
                    ledger = run_dir / journal.BATCH_RECEIPTS_NAME
                    opening_line = ledger.read_bytes()
                    if attack == "duplicate":
                        injected = opening_line
                    else:
                        unrelated = json.loads(opening_line)
                        unrelated.update(
                            {
                                "idempotency_key": key("unrelated-receipt"),
                                "request_sha256": key("unrelated-request"),
                                "journal_sha256": key("not-the-journal"),
                            }
                        )
                        injected = journal._canonical_json_bytes(unrelated) + b"\n"
                    with ledger.open("ab") as stream:
                        stream.write(injected)
                    ledger_before = ledger.read_bytes()
                    journal_before = (run_dir / "journal.jsonl").read_bytes()
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal, "journal diverged from intent"
                    ):
                        self.start_task(repo, run_id)
                    self.assertEqual(ledger.read_bytes(), ledger_before)
                    self.assertEqual(
                        (run_dir / "journal.jsonl").read_bytes(), journal_before
                    )

    def test_intent_without_journal_and_reentrant_pending_read_refuse_exactly(self) -> None:
        with self.api_environment():
            repo, _ = self._new_repo("repo-reader-no-journal")
            run_id = "run-20260828-reader-no-journal"
            run_dir, _ = self._leave_base_intent(repo, run_id)
            (run_dir / "journal.jsonl").unlink()
            records, issues = journal.read_journal(run_dir / "journal.jsonl")
            self.assertEqual(records, [])
            self.assertEqual(issues, [journal.JOURNAL_READ_TRANSACTION_REFUSAL])

            repo, _ = self._new_repo("repo-reader-reentrant")
            run_id = "run-20260828-reader-reentrant"
            run_dir, _ = self._leave_base_intent(repo, run_id)
            before = {
                path.name: path.read_bytes()
                for path in run_dir.iterdir()
                if path.is_file()
            }
            with batch.batch_lock(run_dir, create=False):
                records, issues = journal.read_journal(run_dir / "journal.jsonl")
            after = {
                path.name: path.read_bytes()
                for path in run_dir.iterdir()
                if path.is_file()
            }
            self.assertEqual(records, [])
            self.assertEqual(issues, [journal.JOURNAL_READ_TRANSACTION_REFUSAL])
            self.assertEqual(after, before)

    def test_midflight_intent_hardlink_fifo_and_foreign_uid_fences(self) -> None:
        with self.api_environment():
            for attack in ("hardlink", "fifo", "foreign-uid"):
                with self.subTest(attack=attack):
                    repo, _ = self._new_repo(f"repo-intent-node-{attack}")
                    run_id = f"run-20260828-intent-node-{attack}"
                    run_dir, _ = self._leave_base_intent(repo, run_id)
                    intent_path = run_dir / journal.BATCH_INTENT_NAME
                    intent_before = intent_path.read_bytes()
                    journal_before = (run_dir / "journal.jsonl").read_bytes()
                    patcher = None
                    if attack == "hardlink":
                        os.link(
                            intent_path,
                            Path(self.temporary.name) / "intent-hostile-hardlink",
                        )
                    elif attack == "fifo":
                        intent_path.unlink()
                        os.mkfifo(intent_path, 0o600)
                    else:
                        patcher = mock.patch.object(
                            batch.os, "geteuid", return_value=os.geteuid() + 1
                        )
                    context = patcher if patcher is not None else nullcontext()
                    with context, self.assertRaisesRegex(
                        journal.CoordinationRefusal, "journal diverged from intent"
                    ):
                        batch.recover_batch(repo, run_id)
                    self.assertEqual(
                        (run_dir / "journal.jsonl").read_bytes(), journal_before
                    )
                    if attack != "fifo":
                        self.assertEqual(intent_path.read_bytes(), intent_before)

    def test_batch_controls_are_load_bearing(self) -> None:
        with self.api_environment():
            pending_dir, _ = self._leave_complete_intent(
                self.repo, "run-20260828-control-reader"
            )
            with mock.patch.object(
                journal,
                "BATCH_TRANSACTION_CONTROLS",
                journal.BATCH_TRANSACTION_CONTROLS - {"reader-lock"},
            ):
                records, issues = journal.read_journal(pending_dir / "journal.jsonl")
            self.assertEqual(issues, [])
            # The helper deliberately leaves the complete stored task suffix
            # in the journal. Disabling the reader lock exposes those durable
            # bytes; it does not roll the journal back to the intent base.
            self.assertEqual(records[-1]["type"], "task")

            repo_intent, _ = self._new_repo("repo-control-intent")
            run_intent = "run-20260828-control-intent"
            self.open_run(repo_intent, run_intent)
            with mock.patch.object(
                journal,
                "BATCH_TRANSACTION_CONTROLS",
                journal.BATCH_TRANSACTION_CONTROLS - {"intent"},
            ):
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal, "journal diverged from intent"
                ):
                    self.start_task(repo_intent, run_intent)
            self.assertFalse(
                (self.run_dir(repo_intent, run_intent) / journal.BATCH_INTENT_NAME).exists()
            )

            repo_suffix, _ = self._new_repo("repo-control-suffix")
            run_suffix = "run-20260828-control-suffix"
            suffix_dir, intent = self._leave_complete_intent(repo_suffix, run_suffix)
            with (suffix_dir / "journal.jsonl").open("r+b") as stream:
                stream.truncate(intent["base_size"])
            with mock.patch.object(
                journal,
                "BATCH_TRANSACTION_CONTROLS",
                journal.BATCH_TRANSACTION_CONTROLS - {"journal-suffix"},
            ):
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal, "journal diverged from intent"
                ):
                    batch.recover_batch(repo_suffix, run_suffix)
            self.assertTrue((suffix_dir / journal.BATCH_INTENT_NAME).exists())

            repo_receipt, _ = self._new_repo("repo-control-receipt")
            run_receipt = "run-20260828-control-receipt"
            self.open_run(repo_receipt, run_receipt)
            ledger = self.run_dir(repo_receipt, run_receipt) / journal.BATCH_RECEIPTS_NAME
            before_lines = ledger.read_bytes().splitlines()
            with mock.patch.object(
                journal,
                "BATCH_TRANSACTION_CONTROLS",
                journal.BATCH_TRANSACTION_CONTROLS - {"receipt"},
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal, "journal diverged from intent"
            ):
                self.start_task(repo_receipt, run_receipt)
            self.assertEqual(ledger.read_bytes().splitlines(), before_lines)
            self.assertTrue(
                (
                    self.run_dir(repo_receipt, run_receipt)
                    / journal.BATCH_INTENT_NAME
                ).exists()
            )

    def test_builder_validation_controls_are_detected_in_memory(self) -> None:
        with self.api_environment():
            repo_derived, _ = self._new_repo("repo-control-derived")
            run_derived = "run-20260828-control-derived"
            self.open_run(repo_derived, run_derived)
            with mock.patch.object(
                builders,
                "BUILDER_VALIDATION_CONTROLS",
                builders.BUILDER_VALIDATION_CONTROLS - {"derived-fields"},
            ):
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal, journal.INVALID_JOURNAL_RECORD
                ):
                    self.start_task(repo_derived, run_derived)

            repo_relations, _ = self._new_repo("repo-control-relations")
            run_relations = "run-20260828-control-relations"
            self.open_run(repo_relations, run_relations)
            self.start_task(repo_relations, run_relations)
            with mock.patch.object(
                builders,
                "BUILDER_VALIDATION_CONTROLS",
                builders.BUILDER_VALIDATION_CONTROLS - {"relations"},
            ):
                duplicate = builders.task_start(
                    repo_relations,
                    run_relations,
                    idempotency_key=key("relations-disabled"),
                    task="task-01",
                    goal="Duplicate task",
                    acceptance=["This unsafe duplicate demonstrates the control"],
                    files=["src/example.py"],
                )
            self.assertEqual(duplicate.records[0]["id"], "task-01")

            with mock.patch.object(
                builders,
                "BUILDER_VALIDATION_CONTROLS",
                builders.BUILDER_VALIDATION_CONTROLS - {"binding-replay"},
            ):
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal, "binding replay control unavailable"
                ):
                    builders.resolve_binding(
                        repo_relations,
                        "c-2026-08-28T120000Z-abcd",
                        "0" * 64,
                    )

    def test_builder_request_schema_and_digest_are_exact(self) -> None:
        request, digest = batch.normalized_request(
            self.repo.resolve(),
            "run-20260828-request",
            "journal task-start",
            {
                "task": "task-01",
                "goal": "Goal",
                "acceptance": ["Acceptance"],
                "file": ["src/example.py"],
            },
        )
        self.assertEqual(
            request,
            {
                "schema": "forge-journal-builder-request/1",
                "verb": "journal task-start",
                "repository": str(self.repo.resolve()),
                "run_id": "run-20260828-request",
                "inputs": {
                    "task": "task-01",
                    "goal": "Goal",
                    "acceptance": ["Acceptance"],
                    "file": ["src/example.py"],
                },
            },
        )
        self.assertEqual(digest, journal._sha256(journal._canonical_json_bytes(request)))

    def test_run_open_is_hidden_until_atomic_publication(self) -> None:
        repo, _ = self._new_repo("repo-open-atomic")
        run_id = "run-20260828-open-atomic"
        target = self.run_dir(repo, run_id)
        original = journal._write_exclusive_at
        observed: list[tuple[str, bool]] = []

        def observe(directory_descriptor: int, name: str, payload: bytes, *args, **kwargs):
            result = original(directory_descriptor, name, payload, *args, **kwargs)
            if name in {
                journal.BATCH_LOCK_NAME,
                journal.BATCH_RECEIPTS_NAME,
                journal.BATCH_INTENT_NAME,
                "owner",
                "journal.jsonl",
            }:
                observed.append((name, target.exists()))
            return result

        with self.api_environment(), mock.patch.object(
            journal, "_write_exclusive_at", side_effect=observe
        ):
            self.open_run(repo, run_id)
        self.assertTrue(observed)
        self.assertTrue(all(not published for _name, published in observed))
        self.assertTrue(target.is_dir())
        self.assertFalse((target / journal.BATCH_INTENT_NAME).exists())
        self.assertEqual(
            set(path.name for path in target.iterdir()),
            {
                journal.BATCH_LOCK_NAME,
                journal.BATCH_RECEIPTS_NAME,
                "journal.jsonl",
                "owner",
            },
        )

    def test_run_open_prepublication_crashes_leave_no_visible_run(self) -> None:
        cases = ("journal-write", "publication-rename")
        for case in cases:
            with self.subTest(case=case):
                repo, _ = self._new_repo(f"repo-open-crash-{case}")
                run_id = f"run-20260828-open-crash-{case}"
                target = self.run_dir(repo, run_id)
                with self.api_environment():
                    if case == "journal-write":
                        original = journal._write_exclusive_at

                        def fail_journal(directory_descriptor, name, payload, *args, **kwargs):
                            if name == "journal.jsonl":
                                raise OSError("simulated journal staging crash")
                            return original(directory_descriptor, name, payload, *args, **kwargs)

                        patcher = mock.patch.object(
                            journal, "_write_exclusive_at", side_effect=fail_journal
                        )
                    else:
                        patcher = mock.patch.object(
                            journal,
                            "_move_name_noreplace_between_at",
                            side_effect=OSError("simulated publication crash"),
                        )
                    with patcher, self.assertRaises(journal.CoordinationRefusal):
                        self.open_run(repo, run_id)
                self.assertFalse(target.exists())
                runs_parent = repo / ".codex-orchestrator"
                staging = list(runs_parent.glob(f".run-open.{run_id}.*.staging"))
                self.assertEqual(staging, [])
                registry = repo / ".forge/tmp/run-registry.json"
                if registry.exists():
                    self.assertNotIn(run_id, registry.read_text(encoding="utf-8"))

    def test_run_open_durable_receipt_survives_registry_failure_and_retry(self) -> None:
        repo, _ = self._new_repo("repo-open-registry-retry")
        run_id = "run-20260828-open-registry-retry"
        original = journal._write_registry
        failures = 0

        def fail_once(*args, **kwargs):
            nonlocal failures
            failures += 1
            if failures == 1:
                raise journal.CoordinationRefusal(journal.REGISTRY_UPDATE_FAILED)
            return original(*args, **kwargs)

        with self.api_environment(), mock.patch.object(
            journal, "_write_registry", side_effect=fail_once
        ):
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, journal.REGISTRY_UPDATE_FAILED
            ):
                self.open_run(repo, run_id)
        target = self.run_dir(repo, run_id)
        self.assertTrue(target.is_dir())
        self.assertFalse((target / journal.BATCH_INTENT_NAME).exists())
        self.assertEqual(
            len((target / journal.BATCH_RECEIPTS_NAME).read_bytes().splitlines()), 1
        )
        with self.api_environment():
            retried = self.open_run(repo, run_id)
        self.assertTrue(retried.repeated)
        self.assertEqual(
            len((target / "journal.jsonl").read_bytes().splitlines()), 1
        )
        registry = json.loads(
            (repo / ".forge/tmp/run-registry.json").read_text(encoding="utf-8")
        )
        self.assertIn(run_id, [entry["run_id"] for entry in registry["open_runs"]])

    @unittest.skipUnless(hasattr(os, "fork"), "requires macOS/Linux fork semantics")
    def test_run_open_process_death_keeps_staging_invisible_and_retryable(self) -> None:
        repo, _ = self._new_repo("repo-open-process-death")
        run_id = "run-20260828-open-process-death"
        target = self.run_dir(repo, run_id)
        open_key = key("open")
        staging_name = journal._open_batch_staging_name(run_id, open_key)

        def invoke_open() -> batch.BatchOutcome:
            return builders.run_open(
                repo,
                run_id,
                idempotency_key=open_key,
                goal="Exercise Revision 9",
                scope=["src/**"],
                plugin_ref="forge-test-revision-9",
            )

        read_descriptor, write_descriptor = os.pipe()
        child = os.fork()
        if child == 0:
            try:
                os.close(read_descriptor)
                os.environ["FORGE_SESSION_PID"] = str(os.getpid())
                original = journal._write_exclusive_at

                def die_after_staged_journal(
                    directory_descriptor: int,
                    name: str,
                    payload: bytes,
                    *args,
                    **kwargs,
                ):
                    result = original(
                        directory_descriptor, name, payload, *args, **kwargs
                    )
                    if name == "journal.jsonl":
                        os.write(write_descriptor, b"staged")
                        os._exit(73)
                    return result

                with mock.patch.object(
                    journal,
                    "_write_exclusive_at",
                    side_effect=die_after_staged_journal,
                ):
                    invoke_open()
            except BaseException:
                os._exit(74)
            os._exit(75)
        os.close(write_descriptor)
        signal = os.read(read_descriptor, len(b"staged"))
        os.close(read_descriptor)
        waited, status = os.waitpid(child, 0)
        self.assertEqual(waited, child)
        self.assertEqual(signal, b"staged")
        self.assertTrue(os.WIFEXITED(status))
        self.assertEqual(os.WEXITSTATUS(status), 73)
        self.assertFalse(target.exists())
        registry = repo / ".forge/tmp/run-registry.json"
        if registry.exists():
            self.assertNotIn(run_id, registry.read_text(encoding="utf-8"))
        hidden = repo / ".codex-orchestrator" / staging_name
        self.assertTrue(hidden.is_dir())
        staged_journal = (hidden / "journal.jsonl").read_bytes()
        staged_intent = (hidden / journal.BATCH_INTENT_NAME).read_bytes()
        self.assertTrue(staged_journal.endswith(b"\n"))
        self.assertTrue(staged_intent.endswith(b"\n"))
        with self.api_environment():
            outcome = invoke_open()
        self.assertTrue(outcome.repeated)
        self.assertTrue(target.is_dir())
        self.assertEqual((target / "journal.jsonl").read_bytes(), staged_journal)
        self.assertEqual(outcome.records, (json.loads(staged_journal),))
        self.assertEqual(
            len((target / journal.BATCH_RECEIPTS_NAME).read_bytes().splitlines()),
            1,
        )
        self.assertFalse((target / journal.BATCH_INTENT_NAME).exists())
        self.assertFalse(hidden.exists())

    def test_fr019_failure_phase_order_preserves_earlier_bytes(self) -> None:
        repo, _ = self._new_repo("repo-phase-order")
        run_id = "run-20260828-phase-order"
        with self.api_environment():
            self.open_run(repo, run_id)
            self.start_task(repo, run_id)
        run_dir = self.run_dir(repo, run_id)
        journal_before = (run_dir / "journal.jsonl").read_bytes()
        receipts_before = (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes()
        owner_before = (run_dir / "owner").read_bytes()

        with self.api_environment(), self.assertRaisesRegex(
            journal.CoordinationRefusal,
            "execution_result.status must be one of complete, blocked, failed",
        ):
            builders.execution_result(
                repo,
                run_id,
                idempotency_key=key("phase-invalid-envelope"),
                execution="execution-99",
                agent="missing-agent",
                task="missing-task",
                status="completed",
                summary="invalid before relation lookup",
                files_changed=[],
                caveats=[],
                handoff=None,
            )
        self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_before)
        self.assertEqual(
            (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(), receipts_before
        )
        self.assertEqual((run_dir / "owner").read_bytes(), owner_before)
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

        with self.api_environment():
            current = journal._session_owner()
            stale_owner = journal._owner_bytes(
                journal.Owner(
                    pid=99999999,
                    host=current.host,
                    started_at="2026-08-28T00:00:00Z",
                )
            )
            (run_dir / "owner").write_bytes(stale_owner)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, "task task-01 already exists"
            ):
                builders.task_start(
                    repo,
                    run_id,
                    idempotency_key=key("phase-relation"),
                    task="task-01",
                    goal="Duplicate",
                    acceptance=["Duplicate must be rejected"],
                    files=["src/example.py"],
                )
        self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_before)
        self.assertEqual(
            (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(), receipts_before
        )
        self.assertEqual((run_dir / "owner").read_bytes(), stale_owner)

    def test_batch_crashes_recover_stored_bytes_without_duplicate_receipt(self) -> None:
        crash_points = ("intent", "after-journal", "suffix-proof", "intent-unlink")
        for crash_point in crash_points:
            with self.subTest(crash_point=crash_point):
                repo, _ = self._new_repo(f"repo-batch-crash-{crash_point}")
                run_id = f"run-20260828-batch-crash-{crash_point}"
                with self.api_environment():
                    self.open_run(repo, run_id)
                    run_dir = self.run_dir(repo, run_id)
                    original_intent = batch._write_intent
                    original_append = batch._append_missing_prefix
                    original_verify = batch._verify_receipt_journal
                    original_unlink = batch._unlink_intent
                    receipt_appends = 0

                    def crash_intent(*args, **kwargs):
                        original_intent(*args, **kwargs)
                        raise RuntimeError("crash after intent fsync")

                    def crash_after_journal(locked, name, *args, **kwargs):
                        nonlocal receipt_appends
                        result = original_append(locked, name, *args, **kwargs)
                        if name == "journal.jsonl":
                            raise RuntimeError("crash after journal suffix")
                        receipt_appends += int(name == journal.BATCH_RECEIPTS_NAME)
                        return result

                    def crash_verify(*args, **kwargs):
                        result = original_verify(*args, **kwargs)
                        receipt = args[1]
                        if receipt.get("idempotency_key") == key(
                            f"{run_id}-task"
                        ):
                            raise RuntimeError("crash after suffix proof")
                        return result

                    def crash_unlink(*args, **kwargs):
                        raise RuntimeError("crash before intent unlink")

                    patch_target, side_effect = {
                        "intent": ("_write_intent", crash_intent),
                        "after-journal": ("_append_missing_prefix", crash_after_journal),
                        "suffix-proof": ("_verify_receipt_journal", crash_verify),
                        "intent-unlink": ("_unlink_intent", crash_unlink),
                    }[crash_point]
                    with mock.patch.object(batch, patch_target, side_effect=side_effect):
                        with self.assertRaises(RuntimeError):
                            self.start_task(repo, run_id)
                    self.assertTrue((run_dir / journal.BATCH_INTENT_NAME).exists())
                    recovered = batch.recover_batch(repo, run_id)
                self.assertTrue(recovered.repeated)
                self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())
                self.assertEqual(
                    [
                        json.loads(line)["schema"]
                        for line in (
                            run_dir / journal.BATCH_RECEIPTS_NAME
                        ).read_text(encoding="utf-8").splitlines()
                    ],
                    [journal.BATCH_RECEIPT_SCHEMA, journal.BATCH_RECEIPT_SCHEMA],
                )
                self.assertEqual(
                    [json.loads(line)["type"] for line in (
                        run_dir / "journal.jsonl"
                    ).read_text(encoding="utf-8").splitlines()],
                    ["run_started", "task"],
                )

    def test_prepublication_intent_stage_crashes_retry_without_authority(self) -> None:
        if not hasattr(os, "fork"):
            self.skipTest("requires os.fork process-death injection")
        for crash_point, exit_code in (
            ("empty", 71),
            ("partial", 72),
            ("before-rename", 73),
        ):
            with self.subTest(crash_point=crash_point):
                repo, _ = self._new_repo(
                    f"repo-intent-stage-{crash_point}"
                )
                run_id = f"run-20260828-intent-stage-{crash_point}"
                with self.api_environment():
                    self.open_run(repo, run_id)
                    run_dir = self.run_dir(repo, run_id)
                    child = os.fork()
                    if child == 0:
                        def crash_write(
                            descriptor: int, payload: bytes
                        ) -> None:
                            if crash_point == "partial":
                                os.write(
                                    descriptor,
                                    payload[: max(1, len(payload) // 2)],
                                )
                                os.fsync(descriptor)
                            os._exit(exit_code)

                        def crash_move(*_args, **_kwargs) -> None:
                            os._exit(exit_code)

                        target = (
                            batch,
                            "_write_all",
                            crash_write,
                        ) if crash_point != "before-rename" else (
                            journal,
                            "_move_name_noreplace_at",
                            crash_move,
                        )
                        try:
                            with mock.patch.object(
                                target[0], target[1], side_effect=target[2]
                            ):
                                self.start_task(repo, run_id)
                        except BaseException:
                            os._exit(99)
                        os._exit(98)
                    waited, status = os.waitpid(child, 0)
                    self.assertEqual(waited, child)
                    self.assertTrue(os.WIFEXITED(status))
                    self.assertEqual(os.WEXITSTATUS(status), exit_code)
                    stages = [
                        path
                        for path in run_dir.iterdir()
                        if batch._INTENT_TEMP_PATTERN.fullmatch(path.name)
                    ]
                    self.assertEqual(len(stages), 1)
                    self.assertFalse(
                        (run_dir / journal.BATCH_INTENT_NAME).exists()
                    )
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal,
                        journal.BATCH_PENDING,
                    ):
                        batch.recover_batch(repo, run_id)
                    outcome = self.start_task(repo, run_id)
                self.assertFalse(outcome.repeated)
                self.assertFalse(
                    any(
                        batch._INTENT_TEMP_PATTERN.fullmatch(path.name)
                        for path in run_dir.iterdir()
                    )
                )
                records, issues = journal.read_journal(
                    run_dir / "journal.jsonl"
                )
                self.assertEqual(issues, [])
                self.assertEqual(
                    [record["type"] for record in records],
                    ["run_started", "task"],
                )

    def test_foreign_request_intent_stage_is_not_deleted(self) -> None:
        repo, _ = self._new_repo("repo-foreign-intent-stage")
        run_id = "run-20260828-foreign-intent-stage"
        with self.api_environment():
            self.open_run(repo, run_id)
            run_dir = self.run_dir(repo, run_id)
            planted = run_dir / batch._intent_temporary_name(
                key("foreign-intent-key"), key("foreign-intent-request")
            )
            planted.write_bytes(b"untrusted staging bytes")
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.BATCH_PENDING,
            ):
                self.start_task(repo, run_id)
        self.assertEqual(planted.read_bytes(), b"untrusted staging bytes")
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

    def test_intent_source_name_substitution_never_survives_canonical(self) -> None:
        repo, _ = self._new_repo("repo-intent-source-substitution")
        run_id = "run-20260828-intent-source-substitution"
        with self.api_environment():
            self.open_run(repo, run_id)
            run_dir = self.run_dir(repo, run_id)
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            receipts_before = (
                run_dir / journal.BATCH_RECEIPTS_NAME
            ).read_bytes()
            original_move = journal._move_name_noreplace_at

            def substitute_source(
                directory_descriptor: int,
                source_name: str,
                destination_name: str,
            ) -> None:
                if destination_name == journal.BATCH_INTENT_NAME:
                    os.unlink(source_name, dir_fd=directory_descriptor)
                    hostile = os.open(
                        source_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=directory_descriptor,
                    )
                    try:
                        os.write(hostile, b"foreign intent bytes\n")
                        os.fsync(hostile)
                    finally:
                        os.close(hostile)
                original_move(
                    directory_descriptor, source_name, destination_name
                )

            with mock.patch.object(
                journal,
                "_move_name_noreplace_at",
                side_effect=substitute_source,
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.BATCH_DIVERGED,
            ):
                self.start_task(repo, run_id)
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())
        quarantine = run_dir / batch._INTENT_QUARANTINE_NAME
        self.assertEqual(quarantine.read_bytes(), b"foreign intent bytes\n")
        self.assertFalse(
            any(
                batch._INTENT_TEMP_PATTERN.fullmatch(path.name)
                for path in run_dir.iterdir()
            )
        )
        self.assertEqual(
            (run_dir / "journal.jsonl").read_bytes(), journal_before
        )
        self.assertEqual(
            (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(),
            receipts_before,
        )
        with self.api_environment(), self.assertRaisesRegex(
            journal.CoordinationRefusal,
            journal.BATCH_DIVERGED,
        ):
            self.start_task(repo, run_id)
        with self.api_environment(), self.assertRaisesRegex(
            journal.CoordinationRefusal,
            journal.BATCH_DIVERGED,
        ):
            batch.recover_batch(repo, run_id)

    def test_intent_quarantine_preserves_a_second_canonical_swap(self) -> None:
        repo, _ = self._new_repo("repo-intent-quarantine-second-swap")
        run_id = "run-20260828-intent-quarantine-second-swap"
        first_bytes = b"first foreign intent bytes\n"
        second_bytes = b"unrelated replacement bytes\n"
        preserved_name = "hostile-preserved-first-intent"
        with self.api_environment():
            self.open_run(repo, run_id)
            run_dir = self.run_dir(repo, run_id)
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            receipts_before = (
                run_dir / journal.BATCH_RECEIPTS_NAME
            ).read_bytes()
            original_move = journal._move_name_noreplace_at

            def write_name(
                directory_descriptor: int, name: str, payload: bytes
            ) -> None:
                descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory_descriptor,
                )
                try:
                    os.write(descriptor, payload)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

            def swap_twice(
                directory_descriptor: int,
                source_name: str,
                destination_name: str,
            ) -> None:
                if destination_name == journal.BATCH_INTENT_NAME:
                    os.unlink(source_name, dir_fd=directory_descriptor)
                    write_name(
                        directory_descriptor, source_name, first_bytes
                    )
                elif destination_name == batch._INTENT_QUARANTINE_NAME:
                    original_move(
                        directory_descriptor, source_name, preserved_name
                    )
                    write_name(
                        directory_descriptor, source_name, second_bytes
                    )
                original_move(
                    directory_descriptor, source_name, destination_name
                )

            with mock.patch.object(
                journal,
                "_move_name_noreplace_at",
                side_effect=swap_twice,
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.BATCH_DIVERGED,
            ):
                self.start_task(repo, run_id)

        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())
        self.assertEqual(
            (run_dir / batch._INTENT_QUARANTINE_NAME).read_bytes(),
            second_bytes,
        )
        self.assertEqual((run_dir / preserved_name).read_bytes(), first_bytes)
        self.assertEqual(
            (run_dir / "journal.jsonl").read_bytes(), journal_before
        )
        self.assertEqual(
            (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(),
            receipts_before,
        )
        with self.api_environment(), self.assertRaisesRegex(
            journal.CoordinationRefusal,
            journal.BATCH_DIVERGED,
        ):
            self.start_task(repo, run_id)
        with self.api_environment(), self.assertRaisesRegex(
            journal.CoordinationRefusal,
            journal.BATCH_DIVERGED,
        ):
            batch.recover_batch(repo, run_id)
        self.assertEqual(
            (run_dir / batch._INTENT_QUARANTINE_NAME).read_bytes(),
            second_bytes,
        )
        self.assertEqual((run_dir / preserved_name).read_bytes(), first_bytes)

    def test_chain_drain_raw_records_without_capability_refuses(self) -> None:
        repo, _ = self._new_repo("repo-chain-drain-no-capability")
        run_id = "run-20260828-chain-drain-no-capability"
        chain_id = "c-2026-08-28T120000Z-abcd"
        source_digest = key("chain-drain-source-event")
        with self.api_environment():
            self.open_run(repo, run_id)
            run_dir = self.run_dir(repo, run_id)
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            receipts_before = (
                run_dir / journal.BATCH_RECEIPTS_NAME
            ).read_bytes()
            binding = {
                "schema": journal.BINDING_SCHEMA,
                "source_record": {
                    "chain_id": chain_id,
                    "event_digest": source_digest,
                },
                "candidate": {
                    "kind": "staged-diff-sha256",
                    "value": key("chain-drain-candidate"),
                },
                "review": None,
            }
            binding["binding_id"] = journal._sha256(
                journal._canonical_json_bytes(binding)
            )
            record = {
                "type": "decision",
                "recorded_at": "2026-08-28T12:00:00Z",
                "run_id": run_id,
                "id": "decision-01",
                "task": "task-01",
                "resolution": "Reject unauthenticated raw records",
                "outcome": "chain-landing",
                "basis": [],
                "binding": binding,
            }
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.INVALID_JOURNAL_RECORD,
            ):
                batch.drain_chain_batch(
                    repo,
                    run_id,
                    chain_id=chain_id,
                    source_event_digest=source_digest,
                    records=[record],
                )
        self.assertEqual(
            (run_dir / "journal.jsonl").read_bytes(), journal_before
        )
        self.assertEqual(
            (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(),
            receipts_before,
        )
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

    def test_hostile_transaction_nodes_and_midflight_inode_replacement_freeze(self) -> None:
        for attack in (
            "hardlinked-journal",
            "symlink-intent",
            "replaced-lock",
            "replaced-journal",
            "replaced-receipts",
        ):
            with self.subTest(attack=attack):
                repo, _ = self._new_repo(f"repo-hostile-{attack}")
                run_id = f"run-20260828-hostile-{attack}"
                with self.api_environment():
                    if attack in {"replaced-lock", "replaced-journal", "replaced-receipts"}:
                        run_dir, _intent = self._leave_complete_intent(repo, run_id)
                        replacement = Path(self.temporary.name) / f"{attack}.replacement"
                        target_name = (
                            journal.BATCH_LOCK_NAME
                            if attack == "replaced-lock"
                            else (
                                journal.BATCH_RECEIPTS_NAME
                                if attack == "replaced-receipts"
                                else "journal.jsonl"
                            )
                        )
                        replacement.write_bytes((run_dir / target_name).read_bytes())
                        original_recover = batch._recover_locked

                        def replace_then_recover(*args, **kwargs):
                            os.replace(replacement, run_dir / target_name)
                            return original_recover(*args, **kwargs)

                        with mock.patch.object(
                            batch, "_recover_locked", side_effect=replace_then_recover
                        ), self.assertRaisesRegex(
                            journal.CoordinationRefusal, "journal diverged from intent"
                        ):
                            batch.recover_batch(repo, run_id)
                        self.assertTrue((run_dir / journal.BATCH_INTENT_NAME).exists())
                        continue

                    self.open_run(repo, run_id)
                    run_dir = self.run_dir(repo, run_id)
                    journal_before = (run_dir / "journal.jsonl").read_bytes()
                    if attack == "hardlinked-journal":
                        os.link(
                            run_dir / "journal.jsonl",
                            Path(self.temporary.name) / f"{attack}.link",
                        )
                    else:
                        target = Path(self.temporary.name) / f"{attack}.target"
                        target.write_text("{}\n", encoding="utf-8")
                        os.symlink(target, run_dir / journal.BATCH_INTENT_NAME)
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal, "journal diverged from intent"
                    ):
                        self.start_task(repo, run_id)
                    self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_before)

    def _write_bound_chain_state(
        self,
        repo: Path,
        run_id: str,
        *,
        run_binding: object,
        outbox: object = None,
    ) -> tuple[str, Path]:
        chain_id = "c-2026-08-28T120000Z-abcd"
        chains = repo / ".forge/chains"
        chains.mkdir(parents=True, exist_ok=True)
        state_path = chains / f"{chain_id}.json"

        # Terminal controls authenticate a bound chain by replaying its event
        # stream before trusting either the materialized outbox or landing
        # state.  Keep malformed/unbound fixtures minimal for the controls
        # that intentionally stop before replay; valid bindings receive a
        # small, semantically valid commit history.
        if not (
            isinstance(run_binding, dict)
            and set(run_binding)
            == {"run_id", "task_id", "repository", "policy_digest"}
        ):
            state_path.write_bytes(
                journal._canonical_json_bytes(
                    {
                        "schema": "fixture-chain/1",
                        "chain_id": chain_id,
                        "run_binding": run_binding,
                        "journal_outbox": outbox,
                    }
                )
                + b"\n"
            )
            return chain_id, state_path

        paths = ["src/example.py"]
        candidate = key("terminal-candidate")
        inactive_after = "2026-08-29T12:00:00Z"
        state: dict[str, object] = {
            "schema": "forge-chain/1",
            "chain_id": chain_id,
            "kind": "commit",
            "state": "classifying",
            "created_at": "2026-08-28T12:00:00Z",
            "last_event_at": "2026-08-28T12:00:00Z",
            "inactive_after": inactive_after,
            "repo_head": "1" * 40,
            "policy_source": {
                "path": "forge-project.md",
                "sha": "1" * 40,
                "digest": run_binding["policy_digest"],
            },
            "paths": paths,
            "staging": {
                "worktree_root": str(repo.resolve()),
                "session_identity": "fixture",
                "staged_paths": [],
                "staged_at": None,
                "classification_runs": 0,
                "anomalies": [],
            },
            "candidate": {"sha256": None, "computed_at": None},
            "tier": {
                "declared": None,
                "derived": None,
                "effective": None,
                "control": False,
                "categories": [],
                "classification": None,
            },
            "steps": {},
            "review": {
                "iteration": 0,
                "request": None,
                "verdict": None,
                "dispositions": [],
                "operator_cosign_required": False,
                "residual_risk": None,
            },
            "approval": {},
            "authorization": {},
            "commit_result": {},
            "run_binding": copy.deepcopy(run_binding),
            "journal_outbox": None,
        }
        events: list[dict[str, object]] = []
        previous = "0" * 64

        def append_event(
            event_name: str,
            at: str,
            details: dict[str, object],
            snapshot: dict[str, object],
        ) -> None:
            nonlocal previous
            unsigned = {
                "sequence": len(events) + 1,
                "prev_digest": previous,
                "payload": {
                    "at": at,
                    "details": details,
                    "event": event_name,
                    "state": copy.deepcopy(snapshot),
                },
            }
            event = {
                **unsigned,
                "digest": journal._sha256(journal._canonical_json_bytes(unsigned)),
            }
            events.append(event)
            previous = str(event["digest"])

        append_event("chain_started", state["last_event_at"], {"paths": paths}, state)

        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-08-28T12:01:00Z"
        assert isinstance(state["staging"], dict)
        state["staging"]["staged_paths"] = paths
        state["staging"]["staged_at"] = state["last_event_at"]
        state["candidate"] = {
            "sha256": candidate,
            "computed_at": state["last_event_at"],
        }
        append_event(
            "candidate_staged",
            str(state["last_event_at"]),
            {"candidate": candidate, "paths": paths},
            state,
        )

        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-08-28T12:02:00Z"
        state["state"] = "verifying"
        assert isinstance(state["staging"], dict)
        state["staging"]["classification_runs"] = 1
        state["tier"] = {
            "declared": None,
            "derived": "fast",
            "effective": "fast",
            "control": False,
            "categories": [],
            "classification": {"fixture": True},
        }
        state["steps"] = {
            "classification": [
                {"candidate": candidate, "result": "passed"}
            ]
        }
        append_event(
            "classified",
            str(state["last_event_at"]),
            {"effective_tier": "fast", "control": False},
            state,
        )

        if outbox is not None:
            state = copy.deepcopy(state)
            state["last_event_at"] = "2026-08-28T12:03:00Z"
            assert isinstance(state["steps"], dict)
            state["steps"]["gate-1"] = [
                {"candidate": candidate, "result": "passed"}
            ]
            unsigned = {
                "sequence": len(events) + 1,
                "prev_digest": previous,
                "payload": {
                    "at": state["last_event_at"],
                    "details": {
                        "step_id": "gate-1",
                        "result": "passed",
                        "run": 1,
                    },
                    "event": "step_recorded",
                    "state": state,
                },
            }
            source_digest = journal._sha256(
                journal._canonical_json_bytes(unsigned)
            )
            binding_preimage = {
                "schema": journal.BINDING_SCHEMA,
                "source_record": {
                    "chain_id": chain_id,
                    "event_digest": source_digest,
                },
                "candidate": {
                    "kind": "staged-diff-sha256",
                    "value": candidate,
                },
                "review": None,
            }
            binding = {
                **binding_preimage,
                "binding_id": journal._sha256(
                    journal._canonical_json_bytes(binding_preimage)
                ),
            }
            record = {
                "type": "verification",
                "recorded_at": state["last_event_at"],
                "run_id": run_id,
                "id": "check-fixture",
                "task": run_binding["task_id"],
                "criterion": "gate-1: terminal fixture",
                "method": "fixture",
                "check": "fixture",
                "result": "passed",
                "observation": "fixture",
                "evidence": [],
                "binding": binding,
            }
            batch_bytes = journal._journal_line(record)
            journal_batch = {
                "idempotency_key": source_digest,
                "batch_digest": journal._sha256(batch_bytes),
                "record_count": 1,
                "records": [record],
            }
            assert isinstance(unsigned["payload"], dict)
            details = unsigned["payload"]["details"]
            assert isinstance(details, dict)
            details["source_event_digest"] = source_digest
            details["journal_batch"] = journal_batch
            state["journal_outbox"] = {
                "idempotency_key": source_digest,
                "batch_digest": journal_batch["batch_digest"],
                "record_count": 1,
                "source_event_digest": source_digest,
            }
            final_event = {
                **unsigned,
                "digest": journal._sha256(journal._canonical_json_bytes(unsigned)),
            }
            events.append(final_event)

        (chains / f"{chain_id}.events.jsonl").write_bytes(
            b"".join(
                journal._canonical_json_bytes(event) + b"\n" for event in events
            )
        )
        state_path.write_bytes(
            journal._canonical_json_bytes(state) + b"\n"
        )
        return chain_id, state_path

    def _chain_drain_case(
        self, name: str
    ) -> tuple[
        Path,
        str,
        str,
        str,
        tuple[dict[str, object], ...],
    ]:
        repo, run_id, run_binding = self._terminal_control_repo(name)
        chain_id, _ = self._write_bound_chain_state(
            repo,
            run_id,
            run_binding=run_binding,
            outbox={"fixture": True},
        )
        events = [
            json.loads(line)
            for line in (
                repo / ".forge/chains" / f"{chain_id}.events.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        carriers = [
            event["payload"]["details"]
            for event in events
            if isinstance(event.get("payload"), dict)
            and isinstance(event["payload"].get("details"), dict)
            and isinstance(
                event["payload"]["details"].get("journal_batch"), dict
            )
        ]
        self.assertEqual(len(carriers), 1)
        carrier = carriers[0]
        journal_batch = carrier["journal_batch"]
        assert isinstance(journal_batch, dict)
        raw_records = journal_batch["records"]
        assert isinstance(raw_records, list)
        records = tuple(copy.deepcopy(raw_records))
        source_event_digest = str(carrier["source_event_digest"])
        return repo, run_id, chain_id, source_event_digest, records

    def _chain_drain_authorizer(
        self,
        repo: Path,
        run_id: str,
        chain_id: str,
        source_event_digest: str,
        records: tuple[dict[str, object], ...],
        *,
        mismatch: str | None = None,
    ) -> tuple[object, object, list[dict[str, object]]]:
        capability = object()
        calls: list[dict[str, object]] = []
        task_id = str(records[0]["task"])
        batch_bytes = b"".join(
            journal._journal_line(record) for record in records
        )
        inputs = {
            "chain_id": chain_id,
            "source_event_digest": source_event_digest,
            "batch_digest": journal._sha256(batch_bytes),
            "record_count": len(records),
        }
        _, request_sha256 = batch.normalized_request(
            repo.resolve(), run_id, "chain outbox-drain", inputs
        )

        def exact(path: Path) -> journal.ExactFile:
            observed = os.lstat(path)
            return journal.ExactFile(
                path.read_bytes(), journal._file_observation(observed)
            )

        def authorize(**kwargs: object) -> object:
            calls.append(dict(kwargs))
            if kwargs.get("capability") is not capability:
                raise journal.CoordinationRefusal(
                    journal.INVALID_JOURNAL_RECORD
                )
            self.assertEqual(kwargs.get("repository"), repo.resolve())
            self.assertEqual(kwargs.get("run_id"), run_id)
            self.assertEqual(kwargs.get("task_id"), task_id)
            self.assertEqual(kwargs.get("chain_id"), chain_id)
            self.assertEqual(
                kwargs.get("source_event_digest"), source_event_digest
            )
            self.assertEqual(kwargs.get("supplied_records"), records)
            run_dir = self.run_dir(repo, run_id)
            values: dict[str, object] = {
                "repository": str(repo.resolve()),
                "run_id": run_id,
                "task_id": task_id,
                "chain_id": chain_id,
                "source_event_digest": source_event_digest,
                "request_sha256": request_sha256,
                "batch_bytes": batch_bytes,
                "record_count": len(records),
                "journal_exact": exact(run_dir / "journal.jsonl"),
                "receipts_exact": exact(
                    run_dir / journal.BATCH_RECEIPTS_NAME
                ),
            }
            if mismatch == "repository":
                values["repository"] = str(repo.resolve()) + "-foreign"
            elif mismatch in {
                "run_id",
                "task_id",
                "chain_id",
                "source_event_digest",
                "request_sha256",
            }:
                values[mismatch] = key(f"mismatch-{mismatch}")
            elif mismatch == "batch_bytes":
                changed = copy.deepcopy(records[0])
                changed["recorded_at"] = "2026-08-28T12:59:59Z"
                values["batch_bytes"] = journal._journal_line(changed)
            elif mismatch == "record_count":
                values["record_count"] = len(records) + 1
            elif mismatch == "journal_exact":
                current = values["journal_exact"]
                assert isinstance(current, journal.ExactFile)
                values["journal_exact"] = journal.ExactFile(
                    current.payload + b" ", current.observation
                )
            elif mismatch == "receipts_exact":
                current = values["receipts_exact"]
                assert isinstance(current, journal.ExactFile)
                values["receipts_exact"] = journal.ExactFile(
                    current.payload + b" ", current.observation
                )
            return batch._ChainBatchAuthorization(**values)

        return capability, authorize, calls

    def test_chain_drain_valid_authorizer_new_and_repeated_paths(self) -> None:
        with self.api_environment():
            case = self._chain_drain_case("chain-drain-authorized")
            repo, run_id, chain_id, source_digest, records = case
            capability, authorizer, calls = self._chain_drain_authorizer(
                *case
            )
            with mock.patch.object(batch, "_CHAIN_BATCH_AUTHORIZER", None):
                batch._register_chain_batch_authorizer(authorizer)
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal,
                    journal.INVALID_JOURNAL_RECORD,
                ):
                    batch._register_chain_batch_authorizer(authorizer)
                created = batch.drain_chain_batch(
                    repo,
                    run_id,
                    chain_id=chain_id,
                    source_event_digest=source_digest,
                    records=records,
                    capability=capability,
                )
                self.assertFalse(created.repeated)
                self.assertEqual(len(calls), 1)
                repeated = batch.drain_chain_batch(
                    repo,
                    run_id,
                    chain_id=chain_id,
                    source_event_digest=source_digest,
                    records=records,
                    capability=capability,
                )
            self.assertTrue(repeated.repeated)
            self.assertEqual(repeated.records, records)
            self.assertEqual(len(calls), 2)

    def test_chain_drain_authorized_pending_and_lost_response_retry(self) -> None:
        for crash_point in ("pending", "lost-response"):
            with self.subTest(crash_point=crash_point), self.api_environment():
                case = self._chain_drain_case(
                    f"chain-drain-{crash_point}"
                )
                repo, run_id, chain_id, source_digest, records = case
                capability, authorizer, calls = self._chain_drain_authorizer(
                    *case
                )
                original_recover = batch._recover_locked

                def crash_recovery(*args, **kwargs):
                    if crash_point == "pending":
                        raise RuntimeError("crash before recovery")
                    original_recover(*args, **kwargs)
                    raise RuntimeError("lost response")

                with mock.patch.object(
                    batch, "_CHAIN_BATCH_AUTHORIZER", authorizer
                ), mock.patch.object(
                    batch, "_recover_locked", side_effect=crash_recovery
                ), self.assertRaises(RuntimeError):
                    batch.drain_chain_batch(
                        repo,
                        run_id,
                        chain_id=chain_id,
                        source_event_digest=source_digest,
                        records=records,
                        capability=capability,
                    )
                intent_path = (
                    self.run_dir(repo, run_id) / journal.BATCH_INTENT_NAME
                )
                self.assertEqual(
                    intent_path.exists(), crash_point == "pending"
                )
                with mock.patch.object(
                    batch, "_CHAIN_BATCH_AUTHORIZER", authorizer
                ):
                    recovered = batch.drain_chain_batch(
                        repo,
                        run_id,
                        chain_id=chain_id,
                        source_event_digest=source_digest,
                        records=records,
                        capability=capability,
                    )
                self.assertTrue(recovered.repeated)
                self.assertEqual(recovered.records, records)
                self.assertEqual(len(calls), 2)
                self.assertFalse(intent_path.exists())
                recorded, issues = journal.read_journal(
                    self.run_dir(repo, run_id) / "journal.jsonl"
                )
                self.assertEqual(issues, [])
                self.assertEqual(
                    sum(
                        record.get("id") == records[0].get("id")
                        for record in recorded
                    ),
                    1,
                )

    def test_chain_drain_authorization_exact_field_bindings(self) -> None:
        with self.api_environment():
            case = self._chain_drain_case("chain-drain-bindings")
            repo, run_id, chain_id, source_digest, records = case
            run_dir = self.run_dir(repo, run_id)
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            receipts_before = (
                run_dir / journal.BATCH_RECEIPTS_NAME
            ).read_bytes()
            for mismatch in (
                "repository",
                "run_id",
                "task_id",
                "chain_id",
                "source_event_digest",
                "request_sha256",
                "batch_bytes",
                "record_count",
                "journal_exact",
                "receipts_exact",
            ):
                with self.subTest(mismatch=mismatch):
                    capability, authorizer, calls = (
                        self._chain_drain_authorizer(
                            *case, mismatch=mismatch
                        )
                    )
                    with mock.patch.object(
                        batch, "_CHAIN_BATCH_AUTHORIZER", authorizer
                    ), self.assertRaises(journal.CoordinationRefusal):
                        batch.drain_chain_batch(
                            repo,
                            run_id,
                            chain_id=chain_id,
                            source_event_digest=source_digest,
                            records=records,
                            capability=capability,
                        )
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(
                        (run_dir / "journal.jsonl").read_bytes(),
                        journal_before,
                    )
                    self.assertEqual(
                        (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(),
                        receipts_before,
                    )
                    self.assertFalse(
                        (run_dir / journal.BATCH_INTENT_NAME).exists()
                    )
            capability, authorizer, calls = self._chain_drain_authorizer(
                *case
            )
            with mock.patch.object(
                batch, "_CHAIN_BATCH_AUTHORIZER", authorizer
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.INVALID_JOURNAL_RECORD,
            ):
                batch.drain_chain_batch(
                    repo,
                    run_id,
                    chain_id=chain_id,
                    source_event_digest=source_digest,
                    records=records,
                    capability=object(),
                )
            self.assertEqual(len(calls), 1)
            with mock.patch.object(
                batch, "_CHAIN_BATCH_AUTHORIZER", authorizer
            ):
                accepted = batch.drain_chain_batch(
                    repo,
                    run_id,
                    chain_id=chain_id,
                    source_event_digest=source_digest,
                    records=records,
                    capability=capability,
                )
            self.assertFalse(accepted.repeated)

    def test_chain_drain_authorization_controls_are_load_bearing(self) -> None:
        with self.api_environment():
            case = self._chain_drain_case("chain-drain-controls")
            repo, run_id, chain_id, source_digest, records = case
            capability, authorizer, calls = self._chain_drain_authorizer(
                *case
            )
            run_dir = self.run_dir(repo, run_id)
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            receipts_before = (
                run_dir / journal.BATCH_RECEIPTS_NAME
            ).read_bytes()
            for control in batch._CHAIN_BATCH_AUTHORIZATION_REQUIRED:
                with self.subTest(control=control), mock.patch.object(
                    batch, "_CHAIN_BATCH_AUTHORIZER", authorizer
                ), mock.patch.object(
                    batch,
                    "CHAIN_BATCH_AUTHORIZATION_CONTROLS",
                    batch._CHAIN_BATCH_AUTHORIZATION_REQUIRED - {control},
                ), self.assertRaisesRegex(
                    journal.CoordinationRefusal,
                    journal.INVALID_JOURNAL_RECORD,
                ):
                    batch.drain_chain_batch(
                        repo,
                        run_id,
                        chain_id=chain_id,
                        source_event_digest=source_digest,
                        records=records,
                        capability=capability,
                    )
            self.assertEqual(calls, [])
            self.assertEqual(
                (run_dir / "journal.jsonl").read_bytes(), journal_before
            )
            self.assertEqual(
                (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(),
                receipts_before,
            )
            with mock.patch.object(
                batch, "_CHAIN_BATCH_AUTHORIZER", authorizer
            ):
                accepted = batch.drain_chain_batch(
                    repo,
                    run_id,
                    chain_id=chain_id,
                    source_event_digest=source_digest,
                    records=records,
                    capability=capability,
                )
            self.assertFalse(accepted.repeated)
            self.assertEqual(len(calls), 1)

    def test_ingest_requires_registered_proof_complete_authority(self) -> None:
        run_id = "run-20260828-ingest-authority"
        records = (
            {
                "type": "task",
                "recorded_at": "2026-08-28T12:00:00Z",
                "run_id": run_id,
                "id": "task-01",
                "status": "complete",
                "goal": "Implement the typed transaction",
                "acceptance": ["The focused behavior passes"],
                "files": ["src/example.py"],
            },
        )

        def ingest() -> batch.BatchOutcome:
            return builders.ingest_chain_records(
                self.repo,
                run_id,
                idempotency_key=key("ingest-authority"),
                task="task-01",
                state_file="external/state.json",
                events_file="external/events.jsonl",
                outcome_map="external/outcome-map.json",
                state_sha256=key("external-state"),
                events_sha256=key("external-events"),
                outcome_map_sha256=key("external-outcome-map"),
                closing_head=self.head,
                task_status="complete",
                records=records,
            )

        with self.api_environment():
            self.open_run(self.repo, run_id)
            self.start_task(self.repo, run_id)
            external = self.repo / "external"
            external.mkdir()
            for name in ("state.json", "events.jsonl", "outcome-map.json"):
                (external / name).write_text("fixture evidence\n", encoding="utf-8")
            run_dir = self.run_dir(self.repo, run_id)
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            receipts_before = (
                run_dir / journal.BATCH_RECEIPTS_NAME
            ).read_bytes()
            with mock.patch.object(
                builders, "_INGEST_PROOF_VERIFIER", None
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal,
                builders.INGEST_PROOF_INVALID,
            ):
                ingest()
            self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_before)
            self.assertEqual(
                (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(),
                receipts_before,
            )
            self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

            verifier = lambda _repo, _run, _request: (
                records,
                builders._INGEST_PROOF_ORDER,
            )
            different_records = (dict(records[0], status="failed"),)
            with mock.patch.object(
                builders,
                "_INGEST_PROOF_VERIFIER",
                lambda _repo, _run, _request: (
                    different_records,
                    builders._INGEST_PROOF_ORDER,
                ),
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal,
                builders.INGEST_PROOF_INVALID,
            ):
                ingest()
            for control in builders._INGEST_PROOF_ORDER:
                with self.subTest(control=control), mock.patch.object(
                    builders, "_INGEST_PROOF_VERIFIER", verifier
                ), mock.patch.object(
                    builders,
                    "INGEST_PROOF_CONTROLS",
                    builders.INGEST_PROOF_CONTROLS - {control},
                ), self.assertRaisesRegex(
                    journal.CoordinationRefusal, builders.INGEST_PROOF_INVALID
                ):
                    ingest()
            self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_before)
            self.assertEqual(
                (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(),
                receipts_before,
            )
            self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

    def _append_test_landing(
        self, repo: Path, run_id: str, chain_id: str
    ) -> dict[str, object]:
        preimage = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain_id,
                "event_digest": key("terminal-event"),
            },
            "candidate": {
                "kind": "staged-diff-sha256",
                "value": key("terminal-candidate"),
            },
            "review": None,
        }
        binding = {
            **preimage,
            "binding_id": journal._sha256(journal._canonical_json_bytes(preimage)),
        }
        with mock.patch.object(builders, "resolve_binding", return_value=binding):
            outcome = builders.decision_add(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-{chain_id}-terminal-landing"),
                task="task-01",
                resolution="The bound candidate landed",
                finding=None,
                outcome="chain-landing",
                risk=None,
                basis=[],
                binding_chain=chain_id,
                binding_id=str(binding["binding_id"]),
            )
        self.assertFalse(outcome.repeated)
        self.assertEqual(len(outcome.records), 1)
        recorded_binding = outcome.records[0].get("binding")
        self.assertEqual(recorded_binding, binding)
        assert isinstance(recorded_binding, dict)
        return recorded_binding

    def _terminal_control_repo(self, name: str) -> tuple[Path, str, dict[str, object]]:
        repo, _ = self._new_repo(name)
        run_id = f"run-20260828-{name}"
        self.open_run(repo, run_id)
        self.start_task(repo, run_id)
        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key("policy"),
        }
        return repo, run_id, run_binding

    def test_terminal_builder_guards_pending_outbox_and_missing_landing(self) -> None:
        with self.api_environment():
            repo, run_id, run_binding = self._terminal_control_repo("terminal-pending")
            self._write_bound_chain_state(
                repo,
                run_id,
                run_binding=run_binding,
                outbox={"pending": True},
            )
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.JOURNAL_OUTBOX_PENDING
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-pending"),
                    task="task-01",
                    status="complete",
                )
            self.assertFalse(
                (self.run_dir(repo, run_id) / journal.BATCH_INTENT_NAME).exists()
            )

            repo, run_id, run_binding = self._terminal_control_repo("terminal-landing")
            self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-landing"),
                    task="task-01",
                    status="complete",
                )

    def test_each_terminal_chain_control_is_load_bearing(self) -> None:
        with self.api_environment():
            repo, run_id, run_binding = self._terminal_control_repo("control-enumeration")
            self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox={"pending": True}
            )
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"enumeration"},
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("no-enumeration"),
                    task="task-01", status="complete",
                )
            self.assertEqual(outcome.records[0]["status"], "complete")

            repo, run_id, _run_binding = self._terminal_control_repo("control-lock")
            chain_id, _ = self._write_bound_chain_state(
                repo, run_id, run_binding=None, outbox=None
            )
            lock = repo / ".forge/chains" / f".{chain_id}.events.lock"
            target = Path(self.temporary.name) / "hostile-chain-lock"
            target.write_text("foreign\n", encoding="utf-8")
            os.symlink(target, lock)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("with-lock"),
                    task="task-01", status="complete",
                )
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"lock"},
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("without-lock"),
                    task="task-01", status="complete",
                )
            self.assertEqual(outcome.records[0]["status"], "complete")

            repo, run_id, _run_binding = self._terminal_control_repo("control-binding")
            self._write_bound_chain_state(
                repo, run_id, run_binding={"malformed": True}, outbox=None
            )
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"binding"},
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("without-binding"),
                    task="task-01", status="complete",
                )
            self.assertEqual(outcome.records[0]["status"], "complete")

            repo, run_id, run_binding = self._terminal_control_repo("control-landing")
            self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"landing"},
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("without-landing"),
                    task="task-01", status="complete",
                )
            self.assertEqual(outcome.records[0]["status"], "complete")

            repo, run_id, run_binding = self._terminal_control_repo("control-outbox")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox={"pending": True}
            )
            binding = self._append_test_landing(repo, run_id, chain_id)
            replayed_state = json.loads(state_path.read_text(encoding="utf-8"))

            def resolve_outbox_fixture(*_args, replay_only=False, **_kwargs):
                return replayed_state if replay_only else binding

            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"outbox"},
            ), mock.patch.object(
                builders,
                "_resolve_binding_from_descriptor",
                side_effect=resolve_outbox_fixture,
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("without-outbox"),
                    task="task-01", status="complete",
                )
            self.assertEqual(outcome.records[0]["status"], "complete")

            repo, run_id, run_binding = self._terminal_control_repo("control-replay")
            chain_id, _ = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._append_test_landing(repo, run_id, chain_id)
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"replay"},
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("without-replay"),
                    task="task-01", status="complete",
                )
            self.assertEqual(outcome.records[0]["status"], "complete")

    def test_terminal_guard_refuses_chain_root_swap_after_enumeration(self) -> None:
        with self.api_environment():
            repo, run_id, _run_binding = self._terminal_control_repo(
                "terminal-root-swap"
            )
            self._write_bound_chain_state(
                repo, run_id, run_binding=None, outbox=None
            )
            chains = repo / ".forge/chains"
            displaced = repo / ".forge/chains-displaced"
            swapped = False
            original_chain_lock = builders._optional_chain_lock

            @contextmanager
            def swap_before_chain_lock(
                _root: Path, _chain_id: str, **_descriptor_binding: object
            ):
                nonlocal swapped
                if not swapped:
                    chains.rename(displaced)
                    chains.mkdir()
                    for source in displaced.iterdir():
                        if source.name.endswith(".json"):
                            (chains / source.name).write_bytes(source.read_bytes())
                    swapped = True
                with original_chain_lock(
                    _root, _chain_id, **_descriptor_binding
                ):
                    yield

            journal_before = (
                self.run_dir(repo, run_id) / "journal.jsonl"
            ).read_bytes()
            with mock.patch.object(
                builders, "_optional_chain_lock", side_effect=swap_before_chain_lock
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-root-swap"),
                    task="task-01",
                    status="complete",
                )
            self.assertEqual(
                (self.run_dir(repo, run_id) / "journal.jsonl").read_bytes(),
                journal_before,
            )

    def _open_legacy_run(
        self,
        repo: Path,
        run_id: str,
        *,
        successor_of: str | None = None,
        scope: list[str] | None = None,
    ) -> None:
        record: dict[str, object] = {
            "type": "run_started",
            "recorded_at": "2026-08-28T12:00:00Z",
            "run_id": run_id,
            "goal": "Legacy successor recovery fixture",
            "repo": str(repo.resolve()),
            "repo_head": subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "repo_status": [],
            "plugin_ref": "forge-test-revision-9",
        }
        if successor_of is not None:
            record["successor_of"] = successor_of
        journal.open_run(
            repo,
            run_id,
            ["src/**"] if scope is None else scope,
            record,
            successor_of=successor_of,
        )

    def test_retired_successor_close_intent_recovers_and_releases_registry(self) -> None:
        repo, _ = self._new_repo("repo-retired-successor")
        predecessor = "run-20260828-retired-predecessor"
        successor = "run-20260828-retired-successor"
        with self.api_environment():
            self._open_legacy_run(repo, predecessor)
            journal.retire_run(repo, predecessor)
            self._open_legacy_run(
                repo, successor, successor_of=predecessor
            )
            journal.retire_run(repo, successor)
            with mock.patch.object(
                batch, "_recover_locked", side_effect=RuntimeError("close crash")
            ):
                with self.assertRaisesRegex(RuntimeError, "close crash"):
                    builders.run_close(
                        repo,
                        successor,
                        idempotency_key=key("retired-successor-close"),
                        judgment="blocked",
                        summary="Recover the retired successor close",
                        risks=[],
                        follow_ups=[],
                    )
            run_dir = self.run_dir(repo, successor)
            self.assertTrue((run_dir / journal.BATCH_INTENT_NAME).exists())
            recovered = batch.recover_batch(repo, successor)
        self.assertTrue(recovered.repeated)
        self.assertEqual(recovered.records[0]["type"], "run_closed")
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())
        records, issues = journal.read_journal(run_dir / "journal.jsonl")
        self.assertEqual(issues, [])
        self.assertEqual(records[-1]["type"], "run_closed")
        registry = json.loads(
            (repo / ".forge/tmp/run-registry.json").read_text(encoding="utf-8")
        )
        active_ids = {entry["run_id"] for entry in registry["open_runs"]}
        self.assertNotIn(predecessor, active_ids)
        self.assertNotIn(successor, active_ids)

    def test_retired_successor_close_recovers_every_stored_suffix_prefix(self) -> None:
        for suffix_state in ("partial", "complete"):
            with self.subTest(suffix_state=suffix_state):
                repo, _ = self._new_repo(
                    f"repo-retired-successor-{suffix_state}"
                )
                predecessor = (
                    f"run-20260828-retired-predecessor-{suffix_state}"
                )
                successor = (
                    f"run-20260828-retired-successor-{suffix_state}"
                )
                with self.api_environment():
                    self._open_legacy_run(repo, predecessor)
                    journal.retire_run(repo, predecessor)
                    self._open_legacy_run(
                        repo, successor, successor_of=predecessor
                    )
                    journal.retire_run(repo, successor)
                    with mock.patch.object(
                        batch,
                        "_recover_locked",
                        side_effect=RuntimeError("close crash"),
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError, "close crash"
                        ):
                            builders.run_close(
                                repo,
                                successor,
                                idempotency_key=key(
                                    f"retired-successor-{suffix_state}"
                                ),
                                judgment="blocked",
                                summary=(
                                    "Recover the stored retired close suffix"
                                ),
                                risks=[],
                                follow_ups=[],
                            )
                    run_dir = self.run_dir(repo, successor)
                    intent = json.loads(
                        (run_dir / journal.BATCH_INTENT_NAME).read_text(
                            encoding="utf-8"
                        )
                    )
                    suffix = base64.urlsafe_b64decode(
                        str(intent["batch_bytes"])
                        + "="
                        * (-len(str(intent["batch_bytes"])) % 4)
                    )
                    stored_size = (
                        len(suffix)
                        if suffix_state == "complete"
                        else max(1, len(suffix) // 2)
                    )
                    with (run_dir / "journal.jsonl").open("ab") as stream:
                        stream.write(suffix[:stored_size])
                        stream.flush()
                        os.fsync(stream.fileno())
                    recovered = batch.recover_batch(repo, successor)
                self.assertTrue(recovered.repeated)
                self.assertEqual(recovered.records[0]["type"], "run_closed")
                self.assertFalse(
                    (run_dir / journal.BATCH_INTENT_NAME).exists()
                )
                records, issues = journal.read_journal(
                    run_dir / "journal.jsonl"
                )
                self.assertEqual(issues, [])
                self.assertEqual(records[-1]["type"], "run_closed")
                registry = json.loads(
                    (repo / ".forge/tmp/run-registry.json").read_text(
                        encoding="utf-8"
                    )
                )
                active_ids = {
                    entry["run_id"] for entry in registry["open_runs"]
                }
                self.assertNotIn(predecessor, active_ids)
                self.assertNotIn(successor, active_ids)

    def test_retired_successor_recovery_rejects_other_run_mutation(self) -> None:
        repo, _ = self._new_repo("repo-retired-successor-other-run-race")
        other = "run-20260828-retired-other-race"
        predecessor = "run-20260828-retired-predecessor-race"
        successor = "run-20260828-retired-successor-race"
        with self.api_environment():
            self._open_legacy_run(repo, other, scope=["other/**"])
            journal.retire_run(repo, other)
            self._open_legacy_run(repo, predecessor)
            journal.retire_run(repo, predecessor)
            self._open_legacy_run(
                repo, successor, successor_of=predecessor
            )
            journal.retire_run(repo, successor)
            with mock.patch.object(
                batch,
                "_recover_locked",
                side_effect=RuntimeError("close crash"),
            ):
                with self.assertRaisesRegex(RuntimeError, "close crash"):
                    builders.run_close(
                        repo,
                        successor,
                        idempotency_key=key(
                            "retired-successor-other-run-race"
                        ),
                        judgment="blocked",
                        summary="Reject a concurrent other-run mutation",
                        risks=[],
                        follow_ups=[],
                    )
            run_dir = self.run_dir(repo, successor)
            intent_path = run_dir / journal.BATCH_INTENT_NAME
            intent = json.loads(intent_path.read_text(encoding="utf-8"))
            suffix = base64.urlsafe_b64decode(
                str(intent["batch_bytes"])
                + "=" * (-len(str(intent["batch_bytes"])) % 4)
            )
            with (run_dir / "journal.jsonl").open("ab") as stream:
                stream.write(suffix[: max(1, len(suffix) // 2)])
                stream.flush()
                os.fsync(stream.fileno())
            target_before = (run_dir / "journal.jsonl").read_bytes()
            owner_path = self.run_dir(repo, other) / "owner"
            owner_lines = owner_path.read_bytes().splitlines()
            mutated_owner = b"\n".join(
                owner_lines[:2]
                + [b"started_at: 2000-01-01T00:00:00Z"]
            ) + b"\n"
            self.assertNotEqual(owner_path.read_bytes(), mutated_owner)
            original_fence = batch._validate_recovery_view_fences
            fence_calls = 0

            def mutate_after_first_fence(*args, **kwargs) -> None:
                nonlocal fence_calls
                fence_calls += 1
                original_fence(*args, **kwargs)
                if fence_calls == 1:
                    with owner_path.open("r+b") as stream:
                        stream.write(mutated_owner)
                        stream.truncate()
                        stream.flush()
                        os.fsync(stream.fileno())

            with mock.patch.object(
                batch,
                "_validate_recovery_view_fences",
                side_effect=mutate_after_first_fence,
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.BATCH_DIVERGED,
            ):
                batch.recover_batch(repo, successor)
        self.assertEqual(fence_calls, 2)
        self.assertTrue(intent_path.exists())
        self.assertEqual(
            (run_dir / "journal.jsonl").read_bytes(), target_before
        )
        self.assertEqual(owner_path.read_bytes(), mutated_owner)

    def test_internal_typed_flag_cannot_bypass_activated_batch_builders(self) -> None:
        with self.api_environment():
            repo, _ = self._new_repo("repo-typed-append-bypass")
            run_id = "run-20260828-typed-append-bypass"
            self.open_run(repo, run_id)
            run_dir = self.run_dir(repo, run_id)
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                "activated writer requires typed builder",
            ):
                journal.append_run_record(
                    repo,
                    run_id,
                    {
                        "type": "decision",
                        "recorded_at": "2026-08-28T12:00:00Z",
                        "run_id": run_id,
                        "id": "decision-01",
                        "resolution": "Raw append must remain forbidden",
                        "basis": [],
                    },
                    _typed=True,
                )
            self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_before)

            repo, _ = self._new_repo("repo-typed-close-bypass")
            run_id = "run-20260828-typed-close-bypass"
            self.open_run(repo, run_id)
            run_dir = self.run_dir(repo, run_id)
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            validation = journal.validate_run(run_dir, gates=True)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                "activated writer requires typed builder",
            ):
                journal.close_run(
                    repo,
                    run_id,
                    {
                        "type": "run_closed",
                        "recorded_at": "2026-08-28T12:00:00Z",
                        "run_id": run_id,
                        "judgment": "blocked",
                        "summary": "Raw close must remain forbidden",
                        "validation": validation,
                        "risks": [],
                        "follow_ups": [],
                    },
                    _typed=True,
                )
            self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_before)

    def command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOLS), *arguments],
            cwd=self.repo,
            env=self.env,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )

    def test_cli_singleton_and_idempotency_key_diagnostics(self) -> None:
        base = [
            "run-open", "--repo", str(self.repo), "--run-id", "run-20260828-cli",
            "--idempotency-key", key("cli"), "--goal", "goal", "--scope", "src/**",
            "--plugin-ref", "forge-test",
        ]
        duplicate = self.command(*(base + ["--goal", "other"]))
        self.assertEqual(duplicate.returncode, 1)
        self.assertEqual(duplicate.stderr.strip(), "forge: CLI option refused — duplicate --goal")

        empty = list(base)
        empty[empty.index("goal")] = ""
        refused_empty = self.command(*empty)
        self.assertEqual(refused_empty.returncode, 1)
        self.assertEqual(refused_empty.stderr.strip(), "forge: CLI option refused — empty --goal")

        invalid = list(base)
        invalid[invalid.index(key("cli"))] = "BAD"
        refused_key = self.command(*invalid)
        self.assertEqual(refused_key.returncode, 1)
        self.assertEqual(refused_key.stderr.strip(), journal.BATCH_KEY_REFUSAL)

        recovery_key = self.command(
            "journal", "batch-recover", "--repo", str(self.repo),
            "--run-id", "run-20260828-cli", "--idempotency-key", key("cli"),
        )
        self.assertEqual(recovery_key.returncode, 1)
        self.assertEqual(recovery_key.stderr.strip(), journal.BATCH_KEY_REFUSAL)


class Revision9BindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-revision9-binding-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        subprocess.run(["git", "init", "--quiet", str(self.repo)], check=True)

    def binding(
        self,
        seed: str,
        *,
        candidate: dict[str, object] | None = None,
        review: dict[str, object] | None = None,
    ) -> dict[str, object]:
        preimage: dict[str, object] = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": "c-2026-08-28T120000Z-abcd",
                "event_digest": key(f"event-{seed}"),
            },
            "candidate": candidate
            or {"kind": "staged-diff-sha256", "value": key("candidate")},
            "review": review,
        }
        return {**preimage, "binding_id": journal._sha256(journal._canonical_json_bytes(preimage))}

    def _write_commit_gate_binding_chain(
        self,
        chain_id: str,
        *,
        evidence_result: str,
        record_result: str,
        later_result: str | None = None,
    ) -> tuple[str, str]:
        """Write a replay-valid, receipted Gate-2 binding history."""

        chains = self.repo / ".forge/chains"
        chains.mkdir(parents=True, exist_ok=True)
        run_id = "run-20260828-resolver-binding"
        task_id = "task-01"
        candidate = key(f"{chain_id}-candidate")
        policy_digest = key(f"{chain_id}-policy")
        paths = ["src/example.py"]
        state: dict[str, object] = {
            "schema": "forge-chain/1",
            "chain_id": chain_id,
            "kind": "commit",
            "state": "classifying",
            "created_at": "2026-08-28T12:00:00Z",
            "last_event_at": "2026-08-28T12:00:00Z",
            "inactive_after": "2026-08-29T12:00:00Z",
            "repo_head": "1" * 40,
            "policy_source": {
                "path": "forge-project.md",
                "sha": "1" * 40,
                "digest": policy_digest,
            },
            "paths": paths,
            "staging": {
                "worktree_root": str(self.repo.resolve()),
                "session_identity": "fixture",
                "staged_paths": [],
                "staged_at": None,
                "classification_runs": 0,
                "anomalies": [],
            },
            "candidate": {"sha256": None, "computed_at": None},
            "tier": {
                "declared": None,
                "derived": None,
                "effective": None,
                "control": False,
                "categories": [],
                "classification": None,
            },
            "steps": {},
            "review": {
                "iteration": 0,
                "request": None,
                "verdict": None,
                "dispositions": [],
                "operator_cosign_required": False,
                "residual_risk": None,
            },
            "approval": {},
            "authorization": {},
            "commit_result": {},
            "run_binding": {
                "run_id": run_id,
                "task_id": task_id,
                "repository": str(self.repo.resolve()),
                "policy_digest": policy_digest,
            },
            "journal_outbox": None,
        }
        events: list[dict[str, object]] = []
        previous = "0" * 64

        def append_event(
            event_name: str,
            details: dict[str, object],
            snapshot: dict[str, object],
        ) -> dict[str, object]:
            nonlocal previous
            unsigned = {
                "sequence": len(events) + 1,
                "prev_digest": previous,
                "payload": {
                    "at": snapshot["last_event_at"],
                    "details": copy.deepcopy(details),
                    "event": event_name,
                    "state": copy.deepcopy(snapshot),
                },
            }
            event = {
                **unsigned,
                "digest": journal._sha256(journal._canonical_json_bytes(unsigned)),
            }
            events.append(event)
            previous = str(event["digest"])
            return event

        append_event("chain_started", {"paths": paths}, state)

        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-08-28T12:01:00Z"
        assert isinstance(state["staging"], dict)
        state["staging"]["staged_paths"] = paths
        state["staging"]["staged_at"] = state["last_event_at"]
        state["candidate"] = {
            "sha256": candidate,
            "computed_at": state["last_event_at"],
        }
        append_event(
            "candidate_staged",
            {"candidate": candidate, "paths": paths},
            state,
        )

        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-08-28T12:02:00Z"
        state["state"] = "verifying"
        assert isinstance(state["staging"], dict)
        state["staging"]["classification_runs"] = 1
        state["tier"] = {
            "declared": None,
            "derived": "fast",
            "effective": "fast",
            "control": False,
            "categories": [],
            "classification": {"fixture": True},
        }
        state["steps"] = {
            "classification": [{"candidate": candidate, "result": "passed"}]
        }
        append_event(
            "classified",
            {"effective_tier": "fast", "control": False},
            state,
        )

        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-08-28T12:03:00Z"
        assert isinstance(state["steps"], dict)
        state["steps"]["assertion-sensor"] = [
            {"candidate": candidate, "result": evidence_result}
        ]
        ordinary_details = {
            "step_id": "assertion-sensor",
            "result": evidence_result,
            "run": 1,
        }
        source_projection = {
            "sequence": len(events) + 1,
            "prev_digest": previous,
            "payload": {
                "at": state["last_event_at"],
                "details": copy.deepcopy(ordinary_details),
                "event": "step_recorded",
                "state": copy.deepcopy(state),
            },
        }
        source_digest = journal._sha256(
            journal._canonical_json_bytes(source_projection)
        )
        binding_preimage = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain_id,
                "event_digest": source_digest,
            },
            "candidate": {
                "kind": "staged-diff-sha256",
                "value": candidate,
            },
            "review": None,
        }
        binding = {
            **binding_preimage,
            "binding_id": journal._sha256(
                journal._canonical_json_bytes(binding_preimage)
            ),
        }
        record = {
            "type": "verification",
            "recorded_at": state["last_event_at"],
            "run_id": run_id,
            "id": "check-01",
            "task": task_id,
            "criterion": "gate-2: assertion sensor",
            "method": "fixture",
            "check": "fixture",
            "result": record_result,
            "observation": "fixture",
            "evidence": [],
            "binding": binding,
        }
        batch_bytes = journal._journal_line(record)
        carried = {
            "idempotency_key": source_digest,
            "batch_digest": journal._sha256(batch_bytes),
            "record_count": 1,
            "records": [record],
        }
        outbox = {
            "idempotency_key": source_digest,
            "batch_digest": carried["batch_digest"],
            "record_count": 1,
            "source_event_digest": source_digest,
        }
        state["journal_outbox"] = outbox
        source_details = {
            **ordinary_details,
            "source_event_digest": source_digest,
            "journal_batch": carried,
        }
        append_event("step_recorded", source_details, state)

        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-08-28T12:04:00Z"
        state["journal_outbox"] = None
        append_event(
            "journal_receipted",
            {
                "idempotency_key": source_digest,
                "batch_digest": carried["batch_digest"],
                "receipt_digest": key(f"{chain_id}-receipt"),
            },
            state,
        )

        if later_result is not None:
            state = copy.deepcopy(state)
            state["last_event_at"] = "2026-08-28T12:05:00Z"
            assert isinstance(state["steps"], dict)
            runs = state["steps"]["assertion-sensor"]
            assert isinstance(runs, list)
            runs.append({"candidate": candidate, "result": later_result})
            append_event(
                "step_recorded",
                {
                    "step_id": "assertion-sensor",
                    "result": later_result,
                    "run": 2,
                },
                state,
            )

        (chains / f"{chain_id}.events.jsonl").write_bytes(
            b"".join(
                journal._canonical_json_bytes(event) + b"\n" for event in events
            )
        )
        (chains / f"{chain_id}.json").write_bytes(
            journal._canonical_json_bytes(state) + b"\n"
        )
        return run_id, str(binding["binding_id"])

    def _write_commit_decision_cycle_chain(
        self,
        chain_id: str,
        *,
        outcome: str,
        cycle: bool = True,
        retain_fact: bool = False,
    ) -> tuple[str, str]:
        """Extend a valid commit history with an A-to-B-to-A decision cycle."""

        if outcome not in {"chain-approval", "chain-skip"}:
            raise AssertionError(outcome)
        run_id, _gate_binding = self._write_commit_gate_binding_chain(
            chain_id,
            evidence_result="passed",
            record_result="passed",
        )
        chains = self.repo / ".forge/chains"
        events = [
            json.loads(line)
            for line in (chains / f"{chain_id}.events.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        state = json.loads(
            (chains / f"{chain_id}.json").read_text(encoding="utf-8")
        )
        previous = str(events[-1]["digest"])
        minute = 4

        def next_at() -> str:
            nonlocal minute
            minute += 1
            return f"2026-08-28T12:{minute:02d}:00Z"

        def append_event(
            event_name: str,
            details: dict[str, object],
            snapshot: dict[str, object],
        ) -> dict[str, object]:
            nonlocal previous
            unsigned = {
                "sequence": len(events) + 1,
                "prev_digest": previous,
                "payload": {
                    "at": snapshot["last_event_at"],
                    "details": copy.deepcopy(details),
                    "event": event_name,
                    "state": copy.deepcopy(snapshot),
                },
            }
            event = {
                **unsigned,
                "digest": journal._sha256(journal._canonical_json_bytes(unsigned)),
            }
            events.append(event)
            previous = str(event["digest"])
            return event

        candidate_state = state["candidate"]
        assert isinstance(candidate_state, dict)
        candidate_a = candidate_state["sha256"]
        assert isinstance(candidate_a, str)
        candidate_b = key(f"{chain_id}-candidate-b")

        def prepare_approval(review_seed: str) -> None:
            nonlocal state
            state = copy.deepcopy(state)
            state["last_event_at"] = next_at()
            state["state"] = "reviewing"
            append_event(
                "mechanical_verification_complete",
                {"candidate": candidate_a, "retained_review": False},
                state,
            )

            state = copy.deepcopy(state)
            state["last_event_at"] = next_at()
            state["state"] = "awaiting_approval"
            review = state["review"]
            assert isinstance(review, dict)
            review["iteration"] = int(review.get("iteration", 0)) + 1
            review["verdict"] = {
                "verdict": "PASS",
                "candidate": candidate_a,
                "reviewer_role": "review-final",
                "package_digest": key(review_seed),
            }
            state["approval"] = {
                "required_for": "control",
                "candidate": candidate_a,
            }
            append_event(
                "review_passed",
                {"candidate": candidate_a, "awaiting_approval": True},
                state,
            )

        if outcome == "chain-approval":
            prepare_approval(f"{chain_id}-source-review")

        source_fact: dict[str, object]
        authorization_fact: dict[str, object] | None = None
        state = copy.deepcopy(state)
        state["last_event_at"] = next_at()
        if outcome == "chain-approval":
            event_name = "operator_approved"
            ordinary_details = {
                "candidate": candidate_a,
                "directed_by": "operator",
            }
            source_fact = {
                "candidate": candidate_a,
                "approved_at": state["last_event_at"],
                "directed_by": "operator",
                "qualification": {
                    "command_digest": key(f"{chain_id}-approval-command"),
                    "env_fingerprint": key(f"{chain_id}-approval-environment"),
                    "recorded_at": state["last_event_at"],
                    "transcript": f".forge/chains/{chain_id}/approval.log",
                },
            }
            authorization_fact = {
                "token": key(f"{chain_id}-authorization")[:32],
                "candidate": candidate_a,
                "issued_at": state["last_event_at"],
                "expires_at": "2026-08-28T12:30:00Z",
                "consumed": False,
                "consumed_at": None,
            }
            state["state"] = "authorized"
            state["approval"] = copy.deepcopy(source_fact)
            state["authorization"] = copy.deepcopy(authorization_fact)
        else:
            event_name = "operator_skip"
            ordinary_details = {
                "gate_id": "assertion-sensor",
                "directed_by": "operator",
                "reason": "fixture skip",
            }
            source_fact = {
                "directed_by": "operator",
                "reason": "fixture skip",
                "argv_digest": key(f"{chain_id}-skip-command"),
                "journaled_at": state["last_event_at"],
            }
            steps = state["steps"]
            assert isinstance(steps, dict)
            steps["user_skips"] = {
                "assertion-sensor": copy.deepcopy(source_fact)
            }

        source_projection = {
            "sequence": len(events) + 1,
            "prev_digest": previous,
            "payload": {
                "at": state["last_event_at"],
                "details": copy.deepcopy(ordinary_details),
                "event": event_name,
                "state": copy.deepcopy(state),
            },
        }
        source_digest = journal._sha256(
            journal._canonical_json_bytes(source_projection)
        )
        binding_preimage = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain_id,
                "event_digest": source_digest,
            },
            "candidate": {
                "kind": "staged-diff-sha256",
                "value": candidate_a,
            },
            "review": None,
        }
        binding = {
            **binding_preimage,
            "binding_id": journal._sha256(
                journal._canonical_json_bytes(binding_preimage)
            ),
        }
        record = {
            "type": "decision",
            "recorded_at": state["last_event_at"],
            "run_id": run_id,
            "id": "decision-01",
            "task": "task-01",
            "resolution": "Fixture chain decision",
            "outcome": outcome,
            "basis": [],
            "binding": binding,
        }
        batch_bytes = journal._journal_line(record)
        carried = {
            "idempotency_key": source_digest,
            "batch_digest": journal._sha256(batch_bytes),
            "record_count": 1,
            "records": [record],
        }
        state["journal_outbox"] = {
            "idempotency_key": source_digest,
            "batch_digest": carried["batch_digest"],
            "record_count": 1,
            "source_event_digest": source_digest,
        }
        append_event(
            event_name,
            {
                **ordinary_details,
                "source_event_digest": source_digest,
                "journal_batch": carried,
            },
            state,
        )

        state = copy.deepcopy(state)
        state["last_event_at"] = next_at()
        state["journal_outbox"] = None
        append_event(
            "journal_receipted",
            {
                "idempotency_key": source_digest,
                "batch_digest": carried["batch_digest"],
                "receipt_digest": key(f"{chain_id}-decision-receipt"),
            },
            state,
        )

        if not cycle:
            (chains / f"{chain_id}.events.jsonl").write_bytes(
                b"".join(
                    journal._canonical_json_bytes(event) + b"\n"
                    for event in events
                )
            )
            (chains / f"{chain_id}.json").write_bytes(
                journal._canonical_json_bytes(state) + b"\n"
            )
            return run_id, str(binding["binding_id"])

        def restage(new_candidate: str) -> None:
            nonlocal state
            old_candidate_state = state["candidate"]
            assert isinstance(old_candidate_state, dict)
            old_candidate = old_candidate_state["sha256"]
            assert isinstance(old_candidate, str)
            state = copy.deepcopy(state)
            state["last_event_at"] = next_at()
            state["state"] = "classifying"
            state["candidate"] = {
                "sha256": new_candidate,
                "computed_at": state["last_event_at"],
            }
            old_steps = state["steps"]
            assert isinstance(old_steps, dict)
            retained_skips = old_steps.get("user_skips")
            state["steps"] = (
                {"user_skips": copy.deepcopy(retained_skips)}
                if retain_fact
                and outcome == "chain-skip"
                and isinstance(retained_skips, dict)
                else {}
            )
            review = state["review"]
            assert isinstance(review, dict)
            review["request"] = None
            review["verdict"] = None
            review["dispositions"] = []
            review["operator_cosign_required"] = False
            if not (retain_fact and outcome == "chain-approval"):
                state["approval"] = {}
                state["authorization"] = {}
            state["commit_result"] = {}
            append_event(
                "candidate_restaged",
                {
                    "old_candidate": old_candidate,
                    "new_candidate": new_candidate,
                    "paths": state["paths"],
                },
                state,
            )

        restage(candidate_b)
        restage(candidate_a)

        state = copy.deepcopy(state)
        state["last_event_at"] = next_at()
        state["state"] = "verifying"
        staging = state["staging"]
        assert isinstance(staging, dict)
        staging["classification_runs"] = int(staging["classification_runs"]) + 1
        state["steps"] = {
            "classification": [{"candidate": candidate_a, "result": "passed"}]
        }
        if retain_fact and outcome == "chain-skip":
            state["steps"]["user_skips"] = {
                "assertion-sensor": copy.deepcopy(source_fact)
            }
        append_event(
            "classified",
            {"effective_tier": "fast", "control": False},
            state,
        )

        if retain_fact:
            (chains / f"{chain_id}.events.jsonl").write_bytes(
                b"".join(
                    journal._canonical_json_bytes(event) + b"\n"
                    for event in events
                )
            )
            (chains / f"{chain_id}.json").write_bytes(
                journal._canonical_json_bytes(state) + b"\n"
            )
            return run_id, str(binding["binding_id"])

        if outcome == "chain-approval":
            prepare_approval(f"{chain_id}-current-review")
            state = copy.deepcopy(state)
            state["last_event_at"] = next_at()
            state["state"] = "authorized"
            state["approval"] = copy.deepcopy(source_fact)
            assert authorization_fact is not None
            state["authorization"] = copy.deepcopy(authorization_fact)
            append_event(
                "operator_approved",
                {"candidate": candidate_a, "directed_by": "operator"},
                state,
            )
        else:
            state = copy.deepcopy(state)
            state["last_event_at"] = next_at()
            steps = state["steps"]
            assert isinstance(steps, dict)
            steps["user_skips"] = {
                "assertion-sensor": copy.deepcopy(source_fact)
            }
            append_event(
                "operator_skip",
                {
                    "gate_id": "assertion-sensor",
                    "directed_by": "operator",
                    "reason": "fixture skip",
                },
                state,
            )

        (chains / f"{chain_id}.events.jsonl").write_bytes(
            b"".join(
                journal._canonical_json_bytes(event) + b"\n" for event in events
            )
        )
        (chains / f"{chain_id}.json").write_bytes(
            journal._canonical_json_bytes(state) + b"\n"
        )
        return run_id, str(binding["binding_id"])

    def test_resolver_rejects_stale_and_result_mismatched_gate_bindings(self) -> None:
        valid_chain = "c-2026-08-28T120000Z-a101"
        run_id, valid_binding = self._write_commit_gate_binding_chain(
            valid_chain,
            evidence_result="passed",
            record_result="passed",
        )
        stale_chain = "c-2026-08-28T120000Z-a102"
        _run_id, stale_binding = self._write_commit_gate_binding_chain(
            stale_chain,
            evidence_result="passed",
            record_result="passed",
            later_result="failed",
        )
        mismatch_chain = "c-2026-08-28T120000Z-a103"
        _run_id, mismatch_binding = self._write_commit_gate_binding_chain(
            mismatch_chain,
            evidence_result="failed",
            record_result="passed",
        )
        expected_fields = {
            "task": "task-01",
            "criterion": "gate-2: assertion sensor",
            "result": "passed",
        }

        with mock.patch.object(builders, "_verify_receipted_batch"):
            resolved = builders.resolve_binding(
                self.repo,
                valid_chain,
                valid_binding,
                expected_type="verification",
                expected_fields=expected_fields,
                expected_run_id=run_id,
                expected_task_id="task-01",
            )
            self.assertEqual(resolved["binding_id"], valid_binding)

            for chain_id, binding_id in (
                (stale_chain, stale_binding),
                (mismatch_chain, mismatch_binding),
            ):
                with self.subTest(chain_id=chain_id), self.assertRaisesRegex(
                    journal.CoordinationRefusal,
                    "binding chain replay failed",
                ):
                    builders.resolve_binding(
                        self.repo,
                        chain_id,
                        binding_id,
                        expected_type="verification",
                        expected_fields=expected_fields,
                        expected_run_id=run_id,
                        expected_task_id="task-01",
                    )

    def test_resolver_rejects_recreated_approval_and_skip_facts(self) -> None:
        cases = (
            (
                "chain-approval",
                "c-2026-08-28T120000Z-a104",
                "c-2026-08-28T120000Z-a106",
            ),
            (
                "chain-skip",
                "c-2026-08-28T120000Z-a105",
                "c-2026-08-28T120000Z-a107",
            ),
        )
        with mock.patch.object(builders, "_verify_receipted_batch"):
            for outcome, current_chain, cycled_chain in cases:
                with self.subTest(outcome=outcome):
                    run_id, current_binding = self._write_commit_decision_cycle_chain(
                        current_chain,
                        outcome=outcome,
                        cycle=False,
                    )
                    resolved = builders.resolve_binding(
                        self.repo,
                        current_chain,
                        current_binding,
                        expected_type="decision",
                        expected_fields={
                            "task": "task-01",
                            "outcome": outcome,
                        },
                        expected_run_id=run_id,
                        expected_task_id="task-01",
                    )
                    self.assertEqual(resolved["binding_id"], current_binding)

                    run_id, binding_id = self._write_commit_decision_cycle_chain(
                        cycled_chain,
                        outcome=outcome,
                    )
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal,
                        "binding chain replay failed",
                    ):
                        builders.resolve_binding(
                            self.repo,
                            cycled_chain,
                            binding_id,
                            expected_type="decision",
                            expected_fields={
                                "task": "task-01",
                                "outcome": outcome,
                            },
                            expected_run_id=run_id,
                            expected_task_id="task-01",
                        )

    def test_resolver_rejects_candidate_cycles_retaining_decision_facts(self) -> None:
        cases = (
            ("chain-approval", "c-2026-08-28T120000Z-a108"),
            ("chain-skip", "c-2026-08-28T120000Z-a109"),
        )
        with mock.patch.object(builders, "_verify_receipted_batch"):
            for outcome, chain_id in cases:
                with self.subTest(outcome=outcome):
                    run_id, binding_id = self._write_commit_decision_cycle_chain(
                        chain_id,
                        outcome=outcome,
                        retain_fact=True,
                    )
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal,
                        "binding chain replay failed",
                    ):
                        builders.resolve_binding(
                            self.repo,
                            chain_id,
                            binding_id,
                            expected_type="decision",
                            expected_fields={
                                "task": "task-01",
                                "outcome": outcome,
                            },
                            expected_run_id=run_id,
                            expected_task_id="task-01",
                        )

    def test_dm001_exact_shape_candidate_and_review_vectors(self) -> None:
        vectors = (
            self.binding("staged"),
            self.binding("commit", candidate={"kind": "git-commit", "value": "a" * 40}),
            self.binding(
                "range",
                candidate={"kind": "git-range", "value": {"base": "a" * 40, "head": "b" * 40}},
            ),
            self.binding(
                "review",
                review={
                    "verdict": "PASS", "iteration": 1,
                    "reviewer_role": "review-final", "package_digest": key("package"),
                },
            ),
        )
        self.assertTrue(all(journal._binding_shape_valid(value) for value in vectors))
        for mutation in ("extra", "digest", "candidate", "review"):
            value = copy.deepcopy(vectors[0])
            if mutation == "extra":
                value["generation_id"] = "deferred"
            elif mutation == "digest":
                value["binding_id"] = "0" * 64
            elif mutation == "candidate":
                value["candidate"]["kind"] = "unknown"
            else:
                value["review"] = {"verdict": "PASS"}
            self.assertFalse(journal._binding_shape_valid(value), mutation)

    def test_binding_currentness_rejects_superseded_gate_facts(self) -> None:
        candidate = key("candidate")
        binding = self.binding("gate-current")
        first_pass = {
            "candidate": candidate,
            "result": "passed",
            "env_fingerprint": key("environment"),
        }
        second_pass = copy.deepcopy(first_pass)
        source_state = {
            "candidate": {"sha256": candidate},
            "steps": {"gate-1": [first_pass]},
        }
        source_event = {
            "digest": key("gate-one-source-event"),
            "payload": {
                "event": "step_recorded",
                "details": {"step_id": "gate-1", "result": "passed", "run": 1},
            }
        }
        record = {
            "type": "verification",
            "criterion": "gate-1: project tests",
            "result": "passed",
        }
        valid_pair = copy.deepcopy(source_state)
        valid_pair["steps"]["gate-1"].append(second_pass)
        second_event = {
            "digest": key("gate-one-second-event"),
            "payload": {
                "event": "step_recorded",
                "details": {"step_id": "gate-1", "result": "passed", "run": 2},
            },
        }
        valid_pair_replay = (
            (source_event, None, source_state, (), None),
            (second_event, source_state, valid_pair, (), None),
        )
        self.assertTrue(
            builders._binding_is_current(
                valid_pair,
                binding,
                record,
                source_event,
                None,
                source_state,
                valid_pair_replay,
                chain_family="commit",
            )
        )

        later_block = copy.deepcopy(valid_pair)
        later_block["steps"]["gate-1"].append(
            {
                "candidate": candidate,
                "result": "failed",
                "env_fingerprint": key("environment"),
            }
        )
        blocked_event = {
            "digest": key("gate-one-block-event"),
            "payload": {
                "event": "step_recorded",
                "details": {"step_id": "gate-1", "result": "failed", "run": 3},
            },
        }
        self.assertFalse(
            builders._binding_is_current(
                later_block,
                binding,
                record,
                source_event,
                None,
                source_state,
                valid_pair_replay
                + ((blocked_event, valid_pair, later_block, (), None),),
                chain_family="commit",
            )
        )

        different_candidate = {
            "candidate": {"sha256": key("different-candidate")},
            "steps": {},
        }
        returned_candidate = {
            "candidate": {"sha256": candidate},
            "steps": {},
        }
        recreated_fact = copy.deepcopy(source_state)
        away_event = {
            "digest": key("candidate-away-event"),
            "payload": {"event": "candidate_restaged", "details": {}},
        }
        return_event = {
            "digest": key("candidate-return-event"),
            "payload": {"event": "candidate_restaged", "details": {}},
        }
        recreated_event = {
            "digest": key("gate-one-recreated-event"),
            "payload": {
                "event": "step_recorded",
                "details": {"step_id": "gate-1", "result": "passed", "run": 1},
            },
        }
        self.assertFalse(
            builders._binding_is_current(
                recreated_fact,
                binding,
                record,
                source_event,
                None,
                source_state,
                (
                    (source_event, None, source_state, (), None),
                    (
                        away_event,
                        source_state,
                        different_candidate,
                        (),
                        None,
                    ),
                    (
                        return_event,
                        different_candidate,
                        returned_candidate,
                        (),
                        None,
                    ),
                    (
                        recreated_event,
                        returned_candidate,
                        recreated_fact,
                        (),
                        None,
                    ),
                ),
                chain_family="commit",
            )
        )

        gate_two_source = {
            "candidate": {"sha256": candidate},
            "steps": {
                "assertion-sensor": [
                    {"candidate": candidate, "result": "passed"}
                ]
            },
        }
        changed_gate_two = copy.deepcopy(gate_two_source)
        changed_gate_two["steps"]["assertion-sensor"].append(
            {"candidate": candidate, "result": "failed"}
        )
        gate_two_source_event = {
            "digest": key("gate-two-source-event"),
            "payload": {
                "event": "step_recorded",
                "details": {
                    "step_id": "assertion-sensor",
                    "result": "passed",
                    "run": 1,
                },
            },
        }
        gate_two_changed_event = {
            "digest": key("gate-two-changed-event"),
            "payload": {
                "event": "step_recorded",
                "details": {
                    "step_id": "assertion-sensor",
                    "result": "failed",
                    "run": 2,
                },
            },
        }
        self.assertFalse(
            builders._binding_is_current(
                changed_gate_two,
                binding,
                {
                    "type": "verification",
                    "criterion": "gate-2: assertion sensor",
                    "result": "passed",
                },
                gate_two_source_event,
                None,
                gate_two_source,
                (
                    (
                        gate_two_source_event,
                        None,
                        gate_two_source,
                        (),
                        None,
                    ),
                    (
                        gate_two_changed_event,
                        gate_two_source,
                        changed_gate_two,
                        (),
                        None,
                    ),
                ),
                chain_family="commit",
            )
        )

    def test_binding_currentness_rejects_superseded_review_tuple(self) -> None:
        candidate = key("candidate")
        pass_review = {
            "verdict": "PASS",
            "iteration": 1,
            "reviewer_role": "review-final",
            "package_digest": key("pass-package"),
        }
        binding = self.binding("review-current", review=pass_review)
        source_state = {
            "candidate": {"sha256": candidate},
            "review": {
                "iteration": 1,
                "request": None,
                "verdict": copy.deepcopy(pass_review),
            },
        }
        source_event = {
            "digest": key("review-pass-source-event"),
            "payload": {"event": "review_passed", "details": {}}
        }
        record = {
            "type": "verification",
            "criterion": journal.GATE_3_CRITERION,
            "result": "passed",
        }
        self.assertTrue(
            builders._binding_is_current(
                source_state,
                binding,
                record,
                source_event,
                None,
                source_state,
                ((source_event, None, source_state, (), None),),
                chain_family="commit",
            )
        )
        blocked_state = copy.deepcopy(source_state)
        blocked_state["review"] = {
            "iteration": 2,
            "request": None,
            "verdict": {
                "verdict": "BLOCK",
                "reviewer_role": "review-final",
                "package_digest": key("block-package"),
            },
        }
        blocked_event = {
            "digest": key("review-block-event"),
            "payload": {"event": "review_blocked", "details": {}},
        }
        self.assertFalse(
            builders._binding_is_current(
                blocked_state,
                binding,
                record,
                source_event,
                None,
                source_state,
                (
                    (source_event, None, source_state, (), None),
                    (blocked_event, source_state, blocked_state, (), None),
                ),
                chain_family="commit",
            )
        )

    def correlation_records(self) -> list[dict[str, object]]:
        gate1 = self.binding("gate1")
        gate2 = self.binding("gate2")
        gate3 = self.binding(
            "gate3",
            review={
                "verdict": "PASS", "iteration": 1,
                "reviewer_role": "review-final", "package_digest": key("package"),
            },
        )
        landing = self.binding("landing")
        records = [
            {"type": "run_started", "writer_contract": journal.WRITER_CONTRACT},
            {"type": "task", "id": "task-01", "status": "active"},
            {
                "type": "execution", "agent": "codex-impl-01", "execution": "execution-01",
                "task": "task-01", "role": "implementation",
            },
            {
                "type": "execution_result", "agent": "codex-impl-01",
                "execution": "execution-01", "task": "task-01", "status": "complete",
            },
            {
                "type": "verification", "id": "check-01", "task": "task-01",
                "criterion": "gate-1: project tests", "result": "passed", "binding": gate1,
            },
            {
                "type": "verification", "id": "check-02", "task": "task-01",
                "criterion": "gate-2: stack checks", "result": "passed", "binding": gate2,
            },
            {
                "type": "verification", "id": "check-03", "task": "task-01",
                "criterion": journal.GATE_3_CRITERION, "result": "passed", "binding": gate3,
            },
            {
                "type": "decision", "id": "decision-01", "task": "task-01",
                "outcome": "chain-landing", "binding": landing,
            },
            {"type": "task", "id": "task-01", "status": "complete"},
            {"type": "run_closed", "judgment": "passed"},
        ]
        for line, record in enumerate(records, start=1):
            record["_line"] = line
        return records

    def issue_for(self, records: list[dict[str, object]]) -> list[str]:
        issues: list[str] = []
        journal._check_binding_correlation(records, issues)
        return issues

    def test_fr021_four_exact_correlation_issues_and_disabled_control(self) -> None:
        baseline = self.correlation_records()
        self.assertEqual(self.issue_for(baseline), [])

        missing = copy.deepcopy(baseline)
        del missing[4]["binding"]
        self.assertEqual(
            self.issue_for(missing),
            ["activated gate verification 'check-01' has no valid forge-gate-binding/1 binding"],
        )

        inconsistent = copy.deepcopy(baseline)
        inconsistent[7]["binding"] = self.binding(
            "different-landing",
            candidate={"kind": "staged-diff-sha256", "value": key("different")},
        )
        self.assertEqual(
            self.issue_for(inconsistent),
            ["task 'task-01' has inconsistent bound candidate across gate and landing records"],
        )

        preceding = copy.deepcopy(baseline)
        preceding[4]["_line"] = 4
        binding_id = preceding[4]["binding"]["binding_id"]
        self.assertEqual(
            self.issue_for(preceding),
            [f"binding '{binding_id}' precedes the last mutating execution for task 'task-01'"],
        )

        terminal_first = copy.deepcopy(baseline)
        terminal_first[8]["_line"] = 7
        self.assertEqual(
            self.issue_for(terminal_first),
            ["terminal task 'task-01' precedes a bound chain landing decision"],
        )

        with mock.patch.object(journal, "BINDING_CORRELATION_CONTROLS", frozenset()):
            self.assertEqual(self.issue_for(missing), [])

    def _semantic_state(
        self,
        family: str,
        chain_id: str,
        candidate_value: object,
    ) -> dict[str, object]:
        common: dict[str, object] = {
            "schema": "forge-chain/1" if family == "commit" else "forge-merge-chain/1",
            "chain_id": chain_id,
            "kind": family,
            "state": "closed",
            "created_at": "2026-08-28T11:00:00Z",
            "last_event_at": "2026-08-28T12:00:00Z",
            "inactive_after": "2026-08-29T12:00:00Z",
            "policy_source": {},
            "candidate": {},
            "tier": {},
            "steps": {},
            "review": {},
            "approval": {},
            "authorization": {},
            "run_binding": {
                "run_id": "run-20260828-semantic-replay",
                "task_id": "task-01",
                "repository": str(self.repo.resolve()),
                "policy_digest": key("semantic-policy"),
            },
            "journal_outbox": None,
        }
        if family == "commit":
            assert isinstance(candidate_value, str)
            common.update(
                {
                    "repo_head": "1" * 40,
                    "paths": ["src/example.py"],
                    "staging": {},
                    "candidate": {"sha256": candidate_value},
                    "commit_result": {
                        "intent": {"candidate": candidate_value},
                        "commit_sha": "2" * 40,
                    },
                }
            )
        else:
            assert isinstance(candidate_value, dict)
            common.update(
                {
                    "owner": {},
                    "run": {},
                    "repository": str(self.repo.resolve()),
                    "worktree": {},
                    "branch": {},
                    "target": {},
                    "candidate": {
                        "remote_tip": candidate_value["base"],
                        "candidate_head": candidate_value["head"],
                        "generation_digest": key("merge-generation"),
                    },
                    "integration": {
                        "push": {"landed_head": candidate_value["head"]}
                    },
                    "cleanup": {},
                }
            )
        return common

    def _write_semantic_chain(
        self,
        family: str,
        *,
        invented_event: str,
        stale_rollback: bool,
    ) -> tuple[str, str]:
        chain_id = "c-2026-08-28T120000Z-cafe"
        candidate: object = (
            key("semantic-commit-candidate")
            if family == "commit"
            else {"base": "3" * 40, "head": "4" * 40}
        )
        state = self._semantic_state(family, chain_id, candidate)
        chains = self.repo / ".forge/chains"
        chains.mkdir(parents=True, exist_ok=True)
        events: list[dict[str, object]] = []
        previous = "0" * 64

        if stale_rollback:
            newer: object = (
                key("semantic-newer-commit-candidate")
                if family == "commit"
                else {"base": "5" * 40, "head": "6" * 40}
            )
            earlier_state = self._semantic_state(family, chain_id, newer)
            earlier_state["state"] = "reviewing"
            earlier_state["journal_outbox"] = None
            if family == "commit":
                unsigned: dict[str, object] = {
                    "sequence": 1,
                    "prev_digest": previous,
                    "payload": {
                        "at": "2026-08-28T11:30:00Z",
                        "details": {"fixture": "newer candidate"},
                        "event": "review_completed",
                        "state": earlier_state,
                    },
                }
            else:
                unsigned = {
                    "schema": "forge-merge-event/1",
                    "chain_id": chain_id,
                    "sequence": 1,
                    "at": "2026-08-28T11:30:00Z",
                    "event": "review_completed",
                    "generation_digest": key("merge-generation"),
                    "previous_digest": previous,
                    "payload": {"fixture": "newer candidate", "state": earlier_state},
                }
            first = {
                **unsigned,
                "digest": journal._sha256(journal._canonical_json_bytes(unsigned)),
            }
            events.append(first)
            previous = str(first["digest"])

        sequence = len(events) + 1
        if family == "commit":
            unsigned_final: dict[str, object] = {
                "sequence": sequence,
                "prev_digest": previous,
                "payload": {
                    "at": "2026-08-28T12:00:00Z",
                    "details": {"fixture": True},
                    "event": invented_event,
                    "state": copy.deepcopy(state),
                },
            }
            source_carrier = unsigned_final["payload"]["details"]
        else:
            unsigned_final = {
                "schema": "forge-merge-event/1",
                "chain_id": chain_id,
                "sequence": sequence,
                "at": "2026-08-28T12:00:00Z",
                "event": invented_event,
                "generation_digest": key("merge-generation"),
                "previous_digest": previous,
                "payload": {"fixture": True, "state": copy.deepcopy(state)},
            }
            source_carrier = unsigned_final["payload"]
        source_digest = journal._sha256(
            journal._canonical_json_bytes(unsigned_final)
        )
        binding = self.binding(
            f"semantic-{family}",
            candidate=(
                {"kind": "staged-diff-sha256", "value": candidate}
                if family == "commit"
                else {"kind": "git-range", "value": candidate}
            ),
        )
        binding["source_record"] = {
            "chain_id": chain_id,
            "event_digest": source_digest,
        }
        preimage = {name: binding[name] for name in (
            "schema", "source_record", "candidate", "review"
        )}
        binding["binding_id"] = journal._sha256(
            journal._canonical_json_bytes(preimage)
        )
        record = {
            "type": "decision",
            "recorded_at": "2026-08-28T12:00:00Z",
            "run_id": "run-20260828-semantic-replay",
            "id": "decision-01",
            "task": "task-01",
            "resolution": "Candidate landed",
            "outcome": "chain-landing",
            "basis": [],
            "binding": binding,
        }
        batch_bytes = journal._journal_line(record)
        carried = {
            "idempotency_key": source_digest,
            "batch_digest": journal._sha256(batch_bytes),
            "record_count": 1,
            "records": [record],
        }
        source_carrier["source_event_digest"] = source_digest
        source_carrier["journal_batch"] = carried
        final_state = unsigned_final["payload"]["state"]
        final_state["journal_outbox"] = {
            "idempotency_key": source_digest,
            "batch_digest": carried["batch_digest"],
            "record_count": 1,
            "source_event_digest": source_digest,
        }
        final = {
            **unsigned_final,
            "digest": journal._sha256(journal._canonical_json_bytes(unsigned_final)),
        }
        events.append(final)
        (chains / f"{chain_id}.events.jsonl").write_bytes(
            b"".join(journal._canonical_json_bytes(event) + b"\n" for event in events)
        )
        (chains / f"{chain_id}.json").write_bytes(
            journal._canonical_json_bytes(final_state) + b"\n"
        )
        return chain_id, str(binding["binding_id"])

    def test_commit_and_merge_replay_reject_invented_self_consistent_transitions(self) -> None:
        for family in ("commit", "merge"):
            with self.subTest(family=family):
                chain_id, binding_id = self._write_semantic_chain(
                    family,
                    invented_event="invented_candidate_landed",
                    stale_rollback=False,
                )
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal, "binding chain replay failed"
                ):
                    builders.resolve_binding(
                        self.repo,
                        chain_id,
                        binding_id,
                        expected_type="decision",
                        expected_fields={
                            "task": "task-01",
                            "outcome": "chain-landing",
                        },
                        expected_run_id="run-20260828-semantic-replay",
                        expected_task_id="task-01",
                    )

    def test_commit_and_merge_replay_reject_digest_valid_candidate_rollback(self) -> None:
        for family in ("commit", "merge"):
            with self.subTest(family=family):
                other_repo = Path(self.temporary.name) / f"repo-{family}-rollback"
                subprocess.run(
                    ["git", "init", "--quiet", str(other_repo)], check=True
                )
                self.repo = other_repo
                chain_id, binding_id = self._write_semantic_chain(
                    family,
                    invented_event="chain_closed",
                    stale_rollback=True,
                )
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal, "binding chain replay failed"
                ):
                    builders.resolve_binding(
                        self.repo,
                        chain_id,
                        binding_id,
                        expected_type="decision",
                        expected_fields={
                            "task": "task-01",
                            "outcome": "chain-landing",
                        },
                        expected_run_id="run-20260828-semantic-replay",
                        expected_task_id="task-01",
                    )


class Revision9MergeTransitionGrammarTests(unittest.TestCase):
    CHAIN_ID = "c-2026-08-28T120000Z-cafe"
    BASE_AT = "2026-08-28T12:00:00Z"
    NEXT_AT = "2026-08-28T12:01:00Z"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-revision9-merge-grammar-")
        self.addCleanup(self.temporary.cleanup)
        self.repository = str((Path(self.temporary.name) / "repo").resolve())
        self.worktree_path = str((Path(self.temporary.name) / "worktree").resolve())
        self.git_dir = str((Path(self.temporary.name) / "git-dir").resolve())
        self.common_dir = str((Path(self.temporary.name) / "common-dir").resolve())
        worktree_identity = {
            "path": self.worktree_path,
            "git_dir": self.git_dir,
            "common_dir": self.common_dir,
        }
        worktree_digest = journal._sha256(
            journal._canonical_json_bytes(worktree_identity)
        )
        self.claim_path = str(
            Path(self.common_dir).parent
            / ".forge"
            / "chains"
            / "owners"
            / f"{worktree_digest}.claim"
        )
        self.policy_digest = key("merge-policy")
        self.candidate_head = "4" * 40
        self.remote_tip = "3" * 40

    def _candidate(
        self,
        *,
        worktree_identity: dict[str, object] | None = None,
        generation: int = 1,
        remote_tip: str | None = None,
        candidate_head: str | None = None,
    ) -> dict[str, object]:
        preimage: dict[str, object] = {
            "remote": "origin",
            "destination_ref": "refs/heads/main",
            "remote_tip": remote_tip or self.remote_tip,
            "candidate_head": candidate_head or self.candidate_head,
            "diff_sha256": key(f"merge-diff-{generation}"),
            "policy_commit": "2" * 40,
            "policy_digest": self.policy_digest,
            "worktree_identity": worktree_identity
            or {
                "path": self.worktree_path,
                "git_dir": self.git_dir,
                "common_dir": self.common_dir,
            },
            "generation": generation,
        }
        return {
            **preimage,
            "generation_digest": journal._sha256(
                journal._canonical_json_bytes(preimage)
            ),
        }

    def _state(
        self,
        state_name: str = "verifying",
        *,
        candidate: bool = True,
        bound: bool = False,
        claim_status: str = "owned",
        at: str = BASE_AT,
        inactive_after: str = "2026-08-29T12:00:00Z",
    ) -> dict[str, object]:
        run_binding: dict[str, object] | None = None
        if bound:
            run_binding = {
                "run_id": "run-20260828-merge-grammar",
                "task_id": "task-01",
                "repository": self.repository,
                "policy_digest": self.policy_digest,
            }
        current_candidate = self._candidate() if candidate else None
        return {
            "schema": "forge-merge-chain/1",
            "chain_id": self.CHAIN_ID,
            "kind": "merge",
            "state": state_name,
            "created_at": self.BASE_AT,
            "last_event_at": at,
            "inactive_after": inactive_after,
            "owner": {
                "pid": 17,
                "host": "fixture-host",
                "session": "fixture-session",
                "started_at": self.BASE_AT,
            },
            "run": run_binding["run_id"] if run_binding is not None else None,
            "repository": self.repository,
            "worktree": {
                "path": self.worktree_path,
                "git_dir": self.git_dir,
                "common_dir": self.common_dir,
                "claim": {
                    "status": claim_status,
                    "path": self.claim_path,
                    "inode": 17 if claim_status != "unpublished" else None,
                    "digest": (
                        key("merge-claim") if claim_status != "unpublished" else None
                    ),
                },
            },
            "branch": "refs/heads/feature",
            "target": {
                "remote": "origin",
                "destination_ref": "refs/heads/main",
                "manifest_commit": "1" * 40,
            },
            "policy_source": {
                "commit": "2" * 40,
                "digest": self.policy_digest,
            },
            "candidate": current_candidate,
            "tier": {"control": False, "categories": []} if candidate else None,
            "steps": {},
            "review": {},
            "approval": {},
            "authorization": {},
            "integration": {
                "condition": "none",
                "primary_condition": "none",
                "epoch": None,
                "remote_movement_count": 0,
                "intent": None,
                "observed": None,
                "pre_rebase": None,
                "conflict": None,
                "push": None,
            },
            "cleanup": {"condition": "none"},
            "run_binding": run_binding,
            "journal_outbox": None,
        }

    def _deadline(self, prior: dict[str, object], at: str) -> str:
        event_at = builders._utc_value(at)
        prior_deadline = builders._utc_value(prior["inactive_after"])
        assert event_at is not None and prior_deadline is not None
        selected = (
            prior_deadline
            if event_at >= prior_deadline
            else event_at + dt.timedelta(hours=24)
        )
        return selected.isoformat().replace("+00:00", "Z")

    def _with_current_merge_authority(
        self,
        state: dict[str, object],
        *,
        control: bool = False,
    ) -> dict[str, object]:
        current = copy.deepcopy(state)
        candidate = current["candidate"]
        assert isinstance(candidate, dict)
        generation = candidate["generation_digest"]
        current["tier"] = {"control": control, "categories": []}
        current["steps"] = {
            "gate-1": [
                {
                    "criterion": "gate-1: focused tests",
                    "result": "passed",
                    "generation_digest": generation,
                }
            ],
            "assertion-sensor": {
                "criterion": "gate-2: assertion-quality sensor",
                "result": "passed",
                "generation_digest": generation,
            },
        }
        package_digest = key("merge-current-review-package")
        current["review"] = {
            "iteration": 1,
            "request": {
                "candidate": candidate["candidate_head"],
                "package": "review/package.txt",
                "package_digest": package_digest,
                "reviewer": "review-final",
                "iteration": 1,
            },
            "verdict": {
                "verdict": "PASS",
                "candidate": candidate["candidate_head"],
                "package_digest": package_digest,
                "reviewer_role": "review-final",
                "iteration": 1,
            },
            "dispositions": [],
        }
        current["authorization"] = {
            "candidate_head": candidate["candidate_head"],
            "generation_digest": generation,
            "diff_summary": "fixture merge diff",
            "control_paths": ["scripts/control.py"] if control else [],
            "review_verdict": "PASS",
            "recorded_at": self.BASE_AT,
        }
        current["approval"] = (
            {
                "purpose": "gate-4",
                "chain_id": self.CHAIN_ID,
                "candidate": candidate["candidate_head"],
                "generation_digest": generation,
            }
            if control
            else {}
        )
        return current

    def _transition(
        self,
        prior: dict[str, object],
        event_name: str,
        changes: dict[str, object],
        *,
        at: str = NEXT_AT,
        payload: dict[str, object] | None = None,
        previous_digest: str | None = None,
        digest: str | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        current = copy.deepcopy(prior)
        for name, value in changes.items():
            current[name] = copy.deepcopy(value)
        current["last_event_at"] = at
        current["inactive_after"] = self._deadline(prior, at)
        candidate = current.get("candidate")
        generation_digest = (
            candidate.get("generation_digest")
            if isinstance(candidate, dict)
            else None
        )
        event = {
            "schema": "forge-merge-event/1",
            "chain_id": self.CHAIN_ID,
            "sequence": 2,
            "at": at,
            "event": event_name,
            "generation_digest": generation_digest,
            "previous_digest": previous_digest or key(f"previous-{event_name}-{at}"),
            "payload": copy.deepcopy(payload)
            if payload is not None
            else {
                "delta": {
                    name: copy.deepcopy(current[name]) for name in changes
                }
            },
            "digest": digest or key(f"event-{event_name}-{at}"),
        }
        return event, current

    def _initial(self) -> tuple[dict[str, object], dict[str, object]]:
        current = self._state(
            "classifying", candidate=False, claim_status="unpublished"
        )
        delta = {
            name: copy.deepcopy(current[name])
            for name in builders._MERGE_INITIAL_DELTA_FIELDS
        }
        event = {
            "schema": "forge-merge-event/1",
            "chain_id": self.CHAIN_ID,
            "sequence": 1,
            "at": self.BASE_AT,
            "event": "chain_started",
            "generation_digest": None,
            "previous_digest": "0" * 64,
            "payload": {"delta": delta},
            "digest": key("merge-chain-started"),
        }
        return event, current

    def _push_state(self, *, bound: bool = False) -> dict[str, object]:
        state = self._state("pushing", bound=bound)
        candidate = state["candidate"]
        assert isinstance(candidate, dict)
        integration = state["integration"]
        assert isinstance(integration, dict)
        integration["intent"] = {
            "operation": "push",
            "operation_nonce": "a" * 32,
        }
        integration["epoch"] = {
            "operation_nonce": "a" * 32,
            "generation_digest": candidate["generation_digest"],
            "intent_digest": key("merge-epoch-intent"),
            "started_at": self.BASE_AT,
        }
        integration["push"] = {
            "expected_old_tip": self.remote_tip,
            "intended_head": self.candidate_head,
            "destination_ref": "refs/heads/main",
            "intended_at": self.BASE_AT,
            "result": None,
            "attempted_heads": [self.candidate_head],
            "landed_head": None,
        }
        return state

    def _push_observed(
        self,
        *,
        bound: bool,
        landed: bool,
        with_batch: bool = False,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        prior = self._push_state(bound=bound)
        integration = copy.deepcopy(prior["integration"])
        assert isinstance(integration, dict)
        push = integration["push"]
        assert isinstance(push, dict)
        push["result"] = {
            "classification": "success" if landed else "known-failure",
            "exit": 0 if landed else 1,
            "inflight_digest": key("push-inflight"),
            "output_digest": key("push-output"),
            "launch_failed": False,
            "timed_out": False,
            "output_limit_exceeded": False,
            "recorded_at": self.NEXT_AT,
        }
        push["landed_head"] = self.candidate_head if landed else None
        integration["condition"] = "none" if landed else "push-failed"
        integration["observed"] = {
            "exists": True,
            "oid": self.candidate_head if landed else self.remote_tip,
            "contains_intended_head": landed,
            "attempted_head_containment": [
                {"head": self.candidate_head, "contained": landed}
            ],
            "observed_at": self.NEXT_AT,
            "inflight_digest": key("push-inflight"),
            "output_digest": key("push-output"),
        }
        integration["intent"] = {
            "schema": "forge-remote-observation-intent/1",
            "transaction": "merge",
            "chain_id": self.CHAIN_ID,
            "attempt_identity": key("merge-epoch-intent"),
            "phase": "post-push",
            "push_intent_digest": key(
                f"previous-push_observed-{self.NEXT_AT}"
            ),
        }
        changes: dict[str, object] = {"integration": integration}
        if landed:
            changes["state"] = "pushed"
        event, current = self._transition(prior, "push_observed", changes)
        if with_batch:
            source_digest = key("push-source-event")
            record = {"type": "decision", "outcome": "chain-landing"}
            carried = {
                "idempotency_key": source_digest,
                "batch_digest": key("push-batch"),
                "record_count": 1,
                "records": [record],
            }
            event_payload = event["payload"]
            assert isinstance(event_payload, dict)
            event_payload.update(
                {
                    "source_event_digest": source_digest,
                    "journal_batch": carried,
                }
            )
            current["journal_outbox"] = {
                "idempotency_key": source_digest,
                "batch_digest": carried["batch_digest"],
                "record_count": 1,
                "source_event_digest": source_digest,
            }
        return prior, event, current

    def _push_context(
        self, event: dict[str, object], prior: dict[str, object]
    ) -> dict[str, object]:
        integration = prior["integration"]
        assert isinstance(integration, dict)
        return {
            "epoch_intent": {
                "digest": key("merge-epoch-intent"),
                "generation_digest": event["generation_digest"],
                "push_consumed": True,
            },
            "push_intent": {
                "digest": event["previous_digest"],
                "generation_digest": event["generation_digest"],
                "evidence": copy.deepcopy(integration["intent"]),
                "admitted_active": True,
            }
        }

    def test_scalar_edge_table_is_closed_for_all_28_events(self) -> None:
        states = set(builders._MERGE_STATES)
        nonterminal = states - {"closed", "aborted"}
        mutable = {
            "classifying",
            "verifying",
            "reviewing",
            "revising",
            "awaiting_approval",
            "authorized",
        }

        def pairs(before: set[str], after: set[str]) -> set[tuple[str, str]]:
            return {(left, right) for left in before for right in after}

        expected: dict[str, set[tuple[str, str]]] = {
            "chain_started": set(),
            "ownership_intent": {("classifying", "classifying")},
            "ownership_claimed": {("classifying", "classifying")},
            "ownership_release_intent": {(value, value) for value in nonterminal},
            "ownership_released": {(value, value) for value in nonterminal},
            "gate_recorded": {
                ("verifying", "verifying"),
                ("verifying", "reviewing"),
                ("reverifying", "reverifying"),
                ("reverifying", "reverification_failed"),
            },
            "review_requested": {("reviewing", "reviewing")},
            "review_attached": pairs(
                {"reviewing"},
                {"reviewing", "revising", "awaiting_approval", "authorized"},
            ),
            "review_disposition": {
                ("reviewing", "reviewing"),
                ("revising", "revising"),
            },
            "approval_recorded": {
                ("reviewing", "reviewing"),
                ("revising", "revising"),
                ("awaiting_approval", "authorized"),
            },
            "generation_refreshed": pairs(mutable, {"verifying"}),
            "generation_carried_forward": pairs(
                {"rebasing", "reverifying"},
                {"reverifying", "authorized", "awaiting_approval"},
            ),
            "epoch_intent": {("authorized", "rebasing")},
            "fetch_intent": pairs(mutable, {"classifying"})
            | {("rebasing", "rebasing")},
            "fetch_result": pairs({"classifying"}, {"classifying", "verifying"})
            | pairs({"rebasing", "reverifying"}, {"rebasing", "authorized"}),
            "rebase_intent": {
                ("rebasing", "rebasing"),
                ("rebase_conflict", "rebase_conflict"),
            },
            "rebase_conflict": pairs(
                {"rebasing", "rebase_conflict"}, {"rebase_conflict"}
            ),
            "rebase_result": pairs(
                {"rebasing"},
                {"rebasing", "rebase_conflict", "reverifying", "revising", "authorized"},
            )
            | pairs(
                {"rebase_conflict"},
                {"rebase_conflict", "reverifying", "revising"},
            ),
            "reverification_result": pairs(
                {"reverifying"},
                {"reverifying", "reverification_failed", "reviewing", "revising"},
            ),
            "push_intent": pairs({"rebasing", "reverifying"}, {"pushing"}),
            "push_observed": pairs(
                {"rebasing", "reverifying", "pushing"},
                {"authorized", "awaiting_approval"},
            )
            | {
                ("rebasing", "rebasing"),
                ("reverifying", "reverifying"),
                ("pushing", "pushing"),
            },
            "cleanup_intent": {
                ("pushed", "pushed"),
                ("cleanup_pending", "cleanup_pending"),
            },
            "cleanup_result": {
                ("pushed", "pushed"),
                ("pushed", "cleanup_pending"),
                ("cleanup_pending", "cleanup_pending"),
            },
            # The neutral condition is a no-op state edge.  Condition-specific
            # non-neutral edges are pinned separately below.
            "condition_recorded": {(value, value) for value in states},
            "lock_release_result": {(value, value) for value in states},
            "aborted": {(value, "aborted") for value in nonterminal},
            "closed": {
                ("pushed", "closed"),
                ("cleanup_pending", "closed"),
            },
            "journal_receipted": {(value, value) for value in states},
        }
        self.assertEqual(set(expected), set(builders._MERGE_EVENT_NAMES))
        neutral = self._state()
        for event_name, accepted in expected.items():
            for before in states:
                for after in states:
                    with self.subTest(event=event_name, before=before, after=after):
                        current = copy.deepcopy(neutral)
                        current["state"] = after
                        self.assertEqual(
                            builders._merge_state_edge_valid(
                                event_name,
                                before,
                                after,
                                current,
                                prior_inactive=False,
                                delta={"integration": current["integration"]},
                            ),
                            (before, after) in accepted,
                        )

    def test_epoch_identity_is_event_bound_and_cannot_clear_before_park(self) -> None:
        prior = self._with_current_merge_authority(self._state("authorized"))
        generation = prior["candidate"]["generation_digest"]
        epoch_event_digest = key("exact-epoch-intent-event")
        integration = copy.deepcopy(prior["integration"])
        integration["epoch"] = {
            "operation_nonce": "e" * 32,
            "generation_digest": generation,
            "intent_digest": epoch_event_digest,
            "started_at": self.NEXT_AT,
        }
        integration["intent"] = {
            "operation": "epoch",
            "operation_nonce": "e" * 32,
            "generation_digest": generation,
            "intent_digest": epoch_event_digest,
        }
        epoch_event, rebasing = self._transition(
            prior,
            "epoch_intent",
            {"state": "rebasing", "integration": integration},
            digest=epoch_event_digest,
        )
        epoch_event["payload"]["delta"]["integration"]["epoch"][
            "intent_digest"
        ] = None
        context: dict[str, object] = {
            "required_gate_ids": ("gate-1", "assertion-sensor")
        }
        self.assertTrue(
            builders._merge_transition_valid(
                epoch_event, prior, rebasing, context=context
            )
        )

        fabricated = copy.deepcopy(rebasing)
        fabricated["integration"]["epoch"]["intent_digest"] = key(
            "fabricated-epoch-intent"
        )
        fabricated_event = copy.deepcopy(epoch_event)
        self.assertFalse(
            builders._merge_transition_valid(
                fabricated_event,
                prior,
                fabricated,
                context={"required_gate_ids": ("gate-1", "assertion-sensor")},
            )
        )
        recursive_carrier = copy.deepcopy(epoch_event)
        recursive_carrier["payload"]["delta"]["integration"]["epoch"][
            "intent_digest"
        ] = epoch_event_digest
        self.assertFalse(
            builders._merge_transition_valid(
                recursive_carrier,
                prior,
                rebasing,
                context={"required_gate_ids": ("gate-1", "assertion-sensor")},
            )
        )

        injected_condition = copy.deepcopy(rebasing)
        injected_condition["integration"]["condition"] = "remote-churn"
        condition_event = copy.deepcopy(epoch_event)
        condition_event["payload"]["delta"]["integration"] = copy.deepcopy(
            injected_condition["integration"]
        )
        condition_event["payload"]["delta"]["integration"]["epoch"][
            "intent_digest"
        ] = None
        self.assertFalse(
            builders._merge_transition_valid(
                condition_event,
                prior,
                injected_condition,
                context={"required_gate_ids": ("gate-1", "assertion-sensor")},
            )
        )

        history_prior = copy.deepcopy(prior)
        history_prior["integration"]["push"] = copy.deepcopy(
            self._push_state()["integration"]["push"]
        )
        history_current = copy.deepcopy(rebasing)
        history_current["integration"]["push"] = copy.deepcopy(
            history_prior["integration"]["push"]
        )
        history_event = copy.deepcopy(epoch_event)
        history_event["payload"]["delta"]["integration"] = copy.deepcopy(
            history_current["integration"]
        )
        history_event["payload"]["delta"]["integration"]["epoch"][
            "intent_digest"
        ] = None
        self.assertTrue(
            builders._merge_transition_valid(
                history_event,
                history_prior,
                history_current,
                context={"required_gate_ids": ("gate-1", "assertion-sensor")},
            )
        )
        dropped_history = copy.deepcopy(history_current)
        dropped_history["integration"]["push"] = None
        dropped_event = copy.deepcopy(history_event)
        dropped_event["payload"]["delta"]["integration"] = copy.deepcopy(
            dropped_history["integration"]
        )
        dropped_event["payload"]["delta"]["integration"]["epoch"][
            "intent_digest"
        ] = None
        self.assertFalse(
            builders._merge_transition_valid(
                dropped_event,
                history_prior,
                dropped_history,
                context={"required_gate_ids": ("gate-1", "assertion-sensor")},
            )
        )

        retained_integration = copy.deepcopy(rebasing["integration"])
        retained_integration["intent"] = {
            "operation": "fetch",
            "operation_nonce": "e" * 32,
            "generation_digest": generation,
            "attempt": 1,
        }
        fetch_event, fetching = self._transition(
            rebasing,
            "fetch_intent",
            {"integration": retained_integration},
            at="2026-08-28T12:02:00Z",
            previous_digest=str(epoch_event["digest"]),
        )
        self.assertTrue(
            builders._merge_transition_valid(
                fetch_event, rebasing, fetching, context=copy.deepcopy(context)
            )
        )

        cleared = copy.deepcopy(fetching)
        cleared["integration"]["epoch"] = None
        cleared_event = copy.deepcopy(fetch_event)
        cleared_event["payload"]["delta"]["integration"] = copy.deepcopy(
            cleared["integration"]
        )
        self.assertFalse(
            builders._merge_transition_valid(
                cleared_event, rebasing, cleared, context=copy.deepcopy(context)
            )
        )

    def test_inactive_cleanup_replays_only_after_current_pushed_truth(self) -> None:
        _push_prior, _push_event, pushed = self._push_observed(
            bound=False, landed=True
        )
        pushed["inactive_after"] = "2026-08-28T12:00:30Z"
        generation = pushed["candidate"]["generation_digest"]
        epoch_context = {
            "epoch_intent": {
                "digest": key("merge-epoch-intent"),
                "generation_digest": generation,
                "push_consumed": True,
            }
        }

        for scalar_state, condition in (
            ("pushed", "none"),
            ("cleanup_pending", "cleanup-failed"),
        ):
            prior = copy.deepcopy(pushed)
            prior["state"] = scalar_state
            prior["cleanup"] = {"condition": condition}
            cleanup = {
                "condition": condition,
                "intent": {
                    "operation_nonce": "c" * 32,
                    "generation_digest": generation,
                    "started_at": "2026-08-28T13:00:00Z",
                },
            }
            intent_event, intent_state = self._transition(
                prior,
                "cleanup_intent",
                {"cleanup": cleanup},
                at="2026-08-28T13:00:00Z",
                digest=key(f"inactive-cleanup-intent-{scalar_state}"),
            )
            context = copy.deepcopy(epoch_context)
            with self.subTest(state=scalar_state, phase="intent"):
                self.assertTrue(
                    builders._merge_transition_valid(
                        intent_event, prior, intent_state, context=context
                    )
                )

            result_event, result_state = self._transition(
                intent_state,
                "cleanup_result",
                {"cleanup": {"condition": "none"}},
                at="2026-08-28T13:01:00Z",
                previous_digest=str(intent_event["digest"]),
            )
            with self.subTest(state=scalar_state, phase="result"):
                self.assertTrue(
                    builders._merge_transition_valid(
                        result_event, intent_state, result_state, context=context
                    )
                )

        for scalar_state in ("pushed", "cleanup_pending"):
            fabricated = self._state(
                scalar_state,
                at=self.NEXT_AT,
                inactive_after="2026-08-28T12:00:30Z",
            )
            cleanup = {
                "condition": "none",
                "intent": {
                    "operation_nonce": "c" * 32,
                    "generation_digest": fabricated["candidate"][
                        "generation_digest"
                    ],
                    "started_at": "2026-08-28T13:00:00Z",
                },
            }
            event, current = self._transition(
                fabricated,
                "cleanup_intent",
                {"cleanup": cleanup},
                at="2026-08-28T13:00:00Z",
            )
            with self.subTest(state=scalar_state, phase="no-pushed-truth"):
                self.assertFalse(
                    builders._merge_transition_valid(
                        event, fabricated, current, context={}
                    )
                )

    def test_condition_edge_table_and_forbidden_top_level_fields_are_closed(self) -> None:
        states = set(builders._MERGE_STATES)
        expected_condition_edges = {
            "none": {(value, value) for value in states},
            "fetch-failed": {
                (before, after)
                for before in {"classifying", "rebasing", "reverifying"}
                for after in {"classifying", "authorized"}
            },
            "rebase-failed": {
                ("rebasing", "revising"),
                ("rebase_conflict", "revising"),
            },
            "remote-moved": {
                (before, "authorized")
                for before in {"authorized", "rebasing", "reverifying", "pushing"}
            },
            "remote-churn": {
                (before, "awaiting_approval")
                for before in {
                    "authorized",
                    "awaiting_approval",
                    "rebasing",
                    "reverifying",
                    "pushing",
                }
            },
            "push-failed": {("pushing", "pushing")},
            "push-outcome-unknown": {("pushing", "pushing")},
            "non-fast-forward": {("pushing", "authorized")},
            "lock-release-failed": {(value, value) for value in states},
            "foreign-git-state": {(value, value) for value in states},
        }
        for condition, accepted in expected_condition_edges.items():
            for before in states:
                for after in states:
                    current = self._state(after)
                    integration = current["integration"]
                    assert isinstance(integration, dict)
                    integration["condition"] = condition
                    integration["primary_condition"] = (
                        "none" if condition == "lock-release-failed" else "none"
                    )
                    with self.subTest(condition=condition, before=before, after=after):
                        self.assertEqual(
                            builders._merge_state_edge_valid(
                                "condition_recorded",
                                before,
                                after,
                                current,
                                prior_inactive=False,
                                delta={"integration": integration},
                            ),
                            (before, after) in accepted,
                        )

        cleanup_failed = {
            ("pushed", "cleanup_pending"),
            ("cleanup_pending", "cleanup_pending"),
        }
        for before in states:
            for after in states:
                current = self._state(after)
                current["cleanup"] = {"condition": "cleanup-failed"}
                self.assertEqual(
                    builders._merge_state_edge_valid(
                        "condition_recorded",
                        before,
                        after,
                        current,
                        prior_inactive=False,
                        delta={"cleanup": current["cleanup"]},
                    ),
                    (before, after) in cleanup_failed,
                )

        expected_fields = {
            "chain_started": {
                "schema",
                "chain_id",
                "kind",
                "state",
                "created_at",
                "owner",
                "run",
                "repository",
                "worktree",
                "branch",
                "target",
                "policy_source",
                "candidate",
                "tier",
                "steps",
                "review",
                "approval",
                "authorization",
                "integration",
                "cleanup",
                "run_binding",
            },
            "ownership_intent": {"worktree"},
            "ownership_claimed": {"worktree"},
            "ownership_release_intent": {"worktree"},
            "ownership_released": {"worktree"},
            "gate_recorded": {"state", "steps"},
            "review_requested": {"review"},
            "review_attached": {"state", "review", "approval", "authorization"},
            "review_disposition": {"review"},
            "approval_recorded": {
                "state", "review", "approval", "authorization", "integration",
            },
            "generation_refreshed": {
                "state", "policy_source", "candidate", "tier", "steps", "review",
                "approval", "authorization", "integration",
            },
            "generation_carried_forward": {"state", "candidate", "steps", "integration"},
            "epoch_intent": {"state", "integration"},
            "fetch_intent": {"state", "integration"},
            "fetch_result": {
                "state", "policy_source", "candidate", "tier", "steps", "review",
                "approval", "authorization", "integration",
            },
            "rebase_intent": {"state", "integration"},
            "rebase_conflict": {"state", "integration"},
            "rebase_result": {
                "state", "policy_source", "candidate", "tier", "steps", "review",
                "approval", "authorization", "integration",
            },
            "reverification_result": {
                "state", "steps", "review", "approval", "authorization", "integration",
            },
            "push_intent": {"state", "integration", "authorization"},
            "push_observed": {"state", "integration"},
            "cleanup_intent": {"state", "cleanup"},
            "cleanup_result": {"state", "cleanup"},
            "condition_recorded": {"state", "integration", "authorization"},
            "lock_release_result": {"state", "integration"},
            "aborted": {"state"},
            "closed": {"state"},
            "journal_receipted": {"journal_outbox"},
        }
        self.assertEqual(
            {name: set(value) for name, value in builders._MERGE_EVENT_TOP_LEVEL_CHANGES.items()},
            {name: set(value) for name, value in expected_fields.items()},
        )
        for event_name, allowed in expected_fields.items():
            forbidden = (
                builders._MERGE_STATE_KEYS
                - builders._MERGE_DERIVED_STATE_FIELDS
                - set(allowed)
            )
            with self.subTest(event=event_name):
                self.assertTrue(forbidden or event_name == "chain_started")

    def test_initial_nested_shapes_and_candidate_coherence_are_enforced(self) -> None:
        event, current = self._initial()
        self.assertTrue(builders._state_shape_valid(current, self.CHAIN_ID, "merge"))
        self.assertTrue(builders._merge_transition_valid(event, None, current))

        malformed_initial = copy.deepcopy(current)
        malformed_target = malformed_initial["target"]
        assert isinstance(malformed_target, dict)
        malformed_target["unexpected"] = True
        malformed_event = copy.deepcopy(event)
        malformed_event["payload"]["delta"]["target"] = copy.deepcopy(malformed_target)
        self.assertFalse(
            builders._merge_transition_valid(malformed_event, None, malformed_initial)
        )

        wrong_identity = {
            "path": str((Path(self.temporary.name) / "other-worktree").resolve()),
            "git_dir": self.git_dir,
            "common_dir": self.common_dir,
        }
        prior = self._state("reviewing")
        prior["candidate"] = self._candidate(worktree_identity=wrong_identity)
        current_review = {"request": {"reviewer": "review-final"}}
        coherence_event, coherence_current = self._transition(
            prior, "review_requested", {"review": current_review}
        )
        self.assertFalse(
            builders._state_shape_valid(coherence_current, self.CHAIN_ID, "merge")
        )
        self.assertFalse(
            builders._merge_transition_valid(
                coherence_event, prior, coherence_current, context={}
            )
        )

    def test_gate_review_and_approval_require_exact_fact_changes(self) -> None:
        prior = self._state("verifying")
        candidate = prior["candidate"]
        assert isinstance(candidate, dict)
        gate_fact = {
            "criterion": "gate-1: focused tests",
            "result": "passed",
            "generation_digest": candidate["generation_digest"],
        }
        assertion_fact = {
            "criterion": "gate-2: assertion-quality sensor",
            "result": "passed",
            "generation_digest": candidate["generation_digest"],
        }
        prior["steps"] = {"gate-1": [gate_fact]}
        event, current = self._transition(
            prior,
            "gate_recorded",
            {
                "state": "reviewing",
                "steps": {
                    "gate-1": [gate_fact],
                    "assertion-sensor": assertion_fact,
                },
            },
        )
        self.assertTrue(
            builders._merge_transition_valid(
                event,
                prior,
                current,
                context={"required_gate_ids": ("gate-1", "assertion-sensor")},
            )
        )

        state_only, state_only_current = self._transition(
            prior, "gate_recorded", {"state": "reviewing"}
        )
        self.assertFalse(
            builders._merge_transition_valid(
                state_only, prior, state_only_current, context={}
            )
        )
        malformed_steps = copy.deepcopy(current["steps"])
        assert isinstance(malformed_steps, dict)
        malformed_steps["assertion-sensor"]["criterion"] = "gate-1: wrong namespace"
        malformed, malformed_current = self._transition(
            prior,
            "gate_recorded",
            {"state": "reviewing", "steps": malformed_steps},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                malformed, prior, malformed_current, context={}
            )
        )
        forbidden, forbidden_current = self._transition(
            prior,
            "gate_recorded",
            {
                "state": "reviewing",
                "steps": {
                    "gate-1": [gate_fact],
                    "assertion-sensor": assertion_fact,
                },
                "approval": {"forbidden": True},
            },
        )
        self.assertFalse(
            builders._merge_transition_valid(
                forbidden, prior, forbidden_current, context={}
            )
        )
        wrong_edge_prior = self._state("classifying")
        wrong_edge_candidate = wrong_edge_prior["candidate"]
        assert isinstance(wrong_edge_candidate, dict)
        wrong_edge_fact = copy.deepcopy(gate_fact)
        wrong_edge_fact["generation_digest"] = wrong_edge_candidate[
            "generation_digest"
        ]
        wrong_edge, wrong_edge_current = self._transition(
            wrong_edge_prior,
            "gate_recorded",
            {
                "state": "reviewing",
                "steps": {"gate-1": [wrong_edge_fact]},
            },
        )
        self.assertFalse(
            builders._merge_transition_valid(
                wrong_edge, wrong_edge_prior, wrong_edge_current, context={}
            )
        )

        reviewing = self._state("reviewing")
        review_package = key("review-package")
        request_review = {
            "iteration": 1,
            "request": {
                "candidate": self.candidate_head,
                "package": "review/package.txt",
                "package_digest": review_package,
                "reviewer": "review-final",
                "iteration": 1,
            },
        }
        requested_event, requested = self._transition(
            reviewing,
            "review_requested",
            {"review": request_review},
        )
        self.assertTrue(
            builders._merge_transition_valid(
                requested_event, reviewing, requested, context={}
            )
        )
        review = {
            **copy.deepcopy(request_review),
            "verdict": {
                "verdict": "BLOCK",
                "candidate": self.candidate_head,
                "reviewer_role": "review-final",
                "package_digest": review_package,
                "iteration": 1,
            },
        }
        attached, attached_current = self._transition(
            requested,
            "review_attached",
            {"state": "revising", "review": review},
        )
        self.assertTrue(
            builders._merge_transition_valid(
                attached, requested, attached_current, context={}
            )
        )
        review_state_only, review_state_only_current = self._transition(
            requested, "review_attached", {"state": "revising"}
        )
        self.assertFalse(
            builders._merge_transition_valid(
                review_state_only,
                requested,
                review_state_only_current,
                context={},
            )
        )
        malformed_review = copy.deepcopy(review)
        malformed_review["verdict"]["reviewer_role"] = "implementation"
        malformed_attach, malformed_attach_current = self._transition(
            requested,
            "review_attached",
            {"state": "revising", "review": malformed_review},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                malformed_attach, requested, malformed_attach_current, context={}
            )
        )

        awaiting = self._with_current_merge_authority(
            self._state("awaiting_approval"), control=True
        )
        awaiting["approval"] = {}
        approval_candidate = awaiting["candidate"]
        assert isinstance(approval_candidate, dict)
        approval = {
            "purpose": "gate-4",
            "chain_id": self.CHAIN_ID,
            "candidate": self.candidate_head,
            "generation_digest": approval_candidate["generation_digest"],
        }
        approved, approved_current = self._transition(
            awaiting,
            "approval_recorded",
            {
                "state": "authorized",
                "approval": approval,
            },
        )
        self.assertTrue(
            builders._merge_transition_valid(
                approved,
                awaiting,
                approved_current,
                context={"required_gate_ids": ("gate-1", "assertion-sensor")},
            )
        )
        approval_state_only, approval_state_only_current = self._transition(
            awaiting,
            "approval_recorded",
            {"state": "authorized", "authorization": {"token": "fixture-token"}},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                approval_state_only,
                awaiting,
                approval_state_only_current,
                context={},
            )
        )
        malformed_approval = copy.deepcopy(approval)
        malformed_approval["purpose"] = "wrong-purpose"
        malformed_approved, malformed_approved_current = self._transition(
            awaiting,
            "approval_recorded",
            {
                "state": "authorized",
                "approval": malformed_approval,
            },
        )
        self.assertFalse(
            builders._merge_transition_valid(
                malformed_approved,
                awaiting,
                malformed_approved_current,
                context={},
            )
        )

    def test_complete_tuple_closes_gate_review_and_iteration_bypasses(self) -> None:
        prior = self._state("verifying")
        generation = prior["candidate"]["generation_digest"]
        gate_one = {
            "criterion": "gate-1: focused tests",
            "result": "passed",
            "generation_digest": generation,
        }
        assertion = {
            "criterion": "gate-2: assertion-quality sensor",
            "result": "passed",
            "generation_digest": generation,
        }
        prior["steps"] = {"gate-1": [gate_one]}
        gate_event, gate_current = self._transition(
            prior,
            "gate_recorded",
            {
                "state": "reviewing",
                "steps": {
                    "gate-1": [gate_one],
                    "assertion-sensor": assertion,
                },
            },
        )
        self.assertFalse(
            builders._merge_transition_valid(
                gate_event,
                prior,
                gate_current,
                context={
                    "required_gate_ids": (
                        "gate-1",
                        "assertion-sensor",
                        "invariant:1",
                    )
                },
            )
        )

        surplus_prior = copy.deepcopy(prior)
        surplus_prior["steps"]["invariant:999"] = {
            "criterion": "gate-2: invented invariant",
            "result": "passed",
            "generation_digest": generation,
        }
        surplus_event, surplus_current = self._transition(
            surplus_prior,
            "gate_recorded",
            {
                "state": "reviewing",
                "steps": {
                    **copy.deepcopy(surplus_prior["steps"]),
                    "assertion-sensor": assertion,
                },
            },
        )
        self.assertFalse(
            builders._merge_transition_valid(
                surplus_event,
                surplus_prior,
                surplus_current,
                context={"required_gate_ids": ("gate-1", "assertion-sensor")},
            )
        )

        nongate_prior = copy.deepcopy(prior)
        nongate_prior["steps"]["evil"] = {
            "criterion": "gate-2: invented non-gate",
            "result": "passed",
            "generation_digest": generation,
        }
        nongate_event, nongate_current = self._transition(
            nongate_prior,
            "gate_recorded",
            {
                "state": "reviewing",
                "steps": {
                    **copy.deepcopy(nongate_prior["steps"]),
                    "assertion-sensor": assertion,
                },
            },
        )
        self.assertFalse(
            builders._merge_transition_valid(
                nongate_event,
                nongate_prior,
                nongate_current,
                context={"required_gate_ids": ("gate-1", "assertion-sensor")},
            )
        )

        package_digest = key("tuple-review-package")
        request_review = {
            "iteration": 1,
            "request": {
                "candidate": self.candidate_head,
                "package": "review/package.txt",
                "package_digest": package_digest,
                "reviewer": "review-final",
                "iteration": 1,
            },
        }
        review = {
            **copy.deepcopy(request_review),
            "verdict": {
                "verdict": "BLOCK",
                "candidate": self.candidate_head,
                "package_digest": package_digest,
                "reviewer_role": "review-final",
                "iteration": 1,
            },
        }
        reviewing = self._state("reviewing")
        blocked_event, blocked_self = self._transition(
            reviewing, "review_attached", {"review": review}
        )
        self.assertFalse(
            builders._merge_transition_valid(
                blocked_event, reviewing, blocked_self, context={}
            )
        )
        requested_event, requested = self._transition(
            reviewing,
            "review_requested",
            {"review": request_review},
        )
        self.assertTrue(
            builders._merge_transition_valid(
                requested_event, reviewing, requested, context={}
            )
        )
        blocked_event, blocked = self._transition(
            requested,
            "review_attached",
            {"state": "revising", "review": review},
        )
        self.assertTrue(
            builders._merge_transition_valid(
                blocked_event, requested, blocked, context={}
            )
        )

        replaced_review = copy.deepcopy(review)
        replaced_review["request"]["package_digest"] = key(
            "replacement-package"
        )
        replaced_review["verdict"]["package_digest"] = replaced_review[
            "request"
        ]["package_digest"]
        replaced_event, replaced_current = self._transition(
            requested,
            "review_attached",
            {"state": "revising", "review": replaced_review},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                replaced_event, requested, replaced_current, context={}
            )
        )

        fabricated_disposition = copy.deepcopy(review)
        fabricated_disposition["dispositions"] = [
            {
                "finding": 1,
                "severity": "MINOR",
                "resolution": "fabricated during attach",
            }
        ]
        fabricated_event, fabricated_current = self._transition(
            requested,
            "review_attached",
            {"state": "revising", "review": fabricated_disposition},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                fabricated_event, requested, fabricated_current, context={}
            )
        )

        pass_review = copy.deepcopy(review)
        pass_review["verdict"]["verdict"] = "PASS"
        missing_authority_event, missing_authority = self._transition(
            requested,
            "review_attached",
            {"state": "authorized", "review": pass_review},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                missing_authority_event,
                requested,
                missing_authority,
                context={},
            )
        )
        authorization = {
            "candidate_head": self.candidate_head,
            "generation_digest": generation,
            "diff_summary": "fixture merge diff",
            "control_paths": [],
            "review_verdict": "PASS",
            "recorded_at": self.NEXT_AT,
        }
        pass_event, authorized = self._transition(
            requested,
            "review_attached",
            {
                "state": "authorized",
                "review": pass_review,
                "authorization": authorization,
            },
        )
        self.assertTrue(
            builders._merge_transition_valid(
                pass_event, requested, authorized, context={}
            )
        )

        capped = copy.deepcopy(reviewing)
        capped["review"] = {
            "iteration": 8,
            "request": {
                **copy.deepcopy(review["request"]),
                "iteration": 8,
            },
            "verdict": {
                **copy.deepcopy(review["verdict"]),
                "iteration": 8,
            },
            "dispositions": [],
        }
        capped_review = copy.deepcopy(capped["review"])
        capped_review["request"]["package"] = "review/retry.txt"
        cap_event, cap_current = self._transition(
            capped, "review_requested", {"review": capped_review}
        )
        self.assertFalse(
            builders._merge_transition_valid(
                cap_event, capped, cap_current, context={}
            )
        )

    def test_refresh_retains_iteration_and_eighth_block_closes_loop(self) -> None:
        package_digest = key("iteration-seven-package")
        prior = self._state("revising")
        prior["review"] = {
            "iteration": 7,
            "request": {
                "candidate": self.candidate_head,
                "package": "review/iteration-07.txt",
                "package_digest": package_digest,
                "reviewer": "review-final",
                "iteration": 7,
            },
            "verdict": {
                "verdict": "BLOCK",
                "candidate": self.candidate_head,
                "package_digest": package_digest,
                "reviewer_role": "review-final",
                "iteration": 7,
                "findings": [{"severity": "MAJOR", "summary": "cycle seven"}],
            },
        }
        integration = copy.deepcopy(prior["integration"])
        integration["intent"] = {
            "operation": "refresh",
            "operation_nonce": "a" * 32,
            "generation_digest": prior["candidate"]["generation_digest"],
        }
        refresh_event, refreshed = self._transition(
            prior,
            "generation_refreshed",
            {
                "state": "verifying",
                "review": {"iteration": 7},
                "integration": integration,
            },
        )
        self.assertTrue(
            builders._merge_transition_valid(
                refresh_event, prior, refreshed, context={}
            )
        )

        reset_event, reset = self._transition(
            prior,
            "generation_refreshed",
            {
                "state": "verifying",
                "review": {},
                "integration": integration,
            },
        )
        self.assertFalse(
            builders._merge_transition_valid(reset_event, prior, reset, context={})
        )

        pending = copy.deepcopy(prior)
        pending["review"]["dispositions"] = [
            {
                "finding": 1,
                "severity": "MAJOR",
                "resolution": "pending operator co-sign",
            }
        ]
        pending["review"]["operator_cosign_required"] = True
        pending_event, pending_current = self._transition(
            pending,
            "generation_refreshed",
            {
                "state": "verifying",
                "review": {"iteration": 7},
                "integration": integration,
            },
        )
        self.assertFalse(
            builders._merge_transition_valid(
                pending_event, pending, pending_current, context={}
            )
        )

        generation = refreshed["candidate"]["generation_digest"]
        gate_one = {
            "criterion": "gate-1: focused tests",
            "result": "passed",
            "generation_digest": generation,
        }
        first_gate, after_first_gate = self._transition(
            refreshed,
            "gate_recorded",
            {"steps": {"gate-1": [gate_one]}},
        )
        self.assertTrue(
            builders._merge_transition_valid(
                first_gate, refreshed, after_first_gate, context={}
            )
        )
        assertion = {
            "criterion": "gate-2: assertion-quality sensor",
            "result": "passed",
            "generation_digest": generation,
        }
        final_gate, reviewing = self._transition(
            after_first_gate,
            "gate_recorded",
            {
                "state": "reviewing",
                "steps": {
                    "gate-1": [gate_one],
                    "assertion-sensor": assertion,
                },
            },
        )
        self.assertTrue(
            builders._merge_transition_valid(
                final_gate,
                after_first_gate,
                reviewing,
                context={"required_gate_ids": ("gate-1", "assertion-sensor")},
            )
        )

        eighth_package = key("iteration-eight-package")
        request = {
            "iteration": 8,
            "request": {
                "candidate": self.candidate_head,
                "package": "review/iteration-08.txt",
                "package_digest": eighth_package,
                "reviewer": "review-final",
                "iteration": 8,
            },
        }
        request_event, requested = self._transition(
            reviewing, "review_requested", {"review": request}
        )
        self.assertTrue(
            builders._merge_transition_valid(
                request_event, reviewing, requested, context={}
            )
        )
        verdict = {
            **copy.deepcopy(request),
            "verdict": {
                "verdict": "BLOCK",
                "candidate": self.candidate_head,
                "package_digest": eighth_package,
                "reviewer_role": "review-final",
                "iteration": 8,
                "findings": [{"severity": "MAJOR", "summary": "cycle eight"}],
            },
        }
        missing_residual_event, missing_residual = self._transition(
            requested,
            "review_attached",
            {"state": "revising", "review": verdict},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                missing_residual_event, requested, missing_residual, context={}
            )
        )
        verdict["residual_risk"] = {
            "at": self.NEXT_AT,
            "reason": "review iteration cap reached",
            "findings": copy.deepcopy(verdict["verdict"]["findings"]),
        }
        capped_event, capped = self._transition(
            requested,
            "review_attached",
            {"state": "revising", "review": verdict},
        )
        self.assertTrue(
            builders._merge_transition_valid(
                capped_event, requested, capped, context={}
            )
        )

        capped_integration = copy.deepcopy(capped["integration"])
        capped_integration["intent"] = {
            "operation": "refresh",
            "operation_nonce": "b" * 32,
            "generation_digest": generation,
        }
        reopen_event, reopened = self._transition(
            capped,
            "generation_refreshed",
            {
                "state": "verifying",
                "review": {"iteration": 8},
                "integration": capped_integration,
            },
        )
        self.assertFalse(
            builders._merge_transition_valid(
                reopen_event, capped, reopened, context={}
            )
        )

    def test_disposition_cosign_and_remote_churn_approval_are_exact(self) -> None:
        prior = self._with_current_merge_authority(self._state("reviewing"))
        prior["review"]["verdict"]["findings"] = [
            {"severity": "MAJOR", "summary": "fixture finding"}
        ]
        generation = prior["candidate"]["generation_digest"]
        disposition = {
            "finding": 1,
            "severity": "MAJOR",
            "resolution": "fixed in the current candidate",
            "candidate": self.candidate_head,
            "generation_digest": generation,
            "recorded_at": self.NEXT_AT,
        }
        review = copy.deepcopy(prior["review"])
        review["dispositions"] = [disposition]
        review["operator_cosign_required"] = True
        event, pending = self._transition(
            prior, "review_disposition", {"review": review}
        )
        self.assertTrue(
            builders._merge_transition_valid(event, prior, pending, context={})
        )
        wrong_severity = copy.deepcopy(pending)
        wrong_severity["review"]["dispositions"][0]["severity"] = "CRITICAL"
        wrong_event = copy.deepcopy(event)
        wrong_event["payload"]["delta"]["review"] = copy.deepcopy(
            wrong_severity["review"]
        )
        self.assertFalse(
            builders._merge_transition_valid(
                wrong_event, prior, wrong_severity, context={}
            )
        )

        cosigned_review = copy.deepcopy(pending["review"])
        cosigned_review["operator_cosign_required"] = False
        cosign = {
            "purpose": "finding-disposition",
            "chain_id": self.CHAIN_ID,
            "finding": 1,
            "resolution": disposition["resolution"],
            "candidate": self.candidate_head,
            "generation_digest": generation,
        }
        cosign_event, cosigned = self._transition(
            pending,
            "approval_recorded",
            {"review": cosigned_review, "approval": cosign},
            at="2026-08-28T12:02:00Z",
        )
        self.assertTrue(
            builders._merge_transition_valid(
                cosign_event, pending, cosigned, context={}
            )
        )
        altered = copy.deepcopy(cosigned)
        altered["review"]["dispositions"][0]["resolution"] = "different"
        altered_event = copy.deepcopy(cosign_event)
        altered_event["payload"]["delta"]["review"] = copy.deepcopy(
            altered["review"]
        )
        self.assertFalse(
            builders._merge_transition_valid(
                altered_event, pending, altered, context={}
            )
        )
        changed_authority = copy.deepcopy(cosigned)
        changed_authority["authorization"] = {}
        changed_event = copy.deepcopy(cosign_event)
        changed_event["payload"]["delta"]["authorization"] = {}
        self.assertFalse(
            builders._merge_transition_valid(
                changed_event, pending, changed_authority, context={}
            )
        )

        churn = self._with_current_merge_authority(
            self._state("awaiting_approval")
        )
        churn["integration"]["condition"] = "remote-churn"
        churn["integration"]["remote_movement_count"] = 8
        churn["approval"] = {}
        acknowledged_integration = copy.deepcopy(churn["integration"])
        acknowledged_integration["condition"] = "none"
        acknowledged_integration["remote_movement_count"] = 0
        acknowledgement = {
            "purpose": "remote-churn",
            "chain_id": self.CHAIN_ID,
            "candidate": self.candidate_head,
            "generation_digest": generation,
        }
        ack_event, acknowledged = self._transition(
            churn,
            "approval_recorded",
            {
                "state": "authorized",
                "approval": acknowledgement,
                "integration": acknowledged_integration,
            },
        )
        self.assertTrue(
            builders._merge_transition_valid(
                ack_event, churn, acknowledged, context={}
            )
        )
        wrong_count = copy.deepcopy(acknowledged)
        wrong_count["integration"]["remote_movement_count"] = 1
        wrong_count_event = copy.deepcopy(ack_event)
        wrong_count_event["payload"]["delta"]["integration"] = copy.deepcopy(
            wrong_count["integration"]
        )
        self.assertFalse(
            builders._merge_transition_valid(
                wrong_count_event, churn, wrong_count, context={}
            )
        )

    def test_bootstrap_and_push_evidence_cannot_be_fabricated(self) -> None:
        bootstrap = self._state(
            "classifying", candidate=False, claim_status="owned"
        )
        failed_integration = copy.deepcopy(bootstrap["integration"])
        assert isinstance(failed_integration, dict)
        failed_integration["condition"] = "fetch-failed"
        fetched, fetched_current = self._transition(
            bootstrap,
            "fetch_result",
            {"state": "verifying", "integration": failed_integration},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                fetched, bootstrap, fetched_current, context={}
            )
        )

        rebasing = self._state("rebasing")
        fabricated_integration = copy.deepcopy(rebasing["integration"])
        assert isinstance(fabricated_integration, dict)
        fabricated_integration["push"] = {
            "expected_old_tip": self.remote_tip,
            "intended_head": self.candidate_head,
            "destination_ref": "refs/heads/main",
            "intended_at": self.NEXT_AT,
            "result": None,
            "attempted_heads": [self.candidate_head],
            "landed_head": None,
        }
        fabricated, fabricated_current = self._transition(
            rebasing,
            "push_intent",
            {"state": "pushing", "integration": fabricated_integration},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                fabricated, rebasing, fabricated_current, context={}
            )
        )

        null_push_prior = self._state("pushing")
        null_push_integration = copy.deepcopy(null_push_prior["integration"])
        assert isinstance(null_push_integration, dict)
        null_push_integration["observed"] = {
            "exists": None,
            "oid": None,
            "contains_intended_head": None,
            "attempted_head_containment": [],
            "observed_at": self.NEXT_AT,
            "inflight_digest": key("null-push-inflight"),
            "output_digest": key("null-push-output"),
        }
        null_event, null_current = self._transition(
            null_push_prior,
            "push_observed",
            {"integration": null_push_integration},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                null_event,
                null_push_prior,
                null_current,
                context=self._push_context(null_event, null_push_prior),
            )
        )

        vector_prior = self._push_state()
        vector_integration = copy.deepcopy(vector_prior["integration"])
        assert isinstance(vector_integration, dict)
        vector_push = vector_integration["push"]
        assert isinstance(vector_push, dict)
        vector_push["landed_head"] = self.candidate_head
        vector_integration["observed"] = {
            "exists": True,
            "oid": self.candidate_head,
            "contains_intended_head": True,
            "attempted_head_containment": [
                {"head": self.candidate_head, "contained": False}
            ],
            "observed_at": self.NEXT_AT,
            "inflight_digest": key("vector-inflight"),
            "output_digest": key("vector-output"),
        }
        vector_event, vector_current = self._transition(
            vector_prior,
            "push_observed",
            {"state": "pushed", "integration": vector_integration},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                vector_event,
                vector_prior,
                vector_current,
                context=self._push_context(vector_event, vector_prior),
            )
        )

    def test_push_observation_phase_and_classification_are_context_bound(self) -> None:
        prior = self._state("rebasing")
        generation = prior["candidate"]["generation_digest"]
        epoch_digest = key("first-final-prepush-epoch")
        prior["integration"]["epoch"] = {
            "operation_nonce": "c" * 32,
            "generation_digest": generation,
            "intent_digest": epoch_digest,
            "started_at": self.BASE_AT,
        }
        prior["integration"]["observed"] = {
            "exists": True,
            "oid": self.remote_tip,
            "contains_intended_head": False,
            "attempted_head_containment": [],
            "observed_at": self.BASE_AT,
            "inflight_digest": key("push-preseed-final-observation-inflight"),
            "output_digest": key("push-preseed-final-observation-output"),
        }
        integration = copy.deepcopy(prior["integration"])
        integration["intent"] = {
            "schema": "forge-remote-observation-intent/1",
            "transaction": "merge",
            "chain_id": self.CHAIN_ID,
            "attempt_identity": epoch_digest,
            "phase": "final-prepush",
            "push_intent_digest": None,
        }
        integration["observed"] = {
            "exists": True,
            "oid": self.remote_tip,
            "contains_intended_head": False,
            "attempted_head_containment": [],
            "observed_at": self.NEXT_AT,
            "inflight_digest": key("first-final-prepush-inflight"),
            "output_digest": key("first-final-prepush-output"),
        }
        event, current = self._transition(
            prior, "push_observed", {"integration": integration}
        )
        context = {
            "epoch_intent": {
                "digest": epoch_digest,
                "generation_digest": generation,
                "push_consumed": False,
            }
        }
        self.assertTrue(
            builders._merge_transition_valid(
                event, prior, current, context=copy.deepcopy(context)
            )
        )

        historical = self._push_state()
        historical["state"] = "reverifying"
        historical_epoch = key("historical-final-prepush-epoch")
        historical["integration"]["epoch"].update(
            {
                "operation_nonce": "d" * 32,
                "intent_digest": historical_epoch,
            }
        )
        historical_current_integration = copy.deepcopy(historical["integration"])
        historical_current_integration["intent"] = {
            "schema": "forge-remote-observation-intent/1",
            "transaction": "merge",
            "chain_id": self.CHAIN_ID,
            "attempt_identity": historical_epoch,
            "phase": "final-prepush",
            "push_intent_digest": None,
        }
        historical_current_integration["observed"] = {
            "exists": True,
            "oid": self.remote_tip,
            "contains_intended_head": False,
            "attempted_head_containment": [
                {"head": self.candidate_head, "contained": False}
            ],
            "observed_at": self.NEXT_AT,
            "inflight_digest": key("historical-final-prepush-inflight"),
            "output_digest": key("historical-final-prepush-output"),
        }
        historical_event, historical_current = self._transition(
            historical,
            "push_observed",
            {"integration": historical_current_integration},
        )
        historical_context = {
            "epoch_intent": {
                "digest": historical_epoch,
                "generation_digest": generation,
                "push_consumed": False,
            }
        }
        self.assertTrue(
            builders._merge_transition_valid(
                historical_event,
                historical,
                historical_current,
                context=copy.deepcopy(historical_context),
            )
        )
        wrong_attempt = copy.deepcopy(historical_current)
        wrong_attempt["integration"]["intent"]["attempt_identity"] = key(
            "wrong-final-prepush-attempt"
        )
        wrong_attempt_event = copy.deepcopy(historical_event)
        wrong_attempt_event["payload"]["delta"]["integration"] = copy.deepcopy(
            wrong_attempt["integration"]
        )
        self.assertFalse(
            builders._merge_transition_valid(
                wrong_attempt_event,
                historical,
                wrong_attempt,
                context=copy.deepcopy(historical_context),
            )
        )

        landed_prior, landed_event, landed_current = self._push_observed(
            bound=False, landed=True
        )
        landed_current["integration"]["condition"] = "push-outcome-unknown"
        landed_event["payload"]["delta"]["integration"] = copy.deepcopy(
            landed_current["integration"]
        )
        self.assertFalse(
            builders._merge_transition_valid(
                landed_event,
                landed_prior,
                landed_current,
                context=self._push_context(landed_event, landed_prior),
            )
        )

        inactive_prior, inactive_event, inactive_current = self._push_observed(
            bound=False, landed=False
        )
        inactive_prior["inactive_after"] = "2026-08-28T12:00:30Z"
        inactive_current["inactive_after"] = inactive_prior["inactive_after"]
        inactive_current["integration"]["condition"] = "remote-churn"
        inactive_current["integration"]["remote_movement_count"] = 8
        inactive_event["payload"]["delta"]["integration"] = copy.deepcopy(
            inactive_current["integration"]
        )
        self.assertFalse(
            builders._merge_transition_valid(
                inactive_event,
                inactive_prior,
                inactive_current,
                context=self._push_context(inactive_event, inactive_prior),
            )
        )
        retained_prior = copy.deepcopy(inactive_prior)
        retained_prior["integration"]["push"]["result"] = copy.deepcopy(
            inactive_current["integration"]["push"]["result"]
        )
        retained_prior["integration"]["condition"] = "push-failed"
        for fabricated_condition in ("remote-moved", "non-fast-forward"):
            fabricated_current = copy.deepcopy(inactive_current)
            fabricated_current["integration"]["condition"] = fabricated_condition
            fabricated_current["integration"]["remote_movement_count"] = 0
            fabricated_event = copy.deepcopy(inactive_event)
            fabricated_event["payload"]["delta"]["integration"] = copy.deepcopy(
                fabricated_current["integration"]
            )
            with self.subTest(inactive_condition=fabricated_condition):
                self.assertFalse(
                    builders._merge_transition_valid(
                        fabricated_event,
                        retained_prior,
                        fabricated_current,
                        context=self._push_context(
                            fabricated_event, retained_prior
                        ),
                    )
                )

    def test_push_intent_cannot_preseed_landing_and_repeated_oid_lands_once(self) -> None:
        prior = self._with_current_merge_authority(
            self._state("rebasing", bound=True)
        )
        candidate = prior["candidate"]
        generation = candidate["generation_digest"]
        epoch_digest = key("push-preseed-epoch")
        prior["integration"]["epoch"] = {
            "operation_nonce": "e" * 32,
            "generation_digest": generation,
            "intent_digest": epoch_digest,
            "started_at": self.BASE_AT,
        }
        prior["integration"]["observed"] = {
            "exists": True,
            "oid": self.remote_tip,
            "contains_intended_head": False,
            "attempted_head_containment": [],
            "observed_at": self.BASE_AT,
            "inflight_digest": key("push-preseed-final-observation-inflight"),
            "output_digest": key("push-preseed-final-observation-output"),
        }
        integration = copy.deepcopy(prior["integration"])
        integration["intent"] = {
            "operation": "push",
            "operation_nonce": "e" * 32,
        }
        integration["push"] = {
            "expected_old_tip": self.remote_tip,
            "intended_head": self.candidate_head,
            "destination_ref": "refs/heads/main",
            "intended_at": self.NEXT_AT,
            "result": None,
            "attempted_heads": [self.candidate_head],
            "landed_head": None,
        }
        integration["observed"] = None
        intent_event, pushing = self._transition(
            prior,
            "push_intent",
            {"state": "pushing", "integration": integration},
        )
        intent_context = {
            "required_gate_ids": ("gate-1", "assertion-sensor"),
            "epoch_intent": {
                "digest": epoch_digest,
                "generation_digest": generation,
                "push_consumed": False,
            }
        }
        self.assertTrue(
            builders._merge_transition_valid(
                intent_event,
                prior,
                pushing,
                context=copy.deepcopy(intent_context),
            )
        )
        preseeded = copy.deepcopy(pushing)
        preseeded["integration"]["push"]["landed_head"] = self.candidate_head
        preseed_event = copy.deepcopy(intent_event)
        preseed_event["payload"]["delta"]["integration"] = copy.deepcopy(
            preseeded["integration"]
        )
        self.assertFalse(
            builders._merge_transition_valid(
                preseed_event,
                prior,
                preseeded,
                context=copy.deepcopy(intent_context),
            )
        )

        repeated_prior = copy.deepcopy(pushing)
        repeated_push = repeated_prior["integration"]["push"]
        repeated_push["attempted_heads"] = [
            self.candidate_head,
            self.candidate_head,
        ]
        repeated_push["landed_head"] = self.candidate_head
        repeated_integration = copy.deepcopy(repeated_prior["integration"])
        repeated_integration["intent"] = {
            "schema": "forge-remote-observation-intent/1",
            "transaction": "merge",
            "chain_id": self.CHAIN_ID,
            "attempt_identity": epoch_digest,
            "phase": "post-push",
            "push_intent_digest": key("repeated-push-intent"),
        }
        repeated_integration["push"]["result"] = {
            "classification": "success",
            "exit": 0,
            "inflight_digest": key("repeated-push-inflight"),
            "output_digest": key("repeated-push-output"),
            "launch_failed": False,
            "timed_out": False,
            "output_limit_exceeded": False,
            "recorded_at": self.NEXT_AT,
        }
        repeated_integration["observed"] = {
            "exists": True,
            "oid": self.candidate_head,
            "contains_intended_head": True,
            "attempted_head_containment": [
                {"head": self.candidate_head, "contained": True},
                {"head": self.candidate_head, "contained": True},
            ],
            "observed_at": self.NEXT_AT,
            "inflight_digest": key("repeated-observation-inflight"),
            "output_digest": key("repeated-observation-output"),
        }
        repeated_event, repeated_current = self._transition(
            repeated_prior,
            "push_observed",
            {"state": "pushed", "integration": repeated_integration},
        )
        repeated_event["previous_digest"] = key("repeated-push-intent")
        repeated_context = {
            "epoch_intent": {
                "digest": epoch_digest,
                "generation_digest": generation,
                "push_consumed": True,
            },
            "push_intent": {
                "digest": repeated_event["previous_digest"],
                "generation_digest": generation,
                "evidence": {"operation": "push", "operation_nonce": "e" * 32},
                "admitted_active": True,
            },
        }
        self.assertFalse(
            builders._merge_transition_valid(
                repeated_event,
                repeated_prior,
                repeated_current,
                context=copy.deepcopy(repeated_context),
            )
        )
        source_digest = key("repeated-landing-source")
        record = {"type": "decision", "outcome": "chain-landing"}
        batch = {
            "idempotency_key": source_digest,
            "batch_digest": key("repeated-landing-batch"),
            "record_count": 1,
            "records": [record],
        }
        repeated_event["payload"].update(
            {"source_event_digest": source_digest, "journal_batch": batch}
        )
        repeated_current["journal_outbox"] = {
            "idempotency_key": source_digest,
            "batch_digest": batch["batch_digest"],
            "record_count": 1,
            "source_event_digest": source_digest,
        }
        self.assertTrue(
            builders._merge_transition_valid(
                repeated_event,
                repeated_prior,
                repeated_current,
                context=copy.deepcopy(repeated_context),
            )
        )

    def test_claim_release_and_terminal_links_are_replay_context_bound(self) -> None:
        context: dict[str, object] = {}
        prior = self._state(
            "classifying", candidate=True, claim_status="unpublished"
        )
        identity = {
            "path": self.worktree_path,
            "git_dir": self.git_dir,
            "common_dir": self.common_dir,
        }
        intended_digest = builders._merge_claim_record_digest(prior, identity)
        self.assertIsInstance(intended_digest, str)
        intent_payload = {
            "worktree_digest": journal._sha256(
                journal._canonical_json_bytes(identity)
            ),
            "claim_path": self.claim_path,
            "intended_claim_digest": intended_digest,
            "predecessor_chain_id": None,
            "predecessor_release_digest": None,
        }
        intent, intended = self._transition(
            prior,
            "ownership_intent",
            {},
            payload=intent_payload,
            digest=key("ownership-intent-event"),
        )
        intended["worktree"]["claim"].update(
            {"status": "unpublished", "inode": None, "digest": intended_digest}
        )
        forged_intent = copy.deepcopy(intent)
        forged_intent["payload"]["intended_claim_digest"] = key(
            "synthetic-claim-record"
        )
        forged_intended = copy.deepcopy(intended)
        forged_intended["worktree"]["claim"]["digest"] = forged_intent[
            "payload"
        ]["intended_claim_digest"]
        self.assertFalse(
            builders._merge_transition_valid(
                forged_intent, prior, forged_intended, context={}
            )
        )
        self.assertTrue(
            builders._merge_transition_valid(intent, prior, intended, context=context)
        )
        extra_payload = copy.deepcopy(intent)
        extra_payload["payload"]["delta"] = {
            "worktree": copy.deepcopy(intended["worktree"])
        }
        self.assertFalse(
            builders._merge_transition_valid(
                extra_payload, prior, intended, context={}
            )
        )
        retargeted = copy.deepcopy(intent)
        retargeted["previous_digest"] = str(intent["digest"])
        retargeted["payload"]["predecessor_chain_id"] = (
            "c-2026-08-28T115900Z-beef"
        )
        retargeted["payload"]["predecessor_release_digest"] = key(
            "retargeted-predecessor"
        )
        retargeted["digest"] = key("second-ownership-intent")
        self.assertFalse(
            builders._merge_transition_valid(
                retargeted, intended, copy.deepcopy(intended), context=context
            )
        )

        claimed_digest = intended_digest
        claimed_payload = {
            "ownership_intent_digest": intent["digest"],
            "claim_inode": 17,
            "claim_digest": claimed_digest,
            "predecessor_chain_id": None,
            "predecessor_release_digest": None,
        }
        claimed_event, claimed = self._transition(
            intended,
            "ownership_claimed",
            {},
            at="2026-08-28T12:02:00Z",
            payload=claimed_payload,
            previous_digest=str(intent["digest"]),
            digest=key("ownership-claimed-event"),
        )
        claimed["worktree"]["claim"].update(
            {"status": "owned", "inode": 17, "digest": claimed_digest}
        )
        mismatched_digest_event = copy.deepcopy(claimed_event)
        mismatched_digest_current = copy.deepcopy(claimed)
        mismatched_digest = key("claimed-record-mismatch")
        mismatched_digest_event["payload"]["claim_digest"] = mismatched_digest
        mismatched_digest_current["worktree"]["claim"]["digest"] = mismatched_digest
        self.assertFalse(
            builders._merge_transition_valid(
                mismatched_digest_event,
                intended,
                mismatched_digest_current,
                context=copy.deepcopy(context),
            )
        )
        bad_claim_event = copy.deepcopy(claimed_event)
        bad_claim_event["previous_digest"] = key("wrong-intent-link")
        bad_claim_event["payload"]["ownership_intent_digest"] = key(
            "wrong-intent-link"
        )
        self.assertFalse(
            builders._merge_transition_valid(
                bad_claim_event, intended, claimed, context=copy.deepcopy(context)
            )
        )
        self.assertTrue(
            builders._merge_transition_valid(
                claimed_event, intended, claimed, context=context
            )
        )

        release_payload = {
            "target_terminal": "aborted",
            "terminal_disposition": "ordinary",
            "source_state": "classifying",
            "terminal_preconditions_digest": key("terminal-preconditions"),
            "release_mode": "acquired",
        }
        release_intent, releasing = self._transition(
            claimed,
            "ownership_release_intent",
            {},
            at="2026-08-28T12:03:00Z",
            payload=release_payload,
            previous_digest=str(claimed_event["digest"]),
            digest=key("release-intent-event"),
        )
        releasing["worktree"]["claim"]["status"] = "releasing"
        self.assertTrue(
            builders._merge_transition_valid(
                release_intent, claimed, releasing, context=context
            )
        )
        interposed_integration = copy.deepcopy(releasing["integration"])
        interposed_integration["condition"] = "foreign-git-state"
        interposed_event, interposed = self._transition(
            releasing,
            "condition_recorded",
            {"integration": interposed_integration},
            at="2026-08-28T12:03:30Z",
        )
        self.assertFalse(
            builders._merge_transition_valid(
                interposed_event,
                releasing,
                interposed,
                context=copy.deepcopy(context),
            )
        )

        released_payload = {
            "release_intent_digest": release_intent["digest"],
            "release_mode": "acquired",
            "terminal_disposition": "ordinary",
            "claim_inode": 17,
            "claim_digest": claimed_digest,
            "claim_observation_digest": journal._sha256(
                journal._canonical_json_bytes(
                    {
                        "claim_path": self.claim_path,
                        "exists": True,
                        "inode": 17,
                        "digest": claimed_digest,
                    }
                )
            ),
        }
        released_event, released = self._transition(
            releasing,
            "ownership_released",
            {},
            at="2026-08-28T12:04:00Z",
            payload=released_payload,
            previous_digest=str(release_intent["digest"]),
            digest=key("released-event"),
        )
        released["worktree"]["claim"]["status"] = "released"
        bad_release = copy.deepcopy(released_event)
        bad_release["payload"]["release_intent_digest"] = key("wrong-release")
        self.assertFalse(
            builders._merge_transition_valid(
                bad_release, releasing, released, context=copy.deepcopy(context)
            )
        )
        wrong_observation = copy.deepcopy(released_event)
        wrong_observation["payload"]["claim_observation_digest"] = key(
            "wrong-claim-observation-preimage"
        )
        self.assertFalse(
            builders._merge_transition_valid(
                wrong_observation,
                releasing,
                released,
                context=copy.deepcopy(context),
            )
        )
        self.assertTrue(
            builders._merge_transition_valid(
                released_event, releasing, released, context=context
            )
        )

        terminal_event, terminal = self._transition(
            released,
            "aborted",
            {"state": "aborted"},
            at="2026-08-28T12:05:00Z",
            previous_digest=str(released_event["digest"]),
        )
        wrong_terminal = copy.deepcopy(terminal_event)
        wrong_terminal["previous_digest"] = key("wrong-release-result")
        self.assertFalse(
            builders._merge_transition_valid(
                wrong_terminal, released, terminal, context=copy.deepcopy(context)
            )
        )
        wrong_target_context = copy.deepcopy(context)
        wrong_target_context["release_intent"]["payload"]["target_terminal"] = "closed"
        self.assertFalse(
            builders._merge_transition_valid(
                terminal_event, released, terminal, context=wrong_target_context
            )
        )
        self.assertTrue(
            builders._merge_transition_valid(
                terminal_event, released, terminal, context=context
            )
        )

    def test_slot_lineage_rejects_missing_cycle_fork_and_snapshot_substitution(self) -> None:
        predecessor_id = "c-2026-08-28T115900Z-beef"
        sibling_id = "c-2026-08-28T120100Z-acde"
        release_digest = key("predecessor-release")
        current_state = self._state("classifying", claim_status="owned")
        identity = {
            name: current_state["worktree"][name]
            for name in ("path", "git_dir", "common_dir")
        }

        def summary(
            selected: str,
            *,
            predecessor: str | None,
            predecessor_digest: str | None,
            terminal: bool,
            released: str | None,
        ) -> dict[str, object]:
            raw = f"events:{selected}".encode("utf-8")
            state_snapshot = {"chain": selected}
            return {
                "family": "merge",
                "chain_id": selected,
                "identity": copy.deepcopy(identity),
                "claim_status": "released" if terminal else "owned",
                "predecessor_chain_id": predecessor,
                "predecessor_release_digest": predecessor_digest,
                "acquired": True,
                "released_digest": released,
                "terminal": terminal,
                "snapshot_event_digest": journal._sha256(raw),
                "snapshot_state": state_snapshot,
            }

        base = {
            predecessor_id: summary(
                predecessor_id,
                predecessor=None,
                predecessor_digest=None,
                terminal=True,
                released=release_digest,
            ),
            self.CHAIN_ID: summary(
                self.CHAIN_ID,
                predecessor=predecessor_id,
                predecessor_digest=release_digest,
                terminal=False,
                released=None,
            ),
        }

        def exercise(
            selected: dict[str, dict[str, object]],
            *,
            substituted: str | None = None,
            listed_names: list[str] | None = None,
        ) -> None:
            names = (
                [f"{name}.json" for name in selected]
                if listed_names is None
                else listed_names
            )

            def replay(*args: object, **_kwargs: object) -> dict[str, object]:
                selected_id = str(args[2])
                if selected_id not in selected:
                    raise journal.CoordinationRefusal(
                        "forge: binding chain replay failed"
                    )
                return copy.deepcopy(selected[selected_id])

            def read_events(_descriptor: int, name: str) -> bytes:
                selected_id = name.removesuffix(".events.jsonl")
                suffix = ":changed" if selected_id == substituted else ""
                return f"events:{selected_id}{suffix}".encode("utf-8")

            def read_state(_descriptor: int, name: str) -> object:
                selected_id = name.removesuffix(".json")
                return {"chain": selected_id}

            with mock.patch.object(builders.os, "listdir", return_value=names), mock.patch.object(
                builders, "_resolve_binding_from_descriptor", side_effect=replay
            ), mock.patch.object(
                builders, "_read_regular_bytes_at", side_effect=read_events
            ), mock.patch.object(builders, "_read_json_at", side_effect=read_state):
                builders._validate_merge_slot_lineage(
                    Path(self.repository), 17, self.CHAIN_ID, current_state
                )

        exercise(base)

        missing = copy.deepcopy(base)
        missing[self.CHAIN_ID]["predecessor_release_digest"] = key("missing-edge")
        with self.assertRaises(journal.CoordinationRefusal):
            exercise(missing)

        cycle = copy.deepcopy(base)
        cycle[predecessor_id]["predecessor_chain_id"] = self.CHAIN_ID
        cycle[predecessor_id]["predecessor_release_digest"] = key("cycle-edge")
        with self.assertRaises(journal.CoordinationRefusal):
            exercise(cycle)

        fork = copy.deepcopy(base)
        fork[sibling_id] = summary(
            sibling_id,
            predecessor=predecessor_id,
            predecessor_digest=release_digest,
            terminal=False,
            released=None,
        )
        with self.assertRaises(journal.CoordinationRefusal):
            exercise(fork)

        terminal_fork = copy.deepcopy(base)
        terminal_fork[self.CHAIN_ID].update(
            {
                "terminal": True,
                "claim_status": "released",
                "released_digest": key("current-release"),
            }
        )
        terminal_fork[sibling_id] = summary(
            sibling_id,
            predecessor=predecessor_id,
            predecessor_digest=release_digest,
            terminal=True,
            released=key("sibling-release"),
        )
        with self.assertRaises(journal.CoordinationRefusal):
            exercise(terminal_fork)

        event_only_names = [
            *(f"{name}.json" for name in base),
            f"{sibling_id}.events.jsonl",
        ]
        with self.assertRaises(journal.CoordinationRefusal):
            exercise(base, listed_names=event_only_names)

        with self.assertRaises(journal.CoordinationRefusal):
            exercise(base, substituted=predecessor_id)

    def test_condition_cleanup_and_inactive_results_require_exact_evidence(self) -> None:
        prior = self._state("authorized")
        moved = copy.deepcopy(prior["integration"])
        assert isinstance(moved, dict)
        moved["condition"] = "remote-moved"
        condition_event, condition_current = self._transition(
            prior,
            "condition_recorded",
            {"state": "awaiting_approval", "integration": moved},
        )
        self.assertFalse(
            builders._merge_transition_valid(
                condition_event, prior, condition_current, context={}
            )
        )

        cleanup_prior = self._state("pushed")
        cleanup_prior["cleanup"] = {
            "condition": "none",
            "operation_nonce": "b" * 32,
        }
        cleanup = copy.deepcopy(cleanup_prior["cleanup"])
        cleanup["condition"] = "cleanup-failed"
        cleanup_event, cleanup_current = self._transition(
            cleanup_prior, "cleanup_result", {"cleanup": cleanup}
        )
        cleanup_context = {
            "cleanup_intent": {
                "digest": key("cleanup-intent"),
                "generation_digest": cleanup_event["generation_digest"],
                "evidence": copy.deepcopy(cleanup_prior["cleanup"]),
                "admitted_active": True,
            }
        }
        cleanup_context["cleanup_intent"]["digest"] = cleanup_event[
            "previous_digest"
        ]
        self.assertFalse(
            builders._merge_transition_valid(
                cleanup_event,
                cleanup_prior,
                cleanup_current,
                context=cleanup_context,
            )
        )

        inactive = self._state(
            "rebasing",
            at="2026-08-28T12:00:00Z",
            inactive_after="2026-08-28T12:30:00Z",
        )
        failed = copy.deepcopy(inactive["integration"])
        assert isinstance(failed, dict)
        failed["condition"] = "fetch-failed"
        result_event, result_current = self._transition(
            inactive,
            "fetch_result",
            {"state": "authorized", "integration": failed},
            at="2026-08-28T13:00:00Z",
        )
        self.assertFalse(
            builders._merge_transition_valid(
                result_event, inactive, result_current, context={}
            )
        )

    def test_outbox_is_required_iff_an_ordinary_record_is_derived(self) -> None:
        _, nonlanding, nonlanding_current = self._push_observed(
            bound=True, landed=False
        )
        nonlanding_prior = self._push_state(bound=True)
        self.assertTrue(
            builders._merge_transition_valid(
                nonlanding,
                nonlanding_prior,
                nonlanding_current,
                context=self._push_context(nonlanding, nonlanding_prior),
            )
        )

        landing_prior, landing_without_batch, landing_current = self._push_observed(
            bound=True, landed=True
        )
        self.assertFalse(
            builders._merge_transition_valid(
                landing_without_batch,
                landing_prior,
                landing_current,
                context=self._push_context(
                    landing_without_batch, landing_prior
                ),
            )
        )
        landing_prior, landing_with_batch, pending = self._push_observed(
            bound=True, landed=True, with_batch=True
        )
        self.assertTrue(
            builders._merge_transition_valid(
                landing_with_batch,
                landing_prior,
                pending,
                context=self._push_context(landing_with_batch, landing_prior),
            )
        )

        unbound_prior, unbound_landing, unbound_current = self._push_observed(
            bound=False, landed=True
        )
        self.assertTrue(
            builders._merge_transition_valid(
                unbound_landing,
                unbound_prior,
                unbound_current,
                context=self._push_context(unbound_landing, unbound_prior),
            )
        )

        receipt_current = copy.deepcopy(pending)
        receipt_current["journal_outbox"] = None
        receipt_current["last_event_at"] = "2026-08-28T12:02:00Z"
        receipt_current["inactive_after"] = "2026-08-29T12:02:00Z"
        pending_outbox = pending["journal_outbox"]
        assert isinstance(pending_outbox, dict)
        receipt_event = {
            "schema": "forge-merge-event/1",
            "chain_id": self.CHAIN_ID,
            "sequence": 3,
            "at": receipt_current["last_event_at"],
            "event": "journal_receipted",
            "generation_digest": receipt_current["candidate"]["generation_digest"],
            "previous_digest": landing_with_batch["digest"],
            "payload": {
                "idempotency_key": pending_outbox["idempotency_key"],
                "batch_digest": pending_outbox["batch_digest"],
                "receipt_digest": key("merge-receipt"),
            },
            "digest": key("merge-receipted-event"),
        }
        receipt_context = self._push_context(
            landing_with_batch, landing_prior
        )
        self.assertTrue(
            builders._merge_transition_valid(
                receipt_event,
                pending,
                receipt_current,
                context=copy.deepcopy(receipt_context),
            )
        )

        no_pending = copy.deepcopy(pending)
        no_pending["journal_outbox"] = None
        no_pending_receipt_current = copy.deepcopy(receipt_current)
        self.assertFalse(
            builders._merge_transition_valid(
                receipt_event,
                no_pending,
                no_pending_receipt_current,
                context=copy.deepcopy(receipt_context),
            )
        )

        blocked_integration = copy.deepcopy(pending["integration"])
        assert isinstance(blocked_integration, dict)
        blocked_integration["condition"] = "lock-release-failed"
        blocked_event, blocked_current = self._transition(
            pending,
            "lock_release_result",
            {"integration": blocked_integration},
            at="2026-08-28T12:02:00Z",
        )
        self.assertFalse(
            builders._merge_transition_valid(
                blocked_event, pending, blocked_current, context={}
            )
        )

    def test_fractional_deadline_is_sticky_and_never_rearmed(self) -> None:
        active = self._state(
            "reviewing",
            at="2026-08-28T12:00:00.100000Z",
            inactive_after="2026-08-29T12:00:00.100000Z",
        )
        active_event, active_current = self._transition(
            active,
            "review_requested",
            {
                "review": {
                    "iteration": 1,
                    "request": {
                        "candidate": self.candidate_head,
                        "package": "review/package.txt",
                        "package_digest": key("fractional-review-package"),
                        "reviewer": "review-final",
                        "iteration": 1,
                    },
                }
            },
            at="2026-08-28T12:00:01.654321Z",
        )
        self.assertEqual(
            active_current["inactive_after"],
            "2026-08-29T12:00:01.654321Z",
        )
        self.assertTrue(
            builders._merge_transition_valid(
                active_event, active, active_current, context={}
            )
        )

        prior = self._state(
            "authorized",
            at="2026-08-29T11:59:59.999999Z",
            inactive_after="2026-08-29T12:00:00.123456Z",
        )
        integration = copy.deepcopy(prior["integration"])
        assert isinstance(integration, dict)
        integration["condition"] = "lock-release-failed"
        event, current = self._transition(
            prior,
            "lock_release_result",
            {"integration": integration},
            at="2026-08-29T12:00:00.500000Z",
        )
        self.assertEqual(current["inactive_after"], "2026-08-29T12:00:00.123456Z")
        self.assertTrue(
            builders._merge_transition_valid(event, prior, current, context={})
        )

        rearmed = copy.deepcopy(current)
        rearmed["inactive_after"] = "2026-08-30T12:00:00.500000Z"
        self.assertFalse(
            builders._merge_transition_valid(event, prior, rearmed, context={})
        )


if __name__ == "__main__":
    unittest.main()
