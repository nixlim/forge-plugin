from __future__ import annotations

import copy
import hashlib
import json
from unittest import mock

from tests._revision9_cli_constants import CLI, CLI_FIXTURE_SUPPORT, key
from tests._revision9_cli_support import Revision9CliSupport


class Revision9CliSurfacesReplayTests(Revision9CliSupport, CLI_FIXTURE_SUPPORT.ForgeCLIFixture):

    def test_fresh_key_cannot_replay_typed_verification_or_decision_binding(
        self,
    ) -> None:
        _batch, builders, journal = CLI._coordination_modules()

        for record_type in ("verification", "decision"):
            with self.subTest(record_type=record_type):
                run_id = f"run-20260828-cli-binding-replay-{record_type}"
                chain_id = (
                    "c-2026-08-28T120000Z-a001"
                    if record_type == "verification"
                    else "c-2026-08-28T120000Z-a002"
                )
                self.open_run_and_task(
                    run_id,
                    scope=(
                        ("src/**",)
                        if record_type == "verification"
                        else ("docs/**",)
                    ),
                    files=(
                        ("src/app.py",)
                        if record_type == "verification"
                        else ("docs/guide.md",)
                    ),
                )
                preimage = {
                    "schema": journal.BINDING_SCHEMA,
                    "source_record": {
                        "chain_id": chain_id,
                        "event_digest": key(f"{record_type}-source-event"),
                    },
                    "candidate": {
                        "kind": "staged-diff-sha256",
                        "value": key(f"{record_type}-candidate"),
                    },
                    "review": None,
                }
                binding = {
                    **preimage,
                    "binding_id": journal._sha256(
                        journal._canonical_json_bytes(preimage)
                    ),
                }
                if record_type == "verification":
                    operation = builders.verification_add
                    arguments = {
                        "task": "task-01",
                        "criterion": "focused typed binding replay control",
                        "method": "unittest",
                        "check": "focused duplicate replay",
                        "result": "passed",
                        "observation": "the first typed binding was accepted",
                        "evidence": [],
                        "binding_chain": chain_id,
                        "binding_id": str(binding["binding_id"]),
                    }
                else:
                    operation = builders.decision_add
                    arguments = {
                        "task": "task-01",
                        "resolution": "Retain the exact landed candidate",
                        "finding": None,
                        "outcome": "chain-landing",
                        "risk": None,
                        "basis": [],
                        "binding_chain": chain_id,
                        "binding_id": str(binding["binding_id"]),
                    }

                with self.cli_process_context(), mock.patch.object(
                    builders, "resolve_binding", return_value=binding
                ):
                    first = operation(
                        self.repo,
                        run_id,
                        idempotency_key=key(f"{record_type}-first-key"),
                        **arguments,
                    )
                self.assertFalse(first.repeated)
                self.assertEqual(first.records[0]["binding"], binding)

                run_dir = (
                    self.repo / ".codex-orchestrator" / "runs" / run_id
                )
                journal_path = run_dir / "journal.jsonl"
                receipts_path = run_dir / journal.BATCH_RECEIPTS_NAME
                intent_path = run_dir / journal.BATCH_INTENT_NAME
                journal_before = journal_path.read_bytes()
                receipts_before = receipts_path.read_bytes()
                self.assertFalse(intent_path.exists())

                with self.cli_process_context(), mock.patch.object(
                    builders,
                    "resolve_binding",
                    side_effect=AssertionError(
                        "duplicate replay reached binding resolution"
                    ),
                ) as resolver, self.assertRaises(
                    journal.CoordinationRefusal
                ) as raised:
                    operation(
                        self.repo,
                        run_id,
                        idempotency_key=key(f"{record_type}-fresh-key"),
                        **arguments,
                    )
                resolver.assert_not_called()
                self.assertEqual(
                    str(raised.exception), journal.DUPLICATE_CHAIN_BINDING
                )
                self.assertEqual(journal_path.read_bytes(), journal_before)
                self.assertEqual(receipts_path.read_bytes(), receipts_before)
                self.assertFalse(intent_path.exists())

    def test_historical_receipted_binding_replays_after_restage(self) -> None:
        run_id = "run-20260828-cli-stale-carried-binding"
        chain_id = self.start_bound_chain(run_id)
        _batch, _builders, journal = CLI._coordination_modules()
        exit_code, recorded = self.invoke_cli(
            "--chain-id", chain_id, "gate", "run", "gate-1"
        )
        self.assertEqual(exit_code, 0, recorded)
        carried_events = [
            event
            for event in self.events(chain_id)
            if "journal_batch" in event["payload"]["details"]
        ]
        self.assertEqual(len(carried_events), 1)
        carried = carried_events[0]["payload"]["details"]["journal_batch"]
        self.assertEqual(carried["records"][0]["type"], "verification")
        original_candidate = self.state(chain_id)["candidate"]["sha256"]

        self.change("src/app.py", "VALUE = 3\n")
        exit_code, restaged = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "restage",
            "--paths",
            "src/app.py",
        )
        self.assertEqual(exit_code, 0, restaged)
        self.assertNotEqual(
            self.state(chain_id)["candidate"]["sha256"], original_candidate
        )

        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        journal_path = run_dir / "journal.jsonl"
        receipts_path = run_dir / journal.BATCH_RECEIPTS_NAME
        event_path = self.events_path(chain_id)
        journal_before = journal_path.read_bytes()
        receipts_before = receipts_path.read_bytes()
        events_before = event_path.read_bytes()
        state_path = self.state_path(chain_id)
        state_path.unlink()
        repository = CLI.Repository(self.repo)
        context = CLI.CommandContext(
            repo=repository,
            store=CLI.ChainStore(repository.common_root()),
            options=CLI.CLIOptions(
                repo=str(self.repo),
                chain_id=chain_id,
                revision9_face=True,
            ),
        )

        with self.cli_process_context():
            outcome = CLI.Engine(context).status()

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.schema, "forge-cli/2")
        self.assertTrue(state_path.exists())
        self.assertEqual(
            json.loads(state_path.read_bytes()), self.events(chain_id)[-1]["payload"]["state"]
        )
        self.assertEqual(event_path.read_bytes(), events_before)
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertEqual(receipts_path.read_bytes(), receipts_before)

    def test_bound_replay_refuses_noncanonical_event_without_state_repair(self) -> None:
        run_id = "run-20260828-cli-noncanonical-event"
        chain_id = self.start_bound_chain(run_id)
        _batch, _builders, journal = CLI._coordination_modules()
        event_path = self.events_path(chain_id)
        lines = event_path.read_bytes().splitlines(keepends=True)
        canonical_line = lines[0]
        self.assertIsNotNone(
            json.loads(canonical_line)["payload"]["state"]["run_binding"]
        )
        noncanonical_line = canonical_line[:-1] + b" \n"
        self.assertEqual(json.loads(noncanonical_line), json.loads(canonical_line))
        self.assertNotEqual(noncanonical_line, canonical_line)
        lines[0] = noncanonical_line
        tampered_events = b"".join(lines)
        event_path.write_bytes(tampered_events)

        state_path = self.state_path(chain_id)
        state_path.unlink()
        run_dir = (
            self.repo
            / ".codex-orchestrator"
            / "runs"
            / run_id
        )
        journal_path = run_dir / "journal.jsonl"
        receipts_path = run_dir / journal.BATCH_RECEIPTS_NAME
        journal_before = journal_path.read_bytes()
        receipts_before = receipts_path.read_bytes()
        repository = CLI.Repository(self.repo)
        context = CLI.CommandContext(
            repo=repository,
            store=CLI.ChainStore(repository.common_root()),
            options=CLI.CLIOptions(
                repo=str(self.repo),
                chain_id=chain_id,
                revision9_face=True,
            ),
        )

        with self.cli_process_context(), self.assertRaisesRegex(
            CLI.FrozenError, "chain event 1 is not canonical"
        ):
            CLI.Engine(context).status()

        self.assertFalse(state_path.exists())
        self.assertEqual(event_path.read_bytes(), tampered_events)
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertEqual(receipts_path.read_bytes(), receipts_before)

    def test_failed_ingest_proof_captures_but_never_references_or_mutates_journal(self) -> None:
        run_id = "run-20260828-cli-ingest-invalid"
        self.open_run_and_task(run_id)
        external = self.repo / "external"
        external.mkdir()
        sources = {
            "state.json": b'{"chain_id":"not-a-chain"}\n',
            "events.jsonl": b'{"not":"an-event"}\n',
            "outcome-map.json": b'{"schema":"not-an-outcome-map"}\n',
        }
        for name, data in sources.items():
            (external / name).write_bytes(data)

        _batch, _builders, journal = CLI._coordination_modules()
        run_dir = (
            self.repo
            / ".codex-orchestrator"
            / "runs"
            / run_id
        )
        journal_path = run_dir / "journal.jsonl"
        receipts_path = run_dir / journal.BATCH_RECEIPTS_NAME
        intent_path = run_dir / journal.BATCH_INTENT_NAME
        journal_before = journal_path.read_bytes()
        receipts_before = receipts_path.read_bytes()
        self.assertFalse(intent_path.exists())

        exit_code, envelope = self.invoke_cli(
            "--run-id",
            run_id,
            "journal",
            "ingest-chain",
            "--task",
            "task-01",
            "--state-file",
            "external/state.json",
            "--events-file",
            "external/events.jsonl",
            "--outcome-map",
            "external/outcome-map.json",
            "--closing-head",
            self.git("rev-parse", "HEAD"),
            "--task-status",
            "complete",
            "--idempotency-key",
            key("invalid-ingest-proof"),
        )
        self.assertEqual(exit_code, 1, envelope)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["schema"], "forge-cli/2")
        self.assertEqual(envelope["reason_code"], "ingest-proof-invalid")
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertEqual(receipts_path.read_bytes(), receipts_before)
        self.assertFalse(intent_path.exists())

        records, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        task_records = [
            record
            for record in records
            if record.get("type") == "task" and record.get("id") == "task-01"
        ]
        self.assertEqual(task_records[-1]["status"], "active")
        cited_text = journal_path.read_text(encoding="utf-8")
        for name, data in sources.items():
            digest = hashlib.sha256(data).hexdigest()
            captured = run_dir / "captured" / "sha256" / digest / name
            self.assertEqual(captured.read_bytes(), data)
            self.assertNotIn(captured.relative_to(self.repo).as_posix(), cited_text)

    def test_event_carrier_survives_drain_crash_and_replays_once(self) -> None:
        run_id = "run-20260828-cli-outbox-replay"
        chain_id = self.start_bound_chain(run_id)
        batch, _builders, journal = CLI._coordination_modules()
        repository = CLI.Repository(self.repo)
        options = CLI.CLIOptions(
            repo=str(self.repo), chain_id=chain_id, revision9_face=True
        )
        context = CLI.CommandContext(
            repo=repository,
            store=CLI.ChainStore(repository.common_root()),
            options=options,
        )

        with self.cli_process_context(), mock.patch.object(
            batch,
            "drain_chain_batch",
            side_effect=RuntimeError("injected crash after carrier persistence"),
        ), self.assertRaisesRegex(RuntimeError, "injected crash"):
            CLI.Engine(context).verify()

        pending_state = self.state(chain_id)
        pending = pending_state["journal_outbox"]
        self.assertIsInstance(pending, dict)
        carrier_event = self.events(chain_id)[-1]
        self.assertEqual(carrier_event["payload"]["event"], "step_recorded")
        details = carrier_event["payload"]["details"]
        self.assertEqual(
            set(details) - {"step_id", "result", "run"},
            {"source_event_digest", "journal_batch"},
        )
        carried = details["journal_batch"]
        self.assertEqual(
            pending,
            {
                "idempotency_key": details["source_event_digest"],
                "batch_digest": carried["batch_digest"],
                "record_count": carried["record_count"],
                "source_event_digest": details["source_event_digest"],
            },
        )
        self.assertEqual(carried["idempotency_key"], details["source_event_digest"])
        self.assertEqual(carried["record_count"], len(carried["records"]))

        source_projection = copy.deepcopy(carrier_event)
        del source_projection["digest"]
        projected_details = source_projection["payload"]["details"]
        del projected_details["source_event_digest"]
        del projected_details["journal_batch"]
        source_projection["payload"]["state"]["journal_outbox"] = None
        self.assertEqual(
            hashlib.sha256(CLI.canonical_bytes(source_projection)).hexdigest(),
            details["source_event_digest"],
        )

        with self.cli_process_context():
            recovered = CLI.Engine(context).status()
        self.assertTrue(recovered.ok)
        self.assertEqual(recovered.schema, "forge-cli/2")
        final_state = self.state(chain_id)
        self.assertIsNone(final_state["journal_outbox"])
        receipt_event = self.events(chain_id)[-1]
        self.assertEqual(receipt_event["payload"]["event"], "journal_receipted")
        self.assertEqual(
            set(receipt_event["payload"]["details"]),
            {"idempotency_key", "batch_digest", "receipt_digest"},
        )
        self.assertNotIn(
            "journal_batch", receipt_event["payload"]["details"]
        )

        records, issues = journal.read_journal(
            self.repo
            / ".codex-orchestrator"
            / "runs"
            / run_id
            / "journal.jsonl"
        )
        self.assertEqual(issues, [])
        normalized_records = [
            {name: value for name, value in record.items() if name != "_line"}
            for record in records
        ]
        self.assertEqual(
            normalized_records[-len(carried["records"]):], carried["records"]
        )
        for carried_record in carried["records"]:
            self.assertEqual(
                sum(
                    record.get("id") == carried_record.get("id")
                    for record in records
                ),
                1,
            )

        receipt_lines = (
            self.repo
            / ".codex-orchestrator"
            / "runs"
            / run_id
            / journal.BATCH_RECEIPTS_NAME
        ).read_bytes().splitlines(keepends=True)
        matching_receipts = [
            (json.loads(line), line)
            for line in receipt_lines
            if json.loads(line).get("idempotency_key")
            == pending["idempotency_key"]
        ]
        self.assertEqual(len(matching_receipts), 1)
        receipt, receipt_line = matching_receipts[0]
        self.assertEqual(set(receipt), batch._receipt_keys())
        self.assertEqual(receipt["batch_sha256"], pending["batch_digest"])
        self.assertEqual(receipt["record_count"], pending["record_count"])
        self.assertEqual(
            receipt_event["payload"]["details"],
            {
                "idempotency_key": pending["idempotency_key"],
                "batch_digest": pending["batch_digest"],
                "receipt_digest": hashlib.sha256(receipt_line).hexdigest(),
            },
        )

    def test_commit_identity_carrier_pre_drain_crash_replays_once(self) -> None:
        self.assert_commit_identity_drain_crash_replays_once("before-drain")

    def test_commit_identity_journal_append_crash_replays_once(self) -> None:
        self.assert_commit_identity_drain_crash_replays_once("after-journal")

    def test_commit_identity_receipt_append_crash_replays_once(self) -> None:
        self.assert_commit_identity_drain_crash_replays_once("after-receipt")

    def test_chain_receipt_replay_reader_is_read_only_and_fail_closed(
        self,
    ) -> None:
        run_id = "run-20260910-chain-receipt-replay-reader"
        chain_id = self.start_bound_fast_chain(run_id)
        batch, _builders, journal = CLI._coordination_modules()
        repository = CLI.Repository(self.repo)
        context = CLI.CommandContext(
            repo=repository,
            store=CLI.ChainStore(repository.common_root()),
            options=CLI.CLIOptions(
                repo=str(self.repo),
                chain_id=chain_id,
                revision9_face=True,
                original_argv=(
                    "commit",
                    "finalize",
                    "--message",
                    "Exercise the chain replay receipt reader",
                ),
            ),
        )
        original_append = batch._append_missing_prefix
        crashed = False

        def append_journal_then_crash(*args: object, **kwargs: object):
            nonlocal crashed
            result = original_append(*args, **kwargs)
            name = args[1] if len(args) > 1 else kwargs.get("name")
            if not crashed and name == "journal.jsonl":
                crashed = True
                raise RuntimeError("injected chain replay reader crash")
            return result

        with self.cli_process_context(), mock.patch.object(
            batch,
            "_append_missing_prefix",
            side_effect=append_journal_then_crash,
        ), self.assertRaisesRegex(RuntimeError, "chain replay reader crash"):
            CLI.Engine(context).finalize(
                "Exercise the chain replay receipt reader"
            )

        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        journal_path = run_dir / "journal.jsonl"
        ledger_path = run_dir / journal.BATCH_RECEIPTS_NAME
        intent_path = run_dir / journal.BATCH_INTENT_NAME
        paths = (journal_path, ledger_path, intent_path)
        pristine_journal, pristine_ledger, pristine_intent = (
            path.read_bytes() for path in paths
        )
        intent = json.loads(pristine_intent)
        intended_batch = batch._decode_base64url(intent["batch_bytes"])
        intended_receipt = batch._decode_base64url(intent["receipt_bytes"])
        historical_receipts = [
            json.loads(line) for line in pristine_ledger.splitlines()
        ]
        self.assertTrue(historical_receipts)
        self.assertEqual(
            pristine_journal[int(intent["base_size"]) :], intended_batch
        )
        self.assertEqual(len(pristine_ledger), intent["receipt_base_size"])
        self.assertFalse(
            any(
                receipt["idempotency_key"] == intent["idempotency_key"]
                for receipt in historical_receipts
            )
        )

        before = tuple(path.read_bytes() for path in paths)
        with self.cli_process_context(), batch.batch_lock(
            run_dir, create=False
        ) as locked:
            loaded, raw, _observation = batch._load_receipts_for_chain_replay(
                locked
            )
        self.assertEqual(loaded, historical_receipts)
        self.assertEqual(raw, pristine_ledger)
        self.assertEqual(tuple(path.read_bytes() for path in paths), before)

        tampered_intent = dict(intent)
        tampered_intent["base_sha256"] = key("tampered intent base")
        duplicate_receipts = copy.deepcopy(historical_receipts)
        duplicate_receipts[0]["idempotency_key"] = intent["idempotency_key"]
        duplicate_ledger = b"".join(
            batch._canonical_sidecar(receipt)
            for receipt in duplicate_receipts
        )
        duplicate_intent = dict(intent)
        duplicate_intent["receipt_base_sha256"] = hashlib.sha256(
            duplicate_ledger
        ).hexdigest()
        corruptions = (
            (
                "partial journal",
                pristine_journal[:-1],
                pristine_ledger,
                pristine_intent,
            ),
            (
                "extra journal",
                pristine_journal + b"{}\n",
                pristine_ledger,
                pristine_intent,
            ),
            (
                "partial receipt ledger",
                pristine_journal,
                pristine_ledger
                + intended_receipt[: len(intended_receipt) // 2],
                pristine_intent,
            ),
            (
                "tampered intent",
                pristine_journal,
                pristine_ledger,
                batch._canonical_sidecar(tampered_intent),
            ),
            (
                "duplicate pending key",
                pristine_journal,
                duplicate_ledger,
                batch._canonical_sidecar(duplicate_intent),
            ),
        )
        for name, journal_raw, ledger_raw, intent_raw in corruptions:
            with self.subTest(name=name):
                for path, raw in zip(
                    paths, (journal_raw, ledger_raw, intent_raw), strict=True
                ):
                    path.write_bytes(raw)
                corrupted = tuple(path.read_bytes() for path in paths)
                with self.cli_process_context(), self.assertRaises(
                    journal.CoordinationRefusal
                ) as raised, batch.batch_lock(run_dir, create=False) as locked:
                    batch._load_receipts_for_chain_replay(locked)
                self.assertEqual(str(raised.exception), journal.BATCH_DIVERGED)
                self.assertEqual(
                    tuple(path.read_bytes() for path in paths), corrupted
                )

        for path, raw in zip(
            paths,
            (pristine_journal, pristine_ledger, pristine_intent),
            strict=True,
        ):
            path.write_bytes(raw)

    def test_receipted_commit_produced_crash_recovers_one_landing(self) -> None:
        run_id = "run-20260828-cli-landing-replay"
        chain_id = self.start_bound_fast_chain(run_id)
        batch, _builders, journal = CLI._coordination_modules()
        repository = CLI.Repository(self.repo)
        options = CLI.CLIOptions(
            repo=str(self.repo),
            chain_id=chain_id,
            revision9_face=True,
            original_argv=(
                "commit",
                "finalize",
                "--message",
                "Revision-9 receipted landing",
            ),
        )
        context = CLI.CommandContext(
            repo=repository,
            store=CLI.ChainStore(repository.common_root()),
            options=options,
        )
        original_persist = context.store.persist

        def persist_then_crash(
            state: dict[str, object],
            event: str,
            details: dict[str, object],
            **kwargs: object,
        ) -> None:
            original_persist(state, event, details, **kwargs)
            if event == "commit_produced":
                raise RuntimeError(
                    "injected crash after commit_produced was receipted"
                )

        with self.cli_process_context(), mock.patch.object(
            context.store, "persist", side_effect=persist_then_crash
        ), self.assertRaisesRegex(RuntimeError, "commit_produced was receipted"):
            CLI.Engine(context).finalize("Revision-9 receipted landing")

        crashed = self.state(chain_id)
        self.assertEqual(crashed["state"], "committing")
        self.assertIsNone(crashed["journal_outbox"])
        commit_sha = crashed["commit_result"]["commit_sha"]
        self.assertEqual(self.git("rev-parse", "HEAD"), commit_sha)
        crash_events = self.events(chain_id)
        self.assertEqual(
            [event["payload"]["event"] for event in crash_events[-2:]],
            ["commit_produced", "journal_receipted"],
        )
        landing_event = crash_events[-2]
        landing_details = landing_event["payload"]["details"]
        source_digest = landing_details["source_event_digest"]
        carried = landing_details["journal_batch"]
        self.assertEqual(carried["record_count"], 1)
        self.assertEqual(carried["records"][0]["outcome"], "chain-landing")
        self.assertEqual(
            crash_events[-1]["payload"]["details"]["idempotency_key"],
            source_digest,
        )

        journal_path = (
            self.repo
            / ".codex-orchestrator"
            / "runs"
            / run_id
            / "journal.jsonl"
        )
        before_recovery, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        self.assertEqual(
            sum(
                record.get("outcome") == "chain-landing"
                for record in before_recovery
            ),
            1,
        )
        receipt_lines = (
            journal_path.parent / journal.BATCH_RECEIPTS_NAME
        ).read_bytes().splitlines(keepends=True)
        landing_receipts = [
            json.loads(line)
            for line in receipt_lines
            if json.loads(line).get("idempotency_key") == source_digest
        ]
        self.assertEqual(len(landing_receipts), 1)
        self.assertEqual(set(landing_receipts[0]), batch._receipt_keys())
        self.assertEqual(
            landing_receipts[0]["batch_sha256"], carried["batch_digest"]
        )

        exit_code, recovered = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "finalize",
            "--message",
            "Revision-9 receipted landing",
        )
        self.assertEqual(exit_code, 0, recovered)
        self.assertEqual(recovered["schema"], "forge-cli/2")
        self.assertEqual(recovered["state"], "closed")
        final_state = self.state(chain_id)
        self.assertEqual(final_state["state"], "closed")
        self.assertIsNone(final_state["journal_outbox"])
        final_events = self.events(chain_id)
        event_names = [event["payload"]["event"] for event in final_events]
        self.assertEqual(event_names.count("commit_produced"), 1)
        self.assertEqual(event_names.count("commit_close_recovered"), 0)
        self.assertEqual(event_names[-1], "chain_closed")
        after_recovery, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        self.assertEqual(
            sum(
                record.get("outcome") == "chain-landing"
                for record in after_recovery
            ),
            1,
        )
