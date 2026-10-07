"""Focused coverage for collecting typed implementer and plan launches."""

from __future__ import annotations

import errno
import io
import json
import os
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace
from typing import Any
from unittest import mock

from tests._cli_loader import package_module
from tests._launch_support import (
    ENGINE,
    LAUNCH_LANE,
    MARKER_BINDING_CHANGES,
    VERBS_LAUNCH_COLLECT,
    LaunchLaneSupport,
    digest,
)

from codex_orchestrator import journal

ATTEMPT = package_module("engine._review_attempt")
REVIEW_LAUNCH = package_module("engine._review_launch")

NOW = "2026-09-28T12:00:00Z"


class LaunchCollectTests(LaunchLaneSupport, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.configure_route("implementer", "codex")
        self.configure_route("plan", "claude")
        self.open_run_and_task()
        self.engine = self.ready_engine(open_task=False)

    def seed(self, role: str = "implementer") -> dict[str, object]:
        self.seed_launch(role=role)
        return self.execution_records()[-1]

    def publish(
        self,
        record: dict[str, object],
        *,
        error: str | None = None,
        timed_out: bool = False,
        handoff: bytes | None = b"typed handoff\n",
        observed_model: str | None = None,
        mutate: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        paths = self.paths(record)
        marker = self.marker(record)
        binding = LAUNCH_LANE.marker_binding(marker)
        identity = self.live_identity(
            record,
            wrapper_pid=4100,
            reviewer_pid=4101,
            attempt=str(marker["attempt"]),
            starttimes=(7, 8),
        )
        self.write_private_json(paths.leaf("identity.json"), identity)
        if handoff is not None:
            paths.leaf("handoff.md").write_bytes(handoff)
            paths.leaf("handoff.md").chmod(0o600)
        completion = ATTEMPT.make_terminal_completion(
            binding,
            error or "cancelled",
            identity=identity,
            completed_at=NOW,
            overrides={
                "error": error,
                "returncode": None if error is not None or timed_out else 0,
                "timed_out": timed_out,
                "observed_model": observed_model,
                "verdict_digest": digest(handoff) if handoff else None,
                "verdict_size": len(handoff or b""),
            },
        )
        completion.update(mutate or {})
        self.write_private_json(paths.leaf("completion.json"), completion)
        return completion

    def collect(self, record: dict[str, object]) -> Any:
        return VERBS_LAUNCH_COLLECT.launch_collect(
            self.engine, str(record["execution"])
        )

    def result(self, record: dict[str, object]) -> dict[str, object]:
        return next(
            row
            for row in reversed(self.records())
            if row.get("kind") == "execution_finished"
            and row.get("execution_id") == record["execution"]
        )

    def assert_refusal(
        self,
        record: dict[str, object],
        reason: Any,
        fragment: str,
    ) -> None:
        before = (self.run_dir(self.repo, self.run_id) / "journal.jsonl").read_bytes()
        with self.assertRaises(ENGINE.Refusal) as caught:
            self.collect(record)
        self.assertEqual(caught.exception.reason_code, reason)
        self.assertIn(fragment, caught.exception.message)
        self.assertEqual(
            before,
            (self.run_dir(self.repo, self.run_id) / "journal.jsonl").read_bytes(),
        )

    def test_repeat_collect_appends_no_second_finish_and_logs_actual_route(self) -> None:
        record = self.seed()
        handoff = b"complete typed handoff\n"
        self.publish(record, handoff=handoff)

        outcome = self.collect(record)
        result = self.result(record)
        marker = self.marker(record)
        self.assertEqual((outcome.ok, outcome.state), (True, "complete"))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["files_changed"], [])
        self.assertEqual(result["caveats"], [])
        self.assertEqual(
            result["summary"],
            "launch collect: complete; returncode 0; error none; timed_out false; "
            f"handoff {len(handoff)} bytes; observed_model none",
        )
        self.assertEqual(marker["collected_status"], "complete")
        self.assertIsInstance(marker["collected_at"], str)
        self.assertEqual(result["started_at"], marker["requested_at"])
        journal_before = (
            self.run_dir(self.repo, self.run_id) / "journal.jsonl"
        ).read_bytes().count(b'"kind":"execution_finished"')
        marker_before = self.paths(record).leaf("launch.json").read_bytes()
        repeated = self.collect(record)
        self.assertEqual(repeated.state, "complete")
        self.assertEqual(
            journal_before,
            (self.run_dir(self.repo, self.run_id) / "journal.jsonl").read_bytes().count(
                b'"kind":"execution_finished"'
            ),
        )
        self.assertEqual(marker_before, self.paths(record).leaf("launch.json").read_bytes())
        for field in ("provider", "model", "effort", "sandbox", "route_source", "route_sha256"):
            self.assertEqual(result[field], marker[field])

    def test_start_append_failure_reports_but_launches(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch.object(journal, "_write_line", side_effect=journal.CoordinationRefusal(
                journal.APPEND_IO_ERROR
            )),
            redirect_stderr(stderr),
        ):
            outcome = self.seed_launch()
        self.assertTrue(outcome.ok)
        self.assertEqual(stderr.getvalue(), journal.APPEND_IO_ERROR + "\n")
        path = (self.run_dir(self.repo, self.run_id)
                / "codex-implementer-01/execution-01/launch.json")
        self.assertTrue(path.exists())
        self.assertTrue((path.parent / "pid").exists())
        self.assertFalse(self.execution_records())

    def test_finish_append_failure_does_not_make_repeat_collect_append(self) -> None:
        record = self.seed()
        self.publish(record)
        stderr = io.StringIO()
        with (
            mock.patch.object(journal, "_write_line", side_effect=journal.CoordinationRefusal(
                journal.APPEND_IO_ERROR
            )),
            redirect_stderr(stderr),
        ):
            outcome = self.collect(record)
        self.assertEqual(outcome.state, "complete")
        self.assertEqual(stderr.getvalue(), journal.APPEND_IO_ERROR + "\n")
        self.assertEqual(self.marker(record)["collected_status"], "complete")
        self.assertFalse(any(item.get("kind") == "execution_finished" for item in self.records()))
        self.assertEqual(self.collect(record).state, "complete")
        self.assertFalse(any(item.get("kind") == "execution_finished" for item in self.records()))

    def test_completion_repairs_marker_without_journal_result_gate(self) -> None:
        record = self.seed()
        handoff = b"crash repair handoff\n"
        self.paths(record).leaf("handoff.md").write_bytes(handoff)
        self.paths(record).leaf("handoff.md").chmod(0o600)
        self.publish(record, handoff=handoff)
        journal.append_run_record(self.repo, self.run_id, {
            "kind": "execution_finished", "run_id": self.run_id,
            "execution_id": record["execution"], "agent": record["agent"],
            "status": "complete", "caveats": [],
            "handoff": self.paths(record).reference("handoff.md"),
        })
        before = sum(item.get("kind") == "execution_finished" for item in self.records())
        self.assertIsNone(self.marker(record)["collected_at"])
        outcome = self.collect(record)
        self.assertEqual(outcome.state, "complete")
        self.assertEqual(
            sum(item.get("kind") == "execution_finished" for item in self.records()),
            before + 1,
        )
        self.assertEqual(self.marker(record)["collected_status"], "complete")

    def test_journal_only_execution_does_not_supply_a_collect_marker(self) -> None:
        run_dir = self.run_dir(self.repo, self.run_id)
        for name in ("prompt.md", "events.jsonl", "handoff.md"):
            (run_dir / name).write_text("prose evidence\n", encoding="utf-8")
        record = {"kind": "execution_started", "run_id": self.run_id,
                  "execution_id": "execution-01", "execution": "execution-01",
                  "agent": "codex-implementer-01", "task": self.task_id}
        journal.append_run_record(self.repo, self.run_id, record)
        self.assert_refusal(
            record,
            ENGINE.V2ReasonCode.STATE_PRECONDITION,
            "forge: launch collect refused — execution execution-01 does not exist",
        )

    def test_marker_binding_covers_every_owner_record_and_digest_field(self) -> None:
        record = self.seed()
        marker_path = self.paths(record).leaf("launch.json")
        baseline = self.marker(record)
        for field, value in MARKER_BINDING_CHANGES.items():
            with self.subTest(field=field):
                LAUNCH_LANE.write_marker(marker_path, dict(baseline, **{field: value}))
                self.assert_refusal(
                    record, ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
                    f"launch marker does not bind execution execution-01: {field}",
                )
                LAUNCH_LANE.write_marker(marker_path, baseline)
        prompt = self.paths(record).leaf("prompt.md")
        original_prompt = prompt.read_bytes()
        prompt.write_bytes(original_prompt + b"mutated")
        self.assert_refusal(
            record, ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
            "launch marker does not bind execution execution-01: prompt_digest",
        )
        prompt.write_bytes(original_prompt)
        self._check_wrapper_config_binding(record)

    def _check_wrapper_config_binding(self, record: dict[str, object]) -> None:
        path = self.paths(record).leaf(LAUNCH_LANE.WRAPPER_CONFIG_NAME)
        baseline = json.loads(path.read_text(encoding="utf-8"))
        for field, value in MARKER_BINDING_CHANGES.items():
            with self.subTest(field=field):
                self.write_private_json(path, dict(baseline, **{field: value}))
                self.assert_refusal(
                    record, ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
                    f"launch marker does not bind execution execution-01: {field}",
                )
        self.write_private_json(path, baseline)
        path.unlink()
        self.assert_refusal(
            record, ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
            "launch marker does not bind execution execution-01: wrapper_config",
        )
        path.symlink_to(self.paths(record).leaf("launch.json"))
        self.assert_refusal(
            record, ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
            "launch marker does not bind execution execution-01: wrapper_config",
        )
        path.unlink()
        self.write_private_json(path, baseline)
        with (
            mock.patch.object(LAUNCH_LANE, "bind_wrapper_config", return_value=None),
            self.assertRaises(AssertionError),
        ):
            self.write_private_json(path, dict(baseline, task="task-99"))
            self.assert_refusal(
                record, ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
                "launch marker does not bind execution execution-01: task",
            )

    def test_collect_ignores_missing_torn_and_duplicate_journal_starts(self) -> None:
        record = self.seed()
        self.publish(record)
        path = self.run_dir(self.repo, self.run_id) / "journal.jsonl"
        start = next(item for item in self.records() if item.get("kind") == "execution_started")
        line = (json.dumps(start) + "\n").encode("utf-8")
        path.write_bytes(line + line + b'{"kind":"execution_started"\n')
        with mock.patch.object(journal, "read_journal", side_effect=AssertionError):
            self.assertEqual(self.collect(record).state, "complete")
        self.assertEqual(self.marker(record)["collected_status"], "complete")

    def test_collect_recreates_missing_journal_from_marker(self) -> None:
        record = self.seed()
        self.publish(record)
        path = self.run_dir(self.repo, self.run_id) / "journal.jsonl"
        path.unlink()
        self.assertEqual(self.collect(record).state, "complete")
        self.assertEqual(self.marker(record)["collected_status"], "complete")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["kind"],
                         "execution_finished")

    def test_completion_binding_covers_request_identity_and_null_returncode(self) -> None:
        record = self.seed()
        completion = self.publish(record)
        path = self.paths(record).leaf("completion.json")
        changes = {
            "provider": "claude",
            "route_source": "plugin-default",
            "route_sha256": "f" * 64,
            "sandbox": "read-only",
            "argv_digest": "e" * 64,
            "prompt_digest": "d" * 64,
            "wrapper_pid": 5100,
            "pgid": 5100,
            "reviewer_pid": 5101,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                self.write_private_json(path, dict(completion, **{field: value}))
                origin = "launch marker" if field in {
                    "provider", "route_source", "route_sha256", "sandbox",
                    "argv_digest", "prompt_digest",
                } else "completion"
                self.assert_refusal(
                    record,
                    ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
                    f"{origin} does not bind execution execution-01: {field}",
                )
        foreign = dict(completion, attempt="attempt-fedcba9876543210")
        self.write_private_json(path, foreign)
        self.assert_refusal(
            record,
            ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
            "launch marker does not bind execution execution-01: attempt",
        )
        invalid = dict(completion, returncode=None, error=None, timed_out=False)
        self.write_private_json(path, invalid)
        self.assert_refusal(
            record,
            ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
            "attempt record is invalid for execution-01: null returncode",
        )
        self.write_private_json(path, dict(completion, wrapper_pid=5100))
        with (
            mock.patch.object(ATTEMPT, "validate_completion_binding", return_value=None),
            self.assertRaises(AssertionError),
        ):
            self.assert_refusal(
                record,
                ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
                "completion does not bind execution execution-01: wrapper_pid",
            )

    def test_files_changed_are_sorted_and_plan_changes_add_a_caveat(self) -> None:
        record = self.seed(role="plan")
        tracked = self.linked_worktree / "src/example.py"
        tracked.write_text("VALUE = 2\n", encoding="utf-8")
        (self.linked_worktree / "notes.txt").write_text("new\n", encoding="utf-8")
        self.publish(record, observed_model="claude-fixture")
        outcome = self.collect(record)
        result = self.result(record)
        self.assertEqual(outcome.state, "complete")
        self.assertEqual(result["files_changed"], ["notes.txt", "src/example.py"])
        self.assertEqual(result["caveats"], ["plan execution changed files"])
        self.assertIn("observed_model claude-fixture", str(result["summary"]))

    def test_non_utf8_worktree_path_refusal_has_remediation_and_disable_leg(self) -> None:
        record = self.seed()
        self.publish(record)
        raw_path = os.fsencode(self.linked_worktree) + b"/invalid-\xff-name"
        try:
            descriptor = os.open(
                raw_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except OSError as exc:
            if exc.errno == errno.EILSEQ:
                self.skipTest("filesystem rejects non-UTF-8 path components")
            raise
        os.close(descriptor)
        expected = (
            "forge: launch collect refused — worktree paths are not UTF-8 for "
            "execution-01; restore changed tracked paths or rename/remove untracked "
            "paths, then retry launch collect"
        )

        def assertion() -> None:
            self.assert_refusal(
                record,
                ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
                expected,
            )

        assertion()
        with (
            mock.patch.object(
                LAUNCH_LANE,
                "_decode_worktree_path",
                side_effect=lambda value: value.decode("utf-8", "replace"),
            ),
            self.assertRaises(AssertionError),
        ):
            assertion()

    def test_worktree_path_budget_is_cumulative_and_has_a_disable_leg(self) -> None:
        record = self.seed()
        self.publish(record)
        first = b"a" * 600_000 + b"\0"
        second = b"b" * 600_000 + b"\0"
        expected = (
            "forge: launch collect refused — worktree path list exceeds 1 MiB for "
            "execution-01; reduce changed or untracked paths, then retry launch collect"
        )

        def assertion() -> None:
            with mock.patch.object(
                LAUNCH_LANE,
                "git_bytes",
                side_effect=(first, second),
            ):
                self.assert_refusal(
                    record,
                    ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
                    expected,
                )

        assertion()
        with (
            mock.patch.object(
                LAUNCH_LANE,
                "GIT_LIMIT_BYTES",
                len(first) + len(second),
            ),
            self.assertRaises(AssertionError),
        ):
            assertion()

    def test_git_output_limit_classification_is_load_bearing(self) -> None:
        result = SimpleNamespace(
            returncode=-15,
            timed_out=False,
            output_limit=True,
            output=b"x" * LAUNCH_LANE.GIT_LIMIT_BYTES,
        )
        expected = (
            "forge: launch collect refused — worktree path list exceeds 1 MiB for "
            "execution-01; reduce changed or untracked paths, then retry launch collect"
        )
        original = LAUNCH_LANE.git_bytes

        def assertion() -> None:
            with (
                mock.patch.object(
                    LAUNCH_LANE.runtime,
                    "run_bounded",
                    return_value=result,
                ) as bounded,
                self.assertRaises(ENGINE.Refusal) as caught,
            ):
                LAUNCH_LANE.worktree_changes(
                    self.linked_worktree,
                    self.head,
                    "execution-01",
                )
            self.assertEqual(caught.exception.message, expected)
            self.assertEqual(
                bounded.call_args.kwargs["cap"],
                LAUNCH_LANE.GIT_LIMIT_BYTES,
            )

        def legacy_git_bytes(*args: Any, **kwargs: Any) -> bytes:
            try:
                return original(*args, **kwargs)
            except LAUNCH_LANE.GitOutputLimitError as exc:
                raise OSError("bounded Git read failed") from exc

        assertion()
        with (
            mock.patch.object(
                LAUNCH_LANE,
                "git_bytes",
                side_effect=legacy_git_bytes,
            ),
            self.assertRaises(AssertionError),
        ):
            assertion()

    def assert_failed_mapping(
        self,
        *,
        error: str | None,
        timed_out: bool = False,
        handoff: bytes | None = None,
        unsafe_handoff: bool = False,
    ) -> dict[str, object]:
        record = self.seed()
        self.publish(
            record,
            error=error,
            timed_out=timed_out,
            handoff=handoff,
        )
        if unsafe_handoff:
            self.paths(record).leaf("handoff.md").chmod(0o644)
        outcome = self.collect(record)
        result = self.result(record)
        self.assertEqual((outcome.ok, outcome.state), (True, "failed"))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.marker(record)["collected_status"], "failed")
        if error is not None:
            self.assertIn(error, result["caveats"])
        return result


def _failed_test(
    error: str | None,
    *,
    timed_out: bool = False,
    handoff: bytes | None = None,
    unsafe_handoff: bool = False,
    summary: str | None = None,
):
    def test(self: LaunchCollectTests) -> None:
        result = self.assert_failed_mapping(
            error=error,
            timed_out=timed_out,
            handoff=handoff,
            unsafe_handoff=unsafe_handoff,
        )
        if summary is not None:
            self.assertEqual(result["summary"], summary)

    return test


for _name, _arguments in {
    "events_cap": {"error": "events cap"},
    "stderr_cap": {"error": "stderr cap"},
    "bad_line": {"error": "bad line 3"},
    "provider_exit": {"error": "provider exit 9"},
    "claude_result_error": {"error": "claude result error"},
    "claude_init_mismatch": {
        "error": "claude init mismatch",
        "summary": "launch collect: failed; returncode none; error claude init "
        "mismatch; timed_out false; handoff 0 bytes; observed_model none",
    },
    "redaction_damage": {"error": "redaction damaged HOME"},
    "wrapper_failure": {"error": "wrapper failure"},
    "verdict_missing": {"error": "verdict missing"},
    "verdict_empty": {"error": "verdict empty", "handoff": b""},
    "verdict_cap": {"error": "verdict cap"},
    "verdict_invalid": {"error": "verdict invalid"},
    "launch_failed": {"error": "launch-failed: spawn error"},
    "abandoned": {"error": "abandoned"},
    "cancelled": {"error": "cancelled"},
    "wrapper_lost": {"error": "wrapper-lost"},
    "timed_out": {"error": None, "timed_out": True},
    "missing_capture": {"error": None, "handoff": None},
    "empty_capture": {"error": None, "handoff": b""},
    "oversize_capture": {"error": None, "handoff": b"x" * 65_537},
    "unsafe_capture": {
        "error": None,
        "handoff": b"unsafe\n",
        "unsafe_handoff": True,
    },
    "unbound_capture": {"error": None, "handoff": b"bound first\n"},
}.items():
    method = _failed_test(**_arguments)
    if _name == "unbound_capture":
        def method(self: LaunchCollectTests) -> None:
            record = self.seed()
            self.publish(record, handoff=b"original\n")
            self.paths(record).leaf("handoff.md").write_bytes(b"changed\n")
            self.paths(record).leaf("handoff.md").chmod(0o600)
            outcome = self.collect(record)
            self.assertEqual(outcome.state, "failed")
            self.assertIn("handoff does not bind completion", self.result(record)["caveats"])
    setattr(LaunchCollectTests, f"test_failed_{_name}", method)


def _not_logged_in_test(provider: str, role: str):
    def test(self: LaunchCollectTests) -> None:
        record = self.seed(role=role)
        self.publish(record, error="not-logged-in", handoff=None)
        outcome = self.collect(record)
        expected = (
            REVIEW_LAUNCH.CODEX_NOT_LOGGED_IN
            if provider == "codex"
            else REVIEW_LAUNCH.CLAUDE_NOT_LOGGED_IN
        )
        self.assertEqual(outcome.message, expected)
        self.assertEqual(self.result(record)["caveats"], [expected])

    return test


LaunchCollectTests.test_codex_not_logged_in_literal = _not_logged_in_test(
    "codex", "implementer"
)
LaunchCollectTests.test_claude_not_logged_in_literal = _not_logged_in_test(
    "claude", "plan"
)


def _repeat_failed_collect_test(self: LaunchCollectTests) -> None:
    record = self.seed()
    self.publish(record, error="not-logged-in", handoff=None)
    self.collect(record)
    handoff = self.paths(record).reference("handoff.md")
    expected = REVIEW_LAUNCH.CODEX_NOT_LOGGED_IN

    def assertion() -> None:
        repeated = self.collect(record)
        self.assertEqual(repeated.message, expected)
        self.assertEqual(repeated.state, "failed")
        self.assertNotIn(handoff, repeated.evidence_refs)

    assertion()
    original = VERBS_LAUNCH_COLLECT.Path.is_file

    def disabled_control(path: Any) -> bool:
        return True if path.name == "handoff.md" else original(path)

    with mock.patch.object(VERBS_LAUNCH_COLLECT.Path, "is_file", disabled_control):
        with self.assertRaises(AssertionError):
            assertion()


setattr(
    LaunchCollectTests,
    f"test_{_repeat_failed_collect_test.__name__[1:]}",
    _repeat_failed_collect_test,
)


if __name__ == "__main__":
    unittest.main()
