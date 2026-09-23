from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import warnings
from unittest import mock

from tests._cli_loader import patch_chain_core
from tests._revision9_cli_constants import CLI, CLI_FIXTURE_SUPPORT, key
from tests._revision9_cli_support import Revision9CliSupport


class Revision9CliSurfacesIngestTests(Revision9CliSupport, CLI_FIXTURE_SUPPORT.ForgeCLIFixture):

    def test_real_unbound_fast_chain_ingests_and_receipted_retry_skips_reproof(
        self,
    ) -> None:
        prepared = self.prepare_unbound_fast_ingest(
            "run-20260828-cli-ingest-positive",
            install_captures=False,
        )
        _batch, _builders, journal = CLI._coordination_modules()
        journal_path = prepared.run_dir / "journal.jsonl"
        receipts_path = prepared.run_dir / journal.BATCH_RECEIPTS_NAME
        records_before, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        normalized_before = self.normalized_journal_records(records_before)

        exit_code, ingested = self.invoke_cli(*prepared.ingest_argv)
        self.assertEqual(exit_code, 0, ingested)
        self.assertTrue(ingested["ok"])
        self.assertEqual(ingested["schema"], "forge-cli/2")
        self.assertEqual(ingested["chain_id"], prepared.chain_id)
        self.assertEqual(ingested["state"], "closed")
        expected_citations = list(prepared.captured.values())
        self.assertEqual(ingested["evidence_refs"], expected_citations)
        for field, relative in prepared.captured.items():
            self.assertEqual(
                (prepared.run_dir / relative).read_bytes(),
                prepared.source_data[field],
            )

        records_after, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        normalized_after = self.normalized_journal_records(records_after)
        self.assertEqual(
            normalized_after[: len(normalized_before)], normalized_before
        )
        appended = normalized_after[len(normalized_before) :]
        self.assertEqual(len(appended), 9)
        terminal = appended[-1]
        self.assertEqual(
            {name: terminal[name] for name in ("type", "id", "status")},
            {"type": "task", "id": "task-01", "status": "complete"},
        )
        ordinary = appended[:-1]
        verifications = [
            record for record in ordinary if record["type"] == "verification"
        ]
        landings = [
            record
            for record in ordinary
            if record.get("outcome") == "chain-landing"
        ]
        self.assertTrue(verifications)
        self.assertTrue(
            all(record["result"] == "passed" for record in verifications)
        )
        self.assertEqual(len(verifications), 7)
        self.assertEqual(
            sum(
                record.get("criterion")
                == "gate-2: produced commit identity"
                for record in verifications
            ),
            1,
        )
        self.assertEqual(len(landings), 1)
        self.assertEqual(landings[0]["basis"], expected_citations)
        self.assertEqual(
            [
                record["binding"]["source_record"]["event_digest"]
                for record in ordinary
            ],
            prepared.selected_digests,
        )
        for record in ordinary:
            self.assertEqual(
                record["binding"]["source_record"]["chain_id"],
                prepared.chain_id,
            )
            self.assertEqual(
                record["binding"]["candidate"],
                {
                    "kind": "git-tree-candidate-v2",
                    "value": {
                        "authorization_id": prepared.materialized["candidate"][
                            "authorization_id"
                        ],
                        "object_format": prepared.materialized["candidate"][
                            "object_format"
                        ],
                        "tree_oid": prepared.materialized["candidate"]["tree_oid"],
                    },
                },
            )

        journal_after = journal_path.read_bytes()
        receipts_after = receipts_path.read_bytes()
        intent_path = prepared.run_dir / journal.BATCH_INTENT_NAME
        self.assertFalse(intent_path.exists())
        with patch_chain_core("_verify_and_build_ingest_records",
            side_effect=AssertionError("receipted retry attempted re-proof"),
        ) as verifier, mock.patch.object(
            _builders,
            "ingest_chain_records",
            side_effect=AssertionError("receipted retry re-entered the builder"),
        ) as builder:
            exit_code, repeated = self.invoke_cli(*prepared.ingest_argv)
        verifier.assert_not_called()
        builder.assert_not_called()
        self.assertEqual(exit_code, 0, repeated)
        self.assertTrue(repeated["ok"])
        self.assertIn("idempotent replay", str(repeated["message"]))
        self.assertEqual(repeated["evidence_refs"], expected_citations)
        self.assertEqual(journal_path.read_bytes(), journal_after)
        self.assertEqual(receipts_path.read_bytes(), receipts_after)
        self.assertFalse(intent_path.exists())

    def test_legacy_run_ingest_first_typed_use_activates_once_and_is_receipted(
        self,
    ) -> None:
        prepared = self.prepare_unbound_fast_ingest(
            "run-20260910-cli-ingest-legacy-first-use",
            install_captures=False,
            legacy_run=True,
        )
        _batch, _builders, journal = CLI._coordination_modules()
        journal_path = prepared.run_dir / "journal.jsonl"
        receipts_path = prepared.run_dir / journal.BATCH_RECEIPTS_NAME
        journal_before = journal_path.read_bytes()
        self.assertFalse(receipts_path.exists())

        exit_code, ingested = self.invoke_cli(*prepared.ingest_argv)

        self.assertEqual(exit_code, 0, ingested)
        self.assertTrue(ingested["ok"])
        records, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        normalized = self.normalized_journal_records(records)
        appended = normalized[2:]
        markers = [
            record
            for record in appended
            if journal._writer_activation_marker(record)
        ]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["id"], "decision-01")
        self.assertEqual(
            [
                record["id"]
                for record in appended
                if record.get("type") == "decision"
            ],
            ["decision-01", "decision-02"],
        )
        receipts = [
            json.loads(line)
            for line in receipts_path.read_bytes().splitlines()
        ]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["base_size"], len(journal_before))
        self.assertEqual(receipts[0]["record_count"], len(appended))
        self.assertEqual(
            receipts[0]["journal_size"], len(journal_path.read_bytes())
        )
        self.assertFalse(
            (prepared.run_dir / journal.BATCH_INTENT_NAME).exists()
        )

    def test_legacy_run_ingest_allocation_projection_is_load_bearing(
        self,
    ) -> None:
        prepared = self.prepare_unbound_fast_ingest(
            "run-20260910-cli-ingest-legacy-disabled",
            install_captures=False,
            legacy_run=True,
        )
        _batch, _builders, journal = CLI._coordination_modules()
        journal_path = prepared.run_dir / "journal.jsonl"
        receipts_path = prepared.run_dir / journal.BATCH_RECEIPTS_NAME
        journal_before = journal_path.read_bytes()

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch_chain_core("_ingest_allocation_records",
            side_effect=lambda _repository, state: list(state.records),
        ) as disabled_projection, patch_chain_core("register_activation_reservation_seam",
            return_value=None,
        ) as disabled_registration, mock.patch.object(
            _builders,
            "_require_no_pending_activation_outbox",
            return_value=None,
        ) as disabled_reservation, mock.patch.object(
            _builders,
            "_resolve_binding_from_descriptor",
            wraps=_builders._resolve_binding_from_descriptor,
        ) as resolver, self.cli_process_context(), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            exit_code = CLI.main(
                [
                    "--json",
                    "--repo",
                    str(self.repo),
                    *prepared.ingest_argv,
                ]
            )

        self.assertGreaterEqual(disabled_projection.call_count, 1)
        disabled_registration.assert_called()
        disabled_reservation.assert_called()
        resolver.assert_not_called()
        self.assertEqual(stderr.getvalue(), "")
        refused = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "ingest-proof-invalid")
        self.assertEqual(
            refused["message"],
            "forge: journal append refused — invalid journal record: "
            "decision.id must be unique",
        )
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertFalse(receipts_path.exists())
        self.assertFalse(
            (prepared.run_dir / journal.BATCH_INTENT_NAME).exists()
        )

    def test_captured_commit_and_merge_sources_reopen_from_the_run_root(
        self,
    ) -> None:
        run_id = "run-20260829-captured-reader-root"
        self.open_run_and_task(run_id)
        run_dir = (
            self.repo / ".codex-orchestrator" / "runs" / run_id
        )

        for family in ("commit", "merge"):
            with self.subTest(family=family), self.cli_process_context():
                raw = CLI.canonical_bytes(
                    {"schema": "fixture/1", "kind": family}
                ) + b"\n"
                digest = hashlib.sha256(raw).hexdigest()
                relative = CLI._capture_ingest_blob(
                    self.repo,
                    run_dir,
                    digest=digest,
                    name="state.json",
                    data=raw,
                )

                # A same-spelled repository path cannot shadow the canonical
                # run-relative capture selected by the shared surface table.
                repository_collision = self.repo / relative
                repository_collision.parent.mkdir(parents=True, exist_ok=True)
                repository_collision.write_bytes(b"repository collision\n")
                self.assertEqual(
                    CLI._read_ingest_input(
                        self.repo,
                        relative,
                        "ingest.state_file",
                        run_dir=run_dir,
                        expected_capture_name="state.json",
                    ),
                    raw,
                )

                with self.assertRaisesRegex(
                    CLI._coordination_modules()[2].CoordinationRefusal,
                    "record cites path outside run or repository",
                ):
                    CLI._read_ingest_input(
                        self.repo,
                        relative,
                        "ingest.state_file",
                        run_dir=run_dir,
                        expected_capture_name="events.jsonl",
                    )

    def test_captured_source_substitution_before_intent_refuses_without_append(
        self,
    ) -> None:
        prepared = self.prepare_unbound_fast_ingest(
            "run-20260829-captured-substitution",
            install_captures=False,
        )
        batch, _builders, journal = CLI._coordination_modules()
        journal_path = prepared.run_dir / "journal.jsonl"
        receipts_path = prepared.run_dir / journal.BATCH_RECEIPTS_NAME
        intent_path = prepared.run_dir / journal.BATCH_INTENT_NAME
        journal_before = journal_path.read_bytes()
        receipts_before = receipts_path.read_bytes()
        original_prepare = batch._prepare_intent
        substituted = False

        def substitute_capture(*args: object, **kwargs: object) -> object:
            nonlocal substituted
            prepared_intent = original_prepare(*args, **kwargs)
            self.assertFalse(substituted)
            target = prepared.run_dir / prepared.captured["state_file"]
            replacement = target.with_name("state.replacement")
            replacement.write_bytes(b'{"kind":"substituted"}\n')
            os.replace(replacement, target)
            substituted = True
            return prepared_intent

        with mock.patch.object(
            batch, "_prepare_intent", side_effect=substitute_capture
        ):
            exit_code, refused = self.invoke_cli(*prepared.ingest_argv)

        self.assertTrue(substituted)
        self.assertEqual(exit_code, 1, refused)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["reason_code"], "citation-out-of-root")
        self.assertEqual(
            refused["message"],
            "forge: journal append refused — record cites path outside run or "
            "repository: ingest.captured_package: "
            + prepared.captured["state_file"],
        )
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertEqual(receipts_path.read_bytes(), receipts_before)
        self.assertFalse(intent_path.exists())

    def test_captured_source_substitution_before_builder_keeps_exact_diagnostic(
        self,
    ) -> None:
        prepared = self.prepare_unbound_fast_ingest(
            "run-20260829-captured-pre-builder-substitution",
            install_captures=False,
        )
        _batch, builders, journal = CLI._coordination_modules()
        journal_path = prepared.run_dir / "journal.jsonl"
        receipts_path = prepared.run_dir / journal.BATCH_RECEIPTS_NAME
        intent_path = prepared.run_dir / journal.BATCH_INTENT_NAME
        journal_before = journal_path.read_bytes()
        receipts_before = receipts_path.read_bytes()
        original_ingest = builders.ingest_chain_records
        substituted = False

        def substitute_capture(*args: object, **kwargs: object) -> object:
            nonlocal substituted
            self.assertFalse(substituted)
            target = prepared.run_dir / prepared.captured["state_file"]
            replacement = target.with_name("state.pre-builder-replacement")
            replacement.write_bytes(b'{"kind":"substituted"}\n')
            os.replace(replacement, target)
            substituted = True
            return original_ingest(*args, **kwargs)

        with mock.patch.object(
            builders,
            "ingest_chain_records",
            side_effect=substitute_capture,
        ):
            exit_code, refused = self.invoke_cli(*prepared.ingest_argv)

        self.assertTrue(substituted)
        self.assertEqual(exit_code, 1, refused)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["reason_code"], "citation-out-of-root")
        self.assertEqual(
            refused["message"],
            "forge: journal append refused — record cites path outside run or "
            "repository: ingest.captured_package: "
            + prepared.captured["state_file"],
        )
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertEqual(receipts_path.read_bytes(), receipts_before)
        self.assertFalse(intent_path.exists())

    def test_each_ingest_proof_control_refuses_at_its_named_boundary(
        self,
    ) -> None:
        prepared = self.prepare_unbound_fast_ingest(
            "run-20260828-cli-ingest-controls",
            install_captures=True,
        )
        _batch, builders, journal = CLI._coordination_modules()
        journal_path = prepared.run_dir / "journal.jsonl"
        receipts_path = prepared.run_dir / journal.BATCH_RECEIPTS_NAME
        intent_path = prepared.run_dir / journal.BATCH_INTENT_NAME
        journal_before = journal_path.read_bytes()
        receipts_before = receipts_path.read_bytes()
        original_require = CLI._require_ingest_proof

        records, completed = CLI._verify_and_build_ingest_records(
            self.repo, prepared.run_id, prepared.verifier_inputs
        )
        self.assertTrue(records)
        self.assertEqual(completed, CLI.INGEST_PROOF_ORDER)

        proof_order = CLI.INGEST_PROOF_ORDER
        for index, control in enumerate(proof_order):
            observed: list[tuple[str, tuple[str, ...]]] = []

            def track_boundary(
                name: str, completed_proofs: list[str] | None = None
            ) -> None:
                observed.append((name, tuple(completed_proofs or ())))
                original_require(name, completed_proofs)

            enabled = frozenset(proof_order) - {control}
            with self.subTest(control=control), patch_chain_core("INGEST_PROOF_CONTROLS", enabled
            ), patch_chain_core("_REQUIRED_INGEST_PROOF_CONTROLS", enabled
            ), patch_chain_core("_require_ingest_proof", side_effect=track_boundary
            ), self.assertRaises(
                journal.CoordinationRefusal
            ) as raised:
                CLI._verify_and_build_ingest_records(
                    self.repo, prepared.run_id, prepared.verifier_inputs
                )
            self.assertEqual(str(raised.exception), builders.INGEST_PROOF_INVALID)
            self.assertEqual(
                observed,
                [
                    (name, proof_order[:position])
                    for position, name in enumerate(proof_order[: index + 1])
                ],
            )
            self.assertEqual(journal_path.read_bytes(), journal_before)
            self.assertEqual(receipts_path.read_bytes(), receipts_before)
            self.assertFalse(intent_path.exists())

        final_records, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        final_tasks = [
            record
            for record in final_records
            if record.get("type") == "task" and record.get("id") == "task-01"
        ]
        self.assertEqual(final_tasks[-1]["status"], "active")

    def test_fast_mechanical_skip_is_rejected_at_current_gates_proof(
        self,
    ) -> None:
        prepared = self.prepare_unbound_fast_ingest(
            "run-20260828-cli-ingest-fast-skip",
            install_captures=True,
            mechanical_skip=True,
        )
        _batch, builders, journal = CLI._coordination_modules()
        journal_path = prepared.run_dir / "journal.jsonl"
        receipts_path = prepared.run_dir / journal.BATCH_RECEIPTS_NAME
        journal_before = journal_path.read_bytes()
        receipts_before = receipts_path.read_bytes()
        observed: list[tuple[str, tuple[str, ...]]] = []
        original_require = CLI._require_ingest_proof

        def track_boundary(
            name: str, completed_proofs: list[str] | None = None
        ) -> None:
            observed.append((name, tuple(completed_proofs or ())))
            original_require(name, completed_proofs)

        with patch_chain_core("_require_ingest_proof", side_effect=track_boundary
        ), self.assertRaises(journal.CoordinationRefusal) as raised:
            CLI._verify_and_build_ingest_records(
                self.repo, prepared.run_id, prepared.verifier_inputs
            )
        self.assertEqual(str(raised.exception), builders.INGEST_PROOF_INVALID)
        reached = CLI.INGEST_PROOF_ORDER[:6]
        self.assertEqual(
            observed,
            [
                (name, reached[:position])
                for position, name in enumerate(reached)
            ],
        )
        self.assertEqual(reached[-1], "current-gates")
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertEqual(receipts_path.read_bytes(), receipts_before)
        self.assertFalse((prepared.run_dir / journal.BATCH_INTENT_NAME).exists())

    def test_lockless_legacy_bound_chain_activates_and_lands_cleanly(self) -> None:
        run_id = "run-20260910-lockless-bound-start"
        self.open_run_and_task(run_id, legacy=True)
        _batch, builders, journal = CLI._coordination_modules()
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        lock_path = run_dir / journal.BATCH_LOCK_NAME
        receipts_path = run_dir / journal.BATCH_RECEIPTS_NAME
        intent_path = run_dir / journal.BATCH_INTENT_NAME
        journal_path = run_dir / "journal.jsonl"
        journal_before = journal_path.read_bytes()
        self.assertFalse(lock_path.exists())
        self.assertFalse(receipts_path.exists())
        self.change("src/app.py", "VALUE = 2\n")

        exit_code, started = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "src/app.py",
            "--task",
            "task-01",
        )

        self.assertEqual(exit_code, 0, started)
        self.assertTrue(started["ok"])
        self.assertTrue(lock_path.is_file())
        self.assertFalse(receipts_path.exists())
        self.assertEqual(journal_path.read_bytes(), journal_before)
        chain_id = str(started["chain_id"])
        state = self.state(chain_id)
        self.assertEqual(state["run_binding"]["run_id"], run_id)
        self.assertEqual(state["run_binding"]["task_id"], "task-01")

        exit_code, verified = self.invoke_cli(
            "--chain-id", chain_id, "verify"
        )
        self.assertEqual(exit_code, 0, verified)
        self.assertEqual(verified["state"], "reviewing")
        self.assertIsNone(self.state(chain_id)["journal_outbox"])
        self.assertFalse(intent_path.exists())

        records, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        normalized = self.normalized_journal_records(records)
        markers = [
            record
            for record in normalized
            if journal._writer_activation_marker(record)
        ]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["id"], "decision-01")
        self.assertEqual(markers[0]["receipt_origin_size"], len(journal_before))
        self.assertEqual(
            markers[0]["receipt_origin_sha256"],
            hashlib.sha256(journal_before).hexdigest(),
        )
        receipts = [
            json.loads(line) for line in receipts_path.read_bytes().splitlines()
        ]
        self.assertGreaterEqual(len(receipts), 1)
        self.assertEqual(
            len(
                [
                    receipt
                    for receipt in receipts
                    if receipt["base_size"] == len(journal_before)
                ]
            ),
            1,
        )
        self.assertEqual(receipts[0]["base_size"], len(journal_before))
        self.assertEqual(receipts[0]["record_count"], 2)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            exit_code, requested = self.invoke_cli(
                "--chain-id", chain_id, "review", "request"
            )
        self.assertEqual(exit_code, 0, requested)
        request = self.state(chain_id)["review"]["request"]
        self.wait_for_review_completion(request)
        exit_code, reviewed = self.invoke_cli(
            "--chain-id",
            chain_id,
            "review",
            "collect",
        )
        self.assertEqual(exit_code, 0, reviewed)
        self.assertEqual(reviewed["state"], "authorized")
        self.assertIsNone(self.state(chain_id)["journal_outbox"])

        exit_code, finalized = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "finalize",
            "--message",
            "land receipt-less legacy first use",
        )
        self.assertEqual(exit_code, 0, finalized)
        self.assertEqual(finalized["state"], "closed")
        self.assertIsNone(self.state(chain_id)["journal_outbox"])
        self.assertFalse(intent_path.exists())

        with self.cli_process_context():
            finished = builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-finish"),
                task="task-01",
                status="complete",
            )
        self.assertFalse(finished.repeated)
        final_records, final_issues = journal.read_journal(journal_path)
        self.assertEqual(final_issues, [])
        self.assertEqual(
            len(
                [
                    record
                    for record in final_records
                    if journal._writer_activation_marker(record)
                ]
            ),
            1,
        )
