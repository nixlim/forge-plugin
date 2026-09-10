from __future__ import annotations

import base64
import copy
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager, nullcontext, redirect_stderr
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "scripts/codex_orch_tools.py"
FIXTURES = ROOT / "tests/fixtures"
PREFIX_WEDGE_FIXTURE = ROOT / "tests/_fixtures/prefix-wedge-d77d997"
UNREPLAYABLE_CHAIN_ID = "c-2026-08-21T223925Z-1490"
UNREPLAYABLE_CHAIN_FIXTURE = (
    ROOT / "tests/_fixtures/unreplayable-chain-1490"
)

sys.path.insert(0, str(ROOT / "scripts"))
from codex_orchestrator import batch, builders, journal  # noqa: E402


JOURNAL_FIXTURE_SHA256 = (
    "dd0695b47a37506a10efa9f7889855ada36e7cf9d09fdfdae284c57b049eed86"
)
OUTPUT_FIXTURE_SHA256 = (
    "41e563086b48340bb03f35734b6469551d9aab26efe14f12d38f88aebda3aa60"
)
PREFIX_WEDGE_FIXTURE_SHA256 = {
    "intent.json": "0f3f28e6bfaba51a172ca4dc6a54d52bcb18dc5578e1929a8a1cb907a8afc42f",
    "journal.jsonl": "c7a2e5fb6c56d1ba4e47e968d061a28a3b6fb4b7079d8571402bd1bd4ef73e58",
    "owner.txt": "e0766d0114f351c944033ff4d0025cceed6b6ba7a33ede13be40239bbfeee284",
    "receipts.jsonl": "bcbb1b44db79cfa604fb520def49c4dd80b50d82af6f78ea69dcae799fc4aae7",
    "registry.json": "d92f7d6301da5f0aa5adbc54ca13dc726ee258f758fb798e3d6879bd721f1e25",
}
UNREPLAYABLE_CHAIN_FIXTURE_SHA256 = {
    f"{UNREPLAYABLE_CHAIN_ID}.events.jsonl": (
        "7563e6cdeca3f2218a288c70520e15136db38e9648cae462ffab0259b8c471f3"
    ),
    f"{UNREPLAYABLE_CHAIN_ID}.json": (
        "db0fae7dd4337fb36e14a50b833a48ba0ed5ff19bc93c6adac21a0e60e87658f"
    ),
}


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
        journal_path = self.run_dir / "journal.jsonl"
        self.records = [
            json.loads(line)
            for line in journal_path.read_text(encoding="utf-8").splitlines()
        ]
        self._localize_absolute_evidence(journal_path)
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

    def _localize_absolute_evidence(self, journal_path: Path) -> None:
        journal_text = journal_path.read_text(encoding="utf-8")
        localized = 0
        for record in self.records:
            if record.get("type") != "verification":
                continue
            evidence = record.get("evidence")
            if not isinstance(evidence, list):
                continue
            for index, value in enumerate(evidence):
                if not isinstance(value, str) or not Path(value).is_absolute():
                    continue
                relative = (
                    f"fixture-present-evidence/{record['id']}-{index}"
                    f"{Path(value).suffix}"
                )
                source = json.dumps(value)
                replacement = json.dumps(relative)
                if journal_text.count(source) != 1:
                    raise AssertionError(
                        f"absolute fixture evidence path is not unique: {value}"
                    )
                journal_text = journal_text.replace(source, replacement)
                evidence[index] = relative
                self._materialize(relative)
                localized += 1
        if localized != 3:
            raise AssertionError(
                f"expected three absolute fixture evidence paths, found {localized}"
            )
        journal_path.write_text(journal_text, encoding="utf-8")

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

    def test_activated_scope_readmission_uses_typed_builder(self) -> None:
        run_id = "run-20260831-activated-readmit"
        with self.api_environment():
            self.open_run(self.repo, run_id)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                "activated writer requires typed builder",
            ):
                journal.readmit_run(self.repo, run_id, ["src/**"])

            readmission = builders.scope_change(
                self.repo,
                run_id,
                idempotency_key=key("activated-readmit-api"),
                scope=["src/**", "tests/**"],
            )
            self.assertIsInstance(readmission, batch.BatchOutcome)
            self.assertFalse(readmission.repeated)
            repeated = builders.scope_change(
                self.repo,
                run_id,
                idempotency_key=key("activated-readmit-api"),
                scope=["src/**", "tests/**"],
            )
            self.assertIsInstance(repeated, batch.BatchOutcome)
            self.assertTrue(repeated.repeated)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                "idempotency key already names different content",
            ):
                builders.scope_change(
                    self.repo,
                    run_id,
                    idempotency_key=key("activated-readmit-api"),
                    scope=["docs/**", "src/**", "tests/**"],
                )
            state = journal._scan_run(self.run_dir(self.repo, run_id))
            self.assertEqual(state.scope, ("src/**", "tests/**"))
            self.assertEqual(
                state.records[-1]["resolution"], journal.READMISSION_RESOLUTION
            )

            public = self.command(
                "run-readmit",
                "--repo",
                str(self.repo),
                "--run-id",
                run_id,
                "--idempotency-key",
                key("activated-readmit-cli"),
                "--scope",
                "docs/**",
                "--scope",
                "src/**",
                "--scope",
                "tests/**",
            )
            self.assertEqual(public.returncode, 0, public.stderr)
            state = journal._scan_run(self.run_dir(self.repo, run_id))
            self.assertEqual(state.scope, ("docs/**", "src/**", "tests/**"))

            before = (self.run_dir(self.repo, run_id) / "journal.jsonl").read_bytes()
            with mock.patch.object(
                builders,
                "BUILDER_VALIDATION_CONTROLS",
                builders.BUILDER_VALIDATION_CONTROLS - {"scope-change"},
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal, "scope-change control is unavailable"
            ):
                builders.scope_change(
                    self.repo,
                    run_id,
                    idempotency_key=key("activated-readmit-disabled"),
                    scope=["docs/**", "src/**", "tests/**", "tools/**"],
                )
            self.assertEqual(
                (self.run_dir(self.repo, run_id) / "journal.jsonl").read_bytes(),
                before,
            )

    def test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume(self) -> None:
        run_id = "run-20260831-readmit-receipts"
        with self.api_environment():
            self.open_run(self.repo, run_id)
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key("readmit-sequence-task-1"),
                task="task-01",
                goal="Establish the initial admitted task",
                acceptance=["The task is receipted"],
                files=["src/example.py"],
            )
            readmitted = self.command(
                "run-readmit",
                "--repo",
                str(self.repo),
                "--run-id",
                run_id,
                "--idempotency-key",
                key("readmit-sequence-scope"),
                "--scope",
                "src/**",
                "--scope",
                "tests/**",
            )
            self.assertEqual(readmitted.returncode, 0, readmitted.stderr)
            self.assertEqual(
                json.loads(readmitted.stdout)["records"][0]["resolution"],
                journal.READMISSION_RESOLUTION,
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key("readmit-sequence-task-2"),
                task="task-02",
                goal="Use the widened scope",
                acceptance=["The second task is receipted"],
                files=["tests/test_example.py"],
            )

            run_dir = self.run_dir(self.repo, run_id)
            records, issues = journal.read_journal(
                run_dir / "journal.jsonl"
            )
            self.assertEqual(issues, [])
            self.assertEqual(
                [record["type"] for record in records],
                ["run_started", "task", "decision", "task"],
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key("readmit-sequence-task-3"),
                task="task-03",
                goal="Prove appends continue",
                acceptance=["A later append succeeds"],
                files=["tests/test_later.py"],
            )

        receipts = [
            json.loads(line)
            for line in (
                run_dir / journal.BATCH_RECEIPTS_NAME
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(receipts), 5)
        self.assertTrue(
            all(
                current["base_size"] == previous["journal_size"]
                for previous, current in zip(receipts, receipts[1:])
            )
        )
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

    def test_scope_change_recovers_intent_and_receipted_registry_publication(self) -> None:
        for crash_point in ("intent", "registry"):
            with self.subTest(crash_point=crash_point):
                repo, _ = self._new_repo(f"repo-readmit-{crash_point}")
                run_id = f"run-20260831-readmit-{crash_point}"
                transaction_key = key(f"readmit-{crash_point}")
                with self.api_environment():
                    self.open_run(repo, run_id)
                    if crash_point == "intent":
                        with mock.patch.object(
                            batch,
                            "_recover_locked",
                            side_effect=RuntimeError("crash after intent"),
                        ), self.assertRaisesRegex(
                            RuntimeError, "crash after intent"
                        ):
                            builders.scope_change(
                                repo,
                                run_id,
                                idempotency_key=transaction_key,
                                scope=["src/**", "tests/**"],
                            )
                        run_dir = self.run_dir(repo, run_id)
                        self.assertTrue(
                            (run_dir / journal.BATCH_INTENT_NAME).is_file()
                        )
                        original_registry_lock = journal._registry_lock
                        registry_epochs = 0

                        @contextmanager
                        def counted_registry_lock(state_root: Path):
                            nonlocal registry_epochs
                            registry_epochs += 1
                            with original_registry_lock(state_root) as locked:
                                yield locked

                        with mock.patch.object(
                            journal,
                            "_registry_lock",
                            side_effect=counted_registry_lock,
                        ):
                            recovered = batch.recover_batch(repo, run_id)
                        self.assertEqual(registry_epochs, 1)
                    else:
                        with mock.patch.object(
                            journal,
                            "_write_registry",
                            side_effect=journal.CoordinationRefusal(
                                journal.REGISTRY_UPDATE_FAILED
                            ),
                        ), self.assertRaisesRegex(
                            journal.CoordinationRefusal,
                            journal.REGISTRY_UPDATE_FAILED,
                        ):
                            builders.scope_change(
                                repo,
                                run_id,
                                idempotency_key=transaction_key,
                                scope=["src/**", "tests/**"],
                            )
                        run_dir = self.run_dir(repo, run_id)
                        self.assertFalse(
                            (run_dir / journal.BATCH_INTENT_NAME).exists()
                        )
                        recovered = builders.scope_change(
                            repo,
                            run_id,
                            idempotency_key=transaction_key,
                            scope=["src/**", "tests/**"],
                        )
                    self.assertTrue(recovered.repeated)
                    self.assertFalse(
                        (run_dir / journal.BATCH_INTENT_NAME).exists()
                    )
                    state = journal._scan_run(run_dir)
                    self.assertEqual(state.scope, ("src/**", "tests/**"))
                    receipts = [
                        json.loads(line)
                        for line in (
                            run_dir / journal.BATCH_RECEIPTS_NAME
                        ).read_text(encoding="utf-8").splitlines()
                    ]
                    self.assertEqual(len(receipts), 2)

    def test_scope_change_recovery_refuses_unproved_replace_and_disabled_control(self) -> None:
        for scenario in ("unproved-replace", "disabled-control"):
            with self.subTest(scenario=scenario):
                repo, _ = self._new_repo(f"repo-readmit-{scenario}")
                run_id = f"run-20260831-readmit-{scenario}"
                transaction_key = key(f"readmit-{scenario}")
                with self.api_environment():
                    builders.run_open(
                        repo,
                        run_id,
                        idempotency_key=key(f"{scenario}-open"),
                        goal="Exercise guarded readmission recovery",
                        scope=["src/**", "tests/**"],
                        plugin_ref="forge-test-revision-9",
                    )
                    with mock.patch.object(
                        batch,
                        "_recover_locked",
                        side_effect=RuntimeError("crash after intent"),
                    ), self.assertRaisesRegex(RuntimeError, "crash after intent"):
                        builders.scope_change(
                            repo,
                            run_id,
                            idempotency_key=transaction_key,
                            scope=(
                                ["src/**"]
                                if scenario == "unproved-replace"
                                else ["src/**", "tests/**", "tools/**"]
                            ),
                            replace=scenario == "unproved-replace",
                        )
                    run_dir = self.run_dir(repo, run_id)
                    if scenario == "unproved-replace":
                        current = journal._session_owner()
                        (run_dir / "owner").write_bytes(
                            journal._owner_bytes(
                                journal.Owner(
                                    pid=99999999,
                                    host=current.host,
                                    started_at="2026-08-31T00:00:00Z",
                                )
                            )
                        )
                    before = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    controls = (
                        batch.SCOPE_CHANGE_TRANSACTION_CONTROLS
                        if scenario == "unproved-replace"
                        else frozenset()
                    )
                    expected = (
                        "proposed scope omits current pathspecs"
                        if scenario == "unproved-replace"
                        else journal.BATCH_DIVERGED
                    )
                    with mock.patch.object(
                        batch,
                        "SCOPE_CHANGE_TRANSACTION_CONTROLS",
                        controls,
                    ), self.assertRaisesRegex(
                        journal.CoordinationRefusal, expected
                    ):
                        batch.recover_batch(repo, run_id)
                    after = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    self.assertEqual(after, before)

                    recovered = builders.scope_change(
                        repo,
                        run_id,
                        idempotency_key=transaction_key,
                        scope=(
                            ["src/**"]
                            if scenario == "unproved-replace"
                            else ["src/**", "tests/**", "tools/**"]
                        ),
                        replace=scenario == "unproved-replace",
                    )
                    self.assertTrue(recovered.repeated)
                    self.assertFalse(
                        (run_dir / journal.BATCH_INTENT_NAME).exists()
                    )

    def test_batch_gap_repair_refuses_leading_trailing_and_ambiguous_gaps(self) -> None:
        def assert_unchanged_refusal(repo: Path, run_dir: Path) -> None:
            before = {
                path.name: path.read_bytes()
                for path in run_dir.iterdir()
                if path.is_file()
            }
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, journal.BATCH_DIVERGED
            ):
                batch.recover_batch(repo, run_dir.name)
            after = {
                path.name: path.read_bytes()
                for path in run_dir.iterdir()
                if path.is_file()
            }
            self.assertEqual(after, before)

        with self.api_environment():
            repo, _ = self._new_repo("repo-gap-leading")
            run_dir, _intent = self._leave_complete_intent(
                repo, "run-20260831-gap-leading"
            )
            (run_dir / journal.BATCH_RECEIPTS_NAME).write_bytes(b"")
            assert_unchanged_refusal(repo, run_dir)

            repo, _ = self._new_repo("repo-gap-trailing")
            run_dir, _removed = self._leave_scope_receipt_gap(
                repo, "run-20260831-gap-trailing"
            )
            ledger = run_dir / journal.BATCH_RECEIPTS_NAME
            lines = ledger.read_bytes().splitlines(keepends=True)
            ledger.write_bytes(b"".join(lines[:-1]))
            assert_unchanged_refusal(repo, run_dir)

            repo, _ = self._new_repo("repo-gap-multiple")
            run_id = "run-20260831-gap-multiple"
            self.open_run(repo, run_id)
            self.start_task(repo, run_id)
            builders.scope_change(
                repo,
                run_id,
                idempotency_key=key("multiple-gap-readmit-1"),
                scope=["src/**", "tests/**"],
            )
            builders.task_start(
                repo,
                run_id,
                idempotency_key=key("multiple-gap-task-2"),
                task="task-02",
                goal="Separate the receipt gaps",
                acceptance=["A normal receipt separates gaps"],
                files=["tests/example.py"],
            )
            builders.scope_change(
                repo,
                run_id,
                idempotency_key=key("multiple-gap-readmit-2"),
                scope=["docs/**", "src/**", "tests/**"],
            )
            builders.task_start(
                repo,
                run_id,
                idempotency_key=key("multiple-gap-following"),
                task="task-03",
                goal="Anchor both receipt gaps",
                acceptance=["Both gaps remain ambiguous"],
                files=["docs/example.md"],
            )
            run_dir = self.run_dir(repo, run_id)
            ledger = run_dir / journal.BATCH_RECEIPTS_NAME
            lines = ledger.read_bytes().splitlines(keepends=True)
            kept = [lines[0], lines[1], lines[3], lines[5]]
            ledger.write_bytes(b"".join(kept))
            self._write_landed_intent_for_last_receipt(run_dir, kept)
            assert_unchanged_refusal(repo, run_dir)

    def test_batch_recover_repairs_one_n_record_gap(self) -> None:
        run_id = "run-20260831-gap-two-records"
        with self.api_environment():
            run_dir, removed, following, gap_bytes = (
                self._leave_two_record_receipt_gap(self.repo, run_id)
            )
            journal_path = run_dir / "journal.jsonl"
            journal_before = journal_path.read_bytes()
            recovered = batch.recover_batch(self.repo, run_id)

            self.assertTrue(recovered.repeated)
            self.assertEqual(journal_path.read_bytes(), journal_before)
            self.assertFalse(
                (run_dir / journal.BATCH_INTENT_NAME).exists()
            )
            with batch.batch_lock(run_dir, create=False) as locked:
                receipts, _raw, _observed = batch._load_receipts(locked)
            repairs = [
                receipt
                for receipt in receipts
                if receipt.get("repaired") is True
            ]
            self.assertEqual(len(repairs), 1)
            repair = repairs[0]
            gap_base = int(removed[0]["base_size"])
            gap_end = int(removed[-1]["journal_size"])
            gap_sha256 = journal._sha256(gap_bytes)
            self.assertEqual(gap_end, following["base_size"])
            self.assertEqual(repair["base_size"], gap_base)
            self.assertEqual(repair["journal_size"], gap_end)
            self.assertEqual(repair["record_count"], 2)
            self.assertEqual(repair["batch_sha256"], gap_sha256)
            self.assertEqual(
                repair["journal_sha256"],
                journal._sha256(journal_before[:gap_end]),
            )
            self.assertEqual(repair["recorded_at"], following["recorded_at"])
            self.assertEqual(
                repair["repair_reason"], batch._BATCH_GAP_REPAIR_REASON
            )

            repair_identity = {
                "schema": batch._BATCH_GAP_REPAIR_SCHEMA,
                "repository": str(self.repo.resolve()),
                "run_id": run_id,
                "base_size": gap_base,
                "journal_size": gap_end,
                "batch_sha256": gap_sha256,
                "record_count": 2,
                "following_idempotency_key": following["idempotency_key"],
            }
            expected_key = journal._sha256(
                journal._canonical_json_bytes(repair_identity)
            )
            expected_request = {
                "schema": journal.BATCH_REQUEST_SCHEMA,
                "verb": "journal batch-recover",
                "repository": str(self.repo.resolve()),
                "run_id": run_id,
                "inputs": repair_identity,
            }
            self.assertEqual(repair["idempotency_key"], expected_key)
            self.assertEqual(
                repair["request_sha256"],
                journal._sha256(
                    journal._canonical_json_bytes(expected_request)
                ),
            )

            appended = builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key("two-record-gap-task-3"),
                task="task-03",
                goal="Prove post-repair typed append",
                acceptance=["The append succeeds"],
                files=["docs/after-repair.md"],
            )
            self.assertEqual(appended.records[0]["id"], "task-03")

    def test_batch_gap_repair_controls_are_independently_load_bearing(self) -> None:
        self.assertEqual(
            batch.BATCH_GAP_REPAIR_CONTROLS,
            frozenset(
                {
                    "canonical-gap-receipt",
                    "legacy-record-membership",
                    "multi-record-gap",
                }
            ),
        )
        for control in sorted(batch.BATCH_GAP_REPAIR_CONTROLS):
            with self.subTest(control=control):
                repo, _ = self._new_repo(f"repo-gap-control-{control}")
                run_id = f"run-20260910-gap-control-{control}"
                with self.api_environment():
                    if control == "legacy-record-membership":
                        run_dir, _context = self._seed_gh17_wedge(
                            repo, run_id
                        )
                    else:
                        run_dir, _removed, _following, _gap_bytes = (
                            self._leave_two_record_receipt_gap(repo, run_id)
                        )
                    before = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    with mock.patch.object(
                        batch,
                        "BATCH_GAP_REPAIR_CONTROLS",
                        batch.BATCH_GAP_REPAIR_CONTROLS - {control},
                    ), self.assertRaisesRegex(
                        journal.CoordinationRefusal,
                        journal.BATCH_DIVERGED,
                    ):
                        batch.recover_batch(repo, run_id)
                    after = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    self.assertEqual(after, before)

    def test_repair_receipt_is_rederived_on_every_load(self) -> None:
        for field, replacement in (
            ("idempotency_key", key("forged-repair-key")),
            ("request_sha256", key("forged-repair-request")),
            ("recorded_at", "2026-08-31T00:00:00Z"),
        ):
            with self.subTest(field=field):
                repo, _ = self._new_repo(f"repo-forged-repair-{field}")
                run_id = f"run-20260831-forged-repair-{field}"
                with self.api_environment():
                    run_dir, _removed = self._leave_scope_receipt_gap(
                        repo, run_id
                    )
                    batch.recover_batch(repo, run_id)
                    ledger = run_dir / journal.BATCH_RECEIPTS_NAME
                    lines = ledger.read_bytes().splitlines(keepends=True)
                    repair = json.loads(lines[-1])
                    self.assertIs(repair["repaired"], True)
                    repair[field] = replacement
                    lines[-1] = journal._canonical_json_bytes(repair) + b"\n"
                    ledger.write_bytes(b"".join(lines))
                    before = ledger.read_bytes()
                    with batch.batch_lock(
                        run_dir, create=False
                    ) as locked, self.assertRaisesRegex(
                        journal.CoordinationRefusal, journal.BATCH_DIVERGED
                    ):
                        batch._load_receipts(locked)
                    self.assertEqual(ledger.read_bytes(), before)

    def test_torn_repair_receipt_resumes_only_its_derived_suffix(self) -> None:
        run_id = "run-20260831-torn-repair"
        with self.api_environment():
            run_dir, _removed = self._leave_scope_receipt_gap(
                self.repo, run_id
            )
            original = batch._append_named_file
            tore = False

            def tear_repair(
                locked: batch.BatchLock,
                name: str,
                payload: bytes,
                expected: journal.FileObservation,
                **kwargs: object,
            ) -> None:
                nonlocal tore
                if (
                    not tore
                    and name == journal.BATCH_RECEIPTS_NAME
                    and b'"repaired":true' in payload
                ):
                    tore = True
                    prefix = payload[: max(1, len(payload) // 2)]
                    original(locked, name, prefix, expected, **kwargs)
                    raise RuntimeError("torn repair receipt")
                original(locked, name, payload, expected, **kwargs)

            with mock.patch.object(
                batch, "_append_named_file", side_effect=tear_repair
            ), self.assertRaisesRegex(RuntimeError, "torn repair receipt"):
                batch.recover_batch(self.repo, run_id)
            torn = (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes()
            self.assertFalse(torn.endswith(b"\n"))

            recovered = batch.recover_batch(self.repo, run_id)
            self.assertTrue(recovered.repeated)
            self.assertFalse(
                (run_dir / journal.BATCH_INTENT_NAME).exists()
            )
            with batch.batch_lock(run_dir, create=False) as locked:
                receipts, raw, _observed = batch._load_receipts(locked)
            self.assertTrue(raw.endswith(b"\n"))
            self.assertEqual(
                sum(receipt.get("repaired") is True for receipt in receipts),
                1,
            )

    def test_activated_scope_change_rechecks_superset_containment_and_conflicts(self) -> None:
        run_id = "run-20260831-readmit-predicates"
        other_id = "run-20260831-readmit-conflict"
        with self.api_environment():
            builders.run_open(
                self.repo,
                run_id,
                idempotency_key=key("readmit-predicates-open"),
                goal="Exercise every locked readmission predicate",
                scope=["src/**", "tests/**"],
                plugin_ref="forge-test-revision-9",
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key("readmit-predicates-task"),
                task="task-01",
                goal="Pin a contained task",
                acceptance=["Readmission retains this file"],
                files=["src/example.py"],
            )
            builders.run_open(
                self.repo,
                other_id,
                idempotency_key=key("readmit-conflict-open"),
                goal="Reserve a conflicting scope",
                scope=["docs/**"],
                plugin_ref="forge-test-revision-9",
            )
            run_dir = self.run_dir(self.repo, run_id)

            cases = (
                (
                    "omitted-current",
                    ["src/**"],
                    False,
                    '"tests/**"',
                ),
                (
                    "task-containment",
                    ["tests/**"],
                    True,
                    '"src/example.py"',
                ),
                (
                    "other-run-conflict",
                    ["docs/**", "src/**", "tests/**"],
                    False,
                    other_id,
                ),
            )
            for label, scope, replace, expected in cases:
                with self.subTest(label=label):
                    before = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    with self.assertRaises(
                        journal.CoordinationRefusal
                    ) as caught:
                        builders.scope_change(
                            self.repo,
                            run_id,
                            idempotency_key=key(f"readmit-{label}"),
                            scope=scope,
                            replace=replace,
                        )
                    self.assertIn(expected, str(caught.exception))
                    after = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    self.assertEqual(after, before)

    def test_concurrent_admission_and_scope_change_remain_disjoint(self) -> None:
        target = "run-20260831-readmit-race-target"
        contender = "run-20260831-readmit-race-contender"
        with self.api_environment():
            self.open_run(self.repo, target)
            current = journal._session_owner()
            (self.run_dir(self.repo, target) / "owner").write_bytes(
                journal._owner_bytes(
                    journal.Owner(
                        pid=99999999,
                        host=current.host,
                        started_at="2026-08-31T00:00:00Z",
                    )
                )
            )

        barrier_dir = Path(self.temporary.name) / "readmit-race-barrier"
        barrier_dir.mkdir()
        program = r'''
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from codex_orchestrator import builders, journal

mode, repository, barrier = sys.argv[2:]
repository = Path(repository)
barrier = Path(barrier)
os.environ["FORGE_SESSION_PID"] = str(os.getpid())
original = journal._registry_lock
first = True

@contextmanager
def synchronized_registry_lock(state_root):
    global first
    if first:
        first = False
        (barrier / mode).write_text("ready\n", encoding="utf-8")
        deadline = time.monotonic() + 10.0
        while len(tuple(barrier.iterdir())) < 2:
            if time.monotonic() >= deadline:
                raise RuntimeError("barrier timeout")
            time.sleep(0.01)
    with original(state_root) as locked:
        yield locked

journal._registry_lock = synchronized_registry_lock
try:
    if mode == "readmit":
        builders.scope_change(
            repository,
            "run-20260831-readmit-race-target",
            idempotency_key="1" * 64,
            scope=["src/**", "tests/**"],
        )
    else:
        builders.run_open(
            repository,
            "run-20260831-readmit-race-contender",
            idempotency_key="2" * 64,
            goal="Race the locked scope change",
            scope=["tests/**"],
            plugin_ref="forge-test-revision-9",
        )
except journal.CoordinationRefusal as exc:
    print(str(exc))
    raise SystemExit(1)
print("committed")
'''
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    program,
                    str(ROOT / "scripts"),
                    mode,
                    str(self.repo),
                    str(barrier_dir),
                ],
                cwd=self.repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            for mode in ("readmit", "admit")
        ]
        results: list[tuple[int, str, str]] = []
        try:
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                results.append((process.returncode, stdout, stderr))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)

        self.assertEqual(
            sorted(result[0] for result in results), [0, 1], results
        )
        refusal = next(result[1] for result in results if result[0] == 1)
        self.assertIn("scope overlap", refusal)
        registry = json.loads(
            (self.repo / ".forge/tmp/run-registry.json").read_text(
                encoding="utf-8"
            )
        )
        scopes = {
            entry["run_id"]: tuple(entry["scope"])
            for entry in registry["open_runs"]
        }
        if contender in scopes:
            self.assertEqual(scopes[target], ("src/**",))
            self.assertEqual(scopes[contender], ("tests/**",))
        else:
            self.assertEqual(scopes[target], ("src/**", "tests/**"))
        with batch.batch_lock(
            self.run_dir(self.repo, target), create=False
        ) as locked:
            batch._load_receipts(locked)

    def _leave_scope_receipt_gap(
        self, repo: Path, run_id: str
    ) -> tuple[Path, dict[str, object]]:
        self.open_run(repo, run_id)
        builders.task_start(
            repo,
            run_id,
            idempotency_key=key(f"{run_id}-task-1"),
            task="task-01",
            goal="Establish the initial receipt chain",
            acceptance=["The first task is receipted"],
            files=["src/example.py"],
        )
        builders.scope_change(
            repo,
            run_id,
            idempotency_key=key(f"{run_id}-readmit"),
            scope=["src/**", "tests/**"],
        )
        builders.task_start(
            repo,
            run_id,
            idempotency_key=key(f"{run_id}-task-2"),
            task="task-02",
            goal="Land after the unreceipted readmission",
            acceptance=["Recovery resumes later appends"],
            files=["tests/test_gap.py"],
        )
        run_dir = self.run_dir(repo, run_id)
        ledger = run_dir / journal.BATCH_RECEIPTS_NAME
        receipt_lines = ledger.read_bytes().splitlines(keepends=True)
        removed = json.loads(receipt_lines[-2])
        following = json.loads(receipt_lines[-1])
        self.assertEqual(removed["record_count"], 1)
        ledger_prefix = b"".join(receipt_lines[:-2])
        following_line = receipt_lines[-1]
        ledger.write_bytes(ledger_prefix + following_line)

        journal_bytes = (run_dir / "journal.jsonl").read_bytes()
        batch_bytes = journal_bytes[
            int(following["base_size"]) : int(following["journal_size"])
        ]
        intent = {
            "schema": journal.BATCH_INTENT_SCHEMA,
            "idempotency_key": following["idempotency_key"],
            "request_sha256": following["request_sha256"],
            "base_size": following["base_size"],
            "base_sha256": journal._sha256(
                journal_bytes[: int(following["base_size"])]
            ),
            "record_count": following["record_count"],
            "batch_bytes": batch._encode_base64url(batch_bytes),
            "batch_sha256": following["batch_sha256"],
            "receipt_base_size": len(ledger_prefix),
            "receipt_base_sha256": journal._sha256(ledger_prefix),
            "receipt_bytes": batch._encode_base64url(following_line),
        }
        (run_dir / journal.BATCH_INTENT_NAME).write_bytes(
            journal._canonical_json_bytes(intent) + b"\n"
        )

        with batch.batch_lock(run_dir, create=False) as locked, self.assertRaises(
            journal.CoordinationRefusal
        ) as caught:
            batch._load_receipts(locked)
        self.assertEqual(
            str(caught.exception),
            "forge: journal batch recovery refused — journal diverged from intent",
        )
        self.assertTrue((run_dir / journal.BATCH_INTENT_NAME).is_file())
        return run_dir, removed

    def _leave_two_record_receipt_gap(
        self, repo: Path, run_id: str
    ) -> tuple[
        Path,
        tuple[dict[str, object], dict[str, object]],
        dict[str, object],
        bytes,
    ]:
        self.open_run(repo, run_id)
        self.start_task(repo, run_id)
        builders.scope_change(
            repo,
            run_id,
            idempotency_key=key(f"{run_id}-two-record-readmit-1"),
            scope=["src/**", "tests/**"],
        )
        builders.scope_change(
            repo,
            run_id,
            idempotency_key=key(f"{run_id}-two-record-readmit-2"),
            scope=["docs/**", "src/**", "tests/**"],
        )
        builders.task_start(
            repo,
            run_id,
            idempotency_key=key(f"{run_id}-two-record-following"),
            task="task-02",
            goal="Anchor the two-record receipt gap",
            acceptance=["The following receipt is exact"],
            files=["docs/example.md"],
        )
        run_dir = self.run_dir(repo, run_id)
        ledger = run_dir / journal.BATCH_RECEIPTS_NAME
        lines = ledger.read_bytes().splitlines(keepends=True)
        removed = (json.loads(lines[-3]), json.loads(lines[-2]))
        following = json.loads(lines[-1])
        kept = lines[:-3] + [lines[-1]]
        ledger.write_bytes(b"".join(kept))
        self._write_landed_intent_for_last_receipt(run_dir, kept)
        journal_bytes = (run_dir / "journal.jsonl").read_bytes()
        gap_bytes = journal_bytes[
            int(removed[0]["base_size"]) : int(removed[-1]["journal_size"])
        ]
        self.assertEqual(len(journal._parse_raw_records(gap_bytes)), 2)
        return run_dir, removed, following, gap_bytes

    def _write_landed_intent_for_last_receipt(
        self, run_dir: Path, ledger_lines: list[bytes]
    ) -> dict[str, object]:
        following_line = ledger_lines[-1]
        following = json.loads(following_line)
        ledger_prefix = b"".join(ledger_lines[:-1])
        journal_bytes = (run_dir / "journal.jsonl").read_bytes()
        batch_bytes = journal_bytes[
            int(following["base_size"]) : int(following["journal_size"])
        ]
        intent = {
            "schema": journal.BATCH_INTENT_SCHEMA,
            "idempotency_key": following["idempotency_key"],
            "request_sha256": following["request_sha256"],
            "base_size": following["base_size"],
            "base_sha256": journal._sha256(
                journal_bytes[: int(following["base_size"])]
            ),
            "record_count": following["record_count"],
            "batch_bytes": batch._encode_base64url(batch_bytes),
            "batch_sha256": following["batch_sha256"],
            "receipt_base_size": len(ledger_prefix),
            "receipt_base_sha256": journal._sha256(ledger_prefix),
            "receipt_bytes": batch._encode_base64url(following_line),
        }
        (run_dir / journal.BATCH_INTENT_NAME).write_bytes(
            journal._canonical_json_bytes(intent) + b"\n"
        )
        return intent

    def test_batch_recover_repairs_proven_readmission_gap_and_stale_intent(self) -> None:
        run_id = "run-20260831-repair-readmit-gap"
        with self.api_environment():
            run_dir, removed = self._leave_scope_receipt_gap(
                self.repo, run_id
            )
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            recovered = batch.recover_batch(self.repo, run_id)
            self.assertTrue(recovered.repeated)
            self.assertFalse(
                (run_dir / journal.BATCH_INTENT_NAME).exists()
            )
            self.assertEqual(
                (run_dir / "journal.jsonl").read_bytes(), journal_before
            )
            with batch.batch_lock(run_dir, create=False) as locked:
                receipts, _raw, _observed = batch._load_receipts(locked)
            repairs = [
                receipt
                for receipt in receipts
                if receipt.get("repaired") is True
            ]
            self.assertEqual(len(repairs), 1)
            self.assertEqual(repairs[0]["base_size"], removed["base_size"])
            self.assertEqual(
                repairs[0]["journal_size"], removed["journal_size"]
            )
            self.assertEqual(
                repairs[0]["repair_reason"],
                batch._BATCH_GAP_REPAIR_REASON,
            )
            records, issues = journal.read_journal(
                run_dir / "journal.jsonl"
            )
            self.assertEqual(issues, [])
            self.assertEqual(records[-1]["id"], "task-02")
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key("repair-readmit-task-3"),
                task="task-03",
                goal="Prove post-repair append",
                acceptance=["The append succeeds"],
                files=["tests/test_after_repair.py"],
            )

    def test_batch_gap_repair_refuses_unproved_bytes_and_intent(self) -> None:
        attacks = (
            "non-record",
            "tampered",
            "intent-mismatch",
            "repair-intent",
        )
        for attack in attacks:
            with self.subTest(attack=attack):
                repo, _ = self._new_repo(f"repo-gap-{attack}")
                run_id = f"run-20260831-gap-{attack}"
                with self.api_environment():
                    run_dir, removed = self._leave_scope_receipt_gap(
                        repo, run_id
                    )
                    journal_path = run_dir / "journal.jsonl"
                    intent_path = run_dir / journal.BATCH_INTENT_NAME
                    raw = bytearray(journal_path.read_bytes())
                    base = int(removed["base_size"])
                    end = int(removed["journal_size"])
                    if attack == "non-record":
                        raw[base:end] = b"x" * (end - base)
                        journal_path.write_bytes(raw)
                    elif attack == "tampered":
                        marker = b"forge-scope-readmission-"
                        offset = bytes(raw[base:end]).index(marker) + len(marker)
                        absolute = base + offset
                        raw[absolute] = (
                            ord("0") if raw[absolute] != ord("0") else ord("1")
                        )
                        journal_path.write_bytes(raw)
                    elif attack == "intent-mismatch":
                        intent = json.loads(
                            intent_path.read_text(encoding="utf-8")
                        )
                        batch_bytes = base64.urlsafe_b64decode(
                            intent["batch_bytes"]
                            + "=" * (-len(intent["batch_bytes"]) % 4)
                        )
                        record = json.loads(batch_bytes)
                        record["goal"] = "Different already-landed bytes"
                        replacement = journal._journal_line(record)
                        receipt_bytes = base64.urlsafe_b64decode(
                            intent["receipt_bytes"]
                            + "=" * (-len(intent["receipt_bytes"]) % 4)
                        )
                        receipt = json.loads(receipt_bytes)
                        receipt["batch_sha256"] = journal._sha256(replacement)
                        receipt["journal_size"] = int(intent["base_size"]) + len(
                            replacement
                        )
                        prefix = bytes(raw[: int(intent["base_size"])])
                        receipt["journal_sha256"] = journal._sha256(
                            prefix + replacement
                        )
                        replacement_receipt = (
                            journal._canonical_json_bytes(receipt) + b"\n"
                        )
                        intent["batch_bytes"] = batch._encode_base64url(
                            replacement
                        )
                        intent["batch_sha256"] = journal._sha256(replacement)
                        intent["receipt_bytes"] = batch._encode_base64url(
                            replacement_receipt
                        )
                        intent_path.write_bytes(
                            journal._canonical_json_bytes(intent) + b"\n"
                        )
                    elif attack == "repair-intent":
                        intent = json.loads(
                            intent_path.read_text(encoding="utf-8")
                        )
                        receipt_bytes = base64.urlsafe_b64decode(
                            intent["receipt_bytes"]
                            + "=" * (-len(intent["receipt_bytes"]) % 4)
                        )
                        receipt = json.loads(receipt_bytes)
                        receipt["repaired"] = True
                        receipt["repair_reason"] = batch._BATCH_GAP_REPAIR_REASON
                        intent["receipt_bytes"] = batch._encode_base64url(
                            journal._canonical_json_bytes(receipt) + b"\n"
                        )
                        intent_path.write_bytes(
                            journal._canonical_json_bytes(intent) + b"\n"
                        )

                    before = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal,
                        journal.BATCH_DIVERGED,
                    ):
                        batch.recover_batch(repo, run_id)
                    after = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    self.assertEqual(after, before)

    def test_typed_task_scope_refusal_names_offending_pathspec(self) -> None:
        run_id = "run-20260831-typed-task-scope"
        with self.api_environment():
            self.open_run(self.repo, run_id)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, '"docs/example.py"'
            ):
                builders.task_start(
                    self.repo,
                    run_id,
                    idempotency_key=key("typed-task-outside-scope"),
                    task="task-01",
                    goal="Exercise named scope refusal",
                    acceptance=["The path is named"],
                    files=["docs/example.py"],
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

        readmit_request, readmit_digest = batch.normalized_request(
            self.repo.resolve(),
            "run-20260831-readmit-request",
            "run-readmit",
            {"scope": ["tests/**", "src/**"], "replace": False},
        )
        self.assertEqual(
            readmit_request,
            {
                "schema": journal.BATCH_REQUEST_SCHEMA,
                "verb": "run-readmit",
                "repository": str(self.repo.resolve()),
                "run_id": "run-20260831-readmit-request",
                "inputs": {
                    "scope": ["tests/**", "src/**"],
                    "replace": False,
                },
            },
        )
        self.assertEqual(
            readmit_digest,
            journal._sha256(
                journal._canonical_json_bytes(readmit_request)
            ),
        )

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
        activation_marker: dict[str, object] | None = None,
        chain_id: str = "c-2026-08-28T120000Z-abcd",
    ) -> tuple[str, Path]:
        chains = builders.chain_storage_root(repo)
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
            records = (
                [copy.deepcopy(activation_marker), record]
                if activation_marker is not None
                else [record]
            )
            batch_bytes = b"".join(
                journal._journal_line(item) for item in records
            )
            journal_batch = {
                "idempotency_key": source_digest,
                "batch_digest": journal._sha256(batch_bytes),
                "record_count": len(records),
                "records": records,
            }
            assert isinstance(unsigned["payload"], dict)
            details = unsigned["payload"]["details"]
            assert isinstance(details, dict)
            details["source_event_digest"] = source_digest
            details["journal_batch"] = journal_batch
            state["journal_outbox"] = {
                "idempotency_key": source_digest,
                "batch_digest": journal_batch["batch_digest"],
                "record_count": len(records),
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
        task_id = next(
            str(record["task"])
            for record in records
            if isinstance(record.get("task"), str)
        )
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
        return self._append_test_decision(repo, run_id, chain_id, "chain-landing")

    def _append_test_decision(
        self, repo: Path, run_id: str, chain_id: str, outcome: str, *, seed: str = ""
    ) -> dict[str, object]:
        preimage = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain_id,
                "event_digest": key(
                    ("terminal-event" if outcome == "chain-landing" else f"terminal-event-{outcome}")
                    + seed
                ),
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
            appended = builders.decision_add(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-{chain_id}-terminal-{outcome}{seed}"),
                task="task-01",
                resolution=(
                    "The bound candidate landed"
                    if outcome == "chain-landing"
                    else "The bound chain was aborted"
                ),
                finding=None,
                outcome=outcome,
                risk=None,
                basis=[],
                binding_chain=chain_id,
                binding_id=str(binding["binding_id"]),
            )
        self.assertFalse(appended.repeated)
        self.assertEqual(len(appended.records), 1)
        recorded_binding = appended.records[0].get("binding")
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

    def _abort_bound_chain_fixture(
        self, repo: Path, chain_id: str, state_path: Path, *, outbox: object = None
    ) -> None:
        """Append an authenticated chain_aborted event to a fixture chain."""
        events_path = state_path.parent / f"{chain_id}.events.jsonl"
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-08-28T12:05:00Z"
        state["state"] = "aborted"
        state["commit_result"] = {
            "aborted_at": state["last_event_at"],
            "reason": "candidate superseded",
        }
        state["journal_outbox"] = outbox
        unsigned = {
            "sequence": len(events) + 1,
            "prev_digest": events[-1]["digest"],
            "payload": {
                "at": state["last_event_at"],
                "details": {"reason": "candidate superseded"},
                "event": "chain_aborted",
                "state": copy.deepcopy(state),
            },
        }
        event = {
            **unsigned,
            "digest": journal._sha256(journal._canonical_json_bytes(unsigned)),
        }
        events.append(event)
        events_path.write_bytes(
            b"".join(journal._canonical_json_bytes(item) + b"\n" for item in events)
        )
        state_path.write_bytes(journal._canonical_json_bytes(state) + b"\n")

    def test_terminal_builder_accepts_authenticated_abort_disposition(self) -> None:
        """Bead forge-plugin-437: an explicit abort is a terminal disposition."""
        with self.api_environment():
            repo, run_id, run_binding = self._terminal_control_repo("abort-accepted")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._abort_bound_chain_fixture(repo, chain_id, state_path)
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"abort-disposition"},
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-disabled"),
                    task="task-01", status="complete",
                )
            outcome = builders.task_finish(
                repo, run_id, idempotency_key=key("abort-accepted"),
                task="task-01", status="complete",
            )
            self.assertEqual(outcome.records[0]["status"], "complete")

            # A landing decision citing the aborted chain contradicts its state.
            repo, run_id, run_binding = self._terminal_control_repo("abort-landing")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._abort_bound_chain_fixture(repo, chain_id, state_path)
            self._append_test_landing(repo, run_id, chain_id)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-landing"),
                    task="task-01", status="complete",
                )

            # An aborted chain whose outbox is still pending is not terminal.
            repo, run_id, run_binding = self._terminal_control_repo("abort-outbox")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox={"pending": True}
            )
            self._abort_bound_chain_fixture(
                repo, chain_id, state_path, outbox={"pending": True}
            )
            # A consequential chain_aborted appended over an unreceipted outbox
            # is a replay violation, so replay refuses it before the outbox or
            # abort-disposition controls are reached.
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-outbox"),
                    task="task-01", status="complete",
                )

            # A landing decision citing the aborted chain is contradictory even
            # when the journal also holds the abort decision.
            repo, run_id, run_binding = self._terminal_control_repo("abort-both")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._abort_bound_chain_fixture(repo, chain_id, state_path)
            self._append_test_decision(repo, run_id, chain_id, "chain-abort")
            self._append_test_landing(repo, run_id, chain_id)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-both"),
                    task="task-01", status="complete",
                )

            # Two abort decisions for one aborted chain are refused: exactly
            # one carried decision is the only accepted shape.
            repo, run_id, run_binding = self._terminal_control_repo("abort-twice")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._abort_bound_chain_fixture(repo, chain_id, state_path)
            self._append_test_decision(repo, run_id, chain_id, "chain-abort")
            self._append_test_decision(
                repo, run_id, chain_id, "chain-abort", seed="second"
            )
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-twice"),
                    task="task-01", status="complete",
                )

            # An abort decision citing a chain that is not a terminal abort is
            # contradictory too.
            repo, run_id, run_binding = self._terminal_control_repo("abort-live")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._append_test_decision(repo, run_id, chain_id, "chain-abort")
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-live"),
                    task="task-01", status="complete",
                )

    def test_terminal_abort_disposition_fails_closed_on_shape(self) -> None:
        base = {"state": "aborted", "journal_outbox": None}
        self.assertFalse(builders._terminal_abort_disposition(dict(base)))
        self.assertFalse(builders._terminal_abort_disposition({**base, "kind": "other"}))
        self.assertFalse(
            builders._terminal_abort_disposition({**base, "kind": "commit", "commit_result": {}})
        )
        self.assertFalse(
            builders._terminal_abort_disposition(
                {**base, "kind": "commit", "commit_result": {"aborted_at": "2026-08-28T12:05:00Z", "commit_sha": "1" * 40}}
            )
        )
        self.assertTrue(
            builders._terminal_abort_disposition(
                {**base, "kind": "commit", "commit_result": {"aborted_at": "2026-08-28T12:05:00Z", "reason": ""}}
            )
        )
        self.assertTrue(builders._terminal_abort_disposition({**base, "kind": "merge"}))
        self.assertFalse(
            builders._terminal_abort_disposition({**base, "kind": "merge", "journal_outbox": {"pending": True}})
        )

    def _self_event_fixture(self) -> tuple[dict, dict, dict]:
        """A minimal aborted commit state and its abort_disposition_recorded event."""
        sha = key("self-event-candidate")
        prior = {
            "schema": "forge-chain/1",
            "chain_id": "c-2026-09-05T000000Z-abcd",
            "kind": "commit",
            "state": "aborted",
            "created_at": "2026-09-05T00:00:00Z",
            "last_event_at": "2026-09-05T00:01:00Z",
            "inactive_after": "2026-09-06T00:01:00Z",
            "candidate": {"sha256": sha, "computed_at": "2026-09-05T00:00:30Z"},
            "commit_result": {"aborted_at": "2026-09-05T00:01:00Z", "reason": "legacy"},
            "run_binding": {
                "run_id": "run-20260905-self-event",
                "task_id": "task-01",
                "repository": "/repo",
                "policy_digest": key("policy"),
            },
            "journal_outbox": None,
        }
        current = copy.deepcopy(prior)
        current["last_event_at"] = "2026-09-05T00:02:00Z"
        current["inactive_after"] = "2026-09-06T00:02:00Z"
        event = {
            "sequence": 9,
            "prev_digest": key("prev"),
            "payload": {
                "at": "2026-09-05T00:02:00Z",
                "details": {"reason": "legacy"},
                "event": "abort_disposition_recorded",
                "state": copy.deepcopy(current),
            },
        }
        return prior, current, event

    def test_abort_disposition_self_event_admission_controls_are_load_bearing(self) -> None:
        """Bead forge-plugin-rtj: the self-event replays only from aborted, unchanged."""
        prior, current, event = self._self_event_fixture()
        self.assertTrue(builders._commit_transition_valid(event, prior, current))
        # Enum control: an unknown event name is refused.
        with mock.patch.object(
            builders, "_COMMIT_EVENT_NAMES",
            builders._COMMIT_EVENT_NAMES - {"abort_disposition_recorded"},
        ):
            self.assertFalse(builders._commit_transition_valid(event, prior, current))
        # Transition control: the self-event is admitted only from aborted.
        live_prior = {**copy.deepcopy(prior), "state": "authorized"}
        live_current = {**copy.deepcopy(current), "state": "authorized"}
        live_event = copy.deepcopy(event); live_event["payload"]["state"] = copy.deepcopy(live_current)
        self.assertFalse(builders._commit_transition_valid(live_event, live_prior, live_current))
        with mock.patch.dict(
            builders._COMMIT_STATE_TRANSITIONS, {"authorized": frozenset({"authorized"})}
        ):
            # Even with the table loosened, the event-specific branch refuses a
            # non-aborted prior: both controls are load-bearing.
            self.assertFalse(builders._commit_transition_valid(live_event, live_prior, live_current))
        # Top-level control: the self-event may change no state field.
        rewritten = copy.deepcopy(current)
        rewritten["commit_result"] = {"aborted_at": "2026-09-05T00:02:00Z", "reason": "rewritten"}
        rewritten_event = copy.deepcopy(event); rewritten_event["payload"]["state"] = copy.deepcopy(rewritten)
        self.assertFalse(builders._commit_transition_valid(rewritten_event, prior, rewritten))
        with mock.patch.dict(
            builders._COMMIT_EVENT_TOP_LEVEL_CHANGES,
            {"abort_disposition_recorded": frozenset({"commit_result"})},
        ):
            self.assertTrue(builders._commit_transition_valid(rewritten_event, prior, rewritten))

    def test_abort_disposition_self_event_source_fact_requires_aborted_unchanged_prior(self) -> None:
        prior, current, event = self._self_event_fixture()
        binding = {
            "candidate": {"kind": "staged-diff-sha256", "value": current["candidate"]["sha256"]},
            "review": None,
        }
        record = {"type": "decision", "outcome": "chain-abort"}
        self.assertTrue(
            builders._binding_matches_source_fact(binding, record, event, prior, current, family="commit")
        )
        # Prior must already be aborted for the self-event branch.
        live_prior = {**copy.deepcopy(prior), "state": "authorized"}
        self.assertFalse(
            builders._binding_matches_source_fact(binding, record, event, live_prior, current, family="commit")
        )
        # commit_result must be unchanged across the self-event.
        changed_prior = copy.deepcopy(prior)
        changed_prior["commit_result"] = {"aborted_at": "2026-09-05T00:00:59Z", "reason": "other"}
        self.assertFalse(
            builders._binding_matches_source_fact(binding, record, event, changed_prior, current, family="commit")
        )
        # A landed commit never carries an abort decision.
        landed = copy.deepcopy(current); landed["commit_result"] = {**current["commit_result"], "commit_sha": "1" * 40}
        landed_prior = copy.deepcopy(prior); landed_prior["commit_result"] = copy.deepcopy(landed["commit_result"])
        self.assertFalse(
            builders._binding_matches_source_fact(binding, record, event, landed_prior, landed, family="commit")
        )
        # The original chain_aborted branch still requires a transition into aborted.
        aborted_event = copy.deepcopy(event); aborted_event["payload"]["event"] = "chain_aborted"
        self.assertFalse(
            builders._binding_matches_source_fact(binding, record, aborted_event, prior, current, family="commit")
        )
        # Any other event name is refused for a chain-abort binding.
        other = copy.deepcopy(event); other["payload"]["event"] = "head_moved"
        self.assertFalse(
            builders._binding_matches_source_fact(binding, record, other, prior, current, family="commit")
        )

    def test_terminal_builder_accepts_only_explicit_absent_chain_tombstone(self) -> None:
        with self.api_environment():
            repo, run_id, run_binding = self._terminal_control_repo(
                "terminal-tombstone"
            )
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._append_test_landing(repo, run_id, chain_id)
            events_path = state_path.with_name(f"{chain_id}.events.jsonl")
            state_path.unlink()
            events_path.unlink()

            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-tombstone-absent"),
                    task="task-01",
                    status="complete",
                )

            tombstones = state_path.parent / "tombstones"
            tombstones.mkdir(mode=0o700)
            tombstone = {
                "schema": "forge-chain-tombstone/1",
                "chain_id": chain_id,
                "event": "frozen-abort",
                "reason": "operator quarantined exact chain artifacts",
                "recorded_at": "2026-08-31T12:00:00Z",
                "operator": {"host": "fixture", "pid": os.getpid(), "uid": os.geteuid()},
                "artifacts": {
                    "state": {"status": "absent"},
                    "events": {"status": "absent"},
                },
            }
            (tombstones / f"{chain_id}.json").write_bytes(
                journal._canonical_json_bytes(tombstone) + b"\n"
            )

            state_path.write_bytes(b"{}\n")
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-tombstone-partial"),
                    task="task-01",
                    status="complete",
                )
            state_path.unlink()

            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"tombstone"},
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-tombstone-disabled"),
                    task="task-01",
                    status="complete",
                )

            outcome = builders.task_finish(
                repo,
                run_id,
                idempotency_key=key("terminal-tombstone-enabled"),
                task="task-01",
                status="complete",
            )
            self.assertEqual(outcome.records[0]["status"], "complete")

    def test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine(self) -> None:
        with self.api_environment():
            repo, run_id, run_binding = self._terminal_control_repo(
                "terminal-captured-tombstone"
            )
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._append_test_landing(repo, run_id, chain_id)
            events_path = state_path.with_name(f"{chain_id}.events.jsonl")
            events_path.write_bytes(b"{malformed-event}\n")

            def captured(path: Path) -> dict[str, object]:
                raw = path.read_bytes()
                return {
                    "status": "captured",
                    "sha256": journal._sha256(raw),
                    "bytes": len(raw),
                }

            tombstones = state_path.parent / "tombstones"
            tombstones.mkdir(mode=0o700)
            tombstone = {
                "schema": "forge-chain-tombstone/1",
                "chain_id": chain_id,
                "event": "frozen-abort",
                "reason": "operator sealed the exact frozen chain artifacts",
                "recorded_at": "2026-08-31T12:00:00Z",
                "operator": {
                    "host": "fixture",
                    "pid": os.getpid(),
                    "uid": os.geteuid(),
                },
                "artifacts": {
                    "state": captured(state_path),
                    "events": captured(events_path),
                },
            }
            (tombstones / f"{chain_id}.json").write_bytes(
                journal._canonical_json_bytes(tombstone) + b"\n"
            )

            state_bytes = state_path.read_bytes()
            state_path.write_bytes(state_bytes + b" ")
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-captured-changed"),
                    task="task-01",
                    status="complete",
                )
            state_path.write_bytes(state_bytes)

            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"tombstone"},
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-captured-disabled"),
                    task="task-01",
                    status="complete",
                )

            finished = builders.task_finish(
                repo,
                run_id,
                idempotency_key=key("terminal-captured-enabled"),
                task="task-01",
                status="complete",
            )
            self.assertEqual(finished.records[0]["status"], "complete")

            state_path.unlink()
            events_path.unlink()
            closed = builders.run_close(
                repo,
                run_id,
                idempotency_key=key("terminal-captured-quarantined"),
                judgment="blocked",
                summary="Frozen chain was explicitly sealed and quarantined",
                risks=[],
                follow_ups=[],
            )
            self.assertEqual(closed.records[0]["type"], "run_closed")

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

    @staticmethod
    def _activation_markers(
        records: list[dict[str, object]] | tuple[dict[str, object], ...],
    ) -> list[dict[str, object]]:
        return [
            record
            for record in records
            if journal._writer_activation_marker(record)
        ]

    @staticmethod
    def _run_file_bytes(run_dir: Path) -> dict[str, bytes]:
        return {
            path.name: path.read_bytes()
            for path in run_dir.iterdir()
            if path.is_file()
        }

    def _plant_unreplayable_unrelated_chain(self, repo: Path) -> None:
        members = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in UNREPLAYABLE_CHAIN_FIXTURE.iterdir()
            if path.is_file()
        }
        self.assertEqual(members, UNREPLAYABLE_CHAIN_FIXTURE_SHA256)
        chains_root = builders.chain_storage_root(repo)
        chains_root.mkdir(parents=True, exist_ok=True)
        for name in sorted(members, key=os.fsencode):
            shutil.copyfile(
                UNREPLAYABLE_CHAIN_FIXTURE / name,
                chains_root / name,
            )

    @staticmethod
    def _pad_valid_json_over_cap(path: Path, cap: int) -> None:
        raw = path.read_bytes()
        if len(raw) >= cap:
            raise AssertionError("fixture state already reaches the byte cap")
        path.write_bytes(raw + b" " * (cap + 2 - len(raw)))

    @contextmanager
    def _guard_activation_artifact_read_budget(
        self, target_name: str, byte_budget: int
    ):
        original_reader = builders._read_regular_bytes_at
        original_os_read = os.read
        totals: list[int] = []

        def monitored_reader(
            root_descriptor: int,
            name: str,
            *,
            cap: int | None = None,
        ) -> bytes:
            if name != target_name:
                return original_reader(root_descriptor, name, cap=cap)
            total = 0

            def counted_read(descriptor: int, requested: int) -> bytes:
                nonlocal total
                remaining = byte_budget + 2 - total
                if remaining <= 0:
                    raise AssertionError(
                        "activation artifact read crossed its cap-plus-one budget"
                    )
                chunk = original_os_read(
                    descriptor, min(requested, remaining)
                )
                total += len(chunk)
                if total > byte_budget + 1:
                    raise AssertionError(
                        "activation artifact read crossed its cap-plus-one budget"
                    )
                return chunk

            try:
                with mock.patch.object(
                    builders.os, "read", side_effect=counted_read
                ):
                    return original_reader(
                        root_descriptor, name, cap=cap
                    )
            finally:
                totals.append(total)

        with mock.patch.object(
            builders,
            "_read_regular_bytes_at",
            side_effect=monitored_reader,
        ):
            yield totals

    def _assert_first_batch_artifact_substitution_refuses(
        self, target_name: str
    ) -> None:
        label = target_name.strip(".").replace(".", "-")
        repo, _ = self._new_repo(f"repo-create-open-{label}")
        run_id = f"run-20260910-create-open-{key(target_name)[:8]}"
        with self.api_environment():
            self._open_legacy_run(repo, run_id)
            run_dir = self.run_dir(repo, run_id)
            if target_name == journal.BATCH_RECEIPTS_NAME:
                with batch.batch_lock(run_dir, create=True):
                    pass
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            displaced_name = f"{target_name}.displaced-original"
            observations: dict[str, journal.FileObservation] = {}
            original_create = batch._create_empty_at

            def substitute_after_create(
                directory_descriptor: int, name: str
            ) -> journal.FileObservation:
                created = original_create(directory_descriptor, name)
                if name != target_name:
                    return created
                os.rename(
                    name,
                    displaced_name,
                    src_dir_fd=directory_descriptor,
                    dst_dir_fd=directory_descriptor,
                )
                replacement = original_create(directory_descriptor, name)
                observations["created"] = created
                observations["replacement"] = replacement
                return created

            with mock.patch.object(
                batch,
                "_create_empty_at",
                side_effect=substitute_after_create,
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.BATCH_DIVERGED,
            ):
                self.start_task(repo, run_id)

            replacement_path = run_dir / target_name
            displaced_path = run_dir / displaced_name
            self.assertEqual(replacement_path.read_bytes(), b"")
            self.assertEqual(displaced_path.read_bytes(), b"")
            self.assertEqual(
                journal._file_observation(os.lstat(replacement_path)),
                observations["replacement"],
            )
            self.assertEqual(
                journal._file_observation(os.lstat(displaced_path)),
                observations["created"],
            )
            self.assertNotEqual(
                observations["created"], observations["replacement"]
            )
            self.assertEqual(
                (run_dir / "journal.jsonl").read_bytes(), journal_before
            )
            self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

    def test_batch_lock_create_open_substitution_refuses(self) -> None:
        self._assert_first_batch_artifact_substitution_refuses(
            journal.BATCH_LOCK_NAME
        )

    def test_first_receipt_ledger_create_open_substitution_refuses(self) -> None:
        self._assert_first_batch_artifact_substitution_refuses(
            journal.BATCH_RECEIPTS_NAME
        )

    def test_first_receipt_ledger_post_create_substitution_refuses(self) -> None:
        repo, _ = self._new_repo("repo-receipt-post-create-substitution")
        run_id = "run-20260910-receipt-post-create-substitution"
        with self.api_environment():
            self._open_legacy_run(repo, run_id)
            run_dir = self.run_dir(repo, run_id)
            with batch.batch_lock(run_dir, create=True):
                pass
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            displaced_name = (
                f"{journal.BATCH_RECEIPTS_NAME}.displaced-original"
            )
            observations: dict[str, journal.FileObservation] = {}
            original_ensure = batch._ensure_receipt_ledger

            def substitute_after_ensure(
                locked: batch.BatchLock, *, allow_preintent: bool = False
            ) -> journal.FileObservation:
                created = original_ensure(
                    locked, allow_preintent=allow_preintent
                )
                os.rename(
                    journal.BATCH_RECEIPTS_NAME,
                    displaced_name,
                    src_dir_fd=locked.run_descriptor,
                    dst_dir_fd=locked.run_descriptor,
                )
                replacement = batch._create_empty_at(
                    locked.run_descriptor, journal.BATCH_RECEIPTS_NAME
                )
                observations["created"] = created
                observations["replacement"] = replacement
                return created

            with mock.patch.object(
                batch,
                "_ensure_receipt_ledger",
                side_effect=substitute_after_ensure,
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.BATCH_DIVERGED,
            ):
                self.start_task(repo, run_id)

            replacement_path = run_dir / journal.BATCH_RECEIPTS_NAME
            displaced_path = run_dir / displaced_name
            self.assertEqual(replacement_path.read_bytes(), b"")
            self.assertEqual(displaced_path.read_bytes(), b"")
            self.assertEqual(
                journal._file_observation(os.lstat(replacement_path)),
                observations["replacement"],
            )
            self.assertEqual(
                journal._file_observation(os.lstat(displaced_path)),
                observations["created"],
            )
            self.assertNotEqual(
                observations["created"], observations["replacement"]
            )
            self.assertEqual(
                (run_dir / "journal.jsonl").read_bytes(), journal_before
            )
            self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

    def _activation_outbox_case(
        self, name: str
    ) -> tuple[
        Path,
        str,
        Path,
        bytes,
        str,
        str,
        tuple[dict[str, object], ...],
    ]:
        repo, _ = self._new_repo(name)
        run_id = f"run-20260910-{name}"
        self._open_legacy_run(repo, run_id)
        run_dir = self.run_dir(repo, run_id)
        journal_path = run_dir / "journal.jsonl"
        journal.append_owned_record(
            journal_path,
            {
                "type": "task",
                "id": "task-01",
                "status": "active",
                "goal": "Drain the activation-bearing chain outbox",
                "acceptance": ["The durable outbox reserves first use"],
                "files": ["src/example.py"],
                "run_id": run_id,
                "recorded_at": "2026-08-28T12:01:00Z",
            },
        )
        legacy_prefix = journal_path.read_bytes()
        with batch.batch_lock(run_dir, create=True) as locked:
            batch._ensure_receipt_ledger(locked)
            state = journal._scan_run(run_dir)
            marker = builders._writer_activation_decision(
                state,
                receipt_origin_size=len(legacy_prefix),
                receipt_origin_sha256=journal._sha256(legacy_prefix),
                recorded_at="2026-08-28T12:03:00Z",
            )

        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key(f"{name}-policy"),
        }
        chain_id, state_path = self._write_bound_chain_state(
            repo,
            run_id,
            run_binding=run_binding,
            outbox={"fixture": True},
            activation_marker=marker,
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
        carried_batch = carrier["journal_batch"]
        assert isinstance(carried_batch, dict)
        raw_records = carried_batch["records"]
        assert isinstance(raw_records, list)
        records = tuple(copy.deepcopy(raw_records))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0], marker)
        self.assertTrue(journal._writer_activation_marker(records[0]))
        self.assertEqual(records[1]["type"], "verification")
        return (
            repo,
            run_id,
            state_path,
            legacy_prefix,
            chain_id,
            str(carrier["source_event_digest"]),
            records,
        )

    def _compete_with_activation_outbox(
        self, repo: Path, run_id: str, label: str
    ) -> batch.BatchOutcome:
        return builders.verification_add(
            repo,
            run_id,
            idempotency_key=key(f"{run_id}-{label}"),
            task="task-01",
            criterion="activation outbox first-use reservation",
            method="unittest",
            check="focused activation outbox test",
            result="passed",
            observation="The competing typed mutation must not commit",
            evidence=[],
            binding_chain=None,
            binding_id=None,
        )

    def _invoke_raw_lifecycle(
        self, repo: Path, run_id: str, operation: str
    ) -> None:
        if operation == "readmit":
            journal.readmit_run(repo, run_id, ["src/**"])
            return
        if operation == "retire":
            journal.retire_run(repo, run_id)
            return
        self.assertEqual(operation, "close")
        run_dir = self.run_dir(repo, run_id)
        journal.close_run(
            repo,
            run_id,
            {
                "type": "run_closed",
                "recorded_at": "2026-09-10T03:20:01Z",
                "run_id": run_id,
                "judgment": "blocked",
                "summary": "Pending activation retains first-use authority",
                "validation": journal.validate_run(run_dir, gates=True),
                "risks": [],
                "follow_ups": [],
            },
        )

    def _bound_chain_outbox(
        self, repo: Path, chain_id: str
    ) -> tuple[str, tuple[dict[str, object], ...]]:
        events_path = (
            builders.chain_storage_root(repo) / f"{chain_id}.events.jsonl"
        )
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
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
        return (
            str(carrier["source_event_digest"]),
            tuple(copy.deepcopy(raw_records)),
        )

    def _acknowledge_bound_chain(
        self,
        repo: Path,
        chain_id: str,
        state_path: Path,
        receipt: dict[str, object],
    ) -> None:
        chains_root = builders.chain_storage_root(repo)
        events_path = chains_root / f"{chain_id}.events.jsonl"
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
        ]
        state = json.loads(state_path.read_bytes())
        pending = state["journal_outbox"]
        assert isinstance(pending, dict)
        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-08-28T12:04:00Z"
        state["journal_outbox"] = None
        unsigned = {
            "sequence": len(events) + 1,
            "prev_digest": events[-1]["digest"],
            "payload": {
                "at": state["last_event_at"],
                "details": batch.journal_receipted_details(
                    pending, receipt
                ),
                "event": "journal_receipted",
                "state": copy.deepcopy(state),
            },
        }
        event = {
            **unsigned,
            "digest": journal._sha256(
                journal._canonical_json_bytes(unsigned)
            ),
        }
        events.append(event)
        events_path.write_bytes(
            b"".join(
                journal._canonical_json_bytes(item) + b"\n"
                for item in events
            )
        )
        state_path.write_bytes(
            journal._canonical_json_bytes(state) + b"\n"
        )

    def _legacy_receipted_chain_case(
        self,
        repo: Path,
        run_id: str,
        *,
        chain_id: str,
        scope: str,
        task_file: str,
    ) -> tuple[str, str, tuple[dict[str, object], ...]]:
        self._open_legacy_run(repo, run_id, scope=[scope])
        _repository, state_root = journal._resolve_repository(
            repo, "journal append"
        )
        run_dir = state_root / ".codex-orchestrator/runs" / run_id
        journal_path = run_dir / "journal.jsonl"
        journal.append_owned_record(
            journal_path,
            {
                "type": "task",
                "id": "task-01",
                "status": "active",
                "goal": "Preserve one historical chain receipt",
                "acceptance": ["Later activation cannot cross-lock runs"],
                "files": [task_file],
                "run_id": run_id,
                "recorded_at": "2026-08-28T12:01:00Z",
            },
        )
        historical_prefix = journal_path.read_bytes()
        with batch.batch_lock(run_dir, create=True) as locked:
            batch._ensure_receipt_ledger(locked)
        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key(f"{chain_id}-policy"),
        }
        _chain_id, state_path = self._write_bound_chain_state(
            repo,
            run_id,
            chain_id=chain_id,
            run_binding=run_binding,
            outbox={"fixture": True},
        )
        self.assertEqual(_chain_id, chain_id)
        source_digest, records = self._bound_chain_outbox(repo, chain_id)
        batch_bytes = b"".join(
            journal._journal_line(record) for record in records
        )
        inputs = {
            "chain_id": chain_id,
            "source_event_digest": source_digest,
            "batch_digest": journal._sha256(batch_bytes),
            "record_count": len(records),
        }
        _, request_sha256 = batch.normalized_request(
            repo.resolve(), run_id, "chain outbox-drain", inputs
        )
        journal_bytes = historical_prefix + batch_bytes
        journal_path.write_bytes(journal_bytes)
        receipt = {
            "schema": journal.BATCH_RECEIPT_SCHEMA,
            "idempotency_key": source_digest,
            "request_sha256": request_sha256,
            "base_size": len(historical_prefix),
            "batch_sha256": journal._sha256(batch_bytes),
            "record_count": len(records),
            "journal_size": len(journal_bytes),
            "journal_sha256": journal._sha256(journal_bytes),
            "recorded_at": "2026-08-28T12:03:00Z",
        }
        (run_dir / journal.BATCH_RECEIPTS_NAME).write_bytes(
            journal._canonical_json_bytes(receipt) + b"\n"
        )
        self._acknowledge_bound_chain(
            repo, chain_id, state_path, receipt
        )
        binding = records[0]["binding"]
        assert isinstance(binding, dict)
        return source_digest, str(binding["binding_id"]), records

    def test_activation_scan_tolerates_unreplayable_unrelated_chain(self) -> None:
        warning = (
            "forge: warning — skipped unreadable chain "
            f"{UNREPLAYABLE_CHAIN_ID} while enumerating commit chains\n"
        )
        for operation in ("typed", "raw-append", "close", "retire", "readmit"):
            with self.subTest(operation=operation), self.api_environment():
                repo, _ = self._new_repo(f"repo-unreplayable-{operation}")
                run_id = f"run-20260910-unreplayable-{operation}"
                self._open_legacy_run(repo, run_id)
                self._plant_unreplayable_unrelated_chain(repo)
                run_dir = self.run_dir(repo, run_id)
                captured = io.StringIO()

                with redirect_stderr(captured):
                    if operation == "typed":
                        outcome = self.start_task(repo, run_id)
                        self.assertTrue(
                            journal._writer_activation_marker(outcome.records[0])
                        )
                    elif operation == "raw-append":
                        journal.append_owned_record(
                            run_dir / "journal.jsonl",
                            {
                                "type": "decision",
                                "id": "decision-01",
                                "resolution": "Unrelated history does not wedge raw append",
                                "basis": [],
                                "run_id": run_id,
                                "recorded_at": "2026-09-10T04:30:00Z",
                            },
                        )
                    else:
                        self._invoke_raw_lifecycle(repo, run_id, operation)

                self.assertEqual(captured.getvalue(), warning)
                state = journal._scan_run(run_dir)
                if operation == "raw-append":
                    self.assertEqual(
                        state.records[-1]["resolution"],
                        "Unrelated history does not wedge raw append",
                    )
                elif operation == "close":
                    self.assertEqual(state.close_judgment, "blocked")
                elif operation == "retire":
                    self.assertTrue(state.was_retired)
                elif operation == "readmit":
                    self.assertEqual(state.scope, ("src/**",))

    def test_activation_scan_warns_and_continues_on_oversized_unrelated_state(
        self,
    ) -> None:
        repo, _ = self._new_repo("repo-oversized-unrelated-state")
        run_id = "run-20260910-oversized-unrelated-state"
        chain_id = "c-2026-09-10T043000Z-a107"
        foreign_binding = {
            "run_id": "run-20260910-foreign-state-owner",
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key("oversized-unrelated-policy"),
        }
        with self.api_environment():
            self._open_legacy_run(repo, run_id)
            _chain_id, state_path = self._write_bound_chain_state(
                repo,
                run_id,
                chain_id=chain_id,
                run_binding=foreign_binding,
            )
            self.assertEqual(_chain_id, chain_id)
            self._pad_valid_json_over_cap(
                state_path, builders._ACTIVATION_STATE_CAP_BYTES
            )
            self.assertEqual(
                state_path.stat().st_size,
                builders._ACTIVATION_STATE_CAP_BYTES + 2,
            )
            captured = io.StringIO()

            with self._guard_activation_artifact_read_budget(
                state_path.name,
                builders._ACTIVATION_STATE_CAP_BYTES,
            ) as read_totals, redirect_stderr(captured):
                outcome = self.start_task(repo, run_id)

            self.assertTrue(
                journal._writer_activation_marker(outcome.records[0])
            )
            self.assertEqual(
                captured.getvalue(),
                "forge: warning — skipped unreadable chain "
                f"{chain_id} while enumerating commit chains\n",
            )
            self.assertEqual(
                read_totals,
                [
                    builders._ACTIVATION_STATE_CAP_BYTES + 1,
                    builders._ACTIVATION_STATE_CAP_BYTES + 1,
                ],
            )

    def test_activation_scan_refuses_oversized_state_bound_to_this_run(
        self,
    ) -> None:
        repo, _ = self._new_repo("repo-oversized-current-state")
        run_id = "run-20260910-oversized-current-state"
        chain_id = "c-2026-09-10T043000Z-a108"
        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key("oversized-current-policy"),
        }
        with self.api_environment():
            self._open_legacy_run(repo, run_id)
            _chain_id, state_path = self._write_bound_chain_state(
                repo,
                run_id,
                chain_id=chain_id,
                run_binding=run_binding,
            )
            self.assertEqual(_chain_id, chain_id)
            self._pad_valid_json_over_cap(
                state_path, builders._ACTIVATION_STATE_CAP_BYTES
            )
            run_dir = self.run_dir(repo, run_id)
            journal_path = run_dir / "journal.jsonl"
            journal_before = journal_path.read_bytes()

            with self._guard_activation_artifact_read_budget(
                state_path.name,
                builders._ACTIVATION_STATE_CAP_BYTES,
            ) as read_totals, self.assertRaises(
                journal.CoordinationRefusal
            ) as raised:
                self.start_task(repo, run_id)

            self.assertEqual(str(raised.exception), journal.BATCH_DIVERGED)
            self.assertEqual(
                read_totals,
                [builders._ACTIVATION_STATE_CAP_BYTES + 1],
            )
            self.assertEqual(journal_path.read_bytes(), journal_before)
            self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

    def test_activation_state_byte_cap_is_load_bearing_in_memory(self) -> None:
        repo, _ = self._new_repo("repo-oversized-state-cap-disabled")
        run_id = "run-20260910-oversized-state-cap-disabled"
        chain_id = "c-2026-09-10T043000Z-a109"
        foreign_binding = {
            "run_id": "run-20260910-foreign-cap-owner",
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key("oversized-disabled-policy"),
        }
        with self.api_environment():
            self._open_legacy_run(repo, run_id)
            _chain_id, state_path = self._write_bound_chain_state(
                repo,
                run_id,
                chain_id=chain_id,
                run_binding=foreign_binding,
            )
            self.assertEqual(_chain_id, chain_id)
            self._pad_valid_json_over_cap(
                state_path, builders._ACTIVATION_STATE_CAP_BYTES
            )
            byte_budget = builders._ACTIVATION_STATE_CAP_BYTES

            with mock.patch.object(
                builders, "_ACTIVATION_STATE_CAP_BYTES", None
            ), self._guard_activation_artifact_read_budget(
                state_path.name, byte_budget
            ) as read_totals, self.assertRaisesRegex(
                AssertionError,
                "activation artifact read crossed its cap-plus-one budget",
            ):
                builders._require_no_pending_activation_outbox(repo, run_id)

            self.assertEqual(read_totals, [byte_budget + 2])

    def test_activation_scan_refuses_oversized_bound_events_at_cap_plus_one(
        self,
    ) -> None:
        repo, _ = self._new_repo("repo-oversized-bound-events")
        run_id = "run-20260910-oversized-bound-events"
        chain_id = "c-2026-09-10T043000Z-a111"
        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key("oversized-bound-events-policy"),
        }
        with self.api_environment():
            self._open_legacy_run(repo, run_id)
            self._write_bound_chain_state(
                repo,
                run_id,
                chain_id=chain_id,
                run_binding=run_binding,
            )
            events_path = (
                builders.chain_storage_root(repo)
                / f"{chain_id}.events.jsonl"
            )
            with events_path.open("r+b") as stream:
                stream.seek(builders._ACTIVATION_EVENTS_CAP_BYTES + 1)
                stream.write(b"\n")
            self.assertEqual(
                events_path.stat().st_size,
                builders._ACTIVATION_EVENTS_CAP_BYTES + 2,
            )
            run_dir = self.run_dir(repo, run_id)
            journal_path = run_dir / "journal.jsonl"
            journal_before = journal_path.read_bytes()

            with self._guard_activation_artifact_read_budget(
                events_path.name,
                builders._ACTIVATION_EVENTS_CAP_BYTES,
            ) as read_totals, self.assertRaises(
                journal.CoordinationRefusal
            ) as raised:
                self.start_task(repo, run_id)

            self.assertEqual(str(raised.exception), journal.BATCH_DIVERGED)
            self.assertEqual(
                read_totals,
                [builders._ACTIVATION_EVENTS_CAP_BYTES + 1],
            )
            self.assertEqual(journal_path.read_bytes(), journal_before)
            self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

    def test_activation_events_byte_cap_is_load_bearing_in_memory(self) -> None:
        repo, _ = self._new_repo("repo-oversized-events-cap-disabled")
        run_id = "run-20260910-oversized-events-cap-disabled"
        chain_id = "c-2026-09-10T043000Z-a112"
        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key("oversized-events-disabled-policy"),
        }
        with self.api_environment():
            self._open_legacy_run(repo, run_id)
            self._write_bound_chain_state(
                repo,
                run_id,
                chain_id=chain_id,
                run_binding=run_binding,
            )
            events_path = (
                builders.chain_storage_root(repo)
                / f"{chain_id}.events.jsonl"
            )
            byte_budget = builders._ACTIVATION_EVENTS_CAP_BYTES
            with events_path.open("r+b") as stream:
                stream.seek(byte_budget + 1)
                stream.write(b"\n")

            with mock.patch.object(
                builders, "_ACTIVATION_EVENTS_CAP_BYTES", None
            ), self._guard_activation_artifact_read_budget(
                events_path.name, byte_budget
            ) as read_totals, self.assertRaisesRegex(
                AssertionError,
                "activation artifact read crossed its cap-plus-one budget",
            ):
                builders._require_no_pending_activation_outbox(repo, run_id)

            self.assertEqual(read_totals, [byte_budget + 2])

    def test_activation_scan_converts_bounded_path_memory_errors(self) -> None:
        chain_id = "c-2026-09-10T043000Z-a113"
        with mock.patch.object(
            builders,
            "_activation_event_one_binding_authority_unchecked",
            side_effect=MemoryError,
        ):
            self.assertIsNone(
                builders._activation_event_one_binding_authority(-1, chain_id)
            )

        repo, _ = self._new_repo("repo-activation-replay-memory-error")
        run_id = "run-20260910-activation-replay-memory-error"
        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key("activation-replay-memory-policy"),
        }
        with self.api_environment():
            self._open_legacy_run(repo, run_id)
            self._write_bound_chain_state(
                repo,
                run_id,
                chain_id=chain_id,
                run_binding=run_binding,
            )
            journal_path = self.run_dir(repo, run_id) / "journal.jsonl"
            journal_before = journal_path.read_bytes()

            with mock.patch.object(
                builders,
                "_resolve_binding_from_descriptor",
                side_effect=MemoryError,
            ), self.assertRaises(journal.CoordinationRefusal) as raised:
                self.start_task(repo, run_id)

            self.assertEqual(str(raised.exception), journal.BATCH_DIVERGED)
            self.assertEqual(journal_path.read_bytes(), journal_before)

    def test_activation_replay_passes_scan_only_state_and_event_caps(self) -> None:
        repo, _ = self._new_repo("repo-activation-replay-caps")
        run_id = "run-20260910-activation-replay-caps"
        chain_id = "c-2026-09-10T043000Z-a110"
        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key("activation-replay-caps-policy"),
        }
        with self.api_environment():
            self._open_legacy_run(repo, run_id)
            self._write_bound_chain_state(
                repo,
                run_id,
                chain_id=chain_id,
                run_binding=run_binding,
            )
            observed: list[tuple[str, int | None]] = []
            original_reader = builders._read_regular_bytes_at

            def observe_reader(
                root_descriptor: int,
                name: str,
                *,
                cap: int | None = None,
            ) -> bytes:
                if name.startswith(chain_id):
                    observed.append((name, cap))
                return original_reader(root_descriptor, name, cap=cap)

            with mock.patch.object(
                builders,
                "_read_regular_bytes_at",
                side_effect=observe_reader,
            ), mock.patch.object(
                builders,
                "_resolve_tombstone_abort_binding",
                side_effect=AssertionError(
                    "activation replay reached the unbounded tombstone path"
                ),
            ) as tombstone_resolver:
                outcome = self.start_task(repo, run_id)

            self.assertTrue(
                journal._writer_activation_marker(outcome.records[0])
            )
            tombstone_resolver.assert_not_called()
            self.assertEqual(
                observed,
                [
                    (
                        f"{chain_id}.json",
                        builders._ACTIVATION_STATE_CAP_BYTES,
                    ),
                    (
                        f"{chain_id}.events.jsonl",
                        builders._ACTIVATION_EVENTS_CAP_BYTES,
                    ),
                    (
                        f"{chain_id}.json",
                        builders._ACTIVATION_STATE_CAP_BYTES,
                    ),
                    (
                        f"{chain_id}.json",
                        builders._ACTIVATION_STATE_CAP_BYTES,
                    ),
                ],
            )

    def test_activation_scan_unrelated_tolerance_is_load_bearing(self) -> None:
        repo, _ = self._new_repo("repo-unreplayable-disabled")
        run_id = "run-20260910-unreplayable-disabled"
        with self.api_environment():
            self._open_legacy_run(repo, run_id)
            self._plant_unreplayable_unrelated_chain(repo)
            journal_path = self.run_dir(repo, run_id) / "journal.jsonl"
            before = journal_path.read_bytes()

            with mock.patch.object(
                builders,
                "_activation_chain_bound_to_run",
                return_value=True,
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.BATCH_DIVERGED,
            ):
                self.start_task(repo, run_id)

            self.assertEqual(journal_path.read_bytes(), before)

    def test_activation_scan_ignores_unrelated_chain_created_between_scans(
        self,
    ) -> None:
        repo, _ = self._new_repo("repo-activation-scan-race")
        run_id = "run-20260910-activation-scan-race"
        concurrent_chain = "c-2026-09-10T043000Z-a104"
        with self.api_environment():
            self._open_legacy_run(repo, run_id)
            chains_root = builders.chain_storage_root(repo)
            chains_root.mkdir(parents=True, exist_ok=True)
            original_names = builders._activation_chain_names
            scans = 0

            def names_with_unrelated_start(descriptor: int) -> tuple[str, ...]:
                nonlocal scans
                scans += 1
                if scans == 2:
                    (chains_root / f"{concurrent_chain}.json").write_bytes(
                        journal._canonical_json_bytes(
                            {
                                "schema": "forge-chain/1",
                                "chain_id": concurrent_chain,
                                "kind": "commit",
                                "run_binding": None,
                                "journal_outbox": None,
                            }
                        )
                        + b"\n"
                    )
                    (
                        chains_root / f"{concurrent_chain}.events.jsonl"
                    ).write_bytes(b"")
                return original_names(descriptor)

            captured = io.StringIO()
            with mock.patch.object(
                builders,
                "_activation_chain_names",
                side_effect=names_with_unrelated_start,
            ), redirect_stderr(captured):
                outcome = self.start_task(repo, run_id)

            self.assertEqual(scans, 2)
            self.assertTrue(
                journal._writer_activation_marker(outcome.records[0])
            )
            self.assertEqual(
                captured.getvalue(),
                "forge: warning — skipped unreadable chain "
                f"{concurrent_chain} while enumerating commit chains\n",
            )

    def test_activation_scan_bound_chain_created_between_scans_refuses(
        self,
    ) -> None:
        for control_disabled in (False, True):
            with self.subTest(control_disabled=control_disabled), self.api_environment():
                suffix = "disabled" if control_disabled else "enforced"
                repo, _ = self._new_repo(f"repo-activation-bound-race-{suffix}")
                run_id = f"run-20260910-activation-bound-race-{suffix}"
                concurrent_chain = (
                    "c-2026-09-10T043100Z-a106"
                    if control_disabled
                    else "c-2026-09-10T043100Z-a105"
                )
                self._open_legacy_run(repo, run_id)
                chains_root = builders.chain_storage_root(repo)
                chains_root.mkdir(parents=True, exist_ok=True)
                original_names = builders._activation_chain_names
                scans = 0

                def names_with_bound_start(descriptor: int) -> tuple[str, ...]:
                    nonlocal scans
                    scans += 1
                    if scans == 2:
                        binding = {
                            "run_id": run_id,
                            "task_id": "task-01",
                            "repository": str(repo.resolve()),
                            "policy_digest": key(
                                f"activation-bound-race-{suffix}"
                            ),
                        }
                        (chains_root / f"{concurrent_chain}.json").write_bytes(
                            journal._canonical_json_bytes(
                                {
                                    "schema": "forge-chain/1",
                                    "chain_id": concurrent_chain,
                                    "kind": "commit",
                                    "run_binding": binding,
                                    "journal_outbox": None,
                                }
                            )
                            + b"\n"
                        )
                        (
                            chains_root / f"{concurrent_chain}.events.jsonl"
                        ).write_bytes(b"")
                    return original_names(descriptor)

                journal_path = self.run_dir(repo, run_id) / "journal.jsonl"
                before = journal_path.read_bytes()
                stability_control = (
                    mock.patch.object(
                        builders,
                        "_activation_bound_set_stable",
                        return_value=True,
                    )
                    if control_disabled
                    else nullcontext()
                )
                with mock.patch.object(
                    builders,
                    "_activation_chain_names",
                    side_effect=names_with_bound_start,
                ), stability_control as disabled_control:
                    if control_disabled:
                        outcome = self.start_task(repo, run_id)
                    else:
                        with self.assertRaisesRegex(
                            journal.CoordinationRefusal,
                            journal.BATCH_DIVERGED,
                        ):
                            self.start_task(repo, run_id)

                self.assertEqual(scans, 2)
                if control_disabled:
                    disabled_control.assert_called_once()
                    self.assertTrue(
                        journal._writer_activation_marker(outcome.records[0])
                    )
                else:
                    self.assertEqual(journal_path.read_bytes(), before)

    def test_activation_scan_skips_external_sibling_chain_and_run_lock(
        self,
    ) -> None:
        linked = Path(self.temporary.name) / "linked-activation-sibling"
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "worktree",
                "add",
                "--detach",
                "--quiet",
                str(linked),
                "HEAD",
            ],
            check=True,
        )
        sibling_run = "run-20260910-linked-sibling-receipt"
        sibling_chain = "c-2026-09-10T040000Z-a101"
        current_run = "run-20260910-current-legacy-scan"
        with self.api_environment():
            _source, binding_id, _records = (
                self._legacy_receipted_chain_case(
                    linked,
                    sibling_run,
                    chain_id=sibling_chain,
                    scope="src/**",
                    task_file="src/example.py",
                )
            )
            resolved = builders.resolve_binding(
                linked,
                sibling_chain,
                binding_id,
                expected_type="verification",
                expected_fields={
                    "task": "task-01",
                    "criterion": "gate-1: terminal fixture",
                    "result": "passed",
                },
                expected_run_id=sibling_run,
                expected_task_id="task-01",
            )
            self.assertEqual(resolved["binding_id"], binding_id)
            self._open_legacy_run(
                self.repo, current_run, scope=["docs/**"]
            )

            original_lock = batch.batch_lock
            lock_targets: list[str] = []

            @contextmanager
            def probed_lock(run_dir: Path, *, create: bool):
                target = Path(run_dir).name
                lock_targets.append(target)
                if target == sibling_run:
                    raise AssertionError("sibling run lock was acquired")
                with original_lock(run_dir, create=create) as locked:
                    yield locked

            original_resolver = builders._resolve_binding_from_descriptor
            with mock.patch.object(
                batch, "batch_lock", side_effect=probed_lock
            ), mock.patch.object(
                builders,
                "_verify_receipted_batch",
                side_effect=AssertionError(
                    "sibling receipt was externally rederived"
                ),
            ) as external, mock.patch.object(
                builders,
                "_resolve_binding_from_descriptor",
                wraps=original_resolver,
            ) as resolver:
                activated = builders.task_start(
                    self.repo,
                    current_run,
                    idempotency_key=key("current-legacy-scan-task"),
                    task="task-01",
                    goal="Activate without locking the sibling run",
                    acceptance=["Only self-contained sibling replay occurs"],
                    files=["docs/example.md"],
                )

            external.assert_not_called()
            self.assertNotIn(sibling_run, lock_targets)
            resolver.assert_not_called()
            self.assertTrue(
                journal._writer_activation_marker(activated.records[0])
            )

    def test_concurrent_legacy_activation_never_cross_acquires_run_locks(
        self,
    ) -> None:
        linked = Path(self.temporary.name) / "linked-activation-peer"
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "worktree",
                "add",
                "--detach",
                "--quiet",
                str(linked),
                "HEAD",
            ],
            check=True,
        )
        cases = (
            (
                self.repo,
                "run-20260910-concurrent-legacy-a",
                "c-2026-09-10T040100Z-a102",
                "src/a/**",
                "src/a/example.py",
            ),
            (
                linked,
                "run-20260910-concurrent-legacy-b",
                "c-2026-09-10T040200Z-a103",
                "src/b/**",
                "src/b/example.py",
            ),
        )
        with self.api_environment():
            for repo, run_id, chain_id, scope, task_file in cases:
                self._legacy_receipted_chain_case(
                    repo,
                    run_id,
                    chain_id=chain_id,
                    scope=scope,
                    task_file=task_file,
                )

            original_lock = batch.batch_lock
            rendezvous = threading.Barrier(2, timeout=5)
            local = threading.local()
            cross_acquisitions: list[tuple[str, str]] = []

            @contextmanager
            def probed_lock(run_dir: Path, *, create: bool):
                target = Path(run_dir).name
                held = getattr(local, "run_id", None)
                if held is not None and target != held:
                    cross_acquisitions.append((held, target))
                    raise AssertionError(
                        f"cross-run lock acquisition: {held} -> {target}"
                    )
                outer = held is None and target in {
                    case[1] for case in cases
                }
                if outer:
                    local.run_id = target
                try:
                    with original_lock(run_dir, create=create) as locked:
                        if outer:
                            rendezvous.wait()
                        yield locked
                finally:
                    if outer:
                        del local.run_id

            outcomes: dict[str, batch.BatchOutcome] = {}
            failures: list[BaseException] = []

            def activate(repo: Path, run_id: str) -> None:
                try:
                    outcomes[run_id] = builders.verification_add(
                        repo,
                        run_id,
                        idempotency_key=key(f"{run_id}-concurrent-activation"),
                        task="task-01",
                        criterion="concurrent activation lock order",
                        method="unittest",
                        check="bounded lock probe",
                        result="passed",
                        observation="No foreign run lock is acquired",
                        evidence=[],
                        binding_chain=None,
                        binding_id=None,
                    )
                except BaseException as exc:
                    failures.append(exc)

            original_resolver = builders._resolve_binding_from_descriptor
            with mock.patch.object(
                batch, "batch_lock", side_effect=probed_lock
            ), mock.patch.object(
                builders,
                "_resolve_binding_from_descriptor",
                wraps=original_resolver,
            ) as resolver:
                threads = [
                    threading.Thread(
                        target=activate,
                        args=(repo, run_id),
                        daemon=True,
                    )
                    for repo, run_id, _chain, _scope, _task_file in cases
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=10)

            self.assertFalse(
                any(thread.is_alive() for thread in threads),
                "concurrent activation exceeded its bounded join",
            )
            self.assertEqual(failures, [])
            self.assertEqual(cross_acquisitions, [])
            self.assertEqual(set(outcomes), {case[1] for case in cases})
            external_modes = [
                call.kwargs.get("verify_external")
                for call in resolver.call_args_list
            ]
            self.assertEqual(external_modes, [None, None])
            for outcome in outcomes.values():
                self.assertTrue(
                    journal._writer_activation_marker(outcome.records[0])
                )

    def test_id_only_legacy_opening_activates_with_matching_marker_run_id(
        self,
    ) -> None:
        run_id = "run-20260910-id-only-legacy-activation"
        opening = {
            "type": "run_started",
            "id": run_id,
            "goal": "legacy identity is keyed only by id",
        }
        with self.api_environment():
            run_dir = self.run_dir(self.repo, run_id)
            run_dir.mkdir(parents=True)
            opening_bytes = journal._canonical_json_bytes(opening) + b"\n"
            journal_path = run_dir / "journal.jsonl"
            journal_path.write_bytes(opening_bytes)

            started = self.start_task(self.repo, run_id)

            self.assertFalse(started.repeated)
            self.assertEqual(len(started.records), 2)
            marker, task = started.records
            self.assertTrue(journal._writer_activation_marker(marker))
            self.assertEqual(marker["run_id"], run_id)
            self.assertEqual(marker["receipt_origin_size"], len(opening_bytes))
            self.assertEqual(
                marker["receipt_origin_sha256"],
                journal._sha256(opening_bytes),
            )
            self.assertEqual(task["type"], "task")
            persisted = journal_path.read_bytes()
            self.assertEqual(persisted[: len(opening_bytes)], opening_bytes)
            self.assertEqual(json.loads(persisted.splitlines()[0]), opening)
            self.assertNotIn("run_id", json.loads(persisted.splitlines()[0]))
            receipts = [
                json.loads(line)
                for line in (
                    run_dir / journal.BATCH_RECEIPTS_NAME
                ).read_bytes().splitlines()
            ]
            self.assertEqual(len(receipts), 1)
            self.assertEqual(receipts[0]["base_size"], len(opening_bytes))
            self.assertEqual(receipts[0]["record_count"], 2)

    def test_persisted_activation_candidate_requires_allocated_id_and_contract(
        self,
    ) -> None:
        for attack in ("non-allocated-id", "writer-contract-v2"):
            with self.subTest(attack=attack):
                repo, _ = self._new_repo(f"repo-persisted-{attack}")
                run_id = f"run-20260910-persisted-{attack}"
                with self.api_environment():
                    self._open_legacy_run(repo, run_id)
                    run_dir = self.run_dir(repo, run_id)
                    journal_path = run_dir / "journal.jsonl"
                    journal.append_owned_record(
                        journal_path,
                        {
                            "type": "decision",
                            "id": "decision-01",
                            "resolution": "Establish the prior allocation",
                            "basis": [],
                            "run_id": run_id,
                            "recorded_at": "2026-09-10T03:30:00Z",
                        },
                    )
                    legacy_prefix = journal_path.read_bytes()
                    with batch.batch_lock(run_dir, create=True) as locked:
                        batch._ensure_receipt_ledger(locked)
                    state = journal._scan_run(run_dir)
                    marker = builders._writer_activation_decision(
                        state,
                        receipt_origin_size=len(legacy_prefix),
                        receipt_origin_sha256=journal._sha256(legacy_prefix),
                        recorded_at="2026-09-10T03:31:00Z",
                    )
                    if attack == "non-allocated-id":
                        marker["id"] = "decision-03"
                        self.assertTrue(journal._writer_activation_marker(marker))
                        self.assertFalse(
                            journal._writer_activation_id_is_allocated(
                                [*state.records, marker], marker
                            )
                        )
                    else:
                        marker["writer_contract"] = (
                            journal.WRITER_CONTRACT.rsplit("/", 1)[0] + "/2"
                        )
                        self.assertTrue(
                            journal._writer_activation_candidate(marker)
                        )
                        self.assertFalse(journal._writer_activation_marker(marker))
                    task = {
                        "type": "task",
                        "id": "task-01",
                        "status": "active",
                        "goal": "Refuse an unproved persisted activation",
                        "acceptance": ["No bytes change"],
                        "files": ["src/example.py"],
                        "run_id": run_id,
                        "recorded_at": "2026-09-10T03:31:00Z",
                    }
                    adopting_bytes = (
                        journal._journal_line(marker)
                        + journal._journal_line(task)
                    )
                    persisted = legacy_prefix + adopting_bytes
                    journal_path.write_bytes(persisted)
                    receipt = {
                        "schema": journal.BATCH_RECEIPT_SCHEMA,
                        "idempotency_key": key(
                            f"persisted-{attack}-activation"
                        ),
                        "request_sha256": key(
                            f"persisted-{attack}-request"
                        ),
                        "base_size": len(legacy_prefix),
                        "batch_sha256": journal._sha256(adopting_bytes),
                        "record_count": 2,
                        "journal_size": len(persisted),
                        "journal_sha256": journal._sha256(persisted),
                        "recorded_at": "2026-09-10T03:31:00Z",
                    }
                    (run_dir / journal.BATCH_RECEIPTS_NAME).write_bytes(
                        journal._canonical_json_bytes(receipt) + b"\n"
                    )

                    before = self._run_file_bytes(run_dir)
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal,
                        journal.BATCH_DIVERGED,
                    ):
                        builders.task_finish(
                            repo,
                            run_id,
                            idempotency_key=key(
                                f"persisted-{attack}-competing-finish"
                            ),
                            task="task-01",
                            status="complete",
                        )
                    self.assertEqual(self._run_file_bytes(run_dir), before)

    def test_activation_allocation_refuses_unicode_and_oversized_suffixes(
        self,
    ) -> None:
        for attack, suffix in (
            ("unicode-digits", "１２"),
            ("oversized-suffix", "9" * 65),
        ):
            with self.subTest(attack=attack):
                repo, _ = self._new_repo(f"repo-allocation-{attack}")
                run_id = f"run-20260910-allocation-{attack}"
                with self.api_environment():
                    self._open_legacy_run(repo, run_id)
                    run_dir = self.run_dir(repo, run_id)
                    journal_path = run_dir / "journal.jsonl"
                    journal.append_owned_record(
                        journal_path,
                        {
                            "type": "decision",
                            "id": f"decision-{suffix}",
                            "resolution": "Hostile numeric-looking suffix",
                            "basis": [],
                            "run_id": run_id,
                            "recorded_at": "2026-09-10T03:40:00Z",
                        },
                    )
                    with batch.batch_lock(run_dir, create=True) as locked:
                        batch._ensure_receipt_ledger(locked)
                    before = self._run_file_bytes(run_dir)
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal,
                        journal.BATCH_DIVERGED,
                    ):
                        self.start_task(repo, run_id, label=attack)
                    self.assertEqual(self._run_file_bytes(run_dir), before)

                    state = journal._scan_run(run_dir)
                    marker = {
                        "type": "decision",
                        "id": f"decision-{int(suffix) + 1:02d}",
                        "resolution": journal.WRITER_ACTIVATION_RESOLUTION,
                        "writer_contract": journal.WRITER_CONTRACT,
                        "receipt_origin_size": len(
                            journal_path.read_bytes()
                        ),
                        "receipt_origin_sha256": journal._sha256(
                            journal_path.read_bytes()
                        ),
                        "run_id": run_id,
                        "recorded_at": "2026-09-10T03:41:00Z",
                    }
                    self.assertTrue(journal._writer_activation_marker(marker))
                    self.assertFalse(
                        journal._writer_activation_id_is_allocated(
                            [*state.records, marker], marker
                        )
                    )

    def test_removed_batch_lock_after_activation_is_not_recreated(self) -> None:
        run_id = "run-20260910-removed-activation-lock"
        with self.api_environment():
            self._open_legacy_run(self.repo, run_id)
            self.start_task(self.repo, run_id)
            run_dir = self.run_dir(self.repo, run_id)
            lock_path = run_dir / journal.BATCH_LOCK_NAME
            self.assertTrue(lock_path.is_file())
            lock_path.unlink()
            before = self._run_file_bytes(run_dir)

            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.BATCH_DIVERGED,
            ):
                builders.task_finish(
                    self.repo,
                    run_id,
                    idempotency_key=key("removed-activation-lock-finish"),
                    task="task-01",
                    status="complete",
                )

            self.assertFalse(lock_path.exists())
            self.assertEqual(self._run_file_bytes(run_dir), before)

    def test_activation_outbox_blocks_raw_append_byte_exactly_then_drains(
        self,
    ) -> None:
        with self.api_environment():
            (
                repo,
                run_id,
                state_path,
                legacy_prefix,
                chain_id,
                source_digest,
                records,
            ) = self._activation_outbox_case(
                "activation-outbox-raw-append"
            )
            run_dir = self.run_dir(repo, run_id)
            event_path = (
                builders.chain_storage_root(repo)
                / f"{chain_id}.events.jsonl"
            )
            before_run = self._run_file_bytes(run_dir)
            before_state = state_path.read_bytes()
            before_events = event_path.read_bytes()
            self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

            raw_record = {
                "type": "decision",
                "id": "decision-01",
                "resolution": "Raw append cannot steal first use",
                "basis": [],
                "run_id": run_id,
                "recorded_at": "2026-09-10T03:20:00Z",
            }
            for raw_api in ("owned", "repository"):
                with self.subTest(raw_api=raw_api), self.assertRaisesRegex(
                    journal.CoordinationRefusal,
                    journal.BATCH_PENDING,
                ):
                    if raw_api == "owned":
                        journal.append_owned_record(
                            run_dir / "journal.jsonl", raw_record
                        )
                    else:
                        journal.append_run_record(repo, run_id, raw_record)

                self.assertEqual(self._run_file_bytes(run_dir), before_run)
                self.assertEqual(state_path.read_bytes(), before_state)
                self.assertEqual(event_path.read_bytes(), before_events)
                self.assertFalse(
                    (run_dir / journal.BATCH_INTENT_NAME).exists()
                )

            for operation in ("close", "retire", "readmit"):
                with self.subTest(operation=operation), self.assertRaisesRegex(
                    journal.CoordinationRefusal,
                    journal.BATCH_PENDING,
                ):
                    self._invoke_raw_lifecycle(repo, run_id, operation)

                self.assertEqual(self._run_file_bytes(run_dir), before_run)
                self.assertEqual(state_path.read_bytes(), before_state)
                self.assertEqual(event_path.read_bytes(), before_events)
                self.assertFalse(
                    (run_dir / journal.BATCH_INTENT_NAME).exists()
                )

            capability, authorizer, calls = self._chain_drain_authorizer(
                repo,
                run_id,
                chain_id,
                source_digest,
                records,
            )
            with mock.patch.object(batch, "_CHAIN_BATCH_AUTHORIZER", None):
                batch._register_chain_batch_authorizer(authorizer)
                drained = batch.drain_chain_batch(
                    repo,
                    run_id,
                    chain_id=chain_id,
                    source_event_digest=source_digest,
                    records=records,
                    capability=capability,
                )
            self.assertFalse(drained.repeated)
            self.assertEqual(drained.records, records)
            self.assertEqual(len(calls), 1)
            self.assertEqual(
                (run_dir / "journal.jsonl").read_bytes()[
                    : len(legacy_prefix)
                ],
                legacy_prefix,
            )
            self.assertEqual(
                len(
                    self._activation_markers(
                        journal._parse_raw_records(
                            (run_dir / "journal.jsonl").read_bytes()
                        )
                    )
                ),
                1,
            )

    def test_activation_outbox_lifecycle_guard_is_load_bearing(self) -> None:
        for operation in ("close", "retire", "readmit"):
            with self.subTest(operation=operation), self.api_environment():
                (
                    repo,
                    run_id,
                    state_path,
                    _legacy_prefix,
                    chain_id,
                    _source_digest,
                    _records,
                ) = self._activation_outbox_case(
                    f"activation-outbox-disabled-{operation}"
                )
                run_dir = self.run_dir(repo, run_id)
                event_path = (
                    builders.chain_storage_root(repo)
                    / f"{chain_id}.events.jsonl"
                )
                before_run = self._run_file_bytes(run_dir)
                before_state = state_path.read_bytes()
                before_events = event_path.read_bytes()

                with mock.patch.object(
                    builders,
                    "_require_no_pending_activation_outbox",
                    return_value=None,
                ) as disabled_outbox_guard:
                    self._invoke_raw_lifecycle(repo, run_id, operation)

                disabled_outbox_guard.assert_called_once_with(
                    repo.resolve(), run_id
                )
                self.assertNotEqual(self._run_file_bytes(run_dir), before_run)
                self.assertEqual(state_path.read_bytes(), before_state)
                self.assertEqual(event_path.read_bytes(), before_events)

    def test_legacy_raw_guard_intent_conditions_are_load_bearing(self) -> None:
        cases = ("published-intent", "orphan-intent-temporary")
        for condition in cases:
            with self.subTest(condition=condition), self.api_environment():
                repo, _ = self._new_repo(f"repo-raw-guard-{condition}")
                run_id = f"run-20260910-raw-guard-{condition}"
                if condition == "published-intent":
                    run_dir, _context = self._seed_gh17_wedge(repo, run_id)
                    patcher = mock.patch.object(
                        batch, "_load_intent", return_value=None
                    )
                else:
                    self._open_legacy_run(repo, run_id)
                    run_dir = self.run_dir(repo, run_id)
                    with batch.batch_lock(run_dir, create=True):
                        temporary = run_dir / batch._intent_temporary_name(
                            key(f"{run_id}-intent"),
                            key(f"{run_id}-request"),
                        )
                        temporary.write_bytes(b"orphan first-use authority\n")
                    patcher = mock.patch.object(
                        batch,
                        "_validate_no_orphan_intent_temporary",
                        return_value=None,
                    )

                before = self._run_file_bytes(run_dir)
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal, journal.BATCH_PENDING
                ):
                    journal.retire_run(repo, run_id)
                self.assertEqual(self._run_file_bytes(run_dir), before)

                with patcher as disabled_condition:
                    journal.retire_run(repo, run_id)
                self.assertTrue(disabled_condition.called)
                self.assertNotEqual(self._run_file_bytes(run_dir), before)

    def test_raw_lifecycle_validation_precedes_batch_reservation(self) -> None:
        for operation in ("close", "retire", "readmit"):
            with self.subTest(operation=operation), self.api_environment():
                repo, _ = self._new_repo(
                    f"repo-lifecycle-prevalidate-{operation}"
                )
                run_id = f"run-20260910-prevalidate-{operation}"
                self._open_legacy_run(
                    repo, run_id, scope=["src/target/**"]
                )
                run_dir = self.run_dir(repo, run_id)
                lock_path = run_dir / journal.BATCH_LOCK_NAME
                registry_path = repo / ".forge/tmp/run-registry.json"

                if operation == "readmit":
                    self._open_legacy_run(
                        repo,
                        f"{run_id}-blocker",
                        scope=["docs/**"],
                    )
                    invoke = lambda: journal.readmit_run(
                        repo, run_id, ["docs/**"], replace=True
                    )
                elif operation == "retire":
                    (run_dir / "owner").unlink()
                    invoke = lambda: journal.retire_run(repo, run_id)
                else:
                    invalid_close = {
                        "type": "decision",
                        "id": "decision-01",
                        "resolution": "Not a lifecycle closure",
                        "basis": [],
                        "run_id": run_id,
                        "recorded_at": "2026-09-10T03:20:02Z",
                    }
                    invoke = lambda: journal.close_run(
                        repo, run_id, invalid_close
                    )

                before_run = self._run_file_bytes(run_dir)
                before_registry = registry_path.read_bytes()
                self.assertFalse(lock_path.exists())
                with mock.patch.object(
                    journal,
                    "_legacy_raw_append_guard",
                    side_effect=AssertionError(
                        "invalid lifecycle reached batch reservation"
                    ),
                ) as reservation, self.assertRaises(
                    journal.CoordinationRefusal
                ):
                    invoke()

                reservation.assert_not_called()
                self.assertFalse(lock_path.exists())
                self.assertEqual(self._run_file_bytes(run_dir), before_run)
                self.assertEqual(registry_path.read_bytes(), before_registry)

    def test_raw_lifecycle_lock_order_is_load_bearing(self) -> None:
        for operation in ("close", "retire", "readmit"):
            with self.subTest(operation=operation), self.api_environment():
                repo, _ = self._new_repo(
                    f"repo-lifecycle-order-{operation}"
                )
                run_id = f"run-20260910-order-{operation}"
                self._open_legacy_run(repo, run_id)
                run_dir = self.run_dir(repo, run_id)
                if operation == "readmit":
                    invoke = lambda: journal.readmit_run(
                        repo, run_id, ["src/**", "tests/**"]
                    )
                elif operation == "retire":
                    invoke = lambda: journal.retire_run(repo, run_id)
                else:
                    closing_record = {
                        "type": "run_closed",
                        "recorded_at": "2026-09-10T03:20:03Z",
                        "run_id": run_id,
                        "judgment": "blocked",
                        "summary": "Observe the raw lifecycle lock order",
                        "validation": journal.validate_run(
                            run_dir, gates=True
                        ),
                        "risks": [],
                        "follow_ups": [],
                    }
                    invoke = lambda: journal.close_run(
                        repo, run_id, closing_record
                    )

                original_guard = journal._legacy_raw_append_guard
                original_registry_lock = journal._registry_lock
                original_locked_journal = journal._locked_journal
                original_write_registry = journal._write_registry
                active = {"batch": 0, "registry": 0, "journal": 0}
                events: list[str] = []

                @contextmanager
                def observed_guard(*args: object, **kwargs: object):
                    self.assertEqual(active, {
                        "batch": 0,
                        "registry": 0,
                        "journal": 0,
                    })
                    with original_guard(*args, **kwargs):
                        active["batch"] += 1
                        events.append("batch-enter")
                        try:
                            yield
                        finally:
                            events.append("batch-exit")
                            active["batch"] -= 1

                @contextmanager
                def observed_registry_lock(*args: object, **kwargs: object):
                    phase = (
                        "mutation" if active["batch"] else "prevalidation"
                    )
                    if phase == "mutation":
                        self.assertEqual(active["batch"], 1)
                    self.assertEqual(active["registry"], 0)
                    self.assertEqual(active["journal"], 0)
                    events.append(f"{phase}-registry-enter")
                    with original_registry_lock(*args, **kwargs) as locked:
                        active["registry"] += 1
                        try:
                            yield locked
                        finally:
                            active["registry"] -= 1
                            events.append(f"{phase}-registry-exit")

                @contextmanager
                def observed_locked_journal(*args: object, **kwargs: object):
                    phase = (
                        "mutation" if active["batch"] else "prevalidation"
                    )
                    self.assertEqual(active["registry"], 1)
                    self.assertEqual(active["journal"], 0)
                    events.append(f"{phase}-journal-enter")
                    with original_locked_journal(*args, **kwargs) as locked:
                        active["journal"] += 1
                        try:
                            yield locked
                        finally:
                            active["journal"] -= 1
                            events.append(f"{phase}-journal-exit")

                def observed_write_registry(*args: object, **kwargs: object):
                    self.assertEqual(active, {
                        "batch": 1,
                        "registry": 1,
                        "journal": 1,
                    })
                    events.append("registry-write")
                    return original_write_registry(*args, **kwargs)

                with mock.patch.object(
                    journal,
                    "_legacy_raw_append_guard",
                    side_effect=observed_guard,
                ), mock.patch.object(
                    journal,
                    "_registry_lock",
                    side_effect=observed_registry_lock,
                ), mock.patch.object(
                    journal,
                    "_locked_journal",
                    side_effect=observed_locked_journal,
                ), mock.patch.object(
                    journal,
                    "_write_registry",
                    side_effect=observed_write_registry,
                ):
                    invoke()

                self.assertEqual(
                    events,
                    [
                        "prevalidation-registry-enter",
                        "prevalidation-journal-enter",
                        "prevalidation-journal-exit",
                        "prevalidation-registry-exit",
                        "batch-enter",
                        "mutation-registry-enter",
                        "mutation-journal-enter",
                        "registry-write",
                        "mutation-journal-exit",
                        "mutation-registry-exit",
                        "batch-exit",
                    ],
                )
                self.assertEqual(active, {
                    "batch": 0,
                    "registry": 0,
                    "journal": 0,
                })
                self.assertTrue(
                    (run_dir / journal.BATCH_LOCK_NAME).is_file()
                )

    def test_published_first_use_intent_blocks_outbox_before_publication(
        self,
    ) -> None:
        run_id = "run-20260910-intent-before-activation-outbox"
        with self.api_environment():
            self._open_legacy_run(self.repo, run_id)
            run_dir = self.run_dir(self.repo, run_id)
            journal_before = (run_dir / "journal.jsonl").read_bytes()
            original_write = batch._write_intent

            def publish_then_crash(*args: object, **kwargs: object):
                result = original_write(*args, **kwargs)
                raise RuntimeError("first-use intent published")

            with mock.patch.object(
                batch, "_write_intent", side_effect=publish_then_crash
            ), self.assertRaisesRegex(
                RuntimeError, "first-use intent published"
            ):
                self.start_task(self.repo, run_id)

            intent_path = run_dir / journal.BATCH_INTENT_NAME
            self.assertTrue(intent_path.is_file())
            intent_before = intent_path.read_bytes()
            self.assertEqual(
                (run_dir / "journal.jsonl").read_bytes(), journal_before
            )
            publisher = mock.Mock()
            chain_id = "c-2026-09-10T032100Z-a104"
            event_path = (
                builders.chain_storage_root(self.repo)
                / f"{chain_id}.events.jsonl"
            )
            with batch.batch_lock(
                run_dir, create=False
            ) as locked, self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.BATCH_PENDING,
            ):
                state = journal._scan_run(run_dir)
                prepared = batch.prepare_outbox_records(
                    self.repo.resolve(),
                    state,
                    (),
                    recorded_at="2026-09-10T03:21:00Z",
                )
                publisher(prepared)

            publisher.assert_not_called()
            self.assertFalse(event_path.exists())
            self.assertEqual(intent_path.read_bytes(), intent_before)
            self.assertEqual(
                (run_dir / "journal.jsonl").read_bytes(), journal_before
            )

    def test_staged_first_use_intent_blocks_outbox_before_publication(
        self,
    ) -> None:
        run_id = "run-20260910-staged-intent-before-activation-outbox"
        with self.api_environment():
            self._open_legacy_run(self.repo, run_id)
            run_dir = self.run_dir(self.repo, run_id)
            event_publisher = mock.Mock()
            with batch.batch_lock(run_dir, create=True) as locked:
                temporary = run_dir / batch._intent_temporary_name(
                    key("staged-activation-key"),
                    key("staged-activation-request"),
                )
                temporary.write_bytes(b"staged intent authority\n")
                before = self._run_file_bytes(run_dir)
                state = journal._scan_run(run_dir)
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal,
                    journal.BATCH_PENDING,
                ):
                    prepared = batch.prepare_outbox_records(
                        self.repo.resolve(),
                        state,
                        (),
                        recorded_at="2026-09-10T03:21:01Z",
                    )
                    event_publisher(prepared)

                event_publisher.assert_not_called()
                self.assertEqual(self._run_file_bytes(run_dir), before)

    def test_raw_open_cannot_supply_writer_contract_before_any_mutation(
        self,
    ) -> None:
        repo, _ = self._new_repo("repo-raw-open-writer-contract")
        run_id = "run-20260910-raw-open-writer-contract"
        state_root = repo / ".codex-orchestrator"
        registry = repo / ".forge/tmp/run-registry.json"
        target = self.run_dir(repo, run_id)
        self.assertFalse(state_root.exists())
        self.assertFalse(registry.exists())
        with self.api_environment(), self.assertRaisesRegex(
            journal.CoordinationRefusal,
            "forge: journal append refused — activated writer requires typed builder",
        ):
            journal.open_run(
                repo,
                run_id,
                ["src/**"],
                {
                    "type": "run_started",
                    "writer_contract": journal.WRITER_CONTRACT,
                },
            )
        self.assertFalse(state_root.exists())
        self.assertFalse(registry.exists())
        self.assertFalse(target.exists())

    def test_activation_outbox_reserves_first_use_then_drains_exact_batch(
        self,
    ) -> None:
        with self.api_environment():
            case = self._activation_outbox_case(
                "activation-outbox-reservation"
            )
            (
                repo,
                run_id,
                _state_path,
                legacy_prefix,
                chain_id,
                source_digest,
                records,
            ) = case
            run_dir = self.run_dir(repo, run_id)
            before = self._run_file_bytes(run_dir)
            self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                builders.JOURNAL_OUTBOX_PENDING,
            ):
                self._compete_with_activation_outbox(
                    repo, run_id, "before-drain"
                )
            self.assertEqual(self._run_file_bytes(run_dir), before)
            self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

            capability, authorizer, calls = self._chain_drain_authorizer(
                repo,
                run_id,
                chain_id,
                source_digest,
                records,
            )
            with mock.patch.object(batch, "_CHAIN_BATCH_AUTHORIZER", None):
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
            self.assertEqual(created.records, records)
            self.assertEqual(len(calls), 1)
            journal_raw = (run_dir / "journal.jsonl").read_bytes()
            self.assertEqual(journal_raw[: len(legacy_prefix)], legacy_prefix)
            persisted, issues = journal.read_journal(
                run_dir / "journal.jsonl"
            )
            self.assertEqual(issues, [])
            persisted_markers = [
                {
                    name: value
                    for name, value in marker.items()
                    if name != "_line"
                }
                for marker in self._activation_markers(persisted)
            ]
            self.assertEqual(persisted_markers, [records[0]])
            receipts = [
                json.loads(line)
                for line in (
                    run_dir / journal.BATCH_RECEIPTS_NAME
                ).read_bytes().splitlines()
            ]
            self.assertEqual(len(receipts), 1)
            self.assertEqual(receipts[0]["base_size"], len(legacy_prefix))
            self.assertEqual(receipts[0]["record_count"], 2)
            self.assertEqual(
                receipts[0]["batch_sha256"],
                journal._sha256(
                    b"".join(
                        journal._journal_line(record) for record in records
                    )
                ),
            )
            self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

    def test_activation_outbox_missing_events_or_tampered_state_refuses_first_use(
        self,
    ) -> None:
        for attack in ("missing-events", "tampered-state"):
            with self.subTest(attack=attack), self.api_environment():
                (
                    repo,
                    run_id,
                    state_path,
                    _legacy_prefix,
                    _chain_id,
                    _source_digest,
                    _records,
                ) = self._activation_outbox_case(
                    f"activation-outbox-{attack}"
                )
                if attack == "missing-events":
                    state_path.with_name(
                        f"{_chain_id}.events.jsonl"
                    ).unlink()
                else:
                    state = json.loads(state_path.read_bytes())
                    outbox = state["journal_outbox"]
                    assert isinstance(outbox, dict)
                    outbox["batch_digest"] = key(
                        "tampered-materialized-activation-outbox"
                    )
                    state_path.write_bytes(
                        journal._canonical_json_bytes(state) + b"\n"
                    )
                run_dir = self.run_dir(repo, run_id)
                before = self._run_file_bytes(run_dir)

                with self.assertRaisesRegex(
                    journal.CoordinationRefusal,
                    journal.BATCH_DIVERGED,
                ):
                    self._compete_with_activation_outbox(
                        repo, run_id, attack
                    )

                self.assertEqual(self._run_file_bytes(run_dir), before)

    def test_legacy_first_typed_use_atomically_activates(self) -> None:
        run_id = "run-20260910-legacy-first-typed-use"
        with self.api_environment():
            self._open_legacy_run(self.repo, run_id)
            run_dir = self.run_dir(self.repo, run_id)
            journal_path = run_dir / "journal.jsonl"
            journal.append_owned_record(
                journal_path,
                {
                    "type": "decision",
                    "id": "decision-01",
                    "resolution": "Preserve a legacy decision before adoption",
                    "basis": [],
                    "run_id": run_id,
                    "recorded_at": "2026-09-10T00:00:01Z",
                },
            )
            legacy_prefix = journal_path.read_bytes()

            started = self.start_task(self.repo, run_id)
            self.assertFalse(started.repeated)
            self.assertEqual(len(started.records), 2)
            marker, task = started.records
            self.assertEqual(set(marker), set(journal.WRITER_ACTIVATION_FIELDS))
            self.assertEqual(marker["id"], "decision-02")
            self.assertEqual(
                marker["resolution"], journal.WRITER_ACTIVATION_RESOLUTION
            )
            self.assertEqual(marker["writer_contract"], journal.WRITER_CONTRACT)
            self.assertEqual(marker["receipt_origin_size"], len(legacy_prefix))
            self.assertEqual(
                marker["receipt_origin_sha256"],
                journal._sha256(legacy_prefix),
            )
            self.assertEqual(marker["run_id"], run_id)
            self.assertNotIn("basis", marker)
            self.assertEqual(task["type"], "task")
            self.assertEqual(task["id"], "task-01")

            batch_bytes = journal._journal_line(marker) + journal._journal_line(task)
            ledger = run_dir / journal.BATCH_RECEIPTS_NAME
            receipts = [json.loads(line) for line in ledger.read_bytes().splitlines()]
            self.assertEqual(len(receipts), 1)
            adopting = receipts[0]
            self.assertEqual(adopting["base_size"], len(legacy_prefix))
            self.assertEqual(adopting["record_count"], 2)
            self.assertEqual(adopting["batch_sha256"], journal._sha256(batch_bytes))
            self.assertEqual(
                adopting["journal_size"], len(legacy_prefix) + len(batch_bytes)
            )
            self.assertEqual(
                adopting["journal_sha256"],
                journal._sha256(legacy_prefix + batch_bytes),
            )
            records, issues = journal.read_journal(journal_path)
            self.assertEqual(issues, [])
            self.assertTrue(journal._writer_contract_active(records))
            with batch.batch_lock(run_dir, create=False) as locked:
                self.assertTrue(
                    batch._writer_contract_activated(locked.run_descriptor)
                )

            before_raw = self._run_file_bytes(run_dir)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                "activated writer requires typed builder",
            ):
                journal.append_owned_record(
                    journal_path,
                    {
                        "type": "verification",
                        "id": "check-01",
                        "task": "task-01",
                        "criterion": "raw append remains blocked after adoption",
                        "method": "unittest",
                        "check": "python3 -m unittest",
                        "result": "passed",
                        "observation": "must not append",
                        "evidence": [],
                        "run_id": run_id,
                        "recorded_at": "2026-09-10T00:00:02Z",
                    },
                )
            self.assertEqual(self._run_file_bytes(run_dir), before_raw)

            finished = builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=key("legacy-first-use-finish"),
                task="task-01",
                status="complete",
            )
            self.assertEqual(len(finished.records), 1)
            self.assertEqual(finished.records[0]["status"], "complete")

    def test_legacy_activation_crash_matrix(self) -> None:
        fixed_time = "2026-09-10T00:10:00Z"
        for crash_point in (
            "before-intent",
            "torn-marker",
            "torn-user-record",
            "torn-receipt",
            "receipt-before-unlink",
        ):
            with self.subTest(crash_point=crash_point):
                repo, _ = self._new_repo(f"repo-activation-{crash_point}")
                run_id = f"run-20260910-activation-{crash_point}"
                with self.api_environment(), mock.patch.object(
                    journal, "_utc_now", return_value=fixed_time
                ):
                    self._open_legacy_run(repo, run_id)
                    run_dir = self.run_dir(repo, run_id)
                    journal_path = run_dir / "journal.jsonl"
                    legacy_prefix = journal_path.read_bytes()
                    original_append = batch._append_named_file
                    crashed = False

                    def crash_append(
                        locked: batch.BatchLock,
                        name: str,
                        payload: bytes,
                        expected: journal.FileObservation,
                        **kwargs: object,
                    ) -> None:
                        nonlocal crashed
                        should_crash = (
                            not crashed
                            and (
                                (
                                    crash_point
                                    in {"torn-marker", "torn-user-record"}
                                    and name == "journal.jsonl"
                                )
                                or (
                                    crash_point == "torn-receipt"
                                    and name == journal.BATCH_RECEIPTS_NAME
                                )
                            )
                        )
                        if not should_crash:
                            original_append(
                                locked, name, payload, expected, **kwargs
                            )
                            return
                        crashed = True
                        if crash_point == "torn-marker":
                            first_end = payload.index(b"\n") + 1
                            prefix = payload[: max(1, first_end // 2)]
                        elif crash_point == "torn-user-record":
                            first_end = payload.index(b"\n") + 1
                            remaining = len(payload) - first_end
                            prefix = payload[
                                : first_end + max(1, remaining // 2)
                            ]
                        else:
                            prefix = payload[: max(1, len(payload) // 2)]
                        original_append(
                            locked, name, prefix, expected, **kwargs
                        )
                        raise RuntimeError(f"activation crash: {crash_point}")

                    if crash_point == "before-intent":
                        patcher = mock.patch.object(
                            batch,
                            "_write_intent",
                            side_effect=RuntimeError(
                                f"activation crash: {crash_point}"
                            ),
                        )
                    elif crash_point == "receipt-before-unlink":
                        patcher = mock.patch.object(
                            batch,
                            "_unlink_intent",
                            side_effect=RuntimeError(
                                f"activation crash: {crash_point}"
                            ),
                        )
                    else:
                        patcher = mock.patch.object(
                            batch, "_append_named_file", side_effect=crash_append
                        )
                    with patcher, self.assertRaisesRegex(
                        RuntimeError, f"activation crash: {crash_point}"
                    ):
                        self.start_task(repo, run_id)

                    intent_path = run_dir / journal.BATCH_INTENT_NAME
                    if crash_point == "before-intent":
                        self.assertFalse(intent_path.exists())
                        self.assertEqual(journal_path.read_bytes(), legacy_prefix)
                        outcome = self.start_task(repo, run_id)
                        self.assertFalse(outcome.repeated)
                    else:
                        self.assertTrue(intent_path.is_file())
                        intent = json.loads(
                            intent_path.read_text(encoding="utf-8")
                        )
                        intended_records = batch._records_from_batch(
                            batch._decode_base64url(intent["batch_bytes"])
                        )
                        self.assertEqual(len(intended_records), 2)
                        self.assertTrue(
                            journal._writer_activation_marker(
                                intended_records[0]
                            )
                        )
                        self.assertEqual(intended_records[1]["type"], "task")
                        before_read = self._run_file_bytes(run_dir)
                        visible, issues = journal.read_journal(journal_path)
                        self.assertEqual(visible, [])
                        self.assertEqual(
                            issues, [journal.JOURNAL_READ_TRANSACTION_REFUSAL]
                        )
                        self.assertEqual(
                            self._run_file_bytes(run_dir), before_read
                        )
                        outcome = batch.recover_batch(repo, run_id)
                        self.assertTrue(outcome.repeated)

                    self.assertFalse(intent_path.exists())
                    records, issues = journal.read_journal(journal_path)
                    self.assertEqual(issues, [])
                    markers = self._activation_markers(records)
                    self.assertEqual(len(markers), 1)
                    self.assertEqual(
                        [record["type"] for record in records],
                        ["run_started", "decision", "task"],
                    )
                    receipts = [
                        json.loads(line)
                        for line in (
                            run_dir / journal.BATCH_RECEIPTS_NAME
                        ).read_bytes().splitlines()
                    ]
                    self.assertEqual(len(receipts), 1)
                    self.assertEqual(receipts[0]["base_size"], len(legacy_prefix))
                    self.assertEqual(receipts[0]["record_count"], 2)
                    adopting_bytes = b"".join(
                        journal._journal_line(record)
                        for record in outcome.records
                    )
                    self.assertEqual(
                        receipts[0]["batch_sha256"],
                        journal._sha256(adopting_bytes),
                    )
                    before_raw = self._run_file_bytes(run_dir)
                    with self.assertRaisesRegex(
                        journal.CoordinationRefusal,
                        "activated writer requires typed builder",
                    ):
                        journal.append_owned_record(
                            journal_path,
                            {
                                "type": "decision",
                                "id": "decision-02",
                                "resolution": "Raw retry stays blocked",
                                "basis": [],
                                "run_id": run_id,
                                "recorded_at": fixed_time,
                            },
                        )
                    self.assertEqual(
                        self._run_file_bytes(run_dir), before_raw
                    )

    def test_typed_opened_run_bytes_are_unchanged(self) -> None:
        run_id = "run-20260910-typed-open-byte-golden"
        fixed_time = "2026-09-10T01:00:00Z"
        repository = self.repo.resolve()
        open_key = key(f"{run_id}-open")
        task_key = key(f"{run_id}-task")
        opening = {
            "type": "run_started",
            "goal": "Exercise Revision 9",
            "repo": str(repository),
            "repo_head": self.head,
            "repo_status": [],
            "plugin_ref": "forge-test-revision-9",
            "scope": ["src/**"],
            "writer_contract": journal.WRITER_CONTRACT,
            "run_id": run_id,
            "recorded_at": fixed_time,
        }
        opening_bytes = journal._journal_line(opening)
        open_inputs = {
            "goal": "Exercise Revision 9",
            "scope": ["src/**"],
            "plugin_ref": "forge-test-revision-9",
            "successor_of": None,
        }
        open_request = {
            "schema": journal.BATCH_REQUEST_SCHEMA,
            "verb": "run-open",
            "repository": str(repository),
            "run_id": run_id,
            "inputs": open_inputs,
        }
        open_request_sha256 = journal._sha256(
            journal._canonical_json_bytes(open_request)
        )
        open_receipt = {
            "schema": journal.BATCH_RECEIPT_SCHEMA,
            "idempotency_key": open_key,
            "request_sha256": open_request_sha256,
            "base_size": 0,
            "batch_sha256": journal._sha256(opening_bytes),
            "record_count": 1,
            "journal_size": len(opening_bytes),
            "journal_sha256": journal._sha256(opening_bytes),
            "recorded_at": fixed_time,
        }
        open_receipt_bytes = journal._canonical_json_bytes(open_receipt) + b"\n"
        open_intent = {
            "schema": journal.BATCH_INTENT_SCHEMA,
            "idempotency_key": open_key,
            "request_sha256": open_request_sha256,
            "base_size": 0,
            "base_sha256": journal._sha256(b""),
            "record_count": 1,
            "batch_bytes": batch._encode_base64url(opening_bytes),
            "batch_sha256": journal._sha256(opening_bytes),
            "receipt_base_size": 0,
            "receipt_base_sha256": journal._sha256(b""),
            "receipt_bytes": batch._encode_base64url(open_receipt_bytes),
        }
        expected_open_intent = (
            journal._canonical_json_bytes(open_intent) + b"\n"
        )
        captured_open: dict[str, bytes] = {}
        original_open = journal.open_run

        def capture_open(*args: object, **kwargs: object) -> None:
            capability = kwargs.get("_batch")
            self.assertIsNotNone(capability)
            captured_open["intent"] = capability.intent_payload
            captured_open["receipt"] = capability.receipt_payload
            original_open(*args, **kwargs)

        with self.api_environment(), mock.patch.object(
            journal, "_utc_now", return_value=fixed_time
        ), mock.patch.object(journal, "open_run", side_effect=capture_open):
            opened = self.open_run(self.repo, run_id)
        self.assertEqual(captured_open["intent"], expected_open_intent)
        self.assertEqual(captured_open["receipt"], open_receipt_bytes)
        self.assertEqual(
            opened.payload(),
            {
                "receipt": open_receipt,
                "records": [opening],
                "repeated": False,
            },
        )

        task = {
            "type": "task",
            "id": "task-01",
            "status": "active",
            "goal": "Implement the typed transaction",
            "acceptance": ["The focused behavior passes"],
            "files": ["src/example.py"],
            "run_id": run_id,
            "recorded_at": fixed_time,
        }
        task_bytes = journal._journal_line(task)
        task_inputs = {
            "task": "task-01",
            "goal": "Implement the typed transaction",
            "acceptance": ["The focused behavior passes"],
            "file": ["src/example.py"],
        }
        task_request = {
            "schema": journal.BATCH_REQUEST_SCHEMA,
            "verb": "journal task-start",
            "repository": str(repository),
            "run_id": run_id,
            "inputs": task_inputs,
        }
        task_request_sha256 = journal._sha256(
            journal._canonical_json_bytes(task_request)
        )
        task_receipt = {
            "schema": journal.BATCH_RECEIPT_SCHEMA,
            "idempotency_key": task_key,
            "request_sha256": task_request_sha256,
            "base_size": len(opening_bytes),
            "batch_sha256": journal._sha256(task_bytes),
            "record_count": 1,
            "journal_size": len(opening_bytes) + len(task_bytes),
            "journal_sha256": journal._sha256(opening_bytes + task_bytes),
            "recorded_at": fixed_time,
        }
        task_receipt_bytes = journal._canonical_json_bytes(task_receipt) + b"\n"
        task_intent = {
            "schema": journal.BATCH_INTENT_SCHEMA,
            "idempotency_key": task_key,
            "request_sha256": task_request_sha256,
            "base_size": len(opening_bytes),
            "base_sha256": journal._sha256(opening_bytes),
            "record_count": 1,
            "batch_bytes": batch._encode_base64url(task_bytes),
            "batch_sha256": journal._sha256(task_bytes),
            "receipt_base_size": len(open_receipt_bytes),
            "receipt_base_sha256": journal._sha256(open_receipt_bytes),
            "receipt_bytes": batch._encode_base64url(task_receipt_bytes),
        }
        expected_task_intent = (
            journal._canonical_json_bytes(task_intent) + b"\n"
        )
        captured_task: dict[str, bytes] = {}
        original_write_intent = batch._write_intent

        def capture_task_intent(
            locked: batch.BatchLock, intent: dict[str, object]
        ) -> journal.ExactFile:
            captured_task["intent"] = (
                journal._canonical_json_bytes(intent) + b"\n"
            )
            return original_write_intent(locked, intent)

        with self.api_environment(), mock.patch.object(
            journal, "_utc_now", return_value=fixed_time
        ), mock.patch.object(
            batch, "_write_intent", side_effect=capture_task_intent
        ):
            started = self.start_task(self.repo, run_id)

        run_dir = self.run_dir(self.repo, run_id)
        self.assertEqual(captured_task["intent"], expected_task_intent)
        self.assertEqual(
            (run_dir / "journal.jsonl").read_bytes(),
            opening_bytes + task_bytes,
        )
        self.assertEqual(
            (run_dir / journal.BATCH_RECEIPTS_NAME).read_bytes(),
            open_receipt_bytes + task_receipt_bytes,
        )
        self.assertEqual(
            started.payload(),
            {
                "receipt": task_receipt,
                "records": [task],
                "repeated": False,
            },
        )
        self.assertEqual(started.records, (task,))
        self.assertFalse(
            any(
                journal._writer_activation_candidate(record)
                for record in started.records
            )
        )

        before_retry = self._run_file_bytes(run_dir)
        with self.api_environment(), mock.patch.object(
            journal, "_utc_now", return_value="2099-01-01T00:00:00Z"
        ), mock.patch.object(
            batch,
            "_write_intent",
            side_effect=AssertionError("retry must not publish an intent"),
        ):
            repeated = self.start_task(self.repo, run_id)
        self.assertTrue(repeated.repeated)
        self.assertEqual(repeated.receipt, task_receipt)
        self.assertEqual(repeated.records, (task,))
        self.assertEqual(self._run_file_bytes(run_dir), before_retry)

    def test_global_reconciliation_defers_torn_adopted_coverage(self) -> None:
        for condition in ("pending-intent", "stale-consistent-ledger"):
            with self.subTest(condition=condition):
                repo, _ = self._new_repo(f"repo-reconcile-{condition}")
                adopted = f"run-20260910-reconcile-{condition}"
                unrelated = f"run-20260910-unrelated-{condition}"
                with self.api_environment():
                    self._open_legacy_run(repo, adopted, scope=["src/**"])
                    self.start_task(repo, adopted)
                    run_dir = self.run_dir(repo, adopted)
                    journal_path = run_dir / "journal.jsonl"

                    if condition == "pending-intent":
                        original_append = batch._append_named_file

                        def crash_before_receipt(
                            locked: batch.BatchLock,
                            name: str,
                            payload: bytes,
                            expected: journal.FileObservation,
                            **kwargs: object,
                        ) -> None:
                            if name == journal.BATCH_RECEIPTS_NAME:
                                raise RuntimeError(
                                    "adopted journal appended before receipt"
                                )
                            original_append(
                                locked, name, payload, expected, **kwargs
                            )

                        with mock.patch.object(
                            batch,
                            "_append_named_file",
                            side_effect=crash_before_receipt,
                        ), self.assertRaisesRegex(
                            RuntimeError,
                            "adopted journal appended before receipt",
                        ):
                            builders.verification_add(
                                repo,
                                adopted,
                                idempotency_key=key(
                                    "reconcile-adopted-torn-write"
                                ),
                                task="task-01",
                                criterion="unrelated reconciliation",
                                method="unittest",
                                check="focused torn adopted write",
                                result="passed",
                                observation="receipt append is interrupted",
                                evidence=[],
                                binding_chain=None,
                                binding_id=None,
                            )
                        self.assertTrue(
                            (run_dir / journal.BATCH_INTENT_NAME).is_file()
                        )
                    else:
                        historical_tail = {
                            "type": "verification",
                            "id": "check-01",
                            "task": "task-01",
                            "criterion": "historical stale receipt tail",
                            "method": "bash",
                            "check": "true",
                            "result": "passed",
                            "observation": "receipt ledger remains at its prior EOF",
                            "evidence": [],
                            "run_id": adopted,
                            "recorded_at": "2026-09-10T06:00:00Z",
                        }
                        with journal_path.open("ab") as stream:
                            stream.write(journal._journal_line(historical_tail))
                        self.assertFalse(
                            (run_dir / journal.BATCH_INTENT_NAME).exists()
                        )

                    before = self._run_file_bytes(run_dir)
                    records, issues = journal.read_journal(journal_path)
                    self.assertEqual(records, [])
                    self.assertEqual(
                        issues, [journal.JOURNAL_READ_TRANSACTION_REFUSAL]
                    )
                    self.assertEqual(self._run_file_bytes(run_dir), before)

                    opened = builders.run_open(
                        repo,
                        unrelated,
                        idempotency_key=key(f"{condition}-unrelated-open"),
                        goal="Open a disjoint run during adopted recovery",
                        scope=["docs/**"],
                        plugin_ref="forge-test-revision-9",
                    )
                    self.assertEqual(opened.records[0]["run_id"], unrelated)
                    self.assertEqual(self._run_file_bytes(run_dir), before)

                    if condition == "pending-intent":
                        recovered = batch.recover_batch(repo, adopted)
                        self.assertTrue(recovered.repeated)
                        self.assertFalse(
                            (run_dir / journal.BATCH_INTENT_NAME).exists()
                        )

    def _restore_prefix_wedge_fixture(
        self,
    ) -> tuple[Path, Path, Path, journal.Owner]:
        run_id = "run-20260910-inplace-wedge"
        repo, _head = self._new_repo("repo-prefix-wedge-d77d997")
        run_dir = self.run_dir(repo, run_id)
        run_dir.mkdir(parents=True)
        targets = {
            "intent.json": run_dir / journal.BATCH_INTENT_NAME,
            "journal.jsonl": run_dir / "journal.jsonl",
            "owner.txt": run_dir / "owner",
            "receipts.jsonl": run_dir / journal.BATCH_RECEIPTS_NAME,
            "registry.json": repo / ".forge/tmp/run-registry.json",
        }
        self.assertEqual(
            {path.name for path in PREFIX_WEDGE_FIXTURE.iterdir()},
            set(targets),
        )
        for name, target in targets.items():
            payload = (PREFIX_WEDGE_FIXTURE / name).read_bytes()
            self.assertEqual(
                hashlib.sha256(payload).hexdigest(),
                PREFIX_WEDGE_FIXTURE_SHA256[name],
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        (run_dir / journal.BATCH_LOCK_NAME).write_bytes(b"")

        opening = json.loads(
            (run_dir / "journal.jsonl").read_bytes().splitlines()[0]
        )
        recorded_repo = Path(opening["repo"])
        archived_owner = journal._parse_owner_bytes(
            (run_dir / "owner").read_bytes()
        )
        self.assertIsNotNone(archived_owner)
        assert archived_owner is not None
        return repo, run_dir, recorded_repo, archived_owner

    def test_pre_fix_golden_wedge_recovers_and_continues(self) -> None:
        run_id = "run-20260910-inplace-wedge"
        repo, run_dir, recorded_repo, archived_owner = (
            self._restore_prefix_wedge_fixture()
        )
        journal_path = run_dir / "journal.jsonl"
        ledger_path = run_dir / journal.BATCH_RECEIPTS_NAME
        intent_path = run_dir / journal.BATCH_INTENT_NAME
        registry_path = repo / ".forge/tmp/run-registry.json"
        restored_chains_root = builders.chain_storage_root(repo)
        real_realpath = os.path.realpath

        def reject_recorded_realpath(path, *args, **kwargs):
            if os.fspath(path) == os.fspath(recorded_repo):
                self.fail(
                    "restored golden fixture resolved its recorded host path: "
                    f"{recorded_repo}"
                )
            return real_realpath(path, *args, **kwargs)

        def restored_chain_storage_root(repository: Path) -> Path:
            self.assertEqual(Path(repository), recorded_repo)
            return restored_chains_root

        journal_before = journal_path.read_bytes()
        ledger_before = ledger_path.read_bytes()
        registry_before = registry_path.read_bytes()
        receipts_before = [
            json.loads(line) for line in ledger_before.splitlines()
        ]
        self.assertEqual(
            [
                (receipt["base_size"], receipt["journal_size"])
                for receipt in receipts_before
            ],
            [(363, 541), (945, 1191)],
        )
        gap_records = journal._parse_raw_records(journal_before[541:945])
        self.assertEqual(len(gap_records), 2)
        self.assertTrue(
            all("run_id" not in record for record in gap_records)
        )

        with self.api_environment(), mock.patch.object(
            journal,
            "_resolve_repository",
            return_value=(recorded_repo, repo),
        ), mock.patch.object(
            journal, "_session_owner", return_value=archived_owner
        ), mock.patch.object(
            batch, "_read_only_session_owner", return_value=archived_owner
        ), mock.patch.object(
            builders,
            "chain_storage_root",
            side_effect=restored_chain_storage_root,
        ) as chain_storage_resolver, mock.patch(
            "os.path.realpath", side_effect=reject_recorded_realpath
        ):
            recovered = batch.recover_batch(repo, run_id)
            self.assertTrue(recovered.repeated)
            self.assertEqual(
                [record["id"] for record in recovered.records],
                ["check-01"],
            )

            receipts_after = [
                json.loads(line) for line in ledger_path.read_bytes().splitlines()
            ]
            self.assertEqual(receipts_after[:2], receipts_before)
            repairs = [
                receipt
                for receipt in receipts_after
                if receipt.get("repaired") is True
            ]
            self.assertEqual(len(repairs), 1)
            self.assertEqual(
                (
                    repairs[0]["base_size"],
                    repairs[0]["journal_size"],
                    repairs[0]["record_count"],
                ),
                (541, 945, 2),
            )
            activation_receipts = [
                receipt
                for receipt in receipts_after
                if receipt.get("repaired") is not True
                and receipt["base_size"] == 1191
            ]
            self.assertEqual(len(activation_receipts), 1)
            self.assertEqual(
                (
                    activation_receipts[0]["journal_size"],
                    activation_receipts[0]["record_count"],
                ),
                (1532, 1),
            )
            self.assertFalse(intent_path.exists())
            self.assertEqual(registry_path.read_bytes(), registry_before)
            self.assertEqual(journal_path.read_bytes()[:1191], journal_before)
            self.assertEqual(
                hashlib.sha256(journal_path.read_bytes()).hexdigest(),
                "ed2da77d622155efc6fc6c5187747700dd1be8e87802b235bb1ebdee55bb39af",
            )
            self.assertEqual(
                hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
                "379252a7e46e5f931dc4aa41ac1a7b2aa8f78b02bbd4c4b1cd6489c8833f146d",
            )
            records, issues = journal.read_journal(journal_path)
            self.assertEqual(issues, [])
            self.assertEqual(len(self._activation_markers(records)), 1)
            self.assertTrue(journal._writer_contract_active(records))

            finished = builders.task_finish(
                repo,
                run_id,
                idempotency_key=key("prefix-wedge-golden-finish"),
                task="task-01",
                status="complete",
            )
            self.assertEqual(finished.records[0]["status"], "complete")
            closed = builders.run_close(
                repo,
                run_id,
                idempotency_key=key("prefix-wedge-golden-close"),
                judgment="blocked",
                summary="Golden legacy gap recovered and continued",
                risks=[],
                follow_ups=[],
            )
            self.assertEqual(closed.records[0]["type"], "run_closed")
            self.assertGreater(chain_storage_resolver.call_count, 0)

        final_records, final_issues = journal.read_journal(journal_path)
        self.assertEqual(final_issues, [])
        self.assertEqual(final_records[-1]["type"], "run_closed")

    def _seed_unactivated_stale_ledger(
        self, repo: Path, run_id: str
    ) -> tuple[Path, dict[str, object]]:
        """Construct pre-fix typed-task bytes followed by one raw record."""

        self._open_legacy_run(repo, run_id)
        run_dir = self.run_dir(repo, run_id)
        journal_path = run_dir / "journal.jsonl"
        legacy_prefix = journal_path.read_bytes()
        with batch.batch_lock(run_dir, create=True) as locked:
            batch._ensure_receipt_ledger(locked)

        task = {
            "type": "task",
            "id": "task-01",
            "status": "active",
            "goal": "Reproduce the unactivated stale-ledger shape",
            "acceptance": ["The run retains a sanctioned raw exit"],
            "files": ["src/example.py"],
            "run_id": run_id,
            "recorded_at": "2026-09-10T02:00:00Z",
        }
        task_bytes = journal._journal_line(task)
        task_journal = legacy_prefix + task_bytes
        task_inputs = {
            "task": "task-01",
            "goal": task["goal"],
            "acceptance": task["acceptance"],
            "file": task["files"],
        }
        _request, task_request_sha256 = batch.normalized_request(
            repo.resolve(), run_id, "journal task-start", task_inputs
        )
        task_receipt = {
            "schema": journal.BATCH_RECEIPT_SCHEMA,
            "idempotency_key": key(f"{run_id}-legacy-task"),
            "request_sha256": task_request_sha256,
            "base_size": len(legacy_prefix),
            "batch_sha256": journal._sha256(task_bytes),
            "record_count": 1,
            "journal_size": len(task_journal),
            "journal_sha256": journal._sha256(task_journal),
            "recorded_at": task["recorded_at"],
        }
        trailing = {
            "type": "verification",
            "id": "check-01",
            "task": "task-01",
            "criterion": "legacy raw mutation",
            "method": "bash",
            "check": "true",
            "result": "passed",
            "observation": "raw record after the pre-fix typed task",
            "evidence": [],
            "recorded_at": "2026-09-10T02:00:01Z",
        }
        trailing_bytes = journal._journal_line(trailing)
        journal_path.write_bytes(task_journal + trailing_bytes)
        (run_dir / journal.BATCH_RECEIPTS_NAME).write_bytes(
            journal._canonical_json_bytes(task_receipt) + b"\n"
        )
        return run_dir, {
            "legacy_prefix": legacy_prefix,
            "task": task,
            "task_receipt": task_receipt,
            "trailing": trailing,
            "journal_bytes": task_journal + trailing_bytes,
        }

    def test_unactivated_stale_ledger_has_legible_refusal_and_raw_append(
        self,
    ) -> None:
        run_id = "run-20260910-unactivated-stale-append"
        with self.api_environment():
            run_dir, context = self._seed_unactivated_stale_ledger(
                self.repo, run_id
            )
            journal_path = run_dir / "journal.jsonl"
            receipt = context["task_receipt"]
            self.assertIsInstance(receipt, dict)
            self.assertLess(receipt["journal_size"], journal_path.stat().st_size)
            self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())
            self.assertFalse(
                any(
                    journal._writer_activation_candidate(record)
                    for record in journal._parse_raw_records(
                        journal_path.read_bytes()
                    )
                )
            )

            before = self._run_file_bytes(run_dir)
            with self.assertRaises(journal.CoordinationRefusal) as refused:
                builders.task_finish(
                    self.repo,
                    run_id,
                    idempotency_key=key("unactivated-stale-finish"),
                    task="task-01",
                    status="complete",
                )
            self.assertEqual(
                str(refused.exception),
                journal.LEGACY_ACTIVATION_LEDGER_INCOMPLETE,
            )
            self.assertEqual(self._run_file_bytes(run_dir), before)

            appended = {
                "type": "decision",
                "id": "decision-01",
                "resolution": "Unactivated legacy raw compatibility remains",
                "basis": [],
                "run_id": run_id,
                "recorded_at": "2026-09-10T02:00:02Z",
            }
            with mock.patch.object(
                batch,
                "_load_receipts",
                side_effect=AssertionError(
                    "raw guard must not consult a stale receipt ledger"
                ),
            ):
                journal.append_owned_record(journal_path, appended)
            self.assertEqual(
                journal._parse_raw_records(journal_path.read_bytes())[-1],
                appended,
            )

    def test_unactivated_stale_ledger_retire_then_typed_successor(self) -> None:
        repo, _ = self._new_repo("repo-unactivated-stale-retire")
        predecessor = "run-20260910-unactivated-stale-retire"
        successor = "run-20260910-unactivated-stale-successor"
        with self.api_environment():
            run_dir, _context = self._seed_unactivated_stale_ledger(
                repo, predecessor
            )
            with mock.patch.object(
                batch,
                "_load_receipts",
                side_effect=AssertionError(
                    "raw retirement must not consult a stale receipt ledger"
                ),
            ):
                journal.retire_run(repo, predecessor)
            self.assertTrue(journal._scan_run(run_dir).was_retired)

            opened = builders.run_open(
                repo,
                successor,
                idempotency_key=key("unactivated-stale-successor-open"),
                goal="Continue the retired stale-ledger run",
                scope=["src/**"],
                plugin_ref="forge-test-revision-9",
                successor_of=predecessor,
            )
            self.assertEqual(opened.records[0]["successor_of"], predecessor)
            self.assertEqual(opened.records[0]["run_id"], successor)

    def test_unactivated_stale_ledger_raw_close_succeeds(self) -> None:
        repo, _ = self._new_repo("repo-unactivated-stale-close")
        run_id = "run-20260910-unactivated-stale-close"
        with self.api_environment():
            run_dir, _context = self._seed_unactivated_stale_ledger(
                repo, run_id
            )
            with mock.patch.object(
                batch,
                "_load_receipts",
                side_effect=AssertionError(
                    "raw close must not consult a stale receipt ledger"
                ),
            ):
                self._invoke_raw_lifecycle(repo, run_id, "close")
            state = journal._scan_run(run_dir)
            self.assertEqual(state.disposition, "closed")
            self.assertEqual(state.close_judgment, "blocked")

    def test_unactivated_stale_ledger_eof_guard_is_load_bearing(self) -> None:
        repo, _ = self._new_repo("repo-unactivated-stale-disabled")
        run_id = "run-20260910-unactivated-stale-disabled"
        with self.api_environment():
            run_dir, _context = self._seed_unactivated_stale_ledger(
                repo, run_id
            )
            before = self._run_file_bytes(run_dir)
            with mock.patch.object(
                batch,
                "_legacy_receipt_ledger_reaches_eof",
                return_value=True,
            ) as disabled_guard, self.assertRaises(
                journal.CoordinationRefusal
            ) as downstream:
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("unactivated-stale-disabled-finish"),
                    task="task-01",
                    status="complete",
                )
            disabled_guard.assert_called_once()
            self.assertNotEqual(
                str(downstream.exception),
                journal.LEGACY_ACTIVATION_LEDGER_INCOMPLETE,
            )
            self.assertNotEqual(self._run_file_bytes(run_dir), before)

    def _seed_gh17_wedge(
        self,
        repo: Path,
        run_id: str,
        *,
        explicit_gap_run_id: str | None = None,
    ) -> tuple[Path, dict[str, object]]:
        self._open_legacy_run(repo, run_id)
        run_dir = self.run_dir(repo, run_id)
        journal_path = run_dir / "journal.jsonl"
        legacy_prefix = journal_path.read_bytes()
        with batch.batch_lock(run_dir, create=True):
            pass

        task = {
            "type": "task",
            "id": "task-01",
            "status": "active",
            "goal": "Reproduce the historical GH17 recovery wedge",
            "acceptance": ["Recovery does not reapply durable records"],
            "files": ["src/example.py"],
            "run_id": run_id,
            "recorded_at": "2026-09-10T02:00:00Z",
        }
        task_bytes = journal._journal_line(task)
        task_key = key(f"{run_id}-legacy-task")
        task_inputs = {
            "task": "task-01",
            "goal": task["goal"],
            "acceptance": task["acceptance"],
            "file": task["files"],
        }
        _task_request, task_request_sha256 = batch.normalized_request(
            repo.resolve(), run_id, "journal task-start", task_inputs
        )
        task_journal = legacy_prefix + task_bytes
        task_receipt = {
            "schema": journal.BATCH_RECEIPT_SCHEMA,
            "idempotency_key": task_key,
            "request_sha256": task_request_sha256,
            "base_size": len(legacy_prefix),
            "batch_sha256": journal._sha256(task_bytes),
            "record_count": 1,
            "journal_size": len(task_journal),
            "journal_sha256": journal._sha256(task_journal),
            "recorded_at": "2026-09-10T02:00:00Z",
        }
        task_receipt_line = (
            journal._canonical_json_bytes(task_receipt) + b"\n"
        )

        def raw_verification(
            check_id: str,
            observation: str,
            recorded_at: str,
            *,
            legacy: bool = False,
        ) -> dict[str, object]:
            record = {
                "type": "verification",
                "id": check_id,
                "task": "task-01",
                "criterion": "mutation",
                "method": "bash",
                "check": "true",
                "result": "passed",
                "observation": observation,
                "evidence": [],
                "run_id": run_id,
                "recorded_at": recorded_at,
            }
            if legacy:
                del record["run_id"]
            return record

        raw_first = raw_verification(
            "check-01",
            "raw mutation one",
            "2026-09-10T02:00:01Z",
            legacy=True,
        )
        if explicit_gap_run_id is not None:
            raw_first["run_id"] = explicit_gap_run_id
        raw_second = raw_verification(
            "check-02",
            "raw mutation two",
            "2026-09-10T02:00:02Z",
            legacy=True,
        )
        gap_bytes = journal._journal_line(raw_first) + journal._journal_line(
            raw_second
        )
        padding = 786 - len(gap_bytes)
        self.assertGreaterEqual(padding, 0)
        raw_second["observation"] = str(raw_second["observation"]) + (
            "x" * padding
        )
        gap_bytes = journal._journal_line(raw_first) + journal._journal_line(
            raw_second
        )
        self.assertEqual(len(gap_bytes), 786)

        typed_verification = raw_verification(
            "check-03",
            "fully applied typed verification",
            "2026-09-10T02:00:03Z",
        )
        typed_bytes = journal._journal_line(typed_verification)
        gap_base = len(task_journal)
        gap_end = gap_base + len(gap_bytes)
        historical_journal = task_journal + gap_bytes + typed_bytes
        journal_path.write_bytes(historical_journal)

        spent_key = key(f"{run_id}-typed-verification")
        spent_inputs = {
            "task": "task-01",
            "criterion": typed_verification["criterion"],
            "method": typed_verification["method"],
            "check": typed_verification["check"],
            "result": typed_verification["result"],
            "observation": typed_verification["observation"],
            "evidence": [],
            "binding_chain": None,
            "binding_id": None,
        }
        _spent_request, spent_request_sha256 = batch.normalized_request(
            repo.resolve(), run_id, "journal verification-add", spent_inputs
        )
        spent_receipt = {
            "schema": journal.BATCH_RECEIPT_SCHEMA,
            "idempotency_key": spent_key,
            "request_sha256": spent_request_sha256,
            "base_size": gap_end,
            "batch_sha256": journal._sha256(typed_bytes),
            "record_count": 1,
            "journal_size": len(historical_journal),
            "journal_sha256": journal._sha256(historical_journal),
            "recorded_at": typed_verification["recorded_at"],
        }
        spent_receipt_line = (
            journal._canonical_json_bytes(spent_receipt) + b"\n"
        )
        ledger_lines = [task_receipt_line, spent_receipt_line]
        (run_dir / journal.BATCH_RECEIPTS_NAME).write_bytes(
            b"".join(ledger_lines)
        )
        intent = self._write_landed_intent_for_last_receipt(
            run_dir, ledger_lines
        )
        return run_dir, {
            "legacy_prefix": legacy_prefix,
            "task": task,
            "task_receipt": task_receipt,
            "gap_records": (raw_first, raw_second),
            "gap_bytes": gap_bytes,
            "gap_base": gap_base,
            "gap_end": gap_end,
            "typed_verification": typed_verification,
            "spent_receipt": spent_receipt,
            "intent": intent,
            "historical_journal": historical_journal,
        }

    def _assert_gh17_recovered(
        self,
        run_dir: Path,
        context: dict[str, object],
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        journal_path = run_dir / "journal.jsonl"
        records, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        markers = self._activation_markers(records)
        self.assertEqual(len(markers), 1)
        marker = {
            name: value
            for name, value in markers[0].items()
            if name != "_line"
        }
        historical_journal = context["historical_journal"]
        self.assertIsInstance(historical_journal, bytes)
        self.assertEqual(
            journal_path.read_bytes(),
            historical_journal + journal._journal_line(marker),
        )
        self.assertEqual(marker["receipt_origin_size"], len(context["legacy_prefix"]))
        self.assertEqual(
            marker["receipt_origin_sha256"],
            journal._sha256(context["legacy_prefix"]),
        )
        for check_id in ("check-01", "check-02", "check-03"):
            self.assertEqual(
                sum(
                    record.get("type") == "verification"
                    and record.get("id") == check_id
                    for record in records
                ),
                1,
            )

        receipts = [
            json.loads(line)
            for line in (
                run_dir / journal.BATCH_RECEIPTS_NAME
            ).read_bytes().splitlines()
        ]
        repairs = [
            receipt
            for receipt in receipts
            if receipt.get("repaired") is True
        ]
        self.assertEqual(len(repairs), 1)
        self.assertEqual(repairs[0]["base_size"], context["gap_base"])
        self.assertEqual(repairs[0]["journal_size"], context["gap_end"])
        self.assertEqual(repairs[0]["record_count"], 2)
        self.assertEqual(
            repairs[0]["batch_sha256"],
            journal._sha256(context["gap_bytes"]),
        )
        spent_receipt = context["spent_receipt"]
        self.assertIsInstance(spent_receipt, dict)
        self.assertEqual(
            sum(
                receipt["idempotency_key"]
                == spent_receipt["idempotency_key"]
                for receipt in receipts
            ),
            1,
        )
        marker_base = len(historical_journal)
        activation_receipts = [
            receipt
            for receipt in receipts
            if receipt.get("repaired") is not True
            and receipt["base_size"] == marker_base
            and receipt["batch_sha256"]
            == journal._sha256(journal._journal_line(marker))
        ]
        self.assertEqual(len(activation_receipts), 1)
        self.assertEqual(activation_receipts[0]["record_count"], 1)
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())
        return marker, receipts

    def test_gh17_shape_recovers_without_reapplication(self) -> None:
        run_id = "run-20260910-gh17-no-reapplication"
        with self.api_environment():
            run_dir, context = self._seed_gh17_wedge(self.repo, run_id)
            self.assertTrue(
                all(
                    "run_id" not in record
                    for record in context["gap_records"]
                )
            )
            historical_journal = context["historical_journal"]
            self.assertIsInstance(historical_journal, bytes)
            outcome = batch.recover_batch(self.repo, run_id)
            self.assertTrue(outcome.repeated)
            self.assertEqual(outcome.records, (context["typed_verification"],))
            self.assertEqual(outcome.receipt, context["spent_receipt"])
            marker, _receipts = self._assert_gh17_recovered(
                run_dir, context
            )

            journal_path = run_dir / "journal.jsonl"
            before_raw = self._run_file_bytes(run_dir)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                "activated writer requires typed builder",
            ):
                journal.append_owned_record(
                    journal_path,
                    {
                        "type": "decision",
                        "id": "decision-02",
                        "resolution": "Do not replay the recovered transaction",
                        "basis": [],
                        "run_id": run_id,
                        "recorded_at": "2026-09-10T02:00:04Z",
                    },
                )
            self.assertEqual(self._run_file_bytes(run_dir), before_raw)
            self.assertEqual(marker["id"], "decision-01")

            finished = builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=key("gh17-task-finish"),
                task="task-01",
                status="complete",
            )
            self.assertEqual(finished.records[0]["status"], "complete")
            closed = builders.run_close(
                self.repo,
                run_id,
                idempotency_key=key("gh17-run-close"),
                judgment="blocked",
                summary="GH17 recovery and typed continuation completed",
                risks=[],
                follow_ups=[],
            )
            self.assertEqual(closed.records[0]["type"], "run_closed")

    def test_gh17_shape_refuses_explicit_foreign_gap_run_id(self) -> None:
        run_id = "run-20260910-gh17-foreign-gap"
        with self.api_environment():
            run_dir, context = self._seed_gh17_wedge(
                self.repo,
                run_id,
                explicit_gap_run_id="run-20260910-gh17-foreign-source",
            )
            gap_records = context["gap_records"]
            self.assertEqual(
                gap_records[0]["run_id"],
                "run-20260910-gh17-foreign-source",
            )
            self.assertNotIn("run_id", gap_records[1])
            before = self._run_file_bytes(run_dir)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                journal.BATCH_DIVERGED,
            ):
                batch.recover_batch(self.repo, run_id)
            self.assertEqual(self._run_file_bytes(run_dir), before)

    def test_recovery_activation_crash_matrix(self) -> None:
        for crash_point in (
            "after-repair",
            "partial-marker",
            "marker-fsync",
            "partial-activation-receipt",
            "before-intent-unlink",
        ):
            with self.subTest(crash_point=crash_point):
                repo, _ = self._new_repo(
                    f"repo-recovery-activation-{crash_point}"
                )
                run_id = f"run-20260910-recovery-activation-{crash_point}"
                with self.api_environment():
                    run_dir, context = self._seed_gh17_wedge(repo, run_id)
                    original_prefix = batch._append_missing_prefix
                    original_append = batch._append_named_file

                    def crash_prefix(
                        locked: batch.BatchLock,
                        name: str,
                        base_size: int,
                        base_sha256: str,
                        intended: bytes,
                        **kwargs: object,
                    ) -> journal.ExactFile:
                        result = original_prefix(
                            locked,
                            name,
                            base_size,
                            base_sha256,
                            intended,
                            **kwargs,
                        )
                        if (
                            crash_point == "after-repair"
                            and name == journal.BATCH_RECEIPTS_NAME
                            and b'"repaired":true' in intended
                        ) or (
                            crash_point == "marker-fsync"
                            and name == "journal.jsonl"
                        ):
                            raise RuntimeError(
                                f"recovery activation crash: {crash_point}"
                            )
                        return result

                    def crash_append(
                        locked: batch.BatchLock,
                        name: str,
                        payload: bytes,
                        expected: journal.FileObservation,
                        **kwargs: object,
                    ) -> None:
                        should_crash = (
                            crash_point == "partial-marker"
                            and name == "journal.jsonl"
                        ) or (
                            crash_point == "partial-activation-receipt"
                            and name == journal.BATCH_RECEIPTS_NAME
                            and b'"repaired":true' not in payload
                        )
                        if not should_crash:
                            original_append(
                                locked, name, payload, expected, **kwargs
                            )
                            return
                        prefix = payload[: max(1, len(payload) // 2)]
                        original_append(
                            locked, name, prefix, expected, **kwargs
                        )
                        raise RuntimeError(
                            f"recovery activation crash: {crash_point}"
                        )

                    if crash_point in {"after-repair", "marker-fsync"}:
                        patcher = mock.patch.object(
                            batch,
                            "_append_missing_prefix",
                            side_effect=crash_prefix,
                        )
                    elif crash_point == "before-intent-unlink":
                        patcher = mock.patch.object(
                            batch,
                            "_unlink_intent",
                            side_effect=RuntimeError(
                                f"recovery activation crash: {crash_point}"
                            ),
                        )
                    else:
                        patcher = mock.patch.object(
                            batch, "_append_named_file", side_effect=crash_append
                        )
                    with patcher, self.assertRaisesRegex(
                        RuntimeError,
                        f"recovery activation crash: {crash_point}",
                    ):
                        batch.recover_batch(repo, run_id)

                    intent_path = run_dir / journal.BATCH_INTENT_NAME
                    self.assertTrue(intent_path.is_file())
                    before_read = self._run_file_bytes(run_dir)
                    visible, issues = journal.read_journal(
                        run_dir / "journal.jsonl"
                    )
                    self.assertEqual(visible, [])
                    self.assertEqual(
                        issues, [journal.JOURNAL_READ_TRANSACTION_REFUSAL]
                    )
                    self.assertEqual(self._run_file_bytes(run_dir), before_read)

                    recovered = batch.recover_batch(repo, run_id)
                    self.assertTrue(recovered.repeated)
                    self.assertEqual(
                        recovered.records, (context["typed_verification"],)
                    )
                    self._assert_gh17_recovered(run_dir, context)

    def test_repair_receipt_n_record_members_rederived(self) -> None:
        attacks = (
            "repair-count",
            "repair-batch-hash",
            "repair-request-hash",
            "marker-origin-size",
            "marker-origin-hash",
            "marker-grammar",
            "following-receipt-time",
        )
        for attack in attacks:
            with self.subTest(attack=attack):
                repo, _ = self._new_repo(f"repo-n-rederive-{attack}")
                run_id = f"run-20260910-n-rederive-{attack}"
                with self.api_environment():
                    run_dir, context = self._seed_gh17_wedge(repo, run_id)
                    batch.recover_batch(repo, run_id)
                    marker, receipts = self._assert_gh17_recovered(
                        run_dir, context
                    )
                    journal_path = run_dir / "journal.jsonl"
                    ledger_path = run_dir / journal.BATCH_RECEIPTS_NAME
                    ledger_lines = ledger_path.read_bytes().splitlines(
                        keepends=True
                    )
                    repair_index = next(
                        index
                        for index, receipt in enumerate(receipts)
                        if receipt.get("repaired") is True
                    )

                    if attack.startswith("repair-"):
                        repair = dict(receipts[repair_index])
                        if attack == "repair-count":
                            repair["record_count"] = 1
                        elif attack == "repair-batch-hash":
                            repair["batch_sha256"] = key(
                                "forged-n-record-batch"
                            )
                        else:
                            repair["request_sha256"] = key(
                                "forged-n-record-request"
                            )
                        ledger_lines[repair_index] = (
                            journal._canonical_json_bytes(repair) + b"\n"
                        )
                        ledger_path.write_bytes(b"".join(ledger_lines))
                    elif attack == "following-receipt-time":
                        spent = context["spent_receipt"]
                        self.assertIsInstance(spent, dict)
                        following_index = next(
                            index
                            for index, receipt in enumerate(receipts)
                            if receipt["idempotency_key"]
                            == spent["idempotency_key"]
                        )
                        following = dict(receipts[following_index])
                        following["recorded_at"] = "2026-09-10T02:59:59Z"
                        ledger_lines[following_index] = (
                            journal._canonical_json_bytes(following) + b"\n"
                        )
                        ledger_path.write_bytes(b"".join(ledger_lines))
                    else:
                        journal_lines = journal_path.read_bytes().splitlines(
                            keepends=True
                        )
                        historical_journal = b"".join(journal_lines[:-1])
                        mutated_marker = dict(marker)
                        if attack == "marker-origin-size":
                            mutated_marker["receipt_origin_size"] = (
                                int(marker["receipt_origin_size"]) + 1
                            )
                        elif attack == "marker-origin-hash":
                            mutated_marker["receipt_origin_sha256"] = key(
                                "forged-marker-origin"
                            )
                        else:
                            mutated_marker["resolution"] = (
                                journal.WRITER_ACTIVATION_RESOLUTION[:-1] + "2"
                            )
                        mutated_marker_line = journal._journal_line(
                            mutated_marker
                        )
                        self.assertEqual(
                            len(mutated_marker_line), len(journal_lines[-1])
                        )
                        journal_path.write_bytes(
                            historical_journal + mutated_marker_line
                        )
                        activation_index = next(
                            index
                            for index, receipt in enumerate(receipts)
                            if receipt.get("repaired") is not True
                            and receipt["base_size"]
                            == len(historical_journal)
                        )
                        activation_receipt = (
                            batch._recovery_activation_receipt(
                                repository=repo.resolve(),
                                run_id=run_id,
                                marker=mutated_marker,
                                historical_journal=historical_journal,
                                spent_intent=context["intent"],
                                spent_receipt=context["spent_receipt"],
                            )
                        )
                        ledger_lines[activation_index] = (
                            journal._canonical_json_bytes(activation_receipt)
                            + b"\n"
                        )
                        ledger_path.write_bytes(b"".join(ledger_lines))

                    before = self._run_file_bytes(run_dir)
                    with batch.batch_lock(
                        run_dir, create=False
                    ) as locked, self.assertRaisesRegex(
                        journal.CoordinationRefusal,
                        journal.BATCH_DIVERGED,
                    ):
                        batch._load_receipts(locked)
                    self.assertEqual(self._run_file_bytes(run_dir), before)

    def test_stable_reader_rederives_every_n_record_repair_member(self) -> None:
        attacks = (
            "repair-schema",
            "repair-idempotency-key",
            "repair-request-hash",
            "repair-base-size",
            "repair-batch-hash",
            "repair-count",
            "repair-journal-size",
            "repair-journal-hash",
            "repair-recorded-at",
            "repair-flag",
            "repair-reason",
            "following-idempotency-key",
            "following-recorded-at",
        )
        for attack in attacks:
            with self.subTest(attack=attack):
                repo, _ = self._new_repo(f"repo-reader-rederive-{attack}")
                run_id = f"run-20260910-reader-rederive-{attack}"
                with self.api_environment():
                    run_dir, context = self._seed_gh17_wedge(repo, run_id)
                    batch.recover_batch(repo, run_id)
                    _marker, receipts = self._assert_gh17_recovered(
                        run_dir, context
                    )
                    journal_path = run_dir / "journal.jsonl"
                    ledger_path = run_dir / journal.BATCH_RECEIPTS_NAME
                    ledger_lines = ledger_path.read_bytes().splitlines(
                        keepends=True
                    )
                    repair_index = next(
                        index
                        for index, receipt in enumerate(receipts)
                        if receipt.get("repaired") is True
                    )

                    if attack.startswith("following-"):
                        spent = context["spent_receipt"]
                        self.assertIsInstance(spent, dict)
                        following_index = next(
                            index
                            for index, receipt in enumerate(receipts)
                            if receipt["idempotency_key"]
                            == spent["idempotency_key"]
                        )
                        following = dict(receipts[following_index])
                        if attack == "following-idempotency-key":
                            following["idempotency_key"] = key(
                                "forged-reader-following-key"
                            )
                        else:
                            following["recorded_at"] = (
                                "2026-09-10T02:59:59Z"
                            )
                        ledger_lines[following_index] = (
                            journal._canonical_json_bytes(following) + b"\n"
                        )
                        ledger_path.write_bytes(b"".join(ledger_lines))
                    else:
                        repair = dict(receipts[repair_index])
                        if attack == "repair-schema":
                            repair["schema"] = "forge-journal-batch-receipt/2"
                        elif attack == "repair-idempotency-key":
                            repair["idempotency_key"] = key(
                                "forged-reader-repair-key"
                            )
                        elif attack == "repair-request-hash":
                            repair["request_sha256"] = key(
                                "forged-reader-repair-request"
                            )
                        elif attack == "repair-base-size":
                            repair["base_size"] = int(repair["base_size"]) + 1
                        elif attack == "repair-batch-hash":
                            repair["batch_sha256"] = key(
                                "forged-reader-repair-batch"
                            )
                        elif attack == "repair-count":
                            repair["record_count"] = 1
                        elif attack == "repair-journal-size":
                            repair["journal_size"] = (
                                int(repair["journal_size"]) - 1
                            )
                        elif attack == "repair-journal-hash":
                            repair["journal_sha256"] = key(
                                "forged-reader-repair-journal"
                            )
                        elif attack == "repair-recorded-at":
                            repair["recorded_at"] = "2026-09-10T02:59:58Z"
                        elif attack == "repair-flag":
                            repair["repaired"] = False
                        else:
                            repair["repair_reason"] = (
                                batch._BATCH_GAP_REPAIR_REASON + "."
                            )
                        ledger_lines[repair_index] = (
                            journal._canonical_json_bytes(repair) + b"\n"
                        )
                        ledger_path.write_bytes(b"".join(ledger_lines))

                    before = self._run_file_bytes(run_dir)
                    visible, issues = journal.read_journal(journal_path)
                    self.assertEqual(visible, [])
                    self.assertEqual(
                        issues, [journal.JOURNAL_READ_TRANSACTION_REFUSAL]
                    )
                    self.assertEqual(self._run_file_bytes(run_dir), before)

    def test_writer_activation_controls_are_independently_load_bearing(self) -> None:
        for control in sorted(journal.WRITER_ACTIVATION_CONTROLS):
            with self.subTest(control=control):
                repo, _ = self._new_repo(f"repo-activation-control-{control}")
                run_id = f"run-20260910-activation-control-{control}"
                with self.api_environment():
                    if control == "recovery-extension":
                        run_dir, _context = self._seed_gh17_wedge(
                            repo, run_id
                        )
                    else:
                        self._open_legacy_run(repo, run_id)
                        run_dir = self.run_dir(repo, run_id)
                        if control == "marker-injection":
                            with batch.batch_lock(run_dir, create=True):
                                pass
                        else:
                            self.start_task(repo, run_id)
                    before = self._run_file_bytes(run_dir)
                    reduced = journal.WRITER_ACTIVATION_CONTROLS - {control}
                    with mock.patch.object(
                        journal, "WRITER_ACTIVATION_CONTROLS", reduced
                    ):
                        with self.assertRaises(journal.CoordinationRefusal):
                            if control == "marker-injection":
                                self.start_task(repo, run_id)
                            elif control == "marker-recognition":
                                journal.append_owned_record(
                                    run_dir / "journal.jsonl",
                                    {
                                        "type": "decision",
                                        "id": "decision-02",
                                        "resolution": "Recognition must fail closed",
                                        "basis": [],
                                        "run_id": run_id,
                                        "recorded_at": "2026-09-10T03:00:00Z",
                                    },
                                )
                            elif control == "receipt-origin":
                                builders.task_finish(
                                    repo,
                                    run_id,
                                    idempotency_key=key(
                                        "disabled-receipt-origin"
                                    ),
                                    task="task-01",
                                    status="complete",
                                )
                            else:
                                batch.recover_batch(repo, run_id)
                    self.assertEqual(self._run_file_bytes(run_dir), before)

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
        self.assertEqual(recovered.records[-1]["type"], "run_closed")
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
                self.assertEqual(recovered.records[-1]["type"], "run_closed")
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
        chain_id: str = "c-2026-08-28T120000Z-abcd",
    ) -> dict[str, object]:
        preimage: dict[str, object] = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain_id,
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
        tree_sha1 = "1" * 40
        tree_sha256 = "2" * 64
        candidate_v2_sha1 = {
            "kind": "git-tree-candidate-v2",
            "value": {
                "authorization_id": journal._git_tree_candidate_authorization_id(
                    "sha1", tree_sha1
                ),
                "object_format": "sha1",
                "tree_oid": tree_sha1,
            },
        }
        candidate_v2_sha256 = {
            "kind": "git-tree-candidate-v2",
            "value": {
                "authorization_id": journal._git_tree_candidate_authorization_id(
                    "sha256", tree_sha256
                ),
                "object_format": "sha256",
                "tree_oid": tree_sha256,
            },
        }
        vectors = (
            self.binding("staged"),
            self.binding("tree-sha1", candidate=candidate_v2_sha1),
            self.binding("tree-sha256", candidate=candidate_v2_sha256),
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

        malformed_v2 = copy.deepcopy(vectors[1])
        malformed_v2["candidate"]["value"]["authorization_id"] = key("wrong-tree")
        malformed_preimage = {
            name: malformed_v2[name]
            for name in ("schema", "source_record", "candidate", "review")
        }
        malformed_v2["binding_id"] = journal._sha256(
            journal._canonical_json_bytes(malformed_preimage)
        )
        self.assertFalse(journal._binding_shape_valid(malformed_v2))

        wrong_length = copy.deepcopy(vectors[1])
        wrong_length["candidate"]["value"]["tree_oid"] = "9" * 64
        wrong_length_preimage = {
            name: wrong_length[name]
            for name in ("schema", "source_record", "candidate", "review")
        }
        wrong_length["binding_id"] = journal._sha256(
            journal._canonical_json_bytes(wrong_length_preimage)
        )
        self.assertFalse(journal._binding_shape_valid(wrong_length))

        structured_v1 = self.binding(
            "structured-v1",
            candidate={
                "kind": "staged-diff-sha256",
                "value": copy.deepcopy(candidate_v2_sha1["value"]),
            },
        )
        self.assertFalse(journal._binding_shape_valid(structured_v1))

        with mock.patch.object(
            journal,
            "BINDING_CANDIDATE_KINDS",
            journal.BINDING_CANDIDATE_KINDS - {"git-tree-candidate-v2"},
        ):
            self.assertFalse(journal._binding_shape_valid(vectors[1]))

    def test_commit_candidate_binding_reconstructs_v2_without_relabeling_history(self) -> None:
        for object_format, tree_oid in (("sha1", "3" * 40), ("sha256", "4" * 64)):
            with self.subTest(object_format=object_format):
                authorization_id = journal._git_tree_candidate_authorization_id(
                    object_format, tree_oid
                )
                candidate = {
                    "schema": "forge-commit-candidate/2",
                    "sha256": authorization_id,
                    "authorization_id": authorization_id,
                    "object_format": object_format,
                    "tree_oid": tree_oid,
                    "base_commit_oid": "5" * len(tree_oid),
                    "review_diff_sha256": key(f"review-{object_format}"),
                    "review_diff_byte_count": 17,
                    "computed_at": "2026-09-07T12:00:00Z",
                }
                self.assertEqual(
                    builders._candidate_binding_for_state(
                        "commit", {"candidate": candidate}
                    ),
                    {
                        "kind": "git-tree-candidate-v2",
                        "value": {
                            "authorization_id": authorization_id,
                            "object_format": object_format,
                            "tree_oid": tree_oid,
                        },
                    },
                )

                malformed = copy.deepcopy(candidate)
                malformed["review_diff_byte_count"] = -1
                self.assertIsNone(
                    builders._candidate_binding_for_state(
                        "commit", {"candidate": malformed}
                    )
                )

        historical = key("historical-staged-diff")
        self.assertEqual(
            builders._candidate_binding_for_state(
                "commit",
                {
                    "candidate": {
                        "sha256": historical,
                        "computed_at": "2026-08-28T12:00:00Z",
                    }
                },
            ),
            {"kind": "staged-diff-sha256", "value": historical},
        )

        tombstone = {"fixture": "canonical-source"}
        historical_tombstone = builders.tombstone_abort_binding(
            tombstone,
            "c-2026-08-28T120000Z-abcd",
            historical,
        )
        self.assertEqual(
            historical_tombstone["candidate"],
            {"kind": "staged-diff-sha256", "value": historical},
        )
        v2_value = builders._candidate_binding_for_state(
            "commit", {"candidate": candidate}
        )["value"]
        v2_tombstone = builders.tombstone_abort_binding(
            tombstone,
            "c-2026-08-28T120000Z-abcd",
            v2_value,
        )
        self.assertEqual(
            v2_tombstone["candidate"],
            {"kind": "git-tree-candidate-v2", "value": v2_value},
        )

    def test_commit_identity_binding_projects_existing_verification_type(self) -> None:
        tree_oid = "6" * 40
        authorization_id = journal._git_tree_candidate_authorization_id(
            "sha1", tree_oid
        )
        candidate_state = {
            "schema": "forge-commit-candidate/2",
            "sha256": authorization_id,
            "authorization_id": authorization_id,
            "object_format": "sha1",
            "tree_oid": tree_oid,
            "base_commit_oid": "7" * 40,
            "review_diff_sha256": key("identity-review"),
            "review_diff_byte_count": 23,
            "computed_at": "2026-09-07T12:00:00Z",
        }
        candidate_binding = builders._candidate_binding_for_state(
            "commit", {"candidate": candidate_state}
        )
        self.assertIsNotNone(candidate_binding)
        produced_sha = "8" * 40
        identity = {
            "result": "passed",
            "produced_sha": produced_sha,
            "expected": {
                "parent": "7" * 40,
                "tree": tree_oid,
                "message_digest": key("message"),
            },
            "observed": {
                "parent": ["7" * 40],
                "tree": [tree_oid],
                "message_digest": key("message"),
            },
            "checks": {
                "head-movement": True,
                "exact-single-parent": True,
                "exact-tree": True,
                "exact-message": True,
            },
            "transcript": ".forge/chains/candidate/identity.txt",
        }
        intent = {
            "candidate": authorization_id,
            "authorization_id": authorization_id,
            "object_format": "sha1",
            "expected_tree_oid": tree_oid,
            "pre_head": "7" * 40,
        }
        prior = {
            "candidate": copy.deepcopy(candidate_state),
            "commit_result": {"intent": copy.deepcopy(intent)},
            "authorization": {"consumed": False, "consumed_at": None},
        }
        current = copy.deepcopy(prior)
        current["commit_result"]["identity"] = copy.deepcopy(identity)
        source_digest = key("identity-source")
        source_event = {
            "digest": source_digest,
            "payload": {
                "at": "2026-09-07T12:01:00Z",
                "details": copy.deepcopy(identity),
                "event": "commit_identity_checked",
                "state": copy.deepcopy(current),
            },
        }
        binding = self.binding("identity", candidate=candidate_binding)
        binding["source_record"]["event_digest"] = source_digest
        binding_preimage = {
            name: binding[name]
            for name in ("schema", "source_record", "candidate", "review")
        }
        binding["binding_id"] = journal._sha256(
            journal._canonical_json_bytes(binding_preimage)
        )
        record = {
            "type": "verification",
            "criterion": "gate-2: produced commit identity",
            "result": "passed",
        }
        self.assertTrue(
            builders._binding_matches_source_fact(
                binding,
                record,
                source_event,
                prior,
                current,
                family="commit",
            )
        )
        self.assertTrue(
            builders._binding_is_current(
                current,
                binding,
                record,
                source_event,
                prior,
                current,
                ((source_event, prior, current, (), None),),
                chain_family="commit",
            )
        )

        landing = copy.deepcopy(current)
        landing["state"] = "closed"
        landing["authorization"] = {"consumed": True, "consumed_at": "now"}
        landing["commit_result"]["commit_sha"] = produced_sha
        self.assertTrue(builders._commit_v2_landing_identity_valid(landing))
        landing["commit_result"]["identity"]["result"] = "failed"
        self.assertFalse(builders._commit_v2_landing_identity_valid(landing))

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

    def test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task(self) -> None:
        """Revision 13: an abort decision retires its chain's records from landing correlation."""
        aborted_chain = "c-2026-08-28T110000Z-ab01"
        aborted_candidate = {"kind": "staged-diff-sha256", "value": key("aborted-candidate")}
        stale_gate = self.binding("stale-gate", chain_id=aborted_chain, candidate=aborted_candidate)
        abort = self.binding("abort", chain_id=aborted_chain, candidate=aborted_candidate)
        baseline = self.correlation_records()
        # A gate drained by a chain that was later aborted, without an abort decision,
        # is still counted and breaks correlation (pre-revision-13 abort).
        orphaned = copy.deepcopy(baseline)
        orphaned.insert(4, {
            "type": "verification", "id": "check-00", "task": "task-01",
            "criterion": "gate-2: changelog", "result": "passed", "binding": stale_gate,
        })
        for line, record in enumerate(orphaned, start=1):
            record["_line"] = line
        self.assertEqual(
            self.issue_for(orphaned),
            ["task 'task-01' has inconsistent bound candidate across gate and landing records"],
        )
        # With the chain's abort decision present, the gate is retired.
        retired = copy.deepcopy(orphaned)
        retired.insert(5, {
            "type": "decision", "id": "decision-00", "task": "task-01",
            "outcome": "chain-abort", "binding": abort,
        })
        for line, record in enumerate(retired, start=1):
            record["_line"] = line
        self.assertEqual(self.issue_for(retired), [])
        # The terminal task must follow the abort decision.
        late_abort = copy.deepcopy(retired)
        abort_record = late_abort.pop(5)
        terminal_index = next(
            index for index, record in enumerate(late_abort)
            if record.get("type") == "task" and record.get("status") == "complete"
        )
        late_abort.insert(terminal_index + 1, abort_record)
        for line, record in enumerate(late_abort, start=1):
            record["_line"] = line
        self.assertEqual(
            self.issue_for(late_abort),
            ["terminal task 'task-01' precedes a bound chain abort decision"],
        )
        # A landing that cites the aborted chain is contradictory.
        contradictory = copy.deepcopy(retired)
        landing_index = next(
            index for index, record in enumerate(contradictory)
            if record.get("outcome") == "chain-landing"
        )
        contradictory[landing_index]["binding"] = self.binding(
            "landing-on-aborted", chain_id=aborted_chain, candidate=aborted_candidate
        )
        self.assertEqual(
            self.issue_for(contradictory),
            ["task 'task-01' has inconsistent bound candidate across gate and landing records"],
        )

    def _relined(self, records: list[dict[str, object]]) -> list[dict[str, object]]:
        for line, record in enumerate(records, start=1):
            record["_line"] = line
        return records

    def _superseded_set(self, name: str) -> list[dict[str, object]]:
        """A complete gate set plus approval for an earlier candidate of the landed chain."""
        candidate = {"kind": "staged-diff-sha256", "value": key(f"{name}-candidate")}
        return [
            {
                "type": "verification", "id": f"check-{name}-1", "task": "task-01",
                "criterion": "gate-1: project tests", "result": "passed",
                "binding": self.binding(f"{name}-gate1", candidate=candidate),
            },
            {
                "type": "verification", "id": f"check-{name}-2", "task": "task-01",
                "criterion": "gate-2: stack checks", "result": "passed",
                "binding": self.binding(f"{name}-gate2", candidate=candidate),
            },
            {
                "type": "verification", "id": f"check-{name}-3", "task": "task-01",
                "criterion": journal.GATE_3_CRITERION, "result": "passed",
                "binding": self.binding(
                    f"{name}-gate3", candidate=candidate,
                    review={
                        "verdict": "PASS", "iteration": 1,
                        "reviewer_role": "review-final", "package_digest": key(name),
                    },
                ),
            },
            {
                "type": "decision", "id": f"decision-{name}", "task": "task-01",
                "outcome": "chain-approval",
                "binding": self.binding(f"{name}-approval", candidate=candidate),
            },
        ]

    def _with_control_removed(self, control: str):
        return mock.patch.object(
            journal, "BINDING_CORRELATION_CONTROLS",
            journal.BINDING_CORRELATION_CONTROLS - {control},
        )

    def test_fr021_superseded_candidate_records_are_retired(self) -> None:
        """Revision 13 (2mu): a restaged chain's earlier candidate sets do not break landing."""
        baseline = self.correlation_records()
        inconsistent = "task 'task-01' has inconsistent bound candidate across gate and landing records"
        # Two earlier candidates drained after the mutating execution, then the landed set.
        restaged = copy.deepcopy(baseline)
        restaged[4:4] = self._superseded_set("first") + self._superseded_set("second")
        self._relined(restaged)
        self.assertEqual(self.issue_for(restaged), [])
        with self._with_control_removed("superseded-candidate"):
            self.assertEqual(self.issue_for(copy.deepcopy(restaged)), [inconsistent])
        # Supersession is per chain: the same records on another never-landed,
        # never-aborted chain stay counted and refused.
        other_chain = copy.deepcopy(baseline)
        foreign = self._superseded_set("foreign")
        for record in foreign:
            record["binding"] = self.binding(
                record["id"] + "-foreign", chain_id="c-2026-08-28T120000Z-f0e1",
                candidate=record["binding"]["candidate"],
                review=record["binding"].get("review"),
            )
        other_chain[4:4] = foreign
        self._relined(other_chain)
        self.assertEqual(self.issue_for(other_chain), [inconsistent])
        # A later set with the same candidate does not supersede an earlier one.
        landed_candidate = baseline[4]["binding"]["candidate"]
        repeated = copy.deepcopy(baseline)
        repeat_set = self._superseded_set("repeat")
        for record in repeat_set:
            record["binding"] = self.binding(
                record["id"] + "-repeat", candidate=landed_candidate,
                review=record["binding"].get("review"),
            )
        repeated[4:4] = repeat_set
        self._relined(repeated)
        self.assertEqual(journal._superseded_binding_ids(repeated), set())
        self.assertEqual(self.issue_for(repeated), [])
        # A landing followed by a different candidate on its own chain is a
        # chain that landed twice: refused, never treated as superseded.
        relanded = copy.deepcopy(restaged)
        landing_index = next(
            index for index, record in enumerate(relanded)
            if record.get("outcome") == "chain-landing"
        )
        relanded[landing_index + 1:landing_index + 1] = (
            self._superseded_set("after-landing")[:3] + [
                {
                    "type": "decision", "id": "decision-relanding", "task": "task-01",
                    "outcome": "chain-landing",
                    "binding": self.binding(
                        "relanding",
                        candidate={"kind": "staged-diff-sha256", "value": key("after-landing-candidate")},
                    ),
                },
            ]
        )
        self._relined(relanded)
        first_landing_id = relanded[landing_index]["binding"]["binding_id"]
        self.assertIn(first_landing_id, journal._superseded_binding_ids(relanded))
        self.assertEqual(self.issue_for(relanded), [inconsistent])
        # An abort decision carrying a different candidate on the landed chain
        # is the landing-beside-abort contradiction, not a supersessor.
        abort_after = copy.deepcopy(restaged)
        abort_after.insert(landing_index + 1, {
            "type": "decision", "id": "decision-abort-landed", "task": "task-01",
            "outcome": "chain-abort",
            "binding": self.binding(
                "abort-landed",
                candidate={"kind": "staged-diff-sha256", "value": key("abort-landed-candidate")},
            ),
        })
        self._relined(abort_after)
        self.assertEqual(self.issue_for(abort_after), [inconsistent])
        # A-B-A: the landed candidate's set must be fresh. Gates for the landed
        # candidate A, then a B set, then a re-implementation, then a landing
        # on A without a fresh A set is refused; with a fresh A set it passes.
        landed_candidate = baseline[4]["binding"]["candidate"]
        stale_a = self._superseded_set("stale-a")[:3]
        for record in stale_a:
            record["binding"] = self.binding(
                record["id"] + "-a", candidate=landed_candidate,
                review=record["binding"].get("review"),
            )
        reimplementation = [
            {
                "type": "execution", "agent": "codex-impl-02", "execution": "execution-02",
                "task": "task-01", "role": "implementation",
            },
            {
                "type": "execution_result", "agent": "codex-impl-02",
                "execution": "execution-02", "task": "task-01", "status": "complete",
            },
        ]
        # A second task supplies the run-level gate passes so only the
        # per-task correlation is under test at the gate-profile level.
        other_task = [
            {"type": "task", "id": "task-02", "status": "active"},
            {
                "type": "verification", "id": "check-t2-1", "task": "task-02",
                "criterion": "gate-1: project tests", "result": "passed",
                "binding": self.binding("t2-gate1", chain_id="c-2026-08-28T130000Z-0002"),
            },
            {
                "type": "verification", "id": "check-t2-2", "task": "task-02",
                "criterion": "gate-2: stack checks", "result": "passed",
                "binding": self.binding("t2-gate2", chain_id="c-2026-08-28T130000Z-0002"),
            },
            {
                "type": "verification", "id": "check-t2-3", "task": "task-02",
                "criterion": journal.GATE_3_CRITERION, "result": "passed",
                "binding": self.binding(
                    "t2-gate3", chain_id="c-2026-08-28T130000Z-0002",
                    review={
                        "verdict": "PASS", "iteration": 1,
                        "reviewer_role": "review-final", "package_digest": key("t2"),
                    },
                ),
            },
            {
                "type": "decision", "id": "decision-t2", "task": "task-02",
                "outcome": "chain-landing",
                "binding": self.binding("t2-landing", chain_id="c-2026-08-28T130000Z-0002"),
            },
            {"type": "task", "id": "task-02", "status": "complete"},
        ]
        head = baseline[:4]                       # run, task, execution, result
        fresh_a = baseline[4:7]                   # the landed A set
        landing_and_tail = baseline[7:]           # landing A, task complete, run_closed
        without_fresh = self._relined(copy.deepcopy(
            head + stale_a + self._superseded_set("b") + reimplementation
            + other_task + landing_and_tail
        ))
        self.assertEqual(self.issue_for(without_fresh), [inconsistent])
        profile_issues: list[str] = []
        journal.check_gate_profile(copy.deepcopy(without_fresh), profile_issues, [], None)
        self.assertEqual(profile_issues, [inconsistent])
        with self._with_control_removed("superseded-candidate"):
            stale_binding = stale_a[0]["binding"]["binding_id"]
            self.assertEqual(
                self.issue_for(copy.deepcopy(without_fresh)),
                [
                    f"binding '{stale_binding}' precedes the last mutating "
                    "execution for task 'task-01'"
                ],
            )
        with_fresh = self._relined(copy.deepcopy(
            head + stale_a + self._superseded_set("b") + reimplementation
            + other_task + fresh_a + landing_and_tail
        ))
        self.assertEqual(self.issue_for(with_fresh), [])
        profile_issues = []
        journal.check_gate_profile(copy.deepcopy(with_fresh), profile_issues, [], None)
        self.assertEqual(profile_issues, [])
        # Variant: B set, mutation, then only an approval for C before landing B.
        approval_only = self._relined(copy.deepcopy(
            head + self._superseded_set("b2")[:3] + reimplementation + other_task + [
                {
                    "type": "decision", "id": "decision-c", "task": "task-01",
                    "outcome": "chain-approval",
                    "binding": self.binding(
                        "c-approval",
                        candidate={"kind": "staged-diff-sha256", "value": key("c-candidate")},
                    ),
                },
            ] + [
                {
                    "type": "decision", "id": "decision-b2", "task": "task-01",
                    "outcome": "chain-landing",
                    "binding": self.binding(
                        "b2-landing",
                        candidate={"kind": "staged-diff-sha256", "value": key("b2-candidate")},
                    ),
                },
            ] + baseline[8:]
        ))
        self.assertEqual(self.issue_for(approval_only), [inconsistent])
        # The landed candidate's complete set remains required: removing its
        # gate-3 leaves only the superseded gate-3, which does not count.
        incomplete = copy.deepcopy(restaged)
        incomplete = [
            record for record in incomplete
            if not (
                record.get("criterion") == journal.GATE_3_CRITERION
                and record.get("id") == "check-03"
            )
        ]
        self._relined(incomplete)
        self.assertEqual(self.issue_for(incomplete), [inconsistent])

    def test_fr021_precedence_rule_scopes_to_the_landed_candidate(self) -> None:
        """Revision 13 (2mu): superseded and abort-retired records may precede a re-implementation."""
        baseline = self.correlation_records()
        # Superseded gates drained before the (later) mutating execution result.
        early = copy.deepcopy(baseline)
        early[2:2] = self._superseded_set("early")
        self._relined(early)
        self.assertEqual(self.issue_for(early), [])
        with self._with_control_removed("superseded-candidate"):
            issues = self.issue_for(copy.deepcopy(early))
            self.assertEqual(len(issues), 1)
            self.assertTrue(
                issues[0].startswith("binding '")
                and issues[0].endswith("precedes the last mutating execution for task 'task-01'"),
                issues,
            )
        # Abort-retired gates before the re-implementation are exempt as well.
        aborted_chain = "c-2026-08-28T110000Z-ab02"
        aborted_candidate = {"kind": "staged-diff-sha256", "value": key("aborted-early")}
        aborted = copy.deepcopy(baseline)
        aborted[2:2] = [
            {
                "type": "verification", "id": "check-ab", "task": "task-01",
                "criterion": "gate-1: project tests", "result": "passed",
                "binding": self.binding(
                    "ab-gate", chain_id=aborted_chain, candidate=aborted_candidate
                ),
            },
            {
                "type": "decision", "id": "decision-ab", "task": "task-01",
                "outcome": "chain-abort",
                "binding": self.binding(
                    "ab-abort", chain_id=aborted_chain, candidate=aborted_candidate
                ),
            },
        ]
        self._relined(aborted)
        self.assertEqual(self.issue_for(aborted), [])
        # The landed candidate's own gate preceding the last mutating result is still refused.
        preceding = copy.deepcopy(early)
        gate1_index = next(
            index for index, record in enumerate(preceding) if record.get("id") == "check-01"
        )
        result_index = next(
            index for index, record in enumerate(preceding)
            if record.get("type") == "execution_result"
        )
        preceding.insert(result_index, preceding.pop(gate1_index))
        self._relined(preceding)
        binding_id = next(
            record["binding"]["binding_id"] for record in preceding if record.get("id") == "check-01"
        )
        self.assertEqual(
            self.issue_for(preceding),
            [f"binding '{binding_id}' precedes the last mutating execution for task 'task-01'"],
        )

    def test_fr021_post_landing_result_moves_no_boundary(self) -> None:
        """Revision 13 (2mu): a result appended after the task's landing is bookkeeping."""
        baseline = self.correlation_records()
        late = copy.deepcopy(baseline)
        landing_index = next(
            index for index, record in enumerate(late) if record.get("outcome") == "chain-landing"
        )
        started_before_landing = {
            "type": "execution", "agent": "codex-impl-02", "execution": "execution-02",
            "task": "task-01", "role": "implementation",
        }
        late_result = {
            "type": "execution_result", "agent": "codex-impl-02",
            "execution": "execution-02", "task": "task-01", "status": "complete",
        }
        # The execution was recorded before the landing (between the gates and
        # the landing decision); only its result arrived afterwards.
        late.insert(landing_index + 1, late_result)
        late.insert(landing_index, started_before_landing)
        self._relined(late)
        self.assertEqual(self.issue_for(late), [])
        # An execution started after the landing is a later mutation: refused
        # by the precedence rule and by the run-level gate requirement.
        started_after = copy.deepcopy(baseline)
        started_after[landing_index + 1:landing_index + 1] = [
            copy.deepcopy(started_before_landing), copy.deepcopy(late_result),
        ]
        self._relined(started_after)
        after_binding = started_after[4]["binding"]["binding_id"]
        self.assertEqual(
            self.issue_for(started_after),
            [
                f"binding '{after_binding}' precedes the last mutating "
                "execution for task 'task-01'"
            ],
        )
        after_issues: list[str] = []
        journal.check_gate_profile(copy.deepcopy(started_after), after_issues, [], None)
        self.assertTrue(
            any("without a passing 'gate-1' verification" in issue for issue in after_issues),
            after_issues,
        )
        issues: list[str] = []
        warnings: list[str] = []
        journal.check_gate_profile(copy.deepcopy(late), issues, warnings, None)
        self.assertEqual((issues, warnings), ([], []))
        with self._with_control_removed("post-landing-result"):
            expected_binding = late[4]["binding"]["binding_id"]
            self.assertEqual(
                self.issue_for(copy.deepcopy(late)),
                [
                    f"binding '{expected_binding}' precedes the last mutating "
                    "execution for task 'task-01'"
                ],
            )
            issues = []
            journal.check_gate_profile(copy.deepcopy(late), issues, warnings, None)
            self.assertEqual(
                issues[:3],
                [
                    "run closed as passed without a passing 'gate-1' verification after the last mutating execution",
                    "run closed as passed without a passing 'gate-2' verification after the last mutating execution",
                    f"run closed as passed without a passing '{journal.GATE_3_CRITERION}' verification after the last mutating execution",
                ],
            )
        # The same result placed before the landing still moves the boundary.
        before = copy.deepcopy(baseline)
        before[7:7] = [
            {
                "type": "execution", "agent": "codex-impl-02", "execution": "execution-02",
                "task": "task-01", "role": "implementation",
            },
            {
                "type": "execution_result", "agent": "codex-impl-02",
                "execution": "execution-02", "task": "task-01", "status": "complete",
            },
        ]
        self._relined(before)
        binding_id = before[4]["binding"]["binding_id"]
        self.assertEqual(
            self.issue_for(before),
            [f"binding '{binding_id}' precedes the last mutating execution for task 'task-01'"],
        )
        # An execution that never journaled a result is still refused at run level.
        unterminated = copy.deepcopy(late)
        unterminated = [
            record for record in unterminated
            if not (record.get("type") == "execution_result" and record.get("execution") == "execution-02")
        ]
        self._relined(unterminated)
        issues = []
        journal.check_gate_profile(unterminated, issues, warnings, None)
        self.assertTrue(
            any("without a passing 'gate-1' verification" in issue for issue in issues), issues
        )

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
