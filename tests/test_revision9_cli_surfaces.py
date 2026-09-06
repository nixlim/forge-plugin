"""Focused Revision-9 tests for the public Forge CLI integration surfaces."""

from __future__ import annotations

import contextlib
import datetime
import copy
import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts" / "forge" / "cli.py"
ENVELOPE_KEYS = {
    "chain_id",
    "evidence_refs",
    "expected",
    "message",
    "next_required_step",
    "observed",
    "ok",
    "reason_code",
    "remediation",
    "schema",
    "state",
}


from tests._cli_loader import load_script  # cli split phase 0: one shared loader


CLI = load_script("forge_revision9_cli_surface_tests", CLI_PATH)
CLI_FIXTURE_SUPPORT = load_script(
    "forge_revision9_cli_fixture_support", ROOT / "tests" / "test_cli_chain.py"
)


def key(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


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
                CLI,
                "REVISION9_STATE_CONTROLS",
                CLI.REVISION9_STATE_CONTROLS - {control},
            ), self.assertRaisesRegex(
                CLI.FrozenError,
                "Revision-9 chain-state validation control is unavailable",
            ):
                CLI.validate_state(state)


class Revision9CoordinationSeamTests(unittest.TestCase):
    def test_registration_installs_exact_identities_and_is_idempotent(self) -> None:
        batch, builders, _journal = CLI._coordination_modules()
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
        ):
            CLI.register_coordination_seams()
            self.assertIs(builders.MERGE_TRANSITION_REDUCER, CLI.reduce_merge_event)
            self.assertIs(builders._INGEST_PROOF_VERIFIER, CLI._ingest_proof_verifier)
            self.assertIs(batch._CHAIN_BATCH_AUTHORIZER, CLI._authorize_chain_batch)
            CLI.register_coordination_seams()
            self.assertIs(builders.MERGE_TRANSITION_REDUCER, CLI.reduce_merge_event)
            self.assertIs(builders._INGEST_PROOF_VERIFIER, CLI._ingest_proof_verifier)
            self.assertIs(batch._CHAIN_BATCH_AUTHORIZER, CLI._authorize_chain_batch)

        for callback in (
            CLI.reduce_merge_event,
            CLI._ingest_proof_verifier,
            CLI._authorize_chain_batch,
        ):
            self.assertIs(getattr(callback, "_forge_cli_revision9_seam", None), True)

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
        )
        with mock.patch.object(
            CLI,
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
                with self.subTest(legacy=legacy, phase=phase), mock.patch.object(
                    CLI, "_render_archive_bytes", return_value=b"archive\n"
                ) as render, mock.patch.object(
                    CLI, "_read_archive_candidate", return_value=b"archive\n"
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
            with self.subTest(phase=phase), mock.patch.object(
                CLI, "_render_archive_bytes", return_value=b"changed\n"
            ), mock.patch.object(
                CLI, "_read_archive_candidate", return_value=b"archive\n"
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
        with mock.patch.object(
            CLI, "_render_archive_bytes", return_value=b"archive\n"
        ), mock.patch.object(
            CLI, "_read_archive_candidate", return_value=b"archive\n"
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
            with self.subTest(control=control), mock.patch.object(
                CLI,
                "ARCHIVE_RECHECK_CONTROLS",
                CLI.ARCHIVE_RECHECK_CONTROLS - {control},
            ), mock.patch.object(
                CLI, "_render_archive_bytes", return_value=b"archive\n"
            ), mock.patch.object(
                CLI, "_read_archive_candidate", return_value=b"archive\n"
            ), self.assertRaisesRegex(
                CLI.FrozenError,
                "Revision-9 archive rerender control is unavailable",
            ):
                CLI._archive_recheck(context, state, control)


class Revision9BoundCLIIntegrationTests(CLI_FIXTURE_SUPPORT.ForgeCLIFixture):
    def revision9_environment(self) -> dict[str, str]:
        return self.environment(FORGE_SESSION_PID=str(os.getpid()))

    @contextlib.contextmanager
    def cli_process_context(self):
        with mock.patch.dict(
            os.environ, self.revision9_environment(), clear=True
        ), mock.patch.object(
            CLI, "SCRIPT_DIR", self.helpers
        ), mock.patch.object(
            CLI, "PLUGIN_ROOT", ROOT
        ), mock.patch.object(
            CLI, "CODEX_EXECUTABLE", str(self.helpers / "fake-codex")
        ):
            yield

    def invoke_cli(self, *argv: str) -> tuple[int, dict[str, object]]:
        return self.invoke_cli_at(self.repo, *argv)

    def invoke_cli_at(
        self, repository: Path, *argv: str
    ) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.cli_process_context(), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            exit_code = CLI.main(
                ["--json", "--repo", str(repository), *argv]
            )
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(set(envelope), ENVELOPE_KEYS)
        return exit_code, envelope

    def open_run_and_task(
        self,
        run_id: str,
        *,
        scope: tuple[str, ...] = ("src/**",),
        files: tuple[str, ...] = ("src/app.py",),
    ) -> None:
        _batch, builders, _journal = CLI._coordination_modules()
        with self.cli_process_context():
            builders.run_open(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-open"),
                goal="Exercise the Revision-9 CLI surface",
                scope=list(scope),
                plugin_ref="forge-revision9-cli-tests",
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-task"),
                task="task-01",
                goal="Bind one commit chain",
                acceptance=["The exact binding and outbox controls pass"],
                files=list(files),
            )

    def start_bound_chain(self, run_id: str) -> str:
        self.open_run_and_task(run_id)
        self.change("src/app.py", "VALUE = 2\n")
        exit_code, envelope = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "src/app.py",
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, envelope)
        self.assertTrue(envelope["ok"])
        self.assertEqual(envelope["schema"], "forge-cli/2")
        chain_id = envelope["chain_id"]
        self.assertIsInstance(chain_id, str)
        return str(chain_id)

    def start_bound_fast_chain(self, run_id: str) -> str:
        self.open_run_and_task(
            run_id,
            scope=("docs/**",),
            files=("docs/guide.md",),
        )
        self.change("docs/guide.md", "# Revision-9 fast landing\n")
        exit_code, started = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "docs/guide.md",
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, started)
        chain_id = str(started["chain_id"])
        exit_code, verified = self.invoke_cli(
            "--chain-id", chain_id, "verify"
        )
        self.assertEqual(exit_code, 0, verified)
        self.assertEqual(verified["schema"], "forge-cli/2")
        self.assertEqual(verified["state"], "authorized")
        self.assertEqual(self.state(chain_id)["tier"]["effective"], "fast")
        return chain_id

    def configure_changelog_gate(self) -> None:
        (self.repo / "forge-project.md").write_text(
            CLI_FIXTURE_SUPPORT.policy_with_changelog(), encoding="utf-8"
        )
        (self.repo / "CHANGELOG.md").write_text(
            "# Changes\n", encoding="utf-8"
        )
        self.git("add", "--", "forge-project.md", "CHANGELOG.md")
        self.git("commit", "--quiet", "-m", "configure changelog gate")

    def test_bound_changelog_output_is_committed_policy_machinery(self) -> None:
        self.configure_changelog_gate()
        run_id = "run-20260831-bound-changelog-output"
        chain_id = self.start_bound_chain(run_id)

        exit_code, changed = self.invoke_cli(
            "--chain-id", chain_id, "gate", "run", "changelog"
        )

        self.assertEqual(exit_code, 0, changed)
        self.assertEqual(
            self.state(chain_id)["paths"], ["src/app.py", "CHANGELOG.md"]
        )
        self.assertTrue(changed["ok"])

        with mock.patch.object(
            CLI, "_committed_changelog_output_paths", return_value=frozenset()
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

    def selected_commit_ingest_event_digests(
        self,
        materialized: dict[str, object],
        events: list[dict[str, object]],
    ) -> list[str]:
        """Derive the implementation-owned outcome map from live event facts."""

        selected: list[str] = []
        final_candidate = materialized["candidate"]["sha256"]
        tier = materialized["tier"]
        review = materialized["review"]
        approval = materialized["approval"]
        approval_required = bool(
            tier["control"] or review["operator_cosign_required"]
        )
        prior_state: dict[str, object] | None = None
        for event in events:
            payload = event["payload"]
            details = payload["details"]
            event_state = payload["state"]
            event_name = payload["event"]
            active = False
            if event_name == "step_recorded":
                active = CLI._ingest_step_is_current(
                    materialized, event_state, details
                )
            elif event_name == "secret_scan_recorded":
                active = CLI._ingest_secret_scan_is_current(
                    materialized, event, prior_state, event_state
                )
            elif event_name in {"review_passed", "review_blocked"}:
                active = bool(
                    tier["effective"] == "hard"
                    and event_name == "review_passed"
                    and event_state["review"]["verdict"] == review["verdict"]
                )
            elif event_name == "operator_approved":
                active = bool(
                    approval_required
                    and event_state["approval"] == approval
                )
            elif event_name == "operator_skip":
                gate_id = details.get("gate_id")
                active = bool(
                    isinstance(gate_id, str)
                    and CLI._user_skip(materialized, gate_id)
                    == CLI._user_skip(event_state, gate_id)
                )
            elif event_name in {"commit_produced", "commit_close_recovered"}:
                active = (
                    details.get("commit_sha")
                    == materialized["commit_result"]["commit_sha"]
                )
            if (
                active
                and event_state["candidate"]["sha256"] == final_candidate
            ):
                selected.append(str(event["digest"]))
            prior_state = event_state
        return selected

    @staticmethod
    def normalized_journal_records(
        records: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        return [
            {name: value for name, value in record.items() if name != "_line"}
            for record in records
        ]

    def prepare_unbound_fast_ingest(
        self,
        run_id: str,
        *,
        install_captures: bool,
        mechanical_skip: bool = False,
    ) -> SimpleNamespace:
        """Finalize a native unbound chain and capture its exact live package."""

        self.change(
            "docs/guide.md",
            f"# Retrospective source for {run_id}\n",
        )
        exit_code, started = self.invoke_cli(
            "commit", "start", "--paths", "docs/guide.md"
        )
        self.assertEqual(exit_code, 0, started)
        self.assertEqual(started["schema"], "forge-cli/1")
        chain_id = str(started["chain_id"])

        construction_bypass = (
            mock.patch.object(CLI, "_fast_mechanical_skips", return_value=[])
            if mechanical_skip
            else contextlib.nullcontext()
        )
        with construction_bypass:
            if mechanical_skip:
                exit_code, skipped = self.invoke_cli(
                    "--chain-id",
                    chain_id,
                    "commit",
                    "skip",
                    "assertion-sensor",
                    "--reason",
                    "construct a terminal hostile retrospective package",
                )
                self.assertEqual(exit_code, 0, skipped)
            exit_code, verified = self.invoke_cli(
                "--chain-id", chain_id, "verify"
            )
            self.assertEqual(exit_code, 0, verified)
            self.assertEqual(verified["state"], "authorized")
            exit_code, finalized = self.invoke_cli(
                "--chain-id",
                chain_id,
                "commit",
                "finalize",
                "--message",
                f"Finalize retrospective source for {run_id}",
            )
        self.assertEqual(exit_code, 0, finalized)
        self.assertEqual(finalized["state"], "closed")

        materialized = self.state(chain_id)
        events = self.events(chain_id)
        state_raw = self.state_path(chain_id).read_bytes()
        events_raw = self.events_path(chain_id).read_bytes()
        self.assertEqual(materialized["kind"], "commit")
        self.assertEqual(materialized["state"], "closed")
        self.assertEqual(materialized["tier"]["effective"], "fast")
        self.assertIsNone(materialized["run_binding"])
        self.assertIsNone(materialized["journal_outbox"])
        self.assertEqual(
            materialized["commit_result"]["commit_sha"],
            self.git("rev-parse", "HEAD"),
        )
        self.assertEqual(state_raw, CLI.canonical_bytes(materialized) + b"\n")
        self.assertEqual(
            events_raw,
            b"".join(CLI.canonical_bytes(event) + b"\n" for event in events),
        )

        selected_digests = self.selected_commit_ingest_event_digests(
            materialized, events
        )
        selected_events = [
            event for event in events if event["digest"] in selected_digests
        ]
        selected_identities = tuple(
            event["payload"]["details"].get(
                "step_id", event["payload"]["event"]
            )
            for event in selected_events
        )
        if mechanical_skip:
            self.assertEqual(
                CLI._fast_mechanical_skips(materialized),
                ["assertion-sensor"],
            )
            self.assertIn("operator_skip", selected_identities)
            self.assertNotIn("assertion-sensor", selected_identities)
        else:
            self.assertEqual(
                selected_identities,
                (
                    "gate-1",
                    "gate-1",
                    "stack:docs",
                    "assertion-sensor",
                    "invariant:1",
                    "secret_scan_recorded",
                    "commit_produced",
                ),
            )
        outcome_map = {
            "schema": "forge-chain-ingest-outcome-map/1",
            "chain_id": chain_id,
            "task": "task-01",
            "task_status": "complete",
            "event_digests": selected_digests,
        }
        outcome_raw = CLI.canonical_bytes(outcome_map) + b"\n"
        source_paths = {
            "state_file": "external/source-state.json",
            "events_file": "external/source-events.jsonl",
            "outcome_map": "external/source-outcome-map.json",
        }
        external = self.repo / "external"
        external.mkdir()
        source_data = {
            "state_file": state_raw,
            "events_file": events_raw,
            "outcome_map": outcome_raw,
        }
        for field, relative in source_paths.items():
            (self.repo / relative).write_bytes(source_data[field])

        self.open_run_and_task(
            run_id,
            scope=("docs/**",),
            files=("docs/guide.md",),
        )
        with self.cli_process_context():
            (
                canonical_repository,
                run_dir,
                read_data,
                captured,
                digests,
            ) = CLI._read_ingest_sources(
                self.repo,
                run_id,
                state_file=source_paths["state_file"],
                events_file=source_paths["events_file"],
                outcome_map=source_paths["outcome_map"],
            )
            self.assertEqual(read_data, source_data)
            for field, name in (
                ("state_file", "state.json"),
                ("events_file", "events.jsonl"),
                ("outcome_map", "outcome-map.json"),
            ):
                self.assertEqual(
                    captured[field],
                    f"captured/sha256/{digests[field]}/{name}",
                )
                self.assertFalse(captured[field].startswith(".codex-orchestrator/"))
            if install_captures:
                CLI._install_ingest_sources(
                    canonical_repository, run_dir, read_data, digests
                )

        closing_head = self.git("rev-parse", "HEAD")
        verifier_inputs = {
            "task": "task-01",
            **source_paths,
            "state_file_sha256": digests["state_file"],
            "events_file_sha256": digests["events_file"],
            "outcome_map_sha256": digests["outcome_map"],
            "closing_head": closing_head,
            "task_status": "complete",
        }
        idempotency_key = key(f"{run_id}-ingest")
        ingest_argv = (
            "--run-id",
            run_id,
            "journal",
            "ingest-chain",
            "--task",
            "task-01",
            "--state-file",
            source_paths["state_file"],
            "--events-file",
            source_paths["events_file"],
            "--outcome-map",
            source_paths["outcome_map"],
            "--closing-head",
            closing_head,
            "--task-status",
            "complete",
            "--idempotency-key",
            idempotency_key,
        )
        return SimpleNamespace(
            run_id=run_id,
            run_dir=run_dir,
            chain_id=chain_id,
            materialized=materialized,
            events=events,
            selected_digests=selected_digests,
            source_data=source_data,
            captured=captured,
            digests=digests,
            verifier_inputs=verifier_inputs,
            ingest_argv=ingest_argv,
        )

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
        self.assertEqual(len(appended), 8)
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
        self.assertEqual(len(verifications), 6)
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
                    "kind": "staged-diff-sha256",
                    "value": prepared.materialized["candidate"]["sha256"],
                },
            )

        journal_after = journal_path.read_bytes()
        receipts_after = receipts_path.read_bytes()
        intent_path = prepared.run_dir / journal.BATCH_INTENT_NAME
        self.assertFalse(intent_path.exists())
        with mock.patch.object(
            CLI,
            "_verify_and_build_ingest_records",
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
            with self.subTest(control=control), mock.patch.object(
                CLI, "INGEST_PROOF_CONTROLS", enabled
            ), mock.patch.object(
                CLI, "_REQUIRED_INGEST_PROOF_CONTROLS", enabled
            ), mock.patch.object(
                CLI, "_require_ingest_proof", side_effect=track_boundary
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

        with mock.patch.object(
            CLI, "_require_ingest_proof", side_effect=track_boundary
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

    def test_bound_start_persists_exact_immutable_binding(self) -> None:
        run_id = "run-20260828-cli-binding"
        chain_id = self.start_bound_chain(run_id)
        state = self.state(chain_id)
        self.assertEqual(
            state["run_binding"],
            {
                "run_id": run_id,
                "task_id": "task-01",
                "repository": str(self.repo.resolve()),
                "policy_digest": state["policy_source"]["digest"],
            },
        )
        self.assertIsNone(state["journal_outbox"])
        self.assertIs(CLI.validate_state(state), state)
        for event in self.events(chain_id):
            self.assertEqual(
                event["payload"]["state"]["run_binding"],
                state["run_binding"],
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

    def test_linked_worktree_shares_chain_authority_across_cli_builders_and_archive(
        self,
    ) -> None:
        _batch, builders, journal = CLI._coordination_modules()
        archive = CLI._archive_module()
        linked = self.temp_root / "linked-worktree"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")

        common_root = self.repo.resolve()
        chains_root = common_root / ".forge" / "chains"
        self.assertEqual(CLI.Repository(linked).common_root(), common_root)
        self.assertEqual(CLI._chain_storage_root(linked), chains_root)
        self.assertEqual(builders.chain_storage_root(linked), chains_root)
        self.assertEqual(archive.chain_storage_root(linked), chains_root)

        run_id = "run-20260828-linked-chain-authority"
        with self.cli_process_context():
            builders.run_open(
                linked,
                run_id,
                idempotency_key=key(f"{run_id}-open"),
                goal="Prove shared linked-worktree chain authority",
                scope=["docs/**"],
                plugin_ref="forge-revision9-cli-tests",
            )
            builders.task_start(
                linked,
                run_id,
                idempotency_key=key(f"{run_id}-task"),
                task="task-01",
                goal="Land and archive one linked-worktree chain",
                acceptance=["All chain consumers use the common root"],
                files=["docs/guide.md"],
            )

        (linked / "docs" / "guide.md").write_text(
            "# Linked Revision-9 chain authority\n", encoding="utf-8"
        )
        exit_code, started = self.invoke_cli_at(
            linked,
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "docs/guide.md",
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, started)
        chain_id = str(started["chain_id"])
        state_path = chains_root / f"{chain_id}.json"
        events_path = chains_root / f"{chain_id}.events.jsonl"
        self.assertTrue(state_path.is_file())
        self.assertTrue(events_path.is_file())
        self.assertFalse((linked / ".forge" / "chains").exists())

        exit_code, verified = self.invoke_cli_at(
            linked, "--chain-id", chain_id, "verify"
        )
        self.assertEqual(exit_code, 0, verified)
        self.assertEqual(verified["state"], "authorized")
        exit_code, finalized = self.invoke_cli_at(
            linked,
            "--chain-id",
            chain_id,
            "commit",
            "finalize",
            "--message",
            "Land linked Revision-9 chain authority",
        )
        self.assertEqual(exit_code, 0, finalized)
        self.assertEqual(finalized["state"], "closed")

        with self.cli_process_context():
            finished = builders.task_finish(
                linked,
                run_id,
                idempotency_key=key(f"{run_id}-finish"),
                task="task-01",
                status="complete",
            )
            closed = builders.run_close(
                linked,
                run_id,
                idempotency_key=key(f"{run_id}-close"),
                judgment="blocked",
                summary="Linked-worktree authority lifecycle completed",
                risks=[],
                follow_ups=[],
            )
        self.assertFalse(finished.repeated)
        self.assertFalse(closed.repeated)

        run_dir = common_root / ".codex-orchestrator" / "runs" / run_id
        records, issues = journal.read_journal(run_dir / "journal.jsonl")
        self.assertEqual(issues, [])
        package = archive.capture_archive_chain_package(
            linked,
            run_dir,
            records,
            {chain_id},
            activated=True,
        )
        self.assertEqual(package.root, chains_root)
        self.assertEqual(
            [snapshot.chain_id for snapshot in package.chains], [chain_id]
        )
        resolved = archive.resolve_archive_bindings(
            linked, run_dir, records, package, True
        )
        expected_lines = {
            int(record["_line"])
            for record in records
            if isinstance(record.get("binding"), dict)
            and record["binding"].get("source_record", {}).get("chain_id")
            == chain_id
        }
        self.assertTrue(expected_lines)
        self.assertEqual(set(resolved), expected_lines)

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
        self.assertEqual(abort_binding["candidate"]["value"], state["candidate"]["sha256"])
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
        with mock.patch.object(CLI, "_build_chain_journal_records", return_value=()):
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

    def _quarantine_and_tombstone(self, chain_id: str) -> Path:
        """Reproduce the gse freeze outcome: artifacts moved out, operator tombstone sealed."""
        quarantine = self.repo / ".forge/tmp/quarantine-test"
        quarantine.mkdir(parents=True, exist_ok=True)
        for name in (f"{chain_id}.json", f"{chain_id}.events.jsonl"):
            (self.repo / ".forge/chains" / name).rename(quarantine / name)
        exit_code, sealed = self.invoke_cli(
            "--chain-id", chain_id, "chain", "tombstone",
            "--reason", "operator direction: chain froze; artifacts quarantined",
        )
        self.assertEqual(exit_code, 0, sealed)
        tombstone = self.repo / ".forge/chains/tombstones" / f"{chain_id}.json"
        self.assertTrue(tombstone.exists())
        return tombstone

    def _journal_records(self, run_dir: Path) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in (run_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]

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
        with mock.patch.object(CLI, "_build_chain_journal_records", return_value=()):
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
        with mock.patch.object(CLI, "_build_chain_journal_records", return_value=()):
            exit_code, aborted = self.invoke_cli(
                "--chain-id", chain_id, "commit", "abort", "--reason", "legacy abort"
            )
        self.assertEqual(exit_code, 0, aborted)
        inactive_after = CLI.parse_time(str(self.state(chain_id)["inactive_after"]))
        later = inactive_after + datetime.timedelta(hours=1)
        with mock.patch.object(CLI, "utc_now", return_value=later):
            # Disable proof: without the exemption the deadline refuses the verb.
            with mock.patch.object(
                CLI, "TERMINAL_TOUCH_VERBS", frozenset({"status", "commit abort"})
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
        with mock.patch.object(CLI, "_build_chain_journal_records", return_value=()):
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
            with mock.patch.object(
                CLI, "TERMINAL_TOUCH_VERBS", frozenset({"status", "commit abort"})
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
        with mock.patch.object(CLI, "_build_chain_journal_records", return_value=()):
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
