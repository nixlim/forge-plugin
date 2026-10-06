"""Focused schema and corruption coverage for typed launch markers."""

from __future__ import annotations

import unittest
from unittest import mock

from tests._launch_support import (
    ENGINE,
    LAUNCH_LANE,
    VERBS_LAUNCH_COLLECT,
    LaunchLaneSupport,
)


class LaunchMarkerSchemaTests(LaunchLaneSupport, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.configure_route("implementer", "codex")
        self.open_run_and_task()
        self.engine = self.ready_engine(open_task=False)
        self.seed_launch()
        self.record = self.execution_records()[-1]
        self.marker_path = self.attempt_dir(self.record) / "launch.json"
        self.baseline = self.marker(self.record)

    def assert_invalid_marker(self, marker: dict[str, object]) -> None:
        journal = self.run_dir(self.repo, self.run_id) / "journal.jsonl"
        before = journal.read_bytes()
        LAUNCH_LANE.write_marker(self.marker_path, marker)
        with self.assertRaises(ENGINE.Refusal) as caught:
            VERBS_LAUNCH_COLLECT._bound_execution(
                self.engine, str(self.record["execution"]), "collect"
            )
        self.assertIs(
            caught.exception.reason_code,
            ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
        )
        self.assertEqual(
            caught.exception.message,
            "forge: launch collect refused — launch marker does not bind "
            "execution execution-01: marker",
        )
        self.assertEqual(journal.read_bytes(), before)

    def test_every_marker_schema_invariant_refuses_corruption(self) -> None:
        missing = dict(self.baseline)
        missing.pop("schema")
        cases = [
            ("missing key", missing),
            ("extra key", dict(self.baseline, unexpected="value")),
            ("required string", dict(self.baseline, task="")),
            ("schema", dict(self.baseline, schema="forge-launch-marker/0")),
            ("role", dict(self.baseline, role="review-cheap")),
            ("provider", dict(self.baseline, provider="other")),
            ("attempt", dict(self.baseline, attempt="attempt-ABCDEF0123456789")),
            ("execution", dict(self.baseline, execution="execution-1")),
            ("zero timeout", dict(self.baseline, timeout_seconds=0)),
            ("boolean timeout", dict(self.baseline, timeout_seconds=True)),
            ("head", dict(self.baseline, head="0" * 39)),
            ("environment order", dict(self.baseline, environment_names=["Z", "A"])),
            ("environment member", dict(self.baseline, environment_names=[1])),
            ("omitted duplicate", dict(self.baseline, omitted_short=["A", "A"])),
            ("omitted member", dict(self.baseline, omitted_short=[""])),
            (
                "requested timestamp",
                dict(self.baseline, requested_at="2026-09-28T12:00:00"),
            ),
            ("collection status", dict(self.baseline, collected_status="unknown")),
            (
                "collection time only",
                dict(self.baseline, collected_at="2026-09-28T12:00:00Z"),
            ),
            (
                "collection status only",
                dict(self.baseline, collected_status="complete"),
            ),
            (
                "collection timestamp",
                dict(
                    self.baseline,
                    collected_at="2026-09-28T12:00:00",
                    collected_status="complete",
                ),
            ),
        ]
        for field in (
            "route_sha256",
            "role_body_sha256",
            "argv_digest",
            "prompt_digest",
            "launcher_argv_digest",
        ):
            cases.append((field, dict(self.baseline, **{field: "0" * 63})))
        for field in ("worktree", "plugin_root", "role_body_path"):
            cases.append((field, dict(self.baseline, **{field: "relative/path"})))
        for label, marker in cases:
            with self.subTest(invariant=label):
                self.assert_invalid_marker(marker)

    def test_marker_schema_control_is_load_bearing(self) -> None:
        invalid = dict(self.baseline, unexpected="value")
        self.assert_invalid_marker(invalid)
        with (
            mock.patch.object(
                LAUNCH_LANE,
                "validate_marker",
                side_effect=lambda value: dict(value),
            ),
            self.assertRaises(AssertionError),
        ):
            self.assert_invalid_marker(invalid)


if __name__ == "__main__":
    unittest.main()
