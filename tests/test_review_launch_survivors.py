"""Adversarial process-identity tests for routed review attempts."""

from __future__ import annotations

import datetime as dt
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._cli_loader import package_module

ATTEMPT = package_module("engine._review_attempt")
ATTEMPT_PROC = package_module("engine._review_attempt_proc")
WRAPPER = package_module("engine._review_wrapper")
ATTEMPT_ID = "attempt-0123456789abcdef"
NOW = "2026-09-27T12:00:00Z"


def birth(label: str = "boot-a", starttime: int = 10) -> dict[str, object]:
    return {"kind": "linux-proc", "boot_id": label, "starttime": starttime}


def identity(
    *,
    wrapper_pid: int = 4100,
    reviewer_pid: int | None = 4101,
) -> dict[str, object]:
    return {
        "schema": WRAPPER.IDENTITY_SCHEMA,
        "attempt": ATTEMPT_ID,
        "wrapper_pid": wrapper_pid,
        "pgid": wrapper_pid,
        "wrapper_birth": birth(starttime=11),
        "reviewer_pid": reviewer_pid,
        "reviewer_birth": birth(starttime=12) if reviewer_pid else None,
        "started_at": NOW,
    }


def request() -> dict[str, object]:
    return {
        "attempt": ATTEMPT_ID,
        "provider": "codex",
        "sandbox": "read-only",
        "route": {
            "provider": "codex",
            "model": "gpt-test",
            "effort": "high",
            "route_source": "committed-default",
            "route_sha256": "1" * 64,
        },
        "argv_digest": "2" * 64,
        "prompt_digest": "3" * 64,
        "environment_names": ["PATH"],
        "omitted_short": ["LANG"],
    }


class AttemptDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-review-attempt-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.descriptor = os.open(self.path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        self.addCleanup(os.close, self.descriptor)

    def test_unknown_identity_schema_uses_newer_shape_literal(self) -> None:
        record = identity()
        record["schema"] = "forge-review-identity/99"
        self.assertTrue(WRAPPER.exclusive_publish(self.descriptor, "identity.json", record))

        with self.assertRaises(ATTEMPT.AttemptShapeNewer) as caught:
            ATTEMPT.read_identity(self.descriptor, ATTEMPT_ID)

        self.assertEqual(str(caught.exception), ATTEMPT.NEWER_SHAPE_LITERAL)

    def test_duplicate_json_keys_fail_closed(self) -> None:
        raw = json.dumps(identity(), sort_keys=True, separators=(",", ":"))
        path = self.path / "identity.json"
        path.write_text(raw[:-1] + ',"attempt":"attempt-feedfacefeedface"}', encoding="utf-8")
        path.chmod(0o600)

        with self.assertRaisesRegex(ATTEMPT.AttemptRecordError, "duplicate JSON keys") as caught:
            ATTEMPT.read_identity(self.descriptor, ATTEMPT_ID)
        self.assertNotIsInstance(caught.exception, ATTEMPT.AttemptShapeNewer)

    def test_abandonment_claim_is_exclusive_and_crash_resumable(self) -> None:
        claim = {
            "schema": WRAPPER.IDENTITY_SCHEMA,
            "attempt": ATTEMPT_ID,
            "wrapper_pid": None,
            "pgid": None,
            "wrapper_birth": None,
            "reviewer_pid": None,
            "reviewer_birth": None,
            "started_at": NOW,
        }
        self.assertTrue(WRAPPER.exclusive_publish(self.descriptor, "identity.json", claim))

        resumed, completion = ATTEMPT.claim_abandoned(self.descriptor, request(), NOW)
        resumed_again, existing = ATTEMPT.claim_abandoned(
            self.descriptor, request(), "2026-09-27T12:00:01Z"
        )

        self.assertTrue(resumed)
        self.assertTrue(resumed_again)
        self.assertEqual(completion["error"], "abandoned")
        self.assertEqual(existing, completion)
        self.assertEqual(ATTEMPT.read_completion(self.descriptor, ATTEMPT_ID), completion)
        self.assertFalse(WRAPPER.exclusive_publish(self.descriptor, "identity.json", identity()))

    def test_observe_distinguishes_launching_deadline_and_abandoned_claim(self) -> None:
        deadline = dt.datetime(2026, 9, 27, 12, 1, tzinfo=dt.timezone.utc)
        before = ATTEMPT.observe_attempt(
            self.descriptor,
            ATTEMPT_ID,
            deadline,
            dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc),
        )
        after = ATTEMPT.observe_attempt(
            self.descriptor,
            ATTEMPT_ID,
            deadline,
            dt.datetime(2026, 9, 27, 12, 2, tzinfo=dt.timezone.utc),
        )
        self.assertEqual((before.outcome, after.outcome), ("launching", "abandonable"))
        ATTEMPT.claim_abandoned(self.descriptor, request(), NOW)
        os.unlink("completion.json", dir_fd=self.descriptor)
        observed = ATTEMPT.observe_attempt(self.descriptor, ATTEMPT_ID, deadline, deadline)
        self.assertEqual(observed.outcome, "abandoned-claimed")

    def test_unreadable_wrapper_birth_is_published_and_never_launched(self) -> None:
        def assert_control() -> dict[str, object]:
            with (
                mock.patch.object(WRAPPER.os, "getpid", return_value=4100),
                mock.patch.object(WRAPPER.os, "getpgid", return_value=4100),
                mock.patch.object(WRAPPER.os, "getsid", return_value=4100),
                mock.patch.object(WRAPPER, "birth_identity", return_value=None),
                mock.patch.object(WRAPPER, "_launch_inputs") as launch,
            ):
                WRAPPER._run(self.descriptor, {"attempt": ATTEMPT_ID})
            owner = ATTEMPT.read_identity(self.descriptor, ATTEMPT_ID)
            self.assertIsNotNone(owner)
            assert owner is not None
            self.assertIsNone(owner["wrapper_birth"])
            self.assertIsNone(owner["reviewer_pid"])
            launch.assert_not_called()
            return owner

        owner = assert_control()
        with (
            mock.patch.object(ATTEMPT, "_group_members", return_value=((4100,), True)),
            mock.patch.object(ATTEMPT, "_send_group_signal") as send,
        ):
            proof = ATTEMPT.prove_group_ownership(owner)
            observed = ATTEMPT.observe_attempt(
                self.descriptor, ATTEMPT_ID, dt.datetime.now(dt.timezone.utc)
            )
            terminated = ATTEMPT.terminate_owned_group(owner)
        self.assertEqual(proof.outcome, "wrapper-identity-unproven")
        self.assertEqual(observed.outcome, "wrapper-identity-unproven")
        self.assertEqual(terminated.outcome, "wrapper-identity-unproven")
        send.assert_not_called()
        self.assertFalse(WRAPPER.exclusive_publish(self.descriptor, "identity.json", owner))
        with mock.patch.object(ATTEMPT, "_group_members", return_value=((), True)):
            recovered = ATTEMPT.observe_attempt(
                self.descriptor, ATTEMPT_ID, dt.datetime.now(dt.timezone.utc)
            )
        self.assertEqual((recovered.outcome, recovered.reason), ("wrapper-lost", "group-empty"))

        os.unlink("identity.json", dir_fd=self.descriptor)
        with (
            mock.patch.object(WRAPPER, "_claim_identity", return_value=None),
            self.assertRaises(AssertionError),
        ):
            assert_control()

    def test_launch_inputs_bind_optional_role_body_digest(self) -> None:
        prompt, role_body = b"prompt", b"trusted role body"
        for name, data in (("prompt.txt", prompt), ("review-final-body.md", role_body)):
            path = self.path / name
            path.write_bytes(data)
            path.chmod(0o600)
        config = {
            "argv": [],
            "argv_digest": WRAPPER._canonical_digest([]),
            "environment_names": [],
            "prompt_digest": WRAPPER.hashlib.sha256(prompt).hexdigest(),
            "role_body_digest": WRAPPER.hashlib.sha256(role_body).hexdigest(),
        }
        self.assertEqual(WRAPPER._launch_inputs(self.descriptor, config)[2], prompt)
        (self.path / "review-final-body.md").write_bytes(b"mutated role body")
        with self.assertRaisesRegex(ValueError, "role body digest"):
            WRAPPER._launch_inputs(self.descriptor, config)

    def test_stale_marker_is_exclusive_and_bound_to_valid_completion(self) -> None:
        completion = ATTEMPT.make_terminal_completion(request(), "cancelled", completed_at=NOW)
        self.assertTrue(ATTEMPT.record_stale(self.descriptor, ATTEMPT_ID, completion))
        self.assertFalse(ATTEMPT.record_stale(self.descriptor, ATTEMPT_ID, completion))
        marker = (self.path / "stale.json").read_text(encoding="utf-8")
        self.assertIn('"schema":"forge-review-stale/1"', marker)

    def test_terminal_completion_is_exclusive_and_never_clobbered(self) -> None:
        wrapper_completion = ATTEMPT.make_terminal_completion(
            request(), "cancelled", completed_at=NOW
        )
        wrapper_completion.update(
            error=None,
            returncode=0,
            verdict_digest="4" * 64,
            verdict_size=16,
        )
        ATTEMPT._validate_completion(wrapper_completion, ATTEMPT_ID)
        verb_completion = ATTEMPT.make_terminal_completion(
            request(), "wrapper-lost", completed_at="2026-09-27T12:00:01Z"
        )

        self.assertTrue(
            ATTEMPT.publish_terminal_completion(self.descriptor, wrapper_completion)
        )
        self.assertFalse(
            ATTEMPT.publish_terminal_completion(self.descriptor, verb_completion)
        )
        self.assertEqual(
            ATTEMPT.read_completion(self.descriptor, ATTEMPT_ID), wrapper_completion
        )

    def test_completion_binding_rejects_route_and_identity_divergence(self) -> None:
        owner = identity()
        completion = ATTEMPT.make_terminal_completion(
            request(), "cancelled", identity=owner, completed_at=NOW
        )
        ATTEMPT.validate_completion_binding(completion, request(), owner)
        changed = dict(completion, route_sha256="f" * 64)
        with self.assertRaisesRegex(ValueError, "route_sha256"):
            ATTEMPT.validate_completion_binding(changed, request(), owner)
        changed = dict(completion, reviewer_pid=9999)
        with self.assertRaisesRegex(ValueError, "reviewer_pid"):
            ATTEMPT.validate_completion_binding(changed, request(), owner)

    def test_completion_without_identity_may_not_claim_processes(self) -> None:
        completion = ATTEMPT.make_terminal_completion(
            request(), "launch-failed: spawn error", completed_at=NOW
        )
        ATTEMPT.validate_completion_binding(completion, request(), None)
        completion["wrapper_pid"] = 9001
        with self.assertRaisesRegex(ValueError, "without identity"):
            ATTEMPT.validate_completion_binding(completion, request(), None)
        success = dict(
            completion,
            wrapper_pid=None,
            error=None,
            returncode=0,
            verdict_digest="4" * 64,
            verdict_size=16,
        )
        with self.assertRaisesRegex(ValueError, "not launch-failed"):
            ATTEMPT.validate_completion_binding(success, request(), None)

    def test_completion_error_vocabulary_is_closed(self) -> None:
        for error in ("wrapper failure", "provider exit 17", "provider exit -15", "bad line 4"):
            with self.subTest(error=error):
                ATTEMPT.make_terminal_completion(request(), error, completed_at=NOW)
        timed_out = ATTEMPT.make_terminal_completion(
            request(), "cancelled", completed_at=NOW
        )
        timed_out.update(error=None, timed_out=True)
        ATTEMPT._validate_completion(timed_out, ATTEMPT_ID)
        for error in ("timeout", "citation invalid"):
            with self.assertRaisesRegex(ValueError, "invalid error"):
                ATTEMPT.make_terminal_completion(request(), error, completed_at=NOW)


