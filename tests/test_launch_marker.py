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

    def test_prose_execution_directory_has_exact_collect_refusal(self) -> None:
        directory = self.run_dir(self.repo, self.run_id) / "prose-agent/execution-02"
        directory.mkdir(parents=True)
        with self.assertRaises(ENGINE.Refusal) as caught:
            VERBS_LAUNCH_COLLECT.launch_collect(self.ready_engine(), "execution-02")
        self.assertEqual(
            caught.exception.message,
            "forge: launch collect refused — execution execution-02 has no "
            "launch_marker; collect a prose launch by prose",
        )

    def test_marker_binding_uses_independent_path_sidecar_and_completion_fields(self) -> None:
        engine = self.ready_engine()
        paths = self.paths(self.record)
        self.write_private_json(
            paths.leaf("completion.json"),
            {field: self.baseline[field] for field in (
                "attempt", "provider", "sandbox", "route_source", "route_sha256",
                "argv_digest", "prompt_digest",
            )},
        )
        changes = {
            "run_id": "another-run", "agent": "codex-implementer-99",
            "execution": "execution-99", "attempt": "attempt-0123456789abcdef",
            "worktree": str(self.repo), "provider": "claude", "role": "plan",
            "sandbox": "read-only", "route_source": "different",
            "route_sha256": "a" * 64,
        }

        def assert_field(field: str, value: str) -> None:
            changed = dict(self.baseline, **{field: value})
            if field == "provider":
                changed["argv_digest"] = engine.ctx.command_digest(
                    LAUNCH_LANE.marker_argv(changed, paths)
                )
            LAUNCH_LANE.write_marker(self.marker_path, changed)
            with self.assertRaises(ENGINE.Refusal) as caught:
                VERBS_LAUNCH_COLLECT._bound_execution(engine, "execution-01", "collect")
            self.assertEqual(
                caught.exception.message,
                "forge: launch collect refused — launch marker does not bind "
                f"execution execution-01: {field}",
            )
            LAUNCH_LANE.write_marker(self.marker_path, self.baseline)

        for field, value in changes.items():
            with self.subTest(field=field):
                assert_field(field, value)
        LAUNCH_LANE.replace_owner_file(
            paths.directory,
            LAUNCH_LANE.WORKTREE_NAME,
            (str(self.repo) + "\n").encode("utf-8"),
        )
        with self.assertRaises(ENGINE.Refusal) as caught:
            VERBS_LAUNCH_COLLECT._bound_execution(engine, "execution-01", "collect")
        self.assertIn("execution execution-01: worktree", caught.exception.message)
        with (
            mock.patch.object(LAUNCH_LANE, "bind_marker", return_value=None),
            self.assertRaises(AssertionError),
        ):
            with self.assertRaises(ENGINE.Refusal):
                VERBS_LAUNCH_COLLECT._bound_execution(engine, "execution-01", "collect")

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
