"""Focused coverage for collecting typed implementer and plan launches."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from typing import Any
from unittest import mock

from tests._cli_loader import package_module
from tests._launch_support import (
    ENGINE,
    LAUNCH_LANE,
    ROOT,
    VERBS_LAUNCH_COLLECT,
    LaunchLaneSupport,
    digest,
)
from tests._revision9_coord_constants import key

ATTEMPT = package_module("engine._review_attempt")
REVIEW_LAUNCH = package_module("engine._review_launch")
RUNTIME = package_module("runtime")

NOW = "2026-09-28T12:00:00Z"


class LaunchCollectTests(LaunchLaneSupport, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.configure_route("implementer", "codex")
        self.configure_route("plan", "claude")
        self.open_run_and_task()
        self.engine = self.ready_engine(open_task=False)

    @property
    def builders(self) -> Any:
        return RUNTIME._coordination_modules()[1]

    @property
    def journal(self) -> Any:
        return RUNTIME._coordination_modules()[2]

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
            if row.get("type") == "execution_result"
            and row.get("execution") == record["execution"]
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

    def test_complete_is_idempotent_and_supplies_task_completion_provenance(self) -> None:
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
        journal_before = (
            self.run_dir(self.repo, self.run_id) / "journal.jsonl"
        ).read_bytes()
        marker_before = self.paths(record).leaf("launch.json").read_bytes()
        repeated = self.collect(record)
        self.assertEqual(repeated.state, "complete")
        self.assertEqual(
            journal_before,
            (self.run_dir(self.repo, self.run_id) / "journal.jsonl").read_bytes(),
        )
        self.assertEqual(marker_before, self.paths(record).leaf("launch.json").read_bytes())
        with self.api_environment():
            finished = self.builders.task_finish(
                self.repo,
                self.run_id,
                idempotency_key=key("typed-launch-task-finish"),
                task=self.task_id,
                status="complete",
            )
        self.assertEqual(finished.records[0]["status"], "complete")

    def test_terminal_result_repairs_only_an_uncollected_marker(self) -> None:
        record = self.seed()
        handoff = b"crash repair handoff\n"
        self.paths(record).leaf("handoff.md").write_bytes(handoff)
        self.paths(record).leaf("handoff.md").chmod(0o600)
        with self.api_environment():
            self.builders.execution_result(
                self.repo,
                self.run_id,
                idempotency_key=key("crash-between-result-and-marker"),
                execution=str(record["execution"]),
                agent=str(record["agent"]),
                task=self.task_id,
                status="complete",
                summary="pre-existing terminal result",
                files_changed=(),
                caveats=(),
                handoff=self.paths(record).reference("handoff.md"),
            )
        journal_before = (
            self.run_dir(self.repo, self.run_id) / "journal.jsonl"
        ).read_bytes()
        self.assertIsNone(self.marker(record)["collected_at"])
        outcome = self.collect(record)
        self.assertEqual(outcome.state, "complete")
        self.assertEqual(
            journal_before,
            (self.run_dir(self.repo, self.run_id) / "journal.jsonl").read_bytes(),
        )
        self.assertEqual(self.marker(record)["collected_status"], "complete")

    def test_prose_execution_is_refused_with_migration_literal(self) -> None:
        run_dir = self.run_dir(self.repo, self.run_id)
        for name in ("prompt.md", "events.jsonl", "handoff.md"):
            (run_dir / name).write_text("prose evidence\n", encoding="utf-8")
        opening = self.records()[0]
        route = opening["route"]["implementer"]
        with self.api_environment():
            outcome = self.builders.execution_start(
                self.repo,
                self.run_id,
                idempotency_key=key("prose-launch"),
                agent="codex-implementer-01",
                task=self.task_id,
                provider=str(route["provider"]),
                role="implementer",
                mode="headless",
                model=str(route["model"]),
                effort=str(route["effort"]),
                worktree=str(self.repo),
                head=self.head,
                prompt="prompt.md",
                handoff="handoff.md",
                event_source="exec",
                events="events.jsonl",
                sandbox="workspace-write",
                route_source=str(route["route_source"]),
                route_sha256=str(route["route_sha256"]),
            )
        record = dict(outcome.records[0])
        self.assert_refusal(
            record,
            ENGINE.V2ReasonCode.STATE_PRECONDITION,
            "forge: launch collect refused — execution execution-01 has no "
            "launch_marker; collect a prose launch by prose",
        )

    def test_marker_binding_covers_every_owner_record_and_digest_field(self) -> None:
        record = self.seed()
        marker_path = self.paths(record).leaf("launch.json")
        baseline = self.marker(record)
        changes = {
            "agent": "codex-implementer-99",
            "task": "task-99",
            "execution": "execution-99",
            "role": "plan",
            "provider": "claude",
            "model": "other-model",
            "effort": "opaque-other",
            "sandbox": "read-only",
            "route_source": "plugin-default",
            "route_sha256": "f" * 64,
            "worktree": str(self.repo),
            "head": "f" * 40,
            "argv_digest": "e" * 64,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                changed = dict(baseline, **{field: value})
                LAUNCH_LANE.write_marker(marker_path, changed)
                self.assert_refusal(
                    record,
                    ENGINE.V2ReasonCode.BINDING_INVALID,
                    f"launch marker does not bind execution execution-01: {field}",
                )
                LAUNCH_LANE.write_marker(marker_path, baseline)
        prompt = self.paths(record).leaf("prompt.md")
        original = prompt.read_bytes()
        prompt.write_bytes(original + b"mutated")
        self.assert_refusal(
            record,
            ENGINE.V2ReasonCode.BINDING_INVALID,
            "launch marker does not bind execution execution-01: prompt_digest",
        )

    def test_record_launch_marker_reference_is_bound_and_control_is_load_bearing(self) -> None:
        record = self.seed()
        original = VERBS_LAUNCH_COLLECT._execution_record

        def mismatched(state: Any, execution: str, verb: str) -> dict[str, object]:
            return dict(original(state, execution, verb), launch_marker="wrong/launch.json")

        with mock.patch.object(
            VERBS_LAUNCH_COLLECT, "_execution_record", side_effect=mismatched
        ):
            self.assert_refusal(
                record,
                ENGINE.V2ReasonCode.BINDING_INVALID,
                "launch marker does not bind execution execution-01: launch_marker",
            )
        marker_path = self.paths(record).leaf("launch.json")
        LAUNCH_LANE.write_marker(marker_path, dict(self.marker(record), provider="claude"))
        with (
            mock.patch.object(LAUNCH_LANE, "bind_marker", return_value=None),
            self.assertRaises(AssertionError),
        ):
            self.assert_refusal(
                record,
                ENGINE.V2ReasonCode.BINDING_INVALID,
                "launch marker does not bind execution execution-01: provider",
            )

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
                self.assert_refusal(
                    record,
                    ENGINE.V2ReasonCode.BINDING_INVALID,
                    f"completion does not bind execution execution-01: {field}",
                )
        foreign = dict(completion, attempt="attempt-fedcba9876543210")
        self.write_private_json(path, foreign)
        self.assert_refusal(
            record,
            ENGINE.V2ReasonCode.BINDING_INVALID,
            "completion does not bind execution execution-01: attempt",
        )
        invalid = dict(completion, returncode=None, error=None, timed_out=False)
        self.write_private_json(path, invalid)
        self.assert_refusal(
            record,
            ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
            "attempt record is invalid for execution-01: null returncode",
        )
        self.write_private_json(path, dict(completion, provider="claude"))
        with (
            mock.patch.object(ATTEMPT, "validate_completion_binding", return_value=None),
            self.assertRaises(AssertionError),
        ):
            self.assert_refusal(
                record,
                ENGINE.V2ReasonCode.BINDING_INVALID,
                "completion does not bind execution execution-01: provider",
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

    def test_launch_record_replays_historically_and_journal_patterns_accepts_it(self) -> None:
        record = self.seed()
        self.publish(record)
        self.collect(record)
        records = tuple(self.records())
        replayed = self.journal._validate_proposed_record(
            record,
            run_id=self.run_id,
            repo_root=self.repo.resolve(),
            scope=("src/**",),
            prior_records=records[:2],
            _historical_replay=self.journal._HISTORICAL_REPLAY,
        )
        self.assertEqual(replayed["launch_marker"], record["launch_marker"])
        process = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/forge/journal-patterns.py"),
                "--repo",
                str(self.repo),
                "--revision",
                self.head,
                str(self.run_dir(self.repo, self.run_id) / "journal.jsonl"),
            ],
            cwd=self.repo,
            env=self.env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        patterns = json.loads(process.stdout)
        self.assertTrue(patterns["available"])
        self.assertEqual(patterns["failure"], "")

    def assert_failed_mapping(
        self,
        *,
        error: str | None,
        timed_out: bool = False,
        handoff: bytes | None = None,
        unsafe_handoff: bool = False,
    ) -> None:
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


def _failed_test(
    error: str | None,
    *,
    timed_out: bool = False,
    handoff: bytes | None = None,
    unsafe_handoff: bool = False,
):
    def test(self: LaunchCollectTests) -> None:
        self.assert_failed_mapping(
            error=error,
            timed_out=timed_out,
            handoff=handoff,
            unsafe_handoff=unsafe_handoff,
        )

    return test


for _name, _arguments in {
    "events_cap": {"error": "events cap"},
    "stderr_cap": {"error": "stderr cap"},
    "bad_line": {"error": "bad line 3"},
    "provider_exit": {"error": "provider exit 9"},
    "claude_result_error": {"error": "claude result error"},
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


if __name__ == "__main__":
    unittest.main()