class OwnershipProofTests(unittest.TestCase):
    def test_proc_stat_uses_last_parenthesis_for_hostile_comm(self) -> None:
        fields = ["S", "1", "4100", *("0" for _ in range(16)), "987654"]
        record = f"4101 (worker ) name) {' '.join(fields)}\n".encode()

        self.assertEqual(ATTEMPT_PROC.parse_proc_stat(record), ("S", 4100, 987654))

    def test_proc_stat_without_closing_delimiter_fails_closed(self) -> None:
        fields = ["S", "1", "4100", *("0" for _ in range(16)), "987654"]
        with self.assertRaisesRegex(ValueError, "malformed proc stat"):
            ATTEMPT_PROC.parse_proc_stat(f"x{' '.join(fields)}".encode())

    @unittest.skipUnless(os.path.exists("/proc/self/stat"), "Linux birth identity test")
    def test_linux_birth_identity_matches_proc_start_and_boot(self) -> None:
        _state, _pgid, starttime = ATTEMPT_PROC.parse_proc_stat(
            Path("/proc/self/stat").read_bytes()
        )

        observed = ATTEMPT_PROC.birth_identity(os.getpid())

        self.assertEqual(observed["kind"], "linux-proc")
        self.assertEqual(observed["starttime"], starttime)
        self.assertEqual(
            observed["boot_id"],
            Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip(),
        )

    def test_linux_snapshot_treats_zombie_as_gone_for_group_liveness(self) -> None:
        fields = ["Z", "1", "4100", *("0" for _ in range(16)), "22"]
        record = f"4101 (zombie ) child) {' '.join(fields)}\n".encode()
        with (
            mock.patch.object(ATTEMPT_PROC, "_reaped_child", return_value=False),
            mock.patch.object(ATTEMPT_PROC.Path, "read_bytes", return_value=record),
            mock.patch.object(
                ATTEMPT_PROC,
                "birth_identity",
                return_value=birth(starttime=22),
            ),
        ):
            observed = ATTEMPT_PROC.process_snapshot(4101)

        self.assertEqual(observed["status"], "zombie")

    def test_process_probe_detects_pid_reuse_from_later_starttime(self) -> None:
        with mock.patch.object(
            ATTEMPT_PROC,
            "process_snapshot",
            return_value={
                "status": "alive",
                "pgid": 4100,
                "birth": birth(starttime=99),
            },
        ):
            outcome, pid = ATTEMPT_PROC.process_probe(4100, birth(starttime=11), 4100)

        self.assertEqual((outcome, pid), ("identity-mismatch", 4100))

    def test_leader_alive_proves_group_ownership(self) -> None:
        with (
            mock.patch.object(ATTEMPT, "_group_members", return_value=((4100, 4101), True)),
            mock.patch.object(ATTEMPT, "_process_probe", return_value=("match", 4100)),
        ):
            proof = ATTEMPT.prove_group_ownership(identity())

        self.assertEqual(proof.outcome, "wrapper-alive")
        self.assertEqual(proof.members, (4100, 4101))

    def test_zombie_leader_live_recorded_reviewer_proves_group(self) -> None:
        with (
            mock.patch.object(ATTEMPT, "_group_members", return_value=((4101,), True)),
            mock.patch.object(
                ATTEMPT,
                "_process_probe",
                side_effect=(("zombie", 4100), ("match", 4101)),
            ),
        ):
            proof = ATTEMPT.prove_group_ownership(identity())

        self.assertEqual(proof.outcome, "reviewer-alive")

    def test_only_unrecorded_member_is_identity_unproven(self) -> None:
        with (
            mock.patch.object(ATTEMPT, "_group_members", return_value=((4199,), True)),
            mock.patch.object(
                ATTEMPT,
                "_process_probe",
                side_effect=(("gone", 4100), ("gone", 4101)),
            ),
        ):
            proof = ATTEMPT.prove_group_ownership(identity())

        self.assertEqual(proof.outcome, "identity-unproven")
        self.assertEqual(proof.members, (4199,))

    def test_null_reviewer_birth_is_recorded_identity_unproven(self) -> None:
        owner = identity()
        owner["reviewer_birth"] = None
        with (
            mock.patch.object(ATTEMPT, "_group_members", return_value=((4101,), True)),
            mock.patch.object(
                ATTEMPT,
                "_process_probe",
                side_effect=(("gone", 4100), ("identity-unproven", 4101)),
            ),
        ):
            proof = ATTEMPT.prove_group_ownership(owner)

        self.assertEqual(proof.outcome, "recorded-identity-unproven")

    def test_unprovable_wrapper_is_distinct_and_never_signalled(self) -> None:
        owner = identity()
        with (
            mock.patch.object(ATTEMPT, "_group_members", return_value=((4100,), True)),
            mock.patch.object(
                ATTEMPT,
                "_process_probe",
                side_effect=(("identity-unproven", 4100), ("identity-mismatch", 4101)),
            ),
        ):
            proof = ATTEMPT.prove_group_ownership(owner)
        self.assertEqual(proof.outcome, "wrapper-identity-unproven")
        with (
            mock.patch.object(ATTEMPT, "read_completion", return_value=None),
            mock.patch.object(ATTEMPT, "read_identity", return_value=owner),
            mock.patch.object(ATTEMPT, "prove_group_ownership", return_value=proof),
        ):
            observed = ATTEMPT.observe_attempt(0, ATTEMPT_ID, dt.datetime.now(dt.timezone.utc))
        with (
            mock.patch.object(ATTEMPT, "prove_group_ownership", return_value=proof),
            mock.patch.object(ATTEMPT, "_send_group_signal") as send,
        ):
            terminated = ATTEMPT.terminate_owned_group(owner)
        self.assertEqual(observed.outcome, "wrapper-identity-unproven")
        self.assertEqual(terminated.outcome, "wrapper-identity-unproven")
        send.assert_not_called()

    def test_recycled_pid_is_identity_mismatch_and_never_signalled(self) -> None:
        with (
            mock.patch.object(ATTEMPT, "_group_members", return_value=((4100,), True)),
            mock.patch.object(
                ATTEMPT,
                "_process_probe",
                side_effect=(("identity-mismatch", 4100), ("gone", 4101)),
            ),
            mock.patch.object(ATTEMPT, "_send_group_signal") as send,
        ):
            result = ATTEMPT.terminate_owned_group(identity())

        self.assertEqual(result.outcome, "identity-mismatch")
        send.assert_not_called()

    def test_changed_boot_id_and_empty_group_are_wrapper_lost(self) -> None:
        deadline = dt.datetime.now(dt.timezone.utc)
        cases = (("boot-id-changed", (4100,)), ("group-empty", ()))
        for proof_outcome, members in cases:
            with (
                self.subTest(proof=proof_outcome),
                mock.patch.object(
                    ATTEMPT,
                    "prove_group_ownership",
                    return_value=ATTEMPT.GroupProof(proof_outcome, 4100, members),
                ),
            ):
                with (
                    mock.patch.object(ATTEMPT, "read_completion", return_value=None),
                    mock.patch.object(ATTEMPT, "read_identity", return_value=identity()),
                ):
                    observed = ATTEMPT.observe_attempt(0, ATTEMPT_ID, deadline, deadline)
            self.assertEqual(observed.outcome, "wrapper-lost")
            self.assertEqual(observed.reason, proof_outcome)

    def test_term_then_kill_and_bounded_unconfirmed_result(self) -> None:
        proof = ATTEMPT.GroupProof("wrapper-alive", 4100, (4100, 4101))
        with (
            mock.patch.object(ATTEMPT, "prove_group_ownership", return_value=proof),
            mock.patch.object(ATTEMPT, "_send_group_signal", return_value="sent") as send,
            mock.patch.object(
                ATTEMPT,
                "_wait_group_empty",
                side_effect=(((4101,), False), ((4101,), False)),
            ),
        ):
            result = ATTEMPT.terminate_owned_group(identity(), 0.01, 0.01)

        self.assertEqual((result.outcome, result.members), ("kill-unconfirmed", (4101,)))
        self.assertEqual([call.args[1] for call in send.call_args_list], [
            ATTEMPT.signal.SIGTERM, ATTEMPT.signal.SIGKILL])
        with mock.patch.object(ATTEMPT, "prove_group_ownership", return_value=proof), \
                mock.patch.object(ATTEMPT, "_send_group_signal", return_value="gone"):
            vanished = ATTEMPT.terminate_owned_group(identity())
        self.assertEqual(vanished.outcome, "group-empty")

    def test_incomplete_empty_scan_never_claims_group_empty(self) -> None:
        with mock.patch.object(ATTEMPT_PROC, "group_members", return_value=((), False)):
            remaining, empty = ATTEMPT_PROC.wait_group_empty(4100, 0.0)

        self.assertEqual((remaining, empty), ((), False))

    @mock.patch.object(ATTEMPT_PROC, "process_snapshot")
    @mock.patch.object(ATTEMPT_PROC.subprocess, "run")
    def test_macos_group_scan_lists_unproven_members(self, run, snapshot) -> None:
        run.return_value = mock.Mock(returncode=0, stdout="4101\n4102\n4103\n")
        statuses = ("alive", "identity-unproven", "zombie")
        snapshot.side_effect = ({"status": status} for status in statuses)
        members, complete = ATTEMPT_PROC._mac_group_members(4100, None)
        self.assertEqual((members, complete), ((4101, 4102), False))

    def test_incomplete_empty_scans_end_as_kill_unconfirmed(self) -> None:
        proof = ATTEMPT.GroupProof("wrapper-alive", 4100, (4100,))
        with (
            mock.patch.object(ATTEMPT, "prove_group_ownership", return_value=proof),
            mock.patch.object(ATTEMPT, "_send_group_signal", return_value="sent") as send,
            mock.patch.object(
                ATTEMPT,
                "_wait_group_empty",
                side_effect=(((), False), ((), False)),
            ),
        ):
            result = ATTEMPT.terminate_owned_group(identity(), 0.01, 0.01)

        self.assertEqual(result.outcome, "kill-unconfirmed")
        self.assertEqual(
            [call.args[1] for call in send.call_args_list],
            [ATTEMPT.signal.SIGTERM, ATTEMPT.signal.SIGKILL],
        )

    def test_wait_deadline_is_forwarded_to_group_scan(self) -> None:
        with (
            mock.patch.object(
                ATTEMPT_PROC.time,
                "monotonic",
                side_effect=(10.0, 10.1, 10.1, 10.2, 10.25),
            ),
            mock.patch.object(
                ATTEMPT_PROC, "group_members", return_value=((4101,), True)
            ) as scan,
            mock.patch.object(ATTEMPT_PROC.time, "sleep"),
        ):
            remaining, empty = ATTEMPT_PROC.wait_group_empty(4100, 0.2)

        self.assertEqual((remaining, empty), ((4101,), False))
        self.assertEqual(scan.call_args.args, (4100, 10.2))

    def test_identity_unproven_never_signals_group(self) -> None:
        proof = ATTEMPT.GroupProof("identity-unproven", 4100, (4199,))
        with (
            mock.patch.object(ATTEMPT, "prove_group_ownership", return_value=proof),
            mock.patch.object(ATTEMPT, "_send_group_signal") as send,
        ):
            result = ATTEMPT.terminate_owned_group(identity())

        self.assertEqual(result.outcome, "identity-unproven")
        send.assert_not_called()

    def test_macos_starttime_parser_uses_microsecond_fixture(self) -> None:
        packed = struct.pack("@ll", 1_727_424_000, 987_654)
        self.assertEqual(
            ATTEMPT_PROC._parse_macos_kinfo_start(packed),
            (1_727_424_000, 987_654),
        )

    def test_macos_birth_identity_uses_sysctl_pid_mib(self) -> None:
        packed = struct.pack("@ll", 1_727_424_000, 987_654)
        calls: list[tuple[int, ...]] = []

        def sysctl(mib, count, output, output_size, _new, _new_size):
            calls.append(tuple(mib[index] for index in range(count)))
            if output is None:
                output_size._obj.value = len(packed)
            else:
                WRAPPER.ctypes.memmove(output, packed, len(packed))
                output_size._obj.value = len(packed)
            return 0

        library = mock.Mock(sysctl=sysctl)
        with (
            mock.patch.object(WRAPPER.sys, "platform", "darwin"),
            mock.patch.object(WRAPPER.ctypes, "CDLL", return_value=library),
        ):
            observed = ATTEMPT_PROC.birth_identity(4321)

        self.assertEqual(calls, [(1, 14, 1, 4321), (1, 14, 1, 4321)])
        self.assertEqual(
            observed,
            {
                "kind": "macos-starttime",
                "seconds": 1_727_424_000,
                "microseconds": 987_654,
            },
        )


if __name__ == "__main__":
    unittest.main()
