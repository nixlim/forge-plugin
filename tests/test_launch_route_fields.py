"""Launch records describe the selected route for each execution."""

from __future__ import annotations

import unittest

from tests._launch_support import LAUNCH_LANE, LaunchLaneSupport


class LaunchRouteFieldTests(LaunchLaneSupport, unittest.TestCase):
    def test_start_and_finish_records_carry_the_actual_route(self) -> None:
        self.open_run_and_task()
        for provider in ("codex", "claude"):
            with self.subTest(provider=provider):
                self.seed_launch(provider=provider)
                start = self.execution_records()[-1]
                stored_start = next(row for row in reversed(self.records())
                                    if row.get("kind") == "execution_started")
                marker = self.marker(start)
                self.assertEqual(start["kind"], "execution_started")
                self.assertFalse({"execution", "task"} & stored_start.keys())
                self.assertRegex(str(stored_start["started_at"]),
                                 r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
                self.assertEqual(start["execution_id"], marker["execution"])
                self.assertEqual(start["attempt_id"], marker["attempt"])
                for field in ("provider", "model", "effort", "sandbox",
                              "route_source", "route_sha256"):
                    self.assertEqual(start[field], marker[field])
                result = LAUNCH_LANE.CompletionResult(
                    "failed", "fixture failure", (), (), None, "launch collect: failed"
                )
                run = LAUNCH_LANE.run_state(self.ready_engine(open_task=False).ctx, self.run_id)
                finish = LAUNCH_LANE.append_execution_result(
                    run, self.paths(start), task=self.task_id, result=result,
                    completion_raw=b"fixture completion",
                )
                self.assertEqual(finish["kind"], "execution_finished")
                for field in ("provider", "model", "effort", "sandbox",
                              "route_source", "route_sha256"):
                    self.assertEqual(finish[field], marker[field])
                completion = self.paths(start).leaf("completion.json")
                completion.write_text("{}", encoding="utf-8")
                completion.chmod(0o600)
                LAUNCH_LANE.mark_collected(self.paths(start), marker, "failed")

    def test_run_open_route_does_not_freeze_later_execution(self) -> None:
        self.open_run_and_task()
        self.configure_route("implementer", "codex")
        self.seed_launch()
        first = self.execution_records()[0]
        marker = self.marker(first)
        completion = self.paths(first).leaf("completion.json")
        completion.write_text("{}", encoding="utf-8")
        completion.chmod(0o600)
        LAUNCH_LANE.mark_collected(self.paths(first), marker, "failed")
        self.configure_route("implementer", "claude")
        self.seed_launch()
        second = self.execution_records()[1]
        self.assertEqual((first["provider"], second["provider"]), ("codex", "claude"))
        self.assertNotEqual(first["route_sha256"], second["route_sha256"])
