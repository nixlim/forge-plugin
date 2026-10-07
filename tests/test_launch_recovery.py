"""Recovery and survivor coverage for typed launches."""

from __future__ import annotations

import io
import json
import os
import re
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from tests._cli_loader import package_module, patch_engine
from tests._launch_support import (
    LAUNCH_LANE,
    VERBS_LAUNCH,
    VERBS_LAUNCH_COLLECT,
    LaunchLaneSupport,
    kill_group,
    wait_path,
)

from codex_orchestrator import journal

ENGINE = package_module("engine")
ATTEMPT = package_module("engine._review_attempt")
LANE_API = package_module("engine._review_lane_api")


class LaunchReservedReasonTests(unittest.TestCase):
    def test_cli_modules_have_no_reserved_reason_emitters(self):
        reserved = {
            "archive-rerender-mismatch", "archive-size-limit", "batch-idempotency-conflict",
            "citation-out-of-root",
            "batch-pending", "binding-invalid", "execution-result-pending", "ingest-proof-invalid",
            "journal-outbox-pending", "legacy-recovery-approval-required", "lzma-unavailable",
            "run-task-binding-invalid", "run-task-binding-required", "run-scope-exceeded",
        }
        members = {code.name for code in ENGINE.V2ReasonCode if code.value in reserved}
        self.assertEqual(len(members), len(reserved))
        pattern = re.compile(r"\b(?:" + "|".join(sorted(members | reserved)) + r")\b")
        modules = sorted(Path(LAUNCH_LANE.__file__).parent.parent.rglob("*.py"))
        self.assertTrue(modules)
        for path in modules:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                if path.name == "envelope.py":
                    source = re.sub(r'^    [A-Z_]+ = "[a-z-]+"$', "", source, flags=re.MULTILINE)
                self.assertIsNone(pattern.search(source))
                self.assertNotIn("journal batch-recover", source)


