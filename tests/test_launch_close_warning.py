"""Typed-launch coverage for passed-close-impossible append warnings."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tests._cli_loader import package_module, patch_engine
from tests._launch_support import (
    ENGINE,
    LAUNCH_LANE,
    VERBS_LAUNCH,
    VERBS_LAUNCH_COLLECT,
    LaunchLaneSupport,
    digest,
)
from tests._revision9_coord_constants import key

from codex_orchestrator import result_gate

ATTEMPT = package_module("engine._review_attempt")
RUNTIME = package_module("runtime")

NOW = "2026-09-30T12:00:00Z"
WARNING_PREFIX = (
    "forge: journal warning — this append makes a passed close impossible "
    "as recorded: "
)
GATE_ISSUES = (
    "execution codex-implementer-01/execution-01 has no terminal execution_result",
    "run closed as passed without a passing 'gate-1' verification after the "
    "last mutating execution",
    "run closed as passed without a passing 'gate-2' verification after the "
    "last mutating execution",
    "run closed as passed without a passing 'gate-3: review-final verdict' "
    "verification after the last mutating execution",
)


class LaunchCloseWarningTests(LaunchLaneSupport, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.configure_route("implementer", "codex")
        self.open_run_and_task()
        self.engine = self.ready_engine(open_task=False)

    @property
    def builders(self) -> Any:
        return RUNTIME._coordination_modules()[1]

    @property
    def journal(self) -> Any:
        return RUNTIME._coordination_modules()[2]

    def _binding(
        self, chain_id: str, seed: str, *, reviewed: bool = False
    ) -> dict[str, object]:
        review = (
            {
                "verdict": "PASS",
                "iteration": 1,
                "reviewer_role": "review-final",
                "package_digest": key(f"{seed}-review-package"),
            }
            if reviewed
            else None
        )
        preimage = {
            "schema": self.journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain_id,
                "event_digest": key(f"{seed}-event"),
            },
            "candidate": {
                "kind": "staged-diff-sha256",
                "value": key("launch-warning-candidate"),
            },
            "review": review,
        }
        return {
            **preimage,
            "binding_id": self.journal._sha256(
                self.journal._canonical_json_bytes(preimage)
            ),
        }

    def _add_landed_gate_set(self, *, land: bool = True) -> str:
        chain_id = "c-2026-09-30T120000Z-71a7"
        criteria = (
            "gate-1: gate-1",
            "gate-2: stack validation",
            self.journal.GATE_3_CRITERION,
        )
        first_binding = ""
        with self.api_environment():
            for index, criterion in enumerate(criteria, start=1):
                binding = self._binding(
                    chain_id,
                    f"gate-{index}",
                    reviewed=criterion == self.journal.GATE_3_CRITERION,
                )
                if index == 1:
                    first_binding = str(binding["binding_id"])
                with mock.patch.object(
                    self.builders, "resolve_binding", return_value=binding
                ):
                    self.builders.verification_add(
                        self.repo,
                        self.run_id,
                        idempotency_key=key(f"warning-gate-{index}"),
                        task=self.task_id,
                        criterion=criterion,
                        method="unittest",
                        check="python3 -m unittest synthetic",
                        result="passed",
                        observation="synthetic bound gate passed",
                        evidence=[],
                        binding_chain=chain_id,
                        binding_id=str(binding["binding_id"]),
                    )
            if land:
                landing = self._binding(chain_id, "landing")
                with mock.patch.object(
                    self.builders, "resolve_binding", return_value=landing
                ):
                    self.builders.decision_add(
                        self.repo,
                        self.run_id,
                        idempotency_key=key("warning-landing"),
                        task=self.task_id,
                        resolution="The synthetic candidate landed",
                        finding=None,
                        outcome="chain-landing",
                        risk=None,
                        basis=[],
                        binding_chain=chain_id,
                        binding_id=str(landing["binding_id"]),
                    )
        return first_binding

    def _publish_completion(
        self,
        record: dict[str, object],
        *,
        error: str | None = None,
    ) -> None:
        paths = self.paths(record)
        marker = self.marker(record)
        identity = self.live_identity(
            record,
            wrapper_pid=4100,
            reviewer_pid=4101,
            attempt=str(marker["attempt"]),
            starttimes=(7, 8),
        )
        self.write_private_json(paths.leaf("identity.json"), identity)
        handoff = b"typed warning handoff\n"
        paths.leaf("handoff.md").write_bytes(handoff)
        paths.leaf("handoff.md").chmod(0o600)
        completion = ATTEMPT.make_terminal_completion(
            LAUNCH_LANE.marker_binding(marker),
            error or "cancelled",
            identity=identity,
            completed_at=NOW,
            overrides={
                "error": error,
                "returncode": None if error is not None else 0,
                "timed_out": False,
                "observed_model": None,
                "verdict_digest": digest(handoff),
                "verdict_size": len(handoff),
            },
        )
        self.write_private_json(paths.leaf("completion.json"), completion)

    def _seed_silently(self) -> dict[str, object]:
        with contextlib.redirect_stderr(io.StringIO()):
            self.seed_launch()
        return self.execution_records()[-1]

    def _collect(self, record: dict[str, object]) -> Any:
        return VERBS_LAUNCH_COLLECT.launch_collect(
            self.engine, str(record["execution"])
        )

    def _run_snapshot(self, label: str) -> Path:
        source = self.run_dir(self.repo, self.run_id)
        snapshot = self.scratch / f"run-snapshot-{label}"
        shutil.copytree(source, snapshot)
        return snapshot

    def _restore_run(self, snapshot: Path) -> None:
        target = self.run_dir(self.repo, self.run_id)
        shutil.rmtree(target)
        shutil.copytree(snapshot, target)

    def _append_then_repeat(self, reported_repeat: bool):
        append_result = LAUNCH_LANE.append_execution_result

        def crash_window(*args: object, **kwargs: object):
            _record, first_repeat = append_result(*args, **kwargs)
            self.assertFalse(first_repeat)
            record, actual_repeat = append_result(*args, **kwargs)
            self.assertTrue(actual_repeat)
            return record, reported_repeat

        return crash_window

    @staticmethod
    def _envelope_bytes(outcome: Any) -> bytes:
        return json.dumps(
            outcome.envelope(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @staticmethod
    def _result_warning(binding_id: str) -> str:
        return (
            f"{WARNING_PREFIX}binding {binding_id!r} precedes the last mutating "
            "execution for task 'task-01'"
        )

    def test_launch_warns_and_control_disable_preserves_the_envelope(self) -> None:
        self._add_landed_gate_set()
        snapshot = self._run_snapshot("launch")
        expected = "".join(f"{WARNING_PREFIX}{issue}\n" for issue in GATE_ISSUES)
        observed: dict[str, object] = {}

        def assertion() -> None:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                outcome = self.seed_launch()
            observed["envelope"] = self._envelope_bytes(outcome)
            observed["exit"] = outcome.exit_code
            observed["stderr"] = stderr.getvalue()
            self.assertEqual(stderr.getvalue(), expected)

        assertion()
        enabled_envelope = observed["envelope"]
        enabled_exit = observed["exit"]
        self._restore_run(snapshot)
        with mock.patch.object(
            result_gate,
            "RESULT_GATE_CONTROLS",
            result_gate.RESULT_GATE_CONTROLS - {"close-projection-warning"},
        ):
            with self.assertRaises(AssertionError):
                assertion()
        self.assertEqual(observed["stderr"], "")
        self.assertEqual(observed["envelope"], enabled_envelope)
        self.assertEqual(observed["exit"], enabled_exit)

    def test_launch_spawns_and_publishes_pid_before_warning_lock(self) -> None:
        self._add_landed_gate_set()
        holder: subprocess.Popen[str] | None = None
        events: list[str] = []
        real_owner_record = VERBS_LAUNCH._owner_record
        real_write_pid = LAUNCH_LANE.write_pid
        real_take_shared_lock = result_gate.close_preflight._take_shared_lock

        def owner_with_foreign_lock(*args: object, **kwargs: object) -> Any:
            nonlocal holder
            owner = real_owner_record(*args, **kwargs)
            lock_path = owner.facts.run_dir / self.journal.BATCH_LOCK_NAME
            holder = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import fcntl,os,sys,time;"
                        "fd=os.open(sys.argv[1],os.O_RDONLY);"
                        "fcntl.flock(fd,fcntl.LOCK_EX);"
                        "print('locked',flush=True);time.sleep(60)"
                    ),
                    str(lock_path),
                ],
                stdout=subprocess.PIPE,
                text=True,
            )
            assert holder.stdout is not None
            self.assertEqual(holder.stdout.readline(), "locked\n")
            return owner

        def capture_spawn(*_args: object, **_kwargs: object) -> mock.Mock:
            events.append("spawn")
            return mock.Mock(pid=424_242)

        def publish_pid(*args: object, **kwargs: object) -> None:
            real_write_pid(*args, **kwargs)
            events.append("pid-published")

        def attempt_warning_lock(*args: object, **kwargs: object) -> None:
            events.append("warning-lock-attempt")
            real_take_shared_lock(*args, **kwargs)

        stderr = io.StringIO()
        started = time.monotonic()
        try:
            with (
                mock.patch.object(
                    VERBS_LAUNCH, "_owner_record", side_effect=owner_with_foreign_lock
                ),
                patch_engine("spawn_wrapper", side_effect=capture_spawn),
                mock.patch.object(LAUNCH_LANE, "write_pid", side_effect=publish_pid),
                mock.patch.object(
                    result_gate.close_preflight,
                    "_take_shared_lock",
                    side_effect=attempt_warning_lock,
                ),
                mock.patch.object(
                    result_gate.close_law, "CHAIN_LOCK_WAIT_SECONDS", 0.05
                ),
                contextlib.redirect_stderr(stderr),
            ):
                outcome = self.launch_direct(engine=self.engine)
            elapsed = time.monotonic() - started
            self.assertEqual(events, ["spawn", "pid-published", "warning-lock-attempt"])
            self.assertEqual((outcome.exit_code, stderr.getvalue()), (0, ""))
            self.assertLess(elapsed, 30, "launch exceeded the hang guard")
            assert holder is not None
            self.assertIsNone(holder.poll())
        finally:
            if holder is not None and holder.poll() is None:
                holder.terminate()
                holder.wait(timeout=5)
            if holder is not None and holder.stdout is not None:
                holder.stdout.close()

    def test_collect_warns_after_append_and_repeat_is_silent(self) -> None:
        record = self._seed_silently()
        first_binding = self._add_landed_gate_set(land=False)
        self._publish_completion(record)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            outcome = self._collect(record)
        self.assertEqual((outcome.exit_code, outcome.state), (0, "complete"))
        self.assertEqual(
            stderr.getvalue(), self._result_warning(first_binding) + "\n"
        )
        records = self.records()
        execution_line = next(
            index
            for index, item in enumerate(records)
            if item.get("type") == "execution"
            and item.get("execution") == record["execution"]
        )
        gate_line = next(
            index
            for index, item in enumerate(records)
            if item.get("criterion") == "gate-1: gate-1"
        )
        result_line = next(
            index
            for index, item in enumerate(records)
            if item.get("type") == "execution_result"
            and item.get("execution") == record["execution"]
        )
        self.assertLess(execution_line, gate_line)
        self.assertLess(gate_line, result_line)

        repeated_stderr = io.StringIO()
        with (
            mock.patch.object(
                result_gate,
                "record_warnings",
                side_effect=AssertionError("repeat must not inspect warnings"),
            ) as repeated_spy,
            contextlib.redirect_stderr(repeated_stderr),
        ):
            repeated = self._collect(record)
        self.assertEqual((repeated.exit_code, repeated.state), (0, "complete"))
        self.assertEqual(repeated_stderr.getvalue(), "")
        repeated_spy.assert_not_called()

    def test_collect_crash_window_repeat_skips_result_warning(self) -> None:
        record = self._seed_silently()
        self._publish_completion(record)
        snapshot = self._run_snapshot("collect-crash-window")

        def assert_guard(reported_repeat: bool) -> None:
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    LAUNCH_LANE,
                    "append_execution_result",
                    side_effect=self._append_then_repeat(reported_repeat),
                ),
                mock.patch.object(
                    VERBS_LAUNCH_COLLECT,
                    "_print_record_warnings",
                    side_effect=AssertionError("repeat must not warn"),
                ) as warning_spy,
                contextlib.redirect_stderr(stderr),
            ):
                outcome = self._collect(record)
            self.assertEqual((outcome.exit_code, outcome.state), (0, "complete"))
            self.assertEqual(stderr.getvalue(), "")
            warning_spy.assert_not_called()

        assert_guard(True)
        self._restore_run(snapshot)
        with self.assertRaises(AssertionError):
            assert_guard(False)

    def test_spawn_failure_crash_window_repeat_skips_result_warning(self) -> None:
        snapshot = self._run_snapshot("spawn-failure-crash-window")

        def assert_guard(reported_repeat: bool) -> None:
            def reject_result_warning(
                _repository: Path, _run_id: str, record: dict[str, object]
            ) -> None:
                if record.get("type") == "execution_result":
                    raise AssertionError("repeated spawn failure must not warn")

            with (
                patch_engine(
                    "spawn_wrapper", side_effect=OSError("fixture spawn failure")
                ),
                mock.patch.object(
                    LAUNCH_LANE,
                    "append_execution_result",
                    side_effect=self._append_then_repeat(reported_repeat),
                ),
                mock.patch.object(
                    VERBS_LAUNCH,
                    "_print_record_warnings",
                    side_effect=reject_result_warning,
                ) as warning_spy,
            ):
                outcome = self.launch_direct(engine=self.engine)
            self.assertEqual((outcome.exit_code, outcome.state), (0, "failed"))
            warning_spy.assert_called_once()

        assert_guard(True)
        self._restore_run(snapshot)
        with self.assertRaises(AssertionError):
            assert_guard(False)

    def test_cancel_warns_once_through_collect(self) -> None:
        record = self._seed_silently()
        first_binding = self._add_landed_gate_set(land=False)
        self.write_identity(self.live_identity(record), record)

        stderr = io.StringIO()
        with (
            patch_engine(
                "prove_group_ownership",
                return_value=ATTEMPT.GroupProof("group-empty", 77),
            ),
            contextlib.redirect_stderr(stderr),
        ):
            outcome = VERBS_LAUNCH_COLLECT.launch_cancel(
                self.engine, str(record["execution"])
            )
        self.assertEqual((outcome.exit_code, outcome.state), (0, "failed"))
        self.assertEqual(
            stderr.getvalue(), self._result_warning(first_binding) + "\n"
        )

    def test_spawn_failure_prints_its_result_warning_exactly_once(self) -> None:
        first_binding = self._add_landed_gate_set()
        result_warning = self._result_warning(first_binding)
        stderr = io.StringIO()
        with (
            patch_engine(
                "spawn_wrapper", side_effect=OSError("fixture spawn failure")
            ),
            contextlib.redirect_stderr(stderr),
            self.assertRaises(ENGINE.Refusal),
        ):
            self.launch_direct()
        expected = (
            "".join(f"{WARNING_PREFIX}{issue}\n" for issue in GATE_ISSUES)
            + result_warning
            + "\n"
        )
        self.assertEqual(stderr.getvalue(), expected)
        self.assertEqual(stderr.getvalue().count(result_warning), 1)
        results = [
            item
            for item in self.records()
            if item.get("type") == "execution_result"
        ]
        self.assertEqual(len(results), 1)

    def test_internal_warning_error_leaves_exit_and_envelope_unchanged(self) -> None:
        snapshot = self._run_snapshot("internal-error")
        error_stderr = io.StringIO()
        with (
            mock.patch.object(
                result_gate,
                "record_warnings",
                side_effect=RuntimeError("synthetic warning failure"),
            ),
            contextlib.redirect_stderr(error_stderr),
        ):
            error_outcome = self.seed_launch()
        self._restore_run(snapshot)
        baseline_stderr = io.StringIO()
        with (
            mock.patch.object(result_gate, "record_warnings", return_value=[]),
            contextlib.redirect_stderr(baseline_stderr),
        ):
            baseline_outcome = self.seed_launch()
        self.assertEqual(error_stderr.getvalue(), "")
        self.assertEqual(baseline_stderr.getvalue(), "")
        self.assertEqual(error_outcome.exit_code, baseline_outcome.exit_code)
        self.assertEqual(
            self._envelope_bytes(error_outcome),
            self._envelope_bytes(baseline_outcome),
        )

    def test_record_warnings_rejects_absent_and_duplicate_records(self) -> None:
        record = self._seed_silently()
        stable_read = result_gate.journal._stable_journal_read
        absent = {
            "type": "execution",
            "execution": "execution-99",
            "agent": "codex-implementer-99",
        }
        with mock.patch.object(
            result_gate.journal,
            "_stable_journal_read",
            wraps=stable_read,
        ) as read_spy:
            self.assertEqual(
                result_gate.record_warnings(self.repo, self.run_id, absent), []
            )
        read_spy.assert_called_once()

        journal_path = self.run_dir(self.repo, self.run_id) / "journal.jsonl"
        duplicate = dict(record)
        duplicate.pop("_line", None)
        raw = journal_path.read_bytes() + self.journal._journal_line(duplicate)
        with mock.patch.object(
            result_gate.journal,
            "_stable_journal_read",
            return_value=raw,
        ) as read_spy:
            self.assertEqual(
                result_gate.record_warnings(self.repo, self.run_id, record), []
            )
        read_spy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
