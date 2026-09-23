from __future__ import annotations

import base64
import copy
import json
import os
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from tests._revision9_coord_constants import key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

from codex_orchestrator import batch, builders, journal


class Revision9BatchBuilderTests(Revision9BuilderBatchSupport, unittest.TestCase):

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
