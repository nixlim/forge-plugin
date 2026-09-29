"""Cancellation-specific coverage for typed launches."""

from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from unittest import mock

from tests._cli_loader import package_module, patch_engine
from tests._launch_support import (
    VERBS_LAUNCH_COLLECT,
    LaunchLaneSupport,
    kill_group,
    wait_path,
    wait_process_gone,
)

ENGINE = package_module("engine")
ATTEMPT = package_module("engine._review_attempt")
LANE_API = package_module("engine._review_lane_api")


class LaunchCancelTests(LaunchLaneSupport, unittest.TestCase):
    def test_cancel_missing_execution_uses_cancel_diagnostic(self) -> None:
        with self.assertRaises(ENGINE.Refusal) as caught:
            VERBS_LAUNCH_COLLECT.launch_cancel(self.ready_engine(), "execution-99")
        self.assertEqual(
            caught.exception.message,
            "forge: launch cancel refused — execution execution-99 does not exist",
        )

    def test_wrapper_dead_child_alive_names_cancel_and_lost_proofs_map(self) -> None:
        self.seed_launch(provider="codex")
        engine = self.ready_engine()
        record = self.execution_records()[-1]
        bound = VERBS_LAUNCH_COLLECT._bound_execution(
            engine, str(record["execution"]), "collect"
        )
        observed = ATTEMPT.AttemptObservation(
            "wrapper-dead / child-alive", identity=self.live_identity(record),
            members=(88,),
        )
        refusal = VERBS_LAUNCH_COLLECT._nonterminal_refusal(bound, observed)
        self.assertEqual(
            refusal.message,
            "forge: launch collect refused — wrapper-dead / child-alive for "
            f"{record['execution']}; run launch cancel --repo {self.repo} --run-id "
            f"{self.run_id} --execution {record['execution']}",
        )
        for reason in ("identity-mismatch", "group-empty"):
            proof = ATTEMPT.GroupProof(reason, 77)
            with patch_engine("prove_group_ownership", return_value=proof):
                outcome = VERBS_LAUNCH_COLLECT._cancel_group(
                    bound, self.live_identity(record)
                )
            self.assertEqual(outcome, "wrapper-lost")

    def test_kill_unconfirmed_refuses_without_publication(self) -> None:
        self.seed_launch(provider="codex")
        engine = self.ready_engine()
        record = self.execution_records()[-1]
        bound = VERBS_LAUNCH_COLLECT._bound_execution(
            engine, str(record["execution"]), "cancel"
        )
        alive = ATTEMPT.GroupProof("wrapper-alive", 77, (77, 88))
        stuck = ATTEMPT.GroupProof("kill-unconfirmed", 77, (88,))
        with (
            patch_engine("prove_group_ownership", return_value=alive),
            patch_engine("terminate_owned_group", return_value=stuck),
            patch_engine("publish_or_read_terminal") as publish,
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            VERBS_LAUNCH_COLLECT._publish_cancel(
                bound, 9, self.live_identity(record)
            )
        self.assertEqual(
            caught.exception.message,
            f"forge: launch cancel refused — kill-unconfirmed for "
            f"{record['execution']}: [88]",
        )
        publish.assert_not_called()

    def test_cancel_holds_publication_lock_and_reproves_refreshed_identity(self) -> None:
        self.seed_launch(provider="codex")
        engine = self.ready_engine()
        record = self.execution_records()[-1]
        execution = str(record["execution"])
        initial = self.live_identity(record)
        refreshed = dict(initial, reviewer_pid=99)
        refreshed["reviewer_birth"] = {
            "kind": "linux-proc", "boot_id": "boot", "starttime": 3,
        }
        self.write_identity(initial, record)
        original_publish = LANE_API.publish_or_read_terminal
        held = False
        read_count = 0
        proofs = iter((
            ATTEMPT.GroupProof("group-empty", 77),
            ATTEMPT.GroupProof("reviewer-alive", 77, (99,)),
        ))

        @contextmanager
        def locked(_descriptor: int):
            nonlocal held
            held = True
            try:
                yield True
            finally:
                held = False

        def read_identity(*_args: object) -> dict[str, object]:
            nonlocal read_count
            read_count += 1
            if read_count <= 3:
                self.assertTrue(held)
            return initial if read_count == 1 else refreshed

        def prove(*_args: object) -> object:
            self.assertTrue(held)
            return next(proofs)

        def terminate(*_args: object) -> object:
            self.assertTrue(held)
            return ATTEMPT.GroupProof("cancelled", 77)

        def publish(*args: object) -> object:
            self.assertTrue(held)
            return original_publish(*args)

        with (
            patch_engine("attempt_publication_lock", side_effect=locked),
            patch_engine("read_identity", side_effect=read_identity),
            patch_engine("prove_group_ownership", side_effect=prove),
            patch_engine("terminate_owned_group", side_effect=terminate) as killed,
            patch_engine("publish_or_read_terminal", side_effect=publish),
        ):
            outcome = VERBS_LAUNCH_COLLECT.launch_cancel(engine, execution)
        self.assertFalse(held)
        self.assertEqual(outcome.state, "failed")
        killed.assert_called_once_with(refreshed, 5)
        completion = self.attempt_dir(record) / "completion.json"
        self.assertEqual(json.loads(completion.read_text())["error"], "cancelled")

    def test_cancel_refuses_each_changed_immutable_identity_field(self) -> None:
        self.seed_launch(provider="codex")
        engine = self.ready_engine()
        record = self.execution_records()[-1]
        bound = VERBS_LAUNCH_COLLECT._bound_execution(
            engine, str(record["execution"]), "cancel"
        )
        initial = self.live_identity(record)
        changes = {
            "attempt": "attempt-fedcba9876543210",
            "wrapper_pid": 78,
            "pgid": 78,
            "wrapper_birth": {
                "kind": "linux-proc", "boot_id": "other", "starttime": 77,
            },
        }

        def assert_refusal(field: str, value: object) -> None:
            current = dict(initial, **{field: value})
            proof = ATTEMPT.GroupProof("group-empty", 77)
            with (
                patch_engine("prove_group_ownership", return_value=proof),
                patch_engine("read_identity", return_value=current),
                patch_engine("publish_or_read_terminal", return_value=(True, {})) as publish,
                self.assertRaises(ENGINE.Refusal) as caught,
            ):
                VERBS_LAUNCH_COLLECT._publish_cancel(bound, 9, dict(initial))
            self.assertIs(
                caught.exception.reason_code,
                ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
            )
            self.assertEqual(
                caught.exception.message,
                "forge: launch cancel refused — attempt record is invalid for "
                "execution-01: identity.json changed group identity before "
                "completion publication",
            )
            publish.assert_not_called()

        for field, value in changes.items():
            with self.subTest(field=field):
                assert_refusal(field, value)
        with (
            patch_engine("IMMUTABLE_IDENTITY_FIELDS", ()),
            self.assertRaises(AssertionError),
        ):
            assert_refusal("pgid", 78)

    def test_cancel_refuses_identity_that_keeps_changing(self) -> None:
        self.seed_launch(provider="codex")
        engine = self.ready_engine()
        record = self.execution_records()[-1]
        bound = VERBS_LAUNCH_COLLECT._bound_execution(
            engine, str(record["execution"]), "cancel"
        )
        initial = self.live_identity(record)

        def assert_refusal() -> None:
            identities = [
                dict(
                    initial,
                    reviewer_pid=100 + index,
                    reviewer_birth={
                        "kind": "linux-proc", "boot_id": "fixture",
                        "starttime": 100 + index,
                    },
                )
                for index in range(8)
            ]
            with (
                mock.patch.object(
                    VERBS_LAUNCH_COLLECT, "_cancel_group",
                    return_value="wrapper-lost",
                ) as cancel_group,
                patch_engine("read_identity", side_effect=identities),
                patch_engine("publish_or_read_terminal", return_value=(True, {})) as publish,
                self.assertRaises(ENGINE.Refusal) as caught,
            ):
                VERBS_LAUNCH_COLLECT._publish_cancel(bound, 9, dict(initial))
            self.assertEqual(
                caught.exception.message,
                "forge: launch cancel refused — attempt record is invalid for "
                "execution-01: identity.json kept changing before completion publication",
            )
            self.assertEqual(cancel_group.call_count, 9)
            publish.assert_not_called()

        assert_refusal()
        with (
            mock.patch.object(LANE_API, "REFRESH_RECHECK_FIELDS", frozenset()),
            self.assertRaises(AssertionError),
        ):
            assert_refusal()

    def test_cancel_publication_race_has_one_winner(self) -> None:
        self.seed_launch(provider="codex")
        engine = self.ready_engine()
        record = self.execution_records()[-1]
        directory = self.attempt_dir(record)
        execution = str(record["execution"])
        identity = self.live_identity(record)
        self.write_identity(identity, record)
        original_publish = LANE_API.publish_or_read_terminal
        published: list[bool] = []

        def race(directory_fd, binding, _error, current_identity):
            winner = ATTEMPT.make_terminal_completion(
                binding, "provider exit 9", identity=current_identity
            )
            published.append(ATTEMPT.publish_terminal_completion(directory_fd, winner))
            return original_publish(
                directory_fd, binding, "wrapper-lost", current_identity
            )

        with (
            patch_engine(
                "prove_group_ownership",
                return_value=ATTEMPT.GroupProof("group-empty", 77),
            ),
            patch_engine("publish_or_read_terminal", side_effect=race),
        ):
            outcome = VERBS_LAUNCH_COLLECT.launch_cancel(engine, execution)
        self.assertEqual((published, outcome.state), ([True], "failed"))
        completion = json.loads((directory / "completion.json").read_text())
        self.assertEqual(completion["error"], "provider exit 9")
        results = [
            item for item in self.records() if item.get("type") == "execution_result"
        ]
        self.assertEqual(len(results), 1)

    def test_real_cancel_kills_provider_group_and_grandchild(self) -> None:
        executable = self.install_mode_provider("codex", "fork-sleeper")
        with patch_engine("CODEX_EXECUTABLE", str(executable)):
            self.launch_direct(provider="codex")
            engine = self.ready_engine()
            record = self.execution_records()[-1]
            directory = self.attempt_dir(record)
            pgid = int((directory / "pid").read_text().splitlines()[1])
            self.addCleanup(kill_group, pgid)
            identity_path = wait_path(directory / "identity.json")
            grandchild_path = wait_path(self.logs / "codex.grandchild-pid")
            identity = json.loads(identity_path.read_text())
            grandchild = int(grandchild_path.read_text())
            self.assertEqual(identity["pgid"], pgid)
            outcome = VERBS_LAUNCH_COLLECT.launch_cancel(
                engine, str(record["execution"])
            )
        self.assertEqual(outcome.state, "failed")
        completion = json.loads((directory / "completion.json").read_text())
        self.assertEqual(completion["error"], "cancelled")
        wait_process_gone(grandchild)


if __name__ == "__main__":
    unittest.main()