class LaunchRecoveryTests(LaunchLaneSupport, unittest.TestCase):
    def test_start_append_failure_reports_and_keeps_launch_files(self) -> None:
        engine = self.ready_engine()
        stderr = io.StringIO()
        with (
            mock.patch.object(journal, "_write_line", side_effect=journal.CoordinationRefusal(
                journal.APPEND_IO_ERROR
            )),
            redirect_stderr(stderr),
        ):
            outcome = self.seed_launch(engine=engine)
        self.assertTrue(outcome.ok)
        self.assertEqual(stderr.getvalue(), journal.APPEND_IO_ERROR + "\n")
        marker_path = (self.run_dir(self.repo, self.run_id)
                       / "codex-implementer-01/execution-01/launch.json")
        self.assertTrue(marker_path.exists())
        self.assertTrue((marker_path.parent / "pid").exists())
        self.assertEqual(self.execution_records(), [])

    def test_append_lock_failure_reports_and_launches(self) -> None:
        engine = self.ready_engine()
        stderr = io.StringIO()
        with (
            mock.patch.object(LAUNCH_LANE.fcntl, "flock", side_effect=OSError("lock failed")),
            redirect_stderr(stderr),
        ):
            outcome = self.seed_launch(engine=engine)
        self.assertTrue(outcome.ok)
        self.assertEqual(stderr.getvalue(), journal.APPEND_IO_ERROR + "\n")
        marker_path = (self.run_dir(self.repo, self.run_id)
                       / "codex-implementer-01/execution-01/launch.json")
        self.assertTrue(marker_path.exists())
        self.assertTrue((marker_path.parent / "pid").exists())

    def _assert_cleanup_failure_is_explicit(self) -> None:
        engine = self.ready_engine()
        directory = self.run_dir(self.repo, self.run_id) / "codex-implementer-01/execution-01"
        with (
            mock.patch.object(
                VERBS_LAUNCH._review_lane_api,
                "wrapper_launcher",
                side_effect=RuntimeError("fixture preparation failure"),
            ),
            mock.patch.object(VERBS_LAUNCH.os, "rmdir", side_effect=PermissionError()),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            self.launch_direct(engine=engine)
        self.assertIs(caught.exception.reason_code, ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE)
        self.assertEqual(
            caught.exception.message,
            f"forge: launch refused — cleanup incomplete for execution-01; "
            f"remove {directory} before retrying",
        )
        self.assertTrue(directory.is_dir())
        self.assertFalse(self.execution_records())

    def test_pre_record_cleanup_failure_is_explicit_and_recoverable(self) -> None:
        self._assert_cleanup_failure_is_explicit()

    def test_pre_record_cleanup_failure_control_is_load_bearing(self) -> None:
        with mock.patch.object(VERBS_LAUNCH, "_cleanup", return_value=None):
            with self.assertRaises(AssertionError):
                self._assert_cleanup_failure_is_explicit()

    def test_record_without_spawn_launches_then_abandons_and_allows_retry(self) -> None:
        self.seed_launch(provider="codex")
        engine = self.ready_engine()
        record = self.execution_records()[-1]
        directory = self.attempt_dir(record)
        execution = str(record["execution"])

        with self.assertRaises(ENGINE.Refusal) as caught:
            VERBS_LAUNCH_COLLECT.launch_collect(engine, execution)
        self.assertEqual(
            caught.exception.message,
            f"forge: launch collect refused — execution {execution} is still "
            "launching; retry after the identity deadline",
        )
        self.assertFalse((directory / "identity.json").exists())

        with patch_engine("IDENTITY_DEADLINE_SECONDS", -1):
            outcome = VERBS_LAUNCH_COLLECT.launch_collect(engine, execution)
        self.assertEqual(outcome.state, "failed")
        completion = json.loads((directory / "completion.json").read_text())
        self.assertEqual(completion["error"], "abandoned")
        self.assertEqual(self.marker(record)["collected_status"], "failed")

        self.seed_launch(provider="codex")
        self.assertEqual(len(self.execution_records()), 2)

    def test_wrapper_winning_abandonment_claim_is_reobserved(self) -> None:
        self.seed_launch(provider="codex")
        engine = self.ready_engine()
        record = self.execution_records()[-1]
        bound = VERBS_LAUNCH_COLLECT._bound_execution(
            engine, str(record["execution"]), "collect"
        )
        first = ATTEMPT.AttemptObservation("abandonable")
        winner = ATTEMPT.AttemptObservation(
            "completed", identity=self.live_identity(record),
            completion={"error": "wrapper failure"},
        )
        descriptor = LAUNCH_LANE.open_attempt(bound.paths)
        try:
            with (
                patch_engine("observe_attempt", side_effect=(first, winner)),
                patch_engine("claim_abandoned", return_value=(False, {})) as claim,
            ):
                observed = VERBS_LAUNCH_COLLECT._classify_attempt(bound, descriptor)
        finally:
            os.close(descriptor)
        self.assertIs(observed, winner)
        claim.assert_called_once()

    def test_identity_unproven_is_byte_stable_then_group_empty_clears(self) -> None:
        self.seed_launch(provider="codex")
        engine = self.ready_engine()
        record = self.execution_records()[-1]
        directory = self.attempt_dir(record)
        execution = str(record["execution"])
        identity_path = self.write_identity(self.live_identity(record), record)
        identity_raw = identity_path.read_bytes()
        journal_path = self.run_dir(self.repo, self.run_id) / "journal.jsonl"
        marker_path = directory / "launch.json"
        before = (journal_path.read_bytes(), marker_path.read_bytes(), identity_raw)

        for name in sorted(LANE_API.NO_SIGNAL_OUTCOMES):
            with self.subTest(outcome=name):
                proof = ATTEMPT.GroupProof(name, 77, (77, 88))
                with (
                    patch_engine("prove_group_ownership", return_value=proof),
                    patch_engine("terminate_owned_group") as terminate,
                    self.assertRaises(ENGINE.Refusal) as collected,
                ):
                    VERBS_LAUNCH_COLLECT.launch_collect(engine, execution)
                with (
                    patch_engine("prove_group_ownership", return_value=proof),
                    patch_engine("terminate_owned_group") as cancel_terminate,
                    self.assertRaises(ENGINE.Refusal) as cancelled,
                ):
                    VERBS_LAUNCH_COLLECT.launch_cancel(engine, execution)
                expected = (
                    f"identity-unproven for {execution}; member PIDs [77, 88]; "
                    "recorded PGID 77; nothing was signalled"
                )
                self.assertEqual(
                    collected.exception.message,
                    f"forge: launch collect refused — {expected}",
                )
                self.assertEqual(
                    cancelled.exception.message,
                    f"forge: launch cancel refused — {expected}",
                )
                terminate.assert_not_called()
                cancel_terminate.assert_not_called()
                self.assertEqual(
                    (
                        journal_path.read_bytes(),
                        marker_path.read_bytes(),
                        (directory / "identity.json").read_bytes(),
                    ),
                    before,
                )
                self.assertFalse((directory / "completion.json").exists())

        def assert_cancel_guard() -> None:
            proof = ATTEMPT.GroupProof("identity-unproven", 77, (77, 88))
            with (
                patch_engine("prove_group_ownership", return_value=proof),
                self.assertRaises(ENGINE.Refusal) as caught,
            ):
                VERBS_LAUNCH_COLLECT.launch_cancel(engine, execution)
            self.assertIn("nothing was signalled", caught.exception.message)

        assert_cancel_guard()
        with (
            patch_engine("NO_SIGNAL_OUTCOMES", frozenset()),
            self.assertRaises(AssertionError),
        ):
            assert_cancel_guard()

        empty = ATTEMPT.GroupProof("group-empty", 77)
        with patch_engine("prove_group_ownership", return_value=empty):
            outcome = VERBS_LAUNCH_COLLECT.launch_collect(engine, execution)
        self.assertEqual(outcome.state, "failed")
        completion = json.loads((directory / "completion.json").read_text())
        self.assertEqual(completion["error"], "wrapper-lost")
        self.assertEqual(self.marker(record)["collected_status"], "failed")

    def test_real_timeout_is_collected_as_failed(self) -> None:
        executable = self.install_mode_provider("codex", "hang")
        timeouts = {"review": 1200, "implementer": 1, "plan": 1200}
        with (
            patch_engine("CODEX_EXECUTABLE", str(executable)),
            patch_engine("PROFILE_TIMEOUT_SECONDS", timeouts),
        ):
            self.launch_direct(provider="codex")
            engine = self.ready_engine()
            record = self.execution_records()[-1]
            directory = self.attempt_dir(record)
            pgid = int((directory / "pid").read_text().splitlines()[1])
            self.addCleanup(kill_group, pgid)
            identity = json.loads(wait_path(directory / "identity.json").read_text())
            self.assertEqual(identity["pgid"], pgid)
            completion = wait_path(directory / "completion.json", timeout=10)
            outcome = VERBS_LAUNCH_COLLECT.launch_collect(
                engine, str(record["execution"])
            )
        self.assertEqual(outcome.state, "failed")
        value = json.loads(completion.read_text())
        self.assertEqual((value["timed_out"], value["error"]), (True, None))


if __name__ == "__main__":
    unittest.main()
