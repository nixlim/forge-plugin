"""New-write controls for typed-launch execution route evidence."""

from __future__ import annotations

import copy
import unittest
from unittest import mock

from tests._revision9_coord_constants import key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

from codex_orchestrator import builders, journal

route_evidence = journal.route_evidence


class LaunchRouteFieldTests(Revision9BuilderBatchSupport, unittest.TestCase):
    def execution_record(self, *, role: str = "implementer") -> dict[str, object]:
        return {
            "type": "execution",
            "recorded_at": "2026-09-28T12:00:00Z",
            "run_id": "run-20260928-launch-route-fields",
            "execution": "execution-01",
            "agent": "codex-implementer-01",
            "task": "task-01",
            "provider": "codex",
            "role": role,
            "mode": "detached",
            "model": "gpt-test",
            "effort": "high",
            "worktree": str(self.repo.resolve()),
            "head": self.head,
            "prompt": "prompt.md",
            "handoff": "handoff.md",
            "event_source": "exec",
            "events": "events.jsonl",
        }

    @staticmethod
    def route_fields(role: str = "implementer") -> dict[str, object]:
        return {
            "sandbox": "workspace-write" if role == "implementer" else "read-only",
            "route_source": "local",
            "route_sha256": "a" * 64,
        }

    @staticmethod
    def snapshot() -> tuple[dict[str, object], ...]:
        return ({"type": "run_started", "route": {}},)

    def marker_record(self) -> dict[str, object]:
        return {
            **self.execution_record(),
            **self.route_fields(),
            "launch_marker": "codex-implementer-01/execution-01/launch.json",
        }

    def assert_marker_refuses(self, record: dict[str, object]) -> None:
        expected = (
            "forge: journal append refused — invalid journal record: "
            "execution.launch_marker must equal "
            "codex-implementer-01/execution-01/launch.json and requires the route "
            "trio and mode detached"
        )
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            route_evidence.validate_execution(
                record, (), refusal=journal.CoordinationRefusal
            )
        self.assertEqual(expected, str(caught.exception))

    def test_launch_marker_requires_exact_path_route_trio_and_detached_mode(self) -> None:
        cases: dict[str, dict[str, object]] = {}
        cases["non-string"] = {**self.marker_record(), "launch_marker": None}
        cases["wrong-path"] = {**self.marker_record(), "launch_marker": "elsewhere"}
        cases["wrong-mode"] = {**self.marker_record(), "mode": "headless"}
        without_route = self.marker_record()
        without_route.pop("route_source")
        cases["missing-route"] = without_route
        for label, record in cases.items():
            with self.subTest(label=label):
                self.assert_marker_refuses(record)

        route_evidence.validate_execution(
            self.marker_record(), (), refusal=journal.CoordinationRefusal
        )

    def test_launch_marker_control_is_load_bearing(self) -> None:
        record = {**self.marker_record(), "mode": "headless"}
        self.assert_marker_refuses(record)
        with mock.patch.object(
            route_evidence, "_validate_launch_marker", return_value=None
        ):
            with self.assertRaises(AssertionError):
                self.assert_marker_refuses(record)

    def assert_missing_snapshot_route_refuses(self, role: str) -> None:
        expected = (
            f"forge: execution refused — role {role} carries no route fields "
            "in a run with a route snapshot"
        )
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            route_evidence.validate_execution(
                self.execution_record(role=role),
                self.snapshot(),
                refusal=journal.CoordinationRefusal,
            )
        self.assertEqual(expected, str(caught.exception))

    def test_snapshot_runs_require_routes_for_implementer_and_plan_only(self) -> None:
        for role in ("implementer", "plan"):
            with self.subTest(role=role):
                self.assert_missing_snapshot_route_refuses(role)
        for role in ("review-cheap", "review-final", "monitoring"):
            with self.subTest(role=role):
                route_evidence.validate_execution(
                    self.execution_record(role=role),
                    self.snapshot(),
                    refusal=journal.CoordinationRefusal,
                )
        for role in ("implementer", "plan"):
            route_evidence.validate_execution(
                self.execution_record(role=role),
                (),
                refusal=journal.CoordinationRefusal,
            )

    def test_snapshot_route_requirement_is_load_bearing(self) -> None:
        self.assert_missing_snapshot_route_refuses("implementer")
        with mock.patch.object(
            route_evidence, "_require_snapshot_route", return_value=None
        ):
            with self.assertRaises(AssertionError):
                self.assert_missing_snapshot_route_refuses("implementer")

    def test_historical_replay_skips_new_route_controls(self) -> None:
        record = self.execution_record()
        record["launch_marker"] = "historical/free-form-marker"
        with mock.patch.object(
            route_evidence,
            "validate_execution",
            side_effect=AssertionError("new-write route controls invoked"),
        ):
            validated = journal._validate_proposed_record(
                record,
                run_id=str(record["run_id"]),
                repo_root=self.repo.resolve(),
                scope=("src/**",),
                prior_records=self.snapshot(),
                _historical_replay=journal._HISTORICAL_REPLAY,
            )
        self.assertEqual(record, validated)

    def test_execution_start_carries_launch_marker(self) -> None:
        run_id = "run-20260928-launch-marker-builder"
        with self.api_environment():
            opening = self.open_run(self.repo, run_id).records[0]
            self.start_task(self.repo, run_id)
        run_dir = self.run_dir(self.repo, run_id)
        for relative in ("prompt.md", "events.jsonl", "handoff.md"):
            (run_dir / relative).write_text("evidence\n", encoding="utf-8")
        route = copy.deepcopy(opening["route"]["implementer"])
        with self.api_environment():
            outcome = builders.execution_start(
                self.repo,
                run_id,
                idempotency_key=key("launch marker execution"),
                agent="codex-implementer-01",
                task="task-01",
                provider=route["provider"],
                role="implementer",
                mode="detached",
                model=route["model"],
                effort=route["effort"],
                worktree=str(self.repo.resolve()),
                head=self.head,
                prompt="prompt.md",
                handoff="handoff.md",
                event_source="exec",
                events="events.jsonl",
                sandbox="workspace-write",
                route_source=route["route_source"],
                route_sha256=route["route_sha256"],
                launch_marker="codex-implementer-01/execution-01/launch.json",
            )
        self.assertEqual(
            "codex-implementer-01/execution-01/launch.json",
            outcome.records[0]["launch_marker"],
        )


if __name__ == "__main__":
    unittest.main()
