from __future__ import annotations

import datetime
import json
import os
import stat
from unittest import mock

from tests._cli_loader import patch_engine
from tests._revision9_cli_constants import CLI, CLI_FIXTURE_SUPPORT, RUNTIME, key
from tests._revision9_cli_support import Revision9CliSupport


class Revision9CliSurfacesDispositionsTests(Revision9CliSupport, CLI_FIXTURE_SUPPORT.ForgeCLIFixture):

    def test_frozen_abort_writes_explicit_tombstone_without_replay(self) -> None:
        run_id = "run-20260831-frozen-abort"
        chain_id = self.start_bound_chain(run_id)
        state_before = self.state_path(chain_id).read_bytes()
        self.events_path(chain_id).write_bytes(b"{malformed-event}\n")
        events_before = self.events_path(chain_id).read_bytes()

        exit_code, aborted = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "abort",
            "--reason",
            "operator quarantined malformed replay",
        )

        self.assertEqual(exit_code, 0, aborted)
        self.assertEqual(aborted["state"], "aborted")
        tombstone_path = (
            self.state_path(chain_id).parent
            / "tombstones"
            / f"{chain_id}.json"
        )
        tombstone = json.loads(tombstone_path.read_bytes())
        self.assertEqual(tombstone["schema"], CLI.CHAIN_TOMBSTONE_SCHEMA)
        self.assertEqual(tombstone["event"], CLI.CHAIN_TOMBSTONE_EVENT)
        self.assertEqual(tombstone["artifacts"]["state"]["status"], "captured")
        self.assertEqual(tombstone["artifacts"]["events"]["status"], "captured")
        self.assertEqual(self.state_path(chain_id).read_bytes(), state_before)
        self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)

        exit_code, status = self.invoke_cli("--chain-id", chain_id, "status")
        self.assertEqual(exit_code, 0, status)
        self.assertEqual(status["state"], "aborted")

        _batch, builders, journal = CLI._coordination_modules()
        with self.cli_process_context(), mock.patch.object(
            builders,
            "TERMINAL_CHAIN_CONTROLS",
            builders.TERMINAL_CHAIN_CONTROLS - {"tombstone"},
        ), self.assertRaisesRegex(
            journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
        ):
            builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-finish-disabled"),
                task="task-01",
                status="blocked",
            )

        with self.cli_process_context():
            finished = builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-finish"),
                task="task-01",
                status="blocked",
            )
        self.assertFalse(finished.repeated)
        self.assertTrue(self.state_path(chain_id).exists())
        self.assertTrue(self.events_path(chain_id).exists())

        with self.cli_process_context(), mock.patch.object(
            builders,
            "TERMINAL_CHAIN_CONTROLS",
            builders.TERMINAL_CHAIN_CONTROLS - {"tombstone"},
        ), self.assertRaisesRegex(
            journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
        ):
            builders.run_close(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-close-disabled"),
                judgment="blocked",
                summary="Frozen chain remains sealed by its captured tombstone",
                risks=[],
                follow_ups=[],
            )

        with self.cli_process_context():
            closed = builders.run_close(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-close"),
                judgment="blocked",
                summary="Frozen chain remains sealed by its captured tombstone",
                risks=[],
                follow_ups=[],
            )
        self.assertFalse(closed.repeated)
        self.assertTrue(self.state_path(chain_id).exists())
        self.assertTrue(self.events_path(chain_id).exists())

    def test_explicit_abort_of_readable_bound_chain_is_a_terminal_disposition(self) -> None:
        """Bead forge-plugin-437: an operator abort must not dead-end the task.

        A readable run-bound chain aborted explicitly has no landing and cannot
        be tombstoned; its authenticated terminal state is the disposition the
        landing predicate accepts, so task-finish and run-close proceed.
        """
        run_id = "run-20260904-explicit-abort"
        # A verified chain has drained gate records into the journal; the
        # abort must retire them from FR-021 correlation.
        chain_id = self.start_bound_fast_chain(run_id)
        exit_code, aborted = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "abort",
            "--reason",
            "candidate superseded by a later chain",
        )
        self.assertEqual(exit_code, 0, aborted)
        self.assertEqual(aborted["state"], "aborted")
        tombstone_path = (
            self.state_path(chain_id).parent / "tombstones" / f"{chain_id}.json"
        )
        self.assertFalse(tombstone_path.exists())
        state = json.loads(self.state_path(chain_id).read_bytes())
        self.assertEqual(state["state"], "aborted")
        self.assertIsNone(state["journal_outbox"])
        self.assertIn("aborted_at", state["commit_result"])
        _batch, builders, journal = CLI._coordination_modules()
        # Revision 13: the abort drained exactly one chain-abort decision bound
        # to the abandoned candidate, carried by the chain_aborted event and
        # receipted, and its binding replays exactly.
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        records = [
            json.loads(line)
            for line in (run_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        aborts = [
            record for record in records
            if record.get("type") == "decision" and record.get("outcome") == "chain-abort"
        ]
        self.assertEqual(len(aborts), 1)
        abort_binding = aborts[0]["binding"]
        self.assertEqual(abort_binding["source_record"]["chain_id"], chain_id)
        self.assertEqual(abort_binding["candidate"]["kind"], "git-tree-candidate-v2")
        self.assertEqual(
            abort_binding["candidate"]["value"],
            {
                "authorization_id": state["candidate"]["authorization_id"],
                "object_format": state["candidate"]["object_format"],
                "tree_oid": state["candidate"]["tree_oid"],
            },
        )
        self.assertIsNone(abort_binding["review"])
        self.assertTrue(aborts[0]["resolution"].startswith("Forge commit chain abort recorded: "))
        events = self.events(chain_id)
        self.assertEqual(events[-1]["payload"]["event"], "journal_receipted")
        self.assertEqual(events[-2]["payload"]["event"], "chain_aborted")
        carried = events[-2]["payload"]["details"]["journal_batch"]["records"]
        self.assertEqual([record["outcome"] for record in carried], ["chain-abort"])
        with self.cli_process_context():
            resolved = builders.resolve_binding(
                self.repo,
                chain_id,
                str(abort_binding["binding_id"]),
                expected_type="decision",
                expected_fields={"task": "task-01", "outcome": "chain-abort"},
                expected_run_id=run_id,
                expected_task_id="task-01",
            )
        self.assertEqual(resolved, abort_binding)
        # The disposition is load-bearing: without it the abort dead-ends the task.
        with self.cli_process_context(), mock.patch.object(
            builders,
            "TERMINAL_CHAIN_CONTROLS",
            builders.TERMINAL_CHAIN_CONTROLS - {"abort-disposition"},
        ), self.assertRaisesRegex(
            journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
        ):
            builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-finish-disabled"),
                task="task-01",
                status="complete",
            )
        with self.cli_process_context():
            finished = builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-finish"),
                task="task-01",
                status="complete",
            )
        self.assertFalse(finished.repeated)
        self.assertEqual(finished.records[0]["status"], "complete")
        with self.cli_process_context(), mock.patch.object(
            builders,
            "TERMINAL_CHAIN_CONTROLS",
            builders.TERMINAL_CHAIN_CONTROLS - {"abort-disposition"},
        ), self.assertRaisesRegex(
            journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
        ):
            builders.run_close(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-close-disabled"),
                judgment="blocked",
                summary="Aborted chain still blocks the run without the disposition",
                risks=[],
                follow_ups=[],
            )
        with self.cli_process_context():
            closed = builders.run_close(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-close"),
                judgment="passed",
                summary="The aborted chain is an explicit terminal disposition",
                risks=[],
                follow_ups=[],
            )
        self.assertFalse(closed.repeated)
        # The aborted chain's artifacts stay exactly as the abort left them.
        self.assertEqual(
            json.loads(self.state_path(chain_id).read_bytes())["state"], "aborted"
        )
        # The passed close validated: the abort decision retired the chain's
        # drained gate records (FR-021) and their repository-relative evidence
        # citations resolve through the run's repository root (FR-011,
        # Revision 13). The correlation proof below repeats it in isolation.
        with self.cli_process_context():
            validation = journal.validate_run(run_dir, gates=True)
        self.assertTrue(validation["ok"], validation)
        records = [
            json.loads(line)
            for line in (run_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        for line, record in enumerate(records, start=1):
            record["_line"] = line
        drained_gates = [
            record for record in records
            if record.get("type") == "verification"
            and record.get("result") == "passed"
            and str(record.get("criterion", "")).startswith(("gate-1: ", "gate-2: "))
            and record["binding"]["source_record"]["chain_id"] == chain_id
        ]
        self.assertGreater(len(drained_gates), 0)
        issues: list[str] = []
        journal._check_binding_correlation(records, issues)
        self.assertEqual(issues, [])
        # Without the abort decision the same drained gate records would be an
        # unretired, un-landed candidate: the decision is load-bearing.
        without_abort = [
            record for record in records if record.get("outcome") != "chain-abort"
        ]
        issues = []
        journal._check_binding_correlation(without_abort, issues)
        self.assertEqual(
            issues,
            ["task 'task-01' has inconsistent bound candidate across gate and landing records"],
        )

    def test_abort_refuses_terminal_chains_before_any_mutation(self) -> None:
        """Bead forge-plugin-437 iteration 2: an abort is never retried."""
        _batch, builders, journal = CLI._coordination_modules()
        # Retry of an abort: refused, no event, outbox null, journal unchanged.
        run_id = "run-20260904-abort-retry"
        chain_id = self.start_bound_fast_chain(run_id)
        exit_code, aborted = self.invoke_cli(
            "--chain-id", chain_id, "commit", "abort", "--reason", "first"
        )
        self.assertEqual(exit_code, 0, aborted)
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        journal_before = (run_dir / "journal.jsonl").read_bytes()
        events_before = self.events_path(chain_id).read_bytes()
        state_before = self.state_path(chain_id).read_bytes()
        exit_code, retried = self.invoke_cli(
            "--chain-id", chain_id, "commit", "abort", "--reason", "second"
        )
        self.assertEqual(exit_code, 1, retried)
        self.assertEqual(retried["reason_code"], "state-precondition")
        self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)
        self.assertEqual(self.state_path(chain_id).read_bytes(), state_before)
        self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_before)
        exit_code, status = self.invoke_cli("--chain-id", chain_id, "status")
        self.assertEqual(exit_code, 0, status)
        self.assertEqual(status["state"], "aborted")
        with self.cli_process_context():
            finished = builders.task_finish(
                self.repo, run_id, idempotency_key=key(f"{run_id}-finish"),
                task="task-01", status="complete",
            )
        self.assertEqual(finished.records[0]["status"], "complete")

    def test_abort_refuses_landed_chain_and_keeps_its_landing(self) -> None:
        """Bead forge-plugin-437 iteration 2: a landing is never rewritten."""
        _batch, builders, journal = CLI._coordination_modules()
        run_id = "run-20260904-abort-after-close"
        chain_id = self.start_bound_fast_chain(run_id)
        exit_code, finalized = self.invoke_cli(
            "--chain-id", chain_id, "commit", "finalize", "--message", "land it"
        )
        self.assertEqual(exit_code, 0, finalized)
        self.assertEqual(finalized["state"], "closed")
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        journal_before = (run_dir / "journal.jsonl").read_bytes()
        events_before = self.events_path(chain_id).read_bytes()
        landed = self.state(chain_id)
        commit_sha = landed["commit_result"]["commit_sha"]
        exit_code, aborted = self.invoke_cli(
            "--chain-id", chain_id, "commit", "abort", "--reason", "too late"
        )
        self.assertEqual(exit_code, 1, aborted)
        self.assertEqual(aborted["reason_code"], "state-precondition")
        after = self.state(chain_id)
        self.assertEqual(after["state"], "closed")
        self.assertEqual(after["commit_result"]["commit_sha"], commit_sha)
        self.assertIsNone(after["journal_outbox"])
        self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)
        self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_before)
        records = [
            json.loads(line)
            for line in (run_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(
            [record.get("outcome") for record in records if record.get("type") == "decision"
             and record.get("outcome") in {"chain-landing", "chain-abort"}],
            ["chain-landing"],
        )
        with self.cli_process_context():
            finished = builders.task_finish(
                self.repo, run_id, idempotency_key=key(f"{run_id}-finish"),
                task="task-01", status="complete",
            )
        self.assertEqual(finished.records[0]["status"], "complete")

    def test_retrospective_abort_disposition_carries_the_decision_once(self) -> None:
        """Bead forge-plugin-rtj: a legacy uncarried abort gains its disposition later."""
        _batch, builders, journal = CLI._coordination_modules()
        run_id = "run-20260905-retro-abort"
        chain_id = self.start_bound_fast_chain(run_id)
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        # A pre-revision-13 abort shape: the chain_aborted event carries nothing.
        with mock.patch.object(RUNTIME, "_build_chain_journal_records", return_value=()):
            exit_code, aborted = self.invoke_cli(
                "--chain-id", chain_id, "commit", "abort", "--reason", "legacy abort"
            )
        self.assertEqual(exit_code, 0, aborted)
        events = self.events(chain_id)
        self.assertEqual(events[-1]["payload"]["event"], "chain_aborted")
        self.assertNotIn("journal_batch", events[-1]["payload"]["details"])
        journal_before = (run_dir / "journal.jsonl").read_bytes()
        state_before = self.state(chain_id)

        # Retrospective disposition: one self-event, one carried decision, receipted.
        exit_code, disposed = self.invoke_cli("--chain-id", chain_id, "commit", "abort-disposition")
        self.assertEqual(exit_code, 0, disposed)
        self.assertEqual(disposed["state"], "aborted")
        events = self.events(chain_id)
        self.assertEqual(
            [event["payload"]["event"] for event in events[-2:]],
            ["abort_disposition_recorded", "journal_receipted"],
        )
        carried = events[-2]["payload"]["details"]["journal_batch"]["records"]
        self.assertEqual([record["outcome"] for record in carried], ["chain-abort"])
        after = self.state(chain_id)
        self.assertEqual(after["state"], "aborted")
        self.assertEqual(after["commit_result"], state_before["commit_result"])
        self.assertIsNone(after["journal_outbox"])
        records = [
            json.loads(line)
            for line in (run_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        aborts = [r for r in records if r.get("type") == "decision" and r.get("outcome") == "chain-abort"]
        self.assertEqual(len(aborts), 1)
        self.assertTrue(aborts[0]["resolution"].startswith("Forge commit chain abort disposition recorded retrospectively: "))
        self.assertEqual(
            aborts[0]["binding"]["source_record"]["event_digest"],
            events[-2]["payload"]["details"]["source_event_digest"],
        )
        with self.cli_process_context():
            resolved = builders.resolve_binding(
                self.repo, chain_id, str(aborts[0]["binding"]["binding_id"]),
                expected_type="decision", expected_fields={"task": "task-01", "outcome": "chain-abort"},
                expected_run_id=run_id, expected_task_id="task-01",
            )
        self.assertEqual(resolved, aborts[0]["binding"])

        # Single-shot: a retry refuses and changes nothing.
        journal_after = (run_dir / "journal.jsonl").read_bytes()
        events_after = self.events_path(chain_id).read_bytes()
        exit_code, retried = self.invoke_cli("--chain-id", chain_id, "commit", "abort-disposition")
        self.assertEqual(exit_code, 1, retried)
        self.assertEqual(retried["reason_code"], "state-precondition")
        self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_after)
        self.assertEqual(self.events_path(chain_id).read_bytes(), events_after)
        self.assertNotEqual(journal_after, journal_before)

        # The disposition satisfies the guards, correlation, and validation.
        with self.cli_process_context():
            finished = builders.task_finish(
                self.repo, run_id, idempotency_key=key(f"{run_id}-finish"),
                task="task-01", status="complete",
            )
            self.assertEqual(finished.records[0]["status"], "complete")
            closed = builders.run_close(
                self.repo, run_id, idempotency_key=key(f"{run_id}-close"),
                judgment="passed", summary="Legacy abort dispositioned retrospectively",
                risks=[], follow_ups=[],
            )
            self.assertFalse(closed.repeated)
            validation = journal.validate_run(run_dir, gates=True)
        self.assertTrue(validation["ok"], validation)

    def test_tombstone_disposition_retires_a_frozen_chain_after_its_task_closed(self) -> None:
        """Bead forge-plugin-11a: an operator-tombstoned chain gains its abort decision."""
        _batch, builders, journal = CLI._coordination_modules()
        run_id = "run-20260905-tombstone-disp"
        chain_id = self.start_bound_fast_chain(run_id)
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        bound_before = [
            record for record in self._journal_records(run_dir)
            if isinstance(record.get("binding"), dict)
            and record["binding"]["source_record"]["chain_id"] == chain_id
        ]
        self.assertGreaterEqual(len(bound_before), 2)
        candidate = bound_before[0]["binding"]["candidate"]["value"]
        self.assertTrue(all(r["binding"]["candidate"]["value"] == candidate for r in bound_before))
        tombstone_path = self._quarantine_and_tombstone(chain_id)
        tombstone = json.loads(tombstone_path.read_text(encoding="utf-8"))

        # Revision 11 acceptance: the task closes over the undispositioned tombstone.
        with self.cli_process_context():
            finished = builders.task_finish(
                self.repo, run_id, idempotency_key=key(f"{run_id}-finish"),
                task="task-01", status="complete",
            )
        self.assertEqual(finished.records[0]["status"], "complete")
        # Without the disposition a passed close is refused by journal-only correlation.
        projected = self._journal_records(run_dir) + [{"type": "run_closed", "judgment": "passed"}]
        for line, record in enumerate(projected, start=1):
            record["_line"] = line
        issues: list[str] = []
        journal._check_binding_correlation(projected, issues)
        self.assertEqual(
            issues, ["task 'task-01' has inconsistent bound candidate across gate and landing records"]
        )

        # The verb requires the run to be named explicitly.
        exit_code, no_run = self.invoke_cli("--chain-id", chain_id, "commit", "abort-disposition")
        self.assertEqual(exit_code, 1, no_run)
        self.assertEqual(no_run["reason_code"], "state-precondition")
        self.assertEqual(
            no_run["message"],
            "commit abort-disposition refused — tombstoned chain is not dispositionable",
        )
        journal_before = (run_dir / "journal.jsonl").read_bytes()

        exit_code, disposed = self.invoke_cli(
            "--run-id", run_id, "--chain-id", chain_id, "commit", "abort-disposition"
        )
        self.assertEqual(exit_code, 0, disposed)
        self.assertEqual(disposed["message"], f"chain {chain_id} tombstone abort disposition recorded")
        records = self._journal_records(run_dir)
        aborts = [r for r in records if r.get("type") == "decision" and r.get("outcome") == "chain-abort"]
        self.assertEqual(len(aborts), 1)
        abort = aborts[0]
        self.assertEqual(abort["task"], "task-01")
        self.assertEqual(abort["basis"], [f".forge/chains/tombstones/{chain_id}.json"])
        expected_binding = builders.tombstone_abort_binding(tombstone, chain_id, candidate)
        self.assertEqual(abort["binding"], expected_binding)
        self.assertEqual(
            abort["binding"]["source_record"]["event_digest"],
            journal._sha256(journal._canonical_json_bytes(tombstone)),
        )
        # The decision follows the terminal task record and is still accepted.
        terminal_line = max(
            i for i, r in enumerate(records) if r.get("type") == "task" and r.get("status") == "complete"
        )
        self.assertGreater(records.index(abort), terminal_line)

        # Single shot: a retry refuses and appends nothing.
        journal_after = (run_dir / "journal.jsonl").read_bytes()
        exit_code, retried = self.invoke_cli(
            "--run-id", run_id, "--chain-id", chain_id, "commit", "abort-disposition"
        )
        self.assertEqual(exit_code, 1, retried)
        self.assertEqual(retried["reason_code"], "state-precondition")
        self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_after)
        self.assertNotEqual(journal_after, journal_before)

        # The binding authenticates against the tombstone through the builders.
        with self.cli_process_context():
            resolved = builders.resolve_binding(
                self.repo, chain_id, str(abort["binding"]["binding_id"]),
                expected_type="decision", expected_fields={"outcome": "chain-abort"},
                tombstone_candidate=candidate,
            )
            self.assertEqual(resolved, abort["binding"])
            for kwargs in (
                {"expected_type": "verification", "expected_fields": {"outcome": "chain-abort"}},
                {"expected_type": "decision", "expected_fields": {"outcome": "chain-landing"}},
                {"expected_type": "decision", "expected_fields": {"outcome": "chain-abort"},
                 "tombstone_candidate": key("other-candidate")},
                {"expected_type": "decision", "expected_fields": {"outcome": "chain-abort"}},
            ):
                kwargs.setdefault("tombstone_candidate", None) if "tombstone_candidate" not in kwargs else None
                with self.subTest(refusal=kwargs):
                    with self.assertRaises(journal.CoordinationRefusal):
                        builders.resolve_binding(
                            self.repo, chain_id, str(abort["binding"]["binding_id"]), **kwargs
                        )
            with mock.patch.object(
                builders, "BUILDER_VALIDATION_CONTROLS",
                builders.BUILDER_VALIDATION_CONTROLS - {"tombstone-binding"},
            ):
                with self.assertRaises(journal.CoordinationRefusal):
                    builders.resolve_binding(
                        self.repo, chain_id, str(abort["binding"]["binding_id"]),
                        expected_type="decision", expected_fields={"outcome": "chain-abort"},
                        tombstone_candidate=candidate,
                    )

            # Guards, correlation, and validation accept the dispositioned run.
            closed = builders.run_close(
                self.repo, run_id, idempotency_key=key(f"{run_id}-close"),
                judgment="passed", summary="Frozen chain dispositioned from its tombstone",
                risks=[], follow_ups=[],
            )
            self.assertFalse(closed.repeated)
            validation = journal.validate_run(run_dir, gates=True)
        self.assertTrue(validation["ok"], validation)

    def test_tombstone_disposition_refuses_a_nonexistent_run_before_any_lock(self) -> None:
        """A run without a journal gets the named precondition, not a lock failure."""
        run_id = "run-20260905-tombstone-norun"
        chain_id = self.start_bound_fast_chain(run_id)
        self._quarantine_and_tombstone(chain_id)
        exit_code, refused = self.invoke_cli(
            "--run-id", "run-20260905-does-not-exist", "--chain-id", chain_id,
            "commit", "abort-disposition",
        )
        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "state-precondition")
        self.assertEqual(
            refused["message"],
            "commit abort-disposition refused — tombstoned chain is not dispositionable",
        )
        self.assertEqual(refused["expected"], "a readable run journal")
        self.assertFalse(
            (self.repo / ".codex-orchestrator/runs/run-20260905-does-not-exist").exists()
        )

    def test_abort_disposition_run_id_must_name_a_readable_chains_bound_run(self) -> None:
        """--run-id is admitted for the verb but must match a readable chain's binding."""
        run_id = "run-20260905-retro-runid"
        chain_id = self.start_bound_fast_chain(run_id)
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        with mock.patch.object(RUNTIME, "_build_chain_journal_records", return_value=()):
            exit_code, aborted = self.invoke_cli(
                "--chain-id", chain_id, "commit", "abort", "--reason", "legacy abort"
            )
        self.assertEqual(exit_code, 0, aborted)
        journal_before = (run_dir / "journal.jsonl").read_bytes()
        exit_code, mismatch = self.invoke_cli(
            "--run-id", "run-20260905-other", "--chain-id", chain_id, "commit", "abort-disposition"
        )
        self.assertEqual(exit_code, 1, mismatch)
        self.assertEqual(mismatch["reason_code"], "state-precondition")
        self.assertIn("--run-id does not name the chain's bound run", mismatch["message"])
        self.assertEqual(mismatch["expected"], run_id)
        self.assertEqual((run_dir / "journal.jsonl").read_bytes(), journal_before)
        exit_code, disposed = self.invoke_cli(
            "--run-id", run_id, "--chain-id", chain_id, "commit", "abort-disposition"
        )
        self.assertEqual(exit_code, 0, disposed)
        self.assertEqual(self.events(chain_id)[-2]["payload"]["event"], "abort_disposition_recorded")

    def test_tombstone_disposition_guard_and_correlation_controls_are_load_bearing(self) -> None:
        """Disable proofs for the terminal guard and the FR-021 ordering exemption."""
        _batch, builders, journal = CLI._coordination_modules()
        run_id = "run-20260905-tombstone-guard"
        chain_id = self.start_bound_fast_chain(run_id)
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        self._quarantine_and_tombstone(chain_id)
        with self.cli_process_context():
            builders.task_finish(
                self.repo, run_id, idempotency_key=key(f"{run_id}-finish"),
                task="task-01", status="complete",
            )
        exit_code, disposed = self.invoke_cli(
            "--run-id", run_id, "--chain-id", chain_id, "commit", "abort-disposition"
        )
        self.assertEqual(exit_code, 0, disposed)
        records = self._journal_records(run_dir)
        abort = next(r for r in records if r.get("outcome") == "chain-abort")
        projected = [dict(r) for r in records] + [{"type": "run_closed", "judgment": "passed"}]
        for line, record in enumerate(projected, start=1):
            record["_line"] = line
        issues: list[str] = []
        journal._check_binding_correlation(projected, issues)
        self.assertEqual(issues, [])
        with mock.patch.object(
            journal, "BINDING_CORRELATION_CONTROLS",
            journal.BINDING_CORRELATION_CONTROLS - {"tombstone-disposition"},
        ):
            issues = []
            journal._check_binding_correlation([dict(r) for r in projected], issues)
            self.assertEqual(
                issues, ["terminal task 'task-01' precedes a bound chain abort decision"]
            )
        # A basis that is not exactly the tombstone path is an ordinary abort decision.
        altered = [dict(r) for r in projected]
        altered_abort = next(r for r in altered if r.get("outcome") == "chain-abort")
        altered_abort["basis"] = []
        issues = []
        journal._check_binding_correlation(altered, issues)
        self.assertEqual(issues, ["terminal task 'task-01' precedes a bound chain abort decision"])

        chains_root = self.repo / ".forge/chains"
        descriptor = os.open(chains_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.cli_process_context():
                self.assertTrue(
                    builders._terminal_tombstone_disposition(self.repo, descriptor, chain_id, records)
                )
                # Two aborts, a landing, or a candidate mismatch refuse.
                for tampered_records in (
                    records + [dict(abort)],
                    records + [{**abort, "outcome": "chain-landing"}],
                    [
                        {**r, "binding": {**r["binding"], "candidate": {"kind": "staged-diff-sha256", "value": key("mismatch")}}}
                        if r.get("type") == "verification" and r.get("binding") else r
                        for r in records
                    ],
                    [
                        {**r, "binding": {**r["binding"], "binding_id": key("forged")}}
                        if r.get("outcome") == "chain-abort" else r
                        for r in records
                    ],
                ):
                    with self.subTest(tampered=tampered_records[-1].get("outcome")):
                        with self.assertRaises(journal.CoordinationRefusal) as caught:
                            builders._terminal_tombstone_disposition(
                                self.repo, descriptor, chain_id, tampered_records
                            )
                        self.assertEqual(str(caught.exception), builders.TERMINAL_CHAIN_INVALID)
                with mock.patch.object(
                    builders, "TERMINAL_CHAIN_CONTROLS",
                    builders.TERMINAL_CHAIN_CONTROLS - {"tombstone-disposition"},
                ):
                    # Disabled: the guard falls back to Revision 11's unconditional acceptance.
                    self.assertTrue(
                        builders._terminal_tombstone_disposition(
                            self.repo, descriptor, chain_id, records + [dict(abort)]
                        )
                    )
        finally:
            os.close(descriptor)

    def test_abort_disposition_refuses_every_ineligible_chain(self) -> None:
        """Bead forge-plugin-rtj: the verb is only for uncarried run-bound aborts."""
        _batch, builders, journal = CLI._coordination_modules()
        # A revision-13 abort already carried its decision: refuse.
        run_id = "run-20260905-retro-carried"
        chain_id = self.start_bound_fast_chain(run_id)
        exit_code, aborted = self.invoke_cli(
            "--chain-id", chain_id, "commit", "abort", "--reason", "current abort"
        )
        self.assertEqual(exit_code, 0, aborted)
        events_before = self.events_path(chain_id).read_bytes()
        exit_code, refused = self.invoke_cli("--chain-id", chain_id, "commit", "abort-disposition")
        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "state-precondition")
        self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)

    def test_abort_disposition_preconditions_are_independently_load_bearing(self) -> None:
        """Bead forge-plugin-rtj: each precondition refuses alone and only when in force."""
        binding = {"run_id": "run-20260905-x", "task_id": "task-01", "repository": "/r", "policy_digest": "0" * 64}
        good = {
            "chain_id": "c-2026-09-05T000000Z-abcd", "state": "aborted", "journal_outbox": None,
            "candidate": {"sha256": "1" * 64, "computed_at": "2026-09-05T00:00:00Z"},
            "commit_result": {"aborted_at": "2026-09-05T00:01:00Z", "reason": "x"},
            "run_binding": binding,
        }
        uncarried = [{"payload": {"event": "chain_aborted", "details": {"reason": "x"}}}]
        self.assertIsNone(CLI.abort_disposition_refusal(good, uncarried, [], []))
        decision = {"type": "decision", "outcome": "chain-abort",
                    "binding": {"source_record": {"chain_id": good["chain_id"]}}}
        violations = {
            "run-bound": ({**good, "run_binding": None}, uncarried, [], []),
            "aborted": ({**good, "state": "authorized"}, uncarried, [], []),
            "null-outbox": ({**good, "journal_outbox": {"pending": True}}, uncarried, [], []),
            "candidate": ({**good, "candidate": {"sha256": None, "computed_at": None}}, uncarried, [], []),
            "never-landed": ({**good, "commit_result": {"aborted_at": "2026-09-05T00:01:00Z", "commit_sha": "2" * 40}}, uncarried, [], []),
            "uncarried-abort": (good, [{"payload": {"event": "chain_aborted", "details": {"reason": "x", "journal_batch": {}}}}], [], []),
            "journal-readable": (good, uncarried, [], ["line 3: malformed"]),
            "no-journaled-decision": (good, uncarried, [decision], []),
        }
        self.assertEqual(set(violations), set(CLI.ABORT_DISPOSITION_PRECONDITIONS))
        for name, (state, events, records, issues) in violations.items():
            with self.subTest(precondition=name):
                # In force: exactly this precondition refuses.
                self.assertIsNotNone(CLI.abort_disposition_refusal(state, events, records, issues))
                # Removed from the control set: the same input is accepted.
                remaining = tuple(item for item in CLI.ABORT_DISPOSITION_PRECONDITIONS if item != name)
                self.assertIsNone(
                    CLI.abort_disposition_refusal(state, events, records, issues, controls=remaining)
                )

    def test_abort_disposition_reaches_a_dead_in_place_chain(self) -> None:
        """Bead forge-plugin-rtj: the verb must reach chains untouched for over 24 hours."""
        _batch, builders, journal = CLI._coordination_modules()
        run_id = "run-20260905-retro-stale"
        chain_id = self.start_bound_fast_chain(run_id)
        with mock.patch.object(RUNTIME, "_build_chain_journal_records", return_value=()):
            exit_code, aborted = self.invoke_cli(
                "--chain-id", chain_id, "commit", "abort", "--reason", "legacy abort"
            )
        self.assertEqual(exit_code, 0, aborted)
        inactive_after = CLI.parse_time(str(self.state(chain_id)["inactive_after"]))
        later = inactive_after + datetime.timedelta(hours=1)
        with mock.patch.object(RUNTIME, "utc_now", return_value=later):
            # Disable proof: without the exemption the deadline refuses the verb.
            with patch_engine(
                "TERMINAL_TOUCH_VERBS", frozenset({"status", "commit abort"})
            ):
                exit_code, refused = self.invoke_cli("--chain-id", chain_id, "commit", "abort-disposition")
            self.assertEqual(exit_code, 1, refused)
            self.assertEqual(refused["reason_code"], "inactive-chain")
            exit_code, disposed = self.invoke_cli("--chain-id", chain_id, "commit", "abort-disposition")
        self.assertEqual(exit_code, 0, disposed)
        events = self.events(chain_id)
        self.assertEqual(
            [event["payload"]["event"] for event in events[-2:]],
            ["abort_disposition_recorded", "journal_receipted"],
        )

    def test_abort_disposition_is_exempt_from_the_iteration_cap(self) -> None:
        """Bead forge-plugin-rtj: the FR-053 cap never strands a retrospective disposition."""
        run_id = "run-20260905-retro-cap"
        chain_id = self.start_bound_fast_chain(run_id)
        with mock.patch.object(RUNTIME, "_build_chain_journal_records", return_value=()):
            exit_code, aborted = self.invoke_cli(
                "--chain-id", chain_id, "commit", "abort", "--reason", "legacy abort"
            )
        self.assertEqual(exit_code, 0, aborted)
        # Drive the shared preflight directly on the real aborted state with the
        # review iteration forced to the cap; only the exemption admits the verb.
        state = self.state(chain_id)
        state["review"]["iteration"] = 8
        state["run_binding"] = None  # keep this a pure preflight-exemption probe
        repository = CLI.Repository(self.repo)
        context = CLI.CommandContext(
            repo=repository,
            store=CLI.ChainStore(repository.common_root()),
            options=CLI.CLIOptions(repo=str(self.repo), chain_id=chain_id, revision9_face=True),
        )
        engine = CLI.Engine(context)
        with self.cli_process_context():
            engine._preflight(
                state, "commit abort-disposition", mutating=False,
                allow_head_moved=True, check_candidate=False,
            )
            with patch_engine(
                "TERMINAL_TOUCH_VERBS", frozenset({"status", "commit abort"})
            ), self.assertRaises(CLI.Refusal) as caught:
                engine._preflight(
                    state, "commit abort-disposition", mutating=False,
                    allow_head_moved=True, check_candidate=False,
                )
        self.assertEqual(caught.exception.reason_code.value, "iteration-cap")

    def test_abort_disposition_requires_a_chain_id_and_a_readable_journal(self) -> None:
        _batch, builders, journal = CLI._coordination_modules()
        run_id = "run-20260905-retro-args"
        chain_id = self.start_bound_fast_chain(run_id)
        with mock.patch.object(RUNTIME, "_build_chain_journal_records", return_value=()):
            exit_code, aborted = self.invoke_cli(
                "--chain-id", chain_id, "commit", "abort", "--reason", "legacy abort"
            )
        self.assertEqual(exit_code, 0, aborted)
        events_before = self.events_path(chain_id).read_bytes()
        exit_code, refused = self.invoke_cli("commit", "abort-disposition")
        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "state-precondition")
        self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)
        with mock.patch.object(journal, "read_journal", return_value=([], ["line 1: malformed"])):
            exit_code, refused = self.invoke_cli("--chain-id", chain_id, "commit", "abort-disposition")
        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "state-precondition")
        self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)

    def test_abort_disposition_refuses_a_live_bound_chain(self) -> None:
        run_id = "run-20260905-retro-live"
        chain_id = self.start_bound_fast_chain(run_id)
        events_before = self.events_path(chain_id).read_bytes()
        exit_code, refused = self.invoke_cli("--chain-id", chain_id, "commit", "abort-disposition")
        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "state-precondition")
        self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)
        self.assertEqual(self.state(chain_id)["state"], "authorized")

    def test_abort_disposition_refuses_an_unbound_aborted_chain(self) -> None:
        self.change("docs/guide.md", "# unbound\n")
        exit_code, started = self.invoke_cli("commit", "start", "--paths", "docs/guide.md")
        self.assertEqual(exit_code, 0, started)
        unbound = str(started["chain_id"])
        exit_code, aborted = self.invoke_cli("--chain-id", unbound, "commit", "abort", "--reason", "unbound")
        self.assertEqual(exit_code, 0, aborted)
        events_before = self.events_path(unbound).read_bytes()
        exit_code, refused = self.invoke_cli("--chain-id", unbound, "commit", "abort-disposition")
        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "state-precondition")
        self.assertEqual(self.events_path(unbound).read_bytes(), events_before)

    def test_task_finish_inspects_only_the_finishing_tasks_chains(self) -> None:
        """Bead forge-plugin-437: another task's cited chain is not a refusal."""
        run_id = "run-20260904-other-task-chain"
        first_chain = self.start_bound_chain(run_id)
        exit_code, aborted = self.invoke_cli(
            "--chain-id", first_chain, "commit", "abort", "--reason", "superseded"
        )
        self.assertEqual(exit_code, 0, aborted)
        _batch, builders, journal = CLI._coordination_modules()
        with self.cli_process_context():
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-task-02"),
                task="task-02",
                goal="A second task with its own live chain",
                acceptance=["its chain is not the first task's business"],
                files=["src/other.py"],
            )
        # The abort leaves task-01's candidate staged; a new chain needs a clean index.
        self.git("restore", "--staged", "src/app.py")
        self.change("src/other.py", "OTHER = 1\n")
        exit_code, started = self.invoke_cli(
            "--run-id", run_id, "commit", "start", "--paths", "src/other.py",
            "--task", "task-02",
        )
        self.assertEqual(exit_code, 0, started)
        second_chain = str(started["chain_id"])
        exit_code, verified = self.invoke_cli("--chain-id", second_chain, "verify")
        self.assertEqual(exit_code, 0, verified)
        # task-01's finish ignores task-02's live, journal-cited chain ...
        with self.cli_process_context():
            finished = builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-finish-01"),
                task="task-01",
                status="complete",
            )
        self.assertEqual(finished.records[0]["status"], "complete")
        # ... while task-02's own nonterminal chain still refuses its finish,
        # and run-close still sees every chain in the run.
        with self.cli_process_context(), self.assertRaisesRegex(
            journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
        ):
            builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-finish-02"),
                task="task-02",
                status="complete",
            )
        with self.cli_process_context(), self.assertRaisesRegex(
            journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
        ):
            builders.run_close(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-close-early"),
                judgment="blocked",
                summary="task-02's chain is still live",
                risks=[],
                follow_ups=[],
            )

    def test_operator_tombstone_admits_absent_chain_and_refuses_healthy_chain(self) -> None:
        absent_id = "c-2026-08-31T120000Z-abcd"
        exit_code, unknown = self.invoke_cli(
            "--chain-id",
            absent_id,
            "commit",
            "abort",
            "--reason",
            "must not guess an unknown chain family",
        )
        self.assertEqual(exit_code, 1, unknown)
        self.assertEqual(unknown["reason_code"], "state-precondition")
        self.assertIn(
            "commit-family identity is not authenticated",
            str(unknown["message"]),
        )
        self.assertFalse(
            (
                self.repo
                / ".forge/chains/tombstones"
                / f"{absent_id}.json"
            ).exists()
        )

        exit_code, absent = self.invoke_cli(
            "--chain-id",
            absent_id,
            "chain",
            "tombstone",
            "--reason",
            "artifacts were explicitly quarantined",
        )
        self.assertEqual(exit_code, 0, absent)
        self.assertEqual(absent["state"], "aborted")

        self.change("src/app.py", "VALUE = 2\n")
        exit_code, started = self.invoke_cli(
            "commit", "start", "--paths", "src/app.py"
        )
        self.assertEqual(exit_code, 0, started)
        healthy_id = str(started["chain_id"])
        exit_code, refused = self.invoke_cli(
            "--chain-id",
            healthy_id,
            "chain",
            "tombstone",
            "--reason",
            "must not seal a healthy chain",
        )
        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "state-precondition")
        self.assertIn("readable chain is not frozen", str(refused["message"]))

    def test_tombstone_publication_recovers_only_authenticated_temp_alias(self) -> None:
        chain_id = "c-2026-08-31T120001Z-abcd"
        exit_code, created = self.invoke_cli(
            "--chain-id",
            chain_id,
            "chain",
            "tombstone",
            "--reason",
            "simulate an interrupted final-link publication",
        )
        self.assertEqual(exit_code, 0, created)
        tombstones = self.repo / ".forge/chains/tombstones"
        final = tombstones / f"{chain_id}.json"
        temporary_alias = tombstones / (
            f".{chain_id}.{os.getpid()}.0123456789abcdef.tmp"
        )
        os.link(final, temporary_alias)
        self.assertEqual(final.stat().st_nlink, 2)

        exit_code, status = self.invoke_cli("--chain-id", chain_id, "status")
        self.assertEqual(exit_code, 0, status)
        self.assertTrue(temporary_alias.exists())

        exit_code, recovered = self.invoke_cli(
            "--chain-id",
            chain_id,
            "chain",
            "tombstone",
            "--reason",
            "recover the interrupted publication",
        )
        self.assertEqual(exit_code, 0, recovered)
        self.assertFalse(temporary_alias.exists())
        self.assertEqual(final.stat().st_nlink, 1)

        foreign_alias = tombstones / "foreign-hardlink"
        os.link(final, foreign_alias)
        exit_code, refused = self.invoke_cli("--chain-id", chain_id, "status")
        self.assertEqual(exit_code, 2, refused)
        self.assertEqual(refused["reason_code"], "frozen-chain")
        self.assertIn("unsafe hardlink topology", str(refused["message"]))

    def test_tombstone_publication_retries_prelink_and_postunlink_failures(self) -> None:
        repository = CLI.Repository(self.repo)

        prelink_id = "c-2026-08-31T120002Z-abcd"
        prelink_store = CLI.ChainStore(repository.common_root())
        with self.cli_process_context(), mock.patch.object(
            CLI.os, "link", side_effect=OSError("failure before final link")
        ), self.assertRaisesRegex(
            CLI.FrozenError, "chain tombstone publication failed"
        ):
            prelink_store.create_tombstone(
                prelink_id,
                "pre-link publication failure",
                frozen_proven=True,
            )
        tombstones = self.repo / ".forge/chains/tombstones"
        self.assertFalse((tombstones / f"{prelink_id}.json").exists())
        self.assertEqual(list(tombstones.glob(f".{prelink_id}.*.tmp")), [])
        with self.cli_process_context():
            prelink_record = prelink_store.create_tombstone(
                prelink_id,
                "pre-link publication retry",
                frozen_proven=True,
            )
        self.assertEqual(prelink_record["chain_id"], prelink_id)

        postunlink_id = "c-2026-08-31T120003Z-abcd"
        stages: list[str] = []
        postunlink_store = CLI.ChainStore(
            repository.common_root(), boundary=stages.append
        )
        real_fsync = CLI.os.fsync

        def fail_directory_fsync(descriptor: int) -> None:
            if (
                stages
                and stages[-1] == "tombstone-temp-unlinked"
                and stat.S_ISDIR(os.fstat(descriptor).st_mode)
            ):
                raise OSError("failure before tombstone directory fsync")
            real_fsync(descriptor)

        with self.cli_process_context(), mock.patch.object(
            CLI.os, "fsync", side_effect=fail_directory_fsync
        ), self.assertRaisesRegex(
            CLI.FrozenError, "chain tombstone publication failed"
        ):
            postunlink_store.create_tombstone(
                postunlink_id,
                "post-unlink publication failure",
                frozen_proven=True,
            )
        postunlink_final = tombstones / f"{postunlink_id}.json"
        self.assertTrue(postunlink_final.exists())
        self.assertEqual(postunlink_final.stat().st_nlink, 1)
        self.assertIn("tombstone-temp-unlinked", stages)
        self.assertNotIn("tombstone-directory-fsynced", stages)

        with self.cli_process_context():
            postunlink_record = postunlink_store.create_tombstone(
                postunlink_id,
                "post-unlink publication retry",
                frozen_proven=True,
            )
        self.assertEqual(postunlink_record["chain_id"], postunlink_id)
