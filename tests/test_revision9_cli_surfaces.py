"""Focused Revision-9 tests for the public Forge CLI integration surfaces."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import warnings
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


from tests._cli_loader import load_script, package_module, patch_chain_core, patch_engine  # cli split phase 0: one shared loader
from tests._revision9_cli_constants import CANDIDATE, CLI, CLI_FIXTURE_SUPPORT, CORE, ENVELOPE_KEYS, RUNTIME, key
from tests._revision9_cli_support import Revision9CliSupport


class Revision9CLIParsingTests(unittest.TestCase):
    def invoke_before_repository(
        self, argv: list[str]
    ) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(CLI.Repository, "discover") as discover, \
            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            discover.side_effect = AssertionError("repository discovery was reached")
            exit_code = CLI.main(["--json", *argv])
        discover.assert_not_called()
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(set(envelope), ENVELOPE_KEYS)
        return exit_code, envelope

    def assert_revision9_refusal(
        self,
        argv: list[str],
        *,
        reason: str,
        message: str | None = None,
    ) -> dict[str, object]:
        exit_code, envelope = self.invoke_before_repository(argv)
        self.assertEqual(exit_code, 1, envelope)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["schema"], "forge-cli/2")
        self.assertEqual(envelope["reason_code"], reason)
        if message is not None:
            self.assertEqual(envelope["message"], message)
        self.assertIsInstance(envelope["remediation"], str)
        self.assertTrue(str(envelope["remediation"]).strip())
        self.assertIsInstance(envelope["next_required_step"], str)
        self.assertTrue(str(envelope["next_required_step"]).strip())
        return envelope

    def dispatch_only(
        self, argv: list[str]
    ) -> tuple[object, object, mock.Mock]:
        options, remaining = CLI._extract_global_options(argv)
        parsed = CLI.build_parser().parse_args(remaining)
        engine = mock.Mock()
        engine.ctx.options = options
        sentinel = object()
        engine.start.return_value = sentinel
        return CLI.dispatch(engine, parsed), parsed, engine

    def assert_dispatch_revision9_refusal(
        self, argv: list[str], reason: str
    ) -> dict[str, object]:
        with self.assertRaises(CLI.Refusal) as raised:
            self.dispatch_only(argv)
        envelope = raised.exception.outcome().envelope()
        self.assertEqual(envelope["schema"], "forge-cli/2")
        self.assertEqual(envelope["reason_code"], reason)
        return envelope

    def test_singleton_duplicates_refuse_exactly_before_repository_selection(self) -> None:
        values = {
            "--repo": "/definitely/not/a/repository",
            "--run-id": "run-revision9-cli",
            "--chain-id": "c-2026-08-28T120000Z-cafe",
        }
        for option, value in values.items():
            spellings = (
                [option, value, f"{option}={value}"],
                [f"{option}={value}", option, value],
            )
            for repeated in spellings:
                with self.subTest(option=option, repeated=repeated):
                    self.assert_revision9_refusal(
                        [
                            "--repo",
                            "/definitely/not/a/repository",
                            *repeated,
                            "status",
                        ]
                        if option != "--repo"
                        else [*repeated, "status"],
                        reason="option-duplicate",
                        message=f"forge: CLI option refused — duplicate {option}",
                    )

    def test_singleton_empty_values_refuse_exactly_before_repository_selection(self) -> None:
        for option in ("--repo", "--run-id", "--chain-id"):
            for spelling in ([f"{option}="], [option, ""]):
                with self.subTest(option=option, spelling=spelling):
                    prefix = (
                        []
                        if option == "--repo"
                        else ["--repo", "/definitely/not/a/repository"]
                    )
                    self.assert_revision9_refusal(
                        [*prefix, *spelling, "status"],
                        reason="option-empty",
                        message=f"forge: CLI option refused — empty {option}",
                    )

    def test_commit_start_requires_both_run_and_task_or_neither(self) -> None:
        cases = (
            [
                "--repo",
                "/definitely/not/a/repository",
                "--run-id",
                "run-revision9-cli",
                "commit",
                "start",
                "--paths",
                "src/example.py",
            ],
            [
                "--repo",
                "/definitely/not/a/repository",
                "commit",
                "start",
                "--paths",
                "src/example.py",
                "--task",
                "task-01",
            ],
        )
        for argv in cases:
            with self.subTest(argv=argv):
                self.assert_dispatch_revision9_refusal(
                    argv, "run-task-binding-required"
                )

        result, parsed, engine = self.dispatch_only(
            ["commit", "start", "--paths", "src/example.py"]
        )
        self.assertIs(result, engine.start.return_value)
        self.assertIsNone(engine.ctx.options.run_id)
        self.assertIsNone(parsed.task)
        engine.start.assert_called_once()

        result, parsed, engine = self.dispatch_only(
            [
                "--run-id",
                "run-revision9-cli",
                "commit",
                "start",
                "--paths",
                "src/example.py",
                "--task",
                "task-01",
            ]
        )
        self.assertIs(result, engine.start.return_value)
        self.assertEqual(engine.ctx.options.run_id, "run-revision9-cli")
        self.assertEqual(parsed.task, "task-01")
        engine.start.assert_called_once()

    def test_archive_start_legacy_recovery_flags_are_an_inseparable_pair(self) -> None:
        options, remaining = CLI._extract_global_options(
            [
                "commit",
                "start",
                "--archive-run-id",
                "run-target",
                "--legacy-recovered-head",
                "a" * 40,
                "--legacy-approval",
                "run-recovery:decision-01",
            ]
        )
        parsed = CLI.build_parser().parse_args(remaining)
        self.assertIsNone(options.run_id)
        self.assertEqual(parsed.archive_run_id, "run-target")
        self.assertEqual(parsed.legacy_recovered_head, "a" * 40)
        self.assertEqual(parsed.legacy_approval, "run-recovery:decision-01")

        for incomplete in (
            ["--legacy-recovered-head", "a" * 40],
            ["--legacy-approval", "run-recovery:decision-01"],
        ):
            with self.subTest(incomplete=incomplete):
                self.assert_dispatch_revision9_refusal(
                    [
                        "--repo",
                        "/definitely/not/a/repository",
                        "commit",
                        "start",
                        "--archive-run-id",
                        "run-target",
                        *incomplete,
                    ],
                    "legacy-recovery-approval-required",
                )

        self.assert_dispatch_revision9_refusal(
            [
                "--run-id",
                "run-bound",
                "commit",
                "start",
                "--archive-run-id",
                "run-target",
                "--task",
                "task-01",
            ],
            "run-task-binding-invalid",
        )
        self.assert_dispatch_revision9_refusal(
            [
                "commit",
                "start",
                "--paths",
                "src/example.py",
                "--legacy-recovered-head",
                "a" * 40,
                "--legacy-approval",
                "run-recovery:decision-01",
            ],
            "legacy-recovery-approval-required",
        )

    def test_journal_ingest_chain_exposes_the_complete_proof_face(self) -> None:
        options, remaining = CLI._extract_global_options(
            [
                "--repo",
                "/fixture/revision9/repository",
                "--run-id",
                "run-revision9-ingest",
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
                "a" * 40,
                "--task-status",
                "complete",
                "--idempotency-key",
                "b" * 64,
            ]
        )
        parsed = CLI.build_parser().parse_args(remaining)
        self.assertEqual(options.repo, "/fixture/revision9/repository")
        self.assertEqual(options.run_id, "run-revision9-ingest")
        self.assertEqual(parsed.command, "journal")
        self.assertEqual(parsed.journal_command, "ingest-chain")
        self.assertEqual(
            {
                "task": parsed.task,
                "state_file": parsed.state_file,
                "events_file": parsed.events_file,
                "outcome_map": parsed.outcome_map,
                "closing_head": parsed.closing_head,
                "task_status": parsed.task_status,
                "idempotency_key": parsed.idempotency_key,
            },
            {
                "task": "task-01",
                "state_file": "external/state.json",
                "events_file": "external/events.jsonl",
                "outcome_map": "external/outcome-map.json",
                "closing_head": "a" * 40,
                "task_status": "complete",
                "idempotency_key": "b" * 64,
            },
        )


class Revision9CommitStateTests(unittest.TestCase):
    def new_state(self, *, bound: bool) -> dict[str, object]:
        repository = Path("/fixture/revision9/repository")
        policy = CLI.Policy(
            sha="1" * 40,
            raw=b"fixture policy\n",
            digest="2" * 64,
            regions={},
            gate1="true",
            stack_commands=["true"],
            invariants=[],
            changelog=None,
            reviewer_eval_triggers=(),
            reviewer_eval_region_digest=None,
            reviewer_eval_trigger_error=None,
        )
        binding = (
            {
                "run_id": "run-revision9-cli",
                "task_id": "task-01",
                "repository": str(repository),
                "policy_digest": policy.digest,
            }
            if bound
            else None
        )
        return CLI._new_state(
            "c-2026-08-28T120000Z-cafe",
            SimpleNamespace(root=repository),
            "3" * 40,
            policy,
            ["src/example.py"],
            None,
            binding,
        )

    def test_state_has_exact_revision9_keys_and_null_unbound_controls(self) -> None:
        state = self.new_state(bound=False)
        self.assertEqual(set(state), CLI.STATE_KEYS)
        self.assertEqual(
            CLI.STATE_KEYS,
            {
                "schema",
                "chain_id",
                "kind",
                "state",
                "created_at",
                "last_event_at",
                "inactive_after",
                "repo_head",
                "policy_source",
                "paths",
                "staging",
                "candidate",
                "tier",
                "steps",
                "review",
                "approval",
                "authorization",
                "commit_result",
                "run_binding",
                "journal_outbox",
            },
        )
        self.assertIsNone(state["run_binding"])
        self.assertIsNone(state["journal_outbox"])

    def test_state_validates_exact_binding_and_outbox_shapes(self) -> None:
        state = self.new_state(bound=True)
        self.assertIs(CLI.validate_state(state), state)

        valid_outbox = {
            "idempotency_key": "4" * 64,
            "batch_digest": "5" * 64,
            "record_count": 1,
            "source_event_digest": "4" * 64,
        }
        state["journal_outbox"] = valid_outbox
        self.assertIs(CLI.validate_state(state), state)

        malformed: list[tuple[str, dict[str, object]]] = []
        missing_binding = copy.deepcopy(state)
        del missing_binding["run_binding"]
        malformed.append(("missing-run-binding", missing_binding))
        extra_binding_key = copy.deepcopy(state)
        extra_binding_key["run_binding"]["extra"] = True
        malformed.append(("extra-run-binding-key", extra_binding_key))
        wrong_repository = copy.deepcopy(state)
        wrong_repository["run_binding"]["repository"] = "/fixture/other"
        malformed.append(("wrong-binding-repository", wrong_repository))
        wrong_policy = copy.deepcopy(state)
        wrong_policy["run_binding"]["policy_digest"] = "6" * 64
        malformed.append(("wrong-binding-policy", wrong_policy))
        wrong_source_digest = copy.deepcopy(state)
        wrong_source_digest["journal_outbox"]["source_event_digest"] = "7" * 64
        malformed.append(("wrong-outbox-source", wrong_source_digest))
        boolean_count = copy.deepcopy(state)
        boolean_count["journal_outbox"]["record_count"] = True
        malformed.append(("boolean-outbox-count", boolean_count))
        extra_outbox_key = copy.deepcopy(state)
        extra_outbox_key["journal_outbox"]["extra"] = True
        malformed.append(("extra-outbox-key", extra_outbox_key))

        for label, candidate in malformed:
            with self.subTest(label=label), self.assertRaises(CLI.FrozenError):
                CLI.validate_state(candidate)

    def test_each_revision9_state_validation_control_is_load_bearing(self) -> None:
        state = self.new_state(bound=True)
        self.assertEqual(
            CLI.REVISION9_STATE_CONTROLS,
            frozenset({"run-binding-shape", "journal-outbox-shape"}),
        )
        for control in CLI.REVISION9_STATE_CONTROLS:
            with self.subTest(control=control), mock.patch.object(
                RUNTIME,
                "REVISION9_STATE_CONTROLS",
                CLI.REVISION9_STATE_CONTROLS - {control},
            ), self.assertRaisesRegex(
                CLI.FrozenError,
                "Revision-9 chain-state validation control is unavailable",
            ):
                CLI.validate_state(state)


class Revision9CoordinationSeamTests(unittest.TestCase):
    def _build_legacy_chain_decision(
        self, *, retrospective_ingest: bool
    ) -> SimpleNamespace:
        batch, _builders, journal = CLI._coordination_modules()
        repository = Path("/fixture/revision9/repository")
        run_id = "run-20260910-legacy-chain-records"
        chain_id = "c-2026-09-10T120000Z-cafe"
        source_event_digest = key("legacy-chain-source-event")
        state = {
            "chain_id": chain_id,
            "candidate": {"sha256": key("legacy-chain-candidate")},
            "run_binding": {
                "run_id": run_id,
                "task_id": "task-01",
                "repository": str(repository),
                "policy_digest": key("legacy-chain-policy"),
            },
        }
        run_state = SimpleNamespace(
            records=[
                {
                    "type": "run_started",
                    "run_id": run_id,
                    "recorded_at": "2026-09-10T11:59:00Z",
                },
                {"type": "task", "id": "task-01", "status": "active"},
            ]
        )
        activation_marker = {
            "type": "decision",
            "id": "decision-01",
            "resolution": journal.WRITER_ACTIVATION_RESOLUTION,
            "writer_contract": journal.WRITER_CONTRACT,
            "receipt_origin_size": 123,
            "receipt_origin_sha256": key("legacy-prefix"),
            "run_id": run_id,
            "recorded_at": "2026-09-10T12:00:00Z",
        }
        prepare_outbox_records = mock.Mock(
            return_value=(activation_marker,)
        )
        with mock.patch.object(
            journal,
            "_resolve_repository",
            return_value=(repository, repository),
        ), mock.patch.object(
            journal, "_scan_run", return_value=run_state
        ), mock.patch.object(
            batch, "prepare_outbox_records", prepare_outbox_records
        ):
            records = CLI._build_chain_journal_records(
                repository,
                state,
                "operator_skip",
                {"gate_id": "gate-2", "reason": "fixture skip"},
                source_event_digest,
                retrospective_ingest=retrospective_ingest,
            )

        return SimpleNamespace(
            activation_marker=activation_marker,
            chain_id=chain_id,
            journal=journal,
            prepare_outbox_records=prepare_outbox_records,
            records=records,
            repository=repository,
            run_state=run_state,
            source_event_digest=source_event_digest,
        )

    def test_registration_installs_exact_identities_and_is_idempotent(self) -> None:
        batch, builders, _journal = CLI._coordination_modules()
        original_scanner = getattr(
            builders,
            "_FORGE_CLI_ORIGINAL_ACTIVATION_SCANNER",
            builders._require_no_pending_activation_outbox,
        )
        with mock.patch.object(
            builders, "MERGE_TRANSITION_REDUCER", None
        ), mock.patch.object(
            builders, "_INGEST_PROOF_VERIFIER", None
        ), mock.patch.object(
            batch, "_CHAIN_BATCH_AUTHORIZER", None
        ), mock.patch.object(
            batch, "_FORGE_CLI_CHAIN_CAPABILITIES", {}, create=True
        ), mock.patch.object(
            batch,
            "_FORGE_CLI_CHAIN_CAPABILITIES_LOCK",
            threading.Lock(),
            create=True,
        ), mock.patch.object(
            builders,
            "_require_no_pending_activation_outbox",
            original_scanner,
        ):
            CLI.register_coordination_seams()
            self.assertIs(builders.MERGE_TRANSITION_REDUCER, CLI.reduce_merge_event)
            self.assertIs(builders._INGEST_PROOF_VERIFIER, CLI._ingest_proof_verifier)
            self.assertIs(batch._CHAIN_BATCH_AUTHORIZER, CLI._authorize_chain_batch)
            self.assertIs(
                builders._require_no_pending_activation_outbox,
                CORE._require_no_pending_chain_activation_outbox,
            )
            CLI.register_coordination_seams()
            self.assertIs(builders.MERGE_TRANSITION_REDUCER, CLI.reduce_merge_event)
            self.assertIs(builders._INGEST_PROOF_VERIFIER, CLI._ingest_proof_verifier)
            self.assertIs(batch._CHAIN_BATCH_AUTHORIZER, CLI._authorize_chain_batch)
            self.assertIs(
                builders._require_no_pending_activation_outbox,
                CORE._require_no_pending_chain_activation_outbox,
            )

        for callback in (
            CLI.reduce_merge_event,
            CLI._ingest_proof_verifier,
            CLI._authorize_chain_batch,
            CORE._require_no_pending_chain_activation_outbox,
        ):
            self.assertIs(getattr(callback, "_forge_cli_revision9_seam", None), True)

    def test_gate3_record_names_v2_authorization_and_review_evidence(self) -> None:
        tree_oid = "3" * 40
        authorization_id = CANDIDATE.authorization_id("sha1", tree_oid)
        review_diff_sha256 = key("reviewed-v2-patch")
        state = {
            "chain_id": "c-2026-08-28T120000Z-cafe",
            "candidate": {
                "schema": "forge-commit-candidate/2",
                "sha256": authorization_id,
                "authorization_id": authorization_id,
                "object_format": "sha1",
                "tree_oid": tree_oid,
                "base_commit_oid": "4" * 40,
                "review_diff_sha256": review_diff_sha256,
                "review_diff_byte_count": 123,
                "computed_at": "2026-08-28T12:00:00Z",
            },
            "run_binding": {
                "run_id": "run-20260828-review-binding",
                "task_id": "task-01",
                "repository": "/fixture/revision9/repository",
                "policy_digest": key("policy"),
            },
            "review": {
                "iteration": 2,
                "request": {"reviewer": "review-final"},
                "verdict": {
                    "verdict": "PASS",
                    "package_digest": key("review-package"),
                    "verdict_path": "execution-01/review/verdict.txt",
                },
            },
        }
        run_state = SimpleNamespace(
            records=[{"type": "task", "id": "task-01", "status": "active"}]
        )
        fake_builders = SimpleNamespace(
            _allocate_id=lambda _records, _kind: "check-01",
            _with_derived=lambda record, run_id: {**record, "run_id": run_id},
        )
        fake_journal = SimpleNamespace(
            GATE_3_CRITERION="gate-3: review-final verdict",
            _resolve_repository=lambda repository, _operation: (
                Path(repository),
                Path(repository),
            ),
            _scan_run=lambda _run_dir: run_state,
            _writer_contract_active=lambda _records: True,
        )
        with mock.patch.object(
            RUNTIME,
            "_coordination_modules",
            return_value=(SimpleNamespace(), fake_builders, fake_journal),
        ):
            records = CLI._build_chain_journal_records(
                Path("/fixture/revision9/repository"),
                state,
                "review_passed",
                {},
                key("review-source-event"),
            )
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["check"],
            "forge-commit-candidate/2 "
            f"authorization_id={authorization_id} "
            f"review_diff_sha256={review_diff_sha256}",
        )
        self.assertEqual(
            records[0]["binding"]["candidate"],
            {
                "kind": "git-tree-candidate-v2",
                "value": {
                    "authorization_id": authorization_id,
                    "object_format": "sha1",
                    "tree_oid": tree_oid,
                },
            },
        )

    def test_retrospective_commit_ingest_builds_only_source_bound_records(
        self,
    ) -> None:
        built = self._build_legacy_chain_decision(
            retrospective_ingest=True
        )

        self.assertEqual(len(built.records), 1)
        ordinary = built.records[0]
        self.assertFalse(
            built.journal._writer_activation_candidate(ordinary)
        )
        self.assertEqual(ordinary["id"], "decision-01")
        self.assertEqual(ordinary["outcome"], "chain-skip")
        self.assertEqual(
            ordinary["binding"]["source_record"],
            {
                "chain_id": built.chain_id,
                "event_digest": built.source_event_digest,
            },
        )
        built.prepare_outbox_records.assert_not_called()

    def test_retrospective_multicell_stack_never_uses_live_deferral(self) -> None:
        repository = Path("/fixture/revision9/retrospective-stack")
        run_id = "run-20260913-retrospective-stack-builder"
        chain_id = "c-2026-09-13T120000Z-cafe"
        candidate = key("retrospective-stack-candidate")
        facts = [
            {
                "batch_id": "batch-retrospective",
                "candidate": candidate,
                "cell_count": 2,
                "cell_index": index,
                "command_argv": [f"cell-{index}"],
                "result": "passed",
            }
            for index in (1, 2)
        ]
        state = {
            "chain_id": chain_id,
            "candidate": {"sha256": candidate},
            "run_binding": {
                "run_id": run_id,
                "task_id": "task-01",
                "repository": str(repository),
                "policy_digest": key("retrospective-stack-policy"),
            },
            "steps": {"stack:python": facts},
        }
        run_state = SimpleNamespace(
            records=[{"type": "task", "id": "task-01", "status": "active"}]
        )
        builders = SimpleNamespace(
            _allocate_id=lambda _records, _kind: "check-01",
            _with_derived=lambda record, selected_run: {
                **record,
                "run_id": selected_run,
            },
        )
        journal = SimpleNamespace(
            _resolve_repository=lambda selected, _operation: (
                selected,
                selected,
            ),
            _scan_run=lambda _run_dir: run_state,
            _writer_contract_active=lambda _records: True,
        )

        with mock.patch.object(
            RUNTIME,
            "_coordination_modules",
            return_value=(SimpleNamespace(), builders, journal),
        ), patch_engine(
            "_passed_stack_cell_is_intermediate", return_value=True
        ) as live_deferral:
            records_per_cell = [
                CLI._build_chain_journal_records(
                    repository,
                    state,
                    "step_recorded",
                    {
                        "step_id": "stack:python",
                        "run": index,
                        "result": "passed",
                    },
                    key(f"retrospective-stack-event-{index}"),
                    retrospective_ingest=True,
                )
                for index in (1, 2)
            ]

        live_deferral.assert_not_called()
        self.assertEqual([len(records) for records in records_per_cell], [1, 1])
        self.assertEqual(
            [records[0]["check"] for records in records_per_cell],
            ["cell-1", "cell-2"],
        )
        self.assertEqual(
            [
                records[0]["binding"]["source_record"]["event_digest"]
                for records in records_per_cell
            ],
            [
                key("retrospective-stack-event-1"),
                key("retrospective-stack-event-2"),
            ],
        )

    def test_live_first_use_outbox_builds_marker_then_source_bound_record(
        self,
    ) -> None:
        built = self._build_legacy_chain_decision(
            retrospective_ingest=False
        )

        self.assertEqual(len(built.records), 2)
        marker, ordinary = built.records
        self.assertEqual(marker, built.activation_marker)
        self.assertTrue(built.journal._writer_activation_marker(marker))
        self.assertFalse(
            built.journal._writer_activation_candidate(ordinary)
        )
        self.assertEqual(ordinary["id"], "decision-02")
        self.assertEqual(ordinary["outcome"], "chain-skip")
        self.assertEqual(
            ordinary["binding"]["source_record"],
            {
                "chain_id": built.chain_id,
                "event_digest": built.source_event_digest,
            },
        )
        built.prepare_outbox_records.assert_called_once_with(
            built.repository, built.run_state, ()
        )

    def test_merge_reducer_uses_explicit_delta_and_refuses_payload_state(self) -> None:
        recorded_at = "2026-08-28T12:00:00Z"
        delta: dict[str, object] = {
            "schema": "forge-merge-chain/1",
            "chain_id": "c-2026-08-28T120000Z-cafe",
            "kind": "merge",
            "state": "classifying",
            "created_at": recorded_at,
            "owner": {},
            "run": None,
            "repository": "/fixture/revision9/repository",
            "worktree": {},
            "branch": "refs/heads/fixture",
            "target": {},
            "policy_source": {},
            "candidate": None,
            "tier": None,
            "steps": {},
            "review": {},
            "approval": {},
            "authorization": {},
            "integration": {},
            "cleanup": {},
            "run_binding": None,
        }
        event: dict[str, object] = {
            "schema": "forge-merge-event/1",
            "chain_id": delta["chain_id"],
            "sequence": 1,
            "at": recorded_at,
            "event": "chain_started",
            "generation_digest": None,
            "previous_digest": "0" * 64,
            "payload": {"delta": delta},
            "digest": "1" * 64,
        }

        reduced = CLI.reduce_merge_event(None, copy.deepcopy(event))
        self.assertEqual(reduced["state"], "classifying")
        self.assertEqual(reduced["last_event_at"], recorded_at)
        self.assertEqual(reduced["journal_outbox"], None)
        self.assertNotIn("state", event["payload"])

        malicious = copy.deepcopy(event)
        malicious["payload"]["state"] = {
            "state": "closed",
            "journal_outbox": None,
            "invented": True,
        }
        with self.assertRaisesRegex(
            ValueError, "merge transition lacks an explicit state delta"
        ):
            CLI.reduce_merge_event(None, malicious)

        epoch_digest = key("derived-epoch-event")
        epoch_event = {
            "schema": "forge-merge-event/1",
            "chain_id": delta["chain_id"],
            "sequence": 2,
            "at": "2026-08-28T12:01:00Z",
            "event": "epoch_intent",
            "generation_digest": key("derived-epoch-generation"),
            "previous_digest": event["digest"],
            "payload": {
                "delta": {
                    "state": "rebasing",
                    "integration": {
                        "epoch": {
                            "operation_nonce": "e" * 32,
                            "generation_digest": key(
                                "derived-epoch-generation"
                            ),
                            "intent_digest": None,
                            "started_at": "2026-08-28T12:01:00Z",
                        }
                    },
                }
            },
            "digest": epoch_digest,
        }
        epoch_state = CLI.reduce_merge_event(reduced, epoch_event)
        self.assertEqual(
            epoch_state["integration"]["epoch"]["intent_digest"],
            epoch_digest,
        )
        recursive_epoch = copy.deepcopy(epoch_event)
        recursive_epoch["payload"]["delta"]["integration"]["epoch"][
            "intent_digest"
        ] = epoch_digest
        with self.assertRaisesRegex(
            ValueError, "merge transition lacks an explicit state delta"
        ):
            CLI.reduce_merge_event(reduced, recursive_epoch)


class Revision9IngestProofControlTests(unittest.TestCase):
    def test_exact_sixteen_proof_order_matches_the_registered_builder(self) -> None:
        _batch, builders, _journal = CLI._coordination_modules()
        self.assertEqual(
            CLI.INGEST_PROOF_ORDER,
            (
                "chain-schema-and-digest-replay",
                "materialized-state",
                "repository",
                "policy",
                "generation",
                "current-gates",
                "review-package",
                "reviewer-role",
                "reviewer-iteration",
                "reviewer-verdict",
                "operator-approval",
                "landing-proof",
                "monotonic-transitions",
                "closing-head-containment",
                "task-membership",
                "scope-membership",
            ),
        )
        self.assertEqual(
            CLI.INGEST_PROOF_CONTROLS,
            frozenset(CLI.INGEST_PROOF_ORDER),
        )
        self.assertEqual(CLI.INGEST_PROOF_ORDER, builders._INGEST_PROOF_ORDER)

    def test_secret_scan_selection_is_exact_current_gate_two_authority(self) -> None:
        _batch, builders, _journal = CLI._coordination_modules()
        candidate = key("secret-scan-candidate")
        policy_digest = key("secret-scan-policy")
        repo_head = "1" * 40
        worktree_root = "/tmp/forge-secret-scan-fixture"
        prior = {
            "candidate": {"sha256": candidate},
            "policy_source": {"digest": policy_digest},
            "repo_head": repo_head,
            "staging": {"worktree_root": worktree_root},
            "steps": {},
        }

        def scan_fact(
            findings: list[dict[str, object]] | None = None,
        ) -> dict[str, object]:
            selected = [] if findings is None else findings
            argv = ["forge-cli", "scan", "secrets", "--staged"]
            command_digest = hashlib.sha256(CLI.canonical_bytes(argv)).hexdigest()
            preimage = {
                "command_digest": command_digest,
                "cwd": worktree_root,
                "platform": "linux",
                "policy_digest": policy_digest,
                "python_version": "3.13.7",
                "repo_head": repo_head,
            }
            return {
                "candidate": candidate,
                "recorded_at": "2026-08-28T12:00:00Z",
                "result": "failed" if selected else "passed",
                "exit_code": 1 if selected else 0,
                "duration_seconds": 0.125,
                "stdout_stderr_digest": hashlib.sha256(
                    CLI.canonical_bytes(selected)
                ).hexdigest(),
                "transcript": None,
                "command_argv": argv,
                "command_digest": command_digest,
                "env_fingerprint_preimage": preimage,
                "env_fingerprint": hashlib.sha256(
                    CLI.canonical_bytes(preimage)
                ).hexdigest(),
                "repo_head": repo_head,
                "findings": selected,
            }

        fact = scan_fact()
        current = copy.deepcopy(prior)
        current["steps"] = {"secret-scan": [fact]}

        def source_event(
            *, result: str = "passed", finding_count: int = 0
        ) -> dict[str, object]:
            return {
                "sequence": 2,
                "prev_digest": "0" * 64,
                "payload": {
                    "at": "2026-08-28T12:00:01Z",
                    "details": {
                        "result": result,
                        "finding_count": finding_count,
                    },
                    "event": "secret_scan_recorded",
                    "state": current,
                },
                "digest": key(f"secret-{result}-{finding_count}"),
            }

        event = source_event()
        self.assertTrue(
            CLI._ingest_secret_scan_is_current(current, event, prior, current)
        )
        self.assertIsNotNone(
            builders._commit_secret_scan_delta(event, prior, current)
        )

        bound = copy.deepcopy(current)
        bound["chain_id"] = "c-2026-08-28T120000Z-cafe"
        bound["run_binding"] = {
            "run_id": "run-20260828-secret-scan",
            "task_id": "task-01",
            "repository": worktree_root,
            "policy_digest": policy_digest,
        }
        run_state = SimpleNamespace(
            records=[{"type": "task", "id": "task-01", "status": "active"}]
        )
        fake_builders = SimpleNamespace(
            _allocate_id=builders._allocate_id,
            _with_derived=builders._with_derived,
            _commit_secret_scan_fact_valid=builders._commit_secret_scan_fact_valid,
        )
        fake_journal = SimpleNamespace(
            _resolve_repository=lambda repository, _operation: (
                Path(repository),
                Path(repository),
            ),
            _scan_run=lambda _run_dir: run_state,
            _writer_contract_active=lambda _records: True,
        )
        with mock.patch.object(
            RUNTIME,
            "_coordination_modules",
            return_value=(SimpleNamespace(), fake_builders, fake_journal),
        ):
            records = CLI._build_chain_journal_records(
                Path(worktree_root),
                bound,
                "secret_scan_recorded",
                {"result": "passed", "finding_count": 0},
                key("secret-scan-source-event"),
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(
                records[0]["check"], "forge-cli scan secrets --staged"
            )
            synthetic = copy.deepcopy(bound)
            synthetic["steps"]["secret-scan"][-1] = {
                "candidate": candidate,
                "result": "passed",
            }
            self.assertEqual(
                CLI._build_chain_journal_records(
                    Path(worktree_root),
                    synthetic,
                    "secret_scan_recorded",
                    {"result": "passed", "finding_count": 0},
                    key("synthetic-secret-scan-source-event"),
                ),
                (),
            )

        mutations: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
        wrong_result = source_event(result="failed")
        mutations["details-result"] = (wrong_result, current)
        wrong_count = source_event(finding_count=1)
        mutations["details-count"] = (wrong_count, current)
        for label, field, value in (
            ("stored-result", "result", "failed"),
            ("synthetic-count", "finding_count", 0),
            ("synthetic-criterion", "criterion", "gate-2: secret-scan"),
            ("stored-findings", "findings", [{"path": "secret.txt"}]),
            ("stored-command", "command_argv", ["scan", "secrets"]),
            ("stored-output-digest", "stdout_stderr_digest", key("wrong-output")),
        ):
            hostile = copy.deepcopy(current)
            hostile["steps"]["secret-scan"][0][field] = value
            mutations[label] = (event, hostile)
        stale = copy.deepcopy(current)
        stale["steps"]["secret-scan"].append(scan_fact())
        mutations["stale"] = (event, stale)

        for label, (hostile_event, final_state) in mutations.items():
            with self.subTest(label=label):
                self.assertFalse(
                    CLI._ingest_secret_scan_is_current(
                        final_state, hostile_event, prior, current
                    )
                )

        for label, mutate in (
            ("missing-findings", lambda value: value.pop("findings")),
            (
                "extra-criterion",
                lambda value: value.__setitem__(
                    "criterion", "gate-2: secret-scan"
                ),
            ),
            (
                "wrong-finding-shape",
                lambda value: value.__setitem__("findings", [{"path": "secret.txt"}]),
            ),
            (
                "wrong-candidate",
                lambda value: value.__setitem__("candidate", key("wrong-candidate")),
            ),
            (
                "wrong-fingerprint",
                lambda value: value.__setitem__(
                    "env_fingerprint", key("wrong-fingerprint")
                ),
            ),
        ):
            hostile_state = copy.deepcopy(current)
            mutate(hostile_state["steps"]["secret-scan"][0])
            hostile_event = source_event()
            hostile_event["payload"]["state"] = hostile_state
            with self.subTest(native_fact=label):
                self.assertIsNone(
                    builders._commit_secret_scan_delta(
                        hostile_event, prior, hostile_state
                    )
                )

        record = {
            "type": "verification",
            "criterion": "gate-2: secret-scan",
            "result": "passed",
        }
        binding = {
            "candidate": {"kind": "staged-diff-sha256", "value": candidate},
            "review": {"verdict": "PASS"},
        }
        self.assertFalse(
            builders._binding_matches_source_fact(
                binding,
                record,
                event,
                prior,
                current,
                family="commit",
            )
        )


class Revision9ArchiveRecheckTests(unittest.TestCase):
    def archive_state(self, *, legacy: bool = False) -> dict[str, object]:
        run_id = "run-revision9-archive"
        relative = f".forge/history/runs/{run_id}.md"
        return {
            "chain_id": "c-2026-08-28T120000Z-cafe",
            "state": "verifying",
            "staging": {
                "archive": {
                    "run_id": run_id,
                    "path": relative,
                    "closing_head": None if legacy else "1" * 40,
                    "legacy_recovered_head": "2" * 40 if legacy else None,
                    "legacy_approval": (
                        "run-recovery:decision-01" if legacy else None
                    ),
                    "post_close_validation": (
                        "/fixture/revision9/run/post-close-validation.json"
                    ),
                    "dispense_targets": [],
                    "dispense_reason": None,
                    "rendered_sha256": hashlib.sha256(b"archive\n").hexdigest(),
                }
            },
        }

    def archive_context(self, state: dict[str, object]) -> SimpleNamespace:
        relative = state["staging"]["archive"]["path"]
        # Revision 9 projects the candidate through the shared FR-017 surface
        # before rerender/index checks.  Keep this fixture on that real path by
        # supplying the required owner-controlled regular file.
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repository_root = Path(temporary.name) / "repository"
        candidate = repository_root / relative
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(b"archive\n")
        repository = mock.Mock()
        repository.root = repository_root
        repository.git.side_effect = lambda arguments, **_kwargs: SimpleNamespace(
            returncode=1 if arguments[:2] == ["cat-file", "-e"] else 0,
            stdout=b"",
            stderr=b"",
        )
        repository.staged_paths.return_value = [relative]
        return SimpleNamespace(repo=repository)

    def test_normal_and_legacy_modes_recheck_identical_bytes_at_all_phases(self) -> None:
        self.assertEqual(
            CLI.ARCHIVE_RECHECK_CONTROLS,
            frozenset({"start", "authorization", "commit"}),
        )
        for legacy in (False, True):
            for phase in sorted(CLI.ARCHIVE_RECHECK_CONTROLS):
                state = self.archive_state(legacy=legacy)
                context = self.archive_context(state)
                with self.subTest(legacy=legacy, phase=phase), patch_engine(
                    "_render_archive_bytes", return_value=b"archive\n"
                ) as render, patch_engine(
                    "_read_archive_candidate", return_value=b"archive\n"
                ) as read:
                    CLI._archive_recheck(context, state, phase)
                render.assert_called_once_with(
                    context, state["staging"]["archive"]
                )
                read.assert_called_once_with(
                    context.repo.root, "run-revision9-archive"
                )
                context.repo.staged_paths.assert_called_once_with()

    def test_rerender_mismatch_refuses_at_each_required_phase(self) -> None:
        state = self.archive_state()
        for phase in sorted(CLI.ARCHIVE_RECHECK_CONTROLS):
            context = self.archive_context(state)
            with self.subTest(phase=phase), patch_engine(
                "_render_archive_bytes", return_value=b"changed\n"
            ), patch_engine(
                "_read_archive_candidate", return_value=b"archive\n"
            ), self.assertRaises(CLI.Refusal) as raised:
                CLI._archive_recheck(context, state, phase)
            envelope = raised.exception.outcome().envelope()
            self.assertEqual(envelope["schema"], "forge-cli/2")
            self.assertEqual(
                envelope["reason_code"], "archive-rerender-mismatch"
            )
            self.assertIn(phase, envelope["remediation"])

    def test_archive_recheck_refuses_an_extra_staged_path(self) -> None:
        state = self.archive_state()
        context = self.archive_context(state)
        context.repo.staged_paths.return_value.append("src/unrelated.py")
        with patch_engine(
            "_render_archive_bytes", return_value=b"archive\n"
        ), patch_engine(
            "_read_archive_candidate", return_value=b"archive\n"
        ), self.assertRaises(CLI.Refusal) as raised:
            CLI._archive_recheck(context, state, "authorization")
        envelope = raised.exception.outcome().envelope()
        self.assertEqual(envelope["schema"], "forge-cli/2")
        self.assertEqual(envelope["reason_code"], "state-precondition")
        self.assertEqual(
            envelope["message"],
            "forge: archive refused — close tree contains unrelated changes",
        )

    def test_each_archive_recheck_control_is_load_bearing(self) -> None:
        state = self.archive_state()
        context = self.archive_context(state)
        for control in CLI.ARCHIVE_RECHECK_CONTROLS:
            with self.subTest(control=control), patch_engine(
                "ARCHIVE_RECHECK_CONTROLS",
                CLI.ARCHIVE_RECHECK_CONTROLS - {control},
            ), patch_engine(
                "_render_archive_bytes", return_value=b"archive\n"
            ), patch_engine(
                "_read_archive_candidate", return_value=b"archive\n"
            ), self.assertRaisesRegex(
                CLI.FrozenError,
                "Revision-9 archive rerender control is unavailable",
            ):
                CLI._archive_recheck(context, state, control)


class Revision9BoundCLIIntegrationTests(Revision9CliSupport, CLI_FIXTURE_SUPPORT.ForgeCLIFixture):

    def test_bound_multicell_stack_journals_one_completed_batch(self) -> None:
        run_id = "run-20260913-bound-multicell-stack"
        chain_id = self.start_bound_multicell_stack_chain(run_id)
        batch, _builders, journal = CLI._coordination_modules()
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        journal_path = run_dir / "journal.jsonl"
        receipts_path = run_dir / journal.BATCH_RECEIPTS_NAME

        exit_code, verified = self.invoke_cli(
            "--chain-id", chain_id, "verify"
        )

        self.assertEqual(exit_code, 0, verified)
        self.assertEqual(
            verified["message"],
            "all required mechanical verification steps are complete",
        )
        self.assertEqual(verified["state"], "reviewing")
        state = self.state(chain_id)
        stack_batches = {
            step_id: facts
            for step_id, facts in state["steps"].items()
            if step_id.startswith("stack:")
        }
        self.assertEqual(set(stack_batches), {"stack:docs", "stack:python"})
        for facts in stack_batches.values():
            self.assertEqual(len(facts), 2)
            self.assertEqual(
                {fact["batch_id"] for fact in facts}, {facts[-1]["batch_id"]}
            )
            self.assertEqual(
                [
                    (fact["cell_index"], fact["cell_count"], fact["result"])
                    for fact in facts
                ],
                [(1, 2, "passed"), (2, 2, "passed")],
            )
        gate_lines = self.gate_lines()
        first_cell = gate_lines.index("stack:python")
        self.assertEqual(
            gate_lines[first_cell : first_cell + 4],
            [
                "stack:python",
                "stack:python-cell-2",
                "stack:python",
                "stack:python-cell-2",
            ],
        )

        events = self.events(chain_id)
        self.assertEqual(
            events[-1]["payload"]["event"], "mechanical_verification_complete"
        )
        stack_events = [
            event
            for event in events
            if event["payload"]["event"] == "step_recorded"
            and event["payload"]["details"].get("step_id") in stack_batches
        ]
        self.assertEqual(len(stack_events), 4)
        stack_carriers = [
            event
            for event in stack_events
            if "journal_batch" in event["payload"]["details"]
        ]
        self.assertEqual(len(stack_carriers), 2)

        records, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        stack_verifications = [
            record
            for record in records
            if record.get("type") == "verification"
            and str(record.get("criterion", "")).startswith("gate-2: stack:")
        ]
        self.assertEqual(
            [record["criterion"] for record in stack_verifications],
            ["gate-2: stack:docs", "gate-2: stack:python"],
        )

        with self.cli_process_context(), batch.batch_lock(
            run_dir, create=False
        ) as locked:
            receipts, _raw_receipts, _observation = (
                batch._load_receipts_for_chain_replay(locked)
            )
        for carrier in stack_carriers:
            carrier_details = carrier["payload"]["details"]
            step_id = carrier_details["step_id"]
            self.assertEqual(carrier_details["run"], 2)
            matching_verifications = [
                record
                for record in stack_verifications
                if record["criterion"] == f"gate-2: {step_id}"
            ]
            self.assertEqual(len(matching_verifications), 1)
            stack_verification = matching_verifications[0]
            self.assertEqual(stack_verification["result"], "passed")
            source_digest = stack_verification["binding"]["source_record"][
                "event_digest"
            ]
            self.assertEqual(
                carrier_details["source_event_digest"], source_digest
            )
            source_fact = carrier["payload"]["state"]["steps"][step_id][1]
            self.assertEqual(
                {
                    "batch_id": source_fact["batch_id"],
                    "cell_count": source_fact["cell_count"],
                    "cell_index": source_fact["cell_index"],
                },
                {
                    "batch_id": stack_batches[step_id][-1]["batch_id"],
                    "cell_count": 2,
                    "cell_index": 2,
                },
            )
            matching_receipts = [
                receipt
                for receipt in receipts
                if receipt.get("idempotency_key") == source_digest
            ]
            self.assertEqual(len(matching_receipts), 1)
            self.assertEqual(
                matching_receipts[0]["batch_sha256"],
                carrier_details["journal_batch"]["batch_digest"],
            )
            self.assertEqual(matching_receipts[0]["record_count"], 1)

        snapshot_paths = (
            self.state_path(chain_id),
            self.events_path(chain_id),
            journal_path,
            receipts_path,
            self.gate_log,
        )
        before_noop = tuple(path.read_bytes() for path in snapshot_paths)
        exit_code, noop = self.invoke_cli("--chain-id", chain_id, "verify")
        self.assertEqual(exit_code, 0, noop)
        self.assertEqual(
            noop["message"], "mechanical verification already complete; no-op"
        )
        self.assertEqual(noop["state"], "reviewing")
        self.assertEqual(
            tuple(path.read_bytes() for path in snapshot_paths), before_noop
        )

    def test_bound_multicell_stack_failure_journals_failed_cell_and_stops(
        self,
    ) -> None:
        run_id = "run-20260913-bound-multicell-stack-failure"
        chain_id = self.start_bound_multicell_stack_chain(run_id, cell_count=3)
        gate_helper = self.helpers / "gate.py"
        original_gate_helper = gate_helper.read_text(encoding="utf-8")
        gate_helper.write_text(
            original_gate_helper
            + '\nif step == "stack:python-cell-2":\n    raise SystemExit(7)\n',
            encoding="utf-8",
        )
        batch, _builders, journal = CLI._coordination_modules()
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        journal_path = run_dir / "journal.jsonl"

        exit_code, failed = self.invoke_cli("--chain-id", chain_id, "verify")

        self.assertEqual(exit_code, 1, failed)
        self.assertEqual(failed["reason_code"], "evidence-incomplete")
        self.assertEqual(failed["message"], "gate stack:docs cell 2 did not pass")
        self.assertEqual(failed["state"], "verifying")
        state = self.state(chain_id)
        stack_facts = state["steps"]["stack:docs"]
        self.assertNotIn("stack:python", state["steps"])
        self.assertEqual(
            [
                (fact["cell_index"], fact["cell_count"], fact["result"])
                for fact in stack_facts
            ],
            [(1, 3, "passed"), (2, 3, "failed")],
        )
        self.assertEqual(
            {fact["batch_id"] for fact in stack_facts},
            {stack_facts[-1]["batch_id"]},
        )
        self.assertEqual(
            [
                line
                for line in self.gate_lines()
                if line.startswith("stack:python")
            ],
            ["stack:python", "stack:python-cell-2"],
        )

        events = self.events(chain_id)
        self.assertFalse(
            any(
                event["payload"]["event"] == "mechanical_verification_complete"
                for event in events
            )
        )
        stack_carriers = [
            event
            for event in events
            if event["payload"]["event"] == "step_recorded"
            and event["payload"]["details"].get("step_id") == "stack:docs"
            and "journal_batch" in event["payload"]["details"]
        ]
        self.assertEqual(len(stack_carriers), 1)
        carrier_details = stack_carriers[0]["payload"]["details"]
        self.assertEqual(
            (carrier_details["run"], carrier_details["result"]), (2, "failed")
        )

        records, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        stack_verifications = [
            record
            for record in records
            if record.get("type") == "verification"
            and record.get("criterion") == "gate-2: stack:docs"
        ]
        self.assertEqual(len(stack_verifications), 1)
        self.assertEqual(stack_verifications[0]["result"], "failed")
        source_digest = stack_verifications[0]["binding"]["source_record"][
            "event_digest"
        ]
        self.assertEqual(carrier_details["source_event_digest"], source_digest)
        source_fact = stack_carriers[0]["payload"]["state"]["steps"][
            "stack:docs"
        ][1]
        self.assertEqual(
            {
                "batch_id": source_fact["batch_id"],
                "cell_count": source_fact["cell_count"],
                "cell_index": source_fact["cell_index"],
                "result": source_fact["result"],
            },
            {
                "batch_id": stack_facts[-1]["batch_id"],
                "cell_count": 3,
                "cell_index": 2,
                "result": "failed",
            },
        )

        with self.cli_process_context(), batch.batch_lock(
            run_dir, create=False
        ) as locked:
            receipts, _raw_receipts, _observation = (
                batch._load_receipts_for_chain_replay(locked)
            )
        matching_receipts = [
            receipt
            for receipt in receipts
            if receipt.get("idempotency_key") == source_digest
        ]
        self.assertEqual(len(matching_receipts), 1)
        self.assertEqual(
            matching_receipts[0]["batch_sha256"],
            carrier_details["journal_batch"]["batch_digest"],
        )
        self.assertEqual(matching_receipts[0]["record_count"], 1)

        failed_candidate = self.state(chain_id)["candidate"]["authorization_id"]
        gate_helper.write_text(original_gate_helper, encoding="utf-8")
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
        self.assertEqual(restaged["state"], "verifying")
        restaged_candidate = self.state(chain_id)["candidate"][
            "authorization_id"
        ]
        self.assertNotEqual(restaged_candidate, failed_candidate)

        exit_code, recovered = self.invoke_cli(
            "--chain-id", chain_id, "verify"
        )

        self.assertEqual(exit_code, 0, recovered)
        self.assertEqual(
            recovered["message"],
            "all required mechanical verification steps are complete",
        )
        self.assertEqual(recovered["state"], "reviewing")
        recovered_state = self.state(chain_id)
        recovered_candidate = recovered_state["candidate"]["authorization_id"]
        self.assertNotEqual(recovered_candidate, failed_candidate)
        recovered_stack_batches = {
            step_id: facts
            for step_id, facts in recovered_state["steps"].items()
            if step_id.startswith("stack:")
        }
        self.assertEqual(
            set(recovered_stack_batches), {"stack:docs", "stack:python"}
        )
        for facts in recovered_stack_batches.values():
            self.assertEqual(
                [
                    (
                        fact["cell_index"],
                        fact["cell_count"],
                        fact["result"],
                        fact["candidate"],
                    )
                    for fact in facts
                ],
                [
                    (1, 3, "passed", recovered_candidate),
                    (2, 3, "passed", recovered_candidate),
                    (3, 3, "passed", recovered_candidate),
                ],
            )

        recovered_events = self.events(chain_id)
        self.assertEqual(
            sum(
                event["payload"]["event"] == "mechanical_verification_complete"
                for event in recovered_events
            ),
            1,
        )
        recovered_carriers = [
            event
            for event in recovered_events
            if event["payload"]["event"] == "step_recorded"
            and event["payload"]["details"].get("step_id")
            in {"stack:docs", "stack:python"}
            and "journal_batch" in event["payload"]["details"]
        ]
        self.assertEqual(len(recovered_carriers), 3)
        self.assertEqual(
            [
                (
                    event["payload"]["details"]["step_id"],
                    event["payload"]["details"]["result"],
                    event["payload"]["details"]["run"],
                )
                for event in recovered_carriers
            ],
            [
                ("stack:docs", "failed", 2),
                ("stack:docs", "passed", 3),
                ("stack:python", "passed", 3),
            ],
        )

        recovered_records, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        recovered_stack_verifications = [
            record
            for record in recovered_records
            if record.get("type") == "verification"
            and record.get("criterion")
            in {"gate-2: stack:docs", "gate-2: stack:python"}
        ]
        self.assertEqual(
            [
                (
                    record["criterion"],
                    record["result"],
                    record["binding"]["candidate"]["value"][
                        "authorization_id"
                    ],
                )
                for record in recovered_stack_verifications
            ],
            [
                ("gate-2: stack:docs", "failed", failed_candidate),
                ("gate-2: stack:docs", "passed", recovered_candidate),
                ("gate-2: stack:python", "passed", recovered_candidate),
            ],
        )
        self.assertEqual(
            sum(
                record["result"] == "passed"
                and record["binding"]["candidate"]["value"][
                    "authorization_id"
                ]
                == failed_candidate
                for record in recovered_stack_verifications
            ),
            0,
        )

        with self.cli_process_context(), batch.batch_lock(
            run_dir, create=False
        ) as locked:
            recovered_receipts, _raw_receipts, _observation = (
                batch._load_receipts_for_chain_replay(locked)
            )
        source_digests = [
            event["payload"]["details"]["source_event_digest"]
            for event in recovered_carriers
        ]
        self.assertEqual(len(source_digests), len(set(source_digests)))
        for carrier, record in zip(
            recovered_carriers, recovered_stack_verifications, strict=True
        ):
            details = carrier["payload"]["details"]
            self.assertEqual(
                record["binding"]["source_record"]["event_digest"],
                details["source_event_digest"],
            )
            matching = [
                receipt
                for receipt in recovered_receipts
                if receipt.get("idempotency_key")
                == details["source_event_digest"]
            ]
            self.assertEqual(len(matching), 1)
            self.assertEqual(
                matching[0]["batch_sha256"],
                details["journal_batch"]["batch_digest"],
            )
            self.assertEqual(matching[0]["record_count"], 1)

    def test_bound_multicell_stack_journal_deferral_is_load_bearing(self) -> None:
        run_id = "run-20260913-bound-multicell-stack-disabled"
        chain_id = self.start_bound_multicell_stack_chain(run_id)

        with patch_engine(
            "_passed_stack_cell_is_intermediate", return_value=False
        ) as disabled_deferral:
            exit_code, frozen = self.invoke_cli(
                "--chain-id", chain_id, "verify"
            )

        self.assertEqual(exit_code, 2, frozen)
        status = f"forge status --chain-id {chain_id}"
        self.assertEqual(
            frozen,
            {
                "chain_id": chain_id,
                "evidence_refs": [],
                "expected": "digest-valid reconstructible chain state",
                "message": (
                    "bound chain event replay failed; chain frozen pending "
                    "status/abort, never a guessed recovery"
                ),
                "next_required_step": status,
                "observed": "carried binding fact is stale",
                "ok": False,
                "reason_code": "frozen-chain",
                "remediation": status,
                "schema": "forge-cli/2",
                "state": None,
            },
        )
        disabled_deferral.assert_called_once()
        self.assertNotIn("stack:python", self.state(chain_id)["steps"])
        self.assertIn("stack:python", self.gate_lines())
        self.assertNotIn("stack:python-cell-2", self.gate_lines())

    def test_bound_changelog_output_is_committed_policy_machinery(self) -> None:
        self.configure_changelog_gate()
        run_id = "run-20260831-bound-changelog-output"
        chain_id = self.start_bound_chain(run_id)

        exit_code, changed = self.invoke_cli(
            "--chain-id", chain_id, "gate", "run", "changelog"
        )

        self.assertEqual(exit_code, 0, changed)
        self.assertEqual(
            self.state(chain_id)["paths"], ["CHANGELOG.md", "src/app.py"]
        )
        self.assertTrue(changed["ok"])

        with patch_chain_core("_committed_changelog_output_paths", return_value=frozenset()
        ):
            exit_code, refused = self.invoke_cli(
                "--chain-id", chain_id, "gate", "run", "gate-1"
            )
        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "run-task-binding-invalid")
        self.assertIn("CHANGELOG.md", str(refused["observed"]))

        exit_code, passed = self.invoke_cli(
            "--chain-id", chain_id, "gate", "run", "gate-1"
        )
        self.assertEqual(exit_code, 0, passed)
        self.assertTrue(passed["ok"])

    def test_bound_non_changelog_output_still_names_out_of_scope_path(self) -> None:
        self.configure_changelog_gate()
        run_id = "run-20260831-bound-non-output"
        self.open_run_and_task(run_id)
        self.change("docs/guide.md", "# Outside task\n")

        exit_code, refused = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "docs/guide.md",
            "--task",
            "task-01",
        )

        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "run-task-binding-invalid")
        self.assertIn("docs/guide.md", str(refused["observed"]))

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

    def test_real_unbound_multicell_stack_ingest_keeps_every_head_record(
        self,
    ) -> None:
        prepared = self.prepare_unbound_fast_ingest(
            "run-20260913-cli-ingest-multicell-stack",
            install_captures=False,
            multicell_stack=True,
        )
        _batch, _builders, journal = CLI._coordination_modules()
        journal_path = prepared.run_dir / "journal.jsonl"
        records_before, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        normalized_before = self.normalized_journal_records(records_before)
        stack_events = [
            event
            for event in prepared.events
            if event["digest"] in prepared.selected_digests
            and event["payload"]["event"] == "step_recorded"
            and event["payload"]["details"].get("step_id") == "stack:python"
        ]
        self.assertEqual(
            [event["payload"]["details"]["run"] for event in stack_events],
            [1, 2],
        )

        exit_code, ingested = self.invoke_cli(*prepared.ingest_argv)

        self.assertEqual(exit_code, 0, ingested)
        self.assertEqual(ingested["state"], "closed")
        records_after, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        normalized_after = self.normalized_journal_records(records_after)
        appended = normalized_after[len(normalized_before) :]
        stack_records = [
            record
            for record in appended
            if record.get("type") == "verification"
            and record.get("criterion") == "gate-2: stack:python"
        ]
        self.assertEqual(len(stack_records), 2)

        expected_records = []
        expected_ids = ("check-03", "check-04")
        candidate = prepared.materialized["candidate"]
        for event, check_id in zip(stack_events, expected_ids, strict=True):
            payload = event["payload"]
            details = payload["details"]
            fact = payload["state"]["steps"]["stack:python"][
                details["run"] - 1
            ]
            transcript = str(fact["transcript"])
            transcript_bytes = (self.repo / transcript).read_bytes()
            transcript_digest = hashlib.sha256(transcript_bytes).hexdigest()
            captured_transcript = (
                f"captured/sha256/{transcript_digest}/events.jsonl"
            )
            source_record = {
                "chain_id": prepared.chain_id,
                "event_digest": event["digest"],
            }
            binding_preimage = {
                "schema": "forge-gate-binding/1",
                "source_record": source_record,
                "candidate": {
                    "kind": "git-tree-candidate-v2",
                    "value": {
                        "authorization_id": candidate["authorization_id"],
                        "object_format": candidate["object_format"],
                        "tree_oid": candidate["tree_oid"],
                    },
                },
                "review": None,
            }
            expected_records.append(
                {
                    "type": "verification",
                    "id": check_id,
                    "task": "task-01",
                    "criterion": "gate-2: stack:python",
                    "method": "Forge CLI commit chain",
                    "check": " ".join(fact["command_argv"]),
                    "result": "passed",
                    "observation": (
                        "Forge CLI recorded stack:python result passed"
                    ),
                    "evidence": [captured_transcript],
                    "run_id": prepared.run_id,
                    "recorded_at": payload["at"],
                    "binding": {
                        **binding_preimage,
                        "binding_id": hashlib.sha256(
                            CLI.canonical_bytes(binding_preimage)
                        ).hexdigest(),
                    },
                }
            )
            self.assertEqual(
                (prepared.run_dir / captured_transcript).read_bytes(),
                transcript_bytes,
            )

        self.assertEqual(stack_records, expected_records)
        self.assertEqual(
            [CLI.canonical_bytes(record) + b"\n" for record in stack_records],
            [CLI.canonical_bytes(record) + b"\n" for record in expected_records],
        )

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


if __name__ == "__main__":
    unittest.main()


class LegacyChainKeySetTests(unittest.TestCase):
    def test_pre_revision9_chain_state_reads_absent_keys_as_null(self) -> None:
        # Regression: the loader froze every pre-Revision-9 chain file
        # (phase-1 key set) repo-wide; absence of the two added keys must
        # read as null per the DM-012 amendment's legacy sentence.
        module = CLI
        legacy = {
            key: None
            for key in module.STATE_KEYS - {"run_binding", "journal_outbox"}
        }
        legacy["chain_id"] = "c-2026-08-21T223925Z-1490"
        legacy["schema"] = "forge-chain/1"
        # The key-set stage must inject the two null keys (mutating the
        # mapping in place) before any deeper validation runs; deeper checks
        # may still refuse this minimal synthetic, but never with the
        # key-set diagnostic.
        probe = dict(legacy)
        try:
            module.validate_state(probe, legacy["chain_id"])
        except module.FrozenError as error:
            self.assertNotIn("invalid top-level key set", str(error))
        self.assertIn("run_binding", probe)
        self.assertIn("journal_outbox", probe)
        self.assertIsNone(probe["run_binding"])
        self.assertIsNone(probe["journal_outbox"])
        broken = dict(legacy)
        broken.pop("steps")
        with self.assertRaises(module.FrozenError) as caught:
            module.validate_state(dict(broken), legacy["chain_id"])
        self.assertIn("invalid top-level key set", str(caught.exception))


class GateEnvironmentScrubTests(unittest.TestCase):
    def test_gate_run_source_retains_the_scrub(self) -> None:
        # Supplementary source pin; the behavioral proof lives in
        # GateEnvironmentScrubBehaviorTests below.
        import inspect

        source = inspect.getsource(CLI.Engine.gate_run)
        self.assertIn('environment.pop("FORGE_SESSION_PID", None)', source)


class GateEnvironmentScrubBehaviorTests(CLI_FIXTURE_SUPPORT.ForgeCLIFixture):
    def test_every_stack_cell_child_env_lacks_the_session_identity(self) -> None:
        # Regression: a live inherited FORGE_SESSION_PID leaked into gate
        # children and collided with hermetic fixture owners; the scrub must
        # cover the first cell AND every remaining cell of a multi-cell
        # stack, which previously inherited the unscrubbed environment.
        policy_path = self.repo / "forge-project.md"
        policy = policy_path.read_text(encoding="utf-8")
        original_region = (
            "<!-- FORGE:REGION stack-validations BEGIN -->\n"
            "```bash\n"
            'python3 "$FORGE_CLI_SCRIPTS_DIR/gate.py" stack:python "$@"\n'
            "```\n"
            "<!-- FORGE:REGION stack-validations END -->"
        )
        probe_region = (
            "<!-- FORGE:REGION stack-validations BEGIN -->\n"
            "```bash\n"
            'printf "cell1:%s\\n" "${FORGE_SESSION_PID:-unset}" >> "$FORGE_TEST_GATE_LOG"\n'
            "```\n"
            "```bash\n"
            'printf "cell2:%s\\n" "${FORGE_SESSION_PID:-unset}" >> "$FORGE_TEST_GATE_LOG"\n'
            "```\n"
            "<!-- FORGE:REGION stack-validations END -->"
        )
        self.assertIn(original_region, policy)
        policy_path.write_text(
            policy.replace(original_region, probe_region, 1), encoding="utf-8"
        )
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", "two-cell stack probe policy")

        self.change("src/app.py", "VALUE = 3\n")
        chain_id = str(self.start("src/app.py")["chain_id"])
        self.cli(
            "gate",
            "run",
            "stack:python",
            "--chain-id",
            chain_id,
            expected=0,
            FORGE_SESSION_PID="424242",
        )
        lines = [
            line
            for line in self.gate_log.read_text(encoding="utf-8").splitlines()
            if line.startswith("cell")
        ]
        self.assertEqual(lines, ["cell1:unset", "cell2:unset"])
